# Abzug der Online-Ansicht

## Technik der Quelle

ebm.kbv.de ist eine JSF-Anwendung (PrimeFaces 13). Der Zustand liegt in der Sitzung (`JSESSIONID`) und im `javax.faces.ViewState`; Inhalte werden per AJAX nachgeladen. Es gibt keine Adresse je Knoten, keine Sitemap und keine Schnittstelle.

`werkzeuge/ek/jsf.py` bildet die Anfragen des Browsers nach:

| Vorgang | Parameter |
|---|---|
| Knoten aufklappen | `mainForm:tree_expandNode=<Zeilenschlüssel>`, Rendern von `mainForm:tree` |
| Knoten auswählen | Ereignis `select`, `mainForm:tree_instantSelection=<Zeilenschlüssel>`, Rendern von `mainForm:detailsPanel` |
| Arztgruppe filtern | Ereignis `valueChange` an `mainForm:arztgrpFilter` |
| Anhang-2-Ansicht | dieselben Baumvorgänge auf `/ops.xhtml`, mit `abulant=on` und `stationaer=on` |

Jede Detailansicht enthält die interne Knotenkennung (`knotenId`) und den Zeilenschlüssel (`rowKey`). Querverweise im Text sind Links auf Knotenkennungen; Bereiche wie „01670 bis 01672“ sind als mit `_` verkettete Kennungen kodiert.

## Ablauf

1. `ek.py abzug` — Tiefensuche über den Baum: jeden Knoten auswählen, jeden Elternknoten aufklappen. Eine Anfrage nach der anderen, 0,3 s Pause, Wiederholung bei Zeitüberschreitung, fortsetzbar.
2. `ek.py abzug --ansicht ops` — dasselbe für die Anhang-2-Ansicht.
3. `ek.py abzug --arztgruppen` — je Arztgruppe Filter setzen und den gefilterten Baum aufklappen, ohne Auswahl. Gebührenordnungspositionen mit Untergliederung werden nicht aufgeklappt; ihre Kinder tragen dieselbe Nummer. Eine fertige Gruppe wird mit `<Gruppe>.fertig` markiert.
4. `ek.py packen` — Rohdaten packen.
5. `ek.py exportieren` und `ek.py pruefen`.

Das Quartal ist das in der Online-Ansicht voreingestellte. Für einen erneuten Abzug desselben Quartals das Verzeichnis `rohdaten/<Quartal>/` vorher leeren.

## Dauer und Last (Quartal 2026/Q4)

| Teil | Anfragen | Dauer |
|---|---|---|
| EBM-Ansicht | rund 4.500 | 33 Minuten |
| Arztgruppenfilter | rund 1–2 Minuten je Gruppe | rund 70 Minuten (46 Gruppen) |
| Anhang-2-Ansicht | rund 13.100 (eine je Knoten plus Aufklappen) | rund 2 Stunden 20 Minuten |

## BMV-Ä

`ek.py bmv` lädt die in `quellen/bmv/liste.tsv` verzeichneten PDF nach `ausgabe/bmv/pdf/` und legt den Text mit Seitenmarken in `ausgabe/bmv/text/` ab. Die Pauschalen in `quellen/bmv/bmv_pauschalen.json` sind von Hand aus diesen Texten erfasst, jeweils mit Datei und Seite. Dieselben Texte durchsucht das Werkzeug `bmv_text` (Gliederung nach Paragraf, Anhang, Abschnitt und Seite); sie werden nicht eingecheckt, die CI lädt sie bei geänderter Dokumentliste neu und hält sie im Zwischenspeicher.
