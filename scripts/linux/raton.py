# -*- coding: utf-8 -*-
"""raton.py — Raton del dominio LINUX (skill computer-use-py).

MISMO contrato JSON del dominio Windows; superficie 100 % Python:
  X11     pyautogui (libreria Python; inyecta XTEST) para mover/click/drag y
          pynput/xdotool para scroll. En X11 NO existe la division
          "primario vs secundario" de Windows: el servidor X tiene UN solo
          espacio de coordenadas (el screen) y pyautogui lo cubre entero
          — el offset del primario se lee en monitores.py listar
          (refs linux-python.md §7).
  Wayland pyautogui no llega al compositor nativo: el raton va por
          ydotool (uinput). VERIFICADO en su man: mousemove es RELATIVO por
          defecto y existe la bandera `--absolute` ("ydotool mousemove
          --absolute 100 100") => esta skill usa SIEMPRE --absolute. El
          soporte absoluto real del dispositivo uinput del demonio es
          [runtime]. NO hay FAILSAFE de pyautogui en Wayland: el freno humano
          es la bandera ABORT del .tmp (vigilar) o Ctrl+C (refs §11 y abajo).

Guard de marco (equivalente al de Windows): todo destino debe caer dentro
del bounding de LAYOUT; fuera => JSON "error". En X11 los "huecos" entre
monitores son zona viva del screen (fondo de escritorio): se permiten y se
anotan, a diferencia de Windows donde abortan.

Click/drag Wayland (man ydotool, verbatim): botones con mascara "0x40 Mouse
down / 0x80 Mouse up": click = 0xC0 (left, "down then up"), 0x41 (right
down), 0x82 (middle up) => down=0x40/0x41/0x42, up=0x80/0x81/0x82, doble =
--repeat 2 (opcion verificada).

Salida: JSON por stdout; errores JSON con "error".

Subcomandos:
  mover      Cursor a (x, y) de layout (animado via pyautogui en X11).
  click      Simple/derecho/doble, donde este el cursor o en (--x, --y).
  arrastrar  press -> trayectoria -> release (SIEMPRE suelta al final).
  scroll     Rueda vertical (X11; pynput o xdotool click 4/5). Wayland:
             ydotool 1.0.4 NO implementa eje de rueda => error honesto con
             workaround por teclas Page_Up/Page_Down [runtime].
  posicion   Cursor actual (solo X11: xdotool getmouselocation --shell).

Ejemplos (desde la carpeta computer-use-py, en la maquina Linux):
  python3 scripts/linux/raton.py mover 640 300 --duracion 0.2
  python3 scripts/linux/raton.py click --x 640 --y 300 --boton right
  python3 scripts/linux/raton.py arrastrar 100 100 400 350 --duracion 0.5
  python3 scripts/linux/raton.py scroll --vertical -5 --x 800 --y 400
  python3 scripts/linux/raton.py posicion
"""

import argparse
import time

import _compartido_linux as c

_BOTONES = ("left", "right", "middle")
# Codigos de click ydotool (man): 0x00 LEFT / 0x01 RIGHT / 0x02 MIDDLE mas
# mascara 0x40 down | 0x80 up. 0xC0 verbatim; 0xC1/0xC2/0x4x/0x8x derivados
# de la regla documentada [runtime].
_CLICK_YDOTOOL = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}
_DOWN_YDOTOOL = {"left": "0x40", "right": "0x41", "middle": "0x42"}
_UP_YDOTOOL = {"left": "0x80", "right": "0x81", "middle": "0x82"}

_AVISO_WAYLAND = ("WAYLAND: no existe el FAILSAFE de pyautogui en esta ruta "
                  "(uinput via ydotool): el freno humano es la bandera ABORT "
                  "del .tmp o Ctrl+C; tras un abort a medio arrastre el boton "
                  "puede quedar pulsado — sueltalo con click 0x8x")


