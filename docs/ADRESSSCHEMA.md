# Adressschema (Vorschlag)

Wie die Inhalte dieses Katalogs unter festen Adressen erreichbar wären. **Keine dieser Adressen existiert.** Die Katalogseite zeigt sie je Eintrag als Beispiel.

## Grundsätze

1. **Eine Adresse, mehrere Darstellungen.** Dieselbe URL liefert HTML, JSON oder FHIR, gesteuert über den `Accept`-Header oder die Endung.
2. **Quartal ist Version.** Mit Quartal unveränderlich und zitierfähig, ohne Quartal immer aktuell (Weiterleitung).
3. **Knotenkennung als Schlüssel.** Die vorhandene interne Kennung wird Teil der Adresse; Gebührenordnungspositionen zusätzlich über die Nummer.
4. **Verweise sind Links**, in beide Richtungen. Verweise ins Leere werden gekennzeichnet.
5. **Ein Katalog über Regelwerksgrenzen.** EBM, Anhang 2 und Pauschalen aus dem BMV-Ä unter einem Schema; die Herkunft ist je Eintrag ausgewiesen.

## Adressen

| Zweck | Pfad | Antwort |
|---|---|---|
| Position, Quartal fest | `/2026-4/gop/03000` | HTML mit eingebettetem JSON-LD |
| Position, immer aktuell | `/gop/03000` | Weiterleitung auf das aktuelle Quartal |
| Position als Daten | `/api/2026-4/gop/03000` | JSON mit Arztgruppen und OPS-Zuordnung |
| Beliebiger Knoten | `/api/2026-4/knoten/{Knotenkennung}` | JSON, auch Präambeln und Bestimmungen |
| Gliederung | `/api/2026-4/index.json` | Baum mit Nummer, Titel, Bewertung |
| Arztgruppe | `/api/2026-4/arztgruppe/Hausarzt` | sichtbare Knoten |
| OPS-Code | `/api/2026-4/ops/5-010.2` | Kategorie, §115b, GOP-Zuordnung |
| Pauschale außerhalb des EBM | `/api/bmv/pauschale/86510` | Anlage, Betrag oder „regional", Fundstelle |
| Suche | `/api/2026-4/suche?q=Videosprechstunde` | Trefferliste mit Links |
| Quartalsvergleich | `/api/vergleich?von=2026-3&bis=2026-4` | neue, gestrichene, geänderte Knoten |
| FHIR CodeSystem | `/fhir/CodeSystem/ebm?version=2026-4` | FHIR R4 |
| FHIR ConceptMap | `/fhir/ConceptMap/ops-ebm?version=2026-4` | OPS → GOP |
| FHIR Lookup | `/fhir/CodeSystem/$lookup?system=…/fhir/CodeSystem/ebm&code=03000&version=2026-4` | `Parameters` |
| Hinweise für KI-Assistenten | `/llms.txt` | Schnittstelle und Zitierregel |

## FHIR

- `CodeSystem` EBM je Quartal (`ausgabe/<Quartal>/CodeSystem-ebm.json` als Muster).
- `ValueSet` je Arztgruppe aus `arztgruppen.json`.
- `ConceptMap` OPS → GOP aus `ops.json`, Art der Zuordnung als Property.
- Eigenes `CodeSystem` für die Pauschalen aus dem BMV-Ä, getrennt vom EBM.
