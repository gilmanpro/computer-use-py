# -*- coding: utf-8 -*-
"""pantalla.py — Capturas e inspección visual (skill computer-use-py).

Coordenadas: pixeles del ESPACIO VIRTUAL (origen (0,0) = vértice
sup-izq del monitor PRIMARIO; negativos hacia la izquierda/arriba con
monitores vecinos). Mapa exacto de la máquina: monitores.py listar.
Las capturas por monitor/región usan PIL.ImageGrab.grab(bbox=...,
all_screens=True), que SÍ traduce coordenadas negativas; NO se usa
pyautogui.screenshot(region=) para el secundario: su crop no descuenta el
offset del bounding virtual y produce negro (VERIFICADO en código; ver
references/monitores-multi.md). En un equipo de un solo monitor todo coincide
con el marco histórico del primario.

Las capturas se guardan por defecto en el .tmp/capturas/ de ESTA skill
(contenido jamás commiteable; el JSON siempre devuelve la ruta absoluta).
Salida: JSON por stdout; los errores son JSON con "error".

Subcomandos:
  capturar   PNG de la pantalla: por defecto el primario (ruta histórica);
             --monitor <indice|primario|virtual|nombre>, --region (coords
              virtuales, acepta negativos) y --max-lado N (thumbnail LANCZOS
              ANTES de guardar). El JSON de TODA captura trae "origen"
              (esquina sup-izq en coords virtuales), "px_por_unidad_coord"
              (factor TOTAL imagen->coordenada: la unica cifra para
              re-escalar), "escala" (solo el recorte --max-lado), "marco"
              y "regla".
  tamano     Resolución del monitor primario; con --virtual, el bounding
             de todos los monitores y su origen.
  posicion   Posición actual del cursor (GetCursorPos: dentro del primario
             coincide con el marco histórico).
  pixel      Color RGB de un pixel en coords VIRTUALES (negativos vía
             ImageGrab de 1 px; el primario sigue por pyautogui.pixel).
  esperar    Pausa: fija con --milisegundos N (default 400, cap 30000) o
             adaptativa con --pixel X Y --color r,g,b y --cambia|--estable M
             (poll ~100 ms; el FAILSAFE sigue intacto).
  localizar  Busca una imagen en pantalla (locateOnScreen). pyscreeze es
             PRIMARIO-ONLY: solo ve el monitor primario (documentado, sin
             cambiar la conducta).

Ejemplos (desde la carpeta computer-use-py):
  py scripts/pantalla.py capturar
  py scripts/pantalla.py capturar --monitor 1 --max-lado 1280
  py scripts/pantalla.py capturar --monitor virtual
  py scripts/pantalla.py capturar --region -800 0 600 400 --archivo trozo.png
  py scripts/pantalla.py tamano --virtual
  py scripts/pantalla.py esperar --milisegundos 600
  py scripts/pantalla.py esperar --pixel 300 200 --color 255,255,255 --cambia --timeout 5
  py scripts/pantalla.py localizar boton.png --confidence 0.9
"""

import argparse
import os
import time

import _compartido as c  # importa pyautogui ya con DPI + FAILSAFE + PAUSE
import pyautogui
from PIL import Image, ImageGrab

_REGLA_REESCALADO = (
    "coordenada_virtual_x = origen[0] + x_en_la_imagen / px_por_unidad_coord; "
    "coordenada_virtual_y = origen[1] + y_en_la_imagen / px_por_unidad_coord. "
    "'px_por_unidad_coord' es el factor TOTAL imagen->coordenada (ya incluye "
    "el recorte --max-lado; en Windows equivale a 'escala'), asi que UN unico "
    "campo basta para re-escalar: 'escala'/'escala_y' quedan SOLO como factor "
    "del thumbnail --max-lado. Con 'origen' distinto de [0, 0] suma el offset "
    "de la captura (coordenadas de imagen -> coordenadas virtuales). Marco: "
    "'marco' enum del JSON (px_fisicos_virtual en Windows)."
)


