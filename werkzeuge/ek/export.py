"""Strukturierter Export aus dem Abzug der EBM-Online-Ansicht.

Liest rohdaten/<Q>/nodes.jsonl(.gz) und schreibt nach ausgabe/<Q>/:
  index.json            Baum: alle Knoten mit Nummer, Titel, Typ, Eltern, Kindern, Bewertung
  teil-<n>.json         Inhalte je Teil I–VIII (bereinigtes HTML je Abschnitt, Ausschlüsse, Verweise)
  arztgruppen.json, ops.json, bmv.json   Ergänzungen (siehe extra.py)
  gop/<GOP>.json        eine Datei je Gebührenordnungsposition
  CodeSystem-ebm.json   FHIR-R4-CodeSystem
und baut die Katalogseite nach ausgabe/site/.

Alle Inhalte stammen 1:1 aus ebm.kbv.de; nur Markup wird bereinigt (Klassen, Skripte, Stile entfernt),
interne Verweise werden auf die Knotenkennung umgeschrieben.
"""
import html as H, json, re, shutil
from collections import defaultdict
from html.parser import HTMLParser

from .grundlagen import AUS, ROH, WEB, WURZEL, lies_jsonl
SRC = "https://ebm.kbv.de"
KEEP = {"p", "ul", "ol", "li", "strong", "b", "em", "i", "br", "table", "thead", "tbody", "tr", "th", "td", "sup", "sub", "a", "h5", "h6", "span", "div"}
VOID = {"br"}
GOP = re.compile(r"^\d{5}[A-Z]?$")


def text(s):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


class Clean(HTMLParser):
    """Whitelist-Bereinigung; Links auf EBM-Knoten werden zu <a data-k="KnotenId">."""
    def __init__(self, links):
        super().__init__(convert_charrefs=True)
        self.out, self.links, self.skip = [], links, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1; return
        if self.skip or tag not in KEEP or tag in ("span", "div"):
            return
        a = dict(attrs)
        if tag == "a":
            href = a.get("href", "")
            if href.startswith("http"):
                self.out.append(f'<a href="{H.escape(href)}" target="_blank" rel="noopener">'); return
            self.links.append(href)
            self.out.append(f'<a data-k="{H.escape(href)}">'); return
        extra = "".join(f' {k}="{H.escape(v)}"' for k, v in attrs if k in ("colspan", "rowspan"))
        self.out.append(f"<{tag}{extra}>")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1; return
        if self.skip or tag not in KEEP or tag in VOID or tag in ("span", "div"):
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, d):
        if not self.skip:
            self.out.append(H.escape(d))


def clean(fragment, links):
    c = Clean(links); c.feed(fragment); c.close()
    s = "".join(c.out)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*(</?(?:p|ul|ol|li|table|thead|tbody|tr|th|td|h5|h6)[^>]*>)\s*", r"\1", s)
    return s.strip()


