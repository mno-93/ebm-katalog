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
import os
import posixpath
import re
from collections import defaultdict

from .grundlagen import AUS
from .katalog import HINWEIS, Katalog, synonyme

BMV_SEITE = "https://www.kbv.de/infothek/rechtsquellen/bundesmantelvertrag"
LESEHILFE = "Lesehilfe des Katalogs (maschinell abgeleitet, nicht EBM-Wortlaut)"

_ALTER = [
    (re.compile(r"ab (?:dem )?Beginn des (\d+)\.\s*bis (?:zum )?vollendeten (\d+)\.\s*Lebensjahr(?:es)?"),
     lambda a, b: f"Alter {int(a) - 1} bis {int(b) - 1} Jahre"),
    (re.compile(r"ab (?:dem )?Beginn des (\d+)\.\s*Lebensjahr(?:es)?"), lambda a: f"ab Alter {int(a) - 1} Jahre"),
    (re.compile(r"(?:nach Vollendung des|ab (?:dem )?vollendeten) (\d+)\.\s*Lebensjahr(?:es)?"), lambda a: f"ab Alter {int(a)} Jahre"),
    (re.compile(r"bis (?:zum )?vollendeten (\d+)\.\s*Lebensjahr(?:es)?"), lambda b: f"Alter 0 bis {int(b) - 1} Jahre (unter {int(b)})"),
]


