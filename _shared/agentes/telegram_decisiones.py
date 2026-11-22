from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

FACTORY = Path(__file__).resolve().parents[1] / "factory"
if str(FACTORY) not in sys.path:
    sys.path.insert(0, str(FACTORY))

import notificador_telegram

RESPALDOS = Path(__file__).resolve().parent / "respaldos"


def enviar(mensaje: str) -> bool:
    try:
        notificador_telegram.enviar_mensaje(mensaje[:4000])
        return True
    except Exception:
        return False


def notificar_urgente(titulo: str, detalle: str, correccion: str) -> bool:
    texto = (
        "CORRECCIÓN URGENTE\n"
        f"{titulo}\n"
        f"Problema: {detalle[:900]}\n"
        f"Acción aplicada: {correccion[:900]}"
    )
    return enviar(texto)


def notificar_cambio_estructural(titulo: str, detalle: str) -> bool:
    return enviar("CAMBIO ESTRUCTURAL PROPUESTO\n" f"{titulo}\n{detalle[:1200]}")


def _credenciales() -> tuple[str, str]:
    try:
        return notificador_telegram.cargar_credenciales()
    except Exception:
        return "", ""


def _ultimo_update_id(token: str, session: Any) -> int:
    try:
        respuesta = session.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"limit": 1, "timeout": 1},
            timeout=5,
        )
        datos = respuesta.json() if respuesta.ok else {}
        resultados = datos.get("result") or []
        return int(resultados[-1].get("update_id", 0)) + 1 if resultados else 0
    except Exception:
        return 0


def pedir_confirmacion(
    pregunta: str,
    clave: str,
    modo_prueba: bool = False,
    timeout_s: int | None = None,
) -> dict[str, Any]:
    respuesta_base = {"clave": clave, "aprobado": False, "estado": "sin_respuesta", "respuesta": ""}
    if modo_prueba:
        return {**respuesta_base, "estado": "omitido_prueba"}
    if os.getenv("AURA_TELEGRAM_CONFIRMACIONES", "1") != "1":
        return {**respuesta_base, "estado": "desactivado"}
    token, chat_id = _credenciales()
    if not token or not chat_id:
        return {**respuesta_base, "estado": "sin_credenciales"}
    try:
        import requests
    except ImportError:
        return {**respuesta_base, "estado": "sin_requests"}
    limite = timeout_s or int(os.getenv("AURA_TELEGRAM_TIMEOUT_S", "600"))
    si = f"{clave}_SI"
    no = f"{clave}_NO"
    texto = (
        "DECISIÓN PENDIENTE\n"
        f"{pregunta[:2400]}\n\n"
        "Responde con los botones o escribe SI / NO. "
        "Si no hay respuesta, no se aplicará ningún cambio."
    )
    try:
        sesion = requests.Session()
        offset = _ultimo_update_id(token, sesion)
        mensaje = sesion.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": texto[:4000],
                "disable_web_page_preview": True,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "Sí", "callback_data": si}, {"text": "No", "callback_data": no}]
                    ]
                },
            },
            timeout=15,
        )
        if not mensaje.ok or not mensaje.json().get("ok"):
            return {**respuesta_base, "estado": "error_envio"}
        fin = time.time() + max(10, limite)
        while time.time() < fin:
            actualizaciones = sesion.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={
                    "offset": offset,
                    "timeout": 5,
                    "allowed_updates": json.dumps(["message", "callback_query"]),
                },
                timeout=10,
            )
            if not actualizaciones.ok:
                time.sleep(2)
                continue
            for actualizacion in actualizaciones.json().get("result", []):
                offset = max(offset, int(actualizacion.get("update_id", 0)) + 1)
                callback = actualizacion.get("callback_query") or {}
                if callback:
                    remitente = str((callback.get("from") or {}).get("id", ""))
                    dato = str(callback.get("data") or "")
                    if remitente == str(chat_id) and dato in {si, no}:
                        sesion.post(
                            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                            json={"callback_query_id": callback.get("id")},
                            timeout=10,
                        )
                        aprobado = dato == si
                        return {
                            "clave": clave,
                            "aprobado": aprobado,
                            "estado": "aprobado" if aprobado else "rechazado",
                            "respuesta": dato,
                        }
                mensaje_recibido = actualizacion.get("message") or {}
                remitente = str((mensaje_recibido.get("from") or {}).get("id", ""))
                contenido = str(mensaje_recibido.get("text") or "").strip().lower()
                if remitente != str(chat_id):
                    continue
                if contenido in {"si", "sí", "s", "yes", f"{clave} si", f"{clave} sí"}:
                    return {"clave": clave, "aprobado": True, "estado": "aprobado", "respuesta": contenido}
                if contenido in {"no", "n", f"{clave} no"}:
                    return {"clave": clave, "aprobado": False, "estado": "rechazado", "respuesta": contenido}
    except Exception as error:
        return {
            **respuesta_base,
            "estado": "error",
            "respuesta": f"{type(error).__name__}: {error}"[:500],
        }
    return respuesta_base


def respaldar(ruta: Path | str) -> str:
    origen = Path(ruta)
    destino = RESPALDOS / datetime.now().strftime("%Y%m%d_%H%M%S") / origen.name
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origen, destino)
    return str(destino)
