"""Abfragen auf den exportierten Katalog — Grundlage für den MCP-Server und den Fragenkatalog.

Jede Antwort ist ein dict mit den Fakten und einem Feld `belege` (Quartal, Nummer, Knotenkennung,
Herkunft, Auszug). Antworten ohne Treffer sagen das ausdrücklich (`gefunden: False`), statt zu raten.
"""
import html as H
import json
import re
from functools import cached_property

from .grundlagen import AUS, aktuelles_quartal

HINWEIS = ("Nicht amtlich: abgeleitet aus der EBM-Online-Ansicht (ebm.kbv.de) und den Verträgen auf kbv.de. "
           "Verbindlich sind ausschließlich diese Veröffentlichungen.")
EBM_URL = "https://ebm.kbv.de/"
OPS_URL = "https://ebm.kbv.de/ops.xhtml"


def klartext(html, links=None):
    """Bereinigtes HTML der Abschnitte in lesbaren Text (Listen mit Spiegelstrich)."""
    s = re.sub(r"<li>\s*(?:<p>)?", "\n- ", html)
    s = re.sub(r"</p>\s*</li>", "</li>", s)
    s = re.sub(r"</?(p|ul|ol|tr|table|thead|tbody|h5|h6)[^>]*>", "\n", s)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</t[dh]>\s*", " | ", s)
    s = H.unescape(re.sub(r"<[^>]+>", "", s))
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").lower())


