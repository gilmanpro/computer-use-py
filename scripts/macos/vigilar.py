# -*- coding: utf-8 -*-
"""vigilar.py — Watchdog de entrada humana en macOS (listener pynput, skill
computer-use-py, dominio mac).

Escucha el teclado durante N segundos y distingue entrada HUMANA de la
inyectada por el propio bot gracias al argumento `injected` de los callbacks:
VERIFICADO fuente pynput 1.8.2 keyboard/_darwin.py:279-330 — el listener
darwin (CGEventTapCreate en kCGSessionEventTap, _util/darwin.py:272-279)
pasa `injected` a on_press/on_release.

EQUIVALENTE DEL FAILSAFE: pyautogui (esquinas que abortan) NO interviene en
este dominio; el freno humano canonico de mac es ESTE script: la tecla de
panico (ESC por defecto, configurable) no inyectada crea la bandera
.tmp/ABORT que el agente revisa entre paso y paso [runtime: depende del
permiso TCC Accesibilidad — limitations.html: el MONITOREO de teclado exige
whitelist del binario Python o del terminal; pynput lo reporta con
IS_TRUSTED, se emite en el JSON].

Flujo (identico al vigilar.py de Windows):
1. El agente lanza `arrancar` EN SEGUNDO PLANO justo antes de una serie de
   acciones y sigue con su loop:
     nohup python3 scripts/macos/vigilar.py arrancar --segundos 30 \
         --pausar-si-humano > .tmp/vigilar.log 2>&1 &
   (o desde Python propio: subprocess.Popen(..., stdout=archivo,
   start_new_session=True) — el equivalente mac del CREATE_NO_WINDOW).
2. Si el usuario pulsa la tecla de panico, este proceso crea .tmp/ABORT.
3. El agente comprueba la bandera entre paso y paso; si existe: parar,
   capturar y preguntar. Con --pausar-si-humano, cualquier pulsacion humana
   crea tambien .tmp/PAUSA (aviso suave).
4. Al cumplirse los segundos (o al abortar) el listener se para con
   stop()+join() y se imprime el JSON resumen.

Garantias y limites (VERIFICADO docs/fuente pynput):
- Los callbacks SOLO marcan eventos en memoria (threading.Event); todo I/O
  ocurre en el hilo principal.
- NO se usa suppress: suppress=True (o darwin_intercept que no devuelve el
  evento) suprime la entrada a TODO el sistema (docs mouse/keyboard.html):
  prohibido.
- Un listener parado no se reinicia (Thread): cada secuencia relanza este
  proceso.
- La escucha exige TCC Accesibilidad; sin ella el listener arranca pero no
  ve nada (IS_TRUSTED=false en el JSON) [runtime].

Salida: JSON por stdout; errores JSON con "error".

Subcomandos:
  arrancar  Escuchar el teclado durante N segundos (banderas en .tmp/).

Ejemplo (desde la carpeta computer-use-py, en el Mac):
  nohup python3 scripts/macos/vigilar.py arrancar --segundos 30 --pausar-si-humano > .tmp/vigilar.log 2>&1 &
"""

import argparse
import threading
import time

import _compartido_mac as c


def cmd_arrancar(args):
    if not (1 <= args.segundos <= 900):
        c.fail("--segundos debe estar entre 1 y 900 (no es un demonio "
               "permanente).")
    keyboard = c.try_pynput()
    tecla_panic = c.tecla_pynput_mac(args.tecla_panic)
    if tecla_panic is None:
        c.fail("Tecla de panico %r no existe en pynput.keyboard.Key (darwin). "
               "Nombres validos: esc, f5, media_play_pause, cmd, ctrl_l..."
               % args.tecla_panic)

    # Estado limpio: banderas de la secuencia anterior no deben confundir.
    c.borrar(c.ARCHIVO_ABORT)
    c.borrar(c.ARCHIVO_PAUSA)

    abortado = threading.Event()
    humano = threading.Event()
    pulsaciones_humanas = []

    def on_press(key, injected):
        # Callback en el hilo del tap: SOLO marcar, nada de I/O ni sleep.
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
    listener.wait()  # hasta que el tap esta instalado (doc pynput)
    # VERIFICADO limitations.html: todos los Listener tienen IS_TRUSTED.
    is_trusted = bool(getattr(listener, "IS_TRUSTED", True))
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

    resumen = {
        "ok": True,
        "escuchado_segundos": args.segundos,
        "abortado": abortado.is_set(),
        "hubo_entrada_humana": humano.is_set(),
        "is_trusted": is_trusted,
        "tecla_panic": args.tecla_panic,
        "archivo_abort": c.ARCHIVO_ABORT if banderas["abort"] else None,
        "archivo_pausa": c.ARCHIVO_PAUSA if banderas["pausa"] else None,
        "nota": ("si existe la bandera ABORT del .tmp de ESTA skill (ruta "
                 "absoluta en 'archivo_abort'), el agente DEBE parar la "
                 "secuencia, capturar la pantalla y preguntar; tras atender, "
                 "borrar la bandera y relanzar el watchdog si continua; "
                 "PAUSA (si --pausar-si-humano) detiene el ARRANQUE de cada "
                 "accion hasta que se borre"),
    }
    if not is_trusted:
        # VERIFICADO limitations.html: sin whitelist de Accesibilidad el
        # monitoreo de teclado no ve nada: el watchdog NO puede frenar.
        resumen["hubo_entrada_humana"] = False
        resumen["aviso"] = (
            "IS_TRUSTED=false: SIN permiso TCC Accesibilidad el listener NO "
            "ve el teclado (limitations.html). Concede Accesibilidad a este "
            "binario Python (o al Terminal que lo lanza), reabre la sesion "
            "del proceso y relanza el watchdog: mientras, el freno humano "
            "disponible es Ctrl+C en la consola.")
    c.json_out(resumen)


def construir_parser():
    parser = c.Parser(
        prog="vigilar.py (macOS)",
        description="Watchdog de entrada humana con listener pynput (tap de "
                    "Sesion Quartz): ESC (u otra tecla) HUMANA crea la "
                    "bandera ABORT en el .tmp de ESTA skill — el freno "
                    "canonico del dominio mac (no hay FAILSAFE pyautogui "
                    "aqui). Exige TCC Accesibilidad (IS_TRUSTED).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1]
        if __doc__ and "Subcomandos:" in __doc__ else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True,
                                metavar="SUBCOMANDO")

    p = sub.add_parser("arrancar",
                       help="escuchar el teclado N segundos (lanzado en "
                            "segundo plano)")
    p.add_argument("--segundos", type=int, required=True,
                   help="duracion de la escucha (1-900)")
    p.add_argument("--tecla-panic", default="esc", metavar="TECLA",
                   help="tecla humana que aborta (nombre "
                        "pynput.keyboard.Key; por defecto esc)")
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
