# -*- coding: utf-8 -*-
"""teclado.py — Teclado de la skill computer-use-py (PyAutoGUI + pynput).

ENTRADA MULTI-OS (FASE SEG3): `python scripts/teclado.py ...` vale en los 3
SO — en Windows ejecuta esta ruta nativa (validada en escritorio real); en
Linux/macOS ejecuta EN EL PROPIO PROCESO la ruta de su SO (las primitivas
exclusivas viven en scripts/linux/linux_especiales.py y
scripts/macos/macos_especiales.py; el dispatch es por sys.platform en main());
plataforma desconocida responde JSON + rc 2.

Camino de cada tecla (piramide de la skill):
- pyautogui.press/write/hotkey: ASCII y teclas nombradas. En Windows su
  mapeo solo cubre caracteres 32-127: los NO-ASCII (ñ, á, ¿, emojis) se
  DESCARTAN EN SILENCIO, sin excepcion (verificado en _pyautogui_win.py).
- pynput.keyboard: tipeo unicode real via KEYEVENTF_UNICODE (funciona en
  apps normales: Office, navegadores, Explorador) y teclas multimedia
  Key.media_*.
- portapapeles (pyperclip + ctrl+v): respaldo cuando lo anterior falla.

Salida: JSON por stdout; errores JSON con "error". FAILSAFE siempre activo.

Verificacion de foco (P0.2 + IMPL-K P0.1): los flags OPCIONALES
--requiere-foco "SUBCADENA" y --foco-id N en escribir/tecla/combo leen la
ventana foreground (pygetwindow.getActiveWindow, que en 0.0.9 es
GetForegroundWindow) ANTES de emitir: con subcadena, el titulo debe
contenerla (case-insensitive); con --foco-id, el hWnd (campo "id" del item
de listar/foco) debe ser EXACTAMENTE ese id — el titulo de apps multi-ventana
(Notepad 11) es compartido y cambia al teclear; SOLO el hWnd es estable. Si
algo falla ABORTA con JSON "error" que incluye ventana_actual{id,titulo}
(vento titulo_actual legacy), sin teclear nada. Con ambos flags exigen ambos.
Sin flags el flujo queda identico al validado (aditivo).

Subcomandos:
  escribir  Texto en la ventana enfocada (auto: pynput si hay no-ASCII).
  tecla     Una tecla por nombre, con repeticiones y modificadores.
  combo     Cadena tipo "ctrl+shift+esc" (pulsar en orden, soltar al reves).
  mantener  keyDown + sleep + keyUp (sin auto-repetición en Windows).

Ejemplos (desde la carpeta computer-use-py):
  py scripts/teclado.py escribir "Hola"            # Windows (python3 en otros SO)
  py scripts/teclado.py escribir "Espana: ñ ¿á? 😀" --via pynput
  py scripts/teclado.py escribir "clave" --requiere-foco "Firefox"
  py scripts/teclado.py tecla enter --repeticiones 2
  py scripts/teclado.py combo "ctrl+shift+esc"
  py scripts/teclado.py combo "win+shift+left"
  py scripts/teclado.py mantener shift --segundos 1
"""

import argparse
import os
import sys
import time

_DIR_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _DIR_SCRIPTS not in sys.path:
    sys.path.insert(0, _DIR_SCRIPTS)
import _core


# ===========================================================================
# SECCION WINDOWS — cmd_*/helpers/parser VERBATIM del CLI raiz historico.
# `c` (glue_windows) y `pyautogui` se bind-eaban en el top del archivo; en
# SEG3 se bind-ean en main() (global) ANTES de parsear = mismo comportamiento.
# ===========================================================================

# Vias validadas EN HANDLER (P1-7): un --via de otra rama o falso debe
# responder JSON {"error", "validos"}, no stderr de argparse.
_VIAS = ("auto", "pyautogui", "pynput", "portapapeles")


# _tiene_no_ascii: movido a _core (identico en las 3 ramas); se usa via
# c.tiene_no_ascii.


def _verificar_foco_requerido(subcadena, foco_id=None):
    """Comprueba el foco ANTES de emitir (flags opcionales del P0.1).

    Aborta con JSON "error" (incluye ventana_actual{id,titulo} y el
    titulo_actual legacy) si la ventana foreground no existe, su titulo no
    contiene `subcadena` (case-insensitive) o su hWnd no coincide con
    `foco_id`. Con ambos flags exige ambos. Devuelve el titulo cuando pasa
    la comprobacion. pygetwindow se importa aqui (solo donde se usa): sin
    los flags ningun camino de este script lo toca (comportamiento
    historico intacto).
    """
    import pygetwindow as gw

    ventana = gw.getActiveWindow()  # 0.0.9 = GetForegroundWindow (VERIFICADO)
    titulo = ventana.title if ventana is not None else None
    hwnd = getattr(ventana, "_hWnd", None) if ventana is not None else None
    actual = {"id": hwnd, "titulo": titulo}
    if foco_id is not None and hwnd != int(foco_id):
        c.fail("Foco incorrecto: NO se emitio nada. La ventana foreground "
               "tiene id %r y --foco-id pedia %r. Pon el foco correcto "
               "(ventanas.py activar --id %s / clic) o retira el flag "
               "asumiendo el riesgo." % (hwnd, int(foco_id), foco_id),
               ventana_actual=actual, titulo_actual=titulo,
               requiere=subcadena, requiere_id=int(foco_id),
               pista="ventanas.py foco/listar muestran el id (hWnd) de cada "
                     "ventana; el titulo es compartido y cambia en apps "
                     "multi-ventana (Notepad 11)")
    if subcadena and (titulo is None or
                      subcadena.lower() not in titulo.lower()):
        c.fail("Foco incorrecto: NO se emitio nada. La ventana activa es %r y "
               "--requiere-foco pedia contener %r. Pon el foco correcto "
               "(ventanas.py activar / clic) o retira el flag asumiendo el "
               "riesgo." % (titulo, subcadena),
               ventana_actual=actual, titulo_actual=titulo,
               requiere=subcadena,
               pista="ventanas.py foco muestra la ventana foreground actual")
    return titulo


def _escribir_pyautogui(texto, intervalo):
    """Caracteres ASCII por typewrite; \\n y \\t se emiten como teclas.

    pyautogui.write() SOLO acepta caracteres de una tecla (docs teclado):
    aqui se trocea el texto en tramos imprimibles y el resto se presiona
    por nombre. Cualquier no-ASCII aborta con error (no se tolera el
    descarte silencioso de Windows).
    """
    tramo = ""
    for ch in texto:
        if ch == "\n":
            if tramo:
                pyautogui.write(tramo, interval=intervalo)
                tramo = ""
            pyautogui.press("enter")
        elif ch == "\t":
            if tramo:
                pyautogui.write(tramo, interval=intervalo)
                tramo = ""
            pyautogui.press("tab")
        elif ord(ch) > 127:
            c.fail("pyautogui descarta en silencio los caracteres no-ASCII en "
                   "Windows (mapea solo 32-127). Repite con --via pynput "
                   "(unicode real) o --via portapapeles.",
                   posicion=len(tramo), caracter=ch)
        else:
            tramo += ch
    if tramo:
        pyautogui.write(tramo, interval=intervalo)


def _escribir_pynput(texto, intervalo):
    """Tipeo caracter a caracter con pynput (via UNICODE para no-ASCII).

    pynput.keyboard Controller.type() no acepta retardo (1.8.2), y mantiene
    el estado de modificadores interno: por eso se emite tap() por caracter
    con sueno explicito, traduciendo \\n y \\t a Key (type() solo traduce
    \\n \\r \\t; cualquier otro control lanzaria InvalidCharacterException).
    """
    from pynput import keyboard

    kb = keyboard.Controller()
    for i, ch in enumerate(texto):
        try:
            if ch == "\n":
                kb.tap(keyboard.Key.enter)
            elif ch == "\t":
                kb.tap(keyboard.Key.tab)
            else:
                kb.tap(ch)
        except Exception as exc:
            c.fail("pynput no pudo emitir el caracter %r (indice %d): %s"
                   % (ch, i, exc))
        if intervalo > 0:
            time.sleep(intervalo)


