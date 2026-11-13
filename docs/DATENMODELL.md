# Datenmodell

Erzeugt von `ek.py exportieren` nach `ausgabe/<Quartal>/`. Die Katalogseite lädt dieselben Dateien aus `ausgabe/site/daten/`.

## index.json — Gliederung

`quartal`, `anzahl_knoten`, `anzahl_gop` (GOP-Einträge im Baum, einschließlich Varianten wie den Altersstufen der 03000), `anzahl_gop_nummern` (verschiedene Nummern), `wurzeln[]`, `knoten[]` in Baumreihenfolge. Je Knoten:

| Feld | Inhalt |
|---|---|
| `knotenId` | interne Kennung der Online-Ansicht |
| `nr`, `titel`, `baumtitel` | Nummer und Überschrift der Detailansicht; Beschriftung im Baum |
| `typ` | `gop` (fünfstellige Nummer) oder `abschnitt` |
| `teil` | Teil I–VIII als Index 0–7 |
| `eltern`, `kinder[]` | Baum über Knotenkennungen |
| `bewertung` | `punkte`, `euro` wie im Kopf der Detailansicht angezeigt |

Mehrere Knoten können dieselbe Nummer tragen: Untergliederungen einer GOP (z. B. 03000 mit fünf Altersstufen). Der erste Knoten einer Nummer gilt als die GOP.

## teil-&lt;n&gt;.json — Inhalte

Objekt je Knotenkennung:

| Feld | Inhalt |
|---|---|
| `merkmale[]` | `text`, `zutreffend` (z. B. Berichtspflicht, Versorgungsbereich) |
| `abschnitte[]` | `id`, `ueberschrift`, `html`: Beschreibung, obligater und fakultativer Leistungsinhalt, Abrechnungsbestimmung, Anmerkung, Kapiteltext. Bereinigtes HTML; Links als `<a data-k="Knotenkennung">`, BMV-Ä-Nummern als `data-k="bmv:<Nr>"`, Anlagen als `data-k="anl:<Nr>"` |
| `ausschluesse[]` | `bezug`, `leistungen[]` und `kapitel[]` mit `nr` und `k` (Knotenkennung) |
| `verweise[]`, `referenziert_von[]` | Querverweise in beide Richtungen |
| `bmv_verweise[]` | im Text genannte BMV-Ä-Pauschalen und Anlagen |

## arztgruppen.json

`gruppen[]`, `sichtbar{Gruppe: [Index in index.knoten]}`, `unvollstaendig[]`, `nicht_zugeordnet{}`.

## ops.json — Anhang 2

`knoten[]` mit `id`, `nr` (OPS-Code), `titel`, `eltern`, `kinder[]`, `seite` (Seitenangabe), `kategorie`, `p115b` und `gops[]` (`art`, `gop`, `bezeichnung`, `punkte`, `kalk`, `pruef`).

## bmv.json — Pauschalen außerhalb des EBM

`anlagen[]` (`id`, `anlage`, `titel`, `fassung`, `hoehe`, `status`, `pauschalen[]`, `urls[]`), `pauschalen[]` (`id`, `nr` oder Ersatzkennung, `titel`, `anlage`, `abrechnung`, `betrag[]` mit `bedingung` und `euro`, `ausschluesse[]`, `fundstelle` mit `datei`, `seite`, `url`, optional `leistungsinhalt[]` und `geltung` mit `nur_fuer_diga[]`, `voraussetzung`, `berechtigt[]`, `verguetung` samt Fundstellen), `ohne_eigene_pauschale[]`, `nicht_im_katalog[]` (Themen, die der Katalog bewusst nicht enthält, mit Stichwörtern, Hinweis und Fundstelle), `ebm_verweise{"bmv:<Nr>"|"anl:<Nr>": [Knotenkennungen]}`.

## Weitere Ausgaben

- `gop/<Nr>.json` — eine Datei je GOP mit allen Feldern, Muster für eine Schnittstelle je Position.
- `CodeSystem-ebm.json` — FHIR-R4-CodeSystem, Properties `punkte`, `euro`, `ausschluss`, `knotenId`.
- `unaufgeloest.txt` — Verweisziele, die nicht im Baum des Quartals stehen.
