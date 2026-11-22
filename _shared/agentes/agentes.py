from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "_shared"
FACTORY = SHARED / "factory"
PUBLISHER = SHARED / "publisher"
for ruta in (FACTORY, PUBLISHER):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))

try:
    from .contratos import Contexto, ResultadoAgente, resultado
    from .memoria import CACHE, escribir_texto, leer_json, buscar_binario
except ImportError:
    from contratos import Contexto, ResultadoAgente, resultado
    from memoria import CACHE, escribir_texto, leer_json, buscar_binario

try:
    import estilos_video
except Exception:
    estilos_video = None

try:
    from .herramientas_externas import resumen as herramientas_externas
except ImportError:
    try:
        from herramientas_externas import resumen as herramientas_externas
    except ImportError:
        herramientas_externas = None

try:
    import metadata_viral
except Exception:
    metadata_viral = None

try:
    import voice_engine
except Exception:
    voice_engine = None


class Agente:
    id = "A00"
    nombre = "Agente base"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        return resultado(self.id, self.nombre)


def _texto(contexto: Contexto, clave: str, defecto: str = "") -> str:
    return contexto.texto(clave, defecto)


def _titulo(contexto: Contexto) -> str:
    return _texto(contexto, "titulo") or _texto(contexto, "tema") or "este tema"


def _limpio(valor: Any, maximo: int = 220) -> str:
    texto = re.sub(r"\s+", " ", str(valor or "")).strip()
    return texto[:maximo]


def _reglas(contexto: Contexto) -> dict[str, Any]:
    if estilos_video is None:
        return {}
    try:
        return estilos_video.reglas_referencia(contexto.estilo)
    except Exception:
        return {}


def _herramientas() -> dict[str, Any]:
    if herramientas_externas is None:
        return {}
    try:
        return herramientas_externas()
    except Exception:
        return {}


def _carpetas_broll(contexto: Contexto) -> list[str]:
    if estilos_video is None:
        return []
    try:
        return list(estilos_video.carpetas_broll(contexto.estilo))
    except Exception:
        return []


class AgenteIdeasVirales(Agente):
    id = "A01"
    nombre = "Investigador de ideas virales"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        titulo = _titulo(contexto)
        categoria = _texto(contexto, "categoria", "general")
        angulos = [
            {"angulo": "error comun", "gancho": f"El error con {titulo} que casi nadie corrige", "fuerza": 9},
            {"angulo": "resultado directo", "gancho": f"Así se resolvería {titulo} en menos de un minuto", "fuerza": 8},
            {"angulo": "comparativa", "gancho": f"Antes y después de {titulo}: la diferencia está en un detalle", "fuerza": 7},
        ]
        return resultado(
            self.id,
            self.nombre,
            {"titulo": titulo, "categoria": categoria, "angulos": angulos, "seleccion": angulos[0]["gancho"]},
        )


class AgenteGanchoRetencion(Agente):
    id = "A02"
    nombre = "Diseñador de gancho y retención"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        titulo = _titulo(contexto)
        gancho = _texto(contexto, "gancho") or f"No hagas lo obvio con {titulo}."
        variantes = [
            {"texto": _limpio(gancho, 90), "duracion_s": 2.6, "retencion": 9},
            {"texto": f"Escucha esto antes de tocar {_limpio(titulo, 50)}.", "duracion_s": 2.9, "retencion": 8},
            {"texto": f"Hay un detalle en {_limpio(titulo, 50)} que cambia todo.", "duracion_s": 3.0, "retencion": 8},
        ]
        return resultado(self.id, self.nombre, {"variantes": variantes, "elegida": variantes[0]})


class AgenteGuionista(Agente):
    id = "A03"
    nombre = "Guionista de estructura cerrada"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        titulo = _titulo(contexto)
        bloques = [
            {"inicio_s": 0.0, "fin_s": 3.0, "seccion": "gancho", "texto": f"No sigas haciendo lo obvio con {titulo}."},
            {"inicio_s": 3.0, "fin_s": 10.0, "seccion": "contexto", "texto": "El problema casi siempre está en el ajuste previo, no en el resultado final."},
            {"inicio_s": 10.0, "fin_s": 30.0, "seccion": "desarrollo", "texto": "Primero revisa la configuración base; después cambia una sola variable y observa el efecto."},
            {"inicio_s": 30.0, "fin_s": 45.0, "seccion": "giro", "texto": "Cuando el ajuste correcto aparece, el resultado se nota de inmediato y el proceso se vuelve repetible."},
            {"inicio_s": 45.0, "fin_s": 57.0, "seccion": "cierre", "texto": "Guarda este orden y aplícalo la próxima vez; la diferencia está en el método."},
        ]
        return resultado(
            self.id,
            self.nombre,
            {"bloques": bloques, "duracion_s": 57.0, "dentro_de_limite": 57.0 <= contexto.duracion_maxima_s},
        )


