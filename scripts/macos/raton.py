# -*- coding: utf-8 -*-
"""raton.py — Raton en macOS (skill computer-use-py, dominio mac).

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
  python3 scripts/macos/raton.py mover 640 300 --duracion 0.2
  python3 scripts/macos/raton.py click --x 640 --y 300 --boton right
  python3 scripts/macos/raton.py click --x 2000 --y 300 --doble
  python3 scripts/macos/raton.py arrastrar 100 100 400 350 --duracion 0.5
  python3 scripts/macos/raton.py scroll --vertical -5 --x 800 --y 400
  python3 scripts/macos/raton.py scroll --horizontal 3
"""

import argparse
import shutil
import subprocess
import time

import _compartido_mac as c

# Botones: darwin NO define x1/x2 (VERIFICADO fuente mouse/_darwin.py:55-61).
_BOTONES = ("left", "right", "middle")
_DARWIN_CATCH_UP = 0.01  # pausa post-evento: VERIFICADO pyautogui 0.9.54
                        # __init__.py:567 DARWIN_CATCH_UP_TIME = 0.01


def _guard_destino(x, y):
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


def _pynput_mouse():
    """(Controller, Button) de pynput o None si no esta instalado."""
    try:
        from pynput.mouse import Button, Controller as ControladorRaton
        return ControladorRaton(), Button
    except ImportError:
        return None


def _raton_ruta():
    """('pynput'|'quartz'|'cliclick'|None, handle)."""
    par = _pynput_mouse()
    if par is not None:
        return "pynput", par
    if c.quartz_disponible():
        return "quartz", None
    if shutil.which("cliclick"):
        return "cliclick", None
    return None, None


# --- primitives Quartz manuales (respaldo) -------------------------------

def _q_move(Q, x, y):
    Q.CGEventPost(Q.kCGHIDEventTap, Q.CGEventCreateMouseEvent(
        None, Q.kCGEventMouseMoved, (x, y), 0))


def _q_button_events(Q, boton):
    """(down, up, dragged, btn_id) segun el boton, replicando la tabla del
    fuente pynput _darwin.py:36-61 y _pyautogui_osx.py:355-373 [runtime]."""
    base = {"left": "kCGEventLeft", "right": "kCGEventRight",
            "middle": "kCGEventOther"}[boton]
    btn_id = {"left": Q.kCGMouseButtonLeft, "right": Q.kCGMouseButtonRight,
              "middle": Q.kCGMouseButtonCenter}[boton]
    return (getattr(Q, base + "MouseDown"), getattr(Q, base + "MouseUp"),
            getattr(Q, base + "MouseDragged"), btn_id)


def _q_click(Q, x, y, boton, doble):
    """Clic manual: down/up; para doble, kCGMouseEventClickState=1 y 2 en
    cada ciclo — patron exactamente leido en mouse/_darwin.py:105-133
    (efecto en Finder/AppKit [runtime: verificar apertura])."""
    down, up, _dr, btn_id = _q_button_events(Q, boton)
    ciclos = 2 if doble else 1
    for i in range(1, ciclos + 1):
        ev = Q.CGEventCreateMouseEvent(None, down, (x, y), btn_id)
        try:
            Q.CGEventSetIntegerValueField(
                ev, Q.kCGMouseEventClickState, i)
        except AttributeError:
            pass
        Q.CGEventPost(Q.kCGHIDEventTap, ev)
        ev2 = Q.CGEventCreateMouseEvent(None, up, (x, y), btn_id)
        try:
            Q.CGEventSetIntegerValueField(
                ev2, Q.kCGMouseEventClickState, i)
        except AttributeError:
            pass
        Q.CGEventPost(Q.kCGHIDEventTap, ev2)
        if i < ciclos:
            time.sleep(0.05)


def _cliclick(x, y, boton, doble):
    """Ultima ruta [3p]: cliclick sin auditar, solo si no hay Python
    grafico. Sintaxis c:/dc: segun la herramienta [3p: no fetcheada]."""
    if boton != "left":
        c.fail("cliclick [3p] como unica ruta: la skill solo define su "
               "sintaxis para boton left; para right/doble instala "
               "pynput==1.8.2 o pyobjc-framework-Quartz.")
    accion = "dc:" if doble else "c:"
    p = subprocess.run(["cliclick", "%s%d,%d" % (accion, x, y)],
                       capture_output=True)
    if p.returncode != 0:
        c.fail("cliclick fallo (rc=%d): %s" % (
            p.returncode, (p.stderr or b"").decode("utf-8", "replace")))


# --- subcomandos ----------------------------------------------------------

def _aviso_guard():
    """Nota cuando el guard de bounding se omitio por no haber mapa."""
    if not c.quartz_disponible():
        return ("sin pyobjc-framework-Quartz: el destino NO se valido contra "
                "el bounding de monitores; un valor fuera de pantalla no se "
                "detecta aqui (pynput/CGEvent lo aceptan e ignoran)")
    return None


def _monitor_dict(x, y):
    """Sub-objeto monitor canonico {indice,nombre,primario} del punto dado,
    o None sin mapa/punto en hueco (P1-3)."""
    if not c.quartz_disponible():
        return None
    m = c._monitor_contiene(x, y)
    if m is None:
        return None
    return {"indice": m["indice"], "nombre": m["nombre"],
            "primario": m["primario"]}


def cmd_mover(args):
    c.checar_abort()
    c.checar_pausa()  # P1-5: freno suave antes de emitir
    _guard_destino(args.x, args.y)
    c.fail_safe_check()
    ruta, par = _raton_ruta()
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
            _q_move(Q, int(nx), int(ny))
            time.sleep(_DARWIN_CATCH_UP)
    nx_, ny_ = c.posicion_cursor()
    item = {"ok": True, "via": ruta,
            "marco": c.MARCO,
            "unidad": "puntos logicos",
            "monitor": _monitor_dict(args.x, args.y),
            "desde": [ax, ay], "hasta": [nx_, ny_]}
    ag = _aviso_guard()
    if ag:
        item["aviso_guard"] = ag
    c.json_out(item)


