from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo

    ZONA = ZoneInfo("America/Mexico_City")
except Exception:
    from datetime import timedelta as _timedelta
    from datetime import timezone as _timezone

    ZONA = _timezone(_timedelta(hours=-6), "America/Mexico_City")

PUBLISHER_DIR = Path(__file__).resolve().parent
QUEUE_PATH = PUBLISHER_DIR / "schedule_queue.json"
ZONA_NOMBRE = "America/Mexico_City"
MAX_POR_DIA = 3
MARGEN_MINUTOS = 20
HORARIOS: dict[str, list[str]] = {
    "youtube": ["09:00", "13:30", "19:30"],
    "tiktok": ["08:30", "13:00", "20:00"],
    "instagram": ["09:00", "13:30", "19:00"],
    "facebook": ["08:30", "13:00", "19:30"],
}


def ahora_local() -> datetime:
    return datetime.now(ZONA)


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZONA)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_scheduled_at(value: Any) -> datetime | None:
    if not value:
        return None
    texto = str(value).strip().replace("Z", "+00:00")
    try:
        fecha = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=ZONA)
    return fecha.astimezone(timezone.utc)


def _leer_cola() -> dict[str, Any]:
    base = {"timezone": ZONA_NOMBRE, "max_por_plataforma_por_dia": MAX_POR_DIA, "tareas": []}
    if not QUEUE_PATH.exists():
        return base

    try:
        crudo = QUEUE_PATH.read_text(encoding="utf-8", errors="replace").strip()
        if not crudo:
            return base
        data = json.loads(crudo)
    except (OSError, json.JSONDecodeError) as error:
        try:
            corrupto = QUEUE_PATH.with_name(f"{QUEUE_PATH.stem}.corrupt-{uuid.uuid4().hex[:8]}.json")
            QUEUE_PATH.replace(corrupto)
        except OSError:
            pass
        return base
    if not isinstance(data, dict):
        data = {}
    data.setdefault("timezone", ZONA_NOMBRE)
    data.setdefault("max_por_plataforma_por_dia", MAX_POR_DIA)
    tareas = data.get("tareas")
    if not isinstance(tareas, list):
        tareas = []
    data["tareas"] = tareas
    return data


def cargar_cola() -> dict[str, Any]:
    return _leer_cola()


def guardar_cola(data: dict[str, Any]) -> None:
    data.setdefault("timezone", ZONA_NOMBRE)
    data.setdefault("max_por_plataforma_por_dia", MAX_POR_DIA)
    if not isinstance(data.get("tareas"), list):
        data["tareas"] = []

    temporal = QUEUE_PATH.with_name(QUEUE_PATH.name + ".tmp")
    backup = QUEUE_PATH.with_name(QUEUE_PATH.stem + ".bak.json")
    contenido = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    # validar JSON UTF-8 antes de reemplazar
    json.loads(contenido)
    temporal.write_bytes(contenido.encode("utf-8"))
    if QUEUE_PATH.exists():
        try:
            backup.write_bytes(QUEUE_PATH.read_bytes())
        except Exception:
            pass
    temporal.replace(QUEUE_PATH)


def listar_tareas() -> list[dict[str, Any]]:
    return [tarea for tarea in _leer_cola()["tareas"] if isinstance(tarea, dict)]


def encolar_tarea(tarea: dict[str, Any]) -> dict[str, Any]:
    data = _leer_cola()
    tarea = dict(tarea)
    tarea.setdefault("id", f"{tarea.get('plataforma', 'tarea')}-{uuid.uuid4().hex[:10]}")
    tarea.setdefault("creado_en", iso_utc(ahora_utc()))
    tarea.setdefault("estado", "pending")
    data["tareas"].append(tarea)
    guardar_cola(data)
    return tarea


def asignar_siguiente_slot(plataforma: str) -> dict[str, Any]:
    plataforma = plataforma.strip().lower()
    if plataforma not in HORARIOS:
        raise ValueError(f"scheduler_manager: plataforma desconocida '{plataforma}'")

    tareas = listar_tareas()
    ahora = ahora_local()
    limite = ahora + timedelta(minutes=MARGEN_MINUTOS)
    dia = ahora.date()

    while True:
        asignados = [
            tarea
            for tarea in tareas
            if str(tarea.get("plataforma", "")).lower() == plataforma
            and str(tarea.get("estado", "")) not in {"cancelled", "failed"}
            and (fecha := parse_scheduled_at(tarea.get("scheduled_at"))) is not None
            and fecha.astimezone(ZONA).date() == dia
        ]

        if len(asignados) < MAX_POR_DIA:
            ocupados = {
                parse_scheduled_at(tarea.get("scheduled_at")).astimezone(ZONA).replace(second=0, microsecond=0)
                for tarea in asignados
                if parse_scheduled_at(tarea.get("scheduled_at")) is not None
            }

            for hora in HORARIOS[plataforma]:
                slot = datetime.combine(dia, datetime.strptime(hora, "%H:%M").time(), tzinfo=ZONA)
                if slot < limite:
                    continue
                if slot.replace(second=0, microsecond=0) in ocupados:
                    continue
                return {
                    "plataforma": plataforma,
                    "fecha_local": dia.isoformat(),
                    "slot": hora,
                    "scheduled_at_local": slot.isoformat(),
                    "scheduled_at": iso_utc(slot),
                    "scheduled_unix": int(slot.timestamp()),
                }

        dia += timedelta(days=1)