def _pixel_virtual(x, y):
    """(r, g, b) de UN pixel en coords virtuales vía ImageGrab (bbox traduce
    negativos; all_screens=True desde Pillow 6.2.0, ver doc oficial)."""
    im = ImageGrab.grab(bbox=(int(x), int(y), int(x) + 1, int(y) + 1),
                        all_screens=True)
    if im.mode != "RGB":
        im = im.convert("RGB")
    return im.getpixel((0, 0))


def _color_coincide(x, y, color, tol):
    """Comparación de un pixel (coords VIRTUALES) con tolerancia por canal.

    Dentro del monitor primario se usa pyautogui.pixelMatchesColor (semántica
    verificada); fuera de él no: mide solo el primario, así que se lee 1 px
    con ImageGrab y se compara a mano con la misma tolerancia.
    """
    m = c._monitor_contiene(x, y)
    if m is not None and m["primario"]:
        return bool(pyautogui.pixelMatchesColor(int(x), int(y), tuple(color),
                                                tolerance=tol))
    r, g, b = _pixel_virtual(x, y)
    cr, cg, cb = color
    return abs(r - cr) <= tol and abs(g - cg) <= tol and abs(b - cb) <= tol


def _parsear_color(texto):
    partes = texto.split(",")
    if len(partes) != 3:
        c.fail('Color con formato "r,g,b" (tres enteros 0-255 separados por comas, '
               'sin espacios), no %r.' % texto)
    try:
        valores = [int(p) for p in partes]
    except ValueError:
        c.fail('Color con componentes no enteros: %r.' % texto)
    for v in valores:
        if not 0 <= v <= 255:
            c.fail("Color fuera de rango 0-255: %r." % texto)
    return tuple(valores)


def _checar_aborto_espera():
    """Corta una espera larga si el humano pidio parar (bandera de vigilar.py)."""
    c.checar_abort("esperar interrumpida")


def _resolver_monitor(valor):
    """--monitor: None si 'virtual' (bounding completo) | dict del monitor.

    Acepta el índice (según el orden de monitores.py listar), 'primario' o
    una subcadena del nombre (p. ej. 'DISPLAY1'), case-insensitive.
    """
    v = valor.strip().lower()
    if v in ("virtual", "toda", "todas", "todo"):
        return None
    mons = c.monitores()
    if v in ("primario", "primary"):
        for m in mons:
            if m["primario"]:
                return m
        c.fail("Ningún monitor figura como primario (dwFlags inesperado). "
               "Revisa monitores.py listar.")
    try:
        idx = int(valor)
    except ValueError:
        idx = None
    if idx is not None:
        if 0 <= idx < len(mons):
            return mons[idx]
        c.fail("Índice de monitor %d fuera de rango (0..%d). "
               "Mapa: monitores.py listar." % (idx, len(mons) - 1))
    coincidencias = [m for m in mons if v in m["nombre"].lower()]
    if len(coincidencias) == 1:
        return coincidencias[0]
    if len(coincidencias) > 1:
        c.fail("La subcadena %r coincide con varios monitores (%s): usa el "
               "índice." % (valor, [m["nombre"] for m in coincidencias]))
    c.fail("Ningún monitor tiene el nombre %r (subcadena de szDevice). "
           "Mapa: monitores.py listar." % valor)