class Katalog:
    def __init__(self, quartal=None, verzeichnis=None):
        self.quartal = quartal or aktuelles_quartal()
        self.d = verzeichnis or (AUS / self.quartal)
        if not (self.d / "index.json").exists():
            from . import export
            export.main(self.quartal)
        self.index = self._json("index.json")
        self.K = {n["knotenId"]: n for n in self.index["knoten"]}
        self.pos = {n["knotenId"]: i for i, n in enumerate(self.index["knoten"])}
        self.nr = {}
        for n in self.index["knoten"]:
            self.nr.setdefault(n["nr"], []).append(n)
        self._teile = {}

    def _json(self, name, optional=False):
        f = self.d / name
        if optional and not f.exists():
            return None
        return json.loads(f.read_text(encoding="utf-8"))

    # ---------- Grundbausteine ----------
    def inhalt(self, kid):
        t = self.K[kid]["teil"]
        if t not in self._teile:
            self._teile[t] = self._json(f"teil-{t}.json")
        return self._teile[t].get(kid, {})

    @cached_property
    def ops_daten(self):
        d = self._json("ops.json", optional=True)
        if not d:
            return None
        d["nach_id"] = {o["id"]: o for o in d["knoten"]}
        d["nach_nr"] = {o["nr"]: o for o in d["knoten"]}
        d["nach_gop"] = {}
        for o in d["knoten"]:
            for g in o.get("gops", []):
                d["nach_gop"].setdefault(g["gop"], []).append((o, g["art"]))
        return d

    @cached_property
    def bmv_daten(self):
        d = self._json("bmv.json", optional=True)
        if not d:
            return None
        d["nach_id"] = {p["id"]: p for p in d["pauschalen"]}
        d["anlage_nach_id"] = {a["id"]: a for a in d["anlagen"]}
        return d

    @cached_property
    def ag_daten(self):
        d = self._json("arztgruppen.json", optional=True)
        if d:
            d["mengen"] = {g: set(v) for g, v in d["sichtbar"].items()}
        return d

    def pfad(self, n):
        out, p = [], self.K.get(n["eltern"])
        while p:
            out.insert(0, f"{p['nr']} {p['titel'] or p['baumtitel']}".strip()); p = self.K.get(p["eltern"])
        return out

    def beleg(self, n, auszug=None):
        b = {"quartal": self.quartal, "nr": n["nr"], "titel": n["titel"] or n["baumtitel"], "knotenId": n["knotenId"],
             "pfad": " › ".join(self.pfad(n)), "herkunft": f"EBM-Online-Ansicht {EBM_URL} (Quartal {self.quartal.replace('-', '/Q')})"}
        if auszug:
            b["auszug"] = auszug[:600]
        return b

    def gop_knoten(self, nr):
        """Hauptknoten einer GOP (erster Knoten der Nummer) und Untergliederungen."""
        ns = [n for n in self.nr.get(nr.strip().upper(), []) if n["typ"] == "gop"]
        if not ns:
            return None, []
        return ns[0], [self.K[c] for c in ns[0]["kinder"]]

    def _abschnitte(self, kid):
        return [{"ueberschrift": a.get("ueberschrift"), "text": klartext(a["html"])} for a in self.inhalt(kid).get("abschnitte", [])]

    def _nr_von(self, kid):
        n = self.K.get(kid)
        return n["nr"] if n else None

    # ---------- Werkzeuge ----------
    def gop(self, nr):
        n, kinder = self.gop_knoten(nr)
        if not n:
            b = self.bmv(nr)
            if b.get("gefunden"):
                return {"gefunden": False, "hinweis": f"{nr} ist keine Gebührenordnungsposition des EBM, sondern eine Pauschale aus dem BMV-Ä.", "bmv": b}
            return {"gefunden": False, "hinweis": f"{nr} steht im EBM {self.quartal} nicht.", "quartal": self.quartal}
        d = self.inhalt(n["knotenId"])
        bew = []
        if n.get("bewertung"):
            bew.append({"bedingung": None, **n["bewertung"]})
        for c in kinder:
            if c.get("bewertung"):
                bew.append({"bedingung": c["titel"], **c["bewertung"]})
        aus = [{"bezug": a["bezug"], "gop": [x["nr"] for x in a["leistungen"]], "kapitel": [x["nr"] for x in a["kapitel"]]} for a in d.get("ausschluesse", [])]
        r = {"gefunden": True, "nr": n["nr"], "titel": n["titel"], "bewertung": bew,
             "bewertung_hinweis": None if bew else "Keine Bewertung im Kopf der Detailansicht; sie kann im Text (Anmerkung, Präambel) stehen.",
             "merkmale": d.get("merkmale", []), "abschnitte": self._abschnitte(n["knotenId"]), "ausschluesse": aus,
             "untergliederung": [c["titel"] for c in kinder],
             "erwaehnt_in": [self._nr_von(k) for k in d.get("referenziert_von", [])],
             "bmv_bezuege": d.get("bmv_verweise", [])}
        if self.ag_daten:
            p = self.pos[n["knotenId"]]
            r["arztgruppen"] = [g for g, m in self.ag_daten["mengen"].items() if p in m]
        if self.ops_daten and n["nr"] in self.ops_daten["nach_gop"]:
            r["ops_anzahl"] = len(self.ops_daten["nach_gop"][n["nr"]])
        r["belege"] = [self.beleg(n)]
        r["hinweis"] = HINWEIS
        return r

    def knoten(self, nr_oder_id):
        """Abschnitt, Präambel oder Bestimmung über Nummer (z. B. 4.3.1) oder Knotenkennung."""
        ns = [self.K[nr_oder_id]] if nr_oder_id in self.K else self.nr.get(nr_oder_id.strip(), [])
        if not ns:
            return {"gefunden": False, "hinweis": f"Kein Knoten {nr_oder_id} im EBM {self.quartal}."}
        out = []
        for n in ns:
            out.append({"nr": n["nr"], "titel": n["titel"] or n["baumtitel"], "typ": n["typ"], "pfad": " › ".join(self.pfad(n)),
                        "abschnitte": self._abschnitte(n["knotenId"]),
                        "enthaelt": [f"{self.K[c]['nr']} {self.K[c]['titel'] or self.K[c]['baumtitel']}" for c in n["kinder"]][:60],
                        "beleg": self.beleg(n)})
        return {"gefunden": True, "treffer": out, "mehrdeutig": len(out) > 1, "hinweis": HINWEIS}

    def suche(self, text, bereich="alle", grenze=15):
        """Volltextsuche über Nummer, Titel und Text; bereich: alle | ebm | ops | bmv."""
        w = [x for x in _norm(text).split() if x]
        if not w:
            return {"treffer": []}
        tr = []
        if bereich in ("alle", "ebm"):
            for n in self.index["knoten"]:
                titel = _norm(f"{n['nr']} {n['titel'] or n['baumtitel']}")
                body = None
                if not all(x in titel for x in w):
                    body = _norm(" ".join(a["text"] for a in self._abschnitte(n["knotenId"])))
                    if not all(x in titel or x in body for x in w):
                        continue
                s = sum(40 for x in w if x in titel) + (5 if n["typ"] == "gop" else 0) + (0 if body is None else sum(min(body.count(x), 8) for x in w))
                tr.append((s, {"bereich": "ebm", "nr": n["nr"], "titel": n["titel"] or n["baumtitel"], "typ": n["typ"], "knotenId": n["knotenId"]}))
        if bereich in ("alle", "ops") and self.ops_daten:
            for o in self.ops_daten["knoten"]:
                t = _norm(f"{o['nr']} {o['titel']}")
                if all(x in t for x in w):
                    tr.append((30 * len(w) + (3 if o.get("gops") else 0), {"bereich": "ops", "nr": o["nr"], "titel": o["titel"]}))
        if bereich in ("alle", "bmv") and self.bmv_daten:
            for p in self.bmv_daten["pauschalen"]:
                a = self.bmv_daten["anlage_nach_id"][p["anlage"]]
                t = _norm(f"{p['nr'] or ''} {p['titel']} {p.get('abrechnung') or ''} {a['titel']}")
                if all(x in t for x in w):
                    tr.append((35 * len(w), {"bereich": "bmv", "nr": p["nr"] or p["id"], "titel": p["titel"], "anlage": a["anlage"]}))
        tr.sort(key=lambda x: -x[0])
        return {"anfrage": text, "anzahl": len(tr), "treffer": [t for _, t in tr[:grenze]], "quartal": self.quartal}

    def nebeneinander(self, a, b):
        """Prüft eingetragene Abrechnungsausschlüsse zwischen zwei Nummern, in beide Richtungen."""
        def eintraege(x, y):
            out = []
            for n in self.nr.get(x, []):
                for z in self.inhalt(n["knotenId"]).get("ausschluesse", []):
                    for l in z["leistungen"]:
                        ids = l["k"].split("_")
                        if l["nr"] == y or any(self._nr_von(i) == y for i in ids):
                            out.append({"eingetragen_bei": x, "bezug": z["bezug"], "beleg": self.beleg(n, f"Abrechnungsausschluss {z['bezug']}: {l['nr']}")})
            if self.bmv_daten:
                for p in self.bmv_daten["pauschalen"]:
                    if (p["nr"] or p["id"]) == x:
                        for z in p["ausschluesse"]:
                            if y in z["nr"]:
                                out.append({"eingetragen_bei": x, "bezug": z["bezug"], "beleg": self.bmv_beleg(p)})
            return out
        a, b = a.strip().upper(), b.strip().upper()
        unbekannt = [x for x in (a, b) if x not in self.nr and not (self.bmv_daten and x in self.bmv_daten["nach_id"])]
        if unbekannt:
            return {"bekannt": False, "hinweis": f"Nicht im Katalog: {', '.join(unbekannt)}."}
        e = eintraege(a, b) + eintraege(b, a)
        return {"a": a, "b": b, "ausschluss_eingetragen": bool(e), "eintraege": e,
                "hinweis": ("Ausschluss eingetragen; der Bezug (z. B. am Behandlungstag, im Behandlungsfall) bestimmt, wann er gilt."
                            if e else "In den Ausschlusstabellen beider Positionen ist kein Ausschluss eingetragen. "
                            "Das ist keine Zusage, dass beide nebeneinander berechnungsfähig sind: Präambeln, Allgemeine Bestimmungen "
                            "und Anmerkungen können weitere Bedingungen enthalten."), "quartal": self.quartal}

    def arztgruppe(self, gruppe=None, gop=None):
        ag = self.ag_daten
        if not ag:
            return {"verfuegbar": False, "hinweis": "Arztgruppenfilter nicht abgezogen."}
        if not gruppe:
            return {"gruppen": ag["gruppen"], "unvollstaendig": ag["unvollstaendig"]}
        g = next((x for x in ag["gruppen"] if _norm(x) == _norm(gruppe)), None) or next((x for x in ag["gruppen"] if _norm(gruppe) in _norm(x)), None)
        if not g:
            return {"gefunden": False, "hinweis": f"Arztgruppe {gruppe} unbekannt.", "gruppen": ag["gruppen"]}
        m = ag["mengen"].get(g, set())
        r = {"gruppe": g, "vollstaendig": g not in ag["unvollstaendig"],
             "anzahl_gop": len({self.index['knoten'][i]['nr'] for i in m if self.index['knoten'][i]['typ'] == 'gop'}),
             "herkunft": f"Arztgruppenfilter der EBM-Online-Ansicht {EBM_URL}", "quartal": self.quartal}
        if gop:
            n, _ = self.gop_knoten(gop)
            r["gop"] = gop
            r["sichtbar"] = bool(n) and self.pos[n["knotenId"]] in m
            r["hinweis"] = "Sichtbar heißt: Die Position erscheint im Filter dieser Arztgruppe. Ob sie im Einzelfall berechnungsfähig ist, regeln Präambeln und Genehmigungen."
        return r

    def ops(self, code=None, gop=None):
        d = self.ops_daten
        if not d:
            return {"verfuegbar": False, "hinweis": "Anhang-2-Ansicht nicht abgezogen."}
        if code:
            o = d["nach_nr"].get(code.strip())
            if not o:
                kand = [x["nr"] for x in d["knoten"] if x["nr"].startswith(code.strip())][:20]
                return {"gefunden": False, "hinweis": f"OPS {code} steht nicht im Anhang 2 {self.quartal}.", "aehnlich": kand}
            return {"gefunden": True, "nr": o["nr"], "titel": o["titel"], "kategorie": o.get("kategorie"), "p115b": o.get("p115b"),
                    "seitenangabe": o.get("seite"), "zuordnung": o.get("gops", []),
                    "beleg": {"quartal": self.quartal, "herkunft": f"Anhang-2-Ansicht {OPS_URL}", "knotenId": o["id"]}, "hinweis": HINWEIS}
        if gop:
            rows = d["nach_gop"].get(gop.strip(), [])
            return {"gop": gop, "anzahl": len(rows), "ops": [{"nr": o["nr"], "titel": o["titel"], "art": art} for o, art in rows[:200]],
                    "gekuerzt": len(rows) > 200, "beleg": {"quartal": self.quartal, "herkunft": f"Anhang-2-Ansicht {OPS_URL}"}}
        return {"anzahl_knoten": d["anzahl"], "mit_zuordnung": d["mit_zuordnung"]}

    def bmv_beleg(self, p):
        a = self.bmv_daten["anlage_nach_id"][p["anlage"]]
        f = p["fundstelle"]
        return {"anlage": a["anlage"], "regelung": a["titel"], "fassung": a.get("fassung"), "datei": f["datei"], "seite": f["seite"],
                "url": f"{f['url']}#page={f['seite']}" if f.get("url") else None, "herkunft": "BMV-Ä, von Hand aus dem PDF erfasst"}

    def bmv(self, nr_oder_begriff=None):
        d = self.bmv_daten
        if not d:
            return {"verfuegbar": False}
        if not nr_oder_begriff:
            return {"anlagen": [{"anlage": a["anlage"], "titel": a["titel"], "pauschalen": len(a["pauschalen"]), "hoehe": a["hoehe"]} for a in d["anlagen"]],
                    "ohne_eigene_pauschale": d["ohne_eigene_pauschale"], "hinweis": HINWEIS}
        q = nr_oder_begriff.strip()
        p = d["nach_id"].get(q)
        treffer = [p] if p else [x for x in d["pauschalen"] if all(w in _norm(x["titel"] + " " + d["anlage_nach_id"][x["anlage"]]["titel"]) for w in _norm(q).split())]
        if not treffer:
            return {"gefunden": False, "hinweis": f"Keine Pauschale „{q}“ im BMV-Ä-Teil des Katalogs."}
        out = []
        for p in treffer[:10]:
            a = d["anlage_nach_id"][p["anlage"]]
            out.append({"nr": p["nr"], "titel": p["titel"], "betrag": p["betrag"],
                        "hoehe": "regional je Kassenärztlicher Vereinigung" if not p["betrag"] else "bundeseinheitlich",
                        "hoehe_erlaeuterung": a["hoehe"], "status": a.get("status"), "abrechnung": p.get("abrechnung"),
                        "ausschluesse": p["ausschluesse"], "im_ebm_genannt_in": [self._nr_von(k) for k in d.get("ebm_verweise", {}).get("bmv:" + (p["nr"] or ""), [])],
                        "beleg": self.bmv_beleg(p)})
        return {"gefunden": True, "treffer": out, "hinweis": HINWEIS}

    def verweise(self, nr):
        n, _ = self.gop_knoten(nr)
        if not n:
            ns = self.nr.get(nr, [])
            n = ns[0] if ns else None
        if not n:
            return {"gefunden": False, "hinweis": f"{nr} steht im EBM {self.quartal} nicht."}
        d = self.inhalt(n["knotenId"])
        return {"nr": n["nr"], "erwaehnt_in": [f"{self.K[k]['nr']} {self.K[k]['titel'] or self.K[k]['baumtitel']}" for k in d.get("referenziert_von", [])],
                "verweist_auf": [f"{self.K[k]['nr']} {self.K[k]['titel'] or self.K[k]['baumtitel']}" for k in d.get("verweise", [])],
                "beleg": self.beleg(n)}


