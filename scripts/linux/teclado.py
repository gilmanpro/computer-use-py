# -*- coding: utf-8 -*-
"""teclado.py — Teclado del dominio LINUX (skill computer-use-py).

MISMO contrato JSON del dominio Windows; superficie 100 % Python. Piramide
(references/linux-python.md §4 y §10):
  X11     pyautogui (ASCII; bajo Xlib/XTEST) y pynput (unicode segun el layout
          XKB [runtime]); portapapeles = pyperclip o xclip + ctrl+v [runtime].
  Wayland pyautogui/pynput NO llegan al compositor nativo (XTEST es de X11):
          wtype para texto/teclas y ydotool para combos/mantener. FLAGS DE
          wtype NO verificados aqui (el fetch del repo fallo) => [runtime];
          la sintaxis de ydotool key CODE:1/CODE:0 SI esta verificada en su
          man (28=Enter; codigos: /usr/include/linux/input-event-codes.h).

Verificacion de foco (paridad P0.2 con Windows): el flag OPCIONAL
--requiere-foco "SUBCADENA" lee la ventana activa ANTES de emitir — X11:
xdotool getactivewindow getwindowname (man verbatim); Wayland: nodo focused de
swaymsg -t get_tree o hyprctl activewindow -j [runtime]. Si el titulo no
contiene la subcadena (case-insensitive) ABORTA con JSON "error" y el titulo
real, sin teclear nada.

Salida: JSON por stdout; errores JSON con "error".

Subcomandos:
  escribir  Texto en la ventana enfocada (auto elige la ruta por sesion).
  tecla     Una tecla por nombre, con repeticiones.
  combo     Cadena tipo "ctrl+shift+esc" (pulsar en orden, soltar al reves).
  mantener  keyDown + sleep + keyUp (Wayland: ydotool key CODE:1 ... CODE:0).

Ejemplos (desde la carpeta computer-use-py, en la maquina Linux):
  python3 scripts/linux/teclado.py escribir "Hola"
  python3 scripts/linux/teclado.py escribir "Espana: n con tilde" --via wtype
  python3 scripts/linux/teclado.py escribir "clave" --requiere-foco "Firefox"
  python3 scripts/linux/teclado.py tecla enter --repeticiones 2
  python3 scripts/linux/teclado.py combo "ctrl+shift+esc"
  python3 scripts/linux/teclado.py mantener shift --segundos 1
"""

import argparse
import time

import _compartido_linux as c

# Vias validadas EN HANDLER (P1-7): un --via falso o de otra rama responde JSON
# {"error","validos"}, nunca stderr de argparse.
_VIAS = ("auto", "pyautogui", "pynput", "portapapeles", "wtype", "ydotool")


def _pyautogui():
    """Import LAZY delegado al helper unico de la rama (P2-2)."""
    return c.pyautogui_lazy()


# _tiene_no_ascii: generico en _core (identico en las 3 ramas); se llama via
# c.tiene_no_ascii.


def _titulo_foco():
    """Titulo de la ventana activa o None (best effort por sesion)."""
    sesion = c.deteccion_sesion()
    if sesion == "x11":
        r = c.run("xdotool", ["getactivewindow", "getwindowname"], timeout=10.0)
        if r["rc"] != 0:
            return None
        return r["stdout"].strip() or None
    if sesion == "wayland":
        import json as _json
        import shutil
        if shutil.which("swaymsg"):
            r = c.run("swaymsg", ["-t", "get_tree"], timeout=15.0)
            if r["rc"] == 0:
                try:
                    nodo = _buscar_foco(_json.loads(r["stdout"]))
                except ValueError:
                    nodo = None
                if nodo is not None:
                    return nodo
        elif shutil.which("hyprctl"):
            r = c.run("hyprctl", ["activewindow", "-j"], timeout=15.0)
            if r["rc"] == 0:
                try:
                    d = _json.loads(r["stdout"])
                    return d.get("title")  # [runtime] hyprctl -j no fetcheado
                except ValueError:
                    return None
        return None
    return None


