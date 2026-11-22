from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageStat

ROOT = Path(__file__).resolve().parents[2]
ANCHO, ALTO = 1080, 1920
ZONAS_PORTADA = {
    "etiqueta": (70, 270, 1010, 365),
    "titulo": (80, 390, 1000, 900),
    "secundario": (80, 930, 1000, 1130),
    "instagram_titulo": (110, 1210, 970, 1430),
    "instagram_pie": (360, 1510, 900, 1590),
}


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def _texto(valor: Any, limite: int = 80) -> str:
    txt = re.sub(r"\s+", " ", str(valor or "")).strip()
    return txt[:limite].strip()


def _resumen(texto: str, max_palabras: int = 5) -> str:
    palabras = [p for p in re.sub(r"[^\wÁÉÍÓÚÜÑáéíóúüñ#\- ]", " ", texto).split() if p]
    return " ".join(palabras[:max_palabras]).upper() or "MIRA ESTO"


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidatos = [
        ROOT / "_shared" / "fonts" / ("Montserrat-ExtraBold.ttf" if bold else "Montserrat-Bold.ttf"),
        ROOT / "_shared" / "fonts" / ("Outfit-Bold.ttf" if bold else "Outfit-Regular.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for c in candidatos:
        if c.exists():
            try:
                return ImageFont.truetype(str(c), size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _duracion(video: Path) -> float:
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    try:
        return max(1.0, float((p.stdout or "0").strip().splitlines()[0]))
    except Exception:
        return 10.0


def _extraer_frame(video: Path, segundo: float, salida: Path) -> bool:
    salida.parent.mkdir(parents=True, exist_ok=True)
    cmd = [_ffmpeg(), "-y", "-ss", f"{max(0, segundo):.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(salida)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.returncode == 0 and salida.exists() and salida.stat().st_size > 1024


def _puntaje_frame(img: Image.Image) -> float:
    g = img.convert("L").resize((270, 480))
    stat = ImageStat.Stat(g)
    mean = stat.mean[0]
    std = stat.stddev[0]
    # penaliza negro/blanco quemado y favorece contraste
    if mean < 18 or mean > 245:
        return -100 + std
    return std + min(mean, 220) / 20


def seleccionar_frames(video: Path) -> dict[str, Path]:
    dur = _duracion(video)
    candidatos = []
    for frac in [0.08, 0.15, 0.22, 0.30, 0.40, 0.50, 0.60, 0.75]:
        t = dur * frac
        out = video.parent / f".frame_{int(frac*100)}.jpg"
        if _extraer_frame(video, t, out):
            try:
                img = Image.open(out).convert("RGB")
                candidatos.append(( _puntaje_frame(img), frac, out, img.copy()))
                img.close()
            except Exception:
                pass
    candidatos.sort(key=lambda x: x[0], reverse=True)
    if not candidatos:
        # fallback
        out = video.parent / ".frame_fallback.jpg"
        _extraer_frame(video, min(1.0, dur * 0.2), out)
        img = Image.open(out).convert("RGB")
        candidatos = [(1, 0.2, out, img)]
    best = candidatos[0][3]
    alt = candidatos[1][3] if len(candidatos) > 1 else candidatos[0][3]
    clean = candidatos[min(2, len(candidatos)-1)][3]
    rutas = {}
    for nombre, im in {"base_best": best, "base_alt": alt, "base_clean": clean}.items():
        p = video.parent / f".{nombre}.jpg"
        im.resize((ANCHO, ALTO)).save(p, quality=92)
        rutas[nombre] = p
    # limpiar temporales
    for _,_,out,_ in candidatos:
        try:
            out.unlink(missing_ok=True)
        except Exception:
            pass
    return rutas


def _wrap(draw: ImageDraw.ImageDraw, texto: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
    palabras = texto.split()
    lineas, actual = [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        bbox = draw.textbbox((0,0), prueba, font=font)
        if bbox[2]-bbox[0] <= max_w or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas[:3]


def _panel(img: Image.Image, box: tuple[int,int,int,int], alpha: int = 150, acento: tuple[int,int,int] | None = None) -> None:
    capa = Image.new("RGBA", img.size, (0,0,0,0))
    dibujo = ImageDraw.Draw(capa)
    dibujo.rounded_rectangle(box, radius=24, fill=(6, 8, 14, alpha))
    if acento:
        dibujo.rounded_rectangle([box[0], box[1], box[0] + 10, box[3]], radius=5, fill=(*acento, 235))
    img.paste(Image.alpha_composite(img.convert("RGBA"), capa).convert("RGB"))


def _draw_text_block(img: Image.Image, texto: str, box: tuple[int,int,int,int], size=72, color=(255,255,255), stroke=6, align="center"):
    draw = ImageDraw.Draw(img)
    x1,y1,x2,y2 = box
    ancho = x2 - x1
    alto = y2 - y1
    font = _font(size, True)
    lineas = _wrap(draw, texto, font, ancho - stroke * 2)
    altura = sum(draw.textbbox((0,0), linea, font=font, stroke_width=stroke)[3] - draw.textbbox((0,0), linea, font=font, stroke_width=stroke)[1] + 8 for linea in lineas)
    tamano = size
    while altura > alto and tamano > 28:
        tamano -= 4
        font = _font(tamano, True)
        lineas = _wrap(draw, texto, font, ancho - stroke * 2)
        altura = sum(draw.textbbox((0,0), linea, font=font, stroke_width=stroke)[3] - draw.textbbox((0,0), linea, font=font, stroke_width=stroke)[1] + 8 for linea in lineas)
    y = y1 + max(0, (alto - altura) // 2)
    for linea in lineas:
        bbox = draw.textbbox((0,0), linea, font=font, stroke_width=stroke)
        w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        x = x1 + ((ancho-w)//2 if align=="center" else 0)
        draw.text((x,y), linea, font=font, fill=color, stroke_width=stroke, stroke_fill=(0,0,0))
        y += h + 8


def portada_youtube(base: Path, destino: Path, idea: dict[str, Any], metadata: dict[str, Any]):
    img = Image.open(base).convert("RGB").resize((ANCHO, ALTO))
    _panel(img, (60, 290, 1020, 900), alpha=145, acento=(255, 107, 0))
    gancho = _resumen(str((metadata.get("youtube") or {}).get("title") or idea.get("gancho_a") or idea.get("titulo") or ""), 5)
    _draw_text_block(img, gancho, (90, 380, 990, 880), size=84, stroke=8)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([90, 950, 470, 1030], radius=20, fill=(255, 107, 0))
    draw.text((120, 968), "SHORTS", font=_font(46, True), fill=(255, 255, 255))
    img.save(destino, quality=95)


def portada_tiktok(base: Path, destino: Path, idea: dict[str, Any], metadata: dict[str, Any]):
    img = Image.open(base).convert("RGB").resize((ANCHO, ALTO))
    _panel(img, (60, 260, 1020, 1160), alpha=135, acento=(255, 209, 102))
    etiqueta = idea.get("etiqueta") or (f"EPISODIO {idea.get('episodio')}/{idea.get('total_episodios')}" if idea.get("serie_id") else _resumen(str(idea.get("categoria") or idea.get("titulo") or "DRONES"), 2))
    etiqueta = _texto(etiqueta, 28)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([90, 285, 790, 365], radius=24, fill=(8, 10, 18))
    draw.text((120, 305), etiqueta.upper(), font=_font(38, True), fill=(255, 255, 255))
    tiktok = metadata.get("tiktok") if isinstance(metadata.get("tiktok"), dict) else {}
    titulo = _resumen(str(tiktok.get("description") or idea.get("titulo") or idea.get("gancho") or "DRONES"), 5)
    _draw_text_block(img, titulo, (90, 430, 990, 940), size=76, stroke=7)
    img.save(destino, quality=95)


def portada_instagram(base: Path, destino: Path, idea: dict[str, Any], metadata: dict[str, Any]):
    img = Image.open(base).convert("RGB").resize((ANCHO, ALTO))
    overlay = Image.new("RGBA", img.size, (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([60, 315, 1020, 1605], outline=(255,255,255,210), width=8)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    _panel(img, (80, 1180, 1000, 1490), alpha=165, acento=(139, 92, 246))
    titulo = _texto(str(idea.get("titulo") or (metadata.get("instagram") or {}).get("title") or "Aura Drones"), 70)
    _draw_text_block(img, titulo.upper(), ZONAS_PORTADA["instagram_titulo"], size=58, stroke=4)
    draw = ImageDraw.Draw(img)
    draw.text((400, 1530), "@aldo_auradrones", font=_font(34, True), fill=(240, 240, 240))
    img.save(destino, quality=95)


def portada_facebook(base: Path, destino: Path, idea: dict[str, Any], metadata: dict[str, Any]):
    img = Image.open(base).convert("RGB").resize((ANCHO, ALTO))
    _panel(img, (50, 240, 1030, 900), alpha=145, acento=(59, 130, 246))
    gancho_b = _resumen(str(idea.get("gancho_b") or (metadata.get("facebook") or {}).get("title") or idea.get("titulo") or ""), 6)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([90, 285, 750, 365], radius=22, fill=(24, 119, 242))
    draw.text((120, 305), "MIRA EL RESULTADO", font=_font(38, True), fill=(255,255,255))
    _draw_text_block(img, gancho_b, (90, 420, 990, 870), size=76, stroke=7)
    img.save(destino, quality=95)



def _realce_impacto(img):
    from PIL import ImageEnhance, ImageDraw
    img = img.convert("RGB")
    img = ImageEnhance.Contrast(img).enhance(1.25)
    img = ImageEnhance.Color(img).enhance(1.22)
    img = ImageEnhance.Sharpness(img).enhance(1.35)
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for y in range(h):
        # Viñeta sutil arriba y abajo para destacar texto central
        dist = abs((y / max(1, h - 1)) - 0.45)
        alpha = int(min(135, max(0, (dist - 0.15) * 280)))
        if alpha > 0:
            odraw.line([(0, y), (w, y)], fill=(8, 10, 18, alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _portada_fallback(renders: Path, frames: dict[str, Path] | None = None) -> Path:
    destino = renders / "portada.jpg"
    candidato: Path | None = None
    for clave in ("base_best", "base_clean", "base_alt"):
        ruta = (frames or {}).get(clave)
        if ruta and ruta.is_file() and ruta.stat().st_size > 1024:
            candidato = ruta
            break
    if candidato is None and destino.is_file() and destino.stat().st_size > 1024:
        return destino
    if candidato is not None:
        shutil.copy2(candidato, destino)
    else:
        Image.new("RGB", (ANCHO, ALTO), (8, 10, 18)).save(destino, quality=90)
    return destino


def generar_portadas_redes(proyecto: Path, video: Path, idea: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> dict[str, str]:
    idea = idea or {}
    metadata = metadata or {}
    renders = proyecto / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    frames: dict[str, Path] = {}
    try:
        frames = seleccionar_frames(video)
        mejor = frames.get("base_best")
        if mejor and mejor.is_file():
            with Image.open(mejor) as imagen:
                realzada = _realce_impacto(imagen.convert("RGB"))
            realzada.save(mejor, quality=95)
    except Exception:
        frames = {}
    fallback = _portada_fallback(renders, frames)
    rutas = {
        "youtube": renders / "portada_youtube.jpg",
        "tiktok": renders / "portada_tiktok.jpg",
        "instagram": renders / "portada_instagram.jpg",
        "facebook": renders / "portada_facebook.jpg",
    }
    tareas = (
        ("youtube", portada_youtube, "base_best"),
        ("tiktok", portada_tiktok, "base_clean"),
        ("instagram", portada_instagram, "base_best"),
        ("facebook", portada_facebook, "base_alt"),
    )
    fallbacks: list[str] = []
    for plataforma, funcion, clave_base in tareas:
        try:
            base = frames.get(clave_base) or fallback
            funcion(base, rutas[plataforma], idea, metadata)
            if not rutas[plataforma].is_file() or rutas[plataforma].stat().st_size <= 1024:
                raise RuntimeError("portada vacía")
        except Exception:
            shutil.copy2(fallback, rutas[plataforma])
            fallbacks.append(plataforma)
    shutil.copy2(rutas["youtube"], renders / "portada.jpg")
    meta_path = renders / "metadata.json"
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data["portadas"] = {k: f"renders/{v.name}" for k, v in rutas.items()}
        data["portada"] = "renders/portada.jpg"
        if fallbacks:
            data["portadas_fallback"] = fallbacks
        meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for ruta in frames.values():
        try:
            ruta.unlink(missing_ok=True)
        except Exception:
            pass
    return {k: str(v) for k, v in rutas.items()}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("proyecto")
    ap.add_argument("video")
    args = ap.parse_args()
    proyecto = Path(args.proyecto)
    video = Path(args.video)
    meta = {}
    mp = proyecto / "renders" / "metadata.json"
    if mp.exists():
        meta = json.loads(mp.read_text(encoding="utf-8"))
    print(json.dumps(generar_portadas_redes(proyecto, video, {}, meta), ensure_ascii=False, indent=2))