def block(html_, start):
    """Inhalt des <div> ab Position start bis zum passenden </div>."""
    depth, i = 0, start
    for m in re.finditer(r"<(/?)div\b[^>]*>", html_[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return html_[start:start + m.end()]
    return html_[start:]


SECTION_IDS = [("beschreibung", "Beschreibung"), ("oblgLeistungsinhalt", "Obligater Leistungsinhalt"),
               ("fkttLeistungsinhalt", "Fakultativer Leistungsinhalt"), ("abrechnungsbestimmung", "Abrechnungsbestimmung"),
               ("anmerkung", "Anmerkung"), ("kapitelText", None)]


def parse(node):
    h = node["html"]
    links = []
    heads = re.findall(r"<h4[^>]*>(.*?)</h4>", h, re.S)
    nr = text(heads[0]) if heads else ""
    titel = text(heads[1]) if len(heads) > 1 else ""
    rec = {"knotenId": node["knotenId"], "rowkey": node["rowkey"], "nr": nr, "titel": titel,
           "baumtitel": node["label"], "typ": "gop" if GOP.match(nr) else "abschnitt"}
    # Bewertung (Kopfzeile mit .value/.unit) und Merkmale (Glyphicons)
    vals = re.findall(r'<span class="value">(.*?)</span>\s*<br\s*/?>\s*<span class="unit">(.*?)</span>', h, re.S)
    bew = {}
    for v, u in vals:
        v = text(v)
        if v and v != "nu":
            bew[text(u).lower()] = v
    if bew:
        rec["bewertung"] = bew
    merk = re.findall(r'glyphicon-(ok|remove)-circle"[^>]*>\s*</span>\s*<span class="glyphicon-class">(.*?)</span>', h, re.S)
    if merk:
        rec["merkmale"] = [{"text": text(t), "zutreffend": s == "ok"} for s, t in merk]
    # Textabschnitte in Seitenreihenfolge
    secs = []
    for m in re.finditer(r'<div id="([^"]+)"', h):
        did = m.group(1)
        if did in ("detailsContent", "knotenId", "rowKey", "mainForm:messages", "ueberschrift_details") or did == "abrechnungsausschlüsse":
            continue
        b = block(h, m.start())
        inner = b[b.find(">") + 1:]
        hm = re.search(r"<h5[^>]*>(.*?)</h5>", inner, re.S)
        head = text(hm.group(1)) if hm else dict(SECTION_IDS).get(did)
        if hm:
            inner = inner[:hm.start()] + inner[hm.end():]
        body = clean(inner, links)
        if body:
            secs.append({"id": did, "ueberschrift": head, "html": body})
    # verschachtelte divs (z. B. EBMBESCHREIBUNG in beschreibung) nicht doppelt führen
    seen, uniq = set(), []
    for s in secs:
        key = s["html"]
        if any(key in t for t in seen):
            continue
        seen.add(key); uniq.append(s)
    rec["abschnitte"] = [s for s in uniq if s["id"] in dict(SECTION_IDS) or not s["id"].startswith(("EBM",))]
    # Abrechnungsausschlüsse
    am = re.search(r'<div id="abrechnungsausschlüsse">', h)
    if am:
        tb = block(h, am.start())
        rows = []
        for tr in re.findall(r"<tr>(.*?)</tr>", tb, re.S):
            bz = re.search(r'<td class="brBz">(.*?)</td>', tr, re.S)
            if not bz:
                continue
            le = re.search(r'<td class="leistungen">(.*?)</td>', tr, re.S)
            ka = re.search(r'<td class="kapitel">(.*?)</td>', tr, re.S)
            def refs(cell):
                out = []
                for href, t in re.findall(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', cell or "", re.S):
                    links.append(href); out.append({"nr": text(t), "k": href})
                rest = text(re.sub(r"<a[^>]*>.*?</a>", " ", cell or "", flags=re.S))
                return out, rest
            lg, lr = refs(le.group(1) if le else "")
            kg, kr = refs(ka.group(1) if ka else "")
            row = {"bezug": text(bz.group(1)), "leistungen": lg, "kapitel": kg}
            if lr: row["leistungen_text"] = lr
            if kr: row["kapitel_text"] = kr
            rows.append(row)
        rec["ausschluesse"] = rows
    # Mehrfachziele („03040 bis 03045") sind in der Online-Ansicht als mit „_" verkettete Knoten-IDs kodiert
    rec["verweise"] = sorted({p for l in links if l and not l.startswith("http") for p in l.split("_") if p})
    return rec


def main(q):
    nodes = lies_jsonl(ROH / q / "nodes.jsonl")
    recs = [parse(n) for n in nodes]
    by_k = {r["knotenId"]: r for r in recs}
    by_row = {r["rowkey"]: r for r in recs}
    # Baum
    for r in recs:
        p = r["rowkey"].rsplit("_", 1)[0] if "_" in r["rowkey"] else None
        r["eltern"] = by_row[p]["knotenId"] if p in by_row else None
        r["kinder"] = []
    for r in sorted(recs, key=lambda x: [int(i) for i in x["rowkey"].split("_")]):
        if r["eltern"]:
            by_k[r["eltern"]]["kinder"].append(r["knotenId"])
    for r in recs:
        r["teil"] = r["rowkey"].split("_")[0]
        r["referenziert_von"] = []
    for r in recs:
        for v in r["verweise"]:
            if v in by_k and v != r["knotenId"]:
                by_k[v]["referenziert_von"].append(r["knotenId"])
    unresolved = sorted({v for r in recs for v in r["verweise"] if v not in by_k})
    for r in recs:
        r["referenziert_von"] = sorted(set(r["referenziert_von"]))
        r["verweise"] = [v for v in r["verweise"] if v in by_k and v != r["knotenId"]]
    out = AUS / q
    (out / "gop").mkdir(parents=True, exist_ok=True)
    order = sorted(recs, key=lambda x: [int(i) for i in x["rowkey"].split("_")])
    # Ergänzungen: Arztgruppen, Anhang 2 (OPS), BMV-Ä
    from . import extra as X
    for r in recs:
        r["kinder_obj"] = [by_k[c] for c in r["kinder"]]
    extra = {"arztgruppen": X.arztgruppen(q, order, by_row), "ops": X.ops(q), "bmv": X.bmv()}
    for r in recs:
        del r["kinder_obj"]
    if extra["bmv"]:
        codes = {p["nr"] for p in extra["bmv"]["pauschalen"] if p["nr"]}
        for r in recs:
            bv = set()
            for a in r.get("abschnitte", []):
                a["html"], hits = X.link_bmv(a["html"], codes)
                bv.update(hits)
            if bv:
                r["bmv_verweise"] = sorted(bv)
                for h in bv:
                    extra["bmv"].setdefault("ebm_verweise", {}).setdefault(h, []).append(r["knotenId"])
    for name, data in extra.items():
        if data:
            (out / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    index = {"quartal": q, "quelle": SRC, "hinweis": "KI-gebaut (mit einem KI-Assistenten erstellt, nur stichprobenartig geprüft). Inhalte 1:1 aus der EBM-Online-Ansicht der KBV; Markup bereinigt. Nicht amtlich, verbindlich ist die Veröffentlichung der KBV.",
             "anzahl_knoten": len(recs), "anzahl_gop": sum(r["typ"] == "gop" for r in recs),
             "anzahl_gop_nummern": len({r["nr"] for r in recs if r["typ"] == "gop"}),
             "wurzeln": [r["knotenId"] for r in order if r["eltern"] is None],
             "knoten": [{k: r.get(k) for k in ("knotenId", "nr", "titel", "baumtitel", "typ", "teil", "eltern", "kinder", "bewertung")} for r in order]}
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    parts = defaultdict(dict)
    for r in order:
        parts[r["teil"]][r["knotenId"]] = {k: r.get(k) for k in ("merkmale", "abschnitte", "ausschluesse", "verweise", "referenziert_von", "bmv_verweise") if r.get(k)}
    for t, d in parts.items():
        (out / f"teil-{t}.json").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    gops = [r for r in order if r["typ"] == "gop"]
    seen = set()
    for r in gops:
        if r["nr"] in seen:
            continue  # Unterknoten mit gleicher Nummer: Elternknoten gilt
        seen.add(r["nr"])
        g = dict(r)
        g["ausschluesse_aufgeloest"] = [{"bezug": a["bezug"], "gop": [x["nr"] for x in a["leistungen"]],
                                         "kapitel": [x["nr"] for x in a["kapitel"]]} for a in r.get("ausschluesse", [])]
        g["links"] = {"self": f"{SRC}/api/{q}/gop/{r['nr']}", "html": f"{SRC}/{q}/gop/{r['nr']}", "aktuell": f"{SRC}/gop/{r['nr']}"}
        (out / "gop" / f"{r['nr']}.json").write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
    cs = {"resourceType": "CodeSystem", "id": f"ebm-{q}", "url": f"{SRC}/fhir/CodeSystem/ebm", "version": q,
          "name": "EBM", "title": "Einheitlicher Bewertungsmaßstab (Prototyp)", "status": "draft", "experimental": True,
          "publisher": "Prototyp, KI-gebaut, nicht amtlich", "content": "complete", "caseSensitive": True, "hierarchyMeaning": "is-a",
          "property": [{"code": "punkte", "type": "integer"}, {"code": "euro", "type": "decimal"},
                       {"code": "parent", "type": "code"}, {"code": "ausschluss", "type": "code"}, {"code": "knotenId", "type": "string"}],
          "concept": []}
    seen = set()
    for r in gops:
        if r["nr"] in seen:
            continue
        seen.add(r["nr"])
        props = [{"code": "knotenId", "valueString": r["knotenId"]}]
        b = r.get("bewertung", {})
        if re.fullmatch(r"\d+", b.get("punkte", "")):
            props.append({"code": "punkte", "valueInteger": int(b["punkte"])})
        e = b.get("euro", "")
        if re.fullmatch(r"\d+(?:[.,]\d+)?", e):
            props.append({"code": "euro", "valueDecimal": float(e.replace(",", "."))})
        par = by_k.get(r["eltern"])
        while par and par["typ"] == "gop":
            par = by_k.get(par["eltern"])
        for a in r.get("ausschluesse", []):
            props += [{"code": "ausschluss", "valueCode": x["nr"]} for x in a["leistungen"] if GOP.match(x["nr"])]
        cs["concept"].append({"code": r["nr"], "display": r["titel"][:250], "property": props})
    (out / "CodeSystem-ebm.json").write_text(json.dumps(cs, ensure_ascii=False, indent=1), encoding="utf-8")
    site = AUS / "site"
    proto = site / "daten"
    if site.exists():
        shutil.rmtree(site)
    proto.mkdir(parents=True)
    shutil.copy(WEB / "index.html", site / "index.html")
    for f in [out / "index.json"] + sorted(out.glob("teil-*.json")) + [out / f"{n}.json" for n, d in extra.items() if d]:
        (proto / f.name).write_bytes(f.read_bytes())
    bsp = WURZEL / "fragen" / "beispielantworten.json"
    if bsp.exists():
        (proto / bsp.name).write_bytes(bsp.read_bytes())
    print(f"{len(recs)} Knoten, {len(seen)} GOP, {len(parts)} Teile, {len(unresolved)} Verweisziele ohne Knoten im Baum -> {out}")
    if unresolved:
        (out / "unaufgeloest.txt").write_text("\n".join(unresolved), encoding="utf-8")

