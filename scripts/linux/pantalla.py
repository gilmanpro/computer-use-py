# -*- coding: utf-8 -*-
"""pantalla.py — Capturas e inspeccion visual del dominio LINUX (computer-use-py).

Superficie 100 % Python con el MISMO contrato JSON del dominio Windows; la
implementacion interna elige la ruta segun la sesion (references/linux-python.md):
  X11     pyautogui.screenshot() (debajo Pillow ImageGrab via XCB o scrot
          segun pyscreeze [runtime]); el recorte por monitor se hace con PIL
          SOBRE la captura completa usando el offset xrandr — la traduccion
          de region= de pyscreeze en multi-monitor Linux NO esta verificada
          (se evita la trampa documentada en Windows).
  Wayland grim (man verbatim: "-g \"<x>,<y> <width>x<height>\" Set the region
          to capture, in layout coordinates"; "-o <output>"; "-" = stdout),
          que se recorta/lee con PIL cuando hace falta.

Coordenadas: LAYOUT. En X11 (0,0) = vertice sup-izq del SCREEN (el primario
puede NO estar en 0,0; mapa: monitores.py listar). En Wayland sway/hypr los
offsets los fija el compositor y puede haber negativos [runtime].

Las capturas se guardan por defecto en .tmp/capturas/ de ESTA skill (el JSON
siempre devuelve la ruta absoluta). Salida: JSON por stdout; errores JSON con
"error". pyautogui se importa LAZY para que el fallo de import responda JSON
accionable (nunca traceback) y fijar FAILSAFE=True + PAUSE=0.15 como el padre.

Subcomandos:
   capturar   PNG: --monitor <indice|primario|virtual|nombre>, --region (coords
              de layout x y w h), --max-lado N (thumbnail LANCZOS), --archivo.
              El JSON de TODA captura trae "origen", "px_por_unidad_coord"
              (factor TOTAL imagen->coordenada; unica cifra para re-escalar),
              "factor_grim" (Wayland), "escala" (solo --max-lado), "marco" y
              "regla".
  tamano     Resolucion del primario; con --virtual, el bounding de layout.
  posicion   Posicion actual del cursor (solo X11: xdotool getmouselocation).
  pixel      Color RGB de un pixel: X11 pyautogui.pixel; Wayland grim 1x1 a
             stdout (man: "-" escribe la imagen por stdout) + PIL.
  esperar    Pausa fija --milisegundos N (default 400, cap 30000) o adaptativa
             --pixel X Y --color r,g,b con --cambia|--estable M (poll ~100 ms).
  localizar  Busca una imagen (locateOnScreen). SOLO X11: en Wayland
             pyautogui no inyecta/lee nativo => error honesto.

Ejemplos (desde la carpeta computer-use-py, en la maquina Linux):
  python3 scripts/linux/pantalla.py capturar
  python3 scripts/linux/pantalla.py capturar --monitor 1 --max-lado 1280
  python3 scripts/linux/pantalla.py capturar --monitor virtual
  python3 scripts/linux/pantalla.py capturar --region 1920 0 600 400
  python3 scripts/linux/pantalla.py tamano --virtual
  python3 scripts/linux/pantalla.py esperar --milisegundos 600
  python3 scripts/linux/pantalla.py esperar --pixel 300 200 --color 255,255,255 --cambia
  python3 scripts/linux/pantalla.py localizar boton.png --confidence 0.9
"""

import argparse
import io
import json
import os
import shutil
import time

import _compartido_linux as c

_REGLA_REESCALADO = (
    "coordenada_layout_x = origen[0] + x_en_la_imagen / px_por_unidad_coord; "
    "coordenada_layout_y = origen[1] + y_en_la_imagen / px_por_unidad_coord. "
    "'px_por_unidad_coord' es el factor TOTAL imagen->coordenada: ya incluye "
    "el recorte --max-lado y, en Wayland, el factor de escala global que grim "
    "aplica ('factor_grim'; si es null porque la fuente no lo informa, el "
    "factor no verificado queda SOLO en esta formula: verifica con una "
    "captura de prueba). 'escala'/'escala_y' quedan SOLO como factor del "
    "thumbnail --max-lado. Con 'origen' distinto del screen, suma el offset "
    "(coords de imagen -> coords de layout). Marco: 'marco' enum del JSON."
)


