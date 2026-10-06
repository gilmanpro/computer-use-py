# -*- coding: utf-8 -*-
"""monitores.py — Mapa de monitores y pantalla virtual (skill computer-use-py).

ENTRADA MULTI-OS (FASE SEG3): `python scripts/monitores.py ...` vale en los 3
SO — el CLI ejecuta la ruta de TU SO EN EL PROPIO PROCESO (dispatch por
sys.platform en tiempo de ejecucion, bind `c = _core.modulo_sistema()`): en
Windows la ruta nativa de abajo; en Linux/macOS las primitivas exclusivas
viven en la libreria scripts/linux/linux_especiales.py o
scripts/macos/macos_especiales.py; plataforma desconocida responde JSON + rc 2.

Ruta Windows nativa — ctypes puro: EnumDisplayMonitors + GetMonitorInfoW +
GetSystemMetrics (SM_X/Y/CX/CYVIRTUALSCREEN) + GetCursorPos. Sin dependencias
nuevas: la unica importacion propia es glue_windows (JSON canonico y DPI
per-monitor fijado ANTES de leer metricas, para que el mapa este en pixeles
fisicos igual que las capturas). Marco: referencias/monitores-multi.md.

Coordenadas del ESPACIO VIRTUAL: el origen logico (0,0) es el vertice
sup-izq del monitor PRIMARIO; un monitor a la izquierda/arriba tiene
rectangulos NEGATIVOS y sus coordenadas siguen siendo validas.

Salida: JSON por stdout; errores JSON con "error". Subcomandos:
  listar  Cada monitor (nombre, izq/top/der/bot, work, primario, tamano)
          + bloque "virtual" (origen y bounding de todos los monitores).
  cursor  Que monitor contiene el cursor (GetCursorPos, via solo lectura).

Ejemplos (desde la carpeta computer-use-py):
  py scripts/monitores.py listar          # Windows (python3 en Linux/macOS)
  py scripts/monitores.py cursor
"""

import argparse
import os
import sys

_DIR_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _DIR_SCRIPTS not in sys.path:
    sys.path.insert(0, _DIR_SCRIPTS)
import _core  # noqa: E402  (genericos multi-OS + modulo_sistema: dispatch en tiempo de ejecucion)

# ===========================================================================
# SECCION WINDOWS — ruta nativa ctypes (cuerpos VERBATIM del CLI SEG2; `c` se
# bind-eea a glue_windows en main()).
# ===========================================================================


def cmd_listar(args):
    mons = c.monitores()
    v = c.tamano_virtual()
    c.json_out({
        "monitores": [
            {
                "indice": m["indice"],
                "nombre": m["nombre"],
                "izq": m["izq"], "top": m["top"],
                "der": m["der"], "bot": m["bot"],
                "ancho": m["ancho"], "alto": m["alto"],
                "work": list(m["work"]),
                "primario": m["primario"],
            }
            for m in mons
        ],
        "virtual": {
            "x": v["x"], "y": v["y"],
            "ancho": v["ancho"], "alto": v["alto"],
            "origen": [v["x"], v["y"]],
        },
        "marco": c.MARCO,
        "via": "ctypes EnumDisplayMonitors",
        "nota": "coordenadas del ESPACIO VIRTUAL (negativas hacia la "
                "izquierda/arriba del primario); der/bot exclusivos "
                "(ancho = der-izq). El indice sigue el orden de "
                "EnumDisplayMonitors: volver a listar tras reconectar "
                "monitores.",
    })


def cmd_cursor(args):
    pt = wintypes.POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
        c.fail("GetCursorPos fallo: %s" % ctypes.WinError())
    m = c._monitor_contiene(pt.x, pt.y)
    c.json_out({
        "x": int(pt.x), "y": int(pt.y),
        "marco": c.MARCO,
        "via": "ctypes GetCursorPos",
        "dentro_de_monitor": m is not None,
        "monitor": None if m is None else {
            "indice": m["indice"], "nombre": m["nombre"],
            "primario": m["primario"], "izq": m["izq"], "top": m["top"],
            "der": m["der"], "bot": m["bot"],
        },
        "nota": "lectura de solo lectura: el marco coincide con el de las "
                "capturas y con raton.py (coords virtuales). Un punto en el "
                "hueco de un bounding con monitores desalineados no esta en "
                "ningun monitor.",
    })