def _escribir_portapapeles(texto):
    """Respaldo comunitario para no-ASCII (verificado en el digest): copiar a
    portapapeles y pegar con ctrl+v."""
    import pyperclip

    pyperclip.copy(texto)
    time.sleep(0.05)  # asentar el portapapeles antes de pegar
    pyautogui.hotkey("ctrl", "v")


def cmd_escribir(args):
    c.checar_abort("escribir")
    c.checar_pausa()
    if args.via not in _VIAS:
        c.fail("--via %r invalido para la rama Windows." % args.via,
               validos=list(_VIAS))
    foco = (_verificar_foco_requerido(args.requiere_foco, args.foco_id)
            if (args.requiere_foco or args.foco_id is not None) else None)
    texto = args.texto
    via = args.via
    if via == "auto":
        via = "pynput" if c.tiene_no_ascii(texto) else "pyautogui"
    if via == "pyautogui" and c.tiene_no_ascii(texto):
        # auto ya desvio; solo se llega aqui con --via pyautogui forzado.
        c.fail("--via pyautogui con texto no-ASCII: Windows lo ignoraria en "
               "silencio. Usa --via pynput o --via portapapeles.")
    if via == "portapapeles":
        _escribir_portapapeles(texto)
    elif via == "pynput":
        _escribir_pynput(texto, args.intervalo)
    else:
        _escribir_pyautogui(texto, args.intervalo)
    item = {
        "ok": True,
        "via": via,
        "caracteres": len(texto),
        "contiene_no_ascii": c.tiene_no_ascii(texto),
        "aviso": "el teclado va a la ventana enfocada (un toast de Windows 11 "
                 "puede robarte el foco): verifica con pantalla.py capturar",
    }
    if foco:
        item["foco_verificado"] = foco
    c.json_out(item)


def cmd_tecla(args):
    c.checar_abort("tecla")
    c.checar_pausa()
    foco = (_verificar_foco_requerido(args.requiere_foco, args.foco_id)
            if (args.requiere_foco or args.foco_id is not None) else None)
    nombre = args.tecla.lower()
    repeticiones = max(1, args.repeticiones)
    mods = [m.lower() for m in (args.mods or [])]
    for m in mods:
        if not pyautogui.isValidKey(m):
            c.fail("Modificador no reconocido por pyautogui: %r. Nombres validos: "
                   "ctrl, shift, alt, win (lista completa en pyautogui.KEYBOARD_KEYS)."
                   % m)
    via = "pyautogui"
    try:
        if mods:
            for _ in range(repeticiones):
                pyautogui.hotkey(*mods, nombre, interval=0.05)
        else:
            if not pyautogui.isValidKey(nombre):
                raise KeyError(nombre)
            pyautogui.press(nombre, presses=repeticiones, interval=0.05)
    except KeyError:
        # Nombre valido solo en pynput (variantes multimedia u otras).
        tecla = c.tecla_pynput(nombre)
        if tecla is None:
            c.fail("Ninguna libreria reconoce la tecla %r. Prueba nombres de "
                   "pyautogui.KEYBOARD_KEYS o de pynput Key (esc, ctrl_l, "
                   "media_volume_mute, ...)." % nombre)
        from pynput import keyboard

        kb = keyboard.Controller()
        objetos_mods = [c.tecla_pynput(m) for m in mods]
        if mods and any(m is None for m in objetos_mods):
            c.fail("pynput no reconoce alguno de los modificadores %s." % mods)
        for _ in range(repeticiones):
            if objetos_mods:
                # pressed() suelta en orden inverso (try/finally interno).
                with kb.pressed(*objetos_mods):
                    kb.tap(tecla)
            else:
                kb.tap(tecla)
            if repeticiones > 1:
                time.sleep(0.05)
        via = "pynput"
    item = {
        "ok": True,
        "tecla": nombre,
        "repeticiones": repeticiones,
        "mods": mods,
        "via": via,
        "aviso": "verificar con capturar: en apps elevadas la pulsacion no llega",
    }
    if foco:
        item["foco_verificado"] = foco
    c.json_out(item)


def cmd_combo(args):
    c.checar_abort("combo")
    c.checar_pausa()
    foco = (_verificar_foco_requerido(args.requiere_foco, args.foco_id)
            if (args.requiere_foco or args.foco_id is not None) else None)
    # _partes_combo: algoritmo movido a _core; el ejemplo del mensaje es de la rama.
    partes = c.partes_combo(args.cadena, "ctrl+shift+esc")
    # Camino preferido: pyautogui.hotkey (pulsar en orden, soltar en reversa).
    if all(pyautogui.isValidKey(p) for p in partes):
        try:
            pyautogui.hotkey(*partes)
            item = {"ok": True, "combo": partes, "via": "pyautogui"}
            if foco:
                item["foco_verificado"] = foco
            c.json_out(item)
            return
        except Exception as exc:
            error_pyautogui = "%s: %s" % (type(exc).__name__, exc)
    else:
        error_pyautogui = "alguna tecla no esta en KEYBOARD_KEYS de pyautogui"
    # Reserva: pynput con pressed() (libera en orden inverso, try/finally).
    from pynput import keyboard

    kb = keyboard.Controller()
    objetos = []
    for p in partes:
        tecla = c.tecla_pynput(p)
        if tecla is None and len(p) == 1:
            tecla = p  # caracter literal
        if tecla is None:
            c.fail("No se pudo emitir el combo %r: pyautogui -> %s; y pynput "
                   "no reconoce la tecla %r."
                   % (args.cadena, error_pyautogui, p))
        objetos.append(tecla)
    try:
        with kb.pressed(*objetos):
            pass
    except Exception as exc:
        c.fail("Combo %r fallo tambien por pynput (pyautogui -> %s): %s"
               % (args.cadena, error_pyautogui, exc))
    item = {"ok": True, "combo": partes, "via": "pynput",
            "motivo_respaldo": error_pyautogui}
    if foco:
        item["foco_verificado"] = foco
    c.json_out(item)


def cmd_mantener(args):
    c.checar_abort("mantener")
    c.checar_pausa()
    segundos = c.cap_segundos_mantener(args.segundos)
    nombre = args.tecla.lower()
    via = "pyautogui"
    try:
        if not pyautogui.isValidKey(nombre):
            raise KeyError(nombre)
        # No existe holdKeyOn en pyautogui (verificado): keyDown/sleep/keyUp.
        # keyUp SIEMPRE, aunque se interrumpa sueno o falle algo.
        pyautogui.keyDown(nombre)
        try:
            time.sleep(segundos)
        finally:
            pyautogui.keyUp(nombre)
    except KeyError:
        tecla = c.tecla_pynput(nombre)
        if tecla is None:
            c.fail("Ninguna libreria reconoce la tecla %r para mantenerla." % nombre)
        from pynput import keyboard

        kb = keyboard.Controller()
        kb.press(tecla)
        try:
            time.sleep(segundos)
        finally:
            kb.release(tecla)
        via = "pynput"
    c.json_out({
        "ok": True,
        "tecla": nombre,
        "segundos": segundos,
        "via": via,
        "aviso": "Windows NO considera 'pulsada de verdad' una tecla inyectada: "
                 "mantener no genera auto-repeticion (flechas/scroll continuo "
                 "requiere emitir pulsaciones repetidas)",
    })


