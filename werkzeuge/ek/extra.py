"""Ergänzungen zum Web-Export: Arztgruppenfilter, Anhang-2-Ansicht (OPS) und BMV-Ä-Pauschalen.

Wird von web_export.py aufgerufen. Erzeugt:
  arztgruppen.json   {gruppen: [...], sichtbar: {Gruppe: [Index in index.knoten, ...]}}
  ops.json           Baum der Anhang-2-Ansicht mit Kategorie, Seitenangabe, §115b und GOP-Zuordnung
  bmv.json           Pauschalen aus dem BMV-Ä und seinen Anlagen (aus bmv/bmv_pauschalen.json)
"""
import html as H, json, re

from .grundlagen import QUELLEN, ROH, datei, lies_jsonl
GOP = re.compile(r"^\d{5}[A-Z]?$")


def text(s):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def rk_key(rk):
    return [int(i) for i in rk.split("_")]


# ---------- Arztgruppen ----------
def arztgruppen(q, order, by_row):
    d = ROH / q / "arztgruppen"
    if not (d / "_gruppen.json").exists():
        return None
    groups = json.loads((d / "_gruppen.json").read_text(encoding="utf-8"))
    pos = {r["knotenId"]: i for i, r in enumerate(order)}
    path_of = {}
    for r in order:
        parts = r["rowkey"].split("_")
        path_of[tuple(by_row["_".join(parts[:i + 1])]["baumtitel"] for i in range(len(parts)))] = r
    def desc(r):
        out = [r]
        for c in r["kinder_obj"]:
            out += desc(c)
        return out
    sichtbar, fehlend, unvollstaendig = {}, {}, []
    for g in groups:
        fn = d / (re.sub(r"[^\w-]+", "_", g).strip("_") + ".jsonl")
        if datei(fn) is None:
            unvollstaendig.append(g); continue
        if not fn.with_suffix(".fertig").exists():
            unvollstaendig.append(g)
        ids, miss = set(), 0
        for x in lies_jsonl(fn):
            r = path_of.get(tuple(x["pfad"] + [x["label"]]))
            if not r:
                miss += 1; continue
            if x["parent"] and r["typ"] == "gop":
                ids.update(pos[n["knotenId"]] for n in desc(r))  # Untergliederung erbt die Sichtbarkeit
            else:
                ids.add(pos[r["knotenId"]])
        sichtbar[g] = sorted(ids)
        if miss:
            fehlend[g] = miss
    return {"gruppen": groups, "sichtbar": sichtbar, "nicht_zugeordnet": fehlend, "unvollstaendig": unvollstaendig}


