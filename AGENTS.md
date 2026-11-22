# Manual maestro de `videos-ia` — HyperFrames

Este archivo es obligatorio para **todos** los proyectos nuevos de `videos-ia`. Reemplaza las reglas dispersas anteriores. Objetivo: máxima calidad visual/sonora, mínimo consumo de tokens y mínimo gasto de créditos.

## 0. Orden obligatorio de trabajo

1. Clonar la plantilla compartida.
2. Refrescar scripts, fuentes y SFX locales desde `_shared/`.
3. Consultar skills antes de producir: `remotion-best-practices` (router), `remotion-code-motion-explainer` (motion/cámara/SVG/QA), `_shared/skills_ext/claude-remotion-skill/remotion-motion-graphics/SKILL.md` (spring/stagger/curvas seguras) y las guías HyperFrames locales.
4. Escribir el guion en español y generar SIEMPRE la voz con `edge-tts` gratis e ilimitado, alternando `es-MX-JorgeNeural` y `es-MX-DaliaNeural` con prosodia conversacional, pausas naturales y pronunciación limpia de `FPV`, `AUX`, `FPS`.
5. Normalizar voz a **-14 LUFS** y ducking de música con `mezclar_audio.ps1`.
6. Ajustar duración, escenas y subtítulos a la voz normalizada. El cierre hablado (últimos 3–4 s) debe ser CTA conversacional específico del tema; la misma frase va en `cta.html`, `metadata.json` y primer comentario automático de YouTube.
7. `check` → `render` → autoinspección visual: extraer frames `15%/50%/85%` con `ffmpeg` y validar en `qa_video.py` que no haya solapamientos ni texto fuera de zonas seguras; corregir y repetir hasta pasar.
8. `portada.jpg` → generar `renders/metadata.json` desde `_shared/templates/renders-metadata.template.json`, con copy único por plataforma y pregunta detonadora UTF-8.
9. Solo si el usuario pide publicar: ejecutar `_shared/publisher/publicar_todo.py` con las plataformas autorizadas y `--auto-schedule` cuando aplique.
10. Solo si el usuario pide calidad final y autoriza créditos: regenerar voz con `--final`.

---

## 0.1 Seguridad y dependencias

- Instalar Python solo desde `https://pypi.org/simple` con `python -m pip install`.
- Lista blanca estricta: `requests`, `google-api-python-client`, `google-auth-oauthlib`, `python-dotenv`, `feedparser`, `ddgs`, `yt-dlp`, `tzdata`, `edge-tts`. Prohibidos paquetes desconocidos, repositorios externos y binarios `.exe` ajenos.
- Antes de instalar, verificar con `python -m pip show <paquete>`. Versiones exactas en `_shared/requirements.txt`. Cerrar con `python -m pip check`.
- `opencode.json` de la raíz habilita `bash`, `edit` y `webfetch` para la automatización local. Requiere reiniciar OpenCode después de cambiarlo.

---

## 1. Plantilla y recursos compartidos

- **SIEMPRE** iniciar un video nuevo clonando `_shared/templates/vertical-pro/`. Nunca crear un proyecto desde cero.
  ```powershell
  Copy-Item -Recurse "_shared\templates\vertical-pro\*" "<nombre-video>\"
  ```
- La plantilla ya trae copias locales de los recursos compartidos. Si `_shared/` cambió, refrescar antes de renderizar:
  ```powershell
  Copy-Item "_shared\scripts\*" "<nombre-video>\assets\scripts\" -Force
  Copy-Item "_shared\fonts\*" "<nombre-video>\assets\fonts\" -Force
  Copy-Item "_shared\sfx\*" "<nombre-video>\assets\audio\sfx\" -Force
  ```
- Recursos compartidos:
  - `_shared/scripts/gsap.min.js`
  - `_shared/scripts/TextPlugin.min.js`
  - `_shared/scripts/lottie.min.js` (lottie-web 5.12.2 local, para JSON/Lottie sin CDN)
  - `_shared/scripts/mezclar_audio.ps1` (normalización + ducking)
  - `_shared/fonts/fonts.css` con `@font-face` relativo a `.woff2` reales.
  - Fuentes disponibles: Montserrat 800/900, Outfit 700/800, Space Grotesk 500/700, Inter 400/600/700.
  - `_shared/factory/voice_engine.py`: voz edge-tts con prosodia por segmento y sidecar `voz.json`.
  - `_shared/sfx/`: 20 efectos locales (`whoosh.mp3`, `whoosh-short.mp3`, `sparkle.mp3`, `click.mp3`, `hit.mp3` = alias de `impact-bass-1.mp3`, `pop.mp3`, `riser.mp3`, etc.) con `manifest.json` y `CREDITS.md`.
  - `_shared/media_vault/`: B-roll propio por carpeta; se copia al proyecto y se activa con `data-media-vault` sobre `#broll-slot`.
- **NUNCA** usar CDN, Google Fonts en tiempo de render, `fetch`, URLs externas ni peticiones de red durante el render.
- Usar como máximo **2 fuentes por video**: una display gruesa para titulares (Montserrat por defecto) y una sans-serif limpia para cuerpo/subtítulos (Inter por defecto).

---

## 2. Formato y duración

- Resolución fija: **1080x1920**, **30 fps**, vertical.
- Duración obligatoria: **15–60 segundos**. `qa_video.py` rechaza cualquier MP4 fuera de ese rango antes de agendar.
- Para videos de 20–60 s: guion directo en español de **600–850 caracteres** (máx. ~140 palabras), con pausas visuales de **1–1.5 s** entre bloques en vez de pagar caracteres extra de voz.
- Un bloque visual nuevo cada 2–3 s; ninguna pantalla se queda quieta más de 3 s.

---

## 3. Guion, voz y audio

- Redactar el guion en español antes de tocar el HTML.
- **Loop invisible de retención:** en al menos el 50% de los guiones (fábrica: órdenes 1 y 2 de cada jornada de 3), el cierre debe empezar con la misma primera palabra del gancho y encadenarse sintácticamente con él, sin decir "como al inicio" ni explicar el recurso. Ejemplo: gancho "Qué pasa si…" → cierre "Qué pasa si lo repites ahora…". El resto cierra con una pregunta nueva.
- **Obligatorio en todos los videos nuevos: `voice_engine.py` con `edge-tts`, gratis e ilimitado.** No necesita API key ni consume créditos. El módulo `_shared/factory/voice_engine.py` reemplaza a `generar_voz.py` para producción y aplica prosodia conversacional por segmento.
  ```bash
  python _shared/factory/voice_engine.py "<guion>" "<nombre-video>\assets\audio\voz.mp3" --categoria "<categoría>" --titulo "<título>"
  ```