def _buscar_foco(nodo):
    """Recorre el arbol sway buscando el primer nodo focused con nombre."""
    import json  # noqa: F401 (el llamador ya parseo; recursion pura)
    if isinstance(nodo, dict):
        if nodo.get("focused") and nodo.get("name"):
            return nodo["name"]
        for clave in ("nodes", "floating_nodes", "window", "contents"):
            hijo = nodo.get(clave)
            if isinstance(hijo, list):
                for sub in hijo:
                    t = _buscar_foco(sub)
                    if t:
                        return t
    return None


def _verificar_foco_requerido(subcadena):
    """Comprueba el foco ANTES de emitir (flag opcional --requiere-foco)."""
    titulo = _titulo_foco()
    if titulo is None or subcadena.lower() not in titulo.lower():
        c.fail("Foco incorrecto: NO se emitio nada. La ventana activa es %r y "
               "--requiere-foco pedia contener %r. Pon el foco correcto "
               "(ventanas.py activar / clic) o retira el flag asumiendo el "
               "riesgo." % (titulo, subcadena),
               titulo_actual=titulo, requiere=subcadena,
               pista="ventanas.py foco muestra la ventana foreground actual")
    return titulo


# --- rutas X11 ------------------------------------------------------------

def _escribir_pyautogui(texto, intervalo):
    """ASCII por write(); \\n y \\t por press(). No-ASCII: en Linux pyautogui
    usa keysyms Xlib y PUEDE cubrir mas que el rango 32-127 de Windows, pero
    no esta verificado ([runtime]): ante cualquier fallo se deriva al JSON con
    sugerencia de --via pynput/portapapeles/wtype."""
    pa = _pyautogui()
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


def _escribir_pynput(texto, intervalo):
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


def _escribir_portapapeles(texto):
    """X11: pyperclip (usa xclip/xsel por debajo [runtime]) o xclip directo;
    pegar con ctrl+v de pyautogui."""
    pa = _pyautogui()
    try:
        import pyperclip

        pyperclip.copy(texto)
        via_clip = "pyperclip"
    except Exception:
        r = c.run("xclip", ["-selection", "clipboard"], entrada=texto,
                  timeout=10.0)
        if r["rc"] != 0:
            c.fail("Ni pyperclip ni xclip pudieron escribir el portapapeles "
                   "(xclip: %s). Instalar: apt install xclip / python3 -m pip "
                   "install pyperclip." % r["stderr"].strip())
        via_clip = "xclip -selection clipboard"
    time.sleep(0.05)  # asentar el portapapeles antes de pegar
    pa.hotkey("ctrl", "v")
    return via_clip


# --- rutas Wayland ---------------------------------------------------------

def _escribir_wtype(texto):
    """wtype emite el texto por la capa del compositor (unicode nativo).
    FLAGS [runtime] (el fetch del repo fallo en la investigacion): se pasa el
    texto posicional; si empieza con '-' se protege con '--'."""
    argv = ["--", texto] if texto.startswith("-") else [texto]
    r = c.run("wtype", argv, timeout=30.0)
    if r["rc"] != 0:
        c.fail("wtype fallo (rc=%d): %s. Verifica `wtype -h` (flags "
               "[runtime] en references/linux-python.md) o usa --via ydotool "
               "type." % (r["rc"], r["stderr"].strip()))


def _tecla_wtype(nombre):
    """wtype -k <keysym>: sintaxis [-k] NO verificada [runtime]; keysym por
    nombre XKB."""
    keysym = _KEYSYMS.get(nombre, nombre)
    r = c.run("wtype", ["-k", keysym], timeout=15.0)
    if r["rc"] != 0:
        c.fail("wtype -k %r fallo (rc=%d): %s (flags wtype = [runtime]; "
               "alternativa: ydotool key CODE:1 CODE:0 con la tabla de "
               "teclado.py)" % (nombre, r["rc"], r["stderr"].strip()))


