from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from agentes.memoria import (
    CACHE,
    asegurar_paquete,
    buscar_binario,
    cache_video,
    clave_archivos,
    hash_canonico,
    perfil_hardware,
)

ARCHIVOS_CLAVE = [
    "config.json",
    "index.html",
    "package.json",
    "hyperframes.json",
    "assets/styles/estilos.css",
    "assets/fonts/fonts.css",
    "assets/scripts/three.module.js",
    "assets/scripts/three.core.js",
    "assets/scripts/d3.min.js",
    "assets/scripts/flubber.min.js",
    "assets/audio/voz.mp3",
    "assets/audio/voz.json",
]

class _ServidorSilencioso(SimpleHTTPRequestHandler):
    def log_message(self, formato: str, *args: Any) -> None:
        return


SEEK_JS = """
(t) => {
  const gsap = window.gsap;
  if (gsap && gsap.globalTimeline) gsap.globalTimeline.pause();
  const posibles = [window.timeline, window.tl, window.__timeline, window.auraTimeline];
  posibles.forEach((linea) => {
    if (!linea || typeof linea.pause !== "function") return;
    linea.pause();
    if (typeof linea.seek === "function") linea.seek(t);
  });
  if (typeof window.auraSeek === "function") window.auraSeek(t);
  document.dispatchEvent(new CustomEvent("aura:seek", { detail: t }));
}
"""


def _composiciones(proyecto: Path) -> list[str]:
    carpeta = proyecto / "compositions"
    if not carpeta.is_dir():
        return []
    return sorted(str(ruta.relative_to(proyecto)).replace("\\", "/") for ruta in carpeta.glob("*.html"))


def clave_render(proyecto: Path, motor: str) -> dict[str, Any]:
    archivos = [nombre for nombre in ARCHIVOS_CLAVE if (proyecto / nombre).exists()]
    archivos.extend(_composiciones(proyecto))
    return {
        "version": 1,
        "motor": motor,
        "proyecto": proyecto.name,
        "archivos": clave_archivos(proyecto, archivos),
    }


def duracion_objetivo(proyecto: Path, defecto: float = 58.0) -> float:
    config = proyecto / "config.json"
    try:
        datos = json.loads(config.read_text(encoding="utf-8"))
        valor = datos.get("duracion_objetiva_s") or datos.get("duracion_objetivo_s")
        if valor:
            return min(60.0, float(valor))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    valores = []
    for ruta in [proyecto / "index.html", *sorted((proyecto / "compositions").glob("*.html"))]:
        if not ruta.is_file():
            continue
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        valores.extend(float(valor) for valor in re.findall(r'data-duration=["\']([0-9.]+)["\']', texto))
    return min(60.0, max(valores)) if valores else defecto


def duracion_video(video: Path) -> float:
    ffprobe = buscar_binario("ffprobe")
    if not ffprobe:
        return 0.0
    try:
        proceso = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float(proceso.stdout.strip() or 0)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def _ultimo_mp4(proyecto: Path) -> Path | None:
    renders = proyecto / "renders"
    if not renders.is_dir():
        return None
    videos = [ruta for ruta in renders.glob("*.mp4") if ruta.is_file()]
    return max(videos, key=lambda ruta: ruta.stat().st_mtime) if videos else None


def _copiar_salida(proyecto: Path, origen: Path, destino: Path) -> Path:
    renders = proyecto / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    final = renders / "render_engine.mp4"
    if origen.resolve() != final.resolve():
        shutil.copy2(origen, final)
    if origen.resolve() != destino.resolve() and destino.resolve() != final.resolve():
        shutil.copy2(origen, destino)
    metadata_path = renders / "metadata.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(metadata, dict):
                metadata["video"] = final.name
                metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return final


def _render_hyperframes(proyecto: Path, destino: Path, perfil: dict[str, Any]) -> Path:
    antes = _ultimo_mp4(proyecto)
    npm = "npm.cmd" if os.name == "nt" else "npm"
    comando = [npm, "run", "render"]
    entorno = dict(os.environ)
    entorno["HYPERFRAMES_WORKERS"] = str(perfil.get("workers", 2))
    proceso = subprocess.run(
        comando,
        cwd=str(proyecto),
        capture_output=True,
        text=True,
        timeout=int(os.getenv("AURA_RENDER_TIMEOUT_S", "1200")),
        env=entorno,
    )
    if proceso.returncode != 0:
        raise RuntimeError(f"npm run render falló: {(proceso.stderr or proceso.stdout)[-1200:]}")
    generado = _ultimo_mp4(proyecto)
    if generado is None or (antes is not None and generado.samefile(antes)):
        raise RuntimeError("npm run render no produjo un MP4 nuevo")
    return _copiar_salida(proyecto, generado, destino)


