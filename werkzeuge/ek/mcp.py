"""MCP-Server (Model Context Protocol) über stdio, nur Standardbibliothek.

Start: python3 -I werkzeuge/ek.py mcp [QUARTAL]

Angeboten werden:
- Werkzeuge (katalog.WERKZEUGE) mit Titel, Annotations (nur lesend) und strukturierter Ausgabe (structuredContent);
  GOP-Ergebnisse verweisen zusätzlich auf ihre Resource (resource_link).
- Resources: Antwortregeln, Feldglossar, BMV-Ä-Übersicht; Vorlagen ebm://{quartal}/gop/{nr},
  ebm://{quartal}/abschnitt/{nr}, ebm://{quartal}/ops/{code} als Markdown.
- Vorlagen (Prompts): ebm_frage, ebm_fallpruefung, ebm_folgenabschaetzung.
- Completions für die Argumente der Resource-Vorlagen und Prompts (GOP-Nummern, Arztgruppen, OPS-Codes).
Antwortregeln: docs/ANTWORTREGELN.md (als `instructions`).
"""
import json
import sys
import traceback

from .grundlagen import AUS, WURZEL, aktuelles_quartal
from .katalog import FELDER, HINWEIS, TITEL, WERKZEUGE, Katalog

VERSIONEN = ["2025-06-18", "2025-03-26", "2024-11-05"]
REGELN = (WURZEL / "docs" / "ANTWORTREGELN.md").read_text(encoding="utf-8")
ANNOTATIONS = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
MAX_TEXT = 60000  # Zeichen je Werkzeugergebnis im Textteil


class NichtGefunden(Exception):
    """Resource nicht vorhanden (JSON-RPC-Fehler -32002)."""


def arztgruppen_liste(quartal=None):
    """Gruppennamen ohne den ganzen Katalog zu laden (für Schema und Completions)."""
    try:
        f = AUS / (quartal or aktuelles_quartal()) / "arztgruppen.json"
        return json.loads(f.read_text(encoding="utf-8"))["gruppen"] if f.exists() else []
    except Exception:
        return []


def schema(params, quartal=None):
    props = {}
    for k, (t, d, _, *rest) in params.items():
        p = {"type": t, "description": d}
        if rest:
            werte = arztgruppen_liste(quartal) if rest[0] == "ARZTGRUPPEN" else rest[0]
            if werte:
                p["enum"] = werte
        props[k] = p
    return {"type": "object", "additionalProperties": False, "properties": props,
            "required": [k for k, (_, _, pflicht, *__) in params.items() if pflicht]}


PROMPTS = {
    "ebm_frage": ("Frage zum EBM oder BMV-Ä nach den Antwortregeln beantworten",
                  [("frage", "Die Frage", True)],
                  lambda a: f"{REGELN}\n\nFrage: {a.get('frage', '')}"),
    "ebm_fallpruefung": ("Prüfen, was in einem Behandlungsfall abrechenbar ist: Bewertung je Altersstufe, gegenseitige Ausschlüsse, Arztgruppe, Präambel",
                         [("gops", "GOP, durch Komma getrennt", True), ("alter", "Alter der Patientin oder des Patienten in Jahren", False),
                          ("arztgruppe", "Arztgruppe, z. B. Hausarzt", False)],
                         lambda a: (f"{REGELN}\n\nFallprüfung für die GOP {a.get('gops', '')}"
                                    + (f", Alter {a['alter']} Jahre" if a.get("alter") else "") + (f", Arztgruppe {a['arztgruppe']}" if a.get("arztgruppe") else "") + ".\n\n"
                                    "Vorgehen: 1. ebm_gop mit allen Nummern auf einmal (umfang=voll). 2. Für jede Nummer ebm_nebeneinander gegen alle anderen "
                                    "(b als Liste). 3. Bei Angabe der Arztgruppe ebm_arztgruppe je GOP. 4. Die Präambel des Kapitels mit ebm_abschnitt und "
                                    "filter=<GOP> abrufen. 5. Antwort mit Bewertung der passenden Altersstufe, eingetragenen Ausschlüssen samt Bezug, "
                                    "Bedingungen aus Anmerkungen und Präambel; fehlende Angaben als Annahme benennen.")),
    "ebm_folgenabschaetzung": ("Welche Stellen im EBM sind betroffen, wenn eine GOP geändert wird?",
                               [("nr", "GOP", True)],
                               lambda a: (f"{REGELN}\n\nFolgenabschätzung für eine Änderung der {a.get('nr', '')}.\n\n"
                                          "Vorgehen: 1. ebm_verweise (Erwähnungen und Anhangtabellen). 2. ebm_gop für die Position selbst. "
                                          "3. ebm_suche nach der Nummer, um Textstellen in Präambeln zu finden; Präambeln mit ebm_abschnitt und filter=<Nummer>. "
                                          "4. ebm_nebeneinander der Nummer gegen alle erwähnenden GOP als Liste. 5. Inhaltlich parallele Positionen "
                                          "(gleicher Titel in anderen Kapiteln) mit ebm_suche prüfen und als Einschätzung kennzeichnen.")),
}


