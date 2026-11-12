# Offener EBM-Katalog

Prototyp eines maschinenlesbaren, verlinkten Einheitlichen Bewertungsmaßstabs (EBM). Jede Gebührenordnungsposition, jeder Abschnitt, jeder OPS-Code des Anhangs 2 und jede Pauschale aus dem Bundesmantelvertrag-Ärzte (BMV-Ä), die nicht im EBM steht, erhält einen festen Eintrag mit Links in beide Richtungen.

> **KI-gebaut.** Abzug, Aufbereitung, Werkzeuge, Texte und Dokumentation dieses Repositorys wurden mit einem KI-Assistenten (Claude) erstellt und nur stichprobenartig geprüft. Fehler sind möglich.
>
> **Nicht amtlich.** Die Inhalte stammen aus der EBM-Online-Ansicht der Kassenärztlichen Bundesvereinigung (ebm.kbv.de) und aus den Verträgen auf kbv.de. Verbindlich sind ausschließlich diese Veröffentlichungen.

## Inhalt

| Teil | Quelle | Umfang (Quartal 2026/Q4) |
|---|---|---|
| EBM-Ansicht | ebm.kbv.de, Baum und Detailansicht aller Knoten | 3.969 Knoten, 3.179 Gebührenordnungspositionen |
| Arztgruppenfilter | ebm.kbv.de, gefilterter Baum je Arztgruppe | 46 Arztgruppen |
| Anhang-2-Ansicht | ebm.kbv.de/ops.xhtml, OPS-Codes mit Kategorie und GOP-Zuordnung | 13.106 Knoten, davon 11.228 OPS-Codes mit GOP-Zuordnung (439 GOP) |
| Pauschalen außerhalb des EBM | BMV-Ä und Anlagen auf kbv.de, von Hand erfasst | 24 Pauschalen in 7 Regelungen |

Die Katalogseite (`web/index.html`) zeigt die vier Teile mit Suche, Baum, Detailansicht und JSON je Eintrag. Wie dieselben Inhalte unter festen Adressen als Seite, JSON und FHIR erreichbar wären, beschreibt [docs/ADRESSSCHEMA.md](docs/ADRESSSCHEMA.md).

## Schnellstart

Nur Python ab 3.11, keine Pakete.

```bash
python3 -I werkzeuge/ek.py exportieren   # Daten und Seite nach ausgabe/ bauen
python3 -I werkzeuge/ek.py pruefen       # Struktur prüfen
python3 -m http.server 8792 -d ausgabe/site
```

Tests: `python3 -I -m unittest discover -s tests -v`

## Für KI-Assistenten

Der MCP-Server (`ek.py mcp`, eingebunden über `.mcp.json`) gibt Assistenten acht Werkzeuge mit Belegen je Antwort; die [Antwortregeln](docs/ANTWORTREGELN.md) werden mitgeliefert. Für Systeme ohne MCP erzeugt `ek.py texte` Markdown je GOP und eine `llms.txt`. Ein [Fragenkatalog](fragen/fragenkatalog.json) prüft in der CI, ob die Werkzeuge die belegten Fakten liefern. Einzelheiten: [docs/KI-NUTZUNG.md](docs/KI-NUTZUNG.md).

## Befehle

| Befehl | Zweck |
|---|---|
| `ek.py abzug` | EBM-Ansicht abziehen → `rohdaten/<Quartal>/nodes.jsonl` |
| `ek.py abzug --ansicht ops` | Anhang-2-Ansicht → `ops_nodes.jsonl` |
| `ek.py abzug --arztgruppen` | Arztgruppenfilter → `arztgruppen/<Gruppe>.jsonl` |
| `ek.py packen` | Rohdaten packen (`*.jsonl` → `*.jsonl.gz`); nur die gepackten Dateien werden eingecheckt |
| `ek.py exportieren [Quartal]` | `ausgabe/<Quartal>/` (Daten, JSON je GOP, FHIR-CodeSystem) und `ausgabe/site/` |
| `ek.py pruefen [Quartal]` | Strukturprüfung der erzeugten Daten |
| `ek.py mcp` | MCP-Server über stdio |
| `ek.py frage WERKZEUG '{json}'` | ein Werkzeug direkt aufrufen |
| `ek.py fragenkatalog` | Fragenkatalog prüfen, Bericht nach `ausgabe/` |
| `ek.py texte` | Markdown je GOP, Gesamttext, `llms.txt` nach `ausgabe/site/` |
| `ek.py vertraulich` | eingecheckte Dateien auf vertrauliche Inhalte prüfen |
| `ek.py bmv` | BMV-Ä und Anlagen laden, Text ziehen (Arbeitsgrundlage für `quellen/bmv/`; braucht `pypdf`) |
| `ek.py pdf build\|gop\|search\|refs` | EBM aus dem amtlichen Quartals-PDF durchsuchen (Rückfallebene; braucht `pypdf`) |

Alle Befehle mit `python3 -I werkzeuge/ek.py …` aufrufen.

## Aufbau

```
werkzeuge/ek.py            Kommandozeile
werkzeuge/ek/              abzug (JSF-Client), export, extra (Arztgruppen, OPS, BMV-Ä), pruefen, vertraulich, …
web/index.html             Katalogseite (eine Datei, lädt ausgabe/site/daten/*.json)
rohdaten/<Quartal>/        gepackte Abzüge der Online-Ansicht
quellen/bmv/               Pauschalen aus dem BMV-Ä (von Hand, mit Fundstelle) und Dokumentliste
fragen/                    Fragenkatalog mit Sollantworten (Entwurf)
tests/                     Tests mit Ausschnitten der Online-Ansicht
docs/                      Abzug, Datenmodell, Adressschema, KI-Nutzung, Antwortregeln
```

## CI

`.github/workflows/ci.yml` läuft bei jedem Push: Vertraulichkeit, Tests, Export aus den eingecheckten Rohdaten, Strukturprüfung, Fragenkatalog, Texte, Probelauf des MCP-Servers. Die gebaute Seite liegt als Pages-Artefakt bereit. **Veröffentlicht wird nur**, wenn die Repository-Variable `PAGES_FREIGEGEBEN` auf `ja` steht und der Push auf `main` geht.

`.github/workflows/abzug.yml` startet einen neuen Abzug nur von Hand und legt die gepackten Rohdaten als Artefakt ab. Eingecheckt wird nach Durchsicht von Hand.

Projektbezogene Muster für die Vertraulichkeitsprüfung stehen in der Repository-Variable `VERTRAULICH_MUSTER` oder lokal in `.vertraulich-muster` (nicht eingecheckt).

## Grenzen

- Ein Quartal je Abzug; Quartalsvergleich und frühere Quartale sind nicht abgebildet.
- Markup ist bereinigt (Klassen, Stile, Skripte entfernt), Texte und Tabellen sind unverändert.
- Arztgruppen werden über den Pfad der Baumtitel zugeordnet; der gefilterte Baum liefert keine Knotenkennungen.
- Die Pauschalen aus dem BMV-Ä sind von Hand erfasst und gekürzt. Anlage 3 (Qualitätssicherungsvereinbarungen), regionale Vereinbarungen und Selektivverträge fehlen.
- Verweise auf Knoten, die nicht im Baum des Quartals stehen, sind gekennzeichnet; sie lassen sich auch in der Online-Ansicht nicht öffnen.
