from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

DURACION_MAXIMA_S = 60.0

REGLAS_REFERENCIA: dict[str, dict[str, Any]] = {
    "1000350669": {
        "archivo": "1000350669.mp4",
        "metrica": {"duracion_s": 15.125, "cortes": 6, "texto": 30, "bpm": 143.6, "silencio": 0.126, "brillo": 58.1, "movimiento": 61.8},
        "corte_s": (1.5, 3.0),
        "pulso_bpm": (138, 148),
        "texto": "Palabras sueltas de una a tres palabras, máximo dos bloques simultáneos, tipografía condensada en mayúsculas y recortes enmascarados; sin frases largas.",
        "zonas": "Superior y central; inferior libre.",
        "audio": "Cama rítmica continua con golpe seco en cada cambio; sin silencio inicial.",
        "luz": "Gris neutro, alto contraste y viñeta ligera.",
        "movimiento": "Alto: barridos, rejillas y etiquetas que entran a ritmo.",
    },
    "1000350985": {
        "archivo": "1000350985.mp4",
        "metrica": {"duracion_s": 260.552, "cortes": 31, "texto": 53, "bpm": 107.7, "silencio": 0.032, "brillo": 63.9, "movimiento": 58.3},
        "corte_s": (6.0, 9.0),
        "pulso_bpm": (100, 115),
        "texto": "Subtítulo narrativo en dos líneas, cartel de fecha y lugar, un dato por tarjeta y máximo dos bloques simultáneos.",
        "zonas": "Superior para fecha y lugar, inferior para subtítulo; central para la reconstrucción.",
        "audio": "Narración cálida sobre cama baja; sin pausas mayores a 0.3 s.",
        "luz": "Contraste moderado, tonos fríos y carteles muy legibles.",
        "movimiento": "Bloques que se arman y desarman con parallax suave.",
    },
    "1000350986": {
        "archivo": "1000350986.mp4",
        "metrica": {"duracion_s": 173.5, "cortes": 174, "texto": 37, "bpm": 107.7, "silencio": 0.016, "brillo": 128.7, "movimiento": 73.4},
        "corte_s": (0.8, 1.3),
        "pulso_bpm": (105, 120),
        "texto": "Etiquetas de dos a cuatro palabras en una sola línea; un rótulo por corte y nunca texto superior e inferior a la vez.",
        "zonas": "Central para la acción e inferior para el rótulo; superior solo para alerta breve.",
        "audio": "Cama de tensión e impactos en cada corte; voz corta y silencio por debajo del 2%.",
        "luz": "Escena muy luminosa, frío intenso y acentos rojos de peligro.",
        "movimiento": "Muy alto: cámara baja, polvo y seguimiento rápido.",
    },
    "1000350987": {
        "archivo": "1000350987.mp4",
        "metrica": {"duracion_s": 80.736, "cortes": 4, "texto": 58, "bpm": 112.3, "silencio": 0.053, "brillo": 27.3, "movimiento": 31.9},
        "corte_s": (10.0, 16.0),
        "pulso_bpm": (105, 120),
        "texto": "HUD con tres datos aislados, una cifra relevante por plano y etiquetas centrales breves.",
        "zonas": "Central para el HUD, inferior para una conclusión; superior solo para el título.",
        "audio": "Cama técnica limpia, voz pausada y un clic único al congelar el instante.",
        "luz": "Fondo oscuro con datos brillantes y movimiento de cámara bajo.",
        "movimiento": "Cámara lenta, vectores y microzoom en el punto clave.",
    },
    "1000350988": {
        "archivo": "1000350988.mp4",
        "metrica": {"duracion_s": 117.3, "cortes": 2, "texto": 43, "bpm": 95.7, "silencio": 0.029, "brillo": 72.9, "movimiento": 52.4},
        "corte_s": (20.0, 35.0),
        "pulso_bpm": (90, 105),
        "texto": "Pregunta inicial, un dato numérico y una respuesta; tarjetas numeradas y máximo dos bloques.",
        "zonas": "Inferior para subtítulos, central para el diagrama; apenas texto superior.",
        "audio": "Explicación continua con cama cálida; sin silencios mayores a 0.3 s.",
        "luz": "Fondo cálido tipo pizarra o papel con flechas de alto contraste.",
        "movimiento": "Dibujo progresivo y transiciones suaves; sin cortes bruscos.",
    },
    "1000350997": {
        "archivo": "1000350997.mp4",
        "metrica": {"duracion_s": 167.935, "cortes": 47, "texto": 69, "bpm": 103.4, "silencio": 0.017, "brillo": 94.7, "movimiento": 80.2},
        "corte_s": (2.5, 4.0),
        "pulso_bpm": (98, 110),
        "texto": "Titular, fecha y fuente; fichas con iniciales y dos bloques máximo por plano.",
        "zonas": "Central para el expediente e inferior para el subtítulo; sin texto superior.",
        "audio": "Voz sobria sobre cama baja, casi sin silencio y golpe suave al abrir documentos.",
        "luz": "Fondo azul grisáceo, documentos y sellos con contraste alto.",
        "movimiento": "Muy alto: capas que se abren y mapas que se recorren.",
    },
    "1000350998": {
        "archivo": "1000350998.mp4",
        "metrica": {"duracion_s": 69.967, "cortes": 14, "texto": 44, "bpm": 99.4, "silencio": 0.043, "brillo": 107.4, "movimiento": 49.2},
        "corte_s": (3.5, 5.5),
        "pulso_bpm": (95, 108),
        "texto": "Paso numerado, nombre de la opción y resultado; dos bloques máximo por plano.",
        "zonas": "Central para la interfaz resaltada, inferior para el subtítulo; superior solo para el contador.",
        "audio": "Voz instructiva con clics suaves; sin pausas largas.",
        "luz": "Fondo verde limpio, recuadros claros y cursor siempre visible.",
        "movimiento": "Cursor, resaltados y transiciones limpias.",
    },
    "1000350999": {
        "archivo": "1000350999.mp4",
        "metrica": {"duracion_s": 66.6, "cortes": 14, "texto": 41, "bpm": 161.5, "silencio": 0.209, "brillo": 87.1, "movimiento": 72.2},
        "corte_s": (3.5, 5.0),
        "pulso_bpm": (125, 145),
        "texto": "Diálogo de una frase, rótulo de capítulo arriba y subtítulo abajo; nunca tres bloques a la vez.",
        "zonas": "Superior para capítulo, inferior para diálogo y central para el personaje.",
        "audio": "Narración en primera persona con pausas controladas, máximo 5% de silencio y cama emocional continua.",
        "luz": "Fondo en tres planos con tonos fríos y acento cálido en el personaje.",
        "movimiento": "Parallax suave y cortes al cambiar de capítulo.",
    },
    "1000351002": {
        "archivo": "1000351002.mp4",
        "metrica": {"duracion_s": 79.267, "cortes": 5, "texto": 81, "bpm": 143.6, "silencio": 0.141, "brillo": 44.9, "movimiento": 43.2},
        "corte_s": (10.0, 16.0),
        "pulso_bpm": (130, 145),
        "texto": "Tabla de tres filas y regla de decisión en tres líneas; una métrica por fila y densidad reducida.",
        "zonas": "Central para la tabla, inferior para la regla; superior solo para opción A frente a B.",
        "audio": "Voz comparativa con cama tecnológica; sin silencio muerto entre opciones.",
        "luz": "Fondo oscuro, tarjetas claras y barras con un acento cromático.",
        "movimiento": "Barras que crecen y filas que se llenan con movimiento medio.",
    },
    "1000351029": {
        "archivo": "1000351029.mp4",
        "metrica": {"duracion_s": 126.492, "cortes": 82, "texto": 44, "bpm": 71.8, "silencio": 0.025, "brillo": 108.0, "movimiento": 68.4},
        "corte_s": (1.0, 1.6),
        "pulso_bpm": (70, 85),
        "texto": "Frases de tres a cinco palabras abajo, un número de reloj por repetición y sin explicar el truco antes del remate.",
        "zonas": "Inferior para el subtítulo, central para el bucle; superior para la cuenta regresiva.",
        "audio": "Cama tensa, tic-tac sutil y un efecto idéntico en cada repetición; sin silencios.",
        "luz": "Frío y azulado, con bordes y contraste muy marcados.",
        "movimiento": "Alto: mismo encuadre con un detalle distinto en cada repetición.",
    },
}

