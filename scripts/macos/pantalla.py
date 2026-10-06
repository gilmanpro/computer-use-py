# -*- coding: utf-8 -*-
"""pantalla.py — Capturas e inspeccion visual en macOS (skill computer-use-py).

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
  python3 scripts/macos/pantalla.py capturar
  python3 scripts/macos/pantalla.py capturar --monitor 1 --max-lado 1280
  python3 scripts/macos/pantalla.py capturar --region 100 80 640 480
  python3 scripts/macos/pantalla.py esperar --milisegundos 600
  python3 scripts/macos/pantalla.py pixel 300 200
"""

import argparse
import os
import time

import _compartido_mac as c


_REGLA_MAC = (
    "coordenada_puntos_x = origen[0] + x_en_la_imagen / px_por_unidad_coord; "
    "coordenada_puntos_y = origen[1] + y_en_la_imagen / px_por_unidad_coord. "
    "'px_por_unidad_coord' es el factor TOTAL imagen->punto logico: ya "
    "incluye RETINA (escala_retina, p. ej. 2.0) y el recorte --max-lado "
    "(escala) en UN solo campo — NO multipliques escala y escala_retina a "
    "mano; 'escala' queda solo como factor del thumbnail. Si el campo viene "
    "null (via -D sin mapa de posiciones), mide primero: captura una region "
    "conocida y divide px/puntos. Los CLICS van en PUNTOS LOGICOS."
)


def _screencapture(destino, rect=None, display=None, silent=True):
    """Invoca screencapture -x [(-R x,y,w,h)|( -D n)] destino.

    VERIFICADO man: -x silencia; -R formato x,y,width,height; -D <display>.
    Unidades de -R: puntos lógicos [runtime]. Devuelve (rc, stderr).
    """
    cmd = ["screencapture"]
    if silent:
        cmd.append("-x")
    if rect is not None:
        x, y, w, h = rect
        cmd += ["-R", "%d,%d,%d,%d" % (int(x), int(y), int(w), int(h))]
    elif display is not None:
        cmd += ["-D", str(int(display))]
    else:
        c.fail("_screencapture interno: falta rect o display.")
    cmd.append(destino)
    try:
        p = subprocess_run(cmd)
    except FileNotFoundError:
        c.fail("screencapture no existe (esto solo corre en macOS).")
    return p.returncode, (p.stderr or b"").decode("utf-8", errors="replace")


def subprocess_run(cmd):
    import subprocess
    return subprocess.run(cmd, capture_output=True, timeout=60)


# _destino(archivo): la convencion de ruta (nombre pelado -> .tmp/capturas,
# con directorio se respeta, default captura_<fecha_hora>) es generica y vive
# en _core.ruta_destino_captura; cmd_capturar la llama directo.


def _resolver_monitor(valor):
    """--monitor: None si 'virtual' | dict del monitor (mismos criterios
    que en Windows: indice, 'primario', subcadena del nombre).

    El algoritmo es el generico de _core.resolver_monitor; aqui solo la
    FUENTE de la lista (la cadena de fallback de monitores.py) y los TEXTOS
    historicos de la rama."""
    return c.resolver_monitor(
        valor, lambda: _mon_listar()[0],
        sin_primario="Ningun monitor figura como primario. Revisa "
                     "monitores.py listar.",
        indice_rango="Indice de monitor %d fuera de rango (0..%d). "
                     "Mapa: monitores.py listar.",
        ambiguo="La subcadena %r coincide con varios monitores (%s): usa el "
                "indice.",
        sin_nombre="Ningun monitor tiene el nombre %r. Mapa: monitores.py "
                   "listar.")


def _mon_listar():
    """Reutiliza la cadena de fallback de monitores.py sin duplicarla."""
    import monitores
    return monitores._colectar()


def _capturar_rect(destino, rect, display_fallback=None):
    """-R con rect en puntos; si falla y hay -D, degrada al ordinal con aviso.

    Las coordenadas negativas en -R son [runtime]: si screencapture rechaza,
    se reintenta por --monitor -D y se avisa en el JSON. Con rect=None se usa
    directamente -D (display_fallback o 1 = principal, "1 is main" VERIFICADO
    man).
    """
    if rect is None:
        disp = int(display_fallback if display_fallback is not None else 1)
        rc, err = _screencapture(destino, display=disp)
        if rc == 0 and os.path.getsize(destino) > 0:
            return ("screencapture -D %d (1=principal, VERIFICADO man; el "
                    "PNG sale a 2x en Retina: se mide con PIL)" % disp), None
        c.fail("screencapture -D %d fallo (rc=%d): %s"
               % (disp, rc, err.strip()[:300]))
    rc, err = _screencapture(destino, rect=rect)
    if rc == 0 and os.path.getsize(destino) > 0:
        return "screencapture -R x,y,w,h (puntos logicos [runtime])", None
    aviso = None
    if display_fallback is not None:
        rc2, err2 = _screencapture(destino, display=display_fallback)
        if rc2 == 0 and os.path.getsize(destino) > 0:
            aviso = ("-R fallo (rc=%d: %s): capturado por -D %d, que captura "
                     "EL MONITOR ENTERO, no el rect pedido — origen/region "
                     "aplican solo si pediste un monitor completo "
                     "[runtime]" % (rc, err.strip()[:120], display_fallback))
            return ("screencapture -D %d (fallback)" % display_fallback), aviso
    c.fail("screencapture fallo (rc=%d): %s" % (rc, err.strip()[:300]),
           nota="si la region tiene x o y negativos, puede ser la "
                "limitacion [runtime] de -R: prueba --monitor")