def _playwright_disponible() -> bool:
    paquete = asegurar_paquete("playwright")
    if paquete.get("estado") not in {"ya_disponible", "instalado", "instalado_con_aviso"}:
        return False
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False
    try:
        with sync_playwright() as motor:
            navegador = motor.chromium.launch(headless=True, args=["--no-sandbox"])
            navegador.close()
        return True
    except Exception:
        if os.getenv("AURA_PLAYWRIGHT_BROWSER_AUTO_INSTALL", "1") != "1":
            return False
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                text=True,
                timeout=900,
            )
            with sync_playwright() as motor:
                navegador = motor.chromium.launch(headless=True, args=["--no-sandbox"])
                navegador.close()
            return True
        except Exception:
            return False


def _capturar_frames(proyecto: Path, duracion: float, fps: int, clave: dict[str, Any]) -> tuple[Path, int]:
    destino = CACHE / "frames" / (hash_canonico(clave) + "-playwright")
    cantidad = max(1, int(duracion * fps))
    existentes = sorted(destino.glob("frame-*.png")) if destino.is_dir() else []
    if len(existentes) >= cantidad:
        return destino, cantidad
    if destino.exists():
        shutil.rmtree(destino, ignore_errors=True)
    destino.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    index = proyecto / "index.html"
    manejador = partial(_ServidorSilencioso, directory=str(proyecto))
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), manejador)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    url = f"http://127.0.0.1:{servidor.server_address[1]}/{index.name}"
    try:
        with sync_playwright() as motor:
            navegador = motor.chromium.launch(headless=True, args=["--no-sandbox", "--use-gl=swiftshader"])
            pagina = navegador.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
            pagina.goto(url, wait_until="load", timeout=60000)
            pagina.wait_for_function("window.__AURA_LISTO !== false", timeout=30000)
            pagina.wait_for_timeout(400)
            for indice in range(cantidad):
                pagina.evaluate(SEEK_JS, indice / fps)
                pagina.screenshot(path=str(destino / f"frame-{indice:06d}.png"))
            navegador.close()
    finally:
        servidor.shutdown()
        servidor.server_close()
        hilo.join(timeout=5)
    return destino, cantidad


def _render_playwright(proyecto: Path, destino: Path, perfil: dict[str, Any]) -> Path:
    if not _playwright_disponible():
        raise RuntimeError("Playwright o Chromium no disponibles")
    ffmpeg = str(perfil.get("ffmpeg") or buscar_binario("ffmpeg"))
    if not ffmpeg:
        raise RuntimeError("ffmpeg no disponible")
    duracion = duracion_objetivo(proyecto)
    fps = 30
    frame_key = clave_render(proyecto, "playwright-frames")
    frame_key["duracion"] = duracion
    frame_key["fps"] = fps
    frames, cantidad = _capturar_frames(proyecto, duracion, fps, frame_key)
    audios = sorted((proyecto / "assets" / "audio").glob("*.mp3")) if (proyecto / "assets" / "audio").is_dir() else []
    audio = next((ruta for ruta in audios if ruta.name.lower().startswith("voz")), audios[0] if audios else None)
    comando = [
        ffmpeg,
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frames / "frame-%06d.png"),
    ]
    if audio:
        comando.extend(["-i", str(audio)])
    comando.extend(
        [
            "-frames:v",
            str(cantidad),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-movflags",
            "+faststart",
        ]
    )
    if audio:
        comando.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
    else:
        comando.append("-an")
    comando.append(str(destino))
    proceso = subprocess.run(comando, capture_output=True, text=True, timeout=int(os.getenv("AURA_RENDER_TIMEOUT_S", "1200")))
    if proceso.returncode != 0:
        raise RuntimeError(f"FFmpeg falló: {(proceso.stderr or '')[-1200:]}")
    return _copiar_salida(proyecto, destino, destino)


