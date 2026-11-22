import hashlib
import json
import math
import re
import subprocess
from pathlib import Path


def localizar_audio_proyecto(proyecto_dir: Path) -> Path | None:
    prioridades = [
        proyecto_dir / "assets" / "audio" / "mezcla_preview.wav",
        proyecto_dir / "assets" / "audio" / "voz_norm.wav",
        proyecto_dir / "assets" / "audio" / "voz.mp3",
        proyecto_dir / "assets" / "audio" / "musica_duck.wav",
        proyecto_dir / "mezcla_preview.wav",
        proyecto_dir / "voz_norm.wav",
        proyecto_dir / "voz.mp3",
    ]
    for p in prioridades:
        if p.exists() and p.stat().st_size > 1024:
            return p

    for ext in ("*.wav", "*.mp3", "*.m4a", "*.aac", "*.ogg"):
        for p in sorted(proyecto_dir.rglob(ext)):
            if any(part in {"_cache_segmentos", "_qa_frames", "sfx"} for part in p.parts):
                continue
            if p.stat().st_size > 1024:
                return p
    return None


def detectar_estilo_tema(proyecto_dir: Path) -> dict:
    """
    Adapta el color y estilo al tema del video y a las referencias disponibles
    en lugar de imponer un fondo oscuro fijo.
    """
    estilo = {
        "fondo_hex": "#141a24",
        "tema": "hud-diagramas-adaptativo",
        "referencias_encontradas": [],
    }

    dirs_ref = [
        proyecto_dir / "referencias",
        Path(r"C:\Users\aldo_\Downloads\referencias"),
    ]
    for d in dirs_ref:
        if d.exists() and d.is_dir():
            for f in sorted(d.iterdir()):
                if f.is_file() and f.suffix.lower() in {".gif", ".png", ".jpg", ".jpeg", ".webp", ".mp4", ".json", ".md"}:
                    estilo["referencias_encontradas"].append(f.name)

    texto_contexto = " ".join([
        proyecto_dir.name.lower(),
        " ".join(estilo["referencias_encontradas"]).lower(),
    ])

    for rel in ["config.json", "meta.json", "hyperframes.json", "guion.md", "guion.txt", "index.html"]:
        p = proyecto_dir / rel
        if p.exists():
            try:
                contenido = p.read_text(encoding="utf-8", errors="ignore")
                texto_contexto += " " + contenido[:4000].lower()
                m_hex = re.search(r'["\']?(?:bg|background|fondo|color_fondo)["\']?\s*[:=]\s*["\']?#([0-9a-fA-F]{6})["\']?', contenido)
                if m_hex:
                    estilo["fondo_hex"] = f"#{m_hex.group(1)}"
            except Exception:
                pass

    if "claro" in texto_contexto or "light" in texto_contexto or "blanco" in texto_contexto:
        estilo["fondo_hex"] = "#f4f6f9"
        estilo["tema"] = "claro-tecnico"
    elif "diagrama" in texto_contexto or "hud" in texto_contexto or "fpv" in texto_contexto or "dji" in texto_contexto:
        estilo["tema"] = "hud-diagrama-dinamico"

    return estilo


def calcular_hash_proyecto(proyecto_dir: Path, duracion_objetivo: float) -> str:
    h = hashlib.sha256()
    h.update(f"{duracion_objetivo:.2f}".encode("utf-8"))
    estilo = detectar_estilo_tema(proyecto_dir)
    h.update(json.dumps(estilo, sort_keys=True).encode("utf-8"))
    for rel in ["index.html", "config.json", "hyperframes.json", "meta.json", "guion.md", "guion.txt"]:
        p = proyecto_dir / rel
        if p.exists():
            h.update(rel.encode("utf-8"))
            h.update(p.read_bytes())
    audio = localizar_audio_proyecto(proyecto_dir)
    if audio:
        h.update(audio.name.encode("utf-8"))
        h.update(str(audio.stat().st_size).encode("utf-8"))
    return h.hexdigest()[:16]


