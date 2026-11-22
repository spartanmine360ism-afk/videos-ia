from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parents[2]
FACTORY_DIR = Path(__file__).resolve().parent
PUBLISHER_DIR = ROOT_DIR / "_shared" / "publisher"
PLAN_PATH = FACTORY_DIR / "plan_semanal.json"

if str(PUBLISHER_DIR) not in sys.path:
    sys.path.insert(0, str(PUBLISHER_DIR))
if str(FACTORY_DIR) not in sys.path:
    sys.path.insert(0, str(FACTORY_DIR))

import dedup_manager
import notificador_telegram
import scheduler_manager
import trend_hunter

FRANJAS = ["mañana", "tarde", "noche"]
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
PLANTILLAS_AURA = [
    {"tipo": "FPV", "categoria": "FPV Avata", "titulo": "Vuelo FPV Avata: error oculto en {tema}", "gancho": "Esto arruina tu vuelo FPV con Avata antes de despegar.", "enfoque": "Vuelo FPV Avata, control, seguridad y sensación inmersiva con ajuste práctico."},
    {"tipo": "DJI", "categoria": "DJI Mini 3 cinemática", "titulo": "Toma cinemática DJI Mini 3: {tema}", "gancho": "Esta toma con DJI Mini 3 hace ver tu video como cine.", "enfoque": "Toma cinemática DJI Mini 3: movimiento, luz y encuadre limpio."},
    {"tipo": "TIP", "categoria": "Tip técnico", "titulo": "Tip técnico de drones: {tema}", "gancho": "El ajuste técnico que casi nadie revisa en su dron.", "enfoque": "Tip técnico accionable con checklist, riesgo y solución."},
    {"tipo": "BTS", "categoria": "Detrás de cámaras", "titulo": "Detrás de cámaras Aura Drones: {tema}", "gancho": "Así se ve realmente una grabación con drones antes del resultado final.", "enfoque": "Detrás de cámaras: preparación, crew, seguridad y toma final."},
    {"tipo": "CROSS-NICHE", "categoria": "Cross-niche bienes raíces", "titulo": "Drones + bienes raíces: {tema}", "gancho": "Este video con dron puede vender una propiedad más rápido.", "enfoque": "Unir drones con bienes raíces para atraer público nuevo y clientes."},
    {"tipo": "CROSS-NICHE", "categoria": "Cross-niche autos/deportes", "titulo": "Drones + autos/deportes: {tema}", "gancho": "La toma con dron que hace ver épico un auto o deporte.", "enfoque": "Unir drones con autos/deportes para alcance cross-niche."},
    {"tipo": "CROSS-NICHE", "categoria": "Cross-niche turismo/arquitectura", "titulo": "Drones + turismo/arquitectura: {tema}", "gancho": "Esta toma aérea cambia cómo se ve un destino o edificio.", "enfoque": "Unir drones con turismo/arquitectura para atraer audiencia nueva."},
    {"tipo": "CROSS-NICHE", "categoria": "Cross-niche eventos", "titulo": "Drones + eventos: {tema}", "gancho": "El ángulo aéreo que todo evento quiere en sus redes.", "enfoque": "Unir drones con eventos para mostrar valor visual y comercial."},
    {"tipo": "COMERCIAL", "categoria": "Comercial Aura Drones", "titulo": "Servicio Aura Drones: {tema}", "gancho": "Si necesitas grabar esto, un dron te ahorra tiempo y dinero.", "enfoque": "Slot comercial suave: problema, resultado visual y CTA a cotización Aura Drones.", "es_comercial": True, "cta_tipo": "cotizacion"},
]


def cargar_plan(path: Path = PLAN_PATH) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        if not raw:
            return None
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get("dias"), list):
            return None
        return data
    except Exception:
        return None


