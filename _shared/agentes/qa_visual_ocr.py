import json
import subprocess
from pathlib import Path


def inspeccionar_video_ffprobe(mp4_path: Path) -> dict:
    if not mp4_path.exists():
        return {"ok": False, "error": "Archivo MP4 no encontrado"}
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,width,height",
        "-of", "json", str(mp4_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if res.returncode != 0:
        return {"ok": False, "error": res.stderr.strip() or "ffprobe falló"}
    info = json.loads(res.stdout or "{}")
    duracion = float(info.get("format", {}).get("duration", 0.0) or 0.0)
    streams = info.get("streams", [])
    tiene_video = any(s.get("codec_type") == "video" for s in streams)
    tiene_audio = any(s.get("codec_type") == "audio" for s in streams)
    return {
        "ok": tiene_video and 0 < duracion <= 60.0,
        "duracion_seg": round(duracion, 2),
        "dentro_limite_60s": duracion <= 60.0,
        "tiene_video": tiene_video,
        "tiene_audio": tiene_audio,
    }


def extraer_frames_clave(mp4_path: Path, out_dir: Path, num_frames: int = 6) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    info = inspeccionar_video_ffprobe(mp4_path)
    dur = max(1.0, min(60.0, float(info.get("duracion_seg") or 10.0)))
    paso = max(0.5, dur / max(1, num_frames))
    patron = str(out_dir / "frame_%02d.png")
    cmd = [
        "ffmpeg", "-y", "-i", str(mp4_path),
        "-vf", f"fps=1/{paso:.2f},scale=720:-1",
        "-frames:v", str(num_frames), patron
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return sorted(out_dir.glob("frame_*.png"))


def auditar_texto_ocr_frames(frames: list[Path]) -> dict:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return {
            "ocr_disponible": False,
            "aviso": "Instala rapidocr-onnxruntime para OCR local sin tesseract",
            "posibles_solapes": [],
        }

    ocr = RapidOCR()
    posibles_solapes = []
    lecturas = []

    for frame in frames:
        out, _ = ocr(str(frame))
        cajas = out or []
        textos_frame = []
        for item in cajas:
            if len(item) >= 2:
                box, texto = item[0], str(item[1]).strip()
                if texto:
                    textos_frame.append({"texto": texto, "box": box})
        for i in range(len(textos_frame)):
            for j in range(i + 1, len(textos_frame)):
                y1_a = min(p[1] for p in textos_frame[i]["box"])
                y2_a = max(p[1] for p in textos_frame[i]["box"])
                y1_b = min(p[1] for p in textos_frame[j]["box"])
                y2_b = max(p[1] for p in textos_frame[j]["box"])
                if max(y1_a, y1_b) < min(y2_a, y2_b):
                    x1_a = min(p[0] for p in textos_frame[i]["box"])
                    x2_a = max(p[0] for p in textos_frame[i]["box"])
                    x1_b = min(p[0] for p in textos_frame[j]["box"])
                    x2_b = max(p[0] for p in textos_frame[j]["box"])
                    if max(x1_a, x1_b) < min(x2_a, x2_b):
                        posibles_solapes.append({
                            "frame": frame.name,
                            "a": textos_frame[i]["texto"],
                            "b": textos_frame[j]["texto"],
                        })
        lecturas.append({"frame": frame.name, "textos": [t["texto"] for t in textos_frame]})

    return {
        "ocr_disponible": True,
        "frames_analizados": len(frames),
        "posibles_solapes": posibles_solapes,
        "lecturas": lecturas,
    }
