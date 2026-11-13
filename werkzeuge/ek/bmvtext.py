"""Volltext des Bundesmantelvertrags-Ärzte (BMV-Ä) und seiner Anlagen.

Grundlage sind die Textauszüge, die `ek.py bmv` aus den PDF auf kbv.de erzeugt (ausgabe/bmv/text/, nicht
eingecheckt). Gliederung je Dokument: Seiten (=====SEITE n=====) und Überschriften (§, Anhang, Abschnitt),
damit jeder Treffer mit Paragraf, Seite und Link belegt werden kann.
"""
import re
from functools import cached_property

from .grundlagen import AUS, QUELLEN

LEITER = re.compile(r"\.{6,}|…{3,}")  # Inhaltsverzeichnis mit Punktleitern
PARA = re.compile(r"^§\s*(\d+[a-z]?)\s*(.*)$")
GLIED = re.compile(r"^(Anhang\s+\d+[a-z]?|Abschnitt\s+\d+(?:\.\d+)*|Anlage\s+\d+[a-z]?)\b[ :–-]*(.{0,80})$")
SATZENDE = re.compile(r"(?<=[.;:])\s+(?=[(A-ZÄÖÜ0-9§])")


def _ueberschrift(zeile, naechste):
    """Erkennt Überschriften wie „§ 29a“ (Titel in der Folgezeile) oder „§ 3 Abrechnung und Vergütung“."""
    z = zeile.strip()
    if LEITER.search(z):
        return None
    m = PARA.match(z)
    if m:
        rest = m.group(2).strip()
        if not rest:
            titel = naechste.strip()
            if (titel and titel[:1].isupper() and len(titel) <= 90 and not titel.endswith(".")
                    and not re.search(r"\b(SGB|Absatz|ZV|Buchst\w*)\b|Abs\.|Nr\.", titel)):
                return f"§ {m.group(1)} {titel}"
            return f"§ {m.group(1)}"
        if (len(z) <= 80 and "," not in rest and not rest.endswith(".") and not rest.endswith(")")
                and not re.search(r"\b(SGB|Absatz|Satz|BMV|ZV|Buchst\w*|dieses|der|des)\b|Abs\.|Nr\.", rest)
                and rest[:1].isupper()):
            return f"§ {m.group(1)} {rest}"
        return None
    m = GLIED.match(z)
    if m and len(z) <= 75 and not z.endswith(",") and "." not in m.group(2) and not re.match(r"\s*(zu|zum|BMV|des|der|gemäß)\b", m.group(2)):
        return z
    return None


