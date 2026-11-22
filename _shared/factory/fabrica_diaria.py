from __future__ import annotations

import argparse
import html
import json
import os
import random
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

ROOT_DIR = Path(__file__).resolve().parents[2]
FACTORY_DIR = Path(__file__).resolve().parent
SHARED_DIR = ROOT_DIR / "_shared"
AGENTES_DIR = SHARED_DIR / "agentes"
PUBLISHER_DIR = SHARED_DIR / "publisher"
IDEAS_PATH = FACTORY_DIR / "ideas_pendientes.json"
OPORTUNIDADES_PATH = FACTORY_DIR / "oportunidades_colab.json"
LOG_PATH = FACTORY_DIR / "factory.log"
PLATAFORMAS_FABRICA = "youtube,tiktok,instagram,facebook"
PUBLISHER_SCRIPT = PUBLISHER_DIR / "publicar_todo.py"
OPENCODE_PS1 = Path(os.getenv("AURA_OPENCODE_PS1", str(Path.home() / "AppData" / "Roaming" / "npm" / "opencode.ps1")))
VIDEO_MIN_BYTES = 500_000
CUPO_DIARIO = 3
VAULT_INDEX_PATH = ROOT_DIR / "_shared" / "media_vault" / "index.json"
CARPETAS_BROLL = {
    "tips": ("gadgets", "urbano"),
    "fpv": ("fpv", "urbano"),
    "cine": ("cinematico", "urbano"),
    "tech": ("gadgets", "cinematico"),
}

for ruta_importacion in (PUBLISHER_DIR, SHARED_DIR, FACTORY_DIR):
    if str(ruta_importacion) not in sys.path:
        sys.path.insert(0, str(ruta_importacion))

import carousel_exporter
import cover_generator
import dedup_manager
import descargar_recursos
import estilos_video
import metadata_viral
import notificador_telegram
import paletas
import qa_video
import render_engine
import scheduler_manager
import trend_hunter
import vault_indexer
import voice_engine
try:
    import planificador_semanal
except Exception:
    planificador_semanal = None
try:
    import sfx_generator
except Exception:
    sfx_generator = None
try:
    from agentes.orquestador import ejecutar as ejecutar_orquestador
    from agentes.telegram_decisiones import notificar_urgente
except Exception:
    ejecutar_orquestador = None
    notificar_urgente = None


def log(mensaje: str) -> None:
    linea = f"[{scheduler_manager.ahora_local().isoformat(timespec='seconds')}] {mensaje}"
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as archivo:
        archivo.write(linea + "\n")
    print(linea)


def normalizar(texto: Any) -> str:
    valor = unicodedata.normalize("NFKD", str(texto or ""))
    valor = "".join(caracter for caracter in valor if not unicodedata.combining(caracter))
    return re.sub(r"\s+", " ", valor.casefold()).strip()


def clave_pregunta(texto: Any) -> str:
    valor = re.sub(r"[¿?？]", "", normalizar(texto))
    return re.sub(r"[.!…]+$", "", valor).strip(" .;:!¡")


def slug(texto: Any) -> str:
    valor = re.sub(r"[^a-z0-9]+", "-", normalizar(texto)).strip("-")
    return valor or "video"


