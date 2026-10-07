# -*- coding: utf-8 -*-
"""raton.py — Ratón de la skill computer-use-py (PyAutoGUI + pynput).

ENTRADA MULTI-OS (FASE SEG3): `python scripts/raton.py ...` vale en los 3 SO —
en Windows ejecuta esta ruta nativa (validada en escritorio real); en
Linux/macOS ejecuta EN EL PROPIO PROCESO la ruta de su SO (las primitivas
exclusivas viven en scripts/linux/linux_especiales.py y
scripts/macos/macos_especiales.py; el dispatch es por sys.platform en main());
plataforma desconocida responde JSON + rc 2.

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
  py scripts/raton.py mover 640 300 --duracion 0.2    # Windows (python3 en otros SO)
  py scripts/raton.py click --x 640 --y 300 --boton right
  py scripts/raton.py click --x -800 --y 300          # secundario: pynput
  py scripts/raton.py arrastrar 100 100 400 350 --duracion 0.4
  py scripts/raton.py arrastrar -800 400 300 400      # secundario->primario
  py scripts/raton.py scroll --vertical -5 --x 800 --y 400
  py scripts/raton.py scroll --horizontal 3
"""

import argparse
import os
import shutil
import subprocess
import sys
import time

_DIR_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _DIR_SCRIPTS not in sys.path:
    sys.path.insert(0, _DIR_SCRIPTS)
import _core


# ===========================================================================
# SECCION WINDOWS — cmd_*/helpers/parser VERBATIM del CLI raiz historico.
# `c` (glue_windows) y `pyautogui` se bind-eaban en el top; en SEG3 se bind-ean
# en main() ANTES de parsear = mismo comportamiento. _BOTONES era
# `_BOTONES = c.BOTONES` en el top actual: como el alias c solo existe tras
# main(), la asignacion se movio a la rama win de main() con `global`
# (desviacion obligada, documentada; el placeholder de abajo no se usa en
# linux/mac, cuyas secciones llaman c.BOTONES directamente).
# ===========================================================================

_BOTONES = ()  # reasignado a c.BOTONES en la rama win de main()


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
    duracion = c.cap_duracion(args.duracion)
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
    # TIEMPOS-K: arrastre 0.5->0.4 s (-20%, piso 250 ok): duracion default del
    # interpolado press->mover->release; el retardo por paso se deriva de esta
    # cifra (duracion/pasos), no es constante propia. Verificado en sandbox W11.
    p.add_argument("--duracion", type=float, default=0.4,
                   help="segundos totales del arrastre (por defecto 0.4)")
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


# ===========================================================================
# SECCION LINUX — cmd_*/helpers de scripts/linux/raton.py (FASE SEG3) con
# sufijo _linux. BAJARON a scripts/linux/linux_especiales.py y se llaman via
# c.<nombre>(): _pyautogui, _ydotool, _CLICK_YDOTOOL, _DOWN_YDOTOOL,
# _UP_YDOTOOL, _AVISO_WAYLAND, _cursor. NO bajaron (orquestacion + JSON):
# _guard_destino_linux, _monitor_dict_linux y los cmd_* (aceptaban c.BOTONES
# por alias de rama; aqui se usa c.BOTONES directo — sin constante local).
# ===========================================================================

_DOC_LINUX = """raton.py — Raton del dominio LINUX (skill computer-use-py).

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
  python3 scripts/raton.py mover 640 300 --duracion 0.2
  python3 scripts/raton.py click --x 640 --y 300 --boton right
  python3 scripts/raton.py arrastrar 100 100 400 350 --duracion 0.4
  python3 scripts/raton.py scroll --vertical -5 --x 800 --y 400
  python3 scripts/raton.py posicion
"""


# _BOTONES = c.BOTONES: contrato JSON generico de la skill (vive en _core);
# la seccion lo usa via c.BOTONES (no hay constante de seccion).
# _CLICK_YDOTOOL/_DOWN_YDOTOOL/_UP_YDOTOOL/_AVISO_WAYLAND: BAJARON a la
# libreria (man ydotool) => c.<nombre>.


def _monitor_dict_linux(m):
    """Sub-objeto monitor canonico con 'primario' SIEMPRE (P1-3)."""
    if m is None:
        return None
    return {"indice": m["indice"], "nombre": m["nombre"],
            "primario": m["primario"]}


# _ydotool y _cursor BAJARON a linux_especiales => c._ydotool(...) / c._cursor().


def _guard_destino_linux(x, y):
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