def cmd_capturar(args):
    origen = [0, 0]
    if args.monitor is not None:
        m = _resolver_monitor(args.monitor)
        if m is None:  # pantalla virtual completa
            v = c.tamano_virtual()
            bbox = (v["x"], v["y"], v["x"] + v["ancho"], v["y"] + v["alto"])
            origen = [v["x"], v["y"]]
        elif args.region is not None:
            x, y, w, h = args.region
            if w <= 0 or h <= 0:
                c.fail("Región inválida: ancho/alto deben ser > 0.")
            if x < 0 or y < 0 or x + w > m["ancho"] or y + h > m["alto"]:
                c.fail("Región (%d, %d, %d, %d) fuera del monitor %r "
                       "(%dx%d): con --monitor la region es RELATIVA a ese "
                       "monitor (origen 0,0 de su vértice sup-izq)."
                       % (x, y, w, h, m["nombre"], m["ancho"], m["alto"]))
            bbox = (m["izq"] + x, m["top"] + y, m["izq"] + x + w, m["top"] + y + h)
            origen = [bbox[0], bbox[1]]
        else:
            bbox = (m["izq"], m["top"], m["der"], m["bot"])
            origen = [m["izq"], m["top"]]
        imagen = ImageGrab.grab(bbox=bbox, all_screens=True)
    elif args.region is not None:
        x, y, w, h = args.region
        if w <= 0 or h <= 0:
            c.fail("Región inválida: ancho/alto deben ser > 0 (x e y ACEPTAN "
                   "negativos: son coordenadas del espacio virtual).")
        v = c.tamano_virtual()
        if not (v["x"] <= x and v["y"] <= y
                and x + w <= v["x"] + v["ancho"]
                and y + h <= v["y"] + v["alto"]):
            c.fail("Región (%d, %d, %d, %d) fuera del bounding virtual "
                   "(x %d..%d, y %d..%d). Mapa: monitores.py listar."
                   % (x, y, w, h, v["x"], v["x"] + v["ancho"] - 1,
                      v["y"], v["y"] + v["alto"] - 1))
        bbox = (x, y, x + w, y + h)
        origen = [x, y]
        imagen = ImageGrab.grab(bbox=bbox, all_screens=True)
    else:
        # Comportamiento histórico intacto: captura del monitor primario.
        imagen = pyautogui.screenshot()

    if args.archivo:
        # Convencion de la skill: los PNG viven en el .tmp de ESTA skill. Un
        # nombre pelado (sin separador de carpeta) se resuelve dentro de
        # .tmp/capturas; una ruta con directorio (relativo o absoluto) se
        # respeta tal cual para usos explicitos.
        destino = args.archivo
        if not (os.path.dirname(destino) or destino.startswith(("\\", "/"))):
            destino = os.path.join(c.asegurar_capturas(), destino)
        ruta = os.path.abspath(destino)
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    else:
        ruta = os.path.join(
            c.asegurar_capturas(),
            "captura_%s.png" % time.strftime("%Y%m%d_%H%M%S"),
        )
    fis_w, fis_h = int(imagen.width), int(imagen.height)
    escala_x, escala_y = 1.0, 1.0
    if args.max_lado is not None:
        if args.max_lado < 16:
            c.fail("--max-lado demasiado pequeño (mínimo 16 px).")
        # LANCZOS conserva el aspecto y baja tokens: reescala con la "regla".
        imagen.thumbnail((args.max_lado, args.max_lado), Image.LANCZOS)
        escala_x = fis_w / float(imagen.width)
        escala_y = fis_h / float(imagen.height)
    imagen.save(ruta)
    pw, ph = c.tamano_pantalla()
    px, py = c.posicion_cursor()
    c.json_out({
        "ok": True,
        "archivo": ruta,
        "ancho": int(imagen.width),
        "alto": int(imagen.height),
        "fisico": {"ancho": fis_w, "alto": fis_h},
        "origen": origen,
        "escala": round(escala_x, 6),
        "escala_y": round(escala_y, 6),
        # P0-3/P0-4: factor TOTAL imagen->coordenada (en Windows == escala) y
        # marco canonico. `escala` queda reservada al thumbnail --max-lado.
        "px_por_unidad_coord": round(escala_x, 6),
        "marco": c.MARCO,
        "regla": _REGLA_REESCALADO,
        "pantalla": {"ancho": pw, "alto": ph},
        "cursor": {"x": px, "y": py},
        "nota": "leer este PNG con vision y decidir desde ahi; NO hardcodear "
                "coordenadas de sesiones anteriores; 'origen' es la esquina "
                "sup-izq de la captura en coordenadas VIRTUALES: súmala al "
                "reescalar coords de imagen a coords de clic",
    })