def _captura_virtual(destino, mons):
    """Mosaico del bounding virtual: 1 captura por monitor + composicion PIL.

    VERIFICADO man: sin flags screencapture escribe 1 archivo por pantalla →
    no hay PNG unico nativo. Escala mixta: si un monitor retina 2x y otro
    1x, el mosaico usa la escala del PRINCIPAL y avisa [runtime].
    """
    from PIL import Image
    if any(m["izq"] is None for m in mons):
        c.fail("El mosaico virtual necesita las POSICIONES de cada monitor "
               "(CGDisplayBounds): la via de mapa actual no las tiene. "
               "pip3 install pyobjc-framework-Quartz y re-lista con "
               "monitores.py listar.")
    x0 = min(m["izq"] for m in mons)
    y0 = min(m["top"] for m in mons)
    x1 = max(m["der"] for m in mons)
    y1 = max(m["bot"] for m in mons)
    principal = [m for m in mons if m["primario"]][0]
    # escala retina del principal como base
    pr_base = os.path.join(c.asegurar_capturas(), "_retina_base.png")
    _capturar_rect(pr_base, (principal["izq"], principal["top"],
                             principal["ancho"], principal["alto"]),
                   display_fallback=(principal["indice"] + 1))
    ex, _ey, _sz = c.escala_retina(pr_base, principal["ancho"],
                                   principal["alto"])
    esc = int(round(ex)) if ex and ex > 1 else 1
    lienzo_w = (x1 - x0) * esc
    lienzo_h = (y1 - y0) * esc
    lienzo = Image.new("RGB", (lienzo_w, lienzo_h))
    avisos = []
    for m in mons:
        tmp = os.path.join(c.asegurar_capturas(), "_mons_%d.png" % m["indice"])
        _capturar_rect(tmp, (m["izq"], m["top"], m["ancho"], m["alto"]),
                       display_fallback=(m["indice"] + 1))
        im = Image.open(tmp)
        mx, _my, _sz = c.escala_retina(tmp, m["ancho"], m["alto"])
        if mx and esc and abs(mx - esc) > 0.25:
            im = im.resize((int(round(m["ancho"] * esc)),
                            int(round(m["alto"] * esc))), Image.LANCZOS)
            avisos.append("monitor %r re-escalado a la escala del principal "
                          "(%.2f→%d): mezcla de densidades [runtime]"
                          % (m["nombre"], mx, esc))
        lienzo.paste(im.convert("RGB"),
                     ((m["izq"] - x0) * esc, (m["top"] - y0) * esc))
        im.close()
    lienzo.save(destino)
    return {"origen": [x0, y0],
            "puntos": {"ancho": x1 - x0, "alto": y1 - y0},
            "escala_retina": esc,
            "nota_extra": "; ".join(avisos) if avisos else None}


