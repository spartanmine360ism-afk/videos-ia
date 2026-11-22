from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SHARED = Path(__file__).resolve().parents[1]
FACTORY = SHARED / "factory"
if str(FACTORY) not in sys.path:
    sys.path.insert(0, str(FACTORY))

from .agentes import AGENTES, crear_agente_desde_spec
from .contratos import Contexto, ResultadoAgente
from .herramientas_externas import texto_para_prompt
from .memoria import CACHE, escribir_json, hash_canonico, perfil_hardware
from .telegram_decisiones import pedir_confirmacion, respaldar

try:
    import estilos_video
except Exception:
    estilos_video = None


def _json(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, separators=(",", ":"))


def construir_prompt(contexto: Contexto, resultados: list[ResultadoAgente]) -> str:
    por_id = {resultado.id: resultado.salida for resultado in resultados}
    avisos = [f"{r.id}: {aviso}" for r in resultados for aviso in r.avisos]
    partes = [
        "APORTE DE LOS 20 AGENTES LOCALES (usa este contrato para ejecutar; no lo expliques en pantalla):",
        f"Contexto compartido: estilo={_json(contexto.estilo)}; duración máxima={contexto.duracion_maxima_s:.1f} s; hardware={_json(contexto.hardware)}.",
        f"Guion y retención: {_json(por_id.get('A03', {}))}",
        f"Gancho elegido: {_json(por_id.get('A02', {}).get('elegida', {}))}",
        f"Locución: {_json(por_id.get('A04', {}))}",
        f"Referencia medida: {_json(por_id.get('A06', {}))}",
        f"Dirección de cámara: {_json(por_id.get('A09', {}))}",
        f"Edición y ritmo: {_json(por_id.get('A10', {}))}",
        f"Diseño y zonas seguras: {_json(por_id.get('A11', {}))}",
        f"Assets y B-roll: {_json(por_id.get('A08', {}))}",
        texto_para_prompt(),
        f"Cartoon/3D: {_json(por_id.get('A12', {}))}",
        f"QA previo: {_json(por_id.get('A14', {}))}",
        f"Metadata: {_json(por_id.get('A16', {}))}",
        f"Aprendizaje: {_json(por_id.get('A18', {}))}",
    ]
    if avisos:
        partes.append("Avisos de agentes: " + " | ".join(avisos[:12]))
    partes.append("Regla final: si la voz empuja el video sobre 60 s, recorta y re-renderiza antes de publicar.")
    return "\n".join(partes)


