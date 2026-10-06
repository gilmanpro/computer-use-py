# -*- coding: utf-8 -*-
"""vigilar.py — Watchdog de entrada humana (listener pynput, skill computer-use-py).

ENTRADA MULTI-OS (FASE SEG2): `python scripts/vigilar.py ...` vale en los 3
SO — en Windows ejecuta esta ruta nativa (validada en escritorio real); en
Linux/macOS enruta TRANSPARENTemente al motor de su rama (scripts/linux|macos/)
re-emitiendo su JSON y su exit code; plataforma desconocida responde JSON + rc 2.

Escucha el teclado durante N segundos y distingue entrada HUMANA de la
inyectada por el propio agente gracias al argumento `injected` de los
callbacks (pynput >= 1.8.0, soportado de verdad en Windows via flags
LLKHF_INJECTED/LLKHF_LOWER_IL_INJECTED del hook). Sin ese filtro, los envios
del propio bot dispararian la pausa (bucle de realimentacion).

Flujo pensado:
1. El agente lanza `arrancar` EN SEGUNDO PLANO justo antes de una serie de
   acciones y sigue con su loop.
2. Si el usuario pulsa la tecla de panico (por defecto ESC humana), el
   listener lo detecta y este proceso crea la bandera ABORT dentro del .tmp
   de ESTA skill (el JSON devuelve su ruta absoluta).
3. El agente comprueba el flag entre paso y paso (existencia de
   .tmp/ABORT); si existe, detiene la secuencia, mira la pantalla y
   pregunta. Con --pausar-si-humano, cualquier pulsacion humana ademas crea
   .tmp/PAUSA (aviso suave, no detiene la escucha).
4. Al cumplirse los segundos (o al abortar) el listener se para con
   stop()+join() y el proceso imprime un JSON resumen.

Garantias y limites (verificados en el digest de pynput):
- Los callbacks SOLO marcan banderas en memoria (threading.Event); todo I/O
  ocurre en el hilo principal: un callback lento en el hilo del hook
  WH_KEYBOARD_LL puede congelar la entrada de TODO el sistema operativo.
- NO se usa suppress: suppress=True suprime el evento a todo el sistema (el
  usuario se queda sin teclado, ni Ctrl+C). Aqui solo se observa.
- Un listener parado no se reinicia: cada secuencia lanza este proceso de
  nuevo (semantica de Thread, doc de pynput "Toggling").

Lanzamiento (importante — evidencia H5-SEC 05/10/2026): si el entorno del
agente corta los pipes al terminar la llamada, un segundo plano HEREDADO
(`start /b` sobre la misma consola) muere con el pipe y la escucha jamas
existe. Regla: lanzar `arrancar` como PROCESO APARTE (desvinculado de la
consola del agente) con su salida redirigida a un archivo del .tmp: en
ventana nueva con `start ""` (sin /b), o desde codigo propio con
subprocess.Popen(..., stdout=<archivo del .tmp>,
creationflags=DETACHED_PROCESS). El canal fiable hacia el agente es la
bandera ABORT del .tmp, que no depende de que sobreviva el stdout: aunque
el proceso hijo se corte, el JSON resumen es solo informativo.

Salida: JSON por stdout; errores JSON con "error".

Subcomandos:
  arrancar  Escuchar el teclado durante N segundos (banderas en .tmp/).

Ejemplo (desde la carpeta computer-use-py, en proceso separado con ventana
propia y escucha de 30 s):
  start "" py scripts\\vigilar.py arrancar --segundos 30 --pausar-si-humano
"""

import argparse
import os
import sys
import threading
import time

# Deteccion de plataforma ANTES de los imports exclusivos Windows (pynput
# puede fallar al importar sin sesion grafica: en otro SO se enruta primero).
if sys.platform != "win32":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _core
    _core.enrutar("vigilar.py")  # nunca retorna en linux/darwin/desconocida