def cmd_click(args):
    c.checar_abort()
    c.checar_pausa()
    if (args.x is None) != (args.y is None):
        c.fail("Debe indicar --x e --y juntos, o ninguno (clic en la "
               "posicion actual).")
    if args.boton not in _BOTONES:
        c.fail("Boton %r invalido para la rama macOS (darwin no define "
               "x1/x2)." % args.boton, validos=list(_BOTONES))
    if args.x is not None:
        _guard_destino(args.x, args.y)
    c.fail_safe_check()
    x, y = c.posicion_cursor() if args.x is None else (args.x, args.y)
    ruta, par = _raton_ruta()
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
            _q_move(Q, int(x), int(y))
            time.sleep(_DARWIN_CATCH_UP)
        _q_click(Q, int(x), int(y), args.boton, args.doble)
        via = "pyobjc CGEventCreateMouseEvent+Post (clickState %d) [runtime]" % (
            2 if args.doble else 1)
    elif ruta == "cliclick":
        _cliclick(int(x), int(y), args.boton, args.doble)
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
        "monitor": _monitor_dict(x, y),
        "aviso": "el exito de un clic NO se reporta: sin TCC Accesibilidad "
                 "el evento puede no llegar [runtime]. Verifica SIEMPRE con "
                 "pantalla.py capturar.",
    }
    ag = _aviso_guard()
    if ag:
        item["aviso_guard"] = ag
    c.json_out(item)


def cmd_arrastrar(args):
    c.checar_abort()
    c.checar_pausa()
    if args.boton not in _BOTONES:
        c.fail("Boton %r invalido para la rama macOS." % args.boton,
               validos=list(_BOTONES))
    _guard_destino(args.x1, args.y1)
    _guard_destino(args.x2, args.y2)
    duracion = min(max(args.duracion, 0.1), 30.0)
    pasos = min(max(int(duracion / 0.01), 10), 200)
    retardo = duracion / pasos
    c.fail_safe_check()
    ruta, par = _raton_ruta()
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
        down, up, dragged, btn_id = _q_button_events(Q, args.boton)
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
        "monitor": _monitor_dict(args.x2, args.y2),
        "aviso": "verifica el resultado con pantalla.py capturar",
    }
    ag = _aviso_guard()
    if ag:
        item["aviso_guard"] = ag
    c.json_out(item)


def cmd_scroll(args):
    c.checar_abort()
    c.checar_pausa()
    if args.vertical is None and args.horizontal is None:
        c.fail("Indica --vertical N o --horizontal N (excluyentes).")
    if (args.x is None) != (args.y is None):
        c.fail("Debe indicar --x e --y juntos, o ninguno.")
    via_posicion = None
    if args.x is not None:
        _guard_destino(args.x, args.y)
        c.fail_safe_check()
        ruta, par = _raton_ruta()
        if ruta == "pynput":
            par[0].position = (int(args.x), int(args.y))
            via_posicion = "pynput"
        elif ruta == "quartz":
            _q_move(c.try_quartz(), int(args.x), int(args.y))
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
    ruta, par = _raton_ruta()
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


def cmd_posicion(args):
    por_backend = {}
    if c.quartz_disponible():
        Q = c.try_quartz()
        loc = Q.CGEventGetLocation(Q.CGEventCreate(None))
        por_backend["quartz"] = {"x": int(round(float(loc.x))),
                                 "y": int(round(float(loc.y)))}
    par = _pynput_mouse()
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


def construir_parser():
    parser = c.Parser(
        prog="raton.py (macOS)",
        description="Raton para automatizacion de escritorio en macOS: "
                    "mover, clic (doble clic real via clickState), arrastrar "
                    "y scroll vertical/horizontal. Piramide pynput→pyobjc→"
                    "cliclick[3p]. Coordenadas = PUNTOS LOGICOS del espacio "
                    "global (negativos segun arrangement).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1]
        if __doc__ and "Subcomandos:" in __doc__ else None,
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
    p.set_defaults(func=cmd_mover)

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
    p.set_defaults(func=cmd_click)

    p = sub.add_parser("arrastrar",
                       help="presionar, recorrer la trayectoria y soltar")
    p.add_argument("x1", type=int, help="origen X (puntos)")
    p.add_argument("y1", type=int, help="origen Y (puntos)")
    p.add_argument("x2", type=int, help="destino X (puntos)")
    p.add_argument("y2", type=int, help="destino Y (puntos)")
    p.add_argument("--duracion", type=float, default=0.5,
                   help="segundos totales del arrastre (por defecto 0.5)")
    p.add_argument("--boton", default="left", metavar="BOTON",
                   help="boton a mantener: left|right|middle (validado en handler)")
    p.set_defaults(func=cmd_arrastrar)

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
    p.set_defaults(func=cmd_scroll)

    p = sub.add_parser("posicion",
                       help="cursor segun los marcos disponibles")
    p.set_defaults(func=cmd_posicion)

    return parser


def main():
    args = construir_parser().parse_args()
    try:
        args.func(args)
    except SystemExit:
        raise
    except ValueError as exc:
        # pynput move/scroll pueden lanzar ValueError: convertir a JSON.
        c.fail("pynput rechazo el movimiento/scroll: %s" % exc)
    except Exception as exc:
        c.fail("%s: %s" % (type(exc).__name__, exc))


if __name__ == "__main__":
    main()
