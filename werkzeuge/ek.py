#!/usr/bin/env python3
"""Offener EBM-Katalog — Werkzeuge.

  python3 -I werkzeuge/ek.py abzug [--ansicht ops | --arztgruppen] [--limit N]   Online-Ansicht abziehen
  python3 -I werkzeuge/ek.py packen [QUARTAL]       Rohdaten packen (jsonl -> jsonl.gz)
  python3 -I werkzeuge/ek.py exportieren [QUARTAL]  Daten und Katalogseite nach ausgabe/ bauen
  python3 -I werkzeuge/ek.py pruefen [QUARTAL]      Struktur der erzeugten Daten prüfen
  python3 -I werkzeuge/ek.py vertraulich            eingecheckte Dateien auf vertrauliche Inhalte prüfen
  python3 -I werkzeuge/ek.py mcp [QUARTAL]          MCP-Server (stdio) für KI-Assistenten
  python3 -I werkzeuge/ek.py frage WERKZEUG '{json}'  ein Werkzeug direkt aufrufen, z. B. frage ebm_gop '{"nr":"03000"}'
  python3 -I werkzeuge/ek.py fragenkatalog         Fragenkatalog gegen den Katalog prüfen
  python3 -I werkzeuge/ek.py texte [QUARTAL]       Markdown je GOP und llms.txt nach ausgabe/site/
  python3 -I werkzeuge/ek.py bmv                    BMV-Ä-PDF laden und Text ziehen (braucht pypdf)
  python3 -I werkzeuge/ek.py pdf build|gop|search|refs …   EBM aus dem Quartals-PDF (braucht pypdf)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "abzug":
        from ek import abzug; return abzug.main(rest)
    if cmd == "packen":
        from ek import packen; return packen.main(rest)
    if cmd == "exportieren":
        from ek import export
        from ek.grundlagen import aktuelles_quartal
        export.main(rest[0] if rest else aktuelles_quartal()); return 0
    if cmd == "pruefen":
        from ek import pruefen; return pruefen.main(rest)
    if cmd == "vertraulich":
        from ek import vertraulich; return vertraulich.pruefen()
    if cmd == "mcp":
        from ek import mcp; return mcp.main(rest)
    if cmd == "frage":
        import json
        from ek.katalog import WERKZEUGE, Katalog
        print(json.dumps(WERKZEUGE[rest[0]][2](Katalog(), json.loads(rest[1]) if len(rest) > 1 else {}), ensure_ascii=False, indent=1)); return 0
    if cmd == "fragenkatalog":
        from ek import fragenkatalog; return fragenkatalog.main(rest)
    if cmd == "texte":
        from ek import texte; return texte.main(rest)
    if cmd == "bmv":
        from ek import bmv; return bmv.main(rest)
    if cmd == "pdf":
        from ek import pdf; return pdf.main(rest)
    print(f"Unbekannter Befehl: {cmd}\n{__doc__}"); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