class AgenteLocucion(Agente):
    id = "A04"
    nombre = "Director de locución y voz"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        voz = ""
        if voice_engine is not None:
            try:
                voz = voice_engine.elegir_voz(
                    _texto(contexto, "categoria"),
                    _titulo(contexto),
                    _texto(contexto, "resumen"),
                    contexto.idioma,
                )
            except Exception:
                voz = ""
        return resultado(
            self.id,
            self.nombre,
            {
                "voz": str(voz or "edge-tts/es-MX"),
                "velocidad_wpm": 152,
                "tono": "directo, cercano, sin dramatismo",
                "pausas_s": [0.25, 0.35, 0.4],
                "pronunciacion": ["DJI", "FPV", "configuración"],
                "regla": "La voz manda: el montaje se ajusta a la duración real del audio.",
            },
        )


class AgenteCreativo(Agente):
    id = "A05"
    nombre = "Dirección creativa"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        estilo_id = str(contexto.estilo.get("id") or contexto.estilo.get("estilo_id") or "")
        familia = str(contexto.estilo.get("familia") or "")
        return resultado(
            self.id,
            self.nombre,
            {
                "estilo_id": estilo_id,
                "familia": familia,
                "concepto": f"Mostrar {_titulo(contexto)} como un proceso visible, no como una explicación abstracta.",
                "giro": "Un cambio pequeño al final demuestra por qué el orden importa.",
                "identidad": "Directo, auténtico, sin clichés de plantilla ni prompts genéricos.",
                "recetas_disponibles": list((_herramientas().get("recetas") or {}).keys()),
            },
        )


class AgenteInspectorReferencias(Agente):
    id = "A06"
    nombre = "Inspector de referencias medidas"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        reglas = _reglas(contexto)
        metrica = reglas.get("metrica") or {}
        avisos = [] if reglas else ["Sin reglas de referencia; se aplica cadencia segura por defecto."]
        return resultado(
            self.id,
            self.nombre,
            {
                "estilo_id": reglas.get("estilo_id", ""),
                "metrica": metrica,
                "corte_s": reglas.get("corte_s", [1.2, 2.4]),
                "pulso_bpm": reglas.get("pulso_bpm", [95, 120]),
                "zonas": reglas.get("zonas", "superior 200-340 / central 380-1260 / inferior libre desde 1320"),
                "audio": reglas.get("audio", "voz limpia, música baja y SFX en cortes"),
                "luz": reglas.get("luz", "contraste alto y una fuente dominante"),
                "movimiento": reglas.get("movimiento", "cámara viva con recortes cortos"),
                "contrato_de_escena": "Cada fotograma es una función pura de t; voz y tiempos reales mandan sobre la imagen.",
            },
            avisos,
        )


class AgenteCoherenciaVisual(Agente):
    id = "A07"
    nombre = "Guardián de coherencia visual"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        estilo_id = str(contexto.estilo.get("id") or contexto.estilo.get("estilo_id") or "")
        validos = set((estilos_video.ESTILOS if estilos_video else {}))
        avisos = [] if estilo_id in validos else [f"Estilo fuera del catálogo: {estilo_id or 'sin ID'}"]
        return resultado(
            self.id,
            self.nombre,
            {
                "coherente": not avisos,
                "estilo_id": estilo_id,
                "paleta": contexto.estilo.get("paleta", ""),
                "ajustes": [
                    "Aplicar data-style en html y cada #root",
                    "Respetar zonas 200-340, 380-1260 y dejar libre y>1320",
                    "No mezclar paletas de otras referencias",
                ],
            },
            avisos,
        )