- Prosodia: gancho `+8%` de velocidad y `+3Hz` de tono; cuerpo `+3%` natural; pausas reales por puntuación y comas estratégicas. Alterna `es-MX-JorgeNeural` y `es-MX-DaliaNeural` según categoría/tema, o fuerza una con `--voz`.
- Modo internacional opcional: `voice_engine.py --idioma en` usa `en-US-AndrewNeural`, conectores y pronunciación en inglés (`FPS` → `frames per second`). El guion adaptado, ya revisado, se entrega con `--texto-en` o en `<proyecto>/guion.en.json` (`texto`, `titulo`, `descripcion`, `gancho`); `autopilot_maestro.py --idioma en` propaga la opción a la fábrica para exportar captions y metadata en inglés. Nunca se publica una traducción automática sin revisión.
- El texto hablado limpia siglas (`FPS` → `cuadros por segundo`, `AUX` → `auxiliar`, `FPV` → `efe pe uve`), pero el subtítulo escrito conserva `FPS`, `AUX` y `FPV` con grafía técnica y espacios reales. El sidecar `voz.json` guarda ambos textos en UTF-8.
- **`--final` es el único modo que usa ElevenLabs** (`eleven_flash_v2_5`, ~mitad de créditos por carácter). Usarlo **solo** cuando el usuario pida calidad final o autorice gasto:
  ```bash
  python generar_voz.py "<texto>" "<nombre-video>\assets\audio\voz.mp3" --final
  ```
- Nunca llamar a la API de ElevenLabs sin `--final`.
- Medir la duración exacta:
  ```bash
  ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "<nombre-video>\assets\audio\voz_norm.wav"
  ```
- La voz es el reloj: ajustar `data-duration` del root, de cada escena y de los subtítulos a ese valor (`.agents/skills/hyperframes/references/sound.md` §2).
- Normalizar y mezclar siempre antes de renderizar:
  ```powershell
  powershell -ExecutionPolicy Bypass -File "_shared\scripts\mezclar_audio.ps1" -Proyecto "<nombre-video>" -Sfx "pop.mp3@1.2", "whoosh-short.mp3@3.5"
  ```
  El script:
  - Normaliza voz a **-14 LUFS**, true peak ≈ -1 dBTP con `highpass`, `volume` iterativo y `alimiter`.
  - Música adaptativa: si `_shared/music/` contiene pistas `.mp3/.wav`, `audio_mixer.py` elige entre `fpv_energia/`, `cine_ambiental/` y `tech_limpio/` según la categoría y aplica `sidechaincompress` (voz como disparador, ataque 20 ms y liberación 260 ms) para bajar la música al hablar y subirla en transiciones. Si no hay pistas, el render sigue sin música.
  - El propio script pasa el WAV ya ducked a `mezclar_audio.ps1` con `-SinDucking`; no aplicar el ducking dos veces. Si no hay biblioteca, `_shared/scripts/mezclar_audio.ps1` mantiene su fallback con `assets/audio/musica.mp3`.
  - Mezcla SFX locales opcionales con `adelay` y volumen 0.35.
  - Escribe `assets/audio/voz_norm.wav`, `assets/audio/musica_duck.wav` y `assets/audio/mezcla_preview.wav`.
- En Hyperframes usar `voz_norm.wav` como voz. Si usa `musica_duck.wav`, poner `data-volume="1"` en esa pista: el ducking y el 12% ya están horneados. Si no se ejecutó el script, usar `musica.mp3` original con `data-volume="0.12"` y una lane manual.
- Integrar `<audio id="voz" class="clip" ... data-volume="1" src="assets/audio/voz_norm.wav">` siguiendo `.agents/skills/hyperframes/references/sound.md`.
- Efectos en cambios de escena y cifras clave: solo archivos locales de `_shared/sfx/` o `assets/audio/sfx/`. Nada de tonos sintéticos.
- Lanes de audio en la plantilla: `2` = SFX (`whoosh.mp3` en revelado, `click.mp3` en contador, `hit.mp3` en barrido de continuidad), `3` = voz, `4` = música. Los SFX ya están en `index.html` con `data-volume="0.35"`.
- La música y la voz se añaden cuando existan sus archivos; la plantilla base solo trae SFX para que el render nunca falle por media ausente.
- Nunca regenerar `voz.mp3` innecesariamente.

---

## 4. Estándar de Calidad Visual y Sonora

Obligatorio para cada video nuevo. La plantilla `vertical-pro` ya trae el LOOK aplicado; no lo redibujes desde cero.

**Zonas exclusivas 1080x1920 (cero superposición)**
1. **Zona superior `y=200..340`:** subtítulo dinámico corto (3–4 palabras por bloque, espacios reales, palabra activa resaltada) + píldora de sección + puntos de progreso de escena (`• • • •`). Contenido con `left=80px`, `right=150px`.
2. **Zona central `y=380..1260`:** tarjeta protagonista animada con ilustraciones SVG vectoriales animadas (drones, mandos, trayectorias, diales, iconos) que reaccionan al ritmo de la voz, más micro-estímulos cada 3.5 s. Contenido con `left=80px`, `right=150px`.
3. **Zona inferior `y>1320`:** completamente libre. Sin texto, gráficos, HUD, captions ni CTA.
4. **HUD/telemetría opcional:** si se usa, debe vivir dentro de la zona superior o central sin solapar subtítulo dinámico, tarjeta protagonista ni puntos de progreso; nunca invade `y>1320`.

