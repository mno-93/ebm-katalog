"""BMV-Ä und Anlagen laden und als Text ablegen — Arbeitsgrundlage für quellen/bmv/bmv_pauschalen.json.

Die PDF und Texte landen in ausgabe/bmv/ (nicht eingecheckt). Die Liste der Dokumente steht in
quellen/bmv/liste.tsv (URL, Dateiname, Titel). Textauszug braucht `pypdf` (nicht in der Standardbibliothek).
"""
import time, urllib.request
from .grundlagen import AUS, QUELLEN


def main(argv=None):
    pdfdir, txtdir = AUS / "bmv" / "pdf", AUS / "bmv" / "text"
    pdfdir.mkdir(parents=True, exist_ok=True); txtdir.mkdir(parents=True, exist_ok=True)
    for zeile in (QUELLEN / "bmv" / "liste.tsv").read_text(encoding="utf-8").splitlines():
        url, name, *_ = zeile.split("\t")
        ziel = pdfdir / name
        if not ziel.exists():
            urllib.request.urlretrieve(url, ziel); time.sleep(0.3)
    try:
        import pypdf
    except ImportError:
        raise SystemExit(f"PDF geladen nach {pdfdir}. Für den Textauszug pypdf installieren.")
    for pdf in sorted(pdfdir.iterdir()):
        out = txtdir / (pdf.stem + ".txt")
        if out.exists():
            continue
        r = pypdf.PdfReader(str(pdf))
        out.write_text("".join(f"\n=====SEITE {i}=====\n" + (p.extract_text() or "") for i, p in enumerate(r.pages, 1)), encoding="utf-8")
        print(pdf.name, len(r.pages))
    print(f"Texte in {txtdir}")
