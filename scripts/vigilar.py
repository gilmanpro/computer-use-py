# -*- coding: utf-8 -*-
"""vigilar.py — Watchdog de entrada humana (listener pynput, skill computer-use-py).

ENTRADA MULTI-OS (FASE SEG3): `python scripts/vigilar.py ...` vale en los 3
SO — el CLI ejecuta la ruta de TU SO EN EL PROPIO PROCESO (dispatch por
sys.platform en tiempo de ejecucion, bind `c = _core.modulo_sistema()`): en
Windows la ruta nativa de abajo (pynput se importa en la rama win de main());
en Linux/macOS las primitivas exclusivas viven en la libreria scripts/linux/
linux_especiales.py o scripts/macos/macos_especiales.py; plataforma
desconocida responde JSON + rc 2.

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

_DIR_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _DIR_SCRIPTS not in sys.path:
    sys.path.insert(0, _DIR_SCRIPTS)
import _core  # noqa: E402  (genericos multi-OS + modulo_sistema: dispatch en tiempo de ejecucion)

# ===========================================================================
# SECCION WINDOWS — ruta nativa pynput (cuerpos VERBATIM del CLI SEG2; `c` =
# glue_windows y `keyboard` se bind-eean en la rama win de main()).
# ===========================================================================


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


def construir_parser_win():
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


# ===========================================================================
# SECCION LINUX — cuerpo de scripts/linux/vigilar.py movado VERBATIM (sufijo
# _linux; `c` = scripts/linux/linux_especiales.py, bind-eeado en main()).
# UNICA desviacion documentada: el `from pynput import keyboard` que la rama
# tenia en el top del modulo se ejecuta LAZY dentro de cmd_arrancar_linux
# (en SEG3 el CLI raiz no puede importar pynput al arrancar en otros SO; el
# lazismo conserva el contrato JSON: sin pynput responde c.fail, no traceback).
# Marco: px_layout.
# ===========================================================================

_DOC_LINUX = """vigilar.py — Watchdog de entrada humana, dominio LINUX (computer-use-py).

PORT de la ruta Windows original del watchdog (P0-1 del SPEC): el verbo
`vigilar arrancar` existe
en los 3 dominios; aqui es el MOTOR LINUX (la entrada normal es el CLI de la
raiz scripts/vigilar.py, que ejecuta ESTA ruta en el propio proceso en Linux). X11→pynput; Wayland nativo →
error JSON honesto (coherente con cursor/scroll del motor), NUNCA traceback
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

Lanzamiento en Linux (desvinculado del terminal del agente; el CLI de la raiz
usa esta ruta en el propio proceso):
  nohup python3 scripts/vigilar.py arrancar --segundos 30 \
      --pausar-si-humano > .tmp/vigilar.log 2>&1 &

Subcomandos:
  arrancar  Escuchar el teclado durante N segundos (banderas en .tmp/).
"""


def cmd_arrancar_linux(args):
    from pynput import keyboard  # SEG3: LAZY (era import de top de la rama)
    c.validar_segundos(args.segundos)  # rango generico en _core (3x identico)
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


def construir_parser_linux():
    parser = c.Parser(
        prog="vigilar.py (linux)",
        description="Watchdog de entrada humana (listener pynput, X11): la "
                    "tecla de panico crea la bandera ABORT en el .tmp de ESTA "
                    "skill; Wayland nativo responde error JSON honesto.",
        epilog=_DOC_LINUX.split("Subcomandos:")[1] if _DOC_LINUX and "Subcomandos:" in _DOC_LINUX else None,
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
    p.set_defaults(func=cmd_arrancar_linux)

    return parser


# ===========================================================================
# SECCION macOS — cuerpo de scripts/macos/vigilar.py movado VERBATIM (sufijo
# _mac; `c` = scripts/macos/macos_especiales.py: try_pynput/tecla_pynput_mac/
# banderas del .tmp). La rama ya traia pynput LAZY via c.try_pynput(): cero
# desviaciones aqui. Marco: puntos_logicos.
# ===========================================================================

_DOC_MAC = """vigilar.py — Watchdog de entrada humana en macOS (listener pynput, skill
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
     nohup python3 scripts/vigilar.py arrancar --segundos 30 \
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
  nohup python3 scripts/vigilar.py arrancar --segundos 30 --pausar-si-humano > .tmp/vigilar.log 2>&1 &
"""


def cmd_arrancar_mac(args):
    c.validar_segundos(args.segundos)  # rango generico en _core (3x identico)
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


def construir_parser_mac():
    parser = c.Parser(
        prog="vigilar.py (macOS)",
        description="Watchdog de entrada humana con listener pynput (tap de "
                    "Sesion Quartz): ESC (u otra tecla) HUMANA crea la "
                    "bandera ABORT en el .tmp de ESTA skill — el freno "
                    "canonico del dominio mac (no hay FAILSAFE pyautogui "
                    "aqui). Exige TCC Accesibilidad (IS_TRUSTED).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_DOC_MAC.split("Subcomandos:")[1]
        if _DOC_MAC and "Subcomandos:" in _DOC_MAC else None,
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
    p.set_defaults(func=cmd_arrancar_mac)

    return parser


def main():
    global c
    mod = _core.modulo_sistema()          # lee sys.platform EN TIEMPO DE EJECUCION
    if mod is None:
        _core.so_no_soportado("vigilar.py")  # JSON rc 2 contractual (nunca retorna)
    c = mod
    plat = sys.platform
    if plat == "win32":
        global keyboard                       # solo el que ESTE CLI usaba
        from pynput import keyboard
        parser = construir_parser_win()
    elif plat == "linux":
        parser = construir_parser_linux()
    else:
        parser = construir_parser_mac()
    args = parser.parse_args()
    try:
        args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        c.fail("%s: %s" % (type(exc).__name__, exc))


if __name__ == "__main__":
    main()