**Paleta automática**
- `tips DJI / config / sensores`: cian eléctrico `#00E5FF`, blanco hielo `#F4FBFF`, fondo carbón `#0B111A`.
- `FPV / acción / velocidad`: naranja racing `#FF6B00`, ámbar `#FFD166`, fondo obsidiana `#0D0D0F`.
- `cine aéreo / edición / color`: esmeralda `#10B981`, dorado `#FBBF24`, fondo pizarra profunda `#0F172A`.
- `novedades tech / gadgets / comparativas`: violeta `#8B5CF6`, magenta `#EC4899`, fondo medianoche `#090D16`.
- Antes de editar el proyecto ejecuta `python _shared/factory/paletas.py <proyecto> "<categoría>" --titulo "<título>"`. La clave devuelta debe quedar en `data-palette` de `index.html` y la paleta elegida se guarda en `config.json` y `renders/metadata.json`. Nunca mezcles acentos de paletas distintas.

**Cierre interactivo obligatorio (últimos 3–4 s)**

- Nunca termines de golpe ni con frases genéricas como `sígueme para más`. El guion hablado y `compositions/cta.html` deben cerrar con la misma invitación directa, adaptada al tema y confinada a la zona central (`y=420..1080`); no invade subtítulos ni `y>1360`.
- Tips técnicos DJI/configuración: guardar el video antes de volar y comentar qué modelo de dron usan. FPV/acción: pregunta polarizante o reto rápido sobre la maniobra. Cine/edición: etiquetar o compartir con el compañero de vuelo, o elegir entre dos opciones del video. Tech/gadgets: preguntar si harían el cambio o qué opinan del equipo.
- La frase debe variar entre videos. Antes de fijarla ejecuta `python _shared/factory/dedup_manager.py --verificar-cta "<frase>"`; `fabrica_diaria.py` rechaza CTA idénticos o casi idénticos a los 8 videos más recientes.
- `renders/metadata.json` debe incluir `pregunta_detonadora` en `youtube`, `tiktok`, `instagram` y `facebook`, y cada `description` debe terminar exactamente con esa misma pregunta en UTF-8 limpio.

**Miniseries y detonadores de conversación**
- `trend_hunter.py` agrupa temas complejos en miniseries de 2 o 3 episodios con `serie_id`, `episodio`, `total_episodios`, `arco` y `adelanto`. El título y la etiqueta superior deben mostrar `EPISODIO n/m`, y el cierre hablado debe adelantar el siguiente capítulo.
- Cada idea lleva `detonador_tipo="opcion_a_b"` y `debate_a`/`debate_b`. El guion debe incluir una pregunta específica y la tarjeta central `compositions/debate.html` debe mostrar `Opción A vs Opción B` sin invadir la banda de telemetría, la etiqueta superior, los subtítulos ni `y>1360`.
- `fabrica_diaria.py` acepta la continuación de una miniserie aunque el tema se parezca al episodio anterior, siempre que el episodio inmediatamente previo exista con el mismo `serie_id`.

**Test A/B de ganchos**
- `renders/metadata.json` debe incluir `experimento_ab` con `gancho_a` (curiosidad o error común), `gancho_b` (resultado directo) y `asignacion={"youtube":"A","tiktok":"B"}`.
- `publicar_todo.py` aplica la variante A al título de YouTube Shorts y la variante B a la primera línea de TikTok, y guarda `gancho_id`, `gancho_variante` y el resto del experimento en `schedule_queue.json`.
- `analytics_feedback.py` agrupa vistas y retención por `gancho_id` y escribe `experimentos` y `ganador_ab`; el reporte semanal de Telegram informa la variante ganadora. Sin `yt-analytics.readonly` no hay señal y se reporta "sin señal suficiente".

**Tipografía y movimiento**
- Display: Outfit 800/Space Grotesk 700, 88–96px en el título, `letter-spacing:-0.03em`. Micro: Space Grotesk/Inter 700, 22–26px, mayúsculas, `letter-spacing:0.16em`. Caption: Inter 600, 50px, `line-height:1.12`, máximo 2 líneas.
- Subtítulo dinámico corto en zona superior: 3–4 palabras por bloque, espacios reales, palabra activa resaltada con acento y `stagger:0.07`; un solo host con `data-track-kind="captions"` y `data-zone="caption"`.
- Zona central obligatoria: tarjeta protagonista animada con ilustraciones SVG vectoriales (drones, mandos, trayectorias, diales, iconos) que reaccionan al ritmo de la voz; sin solapar superior ni inferior.
- Tres capas siempre: (1) cuadrícula SVG o B-roll local con overlay sólido `rgba()` y `translate3d` lento; (2) contenido en zonas con `clip-path: inset()`, contadores GSAP y trazos SVG `stroke-dashoffset`; (3) HUD/ornamentos solo si caben en zona superior o central sin tapar contenido.
- Prohibido `filter:blur`, `backdrop-filter`, CDN, `fetch` y URLs externas durante el render.
- Física GSAP/Remotion: prohibido `ease:"none"`, `linear` y arranques simultáneos. Entradas con curvas naturales tipo `spring()`/`elastic.out/back.out/expo.out`, escalonadas con `stagger` breve; ambiente `power2.inOut` con `repeat` finito y `yoyo`, nunca `repeat:-1`.
- Micro-estímulo cada **3.5 s**: zoom punch-in `1.0 -> 1.10` con destello direccional o cambio de tarjeta de dato, sincronizado con `click-soft.mp3` a volumen `0.18`.
- Continuidad entre escenas: barrido de línea/luz, motion blur simulado con ghost strips de acento (nunca `filter:blur`), zoom suave y `clip-path: inset()`; el frame 0 nunca queda vacío.
- Gancho profesional 0–1.5 s: `scale 1.15 -> 1.0` con `elastic.out(1, 0.55)`/spring dentro del recorte de la zona central, light sweep diagonal y SFX local `whoosh-short.mp3@0` + `sparkle.mp3@0.9`.
- Movimiento continuo: Ken Burns en `#bg-plate` o B-roll real de `_shared/media_vault/` activado con `data-media-vault`; diales, barras y trayectorias SVG con `stroke-dashoffset`; tarjetas de datos con entrada escalonada.
- Mezcla y SFX: voz a -14 LUFS, música base al 12% con ducking por sidechain mientras habla el narrador, SFX locales a ~0.35 y picos ≤ -1 dBTP. En la plantilla: `whoosh-short.mp3@0`, `sparkle.mp3@0.9`, `whoosh.mp3@2.35`, `click.mp3@2.75`, `click-soft.mp3@3.5` para el micro-estímulo y `hit.mp3@4.9` para el remate.
- Miniatura automática: tras renderizar, extraer con ffmpeg el fotograma del segundo 2 como `renders/portada.jpg`.
- Metadata de publicación: copiar `_shared/templates/renders-metadata.template.json` a `<proyecto>/renders/metadata.json` y rellenarlo analizando el guion y el tema exacto de ESE video. Revisar antes `_shared/publisher/schedule_queue.json` para no repetir ganchos ni hashtags; `publicar_todo.py` valida unicidad y límites. Nunca reutilizar el mismo copy entre videos ni entre plataformas.
- Reutilización de plantillas: `_shared/templates/vertical-pro/` es la base estructural. El handle "@aldo_auradrones" no va en la zona superior; la zona superior es solo la etiqueta del paso.