def render(
    proyecto: Path | str,
    motor: str = "",
    usar_cache: bool = True,
    notificar: bool = False,
) -> dict[str, Any]:
    proyecto = Path(proyecto).resolve()
    if not proyecto.is_dir():
        raise FileNotFoundError(f"No existe el proyecto {proyecto}")
    motor = motor or os.getenv("AURA_RENDER_MOTOR", "auto")
    perfil = perfil_hardware()
    clave = clave_render(proyecto, motor)
    clave["duracion_objetivo_s"] = duracion_objetivo(proyecto)

    def productor(destino: Path) -> Path:
        errores = []
        if motor in {"auto", "playwright"}:
            try:
                return _render_playwright(proyecto, destino, perfil)
            except Exception as error:
                errores.append(f"playwright: {type(error).__name__}: {error}")
                if motor == "playwright":
                    raise
        try:
            return _render_hyperframes(proyecto, destino, perfil)
        except Exception as error:
            errores.append(f"hyperframes: {type(error).__name__}: {error}")
        raise RuntimeError(" | ".join(errores))

    if usar_cache:
        generado, desde_cache = cache_video("renders", clave, productor)
    else:
        destino = CACHE / "renders" / (hash_canonico(clave) + ".mp4")
        destino.parent.mkdir(parents=True, exist_ok=True)
        generado, desde_cache = productor(destino), False

    final = _copiar_salida(proyecto, generado, generado)
    duracion = duracion_video(final)
    aviso = ""
    if duracion > 60.0 and notificar:
        aviso = f"Duración {duracion:.1f} s supera 60 s"
    return {
        "ok": True,
        "motor": motor,
        "desde_cache": desde_cache,
        "video": str(final),
        "duracion_s": duracion,
        "perfil": perfil,
        "aviso": aviso,
    }


def recortar_duracion(
    proyecto: Path | str,
    duracion_real: float,
    objetivo: float = 59.2,
    notificar: bool = False,
) -> dict[str, Any]:
    proyecto = Path(proyecto).resolve()
    if duracion_real <= 60.0:
        return {"aplicado": False, "motivo": "La duración ya está dentro del límite"}
    factor = max(0.5, objetivo / duracion_real)
    rutas = [proyecto / "index.html", *sorted((proyecto / "compositions").glob("*.html"))]
    modificados = []

    def escalar(coincidencia: re.Match[str]) -> str:
        valor = float(coincidencia.group(2)) * factor
        return f'{coincidencia.group(1)}{valor:.3f}{coincidencia.group(3)}'

    for ruta in rutas:
        if not ruta.is_file():
            continue
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        nuevo = re.sub(r'(data-(?:duration|start)=["\'])([0-9.]+)(["\'])', escalar, texto)
        if nuevo != texto:
            ruta.write_text(nuevo, encoding="utf-8")
            modificados.append(str(ruta.name))
    config_path = proyecto / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8", errors="replace"))
        config["duracion_maxima_s"] = 60.0
        config["duracion_objetiva_s"] = objetivo
        config["ultimo_recorte"] = {
            "duracion_real_s": duracion_real,
            "factor": round(factor, 4),
            "archivos": modificados,
        }
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    if notificar:
        try:
            from agentes.telegram_decisiones import notificar_urgente

            notificar_urgente(
                "Video mayor a 60 segundos",
                f"Duración detectada: {duracion_real:.1f} s",
                f"Reescalado {len(modificados)} composiciones con factor {factor:.4f} y re-render inmediato.",
            )
        except Exception:
            pass
    return {
        "aplicado": True,
        "duracion_real_s": duracion_real,
        "objetivo_s": objetivo,
        "factor": round(factor, 4),
        "modificados": modificados,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Renderiza un proyecto con Playwright+FFmpeg o Hyperframes y caché local.")
    parser.add_argument("proyecto")
    parser.add_argument("--motor", default="", choices=["", "auto", "playwright", "hyperframes"])
    parser.add_argument("--sin-cache", action="store_true")
    parser.add_argument("--recortar", type=float, default=0.0, help="Si el video dura más de 60 s, reescala duraciones antes de renderizar")
    parser.add_argument("--notificar", action="store_true")
    args = parser.parse_args(argv)

    proyecto = Path(args.proyecto).resolve()
    if args.recortar > 0:
        recorte = recortar_duracion(proyecto, args.recortar, notificar=args.notificar)
        print(json.dumps({"recorte": recorte}, ensure_ascii=False, indent=2))
    resultado = render(proyecto, motor=args.motor, usar_cache=not args.sin_cache, notificar=args.notificar)
    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
    return 0 if resultado.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
