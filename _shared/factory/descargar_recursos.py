from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
FACTORY_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = FACTORY_DIR / "recursos_descargables.json"
CACHE_DIR = ROOT_DIR / "_shared" / "cache" / "recursos"
RESUMEN_RELATIVO = Path("renders") / "recursos.json"

ICONOS: dict[str, str] = {
    "hud.svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><circle cx="32" cy="32" r="26" fill="none" stroke="currentColor" stroke-width="3"/><path d="M32 6v12M32 46v12M6 32h12M46 32h12" stroke="currentColor" stroke-width="3"/><circle cx="32" cy="32" r="5" fill="currentColor"/></svg>',
    "ficha.svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="10" y="6" width="44" height="52" rx="6" fill="none" stroke="currentColor" stroke-width="3"/><circle cx="32" cy="24" r="9" fill="none" stroke="currentColor" stroke-width="3"/><path d="M18 46h28M18 52h20" stroke="currentColor" stroke-width="3"/></svg>',
    "reloj.svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><circle cx="32" cy="34" r="24" fill="none" stroke="currentColor" stroke-width="3"/><path d="M25 6h14M32 34l11-8M32 34v13" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>',
    "flecha.svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><path d="M8 32h42M36 16l16 16-16 16" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "drone.svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="24" y="26" width="16" height="12" rx="3" fill="none" stroke="currentColor" stroke-width="3"/><circle cx="14" cy="18" r="8" fill="none" stroke="currentColor" stroke-width="3"/><circle cx="50" cy="18" r="8" fill="none" stroke="currentColor" stroke-width="3"/><circle cx="14" cy="46" r="8" fill="none" stroke="currentColor" stroke-width="3"/><circle cx="50" cy="46" r="8" fill="none" stroke="currentColor" stroke-width="3"/><path d="M20 22l8 8M44 22l-8 8M20 42l8-6M44 42l-8-6" stroke="currentColor" stroke-width="3"/></svg>',
    "check.svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><path d="M14 34l12 12 24-28" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
}

PAQUETES: dict[str, str] = {
    "edge_tts": "edge-tts",
    "requests": "requests",
}


class SinRedirecciones(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def cargar_manifest() -> dict[str, Any]:
    try:
        datos = json.loads(MANIFEST_PATH.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {"recursos": [], "hosts_permitidos": [], "limite_bytes": 12_000_000}
    if not isinstance(datos, dict):
        return {"recursos": [], "hosts_permitidos": [], "limite_bytes": 12_000_000}
    if not isinstance(datos.get("recursos"), list):
        datos["recursos"] = []
    return datos


def ruta_dentro(base: Path, relativo: str) -> Path:
    base_resuelta = base.resolve()
    destino = (base_resuelta / relativo).resolve()
    if destino != base_resuelta and base_resuelta not in destino.parents:
        raise ValueError(f"Ruta fuera del proyecto: {relativo}")
    return destino


def hash_archivo(ruta: Path) -> str:
    digesto = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(65536), b""):
            digesto.update(bloque)
    return digesto.hexdigest()


def ya_listo(destino: Path) -> bool:
    return destino.is_file() and destino.stat().st_size > 0


def copiar_fuente(fuente: Path, destino: Path) -> str:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + ".tmp")
    shutil.copy2(fuente, temporal)
    temporal.replace(destino)
    return hash_archivo(destino)


def descargar(url: str, destino: Path, hosts: list[str], limite: int) -> str:
    analizado = urllib.parse.urlparse(url)
    if analizado.scheme != "https" or not analizado.netloc:
        raise ValueError("La URL debe ser HTTPS")
    if hosts and analizado.hostname not in hosts:
        raise ValueError(f"Host no permitido: {analizado.hostname}")
    extension = Path(analizado.path).suffix.lower()
    if extension not in {".woff", ".woff2", ".ttf", ".otf", ".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp3", ".wav", ".mp4", ".webm", ".json"}:
        raise ValueError(f"Extensión no permitida: {extension or 'sin extensión'}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    clave = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    en_cache = CACHE_DIR / f"{clave}{extension}"
    if not ya_listo(en_cache):
        opener = urllib.request.build_opener(SinRedirecciones)
        with opener.open(url, timeout=15) as respuesta:
            datos = respuesta.read(limite + 1)
        if len(datos) > limite:
            raise ValueError("El archivo supera el límite de tamaño")
        if not datos:
            raise ValueError("Descarga vacía")
        temporal = en_cache.with_suffix(en_cache.suffix + ".tmp")
        temporal.write_bytes(datos)
        temporal.replace(en_cache)
    return copiar_fuente(en_cache, destino)


def asegurar_iconos(proyecto: Path, resumen: list[dict[str, Any]]) -> None:
    for nombre, contenido in ICONOS.items():
        destino = ruta_dentro(proyecto, f"assets/icons/{nombre}")
        if ya_listo(destino):
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido, encoding="utf-8")
        resumen.append({"dest": f"assets/icons/{nombre}", "estado": "fallback_local", "bytes": destino.stat().st_size})


