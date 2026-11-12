"""EBM aus dem amtlichen Quartals-PDF der KBV durchsuchen (Rückfallebene ohne Abzug).

  ek.py pdf build 2026-4      PDF laden, Text ziehen, GOP-Index bauen (ausgabe/pdf/, braucht pypdf)
  ek.py pdf gop 03000         Volltext einer GOP mit Seitenangabe
  ek.py pdf search "Begriff"  Volltextsuche
  ek.py pdf refs 03000        Nennungen der GOP in anderen Positionen

Quelle: https://www.kbv.de/documents/praxis/abrechnung/ebm/<JJJJ>-<Q>-ebm.pdf
Die Erkennung der Positionen ist heuristisch.
"""
import json, re, sys, urllib.request
from pathlib import Path

from .grundlagen import AUS
DATA = AUS / "pdf"
URL = "https://www.kbv.de/documents/praxis/abrechnung/ebm/{q}-ebm.pdf"
GOP_START = re.compile(r"^(\d{5}[A-Z]?) (\S.*)$")
PAGE_MARK = re.compile(r"^=====SEITE (\d+)=====$")
NOISE = re.compile(r"^(Kassenärztliche Bundesvereinigung KBV|Stand \d/\d{4}, erstellt am .*)$")
CONT_WORDS = {"und", "oder", "bis", "sowie", "bzw.", "bzw", "(", ",", "-", "–", "i.", "ff.", "Punkte", "€"}
SIGNALS = ("Obligater Leistungsinhalt", "Punkte", "€", "Fakultativer Leistungsinhalt", "einmal im", "je Behandlungsfall", "Die Gebührenordnungsposition", "Bewertung")


def build(quarter: str):
    import pypdf
    DATA.mkdir(exist_ok=True)
    pdf = DATA / f"{quarter}-ebm.pdf"
    if not pdf.exists():
        print("lade", URL.format(q=quarter), file=sys.stderr)
        urllib.request.urlretrieve(URL.format(q=quarter), pdf)
    cache = DATA / f"{quarter}-text.json"
    if cache.exists():
        lines = [tuple(x) for x in json.loads(cache.read_text(encoding="utf-8"))]
    else:
        r = pypdf.PdfReader(str(pdf))
        lines = []  # (seite, text)
        for i, p in enumerate(r.pages, 1):
            for ln in (p.extract_text() or "").splitlines():
                if not NOISE.match(ln.strip()):
                    lines.append((i, ln.rstrip()))
        cache.write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
    # Kandidaten für GOP-Anfänge
    starts = []
    for idx, (pg, ln) in enumerate(lines):
        m = GOP_START.match(ln)
        if m and m.group(2).split()[0] not in CONT_WORDS and (m.group(2)[0].isupper() or m.group(2)[0].isdigit()):
            starts.append(idx)
    recs, chapter = [], ""
    for n, idx in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        body = [t for _, t in lines[idx:end]]
        if not any(any(s in t for s in SIGNALS) for t in body[:60]):
            continue  # Fließtext, keine Position
        m = GOP_START.match(body[0])
        recs.append({"gop": m.group(1), "titel": m.group(2).strip(),
                     "seite": lines[idx][0], "text": "\n".join(body)})
    # Duplikate (Verweis-Zeilen mit gleichem Code) – längsten Treffer je Code und Seite behalten
    best = {}
    for r_ in recs:
        k = r_["gop"]
        if k not in best or len(r_["text"]) > len(best[k]["text"]):
            best[k] = r_
    out = DATA / f"{quarter}-index.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r_ in sorted(best.values(), key=lambda x: x["gop"]):
            r_["quartal"] = quarter
            f.write(json.dumps(r_, ensure_ascii=False) + "\n")
    (DATA / "aktuell").write_text(quarter)
    print(f"{len(best)} Positionen -> {out}")


def load():
    q = (DATA / "aktuell").read_text().strip()
    return q, [json.loads(l) for l in (DATA / f"{q}-index.jsonl").open(encoding="utf-8")]


def cmd_gop(code):
    q, recs = load()
    hit = [r for r in recs if r["gop"] == code.upper()]
    if not hit:
        sys.exit(f"{code} nicht im Index (Quartal {q})")
    r = hit[0]
    print(f"[EBM {q}, PDF-Seite {r['seite']}]\n{r['text']}")


def cmd_search(term):
    q, recs = load()
    words = [w.lower() for w in term.split()]
    scored = []
    for r in recs:
        t = r["text"].lower()
        if all(w in t for w in words):
            s = sum(t.count(w) for w in words) + 20 * sum(w in r["titel"].lower() for w in words)
            scored.append((s, r))
    for s, r in sorted(scored, key=lambda x: -x[0])[:25]:
        print(f"{r['gop']}  S.{r['seite']:<5} {r['titel'][:90]}")
    print(f"-- {len(scored)} Treffer (EBM {q})")


def cmd_refs(code):
    q, recs = load()
    for r in recs:
        if r["gop"] != code.upper() and re.search(rf"\b{re.escape(code)}\b", r["text"]):
            print(f"{r['gop']}  S.{r['seite']:<5} {r['titel'][:90]}")


def main(a):
    if not a:
        sys.exit(__doc__)
    {"build": lambda: build(a[1] if len(a) > 1 else "2026-4"),
     "gop": lambda: cmd_gop(a[1]), "search": lambda: cmd_search(" ".join(a[1:])),
     "refs": lambda: cmd_refs(a[1])}[a[0]]()