def _ydotool_seq(tokens):
    """ydotool key <CODE:1/0 ...> (sintaxis man-verified en 1 lote)."""
    r = c.run("ydotool", ["key"] + tokens, timeout=30.0)
    if r["rc"] != 0:
        c.fail("ydotool key fallo (rc=%d): %s. Requiere el demonio ydotoold "
               "corriendo, YDOTOOL_SOCKET/permisos correctos y pertenecer al "
               "grupo input [runtime] (refs linux-python.md §4)."
               % (r["rc"], r["stderr"].strip()))


def _code_de(nombre):
    """Codigo ydotool para un nombre/alias, o None."""
    n = str(nombre).strip().lower()
    n = c.ALIAS_TECLAS_PYNPUT.get(n, n)
    return c.KEY_CODES.get(n)


_KEYSYMS = {
    "enter": "Enter", "intro": "Enter", "return": "Enter",
    "esc": "Escape", "escape": "Escape",
    "tab": "Tab", "espacio": "space", "space": "space",
    "backspace": "BackSpace", "supr": "Delete", "del": "Delete",
    "delete": "Delete", "home": "Home", "end": "End",
    "pageup": "Page_Up", "pgup": "Page_Up",
    "pagedown": "Page_Down", "pgdn": "Page_Down",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "ctrl": "Control_L", "shift": "Shift_L", "alt": "Alt_L",
    "win": "Super_L", "super": "Super_L", "meta": "Super_L",
    "printscreen": "Print", "prtsc": "Print",
}


# --- subcomandos -------------------------------------------------------------

def cmd_escribir(args):
    c.checar_abort("escribir")
    c.checar_pausa()
    if args.via not in _VIAS:
        c.fail("--via %r invalido para la rama Linux." % args.via,
               validos=list(_VIAS), sesion=c.deteccion_sesion())
    foco = _verificar_foco_requerido(args.requiere_foco) if args.requiere_foco else None
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
            _ydotool_seq(["29:1", "47:1", "47:0", "29:0"])  # ctrl+v
            via_clip = "wl-copy"
        else:
            via_clip = _escribir_portapapeles(texto)
    elif via == "pynput":
        _escribir_pynput(texto, args.intervalo)
    elif via == "pyautogui":
        _escribir_pyautogui(texto, args.intervalo)
    elif via == "wtype":
        _escribir_wtype(texto)
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


def cmd_tecla(args):
    c.checar_abort("tecla")
    c.checar_pausa()
    foco = _verificar_foco_requerido(args.requiere_foco) if args.requiere_foco else None
    nombre = args.tecla.lower()
    repeticiones = max(1, args.repeticiones)
    mods = [m.lower() for m in (args.mods or [])]
    sesion = c.deteccion_sesion()
    if sesion == "wayland":
        if mods:
            combo = "+".join(mods + [nombre])
            for _ in range(repeticiones):
                _emitir_combo_ydotool(combo)
                if repeticiones > 1:
                    time.sleep(0.05)
            item = {"ok": True, "tecla": nombre, "repeticiones": repeticiones,
                    "mods": mods, "via": "ydotool key (combo)", "sesion": sesion}
        else:
            for _ in range(repeticiones):
                _tecla_wtype(nombre)
                time.sleep(0.05)
            item = {"ok": True, "tecla": nombre, "repeticiones": repeticiones,
                    "via": "wtype -k [runtime]", "sesion": sesion}
        if foco:
            item["foco_verificado"] = foco
        c.json_out(item)
        return
    pa = _pyautogui()
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


