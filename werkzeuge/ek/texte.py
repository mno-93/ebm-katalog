"""Statische Textausgabe für KI-Systeme ohne MCP (Webabruf, Upload in Wissensspeicher).

Ziel: Was der MCP-Server zur Laufzeit errechnet (Bedingungen aus Präambeln, Zeiten aus Anhang 3, aufgelöste
Abschnittsausschlüsse, Ausschlüsse in Gegenrichtung, Rückverweise), steht hier vorberechnet in verlinkten Dateien.
Eine KI, die nur Links abrufen kann, folgt den Links statt Werkzeuge aufzurufen.

Schreibt nach ausgabe/site/:
  llms.txt                     Einstieg: Wegweiser, Antwortregeln ohne Werkzeuge, Verweise
  texte/inhalt.md              Gliederung des EBM mit Links auf alle Abschnitte
  texte/register.md            Register der Kapitel; texte/register/<KK>.md: alle GOP eines Kapitels mit Titel und Punkten
  texte/gop/<Nr>.md            je GOP alle Angaben, Bedingungen aus Präambeln, Ausschlüsse beider Richtungen
  texte/abschnitt/<Pfad>.md    je Abschnitt, Präambel, Allgemeine Bestimmung, Anhang
  texte/ops.md, texte/ops/<Gruppe>.md   Anhang 2: OPS-Code -> GOP
  texte/bmv.md                 Pauschalen aus dem BMV-Ä mit Geltungsbereich
  texte/bmv-gliederung.md      Gliederung des Vertragstexts: Überschriften mit Link auf den Wortlaut und die PDF-Seite
  texte/vertrag/<Datei>.md     Wortlaut des BMV-Ä und seiner Anlagen (Textauszug aus rohdaten/bmv), lange Dokumente in Teilen
  texte/stichworte.md          Alltagsbegriffe, Begriffsbestimmungen, Themen außerhalb des Katalogs
  texte/ebm-<Q>.md             alles in einer Datei (GOP, Abschnitte, Präambeln, BMV-Ä-Pauschalen)
"""
import re
from collections import defaultdict

from .grundlagen import AUS
from .katalog import HINWEIS, Katalog, synonyme

BMV_SEITE = "https://www.kbv.de/infothek/rechtsquellen/bundesmantelvertrag"
ROEMISCH = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


