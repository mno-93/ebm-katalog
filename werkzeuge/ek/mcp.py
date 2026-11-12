"""MCP-Server (Model Context Protocol) über stdio, nur Standardbibliothek.

Start: python3 -I werkzeuge/ek.py mcp [QUARTAL]
Werkzeuge: siehe katalog.WERKZEUGE. Antwortregeln: docs/ANTWORTREGELN.md (als `instructions` und Vorlage `ebm_frage`).
"""
import json
import sys
import traceback

from .grundlagen import WURZEL
from .katalog import WERKZEUGE, Katalog

VERSIONEN = ["2025-06-18", "2025-03-26", "2024-11-05"]
REGELN = (WURZEL / "docs" / "ANTWORTREGELN.md").read_text(encoding="utf-8")


def schema(params):
    return {"type": "object", "additionalProperties": False,
            "properties": {k: {"type": t, "description": d} for k, (t, d, _) in params.items()},
            "required": [k for k, (_, _, pflicht) in params.items() if pflicht]}


class Server:
    def __init__(self, quartal=None):
        self.quartal = quartal
        self._k = None

    @property
    def k(self):
        if self._k is None:
            self._k = Katalog(self.quartal)
        return self._k

    def behandeln(self, m):
        meth, p = m.get("method"), m.get("params") or {}
        if meth == "initialize":
            v = p.get("protocolVersion")
            return {"protocolVersion": v if v in VERSIONEN else VERSIONEN[0],
                    "capabilities": {"tools": {}, "prompts": {}},
                    "serverInfo": {"name": "ebm-katalog", "version": "0.1.0"},
                    "instructions": REGELN}
        if meth == "ping":
            return {}
        if meth == "tools/list":
            return {"tools": [{"name": n, "description": d, "inputSchema": schema(ps)} for n, (d, ps, _) in WERKZEUGE.items()]}
        if meth == "tools/call":
            name, args = p.get("name"), p.get("arguments") or {}
            if name not in WERKZEUGE:
                return {"content": [{"type": "text", "text": f"Unbekanntes Werkzeug {name}"}], "isError": True}
            _, ps, fn = WERKZEUGE[name]
            fehlend = [k for k, (_, _, pflicht) in ps.items() if pflicht and not args.get(k)]
            if fehlend:
                return {"content": [{"type": "text", "text": f"Fehlende Angabe: {', '.join(fehlend)}"}], "isError": True}
            try:
                r = fn(self.k, args)
            except Exception as e:  # Fehler als Werkzeugergebnis, damit das Modell reagieren kann
                return {"content": [{"type": "text", "text": f"Fehler: {e}"}], "isError": True}
            return {"content": [{"type": "text", "text": json.dumps(r, ensure_ascii=False, indent=1)}], "isError": False}
        if meth == "prompts/list":
            return {"prompts": [{"name": "ebm_frage", "description": "Frage zum EBM oder BMV-Ä nach den Antwortregeln beantworten",
                                 "arguments": [{"name": "frage", "description": "Die Frage", "required": True}]}]}
        if meth == "prompts/get":
            frage = (p.get("arguments") or {}).get("frage", "")
            return {"description": "Frage nach den Antwortregeln beantworten",
                    "messages": [{"role": "user", "content": {"type": "text", "text": f"{REGELN}\n\nFrage: {frage}"}}]}
        raise LookupError(meth)


def main(argv=None):
    s = Server(argv[0] if argv else None)
    for zeile in sys.stdin:
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            m = json.loads(zeile)
        except json.JSONDecodeError:
            antwort = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
            print(json.dumps(antwort), flush=True); continue
        if "id" not in m:  # Benachrichtigung
            continue
        try:
            antwort = {"jsonrpc": "2.0", "id": m["id"], "result": s.behandeln(m)}
        except LookupError as e:
            antwort = {"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32601, "message": f"Methode unbekannt: {e}"}}
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            antwort = {"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32603, "message": str(e)}}
        print(json.dumps(antwort, ensure_ascii=False), flush=True)
    return 0
