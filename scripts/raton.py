# -*- coding: utf-8 -*-
"""raton.py — Ratón de la skill computer-use-py (PyAutoGUI + pynput).

Division de trabajo (piramide de la skill):
- Mover/clic/arrastrar DENTRO DEL MONITOR PRIMARIO: PyAutoGUI (moveTo con
  tween, click con x,y) — comportamiento historico intacto.
- Mover/clic/arrastrar FUERA del primario (o con cualquier coordenada
  negativa): pynput. Por que: VERIFICADO en el fuente de pyautogui 0.9.54,
  el clamp de _moveTo esta COMENTADO (_pyautogui_win.py via __init__.py:1474)
  y SetCursorPos moveria al secundario... pero sus docstrings, la FAQ oficial
  y onScreen() siguen declarando "solo primario": es conducta NO documentada
  y un upstream puede re-activar el clamp. pynput si lo garantiza
  (_win32.py:72-75: position = SetCursorPos sin clamp sobre la pantalla
  virtual). Regla dura: fuera del primario, SIEMPRE pynput.
- SCROLL (vertical Y horizontal): pynput.mouse.scroll(dx, dy) SIEMPRE.
  Motivo verificado: en Windows pyautogui.hscroll es un alias directo de
  _scroll vertical (`return _scroll(...)` en _pyautogui_win.py) — rueda
  VERTICALMENTE sin avisar; su propio docstring dice "Currently just
  Linux". pynput en cambio integra el eje horizontal en la misma llamada
  y si funciona en Windows. Signos en Windows (ambas librerias coinciden):
  dy > 0 = rueda hacia ARRIBA, dy < 0 = abajo; dx > 0 = DERECHA,
  dx < 0 = izquierda. 1 paso = WHEEL_DELTA (120) de la API Win32.
  pynput no acepta x,y en scroll: primero se posiciona (pyautogui dentro
  del primario, pynput fuera).

Coordenadas: pixeles del ESPACIO VIRTUAL (origen (0,0) = vertice sup-izq del
monitor PRIMARIO; NEGATIVOS validos hacia la izquierda/arriba con monitores
vecinos). Mapa: monitores.py listar. En un equipo de un solo monitor coincide
con el marco historico del primario.

FAILSAFE: las 4 esquinas que abortan son las del monitor PRIMARIO (semantica
pyautogui; la huida humana clasica a (0,0) sigue válida). En un secundario NO
hay esquina failsafe: el freno alli es la tecla de panico de vigilar.py o
Ctrl+C. Las rutas pynput replican el chequeo llamando a
pyautogui.failSafeCheck() antes de actuar y en cada paso interpolado (ojo:
una trayectoria que CRUCE la esquina (0,0) del primario aborta, igual que el
tween de pyautogui). Tras un FAILSAFE la accion pudo quedar PARCIAL (boton
sin soltar, medio arrastre): re-captura antes de reintentar.

Banderas del .tmp (vigilar.py, P1-5/P1-6): ABORT corta al inicio de cada
accion y en cada paso interpolado de mover/arrastrar (el release del boton se
garantiza igual); PAUSA (flag --pausar-si-humano) detiene el ARRANQUE de la
accion hasta que se borre (tope 300 s). Sin banderas, coste minimo: un
os.path.exists.

Salida: JSON por stdout; errores JSON con "error".

Subcomandos:
  mover      Desplaza el cursor (animado dentro del primario; por pynput
             fuera, interpolado si --duracion > 0).
  click      Clic simple, doble o con boton derecho, donde este el cursor
             o en (x, y) virtuales.
  arrastrar  press -> trayectoria interpolada -> release (pynput si el
             camino sale del primario).
  scroll     Rueda vertical u horizontal via pynput.
  posicion   Lectura del cursor en ambos marcos (pyautogui y pynput).

Ejemplos (desde la carpeta computer-use-py):
  py scripts/raton.py mover 640 300 --duracion 0.2
  py scripts/raton.py click --x 640 --y 300 --boton right
  py scripts/raton.py click --x -800 --y 300        # secundario: pynput
  py scripts/raton.py arrastrar 100 100 400 350 --duracion 0.5
  py scripts/raton.py arrastrar -800 400 300 400    # secundario->primario
  py scripts/raton.py scroll --vertical -5 --x 800 --y 400
  py scripts/raton.py scroll --horizontal 3
"""

import argparse
import time

import _compartido as c  # importa pyautogui ya con DPI + FAILSAFE + PAUSE
import pyautogui

_BOTONES = ("left", "right", "middle")