def _grim_factor():
    """Factor de escala global que grim aplica en Wayland (man grim: escala
    max. de los outputs [runtime]). Fuente honesta: swaymsg -t get_outputs
    campo 'scale'. Sin dato => None (no inventar; la nota/`regla` avisan)."""
    if not shutil.which("swaymsg"):
        return None
    r = c.run("swaymsg", ["-t", "get_outputs"], timeout=10.0)
    if r["rc"] != 0:
        return None
    try:
        datos = json.loads(r["stdout"])
        scales = []
        for o in datos:
            if isinstance(o, dict) and o.get("active") is not False:
                try:
                    scales.append(float(o.get("scale", 1) or 1))
                except (TypeError, ValueError):
                    pass
        return max(scales) if scales else None
    except ValueError:
        return None


def _pyautogui():
    """Import perezoso delegado al helper unico de la rama (P2-2): conserva el
    MENSAJE CANONICO aqui definido (movido a _compartido_linux.py). Cualquier
    fallo responde JSON accionable (Wayland sin XWayland, DISPLAY vacia,
    librerias sin instalar), no traceback."""
    return c.pyautogui_lazy()


def _pillow():
    """Import perezoso de (Image, ImageGrab) con hint accionable."""
    try:
        from PIL import Image, ImageGrab
    except ImportError as exc:
        c.fail("Falta Pillow: %s. Instalar: python3 -m pip install pillow "
               ">= 9.2 (ImageGrab Linux usa XCB [runtime])." % exc)
    return Image, ImageGrab


def _cursor_layout():
    """(x, y) del cursor solo en X11 (xdotool shell); None fuera de X11."""
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


# _parsear_color y la bandera de espera ('esperar interrumpida') son genericos
# (viven en _core, identicos en las 3 ramas): se llaman via c.parsear_color y
# c.checar_aborto_espera.


def _resolver_monitor(valor):
    """--monitor: None si 'virtual' (bounding) | dict del monitor (mismo
    contrato que el padre: indice, 'primario' o subcadena del nombre).

    El algoritmo es el generico de _core.resolver_monitor; aqui quedan la
    FUENTE de la lista (xrandr/sway/hypr) y los TEXTOS con jerga de Linux
    ("*" de xrandr, primary de sway/hypr)."""
    return c.resolver_monitor(
        valor, c.monitores,
        sin_primario="Ningun monitor figura como primario (ni xrandr '*' ni "
                     "sway/hypr primary): trata el primero como tal o revisa "
                     "monitores.py listar.",
        indice_rango="Indice de monitor %d fuera de rango (0..%d). "
                     "Mapa: monitores.py listar.",
        ambiguo="La subcadena %r coincide con varios monitores (%s): usa el "
                "indice.",
        sin_nombre="Ningun monitor tiene el nombre %r. Mapa: monitores.py "
                   "listar.")


def _captura_x11(args):
    """(imagen PIL, origen_layout) en X11: captura completa + crop PIL."""
    pa = _pyautogui()
    try:
        imagen = pa.screenshot()
    except Exception as exc:
        c.fail("pyautogui.screenshot() fallo en X11: %s: %s. Rutas tipicas: "
               "Pillow ImageGrab (XCB) o scrot — instalar pillow / scrot y "
               "reintentar (refs linux-python.md §9)."
               % (type(exc).__name__, exc))
    v = c.tamano_virtual()
    if args.monitor is not None:
        m = _resolver_monitor(args.monitor)
        if m is None:
            return imagen, [v["x"], v["y"]]
        if args.region is not None:
            x, y, w, h = args.region
            if (x < 0 or y < 0 or x + w > m["ancho"] or y + h > m["alto"]):
                c.fail("Region (%d, %d, %d, %d) fuera del monitor %r "
                       "(%dx%d): con --monitor la region es RELATIVA a ese "
                       "monitor." % (x, y, w, h, m["nombre"], m["ancho"],
                                     m["alto"]))
            bbox = (m["izq"] + x - v["x"], m["top"] + y - v["y"],
                    m["izq"] + x + w - v["x"], m["top"] + y + h - v["y"])
            origen = [m["izq"] + x, m["top"] + y]
        else:
            bbox = (m["izq"] - v["x"], m["top"] - v["y"],
                    m["der"] - v["x"], m["bot"] - v["y"])
            origen = [m["izq"], m["top"]]
        return imagen.crop(bbox), origen
    if args.region is not None:
        x, y, w, h = args.region
        if w <= 0 or h <= 0:
            c.fail("Region invalida: ancho/alto deben ser > 0.")
        if not (v["x"] <= x and v["y"] <= y
                and x + w <= v["x"] + v["ancho"]
                and y + h <= v["y"] + v["alto"]):
            c.fail("Region (%d, %d, %d, %d) fuera del bounding de layout "
                   "(x %d..%d, y %d..%d). Mapa: monitores.py listar."
                   % (x, y, w, h, v["x"], v["x"] + v["ancho"] - 1,
                      v["y"], v["y"] + v["alto"] - 1))
        bbox = (x - v["x"], y - v["y"], x - v["x"] + w, y - v["y"] + h)
        return imagen.crop(bbox), [x, y]
    # default historico del padre: capturar "la pantalla" => aqui, el primario
    for m in c.monitores():
        if m["primario"]:
            bbox = (m["izq"] - v["x"], m["top"] - v["y"],
                    m["der"] - v["x"], m["bot"] - v["y"])
            return imagen.crop(bbox), [m["izq"], m["top"]]
    return imagen, [v["x"], v["y"]]