class AgenteRecursos(Agente):
    id = "A08"
    nombre = "Buscador de recursos y B-roll"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        indice = leer_json(SHARED / "media_vault" / "index.json", {}) or {}
        total = int(indice.get("total_clips", 0) or 0)
        carpetas = _carpetas_broll(contexto)
        return resultado(
            self.id,
            self.nombre,
            {
                "carpetas_preferidas": carpetas,
                "clips_disponibles": total,
                "plan": [
                    {"seccion": "gancho", "recurso": "vector/SVG propio"},
                    {"seccion": "desarrollo", "recurso": "clip de bóveda o diagrama animado"},
                    {"seccion": "giro", "recurso": "recorte con zoom y acento de color"},
                ],
                "faltantes": ["Usar vector propio si no hay clip de categoría"],
            },
        )


class AgenteDirectorCamara(Agente):
    id = "A09"
    nombre = "Director de cámara y encuadre"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        planos = [
            {"t_s": 0.0, "plano": "primer plano", "movimiento": "push-in corto", "zona": "central"},
            {"t_s": 3.0, "plano": "plano medio", "movimiento": "tracking lateral", "zona": "central"},
            {"t_s": 10.0, "plano": "detalle", "movimiento": "zoom animado", "zona": "central"},
            {"t_s": 30.0, "plano": "comparativa", "movimiento": "split suave", "zona": "central"},
            {"t_s": 45.0, "plano": "cierre", "movimiento": "pull-out", "zona": "central"},
        ]
        return resultado(self.id, self.nombre, {"planos": planos, "seguridad": "La acción principal nunca baja de y=1260."})


class AgenteEditor(Agente):
    id = "A10"
    nombre = "Editor de ritmo y sonido"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        reglas = _reglas(contexto)
        rango = reglas.get("corte_s") or [1.2, 2.4]
        corte = float(rango[1] if isinstance(rango, list) and rango else 2.0)
        cortes = [round(inicio, 1) for inicio in _frange(1.2, 57.0, max(0.8, corte))]
        return resultado(
            self.id,
            self.nombre,
            {
                "cortes_s": cortes,
                "transiciones": ["cut", "flash", "match-cut"],
                "musica": "cama continua, baja bajo la voz",
                "sfx": ["click en cada cambio", "whoosh suave en el giro"],
                "pulso_bpm": reglas.get("pulso_bpm", [95, 120]),
            },
        )


def _frange(inicio: float, fin: float, paso: float) -> list[float]:
    valores = []
    actual = inicio
    while actual < fin and len(valores) < 80:
        valores.append(actual)
        actual += paso
    return valores


class AgenteDisenador(Agente):
    id = "A11"
    nombre = "Diseñador de tipografía y composición"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        return resultado(
            self.id,
            self.nombre,
            {
                "zonas": {
                    "superior": [200, 340],
                    "central": [380, 1260],
                    "libre_desde": 1320,
                },
                "tipografia": {"titulo_px": 76, "subtitulo_px": 44, "cuerpo_px": 34, "line_height": 1.16},
                "contraste": "Texto claro sobre superficie oscura o texto oscuro sobre superficie clara según estilo",
                "reglas": ["Una idea por bloque", "Máximo dos líneas por subtítulo", "Sin sombras que imiten texto duplicado"],
                "sistemas_disponibles": [lib["nombre"] for lib in (_herramientas().get("bibliotecas") or []) if lib.get("disponible")],
                "diagramas": "Usar D3 + Flubber para HUD y morphing; el texto nunca baja de y=1320.",
                "sin_solapes": True,
            },
        )