def cmd_tamano(args):
    if args.virtual:
        v = c.tamano_virtual()
        c.json_out({
            "ancho": v["ancho"],
            "alto": v["alto"],
            "origen": [v["x"], v["y"]],
            "marco": c.MARCO,
            "nota": "marco historico: pantalla VIRTUAL, bounding de todos los "
                     "monitores (SM_CX/CYVIRTUALSCREEN; origen "
                     "SM_X/YVIRTUALSCREEN). Rectangulo por monitor: "
                     "monitores.py listar",
        })
        return
    w, h = c.tamano_pantalla()
    c.json_out({
        "ancho": w,
        "alto": h,
        "marco": c.MARCO,
        "nota": "pixels fisicos del monitor PRIMARIO (GetSystemMetrics 0/1); "
                "el espacio virtual completo (con negativos hacia la "
                "izquierda) es tamano --virtual",
    })


def cmd_posicion(args):
    x, y = c.posicion_cursor()
    c.json_out({"x": x, "y": y, "marco": c.MARCO,
                "nota": "monitor primario (pyautogui; coincide con el virtual "
                        "dentro del primario)"})


def cmd_pixel(args):
    if not c.dentro_de_virtual(args.x, args.y):
        v = c.tamano_virtual()
        c.fail("Pixel (%d, %d) fuera de la pantalla virtual "
               "(x %d..%d, y %d..%d). Mapa: monitores.py listar."
               % (args.x, args.y, v["x"], v["x"] + v["ancho"] - 1,
                  v["y"], v["y"] + v["alto"] - 1))
    m = c._monitor_contiene(args.x, args.y)
    if m is None:
        c.fail("Pixel (%d, %d) no cae dentro de ningún monitor (hueco del "
               "bounding virtual con monitores desalineados)."
               % (args.x, args.y))
    if m["primario"]:
        r, g, b = pyautogui.pixel(int(args.x), int(args.y))
        via = "pyautogui.pixel (monitor primario: ruta histórica)"
    else:
        r, g, b = _pixel_virtual(args.x, args.y)
        via = ("ImageGrab 1 px all_screens (monitor %s: pyautogui.pixel mide "
               "solo el primario)" % m["nombre"])
    c.json_out({"x": args.x, "y": args.y, "r": int(r), "g": int(g), "b": int(b),
                "marco": c.MARCO, "via": via,
                "nota": "marco historico: pantalla virtual"})


def cmd_esperar(args):
    c.checar_abort("esperar")
    c.checar_pausa()  # P1-5: si hay PAUSA, la espera arranca al reanudarse
    inicio = time.monotonic()
    if args.pixel is not None:
        if args.color is None:
            c.fail("El modo adaptativo requiere --pixel X Y y --color r,g,b juntos.")
        if not args.cambia and args.estable is None:
            c.fail("Indica --cambia o --estable M (ms de coincidencia "
                   "continua) junto a --pixel y --color.")
        x, y = args.pixel
        if not c.dentro_de_virtual(x, y):
            v = c.tamano_virtual()
            c.fail("Pixel (%d, %d) fuera de la pantalla virtual "
                   "(x %d..%d, y %d..%d)." % (x, y, v["x"], v["x"] + v["ancho"] - 1,
                                              v["y"], v["y"] + v["alto"] - 1))
        if c._monitor_contiene(x, y) is None:
            c.fail("Pixel (%d, %d) no cae dentro de ningún monitor (hueco del "
                   "bounding virtual)." % (x, y))
        color = _parsear_color(args.color)
        tol = args.tolerancia
        if not 0 <= tol <= 255:
            c.fail("--tolerancia debe estar entre 0 y 255.")
        limite = min(max(args.timeout, 0.5), 120.0)
        racha_ini = None
        cumplida = False
        while True:
            coincide = _color_coincide(x, y, color, tol)
            if args.cambia:
                cumplida = not coincide
            else:
                if coincide:
                    if racha_ini is None:
                        racha_ini = time.monotonic()
                    cumplida = (time.monotonic() - racha_ini) * 1000.0 >= args.estable
                else:
                    racha_ini = None
                    cumplida = False
            if cumplida or (time.monotonic() - inicio) >= limite:
                break
            _checar_aborto_espera()
            time.sleep(0.1)
        _checar_aborto_espera()
        c.json_out({
            "cumplida": bool(cumplida),
            "ms_esperados": int((time.monotonic() - inicio) * 1000),
            "modo": "cambia" if args.cambia else "estable",
            "pixel": [int(x), int(y)],
            "color": list(color),
            "tolerancia": tol,
            "timeout_s": limite,
            "marco": c.MARCO,
            "nota": "marco historico 'pantalla virtual'; poll ~100 ms; timeout agotado => cumplida=false SIN error "
                    "(el agente decide); --estable M pide M ms de coincidencia "
                    "continua; FAILSAFE intacto",
        })
        return
    if args.color is not None or args.cambia or args.estable is not None:
        c.fail("--color/--cambia/--estable solo valen con --pixel X Y; para "
               "una pausa fija usa solo --milisegundos N.")
    ms = min(max(int(args.milisegundos), 0), 30000)
    restante = ms
    while restante > 0:
        paso = min(restante, 200)
        time.sleep(paso / 1000.0)
        restante -= paso
        _checar_aborto_espera()
    c.json_out({
        "cumplida": True,
        "ms_esperados": ms,
        "modo": "fijo",
        "marco": c.MARCO,
        "nota": "sueño simple (default 400 ms, cap 30000) para dejar renderizar "
                "la UI; FAILSAFE intacto; la bandera ABORT de vigilar.py corta "
                "la espera; PAUSA la posterga",
    })