# _destino(args): la convencion de ruta (nombre pelado -> .tmp/capturas,
# con directorio se respeta, default captura_<fecha_hora>) es generica y
# vive en _core.ruta_destino_captura; cmd_capturar la llama directo.


def _grim_abrir(ruta):
    """PIL abre el PNG de grim y lo CARGA en memoria: permitiria sobreescribir
    el mismo ruta (crop/reescalado) sin escribir sobre un archivo abierto."""
    Image, _ = _pillow()
    im = Image.open(ruta)
    im.load()
    return im


def _captura_wayland(args, ruta):
    """(imagen PIL, origen_layout, via, en_ruta_final) en Wayland con grim.
    en_ruta_final=True cuando el PNG ya esta en `ruta` sin recortar/reescalar.
    """
    v = c.tamano_virtual()
    if args.monitor is not None:
        m = _resolver_monitor(args.monitor)
        if m is None:  # bounding de layout = captura completa
            c.run_ok("grim", [ruta], timeout=20.0)
            return _grim_abrir(ruta), [v["x"], v["y"]], \
                "grim (layout completo)", True
        # captura por output (man verbatim: "-o <output> Set the output name")
        r = c.run("grim", ["-o", m["nombre"], ruta], timeout=20.0)
        if r["rc"] == 0:
            return _grim_abrir(ruta), [m["izq"], m["top"]], \
                "grim -o %s" % m["nombre"], True
        # respaldo: layout completo + crop (grim -o no soportado por el
        # compositor) [runtime]
        c.run_ok("grim", [ruta], timeout=20.0)
        imagen = _grim_abrir(ruta)
        bbox = (m["izq"] - v["x"], m["top"] - v["y"],
                m["der"] - v["x"], m["bot"] - v["y"])
        if not (0 <= bbox[0] and 0 <= bbox[1]
                and bbox[2] <= imagen.width and bbox[3] <= imagen.height):
            c.fail("Rectangulo de %r (%s) cae fuera de la captura de grim: "
                   "desajuste entre el mapa de monitores y el layout real. "
                   "Mapa: monitores.py listar."
                   % (m["nombre"], str(bbox)))
        return imagen.crop(bbox), [m["izq"], m["top"]], \
            "grim completo + crop PIL (respaldo; grim -o fallo)", False
    if args.region is not None:
        x, y, w, h = args.region
        if w <= 0 or h <= 0:
            c.fail("Region invalida: ancho/alto deben ser > 0.")
        r = c.run("grim", ["-g", "%d,%d %dx%d" % (x, y, w, h), ruta],
                  timeout=20.0)
        if r["rc"] != 0:
            c.fail("grim -g rechazo la region (%d, %d, %d, %d): %s"
                   % (x, y, w, h, r["stderr"].strip()),
                   region_formato="grim -g \"<x>,<y> <W>x<H>\" (man verbatim)")
        return _grim_abrir(ruta), [x, y], "grim -g region", True
    # default historico del padre: "la pantalla" = monitor PRIMARIO
    primario = None
    for m in c.monitores():
        if m["primario"]:
            primario = m
            break
    if primario is not None:
        r = c.run("grim", ["-o", primario["nombre"], ruta], timeout=20.0)
        if r["rc"] == 0:
            return _grim_abrir(ruta), [primario["izq"], primario["top"]], \
                "grim -o %s (primario)" % primario["nombre"], True
        c.run_ok("grim", [ruta], timeout=20.0)
        imagen = _grim_abrir(ruta)
        bbox = (primario["izq"] - v["x"], primario["top"] - v["y"],
                primario["der"] - v["x"], primario["bot"] - v["y"])
        return imagen.crop(bbox), [primario["izq"], primario["top"]], \
            "grim completo + crop PIL (primario; grim -o fallo)", False
    c.run_ok("grim", [ruta], timeout=20.0)
    return _grim_abrir(ruta), [v["x"], v["y"]], \
        "grim (layout completo; sin primario)", True


