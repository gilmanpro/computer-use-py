# -*- coding: utf-8 -*-
"""teclado.py — Teclado en macOS (skill computer-use-py, dominio mac).

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
por osascript ANTES de emitir; aborta sin teclear si no coincide.

Subcomandos:
  escribir  Texto en la ventana enfocada (auto: pynput si disponible).
  tecla     Una tecla por nombre (tabla kVK_ del fuente pynput), repeticiones.
  combo     Cadena tipo "cmd+shift+esc" (pynput pressed(); reserva osascript).
  mantener  keyDown + sleep + keyUp (pynput; auto-repeticion [runtime]).

Ejemplos (desde la carpeta computer-use-py, en el Mac):
  python3 scripts/macos/teclado.py escribir "Espana: ñ ¿á? 😀"
  python3 scripts/macos/teclado.py escribir "clave" --via portapapeles
  python3 scripts/macos/teclado.py tecla enter --repeticiones 2
  python3 scripts/macos/teclado.py combo "cmd+s"
  python3 scripts/macos/teclado.py combo "cmd+shift+esc" --via osascript
  python3 scripts/macos/teclado.py mantener shift --segundos 1
"""

import argparse
import time

import _compartido_mac as c

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


def _foco_actual():
    """(app_frontmost, titulo_ventana_o_None) via System Events [runtime]."""
    cuerpo = ('tell application "System Events"\n'
              '\tset p to first application process whose frontmost is true\n'
              '\tset t to ""\n'
              '\ttry\n'
              '\t\tset t to name of window 1 of p\n'
              '\tend try\n'
              '\treturn "OK:" & (name of p) & "||" & t')
    rc, out, err = c.osascript(cuerpo, [])
    if rc != 0 or not out.startswith("OK:"):
        return None, None
    payload = out[3:]
    app, _, titulo = payload.partition("||")
    return app or None, (titulo or None)


def _verificar_foco_requerido(subcadena):
    """Comprueba el foco ANTES de emitir (flag --requiere-foco).

    Aborta con JSON "error" (incluye app y titulo reales) si ni la app
    frontmost ni su ventana 1 contienen la subcadena (case-insensitive).
    """
    app, titulo = _foco_actual()
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


def _escribir_pynput(texto, intervalo):
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


def _escribir_osascript(texto):
    """Respaldo System Events: keystroke con el texto por argv (NUNCA dentro
    del codigo AppleScript). \\n se emite como tecla return aparte [runtime:
    si keystroke existiera con \\n, se delegaria]."""
    lineas = texto.split("\n")
    cuerpo = ('tell application "System Events"\n'
              '\tkeystroke (item 1 of argv)\n'
              'end tell')
    ultimo = len(lineas) - 1
    for i, ln in enumerate(lineas):
        if ln:
            c.osascript_valor(cuerpo, [ln], accion="keystroke")
        if i < ultimo:
            # return entre lineas (kVK_Return=36 VERIFICADO fuente pynput)
            c.osascript_valor(
                'tell application "System Events" to key code 36', [],
                accion="key code return")


def _escribir_portapapeles(texto):
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
_VIAS = ("auto", "pynput", "osascript", "portapapeles")


def cmd_escribir(args):
    c.checar_abort()
    c.checar_pausa()
    if args.via not in _VIAS:
        c.fail("--via %r invalido para la rama macOS." % args.via,
               validos=list(_VIAS))
    foco = _verificar_foco_requerido(args.requiere_foco) \
        if args.requiere_foco else None
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
        _escribir_pynput(texto, args.intervalo)
    elif via == "osascript":
        _escribir_osascript(texto)
    else:
        _escribir_portapapeles(texto)
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


def cmd_tecla(args):
    c.checar_abort()
    c.checar_pausa()
    foco = _verificar_foco_requerido(args.requiere_foco) \
        if args.requiere_foco else None
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


def cmd_combo(args):
    c.checar_abort()
    c.checar_pausa()
    foco = _verificar_foco_requerido(args.requiere_foco) \
        if args.requiere_foco else None
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


def cmd_mantener(args):
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


def construir_parser():
    parser = c.Parser(
        prog="teclado.py (macOS)",
        description="Teclado para automatizacion de escritorio en macOS: "
                    "tipeo ASCII/unicode, teclas, combos y mantener pulsada. "
                    "Piramide: pynput (CGEvent) > osascript (argv) > "
                    "portapapeles (pbcopy). La ventana enfocada recibe todo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1]
        if __doc__ and "Subcomandos:" in __doc__ else None,
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
    p.set_defaults(func=cmd_escribir)

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
    p.set_defaults(func=cmd_tecla)

    p = sub.add_parser("combo",
                       help='combinacion tipo "cmd+shift+esc" '
                            "(down en orden, up inversa)")
    p.add_argument("cadena", help='cadena separada por +, ej. "cmd+s"')
    p.add_argument("--requiere-foco", dest="requiere_foco",
                   metavar="SUBCADENA",
                   help="abortar SIN emitir si la app/ventana foreground no "
                        "contiene esta subcadena")
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
    except SystemExit:
        raise
    except Exception as exc:
        c.fail("%s: %s" % (type(exc).__name__, exc))


if __name__ == "__main__":
    main()