def construir_parser():
    parser = c.Parser(
        prog="teclado.py",
        description="Teclado para automatizacion de escritorio: tipeo ASCII/"
                    "unicode, teclas sueltas, combos y mantener pulsada. "
                    "La ventana enfocada recibe todo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1] if __doc__ and "Subcomandos:" in __doc__ else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    p = sub.add_parser("escribir", help="escribir texto en la ventana enfocada")
    p.add_argument("texto", help="texto literal (usa comillas)")
    p.add_argument("--intervalo", type=float, default=0.05,
                   help="segundos entre caracteres (por defecto 0.05)")
    p.add_argument("--via", default="auto", metavar="VIA",
                   help="auto|pyautogui|pynput|portapapeles (validado en "
                        "handler: invalido => JSON error). auto: pynput si el "
                        "texto tiene no-ASCII, si no pyautogui; portapapeles "
                        "= pyperclip + ctrl+v")
    p.add_argument("--requiere-foco", dest="requiere_foco", metavar="SUBCADENA",
                   help="abortar SIN emitir si el titulo de la ventana "
                        "foreground no contiene esta subcadena (case-insensitive)")
    p.add_argument("--foco-id", dest="foco_id", type=int, metavar="ID",
                   help="abortar SIN emitir si el id (hWnd) de la ventana "
                        "foreground NO es este (unico estable en apps "
                        "multi-ventana; id sale de ventanas.py abrir/foco/"
                        "listar)")
    p.set_defaults(func=cmd_escribir)

    p = sub.add_parser("tecla", help="pulsar una tecla por nombre (enter, esc, f5, win...)")
    p.add_argument("tecla", help="nombre de tecla (pyautogui.KEYBOARD_KEYS; reserva pynput)")
    p.add_argument("--repeticiones", type=int, default=1, help="veces (por defecto 1)")
    p.add_argument("--mods", nargs="+", metavar="MOD",
                   help="modificadores: ctrl shift alt win (usa combo para esto)")
    p.add_argument("--requiere-foco", dest="requiere_foco", metavar="SUBCADENA",
                   help="abortar SIN emitir si el titulo de la ventana "
                        "foreground no contiene esta subcadena (case-insensitive)")
    p.add_argument("--foco-id", dest="foco_id", type=int, metavar="ID",
                   help="abortar SIN emitir si el id (hWnd) foreground NO "
                        "es este (unico estable en apps multi-ventana)")
    p.set_defaults(func=cmd_tecla)

    p = sub.add_parser("combo", help='combinacion tipo "ctrl+shift+esc" (orden down, reversa up)')
    p.add_argument("cadena", help='cadena separada por +, ej. "ctrl+s"')
    p.add_argument("--requiere-foco", dest="requiere_foco", metavar="SUBCADENA",
                   help="abortar SIN emitir si el titulo de la ventana "
                        "foreground no contiene esta subcadena (case-insensitive)")
    p.add_argument("--foco-id", dest="foco_id", type=int, metavar="ID",
                   help="abortar SIN emitir si el id (hWnd) foreground NO "
                        "es este (unico estable en apps multi-ventana)")
    p.set_defaults(func=cmd_combo)

    p = sub.add_parser("mantener", help="mantener una tecla pulsada N segundos")
    p.add_argument("tecla", help="nombre de tecla")
    # TIEMPOS-K: mantener 1.0->0.8 s (-20%, piso 250 ok): duracion DEFAULT del
    # hold (press->sleep->release); el rango 0.05-60 s es limite C intocable.
    p.add_argument("--segundos", type=float, default=0.8,
                   help="duracion del mantenimiento (0.05-60, por defecto 0.8)")
    p.set_defaults(func=cmd_mantener)

    return parser


# ===========================================================================
# SECCION LINUX — cmd_*/helpers de scripts/linux/teclado.py (FASE SEG3) con
# sufijo _linux. Las primitivas que bajaron a scripts/linux/linux_especiales.py
# (_pyautogui, _verificar_foco_requerido, _escribir_portapapeles,
# _escribir_wtype, _tecla_wtype, _KEYSYMS, _ydotool_seq, _code_de,
# _emitir_combo_ydotool, _titulo_foco, _buscar_foco) se llaman via c.<nombre>()
# — el alias c se bind-ea en main() y en el modulo de la libreria su propio
# self-alias mantiene los cuerpos bajados intactos. _VIAS/_escribir_pyautogui/
# _escribir_pynput NO bajaron (van por librerias Python, no por herramientas
# del SO): se copian aqui con sufijo.
# ===========================================================================

_DOC_LINUX = """teclado.py — Teclado del dominio LINUX (skill computer-use-py).

MISMO contrato JSON del dominio Windows; superficie 100 % Python. Piramide
(references/linux-python.md §4 y §10):
  X11     pyautogui (ASCII; bajo Xlib/XTEST) y pynput (unicode segun el layout
          XKB [runtime]); portapapeles = pyperclip o xclip + ctrl+v [runtime].
  Wayland pyautogui/pynput NO llegan al compositor nativo (XTEST es de X11):
          wtype para texto/teclas y ydotool para combos/mantener. FLAGS DE
          wtype NO verificados aqui (el fetch del repo fallo) => [runtime];
          la sintaxis de ydotool key CODE:1/CODE:0 SI esta verificada en su
          man (28=Enter; codigos: /usr/include/linux/input-event-codes.h).

Verificacion de foco (paridad P0.2 con Windows): los flags OPCIONALES
--requiere-foco "SUBCADENA" y --foco-id ID leen la ventana activa ANTES de
emitir — X11: xdotool getactivewindow getwindowname (man verbatim; id
decimal de _NET_ACTIVE_WINDOW); Wayland: nodo focused de swaymsg -t get_tree
o hyprctl activewindow -j [runtime]. Si el titulo no contiene la subcadena
o el id no coincide (ambos comparados como enteros base 0: vale "123" o
"0x7b") ABORTA con JSON "error", ventana_actual{id,titulo} y el titulo
real, sin teclear nada.

Salida: JSON por stdout; errores JSON con "error".

Subcomandos:
  escribir  Texto en la ventana enfocada (auto elige la ruta por sesion).
  tecla     Una tecla por nombre, con repeticiones.
  combo     Cadena tipo "ctrl+shift+esc" (pulsar en orden, soltar al reves).
  mantener  keyDown + sleep + keyUp (Wayland: ydotool key CODE:1 ... CODE:0).

Ejemplos (desde la carpeta computer-use-py, en la maquina Linux):
  python3 scripts/teclado.py escribir "Hola"
  python3 scripts/teclado.py escribir "Espana: n con tilde" --via wtype
  python3 scripts/teclado.py escribir "clave" --requiere-foco "Firefox"
  python3 scripts/teclado.py tecla enter --repeticiones 2
  python3 scripts/teclado.py combo "ctrl+shift+esc"
  python3 scripts/teclado.py mantener shift --segundos 1
"""

# Vias validadas EN HANDLER (P1-7): un --via falso o de otra rama responde JSON
# {"error","validos"}, nunca stderr de argparse.
_VIAS_LINUX = ("auto", "pyautogui", "pynput", "portapapeles", "wtype", "ydotool")


# _tiene_no_ascii: generico en _core (identico en las 3 ramas); se llama via
# c.tiene_no_ascii.


# --- rutas X11 ------------------------------------------------------------

def _escribir_pyautogui_linux(texto, intervalo):
    """ASCII por write(); \\n y \\t por press(). No-ASCII: en Linux pyautogui
    usa keysyms Xlib y PUEDE cubrir mas que el rango 32-127 de Windows, pero
    no esta verificado ([runtime]): ante cualquier fallo se deriva al JSON con
    sugerencia de --via pynput/portapapeles/wtype."""
    pa = c._pyautogui()
    tramo = ""
    for ch in texto:
        if ch == "\n":
            if tramo:
                pa.write(tramo, interval=intervalo)
                tramo = ""
            pa.press("enter")
        elif ch == "\t":
            if tramo:
                pa.write(tramo, interval=intervalo)
                tramo = ""
            pa.press("tab")
        elif ord(ch) > 127:
            c.fail("--via pyautogui con texto no-ASCII (%r): el mapeo Xlib de "
                   "pyautogui sobre caracteres fuera de ASCII no esta "
                   "verificado [runtime] y puede emitir el caracter equivocado "
                   "(man xdotool documenta ese bug para teclados no-US). Usa "
                   "--via pynput, --via portapapeles o --via wtype "
                   "(Wayland/XWayland)." % ch)
        else:
            tramo += ch
    if tramo:
        pa.write(tramo, interval=intervalo)


def _escribir_pynput_linux(texto, intervalo):
    """Tapeo por pynput (X11): teclado -> layout XKB; no-ASCII depende de que
    el layout tenga la tecla [runtime] (si no, InvalidCharacterException)."""
    from pynput import keyboard

    kb = keyboard.Controller()
    for i, ch in enumerate(texto):
        try:
            if ch == "\n":
                kb.tap(keyboard.Key.enter)
            elif ch == "\t":
                kb.tap(keyboard.Key.tab)
            else:
                kb.tap(ch)
        except Exception as exc:
            c.fail("pynput no pudo emitir el caracter %r (indice %d): %s. "
                   "El layout XKB activo quizas no tiene esa tecla: prueba "
                   "--via portapapeles (xclip + ctrl+v)." % (ch, i, exc))
        if intervalo > 0:
            time.sleep(intervalo)


# _escribir_portapapeles (xclip/pyperclip + ctrl+v): BAJA a linux_especiales
# (regla portapapeles de la spec) => se llama via c._escribir_portapapeles.

# --- rutas Wayland ---------------------------------------------------------
# _escribir_wtype, _tecla_wtype, _KEYSYMS, _ydotool_seq, _code_de y
# _emitir_combo_ydotool BAJARON a linux_especiales: se llaman via c.<nombre>.


def cmd_escribir_linux(args):
    c.checar_abort("escribir")
    c.checar_pausa()
    if args.via not in _VIAS_LINUX:
        c.fail("--via %r invalido para la rama Linux." % args.via,
               validos=list(_VIAS_LINUX), sesion=c.deteccion_sesion())
    foco = (c._verificar_foco_requerido(args.requiere_foco, args.foco_id)
            if (args.requiere_foco or args.foco_id is not None) else None)
    texto = args.texto
    sesion = c.deteccion_sesion()
    via = args.via
    if via == "auto":
        if sesion == "wayland":
            via = "wtype"
        elif c.tiene_no_ascii(texto):
            via = "pynput"
        else:
            via = "pyautogui"
    if sesion == "wayland" and via in ("pyautogui", "pynput"):
        c.fail("--via %s en Wayland NATIVO: la inyeccion XTEST/Xlib no llega "
               "al compositor (solo XWayland; refs linux-python.md §4). "
               "Usa --via wtype o --via ydotool." % via, sesion=sesion)
    if sesion == "x11" and via == "wtype":
        c.fail("wtype es una herramienta WAYLAND: en X11 usa --via "
               "pyautogui/pynput/portapapeles.", sesion=sesion)
    via_clip = None
    if via == "portapapeles":
        if sesion == "wayland":
            # wl-clipboard + pegar con ydotool ctrl+v (codigo 29 + v=47
            # [runtime]) — refs linux-python.md §12
            import shutil

            r = c.run("wl-copy", [texto], timeout=10.0)
            if r["rc"] != 0 or shutil.which("wl-copy") is None:
                c.fail("wl-copy fallo/ausente en Wayland: instala wl-clipboard "
                       "o usa --via wtype.", sesion=sesion)
            time.sleep(0.05)
            c._ydotool_seq(["29:1", "47:1", "47:0", "29:0"])  # ctrl+v
            via_clip = "wl-copy"
        else:
            via_clip = c._escribir_portapapeles(texto)
    elif via == "pynput":
        _escribir_pynput_linux(texto, args.intervalo)
    elif via == "pyautogui":
        _escribir_pyautogui_linux(texto, args.intervalo)
    elif via == "wtype":
        c._escribir_wtype(texto)
    elif via == "ydotool":
        r = c.run("ydotool", ["type", texto] if not texto.startswith("-")
                  else ["type", "--", texto], timeout=60.0)
        if r["rc"] != 0:
            c.fail("ydotool type fallo (rc=%d): %s" % (r["rc"], r["stderr"].strip()))
    item = {
        "ok": True,
        "via": via + (" (%s)" % via_clip if via_clip else ""),
        "sesion": sesion,
        "caracteres": len(texto),
        "contiene_no_ascii": c.tiene_no_ascii(texto),
        "aviso": "el teclado va a la ventana enfocada (un toast/notificacion "
                 "puede robar el foco): verifica con pantalla.py capturar",
    }
    if foco:
        item["foco_verificado"] = foco
    c.json_out(item)


def cmd_tecla_linux(args):
    c.checar_abort("tecla")
    c.checar_pausa()
    foco = (c._verificar_foco_requerido(args.requiere_foco, args.foco_id)
            if (args.requiere_foco or args.foco_id is not None) else None)
    nombre = args.tecla.lower()
    repeticiones = max(1, args.repeticiones)
    mods = [m.lower() for m in (args.mods or [])]
    sesion = c.deteccion_sesion()
    if sesion == "wayland":
        if mods:
            combo = "+".join(mods + [nombre])
            for _ in range(repeticiones):
                c._emitir_combo_ydotool(combo)
                if repeticiones > 1:
                    time.sleep(0.05)
            item = {"ok": True, "tecla": nombre, "repeticiones": repeticiones,
                    "mods": mods, "via": "ydotool key (combo)", "sesion": sesion}
        else:
            for _ in range(repeticiones):
                c._tecla_wtype(nombre)
                time.sleep(0.05)
            item = {"ok": True, "tecla": nombre, "repeticiones": repeticiones,
                    "via": "wtype -k [runtime]", "sesion": sesion}
        if foco:
            item["foco_verificado"] = foco
        c.json_out(item)
        return
    pa = c._pyautogui()
    for m in mods:
        if not pa.isValidKey(m):
            c.fail("Modificador no reconocido por pyautogui: %r. Nombres "
                   "validos: ctrl, shift, alt, super/meta (lista completa en "
                   "pyautogui.KEYBOARD_KEYS)." % m)
    via = "pyautogui"
    try:
        if mods:
            for _ in range(repeticiones):
                pa.hotkey(*mods, nombre, interval=0.05)
        else:
            if not pa.isValidKey(nombre):
                raise KeyError(nombre)
            pa.press(nombre, presses=repeticiones, interval=0.05)
    except (KeyError, ValueError):
        tecla = c.tecla_pynput(nombre)
        if tecla is None:
            c.fail("Ninguna libreria reconoce la tecla %r. Prueba nombres de "
                   "pyautogui.KEYBOARD_KEYS o de pynput Key (esc, ctrl_l, "
                   "media_volume_mute, ...)." % nombre)
        from pynput import keyboard

        kb = keyboard.Controller()
        objetos_mods = [c.tecla_pynput(m) for m in mods]
        if mods and any(o is None for o in objetos_mods):
            c.fail("pynput no reconoce alguno de los modificadores %s." % mods)
        for _ in range(repeticiones):
            if objetos_mods:
                with kb.pressed(*objetos_mods):
                    kb.tap(tecla)
            else:
                kb.tap(tecla)
            if repeticiones > 1:
                time.sleep(0.05)
        via = "pynput"
    item = {
        "ok": True,
        "tecla": nombre,
        "repeticiones": repeticiones,
        "mods": mods,
        "via": via,
        "sesion": sesion,
        "aviso": "verificar con capturar: el WM puede no entregar el foco/"
                 "evento a la ventana pedida (refs linux-python.md §13)",
    }
    if foco:
        item["foco_verificado"] = foco
    c.json_out(item)


# _partes_combo: algoritmo generico en _core; el ejemplo del mensaje es de la
# rama ("ctrl+shift+esc"). Se llama via c.partes_combo(cadena, ejemplo).


# _emitir_combo_ydotool: BAJA a linux_especiales => se llama c._emitir_combo_ydotool.


def cmd_combo_linux(args):
    c.checar_abort("combo")
    c.checar_pausa()
    foco = (c._verificar_foco_requerido(args.requiere_foco, args.foco_id)
            if (args.requiere_foco or args.foco_id is not None) else None)
    partes = c.partes_combo(args.cadena, "ctrl+shift+esc")
    sesion = c.deteccion_sesion()
    if sesion == "wayland":
        c._emitir_combo_ydotool(args.cadena)
        item = {"ok": True, "combo": partes, "via": "ydotool key",
                "sesion": sesion,
                "aviso": "codigos de la tabla [runtime] (verificado: sintaxis "
                         "CODE:1/CODE:0 y 28/38/24/42 del man)"}
        if foco:
            item["foco_verificado"] = foco
        c.json_out(item)
        return
    pa = c._pyautogui()
    # Camino preferido: pyautogui.hotkey (pulsar en orden, soltar en reversa).
    error_pyautogui = None
    if all(pa.isValidKey(p) for p in partes):
        try:
            pa.hotkey(*partes)
            item = {"ok": True, "combo": partes, "via": "pyautogui",
                    "sesion": sesion}
            if foco:
                item["foco_verificado"] = foco
            c.json_out(item)
            return
        except Exception as exc:
            error_pyautogui = "%s: %s" % (type(exc).__name__, exc)
    else:
        error_pyautogui = "alguna tecla no esta en KEYBOARD_KEYS de pyautogui"
    # Reserva: pynput con pressed() (libera en orden inverso, try/finally).
    from pynput import keyboard

    kb = keyboard.Controller()
    objetos = []
    for p in partes:
        tecla = c.tecla_pynput(p)
        if tecla is None and len(p) == 1:
            tecla = p  # caracter literal
        if tecla is None:
            c.fail("No se pudo emitir el combo %r: pyautogui -> %s; y pynput "
                   "no reconoce la tecla %r."
                   % (args.cadena, error_pyautogui, p))
        objetos.append(tecla)
    try:
        with kb.pressed(*objetos):
            pass
    except Exception as exc:
        c.fail("Combo %r fallo tambien por pynput (pyautogui -> %s): %s"
               % (args.cadena, error_pyautogui, exc))
    item = {"ok": True, "combo": partes, "via": "pynput",
            "motivo_respaldo": error_pyautogui, "sesion": sesion}
    if foco:
        item["foco_verificado"] = foco
    c.json_out(item)


def cmd_mantener_linux(args):
    c.checar_abort("mantener")
    c.checar_pausa()
    segundos = c.cap_segundos_mantener(args.segundos)
    nombre = args.tecla.lower()
    sesion = c.deteccion_sesion()
    if sesion == "wayland":
        code = c._code_de(nombre)
        if code is None:
            c.fail("mantener (ydotool) no tiene codigo para %r en la tabla "
                   "KEY_CODES [runtime]." % nombre)
        c._ydotool_seq(["%d:1" % code])
        try:
            time.sleep(segundos)
        finally:
            # soltar SIEMPRE: en un solo proceso para minimizar ventanas de
            # boton "pegado" si el script muere entre medias
            c.run("ydotool", ["key", "%d:0" % code], timeout=15.0)
        c.json_out({
            "ok": True, "tecla": nombre, "segundos": segundos,
            "via": "ydotool key CODE:1/CODE:0", "sesion": sesion,
            "aviso": "la auto-repeticion la decide el compositor/app; si "
                     "nada, emite tecla repetida en loop [runtime]",
        })
        return
    pa = c._pyautogui()
    via = "pyautogui"
    try:
        if not pa.isValidKey(nombre):
            raise KeyError(nombre)
        pa.keyDown(nombre)
        try:
            time.sleep(segundos)
        finally:
            pa.keyUp(nombre)  # keyUp SIEMPRE, aunque se interrumpa
    except KeyError:
        tecla = c.tecla_pynput(nombre)
        if tecla is None:
            c.fail("Ninguna libreria reconoce la tecla %r para mantenerla."
                   % nombre)
        from pynput import keyboard

        kb = keyboard.Controller()
        kb.press(tecla)
        try:
            time.sleep(segundos)
        finally:
            kb.release(tecla)
        via = "pynput"
    c.json_out({
        "ok": True,
        "tecla": nombre,
        "segundos": segundos,
        "via": via,
        "sesion": sesion,
        "aviso": "la inyeccion XTEST puede no activar la auto-repeticion "
                 "segun la app: para flechas/scroll continuo emite pulsaciones "
                 "repetidas [runtime] (refs linux-python.md §13: estado de "
                 "modificadores en pynput/pyautogui)",
    })


def construir_parser_linux():
    parser = c.Parser(
        prog="teclado.py (linux)",
        description="Teclado Linux: X11 por pyautogui/pynput (librerias "
                    "Python) y Wayland por wtype/ydotool (subprocess interno; "
                    "superficie JSON identica al dominio Windows).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_DOC_LINUX.split("Subcomandos:")[1] if _DOC_LINUX and "Subcomandos:" in _DOC_LINUX else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    p = sub.add_parser("escribir", help="escribir texto en la ventana enfocada")
    p.add_argument("texto", help="texto literal (usa comillas)")
    p.add_argument("--intervalo", type=float, default=0.05,
                   help="segundos entre caracteres (default 0.05; rutas "
                        "pyautogui/pynput)")
    p.add_argument("--via", default="auto", metavar="VIA",
                   help="auto|pyautogui|pynput|portapapeles|wtype|ydotool "
                        "(validado en handler: invalido => JSON error). auto: "
                        "Wayland->wtype; X11->pynput si hay no-ASCII, si no "
                        "pyautogui; portapapeles: xclip/wl-copy + pegar")
    p.add_argument("--requiere-foco", dest="requiere_foco", metavar="SUBCADENA",
                   help="abortar SIN emitir si el titulo de la ventana "
                        "foreground no contiene esta subcadena (case-insensitive)")
    p.add_argument("--foco-id", dest="foco_id", metavar="ID",
                   help="abortar SIN emitir si el id de la ventana activa "
                        "(X11: xdotool/_NET_ACTIVE_WINDOW; Wayland: nodo "
                        "focused) NO es este (acepta decimal o 0x...)")
    p.set_defaults(func=cmd_escribir_linux)

    p = sub.add_parser("tecla", help="pulsar una tecla por nombre "
                       "(enter, esc, f5, super...)")
    p.add_argument("tecla", help="nombre de tecla (pyautogui KEYBOARD_KEYS / "
                   "pynput Key / keysym wtype / tabla ydotool)")
    p.add_argument("--repeticiones", type=int, default=1, help="veces (default 1)")
    p.add_argument("--mods", nargs="+", metavar="MOD",
                   help="modificadores: ctrl shift alt super (usa combo para esto)")
    p.add_argument("--requiere-foco", dest="requiere_foco", metavar="SUBCADENA",
                   help="abortar SIN emitir si el titulo de la ventana "
                        "foreground no contiene esta subcadena")
    p.add_argument("--foco-id", dest="foco_id", metavar="ID",
                   help="abortar SIN emitir si el id de la ventana activa "
                        "no es este (decimal o 0x...)")
    p.set_defaults(func=cmd_tecla_linux)

    p = sub.add_parser("combo", help='combinacion tipo "ctrl+shift+esc" '
                       "(orden down, reversa up)")
    p.add_argument("cadena", help='cadena separada por +, ej. "ctrl+s"')
    p.add_argument("--requiere-foco", dest="requiere_foco", metavar="SUBCADENA",
                   help="abortar SIN emitir si el titulo de la ventana "
                        "foreground no contiene esta subcadena")
    p.add_argument("--foco-id", dest="foco_id", metavar="ID",
                   help="abortar SIN emitir si el id de la ventana activa "
                        "no es este (decimal o 0x...)")
    p.set_defaults(func=cmd_combo_linux)

    p = sub.add_parser("mantener", help="mantener una tecla pulsada N segundos")
    p.add_argument("tecla", help="nombre de tecla")
    # TIEMPOS-K: mantener 1.0->0.8 s (-20%, piso 250 ok): duracion DEFAULT del
    # hold (press->sleep->release); el rango 0.05-60 s es limite C intocable.
    p.add_argument("--segundos", type=float, default=0.8,
                   help="duracion (0.05-60, default 0.8)")
    p.set_defaults(func=cmd_mantener_linux)

    return parser


# ===========================================================================
# SECCION macOS — cmd_*/helpers de scripts/macos/teclado.py (FASE SEG3) con
# sufijo _mac. BAJARON a scripts/macos/macos_especiales.py: _foco_actual
# (osascript) y _escribir_osascript; se llaman via c.<nombre>() (el self-alias
# del modulo deja intacto su lectura de foco). QUEDAN aqui: _VIAS_MAC,
# _verificar_foco_requerido_mac (orquesta c._foco_actual), _escribir_pynput_mac
# y _escribir_portapapeles_mac (pbcopy: NO es de las utilidades fronterizas —
# decision de @2-M, se queda en raiz) con sufijo; y SIN sufijo porque no
# colisionan con ninguna otra seccion (lista explicita de la tarea SEG3):
# _MAPA_USING, _MOD_KEY, _emitir_combo_pynput_or_quartz, _pynput_disponible.
# Los pynput van lazy (c.try_pynput / import dentro de la funcion).
# ===========================================================================

_DOC_MAC = """teclado.py — Teclado en macOS (skill computer-use-py, dominio mac).

Piramide del dominio (todo corre sobre Python):
- pynput 1.8.2 (PRIMARIA): Controller emite CGEventCreateKeyboardEvent +
  CGEventPost [VERIFICADO fuente keyboard/_darwin.py:225-232]; unicode real
  por CGEventKeyboardSetUnicodeString (fuente:147-148) — ñ/acentos/emojis se
  tipean de verdad en apps normales. Key.cmd existe en darwin (cmd+s); las
  multimedia son Key.media_* = eventos SystemDefined con NX_KEYTYPE (fuente
  :61-68), NO "key code" 100-111 (esos son F8..F12 fisicos). REQUIERE permiso
  Accesibilidad (TCC) para escuchar; p/ inyectar, Apple lo exige igualmente
  en la practica [runtime] — vigilar.py reporta is_trusted.
- osascript/System Events (RESPALDO sin instalar nada): keystroke/key code
  "using {command down}" [runtime: el capitulo fetcheado de la guia Apple no
  lista keystroke; verificar contra el diccionario de System Events del Mac].
  El texto viaja SIEMPRE por argv (man osascript VERIFICADO) — nunca
  interpolado en el codigo (inyeccion AppleScript). OJO: argv es visible en
  `ps`; para TEXTO SENSIBLE usar --via portapapeles (pbcopy).
- portapapeles: pbcopy + cmd+v (teclas por pynput/quartz, no por argv).

Salida: JSON por stdout; errores JSON con "error".

Verificacion de foco (--requiere-foco "SUBCADENA"): lee app+ventana frontmost
por osascript ANTES de emitir; aborta sin teclear si no coincide. --foco-id
NO tiene ruta en macOS (no hay hWnd estable): error JSON honesto [runtime].

Subcomandos:
  escribir  Texto en la ventana enfocada (auto: pynput si disponible).
  tecla     Una tecla por nombre (tabla kVK_ del fuente pynput), repeticiones.
  combo     Cadena tipo "cmd+shift+esc" (pynput pressed(); reserva osascript).
  mantener  keyDown + sleep + keyUp (pynput; auto-repeticion [runtime]).

Ejemplos (desde la carpeta computer-use-py, en el Mac):
  python3 scripts/teclado.py escribir "Espana: ñ ¿á? 😀"
  python3 scripts/teclado.py escribir "clave" --via portapapeles
  python3 scripts/teclado.py tecla enter --repeticiones 2
  python3 scripts/teclado.py combo "cmd+s"
  python3 scripts/teclado.py combo "cmd+shift+esc" --via osascript
  python3 scripts/teclado.py mantener shift --segundos 1
"""

# Modificadores canonicos para el "using {...}" de System Events [runtime].
_MAPA_USING = {
    "cmd": "command down", "command": "command down",
    "ctrl": "control down", "control": "control down",
    "shift": "shift down",
    "alt": "option down", "option": "option down",
}
# Orden canonico para pynput.pressed(): miembros Key de darwin.
_MOD_KEY = {"cmd": "cmd", "command": "cmd", "ctrl": "ctrl", "control": "ctrl",
            "shift": "shift", "alt": "alt", "option": "alt"}

def _verificar_foco_requerido_mac(subcadena, foco_id=None):
    """Comprueba el foco ANTES de emitir (flags --requiere-foco/--foco-id).

    Aborta con JSON "error" (incluye app y titulo reales) si ni la app
    frontmost ni su ventana 1 contienen la subcadena (case-insensitive).
    IMPL-K P0.1: --foco-id exige un id estable y la rama macOS NO lo
    expone (System Events no da hWnd: ver macos_especiales._estado_item,
    "id": None) => error JSON honesto [runtime], sin emitir.
    """
    if foco_id is not None:
        c.fail("--foco-id no esta disponible en la rama macOS [runtime]: "
               "System Events no expone un id estable de ventana (el item "
               "canonical trae 'id': null; la identidad es (app, titulo)). "
               "NO se emitio nada. Usa --requiere-foco con un titulo unico "
               "(p. ej. el nombre del archivo) o actua por coordenadas tras "
               "verificar con capturar.", requiere_id=foco_id,
               hint="references/macos-python.md (identidad de ventana sin "
                    "hWnd)")
    app, titulo = c._foco_actual()
    if app is None:
        c.fail("Foco incorrecto: NO se emitio nada. No se pudo leer la app "
               "frontmost (osascript fallo o TCC Automatizacion pendiente). "
               "Concede el permiso o quita el flag asumiendo el riesgo.",
               requiere=subcadena,
               hint="Seguridad y privacidad > Automatizacion/Accesibilidad "
                    "(references/macos-python.md §3)")
    candidatos = " ".join(x for x in (titulo, app) if x).lower()
    if subcadena.lower() not in candidatos:
        c.fail("Foco incorrecto: NO se emitio nada. La app activa es %r con "
               "ventana %r y --requiere-foco pedia contener %r. Pon el foco "
               "correcto (ventanas.py activar / clic) o retira el flag "
               "asumiendo el riesgo." % (app, titulo, subcadena),
               app_actual=app, titulo_actual=titulo, requiere=subcadena,
               pista="ventanas.py foco muestra la ventana foreground actual")
    return "%s / %s" % (app, titulo or "(sin titulo)")


# _tiene_no_ascii: generico en _core (identico en las 3 ramas); se llama via
# c.tiene_no_ascii.


def _escribir_pynput_mac(texto, intervalo):
    """Tipeo caracter a caracter con pynput (unicode por SetUnicodeString,
    VERIFICADO fuente). tap() por caracter con sueno explicito: type() no
    acepta delay y solo traduce \\n \\r \\t (el resto lanza
    InvalidCharacterException) — mismo patron que el teclado Windows."""
    keyboard = c.try_pynput()
    kb = keyboard.Controller()
    for i, ch in enumerate(texto):
        try:
            if ch == "\n":
                kb.tap(keyboard.Key.enter)
            elif ch == "\t":
                kb.tap(keyboard.Key.tab)
            else:
                kb.tap(ch)
        except Exception as exc:
            c.fail("pynput no pudo emitir el caracter %r (indice %d): %s"
                   % (ch, i, exc))
        if intervalo > 0:
            time.sleep(intervalo)


def _escribir_portapapeles_mac(texto):
    """pbcopy + cmd+v: el texto NO viaja por argv (no se filtra en `ps`).
    pbcopy es preinstalado BSD de macOS [runtime: pagina no fetcheada]."""
    import subprocess
    try:
        p = subprocess.run(["pbcopy"], input=texto.encode("utf-8"),
                           capture_output=True, timeout=10)
    except FileNotFoundError:
        c.fail("pbcopy no existe en el PATH (no es macOS real).")
    if p.returncode != 0:
        c.fail("pbcopy fallo (rc=%d): %s"
               % (p.returncode, (p.stderr or b"").decode("utf-8", "replace")))
    time.sleep(0.05)  # asentar el portapapeles antes de pegar
    _emitir_combo_pynput_or_quartz(["cmd", "v"])


def _emitir_combo_pynput_or_quartz(partes):
    """cmd+v sin pynput no tiene ruta simple: si falta pynput, falla honesto."""
    keyboard = c.try_pynput()
    kb = keyboard.Controller()
    mod = getattr(keyboard.Key, _MOD_KEY[partes[0]], None)
    if mod is None:
        c.fail("Modificador %r no existe en pynput darwin." % partes[0])
    with kb.pressed(mod):
        kb.tap(partes[-1])


# Vias validadas EN HANDLER (P1-7): --via falso o de otra rama => JSON error
# con 'validos' (el set mac difiere de win/linux: esto se documenta por rama).
_VIAS_MAC = ("auto", "pynput", "osascript", "portapapeles")


def cmd_escribir_mac(args):
    c.checar_abort()
    c.checar_pausa()
    if args.via not in _VIAS_MAC:
        c.fail("--via %r invalido para la rama macOS." % args.via,
               validos=list(_VIAS_MAC))
    foco = (_verificar_foco_requerido_mac(args.requiere_foco, args.foco_id)
            if (args.requiere_foco or args.foco_id is not None) else None)
    texto = args.texto
    via = args.via
    hay_pynput = _pynput_disponible()
    if via == "auto":
        if hay_pynput:
            via = "pynput"
        else:
            via = "portapapeles" if c.tiene_no_ascii(texto) else "osascript"
    if via == "pynput":
        if not hay_pynput:
            c.fail("--via pynput sin pynput instalado: "
                   "python3 -m pip install pynput==1.8.2")
        _escribir_pynput_mac(texto, args.intervalo)
    elif via == "osascript":
        c._escribir_osascript(texto)
    else:
        _escribir_portapapeles_mac(texto)
    item = {
        "ok": True,
        "via": via,
        "caracteres": len(texto),
        "contiene_no_ascii": c.tiene_no_ascii(texto),
        "aviso": "el teclado va a la ventana enfocada; verifica con "
                 "pantalla.py capturar. via=osascript pasa el texto por argv "
                 "(visible en `ps`): usa --via portapapeles para credenciales",
    }
    if foco:
        item["foco_verificado"] = foco
    c.json_out(item)


def _pynput_disponible():
    try:
        import pynput  # noqa: F401
        return True
    except ImportError:
        return False


def cmd_tecla_mac(args):
    c.checar_abort()
    c.checar_pausa()
    foco = (_verificar_foco_requerido_mac(args.requiere_foco, args.foco_id)
            if (args.requiere_foco or args.foco_id is not None) else None)
    nombre = args.tecla.lower()
    repeticiones = max(1, args.repeticiones)
    mods = [m.lower() for m in (args.mods or [])]
    canon, es_media = c.nombre_tecla_mac(nombre)
    via = "pynput" if _pynput_disponible() else "osascript"
    if via == "pynput":
        keyboard = c.try_pynput()
        kb = keyboard.Controller()
        if es_media:
            tecla = getattr(keyboard.Key, canon, None)
            if tecla is None:
                c.fail("La multimedia %r no existe en pynput darwin." % canon)
        else:
            tecla = c.tecla_pynput_mac(canon or nombre)
            if tecla is None and len(nombre) == 1:
                tecla = nombre  # caracter literal
            if tecla is None:
                vk = c.vk_mac(nombre)
                if vk is None:
                    c.fail("Ninguna ruta reconoce la tecla %r. Validas: "
                           "nombres pynput Key (esc, enter, cmd, f5, up...) y "
                           "la tabla kVK_ de references/macos-python.md §6."
                           % nombre)
                tecla = keyboard.KeyCode.from_vk(vk)
        objetos_mods = []
        for m in mods:
            om = c.tecla_pynput_mac(m)
            if om is None:
                c.fail("pynput darwin no reconoce el modificador %r "
                       "(validos: cmd, ctrl, alt/option, shift)." % m)
            objetos_mods.append(om)
        for _ in range(repeticiones):
            if objetos_mods:
                with kb.pressed(*objetos_mods):
                    kb.tap(tecla)
            else:
                kb.tap(tecla)
            if repeticiones > 1:
                time.sleep(0.05)
    else:
        # osascript: key code con vk de la tabla (VERIFICADO fuente pynput);
        # media keys NO tienen key code estandar -> error honesto.
        if es_media:
            c.fail("Teclas multimedia: osascript key code no las cubre "
                   "(son eventos SystemDefined, references/macos-python.md "
                   "§6). Instala pynput==1.8.2 (python3 -m pip install "
                   "pynput) para emitirlas.")
        vk = c.vk_mac(nombre)
        if vk is None:
            c.fail("osascript no puede emitir %r: no esta en la tabla kVK_ "
                   "y falta pynput (pip3 install pynput==1.8.2)." % nombre)
        using = [_MAPA_USING[m] for m in mods if m in _MAPA_USING]
        if mods and len(using) != len(mods):
            c.fail("Modificador no reconocido para osascript: %r "
                   "(validos: cmd, ctrl, shift, alt/option)." % mods)
        if using:
            cuerpo = ('tell application "System Events" to key code (item 1 '
                      'of argv) using {%s}'
                      % ", ".join('"%s"' % u for u in using))
        else:
            cuerpo = ('tell application "System Events" to key code '
                      '(item 1 of argv)')
        for _ in range(repeticiones):
            c.osascript_valor(cuerpo, [vk], accion="key code")
            if repeticiones > 1:
                time.sleep(0.05)
    item = {
        "ok": True,
        "tecla": canon or nombre,
        "repeticiones": repeticiones,
        "mods": mods,
        "via": via,
        "aviso": "verificar con capturar: sin TCC Accesibilidad la emision "
                 "no llega [runtime]",
    }
    if foco:
        item["foco_verificado"] = foco
    c.json_out(item)


# _partes_combo: algoritmo generico en _core; el ejemplo del mensaje es de la
# rama mac ("cmd+shift+esc"). Se llama via c.partes_combo(cadena, ejemplo).


def cmd_combo_mac(args):
    c.checar_abort()
    c.checar_pausa()
    foco = (_verificar_foco_requerido_mac(args.requiere_foco, args.foco_id)
            if (args.requiere_foco or args.foco_id is not None) else None)
    partes = c.partes_combo(args.cadena, "cmd+shift+esc")
    final = partes[-1]
    mods = partes[:-1]
    if not mods:
        c.fail('El combo necesita al menos un modificador: "cmd+s", '
               '"cmd+shift+4". Una tecla suelta va a `tecla`.')
    via = "pynput" if _pynput_disponible() else "osascript"
    if via == "pynput":
        keyboard = c.try_pynput()
        kb = keyboard.Controller()
        objetos = []
        for m in mods:
            om = c.tecla_pynput_mac(m)
            if om is None:
                c.fail("pynput darwin no reconoce el modificador %r (validos: "
                       "cmd, ctrl, alt/option, shift). Combo %r."
                       % (m, args.cadena))
            objetos.append(om)
        tecla = c.tecla_pynput_mac(final)
        if tecla is None and len(final) == 1:
            tecla = final  # caracter literal: cmd+s, cmd+shift+e
        if tecla is None:
            vk = c.vk_mac(final)
            if vk is None:
                c.fail("pynput no reconoce la tecla final %r del combo %r."
                       % (final, args.cadena))
            tecla = keyboard.KeyCode.from_vk(vk)
        # pressed() suelta en orden INVERSO con try/finally interno
        # (VERIFICADO docs keyboard.html).
        with kb.pressed(*objetos):
            kb.tap(tecla)
    else:
        using = []
        for m in mods:
            if m not in _MAPA_USING:
                c.fail("osascript no reconoce el modificador %r del combo %r "
                       "(validos: cmd, ctrl, shift, alt/option)."
                       % (m, args.cadena))
            using.append(_MAPA_USING[m])
        vk = c.vk_mac(final)
        if vk is not None and len(final) > 1:
            cuerpo = ('tell application "System Events" to key code (item 1 '
                      'of argv) using {%s}'
                      % ", ".join('"%s"' % u for u in using))
            c.osascript_valor(cuerpo, [vk], accion="key code combo")
        elif len(final) == 1:
            cuerpo = ('tell application "System Events" to keystroke (item 1 '
                      'of argv) using {%s}'
                      % ", ".join('"%s"' % u for u in using))
            c.osascript_valor(cuerpo, [final], accion="keystroke combo")
        else:
            c.fail("osascript no puede emitir la tecla final %r del combo "
                   "%r (sin pynput). pip3 install pynput==1.8.2."
                   % (final, args.cadena))
    item = {"ok": True, "combo": partes, "via": via}
    if foco:
        item["foco_verificado"] = foco
    c.json_out(item)


def cmd_mantener_mac(args):
    c.checar_abort()
    c.checar_pausa()
    segundos = c.cap_segundos_mantener(args.segundos)
    nombre = args.tecla.lower()
    if not _pynput_disponible():
        c.fail("mantener requiere pynput (press/release con sueno entre): "
               "python3 -m pip install pynput==1.8.2. osascript 'key down/up' "
               "solo cubre modificadores [runtime].")
    keyboard = c.try_pynput()
    kb = keyboard.Controller()
    tecla = c.tecla_pynput_mac(nombre)
    if tecla is None and len(nombre) == 1:
        tecla = nombre
    if tecla is None:
        vk = c.vk_mac(nombre)
        if vk is None:
            c.fail("Ninguna ruta reconoce la tecla %r para mantenerla."
                   % nombre)
        tecla = keyboard.KeyCode.from_vk(vk)
    kb.press(tecla)
    try:
        time.sleep(segundos)
    finally:
        kb.release(tecla)  # soltar SIEMPRE
    c.json_out({
        "ok": True,
        "tecla": c.nombre_tecla_mac(nombre)[0] or nombre,
        "segundos": segundos,
        "via": "pynput",
        "aviso": "auto-repeticion con tecla inyectada NO esta documentada "
                 "en macOS [runtime]: si la app no repite, emite pulsaciones "
                 "separadas con tecla --repeticiones",
    })


def construir_parser_mac():
    parser = c.Parser(
        prog="teclado.py (macOS)",
        description="Teclado para automatizacion de escritorio en macOS: "
                    "tipeo ASCII/unicode, teclas, combos y mantener pulsada. "
                    "Piramide: pynput (CGEvent) > osascript (argv) > "
                    "portapapeles (pbcopy). La ventana enfocada recibe todo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_DOC_MAC.split("Subcomandos:")[1]
        if _DOC_MAC and "Subcomandos:" in _DOC_MAC else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True,
                                metavar="SUBCOMANDO")

    p = sub.add_parser("escribir",
                       help="escribir texto en la ventana enfocada")
    p.add_argument("texto", help="texto literal (usa comillas)")
    p.add_argument("--intervalo", type=float, default=0.05,
                   help="segundos entre caracteres (por defecto 0.05)")
    p.add_argument("--via", default="auto", metavar="VIA",
                   help="auto|pynput|osascript|portapapeles (validado en "
                        "handler: invalido => JSON error). auto: pynput si "
                        "esta instalado; si no, portapapeles con no-ASCII u "
                        "osascript con argv")
    p.add_argument("--requiere-foco", dest="requiere_foco",
                   metavar="SUBCADENA",
                   help="abortar SIN emitir si la app/ventana foreground no "
                        "contiene esta subcadena (case-insensitive)")
    p.add_argument("--foco-id", dest="foco_id", type=int, metavar="ID",
                   help="(sin ruta en macOS: responde error JSON honesto "
                        "[runtime] — la rama no expone id estable de ventana)")
    p.set_defaults(func=cmd_escribir_mac)

    p = sub.add_parser("tecla",
                       help="pulsar una tecla por nombre (enter, esc, f5, "
                            "cmd, up, media_play_pause...)")
    p.add_argument("tecla", help="nombre de tecla (pynput Key darwin / tabla "
                                 "kVK_ / alias)")
    p.add_argument("--repeticiones", type=int, default=1,
                   help="veces (por defecto 1)")
    p.add_argument("--mods", nargs="+", metavar="MOD",
                   help="modificadores: cmd ctrl shift alt (usa combo para "
                        "esto)")
    p.add_argument("--requiere-foco", dest="requiere_foco",
                   metavar="SUBCADENA",
                   help="abortar SIN emitir si la app/ventana foreground no "
                        "contiene esta subcadena")
    p.add_argument("--foco-id", dest="foco_id", type=int, metavar="ID",
                   help="(sin ruta en macOS: error JSON honesto [runtime])")
    p.set_defaults(func=cmd_tecla_mac)

    p = sub.add_parser("combo",
                       help='combinacion tipo "cmd+shift+esc" '
                            "(down en orden, up inversa)")
    p.add_argument("cadena", help='cadena separada por +, ej. "cmd+s"')
    p.add_argument("--requiere-foco", dest="requiere_foco",
                   metavar="SUBCADENA",
                   help="abortar SIN emitir si la app/ventana foreground no "
                        "contiene esta subcadena")
    p.add_argument("--foco-id", dest="foco_id", type=int, metavar="ID",
                   help="(sin ruta en macOS: error JSON honesto [runtime])")
    p.set_defaults(func=cmd_combo_mac)

    p = sub.add_parser("mantener", help="mantener una tecla pulsada N segundos")
    p.add_argument("tecla", help="nombre de tecla")
    # TIEMPOS-K: mantener 1.0->0.8 s (-20%, piso 250 ok): duracion DEFAULT del
    # hold (press->sleep->release); el rango 0.05-60 s es limite C intocable.
    p.add_argument("--segundos", type=float, default=0.8,
                   help="duracion del mantenimiento (0.05-60, por defecto 0.8)")
    p.set_defaults(func=cmd_mantener_mac)

    return parser


# ===========================================================================
# main() UNIFICADO (FASE SEG3): dispatch en tiempo de ejecucion por
# sys.platform; `c` se bind-ea al modulo de primitivas del SO.
# ===========================================================================


def main():
    global c
    mod = _core.modulo_sistema()            # lee sys.platform EN TIEMPO DE EJECUCION
    if mod is None:
        _core.so_no_soportado("teclado.py")  # JSON rc 2 (nunca retorna)
    c = mod
    plat = sys.platform
    if plat == "win32":
        global pyautogui                     # import exclusivo Windows (era top)
        import pyautogui                     # glue ya fijo DPI + FAILSAFE + PAUSE
        parser = construir_parser()
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
        # Comportamiento historico por rama: win capturaba pyautogui.
        # FailSafeException tipada; la rama linux probaba por nombre de tipo;
        # la mac no tenia rama de failsafe (solo el generic).
        if (plat == "win32" and isinstance(exc, pyautogui.FailSafeException)) \
                or (plat == "linux"
                    and type(exc).__name__ == "FailSafeException"):
            c.fallar_por_failsafe(exc)
        c.fail("%s: %s" % (type(exc).__name__, exc))


if __name__ == "__main__":
    main()