def _guard_destino(x, y):
    """Guard contra el bounding VIRTUAL + eleccion de backend.

    Devuelve "pyautogui" si el destino cae dentro del monitor PRIMARIO
    (comportamiento actual intacto) y "pynput" si cae en otro monitor
    (coordenadas negativas incluidas). Aborta con JSON "error" si el punto
    esta fuera de la pantalla virtual o en un hueco entre monitores.
    """
    if not c.dentro_de_virtual(x, y):
        v = c.tamano_virtual()
        c.fail("Destino (%d, %d) fuera de la pantalla virtual "
               "(x %d..%d, y %d..%d). Mapa: monitores.py listar."
               % (x, y, v["x"], v["x"] + v["ancho"] - 1,
                  v["y"], v["y"] + v["alto"] - 1))
    m = c._monitor_contiene(x, y)
    if m is None:
        c.fail("Destino (%d, %d) no cae dentro de ningun monitor (hueco del "
               "bounding virtual con monitores desalineados)." % (x, y))
    return "pyautogui" if m["primario"] else "pynput"


def _pynput():
    """(Controller, Button) de pynput, con import perezoso (solo fuera del
    primario: la ruta historica pyautogui no lo toca)."""
    from pynput.mouse import Button, Controller as ControladorRaton

    return ControladorRaton(), Button


def _pynput_mover(x, y, duracion):
    """Movimiento fuera del primario por pynput (SetCursorPos sin clamp:
    unica ruta DOCUMENTADA-GARANTIZADA al espacio virtual). Con duracion>0
    interpola por pasos con failSafeCheck en cada paso (el freno humano de
    las esquinas del primario sigue vigente) y checar_abort por paso (P1-6:
    ABORT corta el interpolado; sin bandera, solo un os.path.exists)."""
    m, _ = _pynput()
    pyautogui.failSafeCheck()
    if duracion and duracion > 0:
        x0, y0 = m.position
        pasos = min(max(int(duracion / 0.01), 2), 200)
        for i in range(1, pasos + 1):
            m.position = (int(x0 + (x - x0) * i / pasos),
                          int(y0 + (y - y0) * i / pasos))
            time.sleep(duracion / pasos)
            pyautogui.failSafeCheck()
            c.checar_abort("mover interpolado")
    else:
        m.position = (int(x), int(y))


def _monitor_de(x, y):
    """Sub-objeto monitor canonico {indice,nombre,primario} del punto dado,
    o None si cae en hueco/ fuera (P1-3)."""
    m = c._monitor_contiene(x, y)
    if m is None:
        return None
    return {"indice": m["indice"], "nombre": m["nombre"], "primario": m["primario"]}


def cmd_mover(args):
    c.checar_abort("mover")      # bandera ABORT = no emitir nada (P1-6)
    c.checar_pausa()             # P1-5: freno suave antes de emitir
    backend = _guard_destino(args.x, args.y)
    ax, ay = c.posicion_cursor()
    if backend == "pyautogui":
        pyautogui.moveTo(args.x, args.y, duration=args.duracion)
    else:
        _pynput_mover(args.x, args.y, args.duracion)
    nx, ny = c.posicion_cursor()
    c.json_out({"ok": True, "via": backend, "desde": [ax, ay], "hasta": [nx, ny],
                "marco": c.MARCO, "monitor": _monitor_de(args.x, args.y)})


def cmd_click(args):
    c.checar_abort("click")
    c.checar_pausa()
    if (args.x is None) != (args.y is None):
        c.fail("Debe indicar --x e --y juntos, o ninguno (clic en la posicion actual).")
    if args.boton not in _BOTONES:
        c.fail("Boton %r invalido para la rama Windows." % args.boton,
               validos=list(_BOTONES))
    backend = _guard_destino(args.x, args.y) if args.x is not None else None
    if backend == "pynput":
        # Doble clic y boton derecho fuera del primario: tambien pynput
        # (click(button, count) emite en la POSICION actual del cursor:
        # primero position=(x,y), igual que press/release).
        m, Button = _pynput()
        pyautogui.failSafeCheck()
        m.position = (int(args.x), int(args.y))
        m.click(getattr(Button, args.boton), 2 if args.doble else 1)
    else:
        # Dentro del primario (o sin coords, donde este el cursor): ruta
        # historica intacta. Nota: sin --x/--y el clic ocurre donde el humano
        # dejo el cursor, aunque ese punto este fisicamente en el secundario.
        pyautogui.click(x=args.x, y=args.y, button=args.boton,
                        clicks=2 if args.doble else 1, interval=0.08)
    x, y = c.posicion_cursor()
    c.json_out({
        "ok": True,
        "via": backend or "pyautogui (posicion actual)",
        "boton": args.boton,
        "doble": bool(args.doble),
        "cursor": [x, y],
        "marco": c.MARCO,
        "monitor": _monitor_de(x, y),
        "aviso": "el exito de un clic NO se reporta: en apps elevadas "
                 "pyautogui captura PermissionError en silencio y el clic no "
                 "ocurre. Verifica SIEMPRE con pantalla.py capturar.",
    })