class Texte:
    def __init__(self, k):
        self.k = k
        self.q = k.quartal.replace("-", "/Q")
        self.slugs = {}
        for n in k.index["knoten"]:
            if n["typ"] != "gop":
                nr = re.sub(r"[^\w.]+", "-", n["nr"] or "").strip("-") or str(k.pos[n["knotenId"]])
                self.slugs[n["knotenId"]] = f"{ROEMISCH[int(n['teil'])]}-{nr}"
        self.vertrag = (f"[Gliederung des BMV-Ä mit Seitenlinks](bmv-gliederung.md)" if k.bmvtext.verfuegbar
                        else f"[Bundesmantelvertrag und Anlagen auf kbv.de]({BMV_SEITE})")
        self.gops = sorted({n["nr"] for n in k.index["knoten"] if n["typ"] == "gop"})
        # Ausschlüsse in Gegenrichtung: bei anderen GOP eingetragen
        self.gegen = defaultdict(list)
        for nr in self.gops:
            n, _ = k.gop_knoten(nr)
            for z in k.inhalt(n["knotenId"]).get("ausschluesse", []):
                for l in z["leistungen"]:
                    if l["nr"] != nr:
                        self.gegen[l["nr"]].append((nr, z["bezug"]))

    # ---------- Links ----------
    def titel(self, n):
        return n["titel"] or n["baumtitel"]

    def link(self, kid, von="gop"):
        """Markdown-Link auf einen Knoten, relativ zu texte/<von>/."""
        n = self.k.K[kid]
        if n["typ"] == "gop":
            h = self.k.gop_knoten(n["nr"])[0]
            return f"[{n['nr']}](../gop/{n['nr']}.md)" if h else n["nr"]
        return f"[{n['nr']} {self.titel(n)}](../abschnitt/{self.slugs[kid]}.md)".replace("[ ", "[")

    def gop_link(self, nr):
        return f"[{nr}](../gop/{nr}.md)" if nr in self.k.nr and self.k.gop_knoten(nr)[0] else nr

    def pfad_links(self, n):
        out, p = [], self.k.K.get(n["eltern"])
        while p:
            out.insert(0, p); p = self.k.K.get(p["eltern"])
        return out

    def praeambeln(self, n):
        """Präambeln der übergeordneten Abschnitte und Kapitel (von innen nach außen)."""
        out = []
        for p in reversed(self.pfad_links(n)):
            for c in p["kinder"]:
                if re.search(r"präambel", (self.titel(self.k.K[c]) or "").lower()):
                    out.append(c)
        return out

    def abschnitt_gops(self, kap):
        """Alle GOP unterhalb eines Abschnitts aus einem Kapitel-Ausschluss."""
        ziele = set(kap.get("k", "").split("_"))
        start = [n for n in self.k.index["knoten"] if n["knotenId"] in ziele] or [n for n in self.k.nr.get(kap.get("nr"), []) if n["typ"] != "gop"]
        out, stapel = [], [c for s in start[:1] for c in s["kinder"]]
        while stapel:
            c = self.k.K[stapel.pop(0)]
            if c["typ"] == "gop" and c["nr"] not in out:
                out.append(c["nr"])
            stapel += [x for x in c["kinder"] if self.k.K[x]["typ"] != "gop"] if c["typ"] != "gop" else []
        return sorted(out)

    # ---------- Seiten ----------
    def kopf(self, titel, n=None):
        z = [f"# {titel}", "", f"EBM, Quartal {self.q}. KI-gebaut, nicht amtlich — verbindlich ist ebm.kbv.de.", ""]
        if n is not None:
            pfad = self.pfad_links(n)
            if pfad:
                z += ["Pfad: " + " › ".join(self.link(p["knotenId"]) for p in pfad), ""]
        return z

    def gop_md(self, nr):
        k, r = self.k, self.k.gop(nr)
        n, _ = k.gop_knoten(nr)
        z = self.kopf(f"GOP {r['nr']} — {r['titel']}", n)
        if r["bewertung"]:
            z += ["## Bewertung", "", "| Bedingung | Punkte | Euro |", "|---|---|---|"]
            z += [f"| {b['bedingung'] or '—'} | {b.get('punkte') or '—'} | {b.get('euro') or '—'} |" for b in r["bewertung"]] + [""]
            z += ["Euro mit dem bundeseinheitlichen Orientierungswert; regionale Punktwerte können abweichen.", ""]
        elif r["bewertung_hinweis"]:
            z += [f"Bewertung: {r['bewertung_hinweis']}", ""]
        if r["merkmale"]:
            z += ["Merkmale (Kennzeichen der Online-Ansicht, Bedeutung dort nicht erläutert): "
                  + "; ".join(f"{m['text']} ({'ja' if m['zutreffend'] else 'nein'})" for m in r["merkmale"]), ""]
        for a in r["abschnitte"]:
            z += [f"## {a['ueberschrift'] or 'Text'}", "", a["text"], ""]
        # Regeln außerhalb der GOP
        pr = self.praeambeln(n)
        bed = r.get("bedingungen_aus_praeambeln", [])
        z += ["## Regeln außerhalb dieser GOP", "",
              "Begrenzungen stehen oft in Präambeln und Allgemeinen Bestimmungen, nicht bei der GOP. "
              "Die folgenden Sätze nennen diese GOP und enthalten eine Bedingung (ausschließlich, nur, Genehmigung, nicht berechnungsfähig …). "
              "Die Auswahl ist maschinell; im Zweifel die verlinkte Stelle lesen.", ""]
        if bed:
            for b in bed:
                e = f"- **{self.link(b['knotenId'])}**"
                if b.get("einleitung"):
                    e += f" — Einleitung der Liste: „{b['einleitung']}“"
                e += f"\n  „{b['satz']}“"
                if b.get("gleichlautend_in"):
                    e += f"\n  Gleichlautend in: {', '.join(b['gleichlautend_in'])}"
                z.append(e)
        else:
            z.append("- Keine Bedingungssätze gefunden, die diese GOP ausdrücklich nennen.")
        if pr:
            z += ["", "Präambeln der übergeordneten Abschnitte (immer prüfen): " + ", ".join(self.link(p) for p in pr)]
        z += ["", "Allgemeine Bestimmungen: [Gliederung](../inhalt.md), Abschnitt I; Begriffe wie Behandlungsfall, Krankheitsfall, Sitzung: [Stichworte](../stichworte.md).", ""]
        # Ausschlüsse
        z += ["## Abrechnungsausschlüsse", ""]
        d = k.inhalt(n["knotenId"])
        if d.get("ausschluesse"):
            z += ["Bei dieser GOP eingetragen:", ""]
            for a in d["ausschluesse"]:
                teile = []
                if a["leistungen"]:
                    teile.append(", ".join(self.gop_link(x["nr"]) for x in a["leistungen"]))
                for kap in a["kapitel"]:
                    g = self.abschnitt_gops(kap)
                    teile.append(f"Abschnitt {kap['nr']}" + (f" (enthält {', '.join(g)})" if g else ""))
                z.append(f"- {a['bezug']}: " + "; ".join(teile))
            z.append("")
        else:
            z += ["Bei dieser GOP ist kein Ausschluss eingetragen.", ""]
        geg = [(x, b) for x, b in self.gegen.get(nr, []) if not any(x in [l["nr"] for l in a["leistungen"]] for a in d.get("ausschluesse", []))]
        if geg:
            nach = defaultdict(list)
            for x, b in geg:
                nach[b].append(x)
            z += ["Nur bei der anderen GOP eingetragen (gilt ebenfalls):", ""]
            z += [f"- {b}: {', '.join(self.gop_link(x) for x in sorted(set(xs)))}" for b, xs in nach.items()] + [""]
        z += ["Kein eingetragener Ausschluss ist keine Zusage der Berechnungsfähigkeit: Präambeln, Allgemeine Bestimmungen und Anmerkungen gelten zusätzlich.", ""]
        if r.get("zeiten"):
            t = r["zeiten"]
            z += ["## Zeiten (Anhang 3)", "", f"Kalkulationszeit {t['kalkulationszeit']} Min., Prüfzeit {t['pruefzeit']} Min., Eignung der Prüfzeit: {t['eignung']}"
                  + (f", Kennzeichen {t['kennzeichen']}" if t.get("kennzeichen") else "") + ". KA = keine Kalkulationszeit, ./. = keine Prüfzeit.", ""]
        if r.get("zuschlaege"):
            z += ["## Zuschläge und Zusatzpauschalen, die diese GOP nennen", ""] + [f"- {self.gop_link(s.split(' ', 1)[0])} {s.split(' ', 1)[1]}" for s in r["zuschlaege"]] + [""]
        refs = d.get("referenziert_von", [])
        if refs:
            als_aus = [x for x in refs if any(l["nr"] == nr for a in k.inhalt(x).get("ausschluesse", []) for l in a["leistungen"])]
            im_text = [x for x in refs if x not in als_aus]
            z += ["## Erwähnt in", ""]
            if im_text:
                z += ["Im Text (Leistungsinhalt, Bestimmung, Anmerkung, Präambel): " + ", ".join(self.link(x) for x in im_text), ""]
            if als_aus:
                z += ["Nur als Abrechnungsausschluss: " + ", ".join(self.link(x) for x in als_aus), ""]
        ber = k.verweise(nr).get("ueber_bereich", [])
        if ber:
            z += ["Stellen, die einen übergeordneten Abschnitt oder das Kapitel dieser GOP nennen (Nummern kommen auch in den Allgemeinen Bestimmungen vor; prüfen):", ""]
            z += [f"- {b['bereich']} ({b['anzahl']} Stellen): {', '.join(b['erwaehnt_in'][:15])}" + (" …" if b["anzahl"] > 15 else "") for b in ber] + [""]
        if r.get("ops_anzahl"):
            z += ["## Anhang 2 (OPS)", "", f"{r['ops_anzahl']} OPS-Codes sind dieser GOP zugeordnet; Liste nach Code-Gruppe in [Anhang 2](../ops.md).", ""]
        if r.get("arztgruppen") is not None:
            z += ["## Arztgruppen (Filter der Online-Ansicht)", "", "Sichtbarkeit im Filter ist keine Abrechnungsberechtigung; die Berechtigung regeln die Präambeln.", "",
                  ", ".join(r["arztgruppen"]) or "In keinem Arztgruppenfilter sichtbar.", ""]
        if r["bmv_bezuege"]:
            z += ["## Bezüge zum BMV-Ä", "", ", ".join(b.replace("bmv:", "Pauschale ").replace("anl:", "Anlage ") for b in r["bmv_bezuege"]) + " — siehe [Pauschalen aus dem BMV-Ä](../bmv.md).", ""]
        z += ["---", f"Herkunft: EBM-Online-Ansicht https://ebm.kbv.de/, Knotenkennung {n['knotenId']}. {HINWEIS}", ""]
        return "\n".join(z)

    def abschnitt_md(self, kid):
        k, n = self.k, self.k.K[kid]
        z = self.kopf(f"{n['nr']} {self.titel(n)}".strip(), n)
        for a in k._abschnitte(kid):
            z += ([f"## {a['ueberschrift']}", ""] if a["ueberschrift"] else []) + [a["text"], ""]
        if n["kinder"]:
            z += ["## Enthält", ""]
            for c in n["kinder"]:
                cn = k.K[c]
                if cn["typ"] == "gop":
                    p = (cn.get("bewertung") or {}).get("punkte")
                    z.append(f"- {self.gop_link(cn['nr'])} {cn['titel']}" + (f" ({p} Punkte)" if p else ""))
                else:
                    z.append(f"- {self.link(c)}")
            z.append("")
        refs = k.inhalt(kid).get("referenziert_von", [])
        if refs:
            z += ["## Erwähnt in", "", ", ".join(self.link(x) for x in refs), ""]
        z += ["---", f"Herkunft: EBM-Online-Ansicht https://ebm.kbv.de/, Knotenkennung {kid}. {HINWEIS}", ""]
        return "\n".join(z)

    def inhalt_md(self):
        k = self.k
        z = ["# Gliederung des EBM", "", f"Quartal {self.q}. Alle Abschnitte, Präambeln, Allgemeinen Bestimmungen und Anhänge mit Link. "
             "GOP je Kapitel stehen im [Register](register.md). KI-gebaut, nicht amtlich.", ""]
        def gehe(kid, tiefe):
            n = k.K[kid]
            if n["typ"] == "gop":
                return
            if tiefe == 0:
                z.extend(["", f"## {n['nr']} {self.titel(n)}", ""])
            else:
                z.append("  " * (tiefe - 1) + f"- [{n['nr']} {self.titel(n)}](abschnitt/{self.slugs[kid]}.md)".replace("[ ", "["))
            for c in n["kinder"]:
                gehe(c, tiefe + 1)
        for w in k.index["wurzeln"]:
            gehe(w, 0)
        return "\n".join(z) + "\n"

    def register(self):
        k = self.k
        kap = defaultdict(list)
        for nr in self.gops:
            kap[nr[:2]].append(nr)
        seiten = {}
        idx = ["# Register der Gebührenordnungspositionen", "", f"Quartal {self.q}, {len(self.gops)} GOP. Je Kapitel (erste zwei Ziffern) eine Liste mit Titel und Punkten. "
               "Wer eine Leistung sucht, aber die Nummer nicht kennt: Kapitel nach Fachgebiet wählen und die Titel lesen; "
               "Alltagsbegriffe in den [Stichworten](stichworte.md). KI-gebaut, nicht amtlich.", "", "| Kapitel | GOP | Bereich | Liste |", "|---|---|---|---|"]
        for kk, nrs in sorted(kap.items()):
            n, _ = k.gop_knoten(nrs[0])
            pfad = self.pfad_links(n)
            bereich = next((f"{p['nr']} {self.titel(p)}" for p in pfad if re.fullmatch(r"\d+", p["nr"] or "")), self.titel(pfad[-1]) if pfad else "")
            idx.append(f"| {kk} | {len(nrs)} | {bereich} | [register/{kk}.md](register/{kk}.md) |")
            z = [f"# GOP {nrs[0]} bis {nrs[-1]}", "", f"Quartal {self.q}. {bereich}. KI-gebaut, nicht amtlich.", "", "| GOP | Titel | Punkte | Abschnitt |", "|---|---|---|---|"]
            for nr in nrs:
                g, kinder = k.gop_knoten(nr)
                p = (g.get("bewertung") or {}).get("punkte") or "/".join(filter(None, ((c.get("bewertung") or {}).get("punkte") for c in kinder))) or "—"
                el = k.K.get(g["eltern"])
                ab = f"[{el['nr']}](../abschnitt/{self.slugs[el['knotenId']]}.md)" if el and el["typ"] != "gop" else ""
                z.append(f"| [{nr}](../gop/{nr}.md) | {g['titel'].replace('|', '/')} | {p} | {ab} |")
            seiten[kk] = "\n".join(z) + "\n"
        return "\n".join(idx) + "\n", seiten

    def titelliste(self):
        z = ["# Alle GOP-Titel", "", f"Quartal {self.q}. Eine Zeile je GOP: Nummer, Titel, Abschnitt. Zum Durchsuchen nach Wörtern; Details über den Link. KI-gebaut, nicht amtlich.", ""]
        for nr in self.gops:
            g, _ = self.k.gop_knoten(nr)
            el = self.k.K.get(g["eltern"])
            z.append(f"- [{nr}](gop/{nr}.md) {g['titel']}" + (f" — {el['nr']} {self.titel(el)}" if el and el["typ"] != "gop" else ""))
        return "\n".join(z) + "\n"

    def ops(self):
        d = self.k.ops_daten
        if not d:
            return None, {}
        gruppen = defaultdict(list)
        for o in d["knoten"]:
            if o.get("gops"):
                gruppen[o["nr"][:5].rstrip(".")].append(o)
        idx = ["# Anhang 2: OPS-Codes und zugeordnete GOP", "", f"Quartal {self.q}. Je Code-Gruppe (erste fünf Zeichen, z. B. 5-927) eine Liste. "
               "Spalte §115b und Kategorie 1:1 aus der Anhang-2-Ansicht; die Online-Ansicht erläutert §115b nicht — nicht deuten. KI-gebaut, nicht amtlich.", ""]
        seiten = {}
        for g, os_ in sorted(gruppen.items()):
            idx.append(f"- [{g}](ops/{g}.md) ({len(os_)} Codes)")
            z = [f"# OPS {g}…: Zuordnung nach Anhang 2 EBM", "", f"Quartal {self.q}. KI-gebaut, nicht amtlich.", ""]
            for o in os_:
                z += [f"## {o['nr']} {o['titel']}", "", f"Kategorie: {o.get('kategorie') or '—'} · §115b: {o.get('p115b') or '—'}", ""]
                for x in o["gops"]:
                    extra = " · ".join(f"{k_} {v}" for k_, v in x.items() if k_ not in ("gop", "art") and v not in (None, ""))
                    z.append(f"- {self.gop_link(x['gop'])} ({x.get('art') or '—'})" + (f" — {extra}" if extra else ""))
                z.append("")
            seiten[g] = "\n".join(z)
        return "\n".join(idx) + "\n", seiten

    def bmv_md(self):
        d = self.k.bmv_daten
        z = ["# Pauschalen aus dem BMV-Ä außerhalb des EBM", "", f"{HINWEIS}", "",
             "Von Hand aus den PDF auf kbv.de erfasst. Regeln, Ansprüche und Berechtigungen stehen im Vertragstext: " + self.vertrag + ".", ""]
        for a in d["anlagen"]:
            z += [f"## Anlage {a['anlage']}: {a['titel']}", "", f"Fassung: {a.get('fassung') or '—'}. Höhe: {a.get('hoehe') or '—'}." + (f" Status: {a['status']}." if a.get("status") else ""), ""]
            for pid in a["pauschalen"]:
                p = d["nach_id"][pid]
                betrag = "; ".join(f"{(b['bedingung'] + ': ') if b['bedingung'] else ''}{b['euro']:.2f} €".replace(".", ",") for b in p["betrag"] or []) or "regional"
                f = p["fundstelle"]
                url = f"{f['url']}#page={f['seite']}" if f.get("url") else f["datei"]
                z.append(f"- **{p['nr'] or 'ohne Nummer'}** {p['titel']} — {betrag}" + (f" — {p['abrechnung']}" if p.get("abrechnung") else "") + f" ([{f['datei']}, S. {f['seite']}]({url}))")
                for li in p.get("leistungsinhalt") or []:
                    z.append(f"  - Leistungsinhalt: {li}")
                for k_, v in (p.get("geltung") or {}).items():
                    z.append(f"  - {k_.replace('_', ' ')}: {', '.join(v) if isinstance(v, list) else v}")
                for x in p["ausschluesse"]:
                    z.append(f"  - Ausschluss {x['bezug']}: {', '.join(self.gop_link(y) for y in x['nr'])}")
            z.append("")
        z += ["## Anlagen ohne eigene Pauschale", ""] + [f"- Anlage {x['anlage']} ({x['titel']}): {x['befund']}" for x in d["ohne_eigene_pauschale"]] + [""]
        if d.get("nicht_im_katalog"):
            z += ["## Themen außerhalb des Katalogs", ""] + [f"- **{x['thema']}:** {x['hinweis']}" for x in d["nicht_im_katalog"]] + [""]
        return "\n".join(z).replace("](../gop/", "](gop/")

    TEIL = 80000  # Zeichen je Vertragsseite; längere Dokumente werden an Überschriften geteilt

    def vertragsseiten(self):
        """Wortlaut je Dokument des BMV-Ä: {Dateiname: Text}; lange Dokumente in Teilen. Zusätzlich die Zuordnung Block -> Datei."""
        b = self.k.bmvtext
        seiten, ort = {}, {}
        hinweis = ("Textauszug aus der PDF auf kbv.de, maschinell gezogen (KI-gebaut). Verbindlich ist die PDF; Seitenumbrüche, "
                   "Tabellen und Silbentrennung können fehlerhaft sein. Seitenangaben beziehen sich auf die PDF.")
        for doc in b.dokumente():
            st = doc["dokument"]
            url = b.liste.get(st, {}).get("url")
            bl = [x for x in b.bloecke if x["stamm"] == st]
            teile, akt, laenge = [], [], 0
            for x in bl:
                if akt and laenge + len(x["text"]) > self.TEIL and (x["ueberschrift"] != akt[-1]["ueberschrift"] or laenge > 1.5 * self.TEIL):
                    teile.append(akt); akt, laenge = [], 0
                akt.append(x); laenge += len(x["text"])
            if akt:
                teile.append(akt)
            namen = [f"{st}.md"] if len(teile) == 1 else [f"{st}-{i}.md" for i in range(1, len(teile) + 1)]
            for name, teil in zip(namen, teile):
                z = [f"# {doc['titel']}" + (f" (Teil {namen.index(name) + 1} von {len(namen)})" if len(namen) > 1 else ""), "",
                     f"Datei {doc['datei']}" + (f", PDF: {url}" if url else "") + f". {hinweis}", ""]
                if len(namen) > 1:
                    z += ["Teile: " + " · ".join(f"[{i + 1}]({n})" for i, n in enumerate(namen)) + " · [Gliederung](../bmv-gliederung.md)", ""]
                kopf = object()
                for x in teil:
                    ort[id(x)] = name
                    if x["ueberschrift"] != kopf:
                        kopf = x["ueberschrift"]
                        if kopf:
                            z += [f"## {kopf}", ""]
                    link = f"[S. {x['seite']}]({url}#page={x['seite']})" if url else f"S. {x['seite']}"
                    z += [f"{x['text']} ({link})", ""]
                seiten[name] = "\n".join(z)
            if len(namen) > 1:
                seiten[f"{st}.md"] = "\n".join([f"# {doc['titel']}", "", f"Datei {doc['datei']}" + (f", PDF: {url}" if url else "") + f". {hinweis}", "",
                                                 "Das Dokument ist in Teile geteilt:", ""] + [f"- [Teil {i + 1}]({n})" for i, n in enumerate(namen)] + [""])
        return seiten, ort

    def bmv_gliederung(self, ort):
        b = self.k.bmvtext
        if not b.verfuegbar:
            return None
        z = ["# Gliederung des BMV-Ä und seiner Anlagen", "", "Überschriften mit Seite. Der Link führt auf den Wortlaut im Katalog (Textauszug), "
             "„PDF“ auf die Seite der verbindlichen PDF auf kbv.de. Ansprüche, Berechtigungen, Geltungsbereiche und Verfahren regelt oft der Vertrag, "
             "nicht der EBM. KI-gebaut: Überschriften maschinell erkannt.", ""]
        gesehen = set()
        for doc in b.dokumente():
            bl = [x for x in b.bloecke if x["stamm"] == doc["dokument"] and x["ueberschrift"]]
            url = b.liste.get(doc["dokument"], {}).get("url")
            z += [f"## {doc['titel']}", "", f"Wortlaut: [vertrag/{doc['dokument']}.md](vertrag/{doc['dokument']}.md)" + (f" · PDF: {url}" if url else ""), ""]
            for x in bl:
                key = (doc["dokument"], x["ueberschrift"])
                if key in gesehen:
                    continue
                gesehen.add(key)
                z.append(f"- [{x['ueberschrift']}](vertrag/{ort[id(x)]}) — S. {x['seite']}" + (f" ([PDF]({url}#page={x['seite']}))" if url else ""))
            z.append("")
        return "\n".join(z)

    def stichworte(self):
        k = self.k
        z = ["# Stichworte", "", "Wegweiser von Alltagsbegriffen zu den Fundstellen. KI-gebaut, nicht amtlich.", "",
             "## Alltagsbegriffe", "", "| Begriff | im Katalog unter |", "|---|---|"]
        z += [f"| {a} | {b} |" for a, b in sorted(synonyme().items())]
        z += ["", "## Begriffsbestimmungen (Allgemeine Bestimmungen)", ""]
        ab = [n for n in k.index["knoten"] if n["teil"] == "0" and n["typ"] != "gop"]
        z += [f"- {self.link(n['knotenId'])}".replace("](../", "](") for n in ab if re.match(r"^3(\.\d+)?$", n["nr"] or "")]
        z += ["", "Der Behandlungsfall ist zusätzlich in § 21 BMV-Ä bestimmt, siehe " + self.vertrag + ".", ""]
        d = k.bmv_daten
        if d and d.get("nicht_im_katalog"):
            z += ["## Nicht im Katalog", ""] + [f"- **{x['thema']}** (Stichwörter: {', '.join(x['stichwoerter'])}): {x['hinweis']}" for x in d["nicht_im_katalog"]] + [""]
        diga = [n for n in k.index["knoten"] if n["typ"] == "gop" and re.search(r"\bDiGA\b", n["titel"] or "")]
        if diga:
            z += ["## Digitale Gesundheitsanwendungen (DiGA)", "",
                  "Für einzelne DiGA gibt es eigene GOP im EBM (Name im Titel). Für weitere DiGA gilt die BMV-Ä-Pauschale 86700, aber nur für die dort genannten DiGA: [BMV-Ä-Pauschalen](bmv.md). "
                  "Erst die GOP-Liste, dann die 86700 prüfen.", ""]
            z += [f"- [{n['nr']}](gop/{n['nr']}.md) {n['titel']}" for n in sorted({n['nr']: n for n in diga}.values(), key=lambda n: n["nr"])] + [""]
        z += ["## Wo steht was?", "",
              f"- Leistung nach Wort suchen: [titel.md](titel.md) enthält alle GOP-Titel in einer Datei (eine Zeile je GOP), Volltext in [ebm-{k.quartal}.md](ebm-{k.quartal}.md).",
              "- Nummer bekannt: `gop/<Nummer>.md`, z. B. [gop/03000.md](gop/03000.md).",
              "- Nummer unbekannt: [Register](register.md) nach Kapitel, [Gliederung](inhalt.md) nach Abschnitt.",
              "- Pauschale nicht im EBM (z. B. Onkologie, DiGA, TI-Pauschale, Kurarzt): [BMV-Ä-Pauschalen](bmv.md).",
              "- OPS-Code: [Anhang 2](ops.md).", ""]
        return "\n".join(z)


