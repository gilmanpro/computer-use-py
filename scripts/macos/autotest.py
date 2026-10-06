# -*- coding: utf-8 -*-
"""autotest.py — autovalidacion de la skill computer-use-py (rama macOS).

Checklist EQUIVALENTE al autotest de Windows, adaptado a los verbos reales de
scripts/macos/ (mismos subcomandos; pynput/Quartz para entrada, screencapture
+ osascript/System Events + open para lo demas). Modo SEGURO por defecto:
solo lectura (las capturas/pixels son lectura de pantalla; no se teclea ni se
mueve el cursor).

Uso (desde la carpeta computer-use-py, en el Mac):
    python3 scripts/macos/autotest.py
    python3 scripts/macos/autotest.py --con-escritura

Requisitos previos leidos como LIMITACIONES (SKIP con motivo, no FAIL):
  - TCC Accesibilidad: sin el, teclado/raton/vigilar no emiten/escuchan
    (vigilar lo dice abiertamente con is_trusted=false).
  - TCC Grabacion de pantalla: sin el, screencapture sale negro (los checks
    de capturacion pasan pero el agente vera negro: nota en la evidencia).
  - TCC Automatizacion: ventanas.py/teclado (foco) usan System Events: el
    -1743 se reporta SKIP con el hint de tccutil reset AppleEvents.
  - pip3: pynput==1.8.2 y pyobjc-framework-Quartz (pillow para pixel/escala).

El modo escritura (--con-escritura) corre el ciclo sandbox con TextEdit:
abrir, teclear ASCII+unicode, backspace, clic/doble/arrastre/scroll/mover en
el lienzo, guard de mover fuera (solo con mapa Quartz), espera adaptativa por
pixel y cerrar sin guardar (ESC al sheet + pkill -x TextEdit del proceso que
el propio sandbox lanzo). Exige TextEdit sin procesos abiertos; si hay
alguno, TODO el ciclo queda SKIP (no toca trabajo del usuario).

En Windows/Linux este archivo sale con el guard de plataforma del dominio
(importa _compartido_mac al arrancar: JSON de error + exit 2).

Salida: tabla [funcion | comando | OK/FAIL/SKIP | evidencia] + JSON resumen
{modo, total, pasados, fallados, skips, veredicto}; exit 0 sin FAILs reales.
"""

import argparse
import json
import os
import subprocess
import sys
import time

import _compartido_mac as c  # el guard de plataforma vive aqui (sal con 2)

RAIZ = c.RAIZ_SKILL
PY = sys.executable
ABORT = c.ARCHIVO_ABORT
PAUSA = c.ARCHIVO_PAUSA

CONT = {"ok": 0, "fail": 0, "skip": 0}
FALLAS = []
STATE = {}

_W = (30, 44)

# Errores = limitaciones de entorno (permiso TCC, libreria pip, herramienta
# del SO): SKIP con motivo, no FAIL.
_PATRONES_LIMITE = (
    "falta pillow", "falta pynput", "falta pyobjc", "no esta en el path",
    "osascript no esta", "tcc", "-1743", "-1712", "-1719", "-1728", "-25211",
    "cggetactivedisplaylist", "no devolvo displays", "screencapture",
    "grabacion de pantalla", "screen recording", "accesibilidad",
    "automatizacion", "opencv", "sesion grafica", "sin pynput",
)


def _trunca(txt, n):
    txt = " ".join(str(txt).split())
    return txt if len(txt) <= n else txt[: n - 3] + "..."


def linea(funcion, comando, estado, evidencia):
    print("%-*s | %-*s | %-*s | %s"
          % (_W[0], _trunca(funcion, _W[0]), _W[1], _trunca(comando, _W[1]),
             4, estado, _trunca(evidencia, 58)))
    if estado == "OK":
        CONT["ok"] += 1
    elif estado == "SKIP":
        CONT["skip"] += 1
    else:
        CONT["fail"] += 1
        FALLAS.append(funcion)