class BmvText:
    def __init__(self, verzeichnis=None):
        self.d = verzeichnis or (AUS / "bmv" / "text")

    @property
    def verfuegbar(self):
        return self.d.exists() and any(self.d.glob("*.txt"))

    @cached_property
    def liste(self):
        out = {}
        f = QUELLEN / "bmv" / "liste.tsv"
        for zeile in f.read_text(encoding="utf-8").splitlines() if f.exists() else []:
            url, name, *rest = zeile.split("\t")
            stamm = name.rsplit(".", 1)[0]
            out[stamm] = {"datei": name, "url": url, "titel": (rest[0] if rest else name).replace(" (PDF)", "")}
        return out

    @cached_property
    def bloecke(self):
        """Absätze mit Dokument, Seite und letzter Überschrift."""
        out = []
        for txt in sorted(self.d.glob("*.txt")):
            meta = self.liste.get(txt.stem, {"datei": txt.stem + ".pdf", "url": None, "titel": txt.stem})
            zeilen = txt.read_text(encoding="utf-8").splitlines()
            seite, kopf, puffer, start = 1, None, [], 1

            def schliessen():
                text = re.sub(r"-\s+\n?\s*(?=[a-zäöüß])", "", " ".join(puffer))  # Silbentrennung
                text = re.sub(r"\s+", " ", text).strip()
                if len(text) > 20 and not LEITER.search(text):
                    out.append({"stamm": txt.stem, **meta, "seite": start, "ueberschrift": kopf, "text": text})
                puffer.clear()

            for i, z in enumerate(zeilen):
                m = re.match(r"=====SEITE (\d+)=====", z)
                if m:
                    seite = int(m.group(1)); continue
                if not z.strip():
                    continue
                u = _ueberschrift(z, zeilen[i + 1] if i + 1 < len(zeilen) else "")
                if u:
                    schliessen(); kopf, start = u, seite; continue
                if re.match(r"^\(\d+[a-z]?\)", z.strip()) and puffer:
                    schliessen(); start = seite
                if not puffer:
                    start = seite
                puffer.append(z.strip())
            schliessen()
        return out

    def dokumente(self):
        gesehen = {}
        for b in self.bloecke:
            gesehen.setdefault(b["stamm"], {"datei": b["datei"], "titel": b["titel"]})
        return [{"dokument": k, **v} for k, v in gesehen.items()]

    def _passt_dokument(self, b, dokument):
        if not dokument:
            return True
        q = dokument.lower()
        return q in b["stamm"].lower() or q in b["titel"].lower() or q.replace("anlage ", "").zfill(2) == b["stamm"][:2]

    @staticmethod
    def _beleg(b):
        return {"dokument": b["titel"], "datei": b["datei"], "seite": b["seite"], "stelle": b["ueberschrift"],
                "url": f"{b['url']}#page={b['seite']}" if b.get("url") else None,
                "herkunft": "BMV-Ä bzw. Anlage, Textauszug aus dem PDF auf kbv.de"}

    def suche(self, text, dokument=None, grenze=8):
        woerter = [w for w in re.findall(r"[\wÄÖÜäöüß§.-]+", text.lower()) if len(w) > 1]
        if not woerter:
            return {"treffer": []}
        def treffer(mindest):
            tr = []
            for b in self.bloecke:
                if not self._passt_dokument(b, dokument):
                    continue
                t = (b["text"] + " " + (b["ueberschrift"] or "")).lower()
                da = [w for w in woerter if w in t]
                if len(da) < mindest:
                    continue
                s = 20 * len(da) + sum(min(t.count(w), 5) for w in da) + sum(3 for w in da if re.search(r"(?<!\w)" + re.escape(w), t))
                s += 6 if b["ueberschrift"] and any(w in b["ueberschrift"].lower() for w in woerter) else 0
                tr.append((s, b, len(da)))
            return sorted(tr, key=lambda x: -x[0])
        tr = treffer(len(woerter))
        r = {"anfrage": text, "anzahl": len(tr)}
        mindest = len(woerter)
        while not tr and mindest > max(1, (len(woerter) + 1) // 2):
            mindest -= 1
            tr = treffer(mindest)
            if tr:
                r["hinweis"] = f"Kein Absatz enthält alle Suchwörter; Treffer mit mindestens {mindest} von {len(woerter)} Wörtern."
        r["treffer"] = [{"auszug": self.auszug(b["text"], woerter), **self._beleg(b)} for _, b, _ in tr[:grenze]]
        return r

    @staticmethod
    def auszug(text, woerter, laenge=700):
        if len(text) <= laenge:
            return text
        saetze = SATZENDE.split(text)
        gew = [s for s in saetze if any(w in s.lower() for w in woerter)] or saetze[:2]
        out = ""
        for s in gew:
            if len(out) + len(s) > laenge and out:
                break
            out += ("" if not out else " … ") + s
        return out

    def paragraf(self, nr, dokument="bmv-aerzte"):
        nr = nr.strip().lstrip("§").strip()
        bl = [b for b in self.bloecke if self._passt_dokument(b, dokument) and b["ueberschrift"]
              and re.match(r"§\s*" + re.escape(nr) + r"(\s|$)", b["ueberschrift"])]
        if not bl:
            return None
        return {"stelle": bl[0]["ueberschrift"], "text": "\n".join(b["text"] for b in bl), **{k: v for k, v in self._beleg(bl[0]).items() if k != "stelle"}}