def plan_broll(idea: dict[str, Any], duracion_objetivo: float = 30.0) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "overlay": "rgba(10, 12, 16, 0.45)",
        "panel": "detrás de los motion graphics, z=0",
        "clips": [],
    }
    if not VAULT_INDEX_PATH.is_file():
        return plan
    try:
        indice = json.loads(VAULT_INDEX_PATH.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return plan
    clips = [clip for clip in indice.get("clips", []) if isinstance(clip, dict)]
    if not clips:
        return plan

    categoria = str(idea.get("categoria") or "")
    titulo = str(idea.get("titulo") or "")
    try:
        estilo = estilos_video.seleccionar(idea)
        preferidas = estilos_video.carpetas_broll(estilo)
        clave = str(estilo.get("id") or "1000350998")
    except (TypeError, ValueError):
        clave = paletas.seleccionar(categoria, titulo)
        preferidas = CARPETAS_BROLL.get(clave, CARPETAS_BROLL["tips"])
    candidatos = [
        clip
        for clip in clips
        if clip.get("carpeta") in preferidas and float(clip.get("duracion_s") or 0) >= 1
    ] or [clip for clip in clips if float(clip.get("duracion_s") or 0) >= 1]

    aleatorio = random.Random(f"{slug(titulo)}|{clave}")
    aleatorio.shuffle(candidatos)
    seleccion: list[dict[str, Any]] = []
    usados: set[str] = set()
    for clip in candidatos:
        origen = str(clip.get("ruta") or "")
        if not origen or origen in usados:
            continue
        duracion = float(clip.get("duracion_s") or 0)
        trozo = min(4.0, max(1.5, duracion / 3 if duracion else 2.0))
        inicio = max(0.0, min(duracion - trozo, duracion * 0.15)) if duracion > trozo else 0.0
        seleccion.append(
            {
                "origen": origen,
                "destino": f"assets/media/{Path(origen).name}",
                "carpeta": clip.get("carpeta"),
                "data-start": round(sum(item["data-duration"] for item in seleccion), 2),
                "data-duration": round(trozo, 2),
                "data-media-start": round(inicio, 2),
                "data-volume": "0",
                "resolucion": clip.get("resolucion", "desconocida"),
            }
        )
        usados.add(origen)
        if len(seleccion) >= 3 or sum(item["data-duration"] for item in seleccion) >= duracion_objetivo:
            break
    plan["clips"] = seleccion
    return plan


def cargar_ideas() -> dict[str, Any]:
    if not IDEAS_PATH.is_file():
        return {"ideas": []}

    try:
        crudo = IDEAS_PATH.read_text(encoding="utf-8", errors="replace").strip()
        datos = json.loads(crudo) if crudo else {}
    except (OSError, json.JSONDecodeError) as error:
        try:
            corrupto = IDEAS_PATH.with_name(f"ideas_pendientes.corrupt-{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
            IDEAS_PATH.replace(corrupto)
        except OSError:
            pass
        log(f"[ideas] ideas_pendientes.json corrupto, respaldado: {error}")
        return {"ideas": []}
    if not isinstance(datos, dict):
        datos = {}
    if not isinstance(datos.get("ideas"), list):
        datos["ideas"] = []
    return datos


def guardar_ideas(datos: dict[str, Any]) -> None:
    temporal = IDEAS_PATH.with_name(IDEAS_PATH.name + ".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporal.replace(IDEAS_PATH)


def limpiar_temporales_proyecto(proyecto: Path) -> int:
    if not proyecto.is_dir():
        return 0
    eliminados = 0
    patrones = (
        "*.tmp",
        "*.part",
        "*.partial",
        "*.crdownload",
        "renders/*.tmp",
        "renders/*.part",
        "renders/.frame_*.jpg",
        "renders/.base_*.jpg",
        "renders/qa_frames/*",
        "assets/audio/voz_tmp*",
    )
    for patron in patrones:
        for ruta in proyecto.glob(patron):
            if ruta.is_file():
                try:
                    ruta.unlink()
                    eliminados += 1
                except OSError:
                    pass
    renders = proyecto / "renders"
    if renders.is_dir():
        for ruta in renders.glob("*.mp4"):
            try:
                if ruta.stat().st_size <= 0:
                    ruta.unlink()
                    eliminados += 1
            except OSError:
                pass
    qa_frames = renders / "qa_frames"
    if qa_frames.is_dir():
        try:
            if not any(qa_frames.iterdir()):
                qa_frames.rmdir()
        except OSError:
            pass
    if eliminados:
        log(f"[limpieza] {eliminados} archivos temporales eliminados en {proyecto.name}")
    return eliminados


def validar_idea(idea: dict[str, Any]) -> tuple[bool, str]:
    titulo = str(idea.get("titulo") or "")
    resumen = str(idea.get("resumen") or "")
    if idea.get("es_colaboracion"):
        try:
            datos = json.loads(OPORTUNIDADES_PATH.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError) as error:
            return False, f"oportunidades_colab.json inválido: {error}"
        for oportunidad in datos.get("oportunidades", []):
            if not isinstance(oportunidad, dict):
                continue
            mismo_titulo = normalizar(oportunidad.get("titulo")) == normalizar(titulo)
            if mismo_titulo and oportunidad.get("vigente") and oportunidad.get("es_formal", True):
                return True, "convocatoria activa validada"
        return False, "convocatoria no vigente o no verificada"

    serie = str(idea.get("serie_id") or "").strip()
    episodio = 0
    try:
        episodio = int(idea.get("episodio") or 0)
    except (TypeError, ValueError):
        episodio = 0
    if serie and episodio > 1:
        anteriores = cargar_ideas().get("ideas", [])
        previo = any(
            isinstance(item, dict)
            and str(item.get("serie_id") or "") == serie
            and str(item.get("episodio") or "") == str(episodio - 1)
            for item in anteriores
        )
        if previo:
            return True, f"continuación válida de miniserie {serie} EPISODIO {episodio}"

    repetido, detalle = dedup_manager.detalle_tema_repetido(titulo, resumen)
    if repetido:
        return False, f"tema repetido ({detalle.get('motivo')}, similitud {detalle.get('similitud')})"
    return True, f"tema inédito (similitud {detalle.get('similitud')})"


def contar_agendados_para(fecha: Any) -> int:
    videos: set[str] = set()

    for tarea in scheduler_manager.listar_tareas():
        estado = str(tarea.get("estado", "")).lower()
        if estado in {"cancelled", "failed"}:
            continue

        fecha_tarea = scheduler_manager.parse_scheduled_at(tarea.get("scheduled_at"))
        if fecha_tarea is None:
            continue
        if fecha_tarea.astimezone(scheduler_manager.ZONA).date() != fecha:
            continue

        identificador = str(tarea.get("video") or tarea.get("proyecto") or tarea.get("id") or "").strip()
        videos.add(identificador or f"tarea-{tarea.get('id', '')}")

    return len(videos)


def nombre_proyecto(idea: dict[str, Any], fecha: Any) -> str:
    base = slug(idea.get("id") or idea.get("titulo") or "video")[:42]
    sello = scheduler_manager.ahora_local().strftime("%Y%m%d_%H%M%S")
    return f"{base}_{sello}"


def horarios_agendados(video: Path, proyecto_nombre: str, fecha: Any) -> dict[str, str]:
    objetivo = str(fecha)
    horarios: dict[str, str] = {}
    for tarea in scheduler_manager.listar_tareas():
        plataforma = str(tarea.get("plataforma", "")).strip().lower()
        if plataforma not in {"youtube", "tiktok"}:
            continue
        ruta_tarea = str(tarea.get("video") or "")
        if ruta_tarea != str(video) and proyecto_nombre not in ruta_tarea:
            continue
        fecha_tarea = scheduler_manager.parse_scheduled_at(tarea.get("scheduled_at"))
        if fecha_tarea is None:
            continue
        if fecha_tarea.astimezone(scheduler_manager.ZONA).date().isoformat() != objetivo:
            continue
        hora = str(tarea.get("slot") or "").strip()
        local = str(tarea.get("scheduled_at_local") or "").strip()
        if not hora and local:
            try:
                hora = datetime.fromisoformat(local.replace("Z", "+00:00")).strftime("%H:%M")
            except ValueError:
                pass
        horarios[plataforma] = hora or "pendiente"
    return horarios


def requiere_loop_invisible(idea: dict[str, Any], fecha: Any) -> bool:
    try:
        orden = int(idea.get("orden") or 0)
    except (TypeError, ValueError):
        orden = 0
    if orden > 0:
        return orden % 3 in (1, 2)
    return int(getattr(fecha, "day", 1)) % 2 == 1


def prompt_generacion(
    idea: dict[str, Any],
    proyecto: str,
    fecha: Any,
    idioma: str = "es",
    estilo: dict[str, Any] | None = None,
    aporte_agentes: str = "",
) -> str:
    bucle = requiere_loop_invisible(idea, fecha)
    estilo_resuelto = estilo or estilos_video.seleccionar(idea)
    serie_id = str(idea.get("serie_id") or "").strip()
    episodio = idea.get("episodio") or ""
    total_episodios = idea.get("total_episodios") or ""
    miniserie = (
        f"MINISERIE {serie_id} EPISODIO {episodio}/{total_episodios}. Arco: {idea.get('arco', '')}. "
        f"Cierre con adelanto: {idea.get('adelanto', '')}. "
        "La etiqueta superior debe incluir EPISODIO n/m dentro de y=220..340. "
        if serie_id
        else ""
    )
    gancho_a = str(idea.get("gancho_a") or f"Error común: {idea.get('gancho', '')}").strip()
    gancho_b = str(idea.get("gancho_b") or f"Resultado directo: {idea.get('gancho', '')}").strip()
    return (
        f"Trabaja en el root de videos-ia: {ROOT_DIR}. "
        f"Crea y termina el proyecto '{proyecto}' siguiendo AGENTS.md y _shared/templates/vertical-pro. "
        f"Fecha objetivo: {fecha.isoformat()}. "
        f"Orden: {idea.get('orden', '?')}. Franja: {idea.get('franja', '')}. "
        f"Categoría: {idea.get('categoria', '')}. "
        f"Tema detectado: {idea.get('titulo', '')}. "
        f"Gancho: {idea.get('gancho', '')}. "
        f"Idioma de exportación: {idioma}. "
        f"Bucle invisible: {'SÍ' if bucle else 'NO'}. "
        f"{miniserie}"
        f"Enfoque: {idea.get('enfoque', '')}. "
        f"Fuente: {idea.get('fuente', '')} {idea.get('url', '')}. "
        f"{estilos_video.prompt_estilo(estilo_resuelto)} "
        f"{aporte_agentes.strip()} "
        "Es un short vertical de 1080x1920 y 30 fps con duración entre 15 y 60 segundos, sin superar nunca 60.0 s, voz conversacional en español mexicano, "
        "gancho visual en 0–1.5 s con spring scale 1.15->1.0 y light sweep, GSAP con eases con nombre, captions cortos y SFX locales. "
        "Consulta antes de animar `.agents/skills/remotion-best-practices/SKILL.md`, `.agents/skills/remotion-code-motion-explainer/SKILL.md` y `_shared/skills_ext/claude-remotion-skill/remotion-motion-graphics/SKILL.md`; adapta spring/stagger/curvas a GSAP pausado (sin React/useCurrentFrame). "
        "Usa SOLO tres zonas exclusivas: Superior y=200..340 (subtítulo dinámico 3–4 palabras por bloque, palabra activa resaltada, píldora de sección y puntos de progreso • • • •, left=80 right=150); "
        "Central y=380..1260 (tarjeta protagonista animada con ilustraciones SVG vectoriales: drones, mandos, trayectorias, diales, iconos reaccionando al ritmo de voz, micro-estímulo cada 3.5s, left=80 right=150); "
        "Inferior y>1320 totalmente libre. Ninguna banda se toca entre sí. "
        "Antes de tocar el HTML ejecuta `python _shared/factory/paletas.py <proyecto> \"<categoría>\" --titulo \"<título>\"`, "
        "pero el estilo asignado más arriba manda: usa su paleta en data-palette de index.html y deja `estilo_id`, `estilo`, `duracion_maxima_s` y la paleta guardados en config.json y renders/metadata.json. "
        f"B-roll automático desde _shared/media_vault/index.json: {json.dumps(plan_broll(idea), ensure_ascii=False)}. "
        "Copia cada origen a su destino dentro del proyecto y colócalo detrás de los motion graphics con z=0, "
        "object-fit cover y overlay rgba(10, 12, 16, 0.45) para oscurecerlo 45%; respeta data-start, data-duration, data-media-start y data-volume=0. "
        "Si el plan está vacío, usa la cuadrícula SVG de la plantilla. "
        "Aplica las reglas vivas de AGENTS.md, especialmente las secciones 12, 13 y 'Mejoras Continuas de Calidad y Diseño', "
        "y consulta _shared/factory/mejoras_semanales.md antes de decidir el ritmo visual. "
        "Aplica la curva de edición de config.json sin excepciones: cortes de 0.9–1.3 s en 0–4 s, ritmo medio de 2.0–2.5 s en el desarrollo y remate con hit.mp3 desde _shared/sfx/; sincroniza SFX sutiles de _shared/sfx/ en cada transición de tarjeta. "
        "cada 3.5 s dispara un micro-estímulo de zoom punch-in 1.0->1.10 con destello direccional o cambio de tarjeta de dato, sincronizado con click-soft.mp3 a volumen 0.18; "
        "en 0–1.5 s usa spring scale 1.15->1.0, light sweep y whoosh-short.mp3; "
        "monta compositions/hud.html con telemetría acorde al tema y, cuando el tema sea de debate, monta compositions/debate.html con Opción A vs Opción B sin solapar el bloque de métricas; "
        "mantén movimiento continuo en tarjetas de datos, diales, barras y trayectorias SVG, y aplica Ken Burns al fondo o al B-roll copiado de _shared/media_vault/. "
        "El tema debe estar validado por dedup_manager.py con cero repeticiones históricas; si es colaboración, "
        "debe figurar como formal y vigente en _shared/factory/oportunidades_colab.json. "
        "Genera la voz SIEMPRE con `python _shared/factory/voice_engine.py \"<guion>\" "
        "\"<proyecto>/assets/audio/voz.mp3\" --categoria \"<categoría>\" --titulo \"<título>\" --idioma \"<idioma>\"`; "
        "el módulo alterna es-MX-JorgeNeural y es-MX-DaliaNeural según el tema, aplica +8%/+3Hz en el gancho y +3% en el cuerpo, "
        "convierte siglas a pronunciación hablada y guarda `<voz>.json` con el texto escrito original para los subtítulos. "
        + (
            "Si el idioma es en, adapta guion, título, descripciones, hashtags, captions y CTA al inglés antes de narrar; "
            "guarda el texto adaptado en `<proyecto>/guion.en.json` con las claves `texto`, `titulo`, `descripcion` y `gancho`, "
            "y usa `--idioma en` para que `voice_engine.py` emplee en-US-AndrewNeural. "
            if idioma == "en"
            else ""
        )
        + "Normaliza con `powershell -ExecutionPolicy Bypass -File \"_shared\\scripts\\mezclar_audio.ps1\" -Proyecto \"<proyecto>\" -Categoria \"<categoría>\" -Sfx ...`; "
        "si _shared/music/ tiene pistas .mp3/.wav, el script llama a audio_mixer.py, elige la carpeta según la categoría "
        "(fpv_energia, cine_ambiental o tech_limpio) y aplica sidechaincompress con la voz como disparador, subiendo la música en las transiciones; "
        "no dupliques el ducking ni uses música remota. Los subtítulos conservan FPS, AUX y FPV con su grafía técnica y espacios reales. "
        "Analiza el tema real, escribe un guion original y distinto a los proyectos existentes. "
        "Cuando 'Bucle invisible' sea SÍ, la última frase hablada debe empezar exactamente con la misma primera palabra del gancho inicial "
        "y encadenarse sintácticamente con él, sin decir 'como al inicio' ni explicar el truco; el remate debe sonar natural y llevar al replay mental. "
        "Esa primera palabra también debe abrir la última tarjeta visual del CTA. Cuando sea NO, cierra con una pregunta nueva y no reiteres el gancho. "
        "El guion DEBE cerrar en los últimos 3–4 s con una invitación directa y natural según la categoría: "
        "tips DJI/configuración → guardar antes de volar y comentar qué modelo usan; FPV/acción → reto o pregunta polarizante sobre la maniobra; "
        "cine/edición → etiquetar al compañero de vuelo o elegir entre dos opciones; tech/gadgets → preguntar si harían el cambio o qué opinan del equipo. "
        "Nunca termines de golpe ni uses 'sígueme para más'. Esa misma frase hablada debe aparecer en la última tarjeta de `compositions/cta.html`, "
        "confinada a la zona central y sin texto en y>1360. Antes de fijarla ejecuta "
        "`python _shared/factory/dedup_manager.py --verificar-cta \"<frase>\"` y rechaza cualquier CTA repetido o casi idéntico. "
        "Copia la plantilla de metadata a renders/metadata.json y rellena los bloques youtube, tiktok, "
        "instagram y facebook con copy 100% único y contextual, títulos llamativos y descripciones que enganchan en la primera línea, explican el giro y cierran con la pregunta; cada bloque con su propio gancho y hashtags virales de nicho en español, sin inglés innecesario, sin signos duplicados y sin texto fuera de los campos de metadata. "
        "Reglas exactas: `youtube.title` de menos de 55 caracteres; `youtube.hashtags` con entre 4 y 5 etiquetas y siempre `Shorts`; `tiktok.description` con gancho de al menos 12 caracteres en la primera línea e invitación a guardar o comentar; `instagram.description` con resumen en viñetas `•` e invitación a guardar o compartir; `facebook.description` invitando a comentar, opinar o compartir. "
        "Agrega `pregunta_detonadora` en los cuatro bloques y haz que cada `description` termine exactamente con esa misma pregunta en UTF-8 limpio. La fábrica normaliza cualquier desvío de formato antes de publicar, sin pedir aprobación. "
        "Agrega el objeto `experimento_ab` con `experimento=\"gancho\"`, "
        f"`gancho_a={json.dumps(gancho_a, ensure_ascii=False)}` (curiosidad/error común) y "
        f"`gancho_b={json.dumps(gancho_b, ensure_ascii=False)}` (resultado directo); YouTube usará A y TikTok usará B, y ambos deben ser distintos. "
        f"Si la idea trae miniserie, agrega `serie` con id {json.dumps(serie_id, ensure_ascii=False)}, episodio {json.dumps(episodio, ensure_ascii=False)}, total {json.dumps(total_episodios, ensure_ascii=False)} y adelanto {json.dumps(str(idea.get('adelanto') or ''), ensure_ascii=False)}. "
        "Revisa antes _shared/publisher/schedule_queue.json para no repetir ganchos ni hashtags. "
        "Verifica con lint, timeline y snapshot; si check falla por el entorno, no lo uses. "
        "Renderiza el MP4 con npm run render, extrae 3 frames con ffmpeg al 15%, 50% y 85% y valida con `python _shared/factory/qa_video.py <proyecto>` que no haya solapamientos ni texto fuera de zonas seguras; si falla, corrige y repite render+QA hasta pasar. Luego extrae renders/portada.jpg con npm run portada. "
        "NO publiques, NO subas y NO programes: la fábrica se encarga de eso después. "
        "Si el proyecto ya existe, corrígelo y termínalo en lugar de crear otro."
    )


def forma_comando(args: list[str], limite: int = 700) -> str:
    texto = " ".join(f'"{arg}"' if " " in str(arg) else str(arg) for arg in args)
    return texto if len(texto) <= limite else texto[:limite] + " ..."


def comando_opencode(prompt: str) -> list[str]:
    auto = os.getenv("AURA_OPENCODE_AUTO", "1") == "1"
    opciones = ["run"]
    if auto:
        opciones.append("--auto")
    opciones.append(prompt)

    if OPENCODE_PS1.is_file():
        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(OPENCODE_PS1),
            *opciones,
        ]

    ejecutable = shutil.which("opencode.cmd") or shutil.which("opencode")
    if not ejecutable:
        raise FileNotFoundError(f"No se encontró OpenCode en {OPENCODE_PS1} ni en PATH")
    return [ejecutable, *opciones]


def ejecutar_comando(
    args: list[str],
    cwd: Path,
    etiqueta: str,
    timeout: int | None = None,
    fallar_si: tuple[str, ...] = (),
) -> tuple[bool, str]:
    log(f"[{etiqueta}] CMD {forma_comando(args)}")
    try:
        proceso = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        mensaje = f"timeout tras {timeout}s"
        log(f"[{etiqueta}] ERROR {mensaje}")
        return False, mensaje
    except OSError as error:
        mensaje = f"{type(error).__name__}: {error}"
        log(f"[{etiqueta}] ERROR {mensaje}")
        return False, mensaje

    for linea in (proceso.stdout or "").splitlines():
        if linea.strip():
            log(f"[{etiqueta}] {linea}")
    for linea in (proceso.stderr or "").splitlines():
        if linea.strip():
            log(f"[{etiqueta}] stderr: {linea}")

    salida = (proceso.stdout or "") + "\n" + (proceso.stderr or "")
    marcadores = [marcador for marcador in fallar_si if marcador in salida]
    if marcadores:
        mensaje = f"salida contiene {', '.join(marcadores)}"
        log(f"[{etiqueta}] ERROR {mensaje}")
        return False, mensaje

    if proceso.returncode == 0:
        log(f"[{etiqueta}] OK exit=0")
        return True, "exit=0"

    mensaje = f"exit={proceso.returncode}"
    log(f"[{etiqueta}] ERROR {mensaje}")
    return False, mensaje


def con_reintento(
    operacion: Callable[[int], tuple[bool, Any, str]],
    etiqueta: str,
) -> tuple[bool, Any, str]:
    ultimo = "sin intentos"

    for intento in (1, 2):
        try:
            ok, valor, mensaje = operacion(intento)
            if ok:
                return True, valor, mensaje
            ultimo = mensaje
        except Exception as error:
            ultimo = f"{type(error).__name__}: {error}"
            log(f"[{etiqueta}] EXCEPCIÓN intento {intento}: {ultimo}")

        if intento == 1:
            log(f"[{etiqueta}] Reintentando una vez")

    log(f"[{etiqueta}] ERROR final: {ultimo}")
    return False, None, ultimo


def validar_cta_metadata(metadata: dict[str, Any], proyecto: Path) -> tuple[bool, str]:
    preguntas: list[str] = []
    for bloque in ("youtube", "tiktok", "instagram", "facebook"):
        config = metadata.get(bloque)
        if not isinstance(config, dict):
            return False, f"falta el bloque {bloque}"
        pregunta = dedup_manager.extraer_pregunta_detonadora(config)
        if not pregunta:
            return False, f"{bloque}.pregunta_detonadora falta o no es una pregunta"
        lineas = [linea.strip() for linea in str(config.get("description", "")).splitlines() if linea.strip()]
        if not lineas or clave_pregunta(lineas[-1]) != clave_pregunta(pregunta):
            return False, f"{bloque}.description no cierra con pregunta_detonadora"
        preguntas.append(pregunta)
    if len({clave_pregunta(pregunta) for pregunta in preguntas}) != 1:
        return False, "las cuatro redes no usan la misma pregunta detonadora"
    repetido, detalle = dedup_manager.cta_repetida(preguntas[0], excluir=proyecto.name)
    if repetido:
        return False, f"{detalle.get('motivo', 'CTA repetido')}: {detalle.get('anterior', '')}"
    return True, preguntas[0]


def validar_experimento_ab(metadata: dict[str, Any]) -> tuple[bool, str, bool]:
    experimental = metadata.get("experimento_ab")
    modificado = False
    if not isinstance(experimental, dict):
        youtube = metadata.get("youtube") if isinstance(metadata.get("youtube"), dict) else {}
        tiktok = metadata.get("tiktok") if isinstance(metadata.get("tiktok"), dict) else {}
        lineas = [linea.strip() for linea in str(tiktok.get("description", "")).splitlines() if linea.strip()]
        experimental = {
            "experimento": "gancho",
            "gancho_a": str(youtube.get("title") or "").strip(),
            "gancho_b": lineas[0] if lineas else "",
            "asignacion": {"youtube": "A", "tiktok": "B"},
        }
        metadata["experimento_ab"] = experimental
        modificado = True

    gancho_a = str(experimental.get("gancho_a") or "").strip()
    gancho_b = str(experimental.get("gancho_b") or "").strip()
    if not gancho_a or not gancho_b:
        return False, "experimento_ab.gancho_a y gancho_b son obligatorios", modificado
    if dedup_manager.normalizar(gancho_a) == dedup_manager.normalizar(gancho_b):
        return False, "gancho_a y gancho_b deben ser distintos", modificado
    asignacion = experimental.get("asignacion")
    if not isinstance(asignacion, dict):
        asignacion = {"youtube": "A", "tiktok": "B"}
        experimental["asignacion"] = asignacion
        modificado = True
    if str(asignacion.get("youtube") or "").upper() != "A" or str(asignacion.get("tiktok") or "").upper() != "B":
        return False, "experimento_ab debe alternar YouTube=A y TikTok=B", modificado
    return True, "A/B YouTube=A TikTok=B", modificado


def normalizar_audio_mp4(video: Path) -> None:
    salida = video.with_name(video.stem + "_loudnorm.mp4")
    comando = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video),
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        str(salida),
    ]
    proceso = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(video.parent))
    if proceso.returncode != 0 or not salida.is_file() or salida.stat().st_size < 1024:
        salida.unlink(missing_ok=True)
        raise RuntimeError((proceso.stderr or proceso.stdout or "ffmpeg loudnorm falló")[-400:])
    os.replace(salida, video)