def altersgrenzen(text):
    """Altersangaben im EBM-Wortlaut mit Umrechnung in Jahre: [(Wortlaut, Lesehilfe)].

    „ab Beginn des 19. Lebensjahres“ = ab dem 18. Geburtstag; „bis zum vollendeten 66. Lebensjahr“ = bis zum 66. Geburtstag,
    also höchstens 65 Jahre alt.
    """
    out, belegt = [], []
    for rx, f in _ALTER:
        for m in rx.finditer(text or ""):
            if any(a <= m.start() < b for a, b in belegt):
                continue
            belegt.append(m.span())
            eintrag = (m.group(0), f(*m.groups()))
            if eintrag not in out:
                out.append(eintrag)
    return out

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
            for b in r["bewertung"]:
                hilfe = "; ".join(h for _, h in altersgrenzen(b["bedingung"] or ""))
                bed = (b["bedingung"] or "—") + (f" (= {hilfe}, Lesehilfe)" if hilfe else "")
                z.append(f"| {bed} | {b.get('punkte') or '—'} | {b.get('euro') or '—'} |")
            z.append("")
            z += ["Euro mit dem bundeseinheitlichen Orientierungswert; regionale Punktwerte können abweichen.", ""]
        elif r["bewertung_hinweis"]:
            z += [f"Bewertung: {r['bewertung_hinweis']}", ""]
        if r["merkmale"]:
            z += ["Merkmale (Kennzeichen der Online-Ansicht, Bedeutung dort nicht erläutert): "
                  + "; ".join(f"{m['text']} ({'ja' if m['zutreffend'] else 'nein'})" for m in r["merkmale"]), ""]
        pr = self.praeambeln(n)
        bed = r.get("bedingungen_aus_praeambeln", [])
        z += self.auf_einen_blick(nr, r, n, bed)
        for a in r["abschnitte"]:
            z += [f"## {a['ueberschrift'] or 'Text'}", "", a["text"], ""]
            hilfe = altersgrenzen(a["text"])
            if hilfe:
                z += [f"{LESEHILFE}: " + "; ".join(f"„{w}“ = {h}" for w, h in hilfe) + ".", ""]
        # Regeln außerhalb der GOP
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

    def ist_zuschlag_zu(self, x, nr):
        """Beschreibt sich x als Zuschlag (oder Zusatzpauschale) zu nr, einzeln oder als Bereich?"""
        h, _ = self.k.gop_knoten(x)
        if not h:
            return False
        text = " ".join(a["text"] for a in self.k._abschnitte(h["knotenId"])[:1]) + " " + (h["titel"] or "")
        m = re.search(r"(?:Zuschlag|Zusatzpauschale)\w* (?:zu|zur|zum)\b(.{0,400})", text, re.S)
        return bool(m) and self.k._nennt(m.group(1), nr)

    def auf_einen_blick(self, nr, r, n, bed):
        """Kurzfassung oben auf der GOP-Seite: was vor der Abrechnung zu prüfen ist. Nur Verweise auf Angaben weiter unten."""
        k, z = self.k, []
        texte = {a["ueberschrift"]: a["text"] for a in r["abschnitte"]}
        alle = " ".join(texte.values()) + " " + " ".join(b["bedingung"] or "" for b in r["bewertung"])
        alter = altersgrenzen(alle)
        if alter:
            z.append("- **Alter:** " + "; ".join(f"„{w}“ = {h}" for w, h in alter) + " (Lesehilfe, maschinell abgeleitet)")
        if texte.get("Abrechnungsbestimmung"):
            z.append(f"- **Häufigkeit:** {texte['Abrechnungsbestimmung'][:200]}")
        wichtig = [b for b in bed if re.search(r"ausschließlich|Genehmigung|nicht berechnungsfähig|Punktzahlvolumen|nur", b["satz"])]
        for b in wichtig[:3]:
            satz = b["satz"] if len(b["satz"]) <= 260 else b["satz"][:257] + " …"
            vor = f" (gilt, wenn: {b['einleitung']})" if b.get("einleitung") else ""
            z.append(f"- **Bedingung aus {self.link(b['knotenId'])}:** „{satz}“{vor}")
        if len(bed) > len(wichtig[:3]):
            z.append(f"- Weitere Bedingungssätze aus Präambeln und Bestimmungen: {len(bed) - len(wichtig[:3])}, siehe „Regeln außerhalb dieser GOP“.")
        d = k.inhalt(n["knotenId"])
        aus = defaultdict(set)
        for a in d.get("ausschluesse", []):
            aus[a["bezug"]].update(x["nr"] for x in a["leistungen"])
            for kap in a["kapitel"]:
                aus[a["bezug"]].update(self.abschnitt_gops(kap))
        for x, b in self.gegen.get(nr, []):
            aus[b].add(x)
        if aus:
            z.append("- **Ausschlüsse (beide Richtungen):** " + "; ".join(f"{b}: {len(v)} GOP" for b, v in aus.items()) + ", Liste unten.")
        zu = [x.split(" ", 1)[0] for x in r.get("zuschlaege", []) if self.ist_zuschlag_zu(x.split(" ", 1)[0], nr)]
        if zu:
            z.append("- **Zuschläge zu dieser GOP:** " + ", ".join(self.gop_link(x) for x in zu[:12])
                     + (" …" if len(zu) > 12 else "") + " (Voraussetzungen jeweils dort)")
        if r.get("zeiten") and (r["zeiten"].get("kalkulationszeit") or r["zeiten"].get("pruefzeit")):
            t = r["zeiten"]
            zeit = lambda v: f"{v} Min." if re.fullmatch(r"\d+", v or "") else {"KA": "keine (KA)", "./.": "keine (./.)"}.get(v, v or "—")
            z.append(f"- **Anhang 3:** Kalkulationszeit {zeit(t['kalkulationszeit'])}, Prüfzeit {zeit(t['pruefzeit'])}")
        if not z:
            return []
        return ["## Auf einen Blick", "", "Vor der Abrechnung prüfen. Kurzfassung aus den Abschnitten unten, maschinell zusammengestellt; maßgeblich ist der Wortlaut.", ""] + z + [""]

    def abschnitt_md(self, kid):
        k, n = self.k, self.k.K[kid]
        z = self.kopf(f"{n['nr']} {self.titel(n)}".strip(), n)
        for a in k._abschnitte(kid):
            z += ([f"## {a['ueberschrift']}", ""] if a["ueberschrift"] else []) + [a["text"], ""]
            hilfe = altersgrenzen(a["text"])
            if hilfe and len(hilfe) <= 12:
                z += [f"{LESEHILFE}: " + "; ".join(f"„{w}“ = {h}" for w, h in hilfe) + ".", ""]
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