def cmd_mover_linux(args):
    c.checar_abort("mover")   # P1-6: bandera dura (Wayland sin FAILSAFE: es el freno)
    c.checar_pausa()          # P1-5
    m = _guard_destino_linux(args.x, args.y)
    sesion = c.deteccion_sesion()
    ax, ay = c._cursor() or (None, None)
    if sesion == "x11":
        pa = c._pyautogui()
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
        c._ydotool(["mousemove", "--absolute", args.x, args.y])
        via = ("ydotool mousemove --absolute (relativo por defecto segun man; "
               "--duracion ignorada: sin lectura de cursor no hay "
               "interpolacion [runtime])")
    else:
        c.fail("Sesion grafica sin detectar: sin ruta de raton. refs "
               "linux-python.md §2/§13.", sesion=sesion)
    nx, ny = c._cursor() or (args.x, args.y)
    c.json_out({
        "ok": True,
        "via": via,
        "sesion": sesion,
        "marco": c.MARCO,
        "desde": None if ax is None else [ax, ay],
        "hasta": [nx, ny],
        "monitor": _monitor_dict_linux(m),
        "aviso": c._AVISO_WAYLAND if sesion == "wayland" else
                 "en X11 el punto puede quedar en un hueco entre monitores "
                 "(zona viva del screen): no es un fallo, es escritorio",
    })


def cmd_click_linux(args):
    c.checar_abort("click")
    c.checar_pausa()
    if args.boton not in c.BOTONES:
        c.fail("Boton %r invalido para la rama Linux." % args.boton,
               validos=list(c.BOTONES))
    if (args.x is None) != (args.y is None):
        c.fail("Debe indicar --x e --y juntos, o ninguno (clic en la "
               "posicion actual).")
    sesion = c.deteccion_sesion()
    m = None
    if args.x is not None:
        m = _guard_destino_linux(args.x, args.y)
    if sesion == "x11":
        pa = c._pyautogui()
        pa.click(x=args.x, y=args.y, button=args.boton,
                 clicks=2 if args.doble else 1, interval=0.08)
        via = "pyautogui.click (X11; FAILSAFE activo)"
    elif sesion == "wayland":
        if args.x is not None:
            c._ydotool(["mousemove", "--absolute", args.x, args.y], timeout=10.0)
        argv = ["click"]
        if args.doble:
            argv += ["--repeat", "2"]
        argv.append(c._CLICK_YDOTOOL[args.boton])
        c._ydotool(argv)
        via = ("ydotool click %s (%s) [runtime 0xC1/0xC2]"
               % (c._CLICK_YDOTOOL[args.boton], args.boton))
    else:
        c.fail("Sesion grafica sin detectar: sin ruta de click. refs "
               "linux-python.md §2/§13.", sesion=sesion)
    cur = c._cursor()
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
        "monitor": _monitor_dict_linux(m),
        "aviso": ("el exito de un clic NO se reporta (la app decide si lo "
                  "consume): verifica SIEMPRE con pantalla.py capturar. "
                  + (c._AVISO_WAYLAND if sesion == "wayland" else "")),
    })


def cmd_arrastrar_linux(args):
    c.checar_abort("arrastrar")
    c.checar_pausa()
    if args.boton not in c.BOTONES:
        c.fail("Boton %r invalido para la rama Linux." % args.boton,
               validos=list(c.BOTONES))
    m1 = _guard_destino_linux(args.x1, args.y1)
    m2 = _guard_destino_linux(args.x2, args.y2)
    sesion = c.deteccion_sesion()
    duracion = c.cap_duracion(args.duracion)
    if sesion == "x11":
        pa = c._pyautogui()
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
        c._ydotool(["mousemove", "--absolute", args.x1, args.y1], timeout=10.0)
        c._ydotool(["click", c._DOWN_YDOTOOL[args.boton]], timeout=10.0)
        try:
            for i in range(1, pasos + 1):
                # ABORT entre pasos: sin FAILSAFE en Wayland, es el freno duro;
                # el finally suelta el boton igualmente (no deja clic colgado).
                c.checar_abort("arrastrar")
                nx = int(args.x1 + (args.x2 - args.x1) * i / pasos)
                ny = int(args.y1 + (args.y2 - args.y1) * i / pasos)
                c._ydotool(["mousemove", "--absolute", nx, ny], timeout=10.0)
                time.sleep(retardo)
        finally:
            c._ydotool(["click", c._UP_YDOTOOL[args.boton]], timeout=10.0)
        via = ("ydotool mousemove --absolute + click %s/%s [regla de "
               "mascara del man; 0x41/0x82 verbatim]"
               % (c._DOWN_YDOTOOL[args.boton], c._UP_YDOTOOL[args.boton]))
    else:
        c.fail("Sesion grafica sin detectar: sin ruta de arrastre. refs "
               "linux-python.md §2/§13.", sesion=sesion)
    cur = c._cursor()
    c.json_out({
        "ok": True,
        "via": via,
        "sesion": sesion,
        "marco": c.MARCO,
        "desde": [args.x1, args.y1],
        "hasta": [cur[0], cur[1]] if cur else [args.x2, args.y2],
        "boton": args.boton,
        "monitor": _monitor_dict_linux(m2),
        "aviso": ("verifica el resultado con pantalla.py capturar. "
                  + (c._AVISO_WAYLAND if sesion == "wayland" else
                     "tras un FAILSAFE a media trayectoria el boton ya fue "
                     "soltado (finally); re-captura antes de reintentar")),
    })