def asegurar_paquetes(resumen: list[dict[str, Any]]) -> None:
    for modulo, paquete in PAQUETES.items():
        if importlib.util.find_spec(modulo) is not None:
            continue
        try:
            terminado = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--timeout", "15", paquete],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=90,
            )
            estado = "instalado" if terminado.returncode == 0 else "fallback_pendiente"
        except (OSError, subprocess.SubprocessError):
            estado = "fallback_pendiente"
        resumen.append({"paquete": paquete, "estado": estado})


def asegurar(proyecto: Path, estilo: Any = "", *, solo_cache: bool = False, instalar_paquetes: bool = True) -> dict[str, Any]:
    proyecto = Path(proyecto).resolve()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = cargar_manifest()
    hosts = [str(host).casefold() for host in manifest.get("hosts_permitidos", []) if isinstance(host, str)]
    try:
        limite = int(manifest.get("limite_bytes") or 12_000_000)
    except (TypeError, ValueError):
        limite = 12_000_000

    resumen: list[dict[str, Any]] = []
    for entrada in manifest["recursos"]:
        if not isinstance(entrada, dict):
            continue
        relativo = str(entrada.get("dest") or "").strip()
        if not relativo or Path(relativo).is_absolute() or ".." in Path(relativo).parts:
            continue
        destino = ruta_dentro(proyecto, relativo)
        if ya_listo(destino):
            resumen.append({"dest": relativo, "estado": "ya_existente"})
            continue
        if not solo_cache:
            destino.parent.mkdir(parents=True, exist_ok=True)

        estado = "sin_recurso"
        digesto = ""
        for fuente_relativa in entrada.get("fuentes", []):
            fuente = ROOT_DIR / str(fuente_relativa)
            if not fuente.is_file():
                continue
            if solo_cache:
                destino_cache = CACHE_DIR / relativo.replace("/", "__")
                digesto = copiar_fuente(fuente, destino_cache)
                estado = "cache_local"
            else:
                digesto = copiar_fuente(fuente, destino)
                estado = "copiado"
            break
        else:
            url = str(entrada.get("url") or "").strip()
            if url:
                try:
                    if solo_cache:
                        destino_url = CACHE_DIR / relativo.replace("/", "__")
                        digesto = descargar(url, destino_url, hosts, limite)
                        estado = "cache_descargado"
                    else:
                        digesto = descargar(url, destino, hosts, limite)
                        estado = "descargado"
                except (OSError, ValueError, urllib.error.URLError) as error:
                    estado = f"fallback: {type(error).__name__}"
        entrada_resumen: dict[str, Any] = {"dest": relativo, "estado": estado}
        if digesto:
            entrada_resumen["sha256"] = digesto
        resumen.append(entrada_resumen)

    if not solo_cache:
        asegurar_iconos(proyecto, resumen)
    if instalar_paquetes:
        asegurar_paquetes(resumen)

    style_id = ""
    if estilo:
        try:
            import estilos_video

            style_id = str(estilos_video.obtener(estilo if isinstance(estilo, str) else estilo.get("id")).get("id") or "")
        except Exception:
            style_id = ""

    resultado = {
        "proyecto": str(proyecto),
        "estilo_id": style_id,
        "cache": str(CACHE_DIR),
        "recursos": resumen,
        "fallos": [
            entrada
            for entrada in resumen
            if str(entrada.get("estado", "")).startswith("sin_recurso")
            or str(entrada.get("estado", "")).startswith("fallback:")
            or entrada.get("estado") == "fallback_pendiente"
        ],
    }
    if not solo_cache:
        ruta_resumen = ruta_dentro(proyecto, str(RESUMEN_RELATIVO))
        ruta_resumen.parent.mkdir(parents=True, exist_ok=True)
        ruta_resumen.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Asegura fuentes, scripts, SFX, iconos y paquetes en caché local.")
    parser.add_argument("proyecto", help="Carpeta del proyecto")
    parser.add_argument("--estilo", default="", help="ID del estilo visual asignado")
    parser.add_argument("--solo-cache", action="store_true", help="Solo llena la caché global, sin tocar el proyecto")
    parser.add_argument("--sin-paquetes", action="store_true", help="No intenta instalar paquetes Python faltantes")
    args = parser.parse_args(argv)

    try:
        resultado = asegurar(
            Path(args.proyecto),
            args.estilo,
            solo_cache=args.solo_cache,
            instalar_paquetes=not args.sin_paquetes,
        )
    except (OSError, ValueError) as error:
        print(json.dumps({"ok": False, "detalle": f"{type(error).__name__}: {error}"}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, **resultado}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