ESTILOS: dict[str, dict[str, Any]] = {
    "1000350669": {
        "nombre": "Collage editorial cinético",
        "familia": "clip_rapido",
        "paleta": "cine",
        "carpetas_broll": ("urbano", "cinematico", "fpv"),
        "duracion": (15, 30),
        "descripcion": (
            "Collage editorial de diseño gráfico cinético: tipografía gigante, recortes con máscara, "
            "rejillas que se deslizan, viñetas que aparecen a golpe de ritmo y una edición seca de concepto, "
            "actitud o remate. Cada palabra clave explota en pantalla con recuadros, tachaduras y barras de color; "
            "sin escenas largas ni explicaciones innecesarias. Todo el texto visible en español."
        ),
        "estructura": (
            "Golpe de tipografía gigante con la palabra del tema",
            "Collage de recortes y etiquetas que contrastan idea vs resultado",
            "Remate con la frase final en grande y corte limpio sobre la pregunta",
        ),
        "marcadores": (
            "collage", "diseno grafico", "diseno", "editorial", "cinetico", "actitud", "mentalidad",
            "concepto", "remate", "edicion", "tipografia", "recorte", "clip rapido", "cortes rapidos",
            "viral", "gancho", "15 segundos", "30 segundos",
        ),
    },
    "1000350985": {
        "nombre": "Crónica low-poly con carteles",
        "familia": "cronica",
        "paleta": "tips",
        "carpetas_broll": ("urbano", "gadgets", "broll_general"),
        "duracion": (30, 58),
        "descripcion": (
            "Crónica en bloques low-poly: figuras geométricas sencillas, personas y objetos de cuerpo entero "
            "construidos con cubos, carteles de fecha y lugar, flechas gruesas y viñetas numeradas. "
            "La escena avanza como una reconstrucción de hechos reales: quién, cuándo, dónde y qué cambió, "
            "con HUD discreto y sin fotos borrosas. Texto en español, sin anglicismos innecesarios."
        ),
        "estructura": (
            "Cartel con fecha y lugar sobre bloques low-poly",
            "Reconstrucción de los hechos en tres viñetas numeradas",
            "Consecuencia final y cartel de cierre con la pregunta",
        ),
        "marcadores": (
            "cronica", "caso", "caso real", "historia real", "hechos reales", "low poly", "bloques",
            "reconstruccion", "fecha", "anio", "lugar", "museo", "robo", "desaparecio", "rescate",
            "informe", "archivo", "historia verdadera",
        ),
    },
    "1000350986": {
        "nombre": "Acción y suspenso en mundo de bloques",
        "familia": "relato",
        "paleta": "fpv",
        "carpetas_broll": ("fpv", "urbano", "avata_fpv"),
        "duracion": (30, 58),
        "descripcion": (
            "Acción y suspenso en un mundo de bloques tipo sandbox: nieve, vías de tren, túneles, "
            "señales de peligro y un robot gigante que persigue al protagonista. Cámara baja, cortes rápidos, "
            "polvo, destellos rojos y cuenta de segundos en pantalla. Diálogo seco en español, "
            "sin texto encimado y con remate de tensión."
        ),
        "estructura": (
            "Plano de amenaza: tren o robots acercándose entre nieve",
            "Persecución con cortes cortos y cuenta regresiva visual",
            "Giro final y pregunta suspendida sobre la última imagen",
        ),
        "marcadores": (
            "accion", "suspenso", "persecucion", "tren", "nieve", "robot", "robots", "gigante",
            "sandbox", "bloques", " Minecraft", "peligro", "escape", "cuenta regresiva", "amenaza",
            "vias", "tunel", "jefe", "boss",
        ),
    },
    "1000350987": {
        "nombre": "Análisis técnico con HUD y cámara lenta",
        "familia": "tecnico",
        "paleta": "tech",
        "carpetas_broll": ("gadgets", "fpv", "cinematico"),
        "duracion": (30, 58),
        "descripcion": (
            "Análisis técnico de balística, trayectorias, fuerzas y telemetría con estilo de HUD militar: "
            "rejilla, radar circular, vectores, números en movimiento, tabla periódica o esquema de materiales "
            "y cámara lenta para congelar el instante clave. Cada dato se muestra con una sola etiqueta en español "
            "y se resuelve con una conclusión clara, sin fórmulas ilegibles ni texto superpuesto."
        ),
        "estructura": (
            "Congelación del momento crítico con HUD y vector",
            "Secuencia de datos: velocidad, ángulo, material y resultado",
            "Conclusión técnica destacada y pregunta final",
        ),
        "marcadores": (
            "balistica", "trayectoria", "aerodinamica", "telemetria", "fisica", "fuerza", "angulo",
            "velocidad", "camera lenta", "camara lenta", "hud", "radar", "vector", "esquema",
            "tabla periodica", "material", "datos", "sensor", "tecnico", "analisis tecnico",
        ),
    },
    "1000350988": {
        "nombre": "Infografía 2D de ingeniería y física",
        "familia": "tecnico",
        "paleta": "tips",
        "carpetas_broll": ("gadgets", "broll_general", "urbano"),
        "duracion": (30, 58),
        "descripcion": (
            "Infografía 2D limpia: diagrama esquemático, flechas, engranajes, péndulos, planos vistos de lado "
            "y una pizarra que se dibuja sola mientras la voz explica. Cada concepto aparece como una tarjeta "
            "numerada con etiqueta corta en español y una comparación visual antes/después. Ritmo constante, "
            "sin párrafos largos y sin términos en inglés que no sean necesarios."
        ),
        "estructura": (
            "Pizarra en blanco con la pregunta física del tema",
            "Dibujo paso a paso del diagrama y sus tres etiquetas",
            "Resultado aplicado al dron o al vuelo y cierre con pregunta",
        ),
        "marcadores": (
            "infografia", "ingenieria", "fisica", "diagrama", "esquema", "pizarra", "engranaje",
            "pendulo", "mecanica", "funciona", "como funciona", "principio", "explicacion",
            "educativo", "formula", "antes despues",
        ),
    },
    "1000350997": {
        "nombre": "Crónica de actualidad e investigación",
        "familia": "cronica",
        "paleta": "cine",
        "carpetas_broll": ("urbano", "broll_general", "cinematico"),
        "duracion": (30, 58),
        "descripcion": (
            "Crónica de actualidad e investigación: titulares recortados, documentos con sellos, mapas, "
            "fichas policiales, líneas de tiempo y clips reales cuando existan. Todo se arma como un expediente "
            "que se abre por capas, con fecha, fuente y dato verificado en cada tarjeta. Voz sobria en español, "
            "sin inventar pruebas y sin frases sensacionalistas."
        ),
        "estructura": (
            "Titular real y fecha sobre fondo de mapa o expediente",
            "Fichas, líneas de tiempo y documentos que explican el hallazgo",
            "Veredicto basado en fuentes y pregunta para la comunidad",
        ),
        "marcadores": (
            "actualidad", "investigacion", "noticia", "periodismo", "expediente", "documento", "mapa",
            "ficha", "titular", "fuente", "detencion", "autoridad", "reporte", "caso actual", "verificado",
            "linea de tiempo", "hallazgo", "escandalo", "anuncio",
        ),
    },
    "1000350998": {
        "nombre": "Tutorial paso a paso con interfaz",
        "familia": "tutorial",
        "paleta": "tips",
        "carpetas_broll": ("gadgets", "avata_fpv", "dji_mini3"),
        "duracion": (30, 58),
        "descripcion": (
            "Tutorial práctico en pantalla: interfaz de configuración o simulador, cursor visible, "
            "contadores de pasos, recuadros alrededor de cada opción y una mano o icono que ejecuta el cambio. "
            "Cada paso tiene su tarjeta numerada y su resultado inmediato; el texto hablado y los subtítulos "
            "van en español natural, con nombres de menú traducidos cuando existan."
        ),
        "estructura": (
            "Pantalla inicial con el objetivo del tutorial y paso 1 resaltado",
            "Pasos 2 y 3 con clic visible, contador y antes/después",
            "Comprobación final y CTA para guardar o probar",
        ),
        "marcadores": (
            "tutorial", "paso a paso", "configuracion", "configura", "activar", "desactivar", "menu",
            "interfaz", "simulador", "software", "app", "ajuste", "checklist", "como configurar",
            "control", "modo", "opcion", "instalar", "activar", "desbloquear",
        ),
    },
    "1000350999": {
        "nombre": "Storytime e ilustración 2D por capas",
        "familia": "relato",
        "paleta": "cine",
        "carpetas_broll": ("cinematico", "urbano", "broll_general"),
        "duracion": (30, 58),
        "descripcion": (
            "Storytime e ilustración 2D por capas: personajes originales, fondos en tres planos, "
            "parallax suave, globos de diálogo cortos y una narración en primera persona que avanza por capítulos. "
            "La historia tiene conflicto, giro y cierre abierto; los personajes mantienen el mismo diseño en todo el video. "
            "Todo el texto, diálogo y subtítulos en español, sin encimar globos sobre la zona inferior libre."
        ),
        "estructura": (
            "Plano establecido y voz que presenta al personaje",
            "Conflicto en tres capas con diálogo breve",
            "Giro emocional y pregunta que abre la siguiente parte",
        ),
        "marcadores": (
            "storytime", "relato", "historia", "lore", "personaje", "protagonista", "capitulo",
            "parte 2", "siguiente parte", "diario", "conflicto", "giro", "narracion", "leyenda",
            "mito", "ficcion", "ilustracion", "capas",
        ),
    },
    "1000351002": {
        "nombre": "Comparativa práctica con regla de decisión",
        "familia": "comparativa",
        "paleta": "tech",
        "carpetas_broll": ("gadgets", "cinematico", "urbano"),
        "duracion": (30, 58),
        "descripcion": (
            "Comparativa práctica en dos ventanas: opción A y opción B lado a lado, con métricas reales "
            "en barras, pesos, precios o tiempos cuando estén disponibles, y una tabla que se llena fila por fila. "
            "Cierra con una regla de decisión en una sola frase: para quién conviene cada opción. "
            "Sin ganador inventado, sin promesas comerciales y con texto en español."
        ),
        "estructura": (
            "Dos ventanas con A y B y la pregunta de la comparativa",
            "Tres filas de métricas con barras animadas y datos verificables",
            "Regla de decisión final y pregunta sobre cuál elegiría la audiencia",
        ),
        "marcadores": (
            "comparativa", "comparar", "versus", "vs", "cual elegir", "cual conviene", "opcion a",
            "opcion b", "diferencia", "mejor", "herramienta", "herramientas", "ia", "inteligencia artificial",
            "modo de vuelo", "modos de vuelo", "equipos", "drone vs", "lado a lado", "tabla",
        ),
    },
    "1000351029": {
        "nombre": "Misterio y bucle temporal",
        "familia": "relato",
        "paleta": "tech",
        "carpetas_broll": ("urbano", "gadgets", "cinematico"),
        "duracion": (30, 58),
        "descripcion": (
            "Misterio de bucle temporal en mundo de bloques: relojes gigantes, agujas que giran al revés, "
            "personajes que repiten la misma acción y una cuenta regresiva que se reinicia. La cámara vuelve "
            "al mismo encuadre con pequeñas diferencias, los colores se enfrían y el sonido marca cada repetición. "
            "Guion en español con giro claro y sin explicar el truco antes del remate."
        ),
        "estructura": (
            "Reloj y cuenta regresiva sobre plano repetido",
            "Tres repeticiones con un detalle distinto en cada una",
            "Descubrimiento del bucle y pregunta final antes del reinicio",
        ),
        "marcadores": (
            "misterio", "bucle", "bucle temporal", "tiempo", "reloj", "cuenta regresiva", "repite",
            "repiten", "reinicio", "cinco minutos", "minutos", "paradoja", "paradojas", "sospecha",
            "enigma", "acertijo", "giro", "se repite", "otra vez",
        ),
    },
}