def cmd_capturar(args):
    sesion = c.deteccion_sesion()
    # Destino con la convencion generica de la skill (_core.ruta_destino_captura).
    ruta = c.ruta_destino_captura(args.archivo)
    en_ruta = False
    if sesion == "x11":
        imagen, origen = _captura_x11(args)
        via = "pyautogui.screenshot + crop PIL (offset xrandr)"
    elif sesion == "wayland":
        imagen, origen, via, en_ruta = _captura_wayland(args, ruta)
    else:
        c.fail("Sesion grafica sin detectar: no hay ruta de captura. En "
               "cron/SSH exporta DISPLAY=:1 (X11) o WAYLAND_DISPLAY + "
               "XDG_RUNTIME_DIR (Wayland). refs linux-python.md §13.",
               sesion=sesion)

    fis_w, fis_h = int(imagen.width), int(imagen.height)
    if args.max_lado is not None:
        # Chequeo y factor del recorte: genericos en _core (el texto canonico
        # es el de la rama Windows validada: "pequeño (mínimo 16 px)").
        c.checar_max_lado(args.max_lado)
        Image, _ = _pillow()
        imagen.thumbnail((args.max_lado, args.max_lado), Image.LANCZOS)
    escala_x, escala_y = c.escalas_thumbnail(fis_w, fis_h,
                                             int(imagen.width),
                                             int(imagen.height))
    if sesion == "x11" or args.max_lado is not None or not en_ruta:
        imagen.save(ruta)  # normalizar: PNG final en la ruta devuelta
    # P0-3: factor TOTAL imagen->coordenada. En Wayland grim aplica una escala
    # global (max. de outputs, man) que antes vivia solo en `nota`: ahora sale
    # como campo `factor_grim` (null si la fuente no lo informa: honesto).
    factor_grim = _grim_factor() if sesion == "wayland" else None
    px_por_unidad_coord = escala_x * (factor_grim or 1.0)
    pw, ph = c.tamano_pantalla()
    cur = _cursor_layout()
    c.json_out({
        "ok": True,
        "archivo": ruta,
        "ancho": int(imagen.width),
        "alto": int(imagen.height),
        "fisico": {"ancho": fis_w, "alto": fis_h},
        "origen": origen,
        "escala": round(escala_x, 6),
        "escala_y": round(escala_y, 6),
        "factor_grim": factor_grim,
        "px_por_unidad_coord": round(px_por_unidad_coord, 6),
        "marco": c.MARCO,
        "regla": _REGLA_REESCALADO,
        "pantalla": {"ancho": pw, "alto": ph},
        "cursor": None if cur is None else {"x": cur[0], "y": cur[1]},
        "sesion": sesion,
        "via": via,
        "nota": "leer este PNG con vision y decidir desde ahi; NO hardcodear "
                "coordenadas de sesiones anteriores; 'origen' es la esquina "
                "sup-izq de la captura en coords de LAYOUT: sumala al "
                "reescalar coords de imagen a coords de clic; en Wayland "
                "grim aplica un factor de escala global (el maximo de los "
                "outputs, man) [runtime]: ver 'factor_grim' (null = no "
                "determinado aqui; verifica con una captura de prueba)",
    })