def extraer_cover_jpg(video: Path) -> Path | None:
    cover = video.parent / "cover.jpg"
    comando = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", "0.8", "-i", str(video),
        "-frames:v", "1", "-q:v", "2", str(cover),
    ]
    proceso = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(video.parent))
    if proceso.returncode == 0 and cover.is_file() and cover.stat().st_size > 1024:
        return cover
    return None


def leer_voz_sidecar(proyecto: Path) -> dict[str, Any]:
    for ruta in (proyecto / "assets" / "audio" / "voz.json", proyecto / "renders" / "voz.json"):
        if ruta.is_file():
            try:
                return json.loads(ruta.read_text(encoding="utf-8"))
            except Exception:
                return {}
    return {}


def seleccionar_media_vault(categoria: str, tema: str) -> list[dict[str, Any]]:
    index_path = ROOT_DIR / "_shared" / "media_vault" / "vault_index.json"
    if not index_path.exists():
        index_path = ROOT_DIR / "_shared" / "media_vault" / "index.json"
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    clips = data.get("clips", []) if isinstance(data, dict) else []
    cat = normalizar(categoria)
    tema_n = normalizar(tema)
    pref = ["general"]
    if "fpv" in cat or "fpv" in tema_n:
        pref = ["fpv", "dji", "general"]
    elif "cine" in cat or "cinema" in tema_n or "aereo" in tema_n:
        pref = ["cine", "dji", "general"]
    elif "dji" in cat or "tech" in cat or "novedad" in cat:
        pref = ["dji", "cine", "general"]
    seleccionados = []
    for bucket in pref:
        for c in clips:
            if str(c.get("carpeta", "")) == bucket and c not in seleccionados:
                seleccionados.append(c)
            if len(seleccionados) >= 2:
                return seleccionados
    return seleccionados[:2]