FALLOS_POR_CATEGORIA: dict[str, str] = {
    "tips": "1000350998",
    "fpv": "1000350986",
    "cine": "1000350669",
    "tech": "1000351002",
}


def normalizar(texto: Any) -> str:
    valor = unicodedata.normalize("NFKD", str(texto or ""))
    valor = "".join(caracter for caracter in valor if not unicodedata.combining(caracter))
    return re.sub(r"\s+", " ", valor.casefold()).strip()


def texto_de(origen: Any) -> str:
    if isinstance(origen, dict):
        partes = [
            origen.get("titulo"),
            origen.get("gancho"),
            origen.get("resumen"),
            origen.get("enfoque"),
            origen.get("categoria"),
            origen.get("tipo"),
            origen.get("tema"),
        ]
        return normalizar(" ".join(str(parte or "") for parte in partes))
    return normalizar(origen)


def obtener(estilo_id: Any = "") -> dict[str, Any]:
    clave = str(estilo_id or "").strip()
    if clave not in ESTILOS:
        clave = "1000350998"
    datos = dict(ESTILOS[clave])
    datos["id"] = clave
    datos["referencia"] = datos.get("referencia") or clave
    return datos


def seleccionar(
    origen: Any = "",
    *,
    categoria: Any = "",
    tipo: Any = "",
    titulo: Any = "",
    gancho: Any = "",
    resumen: Any = "",
    enfoque: Any = "",
) -> dict[str, Any]:
    texto = texto_de(origen)
    texto += " " + normalizar(" ".join(str(parte or "") for parte in (categoria, tipo, titulo, gancho, resumen, enfoque)))
    texto = texto.strip()
    if not texto:
        return obtener(FALLOS_POR_CATEGORIA["tips"])

    mejor_id = ""
    mejor_puntos = 0.0
    for estilo_id, estilo in ESTILOS.items():
        puntos = 0.0
        for marcador in estilo["marcadores"]:
            if normalizar(marcador) in texto:
                puntos += 4.0 if estilo["familia"] in {"tutorial", "comparativa", "relato"} else 3.0
        if "reloj" in texto or "bucle" in texto or "cuenta regresiva" in texto:
            if estilo_id == "1000351029":
                puntos += 8.0
        if "comparar" in texto or "comparativa" in texto or " versus " in f" {texto} ":
            if estilo_id == "1000351002":
                puntos += 8.0
        if "tutorial" in texto or "paso a paso" in texto or "configuracion" in texto:
            if estilo_id == "1000350998":
                puntos += 7.0
        if puntos > mejor_puntos:
            mejor_id, mejor_puntos = estilo_id, puntos

    if mejor_id:
        return obtener(mejor_id)

    base = normalizar(categoria)
    for clave, estilo_id in FALLOS_POR_CATEGORIA.items():
        if clave in base:
            return obtener(estilo_id)
    return obtener(FALLOS_POR_CATEGORIA["tips"])


