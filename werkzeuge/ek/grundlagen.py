"""Pfade und Hilfen für alle Werkzeuge."""
import gzip, json
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
ROH = WURZEL / "rohdaten"          # Abzüge der Online-Ansicht, je Quartal (eingecheckt, gzip)
QUELLEN = WURZEL / "quellen"       # von Hand gepflegte Quellen (BMV-Ä)
AUS = WURZEL / "ausgabe"           # erzeugt, nicht eingecheckt
WEB = WURZEL / "web"               # Quelltext der Katalogseite


def datei(p):
    """Pfad zu einer JSONL-Datei, gepackt (.gz) oder ungepackt; None, wenn keine vorhanden ist."""
    p = Path(p)
    for c in (p, p.with_name(p.name + ".gz")):
        if c.exists():
            return c
    return None


def lies_jsonl(p):
    f = datei(p)
    if f is None:
        raise FileNotFoundError(p)
    op = gzip.open if f.suffix == ".gz" else open
    with op(f, "rt", encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def quartale():
    return sorted(d.name for d in ROH.iterdir() if d.is_dir() and datei(d / "nodes.jsonl")) if ROH.exists() else []


def aktuelles_quartal():
    q = quartale()
    if not q:
        raise SystemExit("Kein Abzug in rohdaten/. Zuerst: python3 -I werkzeuge/ek.py abzug")
    return q[-1]
