# Arbeitsregeln für dieses Repository

- **Eigenständig.** Das Repository muss ohne äußeren Kontext funktionieren: keine Verweise auf Ordner außerhalb, keine lokalen Pfade, keine unveröffentlichten Unterlagen oder Positionen. `ek.py vertraulich` prüft das; projektbezogene Muster stehen in `.vertraulich-muster` (nicht eingecheckt) bzw. in der Repository-Variable `VERTRAULICH_MUSTER`.
- **Nur veröffentlichte Quellen.** Inhalte stammen aus ebm.kbv.de und den Verträgen auf kbv.de. Nichts erfinden: keine Nummern, Beträge oder Adressen ohne Fundstelle. Vorschläge (Adressschema) sind als solche gekennzeichnet.
- **Nur Python-Standardbibliothek** für Abzug, Export, Prüfung und Tests. `pypdf` nur für die Hilfsbefehle `bmv` und `pdf`.
- **Abzug schonend.** Eine Anfrage nach der anderen mit Pause; kein paralleler Abzug derselben Ansicht.
- **Nach jeder Änderung:** `python3 -I -m unittest discover -s tests`, `python3 -I werkzeuge/ek.py exportieren`, `python3 -I werkzeuge/ek.py pruefen`, `python3 -I werkzeuge/ek.py vertraulich`; die Katalogseite im Browser prüfen. README und `docs/` mitführen.
- **Rohdaten** nur gepackt einchecken (`ek.py packen`).
- **Veröffentlichung** auf GitHub Pages nur mit Repository-Variable `PAGES_FREIGEGEBEN=ja`.