class AgenteCartoon(Agente):
    id = "A12"
    nombre = "Generador de personajes y escenas 2D/3D"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        familia = str(contexto.estilo.get("familia") or "")
        estilo_id = str(contexto.estilo.get("id") or "")
        requiere = familia in {"relato", "cronica", "historia", "comparativa"} or estilo_id in {"1000350669", "1000350999"}
        if not requiere:
            return resultado(
                self.id,
                self.nombre,
                {"requerido": False, "motor": "no requerido", "razon": "El estilo asignado no pide personaje recurrente"},
            )
        acento = str(contexto.estilo.get("paleta", {}).get("accent", "#16d98a") if isinstance(contexto.estilo.get("paleta"), dict) else "#16d98a")
        fondo = str(contexto.estilo.get("paleta", {}).get("ground", "#0e1f18") if isinstance(contexto.estilo.get("paleta"), dict) else "#0e1f18")
        slug = re.sub(r"[^a-z0-9]+", "-", _titulo(contexto).lower()).strip("-")[:40] or "escena"
        destino = CACHE / "cartoon" / f"{estilo_id or 'sin-estilo'}-{slug}.svg"
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">'
            f'<rect width="1080" height="1920" fill="{html.escape(fondo)}"/>'
            f'<circle cx="540" cy="720" r="300" fill="{html.escape(acento)}" opacity="0.22"/>'
            f'<rect x="120" y="520" width="840" height="520" rx="80" fill="#ffffff" opacity="0.08"/>'
            f'<path d="M180 1260 L900 1260 L820 1500 L260 1500 Z" fill="{html.escape(acento)}" opacity="0.35"/>'
            "</svg>"
        )
        escribir_texto(destino, svg)
        return resultado(
            self.id,
            self.nombre,
            {
                "requerido": True,
                "motor": "svg2d",
                "ruta": str(destino),
                "personajes": ["protagonista vectorial simple"],
                "escenas": ["plano abierto", "detalle de gesto", "cierre con variación de color"],
                "herramientas": [lib["nombre"] for lib in (_herramientas().get("bibliotecas") or []) if lib.get("disponible")],
                "tecnica": "SVG con tinta que hierve, partes separadas, squash y settle; modelo 3D con Three.js solo si no existe en la biblioteca local.",
            },
        )


class AgenteInspectorCartoon(Agente):
    id = "A13"
    nombre = "Inspector de consistencia de personajes"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        generador = contexto.artefactos.get("A12") or {}
        ruta = generador.get("ruta", "")
        problemas = []
        if not generador.get("requerido"):
            return resultado(self.id, self.nombre, {"aplicable": False, "problemas": []})
        archivo = Path(ruta) if ruta else Path("")
        if not archivo.is_file():
            problemas.append("No se generó el SVG de la escena")
        else:
            contenido = archivo.read_text(encoding="utf-8", errors="replace")
            if "<svg" not in contenido:
                problemas.append("SVG inválido")
            if "<text" in contenido:
                problemas.append("SVG contiene texto rasterizable; usar texto HTML separado")
        return resultado(
            self.id,
            self.nombre,
            {
                "aplicable": True,
                "problemas": problemas,
                "consistente": not problemas,
                "checks": [
                    "Tinta con tres variantes de boil intercambiadas cada dos fotogramas",
                    "Cuerpo, ojos, boca y extremidades como grupos separados",
                    "Sin Math.random, sin reloj y sin estado entre fotogramas",
                ],
            },
            problemas,
        )


class AgenteQATecnico(Agente):
    id = "A14"
    nombre = "QA técnico de entradas"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        duracion = float(contexto.artefactos.get("duracion_real_s", 0) or 0)
        texto = " ".join(str(contexto.idea.get(clave, "")) for clave in ("titulo", "resumen", "gancho"))
        espanol_detectado = any(palabra in texto.lower() for palabra in ("el", "la", "los", "las", "con", "de", "para"))
        ffmpeg = buscar_binario("ffmpeg")
        avisos = []
        if not ffmpeg:
            avisos.append("ffmpeg no encontrado en PATH")
        if not espanol_detectado:
            avisos.append("No se detectaron marcadores de español en la entrada")
        if duracion and duracion > contexto.duracion_maxima_s:
            avisos.append(f"Duración real {duracion:.1f} s supera {contexto.duracion_maxima_s:.1f} s")
        return resultado(
            self.id,
            self.nombre,
            {
                "duracion_real_s": duracion,
                "limite_s": contexto.duracion_maxima_s,
                "ffmpeg": bool(ffmpeg),
                "espanol": espanol_detectado,
                "aprobado": not avisos,
            },
            avisos,
        )


