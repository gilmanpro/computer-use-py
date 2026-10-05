# -*- coding: utf-8 -*-
"""monitores.py — Mapa de monitores y pantalla virtual (skill computer-use-py).

ctypes puro: EnumDisplayMonitors + GetMonitorInfoW + GetSystemMetrics
(SM_X/Y/CX/CYVIRTUALSCREEN) + GetCursorPos. Sin dependencias nuevas: la unica
importacion propia es _compartido (JSON canonico y DPI per-monitor fijado
ANTES de leer metricas, para que el mapa este en pixeles fisicos igual que
las capturas). Marco: referencias/monitores-multi.md.

Coordenadas del ESPACIO VIRTUAL: el origen logico (0,0) es el vertice
sup-izq del monitor PRIMARIO; un monitor a la izquierda/arriba tiene
rectangulos NEGATIVOS y sus coordenadas siguen siendo validas.

Salida: JSON por stdout; errores JSON con "error". Subcomandos:
  listar  Cada monitor (nombre, izq/top/der/bot, work, primario, tamano)
          + bloque "virtual" (origen y bounding de todos los monitores).
  cursor  Que monitor contiene el cursor (GetCursorPos, via solo lectura).

Ejemplos (desde la carpeta computer-use-py):
  py scripts/monitores.py listar
  py scripts/monitores.py cursor
"""

import argparse
import ctypes
from ctypes import wintypes

import _compartido as c  # DPI per-monitor + json_out/fail (no mueve el cursor)


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
        "marco": "pantalla virtual (GetCursorPos)",
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


def construir_parser():
    parser = argparse.ArgumentParser(
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