def carpetas_broll(estilo: dict[str, Any] | str) -> tuple[str, ...]:
    datos = obtener(estilo if isinstance(estilo, str) else estilo.get("id"))
    return tuple(datos["carpetas_broll"])


def reglas_referencia(estilo: dict[str, Any] | str) -> dict[str, Any]:
    datos = obtener(estilo if isinstance(estilo, str) else estilo.get("id"))
    reglas = REGLAS_REFERENCIA.get(datos["id"], {})
    resultado = dict(reglas)
    resultado["estilo_id"] = datos["id"]
    return resultado


def prompt_referencia(estilo: dict[str, Any] | str) -> str:
    datos = obtener(estilo if isinstance(estilo, str) else estilo.get("id"))
    reglas = REGLAS_REFERENCIA.get(datos["id"])
    if not reglas:
        return ""
    corte = reglas["corte_s"]
    pulso = reglas["pulso_bpm"]
    metrica = reglas["metrica"]
    return (
        f"Referencia medida `{reglas['archivo']}`: {metrica['duracion_s']} s originales, "
        f"{metrica['cortes']} cortes, {metrica['texto']} bloques de texto, "
        f"{metrica['bpm']} BPM y {metrica['silencio'] * 100:.1f}% de silencio; "
        "adapta esa cadencia al objetivo de duración sin copiar textos, marcas ni nombres. "
        f"Cortes objetivo cada {corte[0]}–{corte[1]} s y pulso {pulso[0]}–{pulso[1]} BPM. "
        f"Texto: {reglas['texto']} Zonas: {reglas['zonas']} "
        f"Audio: {reglas['audio']} Luz: {reglas['luz']} Movimiento: {reglas['movimiento']} "
    )


