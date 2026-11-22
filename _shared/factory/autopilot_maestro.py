from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parents[2]
FACTORY_DIR = Path(__file__).resolve().parent
LOCK_PATH = FACTORY_DIR / "factory.lock"
LOG_PATH = FACTORY_DIR / "factory.log"
FALLOS_PATH = FACTORY_DIR / "fallos_recuperacion.json"
MAX_EDAD_LOCK_HORAS = 8

if str(FACTORY_DIR) not in sys.path:
    sys.path.insert(0, str(FACTORY_DIR))
if str(ROOT_DIR / "_shared" / "publisher") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "_shared" / "publisher"))

import fabrica_diaria
import housekeeping
import notificador_telegram
import scheduler_manager
import storage_cleaner
import publicar_todo


def log(mensaje: str) -> None:
    fabrica_diaria.log(f"[AUTOPILOTO] {mensaje}")


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_fecha(valor: Any) -> datetime | None:
    texto = str(valor or "").strip().replace("Z", "+00:00")
    if not texto:
        return None
    try:
        fecha = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)


def proceso_activo(pid: Any) -> bool:
    try:
        numero = int(pid)
    except (TypeError, ValueError):
        return False
    try:
        proceso = subprocess.run(
            ["tasklist", "/FI", f"PID eq {numero}", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    return str(numero) in (proceso.stdout or "")


def lock_vencido() -> bool:
    if not LOCK_PATH.is_file():
        return True
    try:
        datos = json.loads(LOCK_PATH.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return True
    inicio = parse_fecha(datos.get("inicio")) or parse_fecha(datos.get("creado_en"))
    if inicio is None:
        return True
    if ahora_utc() - inicio > timedelta(hours=MAX_EDAD_LOCK_HORAS):
        return True
    return not proceso_activo(datos.get("pid"))


@contextmanager
def bloqueo_instancia() -> Iterator[None]:
    if LOCK_PATH.exists():
        if not lock_vencido():
            raise RuntimeError(f"Ya hay una instancia activa: {LOCK_PATH}")
        log(f"Lock huérfano eliminado: {LOCK_PATH}")
        LOCK_PATH.unlink(missing_ok=True)

    datos = {
        "pid": os.getpid(),
        "inicio": ahora_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "equipo": os.environ.get("COMPUTERNAME", ""),
    }
    descriptor = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(descriptor, (json.dumps(datos, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    finally:
        os.close(descriptor)

    try:
        yield
    finally:
        LOCK_PATH.unlink(missing_ok=True)


def registrar_fallo(fecha: datetime.date, mensaje: str) -> None:
    historial: list[dict[str, Any]] = []
    if FALLOS_PATH.is_file():
        try:
            datos = json.loads(FALLOS_PATH.read_text(encoding="utf-8", errors="replace"))
            if isinstance(datos, dict) and isinstance(datos.get("fallos"), list):
                historial = datos["fallos"]
        except (OSError, json.JSONDecodeError):
            historial = []
    historial.append(
        {
            "fecha": fecha.isoformat(),
            "detectado_en": ahora_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "mensaje": mensaje[:1000],
        }
    )
    FALLOS_PATH.write_text(
        json.dumps({"fallos": historial[-100:]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validar_credenciales_prevuelo() -> tuple[bool, list[str]]:
    problemas: list[str] = []
    for plataforma in ("youtube", "tiktok"):
        try:
            ok, detalle = publicar_todo.credentials_configured(plataforma)
        except Exception as error:
            ok, detalle = False, f"{type(error).__name__}: {error}"
        if not ok:
            mensaje = f"{plataforma}: {detalle or 'credenciales no configuradas'}"
            problemas.append(mensaje)
            try:
                notificador_telegram.notificar_alerta_token(plataforma, detalle or "credencial faltante o inválida")
            except Exception:
                pass
    return not problemas, problemas


def fechas_objetivo(solo_fecha: str | None = None) -> list[datetime.date]:
    if solo_fecha:
        fecha = datetime.strptime(solo_fecha, "%Y-%m-%d").date()
        return [fecha]
    hoy = scheduler_manager.ahora_local().date()
    return [hoy, hoy + timedelta(days=1)]


def procesar_fecha(
    fecha: datetime.date, dry_run: bool, notificar_inicio: bool = False, idioma: str = "es"
) -> bool:
    agendados = fabrica_diaria.contar_agendados_para(fecha)
    faltantes = max(0, fabrica_diaria.CUPO_DIARIO - agendados)
    log(f"Fecha {fecha.isoformat()}: agendados={agendados} faltantes={faltantes}")
    if faltantes == 0:
        return True

    argv = ["--fecha", fecha.isoformat(), "--idioma", idioma]
    if dry_run:
        argv.append("--dry-run")
    try:
        codigo = fabrica_diaria.main(argv, notificar_inicio=notificar_inicio)
    except Exception as error:
        mensaje = f"{type(error).__name__}: {error}"
        log(f"Fallo recuperable en {fecha.isoformat()}: {mensaje}")
        registrar_fallo(fecha, mensaje)
        return False

    if codigo == 0:
        log(f"Cobertura completada para {fecha.isoformat()}")
        return True

    mensaje = f"fabrica_diaria devolvió exit={codigo}; se continúa con la siguiente jornada"
    log(f"Fallo recuperable en {fecha.isoformat()}: {mensaje}")
    registrar_fallo(fecha, mensaje)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Autopiloto maestro con recuperación y bloqueo de instancia.")
    parser.add_argument("--dry-run", action="store_true", help="Simula la cobertura sin generar videos")
    parser.add_argument("--fecha", help="Fecha específica YYYY-MM-DD; por defecto hoy y mañana")
    parser.add_argument("--idioma", choices=("es", "en"), default="es", help="Idioma de exportación: es o en")
    args = parser.parse_args(argv)

    try:
        fechas = fechas_objetivo(args.fecha)
    except ValueError:
        print("[ERROR] --fecha debe usar YYYY-MM-DD", file=sys.stderr)
        return 1

    log("=== Inicio autopiloto maestro ===")
    try:
        with bloqueo_instancia():
            log(f"Objetivos: {', '.join(fecha.isoformat() for fecha in fechas)}")
            faltantes_por_fecha = {
                fecha.isoformat(): max(
                    0,
                    fabrica_diaria.CUPO_DIARIO - fabrica_diaria.contar_agendados_para(fecha),
                )
                for fecha in fechas
            }
            if not args.dry_run and any(faltantes_por_fecha.values()):
                ok_cred, problemas = validar_credenciales_prevuelo()
                if not ok_cred:
                    for problema in problemas:
                        log(f"[CREDENCIALES] {problema}")
                    log("Abortado: credenciales YouTube/TikTok inválidas antes de producir")
                    return 2
                notificador_telegram.notificar_inicio_lote(
                    faltantes_por_fecha, [fecha.isoformat() for fecha in fechas]
                )
            resultados = [
                procesar_fecha(fecha, args.dry_run, idioma=args.idioma) for fecha in fechas
            ]
    except RuntimeError as error:
        log(f"Abortado: {error}")
        return 0
    except Exception as error:
        mensaje = f"{type(error).__name__}: {error}"
        log(f"Fallo crítico: {mensaje}")
        registrar_fallo(scheduler_manager.ahora_local().date(), mensaje)
        return 1

    log(f"Fin autopiloto: jornadas_ok={sum(resultados)}/{len(resultados)}")
    if args.dry_run:
        log("Housekeeping omitido en dry-run")
    else:
        try:
            limpieza = housekeeping.limpiar()
            log(
                f"Housekeeping: proyectos={limpieza['proyectos']} "
                f"temporales_eliminados={limpieza['eliminados']}"
            )
        except Exception as error:
            log(f"Housekeeping falló: {type(error).__name__}: {error}")
        try:
            limpieza_disco = storage_cleaner.limpiar()
            log(
                f"Storage cleaner: proyectos={limpieza_disco['proyectos']} "
                f"temporales={limpieza_disco['eliminados']} "
                f"liberado_mb={limpieza_disco['liberado_mb']}"
            )
        except Exception as error:
            log(f"Storage cleaner falló: {type(error).__name__}: {error}")
    if args.dry_run:
        log("Notificación Telegram omitida en dry-run")
    else:
        try:
            aviso = notificador_telegram.enviar_resumen(fechas[-1])
            log(
                f"Telegram: {aviso['estado']} fecha={aviso['fecha']} "
                f"caracteres={aviso['caracteres']}"
            )
        except Exception as error:
            log(f"Telegram falló: {type(error).__name__}: {error}")
    log("=== Fin autopiloto maestro ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
