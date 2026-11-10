"""Sunucu: 3D sınıfı (web/) sunar ve tarayıcıyla öğretmen arasında WebSocket köprüsü kurar.

Çalıştırma:  .venv\\Scripts\\python -m uvicorn server.main:app --port 8765
Sonra tarayıcıda: http://localhost:8765

Öğretmenin motoru (HOCA_ENGINE ile zorlanabilir, yoksa sırayla denenir):
  1. claude : Bilgisayardaki Claude Code, kullanıcının kendi Claude hesabıyla (Pro, Max...). API anahtarı gerekmez.
  2. api    : ANTHROPIC_API_KEY ile Claude API (kullanım kadar ücretli).
  3. demo   : Hiçbiri yoksa hazır senaryolu demo ders.
"""

from __future__ import annotations

import asyncio
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .demo import DemoTeacher
from .memory import StudentMemory
from .tools import execute_tool, validate_input

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data"


def load_env_file(path: Path) -> None:
    """Proje klasöründeki .env dosyasını okur (ör. ANTHROPIC_API_KEY=...). Zaten tanımlı değişkenlere dokunmaz."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


load_env_file(ROOT / ".env")

from .claude_code_teacher import ClaudeCodeTeacher, auth_status  # noqa: E402  (.env okunduktan sonra)

app = FastAPI(title="Hoca Agent")

# ---------------------------------------------------------------- güvenlik
# Sınıf sadece bu bilgisayardaki kendi sayfasından kullanılabilir. Tarayıcıda açık başka bir web sitesi
# localhost'a bağlanmaya çalışırsa (Origin kontrolü) ya da kendi alan adını localhost'a yönlendirirse
# (Host kontrolü, "DNS rebinding") istek reddedilir.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _hostname(value: str | None) -> str | None:
    """'localhost:8765', '[::1]:8765' ya da 'http://localhost:8765' içinden sadece makine adını çıkarır."""
    if not value:
        return None
    if "://" not in value:
        value = "http://" + value
    try:
        return urlsplit(value).hostname
    except ValueError:
        return None


def is_local_host(host_header: str | None) -> bool:
    return _hostname(host_header) in LOCAL_HOSTS


def is_local_origin(origin: str | None) -> bool:
    return origin is not None and urlsplit(origin).scheme in ("http", "https") and _hostname(origin) in LOCAL_HOSTS


@app.middleware("http")
async def only_local_hosts(request: Request, call_next):
    if not is_local_host(request.headers.get("host")):
        return JSONResponse({"error": "Hoca sadece bu bilgisayardan (localhost) kullanılabilir."}, status_code=403)
    return await call_next(request)


# Açık dersler: Claude Code'un araç çağrıları (MCP köprüsü üzerinden) doğru sınıfa buradan yönlenir.
SESSIONS: dict[str, dict] = {}


def has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


async def choose_engine() -> tuple[str, dict | None, str | None]:
    """(motor, claude hesap durumu, kullanıcıya gösterilecek not) döndürür."""
    forced = os.environ.get("HOCA_ENGINE", "").lower()
    if forced == "demo":
        return "demo", None, None
    if forced == "api":
        return ("api", None, None) if has_api_key() else ("demo", None, "HOCA_ENGINE=api ama ANTHROPIC_API_KEY tanımlı değil; demo açıldı.")
    status = await asyncio.to_thread(auth_status)
    if status and status["loggedIn"]:
        return "claude", status, None
    if forced == "claude" or not has_api_key():
        if status is None:
            note = "Claude Code bulunamadı, demo ders açıldı. Kendi Claude hesabınla ders yapmak için Claude Code'u kur."
        else:
            note = "Claude Code'a giriş yapılmamış, demo ders açıldı. Terminalde 'claude' yazıp hesabınla giriş yap, sonra sayfayı yenile."
        return "demo", status, note
    return "api", status, None


def make_teacher(engine: str, session_id: str, server_url: str, token: str, status: dict | None):
    if engine == "claude":
        return ClaudeCodeTeacher(
            StudentMemory(DATA_DIR / "student.json"), session_id, server_url, token,
            (status or {}).get("subscriptionType"),
        )
    if engine == "api":
        from .teacher import LiveTeacher

        return LiveTeacher(StudentMemory(DATA_DIR / "student.json"))
    # Demo kendi dosyasını kullanır ve her seferinde sıfırdan başlar; gerçek öğrenci dosyanı kirletmez.
    demo_file = DATA_DIR / "student_demo.json"
    demo_file.unlink(missing_ok=True)
    return DemoTeacher(StudentMemory(demo_file))


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


@app.post("/internal/tool")
async def internal_tool(request: Request):
    """MCP köprüsünden gelen araç çağrısı: aracı ilgili dersin hafızasıyla çalıştırır, olayları o sınıfa yollar."""
    body = await request.json()
    session = SESSIONS.get(str(body.get("session")))
    if not session or not secrets.compare_digest(session["token"], request.headers.get("X-Hoca-Token", "")):
        return JSONResponse({"result": "Unknown classroom session.", "is_error": True}, status_code=403)
    name, args = body.get("name", ""), body.get("arguments") or {}
    problem = validate_input(name, args)
    if problem:
        return {"result": f"Invalid input: {problem}", "is_error": True}
    events, result = execute_tool(name, args, session["teacher"].memory)
    for ev in events:
        await session["emit"](ev)
    return {"result": result, "is_error": False}


@app.websocket("/ws")
async def classroom(ws: WebSocket):
    # Tarayıcılar WebSocket'te site kısıtlamasını kendiliğinden uygulamaz; başka sitelerden gelen bağlantıyı biz reddediyoruz.
    if not (is_local_host(ws.headers.get("host")) and is_local_origin(ws.headers.get("origin"))):
        await ws.close(code=1008)
        return
    await ws.accept()
    send_lock = asyncio.Lock()
    busy = asyncio.Lock()  # öğretmen konuşurken yeni mesaj sıraya girer

    async def emit(event: dict) -> None:
        async with send_lock:
            await ws.send_json(event)

    engine, status, note = await choose_engine()
    session_id, token = secrets.token_hex(8), secrets.token_urlsafe(24)
    host, port = ws.scope.get("server") or ("127.0.0.1", 8765)
    teacher = make_teacher(engine, session_id, f"http://127.0.0.1:{port}", token, status)
    SESSIONS[session_id] = {"teacher": teacher, "emit": emit, "token": token}

    await emit({
        "type": "hello",
        "mode": engine,
        "plan": (status or {}).get("subscriptionType") if engine == "claude" else None,
        "state": teacher.memory.snapshot(),
    })
    if note:
        await emit({"type": "error", "message": note})

    async def run(coro):
        async with busy:
            try:
                await coro
            except Exception as exc:  # beklenmeyen hata dersi düşürmesin
                await emit({"type": "error", "message": f"Beklenmeyen hata: {exc}"})
                await emit({"type": "turn_end"})

    tasks: set[asyncio.Task] = set()

    def spawn(coro):
        task = asyncio.create_task(run(coro))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    spawn(teacher.start(emit))
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "student" and str(msg.get("text", "")).strip():
                spawn(teacher.student_says(str(msg["text"])[:2000], msg.get("via", "text"), emit))
    except WebSocketDisconnect:
        pass
    finally:
        SESSIONS.pop(session_id, None)
        for task in tasks:
            task.cancel()
        if hasattr(teacher, "close"):
            teacher.close()


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
