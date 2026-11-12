# Nutzung durch KI-Assistenten und Mitarbeitende

Drei Wege, je nach System. Für alle gelten die [Antwortregeln](ANTWORTREGELN.md).

## 1. MCP-Server (empfohlen)

Für Assistenten mit Model Context Protocol. Der Server läuft lokal über stdio, nur mit der Python-Standardbibliothek, und liest die Daten aus `ausgabe/<Quartal>/` (wird bei Bedarf erzeugt).

```bash
python3 -I werkzeuge/ek.py mcp
```

Im Repository liegt `.mcp.json`; Werkzeuge, die diese Datei lesen, binden den Server beim Öffnen des Ordners ein. Für andere Clients denselben Befehl mit dem Repository als Arbeitsverzeichnis eintragen.

| Werkzeug | Wofür |
|---|---|
| `ebm_suche` | Volltext über EBM, Anhang 2 und BMV-Ä-Pauschalen |
| `ebm_gop` | alles zu einer GOP: Bewertung mit Altersstufen, Merkmale, Leistungsinhalte, Abrechnungsbestimmung, Anmerkungen, Ausschlüsse, Arztgruppen, Bezüge zum BMV-Ä |
| `ebm_abschnitt` | Präambeln, Allgemeine Bestimmungen, Kapiteltexte; mehrdeutige Nummern mit Pfad |
| `ebm_nebeneinander` | eingetragene Ausschlüsse zwischen zwei Nummern, beide Richtungen, mit Bezug |
| `ebm_arztgruppe` | Arztgruppenfilter: Gruppen, Umfang, Sichtbarkeit einer GOP |
| `ebm_ops` | Anhang 2: OPS → GOP und GOP → OPS |
| `ebm_bmv` | Pauschalen außerhalb des EBM mit Betrag oder „regional“ und Fundstelle |
| `ebm_verweise` | wer eine Nummer erwähnt — für Folgenabschätzungen |

Jede Antwort enthält Belege (Quartal, Nummer, Knotenkennung, Pfad bzw. Anlage mit Seite) und den Hinweis „KI-gebaut und nicht amtlich“. Ohne Treffer sagt das Werkzeug das ausdrücklich. Zum Ausprobieren ohne Assistent:

```bash
python3 -I werkzeuge/ek.py frage ebm_nebeneinander '{"a":"03000","b":"01436"}'
```

## 2. Texte zum Hochladen

`python3 -I werkzeuge/ek.py texte` schreibt nach `ausgabe/site/`:

- `texte/gop/<Nr>.md` — eine Datei je GOP
- `texte/bmv.md` — Pauschalen aus dem BMV-Ä
- `texte/ebm-<Quartal>.md` — alles in einer Datei, für Wissensspeicher interner KI-Plattformen
- `llms.txt` — Aufbau, Antwortregeln, Verweise auf Texte und Daten

## 3. Daten direkt

JSON nach [DATENMODELL.md](DATENMODELL.md), für eigene Auswertungen.

## Fragenkatalog

`fragen/fragenkatalog.json` enthält typische Fragen mit Sollantwort, Fundstelle und maschinenprüfbaren Erwartungen. `ek.py fragenkatalog` ruft je Frage das passende Werkzeug auf und prüft, ob es die belegten Fakten liefert; die CI bricht ab, wenn eine Prüfung fehlschlägt (Bericht: `ausgabe/fragenkatalog-bericht.md`).

- **Status:** Alle Sollantworten sind Entwürfe. Freigeben müssen sie Fachleute für EBM und BMV-Ä; danach `status` auf `freigegeben` setzen.
- **Erweitern:** neue Frage mit `werkzeug`, `argumente`, `pruefungen` (`gleich`, `enthaelt`, `min`, `laenge`, `nicht_leer`) und `sollantwort` anlegen. Gute Quellen sind echte Anfragen an Service-Stellen.
- **Grenze:** Geprüft wird die Faktenlieferung der Werkzeuge, nicht die Formulierung einer KI-Antwort. Für Letzteres die Sollantworten mit Antworten eines Assistenten vergleichen lassen, wenn ein Modellzugang zur Verfügung steht.

## Einsatz in der Fachabteilung

| Aufgabe | Werkzeuge |
|---|---|
| Anfragen beantworten | `ebm_suche`, `ebm_gop`, `ebm_nebeneinander`, `ebm_bmv` |
| Folgenabschätzung vor Beschlüssen | `ebm_verweise`, `ebm_nebeneinander`, `ebm_ops` |
| Konsistenz prüfen | `ek.py pruefen` (Verweise ins Leere, Anhang-2-GOP außerhalb des Baums), einseitige Ausschlüsse über `ebm_nebeneinander` |
| Quartalswechsel | neuer Abzug, `ek.py pruefen`, `ek.py fragenkatalog` — abweichende Antworten zeigen Änderungen |
