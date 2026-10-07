# -*- coding: utf-8 -*-
"""pantalla.py — Capturas e inspección visual (skill computer-use-py).

ENTRADA MULTI-OS (FASE SEG3): `python scripts/pantalla.py ...` vale en los 3
SO — el CLI ejecuta la ruta de TU SO EN EL PROPIO PROCESO (dispatch por
sys.platform en tiempo de ejecucion, bind `c = _core.modulo_sistema()`): en
Windows la ruta nativa de abajo (PyAutoGUI + PIL ImageGrab); en Linux/macOS
las primitivas exclusivas viven en la libreria scripts/linux/
linux_especiales.py o scripts/macos/macos_especiales.py; plataforma
desconocida responde JSON + rc 2.

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
  esperar    Pausa: fija con --milisegundos N (default 320, cap 30000) o
             adaptativa con --pixel X Y --color r,g,b y --cambia|--estable M
             (poll ~100 ms; el FAILSAFE sigue intacto). IMPL-K: --mientras
             "argv..." lanza el DISPARADOR como hijo y el JSON suma
             'accion'{argv,rc,json}; --auto-pixel --region x y w h ELIGE el
             pixel que cambia (scan de doble muestra; JSON con
             pixel_usado/color_base; solo Windows).
  localizar  Busca una imagen en pantalla (locateOnScreen). pyscreeze es
             PRIMARIO-ONLY: solo ve el monitor primario (documentado, sin
             cambiar la conducta).

Ejemplos (desde la carpeta computer-use-py):
  py scripts/pantalla.py capturar                # Windows (python3 en otros SO)
  py scripts/pantalla.py capturar --monitor 1 --max-lado 1280
  py scripts/pantalla.py capturar --monitor virtual
  py scripts/pantalla.py capturar --region -800 0 600 400 --archivo trozo.png
  py scripts/pantalla.py tamano --virtual
  py scripts/pantalla.py esperar --milisegundos 480
  py scripts/pantalla.py esperar --pixel 300 200 --color 255,255,255 --cambia --timeout 5
  py scripts/pantalla.py esperar --mientras "py scripts/teclado.py tecla enter"
  py scripts/pantalla.py esperar --auto-pixel --region 300 200 420 120 --mientras "py scripts/teclado.py escribir Z"
  py scripts/pantalla.py localizar boton.png --confidence 0.9

En Linux/macOS este mismo proceso ejecuta la seccion del SO (primitivas
exclusivas en scripts/linux/linux_especiales.py |
scripts/macos/macos_especiales.py): JSON y exit code identicos, elegidos por
esa seccion (marco px_layout/puntos_logicos).
"""

import argparse
import json  # parsear el stdout JSON del hijo de --mientras (P1.2-c)
import os
import subprocess  # lanzar el disparador de --mientras (P1.2-c)
import sys
import time

_DIR_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _DIR_SCRIPTS not in sys.path:
    sys.path.insert(0, _DIR_SCRIPTS)
import _core  # noqa: E402  (genericos multi-OS + modulo_sistema: dispatch en tiempo de ejecucion)

# ===========================================================================
# SECCION WINDOWS — ruta nativa (cuerpos VERBATIM del CLI SEG2; `c` se
# bind-eea a glue_windows en main(), que ya trae pyautogui con DPI + FAILSAFE
# + PAUSE; pyautogui/Image/ImageGrab se importan en la rama win de main()).
# ===========================================================================