class Server:
    def __init__(self, quartal=None):
        self.quartal = quartal
        self._k = None

    @property
    def k(self):
        if self._k is None:
            self._k = Katalog(self.quartal)
        return self._k

    @property
    def q(self):
        return self.quartal or aktuelles_quartal()

    # ---------- Werkzeuge ----------
    def werkzeuge(self):
        return [{"name": n, "title": TITEL.get(n, n), "description": d, "inputSchema": schema(ps, self.quartal),
                 "outputSchema": {"type": "object"}, "annotations": {"title": TITEL.get(n, n), **ANNOTATIONS}}
                for n, (d, ps, _) in WERKZEUGE.items()]

    def aufruf(self, name, args):
        if name not in WERKZEUGE:
            return self.fehler(f"Unbekanntes Werkzeug {name}. Verfügbar: {', '.join(WERKZEUGE)}")
        _, ps, fn = WERKZEUGE[name]
        fehlend = [k for k, (_, _, pflicht, *__) in ps.items() if pflicht and not args.get(k)]
        if fehlend:
            return self.fehler(f"Fehlende Angabe: {', '.join(fehlend)}")
        try:
            r = fn(self.k, args)
        except Exception as e:  # Fehler als Werkzeugergebnis, damit das Modell reagieren kann
            return self.fehler(f"Fehler: {e}")
        text = json.dumps(r, ensure_ascii=False, indent=1)
        if len(text) > MAX_TEXT:
            text = text[:MAX_TEXT] + f"\n… [gekürzt: {len(text):,} Zeichen; enger abfragen, z. B. umfang=kompakt oder filter]".replace(",", ".")
        inhalt = [{"type": "text", "text": text}]
        for nr in self.gop_nummern(r):
            inhalt.append({"type": "resource_link", "uri": f"ebm://{self.k.quartal}/gop/{nr}", "name": f"GOP {nr}",
                           "description": f"GOP {nr} als Markdown", "mimeType": "text/markdown"})
        return {"content": inhalt, "structuredContent": r, "isError": False}

    @staticmethod
    def gop_nummern(r):
        if r.get("gefunden") and r.get("nr") and r.get("belege"):
            return [r["nr"]]
        return [p["nr"] for p in r.get("positionen", []) if p.get("gefunden")]

    @staticmethod
    def fehler(text):
        return {"content": [{"type": "text", "text": text}], "isError": True}

    # ---------- Resources ----------
    FEST = {
        "ebm://regeln": ("Antwortregeln", "Regeln für Antworten mit diesem Katalog"),
        "ebm://felder": ("Felder erklärt", "Bedeutung der Felder in den Werkzeugergebnissen"),
        "ebm://bmv": ("Pauschalen aus dem BMV-Ä", "Alle erfassten Pauschalen außerhalb des EBM"),
    }

    def vorlagen(self):
        q = self.q
        return [{"uriTemplate": f"ebm://{q}/gop/{{nr}}", "name": "gop", "title": "Gebührenordnungsposition",
                 "description": f"GOP des EBM {q} als Markdown, z. B. ebm://{q}/gop/03000", "mimeType": "text/markdown"},
                {"uriTemplate": f"ebm://{q}/abschnitt/{{nr}}", "name": "abschnitt", "title": "Abschnitt oder Präambel",
                 "description": f"Abschnitt, Präambel oder Anhang des EBM {q} als Markdown, z. B. ebm://{q}/abschnitt/3.1", "mimeType": "text/markdown"},
                {"uriTemplate": f"ebm://{q}/ops/{{code}}", "name": "ops", "title": "OPS-Zuordnung (Anhang 2)",
                 "description": f"OPS-Code mit Kategorie und GOP-Zuordnung, z. B. ebm://{q}/ops/5-927.09", "mimeType": "text/markdown"}]

    def lesen(self, uri):
        from . import texte
        if uri == "ebm://regeln":
            return REGELN
        if uri == "ebm://felder":
            return "# Felder der Werkzeugergebnisse\n\n" + "\n".join(f"- **{k}:** {v}" for k, v in FELDER.items()) + f"\n\n{HINWEIS}\n"
        if uri == "ebm://bmv":
            return texte.bmv_md(self.k)
        teile = uri.removeprefix("ebm://").split("/", 2)
        if len(teile) != 3 or teile[0] != self.k.quartal:
            raise KeyError(uri)
        art, wert = teile[1], teile[2]
        if art == "gop":
            if not self.k.gop(wert).get("gefunden"):
                raise KeyError(uri)
            return texte.gop_md(self.k, wert)
        if art == "abschnitt":
            r = self.k.knoten(wert, grenze=100000)
            if not r.get("gefunden"):
                raise KeyError(uri)
            z = []
            for t in r["treffer"]:
                z += [f"# {t['nr']} {t['titel']}", "", f"Quartal {self.k.quartal.replace('-', '/Q')} · {t['pfad']}", ""]
                for a in t["abschnitte"]:
                    z += ([f"## {a['ueberschrift']}", ""] if a.get("ueberschrift") else []) + [a.get("text", ""), ""]
                if t["enthaelt"]:
                    z += ["Enthält: " + "; ".join(t["enthaelt"]), ""]
            return "\n".join(z + ["---", HINWEIS, ""])
        if art == "ops":
            r = self.k.ops(code=wert)
            if not r.get("gefunden"):
                raise KeyError(uri)
            z = [f"# OPS {r['nr']} — {r['titel']}", "", f"Anhang 2 EBM {self.k.quartal.replace('-', '/Q')} · Kategorie {r['kategorie']} · Spalte §115b: {r['p115b']}", "",
                 "| Art | GOP | Bezeichnung | Punkte | Kalk. Zeit | Prüfzeit |", "|---|---|---|---|---|---|"]
            z += [f"| {g['art']} | {g['gop']} | {g['bezeichnung']} | {g['punkte']} | {g['kalk']} | {g['pruef']} |" for g in r["zuordnung"]]
            return "\n".join(z + ["", "---", HINWEIS, ""])
        raise KeyError(uri)

    # ---------- Completions ----------
    def vervollstaendigen(self, ref, arg):
        name, wert = arg.get("name"), (arg.get("value") or "").strip()
        if name in ("nr", "gops"):
            wert = wert.split(",")[-1].strip()
            if ref.get("uri", "").endswith("/abschnitt/{nr}"):
                werte = sorted({n["nr"] for n in self.k.index["knoten"] if n["typ"] != "gop" and n["nr"]})
            else:
                werte = sorted({n["nr"] for n in self.k.index["knoten"] if n["typ"] == "gop"})
            treffer = [w for w in werte if w.startswith(wert.upper())]
        elif name == "arztgruppe":
            treffer = [g for g in arztgruppen_liste(self.quartal) if wert.lower() in g.lower()]
        elif name == "code":
            d = self.k.ops_daten
            treffer = [o["nr"] for o in d["knoten"] if o["nr"].startswith(wert)] if d else []
        else:
            treffer = []
        return {"completion": {"values": treffer[:100], "total": len(treffer), "hasMore": len(treffer) > 100}}

    # ---------- Protokoll ----------
    def behandeln(self, m):
        meth, p = m.get("method"), m.get("params") or {}
        if meth == "initialize":
            v = p.get("protocolVersion")
            return {"protocolVersion": v if v in VERSIONEN else VERSIONEN[0],
                    "capabilities": {"tools": {}, "prompts": {}, "resources": {}, "completions": {}},
                    "serverInfo": {"name": "ebm-katalog", "title": "Offener EBM-Katalog (KI-gebaut, nicht amtlich)", "version": "0.2.0"},
                    "instructions": REGELN}
        if meth == "ping":
            return {}
        if meth == "tools/list":
            return {"tools": self.werkzeuge()}
        if meth == "tools/call":
            return self.aufruf(p.get("name"), p.get("arguments") or {})
        if meth == "resources/list":
            return {"resources": [{"uri": u, "name": u.removeprefix("ebm://"), "title": t, "description": d,
                                   "mimeType": "text/markdown"} for u, (t, d) in self.FEST.items()]}
        if meth == "resources/templates/list":
            return {"resourceTemplates": self.vorlagen()}
        if meth == "resources/read":
            uri = p.get("uri", "")
            try:
                text = self.lesen(uri)
            except KeyError:
                raise NichtGefunden(f"Resource nicht gefunden: {uri}")
            return {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": text}]}
        if meth == "prompts/list":
            return {"prompts": [{"name": n, "description": d, "arguments": [{"name": a, "description": ad, "required": r} for a, ad, r in args]}
                                for n, (d, args, _) in PROMPTS.items()]}
        if meth == "prompts/get":
            name = p.get("name", "ebm_frage")
            if name not in PROMPTS:
                raise ValueError(f"Unbekannte Vorlage {name}")
            d, _, fn = PROMPTS[name]
            return {"description": d, "messages": [{"role": "user", "content": {"type": "text", "text": fn(p.get("arguments") or {})}}]}
        if meth == "completion/complete":
            return self.vervollstaendigen(p.get("ref") or {}, p.get("argument") or {})
        raise LookupError(meth)


def main(argv=None):
    s = Server(argv[0] if argv else None)
    for zeile in sys.stdin:
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            m = json.loads(zeile)
        except json.JSONDecodeError:
            antwort = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
            print(json.dumps(antwort), flush=True); continue
        if "id" not in m:  # Benachrichtigung
            continue
        try:
            antwort = {"jsonrpc": "2.0", "id": m["id"], "result": s.behandeln(m)}
        except LookupError as e:
            antwort = {"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32601, "message": f"Methode unbekannt: {e}"}}
        except NichtGefunden as e:
            antwort = {"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32002, "message": str(e)}}
        except ValueError as e:
            antwort = {"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32602, "message": str(e)}}
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            antwort = {"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32603, "message": str(e)}}
        print(json.dumps(antwort, ensure_ascii=False), flush=True)
    return 0
