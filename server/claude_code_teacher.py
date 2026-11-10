"""Claude Code öğretmen motoru: öğretmeni kullanıcının kendi Claude hesabıyla (Pro, Max...) çalıştırır.

API anahtarı gerekmez. Bilgisayarda kurulu Claude Code'u arka planda başlatır:
  - Öğretmenin kişiliği sistem promptu olarak verilir.
  - Sınıf araçları (tahta, soru kartı, kırmızı kalem...) mcp_bridge.py üzerinden bağlanır.
  - Claude Code'un kendi kodlama araçları (dosya, komut satırı...) tamamen kapatılır.
Kullanım, kullanıcının Claude aboneliğinin limitlerinden düşer.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from .memory import StudentMemory
from .teacher import Emit, build_system_prompt

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "data" / "claude_workspace"

CLAUDE_CODE_NOTE = """
# Tools in this app
Your classroom tools come from the "hoca" MCP server, so their full names are mcp__hoca__board_write,
mcp__hoca__ask_question, mcp__hoca__correct_mistake and so on. They are your only tools.
"""


def find_claude() -> str | None:
    """Claude Code'un çalıştırılabilir dosyasını bulur. npm ile kurulduysa .cmd yerine asıl claude.exe'yi döndürür."""
    path = shutil.which("claude")
    if not path:
        return None
    p = Path(path)
    if p.suffix.lower() in (".cmd", ".bat", "") and os.name == "nt":
        exe = p.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if exe.exists():
            return str(exe)
        cmd = p.with_suffix(".cmd")
        return str(cmd) if cmd.exists() else path
    return path


def _child_env() -> dict:
    env = dict(os.environ)
    # API anahtarı ortamda varsa Claude Code onu kullanır; abonelikle çalışması için çıkarıyoruz.
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return env


_auth_cache: dict = {"at": 0.0, "value": None}


def auth_status() -> dict | None:
    """Claude Code'a giriş yapılmış mı? {"loggedIn": bool, "subscriptionType": "pro", ...} ya da None (kurulu değil)."""
    if time.time() - _auth_cache["at"] < 60 and _auth_cache["value"] is not None:
        return _auth_cache["value"]
    exe = find_claude()
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "auth", "status", "--json"], capture_output=True, text=True, encoding="utf-8",
            timeout=30, env=_child_env(),
        )
        data = json.loads(out.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        data = {"loggedIn": False}
    value = {"loggedIn": bool(data.get("loggedIn")), "subscriptionType": data.get("subscriptionType")}
    _auth_cache.update(at=time.time(), value=value)
    return value


class ClaudeCodeTeacher:
    mode = "claude"

    def __init__(self, memory: StudentMemory, session_id: str, server_url: str, token: str, plan: str | None):
        self.memory = memory
        self.session_id = session_id
        self.server_url = server_url
        self.token = token
        self.plan = plan
        self.proc: subprocess.Popen | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queue: asyncio.Queue = asyncio.Queue()
        self.stderr_tail: deque[str] = deque(maxlen=20)
        self.emit: Emit | None = None
        self.turn_done: asyncio.Event | None = None
        self.pump_task: asyncio.Task | None = None
        # akış durumu
        self.text_blocks: set[int] = set()
        self.streamed_messages: set[str] = set()
        self.current_message: str | None = None
        self.reported_error = False

    # ---------------------------------------------------------------- süreç
    def _write_files(self) -> tuple[Path, Path]:
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        prompt_file = WORKSPACE / f"system_{self.session_id}.md"
        prompt_file.write_text(
            build_system_prompt() + CLAUDE_CODE_NOTE + "\n\n" + self.memory.summary_for_teacher(), encoding="utf-8"
        )
        mcp_file = WORKSPACE / f"mcp_{self.session_id}.json"
        mcp_file.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "hoca": {
                            "command": sys.executable,
                            "args": [str(ROOT / "server" / "mcp_bridge.py")],
                            "env": {
                                "HOCA_URL": self.server_url,
                                "HOCA_SESSION": self.session_id,
                                "HOCA_TOKEN": self.token,
                                "PYTHONIOENCODING": "utf-8",
                            },
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        return prompt_file, mcp_file

    def _spawn(self) -> None:
        exe = find_claude()
        prompt_file, mcp_file = self._write_files()
        args = [
            exe, "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--system-prompt-file", str(prompt_file),
            "--mcp-config", str(mcp_file),
            "--strict-mcp-config",
            "--allowedTools", "mcp__hoca",
            "--tools", "",
            "--setting-sources", "local",
            "--disable-slash-commands",
            "--no-session-persistence",
        ]
        if os.environ.get("HOCA_CLAUDE_MODEL"):
            args += ["--model", os.environ["HOCA_CLAUDE_MODEL"]]
        if os.environ.get("HOCA_EFFORT"):
            args += ["--effort", os.environ["HOCA_EFFORT"]]
        self.proc = subprocess.Popen(
            args, cwd=WORKSPACE, env=_child_env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            self.loop.call_soon_threadsafe(self.queue.put_nowait, obj)
        self.loop.call_soon_threadsafe(self.queue.put_nowait, {"type": "_exit"})

    def _read_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        for line in self.proc.stderr:
            if line.strip():
                self.stderr_tail.append(line.strip())

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def close(self) -> None:
        if self.alive():
            try:
                self.proc.stdin.close()
                self.proc.terminate()
            except OSError:
                pass
        for f in WORKSPACE.glob(f"*_{self.session_id}.*"):
            f.unlink(missing_ok=True)

    # ---------------------------------------------------------------- ders
    async def start(self, emit: Emit) -> None:
        self.emit = emit
        self.loop = asyncio.get_running_loop()
        await self.student_turn(
            "[system] The student has just sat down at their desk. Greet them and start today's lesson.", emit
        )

    async def student_says(self, text: str, via: str, emit: Emit) -> None:
        tag = via if via in ("text", "voice", "answer") else "text"
        await self.student_turn(f"[{tag}] {text}", emit)

    async def student_turn(self, content: str, emit: Emit) -> None:
        self.emit = emit
        if not self.alive():
            if self.proc is not None:
                await emit({"type": "error", "message": "Claude Code yeniden başlatıldı; öğretmen bu dersin önceki kısmını hatırlamayabilir."})
            self.queue = asyncio.Queue()
            self._spawn()
            if self.pump_task is None or self.pump_task.done():
                self.pump_task = asyncio.create_task(self._pump())
        self.turn_done = asyncio.Event()
        self.reported_error = False
        await emit({"type": "thinking", "on": True})
        msg = {"type": "user", "message": {"role": "user", "content": content}}
        try:
            self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except OSError:
            await emit({"type": "error", "message": "Claude Code'a mesaj gönderilemedi."})
            await emit({"type": "turn_end"})
            return
        await self.turn_done.wait()

    async def _finish_turn(self) -> None:
        await self.emit({"type": "thinking", "on": False})
        await self.emit({"type": "turn_end"})
        if self.turn_done:
            self.turn_done.set()

    async def _pump(self) -> None:
        """Claude Code'un çıktısını okuyup sınıf olaylarına çevirir."""
        while True:
            obj = await self.queue.get()
            kind = obj.get("type")
            try:
                if kind == "_exit":
                    tail = " ".join(list(self.stderr_tail)[-3:]) or "bilinmeyen sebep"
                    await self.emit({"type": "error", "message": f"Claude Code kapandı: {tail}"})
                    await self._finish_turn()
                    return
                if kind == "system" and obj.get("subtype") == "init":
                    for server in obj.get("mcp_servers", []):
                        if server.get("name") == "hoca" and server.get("status") != "connected":
                            await self.emit({"type": "error", "message": f"Sınıf araçları bağlanamadı ({server.get('status')})."})
                elif kind == "stream_event":
                    await self._on_stream_event(obj.get("event", {}))
                elif kind == "assistant":
                    await self._on_assistant(obj.get("message", {}))
                elif kind == "result":
                    if (obj.get("is_error") or obj.get("subtype") != "success") and not self.reported_error:
                        detail = obj.get("result") or obj.get("subtype") or "bilinmeyen hata"
                        await self.emit({"type": "error", "message": f"Claude: {detail}"})
                    await self._finish_turn()
            except Exception as exc:  # bir olay bozuk diye ders düşmesin
                await self.emit({"type": "error", "message": f"Olay işlenemedi: {exc}"})

    async def _on_stream_event(self, ev: dict) -> None:
        t = ev.get("type")
        if t == "message_start":
            self.current_message = ev.get("message", {}).get("id")
            self.text_blocks = set()
        elif t == "content_block_start":
            block = ev.get("content_block", {})
            if block.get("type") == "text":
                self.text_blocks.add(ev.get("index"))
                if self.current_message:
                    self.streamed_messages.add(self.current_message)
                await self.emit({"type": "thinking", "on": False})
                await self.emit({"type": "say_start"})
            elif block.get("type") == "tool_use":
                await self.emit({"type": "thinking", "on": False})
        elif t == "content_block_delta":
            delta = ev.get("delta", {})
            if delta.get("type") == "text_delta" and ev.get("index") in self.text_blocks:
                await self.emit({"type": "say_delta", "text": delta.get("text", "")})
        elif t == "content_block_stop":
            if ev.get("index") in self.text_blocks:
                await self.emit({"type": "say_end"})
        elif t == "message_stop":
            await self.emit({"type": "thinking", "on": True})

    async def _on_assistant(self, message: dict) -> None:
        # Claude Code'un kendi hata mesajları (giriş, limit...) "<synthetic>" model adıyla gelir: öğretmen konuşması değil.
        if message.get("model") == "<synthetic>":
            text = " ".join(b.get("text", "") for b in message.get("content", []) if b.get("type") == "text").strip()
            lowered = text.lower()
            if any(k in lowered for k in ("authenticate", "oauth", "/login", "log in", "api key")):
                _auth_cache["at"] = 0.0
                text = (
                    "Claude Code oturumunun süresi dolmuş ya da giriş yapılmamış. Bir terminal aç, "
                    "'claude auth login' yazıp kendi hesabınla giriş yap, sonra bu sayfayı yenile."
                )
            elif any(k in lowered for k in ("limit", "usage")):
                text = f"Claude kullanım limitine ulaşıldı: {text}"
            await self.emit({"type": "error", "message": text or "Claude Code bir hata bildirdi."})
            self.reported_error = True
            return
        # Kısmi akış gelmediyse (eski sürümler) metni tam mesajdan göster.
        if message.get("id") in self.streamed_messages:
            return
        for block in message.get("content", []):
            if block.get("type") == "text" and block.get("text", "").strip():
                await self.emit({"type": "thinking", "on": False})
                await self.emit({"type": "say_start"})
                await self.emit({"type": "say_delta", "text": block["text"]})
                await self.emit({"type": "say_end"})