def cmd_tamano(args):
    if args.virtual:
        v = c.tamano_virtual()
        c.json_out({
            "ancho": v["ancho"],
            "alto": v["alto"],
            "origen": [v["x"], v["y"]],
            "marco": c.MARCO,
            "sesion": c.deteccion_sesion(),
            "via": c.monitores()[0]["via"],
            "nota": "marco historico: bounding de LAYOUT de todos los monitores "
                     "(xrandr --listmonitors / sway get_outputs / hyprctl); "
                     "rectangulo por monitor: monitores.py listar",
        })
        return
    w, h = c.tamano_pantalla()
    primarios = [m for m in c.monitores() if m["primario"]]
    primario = primarios[0] if primarios else c.monitores()[0]
    c.json_out({
        "ancho": w,
        "alto": h,
        "origen": [primario["izq"], primario["top"]],
        "marco": c.MARCO,
        "sesion": c.deteccion_sesion(),
        "via": primario["via"],
        "nota": "pixels del monitor PRIMARIO; en X11 su offset puede NO ser "
                "(0,0) dentro del screen: el bounding completo es tamano "
                "--virtual",
    })


def cmd_posicion(args):
    if c.deteccion_sesion() != "x11":
        c.fail("posicion del cursor no legible en Wayland con las tools "
               "auditadas (ver monitores.py cursor): usa capturar + vision.",
               sesion=c.deteccion_sesion())
    r = c.run_ok("xdotool", ["getmouselocation", "--shell"], timeout=10.0)
    kv = c._shell_kv(r["stdout"])
    c.json_out({
        "x": int(kv.get("X", -1)),
        "y": int(kv.get("Y", -1)),
        "marco": c.MARCO,
        "nota": "screen X11 (layout; origen (0,0) = sup-izq del screen)",
        "via": "xdotool getmouselocation --shell",
    })


def _leer_pixel(x, y):
    """(r, g, b) en coords de LAYOUT, con ruta por sesion."""
    sesion = c.deteccion_sesion()
    if sesion == "x11":
        pa = _pyautogui()
        try:
            return tuple(int(v) for v in pa.pixel(int(x), int(y)))
        except Exception as exc:
            c.fail("pyautogui.pixel fallo (X11): %s: %s"
                   % (type(exc).__name__, exc))
    if sesion == "wayland":
        # grim escribe a stdout con "-" (man verbatim): pixel = region 1x1.
        # c.run() decodifica stdout a TEXTO (no sirve para binarios), asi que
        # aqui se captura el PNG en crudo: archivo temporal dentro del .tmp
        # de la skill (regla: temporales siempre dentro del proyecto).
        ruta = os.path.join(c.DIR_TMP, "pixel_%d_%d.png" % (int(x), int(y)))
        os.makedirs(c.DIR_TMP, exist_ok=True)
        r = c.run_ok("grim", ["-g", "%d,%d 1x1" % (int(x), int(y)), ruta],
                     timeout=10.0)
        Image, _ = _pillow()
        im = Image.open(ruta)
        if im.mode != "RGB":
            im = im.convert("RGB")
        return tuple(int(v) for v in im.getpixel((0, 0)))
    c.fail("Sesion grafica sin detectar: no hay ruta de pixel.", sesion=sesion)


def cmd_pixel(args):
    if not c.dentro_de_virtual(args.x, args.y):
        v = c.tamano_virtual()
        c.fail("Pixel (%d, %d) fuera del bounding de layout "
               "(x %d..%d, y %d..%d). Mapa: monitores.py listar."
               % (args.x, args.y, v["x"], v["x"] + v["ancho"] - 1,
                  v["y"], v["y"] + v["alto"] - 1))
    r, g, b = _leer_pixel(args.x, args.y)
    sesion = c.deteccion_sesion()
    via = ("pyautogui.pixel (X11; debajo Pillow XCB o scrot [runtime])"
           if sesion == "x11" else "grim -g \"x,y 1x1\" - + PIL (stdout)")
    c.json_out({"x": args.x, "y": args.y, "r": r, "g": g, "b": b,
                "marco": c.MARCO, "nota": "marco historico: layout",
                "sesion": sesion, "via": via})


