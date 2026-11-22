import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_EDGE_VOICE = "es-MX-JorgeNeural"
DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_MODEL_ID = "eleven_flash_v2_5"
API_URL = "https://api.elevenlabs.io/v1/text-to-speech"


def preparar_salida(salida):
    directorio = os.path.dirname(os.path.abspath(salida))
    os.makedirs(directorio, exist_ok=True)


def generar_borrador(args):
    preparar_salida(args.salida)
    comando = [
        sys.executable,
        "-m",
        "edge_tts",
        "--voice",
        args.voz_edge,
        "--rate",
        args.rate,
        "--text",
        args.texto,
        "--write-media",
        args.salida,
        "--no-progress",
    ]
    resultado = subprocess.run(comando, text=True, capture_output=True)
    if resultado.returncode != 0:
        detalle = (resultado.stderr or resultado.stdout).strip()
        sys.exit(f"Error de edge-tts ({resultado.returncode}): {detalle}")
    print(f"BORRADOR edge-tts [{args.voz_edge}] -> {args.salida}")


def generar_final(args):
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        sys.exit("Error: --final necesita la variable de entorno ELEVENLABS_API_KEY.")

    voice_id = urllib.parse.quote(args.voice_id, safe="")
    url = f"{API_URL}/{voice_id}?{urllib.parse.urlencode({'output_format': 'mp3_44100_128'})}"
    payload = json.dumps({
        "text": args.texto,
        "model_id": DEFAULT_MODEL_ID,
        "language_code": "es",
    }).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            audio = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        sys.exit(f"Error de ElevenLabs ({error.code}): {detail}")
    except urllib.error.URLError as error:
        sys.exit(f"Error de conexión con ElevenLabs: {error.reason}")

    preparar_salida(args.salida)
    with open(args.salida, "wb") as file:
        file.write(audio)
    print(f"FINAL ElevenLabs [{DEFAULT_MODEL_ID}] -> {args.salida}")


def main():
    parser = argparse.ArgumentParser(
        description="Voz en MP3: edge-tts gratis por defecto; ElevenLabs solo con --final."
    )
    parser.add_argument("texto", help="Texto a narrar")
    parser.add_argument("salida", help="Ruta del archivo MP3 de salida")
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument(
        "--borrador",
        action="store_true",
        help="Usar edge-tts gratis (modo por defecto)",
    )
    modo.add_argument(
        "--final",
        action="store_true",
        help="Usar ElevenLabs eleven_flash_v2_5 (consume créditos)",
    )
    parser.add_argument(
        "--voz-edge",
        default=DEFAULT_EDGE_VOICE,
        help=f"Voz edge-tts para borradores (default: {DEFAULT_EDGE_VOICE})",
    )
    parser.add_argument(
        "--voice-id",
        default=DEFAULT_VOICE_ID,
        help="ID de voz de ElevenLabs solo para --final",
    )
    parser.add_argument(
        "--rate",
        default="+0%",
        help="Velocidad edge-tts, por ejemplo +10%% o -5%% (default: +0%%)",
    )
    args = parser.parse_args()

    if args.final:
        generar_final(args)
    else:
        generar_borrador(args)


if __name__ == "__main__":
    main()