---

## 5. Fast capture y dependencias

- Cero `filter:blur`, `backdrop-filter`, `box-shadow` complejo ni filtros SVG pesados.
- Cero librerías por CDN. Todo en `assets/scripts/`, `assets/fonts/`, `assets/audio/`.
- Sin `Date.now()`, `Math.random()` no sembrado, timers ni `repeat: -1`. Todo depende del tiempo del timeline pausado.
- Animar siempre con `fromTo`, eases con nombre y `stagger:0.07` cuando haya grupo. Nada de `ease:"none"` ni `ease:"linear"`.
- Los efectos de ambiente usan `repeat` finito y `yoyo:true`; los elementos que salen se cortan con `tl.set(..., { visibility:"hidden" })` justo al terminar su `.clip`.
- Registrar un timeline raíz pausado por composición: `window.__timelines["<id>"] = gsap.timeline({ paused: true });`.
- Elementos temporizados: `class="clip"`, `data-start`, `data-duration`; animar hijos, nunca el `.clip` con `display`/`visibility`.
- Lottie: `autoplay: false`, `loop` explícito, JSON local y push a `window.__hfLottie`. No usar dotLottie salvo que se copien también el SDK ESM y el WASM local.

---

## 6. Procesos y recursos

- Antes de renderizar, limpiar **solo** procesos de navegador:
  ```powershell
  Get-Process chrome, headless_shell -ErrorAction SilentlyContinue | Stop-Process -Force
  ```
- **NUNCA** matar `node.exe`: otros renders o sesiones pueden estar activos.
- No instalar herramientas pesadas. Los skills locales ya cubren animación, audio y CLI. La única dependencia Python añadida es `edge-tts` (gratis).

---

## 7. Skills y guías disponibles

- `.agents/skills/` contiene los 9 skills oficiales de `heygen-com/hyperframes` según `skills-manifest.json`: `hyperframes`, `hyperframes-cli`, `hyperframes-registry`, `media-use`, `reverse-any-video`, `style-sampling`, `figma`, `slideshow`, `remotion-to-hyperframes`. No hay skills oficiales adicionales que instalar.
- `npx skills find "visual design motion audio" --json` encontró candidatos externos (`whaleyxbt/claude-motion@sound-design`, `akais-alt/ai-motion-design-skills@beat-sync`, `glebis/humane-agentic-design@semantic-micro-interactions`, etc.). **No instalarlos**: las guías locales cubren lo mismo y mantienen el flujo reproducible y gratis.
- Usar `/hyperframes` para el contrato de render, `/media-use` para voz/música/SFX y `/hyperframes-registry` antes de escribir un efecto o caption nuevo.
- Guías locales obligatorias de consulta antes de producir:

  **Motion / Remotion skills integrados al flujo**
  - `.agents/skills/remotion-best-practices/SKILL.md` — router; consultar antes de tocar motion/markup/render/captions.
  - `.agents/skills/remotion-code-motion-explainer/SKILL.md` — motion code-driven, cámara, SVG, QA visual y secuenciación por evidencia.
  - `_shared/skills_ext/claude-remotion-skill/remotion-motion-graphics/SKILL.md` y `references/motion-patterns.md` — spring, stagger, curvas seguras y patrones de motion graphics; adaptar a HyperFrames/GSAP pausado, nunca React/`useCurrentFrame`.

  **Diseño, narrativa y calidad**
  - `.agents/skills/hyperframes/references/look.md` — estilo visual y línea LOOK.
  - `.agents/skills/hyperframes/references/story.md` — one thing, hook, beats y narrativa.
  - `.agents/skills/hyperframes/references/spec.md` — traducir palabras a números de composición.
  - `.agents/skills/hyperframes/references/film.md` — hechos, ritmo y música.
  - `.agents/skills/hyperframes/references/review.md` — medir antes de mirar y entrega.
  - `.agents/skills/hyperframes/references/format.md` — atributos, lanes y errores de lint.
  - `.agents/skills/hyperframes/references/types/vertical.md` — UI de plataforma, primer segundo y ritmo 9:16.
  - `.agents/skills/hyperframes/references/types/explainer.md`, `types/launch.md`, `types/data.md` — según el tipo de pieza.

  **Movimiento y captions**
  - `.agents/skills/hyperframes/references/motion.md` — artesanía del movimiento y transiciones con causa.
  - `.agents/skills/hyperframes/references/runtimes.md` — GSAP, CSS, Lottie, canvas y protocolo `hf-seek`.
  - `.agents/skills/hyperframes/references/overlays.md` — tarjetas sobre footage.
  - `.agents/skills/hyperframes/references/captions.md` — palabras, timings y colocación.
  - `.agents/skills/remotion-to-hyperframes/references/lottie.md` — patrón Lottie y `window.__hfLottie`.

  **Audio**
  - `.agents/skills/hyperframes/references/sound.md` — defaults, reloj, música, efectos y niveles.
  - `.agents/skills/media-use/references/mixing.md` — `data-automation`, `data-fx-chain`, ducking y carve.
  - `.agents/skills/media-use/references/audio.md` — motor TTS + BGM + SFX y `audio_meta.json`.
  - `.agents/skills/media-use/references/operations.md` — ducking horneado con `sidechaincompress` y publicación a -14 LUFS.
  - `.agents/skills/media-use/audio/references/sfx.md` — librería local, licencias y volumen.
  - `.agents/skills/media-use/audio/references/bgm.md` — música de fondo y mood.
  - `.agents/skills/media-use/audio/references/tts.md` — providers de voz y word timestamps.
  - `.agents/skills/media-use/audio/references/transcribe.md` — regla de idioma y modelos.

  **CLI y verificación**
  - `.agents/skills/hyperframes-cli/references/lint-validate-inspect.md` — `lint`, `check`, `snapshot`.
  - `.agents/skills/hyperframes-cli/references/preview-render.md` — `preview`, `render`, `publish`.

