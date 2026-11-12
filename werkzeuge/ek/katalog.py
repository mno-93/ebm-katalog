"""Abfragen auf den exportierten Katalog — Grundlage für den MCP-Server und den Fragenkatalog.

Jede Antwort ist ein dict mit den Fakten und einem Feld `belege` (Quartal, Nummer, Knotenkennung,
Herkunft, Auszug). Antworten ohne Treffer sagen das ausdrücklich (`gefunden: False`), statt zu raten.
"""
import difflib
import html as H
import json
import re
from functools import cached_property

from .grundlagen import AUS, WURZEL, aktuelles_quartal

HINWEIS = ("KI-gebaut und nicht amtlich: abgeleitet aus der EBM-Online-Ansicht (ebm.kbv.de) und den Verträgen auf kbv.de. "
           "Mit einem KI-Assistenten erstellt und nur stichprobenartig geprüft. "
           "Verbindlich sind ausschließlich diese Veröffentlichungen.")
FELDER = {
    "bewertung.punkte / bewertung.euro": "Punktzahl und Eurobetrag aus dem Kopf der Detailansicht; der Eurobetrag gilt mit dem bundeseinheitlichen Orientierungswert, regionale Punktwerte können abweichen.",
    "merkmale": "Kennzeichen im Kopf der Detailansicht (Häkchen = zutreffend, Kreuz = nicht zutreffend), 1:1 übernommen. Ihre Bedeutung erläutert die Online-Ansicht nicht. „fachärztliche Grundversorgung“ erscheint dort auch bei hausärztlichen GOP mit Häkchen; das ist kein Fehler des Abzugs, aber ungeklärt — nicht deuten.",
    "zuschlaege": "Zuschläge und Zusatzpauschalen, die diese GOP erwähnen (Titel mit „Zuschlag“ oder „Zusatzpauschale“ unter den Rückverweisen). Ob sie im Einzelfall anfallen, regeln deren Bestimmungen.",
    "ausschluesse.bezug": "Bezug des Abrechnungsausschlusses, z. B. „in derselben Sitzung“, „am Behandlungstag“, „im Behandlungsfall“.",
    "ausschluesse.kapitel": "Ausschluss eines ganzen Abschnitts; ebm_nebeneinander löst ihn auf die Positionen des Abschnitts auf.",
    "zeiten": "Anhang 3 EBM: Kalkulationszeit und Prüfzeit in Minuten sowie Eignung der Prüfzeit (Tages-/Quartalsprofil). KA = keine Kalkulationszeit vorgegeben, ./. = keine Prüfzeit.",
    "ops.kategorie": "Kategorie des Eingriffs nach Anhang 2 (z. B. A5); bestimmt die zugeordneten GOP.",
    "ops.p115b": "Wert der Spalte „§115b“ der Anhang-2-Ansicht, 1:1 übernommen. Die Online-Ansicht erläutert ihn nicht; nicht deuten.",
    "ops.zuordnung.kalk / pruef": "Kalkulations- und Prüfzeit in Minuten (Spalten „Kalk. Zeit“ und „Prüfzeit“ der Anhang-2-Ansicht).",
    "arztgruppen": "Gruppen, in deren Filter die Position in der Online-Ansicht erscheint. Sichtbarkeit ist keine Abrechnungsberechtigung.",
}
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


def liste(x):
    """Eine oder mehrere Nummern: Liste oder Text mit Komma, Semikolon oder Leerzeichen."""
    if isinstance(x, (list, tuple)):
        return [str(v).strip().upper() for v in x if str(v).strip()]
    return [v.upper() for v in re.split(r"[,;\s]+", str(x or "").strip()) if v]


def auszuege(text, begriff, fenster=300, hoechstens=20):
    """Textstellen rund um jedes Vorkommen eines Begriffs (überlappende Fenster zusammengeführt)."""
    tl, b = text.lower(), begriff.lower()
    spannen, i = [], tl.find(b)
    while i >= 0 and len(spannen) < hoechstens:
        a, e = max(0, i - fenster), min(len(text), i + len(b) + fenster)
        if spannen and a <= spannen[-1][1]:
            spannen[-1][1] = e
        else:
            spannen.append([a, e])
        i = tl.find(b, i + len(b))
    return [("…" if a else "") + text[a:e].strip() + ("…" if e < len(text) else "") for a, e in spannen]


