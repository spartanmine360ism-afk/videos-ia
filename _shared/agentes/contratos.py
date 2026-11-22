from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ResultadoAgente:
    id: str
    nombre: str
    salida: dict[str, Any] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    estado: str = "ok"
    error: str = ""

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Contexto:
    idea: dict[str, Any]
    estilo: dict[str, Any]
    fecha: str = ""
    artefactos: dict[str, Any] = field(default_factory=dict)
    hardware: dict[str, Any] = field(default_factory=dict)
    duracion_maxima_s: float = 60.0
    idioma: str = "es"
    modo_prueba: bool = False

    def texto(self, clave: str, defecto: str = "") -> str:
        valor = self.idea.get(clave, "")
        return str(valor).strip() if valor is not None else defecto

    def a_dict(self) -> dict[str, Any]:
        return {
            "idea": self.idea,
            "estilo": self.estilo,
            "fecha": self.fecha,
            "artefactos": self.artefactos,
            "hardware": self.hardware,
            "duracion_maxima_s": self.duracion_maxima_s,
            "idioma": self.idioma,
            "modo_prueba": self.modo_prueba,
        }


def resultado(
    id_agente: str,
    nombre: str,
    salida: dict[str, Any] | None = None,
    avisos: list[str] | None = None,
    estado: str = "ok",
    error: str = "",
) -> ResultadoAgente:
    return ResultadoAgente(
        id=id_agente,
        nombre=nombre,
        salida=salida or {},
        avisos=avisos or [],
        estado=estado,
        error=error,
    )