def _pyautogui():
    """Import LAZY delegado al helper unico de la rama (P2-2)."""
    return c.pyautogui_lazy()


def _monitor_dict(m):
    """Sub-objeto monitor canonico con 'primario' SIEMPRE (P1-3)."""
    if m is None:
        return None
    return {"indice": m["indice"], "nombre": m["nombre"],
            "primario": m["primario"]}


def _ydotool(argv, timeout=30.0):
    r = c.run("ydotool", argv, timeout=timeout)
    if r["rc"] != 0:
        c.fail("ydotool %s fallo (rc=%d): %s. Requiere ydotoold corriendo, "
               "YDOTOOL_SOCKET/permisos y grupo input [runtime] (refs "
               "linux-python.md §4)." % (" ".join(argv), r["rc"],
                                          r["stderr"].strip()))


def _guard_destino(x, y):
    """Guard basico: (x, y) dentro del bounding de layout o JSON error.

    Devuelve el monitor que contiene el punto o None (hueco X11 = zona viva
    del screen; se permite con nota).
    """
    if not c.dentro_de_virtual(x, y):
        v = c.tamano_virtual()
        c.fail("Destino (%d, %d) fuera del bounding de layout "
               "(x %d..%d, y %d..%d). Mapa: monitores.py listar."
               % (x, y, v["x"], v["x"] + v["ancho"] - 1,
                  v["y"], v["y"] + v["alto"] - 1))
    return c._monitor_contiene(x, y)


def _cursor():
    """(x, y) actual si es legible (X11), else None."""
    if c.deteccion_sesion() != "x11":
        return None
    r = c.run("xdotool", ["getmouselocation", "--shell"], timeout=10.0)
    if r["rc"] != 0:
        return None
    kv = c._shell_kv(r["stdout"])
    try:
        return int(kv["X"]), int(kv["Y"])
    except (KeyError, ValueError):
        return None


def cmd_mover(args):
    c.checar_abort("mover")   # P1-6: bandera dura (Wayland sin FAILSAFE: es el freno)
    c.checar_pausa()          # P1-5
    m = _guard_destino(args.x, args.y)
    sesion = c.deteccion_sesion()
    ax, ay = _cursor() or (None, None)
    if sesion == "x11":
        pa = _pyautogui()
        # tween interno de pyautogui (opaco al flag entre pasos): el ABORT se
        # honra al INICIO (arriba) y en los interpolados propios de arrastrar.
        pa.moveTo(args.x, args.y, duration=args.duracion)
        via = "pyautogui.moveTo (X11; FAILSAFE activo)"
    elif sesion == "wayland":
        # man ydotool VERIFICA la bandera: "mousemove [-a,--absolute] <x> <y>"
        # con ejemplo absoluto verbatim. Sin lectura de cursor posible, la
        # interpolacion de --duracion no tiene origen del que partir: se hace
        # salto directo (la animacion real la perdona el compositor de todos
        # modos al no haber eventos intermedios conocidos).
        _ydotool(["mousemove", "--absolute", args.x, args.y])
        via = ("ydotool mousemove --absolute (relativo por defecto segun man; "
               "--duracion ignorada: sin lectura de cursor no hay "
               "interpolacion [runtime])")
    else:
        c.fail("Sesion grafica sin detectar: sin ruta de raton. refs "
               "linux-python.md §2/§13.", sesion=sesion)
    nx, ny = _cursor() or (args.x, args.y)
    c.json_out({
        "ok": True,
        "via": via,
        "sesion": sesion,
        "marco": c.MARCO,
        "desde": None if ax is None else [ax, ay],
        "hasta": [nx, ny],
        "monitor": _monitor_dict(m),
        "aviso": _AVISO_WAYLAND if sesion == "wayland" else
                 "en X11 el punto puede quedar en un hueco entre monitores "
                 "(zona viva del screen): no es un fallo, es escritorio",
    })