def guardar_plan(plan: dict[str, Any], path: Path = PLAN_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _fecha_inicio(valor: str | None) -> date:
    if valor:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    return (scheduler_manager.ahora_local() + timedelta(days=1)).date()


def _candidatos_reales() -> list[dict[str, Any]]:
    try:
        ideas = trend_hunter.elegir()  # usa recolectar+filtros internos
        return ideas if isinstance(ideas, list) else []
    except Exception:
        try:
            candidatos, _ = trend_hunter.recolectar(ttl_segundos=900)
            return [trend_hunter.construir_idea(c.get("categoria","Tip práctico DJI/FPV"), c) for c in candidatos[:30]]
        except Exception:
            return []


def _norm_idea(idea: dict[str, Any]) -> str:
    return dedup_manager.normalizar(f"{idea.get('titulo','')} {idea.get('gancho','')} {idea.get('enfoque','')}")


def _es_repetida(idea: dict[str, Any], usadas: list[str]) -> bool:
    titulo = str(idea.get("titulo") or "")
    resumen = f"{idea.get('gancho','')} {idea.get('enfoque','')}"
    if dedup_manager.es_tema_repetido(titulo, resumen):
        return True
    norm = _norm_idea(idea)
    for u in usadas:
        if dedup_manager.SequenceMatcher(None, norm[:1200], u[:1200]).ratio() >= 0.90:
            return True
        claves_a = set(dedup_manager.palabras_clave(norm))
        claves_b = set(dedup_manager.palabras_clave(u))
        sol = len(claves_a & claves_b) / max(1, min(len(claves_a), len(claves_b) or 1))
        sim = dedup_manager.SequenceMatcher(None, norm[:900], u[:900]).ratio()
        if sol >= 0.90 and sim >= 0.90:
            return True
    return False


def _variar_idea(base: dict[str, Any], intento: int, dia: date, franja: str) -> dict[str, Any]:
    idea = copy.deepcopy(base)
    sufijos = [
        "desde otro ángulo", "con error común", "en campo real", "paso a paso", "versión rápida",
        "para principiantes", "avanzado", "con checklist", "en clima difícil", "con comparativa",
    ]
    extra = sufijos[intento % len(sufijos)]
    tema = str(idea.get("titulo") or idea.get("categoria") or "drone")
    idea["titulo"] = f"{tema} ({extra}, {dia.isoformat()} {franja})".strip()
    idea["gancho"] = f"{idea.get('gancho','Idea Aura Drones')} Variante {extra}."
    idea["enfoque"] = f"{idea.get('enfoque','')} Enfoque {extra}, evita repetir tomas y mantiene utilidad real."
    idea["variante_dedup"] = extra
    return idea


def _idea_desde_plantilla(pl: dict[str, Any], dia: date, franja: str, idx: int) -> dict[str, Any]:
    tema = ["control suave", "luz dorada", "seguridad", "storytelling", "valor comercial", "movimiento FPV", "encuadre aéreo"][idx % 7]
    titulo = pl["titulo"].format(tema=tema)
    idea = {
        "titulo": titulo,
        "gancho": pl["gancho"],
        "enfoque": pl["enfoque"],
        "categoria": pl["categoria"],
        "tipo_plan": pl["tipo"],
        "fuente": "Planificador semanal Aura Drones",
        "plataforma": "planificador",
        "puntuacion_viral": 12,
        "estado": "pendiente",
    }
    if pl.get("es_comercial"):
        idea["es_comercial"] = True
        idea["cta_tipo"] = pl.get("cta_tipo", "cotizacion")
    return idea


def _marcar_miniseries(plan: dict[str, Any]) -> None:
    # 2 miniseries por semana: una de 2 y una de 3 episodios
    dias = plan.get("dias", [])
    slots = []
    for d in dias:
        for i in d.get("ideas", []):
            if not i.get("es_comercial"):
                slots.append(i)
    if len(slots) >= 5:
        serie2 = slots[0:2]
        serie3 = slots[2:5]
        sid2 = f"serie-semanal-2-{plan['fecha_inicio']}"
        sid3 = f"serie-semanal-3-{plan['fecha_inicio']}"
        for n, ep in enumerate(serie2, 1):
            ep.update({"serie_id": sid2, "episodio": n, "total_episodios": 2, "tipo_plan": "MINISERIE", "etiqueta": f"[MINISERIE {n}/2]", "adelanto": "En el siguiente episodio revelo la parte clave." if n < 2 else "Comenta A o B para cerrar la miniserie."})
        for n, ep in enumerate(serie3, 1):
            ep.update({"serie_id": sid3, "episodio": n, "total_episodios": 3, "tipo_plan": "MINISERIE", "etiqueta": f"[MINISERIE {n}/3]", "adelanto": "En el Episodio 2 te muestro el ajuste exacto que lo soluciona." if n == 1 else ("Pero falta un detalle crítico en vuelo real que vemos en el Episodio 3." if n == 2 else "Cierre de la miniserie: comenta Opción A o B.")})


def generar_plan(fecha_inicio: date, forzar: bool = False, notificar: bool = False, escribir: bool = True) -> dict[str, Any]:
    existente = cargar_plan()
    if existente and not forzar:
        fechas = {d.get("fecha") for d in existente.get("dias", [])}
        if all((fecha_inicio + timedelta(days=i)).isoformat() in fechas for i in range(7)):
            return existente

    dedup_manager.indexar(escribir=True, ttl_segundos=900)
    reales = _candidatos_reales()
    usadas: list[str] = []
    plan = {
        "generado_en": scheduler_manager.iso_utc(scheduler_manager.ahora_utc()),
        "fecha_inicio": fecha_inicio.isoformat(),
        "fecha_fin": (fecha_inicio + timedelta(days=6)).isoformat(),
        "zona_horaria": "America/Mexico_City",
        "dias": [],
    }

    # ubicar 2 slots comerciales por semana (miércoles tarde, sábado noche)
    comerciales_objetivo = {(2, 1), (5, 2)}
    idx_real = 0
    idx_pl = 0
    for d in range(7):
        dia = fecha_inicio + timedelta(days=d)
        ideas_dia = []
        for f_idx, franja in enumerate(FRANJAS):
            base = None
            if (d, f_idx) in comerciales_objetivo:
                base = _idea_desde_plantilla(next(p for p in PLANTILLAS_AURA if p["tipo"] == "COMERCIAL"), dia, franja, d * 3 + f_idx)
            else:
                while idx_real < len(reales):
                    cand = reales[idx_real]
                    idx_real += 1
                    if isinstance(cand, dict):
                        base = copy.deepcopy(cand)
                        break
                if base is None:
                    pl = PLANTILLAS_AURA[idx_pl % len(PLANTILLAS_AURA)]
                    idx_pl += 1
                    base = _idea_desde_plantilla(pl, dia, franja, d * 3 + f_idx)
            # dedup 90% contra redes/historial y contra semana
            intento = 0
            while _es_repetida(base, usadas) and intento < 30:
                intento += 1
                if idx_real < len(reales):
                    base = copy.deepcopy(reales[idx_real]); idx_real += 1
                else:
                    base = _variar_idea(base, intento, dia, franja)
                    if intento % 5 == 0:
                        pl = PLANTILLAS_AURA[(idx_pl + intento) % len(PLANTILLAS_AURA)]
                        base = _idea_desde_plantilla(pl, dia, franja, intento)
                        base = _variar_idea(base, intento, dia, franja)
            base["fecha"] = dia.isoformat()
            base["franja"] = franja
            base["orden"] = f_idx + 1
            base["estado"] = "pendiente"
            base.setdefault("tipo_plan", "COMERCIAL" if base.get("es_comercial") else base.get("tipo_plan", "AURA"))
            base.setdefault("etiqueta", f"[{base['tipo_plan']}]")
            usadas.append(_norm_idea(base))
            ideas_dia.append(base)
        plan["dias"].append({"fecha": dia.isoformat(), "dia": DIAS[dia.weekday()], "ideas": ideas_dia})

    _marcar_miniseries(plan)
    if escribir:
        guardar_plan(plan)
    if notificar:
        enviar_plan_telegram(plan)
    return plan


def formatear_mensaje_telegram(plan: dict[str, Any]) -> list[str]:
    bloques: list[str] = []
    actual = [f"AuraDrones | Cartelera semanal {plan.get('fecha_inicio')} a {plan.get('fecha_fin')}"]
    for dia in plan.get("dias", []):
        lineas = [f"\n{dia.get('dia')} {dia.get('fecha')}"]
        for idea in dia.get("ideas", []):
            etiqueta = idea.get("etiqueta") or f"[{idea.get('tipo_plan','AURA')}]"
            lineas.append(f"- {idea.get('franja','')}: {etiqueta} {idea.get('titulo','')}")
        bloque = "\n".join(lineas)
        if sum(len(x) for x in actual) + len(bloque) > 3500:
            bloques.append("\n".join(actual))
            actual = ["AuraDrones | Cartelera semanal (cont.)"]
        actual.append(bloque)
    bloques.append("\n".join(actual))
    return bloques


def enviar_plan_telegram(plan: dict[str, Any]) -> None:
    for bloque in formatear_mensaje_telegram(plan):
        notificador_telegram.enviar_mensaje(bloque)


def evaluar_cambio_viral_ultimo_minuto(fecha: Any, plan: dict[str, Any] | None = None, notificar: bool = True, escribir: bool = True) -> dict[str, Any] | None:
    fecha_iso = str(fecha)
    plan = plan or cargar_plan()
    if not plan:
        return None
    dia_plan = next((d for d in plan.get("dias", []) if d.get("fecha") == fecha_iso), None)
    if not dia_plan:
        return None
    try:
        candidatos, _ = trend_hunter.recolectar(ttl_segundos=900)
    except Exception:
        return None
    frescos = []
    for c in candidatos:
        idea = trend_hunter.construir_idea(str(c.get("categoria") or "Tip práctico DJI/FPV"), c)
        idea["puntuacion_viral"] = float(c.get("puntuacion_viral") or idea.get("puntuacion_viral") or 0)
        frescos.append(idea)
    frescos.sort(key=lambda i: float(i.get("puntuacion_viral", 0)), reverse=True)
    if not frescos:
        return None
    top = frescos[0]
    top_score = float(top.get("puntuacion_viral", 0))
    pendientes = [i for i in dia_plan.get("ideas", []) if i.get("estado") in {None, "", "pendiente"}]
    if not pendientes:
        return None
    min_pendiente = min(float(i.get("puntuacion_viral", 0) or 0) for i in pendientes)
    if not (top_score >= 16 or top_score >= min_pendiente + 4):
        return None
    if dedup_manager.es_tema_repetido(str(top.get("titulo","")), f"{top.get('gancho','')} {top.get('enfoque','')}"):
        return None

    reemplazables = [i for i in pendientes if not (i.get("es_comercial") or (i.get("serie_id") and str(i.get("estado")) != "pendiente" and i.get("episodio",1) > 1))]
    # proteger episodios activos de miniserie en curso
    reemplazables = [i for i in reemplazables if not (i.get("serie_id") and any(x.get("serie_id")==i.get("serie_id") and x.get("estado")=="completada" for x in plan.get("dias",[]) for x in x.get("ideas",[])))]
    if not reemplazables:
        reemplazables = pendientes
    reemplazables.sort(key=lambda i: (1 if i.get("es_comercial") else 0, 1 if i.get("serie_id") else 0, float(i.get("puntuacion_viral",0) or 0)))
    objetivo = reemplazables[0]
    anterior = str(objetivo.get("titulo",""))
    nuevo = copy.deepcopy(top)
    nuevo.update({
        "fecha": fecha_iso,
        "franja": objetivo.get("franja"),
        "orden": objetivo.get("orden"),
        "estado": "pendiente",
        "etiqueta": "[VIRAL ÚLTIMO MINUTO]",
        "tipo_plan": "VIRAL_ULTIMO_MINUTO",
        "reemplazado_por_viral": True,
        "titulo_anterior": anterior,
    })
    for k in list(objetivo.keys()):
        objetivo.pop(k)
    objetivo.update(nuevo)
    plan.setdefault("cambios_virales", []).append({
        "fecha": fecha_iso,
        "titulo_anterior": anterior,
        "titulo_nuevo": objetivo.get("titulo"),
        "fuente": objetivo.get("fuente"),
        "plataforma": objetivo.get("plataforma"),
        "puntuacion_viral": top_score,
        "motivo": "Tema viral de último minuto con mayor potencial que el slot pendiente",
        "registrado_en": scheduler_manager.iso_utc(scheduler_manager.ahora_utc()),
    })
    if escribir:
        guardar_plan(plan)
    if notificar:
        msg = (
            "AuraDrones | Cambio viral de último minuto\n"
            f"Fecha: {fecha_iso}\n"
            f"Se sustituyó: {anterior}\n"
            f"Nuevo tema: {objetivo.get('titulo','')}\n"
            f"Fuente/plataforma: {objetivo.get('fuente','')} / {objetivo.get('plataforma','')}\n"
            f"Puntaje viral: {top_score}\n"
            "Motivo: superó el potencial del slot pendiente y pasó deduplicación 90%."
        )
        notificador_telegram.enviar_mensaje(msg)
    return objetivo


def obtener_ideas_para_fecha(fecha: Any, plan: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    fecha_iso = str(fecha)
    plan = plan or cargar_plan()
    if not plan:
        return []
    dia = next((d for d in plan.get("dias", []) if d.get("fecha") == fecha_iso), None)
    return list(dia.get("ideas", [])) if dia else []


def actualizar_estado_idea(fecha: Any, titulo: str, estado: str, detalle: str = "", proyecto: str = "", video: str = "") -> None:
    plan = cargar_plan()
    if not plan:
        return
    fecha_iso = str(fecha)
    for dia in plan.get("dias", []):
        if dia.get("fecha") != fecha_iso:
            continue
        for idea in dia.get("ideas", []):
            if dedup_manager.normalizar(idea.get("titulo")) == dedup_manager.normalizar(titulo):
                idea["estado"] = estado
                if detalle:
                    idea["detalle"] = detalle
                if proyecto:
                    idea["proyecto"] = proyecto
                if video:
                    idea["video"] = video
                idea["actualizado_en"] = scheduler_manager.iso_utc(scheduler_manager.ahora_utc())
                guardar_plan(plan)
                return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Planificador semanal Aura Drones")
    parser.add_argument("--fecha-inicio", help="YYYY-MM-DD")
    parser.add_argument("--forzar", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    inicio = _fecha_inicio(args.fecha_inicio)
    plan = generar_plan(inicio, forzar=args.forzar, notificar=not args.dry_run, escribir=not args.dry_run)
    # Simulación segura de lógica viral en dry-run (sin enviar notificación ni mutar plan guardado)
    if args.dry_run:
        copia = copy.deepcopy(plan)
        evaluar_cambio_viral_ultimo_minuto(inicio.isoformat(), copia, notificar=False, escribir=False)
    for bloque in formatear_mensaje_telegram(plan):
        print(bloque)
        print("-" * 40)
    if not args.dry_run:
        enviar_plan_telegram(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
