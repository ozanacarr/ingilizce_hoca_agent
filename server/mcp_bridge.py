"""MCP köprüsü: sınıf araçlarını Claude Code'a tanıtır.

Claude Code bu dosyayı ayrı bir süreç olarak başlatır ve stdin/stdout üzerinden MCP (JSON-RPC) konuşur.
Köprü kendisi hiçbir şey yapmaz: Claude Code bir araç çağırdığında isteği Hoca sunucusuna iletir
(tahtaya yazma, hafızayı güncelleme gibi işler orada yapılır) ve sonucu geri döndürür.

Ortam değişkenleri (sunucu ayarlar): HOCA_URL, HOCA_SESSION, HOCA_TOKEN
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.tools import TOOLS  # noqa: E402

PROTOCOL_VERSION = "2025-06-18"


def tool_list() -> list[dict]:
    return [{"name": t["name"], "description": t["description"], "inputSchema": t["input_schema"]} for t in TOOLS]


def call_hoca(name: str, arguments: dict) -> tuple[str, bool]:
    body = json.dumps(
        {"session": os.environ.get("HOCA_SESSION"), "name": name, "arguments": arguments}, ensure_ascii=False
    ).encode("utf-8")
    req = urllib.request.Request(
        os.environ.get("HOCA_URL", "http://127.0.0.1:8765") + "/internal/tool",
        data=body,
        headers={"Content-Type": "application/json", "X-Hoca-Token": os.environ.get("HOCA_TOKEN", "")},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("result", ""), bool(data.get("is_error"))
    except urllib.error.URLError as exc:
        return f"Classroom server unreachable: {exc}", True


def reply(msg_id, result=None, error=None) -> None:
    out = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, msg_id = msg.get("method"), msg.get("id")
        if msg_id is None:
            continue  # bildirim (ör. notifications/initialized): cevap gerekmez
        if method == "initialize":
            reply(
                msg_id,
                {
                    "protocolVersion": msg.get("params", {}).get("protocolVersion", PROTOCOL_VERSION),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "hoca", "version": "1.0"},
                },
            )
        elif method == "tools/list":
            reply(msg_id, {"tools": tool_list()})
        elif method == "tools/call":
            params = msg.get("params", {})
            text, is_error = call_hoca(params.get("name", ""), params.get("arguments") or {})
            reply(msg_id, {"content": [{"type": "text", "text": text}], "isError": is_error})
        elif method == "ping":
            reply(msg_id, {})
        else:
            reply(msg_id, error={"code": -32601, "message": f"Method not found: {method}"})


if __name__ == "__main__":
    main()