def inyectar_media_vault(proyecto: Path, categoria: str, tema: str) -> list[str]:
    clips = seleccionar_media_vault(categoria, tema)
    if not clips:
        return []
    hook = proyecto / "compositions" / "hook.html"
    if not hook.exists():
        return []
    html = hook.read_text(encoding="utf-8")
    videos_html = []
    usados = []
    for i, c in enumerate(clips[:2]):
        src = c.get("ruta_absoluta") or str((ROOT_DIR / c.get("ruta", "")).resolve())
        src_path = Path(src)
        if not src_path.exists():
            continue
        dest_dir = proyecto / "assets" / "video"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src_path.name
        if not dest.exists():
            shutil.copy2(src_path, dest)
        rel = f"assets/video/{dest.name}"
        style = "position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:brightness(0.45) blur(1px);opacity:0.55;" if i == 0 else "position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:brightness(0.5);opacity:0.45;"
        videos_html.append(f'<video class="vault-bg" data-vault-cat="{c.get("carpeta","")}" src="{rel}" muted loop playsinline autoplay style="{style}"></video>')
        usados.append(rel)
    if not videos_html:
        return []
    bloque = '<div id="vault-bg" class="clip" data-start="0" data-duration="6" data-track-index="0" style="position:absolute;inset:0;z-index:1;overflow:hidden;">' + "".join(videos_html) + '</div>'
    if 'id="vault-bg"' in html:
        html = re.sub(r'<div id="vault-bg"[\s\S]*?</div>', bloque, html, count=1)
    else:
        html = html.replace('<div id="bg-veil"', bloque + '\n    <div id="bg-veil"', 1)
    hook.write_text(html, encoding="utf-8")
    return usados