---

## 8. Check, render y portada

1. Verificar. Si `check` falla por el entorno (`ChildProcess.kill ... Unknown`), usar `lint`, `timeline` y `snapshot`:
   ```bash
   npm run check
   npx --yes hyperframes@0.9.72 lint --json
   npx --yes hyperframes@0.9.72 timeline --json
   npx --yes hyperframes@0.9.72 snapshot --at 0,1,3,5
   ```
2. Renderizar:
   ```bash
   npm run render
   ```
3. Extraer portada automáticamente:
   ```bash
   npm run portada
   ```
   Equivale a:
   ```bash
   ffmpeg -y -ss 2 -i "renders/<ultimo>.mp4" -frames:v 1 -update 1 -q:v 2 renders/portada.jpg
   ```
   `scripts/portada.ps1` busca el MP4 más reciente en `renders/` y siempre escribe `renders/portada.jpg`.

---

## 9. Publicación automática multiplataforma

- Sistema compartido en `_shared/publisher/`. No duplicarlo dentro de cada proyecto.
- Preparación única:
  ```powershell
  Copy-Item "_shared\publisher\.env.example" "_shared\publisher\.env"
  python -m pip install --index-url https://pypi.org/simple -r "_shared\requirements.txt"
  ```
- Cargar las credenciales reales solo en `_shared/publisher/.env`. Ese archivo, `client_secret.json` y los tokens están excluidos por `.gitignore`. **Nunca** imprimirlos, committerlos ni pegarlos en un video.
- Uso inmediato:
  ```bash
  python _shared/publisher/publicar_todo.py "<nombre-video>" --plataformas youtube,facebook,instagram,tiktok
  ```
- Uso con programación automática:
  ```bash
  python _shared/publisher/publicar_todo.py "<nombre-video>" --plataformas youtube,facebook,instagram,tiktok --auto-schedule
  ```
- `publicar_todo.py` lee `<proyecto>/renders/metadata.json`, elige el MP4 indicado en `video` (o el más reciente de `renders/`) y publica o programa solo las plataformas solicitadas que tengan credenciales. Las demás se omiten con `[SKIP]`; un fallo parcial no detiene a las restantes.
- Formato obligatorio: partir de `_shared/templates/renders-metadata.template.json`, analizar el guion exacto y revisar `_shared/publisher/schedule_queue.json` antes de escribir. Ejemplo válido:
  ```json
  {
    "video": "mi-video_2026-11-20_18-00-00.mp4",
    "youtube": {
      "title": "DJI: sensores que salvan vuelos",
      "description": "Tu DJI no depende solo de la señal. Analizamos los sensores ópticos, la visión nocturna y el checklist previo al despegue con ejemplos del vuelo. Suscríbete para más consejos.",
      "hashtags": ["Drones", "Shorts", "FPV", "SeguridadAerea", "AuraDrones"],
      "privacidad": "public"
    },
    "tiktok": {
      "description": "¿Tu DJI decide sin señal? Guarda esto y comenta qué harías.\nTres sensores, un checklist y el remate del clip.",
      "hashtags": ["Drones", "FPV", "DroneTok", "FYP", "Sensores", "AuraDrones"]
    },
    "instagram": {
      "description": "Tu DJI ve más de lo que imaginas.\n\n• Sensores ópticos: spotting de obstáculos.\n• Visión nocturna: contradicción y encuadre.\n• Checklist: batería, luz y distancia.\n\nGuarda este reel y compártelo con tu crew antes de volar.",
      "hashtags": ["Drones", "FPV", "DroneLife", "DronePhotography", "AviationTech", "SeguridadAerea", "ConsejosDeVuelo", "Sensores", "AuraDrones"]
    },
    "facebook": {
      "description": "Hoy vimos cómo los sensores de un DJI cambian una decisión en pleno vuelo. ¿Ustedes también revisan la luz y la distancia antes de despegar? Cuéntalo y comparte tu experiencia.",
      "hashtags": ["Drones", "FPV", "SeguridadAerea", "Sensores", "AuraDrones"]
    }
  }
  ```
- `publicar_todo.py` valida automáticamente: bloques completos, título de YouTube de menos de 55 caracteres con `Shorts`, 6 hashtags en TikTok, 8–10 en Instagram, 4–5 en Facebook, CTA por red y unicidad de gancho/apertura/combinación de hashtags contra el historial de `schedule_queue.json`. Un copy repetido bloquea la publicación.
- Cada tarea encolada guarda un `config` con el `title`, `description` y `hashtags` exactos de su plataforma; `procesar_cola.py` usa esa copia para enviar el texto correcto aunque el `metadata.json` cambie después.
- `privacidad` es opcional y solo aplica a YouTube: `public` (default), `private` u `unlisted`. Con `--auto-schedule`, YouTube fuerza `private` y añade `status.publishAt`.
- Horarios pico en `America/Mexico_City` (`scheduler_manager.py`):

  | Plataforma | Horarios |
  | --- | --- |
  | YouTube | 09:00, 13:30, 19:30 |
  | TikTok | 08:30, 13:00, 20:00 |
  | Instagram | 09:00, 13:30, 19:00 |
  | Facebook | 08:30, 13:00, 19:30 |

- `asignar_siguiente_slot(plataforma)` elige el primer horario libre con al menos 20 minutos de margen. Si hoy ya tiene 3 asignados o pasaron los 3 horarios, avanza al primer horario del día siguiente sin límite de días.
- Con `--auto-schedule`:
  - YouTube: sube de inmediato como `private` con `status.publishAt` ISO 8601 UTC; YouTube publica solo a esa hora.
  - Facebook: sube de inmediato con `published=false` y `scheduled_publish_time` como Unix timestamp.
  - TikTok e Instagram: no se suben todavía; se guarda una tarea `pending` o `pending_credentials` en `_shared/publisher/schedule_queue.json` con `scheduled_at` exacto en UTC, `scheduled_at_local` y `slot` de `08:30`, `13:00` o `20:00` para TikTok.
  - YouTube y Facebook también se registran en la cola como `scheduled_native` para no duplicar slots; `procesar_cola.py` no las reenvía.
