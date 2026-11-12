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
            self.s.behandeln({"method": "resources/list"})

    def test_vorlage(self):
        r = self.s.behandeln({"method": "prompts/get", "params": {"name": "ebm_frage", "arguments": {"frage": "Was ist 03000?"}}})
        self.assertIn("Was ist 03000?", r["messages"][0]["content"]["text"])


class Klartext(unittest.TestCase):
    def test_listen(self):
        self.assertEqual(katalog.klartext("<ul><li><p>eins,</p></li><li><p>zwei</p></li></ul>"), "- eins,\n- zwei")


if __name__ == "__main__":
    unittest.main()