def ejecutar(
    idea: dict[str, Any],
    estilo: dict[str, Any] | str | None = None,
    fecha: str = "",
    artefactos: dict[str, Any] | None = None,
    notificar: bool = False,
    modo_prueba: bool = False,
) -> dict[str, Any]:
    if estilos_video is None:
        raise RuntimeError("No se pudo importar estilos_video")
    estilo_datos = estilos_video.obtener(estilo if isinstance(estilo, str) else (estilo or {}).get("id", ""))
    contexto = Contexto(
        idea=dict(idea),
        estilo=estilo_datos,
        fecha=fecha or datetime.now().date().isoformat(),
        artefactos=dict(artefactos or {}),
        hardware=perfil_hardware(),
        duracion_maxima_s=float(estilo_datos.get("duracion_maxima_s", 60.0)),
        idioma=str(idea.get("idioma", "es") or "es"),
        modo_prueba=modo_prueba,
    )
    clave = {
        "idea": contexto.idea,
        "estilo": estilo_datos["id"],
        "fecha": contexto.fecha,
        "duracion": contexto.duracion_maxima_s,
        "agentes": [agente.id for agente in AGENTES],
    }
    resultados: list[ResultadoAgente] = []
    for agente in AGENTES:
        try:
            respuesta = agente.run(contexto)
        except Exception as error:
            respuesta = ResultadoAgente(
                id=agente.id,
                nombre=agente.nombre,
                salida={},
                avisos=[],
                estado="error",
                error=f"{type(error).__name__}: {error}",
            )
        resultados.append(respuesta)
        contexto.artefactos[respuesta.id] = respuesta.salida

    confirmaciones: list[dict[str, Any]] = []
    arquitecto = next((r for r in resultados if r.id == "A19"), None)
    if arquitecto:
        for propuesta in arquitecto.salida.get("propuestas", []):
            if not notificar or modo_prueba:
                confirmaciones.append({"tipo": "crear_agente", "estado": "pendiente", "propuesta": propuesta})
                continue
            decision = pedir_confirmacion(
                f"El agente A19 propone crear {propuesta.get('clase', 'un agente')}: {propuesta.get('motivo', '')}",
                f"crear_{propuesta.get('clase', 'agente')}",
                modo_prueba=modo_prueba,
            )
            if decision.get("aprobado"):
                decision["archivo"] = crear_agente_desde_spec(propuesta)
            confirmaciones.append({"tipo": "crear_agente", **decision, "propuesta": propuesta})

    auditor = next((r for r in resultados if r.id == "A20"), None)
    if auditor:
        respaldo = ""
        for candidato in auditor.salida.get("candidatos", []):
            if not notificar or modo_prueba:
                confirmaciones.append({"tipo": "poda", "estado": "pendiente", "candidato": candidato})
                continue
            decision = pedir_confirmacion(
                f"El agente A20 propone podar {candidato.get('id', '?')}: {candidato.get('razon', '')}",
                f"poda_{candidato.get('id', 'agente')}",
                modo_prueba=modo_prueba,
            )
            if decision.get("aprobado"):
                if not respaldo:
                    respaldo = respaldar(Path(__file__).resolve().parent / "agentes.py")
                decision["respaldo"] = respaldo
                decision["accion"] = "respaldo_creado_sin_eliminacion"
            confirmaciones.append({"tipo": "poda", **decision, "candidato": candidato})

    payload = {
        "fecha": contexto.fecha,
        "estilo_id": estilo_datos["id"],
        "hardware": contexto.hardware,
        "resultados": [resultado.a_dict() for resultado in resultados],
        "confirmaciones": confirmaciones,
        "prompt_agentes": construir_prompt(contexto, resultados),
        "artefactos": contexto.artefactos,
    }
    ruta = CACHE / "ejecuciones" / (hash_canonico(clave) + ".json")
    escribir_json(ruta, payload)
    return {**payload, "ruta": str(ruta)}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Ejecuta los 20 agentes locales y devuelve su aporte estructurado.")
    parser.add_argument("--idea", default="", help="Tema o título de la idea")
    parser.add_argument("--archivo", default="", help="Ruta a un JSON de idea")
    parser.add_argument("--estilo", default="", help="ID de estilo opcional")
    parser.add_argument("--fecha", default="")
    parser.add_argument("--notificar", action="store_true")
    parser.add_argument("--prueba", action="store_true")
    parser.add_argument("--salida", default="", help="Archivo JSON donde guardar el resultado")
    args = parser.parse_args(argv)

    idea: dict[str, Any] = {"titulo": args.idea} if args.idea else {}
    if args.archivo:
        idea = json.loads(Path(args.archivo).read_text(encoding="utf-8"))
    if not idea:
        parser.error("Se requiere --idea o --archivo")

    resultado_final = ejecutar(
        idea,
        estilo=args.estilo or None,
        fecha=args.fecha,
        notificar=args.notificar,
        modo_prueba=args.prueba,
    )
    if args.salida:
        escribir_json(args.salida, resultado_final)
    print(json.dumps({
        "estilo_id": resultado_final["estilo_id"],
        "agentes": len(resultado_final["resultados"]),
        "errores": [r["id"] for r in resultado_final["resultados"] if r["estado"] == "error"],
        "prompt_agentes": resultado_final["prompt_agentes"],
        "ruta": resultado_final["ruta"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