def _emitir_combo_ydotool(cadena):
    """Combo Wayland por ydotool: mods down -> tecla down/up -> mods up en
    orden inverso, en una sola invocacion. SINTAXIS CODE:1/0 verificada
    (man); CODIGOS de la tabla KEY_CODES = [runtime] salvo 28/38/24/42."""
    partes = c.partes_combo(cadena, "ctrl+shift+esc")
    if len(partes) < 2:
        c.fail("Un combo necesita al menos un modificador y una tecla: "
               '"ctrl+s". Para una tecla suelta usa tecla.')
    mod_codes = []
    for p in partes[:-1]:
        n = c.ALIAS_TECLAS_PYNPUT.get(p, p)
        if n not in c._MODS_YDOTOOL:
            c.fail("Modificador no reconocido para ydotool: %r (validos: "
                   "ctrl, shift, alt, super y sus variantes _l/_r)." % p)
        mod_codes.append(c.KEY_CODES[n])
    final = _code_de(partes[-1])
    if final is None:
        c.fail("Tecla final no esta en la tabla KEY_CODES (ydotool): %r. "
               "La tabla cubre letras, numeros, funciones y navegacion; "
               "confirma codigos en /usr/include/linux/input-event-codes.h "
               "[runtime]." % partes[-1])
    tokens = ["%d:1" % m for m in mod_codes]
    tokens.append("%d:1" % final)
    tokens.append("%d:0" % final)
    tokens += ["%d:0" % m for m in reversed(mod_codes)]
    _ydotool_seq(tokens)


def cmd_combo(args):
    c.checar_abort("combo")
    c.checar_pausa()
    foco = _verificar_foco_requerido(args.requiere_foco) if args.requiere_foco else None
    partes = c.partes_combo(args.cadena, "ctrl+shift+esc")
    sesion = c.deteccion_sesion()
    if sesion == "wayland":
        _emitir_combo_ydotool(args.cadena)
        item = {"ok": True, "combo": partes, "via": "ydotool key",
                "sesion": sesion,
                "aviso": "codigos de la tabla [runtime] (verificado: sintaxis "
                         "CODE:1/CODE:0 y 28/38/24/42 del man)"}
        if foco:
            item["foco_verificado"] = foco
        c.json_out(item)
        return
    pa = _pyautogui()
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


def cmd_mantener(args):
    c.checar_abort("mantener")
    c.checar_pausa()
    segundos = c.cap_segundos_mantener(args.segundos)
    nombre = args.tecla.lower()
    sesion = c.deteccion_sesion()
    if sesion == "wayland":
        code = _code_de(nombre)
        if code is None:
            c.fail("mantener (ydotool) no tiene codigo para %r en la tabla "
                   "KEY_CODES [runtime]." % nombre)
        _ydotool_seq(["%d:1" % code])
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
    pa = _pyautogui()
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


def construir_parser():
    parser = c.Parser(
        prog="teclado.py (linux)",
        description="Teclado Linux: X11 por pyautogui/pynput (librerias "
                    "Python) y Wayland por wtype/ydotool (subprocess interno; "
                    "superficie JSON identica al dominio Windows).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1] if __doc__ and "Subcomandos:" in __doc__ else None,
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
    p.set_defaults(func=cmd_escribir)

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
    p.set_defaults(func=cmd_tecla)

    p = sub.add_parser("combo", help='combinacion tipo "ctrl+shift+esc" '
                       "(orden down, reversa up)")
    p.add_argument("cadena", help='cadena separada por +, ej. "ctrl+s"')
    p.add_argument("--requiere-foco", dest="requiere_foco", metavar="SUBCADENA",
                   help="abortar SIN emitir si el titulo de la ventana "
                        "foreground no contiene esta subcadena")
    p.set_defaults(func=cmd_combo)

    p = sub.add_parser("mantener", help="mantener una tecla pulsada N segundos")
    p.add_argument("tecla", help="nombre de tecla")
    p.add_argument("--segundos", type=float, default=1.0,
                   help="duracion (0.05-60, default 1)")
    p.set_defaults(func=cmd_mantener)

    return parser


def main():
    args = construir_parser().parse_args()
    try:
        args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        if type(exc).__name__ == "FailSafeException":
            c.fallar_por_failsafe(exc)
        c.fail("%s: %s" % (type(exc).__name__, exc))


if __name__ == "__main__":
    main()