def asegurar_pregunta_detonadora(metadata: dict[str, Any], proyecto: Path) -> str:
    bloques = ("youtube", "tiktok", "instagram", "facebook")
    pregunta = str(dedup_manager.extraer_pregunta_detonadora(metadata) or "").strip()
    if not pregunta:
        cta_path = proyecto / "compositions" / "cta.html"
        if cta_path.is_file():
            texto = re.sub(r"<[^>]+>", " ", cta_path.read_text(encoding="utf-8", errors="replace"))
            pregunta = str(dedup_manager.extraer_pregunta_detonadora(html.unescape(texto)) or "").strip()
    if not pregunta:
        tema = str(metadata.get("tema") or metadata.get("titulo") or proyecto.name)
        tema = re.sub(r"[_-]+", " ", tema)
        tema = re.sub(r"\b20\d{6,14}\b", " ", tema)
        tema = re.sub(r"\s+", " ", tema).strip(" -|·")[:60].rstrip(" ,;:-")
        variantes = (
            f"¿Ya probaste {tema} o lo aplicarías de otra forma?",
            f"¿Cuál de estas opciones probarías primero con {tema}?",
            f"¿Tú cómo resolverías {tema} en tu próximo vuelo?",
        )
        for candidata in variantes:
            repetido, _ = dedup_manager.cta_repetida(candidata, excluir=proyecto.name)
            if not repetido:
                pregunta = candidata
                break
        pregunta = pregunta or variantes[-1]
    if not re.search(r"[?？]\s*$", pregunta):
        pregunta = f"{pregunta.rstrip(' .;:!')}?"
    if pregunta and not pregunta.startswith(("¿", "?")):
        pregunta = f"¿{pregunta}"
    pregunta = pregunta.strip()
    for bloque in bloques:
        config = metadata.get(bloque)
        if not isinstance(config, dict):
            continue
        config["pregunta_detonadora"] = pregunta
        desc = str(config.get("description") or "").rstrip()
        lineas = [linea.rstrip() for linea in desc.splitlines()]
        while lineas and not lineas[-1].strip():
            lineas.pop()
        if not lineas:
            config["description"] = pregunta
            continue
        if clave_pregunta(lineas[-1]) == clave_pregunta(pregunta):
            lineas[-1] = pregunta
        else:
            lineas.extend(["", pregunta])
        config["description"] = "\n".join(lineas).strip()
    return pregunta


def verificar_video(proyecto: Path, contexto: dict[str, Any] | None = None, estilo: dict[str, Any] | str | None = None) -> tuple[Path | None, str]:
    renders = proyecto / "renders"
    if not renders.is_dir():
        return None, f"Falta {renders}"

    metadata_path = renders / "metadata.json"
    if not metadata_path.is_file():
        return None, f"Falta {metadata_path}"

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, f"metadata.json inválido: {error}"
    if not isinstance(metadata, dict):
        return None, "metadata.json debe ser un objeto JSON"

    if estilo:
        try:
            estilos_video.aplicar_en_proyecto(proyecto, estilo)
        except (OSError, ValueError) as error_estilo:
            return None, f"No se pudo aplicar el estilo visual: {error_estilo}"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8", errors="replace"))

    metadata, _ = metadata_viral.normalizar_metadata(
        metadata,
        contexto=contexto,
        ruta=metadata_path,
        es_cta_repetido=lambda pregunta: dedup_manager.cta_repetida(pregunta, excluir=proyecto.name)[0],
    )

    for bloque in ("youtube", "tiktok", "instagram", "facebook"):
        config = metadata.get(bloque)
        if not isinstance(config, dict):
            return None, f"metadata.json falta el bloque {bloque}"
        if not str(config.get("description", "")).strip():
            return None, f"metadata.json {bloque}.description está vacía"
        if not config.get("hashtags"):
            return None, f"metadata.json {bloque}.hashtags está vacío"

    pregunta = asegurar_pregunta_detonadora(metadata, proyecto)
    ok_cta, detalle_cta = validar_cta_metadata(metadata, proyecto)
    if not ok_cta:
        return None, f"CTA obligatorio: {detalle_cta}"
    cta_path = proyecto / "compositions" / "cta.html"
    if cta_path.is_file():
        cta_html = cta_path.read_text(encoding="utf-8", errors="replace")
        reemplazo = html.escape(pregunta)
        cta_html = re.sub(
            r'(<div id="cta-question"[^>]*>)(.*?)(</div>)',
            lambda coincidencia: f"{coincidencia.group(1)}{reemplazo}{coincidencia.group(3)}",
            cta_html,
            count=1,
            flags=re.DOTALL,
        )
        cta_path.write_text(cta_html, encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"[CTA] {detalle_cta}")

    ok_ab, detalle_ab, modificado_ab = validar_experimento_ab(metadata)
    if not ok_ab:
        return None, f"Test A/B: {detalle_ab}"
    if modificado_ab:
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"[A/B] {detalle_ab}")

    video: Path | None = None
    nombre = str(metadata.get("video") or "").strip()
    if nombre:
        candidato = renders / nombre
        if candidato.is_file():
            video = candidato

    if video is None:
        mp4s = [ruta for ruta in renders.glob("*.mp4") if ruta.is_file()]
        if mp4s:
            video = max(mp4s, key=lambda ruta: ruta.stat().st_mtime)

    if video is None:
        return None, f"No hay MP4 en {renders}"

    tamano = video.stat().st_size
    if tamano <= VIDEO_MIN_BYTES:
        return None, f"MP4 demasiado pequeño: {video.name} ({tamano} bytes)"

    if metadata.get("video") != video.name:
        metadata["video"] = video.name
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    log(f"[verificación] MP4 {video.name} tamaño={tamano} bytes")
    return video, ""


