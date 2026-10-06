# -*- coding: utf-8 -*-
"""monitores.py — Mapa de monitores del dominio LINUX (skill computer-use-py).

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
  python3 scripts/linux/monitores.py listar
  python3 scripts/linux/monitores.py cursor
"""

import argparse

import _compartido_linux as c


def cmd_listar(args):
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


def cmd_cursor(args):
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


def construir_parser():
    parser = c.Parser(
        prog="monitores.py (linux)",
        description="Mapa de monitores y pantalla de layout en Linux "
                    "(xrandr/swaymsg/hyprctl via subprocess interno; "
                    "superficie 100 % Python con el JSON del dominio "
                    "Windows).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1] if __doc__ and "Subcomandos:" in __doc__ else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    sub.add_parser("listar", help="monitores + bounding virtual + sesion") \
       .set_defaults(func=cmd_listar)
    sub.add_parser("cursor", help="monitor que contiene el cursor (solo X11)") \
       .set_defaults(func=cmd_cursor)

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
