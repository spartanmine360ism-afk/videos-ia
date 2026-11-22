from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

import texto_utf8

PUBLISHER_DIR = Path(__file__).resolve().parent
API_BASE = "https://open.tiktokapis.com/v2"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = f"{API_BASE}/oauth/token/"
REDIRECT_URI = "http://localhost:8080/callback"
SCOPE = "user.info.basic,video.upload"
MAX_CHUNK_SIZE = 64 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 10 * 1024 * 1024


def load_config() -> tuple[str, str, str]:
    load_dotenv(PUBLISHER_DIR / ".env", override=False)
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "").strip()
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "").strip()
    access_token = os.getenv("TIKTOK_ACCESS_TOKEN", "").strip()
    if not client_key or not client_secret:
        raise RuntimeError("TikTok: faltan TIKTOK_CLIENT_KEY o TIKTOK_CLIENT_SECRET en .env")
    return client_key, client_secret, access_token


def credentials_configured() -> bool:
    try:
        client_key, client_secret, _ = load_config()
        return bool(client_key and client_secret)
    except RuntimeError:
        return False


def access_token_configurado() -> bool:
    try:
        _, _, access_token = load_config()
        return bool(access_token)
    except RuntimeError:
        return False


def save_env_value(key: str, value: str) -> None:
    env_path = PUBLISHER_DIR / ".env"
    if env_path.exists():
        lines = texto_utf8.leer_texto_utf8(env_path).splitlines()
    else:
        example_path = PUBLISHER_DIR / ".env.example"
        lines = texto_utf8.leer_texto_utf8(example_path).splitlines() if example_path.exists() else []

    prefix = f"{key}="
    replaced = False
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{prefix}{value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{prefix}{value}")

    temporary = PUBLISHER_DIR / ".env.tmp"
    texto_utf8.escribir_texto_utf8(temporary, "\n".join(lines) + "\n")
    temporary.replace(env_path)
    os.environ[key] = value


class CallbackServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler]) -> None:
        super().__init__(address, handler)
        self.params: dict[str, list[str]] = {}
        self.ready = threading.Event()


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_error(404)
            return

        server = self.server
        if not isinstance(server, CallbackServer):
            self.send_error(500)
            return

        server.params = parse_qs(parsed.query, keep_blank_values=True)
        page = b"<html><body><h1>TikTok autorizado</h1><p>Puedes cerrar esta ventana.</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)
        server.ready.set()

    def log_message(self, format: str, *args: Any) -> None:
        return


def wait_for_code(auth_url: str, state: str) -> str:
    server = CallbackServer(("127.0.0.1", 8080), CallbackHandler)
    server.timeout = 5
    deadline = time.monotonic() + 300

    try:
        webbrowser.open(auth_url)
        while not server.ready.is_set() and time.monotonic() < deadline:
            server.handle_request()

        if not server.ready.is_set():
            raise RuntimeError("TikTok: timeout esperando http://localhost:8080/callback")

        params = server.params
        if params.get("state", [""])[0] != state:
            raise RuntimeError("TikTok: el state del callback no coincide")
        if params.get("error", [""])[0]:
            raise RuntimeError(f"TikTok OAuth: {params.get('error_description', params['error'])[0]}")
        code = params.get("code", [""])[0]
        if not code:
            raise RuntimeError("TikTok: el callback no devolvió code")
        return code
    finally:
        server.server_close()


def exchange_code(code: str, verifier: str, client_key: str, client_secret: str) -> str:
    response = requests.post(
        TOKEN_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cache-Control": "no-cache",
        },
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
        timeout=90,
    )
    response.encoding = "utf-8"
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    token_data = payload.get("data", payload) if isinstance(payload, dict) else {}
    if not isinstance(token_data, dict):
        token_data = {}

    error = payload.get("error") if isinstance(payload, dict) else None
    description = payload.get("error_description") if isinstance(payload, dict) else None
    description = description or token_data.get("error_description")
    if isinstance(error, dict):
        description = error.get("message") or error.get("error_description") or description
    elif isinstance(error, str):
        description = description or error

    if not response.ok or error or not token_data.get("access_token"):
        raise RuntimeError(f"TikTok OAuth: {description or response.text[:300]}")
    return str(token_data["access_token"])


def authorize(client_key: str, client_secret: str) -> str:
    verifier = secrets.token_urlsafe(64)
    challenge = hashlib.sha256(verifier.encode("ascii")).hexdigest()
    state = secrets.token_urlsafe(24)
    params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": SCOPE,
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTH_URL}?{urlencode(params)}"
    print("TikTok: TIKTOK_ACCESS_TOKEN vacío; abriendo autorización OAuth en el navegador.")
    code = wait_for_code(auth_url, state)
    return exchange_code(code, verifier, client_key, client_secret)


def ensure_access_token() -> str:
    client_key, client_secret, access_token = load_config()
    if access_token:
        return access_token

    token = authorize(client_key, client_secret)
    save_env_value("TIKTOK_ACCESS_TOKEN", token)
    print("TikTok: access_token guardado en _shared/publisher/.env")
    return token


def headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }


def request_api(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    response = requests.request(method, url, timeout=90, **kwargs)
    response.encoding = "utf-8"
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        failed = error.get("code") not in (None, 0, "0", "ok")
        message = error.get("message", response.text[:300])
    else:
        failed = bool(error)
        message = str(error) if error else response.text[:300]

    if not response.ok or failed:
        raise RuntimeError(f"TikTok API {response.status_code}: {message}")
    return payload if isinstance(payload, dict) else {}


def upload_plan(size: int) -> tuple[int, int]:
    if size <= 0:
        raise RuntimeError("TikTok: el MP4 está vacío")
    if size <= MAX_CHUNK_SIZE:
        return size, 1
    return UPLOAD_CHUNK_SIZE, size // UPLOAD_CHUNK_SIZE


def normalize_upload_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def publicar(
    video_path: Path,
    config: dict[str, Any],
    caption: str,
    auto_schedule: bool = False,
    scheduled_at: str | None = None,
) -> dict[str, Any]:
    _ = auto_schedule, scheduled_at, config, caption
    token = ensure_access_token()
    size = video_path.stat().st_size
    chunk_size, total_chunks = upload_plan(size)

    payload: dict[str, Any] = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunks,
        },
    }

    init_payload = request_api(
        "POST",
        f"{API_BASE}/post/publish/inbox/video/init/",
        headers=headers(token),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )

    data = init_payload.get("data", {})
    upload_url = normalize_upload_url(str(data.get("upload_url", "")))
    publish_id = str(data.get("publish_id", ""))
    if not upload_url or not publish_id:
        raise RuntimeError("TikTok: la API no devolvió upload_url o publish_id")

    with video_path.open("rb") as handle:
        for index in range(total_chunks):
            read_size = chunk_size if index < total_chunks - 1 else size - chunk_size * (total_chunks - 1)
            chunk = handle.read(read_size)
            start = chunk_size * index
            end = start + len(chunk) - 1
            upload = requests.put(
                upload_url,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Range": f"bytes {start}-{end}/{size}",
                },
                data=chunk,
                timeout=180,
            )
            if upload.status_code not in (200, 201, 206):
                raise RuntimeError(f"TikTok upload HTTP {upload.status_code}: {upload.text[:300]}")

    return {
        "plataforma": "tiktok",
        "id": publish_id,
        "url": "",
        "estado": "subido_borrador_inbox",
    }