def run(args, timeout=40):
    cmd = [PY, os.path.join("scripts", "macos", args[0])] + [str(a) for a in args[1:]]
    try:
        p = subprocess.run(cmd, cwd=RAIZ, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT de %s s superado" % timeout, None
    out = (p.stdout or b"").decode("utf-8", "replace")
    err = (p.stderr or b"").decode("utf-8", "replace")
    try:
        datos = json.loads(out)
    except ValueError:
        datos = None
    return p.returncode, out, err, datos


def comando_de(args):
    return "python3 scripts/macos/" + " ".join(str(a) for a in args)


def _limite(datos):
    if not (isinstance(datos, dict) and "error" in datos):
        return None
    e = (str(datos.get("error", "")) + " " + str(datos.get("hint", ""))
         + " " + str(datos.get("pista", ""))).lower()
    for pat in _PATRONES_LIMITE:
        if pat in e:
            return _trunca(str(datos["error"]), 55)
    return None


def check(funcion, args, validar, timeout=40, limite_comprob=True):
    rc, _o, err, datos = run(args, timeout)
    comando = comando_de(args)
    if limite_comprob and rc != 0 and _limite(datos):
        linea(funcion, comando, "SKIP", "limitacion de entorno (TCC/pip/herr): "
              + _limite(datos))
        return datos
    try:
        ok, ev = validar(rc, err, datos)
    except Exception as exc:
        ok, ev = False, "el autotest no pudo validar (%s: %s); rc=%s" % (
            type(exc).__name__, exc, rc)
    linea(funcion, comando, "OK" if ok else "FAIL", ev)
    return datos


def esperar_ok(*claves):
    def _v(rc, err, d):
        if not isinstance(d, dict) or "error" in d or rc != 0:
            return False, _resumen_fallo(rc, err, d)
        faltan = [k for k in claves if k not in d]
        if faltan:
            return False, "faltan claves %s" % faltan
        return True, _resumen_claves(d, claves)
    return _v


def esperar_error(pista=None):
    def _v(rc, err, d):
        if isinstance(d, dict) and "error" in d:
            if rc == 1 and (pista is None or pista.lower() in
                            str(d["error"]).lower()):
                return True, "error esperado: " + str(d["error"])
            return False, "error inesperado (rc=%s): %s" % (rc, d["error"])
        if rc == 1 and "error" in (err or ""):
            return True, "error esperado (stderr): " + err
        return False, "no hubo JSON de error (rc=%s): %s" % (rc, err)
    return _v


def esperar_parser_error():
    """(P1-7) Los errores de argparse salen AHORA como JSON canonico: rc==1 y
    {"error": "argumentos invalidos: ..."} — nunca stderr rc=2."""
    def _v(rc, err, d):
        if rc == 1 and isinstance(d, dict) and \
                "argumentos invalidos" in str(d.get("error", "")):
            return True, "error JSON esperado: " + str(d["error"])
        return False, "rc=%s esperaba JSON 'argumentos invalidos': %s" % (
            rc, _resumen_fallo(rc, err, d))
    return _v


def _resumen_fallo(rc, err, d):
    if isinstance(d, dict) and "error" in d:
        return "rc=%s error=%s" % (rc, d["error"])
    return "rc=%s stdout-no-JSON stderr=%s" % (rc, _trunca(err, 40))


def _resumen_claves(d, claves):
    return " ".join("%s=%s" % (k, _trunca(d.get(k), 16))
                    for k in list(claves)[:3])


def _limpiar(ruta):
    try:
        os.remove(ruta)
    except OSError:
        pass


def v_capturar(rc, err, d):
    ok, ev = esperar_ok("archivo", "ancho", "origen", "px_por_unidad_coord",
                        "marco", "plataforma")(rc, err, d)
    if not ok:
        return ok, ev
    if d["marco"] != "puntos_logicos" or d["plataforma"] != "darwin":
        return False, "contrato P0-4 roto: marco=%r plataforma=%r" % (
            d["marco"], d["plataforma"])
    if "px_por_unidad_coord" not in str(d.get("regla", "")):
        return False, "la 'regla' no usa el campo unico px_por_unidad_coord"
    if not (os.path.isfile(d["archivo"]) and os.path.getsize(d["archivo"]) > 0):
        return False, "el PNG no existe o esta vacio: " + str(d["archivo"])
    retina = d.get("escala_retina")
    px_por = d["px_por_unidad_coord"]
    if px_por is not None and retina:
        # P0-3: el factor total debe absorber Retina (== escala x retina)
        esperado = d.get("escala", 1.0) * retina
        if abs(px_por - esperado) > max(0.05, esperado * 0.02):
            return False, "px_por_unidad_coord=%s != escala*retina=%s" % (
                px_por, round(esperado, 6))
    _limpiar(d["archivo"])
    return True, "PNG %dx%d retina=%s px/coord=%s via=%s (borrado)" % (
        d["ancho"], d["alto"], retina, px_por, _trunca(d.get("via"), 24))


# --- bateria modo lectura ---------------------------------------------------

def bateria_lectura():
    def v_listar(rc, err, d):
        ok, ev = esperar_ok("monitores", "marco", "plataforma")(rc, err, d)
        if not ok:
            return ok, ev
        if d["marco"] != "puntos_logicos":
            return False, "marco no canonico: %r" % d["marco"]
        prim = [m for m in d["monitores"] if m.get("primario")]
        if not prim:
            return False, "ningun monitor marcado como primario"
        STATE["primario"] = prim[0]
        STATE["monitores"] = d["monitores"]
        STATE["via"] = str(d.get("via", ""))
        return True, "%d monitor(es) primario=%s via=%s" % (
            len(d["monitores"]), STATE["primario"].get("nombre"),
            _trunca(STATE["via"], 20))
    check("monitores listar", ["monitores.py", "listar"], v_listar)
    check("monitores subcomando falso", ["monitores.py", "zz-falso"],
          esperar_parser_error())
    check("monitores cursor", ["monitores.py", "cursor"], esperar_ok("x", "y"))

    if "primario" not in STATE:
        linea("resto de la bateria", "-", "SKIP",
              "sin mapa de monitores (pyobjc/TCC) no hay marco de coordenadas")
        return
    p = STATE["primario"]
    cx, cy = p["izq"] + max(p["ancho"] // 2, 50), p["top"] + max(p["alto"] // 2, 50)

    check("pantalla tamano", ["pantalla.py", "tamano"], esperar_ok("ancho", "alto"))
    check("pantalla tamano --virtual", ["pantalla.py", "tamano", "--virtual"],
          esperar_ok("ancho", "alto", "origen"))
    check("pantalla capturar", ["pantalla.py", "capturar"], v_capturar)
    check("pantalla capturar virtual", ["pantalla.py", "capturar", "--monitor",
                                        "virtual", "--max-lado", "640"],
          v_capturar, timeout=60)
    check("pantalla capturar region", ["pantalla.py", "capturar", "--region",
                                       str(p["izq"]), str(p["top"]),
                                       str(max(p["ancho"] // 4, 64)),
                                       str(max(p["alto"] // 4, 64))], v_capturar)
    if len(STATE["monitores"]) >= 2:
        check("pantalla capturar --monitor 1", ["pantalla.py", "capturar",
                                                "--monitor", "1"], v_capturar)
    else:
        linea("pantalla capturar --monitor 1",
              comando_de(["pantalla.py", "capturar", "--monitor", "1"]), "SKIP",
              "limitacion de hardware: %d monitor(es); se requiere >=2"
              % len(STATE["monitores"]))
    check("pantalla posicion", ["pantalla.py", "posicion"], esperar_ok("x", "y"))
    check("pantalla pixel (punto central)", ["pantalla.py", "pixel", cx, cy],
          esperar_ok("r", "g", "b"))

    def v_color(rc, err, d):
        ok, ev = esperar_ok("r", "g", "b")(rc, err, d)
        if ok:
            STATE["color"] = "%d,%d,%d" % (d["r"], d["g"], d["b"])
        return ok, ev
    check("pantalla pixel para adaptativa", ["pantalla.py", "pixel", cx, cy],
          v_color)
    if "color" in STATE:
        check("pantalla esperar --pixel adaptativa", ["pantalla.py", "esperar",
                                                      "--pixel", cx, cy,
                                                      "--color", STATE["color"],
                                                      "--estable", "200",
                                                      "--timeout", "5"],
              esperar_ok("cumplida", "modo"), timeout=25)

    check("pantalla esperar --milisegundos 50", ["pantalla.py", "esperar",
                                                 "--milisegundos", "50"],
          esperar_ok("cumplida", "ms_esperados"))
    check("pantalla esperar --pixel sin color", ["pantalla.py", "esperar",
                                                 "--pixel", "5", "5"],
          esperar_error("requiere"), limite_comprob=False)
    check("pantalla pixel fuera de bounding", ["pantalla.py", "pixel",
                                               "999999", "999999"],
          esperar_error())
    check("pantalla localizar archivo inexistente", ["pantalla.py", "localizar",
                                                     "__no_existe__.png"],
          esperar_error("no existe"), limite_comprob=False)

    def v_listar_v(rc, err, d):
        ok, ev = esperar_ok("ventanas", "total")(rc, err, d)
        if not ok:
            return ok, ev
        if d["ventanas"]:
            it = d["ventanas"][0]
            for k in ("rect", "estado", "titulo", "app"):
                if k not in it:
                    return False, "item de listar sin clave canonica %r" % k
            if it["rect"] is not None:
                for k in ("left", "top", "ancho", "alto"):
                    if k not in it["rect"]:
                        return False, "rect sin clave %r" % k
            for k in ("minimizada", "maximizada", "activa"):
                if k not in it["estado"]:
                    return False, "estado sin clave %r" % k
        return True, "total=%s items rect/estado anidados (maximizada null: sin zoom)" % d["total"]
    check("ventanas listar", ["ventanas.py", "listar"], v_listar_v)
    check("ventanas foco", ["ventanas.py", "foco"],
          lambda rc, err, d: (rc == 0 and isinstance(d, dict) and
                              "ventana" in d and
                              ("app" in d or d.get("activa") is None),
                              _trunca(str(d or err), 55)))
    check("ventanas activar inexistente", ["ventanas.py", "activar",
                                           "__zz_inexistente__"],
          esperar_error(), limite_comprob=False)
    check("ventanas abrir objetivo imposible", ["ventanas.py", "abrir",
                                                "__zz.inexistente.qqq__"],
          esperar_error("no es url"), limite_comprob=False)
    check("ventanas subcomando falso", ["ventanas.py", "zz-falso"],
          esperar_parser_error())

    def v_posicion_raton(rc, err, d):
        # P1-1: forma canonica plana (sin claves top-level quartz/pynput).
        ok, ev = esperar_ok("x", "y", "marco", "via", "por_backend",
                            "plataforma")(rc, err, d)
        if not ok:
            return ok, ev
        if d["marco"] != "puntos_logicos":
            return False, "marco no canonico: %r" % d["marco"]
        if not any(d["por_backend"].values()):
            return False, "por_backend sin ninguna lectura util"
        return True, "x=%s y=%s via=%s backends=%s" % (
            d["x"], d["y"], d["via"],
            sorted(k for k, v in d["por_backend"].items() if v))
    check("raton posicion (canonica)", ["raton.py", "posicion"], v_posicion_raton)
    check("raton click --boton invalido (sin efecto)", ["raton.py", "click",
                                                        "--boton", "zz-falso"],
          esperar_error("invalido"), limite_comprob=False)
    check("teclado escribir --via invalido (sin efecto)",
          ["teclado.py", "escribir", "hola", "--via", "zz-falso"],
          esperar_error("validos"), limite_comprob=False)
    check("raton click solo --x (sin efecto)", ["raton.py", "click",
                                                "--x", "100"],
          esperar_error("--x e --y juntos"), limite_comprob=False)
    check("raton scroll sin eje (sin efecto)", ["raton.py", "scroll"],
          esperar_error("--vertical"), limite_comprob=False)
    if "quartz" in STATE.get("via", "").lower():
        check("raton mover fuera (sin efecto)", ["raton.py", "mover",
                                                 "999999", "999999"],
              esperar_error())
    else:
        linea("raton mover fuera (guard)", "raton.py mover 999999 999999",
              "SKIP", "sin mapa Quartz el guard se omite por diseno y moveria "
              "el cursor: no se prueba en modo lectura")

    check("teclado escribir foco invalido (sin efecto)",
          ["teclado.py", "escribir", "hola", "--requiere-foco",
           "__zz_imposible__"], esperar_error("foco"))
    check("teclado tecla desconocida (sin efecto)",
          ["teclado.py", "tecla", "__zz_falsa__"], esperar_error(),
          limite_comprob=False)
    check("teclado combo vacio (sin efecto)", ["teclado.py", "combo", ""],
          esperar_error(), limite_comprob=False)
    check("teclado mantener tecla desconocida (sin efecto)",
          ["teclado.py", "mantener", "__zz_falsa__", "--segundos", "0.1"],
          esperar_error(), limite_comprob=False)

    def v_vigilar(rc, err, d):
        if rc != 0 or not isinstance(d, dict):
            return False, _resumen_fallo(rc, err, d)
        if d.get("is_trusted") is False:
            return None, ("TCC Accesibilidad pendiente (IS_TRUSTED=false): la "
                          "escucha arranca pero no vera nada")
        return True, "escucha pasiva 1 s; humana=%s abort=%s is_trusted=%s" % (
            d.get("hubo_entrada_humana"), d.get("abortado"),
            d.get("is_trusted"))

    def v_vigilar_wrap(rc, err, d):
        ok, ev = v_vigilar(rc, err, d)
        if ok is None:
            return "SKIP", ev
        return ok, ev
    # vigilar envuelto a mano para poder devolver SKIP tri-estado
    rc, _o, err, d = run(["vigilar.py", "arrancar", "--segundos", "1"],
                         timeout=15)
    if rc != 0 and _limite(d):
        linea("vigilar arrancar 1 s (escucha pasiva)",
              comando_de(["vigilar.py", "arrancar", "--segundos", "1"]), "SKIP",
              "limitacion de entorno (TCC/pip/herr): " + _limite(d))
    else:
        ok, ev = v_vigilar(rc, err, d)
        estado = "SKIP" if ok is None else ("OK" if ok else "FAIL")
        linea("vigilar arrancar 1 s (escucha pasiva)",
              comando_de(["vigilar.py", "arrancar", "--segundos", "1"]), estado,
              ev)


# --- ciclo sandbox (--con-escritura) -----------------------------------------

def _ventanas_textedit():
    rc, _o, _e, d = run(["ventanas.py", "listar"])
    if not isinstance(d, dict) or "ventanas" not in d:
        return None
    return [v for v in d["ventanas"]
            if "textedit" in str(v.get("app", "")).lower().replace(" ", "")]


def _pkill(nombre):
    subprocess.run(["pkill", "-x", nombre], capture_output=True)
    time.sleep(0.6)


def bateria_escritura():
    W = ["sandbox pre-check (0 TextEdit abiertos)", "ventanas abrir TextEdit",
         "ventana nueva de TextEdit", "ventanas activar + foco",
         "raton click en el lienzo", "teclado escribir ASCII",
         "teclado escribir unicode", "teclado tecla backspace",
         "raton doble clic lienzo", "raton arrastrar lienzo",
         "raton scroll lienzo", "raton mover dentro del lienzo",
         "raton mover fuera (guard)", "pantalla esperar --pixel adaptativa",
         "ventanas cerrar sin guardar"]

    vivo = subprocess.run(["pgrep", "-x", "TextEdit"], capture_output=True)
    if vivo.returncode == 0:
        for nombre in W:
            linea(nombre, "sandbox", "SKIP",
                  "TextEdit ya esta corriendo: cierralo y relanza (el sandbox "
                  "no toca trabajo ajeno)")
        return
    linea(W[0], "pgrep -x TextEdit", "OK", "0 procesos antes del ciclo")

    try:
        rc, _o, err, d = run(["ventanas.py", "abrir", "TextEdit", "--esperar",
                              "12", "--titulo", "TextEdit"], timeout=60)
        ok = (rc == 0 and isinstance(d, dict) and d.get("ok")
              # P0-2: el enum canónico — "app" NO debe volver a salir del JSON
              and d.get("tipo") in ("programa", "url", "archivo"))
        linea(W[1], comando_de(["ventanas.py", "abrir", "TextEdit",
                                "--esperar", "12", "--titulo", "TextEdit"]),
              "OK" if ok else ("SKIP" if _limite(d) else "FAIL"),
              ("pid_nota=%s" % _trunca(d.get("pid_nota"), 30)) if ok
              else _resumen_fallo(rc, err, d))
        if not ok:
            for nombre in W[2:]:
                linea(nombre, "sandbox", "SKIP", "abrir fallo/inaccesible: "
                      "ciclo abortado (revisa TCC Automatizacion)")
            return

        ventana = None
        for _ in range(16):
            nuevos = _ventanas_textedit() or []
            if nuevos:
                ventana = nuevos[0]
                break
            time.sleep(0.5)
        if ventana is None:
            linea(W[2], "ventanas.py listar (app TextEdit)", "SKIP",
                  "sin ventana de TextEdit en 8 s (¿sheet de apertura o "
                  "permiso TCC denegado?)")
            for nombre in W[3:]:
                linea(nombre, "sandbox", "SKIP", "sin ventana: ciclo abortado")
            _pkill("TextEdit")
            return
        titulo = ventana["titulo"]
        # item canonico anidado (P1-2): left/top/ancho/alto viven en "rect"
        rect = ventana.get("rect") or {}
        left = rect.get("left") or 0
        top = rect.get("top") or 0
        ancho = rect.get("ancho") or 600
        alto = rect.get("alto") or 400
        cx, cy = left + max(ancho // 2, 50), top + max(alto // 2, 50)
        linea(W[2], "ventanas.py listar (app TextEdit)", "OK",
              "'%s' %dx%d en (%d,%d)" % (titulo, ancho, alto, left, top))

        def v_ok(rc2, err2, d2):
            return esperar_ok("ok")(rc2, err2, d2)

        rc_a, _o, err_a, d_a = run(["ventanas.py", "activar", titulo])
        rc_f, _o, err_f, d_f = run(["ventanas.py", "foco"])
        foco_ok = (rc_a == 0 and isinstance(d_a, dict) and d_a.get("ok")
                   and rc_f == 0 and isinstance(d_f, dict)
                   and "textedit" in str((d_f or {}).get("app", "")).lower())
        linea(W[3], comando_de(["ventanas.py", "activar", titulo]) + " + foco",
              "OK" if foco_ok else ("SKIP" if _limite(d_a) else "FAIL"),
              "foco app=%r" % (d_f or {}).get("app"))

        for nombre, args in (
            (W[4], ["raton.py", "click", "--x", cx, "--y", cy]),
            (W[5], ["teclado.py", "escribir", "Hola autotest 123"]),
            (W[6], ["teclado.py", "escribir", "Ñ¿Á"]),
            (W[7], ["teclado.py", "tecla", "backspace", "--repeticiones", "3"]),
            (W[8], ["raton.py", "click", "--x", cx, "--y", cy, "--doble"]),
            (W[9], ["raton.py", "arrastrar", cx - 90, cy, cx + 90, cy,
                    "--duracion", "0.4"]),
            (W[10], ["raton.py", "scroll", "--vertical", "-2", "--x", cx,
                     "--y", cy]),
            (W[11], ["raton.py", "mover", cx + 20, cy + 5, "--duracion", "0.2"]),
        ):
            check(nombre, args, v_ok, timeout=25)

        if "quartz" in STATE.get("via", "").lower():
            check(W[12], ["raton.py", "mover", "999999", "999999"],
                  esperar_error(), limite_comprob=False, timeout=15)
        else:
            linea(W[12], "raton.py mover 999999 999999", "SKIP",
                  "sin mapa Quartz el guard no aplica [documentado]")

        rc, _o, err, dpix = run(["pantalla.py", "pixel", cx, cy])
        if isinstance(dpix, dict) and "r" in dpix:
            color = "%d,%d,%d" % (dpix["r"], dpix["g"], dpix["b"])
            check(W[13], ["pantalla.py", "esperar", "--pixel", cx, cy,
                          "--color", color, "--estable", "200", "--timeout",
                          "4"], esperar_ok("cumplida", "modo"), timeout=30)
        else:
            linea(W[13], "pantalla.py esperar --pixel", "SKIP",
                  "sin pixel base (TCC Grabacion?): "
                  + _resumen_fallo(rc, err, dpix))

        rc, _o, err, d5 = run(["ventanas.py", "cerrar", titulo])
        if not (rc == 0 and isinstance(d5, dict) and d5.get("ok")):
            linea(W[14], comando_de(["ventanas.py", "cerrar", titulo]),
                  "OK" if _limite(d5) else "FAIL", _resumen_fallo(rc, err, d5))
            return
        time.sleep(0.8)
        restantes = _ventanas_textedit()
        via = "cerrado sin dejar ventanas"
        if restantes:
            run(["teclado.py", "tecla", "esc"])   # descarta el sheet de guardado
            time.sleep(0.6)
            _pkill("TextEdit")  # limpio: el pre-check garantiza que SOLO hay
                                # ventanas del sandbox
            via = "quedaba ventana/sheet: ESC + pkill TextEdit del sandbox"
        finales = _ventanas_textedit()
        if isinstance(finales, list) and not finales:
            linea(W[14], comando_de(["ventanas.py", "cerrar", titulo])
                  + " + limpieza", "OK", via)
        else:
            linea(W[14], comando_de(["ventanas.py", "cerrar", titulo]), "FAIL",
                  "quedan ventanas TextEdit tras cerrar/limpiar")
    finally:
        try:
            if _ventanas_textedit():
                _pkill("TextEdit")
        except Exception:
            pass


# --- ejecucion ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        prog="autotest.py (macOS)",
        description="Autovalidacion de la skill computer-use-py (rama macOS). "
                    "Por defecto SOLO LECTURA. --con-escritura corre el ciclo "
                    "sandbox con TextEdit (exige TextEdit sin procesos).")
    ap.add_argument("--con-escritura", dest="con_escritura", action="store_true",
                    help="ciclo sandbox completo (solo un humano consciente)")
    args = ap.parse_args()

    residuales = []
    for b in (ABORT, PAUSA):
        if os.path.exists(b):
            residuales.append(os.path.basename(b))
            try:
                os.remove(b)
            except OSError:
                pass

    print("# autotest computer-use-py (macOS) — %s" % (
        "LECTURA + ESCRITURA" if args.con_escritura else "modo seguro (lectura)"))
    print("python: %s | raiz: %s" % (PY, RAIZ))
    if residuales:
        print("banderas previas limpiadas: %s" % ", ".join(residuales))
    print("-" * 130)
    print("%-*s | %-*s | %-*s | %s" % (_W[0], "FUNCION", _W[1], "COMANDO",
                                       4, "EST", "EVIDENCIA"))
    print("-" * 130)

    bateria_lectura()
    if args.con_escritura:
        bateria_escritura()
    else:
        linea("ciclo de escritura completo", "sandbox", "SKIP",
              "modo seguro: relanza con --con-escritura (humano consciente)")

    veredicto = "PASS" if CONT["fail"] == 0 else "FAIL"
    resumen = {
        "modo": "lectura+escritura" if args.con_escritura else "lectura",
        "total": sum(CONT.values()),
        "pasados": CONT["ok"],
        "fallados": CONT["fail"],
        "skips": CONT["skip"],
        "veredicto": veredicto,
        "fallas": FALLAS,
        "nota": "SKIP = limitacion de entorno (TCC/pip/herramienta) con "
                "motivo; FAIL en modo lectura = bug de scripts/macos/: "
                "reportar, no parchar",
    }
    print("\n" + "-" * 130)
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    sys.exit(0 if CONT["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
