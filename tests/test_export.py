"""Tests der Zerlegung (ohne Netz, mit Ausschnitten der Online-Ansicht in tests/fixtures/)."""
import gzip, json, sys, tempfile, unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "werkzeuge"))
from ek import export, extra, grundlagen  # noqa: E402

FIX = WURZEL / "tests" / "fixtures"


class GopDetail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        html = (FIX / "gop_03000.html").read_text(encoding="utf-8")
        cls.r = export.parse({"html": html, "knotenId": "D#####EDI6###H#", "rowkey": "2_0_0_1_0_0_0", "label": "03000 Versichertenpauschale"})

    def test_kopf(self):
        self.assertEqual(self.r["nr"], "03000")
        self.assertEqual(self.r["titel"], "Versichertenpauschale")
        self.assertEqual(self.r["typ"], "gop")
        self.assertNotIn("bewertung", self.r)  # Bewertung steht in den Altersstufen

    def test_merkmale(self):
        self.assertEqual([m["zutreffend"] for m in self.r["merkmale"]], [False, True])

    def test_abschnitte_in_reihenfolge(self):
        ids = [a["id"] for a in self.r["abschnitte"]]
        self.assertEqual(ids[:5], ["beschreibung", "oblgLeistungsinhalt", "fkttLeistungsinhalt", "abrechnungsbestimmung", "anmerkung"])
        self.assertEqual(self.r["abschnitte"][3]["html"], "einmal im Behandlungsfall")

    def test_links_als_knotenid(self):
        html = self.r["abschnitte"][2]["html"]
        self.assertIn('<a data-k="TZ5###UI1###QG#">4.3.1</a>', html)
        self.assertNotIn("class=", html)

    def test_ausschluesse(self):
        a = self.r["ausschluesse"]
        self.assertEqual(a[0]["bezug"], "in derselben Sitzung")
        self.assertEqual(a[0]["leistungen"][0]["nr"], "01436")
        self.assertIn("im Behandlungsfall", [x["bezug"] for x in a])


class Bereinigung(unittest.TestCase):
    def test_skripte_und_klassen_entfernt(self):
        links = []
        s = export.clean('<div class="x"><p class="EBMX">Text <a class="EBMLINKELEMENT" href="AB#">01100</a></p><script>alert(1)</script></div>', links)
        self.assertEqual(s, '<p>Text <a data-k="AB#">01100</a></p>')
        self.assertEqual(links, ["AB#"])


class Anhang2(unittest.TestCase):
    def test_ops_blatt(self):
        r = extra.ops_knoten(json.loads((FIX / "ops_blatt.json").read_text(encoding="utf-8")))
        self.assertEqual((r["nr"], r["kategorie"], r["p115b"], r["seite"]), ("1-465.90", "Q2", "Ja", "N"))
        self.assertEqual(len(r["gops"]), 8)
        self.assertEqual(r["gops"][0], {"art": "Operation (ambulant)", "gop": "31272", "bezeichnung": "Urologischer Eingriff der Kategorie Q2",
                                        "punkte": "1635", "kalk": "36", "pruef": "29"})


class BmvVerweise(unittest.TestCase):
    def test_nummern_und_anlagen_verlinkt(self):
        h, treffer = extra.link_bmv('<p>nicht neben <a data-k="X">07345</a> und 86510 gemäß Anlage 7 zum BMV-Ä</p>', {"86510"})
        self.assertIn('<a data-k="bmv:86510">86510</a>', h)
        self.assertIn('<a data-k="anl:7">Anlage 7 zum BMV-Ä</a>', h)
        self.assertIn('<a data-k="X">07345</a>', h)
        self.assertEqual(treffer, ["anl:7", "bmv:86510"])

    def test_quelle_vollstaendig(self):
        d = json.loads((WURZEL / "quellen" / "bmv" / "bmv_pauschalen.json").read_text(encoding="utf-8"))
        nrs = [p["nr"] for a in d["anlagen"] for p in a["pauschalen"] if p["nr"]]
        self.assertEqual(len(nrs), len(set(nrs)))
        for a in d["anlagen"]:
            for p in a["pauschalen"]:
                self.assertTrue(p.get("seite"), p["titel"])
                self.assertTrue(p.get("betrag") or "regional" in a["verguetung_hoehe"], p["titel"])


class Rohdaten(unittest.TestCase):
    def test_gz_und_ungepackt(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "x.jsonl"
            with gzip.open(p.with_name("x.jsonl.gz"), "wt", encoding="utf-8") as f:
                f.write('{"a": 1}\n')
            self.assertEqual(grundlagen.lies_jsonl(p), [{"a": 1}])
            p.write_text('{"a": 2}\n', encoding="utf-8")
            self.assertEqual(grundlagen.lies_jsonl(p), [{"a": 2}])


if __name__ == "__main__":
    unittest.main()
