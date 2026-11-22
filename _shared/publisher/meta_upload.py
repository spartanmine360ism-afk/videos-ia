from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

import requests
from dotenv import load_dotenv

PUBLISHER_DIR = Path(__file__).resolve().parent
GRAPH_VERSION = "v19.0"
TUNNEL_PATTERN = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


def load_config() -> tuple[str, str, str]:
    load_dotenv(PUBLISHER_DIR / ".env", override=False)
    token = os.getenv("META_ACCESS_TOKEN", "").strip()
    page_id = os.getenv("FB_PAGE_ID", "").strip()
    instagram_id = os.getenv("IG_USER_ID", "").strip()
    return token, page_id, instagram_id


def parse_scheduled_at(value: str) -> datetime:
    fecha = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(timezone.utc)


def request_api(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    response = requests.request(method, url, timeout=90, **kwargs)
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    error = payload.get("error") if isinstance(payload, dict) else None
    if not response.ok or error:
        message = error.get("message", response.text[:300]) if isinstance(error, dict) else response.text[:300]
        raise RuntimeError(f"Meta API {response.status_code}: {message}")
    return payload if isinstance(payload, dict) else {}


def video_url_available() -> bool:
    load_dotenv(PUBLISHER_DIR / ".env", override=False)
    return bool(shutil.which("cloudflared") or os.getenv("META_VIDEO_URL", "").strip())


@contextmanager
def public_video_url(video_path: Path) -> Iterator[str]:
    load_dotenv(PUBLISHER_DIR / ".env", override=False)
    static_url = os.getenv("META_VIDEO_URL", "").strip()
    if static_url:
        yield static_url
        return

    executable = shutil.which("cloudflared")
    if not executable:
        raise RuntimeError("Instagram: cloudflared no disponible y no hay META_VIDEO_URL")

    class SingleVideoHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            expected = "/" + quote(video_path.name)
            if self.path.split("?", 1)[0] not in (expected, "/" + video_path.name):
                self.send_error(404)
                return

            size = video_path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            with video_path.open("rb") as handle:
                shutil.copyfileobj(handle, self.wfile)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), SingleVideoHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    port = server.server_address[1]
    process: subprocess.Popen[str] | None = None
    found: dict[str, str] = {}
    ready = threading.Event()

    try:
        process = subprocess.Popen(
            [executable, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        def read_output() -> None:
            if process.stdout is None:
                return
            for line in process.stdout:
                match = TUNNEL_PATTERN.search(line)
                if match and not ready.is_set():
                    found["url"] = match.group(0)
                    ready.set()

        threading.Thread(target=read_output, daemon=True).start()
        if not ready.wait(timeout=30):
            raise RuntimeError("Instagram: cloudflared no devolvió una URL pública en 30 s")

        yield f"{found['url']}/{quote(video_path.name)}"
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        server.shutdown()
        server.server_close()


def wait_container(container_id: str, token: str) -> None:
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{container_id}"
    for _ in range(60):
        payload = request_api("GET", url, params={"fields": "status_code,status", "access_token": token})
        status = str(payload.get("status_code", ""))
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"Instagram: contenedor {container_id} falló: {payload.get('status', '')}")
        time.sleep(2)
    raise RuntimeError(f"Instagram: timeout esperando el contenedor {container_id}")


def publicar_facebook(
    video_path: Path,
    config: dict[str, Any],
    caption: str,
    auto_schedule: bool = False,
    scheduled_at: str | None = None,
) -> dict[str, Any]:
    _ = config
    token, page_id, _ = load_config()
    if not token or not page_id:
        raise RuntimeError("Facebook: faltan META_ACCESS_TOKEN o FB_PAGE_ID en .env")

    programado = bool(auto_schedule and scheduled_at)
    data: dict[str, Any] = {
        "access_token": token,
        "description": caption[:2200],
        "published": "true",
    }
    if programado:
        fecha = parse_scheduled_at(str(scheduled_at))
        if fecha <= datetime.now(timezone.utc) + timedelta(minutes=10):
            raise RuntimeError("Facebook: scheduled_publish_time debe ser al menos 10 minutos en el futuro")
        data["published"] = "false"
        data["scheduled_publish_time"] = str(int(fecha.timestamp()))

    url = f"https://graph-video.facebook.com/{GRAPH_VERSION}/{page_id}/videos"
    with video_path.open("rb") as handle:
        payload = request_api("POST", url, data=data, files={"file": (video_path.name, handle, "video/mp4")})

    video_id = str(payload.get("id", ""))
    return {
        "plataforma": "facebook",
        "id": video_id,
        "url": f"https://www.facebook.com/{page_id}/videos/{video_id}" if video_id else "",
        "estado": "programado" if programado else "publicado",
        "scheduled_at": str(scheduled_at) if programado else "",
    }


def publicar_instagram(
    video_path: Path,
    config: dict[str, Any],
    caption: str,
    auto_schedule: bool = False,
    scheduled_at: str | None = None,
) -> dict[str, Any]:
    _ = config, auto_schedule, scheduled_at
    token, _, instagram_id = load_config()
    if not token or not instagram_id:
        raise RuntimeError("Instagram: faltan META_ACCESS_TOKEN o IG_USER_ID en .env")

    with public_video_url(video_path) as video_url:
        container = request_api(
            "POST",
            f"https://graph.facebook.com/{GRAPH_VERSION}/{instagram_id}/media",
            data={
                "access_token": token,
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption[:2200],
                "share_to_feed": "true",
            },
        )
        container_id = str(container.get("id", ""))
        if not container_id:
            raise RuntimeError("Instagram: Graph API no devolvió creation_id")

        wait_container(container_id, token)
        published = request_api(
            "POST",
            f"https://graph.facebook.com/{GRAPH_VERSION}/{instagram_id}/media_publish",
            data={"access_token": token, "creation_id": container_id},
        )
        media_id = str(published.get("id", ""))

    return {
        "plataforma": "instagram",
        "id": media_id,
        "url": f"https://www.instagram.com/reel/{media_id}/" if media_id else "",
        "estado": "publicado",
    }
