"""Strukturprüfung der erzeugten Daten in ausgabe/<Q>/ (nach `ek.py exportieren`).

Harte Fehler (Exit 1): fehlende Dateien, leere oder widersprüchliche Struktur, Verweise auf unbekannte Knoten
innerhalb der erzeugten Daten. Hinweise (kein Fehler): Verweisziele, die schon in der Online-Ansicht fehlen,
OPS-Zuordnungen auf GOP außerhalb des Baums, unvollständige Arztgruppen.
"""
import json
from .grundlagen import AUS, aktuelles_quartal

MINDEST = {"knoten": 3000, "gop": 2500}


def main(argv=None):
    q = argv[0] if argv else aktuelles_quartal()
    d = AUS / q
    fehler, hinweise = [], []
    def lade(name, pflicht=True):
        f = d / name
        if not f.exists():
            (fehler if pflicht else hinweise).append(f"{name} fehlt")
            return None
        return json.loads(f.read_text(encoding="utf-8"))
    idx = lade("index.json")
    if idx is None:
        print("\n".join(fehler)); return 1
    K = {n["knotenId"]: n for n in idx["knoten"]}
    if len(K) != len(idx["knoten"]): fehler.append("doppelte Knoten-IDs")
    if len(K) < MINDEST["knoten"]: fehler.append(f"nur {len(K)} Knoten")
    gops = {n["nr"] for n in idx["knoten"] if n["typ"] == "gop"}
    if len(gops) < MINDEST["gop"]: fehler.append(f"nur {len(gops)} GOP")
    for n in idx["knoten"]:
        if n["eltern"] and n["eltern"] not in K: fehler.append(f"{n['nr']}: Elternknoten fehlt")
        for c in n["kinder"]:
            if K.get(c, {}).get("eltern") != n["knotenId"]: fehler.append(f"{n['nr']}: Kind {c} passt nicht")
    teile = {n["teil"] for n in idx["knoten"]}
    inhalt = {}
    for t in sorted(teile):
        p = lade(f"teil-{t}.json")
        if p: inhalt.update(p)
    ohne = [k for k in K if k not in inhalt]
    if ohne: hinweise.append(f"{len(ohne)} Knoten ohne Inhalt (z. B. reine Gliederungsknoten)")
    for k, v in inhalt.items():
        if k not in K: fehler.append(f"Inhalt für unbekannten Knoten {k}")
        for r in v.get("verweise", []) + v.get("referenziert_von", []):
            if r not in K: fehler.append(f"{k}: Verweis auf unbekannten Knoten {r}")
    un = d / "unaufgeloest.txt"
    if un.exists(): hinweise.append(f"{len(un.read_text().split())} Verweisziele fehlen schon in der Online-Ansicht")
    ag = lade("arztgruppen.json", pflicht=False)
    if ag:
        for g, ids in ag["sichtbar"].items():
            if any(i >= len(idx["knoten"]) for i in ids): fehler.append(f"Arztgruppe {g}: Index außerhalb")
        if ag["unvollstaendig"]: hinweise.append(f"{len(ag['unvollstaendig'])} Arztgruppen unvollständig abgezogen")
        if ag["nicht_zugeordnet"]: hinweise.append(f"nicht zugeordnete Knoten im Arztgruppenfilter: {ag['nicht_zugeordnet']}")
    ops = lade("ops.json", pflicht=False)
    if ops:
        fremd = {g["gop"] for o in ops["knoten"] for g in o.get("gops", []) if g["gop"] not in gops}
        if fremd: hinweise.append(f"{len(fremd)} GOP aus Anhang 2 nicht im EBM-Baum: {sorted(fremd)[:10]}")
    bmv = lade("bmv.json", pflicht=False)
    if bmv:
        for p in bmv["pauschalen"]:
            if not p["fundstelle"].get("seite"): fehler.append(f"BMV-Ä {p['id']}: Fundstelle ohne Seite")
            if not p["fundstelle"].get("url"): hinweise.append(f"BMV-Ä {p['id']}: keine URL zur Fundstelle")
            for a in p["ausschluesse"]:
                for nr in a["nr"]:
                    if nr not in gops and nr not in {x["nr"] for x in bmv["pauschalen"]}:
                        hinweise.append(f"BMV-Ä {p['id']}: Ausschluss {nr} unbekannt")
    for h in hinweise: print("Hinweis:", h)
    for f in fehler[:50]: print("FEHLER:", f)
    print(f"Prüfung {q}: {len(K)} Knoten, {len(gops)} GOP, {len(fehler)} Fehler, {len(hinweise)} Hinweise")
    return 1 if fehler else 0