def prompt_estilo(estilo: dict[str, Any] | str) -> str:
    datos = obtener(estilo if isinstance(estilo, str) else estilo.get("id"))
    estilo_id = datos["id"]
    duracion = datos["duracion"]
    estructura = " | ".join(f"{indice + 1}) {paso}" for indice, paso in enumerate(datos["estructura"]))
    return (
        "ESTILO VISUAL ASIGNADO (OBLIGATORIO Y NO NEGOCIABLE): "
        f"ID `{estilo_id}`; referencia `{datos['referencia']}`; nombre «{datos['nombre']}». "
        f"Paleta permitida: `{datos['paleta']}`. Duración objetivo {duracion[0]}–{duracion[1]} s; "
        f"máximo absoluto {DURACION_MAXIMA_S:.1f} s, sin silencios muertos ni colas largas tras el cierre. "
        f"Descripción: {datos['descripcion']} "
        f"Estructura: {estructura}. "
        f"{prompt_referencia(datos)}"
        f"B-roll preferido: {', '.join(datos['carpetas_broll'])}. "
        "Todo el texto visible, hablado, subtítulos, títulos, descripciones y hashtags va en español natural; "
        "ningún bloque de texto se encima con otro ni invade y>1320. "
        "Antes de usar fuentes, íconos, SFX o recortes ejecuta "
        f"`python _shared/factory/descargar_recursos.py <proyecto> --estilo {estilo_id}`; "
        "el comando es idempotente, usa caché local y deja fallback si falta un recurso. "
        f"Guarda en config.json y renders/metadata.json: `\"estilo_id\": \"{estilo_id}\"`, "
        f"`\"estilo\": {{\"id\": \"{estilo_id}\", \"referencia\": \"{datos['referencia']}\", "
        f"\"nombre\": \"{datos['nombre']}\", \"familia\": \"{datos['familia']}\"}}` y "
        f"`\"duracion_maxima_s\": {DURACION_MAXIMA_S:.1f}`. "
        f"Añade `data-style=\"{estilo_id}\"` al elemento `<html>` de index.html y al `#root` de cada archivo en compositions/. "
        "No elijas otro estilo aunque la categoría sugiera otra paleta; la fábrica validará este ID."
    )