- `procesar_cola.py` revisa la cola, ejecuta las tareas `pending` cuya hora ya llegó o está dentro de los próximos 5 minutos, marca `published` y guarda `publicado_en`. Los errores se registran como `failed` con `error`, `intentos` y `ultimo_intento`.
- `schedule_queue.json` es el estado de la cola: `timezone`, `max_por_plataforma_por_dia` y `tareas`. No editar a mano salvo para cancelar (`estado: "cancelled"`) o reintentar (`estado: "pending"`).
- Automatización Windows:
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File "_shared\publisher\instalar_tarea_windows.ps1"
  ```
  Registra `AuraDrones_AutoPublisher`, ejecuta `procesar_cola.py` cada 10 minutos con `pythonw.exe` cuando está disponible y no abre ventana negra.
- Conectores oficiales:
  - `youtube_upload.py`: YouTube Data API v3 con OAuth instalado; cachea `youtube_token.json` en `_shared/publisher/`.
  - `meta_upload.py`: Graph API para Facebook (Page videos) e Instagram Reels. Para Reels necesita `META_VIDEO_URL` o `cloudflared`; si falta, Instagram se omite con `[SKIP]`.
  - `tiktok_upload.py`: Content Posting API v2 con OAuth/PKCE. `access_token_configurado()` determina si hay `TIKTOK_ACCESS_TOKEN`; si falta, `publicar_todo.py` deja la tarea en `pending_credentials` y la notificación avisa `TIKTOK_ACCESS_TOKEN requiere renovación` en lugar de abrir el navegador durante la cola automática. Con token vigente, sube el MP4 por `FILE_UPLOAD` a `/v2/post/publish/inbox/video/init/`; el video queda en la bandeja de borradores de TikTok para que el usuario lo revise y publique.
- Codificación UTF-8 obligatoria: `texto_utf8.py` sanea `metadata.json`, tokens, títulos y descripciones antes de llamar a YouTube o TikTok. Prohíbe caracteres corruptos como `Ã³`, `Ã¡` o `â€¢`; `publicar_todo.py`, `youtube_upload.py` y `tiktok_upload.py` leen/escriben JSON con UTF-8 explícito y envían el payload de TikTok como bytes UTF-8.
- Publicar o programar solo cuando el usuario lo autorice explícitamente: es una acción externa e irreversible.

---

## 10. Fábrica diaria autónoma

- Sistema compartido en `_shared/factory/`. No duplicarlo dentro de cada proyecto.
- `trend_hunter.py` usa solo `feedparser`, `ddgs`, `requests` y `yt-dlp` con `--dump-single-json` y `--skip-download`, sin descargar videos. Detecta tendencias en tiempo real de DJI, FPV, tomas cinematográficas, trucos de edición y tecnología audiovisual en YouTube Shorts, TikTok, Instagram Reels, Facebook Reels, Reddit (`r/drones`, `r/fpv`, `r/djimavic`) y Google News RSS. `dedup_manager.py` indexa `script.md`, `guion.md`, `metadata.json`, `renders/metadata.json`, `meta.json`, `historial_ideas.json` y `_shared/publisher/schedule_queue.json` en `historial_temas.json`, y bloquea con `difflib.SequenceMatcher` y palabras clave cualquier similitud ≥45% o el mismo enfoque técnico. Escribe exactamente 3 ideas inéditas y virales para mañana en `ideas_pendientes.json`. Cada idea trae `orden`, `franja`, `titulo`, `gancho`, `enfoque`, `fuente`, `url`, `resumen`, `metricas` y `puntuacion_viral`.
- Módulo de colaboraciones: el mismo `trend_hunter.py` rastrea colaboraciones, UGC, concursos y retos virales, valida que la convocatoria sea vigente y preferentemente oficial, guarda los hallazgos en `_shared/factory/oportunidades_colab.json` y prioriza un video de colaboración en la franja de la tarde cuando detecta una convocatoria activa real.
- Embudo comercial rotativo: `trend_hunter.py` mantiene `trend_hunter_state.json` e inyecta 1 idea de cada 4 (bienes raíces, inspección, eventos o FPV indoor) con `es_comercial=true` y `cta_tipo="cotizacion"`. Esa idea sustituye a la de toma o tech según el ciclo y cierra con contacto profesional de Aura Drones; nunca inventa precios ni clientes.
  ```bash
  python _shared/factory/trend_hunter.py
  python _shared/factory/trend_hunter.py --dry-run
  ```
- `fabrica_diaria.py` cuenta los videos únicos ya agendados para mañana en `America/Mexico_City`. Si ya hay 3, termina sin producir. Si faltan, produce exactamente los faltantes; si no hay suficientes ideas pendientes, vuelve a llamar a `trend_hunter.py`.
  ```bash
  python _shared/factory/fabrica_diaria.py --dry-run
  python _shared/factory/fabrica_diaria.py
  ```
- Secuencia obligatoria por video, sin saltos: consultar `remotion-best-practices` → `remotion-code-motion-explainer` → `_shared/skills_ext/claude-remotion-skill/remotion-motion-graphics/SKILL.md` antes de tocar motion → `vault_indexer.py` actualiza `_shared/media_vault/index.json` y `opencode run` recibe el plan de B-roll → ejecutar `_shared/factory/paletas.py` y crear guion, MP4 vertical, `config.json` y `renders/metadata.json` con bloques únicos para `youtube`, `tiktok`, `instagram` y `facebook` → verificar MP4 de más de 500 KB con 1 reintento máximo → `qa_video.py` ejecuta loop `render -> extraer frames 15%/50%/85% con ffmpeg -> validar zonas/solapes -> corregir y repetir` antes de dar OK → `carousel_exporter.py` genera 3 PNG 1080x1350 en `<proyecto>/carrusel/` → `python _shared/publisher/publicar_todo.py <proyecto> --plataformas youtube,tiktok,instagram,facebook --auto-schedule`. Nunca publicar desde el prompt de generación.
- Cada etapa tiene un reintento automático. Todo queda registrado en `_shared/factory/factory.log` con hora local, comandos, salidas, errores y resultado. `ideas_pendientes.json` guarda el estado de cada idea: `pendiente`, `completada` o `fallida`, junto con proyecto, video y errores.
- OpenCode se lanza con `--auto` de forma predeterminada para que la tarea funcione sin ventanas ni confirmaciones. Para desactivarlo: `AURA_OPENCODE_AUTO=0`. La ruta se puede redefinir con `AURA_OPENCODE_PS1`.
- Automatización Windows:
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File "_shared\factory\instalar_fabrica_windows.ps1"
  ```
  Registra `AuraDrones_DailyFactory`, todos los días a las 22:00, con `pythonw.exe` cuando está disponible, `-LogonType Interactive` y sin ventana negra.