def basis_url():
    """Öffentliche Adresse der Seite für absolute Links: EK_BASIS_URL, sonst aus GITHUB_REPOSITORY (Pages), sonst None (relativ)."""
    b = os.environ.get("EK_BASIS_URL")
    if not b and os.environ.get("GITHUB_REPOSITORY"):
        konto, repo = os.environ["GITHUB_REPOSITORY"].split("/", 1)
        b = f"https://{konto.lower()}.github.io/{repo}/"
    return (b.rstrip("/") + "/") if b else None


LINK = re.compile(r"\]\(([^)\s]+)\)")


def absolut(text, datei, basis):
    """Relative Links einer Seite (Pfad relativ zur Wurzel der Seite) in absolute Adressen umschreiben."""
    if not basis:
        return text
    ordner = posixpath.dirname(datei)
    def ersetze(m):
        ziel = m.group(1)
        if ziel.startswith(("http:", "https:", "#", "mailto:")):
            return m.group(0)
        pfad, _, anker = ziel.partition("#")
        voll = posixpath.normpath(posixpath.join(ordner, pfad))
        return f"]({basis}{voll}{'#' + anker if anker else ''})"
    return LINK.sub(ersetze, text)


def als_txt(text, basis):
    """Gleiche Seite als .txt: Links auf .md-Seiten des Katalogs zeigen auf die .txt-Fassung."""
    def ersetze(m):
        ziel = m.group(1)
        if ziel.startswith(("http:", "https:")) and not (basis and ziel.startswith(basis)):
            return m.group(0)
        if posixpath.basename(ziel).startswith("ebm-"):
            return m.group(0)  # Gesamtdatei gibt es nur als .md
        return "](" + re.sub(r"\.md(?=$|#)", ".txt", ziel) + ")"
    return LINK.sub(ersetze, text)


