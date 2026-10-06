# -*- coding: utf-8 -*-
"""vigilar.py — Watchdog de entrada humana, dominio LINUX (computer-use-py).

PORT de scripts/vigilar.py (P0-1 del SPEC): el verbo `vigilar arrancar` existe
en Windows y macOS y ahora tambien en Linux: sin X11→pynput; Wayland nativo →
error JSON honesto (coherente con cursor/scroll de la rama), NUNCA traceback
ni "No such file".

Escucha el teclado durante N segundos y, CUANDO EL BACKEND LO PERMITE,
distingue entrada HUMANA de la inyectada por el propio agente gracias al
argumento `injected` de pynput (soporte REAL por backend: verificado en
Windows; en X11/Xorg los eventos XTEST no se marcan de forma fiable
[runtime]). Si el backend nunca entrega `injected`, la bandera ABORT sigue
funcionando (falsa alarma = parada conservadora, segura) pero --pausar-si-humano
SE DESACTIVA solo: crear PAUSA desde pulsaciones del propio bot congelaria al
agente (deadlock del loop).

Flujo (identico al dominio Windows):
1. El agente lanza `arrancar` EN SEGUNDO PLANO antes de la secuencia.
2. Tecla de panico humana (por defecto ESC) => bandera .tmp/ABORT (ruta en el
   JSON). Con --pausar-si-humano y backend que distingue inyectados, cualquier
   pulsacion humana crea ademas .tmp/PAUSA (las acciones la respetan: P1-5).
3. El agente chequea ABORT entre paso y paso y en los interpolados (los
   scripts de la skill ya la honran).
4. Al cumplirse los segundos (o abortar) el listener se para con stop()+join()
   y se imprime el JSON resumen.

Garantias: callbacks SOLO marcan eventos en memoria (I/O en el hilo
principal); NUNCA suppress=True; un listener parado no se reinicia.

Lanzamiento en Linux (desvinculado del terminal del agente):
  nohup python3 scripts/linux/vigilar.py arrancar --segundos 30 \
      --pausar-si-humano > .tmp/vigilar.log 2>&1 &

Subcomandos:
  arrancar  Escuchar el teclado durante N segundos (banderas en .tmp/).
"""

import argparse
import threading
import time

import _compartido_linux as c  # guard de rama + rutas .tmp + JSON canonico
from pynput import keyboard


def cmd_arrancar(args):
    if not (1 <= args.segundos <= 900):
        c.fail("--segundos debe estar entre 1 y 900 (no es un demonio "
               "permanente).")
    sesion = c.deteccion_sesion()
    if sesion != "x11":
        # Wayland nativo/incognito: pynput no tiene listener global de teclado
        # sin X11 (mismo criterio honesto que cursor/scroll de la rama).
        c.fail("watchdog no disponible en Wayland NATIVO: pynput no recibe "
               "eventos globales de teclado sin X11 (el compositor no expone "
               "uno estable a esta skill). Freno humano en Wayland: Ctrl+C en "
               "la consola del agente, o toca .tmp/ABORT a mano (los scripts "
               "lo honran entre acciones).",
               sesion=sesion,
               pista="toca el archivo %s para detener al agente de forma "
                     "cooperativa" % c.ARCHIVO_ABORT)
    tecla_panic = c.tecla_pynput(args.tecla_panic)
    if tecla_panic is None:
        c.fail("Tecla de panico %r no existe en pynput.keyboard.Key. "
               "Nombres validos: esc, f13, media_play_pause, ctrl_l, ..."
               % args.tecla_panic)

    # Estado limpio: banderas de la secuencia anterior no deben confundir.
    c.borrar(c.ARCHIVO_ABORT)
    c.borrar(c.ARCHIVO_PAUSA)

    abortado = threading.Event()
    humano = threading.Event()          # SOLO cuando el backend distingue
    inyectado_visible = threading.Event()  # el backend entrego `injected`
    pulsaciones_registradas = []

    def on_press(key, injected=None):
        # Callback en el hilo del listener: SOLO marcar, nada de I/O ni sleep.
        # pynput pasa `injected` si el backend lo soporta; en X11 puede NO
        # pasarla (XTEST no se marca de forma fiable [runtime]).
        if injected is not None:
            inyectado_visible.set()
            if injected:
                return  # evento sintetico del propio bot: no es humano
            humano.set()
        pulsaciones_registradas.append(repr(key))
        if key == tecla_panic:
            abortado.set()
            return False  # parar el listener desde el callback (doc pynput)

    banderas = {"abort": False, "pausa": False}
    pausa_degradada = {"avisado": False}

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

    pausa_realizable = inyectado_visible.is_set()
    item = {
        "ok": True,
        "escuchado_segundos": args.segundos,
        "abortado": abortado.is_set(),
        "hubo_entrada_humana": humano.is_set() if pausa_realizable else None,
        "injected_visible": pausa_realizable,
        "tecla_panic": args.tecla_panic,
        "sesion": sesion,
        "archivo_abort": c.ARCHIVO_ABORT if banderas["abort"] else None,
        "archivo_pausa": c.ARCHIVO_PAUSA if banderas["pausa"] else None,
        "nota": "si existe la bandera ABORT del .tmp de ESTA skill (ruta en "
                "'archivo_abort'), el agente DEBE parar la secuencia, capturar "
                "la pantalla y preguntar; tras atender, borrar la bandera y "
                "relanzar el watchdog. P1-5: los scripts respetan PAUSA al "
                "arrancar cada accion.",
    }
    if args.pausar_si_humano and not pausa_realizable:
        item["nota"] += (" AVISO: el backend X11 no reporto el flag "
                         "'injected' durante la escucha: PAUSA NO se creo "
                         "(evita el auto-bloqueo del agente); sigue usando "
                         "ABORT/tecla de panico como freno." if not banderas["pausa"]
                         else " AVISO: PAUSA se cree solo con origen humano "
                         "verificable.")
    c.json_out(item)


def construir_parser():
    parser = c.Parser(
        prog="vigilar.py (linux)",
        description="Watchdog de entrada humana (listener pynput, X11): la "
                    "tecla de panico crea la bandera ABORT en el .tmp de ESTA "
                    "skill; Wayland nativo responde error JSON honesto.",
        epilog=__doc__.split("Subcomandos:")[1] if __doc__ and "Subcomandos:" in __doc__ else None,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    p = sub.add_parser("arrancar", help="escuchar el teclado N segundos "
                       "(lanzalo en segundo plano)")
    p.add_argument("--segundos", type=int, required=True,
                   help="duracion de la escucha (1-900)")
    p.add_argument("--tecla-panic", default="esc", metavar="TECLA",
                   help="tecla humana que aborta (nombre pynput.keyboard.Key; "
                        "por defecto esc)")
    p.add_argument("--pausar-si-humano", dest="pausar_si_humano",
                   action="store_true",
                   help="cualquier pulsacion HUMANA verificable crea "
                        ".tmp/PAUSA (las acciones esperan; ver nota)")
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