def cmd_click(args):
    c.checar_abort("click")
    c.checar_pausa()
    if args.boton not in _BOTONES:
        c.fail("Boton %r invalido para la rama Linux." % args.boton,
               validos=list(_BOTONES))
    if (args.x is None) != (args.y is None):
        c.fail("Debe indicar --x e --y juntos, o ninguno (clic en la "
               "posicion actual).")
    sesion = c.deteccion_sesion()
    m = None
    if args.x is not None:
        m = _guard_destino(args.x, args.y)
    if sesion == "x11":
        pa = _pyautogui()
        pa.click(x=args.x, y=args.y, button=args.boton,
                 clicks=2 if args.doble else 1, interval=0.08)
        via = "pyautogui.click (X11; FAILSAFE activo)"
    elif sesion == "wayland":
        if args.x is not None:
            _ydotool(["mousemove", "--absolute", args.x, args.y], timeout=10.0)
        argv = ["click"]
        if args.doble:
            argv += ["--repeat", "2"]
        argv.append(_CLICK_YDOTOOL[args.boton])
        _ydotool(argv)
        via = ("ydotool click %s (%s) [runtime 0xC1/0xC2]"
               % (_CLICK_YDOTOOL[args.boton], args.boton))
    else:
        c.fail("Sesion grafica sin detectar: sin ruta de click. refs "
               "linux-python.md §2/§13.", sesion=sesion)
    cur = _cursor()
    if m is None and cur is not None:
        m = c._monitor_contiene(cur[0], cur[1])
    c.json_out({
        "ok": True,
        "via": via,
        "sesion": sesion,
        "marco": c.MARCO,
        "boton": args.boton,
        "doble": bool(args.doble),
        "cursor": None if cur is None else [cur[0], cur[1]],
        # P1-3: 'monitor' canonico con 'primario' SIEMPRE
        "monitor": _monitor_dict(m),
        "aviso": ("el exito de un clic NO se reporta (la app decide si lo "
                  "consume): verifica SIEMPRE con pantalla.py capturar. "
                  + (_AVISO_WAYLAND if sesion == "wayland" else "")),
    })


def cmd_arrastrar(args):
    c.checar_abort("arrastrar")
    c.checar_pausa()
    if args.boton not in _BOTONES:
        c.fail("Boton %r invalido para la rama Linux." % args.boton,
               validos=list(_BOTONES))
    m1 = _guard_destino(args.x1, args.y1)
    m2 = _guard_destino(args.x2, args.y2)
    sesion = c.deteccion_sesion()
    duracion = min(max(args.duracion, 0.1), 30.0)
    if sesion == "x11":
        pa = _pyautogui()
        pasos = max(10, min(int(duracion / 0.01), 200))
        retardo = duracion / pasos
        pa.moveTo(args.x1, args.y1)
        pa.mouseDown(button=args.boton)
        try:
            for i in range(1, pasos + 1):
                nx = args.x1 + (args.x2 - args.x1) * i / pasos
                ny = args.y1 + (args.y2 - args.y1) * i / pasos
                pa.moveTo(nx, ny)
                time.sleep(retardo)
                # P1-6: ABORT a medio arrastre corta (el finally suelta SIEMPRE).
                c.checar_abort("arrastrar")
        finally:
            pa.mouseUp(button=args.boton)  # soltar SIEMPRE (aunque FAILSAFE)
        via = "pyautogui mouseDown/move/mouseUp (X11)"
    elif sesion == "wayland":
        # trayecto con ydotool: down (0x4x) -> --absolute interpolado -> up
        # (0x8x). Cada paso es un proceso: topamos a 25 para no castigar.
        pasos = max(5, min(int(duracion / 0.04), 25))
        retardo = duracion / pasos
        _ydotool(["mousemove", "--absolute", args.x1, args.y1], timeout=10.0)
        _ydotool(["click", _DOWN_YDOTOOL[args.boton]], timeout=10.0)
        try:
            for i in range(1, pasos + 1):
                # ABORT entre pasos: sin FAILSAFE en Wayland, es el freno duro;
                # el finally suelta el boton igualmente (no deja clic colgado).
                c.checar_abort("arrastrar")
                nx = int(args.x1 + (args.x2 - args.x1) * i / pasos)
                ny = int(args.y1 + (args.y2 - args.y1) * i / pasos)
                _ydotool(["mousemove", "--absolute", nx, ny], timeout=10.0)
                time.sleep(retardo)
        finally:
            _ydotool(["click", _UP_YDOTOOL[args.boton]], timeout=10.0)
        via = ("ydotool mousemove --absolute + click %s/%s [regla de "
               "mascara del man; 0x41/0x82 verbatim]"
               % (_DOWN_YDOTOOL[args.boton], _UP_YDOTOOL[args.boton]))
    else:
        c.fail("Sesion grafica sin detectar: sin ruta de arrastre. refs "
               "linux-python.md §2/§13.", sesion=sesion)
    cur = _cursor()
    c.json_out({
        "ok": True,
        "via": via,
        "sesion": sesion,
        "marco": c.MARCO,
        "desde": [args.x1, args.y1],
        "hasta": [cur[0], cur[1]] if cur else [args.x2, args.y2],
        "boton": args.boton,
        "monitor": _monitor_dict(m2),
        "aviso": ("verifica el resultado con pantalla.py capturar. "
                  + (_AVISO_WAYLAND if sesion == "wayland" else
                     "tras un FAILSAFE a media trayectoria el boton ya fue "
                     "soltado (finally); re-captura antes de reintentar")),
    })


