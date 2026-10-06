# -*- coding: utf-8 -*-
"""monitores.py — Mapa de monitores y pantalla virtual en macOS (skill
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
  python3 scripts/macos/monitores.py listar
  python3 scripts/macos/monitores.py cursor
"""

import argparse
import json
import re
import subprocess

import _compartido_mac as c


def _mons_quartz():
    """Monitores via pyobjc Quartz o None (no aborta)."""
    try:
        return c.monitores_logicos()
    except SystemExit:
        raise
    except Exception:
        return None


def _mons_profiler():
    """Monitores via `system_profiler SPDisplaysDataType -json` [runtime].

    Datos disponibles: nombre y resolucion; POSICIONES NO: se dejan en None
    y el JSON avisa que hace falta pyobjc-framework-Quartz para el mapa
    virtual. Los claves exactas del JSON varian por macOS: se busca de forma
    tolerante (cualquier cadena "A x B" y flags 'main'). [runtime]
    """
    try:
        p = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        return None
    try:
        data = json.loads((p.stdout or b"").decode("utf-8", errors="replace"))
        entradas = data.get("SPDisplaysDataType", [])
    except Exception:
        return None
    out = []
    for e in entradas:
        for d in (e.get("spdisplays_displays") or []):
            if not isinstance(d, dict):
                continue
            nombre = d.get("_name") or d.get("spdisplays_display-name") or \
                d.get("seldisplay") or "pantalla"
            res = d.get("spdisplays_resolution") or \
                d.get("kCGDisplayResolution") or ""
            w = h = None
            m = re.search(r"(\d+)\s*x\s*(\d+)", str(res))
            if m:
                w, h = int(m.group(1)), int(m.group(2))
            main = str(d.get("spdisplays_main", "")).lower() in (
                "yes", "spdisplays_yes", "1", "true")
            out.append({
                "numero": None, "nombre": str(nombre),
                "izq": None, "top": None, "der": None, "bot": None,
                "ancho": w, "alto": h, "work": None, "primario": bool(main),
            })
    # variantes sin sublista "spdisplays_displays": tratar la entrada misma
    if not out:
        for e in entradas:
            if not isinstance(e, dict):
                continue
            nombre = e.get("_name") or "GPU"
            out.append({
                "numero": None, "nombre": str(nombre),
                "izq": None, "top": None, "der": None, "bot": None,
                "ancho": None, "alto": None, "work": None,
                "primario": not out,
            })
    if not out:
        return None
    for i, m in enumerate(out):
        m["indice"] = i
    return out


def _mons_osascript():
    """Unico monitor (principal) via bounds del desktop [runtime].

    VERIFICADO solo en la sintaxis general de System Events (guia Apple);
    'desktop picture'/bounds no esta en el capitulo leido: ruta de último
    recurso marcada [runtime].
    """
    rc, out, err = c.osascript(
        'return "OK:" & (bounds of desktop picture of desktop 1)', [])
    if rc != 0 or not out.startswith("OK:"):
        rc, out, err = c.osascript(
            'tell application "Finder" to return '
            'bounds of window of desktop', [])
    if rc != 0 or not out:
        return None
    cuerpo = out[3:] if out.startswith("OK:") else out
    nums = [int(n) for n in re.findall(r"-?\d+", cuerpo)]
    if len(nums) < 4:
        return None
    x0, y0, x1, y1 = nums[:4]
    w, h = x1 - x0, y1 - y0
    return [{
        "numero": None, "nombre": "Principal (via osascript)",
        "izq": x0, "top": y0, "der": x1, "bot": y1,
        "ancho": w, "alto": h, "work": [x0, y0, x1, y1],
        "primario": True, "indice": 0,
    }]


def _colectar():
    """(monitores, via) con la cadena de fallback de la cabecera."""
    if c.quartz_disponible():
        mons = _mons_quartz()
        if mons:
            return mons, "quartz"
    mons = _mons_profiler()
    if mons:
        return mons, "system_profiler"
    mons = _mons_osascript()
    if mons:
        return mons, "osascript"
    c.fail("Sin Quartz NI system_profiler NI osascript utiles: instala "
           "pyobjc-framework-Quartz (pip3 install pyobjc-framework-Quartz) "
           "para el mapa virtual completo.")


def _bounding(mons):
    """Bounding desde rects conocidos; si faltan positions, usa (0,0)+tamanos."""
    rects = [m for m in mons if m["izq"] is not None]
    if rects:
        x0 = min(m["izq"] for m in rects)
        y0 = min(m["top"] for m in rects)
        x1 = max(m["der"] for m in rects)
        y1 = max(m["bot"] for m in rects)
        return {"x": x0, "y": y0, "ancho": x1 - x0, "alto": y1 - y0}
    # via sin posiciones: bounding aproximado = union apilada a la derecha
    ancho = sum((m["ancho"] or 0) for m in mons)
    alto = max([(m["alto"] or 0) for m in mons] or [0])
    return {"x": 0, "y": 0, "ancho": ancho, "alto": alto}


def cmd_listar(args):
    mons, via = _colectar()
    v = _bounding(mons)
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


def cmd_cursor(args):
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
    mons, via = _colectar()
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


def construir_parser():
    parser = c.Parser(
        prog="monitores.py (macOS)",
        description="Mapa de monitores y pantalla virtual en PUNTOS LOGICOS "
                    "del espacio global (Quartz; fallback system_profiler/"
                    "osascript, solo lectura).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Salida:")[0] if __doc__ else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True,
                                metavar="SUBCOMANDO")

    sub.add_parser("listar", help="monitores + bounding virtual") \
       .set_defaults(func=cmd_listar)
    sub.add_parser("cursor", help="monitor que contiene el cursor") \
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