WERKZEUGE = {
    "ebm_suche": ("Volltextsuche im EBM, im Anhang 2 (OPS) und in den Pauschalen des BMV-Ä. Liefert Nummern und Titel; Details mit den anderen Werkzeugen abrufen.",
                  {"text": ("string", "Suchbegriffe oder Nummer", True), "bereich": ("string", "alle | ebm | ops | bmv", False), "grenze": ("integer", "Anzahl Treffer, Standard 15", False)},
                  lambda k, a: k.suche(a["text"], a.get("bereich", "alle"), int(a.get("grenze", 15)))),
    "ebm_gop": ("Vollständige Angaben zu einer Gebührenordnungsposition: Bewertung (auch Altersstufen), Merkmale, Leistungsinhalt, Abrechnungsbestimmung, Anmerkungen, Ausschlüsse, Arztgruppen, Bezüge zum BMV-Ä.",
                {"nr": ("string", "fünfstellige GOP, z. B. 03000", True)}, lambda k, a: k.gop(a["nr"])),
    "ebm_abschnitt": ("Text eines Abschnitts, einer Präambel oder einer Allgemeinen Bestimmung, z. B. 4.3.1 oder 3.1. Gleiche Nummern kommen in Allgemeinen Bestimmungen und Kapiteln vor; dann alle Treffer mit Pfad.",
                      {"nr": ("string", "Abschnittsnummer oder Knotenkennung", True)}, lambda k, a: k.knoten(a["nr"])),
    "ebm_nebeneinander": ("Prüft, ob zwischen zwei Nummern (GOP oder BMV-Ä-Pauschale) ein Abrechnungsausschluss eingetragen ist, in beide Richtungen, mit Bezug.",
                          {"a": ("string", "erste Nummer", True), "b": ("string", "zweite Nummer", True)}, lambda k, a: k.nebeneinander(a["a"], a["b"])),
    "ebm_arztgruppe": ("Arztgruppenfilter der Online-Ansicht: Liste der Gruppen, Umfang einer Gruppe oder ob eine GOP für eine Gruppe sichtbar ist.",
                       {"gruppe": ("string", "z. B. Hausarzt", False), "gop": ("string", "optional: GOP", False)}, lambda k, a: k.arztgruppe(a.get("gruppe"), a.get("gop"))),
    "ebm_ops": ("Anhang 2: Kategorie, §115b-Status und zugeordnete GOP zu einem OPS-Code, oder alle OPS-Codes zu einer GOP der Kapitel 31/36.",
                {"code": ("string", "OPS-Code, z. B. 5-010.2", False), "gop": ("string", "GOP, z. B. 31272", False)}, lambda k, a: k.ops(a.get("code"), a.get("gop"))),
    "ebm_bmv": ("Pauschalen aus dem Bundesmantelvertrag-Ärzte und seinen Anlagen, die nicht im EBM stehen (z. B. Onkologie, Sozialpsychiatrie, DiGA, Kurarzt, TI-Pauschale). Ohne Argument: Übersicht.",
                {"nr_oder_begriff": ("string", "Nummer (z. B. 86510) oder Begriff", False)}, lambda k, a: k.bmv(a.get("nr_oder_begriff"))),
    "ebm_verweise": ("Welche Knoten erwähnen eine Nummer, und worauf verweist sie? Für Folgenabschätzung bei Änderungen.",
                     {"nr": ("string", "GOP oder Abschnittsnummer", True)}, lambda k, a: k.verweise(a["nr"])),
}