def construir_parser_win():
    parser = c.Parser(
        prog="monitores.py",
        description="Mapa de monitores y pantalla virtual en coordenadas "
                    "del espacio virtual (ctypes puro, solo lectura).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1] if __doc__ and "Subcomandos:" in __doc__ else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    sub.add_parser("listar", help="monitores + bounding virtual").set_defaults(func=cmd_listar)
    sub.add_parser("cursor", help="monitor que contiene el cursor").set_defaults(func=cmd_cursor)

    return parser


# ===========================================================================
# SECCION LINUX — cuerpos de scripts/linux/monitores.py movados VERBATIM
# (solo el sufijo _linux; `c` = scripts/linux/linux_especiales.py: xrandr,
# xdotool, deteccion_sesion, monitores, tamano_virtual, _monitor_contiene,
# genericos _core reexportados). Marco: px_layout.
# ===========================================================================

_DOC_LINUX = """monitores.py — Mapa de monitores del dominio LINUX (skill computer-use-py).

Todo via Python: internamente lee xrandr --listmonitors (X11; la opcion esta
documentada en el man, el FORMATO de salida es empirico [runtime]) o
swaymsg -t get_outputs / hyprctl monitors -j (Wayland; swaymsg verificado en
su man). Marco: coordenadas de LAYOUT — en X11 el (0,0) es el vertice
sup-izq del SCREEN completo; los negativos NO estan documentados en X11 y en
Wayland dependen del compositor [runtime]. references/linux-python.md §6-§7.

Salida: JSON por stdout; errores JSON con "error". Subcomandos:
  listar  Cada monitor (nombre, izq/top/der/bot, ancho/alto, primario, via)
          + bloque "virtual" (bounding de layout) + "sesion".
  cursor  Que monitor contiene el cursor. X11 via xdotool getmouselocation
          --shell (man verbatim: X= Y= SCREEN= WINDOW=). Wayland: sin CLI
          documentada => error honesto.

Ejemplos (desde la carpeta computer-use-py, en la maquina Linux):
  python3 scripts/monitores.py listar
  python3 scripts/monitores.py cursor
"""


def cmd_listar_linux(args):
    mons = c.monitores()
    v = c.tamano_virtual()
    c.json_out({
        "sesion": c.deteccion_sesion(),
        "monitores": [
            {
                "indice": m["indice"],
                "nombre": m["nombre"],
                "izq": m["izq"], "top": m["top"],
                "der": m["der"], "bot": m["bot"],
                "ancho": m["ancho"], "alto": m["alto"],
                "primario": m["primario"],
                "activo": m.get("activo", True),
                "via": m["via"],
            }
            for m in mons
        ],
        "virtual": {
            "x": v["x"], "y": v["y"],
            "ancho": v["ancho"], "alto": v["alto"],
            "origen": [v["x"], v["y"]],
        },
        "marco": c.MARCO,
        "via": "xrandr/swaymsg/hyprctl (ver monitores[].via)",
        "nota": "coordenadas de LAYOUT: en X11 el origen (0,0) es el vertice "
                "sup-izq del SCREEN (no del primario: si el primario no esta "
                "en el extremo, su izq/top NO es 0); en Wayland (sway/hypr) "
                "los offsets los fija el compositor y pueden ser negativos "
                "[runtime]. der/bot exclusivos (ancho = der-izq). Volver a "
                "listar tras conectar monitores.",
    })


def cmd_cursor_linux(args):
    sesion = c.deteccion_sesion()
    if sesion != "x11":
        c.fail("Leer la POSICION del cursor no tiene CLI documentada en "
               "Wayland con las herramientas auditadas (ydotool es uinput "
               "solo-escritura; swaymsg/hyprctl no exponen el puntero): usa "
               "pantalla.py capturar + vision. (XDG_SESSION_TYPE=%r)" % sesion,
               sesion=sesion,
               pista="raton.py mover usa ydotool mousemove --absolute y no "
                     "necesita leer el cursor")
    r = c.run_ok("xdotool", ["getmouselocation", "--shell"], timeout=10.0)
    kv = c._shell_kv(r["stdout"])
    try:
        x, y = int(kv["X"]), int(kv["Y"])
    except (KeyError, ValueError):
        c.fail("xdotool getmouselocation --shell devolvio un formato "
               "inesperado.", salida=r["stdout"].strip()[:300])
    pantalla = int(kv.get("SCREEN", "0") or 0)
    m = c._monitor_contiene(x, y)
    nota = ("lectura XTEST/Xlib de solo lectura (man xdotool verbatim: "
            "'Outputs the x, y, screen, and window id'). Marco: coords del "
            "screen X11; coincide con las capturas.")
    if pantalla != 0:
        nota += (" OJO SCREEN=%d: el servidor X tiene MULTIPLES X screens sin "
                 "Xinerama; ahi las coords absolutas NO son unificadas y el "
                 "marco de esta skill se rompe (references/linux-python.md §6)."
                 % pantalla)
    c.json_out({
        "x": x, "y": y,
        "screen": pantalla,
        "window": kv.get("WINDOW"),
        "marco": c.MARCO,
        "sesion": sesion,
        "via": "xdotool getmouselocation --shell",
        "dentro_de_monitor": m is not None,
        "monitor": None if m is None else {
            "indice": m["indice"], "nombre": m["nombre"],
            "primario": m["primario"], "izq": m["izq"], "top": m["top"],
            "der": m["der"], "bot": m["bot"],
        },
        "nota": nota,
    })


def construir_parser_linux():
    parser = c.Parser(
        prog="monitores.py (linux)",
        description="Mapa de monitores y pantalla de layout en Linux "
                    "(xrandr/swaymsg/hyprctl via subprocess interno; "
                    "superficie 100 % Python con el JSON del dominio "
                    "Windows).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_DOC_LINUX.split("Subcomandos:")[1] if _DOC_LINUX and "Subcomandos:" in _DOC_LINUX else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    sub.add_parser("listar", help="monitores + bounding virtual + sesion") \
       .set_defaults(func=cmd_listar_linux)
    sub.add_parser("cursor", help="monitor que contiene el cursor (solo X11)") \
       .set_defaults(func=cmd_cursor_linux)

    return parser


# ===========================================================================
# SECCION macOS — cuerpos de scripts/macos/monitores.py movados VERBATIM
# (sufijo _mac). _mons_quartz/_mons_profiler/_mons_osascript/_colectar ya
# viven en scripts/macos/macos_especiales.py (llamadas via c.); _bounding no
# bajo (solo lo llaman cmd_*/helpers de raiz) y sube como _bounding_mac.
# Marco: puntos_logicos.
# ===========================================================================

_DOC_MAC = """monitores.py — Mapa de monitores y pantalla virtual en macOS (skill
computer-use-py, dominio mac).

Coordenadas: PUNTOS LOGICOS del espacio global (origen (0,0) = vertice
sup-izq del display PRINCIPAL; VERIFICADO fuente pynput _darwin.py:73-76).
Con monitores a la izquierda/arriba del principal, los rects de
CGDisplayBounds pueden dar NEGATIVOS: como en Windows, son validos, pero
la habilidad NUNCA asume el signo: lee los rects reales cada ejecucion
[runtime: confirmar con 'monitores.py listar' en el Mac].

Rutas (contrato: todo corre sobre Python):
  listar  1) pyobjc Quartz: CGGetActiveDisplayList + CGDisplayBounds +
             CGMainDisplayID (+ nombres via AppKit NSScreen [runtime]);
          2) sin pyobjc: system_profiler SPDisplaysDataType -json
             (parse [runtime]: nombres y resoluciones; SIN posiciones),
          3) ultimo recurso: osascript bounds del desktop (solo principal).
  cursor  Posicion del cursor (CGEventGetLocation via Quartz o pynput) y
          monitor que lo contiene por rects logicos.

Salida: JSON por stdout; errores JSON con "error". Mismos verbos/claves que
el monitores.py de Windows; JSON anade "unidad" y "via".

Ejemplos (desde la carpeta computer-use-py, en el Mac):
  python3 scripts/monitores.py listar
  python3 scripts/monitores.py cursor
"""


def _bounding_mac(mons):
    """Bounding desde rects conocidos; si faltan positions, usa (0,0)+tamanos.

    Con rects presentes la formula min/max es la generica de
    _core.bounding_de (identica a la de las otras ramas); lo exclusivo de
    aqui es el fallback sin posiciones (union apilada, aproximada [runtime])."""
    rects = [m for m in mons if m["izq"] is not None]
    if rects:
        # SEG3: _core directo (no el alias c, que solo se bind ea en main() de
        # ESTE CLI): pantalla.py importa este helper entre CLIs y ahi `c` del
        # modulo monitores puede estar aun sin bind ear. c.bounding_de era la
        # MISMA funcion reexportada de _core: comportamiento intacto.
        return _core.bounding_de(rects)
    # via sin posiciones: bounding aproximado = union apilada a la derecha
    ancho = sum((m["ancho"] or 0) for m in mons)
    alto = max([(m["alto"] or 0) for m in mons] or [0])
    return {"x": 0, "y": 0, "ancho": ancho, "alto": alto}


def cmd_listar_mac(args):
    mons, via = c._colectar()
    v = _bounding_mac(mons)
    c.json_out({
        "monitores": [
            {
                "indice": m["indice"],
                "nombre": m["nombre"],
                "numero": m.get("numero"),
                "izq": m["izq"], "top": m["top"],
                "der": m["der"], "bot": m["bot"],
                "ancho": m["ancho"], "alto": m["alto"],
                "work": m["work"],
                "primario": m["primario"],
            }
            for m in mons
        ],
        "virtual": {
            "x": v["x"], "y": v["y"],
            "ancho": v["ancho"], "alto": v["alto"],
            "origen": [v["x"], v["y"]],
        },
        "marco": c.MARCO,
        "unidad": "puntos logicos (espacio global; 0,0 = sup-izq del "
                  "display principal)",
        "via": via,
        "nota": "der/bot exclusivos (ancho = der-izq). Con via!='quartz' las "
                "POSICIONES pueden faltar (None): instala pyobjc-framework-"
                "Quartz para el mapa virtual. En Retina los PUNTOS no son "
                "PIXELES: las capturas exponen su escala. work=bounds: macOS "
                "no expone area util sin menu/Dock (documentado como "
                "[runtime]). El orden puede cambiar al reconectar monitores: "
                "volver a listar." if via == "quartz" else (
                    "via=%s: datos aproximados SIN posiciones garantizadas: "
                    "instala pyobjc-framework-Quartz (pip3 install "
                    "pyobjc-framework-Quartz) y re-lista. 'work' y bounding "
                    "apilado son aproximados [runtime]." % via),
    })


def cmd_cursor_mac(args):
    if c.quartz_disponible():
        x, y = c.posicion_cursor()
        marco = "pantalla virtual en puntos logicos (CGEventGetLocation)"
    else:
        try:
            from pynput.mouse import Controller as ControladorRaton
            x, y = ControladorRaton().position
            marco = "pantalla virtual en puntos logicos (pynput/NSEvent volteado)"
        except Exception:
            c.fail("Sin Quartz NI pynput: no se puede leer el cursor. "
                   "pip3 install pynput==1.8.2 (o pyobjc-framework-Quartz).")
    mons, via = c._colectar()
    m = None
    for mm in mons:
        if mm["izq"] is None:
            continue
        if mm["izq"] <= int(x) < mm["der"] and mm["top"] <= int(y) < mm["bot"]:
            m = mm
            break
    c.json_out({
        "x": int(x), "y": int(y),
        "marco": c.MARCO,
        "unidad": "puntos logicos",
        "via": via,
        "dentro_de_monitor": m is not None,
        "monitor": None if m is None else {
            "indice": m["indice"], "nombre": m["nombre"],
            "primario": m["primario"], "izq": m["izq"], "top": m["top"],
            "der": m["der"], "bot": m["bot"],
        },
        "nota": "lectura de solo lectura: el marco coincide con el de las "
                "capturas y con raton.py (puntos logicos globales; " + marco +
                "). Un punto en el hueco de un bounding con monitores "
                "desalineados no esta en ningun monitor.",
    })


def construir_parser_mac():
    parser = c.Parser(
        prog="monitores.py (macOS)",
        description="Mapa de monitores y pantalla virtual en PUNTOS LOGICOS "
                    "del espacio global (Quartz; fallback system_profiler/"
                    "osascript, solo lectura).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_DOC_MAC.split("Salida:")[0] if _DOC_MAC else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True,
                                metavar="SUBCOMANDO")

    sub.add_parser("listar", help="monitores + bounding virtual") \
       .set_defaults(func=cmd_listar_mac)
    sub.add_parser("cursor", help="monitor que contiene el cursor") \
       .set_defaults(func=cmd_cursor_mac)

    return parser


def main():
    global c
    mod = _core.modulo_sistema()          # lee sys.platform EN TIEMPO DE EJECUCION
    if mod is None:
        _core.so_no_soportado("monitores.py")  # JSON rc 2 contractual (nunca retorna)
    c = mod
    plat = sys.platform
    if plat == "win32":
        global ctypes, wintypes                # solo los que ESTE CLI usaba
        import ctypes
        from ctypes import wintypes
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
