"""Abzug der EBM-Online-Ansicht (ebm.kbv.de) für das dort voreingestellte Quartal.

  ek.py abzug                      EBM-Ansicht: jeden Knoten auswählen   -> rohdaten/<Q>/nodes.jsonl
  ek.py abzug --ansicht ops        Anhang-2-Ansicht (OPS), jeden Knoten  -> rohdaten/<Q>/ops_nodes.jsonl
  ek.py abzug --arztgruppen        je Arztgruppe den gefilterten Baum    -> rohdaten/<Q>/arztgruppen/<Gruppe>.jsonl
  Optionen: --limit N  --delay 0.3

Tiefensuche über den PrimeFaces-Baum; Elternknoten werden aufgeklappt, Knoten ausgewählt
(Detailansicht als Roh-HTML). Im Arztgruppenmodus wird nur aufgeklappt, nicht ausgewählt; GOP mit
Untergliederung werden nicht aufgeklappt (Kinder tragen dieselbe Nummer). Eine Anfrage nach der
anderen mit Pause; fortsetzbar. Danach `ek.py packen` aufrufen.
"""
import argparse, json, re, sys, time
from .grundlagen import ROH as OUT
from .jsf import JSF, updates
BASE = {"mainForm:arztgrpFilter": "", "mainForm:searchTerm_input": "", "mainForm:searchTerm_hinput": "",
        "mainForm:tree_selection": "", "mainForm:tree_scrollState": "0,0", "mainForm:favoritenTabelle_selection": ""}
BASE_OPS = {"mainForm:abulant": "on", "mainForm:stationaer": "on", "mainForm:kstFilter": "",
            "mainForm:searchTerm_input": "", "mainForm:searchTerm_hinput": "", "mainForm:tree_selection": "",
            "mainForm:tree_scrollState": "0,0", "mainForm:favoritenTabelle_selection": ""}
NODE = re.compile(r'<li id="mainForm:tree:[^"]+" data-rowkey="([^"]+)"[^>]*class="([^"]*)".*?white-space: normal;">([^<]*)<', re.S)
GOPLABEL = re.compile(r"^\d{5}[A-Z]?\b")


class Crawler:
    def __init__(self, delay, path="/index.xhtml", base=BASE, filter_=None):
        self.delay, self.path, self.base, self.filter = delay, path, dict(base), filter_
        self.new_session()

    def new_session(self):
        self.j = JSF(self.delay)
        page = self.j.get(self.path)
        self.quartal = re.search(r'<option value="([^"]+)" selected', page).group(1).replace("/Q", "-")
        if self.filter is not None:
            self.base["mainForm:arztgrpFilter"] = self.filter
            page = self.j.ajax("mainForm", "mainForm:arztgrpFilter", event="valueChange",
                               process="mainForm:arztgrpFilter", update="mainForm", extra=self.base)
        self.roots = [(k, "parent" in c, t.strip()) for k, c, t in NODE.findall(page) if "_" not in k]

    def expand(self, key):
        r = self.j.ajax("mainForm", "mainForm:tree", update="mainForm:tree",
                        extra={**self.base, "mainForm:tree_expandNode": key})
        kids = [(k, "parent" in c, t.strip()) for k, c, t in NODE.findall(r) if k.rsplit("_", 1)[0] == key]
        if not kids:
            raise RuntimeError(f"keine Kinder für {key}")
        return kids

    def select(self, key):
        r = self.j.ajax("mainForm", "mainForm:tree", event="select",
                        update="mainForm:detailsPanel mainForm:buttonsPG",
                        extra={**self.base, "mainForm:tree_instantSelection": key, "mainForm:tree_selection": key})
        d = updates(r).get("mainForm:detailsPanel", "")
        rk = re.search(r'<div id="rowKey"[^>]*>([^<]*)<', d)
        if not rk or rk.group(1) != key:
            raise RuntimeError(f"Auswahl {key} lieferte {rk.group(1) if rk else 'nichts'}")
        kid = re.search(r'<div id="knotenId"[^>]*>([^<]*)<', d).group(1)
        return kid, d

    def restore(self, key):
        """Nach Sitzungsverlust die Vorfahren erneut aufklappen."""
        self.new_session()
        parts = key.split("_")
        for i in range(1, len(parts)):
            self.expand("_".join(parts[:i]))


def walk(c, f, select=True, expand_gop=True, limit=0):
    done = set()
    if f.exists():
        for l in f.open(encoding="utf-8"):
            done.add(json.loads(l)["rowkey"])
    fh = f.open("a", encoding="utf-8")
    stack = [(k, p, t, []) for k, p, t in reversed(c.roots)]
    n_new, t0 = 0, time.time()
    while stack:
        key, parent, label, path = stack.pop()
        want_expand = parent and (expand_gop or not GOPLABEL.match(label))
        for attempt in range(4):
            try:
                if key not in done:
                    rec = {"rowkey": key, "parent": parent, "label": label, "pfad": path}
                    if select:
                        rec["knotenId"], rec["html"] = c.select(key)
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n"); fh.flush()
                    done.add(key); n_new += 1
                kids = c.expand(key) if want_expand else []
                break
            except Exception as e:
                print(f"! {key}: {e} – neuer Versuch {attempt + 1}", file=sys.stderr)
                time.sleep(5 * (attempt + 1))
                try:
                    c.restore(key)
                except Exception as e2:
                    print(f"! Wiederherstellung fehlgeschlagen: {e2}", file=sys.stderr)
        else:
            print(f"!! {key} übersprungen", file=sys.stderr)
            continue
        stack.extend((k, p, t, path + [label]) for k, p, t in reversed(kids))
        if n_new and n_new % 200 == 0:
            print(f"{f.name}: {len(done)} Knoten, {n_new} neu, {time.time() - t0:.0f} s, {label[:50]}", file=sys.stderr)
        if limit and n_new >= limit:
            break
    print(f"fertig: {len(done)} Knoten in {f}", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ek.py abzug")
    ap.add_argument("--ansicht", choices=["ebm", "ops"], default="ebm")
    ap.add_argument("--arztgruppen", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=0.3)
    a = ap.parse_args(argv)
    if a.ansicht == "ops":
        c = Crawler(a.delay, "/ops.xhtml", BASE_OPS)
        out = OUT / c.quartal; out.mkdir(parents=True, exist_ok=True)
        walk(c, out / "ops_nodes.jsonl", limit=a.limit)
    elif a.arztgruppen:
        c = Crawler(a.delay)
        groups = re.findall(r'<option value="([^"]+)">', c.j.page.split('id="mainForm:arztgrpFilter"')[1].split("</select>")[0])
        out = OUT / c.quartal / "arztgruppen"; out.mkdir(parents=True, exist_ok=True)
        (out / "_gruppen.json").write_text(json.dumps(groups, ensure_ascii=False, indent=1), encoding="utf-8")
        for g in groups:
            fn = out / (re.sub(r"[^\w-]+", "_", g).strip("_") + ".jsonl")
            if fn.exists() and fn.with_suffix(".fertig").exists():
                continue
            walk(Crawler(a.delay, filter_=g), fn, select=False, expand_gop=False, limit=a.limit)
            if not a.limit:
                fn.with_suffix(".fertig").write_text(g, encoding="utf-8")
    else:
        c = Crawler(a.delay)
        out = OUT / c.quartal; out.mkdir(parents=True, exist_ok=True)
        walk(c, out / "nodes.jsonl", limit=a.limit)