def llms_txt(k, mit_bmv_gliederung):
    q = k.quartal.replace("-", "/Q")
    return "\n".join([
        "# Offener EBM-Katalog", "",
        f"> Maschinenlesbarer Spiegel der EBM-Online-Ansicht (Quartal {q}) mit Arztgruppenfilter, Anhang 2 (OPS) und den Pauschalen des BMV-Ä außerhalb des EBM. {HINWEIS}", "",
        "## Wegweiser", "",
        "Alle Texte sind Markdown und untereinander verlinkt. Für eine Antwort den Links folgen:", "",
        "1. Nummer bekannt: `texte/gop/<Nummer>.md` (z. B. [texte/gop/03000.md](texte/gop/03000.md)). Die Seite enthält Bewertung, Leistungsinhalt, Bestimmungen, "
        "Ausschlüsse in beiden Richtungen (Abschnittsausschlüsse aufgelöst), Zeiten aus Anhang 3, Zuschläge, Rückverweise und — wichtig — "
        "**Regeln außerhalb dieser GOP**: Sätze aus Präambeln und Allgemeinen Bestimmungen, die die GOP mit einer Bedingung nennen, und Links auf die Präambeln.",
        "2. Nummer unbekannt: [texte/titel.md](texte/titel.md) (alle GOP-Titel in einer Datei, nach Wörtern durchsuchen), [texte/register.md](texte/register.md) (GOP je Kapitel), [texte/inhalt.md](texte/inhalt.md) (Gliederung), "
        "[texte/stichworte.md](texte/stichworte.md) (Alltagsbegriffe, Begriffsbestimmungen, Themen außerhalb des Katalogs).",
        "3. Pauschalen außerhalb des EBM (Onkologie, DiGA, TI, Kurarzt …): [texte/bmv.md](texte/bmv.md)."
        + (" Vertragstext des BMV-Ä und seiner Anlagen im Wortlaut: [texte/bmv-gliederung.md](texte/bmv-gliederung.md) (Überschriften mit Link auf den Text, z. B. § 29a Medikationsplan, und auf die PDF-Seite)." if mit_bmv_gliederung else ""),
        "4. OPS-Code: [texte/ops.md](texte/ops.md).", "",
        "## Antwortregeln", "",
        "1. Nur aus diesen Texten (und den verlinkten Verträgen auf kbv.de) antworten. Was dort nicht steht, ist „nicht im Katalog“ — nicht aus dem Gedächtnis ergänzen.",
        "2. Jede Aussage mit Beleg: Quartal, Nummer, Fundstelle (Pfad im EBM bzw. Dokument und Seite des BMV-Ä).",
        f"3. Der Katalog bildet das Quartal {q} ab; andere Zeiträume als nicht abgedeckt kennzeichnen.",
        "4. „Kein Ausschluss eingetragen“ ist keine Erlaubnis. Vor einer Antwort zur Abrechenbarkeit den Abschnitt „Regeln außerhalb dieser GOP“ und die verlinkten Präambeln lesen.",
        "5. Regionale Werte nicht beziffern; Euro-Werte gelten mit dem bundeseinheitlichen Orientierungswert.",
        "6. Keine Einzelfallberatung; im Einzelfall an die Abrechnungsberatung der Kassenärztlichen Vereinigung verweisen.",
        "7. Grenzen nennen: KI-gebaut, nicht amtlich; Qualitätssicherungsvereinbarungen, regionale Verträge und Selektivverträge sind nicht enthalten.",
        "8. Gleiche Abschnittsnummern gibt es in den Allgemeinen Bestimmungen (Pfad I) und in den Kapiteln; den Pfad nennen.",
        "9. Merkmale und die Spalte §115b werden nicht erläutert; unverändert wiedergeben, nicht deuten. Sichtbarkeit im Arztgruppenfilter ist keine Berechtigung.",
        "10. Fehlen Alter, Arztgruppe oder Fallbezug, die Annahme nennen oder nachfragen.",
        "11. Vor „nicht im Katalog“ die BMV-Ä-Pauschalen und den Vertragstext (texte/vertrag/) prüfen: Ansprüche, Berechtigungen und Geltungsbereiche regelt oft der BMV-Ä. Vertragsstellen mit Dokument, Paragraf und PDF-Seite zitieren.", "",
        "## Weitere Formate", "",
        f"- [Gesamter EBM als eine Datei](texte/ebm-{k.quartal}.md) (für Wissensspeicher)",
        "- JSON: [daten/index.json](daten/index.json) (Gliederung), daten/teil-0.json bis daten/teil-7.json, [daten/arztgruppen.json](daten/arztgruppen.json), [daten/ops.json](daten/ops.json), [daten/bmv.json](daten/bmv.json)",
        "- MCP-Server mit Werkzeugen (Suche, Sammelprüfung, Vertragstext): `python3 -I werkzeuge/ek.py mcp` im Repository.", ""])


