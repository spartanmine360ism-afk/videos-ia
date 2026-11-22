---
name: auditar-videos-ia
description: Use when auditing, cleaning, or repairing the videos-ia factory in C:\Users\aldo_\Desktop\videos-ia, especially _shared/factory, _shared/publisher, _shared/skills_ext, fabrica_diaria.py, publicar_todo.py, procesar_cola.py, qa_video.py, or cover_generator.py. Enforces UTF-8, protected media/metadata/credentials, safe temp cleanup, and py_compile verification.
---

# Auditar videos-ia

Audita y repara el proyecto `videos-ia` de forma conservadora, verificable y sin publicar nada.

## Alcance

Trabaja solo dentro de `C:\Users\aldo_\Desktop\videos-ia`. Prioriza:

- `_shared/factory/`
- `_shared/publisher/`
- `_shared/skills_ext/`
- `.opencode/`
- `opencode.json`

No modifiques videos de proyectos terminados salvo que el usuario lo pida explícitamente.

## Reglas de seguridad

- Usa UTF-8 para leer y escribir todo texto, JSON, Markdown y Python: `encoding="utf-8"`.
- Nunca borres ni sobrescribas sin confirmación explícita:
  - `*.mp4`, `*.mov`
  - `metadata.json`, `config.json`, `meta.json`
  - `renders/portada*.jpg`, `renders/cover.jpg`
  - `.env`, `client_secret.json`, `*_token.json`, credenciales o secretos
  - `schedule_queue.json` (si está corrupto, respalda con otro nombre y reconstruye en memoria)
- Nunca imprimas tokens, claves ni contenidos de `.env`.
- No ejecutes `publicar_todo.py`, subidas, renderizados ni publicaciones durante una auditoría, salvo petición explícita.
- No instales paquetes nuevos. Usa solo dependencias ya presentes o la lista blanca de `AGENTS.md`.
- No elimines un archivo solo por su nombre: verifica que no sea importado, referenciado ni necesario.

## Inventario

Antes de tocar nada:

1. Lista `SKILL.md` disponibles, `opencode.json` y `.opencode/`.
2. Lista `_tmp_*`, `*.tmp`, `*.bak`, `*.py.bak`, duplicados y scripts huérfanos.
3. Separa tres grupos: eliminable, conservar, requiere confirmación.
4. Muestra rutas exactas antes de borrar.

## Auditoría de Python

Para cada módulo tocado:

1. Verifica imports relativos y `sys.path` para ejecución directa.
2. Detecta imports no usados, ciclos, funciones duplicadas y variables muertas.
3. Revisa lecturas/escrituras JSON y texto: deben usar UTF-8 explícito.
4. Revisa manejo de excepciones: ningún `except` debe dejar una excepción muda que rompa el flujo.
5. Revisa reintentos: un fallo de una plataforma o de un archivo no debe detener a las demás.
6. Verifica que `pregunta_detonadora` exista en `youtube`, `tiktok`, `instagram` y `facebook`, y que cada `description` termine exactamente con esa pregunta.

## Correcciones permitidas

- Mejorar mensajes de error y agregar fallbacks seguros.
- Hacer que archivos JSON vacíos o corruptos se respalden y no aborten el proceso.
- Ajustar timeouts y cachés para evitar cuellos de botella.
- Corregir legibilidad/contraste/zona segura en portadas y QA sin borrar portadas existentes.
- Crear skills de proyecto en `.opencode/skills/<nombre>/SKILL.md` cuando falten.

## Limpieza

Elimina solo temporales claramente generados por el propio flujo, por ejemplo:

- `_tmp_*.py`
- `*.tmp` de escrituras atómicas ya completadas
- frames temporales de QA y `.frame_*.jpg` huérfanos

Conserva siempre archivos finales, metadata, portadas, credenciales y backups que puedan contener trabajo del usuario.

## Verificación obligatoria

Tras cualquier cambio:

```powershell
$py = Get-ChildItem _shared/factory/*.py,_shared/publisher/*.py | ForEach-Object { $_.FullName }
python -m py_compile @py
```

Si el cambio afecta al flujo autónomo, ejecuta además:

```powershell
python _shared/factory/autopilot_maestro.py --dry-run
```

No consideres terminada la tarea si hay errores de sintaxis o si el dry-run falla por una excepción nueva.

## Reporte

Entrega siempre:

1. Qué se auditó y qué se encontró.
2. Qué se arregló, con rutas de archivos.
3. Qué se eliminó, con lista exacta.
4. Qué se conservó y qué requiere acción manual del usuario.
5. Resultado de `py_compile` y, si aplica, del dry-run.