def cmd_esperar(args):
    c.checar_abort("esperar")  # bandera dura al inicio (luego, por poll)
    c.checar_pausa()           # PAUSA: la espera arranca cuando se libera
    inicio = time.monotonic()
    # Coherencia de flags y bucles: genericos en _core (copias identicas de
    # las 3 ramas). Lo propio de linux —leer el pixel segun sesion (pyautogui
    # X11 / grim 1x1 Wayland)— llega al bucle por callback _coincide().
    if c.checar_args_esperar(args.pixel, args.color, args.cambia, args.estable):
        x, y = args.pixel
        if not c.dentro_de_virtual(x, y):
            v = c.tamano_virtual()
            c.fail("Pixel (%d, %d) fuera del bounding de layout "
                   "(x %d..%d, y %d..%d)."
                   % (x, y, v["x"], v["x"] + v["ancho"] - 1,
                      v["y"], v["y"] + v["alto"] - 1))
        color = c.parsear_color(args.color)
        tol = args.tolerancia
        c.validar_tolerancia(tol)
        limite = c.cap_timeout_esperar(args.timeout)

        def _coincide():
            pr, pg, pb = _leer_pixel(x, y)
            return (abs(pr - color[0]) <= tol and abs(pg - color[1]) <= tol
                    and abs(pb - color[2]) <= tol)

        cumplida, ms_esperados = c.esperar_color(
            _coincide, args.cambia, args.estable, limite, 0.1, inicio,
            c.checar_aborto_espera)
        c.json_out({
            "cumplida": bool(cumplida),
            "ms_esperados": ms_esperados,
            "modo": "cambia" if args.cambia else "estable",
            "pixel": [int(x), int(y)],
            "color": list(color),
            "tolerancia": tol,
            "timeout_s": limite,
            "marco": c.MARCO,
            "sesion": c.deteccion_sesion(),
            "nota": "poll ~100 ms con mini-captura de 1 px por iteracion "
                    "(grim en Wayland cuesta: sube el --timeout si hace "
                    "falta); timeout agotado => cumplida=false SIN error "
                    "(el agente decide); la bandera ABORT del .tmp corta la "
                    "espera",
        })
        return
    ms = c.cap_ms(args.milisegundos)
    c.dormir(ms, c.checar_aborto_espera)
    c.json_out({
        "cumplida": True,
        "ms_esperados": ms,
        "modo": "fijo",
        "marco": c.MARCO,
        "sesion": c.deteccion_sesion(),
        "nota": "sueno simple (default 400 ms, cap 30000) para dejar "
                "renderizar la UI; la bandera ABORT del .tmp corta la espera; "
                "PAUSA la posterga",
    })


def cmd_localizar(args):
    if c.deteccion_sesion() != "x11":
        c.fail("localizar (locateOnScreen) exige pyautogui, que en Wayland "
               "NATIVO no ve el compositor (solo XWayland, refs "
               "linux-python.md §4): haz 'capturar' y decide con vision.",
               sesion=c.deteccion_sesion())
    if not os.path.isfile(args.imagen):
        c.fail("La imagen a buscar no existe: %s" % os.path.abspath(args.imagen))
    pa = _pyautogui()
    kwargs = {}
    if args.region is not None:
        kwargs["region"] = tuple(args.region)
    aviso = None
    if args.confidence is not None:
        c.validar_confidence(args.confidence)
        kwargs["confidence"] = args.confidence
    try:
        try:
            box = pa.locateOnScreen(args.imagen, **kwargs)
        except NotImplementedError:
            # confidence sin OpenCV lanza NotImplementedError (verificado en
            # el dominio Windows): degradar a coincidencia exacta y avisar.
            kwargs.pop("confidence", None)
            box = pa.locateOnScreen(args.imagen, **kwargs)
            aviso = ("confidence descartado: instalar opencv-python "
                     "(python3 -m pip install opencv-python) o buscar por "
                     "vision; se degrado a coincidencia exacta")
    except pa.ImageNotFoundException:
        box = None
    nota_marco = ("en X11 el screen unificado cubre TODOS los monitores: a "
                  "diferencia de Windows (pyscreeze primario-only) aqui no "
                  "hay ese limite, aunque region= usa coords de layout "
                  "[runtime]")
    if box is None:
        c.json_out({
            "encontrado": False,
            "imagen": os.path.abspath(args.imagen),
            "marco": c.MARCO,
            "sesion": "x11",
            "nota": "locate exige pixeles casi identicos (tema/escala/"
                    "antialiasing lo rompen); para el loop normal usa "
                    "capturar + vision. " + nota_marco,
        })
        return
    centro = pa.center(box)
    c.json_out({
        "encontrado": True,
        "imagen": os.path.abspath(args.imagen),
        "box": [int(box.left), int(box.top), int(box.width), int(box.height)],
        "centro": [int(centro.x), int(centro.y)],
        "marco": c.MARCO,
        "sesion": "x11",
        "aviso": aviso,
        "nota": nota_marco,
    })


