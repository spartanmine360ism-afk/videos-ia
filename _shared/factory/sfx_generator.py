from __future__ import annotations

import argparse
import math
import random
import struct
import wave
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SFX_DIR = ROOT_DIR / "_shared" / "sfx"
SR = 44100

SPECS = {
    "whoosh.wav": {"dur": 0.35},
    "pop.wav": {"dur": 0.12},
    "click_ui.wav": {"dur": 0.05},
    "riser.wav": {"dur": 0.9},
    "bass_hit.wav": {"dur": 0.45},
    "drone_beep.wav": {"dur": 0.32},
    "error_buzz.wav": {"dur": 0.28},
    "success_chime.wav": {"dur": 0.45},
}


def _env(i: int, n: int, a: float = 0.005, d: float = 0.08) -> float:
    t = i / SR
    dur = n / SR
    if t < a:
        return t / max(a, 1e-6)
    if t > dur - d:
        return max(0.0, (dur - t) / max(d, 1e-6))
    return 1.0


def _write(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        for s in samples:
            s = max(-1.0, min(1.0, s))
            w.writeframes(struct.pack("<h", int(s * 32767)))


def _sine(freq: float, dur: float, amp: float = 0.6, a: float = 0.003, d: float = 0.06) -> list[float]:
    n = int(SR * dur)
    return [amp * math.sin(2 * math.pi * freq * i / SR) * _env(i, n, a, d) for i in range(n)]


def _noise(dur: float, amp: float = 0.3, seed: int = 1) -> list[float]:
    n = int(SR * dur)
    rnd = random.Random(seed)
    return [amp * (rnd.random() * 2 - 1) * _env(i, n, 0.001, 0.05) for i in range(n)]


def _sweep(f0: float, f1: float, dur: float, amp: float = 0.4) -> list[float]:
    n = int(SR * dur)
    out = []
    for i in range(n):
        t = i / SR
        k = t / max(dur, 1e-6)
        phase = 2 * math.pi * (f0 * dur / math.log(f1 / f0)) * ((f1 / f0) ** k - 1)
        out.append(amp * math.sin(phase) * _env(i, n, 0.001, 0.08))
    return out


def _mix(*tracks: list[float]) -> list[float]:
    n = max((len(t) for t in tracks), default=0)
    out = [0.0] * n
    for t in tracks:
        for i, s in enumerate(t):
            out[i] += s
    peak = max((abs(x) for x in out), default=1.0) or 1.0
    if peak > 1:
        out = [x / peak * 0.95 for x in out]
    return out


def _add(base: list[float], other: list[float], offset_s: float = 0.0) -> list[float]:
    off = int(offset_s * SR)
    n = max(len(base), len(other) + off)
    out = [0.0] * n
    for i, s in enumerate(base):
        out[i] += s
    for i, s in enumerate(other):
        j = i + off
        if j < n:
            out[j] += s
    return out


def synth(name: str) -> list[float]:
    if name == "whoosh.wav":
        return _mix(_sweep(300, 2200, 0.35, 0.35), _noise(0.35, 0.22, 2))
    if name == "pop.wav":
        return _mix(_sine(520, 0.08, 0.5), _sine(1040, 0.05, 0.15))
    if name == "click_ui.wav":
        return _mix(_sine(1800, 0.03, 0.35, 0.001, 0.02), _noise(0.02, 0.12, 3))
    if name == "riser.wav":
        return _mix(_sweep(220, 3600, 0.9, 0.28), _noise(0.9, 0.06, 4))
    if name == "bass_hit.wav":
        return _mix(_sine(60, 0.45, 0.8, 0.001, 0.2), _sine(90, 0.35, 0.25, 0.001, 0.18), _noise(0.08, 0.12, 5))
    if name == "drone_beep.wav":
        s = _add(_sine(880, 0.08, 0.32), _sine(1320, 0.08, 0.18), 0.1)
        return _add(s, _sine(880, 0.08, 0.28), 0.2)
    if name == "error_buzz.wav":
        return _mix(_sine(140, 0.28, 0.33), _sine(145, 0.28, 0.33), _noise(0.28, 0.04, 6))
    if name == "success_chime.wav":
        s = _add(_sine(880, 0.18, 0.26), _sine(1320, 0.22, 0.2), 0.06)
        return _add(s, _sine(1760, 0.28, 0.16), 0.12)
    raise ValueError(name)


def ensure_sfx(out_dir: Path = SFX_DIR, force: bool = False) -> list[Path]:
    created = []
    for name in SPECS:
        path = out_dir / name
        if path.exists() and not force:
            continue
        _write(path, synth(name))
        created.append(path)
    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera SFX WAV virales libres de derechos.")
    parser.add_argument("--out", default=str(SFX_DIR), help="Carpeta destino")
    parser.add_argument("--force", action="store_true", help="Regenera aunque existan")
    args = parser.parse_args(argv)
    created = ensure_sfx(Path(args.out), force=args.force)
    print(f"SFX listos en {args.out}. Generados: {len(created)}")
    for p in created:
        print(f" - {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