def defekte_links(site):
    """Relative Markdown-Links in texte/ und llms.txt, deren Ziel fehlt (Gesamtdatei ausgenommen)."""
    out = []
    dateien = [f for f in (site / "texte").rglob("*.md") if not f.name.startswith("ebm-")] + [site / "llms.txt"]
    for f in dateien:
        if not f.exists():
            continue
        for ziel in re.findall(r"\]\(([^)#\s]+)", f.read_text(encoding="utf-8")):
            if not ziel.startswith(("http:", "https:")) and not (f.parent / ziel).exists():
                out.append(f"{f.relative_to(site)} -> {ziel}")
    return out


def main(argv=None):
    k = Katalog(argv[0] if argv else None)
    t = Texte(k)
    site = AUS / "site"
    td = site / "texte"
    for u in ("gop", "abschnitt", "register", "ops"):
        (td / u).mkdir(parents=True, exist_ok=True)
    alle = []
    for nr in t.gops:
        s = t.gop_md(nr)
        (td / "gop" / f"{nr}.md").write_text(s, encoding="utf-8")
        alle.append(s)
    for kid in t.slugs:
        s = t.abschnitt_md(kid)
        (td / "abschnitt" / f"{t.slugs[kid]}.md").write_text(s, encoding="utf-8")
        alle.append(s)
    (td / "inhalt.md").write_text(t.inhalt_md(), encoding="utf-8")
    idx, seiten = t.register()
    (td / "titel.md").write_text(t.titelliste(), encoding="utf-8")
    (td / "register.md").write_text(idx, encoding="utf-8")
    for kk, s in seiten.items():
        (td / "register" / f"{kk}.md").write_text(s, encoding="utf-8")
    idx, seiten = t.ops()
    if idx:
        (td / "ops.md").write_text(idx, encoding="utf-8")
        for g, s in seiten.items():
            (td / "ops" / f"{g}.md").write_text(s, encoding="utf-8")
    if k.bmv_daten:
        b = t.bmv_md()
        (td / "bmv.md").write_text(b, encoding="utf-8")
        alle.append(b)
    gl = None
    if k.bmvtext.verfuegbar:
        (td / "vertrag").mkdir(exist_ok=True)
        seiten, ort = t.vertragsseiten()
        for name, text in seiten.items():
            (td / "vertrag" / name).write_text(text, encoding="utf-8")
        gl = t.bmv_gliederung(ort)
    if gl:
        (td / "bmv-gliederung.md").write_text(gl, encoding="utf-8")
    (td / "stichworte.md").write_text(t.stichworte(), encoding="utf-8")
    (td / f"ebm-{k.quartal}.md").write_text("\n\n".join(alle), encoding="utf-8")
    (site / "llms.txt").write_text(llms_txt(k, bool(gl)), encoding="utf-8")
    kaputt = defekte_links(site)
    if kaputt:
        print(f"{len(kaputt)} defekte Links, z. B.:\n  " + "\n  ".join(kaputt[:10]))
        return 1
    print(f"{len(t.gops)} GOP-, {len(t.slugs)} Abschnittstexte, Register, Gliederung, OPS, Stichworte, llms.txt -> {site}"
          + ("" if gl else " (ohne BMV-Ä-Gliederung: Vertragstext nicht geladen)"))
    return 0
