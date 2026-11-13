"""Fragenkatalog gegen den Katalog prüfen: liefern die Werkzeuge die belegten Fakten?

Liest fragen/fragenkatalog.json, ruft je Frage das Werkzeug auf und wertet die Prüfungen aus.
Bericht nach ausgabe/fragenkatalog-bericht.md; Exit 1, wenn eine Prüfung fehlschlägt.
"""
import json
import re

from .grundlagen import AUS, WURZEL
from .katalog import WERKZEUGE, Katalog


def wert(obj, pfad):
    for teil in re.findall(r"[^.\[\]]+|\[\d+\]", pfad):
        if teil.startswith("["):
            obj = obj[int(teil[1:-1])]
        else:
            obj = obj[teil]
    return obj


def pruefe(ergebnis, p):
    text = json.dumps(ergebnis, ensure_ascii=False)
    if "enthaelt" in p:
        return p["enthaelt"] in text, f"enthält „{p['enthaelt']}“"
    try:
        v = wert(ergebnis, p["pfad"])
    except (KeyError, IndexError, TypeError):
        return False, f"{p['pfad']} fehlt"
    if "gleich" in p:
        return v == p["gleich"], f"{p['pfad']} = {p['gleich']!r} (ist {v!r})"
    if "min" in p:
        n = len(v) if isinstance(v, (list, dict, str)) else v
        return n >= p["min"], f"{p['pfad']} ≥ {p['min']} (ist {n})"
    if "laenge" in p:
        return len(v) == p["laenge"], f"Länge {p['pfad']} = {p['laenge']} (ist {len(v)})"
    if "nicht_leer" in p:
        return bool(v), f"{p['pfad']} vorhanden"
    return False, f"unbekannte Prüfung {p}"


def main(argv=None):
    d = json.loads((WURZEL / "fragen" / "fragenkatalog.json").read_text(encoding="utf-8"))
    k = Katalog(argv[0] if argv else None)
    zeilen, fehler = [], 0
    uebersprungen = 0
    for f in d["fragen"]:
        if f.get("benoetigt") == "bmv_text" and not k.bmvtext.verfuegbar:
            uebersprungen += 1
            zeilen.append(f"| {f['id']} | ⏭ | {f['frage']} | Vertragstext nicht geladen (ek.py bmv) |")
            continue
        try:
            erg = WERKZEUGE[f["werkzeug"]][2](k, f["argumente"])
            res = [pruefe(erg, p) for p in f["pruefungen"]]
        except Exception as e:
            res = [(False, f"Fehler: {e}")]
        ok = all(r for r, _ in res)
        fehler += not ok
        zeilen.append(f"| {f['id']} | {'✅' if ok else '❌'} | {f['frage']} | {'; '.join(t for r, t in res if not r) or '—'} |")
        if not ok:
            print(f"❌ {f['id']} {f['frage']}: " + "; ".join(t for r, t in res if not r))
    b = WURZEL / "fragen" / "beispielantworten.json"
    bsp = json.loads(b.read_text(encoding="utf-8"))["beispiele"] if b.exists() else []
    for f in bsp:
        res = []
        for i, s in enumerate(f["schritte"], 1):
            try:
                erg = WERKZEUGE[s["werkzeug"]][2](k, s["argumente"])
                res += [(r, f"Schritt {i}: {t}") for r, t in (pruefe(erg, p) for p in s["pruefungen"])]
            except Exception as e:
                res.append((False, f"Schritt {i}: Fehler: {e}"))
        ok = all(r for r, _ in res)
        fehler += not ok
        zeilen.append(f"| {f['id']} | {'✅' if ok else '❌'} | Beispielantwort: {f['frage']} | {'; '.join(t for r, t in res if not r) or '—'} |")
        if not ok:
            print(f"❌ {f['id']} {f['frage']}: " + "; ".join(t for r, t in res if not r))
    n = len(d["fragen"]) + len(bsp) - uebersprungen
    bericht = [f"# Fragenkatalog — Prüfbericht {k.quartal}", "", f"{n - fehler} von {n} Fragen bestanden (davon {len(bsp)} Beispielantworten).", "",
               d["hinweis"], "", "| ID | Ergebnis | Frage | Abweichung |", "|---|---|---|---|"] + zeilen
    AUS.mkdir(exist_ok=True)
    (AUS / "fragenkatalog-bericht.md").write_text("\n".join(bericht) + "\n", encoding="utf-8")
    print(f"Fragenkatalog {k.quartal}: {n - fehler} von {n} bestanden (davon {len(bsp)} Beispielantworten)" + (f", {uebersprungen} übersprungen (Vertragstext nicht geladen)" if uebersprungen else ""))
    return 1 if fehler else 0
