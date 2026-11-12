"""Protokolltests des MCP-Servers (ohne Katalogdaten)."""
import json, sys, unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "werkzeuge"))
from ek import katalog, mcp  # noqa: E402


class Protokoll(unittest.TestCase):
    def setUp(self):
        self.s = mcp.Server()

    def test_initialize_mit_regeln(self):
        r = self.s.behandeln({"method": "initialize", "params": {"protocolVersion": "2025-03-26"}})
        self.assertEqual(r["protocolVersion"], "2025-03-26")
        self.assertIn("Nur aus Werkzeugergebnissen", r["instructions"])
        r = self.s.behandeln({"method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
        self.assertEqual(r["protocolVersion"], mcp.VERSIONEN[0])

    def test_werkzeuge_mit_schema(self):
        tools = self.s.behandeln({"method": "tools/list"})["tools"]
        self.assertEqual({t["name"] for t in tools}, set(katalog.WERKZEUGE))
        gop = next(t for t in tools if t["name"] == "ebm_gop")
        self.assertEqual(gop["inputSchema"]["required"], ["nr"])

    def test_fehler_als_werkzeugergebnis(self):
        r = self.s.behandeln({"method": "tools/call", "params": {"name": "gibtsnicht", "arguments": {}}})
        self.assertTrue(r["isError"])
        r = self.s.behandeln({"method": "tools/call", "params": {"name": "ebm_gop", "arguments": {}}})
        self.assertTrue(r["isError"])

    def test_unbekannte_methode(self):
        with self.assertRaises(LookupError):
            self.s.behandeln({"method": "gibts/nicht"})

    def test_annotations_und_ausgabeschema(self):
        for t in self.s.behandeln({"method": "tools/list"})["tools"]:
            self.assertTrue(t["annotations"]["readOnlyHint"])
            self.assertFalse(t["annotations"]["openWorldHint"])
            self.assertEqual(t["outputSchema"]["type"], "object")
            self.assertTrue(t["title"])

    def test_faehigkeiten(self):
        caps = self.s.behandeln({"method": "initialize", "params": {}})["capabilities"]
        self.assertEqual(set(caps), {"tools", "prompts", "resources", "completions"})

    def test_resources_und_vorlagen(self):
        uris = [r["uri"] for r in self.s.behandeln({"method": "resources/list"})["resources"]]
        self.assertIn("ebm://regeln", uris)
        r = self.s.behandeln({"method": "resources/read", "params": {"uri": "ebm://regeln"}})
        self.assertIn("Nur aus Werkzeugergebnissen", r["contents"][0]["text"])
        tpl = [r["uriTemplate"] for r in self.s.behandeln({"method": "resources/templates/list"})["resourceTemplates"]]
        self.assertTrue(any(u.endswith("/gop/{nr}") for u in tpl))

    def test_vorlagen_liste(self):
        namen = {p["name"] for p in self.s.behandeln({"method": "prompts/list"})["prompts"]}
        self.assertEqual(namen, {"ebm_frage", "ebm_fallpruefung", "ebm_folgenabschaetzung"})
        r = self.s.behandeln({"method": "prompts/get", "params": {"name": "ebm_fallpruefung", "arguments": {"gops": "03000, 03230", "alter": "60"}}})
        self.assertIn("Alter 60", r["messages"][0]["content"]["text"])

    def test_schema_mit_auswahl(self):
        s = mcp.schema({"x": ("string", "d", True, ["a", "b"]), "y": ("integer", "e", False)})
        self.assertEqual(s["properties"]["x"]["enum"], ["a", "b"])
        self.assertEqual(s["required"], ["x"])

    def test_vorlage(self):
        r = self.s.behandeln({"method": "prompts/get", "params": {"name": "ebm_frage", "arguments": {"frage": "Was ist 03000?"}}})
        self.assertIn("Was ist 03000?", r["messages"][0]["content"]["text"])


class Hilfen(unittest.TestCase):
    def test_liste(self):
        self.assertEqual(katalog.liste("03000, 03040;01436 x"), ["03000", "03040", "01436", "X"])
        self.assertEqual(katalog.liste(["03000", " "]), ["03000"])

    def test_auszuege(self):
        t = "a" * 1000 + " 03230 | x " + "b" * 1000 + " 03230 " + "c" * 50
        st = katalog.auszuege(t, "03230", fenster=20)
        self.assertEqual(len(st), 2)
        self.assertTrue(all("03230" in s for s in st))


class Klartext(unittest.TestCase):
    def test_listen(self):
        self.assertEqual(katalog.klartext("<ul><li><p>eins,</p></li><li><p>zwei</p></li></ul>"), "- eins,\n- zwei")


if __name__ == "__main__":
    unittest.main()