def synonyme():
    f = WURZEL / "quellen" / "synonyme.json"
    return json.loads(f.read_text(encoding="utf-8"))["synonyme"] if f.exists() else {}


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

    @cached_property
    def anhang3(self):
        """Zeilen aus Anhang 3 (Zeitaufwand): GOP -> Kalkulations-, Prüfzeit, Eignung."""
        ns = [n for n in self.nr.get("3", []) if self.pfad(n)[:1] and self.pfad(n)[0].startswith("VI")]
        if not ns:
            return {}
        s = "\n".join(a["text"] for a in self._abschnitte(ns[0]["knotenId"]))
        z = re.findall(r"\|\s*(\d{5}[A-Z]?)([*°]{0,3})\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*(?=\||$)", s)
        return {"knoten": ns[0], "zeilen": {r[0]: {"kalkulationszeit": r[3], "pruefzeit": r[4], "eignung": r[5], "kennzeichen": r[1] or None} for r in z}}

    def _in_abschnitt(self, nr, kap):
        """Liegt eine Nummer in dem Abschnitt eines Kapitel-Ausschlusses?"""
        ziele = set(kap.get("k", "").split("_")) | {kap.get("nr")}
        for n in self.nr.get(nr, []):
            p = self.K.get(n["eltern"])
            while p:
                if p["knotenId"] in ziele or p["nr"] in ziele:
                    return True
                p = self.K.get(p["eltern"])
        return False

    # ---------- Werkzeuge ----------
    def gop(self, nr, umfang="voll"):
        nrs = liste(nr)
        if len(nrs) > 1:
            return {"positionen": [self.gop(x, umfang) for x in nrs[:20]], "gekuerzt": len(nrs) > 20, "hinweis": HINWEIS}
        nr = nrs[0] if nrs else ""
        n, kinder = self.gop_knoten(nr)
        if not n:
            b = self.bmv(nr)
            if b.get("gefunden"):
                return {"gefunden": False, "hinweis": f"{nr} ist keine Gebührenordnungsposition des EBM, sondern eine Pauschale aus dem BMV-Ä.", "bmv": b}
            aehnlich = sorted({x for x, ns in self.nr.items() if x[:4] == nr[:4] and any(m["typ"] == "gop" for m in ns)})[:15]
            return {"gefunden": False, "hinweis": f"{nr} steht im EBM {self.quartal} nicht.", "aehnlich": aehnlich, "quartal": self.quartal}
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
             "erwaehnt_in": [self._nr_von(k) for k in d.get("referenziert_von", [])][:25],
             "erwaehnt_in_anzahl": len(d.get("referenziert_von", [])),
             "bmv_bezuege": d.get("bmv_verweise", [])}
        zus = {}
        for k in d.get("referenziert_von", []):
            h = self.gop_knoten(self.K[k]["nr"])[0] if self.K[k]["typ"] == "gop" else None
            if h and re.search(r"zuschlag|zusatzpauschale", _norm(h["titel"] or h["baumtitel"])):
                zus[h["nr"]] = f"{h['nr']} {h['titel'] or h['baumtitel']}"
        if zus:
            r["zuschlaege"] = [zus[x] for x in sorted(zus)]
        if r["erwaehnt_in_anzahl"] > 25:
            r["erwaehnt_in_hinweis"] = "Gekürzt auf 25; vollständige Liste mit ebm_verweise."
        z = self.anhang3.get("zeilen", {}).get(n["nr"]) if self.anhang3 else None
        if z:
            r["zeiten"] = {**z, "quelle": "Anhang 3 EBM"}
        if self.ag_daten:
            p = self.pos[n["knotenId"]]
            r["arztgruppen"] = [g for g, m in self.ag_daten["mengen"].items() if p in m]
        if self.ops_daten and n["nr"] in self.ops_daten["nach_gop"]:
            r["ops_anzahl"] = len(self.ops_daten["nach_gop"][n["nr"]])
        r["belege"] = [self.beleg(n)]
        if umfang == "kompakt":
            behalten = {"Abrechnungsbestimmung", "Obligater Leistungsinhalt"}
            r["abschnitte"] = [a for a in r["abschnitte"] if a["ueberschrift"] in behalten]
            r["umfang"] = "kompakt: nur Bewertung, obligater Leistungsinhalt, Abrechnungsbestimmung, Ausschlüsse; Anmerkungen mit umfang=voll"
            for x in ("erwaehnt_in", "erwaehnt_in_hinweis", "untergliederung"):
                r.pop(x, None)
        r["hinweis"] = HINWEIS
        return r

    def knoten(self, nr_oder_id, filter=None, grenze=15000):
        """Abschnitt, Präambel oder Bestimmung über Nummer (z. B. 4.3.1) oder Knotenkennung.

        filter: nur Textstellen rund um diesen Begriff (z. B. eine GOP in Anhang 3).
        grenze: Höchstlänge je Text in Zeichen; längere Texte werden gekürzt und als gekürzt gekennzeichnet.
        """
        m = re.fullmatch(r"\s*(anhang|ab|allgemeine bestimmungen?)\s+(\d+(?:\.\d+)*)\s*", nr_oder_id, re.I)
        if m:
            wurzel = "VI" if m.group(1).lower() == "anhang" else "I "
            ns = [n for n in self.nr.get(m.group(2), []) if self.pfad(n)[:1] and self.pfad(n)[0].startswith(wurzel)]
        else:
            ns = [self.K[nr_oder_id]] if nr_oder_id in self.K else self.nr.get(nr_oder_id.strip(), [])
        if not ns:
            return {"gefunden": False, "hinweis": f"Kein Knoten {nr_oder_id} im EBM {self.quartal}. Anhänge mit „Anhang N“, Allgemeine Bestimmungen mit „AB N“ abrufen."}
        out, gekuerzt = [], False
        for n in ns:
            abschnitte = []
            for a in self._abschnitte(n["knotenId"]):
                if filter:
                    st = auszuege(a["text"], filter)
                    if st:
                        abschnitte.append({"ueberschrift": a["ueberschrift"], "auszuege": st})
                elif len(a["text"]) > grenze:
                    gekuerzt = True
                    abschnitte.append({"ueberschrift": a["ueberschrift"], "text": a["text"][:grenze] + " …",
                                       "gekuerzt": f"{len(a['text']):,} Zeichen, gezeigt {grenze:,}; gezielt mit filter abrufen".replace(",", ".")})
                else:
                    abschnitte.append(a)
            if filter and not abschnitte:
                continue
            out.append({"nr": n["nr"], "titel": n["titel"] or n["baumtitel"], "typ": n["typ"], "pfad": " › ".join(self.pfad(n)),
                        "abschnitte": abschnitte,
                        "enthaelt": [f"{self.K[c]['nr']} {self.K[c]['titel'] or self.K[c]['baumtitel']}" for c in n["kinder"]][:60],
                        "beleg": self.beleg(n)})
        if not out:
            return {"gefunden": False, "hinweis": f"„{filter}“ kommt in {nr_oder_id} nicht vor."}
        r = {"gefunden": True, "treffer": out, "mehrdeutig": len(out) > 1, "hinweis": HINWEIS}
        if filter:
            r["filter"] = filter
        if gekuerzt:
            r["gekuerzt"] = True
        return r

    def suche(self, text, bereich="alle", grenze=15, _umformuliert=False):
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
                tr.append((s, self._treffer(n)))
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
        r = {"anfrage": text, "anzahl": len(tr), "treffer": [t for _, t in tr[:grenze]], "quartal": self.quartal}
        neu = None if _umformuliert else self._synonym(text)
        if neu and tr:
            r["auch_unter"] = {"begriff": neu, "treffer": self.suche(neu, bereich, 5, _umformuliert=True)["treffer"],
                               "hinweis": "Für die Anfrage ist ein Fachbegriff hinterlegt; Treffer dazu zusätzlich."}
        if not tr and neu:
            r2 = self.suche(neu, bereich, grenze, _umformuliert=True)
            if r2["anzahl"]:
                r2.update({"anfrage": text, "umformuliert_zu": neu, "umformuliert_hinweis": "Ohne Treffer für die Anfrage; gesucht wurde mit einem hinterlegten Fachbegriff."})
                return r2
        if bereich in ("alle", "ebm") and len(w) > 1 and not any(t.get("typ") == "gop" for _, t in tr[:grenze]):
            gops = [n for n in self.index["knoten"] if n["typ"] == "gop"]
            titel = {n["knotenId"]: _norm(n["titel"] or n["baumtitel"]) for n in gops}
            import math
            idf = {x: math.log(len(gops) / (1 + sum(1 for s in titel.values() if x in s))) for x in w}
            teil = []
            for n in gops:
                s, m = 0.0, 0
                for x in w:
                    if x in titel[n["knotenId"]]:
                        m += 1
                        ganz = re.search(r"(?<!\w)" + re.escape(x) + r"(?!\w)", titel[n["knotenId"]])
                        s += idf[x] * (2 if ganz else 1)
                if m:
                    teil.append((s, m, n))
            gesehen, out = set(), []
            for _, m, n in sorted(teil, key=lambda x: -x[0]):
                if n["nr"] not in gesehen:
                    gesehen.add(n["nr"]); out.append({**self._treffer(n), "passende_woerter": m})
                if len(out) >= 10:
                    break
            if out:
                r["teiltreffer"] = out
                r["teiltreffer_hinweis"] = "Keine Gebührenordnungsposition enthält alle Suchwörter; diese GOP enthalten einen Teil davon im Titel."
        return r

    def _treffer(self, n):
        t = {"bereich": "ebm", "nr": n["nr"], "titel": n["titel"] or n["baumtitel"], "typ": n["typ"], "knotenId": n["knotenId"]}
        if n["typ"] == "gop" and n.get("bewertung"):
            t["punkte"] = n["bewertung"].get("punkte")
        return t

    def _synonym(self, text):
        syn, q = synonyme(), _norm(text)
        neu = q
        for alt, fach in syn.items():
            neu = re.sub(r"(?<![\w-])" + re.escape(alt) + r"(?![\w-])", fach, neu)
        return neu if neu != q else None

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
                    for kap in z.get("kapitel", []):
                        if self._in_abschnitt(y, kap):
                            out.append({"eingetragen_bei": x, "bezug": z["bezug"], "ueber_abschnitt": kap["nr"],
                                        "beleg": self.beleg(n, f"Abrechnungsausschluss {z['bezug']}: Abschnitt {kap['nr']} (enthält {y})")})
            if self.bmv_daten:
                for p in self.bmv_daten["pauschalen"]:
                    if (p["nr"] or p["id"]) == x:
                        for z in p["ausschluesse"]:
                            if y in z["nr"]:
                                out.append({"eingetragen_bei": x, "bezug": z["bezug"], "beleg": self.bmv_beleg(p)})
            return out
        bs = liste(b)
        if len(bs) > 1:
            einzeln = [self.nebeneinander(a, x) for x in bs[:100]]
            return {"a": liste(a)[0] if liste(a) else a, "geprueft": len(einzeln),
                    "mit_ausschluss": [{"b": e["b"], "bezuege": sorted({x["bezug"] for x in e["eintraege"]}),
                                        "eingetragen_bei": sorted({x["eingetragen_bei"] for x in e["eintraege"]}),
                                        "ueber_abschnitt": sorted({x["ueber_abschnitt"] for x in e["eintraege"] if x.get("ueber_abschnitt")})}
                                       for e in einzeln if e.get("ausschluss_eingetragen")],
                    "ohne_ausschluss": [e["b"] for e in einzeln if e.get("bekannt", True) and not e.get("ausschluss_eingetragen")],
                    "unbekannt": [x for e in einzeln if e.get("bekannt") is False for x in e.get("unbekannt", [])],
                    "gekuerzt": len(bs) > 100,
                    "hinweis": "Sammelprüfung; Belege je Paar mit einer Einzelprüfung. Kein eingetragener Ausschluss ist keine Zusage der Berechnungsfähigkeit.",
                    "quartal": self.quartal}
        a, b = a.strip().upper(), (bs[0] if bs else "")
        unbekannt = [x for x in (a, b) if x not in self.nr and not (self.bmv_daten and x in self.bmv_daten["nach_id"])]
        if unbekannt:
            return {"bekannt": False, "unbekannt": unbekannt, "b": b, "hinweis": f"Nicht im Katalog: {', '.join(unbekannt)}."}
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
                    "beleg": {"quartal": self.quartal, "herkunft": f"Anhang-2-Ansicht {OPS_URL}", "knotenId": o["id"]},
                    "felder": {k: v for k, v in FELDER.items() if k.startswith("ops.")}, "hinweis": HINWEIS}
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
            neu = self._synonym(q)
            if neu:
                r = self.bmv(neu)
                if r.get("gefunden"):
                    r.update({"umformuliert_zu": neu, "umformuliert_hinweis": "Ohne Treffer für die Anfrage; gesucht wurde mit einem hinterlegten Fachbegriff."})
                    return r
            woerter = sorted({w for x in d["pauschalen"] for w in re.findall(r"[\wÄÖÜäöüß-]{4,}", x["titel"])})
            nah = difflib.get_close_matches(q, woerter, n=5, cutoff=0.6)
            return {"gefunden": False, "hinweis": f"Keine Pauschale „{q}“ im BMV-Ä-Teil des Katalogs.",
                    "vorschlaege": nah, "regelungen": [a["titel"] for a in d["anlagen"]],
                    "nicht_erfasst": d.get("ohne_eigene_pauschale")}
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
        r = {"nr": n["nr"], "erwaehnt_in": [f"{self.K[k]['nr']} {self.K[k]['titel'] or self.K[k]['baumtitel']}" for k in d.get("referenziert_von", [])],
             "verweist_auf": [f"{self.K[k]['nr']} {self.K[k]['titel'] or self.K[k]['baumtitel']}" for k in d.get("verweise", [])],
             "beleg": self.beleg(n)}
        z = self.anhang3.get("zeilen", {}).get(n["nr"]) if self.anhang3 else None
        if z:
            r["in_tabellen"] = [{"stelle": "Anhang 3 (Zeitaufwand)", **z, "beleg": self.beleg(self.anhang3["knoten"])}]
        if self.ops_daten and n["nr"] in self.ops_daten["nach_gop"]:
            r.setdefault("in_tabellen", []).append({"stelle": "Anhang 2 (OPS-Zuordnung)", "ops_anzahl": len(self.ops_daten["nach_gop"][n["nr"]])})
        r["hinweis"] = "erwaehnt_in: Knoten mit Link oder Nummer im Text; in_tabellen: Fundstellen in den Tabellen der Anhänge 2 und 3."
        return r

    def felder(self):
        return {"felder": FELDER, "hinweis": HINWEIS}