def cmd_scroll(args):
    c.checar_abort("scroll")
    c.checar_pausa()
    if args.vertical is None and args.horizontal is None:
        c.fail("Indica --vertical N o --horizontal N (excluyentes).")
    if (args.x is None) != (args.y is None):
        c.fail("Debe indicar --x e --y juntos, o ninguno.")
    sesion = c.deteccion_sesion()
    if sesion == "wayland":
        c.fail("SCROLL no tiene ruta en Wayland con las tools auditadas: "
               "ydotool 1.0.4 solo implementa type/key/mousemove/click "
               "(man verbatim) y la rueda es un eje (REL_WHEEL), no un boton. "
               "Workaround: teclado.py tecla pageup/pagedown (codigos 104/109 "
               "[runtime]) o wtype -k Page_Down [runtime].",
               sesion=sesion,
               referencias="refs linux-python.md §11")
    if args.x is not None:
        _guard_destino(args.x, args.y)
    dy = int(args.vertical) if args.vertical is not None else 0
    dx = int(args.horizontal) if args.horizontal is not None else 0
    es_vertical = args.vertical is not None  # fix menor: --vertical 0 == vertical
    n_solicitado = abs(dy) if es_vertical else abs(dx)
    if n_solicitado == 0:
        # 0 pasos = NO se emite nada (ni siquiera el moveTo de --x: cero
        # efectos). El eje se etiqueta por `is not None`, no por verdad de dy.
        c.json_out({
            "ok": True,
            "eje": "vertical" if es_vertical else "horizontal",
            "pasos": 0,
            "sentido": (("arriba" if dy >= 0 else "abajo") if es_vertical
                        else ("derecha" if dx >= 0 else "izquierda")),
            "via": "nada (0 pasos: sin emision)",
            "sesion": sesion,
            "marco": c.MARCO,
            "nota": "--vertical 0 / --horizontal 0 no rueda ni posiciona: "
                    "el eje se deriva de la bandera presente (is not None), "
                    "no del valor",
        })
        return
    pa = _pyautogui()
    if args.x is not None:
        pa.moveTo(args.x, args.y)
    # Ruta primaria: pynput (ambos ejes en una llamada; signs X11 [runtime]).
    # Respaldo: xdotool click 4/5 — botones VERIFICADOS en man ("wheel up is
    # 4, wheel down is 5"); horizontal 6/7 [runtime].
    via = "pynput.mouse.scroll"
    direccion_garantizada = None
    if args.garantizar_direccion:
        # P1-4: fuerza la ruta xdotool (4/5 con signo VERIFICADO en man),
        # evitando que un pynput con signo invertido [runtime] ruede al reves.
        n = min(abs(dy) if es_vertical else abs(dx), 30)
        if es_vertical:
            steps = ["5"] * n if dy < 0 else ["4"] * n
            direccion_garantizada = "xdotool click 4=arriba/5=abajo (man verbatim)"
        else:
            steps = ["7"] * n if dx < 0 else ["6"] * n
            direccion_garantizada = "xdotool click 6/7 horizontal [runtime]"
        if n > 0:
            r = c.run("xdotool", ["click"] + steps, timeout=30.0)
            if r["rc"] != 0:
                c.fail("xdotool click fallo (rc=%d): %s"
                       % (r["rc"], r["stderr"].strip()))
            via = "xdotool click %s (--garantizar-direccion)" % "/".join(
                sorted(set(steps)))
    else:
        try:
            from pynput.mouse import Controller as ControladorRaton

            ControladorRaton().scroll(dx, dy)
        except Exception as exc:
            n = min(abs(dy) if es_vertical else abs(dx), 30)
            if es_vertical:
                steps = ["5"] * n if dy < 0 else ["4"] * n
            else:
                steps = ["7"] * n if dx < 0 else ["6"] * n
            r = c.run("xdotool", ["click"] + steps, timeout=30.0)
            if r["rc"] != 0:
                c.fail("pynput rechazo el scroll (%s) y xdotool click fallo "
                       "(rc=%d): %s" % (exc, r["rc"], r["stderr"].strip()))
            via = "xdotool click 4/5 (vertical; 6/7 horizontal [runtime])"
    item = {
        "ok": True,
        "eje": "vertical" if es_vertical else "horizontal",
        "pasos": abs(dy) if es_vertical else abs(dx),
        "sentido": (("arriba" if dy > 0 else "abajo") if es_vertical
                    else ("derecha" if dx > 0 else "izquierda")),
        "via": via,
        "sesion": sesion,
        "marco": c.MARCO,
        "nota": "X11 rueda = botones 4 (arriba) / 5 (abajo) VERIFICADOS en "
                "man xdotool; la convencion de signos por pynput en Linux es "
                "[runtime] — si el sentido se invierte en tu WM, repite con "
                "--garantizar-direccion (fuerza xdotool) y verifica con una "
                "captura; 1 paso = 1 click de rueda",
    }
    if direccion_garantizada:
        item["direccion_garantizada"] = direccion_garantizada
    c.json_out(item)