def llms_txt(k, vertrag, basis):
    q = k.quartal.replace("-", "/Q")
    u = lambda pfad: f"{basis or ''}{pfad}"
    z = ["# Offener EBM-Katalog", "",
         f"> Maschinenlesbarer Spiegel der EBM-Online-Ansicht (Quartal {q}) mit Arztgruppenfilter, Anhang 2 (OPS), den Pauschalen des BMV-Ä außerhalb des EBM "
         f"und dem Wortlaut des BMV-Ä und seiner Anlagen. {HINWEIS}", "",
         "## Wegweiser", "",
         "Alle Texte sind Markdown und untereinander verlinkt. Jede Seite gibt es zusätzlich als `.txt` mit gleichem Inhalt "
         f"(für Browser, die `.md` nicht anzeigen), z. B. [{u('texte/gop/03000.txt')}]({u('texte/gop/03000.txt')}). Für eine Antwort den Links folgen:", "",
         f"1. Nummer bekannt: `texte/gop/<Nummer>.md`, z. B. [{u('texte/gop/03000.md')}]({u('texte/gop/03000.md')}). Oben steht **„Auf einen Blick“**: Altersgrenzen "
         "mit Umrechnung in Jahre, Häufigkeit, Bedingungen aus Präambeln, Zahl der Ausschlüsse, Zuschläge. Darunter Wortlaut, **Regeln außerhalb dieser GOP**, "
         "Ausschlüsse in beiden Richtungen, Zeiten aus Anhang 3, Rückverweise.",
         "2. Nummer unbekannt: Titelliste, Register, Gliederung oder Stichworte (Links unten).",
         "3. Pauschalen außerhalb des EBM (Onkologie, DiGA, TI, Kurarzt …): BMV-Ä-Pauschalen. Ansprüche, Berechtigungen und Geltungsbereiche: Vertragstext (Liste unten).",
         "4. OPS-Code: Anhang 2.", "",
         "## Einstiegsseiten", ""]
    for titel, pfad in [("Titelliste aller GOP (nach Wörtern durchsuchen)", "texte/titel.md"), ("Register nach Kapiteln", "texte/register.md"),
                        ("Gliederung mit allen Abschnitten, Präambeln, Allgemeinen Bestimmungen", "texte/inhalt.md"),
                        ("Stichworte: Alltagsbegriffe, DiGA, Begriffsbestimmungen, Themen außerhalb des Katalogs", "texte/stichworte.md"),
                        ("Pauschalen aus dem BMV-Ä", "texte/bmv.md"), ("Anhang 2: OPS-Code → GOP", "texte/ops.md")] + (
                        [("Gliederung des BMV-Ä und seiner Anlagen (Überschriften mit Link auf den Wortlaut)", "texte/bmv-gliederung.md")] if vertrag else []):
        z.append(f"- {titel}: [{u(pfad)}]({u(pfad)})")
    z += ["", "Abschnittsseiten heißen `texte/abschnitt/<Teil>-<Nummer>.md` mit dem Teil als römischer Zahl: I = Allgemeine Bestimmungen (z. B. `I-4.3.1.md`), "
          "II–V und VII–VIII = Kapitel (z. B. `III-3.1.md` = Präambel Kapitel 3), VI = Anhänge (z. B. `VI-3.md`). Bereiche wie „03040 – 03045“ werden zu `III-03040-03045.md`; "
          "im Zweifel den Link aus der Gliederung nehmen statt den Namen zu raten.", ""]
    if vertrag:
        z += ["## Vertragstext (BMV-Ä und Anlagen, Wortlaut)", ""]
        z += [f"- {t}: [{u('texte/vertrag/' + d)}]({u('texte/vertrag/' + d)})" for t, d in vertrag] + [""]
    z += ["## Antwortregeln", "",
          "1. Nur aus diesen Texten (und den verlinkten Verträgen auf kbv.de) antworten. Was dort nicht steht, ist „nicht im Katalog“ — nicht aus dem Gedächtnis ergänzen.",
          "2. Jede Aussage mit Beleg: Quartal, Nummer, Fundstelle. **Fundstelle ist der Pfad im EBM** (z. B. „Präambel 3.1“, „GOP 01474, Anmerkung“) bzw. Dokument, Paragraf und Seite des BMV-Ä. "
          "Dateipfade des Katalogs sind nur der Beleg, wo es steht; Dateien wie Titelliste oder Register sind keine Stellen im EBM.",
          f"3. Der Katalog bildet das Quartal {q} ab; andere Zeiträume als nicht abgedeckt kennzeichnen.",
          "4. „Kein Ausschluss eingetragen“ ist keine Erlaubnis. Vor einer Antwort zur Abrechenbarkeit „Auf einen Blick“, „Regeln außerhalb dieser GOP“ und die verlinkten Präambeln lesen.",
          "5. **Nummern zitieren, nicht zählen:** Nummerierte Punkte stehen mit ihrer EBM-Nummer im Text („10. Relevant für die Fallzählung …“ = Präambel 3.1 Nr. 10). Wo keine Nummer steht, ist der Text nicht nummeriert; keine Nummer erfinden.",
          "6. **Altersgrenzen genau lesen:** „ab Beginn des 19. Lebensjahres“ = ab 18 Jahren; „bis zum vollendeten 66. Lebensjahr“ = bis 65 Jahre. Die Seiten zeigen dazu eine Lesehilfe.",
          "7. Regionale Werte nicht beziffern; Euro-Werte gelten mit dem bundeseinheitlichen Orientierungswert.",
          "8. Keine Einzelfallberatung; im Einzelfall an die Abrechnungsberatung der Kassenärztlichen Vereinigung verweisen.",
          "9. Grenzen nennen: KI-gebaut, nicht amtlich; Qualitätssicherungsvereinbarungen, regionale Verträge und Selektivverträge sind nicht enthalten.",
          "10. Gleiche Abschnittsnummern gibt es in den Allgemeinen Bestimmungen (Pfad I) und in den Kapiteln; den Pfad nennen.",
          "11. Merkmale und die Spalte §115b werden nicht erläutert; unverändert wiedergeben, nicht deuten. Sichtbarkeit im Arztgruppenfilter ist keine Berechtigung.",
          "12. Fehlen Alter, Arztgruppe oder Fallbezug, die Annahme nennen oder nachfragen.",
          "13. Vor „nicht im Katalog“ die BMV-Ä-Pauschalen und den Vertragstext prüfen: Ansprüche, Berechtigungen und Geltungsbereiche regelt oft der BMV-Ä. Vertragsstellen mit Dokument, Paragraf und PDF-Seite zitieren.", "",
          "## Weitere Formate", "",
          f"- Gesamter EBM als eine Datei (für Wissensspeicher): [{u('texte/ebm-' + k.quartal + '.md')}]({u('texte/ebm-' + k.quartal + '.md')})",
          f"- JSON: [{u('daten/index.json')}]({u('daten/index.json')}) (Gliederung), daten/teil-0.json bis daten/teil-7.json, daten/arztgruppen.json, daten/ops.json, daten/bmv.json",
          "- MCP-Server mit Werkzeugen (Suche, Sammelprüfung, Vertragstext): `python3 -I werkzeuge/ek.py mcp` im Repository.", ""]
    return "\n".join(z)