_REGLA_REESCALADO = (
    "coordenada_virtual_x = origen[0] + x_en_la_imagen / px_por_unidad_coord; "
    "coordenada_virtual_y = origen[1] + y_en_la_imagen / px_por_unidad_coord. "
    "'px_por_unidad_coord' es el factor TOTAL imagen->coordenada (ya incluye "
    "el recorte --max-lado; en Windows es el INVERSO de 'escala': vale "
    "imagen_px/fuente_px, por eso la formula DIVIDE), asi que UN unico campo "
    "basta para re-escalar: 'escala'/'escala_y' quedan SOLO como factor "
    "fuente->imagen del thumbnail --max-lado. Con 'origen' distinto de [0, 0] suma el offset "
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


def _resolver_monitor(valor):
    """--monitor: None si 'virtual' (bounding completo) | dict del monitor.

    Acepta el índice (según el orden de monitores.py listar), 'primario' o
    una subcadena del nombre (p. ej. 'DISPLAY1'), case-insensitive. El
    algoritmo es el generico de _core.resolver_monitor (idéntico en las 3
    ramas); aqui solo viven la FUENTE de la lista (ctypes) y los TEXTOS con
    jerga de Windows (dwFlags/szDevice), canonicos para esta rama.
    """
    return c.resolver_monitor(
        valor, c.monitores,
        sin_primario="Ningún monitor figura como primario (dwFlags inesperado). "
                     "Revisa monitores.py listar.",
        indice_rango="Índice de monitor %d fuera de rango (0..%d). "
                     "Mapa: monitores.py listar.",
        ambiguo="La subcadena %r coincide con varios monitores (%s): usa el "
                "índice.",
        sin_nombre="Ningún monitor tiene el nombre %r (subcadena de szDevice). "
                   "Mapa: monitores.py listar.")


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

    # Convencion de destino y matematica del thumbnail: genericos en _core
    # (identicos en las 3 ramas). Sin --max-lado, escala == (1.0, 1.0).
    ruta = c.ruta_destino_captura(args.archivo)
    fis_w, fis_h = int(imagen.width), int(imagen.height)
    if args.max_lado is not None:
        c.checar_max_lado(args.max_lado)
        # LANCZOS conserva el aspecto y baja tokens: reescala con la "regla".
        imagen.thumbnail((args.max_lado, args.max_lado), Image.LANCZOS)
    escala_x, escala_y = c.escalas_thumbnail(fis_w, fis_h,
                                             int(imagen.width),
                                             int(imagen.height))
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
        # P0-3/P0-4: factor TOTAL imagen->coordenada y marco canonico.
        # FIX W11 (verificado en multimonitor real): la `regla` de esta skill
        # DIVIDE (coordenada = origen + px_imagen / px_por_unidad_coord), o
        # sea que el campo son PIXELS-DE-IMAGEN por unidad de coordenada
        # (ancho_final/fis_w) — el INVERSO de 'escala' (fis/ancho, que traduce
        # fuente->imagen). Antes se reportaba escala_x crudo: con un thumbnail
        # != nativo (p. ej. 640 de 1920 => 3.0) la division corria en sentido
        # contrario y descolocaba el clic un factor ppu^2; con --max-lado en
        # tamano nativo ambos campos valen 1.0 y el error quedaba invisible.
        # 'escala'/'escala_y' conservan su semantica historica intacta.
        "px_por_unidad_coord": round(1.0 / escala_x, 6),
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


def _split_mientras(cadena):
    """argv de --mientras: shlex posix=False (conserva backslashes de rutas
    Windows) + limpieza de comillas envolventes. Error JSON si queda vacio."""
    import shlex

    partes = []
    for tok in shlex.split(cadena, posix=False):
        if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
            tok = tok[1:-1]
        partes.append(tok)
    if not partes:
        c.fail("--mientras quedo vacio: pasa el argv COMPLETO del disparador "
               "entre comillas, p. ej. --mientras \"py scripts/teclado.py "
               "tecla enter\".")
    return partes


def _lanzar_mientras(args):
    """IMPL-K P1.2-c: lanza el DISPARADOR como hijo (el patron
    Popen+communicate+kill que los drivers reescribieron 12 veces) y
    devuelve (Popen, argv) o (None, None) sin el flag."""
    if not getattr(args, "mientras", None):
        return None, None
    argv = _split_mientras(args.mientras)
    try:
        proc = subprocess.Popen(argv, shell=False,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess,
                                                      "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        c.fail("El disparador de --mientras no arranco (%s): %s: %s"
               % (" ".join(argv), type(exc).__name__, exc),
               nota="usa el mismo interprete del loop (py/python3) y rutas "
                    "relativas a la raiz de la skill; CREATE_NO_WINDOW evita "
                    "que una consola herede y ensucie el JSON")
    time.sleep(0.3)  # margen para que el hijo arranque antes de medir
    return proc, argv


def _recolectar_mientras(proc, argv, espera_extra=10.0):
    """Espera al hijo del disparador y arma 'accion' {argv, rc, json} (JSON
    hijo parseado o _crudo; TimeoutExpired => kill honesto)."""
    try:
        out, _err = proc.communicate(timeout=espera_extra)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _err = proc.communicate()
        return {"argv": argv, "rc": None,
                "json": {"error": "el hijo de --mientras no retorno en "
                                  "%.0f s (matado); su espera propia pudo "
                                  "seguir" % espera_extra}}
    texto = (out or b"").decode("utf-8", "replace")
    try:
        dados = json.loads(texto)
    except ValueError:
        dados = {"_crudo": texto[:400]}
    return {"argv": argv, "rc": rc, "json": dados}


def _auto_pixel(args):
    """IMPL-K P1.2-d: ELIGE el pixel que cambia en la region y espera su
    cambio (los 8 barridos a mano de b3_v5..v12, hoy en un flag).

    Muestrea la region DOS veces (0.5 s aparte), pick = primer pixel cuyo
    color difiere entre muestras (sensibilidad 'parpadeo', el del caret) o —
    con 'brillo' — el punto MAS OSCURO de la segunda muestra (glifo sobre
    lienzo claro; leccion: el caret XAML de Notepad NO se pinta en el
    framebuffer, monitores-multi.md §11). color_base = color actual del pick.
    Luego corre la espera --cambia canonica sobre el pixel elegido."""
    x, y, w, h = args.region
    if w <= 0 or h <= 0:
        c.fail("--auto-pixel --region exige ancho/alto > 0.")
    v = c.tamano_virtual()
    if not (v["x"] <= x and v["y"] <= y
            and x + w <= v["x"] + v["ancho"]
            and y + h <= v["y"] + v["alto"]):
        c.fail("Region (%d, %d, %d, %d) fuera del bounding virtual." % (x, y, w, h))
    if args.sensibilidad not in ("parpadeo", "brillo"):
        c.fail("--sensibilidad %r invalido." % args.sensibilidad,
               validos=["parpadeo", "brillo"])
    tol = args.tolerancia
    c.validar_tolerancia(tol)
    limite = c.cap_timeout_esperar(args.timeout)
    try:
        im1 = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
        if im1.mode != "RGB":
            im1 = im1.convert("RGB")
    except Exception as exc:
        c.fail("ImageGrab de --auto-pixel fallo: %s: %s"
               % (type(exc).__name__, exc))
    time.sleep(0.5)  # los drivers parpadean a ~0.55 s; default del caret W11
    try:
        im2 = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
        if im2.mode != "RGB":
            im2 = im2.convert("RGB")
    except Exception as exc:
        c.fail("Segunda muestra de --auto-pixel fallo: %s: %s"
               % (type(exc).__name__, exc))
    px, py, color_base, motivo = None, None, None, None
    paso_x = max(1, w // 160)
    paso_y = max(1, h // 80)
    if args.sensibilidad == "parpadeo":
        for yy in range(0, h, paso_y):
            for xx in range(0, w, paso_x):
                c1 = im1.getpixel((xx, yy))
                c2 = im2.getpixel((xx, yy))
                if abs(c1[0] - c2[0]) + abs(c1[1] - c2[1]) + abs(c1[2] - c2[2]) >= 24:
                    px, py, color_base = x + xx, y + yy, list(c2)
                    break
            if px is not None:
                break
        if px is None:
            return {"cumplida": False, "ms_esperados": 0, "modo": "auto-pixel",
                    "pixel_usado": None, "color_base": None,
                    "sensibilidad": args.sensibilidad,
                    "region": [x, y, w, h], "timeout_s": limite,
                    "marco": c.MARCO,
                    "motivo": "region_estatica",
                    "nota": "ningun pixel de la region cambio en 0.5 s: el "
                            "caret XAML puede no repintarse (monitores-multi"
                            ".md §11) o el disparador todavia no actuo. "
                            "Prueba --sensibilidad brillo, region mas pequena "
                            "sobre la fila del texto, o lanza el hijo "
                            "--mientras ANTES de esperar"}
    else:
        mejor = None
        for yy in range(0, h, paso_y):
            for xx in range(0, w, paso_x):
                c2 = im2.getpixel((xx, yy))
                lum = int(c2[0]) + int(c2[1]) + int(c2[2])
                if mejor is None or lum < mejor[0]:
                    mejor = (lum, x + xx, y + yy, list(c2))
        if mejor is not None:
            px, py, color_base = mejor[1], mejor[2], mejor[3]
            motivo = "punto_mas_oscuro"
    cumplida, ms_esperados = c.esperar_color(
        lambda: _color_coincide(px, py, color_base, tol),
        True, None, limite, 0.1, time.monotonic(), c.checar_aborto_espera)
    return {"cumplida": bool(cumplida),
            "ms_esperados": ms_esperados,
            "modo": "auto-pixel",
            "pixel_usado": [px, py],
            "color_base": color_base,
            "sensibilidad": args.sensibilidad,
            "motivo": motivo,
            "region": [x, y, w, h],
            "tolerancia": tol,
            "timeout_s": limite,
            "marco": c.MARCO,
            "nota": "pixel ELEGIDO por la skill (scan doble muestra); espera "
                    "= --cambia contra color_base; leccion W11: los pixeles "
                    "ClearType de glifos son estaticos y el caret XAML no se "
                    "pinta (references/monitores-multi.md §11); coords de "
                    "pixel_usado en el ESPACIO VIRTUAL"}


def cmd_esperar(args):
    """Pausa: fija (--milisegundos), adaptativa por pixel, AUTO-PIXEL
    (--auto-pixel --region: elige el pixel que cambia) y/o con DISPARADOR
    hijo (--mientras "argv...": JSON combinado con 'accion')."""
    c.checar_abort("esperar")
    c.checar_pausa()  # P1-5: si hay PAUSA, la espera arranca al reanudarse
    if getattr(args, "auto_pixel", False):
        if args.pixel is not None or args.color is not None or args.cambia \
                or args.estable is not None:
            c.fail("--auto-pixel elige el pixel SOLO: es excluyente con "
                   "--pixel/--color/--cambia/--estable (y exige --region).")
        if args.region is None:
            c.fail("--auto-pixel exige --region x y w h (coords virtuales).")
        proc, argv = _lanzar_mientras(args)
        try:
            resultado = _auto_pixel(args)
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()  # nada de hijos huesrfanos si algo aborta
        if proc is not None:
            resultado["accion"] = _recolectar_mientras(proc, argv)
        c.json_out(resultado)
        return
    proc, argv = _lanzar_mientras(args)
    try:
        return _esperar_normal(args, proc, argv)
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()  # validacion/ABORT/FAILSAFE: sin huesrfanos


def _esperar_normal(args, proc, argv):
    inicio = time.monotonic()
    # Coherencia de flags y bucles de espera: genericos en _core (copias
    # identicas en las 3 ramas). Lo propio de Windows —como leer el pixel con
    # tolerancia (pyautogui/ImageGrab)— llega al bucle por callback.
    if c.checar_args_esperar(args.pixel, args.color, args.cambia, args.estable):
        x, y = args.pixel
        if not c.dentro_de_virtual(x, y):
            v = c.tamano_virtual()
            c.fail("Pixel (%d, %d) fuera de la pantalla virtual "
                   "(x %d..%d, y %d..%d)." % (x, y, v["x"], v["x"] + v["ancho"] - 1,
                                              v["y"], v["y"] + v["alto"] - 1))
        if c._monitor_contiene(x, y) is None:
            c.fail("Pixel (%d, %d) no cae dentro de ningún monitor (hueco del "
                   "bounding virtual)." % (x, y))
        color = c.parsear_color(args.color)
        tol = args.tolerancia
        c.validar_tolerancia(tol)
        limite = c.cap_timeout_esperar(args.timeout)
        cumplida, ms_esperados = c.esperar_color(
            lambda: _color_coincide(x, y, color, tol),
            args.cambia, args.estable, limite, 0.1, inicio,
            c.checar_aborto_espera)
        resultado = {
            "cumplida": bool(cumplida),
            "ms_esperados": ms_esperados,
            "modo": "cambia" if args.cambia else "estable",
            "pixel": [int(x), int(y)],
            "color": list(color),
            "tolerancia": tol,
            "timeout_s": limite,
            "marco": c.MARCO,
            "nota": "marco historico 'pantalla virtual'; poll ~100 ms; timeout agotado => cumplida=false SIN error "
                    "(el agente decide); --estable M pide M ms de coincidencia "
                    "continua; FAILSAFE intacto",
        }
        if proc is not None:
            resultado["accion"] = _recolectar_mientras(proc, argv)
        c.json_out(resultado)
        return
    ms = c.cap_ms(args.milisegundos)
    c.dormir(ms, c.checar_aborto_espera)
    resultado = {
        "cumplida": True,
        "ms_esperados": ms,
        "modo": "fijo",
        "marco": c.MARCO,
        "nota": "sueño simple (default 320 ms, cap 30000) para dejar renderizar "
                "la UI; FAILSAFE intacto; la bandera ABORT de vigilar.py corta "
                "la espera; PAUSA la posterga",
    }
    if proc is not None:
        resultado["accion"] = _recolectar_mientras(proc, argv)
    c.json_out(resultado)


def cmd_localizar(args):
    if not os.path.isfile(args.imagen):
        c.fail("La imagen a buscar no existe: %s" % os.path.abspath(args.imagen))
    kwargs = {}
    if args.region is not None:
        kwargs["region"] = tuple(args.region)
    aviso = None
    if args.confidence is not None:
        c.validar_confidence(args.confidence)
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


def construir_parser_win():
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

    p = sub.add_parser("esperar", help="pausa fija (--milisegundos), adaptativa "
                       "por pixel (--pixel --color --cambia|--estable), "
                       "AUTO-PIXEL (--auto-pixel --region) y con disparador "
                       "hijo (--mientras)")
    # TIEMPOS-K: default 400->320 (-20% exacto, piso 250 respetado): es la
    # espera de RENDER del loop (accion->esperar->capturar); la evidencia del
    # autotest 06/10 mostro 0 FAIL con 320. Cap 30000 intacto (limite C).
    p.add_argument("--milisegundos", type=int, default=320, metavar="N",
                   help="pausa fija en ms (default 320, cap 30000)")
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
    p.add_argument("--mientras", metavar="ARGV",
                   help="lanza el DISPARADOR como hijo durante la espera "
                        "(argv completo entre comillas, p. ej. \"py "
                        "scripts/teclado.py tecla enter\"): el JSON suma "
                        "'accion' {argv, rc, json} del hijo (P1.2-c)")
    p.add_argument("--auto-pixel", dest="auto_pixel", action="store_true",
                   help="ELIGE el pixel que cambia en --region x y w h y "
                        "espera su cambio (scan de doble muestra; JSON con "
                        "pixel_usado/color_base; excluyente con --pixel/"
                        "--color/--cambia/--estable)")
    p.add_argument("--region", type=int, nargs=4,
                   metavar=("X", "Y", "ANCHO", "ALTO"),
                   help="region de --auto-pixel (coords virtuales)")
    p.add_argument("--sensibilidad", default="parpadeo", metavar="S",
                   help="parpadeo (default: primer pixel que cambio entre "
                        "muestras) | brillo (punto mas oscuro: para glifos "
                        "cuando el caret XAML no se pinta)")
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


# ===========================================================================
# SECCION LINUX — cuerpos de scripts/linux/pantalla.py movados VERBATIM
# (sufijo _linux; el viejo import _compartido_linux cae: el alias global `c`
# lo bind-eea _core.modulo_sistema() en main() = scripts/linux/
# linux_especiales.py). Primitivas ya en la libreria y NO copiadas aqui:
# _grim_factor, _pillow, _pyautogui, _cursor_layout, _resolver_monitor,
# _grim_abrir, _captura_wayland (se llaman via c.). Suben con sufijo:
# _REGLA_REESCALADO_LINUX, _captura_x11_linux, _leer_pixel_linux y los cmd_*.
# Marco: px_layout.
# ===========================================================================

_DOC_LINUX = """pantalla.py — Capturas e inspeccion visual del dominio LINUX (computer-use-py).

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
  esperar    Pausa fija --milisegundos N (default 320, cap 30000) o adaptativa
             --pixel X Y --color r,g,b con --cambia|--estable M (poll ~100 ms).
  localizar  Busca una imagen (locateOnScreen). SOLO X11: en Wayland
             pyautogui no inyecta/lee nativo => error honesto.

Ejemplos (desde la carpeta computer-use-py, en la maquina Linux):
  python3 scripts/pantalla.py capturar
  python3 scripts/pantalla.py capturar --monitor 1 --max-lado 1280
  python3 scripts/pantalla.py capturar --monitor virtual
  python3 scripts/pantalla.py capturar --region 1920 0 600 400
  python3 scripts/pantalla.py tamano --virtual
  python3 scripts/pantalla.py esperar --milisegundos 480
  python3 scripts/pantalla.py esperar --pixel 300 200 --color 255,255,255 --cambia
  python3 scripts/pantalla.py localizar boton.png --confidence 0.9
"""

# Redaccion ESPEJO del fix W11 de la rama Windows (IMPL-K P0.3): la regla
# DIVIDE y 'px_por_unidad_coord' es el INVERSO de 'escala' por el lado del
# thumbnail (escala = fuente/imagen; ppu = imagen/fuente x factor grim).
_REGLA_REESCALADO_LINUX = (
    "coordenada_layout_x = origen[0] + x_en_la_imagen / px_por_unidad_coord; "
    "coordenada_layout_y = origen[1] + y_en_la_imagen / px_por_unidad_coord. "
    "'px_por_unidad_coord' es el factor TOTAL imagen->coordenada (ya incluye "
    "el recorte --max-lado — es el INVERSO de 'escala': vale imagen_px/"
    "fuente_px, por eso la formula DIVIDE — y, en Wayland, el factor de "
    "escala global que grim aplica: ppu = factor_grim/escala; si "
    "'factor_grim' es null porque la fuente no lo informa, el factor no "
    "verificado queda SOLO en esta formula: verifica con una captura de "
    "prueba). 'escala'/'escala_y' quedan SOLO como factor fuente->imagen del "
    "thumbnail --max-lado. Con 'origen' distinto del screen, suma el offset "
    "(coords de imagen -> coords de layout). Marco: 'marco' enum del JSON."
)


def _captura_x11_linux(args):
    """(imagen PIL, origen_layout) en X11: captura completa + crop PIL."""
    pa = c._pyautogui()
    try:
        imagen = pa.screenshot()
    except Exception as exc:
        c.fail("pyautogui.screenshot() fallo en X11: %s: %s. Rutas tipicas: "
               "Pillow ImageGrab (XCB) o scrot — instalar pillow / scrot y "
               "reintentar (refs linux-python.md §9)."
               % (type(exc).__name__, exc))
    v = c.tamano_virtual()
    if args.monitor is not None:
        m = c._resolver_monitor(args.monitor)
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


def cmd_capturar_linux(args):
    sesion = c.deteccion_sesion()
    # Destino con la convencion generica de la skill (_core.ruta_destino_captura).
    ruta = c.ruta_destino_captura(args.archivo)
    en_ruta = False
    if sesion == "x11":
        imagen, origen = _captura_x11_linux(args)
        via = "pyautogui.screenshot + crop PIL (offset xrandr)"
    elif sesion == "wayland":
        imagen, origen, via, en_ruta = c._captura_wayland(args, ruta)
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
        Image, _ = c._pillow()
        imagen.thumbnail((args.max_lado, args.max_lado), Image.LANCZOS)
    escala_x, escala_y = c.escalas_thumbnail(fis_w, fis_h,
                                             int(imagen.width),
                                             int(imagen.height))
    if sesion == "x11" or args.max_lado is not None or not en_ruta:
        imagen.save(ruta)  # normalizar: PNG final en la ruta devuelta
    # P0-3: factor TOTAL imagen->coordenada. En Wayland grim aplica una escala
    # global (max. de outputs, man) que antes vivia solo en `nota`: ahora sale
    # como campo `factor_grim` (null si la fuente no lo informa: honesto).
    # FIX IMPL-K P0.3 (espejo del fix W11 de la rama Windows, arriba en la
    # seccion win): la `regla` DIVIDE (coord = origen + px_imagen/ppu), o sea
    # que ppu son PIXELS-DE-IMAGEN por unidad de coordenada = factor_grim /
    # escala_x. escala_x viene de escalas_thumbnail() = fuente/imagen (>=1 en
    # thumbnail): multiplicarlo invertia el sentido y descolocaba el clic un
    # factor ppu^2 con --max-lado. Sin thumbnail escala_x=1.0 y el valor es
    # idéntico al historico (los demas casos intactos). [runtime: formula
    # verificada algebraicamente contra _core.escalas_thumbnail; la prueba en
    # SO real queda marcada en references/linux-python.md §VERIFICADO]
    factor_grim = c._grim_factor() if sesion == "wayland" else None
    px_por_unidad_coord = (factor_grim or 1.0) / escala_x
    pw, ph = c.tamano_pantalla()
    cur = c._cursor_layout()
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
        "regla": _REGLA_REESCALADO_LINUX,
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


def cmd_tamano_linux(args):
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


def cmd_posicion_linux(args):
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


def _leer_pixel_linux(x, y):
    """(r, g, b) en coords de LAYOUT, con ruta por sesion."""
    sesion = c.deteccion_sesion()
    if sesion == "x11":
        pa = c._pyautogui()
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
        Image, _ = c._pillow()
        im = Image.open(ruta)
        if im.mode != "RGB":
            im = im.convert("RGB")
        return tuple(int(v) for v in im.getpixel((0, 0)))
    c.fail("Sesion grafica sin detectar: no hay ruta de pixel.", sesion=sesion)


def cmd_pixel_linux(args):
    if not c.dentro_de_virtual(args.x, args.y):
        v = c.tamano_virtual()
        c.fail("Pixel (%d, %d) fuera del bounding de layout "
               "(x %d..%d, y %d..%d). Mapa: monitores.py listar."
               % (args.x, args.y, v["x"], v["x"] + v["ancho"] - 1,
                  v["y"], v["y"] + v["alto"] - 1))
    r, g, b = _leer_pixel_linux(args.x, args.y)
    sesion = c.deteccion_sesion()
    via = ("pyautogui.pixel (X11; debajo Pillow XCB o scrot [runtime])"
           if sesion == "x11" else "grim -g \"x,y 1x1\" - + PIL (stdout)")
    c.json_out({"x": args.x, "y": args.y, "r": r, "g": g, "b": b,
                "marco": c.MARCO, "nota": "marco historico: layout",
                "sesion": sesion, "via": via})


def _split_mientras_linux(cadena):
    """argv de --mientras en POSIX (shlex estandar)."""
    import shlex

    partes = shlex.split(cadena)
    if not partes:
        c.fail("--mientras quedo vacio: pasa el argv COMPLETO del disparador "
               "entre comillas, p. ej. --mientras \"python3 "
               "scripts/teclado.py tecla enter\".")
    return partes


def _lanzar_mientras_linux(args):
    """IMPL-K P1.2-c (espejo de la rama Windows): dispara el argv como hijo
    con start_new_session (desvinculado del terminal; su stdout va por PIPE
    al JSON combinado). Sin flag => (None, None)."""
    if not getattr(args, "mientras", None):
        return None, None
    argv = _split_mientras_linux(args.mientras)
    try:
        proc = subprocess.Popen(argv, shell=False, start_new_session=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
    except OSError as exc:
        c.fail("El disparador de --mientras no arranco (%s): %s: %s"
               % (" ".join(argv), type(exc).__name__, exc))
    time.sleep(0.3)
    return proc, argv


def _recolectar_mientras_linux(proc, argv, espera_extra=10.0):
    """('accion' {argv, rc, json} del hijo; timeout => kill honesto)."""
    try:
        out, _err = proc.communicate(timeout=espera_extra)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _err = proc.communicate()
        return {"argv": argv, "rc": None,
                "json": {"error": "el hijo de --mientras no retorno en "
                                  "%.0f s (matado)" % espera_extra}}
    texto = (out or b"").decode("utf-8", "replace")
    try:
        dados = json.loads(texto)
    except ValueError:
        dados = {"_crudo": texto[:400]}
    return {"argv": argv, "rc": rc, "json": dados}


def cmd_esperar_linux(args):
    """Pausa fija/adaptativa + disparador hijo --mientras (P1.2-c).
    --auto-pixel es exclusivo de la rama Windows (scanner de doble muestra
    sobre ImageGrab all_screens; en Wayland grim 1x1 lo haria caro)."""
    c.checar_abort("esperar")  # bandera dura al inicio (luego, por poll)
    c.checar_pausa()           # PAUSA: la espera arranca cuando se libera
    proc, argv = _lanzar_mientras_linux(args)
    try:
        return _esperar_normal_linux(args, proc, argv)
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()  # validacion/ABORT: sin hijos huesrfanos


def _esperar_normal_linux(args, proc, argv):
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
            pr, pg, pb = _leer_pixel_linux(x, y)
            return (abs(pr - color[0]) <= tol and abs(pg - color[1]) <= tol
                    and abs(pb - color[2]) <= tol)

        cumplida, ms_esperados = c.esperar_color(
            _coincide, args.cambia, args.estable, limite, 0.1, inicio,
            c.checar_aborto_espera)
        resultado = {
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
        }
        if proc is not None:
            resultado["accion"] = _recolectar_mientras_linux(proc, argv)
        c.json_out(resultado)
        return
    ms = c.cap_ms(args.milisegundos)
    c.dormir(ms, c.checar_aborto_espera)
    resultado = {
        "cumplida": True,
        "ms_esperados": ms,
        "modo": "fijo",
        "marco": c.MARCO,
        "sesion": c.deteccion_sesion(),
        "nota": "sueno simple (default 320 ms, cap 30000) para dejar "
                "renderizar la UI; la bandera ABORT del .tmp corta la espera; "
                "PAUSA la posterga",
    }
    if proc is not None:
        resultado["accion"] = _recolectar_mientras_linux(proc, argv)
    c.json_out(resultado)


def cmd_localizar_linux(args):
    if c.deteccion_sesion() != "x11":
        c.fail("localizar (locateOnScreen) exige pyautogui, que en Wayland "
               "NATIVO no ve el compositor (solo XWayland, refs "
               "linux-python.md §4): haz 'capturar' y decide con vision.",
               sesion=c.deteccion_sesion())
    if not os.path.isfile(args.imagen):
        c.fail("La imagen a buscar no existe: %s" % os.path.abspath(args.imagen))
    pa = c._pyautogui()
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


def construir_parser_linux():
    parser = c.Parser(
        prog="pantalla.py (linux)",
        description="Capturas e inspeccion de pantalla en Linux: X11 via "
                    "pyautogui (subproceso cero: libreria Python) y Wayland "
                    "via grim; coords de LAYOUT. Mapa: monitores.py listar.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_DOC_LINUX.split("Subcomandos:")[1] if _DOC_LINUX and "Subcomandos:" in _DOC_LINUX else None,
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
    p.set_defaults(func=cmd_capturar_linux)

    p = sub.add_parser("tamano", help="resolucion del primario (o --virtual)")
    p.add_argument("--virtual", action="store_true",
                   help="bounding de LAYOUT + origen de todos los monitores")
    p.set_defaults(func=cmd_tamano_linux)

    p = sub.add_parser("posicion", help="posicion actual del cursor (X11)")
    p.set_defaults(func=cmd_posicion_linux)

    p = sub.add_parser("pixel", help="color RGB de un pixel (coords de layout)")
    p.add_argument("x", type=int, help="coordenada X de layout")
    p.add_argument("y", type=int, help="coordenada Y de layout")
    p.set_defaults(func=cmd_pixel_linux)

    p = sub.add_parser("esperar", help="pausa fija (--milisegundos) o "
                       "adaptativa por pixel (--pixel --color "
                       "--cambia|--estable)")
    # TIEMPOS-K: default 400->320 (-20% exacto, piso 250 respetado): es la
    # espera de RENDER del loop (accion->esperar->capturar); la evidencia del
    # autotest 06/10 mostro 0 FAIL con 320. Cap 30000 intacto (limite C).
    p.add_argument("--milisegundos", type=int, default=320, metavar="N",
                   help="pausa fija en ms (default 320, cap 30000)")
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
    p.add_argument("--mientras", metavar="ARGV",
                   help="lanza el DISPARADOR como hijo durante la espera "
                        "(argv entre comillas; JSON suma 'accion' "
                        "{argv, rc, json}) — espejo de Windows (P1.2-c)")
    p.set_defaults(func=cmd_esperar_linux)

    p = sub.add_parser("localizar", help="buscar una imagen en pantalla "
                       "(locateOnScreen; SOLO X11)")
    p.add_argument("imagen", help="ruta del PNG/JPG a buscar")
    p.add_argument("--region", type=int, nargs=4, metavar=("X", "Y", "ANCHO", "ALTO"),
                   help="limitar la busqueda (coords de layout; [runtime])")
    p.add_argument("--confidence", type=float,
                   help="umbral 0-1; REQUIERE opencv-python, sin el degrada a "
                        "coincidencia exacta")
    p.set_defaults(func=cmd_localizar_linux)

    return parser


# ===========================================================================
# SECCION macOS — cuerpos de scripts/macos/pantalla.py movados VERBATIM
# (sufijo _mac; `c` = scripts/macos/macos_especiales.py, bind-eeado en
# main()). Primitivas ya en la libreria y NO copiadas aqui: _screencapture,
# subprocess_run, _mon_listar, _capturar_rect, _captura_virtual,
# _pixel_punto (se llaman via c.). Suben con sufijo: _REGLA_MAC (constante de
# seccion, sin conflicto de nombre), _resolver_monitor_mac, _bounding_de_mac,
# _color_coincide_mac y los cmd_*. Marco: puntos_logicos.
# ===========================================================================

_DOC_MAC = """pantalla.py — Capturas e inspeccion visual en macOS (skill computer-use-py).

Marco: PUNTOS LOGICOS del espacio global (origen = sup-izq del display
principal; ver monitores.py listar). RETINA: screencapture produce PNGs al
doble de pixeles que los puntos pedidos [runtime por panel] — por eso TODO
JSON de captura trae "origen", "px_por_unidad_coord" (factor TOTAL
imagen->punto: Retina y --max-lado ya absorbidos; unica cifra para re-escalar),
"escala" (solo thumbnail), "escala_retina" y "regla": los CLICS van en puntos
lógicos, nunca en pixeles de la imagen. Marco enum: "puntos_logicos".

Ruta (contrato: todo corre sobre Python): el PNG lo produce la herramienta
nativa `screencapture` por subprocess desde este codigo Python (man
VERIFICADO: -x sin sonido, -R x,y,w,h, -D n con "1 is main, 2 secondary",
-c clipboard, -r sin metadata DPI, -t formato). Sin flags multiple-monitor,
el man declara "1 file per screen": NO hay un PNG unico del bounding, asi
que --monitor virtual captura monitor a monitor con -D y lo compone con PIL.
Prioriza -R (rect en puntos leidos de CGDisplayBounds) sobre -D (ordinal
posiblemente inestable [runtime]).

Salida: JSON por stdout; errores JSON con "error".

Subcomandos (verbos identicos a la version Windows):
  capturar   PNG: default display principal; --monitor
             <indice|primario|virtual|nombre>, --region x y w h (puntos
             globales; negativos posibles [runtime]), --max-lado N
             (thumbnail LANCZOS) y --archivo.
  tamano     Puntos del principal; con --virtual, bounding de todos.
  posicion   Cursor (CGEventGetLocation / pynput) en puntos.
  pixel      Color RGB de un punto (mini-captura 1pt + PIL).
   esperar   Pausa fija --milisegundos N o adaptativa --pixel X Y --color
             r,g,b --cambia|--estable M (poll por mini-capturas; la bandera
             .tmp/ABORT de vigilar.py corta).
  localizar  Solo con opencv-python y una imagen fuente: mini-captura +
             matchTemplate; sin cv2, error honesto.

Ejemplos (desde la carpeta computer-use-py, en el Mac):
  python3 scripts/pantalla.py capturar
  python3 scripts/pantalla.py capturar --monitor 1 --max-lado 1280
  python3 scripts/pantalla.py capturar --region 100 80 640 480
  python3 scripts/pantalla.py esperar --milisegundos 480
  python3 scripts/pantalla.py pixel 300 200
"""

# Redaccion ESPEJO del fix W11 de la rama Windows (IMPL-K P0.3): la regla
# DIVIDE y ppu = escala_retina/escala (INVERSO de 'escala' por el lado del
# thumbnail; 'escala' = fuente/imagen).
_REGLA_MAC = (
    "coordenada_puntos_x = origen[0] + x_en_la_imagen / px_por_unidad_coord; "
    "coordenada_puntos_y = origen[1] + y_en_la_imagen / px_por_unidad_coord. "
    "'px_por_unidad_coord' es el factor TOTAL imagen->punto logico: ya "
    "incluye RETINA (escala_retina, p. ej. 2.0) y el recorte --max-lado en UN "
    "solo campo (ppu = escala_retina/escala: es el INVERSO de 'escala' — "
    "'escala' vale fuente/imagen, por eso la formula DIVIDE) — NO "
    "multipliques 'escala' y 'escala_retina' a mano; 'escala' queda solo "
    "como factor fuente->imagen del thumbnail. Si el campo viene null (via "
    "-D sin mapa de posiciones), mide primero: captura una region conocida y "
    "divide px/puntos. Los CLICS van en PUNTOS LOGICOS."
)


def _resolver_monitor_mac(valor):
    """--monitor: None si 'virtual' | dict del monitor (mismos criterios
    que en Windows: indice, 'primario', subcadena del nombre).

    El algoritmo es el generico de _core.resolver_monitor; aqui solo la
    FUENTE de la lista (la cadena de fallback de monitores.py) y los TEXTOS
    historicos de la rama."""
    return c.resolver_monitor(
        valor, lambda: c._mon_listar()[0],
        sin_primario="Ningun monitor figura como primario. Revisa "
                     "monitores.py listar.",
        indice_rango="Indice de monitor %d fuera de rango (0..%d). "
                     "Mapa: monitores.py listar.",
        ambiguo="La subcadena %r coincide con varios monitores (%s): usa el "
                "indice.",
        sin_nombre="Ningun monitor tiene el nombre %r. Mapa: monitores.py "
                   "listar.")


def cmd_capturar_mac(args):
    via = None
    aviso = None
    origen = [0, 0]
    puntos = None
    extra = {}
    # Destino con la convencion generica de la skill (_core.ruta_destino_captura).
    destino = c.ruta_destino_captura(args.archivo)

    mons, via_mapa = c._mon_listar()
    if args.monitor is not None:
        m = _resolver_monitor_mac(args.monitor)
        if m is None:  # virtual: composing
            info = c._captura_virtual(destino, mons)
            origen = info["origen"]
            puntos = info["puntos"]
            extra = {"escala_retina": info["escala_retina"],
                     "via_mapa": via_mapa}
            aviso = info["nota_extra"]
            via = "screencapture por monitor + composicion PIL"
        elif args.region is not None:
            x, y, w, h = args.region
            if m["izq"] is None:
                c.fail("La region relativa exige las posiciones del monitor "
                       "(CGDisplayBounds): via de mapa %s no las tiene. "
                       "pip3 install pyobjc-framework-Quartz." % via_mapa)
            if w <= 0 or h <= 0:
                c.fail("Region invalida: ancho/alto deben ser > 0.")
            if x < 0 or y < 0 or x + w > m["ancho"] or y + h > m["alto"]:
                c.fail("Region (%d, %d, %d, %d) fuera del monitor %r "
                       "(%dx%d): con --monitor la region es RELATIVA a ese "
                       "monitor." % (x, y, w, h, m["nombre"],
                                      m["ancho"], m["alto"]))
            rect = (m["izq"] + x, m["top"] + y, w, h)
            origen = [rect[0], rect[1]]
            puntos = {"ancho": w, "alto": h}
            via, aviso = c._capturar_rect(destino, rect,
                                        display_fallback=m["indice"] + 1)
        else:
            if m["izq"] is None:
                c.fail("Via de mapa %s sin posiciones: usa --monitor por "
                       "ordinal con via -D o instala pyobjc-framework-Quartz."
                       % via_mapa)
            rect = (m["izq"], m["top"], m["ancho"], m["alto"])
            origen = [m["izq"], m["top"]]
            puntos = {"ancho": m["ancho"], "alto": m["alto"]}
            via, aviso = c._capturar_rect(destino, rect,
                                        display_fallback=m["indice"] + 1)
    elif args.region is not None:
        x, y, w, h = args.region
        if w <= 0 or h <= 0:
            c.fail("Region invalida: ancho/alto deben ser > 0 (x e y ACEPTAN "
                   "negativos si tu arrangement los da: coordenadas del "
                   "espacio global).")
        v = _bounding_de_mac(mons)
        if not (v["x"] <= x and v["y"] <= y
                and x + w <= v["x"] + v["ancho"]
                and y + h <= v["y"] + v["alto"]):
            c.fail("Region (%d, %d, %d, %d) fuera del bounding virtual "
                   "(x %d..%d, y %d..%d). Mapa: monitores.py listar."
                   % (x, y, w, h, v["x"], v["x"] + v["ancho"] - 1,
                      v["y"], v["y"] + v["alto"] - 1))
        origen = [x, y]
        puntos = {"ancho": w, "alto": h}
        via, aviso = c._capturar_rect(destino, (x, y, w, h))
    else:
        # default historico: display PRINCIPAL completo
        principal = [m for m in mons if m["primario"]]
        if principal and principal[0]["izq"] is not None:
            m = principal[0]
            rect = (m["izq"], m["top"], m["ancho"], m["alto"])
            origen = [m["izq"], m["top"]]
            puntos = {"ancho": m["ancho"], "alto": m["alto"]}
            via, aviso = c._capturar_rect(destino, rect,
                                        display_fallback=m["indice"] + 1)
        else:
            via, aviso = c._capturar_rect(destino, None, display_fallback=1)
            puntos = None  # sin mapa de posiciones: escala se mide igualmente

    # medir PNG: pixels reales y factor retina
    im = c.pil_open(destino)
    fis_w, fis_h = int(im.width), int(im.height)
    im.close()
    escala_rx = escala_ry = None
    if puntos:
        escala_rx, escala_ry, _sz = c.escala_retina(
            destino, puntos["ancho"], puntos["alto"])

    if args.max_lado is not None:
        # Chequeo y factor del recorte: genericos en _core (el texto canonico
        # es el de la rama Windows, validada en escritorio real).
        c.checar_max_lado(args.max_lado)
        from PIL import Image
        im = c.pil_open(destino)
        im.thumbnail((args.max_lado, args.max_lado), Image.LANCZOS)
        im.save(destino)
        ancho_final, alto_final = int(im.width), int(im.height)
        im.close()
    else:
        ancho_final, alto_final = fis_w, fis_h
    escala_x, escala_y = c.escalas_thumbnail(fis_w, fis_h,
                                             ancho_final, alto_final)

    try:
        pw, ph = c.tamano_pantalla()
    except SystemExit:
        pw = ph = None  # sin pyobjc: metadatos opcionales, no bloquean
    try:
        cx, cy = c.posicion_cursor()
    except SystemExit:
        cx = cy = None
    esc_ret = escala_rx if escala_rx is not None else extra.get("escala_retina")
    # P0-3 (CRITICO): factor TOTAL imagen->coordenada en UN campo: Retina ya
    # queda absorbido y el agente no multiplica 'escala' x 'escala_retina' a
    # mano. null cuando la via (-D sin mapa) no permite medirlo (honesto).
    # FIX IMPL-K P0.3 (espejo del fix W11 de Windows): la regla DIVIDE, o sea
    # que ppu = pixels-de-imagen por punto logico = esc_ret / escala_x
    # (escala_x = fuente/imagen >= 1 en thumbnail; multiplicarlo invertia el
    # sentido con --max-lado: clic descolocado un factor ppu^2). Sin thumbnail
    # escala_x=1.0 y el valor coincide con el historico. [runtime]
    px_por_unidad_coord = (round(esc_ret / escala_x, 6)
                           if esc_ret else None)
    item = {
        "ok": True,
        "archivo": destino,
        "ancho": ancho_final,
        "alto": alto_final,
        "fisico": {"ancho": fis_w, "alto": fis_h},
        "origen": origen,
        "puntos": puntos,
        "escala": round(escala_x, 6),
        "escala_y": round(escala_y, 6),
        "px_por_unidad_coord": px_por_unidad_coord,
        "marco": c.MARCO,
        "escala_retina": esc_ret,
        "unidad": "puntos logicos (clics AQUI, no en pixeles de la imagen)",
        "regla": _REGLA_MAC,
        "pantalla": None if pw is None else {"ancho": pw, "alto": ph},
        "cursor": None if cx is None else {"x": cx, "y": cy},
        "via": via,
        "nota": "leer este PNG con vision y decidir desde ahi; NO hardcodear "
                "coordenadas de sesiones anteriores; 'origen' es la esquina "
                "sup-izq de la captura en puntos del espacio global; "
                "px_por_unidad_coord" + (
                    " null: la via -D sin mapa de posiciones no permite medir "
                    "Retina aqui [runtime]: verifica el factor con una "
                    "captura de prueba."
                    if px_por_unidad_coord is None else
                    " = imagen_px / punto_logico (Retina y --max-lado "
                    "ya incluidos)."),
    }
    if aviso:
        item["aviso"] = aviso
    c.json_out(item)


def _bounding_de_mac(mons):
    """Bounding sin duplicar logica: reutiliza el helper de monitores.py."""
    import monitores
    return monitores._bounding_mac(mons)


def cmd_tamano_mac(args):
    if args.virtual:
        mons, via = c._mon_listar()
        v = _bounding_de_mac(mons)
        c.json_out({
            "ancho": v["ancho"],
            "alto": v["alto"],
            "origen": [v["x"], v["y"]],
            "unidad": "puntos logicos",
            "via": via,
            "marco": c.MARCO,
            "nota": "marco historico: pantalla VIRTUAL, bounding de todos los "
                     "monitores (calculado desde CGDisplayBounds); rectangulo "
                     "por monitor: monitores.py listar",
        })
        return
    w, h = c.tamano_pantalla()
    c.json_out({
        "ancho": w,
        "alto": h,
        "unidad": "puntos logicos",
        "marco": c.MARCO,
        "nota": "puntos del display PRINCIPAL (CGDisplayBounds); en Retina "
                "las capturas salen al doble de pixeles: el espacio virtual "
                "completo es tamano --virtual",
    })


def cmd_posicion_mac(args):
    x, y = c.posicion_cursor()
    c.json_out({"x": x, "y": y,
                "unidad": "puntos logicos",
                "marco": c.MARCO,
                "nota": "espacio global (0,0 = sup-izq del display principal; "
                        "coincide con los puntos de las capturas)"})


def _color_coincide_mac(x, y, color, tol):
    r, g, b = c._pixel_punto(x, y)
    cr, cg, cb = color
    return abs(r - cr) <= tol and abs(g - cg) <= tol and abs(b - cb) <= tol


def cmd_pixel_mac(args):
    if c.quartz_disponible() and not c.dentro_de_virtual(args.x, args.y):
        mons, _via = c._mon_listar()
        v = _bounding_de_mac(mons)
        c.fail("Pixel (%d, %d) fuera de la pantalla virtual "
               "(x %d..%d, y %d..%d). Mapa: monitores.py listar."
               % (args.x, args.y, v["x"], v["x"] + v["ancho"] - 1,
                  v["y"], v["y"] + v["alto"] - 1))
    if c.quartz_disponible():
        m = c._monitor_contiene(args.x, args.y)
        if m is None:
            c.fail("Pixel (%d, %d) no cae dentro de ningun monitor (hueco "
                   "del bounding virtual)." % (args.x, args.y))
    r, g, b = c._pixel_punto(args.x, args.y)
    c.json_out({"x": args.x, "y": args.y,
                "r": int(r), "g": int(g), "b": int(b),
                "unidad": "puntos logicos",
                "marco": c.MARCO,
                "nota": "marco historico: espacio global",
                "via": "screencapture -R 1pt + PIL (1 px de imagen puede "
                       "ser 2x2 en Retina: se toma el centro [runtime])"})


def _split_mientras_mac(cadena):
    """argv de --mientras en macOS (shlex estandar, como linux)."""
    import shlex

    partes = shlex.split(cadena)
    if not partes:
        c.fail("--mientras quedo vacio: pasa el argv COMPLETO del disparador "
               "entre comillas, p. ej. --mientras \"python3 "
               "scripts/teclado.py tecla enter\".")
    return partes


def _lanzar_mientras_mac(args):
    """IMPL-K P1.2-c (espejo mac): hijo con start_new_session; sin flag =>
    (None, None)."""
    if not getattr(args, "mientras", None):
        return None, None
    argv = _split_mientras_mac(args.mientras)
    try:
        proc = subprocess.Popen(argv, shell=False, start_new_session=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
    except OSError as exc:
        c.fail("El disparador de --mientras no arranco (%s): %s: %s"
               % (" ".join(argv), type(exc).__name__, exc))
    time.sleep(0.3)
    return proc, argv


def _recolectar_mientras_mac(proc, argv, espera_extra=10.0):
    try:
        out, _err = proc.communicate(timeout=espera_extra)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _err = proc.communicate()
        return {"argv": argv, "rc": None,
                "json": {"error": "el hijo de --mientras no retorno en "
                                  "%.0f s (matado)" % espera_extra}}
    texto = (out or b"").decode("utf-8", "replace")
    try:
        dados = json.loads(texto)
    except ValueError:
        dados = {"_crudo": texto[:400]}
    return {"argv": argv, "rc": rc, "json": dados}


def cmd_esperar_mac(args):
    """Pausa fija/adaptativa + disparador hijo --mientras (P1.2-c).
    --auto-pixel es exclusivo de la rama Windows (doble muestra ImageGrab;
    aqui cada muestra es un screencapture caro)."""
    c.checar_abort()   # bandera dura al inicio (luego, por poll); motivo
                       # default 'interrumpido' = mensaje historico de mac
    c.checar_pausa()   # P1-5: con PAUSA la espera arranca al liberarse
    proc, argv = _lanzar_mientras_mac(args)
    try:
        return _esperar_normal_mac(args, proc, argv)
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()  # sin hijos huesrfanos


def _esperar_normal_mac(args, proc, argv):
    inicio = time.monotonic()
    # Coherencia de flags y bucles: genericos en _core (copias identicas de
    # las 3 ramas). Lo propio de mac —mini-captura screencapture 1pt por
    # sondeo y su check ABORT sin motivo— llega al bucle por callbacks.
    if c.checar_args_esperar(args.pixel, args.color, args.cambia, args.estable):
        x, y = args.pixel
        if c.quartz_disponible() and not c.dentro_de_virtual(x, y):
            mons, _via = c._mon_listar()
            v = _bounding_de_mac(mons)
            c.fail("Pixel (%d, %d) fuera de la pantalla virtual "
                   "(x %d..%d, y %d..%d)."
                   % (x, y, v["x"], v["x"] + v["ancho"] - 1,
                      v["y"], v["y"] + v["alto"] - 1))
        color = c.parsear_color(args.color)
        tol = args.tolerancia
        c.validar_tolerancia(tol)
        limite = c.cap_timeout_esperar(args.timeout)
        cumplida, ms_esperados = c.esperar_color(
            lambda: _color_coincide_mac(x, y, color, tol),
            args.cambia, args.estable, limite, 0.25, inicio,
            c.checar_abort)  # poll ~250 ms: mini-captura mas cara que Win
        resultado = {
            "cumplida": bool(cumplida),
            "ms_esperados": ms_esperados,
            "modo": "cambia" if args.cambia else "estable",
            "pixel": [int(x), int(y)],
            "color": list(color),
            "tolerancia": tol,
            "timeout_s": limite,
            "marco": c.MARCO,
            "nota": "marco historico: espacio global (puntos logicos); "
                    "poll ~250 ms por mini-captura screencapture (mas caro "
                    "que en Windows: para esperas largas prefiere "
                    "--milisegundos); timeout agotado => cumplida=false SIN "
                    "error (el agente decide); la bandera .tmp/ABORT de "
                    "vigilar.py corta la espera",
        }
        if proc is not None:
            resultado["accion"] = _recolectar_mientras_mac(proc, argv)
        c.json_out(resultado)
        return
    ms = c.cap_ms(args.milisegundos)
    c.dormir(ms, c.checar_abort)
    resultado = {
        "cumplida": True,
        "ms_esperados": ms,
        "modo": "fijo",
        "marco": c.MARCO,
        "nota": "sueno simple (default 320 ms, cap 30000) para dejar "
                "renderizar la UI; la bandera ABORT de vigilar.py corta la "
                "espera; PAUSA la posterga",
    }
    if proc is not None:
        resultado["accion"] = _recolectar_mientras_mac(proc, argv)
    c.json_out(resultado)


def cmd_localizar_mac(args):
    if not os.path.isfile(args.imagen):
        c.fail("La imagen a buscar no existe: %s" % os.path.abspath(args.imagen))
    try:
        import cv2
    except ImportError:
        c.fail("localizar requiere opencv-python: pip3 install opencv-python. "
               "Sin OpenCV la skill NO degrada a coincidencia exacta en mac "
               "(seria lenta y fragil): usa pantalla.py capturar + vision.",
               pista="el anti-patron del loop es locate cada iteracion: 1-2 s "
                     "por llamada; usa vision sobre la captura")
    # fuente de imagen: region pedida o display principal completo
    destino = os.path.join(c.asegurar_capturas(), "_locate_%d.png" % os.getpid())
    origen = [0, 0]
    puntos = None
    if args.region is not None:
        x, y, w, h = args.region
        if w <= 0 or h <= 0:
            c.fail("Region invalida: ancho/alto deben ser > 0.")
        puntos = {"ancho": w, "alto": h}
        origen = [x, y]
        c._capturar_rect(destino, (x, y, w, h))
    else:
        mons, via = c._mon_listar()
        principal = [m for m in mons if m["primario"]]
        if principal and principal[0]["izq"] is not None:
            m = principal[0]
            puntos = {"ancho": m["ancho"], "alto": m["alto"]}
            origen = [m["izq"], m["top"]]
            c._capturar_rect(destino, (m["izq"], m["top"], m["ancho"], m["alto"]),
                           display_fallback=m["indice"] + 1)
        else:
            c._capturar_rect(destino, None, display_fallback=1)

    gran = cv2.imread(destino)
    plantilla = cv2.imread(args.imagen)
    if gran is None or plantilla is None:
        c.fail("cv2 no pudo leer %s o %s" % (destino, args.imagen))
    gh, gw = gran.shape[:2]
    ph, pw = plantilla.shape[:2]
    if pw > gw or ph > gh:
        c.json_out({"encontrado": False, "imagen": os.path.abspath(args.imagen),
                    "marco": c.MARCO,
                    "nota": "la plantilla es mas grande que la zona capturada"})
        return
    res = cv2.matchTemplate(gran, plantilla, cv2.TM_CCOEFF_NORMED)
    _minv, maxv, _minl, topleft = cv2.minMaxLoc(res)
    conf = 0.999 if args.confidence is None else args.confidence
    if args.confidence is not None:
        c.validar_confidence(args.confidence)
    if maxv < conf:
        c.json_out({
            "encontrado": False,
            "imagen": os.path.abspath(args.imagen),
            "marco": c.MARCO,
            "mejor_similitud": round(float(maxv), 4),
            "nota": "umbral %s no alcanzado; locate exige pixeles casi "
                    "identicos (tema/antialiasing/Retina lo rompen): para el "
                    "loop normal usa capturar + vision" % conf,
        })
        return
    x_im, y_im = topleft
    # imagen px -> puntos logicos (factor retina medido; fallback 2.0)
    if puntos:
        ex, _ey, _sz = c.escala_retina(destino, puntos["ancho"], puntos["alto"])
    else:
        ex = 2.0  # Retina tipica [runtime]
    f = ex if ex and ex > 0 else 1.0
    box = [int(origen[0] + x_im / f), int(origen[1] + y_im / f),
           int(round(pw / f)), int(round(ph / f))]
    centro = [box[0] + box[2] // 2, box[1] + box[3] // 2]
    try:
        os.remove(destino)
    except OSError:
        pass
    c.json_out({
        "encontrado": True,
        "imagen": os.path.abspath(args.imagen),
        "box": box,
        "centro": centro,
        "confianza": round(float(maxv), 4),
        "marco": c.MARCO,
        "unidad": "puntos logicos (marco virtual global)",
        "nota": "box/centro ya convertidos de pixeles de imagen a PUNTOS con "
                "la escala retina medida (%.2f): listos para raton.py" % f,
    })


def construir_parser_mac():
    parser = c.Parser(
        prog="pantalla.py (macOS)",
        description="Capturas e inspeccion de pantalla en macOS via la "
                    "herramienta nativa screencapture llamada desde Python. "
                    "Coordenadas = PUNTOS LOGICOS del espacio global "
                    "(origen = sup-izq del display principal). Mapa: "
                    "monitores.py listar.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_DOC_MAC.split("Subcomandos (verbos identicos a la")[1]
        if _DOC_MAC and "Subcomandos (verbos identicos a la" in _DOC_MAC else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True,
                                metavar="SUBCOMANDO")

    p = sub.add_parser("capturar", help="guardar un PNG (principal, monitor, "
                        "virtual o region en puntos globales)")
    p.add_argument("--region", type=int, nargs=4,
                   metavar=("X", "Y", "ANCHO", "ALTO"),
                   help="recorte en PUNTOS del espacio global (negativos "
                        "posibles segun arrangement [runtime]). Con "
                        "--monitor, la region es RELATIVA a ese monitor")
    p.add_argument("--monitor", metavar="OBJETO",
                   help="indice (0,1,...), 'primario', 'virtual' (mosaico "
                        "completo) o subcadena del nombre")
    p.add_argument("--max-lado", dest="max_lado", type=int, metavar="N",
                   help="thumbnail LANCZOS de lado maximo N ANTES de guardar "
                        "(ahorra tokens): re-escala con 'regla' del JSON")
    p.add_argument("--archivo", help="nombre o ruta destino del PNG (nombre "
                   "pelado cae en .tmp/capturas; por defecto "
                   "captura_<fecha_hora>.png)")
    p.set_defaults(func=cmd_capturar_mac)

    p = sub.add_parser("tamano", help="puntos del principal (o --virtual)")
    p.add_argument("--virtual", action="store_true",
                   help="bounding de TODOS los monitores + origen")
    p.set_defaults(func=cmd_tamano_mac)

    p = sub.add_parser("posicion", help="posicion actual del cursor (puntos)")
    p.set_defaults(func=cmd_posicion_mac)

    p = sub.add_parser("pixel", help="color RGB de un punto (puntos logicos)")
    p.add_argument("x", type=int, help="coordenada X global (negativa posible)")
    p.add_argument("y", type=int, help="coordenada Y global")
    p.set_defaults(func=cmd_pixel_mac)

    p = sub.add_parser("esperar", help="pausa fija (--milisegundos) o "
                        "adaptativa por pixel (--pixel --color "
                        "--cambia|--estable)")
    # TIEMPOS-K: default 400->320 (-20% exacto, piso 250 respetado): es la
    # espera de RENDER del loop (accion->esperar->capturar); la evidencia del
    # autotest 06/10 mostro 0 FAIL con 320. Cap 30000 intacto (limite C).
    p.add_argument("--milisegundos", type=int, default=320, metavar="N",
                   help="pausa fija en ms (default 320, cap 30000)")
    p.add_argument("--pixel", type=int, nargs=2, metavar=("X", "Y"),
                   help="espera adaptativa: punto a vigilar (puntos globales)")
    p.add_argument("--color", metavar="R,G,B",
                   help="color esperado (p. ej. 255,255,255); con --pixel")
    p.add_argument("--tolerancia", type=int, default=0, metavar="T",
                   help="tolerancia por canal 0-255 (default 0)")
    grupo = p.add_mutually_exclusive_group()
    grupo.add_argument("--cambia", action="store_true",
                       help="cumplir cuando el punto DEJE de coincidir con "
                            "--color")
    grupo.add_argument("--estable", type=int, metavar="M",
                       help="cumplir tras M ms de coincidencia continua con "
                            "--color")
    p.add_argument("--timeout", type=float, default=10.0, metavar="S",
                   help="segundos maximos del poll (default 10, cap 120; "
                        "agotarlo NO es error: cumplida=false)")
    p.add_argument("--mientras", metavar="ARGV",
                   help="lanza el DISPARADOR como hijo durante la espera "
                        "(argv entre comillas; JSON suma 'accion' "
                        "{argv, rc, json}) — espejo de Windows (P1.2-c)")
    p.set_defaults(func=cmd_esperar_mac)

    p = sub.add_parser("localizar", help="buscar una imagen en pantalla "
                        "(requiere opencv-python; zona: --region o principal)")
    p.add_argument("imagen", help="ruta del PNG/JPG a buscar")
    p.add_argument("--region", type=int, nargs=4,
                   metavar=("X", "Y", "ANCHO", "ALTO"),
                   help="limitar la busqueda a estos puntos (acelera)")
    p.add_argument("--confidence", type=float,
                   help="umbral 0-1 del matchTemplate (default ~exacto)")
    p.set_defaults(func=cmd_localizar_mac)

    return parser


def main():
    global c
    mod = _core.modulo_sistema()          # lee sys.platform EN TIEMPO DE EJECUCION
    if mod is None:
        _core.so_no_soportado("pantalla.py")  # JSON rc 2 contractual (nunca retorna)
    c = mod
    plat = sys.platform
    if plat == "win32":
        global pyautogui, Image, ImageGrab  # solo los que ESTE CLI usaba
        import pyautogui
        from PIL import Image, ImageGrab
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
        # FAILSAFE conservado de las dos rutas que lo traducian: el CLI win
        # catcheaba pyautogui.FailSafeException (clase) y la rama linux la
        # detectaba por nombre (lazismo del dominio); el JSON de
        # c.fallar_por_failsafe es el mismo en ambas.
        if type(exc).__name__ == "FailSafeException":
            c.fallar_por_failsafe(exc)
        c.fail("%s: %s" % (type(exc).__name__, exc))


if __name__ == "__main__":
    main()