- La fábrica solo programa; no publica de inmediato. Si faltan credenciales, la tarea queda en `pending_credentials` y se promueve sola cuando el publicador las detecta; si el publicador devuelve error, la idea se marca como `fallida` y el incidente queda en el log.

---

## 11. Radar semanal de mejoras

- `weekly_upgrade_radar.py` consulta GitHub, Hugging Face y PyPI con `requests` para detectar plantillas/efectos de video, mejoras de retención, TTS gratis, modelos abiertos de video y skills/flujos nuevos para OpenCode.
- **Nunca instala ni ejecuta automáticamente** nada. Genera `_shared/factory/mejoras_semanales.md` con enlaces oficiales y el comando exacto propuesto para cada mejora, sujeto a aprobación del usuario.
  ```bash
  python _shared/factory/weekly_upgrade_radar.py
  ```
- Automatización Windows: el mismo instalador de la fábrica registra `AuraDrones_WeeklyUpgradeRadar`, domingos a las 11:00, con `pythonw.exe` cuando está disponible y `-LogonType Interactive`.
- El radar dominguero también llama a `notificador_telegram.enviar_reporte_semanal()`: consulta 7 días de YouTube Analytics, envía el top 3 por vistas, el gancho del video ganador y el ajuste de peso aplicado a `trend_hunter.py`. Si faltan permisos o Telegram falla, lo registra como aviso y el radar termina igual.
- Una mejora solo se aplica tras revisar licencia, compatibilidad y seguridad; si es un paquete Python, se agrega a la lista blanca y a `_shared/requirements.txt`, y se cierra con `python -m pip check`.

---

## 12. Bóveda de material propio

- La bóveda vive en `_shared/media_vault/` con cuatro carpetas operativas: `fpv/`, `cinematico/`, `urbano/` y `gadgets/`. Las antiguas `avata_fpv/`, `dji_mini3/`, `tomas_urbanas/` y `broll_general/` se leen como alias y no se duplican en el índice.
- `vault_indexer.py` escanea `.mp4/.mov` con `ffprobe`, extrae duración, resolución y codec, y genera `_shared/media_vault/index.json`. `fabrica_diaria.py` lo ejecuta al iniciar y arma un plan de hasta 3 clips por video según la paleta del tema.
- El plan de B-roll se copia a `assets/media/` del proyecto y se monta **detrás de los motion graphics** (`z=0`, `object-fit: cover`) con overlay sólido `rgba(10, 12, 16, 0.45)` para oscurecerlo 45%. Cada clip conserva `data-start`, `data-duration`, `data-media-start` y `data-volume="0"`; usa `data-has-audio="true"` solo si su audio se aprovecha.
- Correspondencia: tips/configuración → `gadgets`/`urbano`; FPV → `fpv`; cine/edición → `cinematico`/`urbano`; tech/gadgets → `gadgets`/`cinematico`.
- Nunca se inventa un clip: si `index.json` está vacío, se mantiene la cuadrícula SVG de la plantilla. Sin `filter:blur`, sin CDN y sin URLs externas durante el render.

---

## 13. Control de calidad antes de agendar

- `qa_video.py` se ejecuta siempre después del render y antes de `publicar_todo.py`. Sin QA OK, no se agenda y la idea pasa al siguiente tema viral.
- Loop obligatorio `render -> frame check -> fix`: `qa_video.py` extrae 3 frames clave con `ffmpeg` al **15%**, **50%** y **85%** en `<proyecto>/renders/qa_frames/`, valida que ninguna banda invada otra, que no haya solapamiento de subtítulo/tarjeta/puntos de progreso y que `y>1320` quede vacío; si falla, la fábrica corrige y repite el render antes de continuar.
- Valida con `ffprobe`/`ffmpeg`: MP4 vertical **1080x1920**, duración **15–60 s**, pista de audio real y decodificable, sin silencio inicial mayor a **1 s**, zonas exclusivas (`superior 200..340`, `central 380..1260`, `inferior >1320 libre`) y márgenes seguros para la UI móvil.
- Los subtítulos/karaoke pueden revisarse en HTML/CSS o ASS; si no hay subtítulos posicionados, el QA lo registra como nota, no como aprobación automática de diseño.
- `fabrica_diaria.py` también rechaza el proyecto si falta `pregunta_detonadora`, si alguna descripción no cierra con ella, si el CTA se repite frente a los videos recientes o si el archivo no está guardado en UTF-8 limpio.
- Un fallo de QA borra temporales del proyecto, marca la idea como `fallida` con el motivo exacto y dispara la búsqueda de reemplazo.
- Al cerrar `autopilot_maestro.py`, `housekeeping.py` limpia renders de proyectos publicados hace más de 7 días y `storage_cleaner.py` elimina `node_modules`, frames, temporales y audios intermedios de publicados hace más de 48 h, conservando solo el MP4 final y `metadata.json`; el espacio liberado se escribe en `factory.log` con el tag `[STORAGE]`.
- `carousel_exporter.py` corre después de verificar cada video: toma 3 puntos clave del guion (o de `assets/audio/voz.json`), usa la paleta guardada del proyecto y escribe `<proyecto>/carrusel/01.png`, `02.png`, `03.png` y `manifest.json`, todos a 1080x1350 para Instagram o Comunidad de YouTube.

---

## 14. Aprendizaje con Analytics y primer comentario