WERKZEUGE = {
    "ebm_suche": ("Volltextsuche im EBM, im Anhang 2 (OPS) und in den Pauschalen des BMV-Ä. Liefert Nummern, Titel und bei GOP die Punktzahl; Details mit den anderen Werkzeugen. "
                  "Ohne Treffer wird mit hinterlegten Fachbegriffen erneut gesucht (umformuliert_zu); enthält keine GOP alle Wörter, kommen teiltreffer.",
                  {"text": ("string", "Suchbegriffe oder Nummer", True), "bereich": ("string", "alle | ebm | ops | bmv", False, ["alle", "ebm", "ops", "bmv"]),
                   "grenze": ("integer", "Anzahl Treffer, Standard 15", False)},
                  lambda k, a: k.suche(a["text"], a.get("bereich", "alle"), int(a.get("grenze", 15)))),
    "ebm_gop": ("Angaben zu einer oder mehreren Gebührenordnungspositionen: Bewertung (auch Altersstufen), Merkmale, Leistungsinhalt, Abrechnungsbestimmung, Anmerkungen, "
                "Ausschlüsse, Arztgruppen, Zeiten aus Anhang 3, Zuschläge, die die GOP erwähnen, Bezüge zum BMV-Ä. Mehrere Nummern durch Komma trennen (höchstens 20). "
                "umfang=kompakt lässt Anmerkungen und Rückverweise weg.",
                {"nr": ("string", "GOP, z. B. 03000, oder mehrere: 03000, 03040", True),
                 "umfang": ("string", "voll (Standard) | kompakt", False, ["voll", "kompakt"])},
                lambda k, a: k.gop(a["nr"], a.get("umfang", "voll"))),
    "ebm_abschnitt": ("Text eines Abschnitts, einer Präambel, einer Allgemeinen Bestimmung oder eines Anhangs, z. B. 4.3.1, 3.1, „Anhang 2“ oder „AB 4.3.1“. Gleiche Nummern kommen in Allgemeinen Bestimmungen, "
                      "Kapiteln und Anhängen vor; dann alle Treffer mit Pfad. Lange Texte werden gekürzt; mit filter nur die Stellen rund um einen Begriff (z. B. eine GOP).",
                      {"nr": ("string", "Abschnittsnummer oder Knotenkennung", True), "filter": ("string", "optional: nur Textstellen rund um diesen Begriff", False)},
                      lambda k, a: k.knoten(a["nr"], a.get("filter"))),
    "ebm_nebeneinander": ("Prüft, ob zwischen Nummern (GOP oder BMV-Ä-Pauschale) ein Abrechnungsausschluss eingetragen ist, in beide Richtungen, mit Bezug; "
                          "Ausschlüsse ganzer Abschnitte werden aufgelöst. b kann mehrere Nummern enthalten (Sammelprüfung, höchstens 100).",
                          {"a": ("string", "erste Nummer", True), "b": ("string", "zweite Nummer oder mehrere, durch Komma getrennt", True)},
                          lambda k, a: k.nebeneinander(a["a"], a["b"])),
    "ebm_arztgruppe": ("Arztgruppenfilter der Online-Ansicht: Liste der Gruppen, Umfang einer Gruppe oder ob eine GOP für eine Gruppe sichtbar ist.",
                       {"gruppe": ("string", "Arztgruppe, z. B. Hausarzt", False, "ARZTGRUPPEN"), "gop": ("string", "optional: GOP", False)},
                       lambda k, a: k.arztgruppe(a.get("gruppe"), a.get("gop"))),
    "ebm_ops": ("Anhang 2: Kategorie, §115b-Spalte und zugeordnete GOP zu einem OPS-Code, oder alle OPS-Codes zu einer GOP der Kapitel 31/36.",
                {"code": ("string", "OPS-Code, z. B. 5-010.2", False), "gop": ("string", "GOP, z. B. 31272", False)}, lambda k, a: k.ops(a.get("code"), a.get("gop"))),
    "ebm_bmv": ("Pauschalen aus dem Bundesmantelvertrag-Ärzte und seinen Anlagen, die nicht im EBM stehen (z. B. Onkologie, Sozialpsychiatrie, DiGA, Kurarzt, TI-Pauschale). "
                "Ohne Argument: Übersicht mit nicht erfassten Regelungen.",
                {"nr_oder_begriff": ("string", "Nummer (z. B. 86510) oder Begriff", False)}, lambda k, a: k.bmv(a.get("nr_oder_begriff"))),
    "ebm_verweise": ("Welche Knoten erwähnen eine Nummer, worauf verweist sie, und in welchen Anhangtabellen (Anhang 2, Anhang 3) steht sie? Für Folgenabschätzung bei Änderungen.",
                     {"nr": ("string", "GOP oder Abschnittsnummer", True)}, lambda k, a: k.verweise(a["nr"])),
    "ebm_felder": ("Erklärt die Felder der Werkzeugergebnisse (Merkmale, Zeiten, Kategorie, §115b-Spalte, kalk/pruef, Ausschlussbezug).", {}, lambda k, a: k.felder()),
}

TITEL = {"ebm_suche": "EBM durchsuchen", "ebm_gop": "Gebührenordnungsposition", "ebm_abschnitt": "Abschnitt oder Präambel",
         "ebm_nebeneinander": "Nebeneinanderberechnung prüfen", "ebm_arztgruppe": "Arztgruppenfilter", "ebm_ops": "OPS-Zuordnung (Anhang 2)",
         "ebm_bmv": "Pauschalen aus dem BMV-Ä", "ebm_verweise": "Verweise und Folgenabschätzung", "ebm_felder": "Felder erklärt"}
