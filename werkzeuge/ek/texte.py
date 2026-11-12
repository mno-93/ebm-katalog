"""Textausgabe für KI-Systeme ohne MCP: eine Markdown-Datei je GOP, ein Gesamttext und llms.txt.

Schreibt nach ausgabe/site/ (damit die Texte mit der Seite ausgeliefert werden):
  llms.txt                 Aufbau, Zitierregel, Verweise auf die Texte
  texte/gop/<Nr>.md        je GOP: Bewertung, Abschnitte, Ausschlüsse, Arztgruppen, Herkunft
  texte/bmv.md             Pauschalen aus dem BMV-Ä
  texte/ebm-<Q>.md         alles in einer Datei (für Uploads in Wissensspeicher)
"""
from .grundlagen import AUS, WURZEL
from .katalog import HINWEIS, Katalog


def gop_md(k, nr):
    r = k.gop(nr)
    z = [f"# GOP {r['nr']} — {r['titel']}", "", f"Quartal {k.quartal.replace('-', '/Q')} · {r['belege'][0]['pfad']}", ""]
    if r["bewertung"]:
        z += ["## Bewertung", "", "| Bedingung | Punkte | Euro |", "|---|---|---|"]
        z += [f"| {b['bedingung'] or '—'} | {b.get('punkte') or '—'} | {b.get('euro') or '—'} |" for b in r["bewertung"]] + [""]
    elif r["bewertung_hinweis"]:
        z += [f"Bewertung: {r['bewertung_hinweis']}", ""]
    if r["merkmale"]:
        z += ["Merkmale: " + "; ".join(f"{m['text']} ({'ja' if m['zutreffend'] else 'nein'})" for m in r["merkmale"]), ""]
    for a in r["abschnitte"]:
        z += [f"## {a['ueberschrift'] or 'Text'}", "", a["text"], ""]
    if r["ausschluesse"]:
        z += ["## Abrechnungsausschlüsse", ""] + [f"- {a['bezug']}: {', '.join(a['gop'])}" + (f"; Kapitel {', '.join(a['kapitel'])}" if a["kapitel"] else "") for a in r["ausschluesse"]] + [""]
    if r.get("arztgruppen"):
        z += ["## Arztgruppen (Filter der Online-Ansicht)", "", ", ".join(r["arztgruppen"]), ""]
    if r["bmv_bezuege"]:
        z += ["## Bezüge zum BMV-Ä", "", ", ".join(b.replace("bmv:", "Pauschale ").replace("anl:", "Anlage ") for b in r["bmv_bezuege"]), ""]
    z += ["---", f"Herkunft: EBM-Online-Ansicht https://ebm.kbv.de/, Knotenkennung {r['belege'][0]['knotenId']}. {HINWEIS}", ""]
    return "\n".join(z)


def bmv_md(k):
    d = k.bmv_daten
    z = ["# Pauschalen aus dem BMV-Ä außerhalb des EBM", "", HINWEIS, ""]
    for a in d["anlagen"]:
        z += [f"## Anlage {a['anlage']}: {a['titel']}", "", f"Fassung: {a.get('fassung') or '—'}. Höhe: {a.get('hoehe') or '—'}." + (f" Status: {a['status']}." if a.get("status") else ""), ""]
        for pid in a["pauschalen"]:
            p = d["nach_id"][pid]
            betrag = "; ".join(f"{(b['bedingung'] + ': ') if b['bedingung'] else ''}{b['euro']:.2f} €".replace(".", ",") for b in p["betrag"] or []) or "regional"
            z += [f"- **{p['nr'] or 'ohne Nummer'}** {p['titel']} — {betrag}" + (f" — {p['abrechnung']}" if p.get("abrechnung") else "") + f" (Fundstelle {p['fundstelle']['datei']}, S. {p['fundstelle']['seite']})"]
        z.append("")
    z += ["## Anlagen ohne eigene Pauschale", ""] + [f"- Anlage {x['anlage']} ({x['titel']}): {x['befund']}" for x in d["ohne_eigene_pauschale"]] + [""]
    return "\n".join(z)


def llms_txt(k):
    return "\n".join([
        "# Offener EBM-Katalog", "",
        f"> Maschinenlesbarer Spiegel der EBM-Online-Ansicht (Quartal {k.quartal.replace('-', '/Q')}) mit Arztgruppenfilter, Anhang 2 (OPS) und den Pauschalen des BMV-Ä außerhalb des EBM. {HINWEIS}", "",
        "## Antwortregeln", "", "1. " + (WURZEL / "docs" / "ANTWORTREGELN.md").read_text(encoding="utf-8").split("\n1. ", 1)[1].strip(), "",
        "## Texte", "",
        f"- [Gesamter EBM als Text](texte/ebm-{k.quartal}.md)", "- [Pauschalen aus dem BMV-Ä](texte/bmv.md)", "- Je GOP: texte/gop/<Nummer>.md, z. B. [03000](texte/gop/03000.md)", "",
        "## Daten", "", "- [Gliederung](daten/index.json)", "- Inhalte je Teil: daten/teil-0.json bis daten/teil-7.json",
        "- [Arztgruppen](daten/arztgruppen.json)", "- [Anhang 2](daten/ops.json)", "- [BMV-Ä](daten/bmv.json)", "",
        "## Werkzeuge", "", "Für MCP-fähige Assistenten: `python3 -I werkzeuge/ek.py mcp` (stdio) im Repository.", ""])


def main(argv=None):
    k = Katalog(argv[0] if argv else None)
    site = AUS / "site"
    gd = site / "texte" / "gop"
    gd.mkdir(parents=True, exist_ok=True)
    alle = []
    nrs = sorted({n["nr"] for n in k.index["knoten"] if n["typ"] == "gop"})
    for nr in nrs:
        t = gop_md(k, nr)
        (gd / f"{nr}.md").write_text(t, encoding="utf-8")
        alle.append(t)
    if k.bmv_daten:
        b = bmv_md(k)
        (site / "texte" / "bmv.md").write_text(b, encoding="utf-8")
        alle.append(b)
    (site / "texte" / f"ebm-{k.quartal}.md").write_text("\n\n".join(alle), encoding="utf-8")
    (site / "llms.txt").write_text(llms_txt(k), encoding="utf-8")
    print(f"{len(nrs)} GOP-Texte, llms.txt -> {site}")
    return 0
