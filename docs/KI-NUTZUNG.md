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
| `ebm_suche` | Volltext über EBM, Anhang 2 und BMV-Ä-Pauschalen; GOP-Treffer mit Punktzahl. Ohne Treffer wird mit hinterlegten Fachbegriffen erneut gesucht (`umformuliert_zu`, `auch_unter`), enthält keine GOP alle Wörter, kommen `teiltreffer` |
| `ebm_gop` | eine oder mehrere GOP (Komma, höchstens 20): Bewertung mit Altersstufen, Merkmale, Leistungsinhalte, Abrechnungsbestimmung, Anmerkungen, Ausschlüsse, Arztgruppen, Zeiten aus Anhang 3, Zuschläge und Zusatzpauschalen, die die GOP erwähnen, Bezüge zum BMV-Ä; `umfang=kompakt` ohne Anmerkungen und Rückverweise; ohne Treffer `aehnlich` |
| `ebm_abschnitt` | Präambeln, Allgemeine Bestimmungen, Kapitel- und Anhangtexte; mehrdeutige Nummern mit Pfad, eindeutig mit „Anhang 2.1“ oder „AB 4.3.1“. Lange Texte gekürzt, mit `filter` nur die Stellen rund um einen Begriff |
| `ebm_nebeneinander` | eingetragene Ausschlüsse, beide Richtungen, mit Bezug; Ausschlüsse ganzer Abschnitte aufgelöst (`ueber_abschnitt`); `b` als Liste für eine Sammelprüfung (höchstens 100) |
| `ebm_arztgruppe` | Arztgruppenfilter: Gruppen (als Auswahlliste im Schema), Umfang, Sichtbarkeit einer GOP |
| `ebm_ops` | Anhang 2: OPS → GOP und GOP → OPS, mit Felderklärung |
| `ebm_bmv` | Pauschalen außerhalb des EBM mit Betrag oder „regional“ und Fundstelle; ohne Treffer Vorschläge und die Liste nicht erfasster Regelungen |
| `ebm_verweise` | wer eine Nummer erwähnt und in welchen Anhangtabellen (2, 3) sie steht — für Folgenabschätzungen |
| `ebm_felder` | Bedeutung der Felder; was die Online-Ansicht nicht erläutert, ist so gekennzeichnet |

Jede Antwort enthält Belege (Quartal, Nummer, Knotenkennung, Pfad bzw. Anlage mit Seite) und den Hinweis „KI-gebaut und nicht amtlich“. Ohne Treffer sagt das Werkzeug das ausdrücklich. Die Fachbegriffe für die Suche stehen in `quellen/synonyme.json` (von Hand, nur Einträge, deren Zielbegriff im Katalog vorkommt).

Weitere MCP-Funktionen:

- **Annotations:** Alle Werkzeuge sind als nur lesend, wiederholbar und ohne Außenwirkung gekennzeichnet (`readOnlyHint`, `idempotentHint`, `openWorldHint: false`); Clients können sie ohne Rückfrage zulassen.
- **Strukturierte Ausgabe:** Jedes Ergebnis kommt zusätzlich als `structuredContent` (JSON); der Textteil ist auf 60.000 Zeichen begrenzt.
- **Resources:** `ebm://regeln`, `ebm://felder`, `ebm://bmv` und die Vorlagen `ebm://<Quartal>/gop/{nr}`, `ebm://<Quartal>/abschnitt/{nr}`, `ebm://<Quartal>/ops/{code}` als Markdown. GOP-Ergebnisse verweisen per `resource_link` darauf.
- **Vorlagen:** `ebm_frage`, `ebm_fallpruefung` (GOP-Liste, Alter, Arztgruppe), `ebm_folgenabschaetzung` (GOP) mit Regeln und Abfragefolge.
- **Completions:** GOP-Nummern, Abschnittsnummern, Arztgruppen und OPS-Codes für die Argumente der Resource-Vorlagen und Vorlagen.

Zum Ausprobieren ohne Assistent:

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

## Beispielantworten

`fragen/beispielantworten.json` zeigt an Alltagsfragen, wie ein Assistent mit den Werkzeugen antworten könnte; die Katalogseite stellt sie unter „Beispielantworten“ dar. Je Beispiel:

- `frage` und `fuer` (Praxis oder KBV-Fachabteilung),
- `schritte`: Werkzeugaufrufe in der Reihenfolge, in der ein Assistent sie stellen würde, mit Kurzbefund und `pruefungen` wie im Fragenkatalog,
- `antwort` (Absätze, Listen mit `- `, `**fett**`, Links auf Seitenadressen wie `#gop-03230`), `belege`, `einordnung` (was gelingt, wo die Grenzen liegen, was abgeleitet ist).

`ek.py fragenkatalog` führt die Schritte aus und prüft ihre Kernaussagen. Der Antworttext ist von Hand formuliert und KI-gebaut; er wird nicht automatisch geprüft und ist fachlich nicht freigegeben. Die Einordnungen benennen auch Grenzen, etwa dass Begrenzungen in Präambeln stehen und eigens abgerufen werden müssen.

## Einsatz in der Fachabteilung

| Aufgabe | Werkzeuge |
|---|---|
| Anfragen beantworten | `ebm_suche`, `ebm_gop`, `ebm_nebeneinander`, `ebm_bmv` |
| Folgenabschätzung vor Beschlüssen | `ebm_verweise`, `ebm_nebeneinander`, `ebm_ops` |
| Konsistenz prüfen | `ek.py pruefen` (Verweise ins Leere, Anhang-2-GOP außerhalb des Baums), einseitige Ausschlüsse über `ebm_nebeneinander` |
| Quartalswechsel | neuer Abzug, `ek.py pruefen`, `ek.py fragenkatalog` — abweichende Antworten zeigen Änderungen |