def cmd_capturar(args):
    via = None
    aviso = None
    origen = [0, 0]
    puntos = None
    extra = {}
    # Destino con la convencion generica de la skill (_core.ruta_destino_captura).
    destino = c.ruta_destino_captura(args.archivo)

    mons, via_mapa = _mon_listar()
    if args.monitor is not None:
        m = _resolver_monitor(args.monitor)
        if m is None:  # virtual: composing
            info = _captura_virtual(destino, mons)
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
            via, aviso = _capturar_rect(destino, rect,
                                        display_fallback=m["indice"] + 1)
        else:
            if m["izq"] is None:
                c.fail("Via de mapa %s sin posiciones: usa --monitor por "
                       "ordinal con via -D o instala pyobjc-framework-Quartz."
                       % via_mapa)
            rect = (m["izq"], m["top"], m["ancho"], m["alto"])
            origen = [m["izq"], m["top"]]
            puntos = {"ancho": m["ancho"], "alto": m["alto"]}
            via, aviso = _capturar_rect(destino, rect,
                                        display_fallback=m["indice"] + 1)
    elif args.region is not None:
        x, y, w, h = args.region
        if w <= 0 or h <= 0:
            c.fail("Region invalida: ancho/alto deben ser > 0 (x e y ACEPTAN "
                   "negativos si tu arrangement los da: coordenadas del "
                   "espacio global).")
        v = _bounding_de(mons)
        if not (v["x"] <= x and v["y"] <= y
                and x + w <= v["x"] + v["ancho"]
                and y + h <= v["y"] + v["alto"]):
            c.fail("Region (%d, %d, %d, %d) fuera del bounding virtual "
                   "(x %d..%d, y %d..%d). Mapa: monitores.py listar."
                   % (x, y, w, h, v["x"], v["x"] + v["ancho"] - 1,
                      v["y"], v["y"] + v["alto"] - 1))
        origen = [x, y]
        puntos = {"ancho": w, "alto": h}
        via, aviso = _capturar_rect(destino, (x, y, w, h))
    else:
        # default historico: display PRINCIPAL completo
        principal = [m for m in mons if m["primario"]]
        if principal and principal[0]["izq"] is not None:
            m = principal[0]
            rect = (m["izq"], m["top"], m["ancho"], m["alto"])
            origen = [m["izq"], m["top"]]
            puntos = {"ancho": m["ancho"], "alto": m["alto"]}
            via, aviso = _capturar_rect(destino, rect,
                                        display_fallback=m["indice"] + 1)
        else:
            via, aviso = _capturar_rect(destino, None, display_fallback=1)
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
    px_por_unidad_coord = (round(escala_x * esc_ret, 6)
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


def _bounding_de(mons):
    """Bounding sin duplicar logica: reutiliza el helper de monitores.py."""
    import monitores
    return monitores._bounding(mons)


def cmd_tamano(args):
    if args.virtual:
        mons, via = _mon_listar()
        v = _bounding_de(mons)
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


def cmd_posicion(args):
    x, y = c.posicion_cursor()
    c.json_out({"x": x, "y": y,
                "unidad": "puntos logicos",
                "marco": c.MARCO,
                "nota": "espacio global (0,0 = sup-izq del display principal; "
                        "coincide con los puntos de las capturas)"})


def _pixel_punto(x, y):
    """(r,g,b) de un PUNTO via mini-captura -R 1x1 + PIL.

    En Retina el PNG sale 2x2px: se toma el centro de la muestra para
    robustez [runtime por el factor exacto]. Coste: 1 proceso screencapture
    por lectura (mas lento que Windows: documentado en esperar).
    """
    tmp = os.path.join(c.asegurar_capturas(), "_pixel_%d_%d.png" % (x, y))
    rc, err = _screencapture(tmp, rect=(x, y, 1, 1))
    if rc != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
        c.fail("pixel: screencapture -R %d,%d,1,1 fallo (rc=%d): %s"
               % (x, y, rc, err.strip()[:200]))
    im = c.pil_open(tmp)
    if im.mode != "RGB":
        im = im.convert("RGB")
    w, h = im.width, im.height
    rgb = im.getpixel((w // 2, h // 2))
    im.close()
    try:
        os.remove(tmp)
    except OSError:
        pass
    return tuple(rgb[:3])


def cmd_pixel(args):
    if c.quartz_disponible() and not c.dentro_de_virtual(args.x, args.y):
        mons, _via = _mon_listar()
        v = _bounding_de(mons)
        c.fail("Pixel (%d, %d) fuera de la pantalla virtual "
               "(x %d..%d, y %d..%d). Mapa: monitores.py listar."
               % (args.x, args.y, v["x"], v["x"] + v["ancho"] - 1,
                  v["y"], v["y"] + v["alto"] - 1))
    if c.quartz_disponible():
        m = c._monitor_contiene(args.x, args.y)
        if m is None:
            c.fail("Pixel (%d, %d) no cae dentro de ningun monitor (hueco "
                   "del bounding virtual)." % (args.x, args.y))
    r, g, b = _pixel_punto(args.x, args.y)
    c.json_out({"x": args.x, "y": args.y,
                "r": int(r), "g": int(g), "b": int(b),
                "unidad": "puntos logicos",
                "marco": c.MARCO,
                "nota": "marco historico: espacio global",
                "via": "screencapture -R 1pt + PIL (1 px de imagen puede "
                       "ser 2x2 en Retina: se toma el centro [runtime])"})


def _color_coincide(x, y, color, tol):
    r, g, b = _pixel_punto(x, y)
    cr, cg, cb = color
    return abs(r - cr) <= tol and abs(g - cg) <= tol and abs(b - cb) <= tol


def cmd_esperar(args):
    c.checar_abort()   # bandera dura al inicio (luego, por poll); motivo
                       # default 'interrumpido' = mensaje historico de mac
    c.checar_pausa()   # P1-5: con PAUSA la espera arranca al liberarse
    inicio = time.monotonic()
    # Coherencia de flags y bucles: genericos en _core (copias identicas de
    # las 3 ramas). Lo propio de mac —mini-captura screencapture 1pt por
    # sondeo y su check ABORT sin motivo— llega al bucle por callbacks.
    if c.checar_args_esperar(args.pixel, args.color, args.cambia, args.estable):
        x, y = args.pixel
        if c.quartz_disponible() and not c.dentro_de_virtual(x, y):
            mons, _via = _mon_listar()
            v = _bounding_de(mons)
            c.fail("Pixel (%d, %d) fuera de la pantalla virtual "
                   "(x %d..%d, y %d..%d)."
                   % (x, y, v["x"], v["x"] + v["ancho"] - 1,
                      v["y"], v["y"] + v["alto"] - 1))
        color = c.parsear_color(args.color)
        tol = args.tolerancia
        c.validar_tolerancia(tol)
        limite = c.cap_timeout_esperar(args.timeout)
        cumplida, ms_esperados = c.esperar_color(
            lambda: _color_coincide(x, y, color, tol),
            args.cambia, args.estable, limite, 0.25, inicio,
            c.checar_abort)  # poll ~250 ms: mini-captura mas cara que Win
        c.json_out({
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
        })
        return
    ms = c.cap_ms(args.milisegundos)
    c.dormir(ms, c.checar_abort)
    c.json_out({
        "cumplida": True,
        "ms_esperados": ms,
        "modo": "fijo",
        "marco": c.MARCO,
        "nota": "sueno simple (default 400 ms, cap 30000) para dejar "
                "renderizar la UI; la bandera ABORT de vigilar.py corta la "
                "espera; PAUSA la posterga",
    })


def cmd_localizar(args):
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
        _capturar_rect(destino, (x, y, w, h))
    else:
        mons, via = _mon_listar()
        principal = [m for m in mons if m["primario"]]
        if principal and principal[0]["izq"] is not None:
            m = principal[0]
            puntos = {"ancho": m["ancho"], "alto": m["alto"]}
            origen = [m["izq"], m["top"]]
            _capturar_rect(destino, (m["izq"], m["top"], m["ancho"], m["alto"]),
                           display_fallback=m["indice"] + 1)
        else:
            _capturar_rect(destino, None, display_fallback=1)

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


def construir_parser():
    parser = c.Parser(
        prog="pantalla.py (macOS)",
        description="Capturas e inspeccion de pantalla en macOS via la "
                    "herramienta nativa screencapture llamada desde Python. "
                    "Coordenadas = PUNTOS LOGICOS del espacio global "
                    "(origen = sup-izq del display principal). Mapa: "
                    "monitores.py listar.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos (verbos identicos a la")[1]
        if __doc__ and "Subcomandos (verbos identicos a la" in __doc__ else None,
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
    p.set_defaults(func=cmd_capturar)

    p = sub.add_parser("tamano", help="puntos del principal (o --virtual)")
    p.add_argument("--virtual", action="store_true",
                   help="bounding de TODOS los monitores + origen")
    p.set_defaults(func=cmd_tamano)

    p = sub.add_parser("posicion", help="posicion actual del cursor (puntos)")
    p.set_defaults(func=cmd_posicion)

    p = sub.add_parser("pixel", help="color RGB de un punto (puntos logicos)")
    p.add_argument("x", type=int, help="coordenada X global (negativa posible)")
    p.add_argument("y", type=int, help="coordenada Y global")
    p.set_defaults(func=cmd_pixel)

    p = sub.add_parser("esperar", help="pausa fija (--milisegundos) o "
                        "adaptativa por pixel (--pixel --color "
                        "--cambia|--estable)")
    p.add_argument("--milisegundos", type=int, default=400, metavar="N",
                   help="pausa fija en ms (default 400, cap 30000)")
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
    p.set_defaults(func=cmd_esperar)

    p = sub.add_parser("localizar", help="buscar una imagen en pantalla "
                        "(requiere opencv-python; zona: --region o principal)")
    p.add_argument("imagen", help="ruta del PNG/JPG a buscar")
    p.add_argument("--region", type=int, nargs=4,
                   metavar=("X", "Y", "ANCHO", "ALTO"),
                   help="limitar la busqueda a estos puntos (acelera)")
    p.add_argument("--confidence", type=float,
                   help="umbral 0-1 del matchTemplate (default ~exacto)")
    p.set_defaults(func=cmd_localizar)

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