def aplicar_en_proyecto(proyecto: Path, estilo: dict[str, Any] | str) -> dict[str, Any]:
    datos = obtener(estilo if isinstance(estilo, str) else estilo.get("id"))

    proyecto = Path(proyecto).resolve()
    if not proyecto.is_dir():
        raise FileNotFoundError(f"No existe el proyecto {proyecto}")

    from paletas import datos_paleta

    paleta = datos_paleta(datos["paleta"])
    objeto_estilo = {
        "id": datos["id"],
        "referencia": datos["referencia"],
        "nombre": datos["nombre"],
        "familia": datos["familia"],
    }

    config_path = proyecto / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        config = {}
    if not isinstance(config, dict):
        config = {}
    config["estilo"] = objeto_estilo
    config["estilo_id"] = datos["id"]
    config["duracion_maxima_s"] = DURACION_MAXIMA_S
    config["carpetas_broll"] = list(datos["carpetas_broll"])
    config["referencia_visual"] = reglas_referencia(datos)
    config["paleta"] = paleta
    config["paleta_clave"] = datos["paleta"]
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    metadata_path = proyecto / "renders" / "metadata.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
        if isinstance(metadata, dict):
            metadata["estilo"] = objeto_estilo
            metadata["estilo_id"] = datos["id"]
            metadata["duracion_maxima_s"] = DURACION_MAXIMA_S
            metadata["referencia_visual"] = reglas_referencia(datos)
            metadata["paleta"] = paleta
            metadata["paleta_clave"] = datos["paleta"]
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    index_path = proyecto / "index.html"
    if index_path.is_file():
        texto = index_path.read_text(encoding="utf-8", errors="replace")
        if "data-style=" in texto:
            texto = re.sub(r'\sdata-style="[^"]*"', "", texto, count=1)
        texto = texto.replace("<html ", f'<html data-style="{datos["id"]}" ', 1)
        index_path.write_text(texto, encoding="utf-8")

    for ruta in (proyecto / "compositions").glob("*.html"):
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        etiqueta_original = re.search(r'<div id="root"[^>]*>', texto)
        if not etiqueta_original:
            continue
        etiqueta = re.sub(r'\sdata-style="[^"]*"', "", etiqueta_original.group(0))
        etiqueta = etiqueta.replace('id="root"', f'id="root" data-style="{datos["id"]}"', 1)
        texto = texto[: etiqueta_original.start()] + etiqueta + texto[etiqueta_original.end() :]
        ruta.write_text(texto, encoding="utf-8")

    return datos


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Selecciona el estilo visual automático para una idea.")
    parser.add_argument("texto", nargs="?", default="", help="Tema, título o ruta a un JSON de idea")
    parser.add_argument("--categoria", default="")
    parser.add_argument("--tipo", default="")
    parser.add_argument("--titulo", default="")
    parser.add_argument("--gancho", default="")
    parser.add_argument("--resumen", default="")
    parser.add_argument("--enfoque", default="")
    args = parser.parse_args(argv)

    texto: Any = args.texto
    if args.texto and args.texto.endswith(".json"):
        try:
            texto = json.loads(Path(args.texto).read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            texto = args.texto
    estilo = seleccionar(
        texto,
        categoria=args.categoria,
        tipo=args.tipo,
        titulo=args.titulo,
        gancho=args.gancho,
        resumen=args.resumen,
        enfoque=args.enfoque,
    )
    print(json.dumps(estilo, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