def cmd_arrastrar(args):
    c.checar_abort("arrastrar")
    c.checar_pausa()
    if args.boton not in _BOTONES:
        c.fail("Boton %r invalido para la rama Windows." % args.boton,
               validos=list(_BOTONES))
    r1 = _guard_destino(args.x1, args.y1)
    r2 = _guard_destino(args.x2, args.y2)
    duracion = min(max(args.duracion, 0.1), 30.0)
    # Trayectoria interpolada a mano (press -> movimientos con sueno ->
    # release): pynput no trae drag y pyautogui.dragTo no deja controlar el
    # ritmo de los pasos intermedios.
    pasos = max(10, int(duracion / 0.01))
    pasos = min(pasos, 200)
    retardo = duracion / pasos
    if r1 == "pyautogui" and r2 == "pyautogui":
        pyautogui.moveTo(args.x1, args.y1)
        pyautogui.mouseDown(button=args.boton)
        try:
            for i in range(1, pasos + 1):
                nx = args.x1 + (args.x2 - args.x1) * i / pasos
                ny = args.y1 + (args.y2 - args.y1) * i / pasos
                pyautogui.moveTo(nx, ny)
                time.sleep(retardo)
                # P1-6: ABORT a medio arrastre corta (el finally suelta SIEMPRE).
                c.checar_abort("arrastrar")
        finally:
            # Soltar SIEMPRE, incluso si el FAILSAFE interrumpio la trayectoria.
            pyautogui.mouseUp(button=args.boton)
        via = "pyautogui (origen y destino en el primario)"
    else:
        m, Button = _pynput()
        pyautogui.failSafeCheck()
        boton = getattr(Button, args.boton)
        m.position = (int(args.x1), int(args.y1))
        m.press(boton)
        try:
            for i in range(1, pasos + 1):
                m.position = (int(args.x1 + (args.x2 - args.x1) * i / pasos),
                              int(args.y1 + (args.y2 - args.y1) * i / pasos))
                time.sleep(retardo)
                pyautogui.failSafeCheck()
                c.checar_abort("arrastrar")
        finally:
            m.release(boton)  # soltar SIEMPRE (aunque el FAILSAFE haya cortado)
        via = "pynput (el camino toca un monitor no primario)"
    x, y = c.posicion_cursor()
    c.json_out({
        "ok": True,
        "via": via,
        "desde": [args.x1, args.y1],
        "hasta": [x, y],
        "boton": args.boton,
        "pasos": pasos,
        "marco": c.MARCO,
        "monitor": _monitor_de(x, y),
        "aviso": "verifica el resultado con pantalla.py capturar",
    })


def cmd_scroll(args):
    c.checar_abort("scroll")
    c.checar_pausa()
    if args.vertical is None and args.horizontal is None:
        c.fail("Indica --vertical N u horizontal N (excluyentes).")
    if (args.x is None) != (args.y is None):
        c.fail("Debe indicar --x e --y juntos, o ninguno.")
    via_posicion = None
    if args.x is not None:
        # pynput.scroll no acepta x,y: posicionamos primero (pyautogui dentro
        # del primario como siempre; pynput fuera — coords negativas).
        via_posicion = _guard_destino(args.x, args.y)
        if via_posicion == "pyautogui":
            pyautogui.moveTo(args.x, args.y)
        else:
            m, _ = _pynput()
            pyautogui.failSafeCheck()
            m.position = (int(args.x), int(args.y))
    from pynput.mouse import Controller as ControladorRaton

    dx = 0 if args.vertical is not None else int(args.horizontal)
    dy = int(args.vertical) if args.vertical is not None else 0
    ControladorRaton().scroll(dx, dy)
    c.json_out({
        "ok": True,
        "eje": "vertical" if args.vertical is not None else "horizontal",
        "pasos": abs(dx) if dx else abs(dy),
        "sentido": ("arriba" if dy > 0 else "abajo") if args.vertical is not None
                   else ("derecha" if dx > 0 else "izquierda"),
        "posicion_via": via_posicion or "cursor-actual",
        "nota": "signos Windows: dy>0=sube (igual que pyautogui), dx>0=derecha; "
                "1 paso = 120 (WHEEL_DELTA); escala final la decide cada app",
    })


