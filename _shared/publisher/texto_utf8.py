from __future__ import annotations
from pathlib import Path

import unicodedata
from typing import Any

REPAROS_UTF8: dict[str, str] = {
    "\u00c3\u00a1": "\u00e1",
    "\u00c3\u00a9": "\u00e9",
    "\u00c3\u00ad": "\u00ed",
    "\u00c3\u00b3": "\u00f3",
    "\u00c3\u00ba": "\u00fa",
    "\u00c3\u00bc": "\u00fc",
    "\u00c3\u00b1": "\u00f1",
    "\u00c3\u0081": "\u00c1",
    "\u00c3\u0089": "\u00c9",
    "\u00c3\u008d": "\u00cd",
    "\u00c3\u0093": "\u00d3",
    "\u00c3\u009a": "\u00da",
    "\u00c3\u0091": "\u00d1",
    "\u00c2\u00bf": "\u00bf",
    "\u00c2\u00a1": "\u00a1",
    "\u00e2\u20ac\u00a2": "\u2022",
    "\u00e2\u20ac\u201c": "-",
    "\u00e2\u20ac\u201d": "-",
    "\u00e2\u20ac\u2122": "'",
    "\u00e2\u20ac\u0153": '"',
    "\u00e2\u20ac\u009d": '"',
    "\u00e2\u20ac\u00a6": "...",
}


def limpiar_utf8(valor: Any) -> str:
    texto = unicodedata.normalize("NFC", str(valor or "")).replace("\ufeff", "")
    for _ in range(3):
        anterior = texto
        for roto, correcto in REPAROS_UTF8.items():
            texto = texto.replace(roto, correcto)
        if "\u00c3" in texto or "\u00c2" in texto:
            try:
                reparado = texto.encode("latin-1").decode("utf-8")
                if reparado:
                    texto = reparado
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        if texto == anterior:
            break
    return unicodedata.normalize("NFC", texto)


def limpiar_datos_utf8(valor: Any) -> Any:
    if isinstance(valor, str):
        return limpiar_utf8(valor)
    if isinstance(valor, dict):
        return {limpiar_utf8(k): limpiar_datos_utf8(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [limpiar_datos_utf8(item) for item in valor]
    return valor


def contiene_mojibake(valor: Any) -> bool:
    if isinstance(valor, str):
        return any(marca in valor for marca in ("\u00c3", "\u00c2", "\ufffd")) or "\u00e2\u20ac" in valor
    if isinstance(valor, dict):
        return any(contiene_mojibake(k) or contiene_mojibake(v) for k, v in valor.items())
    if isinstance(valor, list):
        return any(contiene_mojibake(item) for item in valor)
    return False


def leer_json_utf8(ruta: Any) -> Any:
    import json
    raw = Path(ruta).read_text(encoding="utf-8", errors="replace")
    return limpiar_datos_utf8(json.loads(raw))


def escribir_texto_utf8(ruta_archivo, contenido: str) -> None:
    destino = Path(ruta_archivo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(str(contenido), encoding="utf-8")