import glue_windows as c  # rutas .tmp y JSON canonico (no toca el raton/teclado)
from pynput import keyboard


def cmd_arrancar(args):
    c.validar_segundos(args.segundos)  # rango generico en _core (3x identico)
    tecla_panic = c.tecla_pynput(args.tecla_panic)
    if tecla_panic is None:
        c.fail("Tecla de panico %r no existe en pynput.keyboard.Key. "
               "Nombres validos: esc, f13, media_play_pause, ctrl_l, ..."
               % args.tecla_panic)

    # Estado limpio: banderas de la secuencia anterior no deben confundir.
    c.borrar(c.ARCHIVO_ABORT)
    c.borrar(c.ARCHIVO_PAUSA)

    abortado = threading.Event()
    humano = threading.Event()
    pulsaciones_humanas = []

    def on_press(key, injected):
        # Callback en el hilo del hook LL: SOLO marcar, nada de I/O ni sleep.
        if injected:
            return  # evento inyectado (nuestro propio bot u otro automation)
        humano.set()
        pulsaciones_humanas.append(repr(key))
        if key == tecla_panic:
            abortado.set()
            return False  # parar el listener desde el callback (doc pynput)

    banderas = {"abort": False, "pausa": False}

    def escribir_banderas():
        # I/O SIEMPRE en el hilo principal, nunca desde el callback.
        if abortado.is_set() and not banderas["abort"]:
            c.tocar(c.ARCHIVO_ABORT)
            banderas["abort"] = True
        if args.pausar_si_humano and humano.is_set() and not banderas["pausa"]:
            c.tocar(c.ARCHIVO_PAUSA)
            banderas["pausa"] = True

    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    listener.wait()  # hasta que el hook esta instalado (doc pynput)
    try:
        limite = time.time() + args.segundos
        while time.time() < limite:
            escribir_banderas()
            if abortado.is_set():
                break
            time.sleep(0.05)
    finally:
        escribir_banderas()
        try:
            listener.stop()
        except Exception:
            pass
        listener.join()

    c.json_out({
        "ok": True,
        "escuchado_segundos": args.segundos,
        "abortado": abortado.is_set(),
        "hubo_entrada_humana": humano.is_set(),
        "tecla_panic": args.tecla_panic,
        "archivo_abort": c.ARCHIVO_ABORT if banderas["abort"] else None,
        "archivo_pausa": c.ARCHIVO_PAUSA if banderas["pausa"] else None,
        "nota": "si existe la bandera ABORT del .tmp de ESTA skill (ruta "
                "absoluta en 'archivo_abort'), el agente DEBE parar la "
                "secuencia, capturar la pantalla y preguntar; tras atender, "
                "borrar la bandera y relanzar el watchdog si continua",
    })


def construir_parser():
    parser = c.Parser(
        prog="vigilar.py",
        description="Watchdog de entrada humana con listener pynput: ESC "
                    "(u otra tecla) humana crea la bandera ABORT en el .tmp "
                    "de ESTA skill para que el agente pare la secuencia "
                    "entre pasos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1] if __doc__ and "Subcomandos:" in __doc__ else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    p = sub.add_parser("arrancar", help="escuchar el teclado N segundos (lanzalo en segundo plano)")
    p.add_argument("--segundos", type=int, required=True,
                   help="duracion de la escucha (1-900)")
    p.add_argument("--tecla-panic", default="esc", metavar="TECLA",
                   help="tecla humana que aborta (nombre pynput.keyboard.Key; "
                        "por defecto esc)")
    p.add_argument("--pausar-si-humano", action="store_true",
                   help="cualquier pulsacion humana crea tambien .tmp/PAUSA "
                        "(aviso suave entre pasos; no detiene la escucha)")
    p.set_defaults(func=cmd_arrancar)

    return parser


def main():
    args = construir_parser().parse_args()
    try:
        args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        c.fail("%s: %s" % (type(exc).__name__, exc))


if __name__ == "__main__":
    main()