def cmd_posicion(args):
    px, py = c.posicion_cursor()
    from pynput.mouse import Controller as ControladorRaton

    vx, vy = ControladorRaton().position
    # P1-1 (CRITICO, spec): forma canonica plana x/y/marco/via/por_backend{},
    # identica en las 3 ramas; las lecturas por backend se mudan a por_backend.
    c.json_out({
        "ok": True,
        "x": int(vx), "y": int(vy),
        "marco": c.MARCO,
        "via": "pynput",
        "monitor": _monitor_de(vx, vy),
        "por_backend": {
            "pyautogui": {"x": int(px), "y": int(py)},
            "pynput": {"x": int(vx), "y": int(vy)},
        },
        "nota": "ambas lecturas son GetCursorPos: mismo marco virtual (0,0 = "
                "vertice del primario; negativos con monitores a la "
                "izquierda/arriba); 'monitor' = quien contiene el cursor; "
                "x/y canonicos = lectura pynput (marco virtual completo)",
    })


def construir_parser():
    parser = c.Parser(
        prog="raton.py",
        description="Raton para automatizacion de escritorio: mover, clic, "
                    "arrastrar y scroll (vertical y horizontal via pynput). "
                    "Coordenadas = espacio VIRTUAL (negativas validas; fuera "
                    "del primario el input va por pynput).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1] if __doc__ and "Subcomandos:" in __doc__ else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    p = sub.add_parser("mover", help="desplazar el cursor")
    p.add_argument("x", type=int, help="destino X (pixel virtual; negativo = monitor a la izquierda)")
    p.add_argument("y", type=int, help="destino Y (pixel virtual)")
    p.add_argument("--duracion", type=float, default=0.2,
                   help="segundos del desplazamiento animado (0 = instantaneo)")
    p.set_defaults(func=cmd_mover)

    p = sub.add_parser("click", help="clic simple/derecho/doble")
    p.add_argument("--x", type=int, help="coordenada X virtual (opcional; si no, posicion actual)")
    p.add_argument("--y", type=int, help="coordenada Y virtual (opcional)")
    p.add_argument("--boton", default="left", metavar="BOTON",
                   help="boton del raton: left|right|middle (por defecto left); "
                        "invalido => error JSON")
    p.add_argument("--doble", action="store_true", help="doble clic")
    p.set_defaults(func=cmd_click)

    p = sub.add_parser("arrastrar", help="presionar, recorrer la trayectoria y soltar")
    p.add_argument("x1", type=int, help="origen X (virtual)")
    p.add_argument("y1", type=int, help="origen Y (virtual)")
    p.add_argument("x2", type=int, help="destino X (virtual)")
    p.add_argument("y2", type=int, help="destino Y (virtual)")
    p.add_argument("--duracion", type=float, default=0.5,
                   help="segundos totales del arrastre (por defecto 0.5)")
    p.add_argument("--boton", default="left", metavar="BOTON",
                   help="boton a mantener: left|right|middle (validado en handler)")
    p.set_defaults(func=cmd_arrastrar)

    p = sub.add_parser("scroll", help="rueda vertical u horizontal (pynput; "
                       "pyautogui.hscroll NO rueda en horizontal en Windows)")
    grupo = p.add_mutually_exclusive_group()
    grupo.add_argument("--vertical", type=int, metavar="N",
                       help="pasos verticales: +sube, -baja (igual que pyautogui)")
    grupo.add_argument("--horizontal", type=int, metavar="N",
                       help="pasos horizontales: +derecha, -izquierda")
    p.add_argument("--x", type=int, help="posicionar el cursor antes de rodar (coordenada virtual)")
    p.add_argument("--y", type=int, help="coordenada Y del posicionamiento")
    p.set_defaults(func=cmd_scroll)

    p = sub.add_parser("posicion", help="cursor segun ambos marcos (pyautogui y pynput)")
    p.set_defaults(func=cmd_posicion)

    return parser


def main():
    args = construir_parser().parse_args()
    try:
        args.func(args)
    except pyautogui.FailSafeException as exc:
        c.fallar_por_failsafe(exc)
    except SystemExit:
        raise
    except ValueError as exc:
        # pynput move/scroll pueden lanzar ValueError; convertirlo a JSON.
        c.fail("pynput rechazo el movimiento/scroll: %s" % exc)
    except Exception as exc:
        c.fail("%s: %s" % (type(exc).__name__, exc))


if __name__ == "__main__":
    main()