def cmd_localizar(args):
    if not os.path.isfile(args.imagen):
        c.fail("La imagen a buscar no existe: %s" % os.path.abspath(args.imagen))
    kwargs = {}
    if args.region is not None:
        kwargs["region"] = tuple(args.region)
    aviso = None
    if args.confidence is not None:
        if not (0.0 <= args.confidence <= 1.0):
            c.fail("confidence debe estar entre 0.0 y 1.0.")
        kwargs["confidence"] = args.confidence
    try:
        try:
            box = pyautogui.locateOnScreen(args.imagen, **kwargs)
        except NotImplementedError:
            # confidence sin OpenCV lanza NotImplementedError (verificado en
            # pyscreeze): degradar a coincidencia exacta y avisar.
            kwargs.pop("confidence", None)
            box = pyautogui.locateOnScreen(args.imagen, **kwargs)
            aviso = ("confidence descartado: instalar opencv-python "
                     "(py -m pip install opencv-python) o buscar por vision; "
                     "se degrado a coincidencia exacta")
    except pyautogui.ImageNotFoundException:
        box = None
    limite_marco = ("pyscreeze captura SOLO el monitor PRIMARIO "
                    "(primario-only, verificado): en un secundario no "
                    "encuentra; usa capturar --monitor + vision")
    if box is None:
        c.json_out({
            "encontrado": False,
            "imagen": os.path.abspath(args.imagen),
            "marco": c.MARCO,
            "nota": "locate exige pixeles casi identicos (tema/DPI/antialiasing "
                    "lo rompen); para el loop normal usa capturar + vision. "
                    + limite_marco,
        })
        return
    centro = pyautogui.center(box)
    c.json_out({
        "encontrado": True,
        "imagen": os.path.abspath(args.imagen),
        "box": [int(box.left), int(box.top), int(box.width), int(box.height)],
        "centro": [int(centro.x), int(centro.y)],
        "marco": c.MARCO,
        "aviso": aviso,
        "nota": limite_marco,
    })