# ---------- Anhang-2-Ansicht ----------
def ops_knoten(x):
    """Detailansicht eines Knotens der Anhang-2-Ansicht zerlegen."""
    h = x["html"]
    heads = re.findall(r"<h4[^>]*>(.*?)</h4>", h, re.S)
    r = {"id": x["knotenId"], "rowkey": x["rowkey"], "nr": text(heads[0]) if heads else "",
         "titel": text(heads[1]) if len(heads) > 1 else "", "baumtitel": x["label"]}
    for v, u in re.findall(r'<span class="value">(.*?)</span>\s*<br\s*/?>\s*<span class="unit">(.*?)</span>', h, re.S):
        v, ut = text(v), text(u)
        if ut == "SEITE": r["seite"] = v
        elif ut == "§115b": r["p115b"] = v
        elif "ic_action_time" in u: r["kategorie"] = v
    tb = re.search(r'aria-describedby="Zuordnung des OPS-Codes[^"]*"(.*?)</table>', h, re.S)
    if tb:
        rows = []
        for tr in re.findall(r"<tr>(.*?)</tr>", tb.group(1), re.S):
            tds = [text(t) for t in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(tds) == 6 and tds[1] not in ("", "-"):
                rows.append({"art": tds[0], "gop": tds[1], "bezeichnung": tds[2], "punkte": tds[3], "kalk": tds[4], "pruef": tds[5]})
        if rows:
            r["gops"] = rows
    return r


def ops(q):
    f = ROH / q / "ops_nodes.jsonl"
    if datei(f) is None:
        return None
    recs = [ops_knoten(x) for x in lies_jsonl(f)]
    by_row = {r["rowkey"]: r for r in recs}
    for r in recs:
        p = r["rowkey"].rsplit("_", 1)[0] if "_" in r["rowkey"] else None
        r["eltern"] = by_row[p]["id"] if p in by_row else None
        r["kinder"] = []
    recs.sort(key=lambda r: rk_key(r["rowkey"]))
    by_id = {r["id"]: r for r in recs}
    for r in recs:
        if r["eltern"]:
            by_id[r["eltern"]]["kinder"].append(r["id"])
    for r in recs:
        del r["rowkey"]
    return {"quartal": q, "quelle": "https://ebm.kbv.de/ops.xhtml", "anzahl": len(recs),
            "mit_zuordnung": sum(1 for r in recs if r.get("gops")),
            "wurzeln": [r["id"] for r in recs if r["eltern"] is None], "knoten": recs}


# ---------- BMV-Ä ----------
def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")).strip("-")


def bmv():
    f = QUELLEN / "bmv" / "bmv_pauschalen.json"
    if not f.exists():
        return None
    src = json.loads(f.read_text(encoding="utf-8"))
    urls = {}
    lt = QUELLEN / "bmv" / "liste.tsv"
    if lt.exists():
        for l in lt.read_text(encoding="utf-8").splitlines():
            u, fn, *_ = l.split("\t")
            urls[fn] = u
    anlagen, pauschalen = [], []
    for a in src["anlagen"]:
        aid = "anl-" + slug(a["anlage"].split(" ")[0] + "-" + a["titel"])[:40]
        ids = []
        for i, p in enumerate(a["pauschalen"]):
            pid = p["nr"] or f"{aid}-{i + 1}"
            ids.append(pid)
            pauschalen.append({"id": pid, "nr": p["nr"], "titel": p["titel"], "anlage": aid, "abrechnung": p.get("abrechnung"),
                               "betrag": p.get("betrag"), "ausschluesse": p.get("ausschluesse", []),
                               "leistungsinhalt": p.get("leistungsinhalt"), "geltung": p.get("geltung"),
                               "fundstelle": {"datei": (fd := p.get("seite_datei") or a["datei"].split(";")[0].strip()), "seite": p.get("seite"), "url": urls.get(fd)}})
        anlagen.append({"id": aid, "anlage": a["anlage"], "titel": a["titel"], "datei": a["datei"], "fassung": a.get("fassung"),
                        "hoehe": a.get("verguetung_hoehe"), "status": a.get("status"), "pauschalen": ids,
                        "urls": [urls.get(x.strip()) for x in a["datei"].split(";") if urls.get(x.strip())]})
    return {"stand": src["stand"], "quelle": src["quelle"], "hinweis": src["hinweis"], "anlagen": anlagen,
            "pauschalen": pauschalen, "ohne_eigene_pauschale": src["ohne_eigene_pauschale"],
            "nicht_im_katalog": src.get("nicht_im_katalog", [])}


ANL = re.compile(r"(Anlage\s+(\d+[a-z]?(?:\.\d)?)\s+(?:zum\s+|des\s+)?(?:BMV-Ä|BMV|Bundesmantelvertrag(?:es|s)?(?:-Ärzte)?))")


def link_bmv(html_, codes):
    """Bloße BMV-Nummern und Anlagenverweise im EBM-Text verlinken (außerhalb bestehender Links)."""
    parts = re.split(r"(<a\b[^>]*>.*?</a>|<[^>]+>)", html_, flags=re.S)
    out, hits = [], set()
    for p in parts:
        if not p or p.startswith("<"):
            out.append(p); continue
        def rep_code(m):
            hits.add("bmv:" + m.group(1)); return f'<a data-k="bmv:{m.group(1)}">{m.group(1)}</a>'
        p = re.sub(r"\b(" + "|".join(sorted(codes)) + r")\b", rep_code, p) if codes else p
        def rep_anl(m):
            hits.add("anl:" + m.group(2)); return f'<a data-k="anl:{m.group(2)}">{m.group(1)}</a>'
        p = ANL.sub(rep_anl, p)
        out.append(p)
    return "".join(out), sorted(hits)
