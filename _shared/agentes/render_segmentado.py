import hashlib
import math
import subprocess
from pathlib import Path


def calcular_hash_proyecto(proyecto_dir: Path, duracion_objetivo: float) -> str:
    h = hashlib.sha256()
    h.update(f"{duracion_objetivo:.2f}".encode("utf-8"))
    for rel in ["index.html", "config.json", "hyperframes.json", "meta.json", "guion.md", "guion.txt"]:
        p = proyecto_dir / rel
        if p.exists():
            h.update(rel.encode("utf-8"))
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


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
            segmentos_mp4.append(seg_file)
            if seg_file.exists() and seg_file.stat().st_size > 1024:
                continue

            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=#090d14:s=1080x1920:r={fps}:d={dur_tramo:.2f}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
                str(seg_file),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_por_segmento)
            if res.returncode != 0 or not seg_file.exists():
                raise RuntimeError(f"Fallo en segmento {idx}: {res.stderr[-200:]}")

        lista_txt = cache_dir / "concat.txt"
        lista_txt.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in segmentos_mp4),
            encoding="utf-8",
        )
        cmd_concat = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(lista_txt), "-t", f"{duracion_seg:.2f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
            str(mp4_salida),
        ]
        res_c = subprocess.run(cmd_concat, capture_output=True, text=True, timeout=timeout_por_segmento)
        if res_c.returncode != 0 or not mp4_salida.exists():
            raise RuntimeError(f"Fallo al unir segmentos: {res_c.stderr[-200:]}")

        if respaldo_temporal.exists():
            respaldo_temporal.unlink(missing_ok=True)
        return True, f"Render segmentado OK ({duracion_seg:.1f}s, {len(segmentos_mp4)} tramos)"

    except Exception as exc:
        if respaldo_temporal.exists() and not mp4_salida.exists():
            respaldo_temporal.replace(mp4_salida)
        return False, f"Fallback a MP4 previo tras error: {exc}"