class AgenteSupervisorVisual(Agente):
    id = "A15"
    nombre = "Supervisor de calidad visual"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        frames = contexto.artefactos.get("frames") or []
        if not frames:
            return resultado(
                self.id,
                self.nombre,
                {
                    "etapa": "pre-render",
                    "requiere_revision": True,
                    "checklist": [
                        "CERO textos encimados",
                        "CERO etiquetas cortadas",
                        "Zona inferior y>1320 libre",
                        "Cambio de plano cada 0.6-1.5 s",
                        "Contraste suficiente en las cuatro esquinas",
                        "Cada fotograma es función pura de t, sin aleatoriedad ni estado previo",
                        "Sin CDN, sin fetch remoto y sin servicios de pago durante el render",
                    ],
                },
            )
        problemas = []
        for frame in frames:
            ruta = Path(frame)
            if not ruta.is_file() or ruta.stat().st_size < 10000:
                problemas.append(f"Frame inválido: {ruta.name}")
        return resultado(
            self.id,
            self.nombre,
            {"etapa": "post-render", "frames": len(frames), "problemas": problemas, "requiere_revision": bool(problemas)},
            problemas,
        )


class AgenteSEO(Agente):
    id = "A16"
    nombre = "Especialista en metadata y portada"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        contexto_seo = {
            "titulo": _titulo(contexto),
            "tema": _titulo(contexto),
            "categoria": _texto(contexto, "categoria"),
            "resumen": _texto(contexto, "resumen"),
            "gancho": _texto(contexto, "gancho"),
        }
        normalizado = {}
        if metadata_viral is not None:
            try:
                normalizado, _ = metadata_viral.normalizar_metadata({}, contexto_seo)
            except Exception:
                normalizado = {}
        return resultado(
            self.id,
            self.nombre,
            {
                "titulo": _titulo(contexto),
                "pregunta_detonadora": normalizado.get("pregunta_detonadora", "¿Cuál de estos ajustes cambia más el resultado?"),
                "hashtags": normalizado.get("tiktok", {}).get("hashtags", []),
                "portada": {"texto": _limpio(_titulo(contexto), 42), "estilo": contexto.estilo.get("id", "")},
            },
        )


class AgenteVerificadorFinal(Agente):
    id = "A17"
    nombre = "Verificador final de video"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        video = contexto.artefactos.get("video", "")
        if not video:
            return resultado(self.id, self.nombre, {"aplicable": False, "motivo": "Sin MP4 aún"}, ["Sin video para verificar"])
        archivo = Path(video)
        if not archivo.is_file():
            return resultado(self.id, self.nombre, {"aplicable": True, "valido": False}, [f"No existe {archivo}"])
        ffprobe = buscar_binario("ffprobe")
        if not ffprobe:
            return resultado(self.id, self.nombre, {"aplicable": True, "valido": False}, ["ffprobe no disponible"])
        try:
            proceso = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(archivo)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            datos = json.loads(proceso.stdout or "{}")
            duracion = float((datos.get("format") or {}).get("duration", 0) or 0)
            tipos = {stream.get("codec_type") for stream in datos.get("streams", [])}
            valido = bool(duracion <= contexto.duracion_maxima_s and "video" in tipos and "audio" in tipos)
            return resultado(
                self.id,
                self.nombre,
                {"aplicable": True, "valido": valido, "duracion_s": duracion, "streams": sorted(str(tipo) for tipo in tipos if tipo)},
                [] if valido else [f"Duración {duracion:.1f} s o streams incompletos"],
            )
        except Exception as error:
            return resultado(self.id, self.nombre, {"aplicable": True, "valido": False}, [f"{type(error).__name__}: {error}"])


class AgenteAprendizaje(Agente):
    id = "A18"
    nombre = "Analista de aprendizaje y analítica"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        reglas = []
        ruta_analytics = ROOT / "_shared" / "factory" / "analytics_feedback.json"
        datos = leer_json(ruta_analytics, {}) or {}
        if datos:
            reglas.append({"fuente": "analytics_feedback.json", "regla": "Repetir ganchos con mejor retención y descartar los de peor cierre."})
        else:
            reglas.append({"fuente": "base", "regla": "Priorizar ganchos de tres segundos y cierre sin cola muerta."})
        reglas.append({"fuente": "referencias", "regla": "Mantener cortes entre 0.6 y 1.5 s y pulso cercano al de la referencia asignada."})
        return resultado(self.id, self.nombre, {"reglas": reglas, "actualiza": "renders/agentes.json"})