def cmd_scroll_linux(args):
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
        _guard_destino_linux(args.x, args.y)
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
    pa = c._pyautogui()
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


def cmd_posicion_linux(args):
    if c.deteccion_sesion() != "x11":
        c.fail("posicion del cursor no legible en Wayland con las tools "
               "auditadas (ydotool es solo-escritura; refs linux-python.md "
               "§11): usa capturar + vision.", sesion=c.deteccion_sesion())
    cur = c._cursor()
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
        "monitor": _monitor_dict_linux(m),
        "por_backend": por_backend,
        "sesion": "x11",
        "nota": nota,
    })


def construir_parser_linux():
    parser = c.Parser(
        prog="raton.py (linux)",
        description="Raton Linux: X11 via pyautogui/pynput/xdotool y Wayland "
                    "via ydotool (mousemove --absolute, click con mascaras). "
                    "Coordenadas = LAYOUT (monitores.py listar).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_DOC_LINUX.split("Subcomandos:")[1] if _DOC_LINUX and "Subcomandos:" in _DOC_LINUX else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    p = sub.add_parser("mover", help="desplazar el cursor")
    p.add_argument("x", type=int, help="destino X (pixel de layout)")
    p.add_argument("y", type=int, help="destino Y (pixel de layout)")
    p.add_argument("--duracion", type=float, default=0.2,
                   help="segundos del desplazamiento animado (0 = instantaneo)")
    p.set_defaults(func=cmd_mover_linux)

    p = sub.add_parser("click", help="clic simple/derecho/doble")
    p.add_argument("--x", type=int, help="coordenada X de layout (opcional; "
                   "si no, posicion actual)")
    p.add_argument("--y", type=int, help="coordenada Y de layout (opcional)")
    p.add_argument("--boton", default="left", metavar="BOTON",
                   help="boton del raton: left|right|middle (validado en handler)")
    p.add_argument("--doble", action="store_true", help="doble clic")
    p.set_defaults(func=cmd_click_linux)

    p = sub.add_parser("arrastrar", help="presionar, recorrer la trayectoria "
                       "y soltar")
    p.add_argument("x1", type=int, help="origen X (layout)")
    p.add_argument("y1", type=int, help="origen Y (layout)")
    p.add_argument("x2", type=int, help="destino X (layout)")
    p.add_argument("y2", type=int, help="destino Y (layout)")
    # TIEMPOS-K: arrastre 0.5->0.4 s (espejo de la rama Windows, -20%, piso ok).
    p.add_argument("--duracion", type=float, default=0.4,
                   help="segundos totales del arrastre (default 0.4)")
    p.add_argument("--boton", default="left", metavar="BOTON",
                   help="boton a mantener: left|right|middle (validado en handler)")
    p.set_defaults(func=cmd_arrastrar_linux)

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
    p.set_defaults(func=cmd_scroll_linux)

    p = sub.add_parser("posicion", help="cursor actual (solo X11)")
    p.set_defaults(func=cmd_posicion_linux)

    return parser


# ===========================================================================
# SECCION macOS — cmd_*/helpers de scripts/macos/raton.py (FASE SEG3) con
# sufijo _mac. BAJARON a scripts/macos/macos_especiales.py y se llaman via
# c.<nombre>(): _q_move, _q_button_events, _q_click, _cliclick. NO bajaron
# (copiados aqui): _guard_destino_mac, _pynput_mouse_mac, _raton_ruta_mac,
# _aviso_guard_mac, _monitor_dict_mac y los cmd_* — todos con sufijo por
# posible colision — y _DARWIN_CATCH_UP pelado (no colisiona con ninguna
# otra seccion; lista explicita de la tarea SEG3). pynput/Quartz van lazy
# via c.try_quartz/_pynput_mouse_mac.
# _BOTONES se resuelve via c.BOTONES (la rama ya la tenia como alias de _core).
# ===========================================================================

_DOC_MAC = """raton.py — Raton en macOS (skill computer-use-py, dominio mac).

Piramide (todo corre sobre Python):
- pynput 1.8.2 (PRIMARIA): `Controller.position` emite
  CGEventCreateMouseEvent(kCGEventMouseMoved) + CGEventPost — coords
  ABSOLUTAS en puntos del espacio global [VERIFICADO fuente
  mouse/_darwin.py:78-88]. Durante un arrastre (con boton presionado) el
  MISMO setter cambia al tipo `...MouseDragged` del boton (fuente:80-83):
  press→position→position→release es el patron de arrastre nativo.
  Doble clic VERIFICADO docs mouse.html: "Double click; this is different
  from pressing and releasing twice on macOS — mouse.click(Button.left, 2)":
  click() envuelve en `with self` (fuente _base.py:112-125) que incrementa
  kCGMouseEventClickState (fuente _darwin.py:105-133). Botones en darwin:
  SOLO left/middle/right (fuente:55-61 — no existen x1/x2).
- pyobjc-framework-Quartz (RESPALDO): las mismas CGEvent a mano
  [runtime: replicar el patron del fuente de pynput].
- cliclick [3p]: solo como ULTIMA ruta si no hay ni pynput ni pyobjc y el
  binario esta en PATH (detectado, no auditado — ver
  references/comandos-sistema.md §H). Nunca se prefiere sobre Python.
- Sin ninguna: error JSON con hint pip de ambas rutas.

Scroll: pynput `scroll(dx, dy)` → CGEventCreateScrollWheelEvent
(kCGScrollEventUnitPixel, dy*10, dx*10) [VERIFICADO fuente:94-103].
Convencion de la skill: dy>0=sube, dx>0=derecha (igual que Windows;
convergen dos lecturas de fuente: listener docs dy<0=down y mapeo
positivo->+ de _pyautogui_osx.py). El "scroll natural" de macOS puede
invertir la percepcion por app [runtime: verificar en la maquina].

FAILSAFE: no existe la API de pyautogui en mac. La skill EMULA el freno
[runtime]: guarda de las 4 esquinas del display PRINCIPAL antes de cada
accion y en los pasos interpolados (fail_safe_check), y el freno humano
real es la bandera .tmp/ABORT que crea vigilar.py (listener ESC). Tras un
abort la accion pudo quedar PARCIAL (boton sin soltar): re-captura.

Coordenadas: PUNTOS LOGICOS del espacio global (0,0 = sup-izq del display
principal; negativos validos segun arrangement [runtime]). Mapa:
monitores.py listar.

Salida: JSON por stdout; errores JSON con "error".

Subcomandos:
  mover      Desplaza el cursor (interpola si --duracion > 0).
  click      Clic simple, doble o con boton derecho, donde este el cursor
             o en (x, y).
  arrastrar  press -> trayectoria -> release (siempre suelta).
  scroll     Rueda vertical u horizontal.
  posicion   Cursor en los dos marcos Python disponibles (quartz/pynput).

Ejemplos (desde la carpeta computer-use-py, en el Mac):
  python3 scripts/raton.py mover 640 300 --duracion 0.2
  python3 scripts/raton.py click --x 640 --y 300 --boton right
  python3 scripts/raton.py click --x 2000 --y 300 --doble
  python3 scripts/raton.py arrastrar 100 100 400 350 --duracion 0.4
  python3 scripts/raton.py scroll --vertical -5 --x 800 --y 400
  python3 scripts/raton.py scroll --horizontal 3
"""

# Botones: darwin NO define x1/x2 (VERIFICADO fuente mouse/_darwin.py:55-61);
# el set canonico vive en _core y se usa via c.BOTONES.
_DARWIN_CATCH_UP = 0.01  # pausa post-evento: VERIFICADO pyautogui 0.9.54
                             # __init__.py:567 DARWIN_CATCH_UP_TIME = 0.01


def _guard_destino_mac(x, y):
    """Guard contra el bounding VIRTUAL en puntos logicos.

    Aborta con JSON "error" si el punto esta fuera del bounding o en un
    hueco entre monitores (misma semantica que el guard padre de Windows).
    SIN pyobjc no existe mapa de rects: el guard se omite (devuelve None) y
    el JSON lo avisa — pynput sigue pudiendo operar con las coordenadas.
    """
    if not c.quartz_disponible():
        return None
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
    return m


def _pynput_mouse_mac():
    """(Controller, Button) de pynput o None si no esta instalado."""
    try:
        from pynput.mouse import Button, Controller as ControladorRaton
        return ControladorRaton(), Button
    except ImportError:
        return None


def _raton_ruta_mac():
    """('pynput'|'quartz'|'cliclick'|None, handle)."""
    par = _pynput_mouse_mac()
    if par is not None:
        return "pynput", par
    if c.quartz_disponible():
        return "quartz", None
    if shutil.which("cliclick"):
        return "cliclick", None
    return None, None


# --- primitives Quartz manuales (respaldo): BAJARON a macos_especiales
# (_q_move, _q_button_events, _q_click, _cliclick) => se llaman c.<nombre>().


# --- subcomandos ----------------------------------------------------------

def _aviso_guard_mac():
    """Nota cuando el guard de bounding se omitio por no haber mapa."""
    if not c.quartz_disponible():
        return ("sin pyobjc-framework-Quartz: el destino NO se valido contra "
                "el bounding de monitores; un valor fuera de pantalla no se "
                "detecta aqui (pynput/CGEvent lo aceptan e ignoran)")
    return None


def _monitor_dict_mac(x, y):
    """Sub-objeto monitor canonico {indice,nombre,primario} del punto dado,
    o None sin mapa/punto en hueco (P1-3)."""
    if not c.quartz_disponible():
        return None
    m = c._monitor_contiene(x, y)
    if m is None:
        return None
    return {"indice": m["indice"], "nombre": m["nombre"],
            "primario": m["primario"]}


def cmd_mover_mac(args):
    c.checar_abort()
    c.checar_pausa()  # P1-5: freno suave antes de emitir
    _guard_destino_mac(args.x, args.y)
    c.fail_safe_check()
    ruta, par = _raton_ruta_mac()
    if ruta is None:
        c.fail("Sin pynput, ni pyobjc, ni cliclick: no se puede mover el "
               "cursor. pip3 install pynput==1.8.2 (o "
               "pyobjc-framework-Quartz).")
    if ruta == "cliclick":
        c.fail("cliclick [3p] no cubre 'mover' de forma fiable en esta "
               "skill: instala pynput==1.8.2 o pyobjc-framework-Quartz.")
    ax, ay = c.posicion_cursor()
    if ruta == "pynput":
        m, _Button = par
        if args.duracion and args.duracion > 0:
            x0, y0 = m.position
            pasos = min(max(int(args.duracion / 0.01), 2), 200)
            for i in range(1, pasos + 1):
                m.position = (int(x0 + (args.x - x0) * i / pasos),
                              int(y0 + (args.y - y0) * i / pasos))
                time.sleep(args.duracion / pasos)
                c.checar_abort()
                c.fail_safe_check()
        else:
            m.position = (int(args.x), int(args.y))
    else:
        Q = c.try_quartz()
        pasos = min(max(int((args.duracion or 0) / 0.01), 1), 200)
        x0, y0 = c.posicion_cursor()
        for i in range(1, pasos + 1):
            nx = x0 + (args.x - x0) * i / pasos
            ny = y0 + (args.y - y0) * i / pasos
            c._q_move(Q, int(nx), int(ny))
            time.sleep(_DARWIN_CATCH_UP)
    nx_, ny_ = c.posicion_cursor()
    item = {"ok": True, "via": ruta,
            "marco": c.MARCO,
            "unidad": "puntos logicos",
            "monitor": _monitor_dict_mac(args.x, args.y),
            "desde": [ax, ay], "hasta": [nx_, ny_]}
    ag = _aviso_guard_mac()
    if ag:
        item["aviso_guard"] = ag
    c.json_out(item)


def cmd_click_mac(args):
    c.checar_abort()
    c.checar_pausa()
    if (args.x is None) != (args.y is None):
        c.fail("Debe indicar --x e --y juntos, o ninguno (clic en la "
               "posicion actual).")
    if args.boton not in c.BOTONES:
        c.fail("Boton %r invalido para la rama macOS (darwin no define "
               "x1/x2)." % args.boton, validos=list(c.BOTONES))
    if args.x is not None:
        _guard_destino_mac(args.x, args.y)
    c.fail_safe_check()
    x, y = c.posicion_cursor() if args.x is None else (args.x, args.y)
    ruta, par = _raton_ruta_mac()
    if ruta == "pynput":
        m, Button = par
        # click NO acepta x,y (docs): se posiciona primero — en darwin el
        # press usa la POSICION actual leida (fuente: self.position).
        if args.x is not None:
            m.position = (int(x), int(y))
        m.click(getattr(Button, args.boton), 2 if args.doble else 1)
        via = "pynput click(Button.%s, %d)" % (
            args.boton, 2 if args.doble else 1)
    elif ruta == "quartz":
        Q = c.try_quartz()
        if args.x is not None:
            c._q_move(Q, int(x), int(y))
            time.sleep(_DARWIN_CATCH_UP)
        c._q_click(Q, int(x), int(y), args.boton, args.doble)
        via = "pyobjc CGEventCreateMouseEvent+Post (clickState %d) [runtime]" % (
            2 if args.doble else 1)
    elif ruta == "cliclick":
        c._cliclick(int(x), int(y), args.boton, args.doble)
        via = "cliclick [3p] (ultima ruta: sin pynput ni pyobjc)"
    else:
        c.fail("Sin pynput NI pyobjc-framework-Quartz NI cliclick en PATH: "
               "no se puede clicar. pip3 install pynput==1.8.2 o "
               "pyobjc-framework-Quartz.")
    fx, fy = c.posicion_cursor()
    item = {
        "ok": True,
        "via": via,
        "boton": args.boton,
        "doble": bool(args.doble),
        "cursor": [fx, fy],
        "marco": c.MARCO,
        "unidad": "puntos logicos",
        "monitor": _monitor_dict_mac(x, y),
        "aviso": "el exito de un clic NO se reporta: sin TCC Accesibilidad "
                 "el evento puede no llegar [runtime]. Verifica SIEMPRE con "
                 "pantalla.py capturar.",
    }
    ag = _aviso_guard_mac()
    if ag:
        item["aviso_guard"] = ag
    c.json_out(item)


def cmd_arrastrar_mac(args):
    c.checar_abort()
    c.checar_pausa()
    if args.boton not in c.BOTONES:
        c.fail("Boton %r invalido para la rama macOS." % args.boton,
               validos=list(c.BOTONES))
    _guard_destino_mac(args.x1, args.y1)
    _guard_destino_mac(args.x2, args.y2)
    duracion = c.cap_duracion(args.duracion)
    pasos = min(max(int(duracion / 0.01), 10), 200)
    retardo = duracion / pasos
    c.fail_safe_check()
    ruta, par = _raton_ruta_mac()
    if ruta == "pynput":
        m, Button = par
        boton = getattr(Button, args.boton)
        m.position = (int(args.x1), int(args.y1))
        m.press(boton)
        try:
            for i in range(1, pasos + 1):
                # durante el press el setter emite MouseDragged (VERIFICADO
                # fuente _darwin.py:78-88): la trayectoria es un drag real.
                m.position = (int(args.x1 + (args.x2 - args.x1) * i / pasos),
                              int(args.y1 + (args.y2 - args.y1) * i / pasos))
                time.sleep(retardo)
                c.checar_abort()
                c.fail_safe_check()
        finally:
            m.release(boton)  # soltar SIEMPRE (aunque se cortara arriba)
        via = "pynput press→position(Dragged)→release"
    elif ruta == "quartz":
        Q = c.try_quartz()
        down, up, dragged, btn_id = c._q_button_events(Q, args.boton)
        ev = Q.CGEventCreateMouseEvent(None, down, (args.x1, args.y1), btn_id)
        Q.CGEventPost(Q.kCGHIDEventTap, ev)
        time.sleep(_DARWIN_CATCH_UP)
        try:
            for i in range(1, pasos + 1):
                nx = int(args.x1 + (args.x2 - args.x1) * i / pasos)
                ny = int(args.y1 + (args.y2 - args.y1) * i / pasos)
                ev = Q.CGEventCreateMouseEvent(None, dragged, (nx, ny), btn_id)
                Q.CGEventPost(Q.kCGHIDEventTap, ev)
                time.sleep(retardo)
                c.checar_abort()
        finally:
            ev = Q.CGEventCreateMouseEvent(None, up, (args.x2, args.y2), btn_id)
            Q.CGEventPost(Q.kCGHIDEventTap, ev)
        via = "pyobjc MouseDown→MouseDragged→MouseUp (patron leido de " \
              "_pyautogui_osx.py:435-444 [runtime]"
    elif ruta == "cliclick":
        if args.boton != "left":
            c.fail("cliclick [3p]: sin sintaxis verificada para arrastrar "
                   "con boton derecho/central. Instala pynput o pyobjc.")
        p = subprocess.run(["cliclick", "dd:%d,%d" % (args.x1, args.y1),
                            "dm:%d,%d" % (args.x2, args.y2),
                            "du:%d,%d" % (args.x2, args.y2)],
                           capture_output=True)
        if p.returncode != 0:
            c.fail("cliclick fallo (rc=%d): %s" % (
                p.returncode, (p.stderr or b"").decode("utf-8", "replace")))
        via = "cliclick dd/dm/du [3p] (ultima ruta)"
    else:
        c.fail("Sin pynput NI pyobjc NI cliclick: no se puede arrastrar. "
               "pip3 install pynput==1.8.2 o pyobjc-framework-Quartz.")
    fx, fy = c.posicion_cursor()
    item = {
        "ok": True,
        "via": via,
        "desde": [args.x1, args.y1],
        "hasta": [fx, fy],
        "boton": args.boton,
        "pasos": pasos,
        "marco": c.MARCO,
        "unidad": "puntos logicos",
        "monitor": _monitor_dict_mac(args.x2, args.y2),
        "aviso": "verifica el resultado con pantalla.py capturar",
    }
    ag = _aviso_guard_mac()
    if ag:
        item["aviso_guard"] = ag
    c.json_out(item)


def cmd_scroll_mac(args):
    c.checar_abort()
    c.checar_pausa()
    if args.vertical is None and args.horizontal is None:
        c.fail("Indica --vertical N o --horizontal N (excluyentes).")
    if (args.x is None) != (args.y is None):
        c.fail("Debe indicar --x e --y juntos, o ninguno.")
    via_posicion = None
    if args.x is not None:
        _guard_destino_mac(args.x, args.y)
        c.fail_safe_check()
        ruta, par = _raton_ruta_mac()
        if ruta == "pynput":
            par[0].position = (int(args.x), int(args.y))
            via_posicion = "pynput"
        elif ruta == "quartz":
            c._q_move(c.try_quartz(), int(args.x), int(args.y))
            via_posicion = "quartz"
        elif ruta == "cliclick":
            subprocess.run(["cliclick", "m:%d,%d" % (args.x, args.y)],
                           capture_output=True)
            via_posicion = "cliclick [3p]"
        else:
            c.fail("Sin ninguna ruta de raton: pip3 install pynput==1.8.2 "
                   "o pyobjc-framework-Quartz.")
    dx = 0 if args.vertical is not None else int(args.horizontal)
    dy = int(args.vertical) if args.vertical is not None else 0
    ruta, par = _raton_ruta_mac()
    if ruta == "pynput":
        par[0].scroll(dx, dy)
        via = "pynput scroll(dx, dy) → CGEventCreateScrollWheelEvent"
    elif ruta == "quartz":
        Q = c.try_quartz()
        pasos = max(abs(dx), abs(dy))
        for _ in range(pasos):
            ev = Q.CGEventCreateScrollWheelEvent(
                None, Q.kCGScrollEventUnitPixel, 2,
                dy * 10, dx * 10)
            Q.CGEventPost(Q.kCGHIDEventTap, ev)
            time.sleep(_DARWIN_CATCH_UP)
        via = "pyobjc ScrollWheelEvent (dy*10/dx*10, patron del fuente " \
              "pynput _darwin.py:94-103)"
    else:
        c.fail("Scroll requiere pynput o pyobjc (cliclick [3p] no tiene "
               "sintaxis verificada aqui): pip3 install pynput==1.8.2 o "
               "pyobjc-framework-Quartz.")
    c.json_out({
        "ok": True,
        "eje": "vertical" if args.vertical is not None else "horizontal",
        "pasos": abs(dx) if dx else abs(dy),
        "sentido": ("arriba" if dy > 0 else "abajo")
        if args.vertical is not None else ("derecha" if dx > 0 else "izquierda"),
        "posicion_via": via_posicion or "cursor-actual",
        "marco": c.MARCO,
        "unidad": "puntos logicos",
        "nota": "convencion de la skill (igual que Windows): dy>0=sube, "
                "dx>0=derecha; 1 paso ~ 10 px de rueda (kCGScrollEventUnit"
                "Pixel x10, fuente pynput). El 'scroll natural' de macOS "
                "puede invertir la percepcion por app [runtime: verificar "
                "en la maquina; el campo 'sentido' describe el valor "
                "emitido, no lo que vio la app]",
    })


def cmd_posicion_mac(args):
    por_backend = {}
    if c.quartz_disponible():
        Q = c.try_quartz()
        loc = Q.CGEventGetLocation(Q.CGEventCreate(None))
        por_backend["quartz"] = {"x": int(round(float(loc.x))),
                                 "y": int(round(float(loc.y)))}
    par = _pynput_mouse_mac()
    if par is not None:
        x, y = par[0].position
        por_backend["pynput"] = {"x": int(x), "y": int(y)}
    if not por_backend:
        c.fail("Sin Quartz NI pynput: pip3 install pynput==1.8.2 o "
               "pyobjc-framework-Quartz.")
    if "quartz" in por_backend:
        x, y = por_backend["quartz"]["x"], por_backend["quartz"]["y"]
        via = "quartz"
    else:
        x, y = por_backend["pynput"]["x"], por_backend["pynput"]["y"]
        via = "pynput"
    m = c._monitor_contiene(x, y) if c.quartz_disponible() else None
    # P1-1: forma canonica plana x/y/marco/via/por_backend (identica a las
    # otras ramas; las claves top-level quartz/pynput se mudaron dentro).
    c.json_out({
        "ok": True,
        "x": int(x), "y": int(y),
        "marco": c.MARCO,
        "via": via,
        "monitor": None if m is None else {
            "indice": m["indice"], "nombre": m["nombre"],
            "primario": m["primario"]},
        "por_backend": por_backend,
        "unidad": "puntos logicos (0,0 = sup-izq del display principal)",
        "nota": ("ambas lecturas comparten el marco global top-left "
                 "(VERIFICADO fuente: pynput revierte el y de Cocoa con "
                 "CGDisplayPixelsHigh); 'monitor' = quien contiene el "
                 "cursor; negativos = display a la izquierda/arriba "
                 "[runtime arrangement]; x/y canonicos = lectura " + via + ")")
    })


def construir_parser_mac():
    parser = c.Parser(
        prog="raton.py (macOS)",
        description="Raton para automatizacion de escritorio en macOS: "
                    "mover, clic (doble clic real via clickState), arrastrar "
                    "y scroll vertical/horizontal. Piramide pynput→pyobjc→"
                    "cliclick[3p]. Coordenadas = PUNTOS LOGICOS del espacio "
                    "global (negativos segun arrangement).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_DOC_MAC.split("Subcomandos:")[1]
        if _DOC_MAC and "Subcomandos:" in _DOC_MAC else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True,
                                metavar="SUBCOMANDO")

    p = sub.add_parser("mover", help="desplazar el cursor")
    p.add_argument("x", type=int,
                   help="destino X (punto logico; negativo = display a la "
                        "izquierda segun arrangement)")
    p.add_argument("y", type=int, help="destino Y (punto logico)")
    p.add_argument("--duracion", type=float, default=0.2,
                   help="segundos del desplazamiento animado (0 = "
                        "instantaneo)")
    p.set_defaults(func=cmd_mover_mac)

    p = sub.add_parser("click", help="clic simple/derecho/doble")
    p.add_argument("--x", type=int,
                   help="coordenada X en puntos (opcional; si no, posicion "
                        "actual)")
    p.add_argument("--y", type=int, help="coordenada Y en puntos")
    p.add_argument("--boton", default="left", metavar="BOTON",
                   help="boton del raton: left|right|middle (darwin no "
                        "define x1/x2; validado en handler)")
    p.add_argument("--doble", action="store_true",
                   help="doble clic (clickState=2, docs pynput macOS)")
    p.set_defaults(func=cmd_click_mac)

    p = sub.add_parser("arrastrar",
                       help="presionar, recorrer la trayectoria y soltar")
    p.add_argument("x1", type=int, help="origen X (puntos)")
    p.add_argument("y1", type=int, help="origen Y (puntos)")
    p.add_argument("x2", type=int, help="destino X (puntos)")
    p.add_argument("y2", type=int, help="destino Y (puntos)")
    # TIEMPOS-K: arrastre 0.5->0.4 s (espejo de la rama Windows, -20%, piso ok).
    p.add_argument("--duracion", type=float, default=0.4,
                   help="segundos totales del arrastre (por defecto 0.4)")
    p.add_argument("--boton", default="left", metavar="BOTON",
                   help="boton a mantener: left|right|middle (validado en handler)")
    p.set_defaults(func=cmd_arrastrar_mac)

    p = sub.add_parser("scroll",
                       help="rueda vertical u horizontal (pynput scroll)")
    grupo = p.add_mutually_exclusive_group()
    grupo.add_argument("--vertical", type=int, metavar="N",
                       help="pasos verticales: +sube, -baja (convencion de "
                            "la skill; verificar scroll natural [runtime])")
    grupo.add_argument("--horizontal", type=int, metavar="N",
                       help="pasos horizontales: +derecha, -izquierda")
    p.add_argument("--x", type=int,
                   help="posicionar el cursor antes de rodar (punto logico)")
    p.add_argument("--y", type=int, help="coordenada Y del posicionamiento")
    p.set_defaults(func=cmd_scroll_mac)

    p = sub.add_parser("posicion",
                       help="cursor segun los marcos disponibles")
    p.set_defaults(func=cmd_posicion_mac)

    return parser


# ===========================================================================
# main() UNIFICADO (FASE SEG3): dispatch en tiempo de ejecucion por
# sys.platform; `c` se bind-ea al modulo de primitivas del SO.
# ===========================================================================


def main():
    global c, _BOTONES
    mod = _core.modulo_sistema()            # lee sys.platform EN TIEMPO DE EJECUCION
    if mod is None:
        _core.so_no_soportado("raton.py")    # JSON rc 2 (nunca retorna)
    c = mod
    plat = sys.platform
    if plat == "win32":
        global pyautogui                     # import exclusivo Windows (era top)
        import pyautogui                     # glue ya fijo DPI + FAILSAFE + PAUSE
        _BOTONES = c.BOTONES                 # era asignacion de top con c
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
        # Historico por rama: win capturaba pyautogui.FailSafeException; linux
        # probaba por nombre de tipo; mac no tenia rama de failsafe. La
        # conversion ValueError->JSON la tenian win y mac (linux NO: su
        # rama ValueError caia al generic).
        if (plat == "win32" and isinstance(exc, pyautogui.FailSafeException)) \
                or (plat == "linux"
                    and type(exc).__name__ == "FailSafeException"):
            c.fallar_por_failsafe(exc)
        if plat != "linux" and isinstance(exc, ValueError):
            c.fail("pynput rechazo el movimiento/scroll: %s" % exc)
        c.fail("%s: %s" % (type(exc).__name__, exc))


if __name__ == "__main__":
    main()