def construir_parser():
    parser = c.Parser(
        prog="pantalla.py",
        description="Capturas e inspeccion de pantalla (PyAutoGUI + PIL "
                    "ImageGrab). Coordenadas = pixeles del ESPACIO VIRTUAL "
                    "(origen = monitor primario; negativos hacia la "
                    "izquierda/arriba). Mapa: monitores.py listar.",
        epilog=__doc__.split("Subcomandos:")[1] if __doc__ and "Subcomandos:" in __doc__ else None,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    p = sub.add_parser("capturar", help="guardar un PNG (pantalla, monitor, "
                       "virtual o region en coords virtuales)")
    p.add_argument("--region", type=int, nargs=4, metavar=("X", "Y", "ANCHO", "ALTO"),
                   help="recorte en coordenadas VIRTUALES (acepta negativos; "
                        "va por ImageGrab all_screens). Con --monitor, la "
                        "region es RELATIVA a ese monitor")
    p.add_argument("--monitor", metavar="OBJETO",
                   help="indice (0,1,...), 'primario', 'virtual' (bounding "
                        "completo) o subcadena del nombre (p. ej. DISPLAY1); "
                        "ver monitores.py listar")
    p.add_argument("--max-lado", dest="max_lado", type=int, metavar="N",
                   help="thumbnail LANCZOS de lado maximo N ANTES de guardar "
                        "(ahorra tokens): RE-ESCALA con 'escala'/'regla' del JSON")
    p.add_argument("--archivo", help="nombre o ruta destino del PNG: un nombre "
                   "pelado cae en .tmp/capturas de ESTA skill (convencion); con "
                   "directorio se respeta. Por defecto "
                   ".tmp/capturas/captura_<fecha_hora>.png")
    p.set_defaults(func=cmd_capturar)

    p = sub.add_parser("tamano", help="resolucion del primario (o --virtual)")
    p.add_argument("--virtual", action="store_true",
                   help="bounding de TODOS los monitores + origen virtual")
    p.set_defaults(func=cmd_tamano)

    p = sub.add_parser("posicion", help="posicion actual del cursor")
    p.set_defaults(func=cmd_posicion)

    p = sub.add_parser("pixel", help="color RGB de un pixel (coords virtuales)")
    p.add_argument("x", type=int, help="coordenada X virtual (negativa = hacia la izquierda)")
    p.add_argument("y", type=int, help="coordenada Y virtual")
    p.set_defaults(func=cmd_pixel)

    p = sub.add_parser("esperar", help="pausa fija (--milisegundos) o adaptativa "
                       "por pixel (--pixel --color --cambia|--estable)")
    p.add_argument("--milisegundos", type=int, default=400, metavar="N",
                   help="pausa fija en ms (default 400, cap 30000)")
    p.add_argument("--pixel", type=int, nargs=2, metavar=("X", "Y"),
                   help="espera adaptativa: pixel a vigilar (coords virtuales)")
    p.add_argument("--color", metavar="R,G,B",
                   help="color esperado (p. ej. 255,255,255); con --pixel")
    p.add_argument("--tolerancia", type=int, default=0, metavar="T",
                   help="tolerancia por canal 0-255 (default 0)")
    grupo = p.add_mutually_exclusive_group()
    grupo.add_argument("--cambia", action="store_true",
                       help="cumplir cuando el pixel DEJE de coincidir con --color")
    grupo.add_argument("--estable", type=int, metavar="M",
                       help="cumplir tras M ms de coincidencia continua con --color")
    p.add_argument("--timeout", type=float, default=10.0, metavar="S",
                   help="segundos maximos del poll (default 10, cap 120; "
                        "agotarlo NO es error: cumplida=false)")
    p.set_defaults(func=cmd_esperar)

    p = sub.add_parser("localizar", help="buscar una imagen en pantalla (locateOnScreen; "
                       "SOLO monitor primario)")
    p.add_argument("imagen", help="ruta del PNG/JPG a buscar")
    p.add_argument("--region", type=int, nargs=4, metavar=("X", "Y", "ANCHO", "ALTO"),
                   help="limitar la busqueda (acelera: locate cuesta 1-2 s); "
                        "marco del PRIMARIO (pyscreeze no ve el secundario)")
    p.add_argument("--confidence", type=float,
                   help="umbral 0-1; REQUIERE opencv-python, sin el degrada a "
                        "coincidencia exacta")
    p.set_defaults(func=cmd_localizar)

    return parser


def main():
    args = construir_parser().parse_args()
    try:
        args.func(args)
    except pyautogui.FailSafeException as exc:
        c.fallar_por_failsafe(exc)
    except SystemExit:
        raise
    except Exception as exc:
        c.fail("%s: %s" % (type(exc).__name__, exc))


if __name__ == "__main__":
    main()