def defekte_links(site, basis=None):
    """Interne Links in texte/ und llms.txt (relativ oder absolut unter basis), deren Ziel fehlt (Gesamtdatei ausgenommen)."""
    out = []
    dateien = [f for f in (site / "texte").rglob("*") if f.suffix in (".md", ".txt") and not f.name.startswith("ebm-")] + [site / "llms.txt"]
    for f in dateien:
        if not f.exists():
            continue
        for ziel in re.findall(r"\]\(([^)#\s]+)", f.read_text(encoding="utf-8")):
            if basis and ziel.startswith(basis):
                if not (site / ziel[len(basis):]).exists():
                    out.append(f"{f.relative_to(site)} -> {ziel}")
            elif not ziel.startswith(("http:", "https:")) and not (f.parent / ziel).exists():
                out.append(f"{f.relative_to(site)} -> {ziel}")
    return out


def main(argv=None):
    k = Katalog(argv[0] if argv else None)
    t = Texte(k)
    basis = basis_url()
    site = AUS / "site"
    seiten = {}  # Pfad relativ zu site -> Text
    alle = []
    for nr in t.gops:
        seiten[f"texte/gop/{nr}.md"] = s = t.gop_md(nr); alle.append(s)
    for kid in t.slugs:
        seiten[f"texte/abschnitt/{t.slugs[kid]}.md"] = s = t.abschnitt_md(kid); alle.append(s)
    seiten["texte/inhalt.md"] = t.inhalt_md()
    idx, reg = t.register()
    seiten["texte/titel.md"] = t.titelliste()
    seiten["texte/register.md"] = idx
    seiten.update({f"texte/register/{kk}.md": s for kk, s in reg.items()})
    idx, ops = t.ops()
    if idx:
        seiten["texte/ops.md"] = idx
        seiten.update({f"texte/ops/{g}.md": s for g, s in ops.items()})
    if k.bmv_daten:
        seiten["texte/bmv.md"] = s = t.bmv_md(); alle.append(s)
    vertrag = []
    if k.bmvtext.verfuegbar:
        vs, ort = t.vertragsseiten()
        seiten.update({f"texte/vertrag/{name}": s for name, s in vs.items()})
        seiten["texte/bmv-gliederung.md"] = t.bmv_gliederung(ort)
        titel = {d["dokument"]: d["titel"] for d in k.bmvtext.dokumente()}
        vertrag = [(f"{titel[st]} ({st}.pdf)", f"{st}.md") for st in titel]
    seiten["texte/stichworte.md"] = t.stichworte()
    for pfad, text in seiten.items():
        ziel = site / pfad
        ziel.parent.mkdir(parents=True, exist_ok=True)
        text = absolut(text, pfad, basis)
        ziel.write_text(text, encoding="utf-8")
        ziel.with_suffix(".txt").write_text(als_txt(text, basis), encoding="utf-8")
    (site / "texte" / f"ebm-{k.quartal}.md").write_text("\n\n".join(alle), encoding="utf-8")
    (site / "llms.txt").write_text(llms_txt(k, vertrag, basis), encoding="utf-8")
    kaputt = defekte_links(site, basis)
    if kaputt:
        print(f"{len(kaputt)} defekte Links, z. B.:\n  " + "\n  ".join(kaputt[:10]))
        return 1
    print(f"{len(t.gops)} GOP-, {len(t.slugs)} Abschnittstexte, Register, Gliederung, OPS, Stichworte, llms.txt, je Seite .md und .txt -> {site}"
          + (f", absolute Links auf {basis}" if basis else ", relative Links")
          + ("" if vertrag else " (ohne Vertragstext)"))
    return 0