def _render_tramo_con_audio(
    seg_file: Path,
    inicio_seg: float,
    dur_tramo: float,
    fps: int,
    fondo_hex: str,
    audio_path: Path | None,
    timeout_por_segmento: int,
) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={fondo_hex}:s=1080x1920:r={fps}:d={dur_tramo:.2f}",
    ]
    if audio_path is not None:
        cmd.extend([
            "-ss", f"{inicio_seg:.2f}",
            "-t", f"{dur_tramo:.2f}",
            "-i", str(audio_path.resolve()),
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-filter_complex", f"[1:a][2:a]concat=n=2:v=0:a=1,atrim=0:{dur_tramo:.2f},asetpts=PTS-STARTPTS[aout]",
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        ])
    else:
        cmd.extend([
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
        ])
    cmd.append(str(seg_file.resolve()))
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_por_segmento)
    if res.returncode != 0 or not seg_file.exists():
        raise RuntimeError(f"Fallo al renderizar tramo: {res.stderr[-250:]}")


def renderizar_segmentado_seguro(
    proyecto_dir: Path,
    mp4_salida: Path,
    duracion_seg: float,
    fps: int = 24,
    segmento_seg: float = 10.0,
    timeout_por_segmento: int = 240,
) -> tuple[bool, str]:
    duracion_seg = max(1.0, min(60.0, float(duracion_seg)))
    mp4_salida.parent.mkdir(parents=True, exist_ok=True)
    respaldo_temporal = mp4_salida.with_suffix(".prev_backup.mp4")
    if mp4_salida.exists():
        mp4_salida.replace(respaldo_temporal)

    estilo = detectar_estilo_tema(proyecto_dir)
    audio_path = localizar_audio_proyecto(proyecto_dir)
    hash_id = calcular_hash_proyecto(proyecto_dir, duracion_seg)
    cache_dir = proyecto_dir / "_cache_segmentos" / hash_id
    cache_dir.mkdir(parents=True, exist_ok=True)

    num_seg = max(1, math.ceil(duracion_seg / segmento_seg))
    segmentos_mp4 = []

    try:
        for idx in range(num_seg):
            inicio = idx * segmento_seg
            dur_tramo = min(segmento_seg, duracion_seg - inicio)
            if dur_tramo <= 0.1:
                continue
            seg_file = cache_dir / f"seg_{idx:02d}.mp4"
            if not (seg_file.exists() and seg_file.stat().st_size > 1024):
                _render_tramo_con_audio(
                    seg_file=seg_file,
                    inicio_seg=inicio,
                    dur_tramo=dur_tramo,
                    fps=fps,
                    fondo_hex=estilo["fondo_hex"],
                    audio_path=audio_path,
                    timeout_por_segmento=timeout_por_segmento,
                )
            segmentos_mp4.append(seg_file)

        if not segmentos_mp4:
            raise RuntimeError("No se generaron segmentos MP4 válidos")

        lista_txt = cache_dir / "concat.txt"
        lineas_concat = [f"file '{p.resolve().as_posix()}'" for p in segmentos_mp4]
        lista_txt.write_text("\n".join(lineas_concat) + "\n", encoding="utf-8")

        cmd_concat = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(lista_txt.resolve()), "-t", f"{duracion_seg:.2f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
        ]
        if audio_path is not None:
            cmd_concat.extend(["-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2"])
        cmd_concat.append(str(mp4_salida.resolve()))

        res_c = subprocess.run(cmd_concat, capture_output=True, text=True, timeout=timeout_por_segmento)
        if res_c.returncode != 0 or not mp4_salida.exists():
            raise RuntimeError(f"Fallo al unir segmentos: {res_c.stderr[-250:]}")

        if respaldo_temporal.exists():
            respaldo_temporal.unlink(missing_ok=True)

        audio_estado = f"audio={audio_path.name}" if audio_path else "sin audio detectado"
        return True, f"Render segmentado OK ({duracion_seg:.1f}s, {len(segmentos_mp4)} tramos, tema={estilo['tema']}, {audio_estado})"

    except Exception as exc:
        if respaldo_temporal.exists() and not mp4_salida.exists():
            respaldo_temporal.replace(mp4_salida)
        return False, f"Fallback a MP4 previo tras error: {exc}"