class AgenteArquitecto(Agente):
    id = "A19"
    nombre = "Arquitecto de capacidades y agentes"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        propuestas = []
        if "frames" not in contexto.artefactos:
            propuestas.append(
                {
                    "clase": "AgenteOCRSolapes",
                    "nombre_archivo": "agente_ocr_solapes.py",
                    "motivo": "Falta inspección OCR post-render de textos encimados o cortados",
                    "descripcion": "Detecta bloques de texto solapados y zonas prohibidas en frames de QA.",
                }
            )
        if "duracion_real_s" not in contexto.artefactos:
            propuestas.append(
                {
                    "clase": "AgenteRecorteAutomatico",
                    "nombre_archivo": "agente_recorte_automatico.py",
                    "motivo": "Falta recorte automático cuando la voz empuja el video sobre 60 s",
                    "descripcion": "Reescala datos de duración y vuelve a renderizar antes de publicar.",
                }
            )
        for propuesta in propuestas:
            propuesta["requiere_confirmacion"] = True
        return resultado(
            self.id,
            self.nombre,
            {"propuestas": propuestas, "politica": "Crear agentes nuevos solo tras confirmación por Telegram"},
        )


class AgenteAuditorPoda(Agente):
    id = "A20"
    nombre = "Auditor de agentes y poda segura"

    def run(self, contexto: Contexto) -> ResultadoAgente:
        candidatos = [
            {
                "id": "A07",
                "razon": "Comparte validación con A14 y A15",
                "riesgo": "medio",
                "requiere_confirmacion": True,
            },
            {
                "id": "A13",
                "razon": "Solo aplica a estilos con personaje recurrente",
                "riesgo": "bajo",
                "requiere_confirmacion": True,
            },
        ]
        return resultado(
            self.id,
            self.nombre,
            {
                "candidatos": candidatos,
                "politica": "Nunca podar sin confirmación por Telegram y respaldo previo",
                "accion_automatica": "ninguna",
            },
        )


def crear_agente_desde_spec(spec: dict[str, Any]) -> str:
    clase = re.sub(r"[^A-Za-z0-9_]", "", str(spec.get("clase", "")))
    nombre_archivo = re.sub(r"[^A-Za-z0-9_.-]", "", str(spec.get("nombre_archivo", "")))
    if not clase or not nombre_archivo or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", clase):
        raise ValueError("Especificación de agente inválida")
    if not nombre_archivo.endswith(".py"):
        nombre_archivo += ".py"
    destino = Path(__file__).resolve().parent / "generados" / nombre_archivo
    if destino.exists():
        return str(destino)
    identidad = re.sub(r"(?<!^)(?=[A-Z])", "-", clase).lower()
    contenido = (
        "from __future__ import annotations\n\n"
        "from contratos import Contexto, ResultadoAgente, resultado\n\n\n"
        "class Agente:\n"
        '    id = "A00"\n'
        '    nombre = "Agente base"\n\n'
        "    def run(self, contexto: Contexto) -> ResultadoAgente:\n"
        "        return resultado(self.id, self.nombre)\n\n\n"
        f"class {clase}(Agente):\n"
        f'    id = "{identidad}"\n'
        f'    nombre = "{_limpio(spec.get("descripcion", clase), 80)}"\n\n'
        "    def run(self, contexto: Contexto) -> ResultadoAgente:\n"
        "        return resultado(self.id, self.nombre, {'especificacion': ESPECIFICACION})\n"
    )
    contenido = contenido.replace("ESPECIFICACION", repr(spec))
    escribir_texto(destino, contenido)
    return str(destino)


AGENTES: list[Agente] = [
    AgenteIdeasVirales(),
    AgenteGanchoRetencion(),
    AgenteGuionista(),
    AgenteLocucion(),
    AgenteCreativo(),
    AgenteInspectorReferencias(),
    AgenteCoherenciaVisual(),
    AgenteRecursos(),
    AgenteDirectorCamara(),
    AgenteEditor(),
    AgenteDisenador(),
    AgenteCartoon(),
    AgenteInspectorCartoon(),
    AgenteQATecnico(),
    AgenteSupervisorVisual(),
    AgenteSEO(),
    AgenteVerificadorFinal(),
    AgenteAprendizaje(),
    AgenteArquitecto(),
    AgenteAuditorPoda(),
]


def obtener_agente(id_agente: str) -> Agente | None:
    for agente in AGENTES:
        if agente.id == id_agente:
            return agente
    return None
