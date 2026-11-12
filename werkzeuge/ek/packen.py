"""Rohdaten eines Abzugs packen: *.jsonl -> *.jsonl.gz (deterministisch, ohne Zeitstempel)."""
import gzip
from .grundlagen import ROH


def main(argv=None):
    q = argv[0] if argv else None
    ziele = [ROH / q] if q else [d for d in ROH.iterdir() if d.is_dir()]
    n = 0
    for d in ziele:
        for f in sorted(d.rglob("*.jsonl")):
            gz = f.with_name(f.name + ".gz")
            with open(f, "rb") as src, open(gz, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as out:
                out.write(src.read())
            f.unlink(); n += 1
            print(f"{gz.relative_to(ROH)}  {gz.stat().st_size // 1024} KB")
    print(f"{n} Dateien gepackt")