def construir_parser():
    parser = c.Parser(
        prog="pantalla.py (linux)",
        description="Capturas e inspeccion de pantalla en Linux: X11 via "
                    "pyautogui (subproceso cero: libreria Python) y Wayland "
                    "via grim; coords de LAYOUT. Mapa: monitores.py listar.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1] if __doc__ and "Subcomandos:" in __doc__ else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    p = sub.add_parser("capturar", help="guardar un PNG (primario, monitor, "
                       "layout o region en coords de layout)")
    p.add_argument("--region", type=int, nargs=4, metavar=("X", "Y", "ANCHO", "ALTO"),
                   help="recorte en coords de LAYOUT; con --monitor es "
                        "RELATIVA a ese monitor")
    p.add_argument("--monitor", metavar="OBJETO",
                   help="indice (0,1,...), 'primario', 'virtual' (bounding "
                        "completo) o subcadena del nombre; ver monitores.py "
                        "listar")
    p.add_argument("--max-lado", dest="max_lado", type=int, metavar="N",
                   help="thumbnail LANCZOS de lado maximo N ANTES de guardar "
                        "(ahorra tokens): RE-ESCALA con 'escala'/'regla'")
    p.add_argument("--archivo", help="nombre o ruta destino del PNG: un "
                   "nombre pelado cae en .tmp/capturas de ESTA skill; con "
                   "directorio se respeta. Por defecto "
                   ".tmp/capturas/captura_<fecha_hora>.png")
    p.set_defaults(func=cmd_capturar)

    p = sub.add_parser("tamano", help="resolucion del primario (o --virtual)")
    p.add_argument("--virtual", action="store_true",
                   help="bounding de LAYOUT + origen de todos los monitores")
    p.set_defaults(func=cmd_tamano)

    p = sub.add_parser("posicion", help="posicion actual del cursor (X11)")
    p.set_defaults(func=cmd_posicion)

    p = sub.add_parser("pixel", help="color RGB de un pixel (coords de layout)")
    p.add_argument("x", type=int, help="coordenada X de layout")
    p.add_argument("y", type=int, help="coordenada Y de layout")
    p.set_defaults(func=cmd_pixel)

    p = sub.add_parser("esperar", help="pausa fija (--milisegundos) o "
                       "adaptativa por pixel (--pixel --color "
                       "--cambia|--estable)")
    p.add_argument("--milisegundos", type=int, default=400, metavar="N",
                   help="pausa fija en ms (default 400, cap 30000)")
    p.add_argument("--pixel", type=int, nargs=2, metavar=("X", "Y"),
                   help="espera adaptativa: pixel a vigilar (coords layout)")
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

    p = sub.add_parser("localizar", help="buscar una imagen en pantalla "
                       "(locateOnScreen; SOLO X11)")
    p.add_argument("imagen", help="ruta del PNG/JPG a buscar")
    p.add_argument("--region", type=int, nargs=4, metavar=("X", "Y", "ANCHO", "ALTO"),
                   help="limitar la busqueda (coords de layout; [runtime])")
    p.add_argument("--confidence", type=float,
                   help="umbral 0-1; REQUIERE opencv-python, sin el degrada a "
                        "coincidencia exacta")
    p.set_defaults(func=cmd_localizar)

    return parser


def main():
    args = construir_parser().parse_args()
    try:
        args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        # FailSafeException vive en pyautogui (ruta X11): traducirla a JSON
        # sin importar el modulo al arrancar (lazismo del dominio linux).
        if type(exc).__name__ == "FailSafeException":
            c.fallar_por_failsafe(exc)
        c.fail("%s: %s" % (type(exc).__name__, exc))


if __name__ == "__main__":
    main()
