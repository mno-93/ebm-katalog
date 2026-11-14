"""BMV-Ä und Anlagen laden und als Text ablegen — Arbeitsgrundlage für quellen/bmv/bmv_pauschalen.json.

Die PDF landen in ausgabe/bmv/pdf/ (nicht eingecheckt). Die Textauszüge werden gepackt nach rohdaten/bmv/
geschrieben (eingecheckt), dazu rohdaten/bmv/stand.json mit URL, Seitenzahl und SHA-256 je PDF. Damit arbeiten
MCP-Server, Texte und CI ohne Download. Die Liste der Dokumente steht in quellen/bmv/liste.tsv (URL, Dateiname,
Titel). Textauszug braucht `pypdf` (nicht in der Standardbibliothek).
"""
import datetime, gzip, hashlib, json, re, time, urllib.request
from .grundlagen import AUS, QUELLEN, ROH


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
    packen(pdfdir, txtdir)


def packen(pdfdir, txtdir):
    """Textauszüge nach rohdaten/bmv/*.txt.gz (reproduzierbar, ohne Zeitstempel) und Stand mit Prüfsummen."""
    roh = ROH / "bmv"
    roh.mkdir(parents=True, exist_ok=True)
    liste = {z.split("\t")[1]: z.split("\t") for z in (QUELLEN / "bmv" / "liste.tsv").read_text(encoding="utf-8").splitlines()}
    stand = []
    for txt in sorted(txtdir.glob("*.txt")):
        daten = txt.read_bytes()
        with open(roh / (txt.name + ".gz"), "wb") as fh, gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0) as gz:
            gz.write(daten)
        pdf = pdfdir / (txt.stem + ".pdf")
        url, name, *rest = liste.get(pdf.name, ["", pdf.name])
        e = {"datei": name, "url": url or None, "titel": (rest[0] if rest else name).replace(" (PDF)", ""),
             "seiten": len(re.findall(r"=====SEITE \d+=====", daten.decode("utf-8")))}
        if pdf.exists():
            e["sha256_pdf"] = hashlib.sha256(pdf.read_bytes()).hexdigest()
            e["abgerufen"] = datetime.date.fromtimestamp(pdf.stat().st_mtime).isoformat()
        stand.append(e)
    (roh / "stand.json").write_text(json.dumps({"hinweis": "Textauszüge der PDF auf kbv.de, maschinell mit pypdf gezogen (KI-gebaut). "
                                                "Verbindlich sind die PDF; Seitenumbrüche, Tabellen und Silbentrennung können fehlerhaft sein.",
                                                "dokumente": stand}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(stand)} Textauszüge gepackt nach {roh}")