def cmd_posicion(args):
    if c.deteccion_sesion() != "x11":
        c.fail("posicion del cursor no legible en Wayland con las tools "
               "auditadas (ydotool es solo-escritura; refs linux-python.md "
               "§11): usa capturar + vision.", sesion=c.deteccion_sesion())
    cur = _cursor()
    if cur is None:
        c.fail("xdotool getmouselocation no devolvio coordenadas (¿DISPLAY "
               "exportada? ¿X server vivo?). refs linux-python.md §13.")
    vx, vy = cur
    m = c._monitor_contiene(vx, vy)
    # P1-1: forma canonica plana x/y/marco/via/por_backend (identica a win/mac).
    por_backend = {"xdotool": {"x": int(vx), "y": int(vy)}}
    nota = ("x/y canonicas en coords de LAYOUT del screen X11; origen (0,0) "
            "= sup-izq del SCREEN (no del primario: lee monitores.py listar). "
            "'monitor' = quien contiene el cursor.")
    try:
        import pyautogui  # lectura OPCIONAL: nunca fail() desde aqui

        p = pyautogui.position()
        por_backend["pyautogui"] = {"x": int(p.x), "y": int(p.y)}
    except Exception as exc:
        por_backend["pyautogui"] = None  # lectura no disponible: null honesto
        nota += (" pyautogui.position no legible aqui (%s): ruta canonica "
                 "xdotool." % type(exc).__name__)
    try:
        from pynput.mouse import Controller as ControladorRaton

        px, py = ControladorRaton().position
        por_backend["pynput"] = {"x": int(px), "y": int(py)}
    except Exception:
        por_backend["pynput"] = None
    c.json_out({
        "ok": True,
        "x": int(vx), "y": int(vy),
        "marco": c.MARCO,
        "via": "xdotool getmouselocation --shell",
        "monitor": _monitor_dict(m),
        "por_backend": por_backend,
        "sesion": "x11",
        "nota": nota,
    })


