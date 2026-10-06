# -*- coding: utf-8 -*-
"""teclado.py — Teclado de la skill computer-use-py (PyAutoGUI + pynput).

Camino de cada tecla (piramide de la skill):
- pyautogui.press/write/hotkey: ASCII y teclas nombradas. En Windows su
  mapeo solo cubre caracteres 32-127: los NO-ASCII (ñ, á, ¿, emojis) se
  DESCARTAN EN SILENCIO, sin excepcion (verificado en _pyautogui_win.py).
- pynput.keyboard: tipeo unicode real via KEYEVENTF_UNICODE (funciona en
  apps normales: Office, navegadores, Explorador) y teclas multimedia
  Key.media_*.
- portapapeles (pyperclip + ctrl+v): respaldo cuando lo anterior falla.

Salida: JSON por stdout; errores JSON con "error". FAILSAFE siempre activo.

Verificacion de foco (P0.2): el flag OPCIONAL --requiere-foco "SUBCADENA" en
escribir/tecla/combo lee la ventana foreground (pygetwindow.getActiveWindow,
que en 0.0.9 es GetForegroundWindow) ANTES de emitir: si el titulo no
contiene la subcadena (case-insensitive) ABORTA con JSON "error" que
incluye el titulo real actual, sin teclear nada. Sin el flag el flujo queda
identico al validado.

Subcomandos:
  escribir  Texto en la ventana enfocada (auto: pynput si hay no-ASCII).
  tecla     Una tecla por nombre, con repeticiones y modificadores.
  combo     Cadena tipo "ctrl+shift+esc" (pulsar en orden, soltar al reves).
  mantener  keyDown + sleep + keyUp (sin auto-repetición en Windows).

Ejemplos (desde la carpeta computer-use-py):
  py scripts/teclado.py escribir "Hola"
  py scripts/teclado.py escribir "Espana: ñ ¿á? 😀" --via pynput
  py scripts/teclado.py escribir "clave" --requiere-foco "Firefox"
  py scripts/teclado.py tecla enter --repeticiones 2
  py scripts/teclado.py combo "ctrl+shift+esc"
  py scripts/teclado.py combo "win+shift+left"
  py scripts/teclado.py mantener shift --segundos 1
"""

import argparse
import time

import _compartido as c  # importa pyautogui ya con DPI + FAILSAFE + PAUSE
import pyautogui

# Vias validadas EN HANDLER (P1-7): un --via de otra rama o falso debe
# responder JSON {"error", "validos"}, no stderr de argparse.
_VIAS = ("auto", "pyautogui", "pynput", "portapapeles")


def _tiene_no_ascii(texto):
    return any(ord(ch) > 127 for ch in texto)


def _verificar_foco_requerido(subcadena):
    """Comprueba el foco ANTES de emitir (flag opcional --requiere-foco).

    Aborta con JSON "error" (incluye el titulo real actual) si la ventana
    foreground no existe o su titulo no contiene `subcadena`
    (case-insensitive). Devuelve el titulo cuando pasa la comprobacion.
    pygetwindow se importa aqui (solo donde se usa): sin el flag ningun
    camino de este script lo toca.
    """
    import pygetwindow as gw

    ventana = gw.getActiveWindow()  # 0.0.9 = GetForegroundWindow (VERIFICADO)
    titulo = ventana.title if ventana is not None else None
    if titulo is None or subcadena.lower() not in titulo.lower():
        c.fail("Foco incorrecto: NO se emitio nada. La ventana activa es %r y "
               "--requiere-foco pedia contener %r. Pon el foco correcto "
               "(ventanas.py activar / clic) o retira el flag asumiendo el "
               "riesgo." % (titulo, subcadena),
               titulo_actual=titulo, requiere=subcadena,
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
    foco = _verificar_foco_requerido(args.requiere_foco) if args.requiere_foco else None
    texto = args.texto
    via = args.via
    if via == "auto":
        via = "pynput" if _tiene_no_ascii(texto) else "pyautogui"
    if via == "pyautogui" and _tiene_no_ascii(texto):
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
        "contiene_no_ascii": _tiene_no_ascii(texto),
        "aviso": "el teclado va a la ventana enfocada (un toast de Windows 11 "
                 "puede robarte el foco): verifica con pantalla.py capturar",
    }
    if foco:
        item["foco_verificado"] = foco
    c.json_out(item)


def cmd_tecla(args):
    c.checar_abort("tecla")
    c.checar_pausa()
    foco = _verificar_foco_requerido(args.requiere_foco) if args.requiere_foco else None
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


def _partes_combo(cadena):
    partes = [p.strip().lower() for p in cadena.split("+") if p.strip()]
    if not partes:
        c.fail('Cadena de combo vacia. Formato: "ctrl+shift+esc" (separado por +).')
    return partes


def cmd_combo(args):
    c.checar_abort("combo")
    c.checar_pausa()
    foco = _verificar_foco_requerido(args.requiere_foco) if args.requiere_foco else None
    partes = _partes_combo(args.cadena)
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
    segundos = min(max(args.segundos, 0.05), 60.0)
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
    p.set_defaults(func=cmd_escribir)

    p = sub.add_parser("tecla", help="pulsar una tecla por nombre (enter, esc, f5, win...)")
    p.add_argument("tecla", help="nombre de tecla (pyautogui.KEYBOARD_KEYS; reserva pynput)")
    p.add_argument("--repeticiones", type=int, default=1, help="veces (por defecto 1)")
    p.add_argument("--mods", nargs="+", metavar="MOD",
                   help="modificadores: ctrl shift alt win (usa combo para esto)")
    p.add_argument("--requiere-foco", dest="requiere_foco", metavar="SUBCADENA",
                   help="abortar SIN emitir si el titulo de la ventana "
                        "foreground no contiene esta subcadena (case-insensitive)")
    p.set_defaults(func=cmd_tecla)

    p = sub.add_parser("combo", help='combinacion tipo "ctrl+shift+esc" (orden down, reversa up)')
    p.add_argument("cadena", help='cadena separada por +, ej. "ctrl+s"')
    p.add_argument("--requiere-foco", dest="requiere_foco", metavar="SUBCADENA",
                   help="abortar SIN emitir si el titulo de la ventana "
                        "foreground no contiene esta subcadena (case-insensitive)")
    p.set_defaults(func=cmd_combo)

    p = sub.add_parser("mantener", help="mantener una tecla pulsada N segundos")
    p.add_argument("tecla", help="nombre de tecla")
    p.add_argument("--segundos", type=float, default=1.0,
                   help="duracion del mantenimiento (0.05-60, por defecto 1)")
    p.set_defaults(func=cmd_mantener)

    return parser


def main():
    args = construir_parser().parse_args()
    try:
        args.func(args)
    except pyautogui.FailSafeException as exc:
        c.fallar_por_failsafe(exc)
    except SystemExit:
        raise
    except Exception as exc:
        c.fail("%s: %s" % (type(exc).__name__, exc))


if __name__ == "__main__":
    main()