- `analytics_feedback.py` consulta YouTube Analytics con `_shared/publisher/youtube_token.json` y escribe `_shared/factory/analytics_feedback.json` con vistas, retención y palabras clave de los Shorts ganadores de los últimos 90 días.
- `trend_hunter.py` usa ese archivo para sumar peso a los temas que ya funcionaron en el canal; si no hay token o permisos, continúa igual y registra el aviso.
- `youtube_upload.py` publica justo después de subir/agendar el mismo `pregunta_detonadora` de `metadata.json` como primer comentario activo (lo aprueba con `setModerationStatus`), para disparar la conversación inicial. Si YouTube no permite comentar o no hay scope, el video sigue agendado y el aviso va al log; nunca se reintenta la subida por este motivo.
- El token de YouTube debe regenerarse con estos scopes: `youtube.upload`, `youtube.force-ssl` e `yt-analytics.readonly`. Sin ellos, subida y programación siguen funcionando, pero comentarios y Analytics quedan desactivados.

---

## 15. Telegram: progreso y resumen

- `notificador_telegram.py` lee `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` desde `_shared/publisher/.env` y envía con `requests`; admite `--test` para verificar el envío.
- `autopilot_maestro.py` avisa al iniciar el ciclo cuántos videos faltan y para qué fechas; `fabrica_diaria.py` envía exactamente tres estatus por video: `🎬 Creando video X/3: [Tema]` con fecha objetivo, `✅ Video X/3 listo y programado` con duración, `YouTube Shorts: hora programada HH:MM` y `TikTok: turno en cola HH:MM`, y errores/reintentos aparte. Si no hay token de TikTok, añade `TIKTOK_ACCESS_TOKEN requiere renovación`.
- `procesar_cola.py` confirma en vivo con `🚀 ¡Video publicado en [Plataforma]!`, título y `Enlace directo` cuando la API lo devuelve.
- Al cerrar cada corrida real se envía además el resumen de los videos fabricados para mañana, sus horarios y las oportunidades de colaboración detectadas en `oportunidades_colab.json`.
- Domingos a las 11:00 se envía el reporte ejecutivo semanal con top 3, gancho ganador y ajuste del algoritmo de temas; también se puede forzar con `python _shared/factory/notificador_telegram.py --semanal`.
- Todas las notificaciones de progreso son silenciosas: si faltan credenciales o Telegram falla, la producción y la cola continúan igual; en `--dry-run` no se envía nada.

---

## Mejoras Continuas de Calidad y Diseño

Actualizado automáticamente el 2026-11-21 por `weekly_upgrade_radar.py`. Solo convierte señales públicas en reglas editoriales; no instala repositorios ni paquetes.

#### Ritmo visual
- Cambia de plano, ángulo, zoom o elemento HUD cada 2–3 segundos para sostener la retención.
- Usa GSAP con eases con nombre (`expo.out`, `power4.out`, `back.out(1.3)`) y stagger breve; prohíbete `ease:"none"` y `ease:"linear"`.
- Mantén la plantilla LOOK fija con una sola paleta por proyecto, tres zonas exclusivas y captions karaoke sincronizadas.

#### Ganchos
- El primer fotograma y la primera línea deben exponer tensión, beneficio o dato concreto antes de 1.5 s.
- Prohíbete arranques genéricos; nombra el modelo, el problema o el resultado verificable.
- Cada red estrena gancho, copy y hashtags propios; reutilizar copy entre plataformas es un error de calidad.

#### Estilo
- Tipografía de impacto con alto contraste, jerarquía clara y microtexto en mayúsculas espaciadas.
- SFX locales en sus tiempos exactos y voz edge-tts normalizada; sin audio remoto ni recursos externos en render.
- Cero `filter:blur`, `backdrop-filter`, CDN o `fetch`; cualquier enfoque nuevo se adopta solo tras validación manual.

#### Señales de la semana · ritmo visual y edición

- inurun/video-admin-template: Admin UI + Remotion stub template for page/TTS editing and video render (https://github.com/inurun/video-admin-template)
- wrg32786/aigent-talking-head: Free, open-source talking-head video editor: turn one phone clip into a captioned reel for TikTok, Reels and Shorts. 51 effects, 29 motion graphics, 56 transitions, local Whisper captions, kinetic typography and an MCP server. Works with Claude Code, Cursor, C (https://github.com/wrg32786/aigent-talking-head)
- nachoweb3/elite-editor: Free local-first video editor with an editable timeline, reviewed AI assistance, GPU effects and local processing. Built on OpenCut. (https://github.com/nachoweb3/elite-editor)

#### Señales de la semana · ganchos y retención

- wrg32786/aigent-talking-head: Free, open-source talking-head video editor: turn one phone clip into a captioned reel for TikTok, Reels and Shorts. 51 effects, 29 motion graphics, 56 transitions, local Whisper captions, kinetic typography and an MCP server. Works with Claude Code, Cursor, C (https://github.com/wrg32786/aigent-talking-head)
- nachoweb3/elite-editor: Free local-first video editor with an editable timeline, reviewed AI assistance, GPU effects and local processing. Built on OpenCut. (https://github.com/nachoweb3/elite-editor)
- NirjharBhattacharjee/mockingbird-studio: A Claude Code plugin that turns your videos into short-form edits (Shorts, Reels, TikTok) with mockingbird: hooks, retention editing, word-by-word captions, b-roll and sound. (https://github.com/NirjharBhattacharjee/mockingbird-studio)

#### Señales de la semana · estilo y diseño

- gg320324492-lgtm/minimax-h3-studio: Local AI video studio: MiniMax-H3 (ComfyUI) generation + Remotion programmatic composition — templates, timeline contracts, QA gates, synthesized audio (https://github.com/gg320324492-lgtm/minimax-h3-studio)
- inurun/video-admin-template: Admin UI + Remotion stub template for page/TTS editing and video render (https://github.com/inurun/video-admin-template)
- XuHo-IT/Content-Agent-Kit: Nói với AI bằng tiếng Việt → tìm chủ đề hot, soi đối thủ, viết bài, dựng video 9:16 với 130 template (có video kể chuyện, giọng đọc tiếng Việt), duyệt rồi mới đăng; kèm bộ công cụ chạy quảng cáo Facebook cho shop. Cài làm skill cho Claude Code hoặc dùng với An (https://github.com/XuHo-IT/Content-Agent-Kit)