def construir_parser():
    parser = c.Parser(
        prog="raton.py (linux)",
        description="Raton Linux: X11 via pyautogui/pynput/xdotool y Wayland "
                    "via ydotool (mousemove --absolute, click con mascaras). "
                    "Coordenadas = LAYOUT (monitores.py listar).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1] if __doc__ and "Subcomandos:" in __doc__ else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    p = sub.add_parser("mover", help="desplazar el cursor")
    p.add_argument("x", type=int, help="destino X (pixel de layout)")
    p.add_argument("y", type=int, help="destino Y (pixel de layout)")
    p.add_argument("--duracion", type=float, default=0.2,
                   help="segundos del desplazamiento animado (0 = instantaneo)")
    p.set_defaults(func=cmd_mover)

    p = sub.add_parser("click", help="clic simple/derecho/doble")
    p.add_argument("--x", type=int, help="coordenada X de layout (opcional; "
                   "si no, posicion actual)")
    p.add_argument("--y", type=int, help="coordenada Y de layout (opcional)")
    p.add_argument("--boton", default="left", metavar="BOTON",
                   help="boton del raton: left|right|middle (validado en handler)")
    p.add_argument("--doble", action="store_true", help="doble clic")
    p.set_defaults(func=cmd_click)

    p = sub.add_parser("arrastrar", help="presionar, recorrer la trayectoria "
                       "y soltar")
    p.add_argument("x1", type=int, help="origen X (layout)")
    p.add_argument("y1", type=int, help="origen Y (layout)")
    p.add_argument("x2", type=int, help="destino X (layout)")
    p.add_argument("y2", type=int, help="destino Y (layout)")
    p.add_argument("--duracion", type=float, default=0.5,
                   help="segundos totales del arrastre (default 0.5)")
    p.add_argument("--boton", default="left", metavar="BOTON",
                   help="boton a mantener: left|right|middle (validado en handler)")
    p.set_defaults(func=cmd_arrastrar)

    p = sub.add_parser("scroll", help="rueda vertical (X11; WAYLAND: sin "
                       "ruta, error honesto)")
    grupo = p.add_mutually_exclusive_group()
    grupo.add_argument("--vertical", type=int, metavar="N",
                       help="pasos verticales: +sube, -baja (convencion a "
                       "verificar en tu WM [runtime])")
    grupo.add_argument("--horizontal", type=int, metavar="N",
                       help="pasos horizontales: +derecha, -izquierda")
    p.add_argument("--x", type=int, help="posicionar el cursor antes de rodar")
    p.add_argument("--y", type=int, help="coordenada Y del posicionamiento")
    p.add_argument("--garantizar-direccion", dest="garantizar_direccion",
                   action="store_true",
                   help="P1-4: fuerza xdotool click 4/5 (signos VERIFICADOS "
                        "en man) en lugar de pynput ([runtime] en tu WM)")
    p.set_defaults(func=cmd_scroll)

    p = sub.add_parser("posicion", help="cursor actual (solo X11)")
    p.set_defaults(func=cmd_posicion)

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