def procesar_idea(
    idea: dict[str, Any],
    fecha: Any,
    indice: Any = None,
    total: Any = CUPO_DIARIO,
    notificar: bool = False,
    idioma: str = "es",
) -> tuple[bool, str, Path | None, str]:
    resultado_qa: dict[str, Any] = {}
    resultado: dict[str, Any] = {"ok": False, "detalle": "", "video": None, "proyecto": "", "publicacion": ""}
    video = None
    proyecto_nombre = nombre_proyecto(idea, fecha)
    proyecto = ROOT_DIR / proyecto_nombre
    resultado["proyecto"] = proyecto_nombre
    estilo = estilos_video.seleccionar(idea)
    fecha_iso = fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha)
    aporte_agentes = ""
    resultado_agentes: dict[str, Any] = {}
    if ejecutar_orquestador and os.getenv("AURA_MULTIAGENTE", "1") == "1":
        try:
            resultado_agentes = ejecutar_orquestador(
                idea,
                estilo,
                fecha_iso,
                notificar=notificar,
                modo_prueba=os.getenv("AURA_MODO_PRUEBA", "0") == "1",
            )
            aporte_agentes = str(resultado_agentes.get("prompt_agentes") or "")
            log(f"[agentes] 20 agentes ejecutados; caché={resultado_agentes.get('ruta', '')}")
            if notificar and notificar_urgente:
                avisos_criticos = []
                for informe in resultado_agentes.get("resultados", []):
                    if informe.get("estado") == "error":
                        avisos_criticos.append(f"{informe.get('id')}: {informe.get('error', '')}")
                    for aviso in informe.get("avisos", []):
                        if any(clave in str(aviso).lower() for clave in ("supera", "ffmpeg no", "no existe", "inválido")):
                            avisos_criticos.append(f"{informe.get('id')}: {aviso}")
                if avisos_criticos:
                    notificar_urgente(
                        "Fallo crítico en agentes locales",
                        " | ".join(avisos_criticos[:5]),
                        "La fábrica continúa con el fallback determinista y validará el MP4 antes de publicar.",
                    )
        except Exception as error_agentes:
            log(f"[agentes] fallback por error: {error_agentes}")
            resultado_agentes = {"error": f"{type(error_agentes).__name__}: {error_agentes}"}
    prompt = prompt_generacion(
        idea,
        proyecto_nombre,
        fecha,
        idioma=idioma,
        estilo=estilo,
        aporte_agentes=aporte_agentes,
    )
    tema = str(idea.get("titulo") or "")
    log(f"[idea {indice or idea.get('orden', '?')}/{total}] {tema}")
    log(f"[idea] proyecto={proyecto_nombre} estilo={estilo.get('id')} referencia={estilo.get('referencia')}")
    paleta_elegida = ""
    voz_elegida = ""
    try:
        paleta_elegida = paletas.datos_paleta(str(estilo.get("paleta") or ""))["nombre"]
    except (KeyError, TypeError, ValueError):
        paleta_elegida = str(estilo.get("nombre") or "")
    try:
        voz_elegida = voice_engine.elegir_voz(str(idea.get("categoria") or ""), tema, "", idioma)
    except Exception:
        voz_elegida = ""
    if notificar:
        notificador_telegram.notificar_etapa_idea(
            indice or idea.get("orden", "?"), total, tema, paleta_elegida, voz_elegida
        )

    valido, motivo = validar_idea(idea)
    if not valido:
        limpiar_temporales_proyecto(proyecto)
        return False, f"Tema descartado: {motivo}", None, proyecto_nombre
    log(f"[idea]validación OK: {motivo}")

    limpiar_temporales_proyecto(proyecto)
    try:
        resultado_recursos = descargar_recursos.asegurar(proyecto, estilo)
        fallos_recursos = len(resultado_recursos.get("fallos", []))
        log(f"[recursos] preparados={len(resultado_recursos.get('recursos', []))} fallos={fallos_recursos}")
    except (OSError, ValueError) as error_recursos:
        log(f"[recursos] fallback por error: {error_recursos}")

    def generar(intento: int) -> tuple[bool, Path | None, str]:
        comando = comando_opencode(prompt)
        ok, mensaje = ejecutar_comando(comando, ROOT_DIR, f"generacion[{intento}]", timeout=3600)
        if not ok:
            if notificar and intento > 1:
                notificador_telegram.notificar_alerta_reintento(tema, "generación", intento, mensaje)
            return False, None, mensaje
        try:
            paletas.guardar_en_proyecto(proyecto, idea.get("categoria", ""), tema)
        except (OSError, ValueError) as error_paleta:
            log(f"[paleta] no se pudo guardar: {error_paleta}")
        video, error = verificar_video(proyecto, idea, estilo)
        if video is None:
            if notificar and intento > 1:
                notificador_telegram.notificar_error_video(tema, error, "verificación de render", intento)
            return False, None, error
        if resultado_agentes:
            try:
                ruta_agentes = proyecto / "renders" / "agentes.json"
                ruta_agentes.parent.mkdir(parents=True, exist_ok=True)
                ruta_agentes.write_text(
                    json.dumps(resultado_agentes, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except (OSError, TypeError, ValueError) as error_agentes_json:
                log(f"[agentes] no se pudo guardar agentes.json: {error_agentes_json}")
        try:
            descargar_recursos.asegurar(proyecto, estilo, instalar_paquetes=False)
        except (OSError, ValueError) as error_recursos:
            log(f"[recursos] segundo pase con fallback: {error_recursos}")
        try:
            usados_vault = inyectar_media_vault(proyecto, str(idea.get("categoria") or ""), tema)
            if usados_vault:
                log(f"[vault] clips inyectados: {', '.join(usados_vault)}")
            else:
                log("[vault] sin clips de categoría; fallback vectorial")
        except Exception as e_vault:
            log(f"[vault] fallback por error: {e_vault}")
        try:
            carrusel = carousel_exporter.exportar(
                proyecto,
                titulo=tema,
                categoria=str(idea.get("categoria") or ""),
            )
            log(f"[carrusel] {len(carrusel['imagenes'])} imágenes 1080x1350 en {proyecto.name}/carrusel")
        except (OSError, ValueError, RuntimeError) as error_carrusel:
            log(f"[carrusel] no se pudo exportar: {error_carrusel}")
        return True, video, "video verificado"

    generado, video, mensaje_generacion = con_reintento(generar, "generacion")
    if not generado or video is None:
        return False, mensaje_generacion, None, proyecto_nombre

    sidecar_voz = leer_voz_sidecar(proyecto)
    duracion_audio = sidecar_voz.get("duracion_seg") or ""
    gancho_inicial = str(idea.get("gancho") or tema)
    if notificar:
        try:
            notificador_telegram.notificar_etapa_guion_voz(
                indice or idea.get("orden", "?"), total, tema, duracion_audio or "?", gancho_inicial
            )
        except Exception:
            pass

    try:
        normalizar_audio_mp4(video)
        log(f"[audio] loudnorm -14 LUFS aplicado a {video.name}")
    except Exception as error:
        log(f"[audio] loudnorm omitido: {error}")
    try:
        meta_path = proyecto / "renders" / "metadata.json"
        meta_cover = {}
        if meta_path.exists():
            try:
                meta_cover = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta_cover = {}
        portadas = cover_generator.generar_portadas_redes(proyecto, video, idea if isinstance(idea, dict) else {}, meta_cover)
        log(f"[cover] portadas generadas: {', '.join(Path(v).name for v in portadas.values())}")
    except Exception as error:
        log(f"[cover] generador avanzado falló, usando fallback: {error}")
        try:
            cover = extraer_cover_jpg(video)
            if cover:
                log(f"[cover] portada fallback: {cover}")
        except Exception:
            pass

    ok_qa = False
    detalle_qa = ""
    for intento_qa in (1, 2):
        try:
            ok_qa, detalle_qa, resultado_qa = qa_video.validar_video(proyecto, video)
        except Exception as error:
            ok_qa = False
            detalle_qa = f"{type(error).__name__}: {error}"
            resultado_qa = {}
        if ok_qa:
            break
        log(f"[QA] intento {intento_qa} falló: {detalle_qa}")
        if notificar:
            try:
                notificador_telegram.notificar_alerta_reintento(tema, "QA visual", intento_qa, detalle_qa)
            except Exception:
                pass
        if intento_qa == 1:
            # auto-ajuste de font/padding y 1 re-render de recuperación
            try:
                cfg_path = proyecto / "config.json"
                if cfg_path.exists():
                    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                    qa_cfg = cfg.setdefault("qa_ajustes", {})
                    qa_cfg["font_scale"] = round(float(qa_cfg.get("font_scale", 1.0)) * 0.94, 3)
                    qa_cfg["padding_extra_px"] = int(qa_cfg.get("padding_extra_px", 0)) + 12
                    qa_cfg["ultimo_motivo"] = detalle_qa[:300]
                    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    # aplicar ajuste básico en hook/captions
                    for comp in ["compositions/hook.html", "compositions/captions.html"]:
                        cp = proyecto / comp
                        if cp.exists():
                            h = cp.read_text(encoding="utf-8")
                            h = h.replace("font-size:88px", "font-size:82px").replace("font-size:58px", "font-size:54px")
                            h = h.replace("width:770px", "width:746px")
                            cp.write_text(h, encoding="utf-8")
            except Exception as e_adj:
                log(f"[QA] ajuste automático falló: {e_adj}")
            duracion_detectada = 0.0
            try:
                tecnico_detectado = resultado_qa.get("tecnico") or {}
                duracion_detectada = float(tecnico_detectado.get("duracion") or 0)
            except (AttributeError, TypeError, ValueError):
                duracion_detectada = 0.0
            if duracion_detectada > 60.0:
                try:
                    recorte = render_engine.recortar_duracion(proyecto, duracion_detectada, notificar=notificar)
                    log(f"[QA] recorte urgente aplicado: {recorte}")
                except Exception as error_recorte:
                    log(f"[QA] recorte urgente falló: {error_recorte}")
            try:
                resultado_render = render_engine.render(proyecto, notificar=notificar)
                ok_render = bool(resultado_render.get("ok"))
                msg_render = json.dumps(resultado_render, ensure_ascii=False, default=str)
            except Exception as error_render_engine:
                log(f"[QA] render_engine con fallback a npm: {error_render_engine}")
                ok_render, msg_render = ejecutar_comando(["npm", "run", "render"], proyecto, "qa-rerender", timeout=1200)
            if not ok_render:
                detalle_qa = f"{detalle_qa} | rerender: {msg_render}"
                break
            if notificar and notificar_urgente and any(
                clave in str(detalle_qa).lower() for clave in ("solap", "cortado", "fuera de zona", "supera 60")
            ):
                notificar_urgente(
                    "Texto o duración corregidos",
                    str(detalle_qa),
                    "Se aplicó reducción tipográfica, padding extra, recorte de duración cuando aplica y re-render inmediato.",
                )
            video, err_video = verificar_video(proyecto, idea, estilo)
            if video is None:
                detalle_qa = err_video or detalle_qa
                ok_qa = False
                break
    if not ok_qa:
        limpiar_temporales_proyecto(proyecto)
        try:
            notificador_telegram.enviar_mensaje(f"QA FAIL {tema}: {detalle_qa[:300]}")
        except Exception:
            pass
        return False, f"QA rechazó el video: {detalle_qa}", video, proyecto_nombre
    frames = resultado_qa.get("frames_qa") or []
    log(f"[QA] {detalle_qa} | frames={len(frames)}")
    peso_mb = round(video.stat().st_size / (1024 * 1024), 2)
    textos_encimados = 0 if resultado_qa.get("ok") else 1
    if notificar:
        notificador_telegram.notificar_etapa_render_qa(
            indice or idea.get("orden", "?"), total, tema, peso_mb, textos_encimados, detalle_qa
        )
    tecnico_qa = resultado_qa.get("tecnico") if isinstance(resultado_qa.get("tecnico"), dict) else {}
    try:
        duracion_video = float(tecnico_qa.get("duracion") or 0)
    except (TypeError, ValueError):
        duracion_video = 0.0
    def publicar(intento: int) -> tuple[bool, Any, str]:
        comando = [
            sys.executable,
            str(PUBLISHER_SCRIPT),
            str(proyecto),
            "--plataformas",
            PLATAFORMAS_FABRICA,
            "--auto-schedule",
        ]
        ok, mensaje = ejecutar_comando(
            comando,
            ROOT_DIR,
            f"publicacion[{intento}]",
            timeout=900,
            fallar_si=("[FATAL]",),
        )
        if not ok and notificar and intento > 1:
            notificador_telegram.notificar_alerta_reintento(tema, "programación", intento, mensaje)
        return ok, None, mensaje

    publicado, _, mensaje_publicacion = con_reintento(publicar, "publicacion")
    if not publicado:
        return False, mensaje_publicacion, video, proyecto_nombre

    horarios = horarios_agendados(video, proyecto_nombre, fecha)
    if notificar:
        yt_hora = str(horarios.get("youtube") or "")
        tt_hora = str(horarios.get("tiktok") or "")
        yt_url = str((resultado_qa.get("youtube_url") or "")) if isinstance(resultado_qa, dict) else ""
        # intentar leer URL de la cola/metadata
        try:
            cola = scheduler_manager.listar_tareas()
            for t in cola:
                if str(t.get("plataforma")) == "youtube" and proyecto_nombre in str(t.get("video") or ""):
                    yt_url = yt_url or str(((t.get("resultado") or {}).get("url")) or "")
                if str(t.get("plataforma")) == "tiktok" and proyecto_nombre in str(t.get("video") or ""):
                    pass
        except Exception:
            pass
        notificador_telegram.notificar_etapa_programado(
            indice or idea.get("orden", "?"),
            total,
            idea.get("titulo") or tema,
            yt_hora,
            yt_url,
            tt_hora,
        )
    detalle = f"proyecto={proyecto_nombre} video={video.name}"
    return True, detalle, video, proyecto_nombre

    

def main(argv: list[str] | None = None, notificar_inicio: bool = True) -> int:
    parser = argparse.ArgumentParser(description="Produce y programa los videos diarios que falten.")
    parser.add_argument("--dry-run", action="store_true", help="Muestra cupos e ideas sin generar videos")
    parser.add_argument("--fecha", help="Fecha objetivo YYYY-MM-DD; por defecto mañana en America/Mexico_City")
    parser.add_argument("--idioma", choices=("es", "en"), default="es", help="Idioma de exportación del guion y la voz")
    args = parser.parse_args(argv)

    if args.fecha:
        try:
            fecha = datetime.strptime(args.fecha, "%Y-%m-%d").date()
        except ValueError:
            print("[ERROR] --fecha debe usar YYYY-MM-DD", file=sys.stderr)
            return 1
    else:
        fecha = (scheduler_manager.ahora_local() + timedelta(days=1)).date()

    log("=== Inicio fábrica diaria ===")
    agendados = contar_agendados_para(fecha)
    faltantes = max(0, CUPO_DIARIO - agendados)
    notificar = not args.dry_run
    log(f"Fecha objetivo={fecha.isoformat()} agendados={agendados} faltantes={faltantes}")

    if faltantes == 0:
        log("Cupo completo; no se produce nada")
        return 0

    if notificar and notificar_inicio:
        notificador_telegram.notificar_inicio_lote({fecha.isoformat(): faltantes}, fecha.isoformat())

    dedup_manager.indexar(escribir=True, ttl_segundos=900)
    try:
        if sfx_generator is None:
            raise RuntimeError("módulo sfx_generator no disponible")
        creados = sfx_generator.ensure_sfx()
        if creados:
            log(f"[SFX] catálogo asegurado: {len(creados)} archivos")
    except Exception as e:
        log(f"[SFX] no se pudo asegurar catálogo: {e}")
    indice_vault = vault_indexer.indexar(escribir=not args.dry_run)
    log(f"[bóveda] {indice_vault['total_clips']} clips indexados")

    plan = None
    if planificador_semanal is not None:
        try:
            plan = planificador_semanal.cargar_plan()
            cubre = bool(plan and any(d.get("fecha") == fecha.isoformat() for d in plan.get("dias", [])))
            if not plan or not cubre:
                log("[plan] generando plan semanal")
                plan = planificador_semanal.generar_plan(
                    fecha, forzar=False, notificar=notificar, escribir=not args.dry_run
                )
            planificador_semanal.evaluar_cambio_viral_ultimo_minuto(
                fecha.isoformat(), plan, notificar=notificar, escribir=not args.dry_run
            )
            plan = planificador_semanal.cargar_plan() or plan
        except Exception as e_plan:
            log(f"[plan] error no bloqueante: {e_plan}")
            plan = planificador_semanal.cargar_plan() if planificador_semanal else None

    datos = cargar_ideas()
    producidas = 0
    recargas = 0
    intentados: set[str] = set()

    while producidas < faltantes and recargas <= 2:
        pendientes_plan = []
        if planificador_semanal is not None:
            plan = planificador_semanal.cargar_plan() or plan
            for idea_p in planificador_semanal.obtener_ideas_para_fecha(fecha.isoformat(), plan):
                if idea_p.get("estado") in {"completada", "fallida"}:
                    continue
                if normalizar(idea_p.get("titulo")) in intentados:
                    continue
                pendientes_plan.append(dict(idea_p))
        pendientes = pendientes_plan or sorted(
            [
                idea
                for idea in datos["ideas"]
                if isinstance(idea, dict)
                and idea.get("estado") not in {"completada", "fallida"}
                and normalizar(idea.get("titulo")) not in intentados
            ],
            key=lambda idea: int(idea.get("orden", 99)),
        )

        if args.dry_run:
            for idea in pendientes[:faltantes]:
                log(f"[DRY-RUN] {idea.get('categoria', '')}: {idea.get('titulo', '')}")
            log("=== Fin fábrica diaria (dry-run) ===")
            return 0

        if not pendientes:
            log("No hay ideas pendientes disponibles")
            break

        for idea in pendientes:
            if producidas >= faltantes:
                break

            titulo = normalizar(idea.get("titulo"))
            if not titulo or titulo in intentados:
                continue
            intentados.add(titulo)

            ok, detalle, video, proyecto = procesar_idea(
                idea, fecha, producidas + 1, faltantes, notificar, idioma=args.idioma
            )
            idea["intentos"] = int(idea.get("intentos", 0)) + 1
            estado_final = "completada" if ok else "fallida"
            if ok:
                idea["estado"] = "completada"
                idea["proyecto"] = proyecto
                idea["video"] = str(video) if video else ""
                idea["fecha_produccion"] = fecha.isoformat()
                idea["completada_en"] = scheduler_manager.iso_utc(datetime.now(scheduler_manager.ZONA))
                idea.pop("error", None)
                producidas += 1
                log(f"[OK] {detalle}")
            else:
                idea["estado"] = "fallida"
                idea["error"] = detalle
                idea["fallida_en"] = scheduler_manager.iso_utc(datetime.now(scheduler_manager.ZONA))
                log(f"[FALLO RECUPERABLE] {detalle}; se prueba el siguiente tema viral")
                if notificar:
                    try:
                        notificador_telegram.notificar_error_video(idea.get("titulo") or titulo, detalle, "producción", None, producidas < faltantes)
                    except Exception:
                        pass
            try:
                if planificador_semanal is not None:
                    planificador_semanal.actualizar_estado_idea(fecha.isoformat(), idea.get("titulo", ""), estado_final, detalle, proyecto or "", str(video) if video else "")
            except Exception as e_sync:
                log(f"[plan] sync estado: {e_sync}")
            try:
                for it in datos.get("ideas", []):
                    if isinstance(it, dict) and normalizar(it.get("titulo")) == normalizar(idea.get("titulo")):
                        it.update({k: v for k, v in idea.items() if k in {"estado","proyecto","video","fecha_produccion","completada_en","fallida_en","error","intentos"}})
            except Exception:
                pass
            guardar_ideas(datos)

        if producidas >= faltantes:
            break
        if recargas >= 2:
            break

        recargas += 1
        log(f"Ideas agotadas por fallos; recarga {recargas}/2 de tendencias")
        try:
            codigo_tendencias = trend_hunter.main(["--output", str(IDEAS_PATH), "--fecha", fecha.isoformat()])
            if codigo_tendencias != 0:
                log(f"Fallo al consultar tendencias: exit={codigo_tendencias}")
        except Exception as error:
            log(f"Fallo al consultar tendencias: {type(error).__name__}: {error}")
        datos = cargar_ideas()

    log(f"Resumen: producidas={producidas} faltantes={faltantes} recargas={recargas}")
    log("=== Fin fábrica diaria ===")
    return 0 if producidas == faltantes else 1


if __name__ == "__main__":
    raise SystemExit(main())
