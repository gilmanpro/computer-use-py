# -*- coding: utf-8 -*-
"""autotest.py — suite del MOTOR LINUX de computer-use-py.

FASE SEG2: el punto de entrada normal es scripts/<verbo>.py (raiz, multi-OS)
y la autovalidacion es `python3 autotest.py` en la raiz de la skill — la suite
raiz (scripts/autotest.py) DELEGA en esta en Linux. Esta llamada directa es la
via avanzada del motor exclusivo:
    python3 scripts/linux/autotest.py
    python3 scripts/linux/autotest.py --con-escritura

Checklist EQUIVALENTE a la bateria raiz de Windows, adaptado a los verbos
reales de scripts/linux/ (mismos subcomandos; X11 por pyautogui/xdotool/wmctrl
y Wayland por grim/ydotool/wtype/swaymsg). Modo SEGURO por defecto: solo
lectura. El modo escritura (--con-escritura) corre un ciclo sandbox con un
editor de texto (gedit/kate/mousepad/pluma/xed/leafpad): abrir, teclear
ASCII+unicode, backspace, clic/doble/arrastre/scroll/mover en el lienzo, guard
de mover fuera, espera adaptativa por pixel y cerrar sin guardar (SIGTERM del
proceso propio). Exige el editor sin ventanas abiertas; si no hay editor
instalado, todo el ciclo queda SKIP con motivo.

Requisitos previos leidos como LIMITACIONES (no FAIL):
  - X11: xdotool + wmctrl instalados y DISPLAY exportada.
  - Wayland: grim (capturas) y, para entrada, ydotool con ydotoold corriendo
    y el usuario en el grupo input; wtype opcional. Sin ellos los checks que
    los necesitan se marcan SKIP con el motivo del JSON.
  - sway/hypr para mapas y ventanas Wayland (GNOME/KDE sin API => SKIP).

En Windows/macOS este archivo sale con el guard de plataforma del dominio
(importa _compartido_linux al arrancar: JSON de error + exit 2).

Salida: tabla [funcion | comando | OK/FAIL/SKIP | evidencia] + JSON resumen
{modo, total, pasados, fallados, skips, veredicto}; exit 0 sin FAILs reales.
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time

import _compartido_linux as c  # el guard de plataforma vive aqui (sal con 2)
import _core  # scripts/ ya esta en sys.path (lo inserto _compartido_linux):
              # se usa SOLO para el autotest de estructura multi-OS (FASE SEG)

RAIZ = c.RAIZ_SKILL
PY = sys.executable
ABORT = c.ARCHIVO_ABORT
PAUSA = c.ARCHIVO_PAUSA

CONT = {"ok": 0, "fail": 0, "skip": 0}
FALLAS = []
STATE = {}

_W = (30, 44)

# Errores que son LIMITACIONES del entorno (herramienta/permiso/sesion), no
# bugs del script: se reportan SKIP con el texto del JSON.
_PATRONES_LIMITE = (
    "no esta en el path", "no esta instalado", "falta pillow", "falta pynput",
    "pyautogui no pudo conectar", "sesion grafica sin detectar",
    "sin cli documentada", "no legible en wayland", "no tiene ruta en wayland",
    "requiere ydotoold", "grupo input", "compositor", "no pude parsear",
    "exporta display", "xserver vivo",
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
    cmd = [PY, os.path.join("scripts", "linux", args[0])] + [str(a) for a in args[1:]]
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
    return "python3 scripts/linux/" + " ".join(str(a) for a in args)


def _limite(datos):
    """Texto del error si es limitacion de entorno (SKIP), else None."""
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
        linea(funcion, comando, "SKIP", "limitacion de entorno: " + _limite(datos))
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


def _sesion():
    return c.deteccion_sesion()


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
    if d["marco"] != "px_layout" or d["plataforma"] != "linux":
        return False, "contrato P0-4 roto: marco=%r plataforma=%r" % (
            d["marco"], d["plataforma"])
    if "px_por_unidad_coord" not in str(d.get("regla", "")):
        return False, "la 'regla' no usa el campo unico px_por_unidad_coord"
    if not (os.path.isfile(d["archivo"]) and os.path.getsize(d["archivo"]) > 0):
        return False, "el PNG no existe o esta vacio: " + str(d["archivo"])
    _limpiar(d["archivo"])
    return True, "PNG %dx%d origen=%s px/coord=%s sesion=%s (borrado)" % (
        d["ancho"], d["alto"], d["origen"], d["px_por_unidad_coord"],
        d.get("sesion"))


def _checks_estructura():
    """Autotest de estructura multi-OS (FASE SEG/SEG2): (1) la raiz de scripts/
    contiene SOLO los 7 CLIs multi-OS + _core.py + glue_windows.py + windows/
    (solo win_especiales.py) + linux/ + macos/; (2) ningun modulo comun redefine
    los helpers movidos a _core. Check interno puro (lee via _core, stdlib): sin
    subprocess y sin efectos. Misma logica en las 3 suites (raiz, linux, macos)."""
    probs = _core.problemas_inventario_scripts()
    linea("estructura: scripts/ raiz", "(check interno)",
          "OK" if not probs else "FAIL",
          "; ".join(probs) if probs
          else "raiz = 7 CLIs + _core.py + glue_windows.py + windows/(solo "
               "win_especiales.py) + linux/ + macos/")
    probs = _core.problemas_redefiniciones()
    linea("estructura: modulos comunes sin redefiniciones", "(check interno)",
          "OK" if not probs else "FAIL",
          "; ".join(probs) if probs
          else "glue_windows/_compartido_linux/_compartido_mac solo reexportan "
               "HELPERS_COMUNES")


# --- bateria modo lectura ---------------------------------------------------

def bateria_lectura():
    _checks_estructura()
    ses = _sesion()

    def v_listar(rc, err, d):
        ok, ev = esperar_ok("monitores", "virtual", "sesion", "marco",
                            "plataforma")(rc, err, d)
        if not ok:
            return ok, ev
        if d["marco"] != "px_layout":
            return False, "marco no canonico: %r" % d["marco"]
        STATE["monitores"] = d["monitores"]
        prim = [m for m in d["monitores"] if m.get("primario")]
        STATE["primario"] = prim[0] if prim else d["monitores"][0]
        STATE["virtual"] = d["virtual"]
        return True, "%d monitor(es) sesion=%s via=%s" % (
            len(d["monitores"]), d["sesion"], STATE["primario"].get("via"))
    check("monitores listar", ["monitores.py", "listar"], v_listar)
    check("monitores subcomando falso", ["monitores.py", "zz-falso"],
          esperar_parser_error())

    if "primario" not in STATE:
        linea("resto de la bateria", "-", "SKIP",
              "sin mapa de monitores no hay marco de coordenadas")
        return
    p = STATE["primario"]
    cx, cy = p["izq"] + max(p["ancho"] // 2, 50), p["top"] + max(p["alto"] // 2, 50)

    # solo X11 lee el cursor; en Wayland el script da error honesto => SKIP
    if ses == "x11":
        check("monitores cursor", ["monitores.py", "cursor"],
              esperar_ok("x", "y", "marco"))
    else:
        check("monitores cursor (Wayland: error honesto)",
              ["monitores.py", "cursor"], esperar_error(), limite_comprob=False)

    check("pantalla tamano", ["pantalla.py", "tamano"], esperar_ok("ancho", "alto"))
    check("pantalla tamano --virtual", ["pantalla.py", "tamano", "--virtual"],
          esperar_ok("ancho", "alto", "origen"))

    def _v_w(fn, args, val):
        return check(fn, args, val)

    check("pantalla capturar", ["pantalla.py", "capturar"], v_capturar)
    check("pantalla capturar virtual", ["pantalla.py", "capturar", "--monitor",
                                        "virtual", "--max-lado", "640"], v_capturar)
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

    if ses == "x11":
        check("pantalla posicion", ["pantalla.py", "posicion"],
              esperar_ok("x", "y"))
    else:
        check("pantalla posicion (Wayland: error honesto)",
              ["pantalla.py", "posicion"], esperar_error(), limite_comprob=False)

    check("pantalla pixel (centro primario)", ["pantalla.py", "pixel", cx, cy],
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
                                                      "--timeout", "3"],
              esperar_ok("cumplida", "modo"), timeout=20)

    check("pantalla esperar --milisegundos 50", ["pantalla.py", "esperar",
                                                 "--milisegundos", "50"],
          esperar_ok("cumplida", "ms_esperados"))
    check("pantalla esperar --pixel sin color", ["pantalla.py", "esperar",
                                                 "--pixel", "5", "5"],
          esperar_error("requiere"), limite_comprob=False)
    check("pantalla pixel fuera de bounding", ["pantalla.py", "pixel",
                                               "999999", "999999"],
          esperar_error(), limite_comprob=False)
    check("pantalla localizar archivo inexistente", ["pantalla.py", "localizar",
                                                     "__no_existe__.png"],
          esperar_error("no existe"), limite_comprob=False)

    def v_listar_v(rc, err, d):
        ok, ev = esperar_ok("ventanas", "total")(rc, err, d)
        if not ok:
            return ok, ev
        if d["ventanas"]:
            it = d["ventanas"][0]
            for k in ("rect", "estado", "titulo"):
                if k not in it:
                    return False, "item de listar sin clave canonica %r" % k
            if it["rect"] is not None:
                for k in ("left", "top", "ancho", "alto"):
                    if k not in it["rect"]:
                        return False, "rect sin clave %r" % k
            for k in ("minimizada", "maximizada", "activa"):
                if k not in it["estado"]:
                    return False, "estado sin clave %r" % k
        return True, "total=%s items rect/estado anidados (maximizada nullable)" % d["total"]
    check("ventanas listar", ["ventanas.py", "listar"], v_listar_v)
    check("ventanas foco", ["ventanas.py", "foco"],
          lambda rc, err, d: (rc == 0 and isinstance(d, dict) and
                              "ventana" in d and
                              ("titulo" in d or d.get("activa") is None),
                              _trunca(str(d or err), 55)))
    check("ventanas activar inexistente", ["ventanas.py", "activar",
                                           "__zz_inexistente__"],
          esperar_error(), limite_comprob=False)
    check("ventanas abrir objetivo imposible", ["ventanas.py", "abrir",
                                                "__zz.inexistente.qqq__"],
          esperar_error("no es url"), limite_comprob=False)
    check("ventanas subcomando falso", ["ventanas.py", "zz-falso"],
          esperar_parser_error())

    if ses == "x11":
        def v_posicion_raton(rc, err, d):
            ok, ev = esperar_ok("x", "y", "marco", "via", "por_backend",
                                "monitor")(rc, err, d)
            if not ok:
                return ok, ev
            if d["marco"] != "px_layout":
                return False, "marco no canonico: %r" % d["marco"]
            if d["por_backend"].get("xdotool") is None:
                return False, "por_backend sin lectura xdotool"
            return True, "x=%s y=%s backends=%s" % (
                d["x"], d["y"], sorted(
                    k for k, v in d["por_backend"].items() if v))
        check("raton posicion (canonica)", ["raton.py", "posicion"],
              v_posicion_raton)
        check("raton scroll --vertical 0 (eje correcto, sin pasos)",
              ["raton.py", "scroll", "--vertical", "0"],
              lambda rc, err, d: (rc == 0 and isinstance(d, dict) and
                                  d.get("eje") == "vertical" and
                                  d.get("sentido") == "arriba",
                                  _trunca(str(d or err), 55)))
    else:
        check("raton posicion (Wayland: error honesto)", ["raton.py", "posicion"],
              esperar_error(), limite_comprob=False)

    check("raton click solo --x (sin efecto)", ["raton.py", "click",
                                                "--x", "100"],
          esperar_error("--x e --y juntos"), limite_comprob=False)
    check("raton scroll sin eje (sin efecto)", ["raton.py", "scroll"],
          esperar_error("--vertical"), limite_comprob=False)
    # el guard de bounding corre ANTES de cualquier emision (X11 y Wayland):
    # destino fuera del layout = error JSON, cursor intacto.
    check("raton mover fuera (sin efecto)", ["raton.py", "mover",
                                             "999999", "999999"],
          esperar_error())
    linea("raton scroll real (inyeccion)",
          comando_de(["raton.py", "scroll", "--vertical", "-2"]), "SKIP",
          "rodar la rueda mueve la UI del usuario: se prueba en el sandbox "
          "(--con-escritura); en Wayland ademas no tiene ruta documentada")

    check("teclado escribir foco invalido (sin efecto)",
          ["teclado.py", "escribir", "hola", "--requiere-foco",
           "__zz_imposible__"], esperar_error("no se emitio nada"),
          limite_comprob=False)
    check("teclado tecla desconocida (sin efecto)",
          ["teclado.py", "tecla", "__zz_falsa__"], esperar_error(),
          limite_comprob=False)
    check("teclado combo vacio (sin efecto)", ["teclado.py", "combo", ""],
          esperar_error(), limite_comprob=False)

    # vigilar (P0-1): el watchdog ya existe en la rama. En X11 es escucha
    # PASIVA real (no inyecta nada); en Wayland el script responde error JSON
    # honesto => se reporta SKIP con el motivo (limitacion documentada).
    def v_vigilar_final(rc, err, d):
        if isinstance(d, dict) and d.get("abortado"):
            return True, ("un humano pulso la tecla de panico durante la "
                          "escucha (bandera creada): no es un fallo")
        return esperar_ok("escuchado_segundos", "abortado",
                          "plataforma")(rc, err, d)
    check("vigilar arrancar 1 s (escucha pasiva)",
          ["vigilar.py", "arrancar", "--segundos", "1"], v_vigilar_final,
          timeout=15)
    check("vigilar segundos invalido", ["vigilar.py", "arrancar",
                                        "--segundos", "0"],
          esperar_error("entre 1 y 900"), limite_comprob=False)

    # --via de otra rama / boton invalido: JSON con 'validos', no argparse
    check("teclado escribir --via invalido (sin efecto)",
          ["teclado.py", "escribir", "hola", "--via", "zz-falso"],
          esperar_error("invalido"), limite_comprob=False)
    check("raton click --boton invalido (sin efecto)",
          ["raton.py", "click", "--boton", "zz-falso"],
          esperar_error("invalido"), limite_comprob=False)


# --- ciclo sandbox (--con-escritura) -----------------------------------------

_EDITORES = ("gedit", "kate", "mousepad", "pluma", "xed", "leafpad")


def _vidas(editor):
    """Ventanas cuyo titulo/inscripcion insinua el editor (diff-friendly)."""
    rc, _o, _e, d = run(["ventanas.py", "listar"])
    if not isinstance(d, dict) or "ventanas" not in d:
        return None
    pat = editor.lower()
    return [v for v in d["ventanas"]
            if pat in str(v.get("titulo", "")).lower()
            or pat.replace("gedit", "text editor") in str(v.get("titulo", "")).lower()]


def _matar(pid):
    if not pid:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            return
        time.sleep(0.6)
        try:
            os.kill(pid, 0)  # vivo?
        except ProcessLookupError:
            return


def bateria_escritura():
    editor = next((e for e in _EDITORES if shutil.which(e)), None)
    W = ["sandbox pre-check (0 %s abiertos)" % (editor or "editor"),
         "ventanas abrir %s" % (editor or "?"), "ventana nueva del editor",
         "ventanas activar + foco", "raton click en el lienzo",
         "teclado escribir ASCII", "teclado escribir unicode",
         "teclado tecla backspace", "raton doble clic lienzo",
         "raton arrastrar lienzo", "raton scroll lienzo",
         "raton mover dentro del lienzo", "raton mover fuera (guard)",
         "pantalla esperar --pixel adaptativa", "ventanas cerrar sin guardar"]
    if editor is None:
        for nombre in W:
            linea(nombre, "sandbox", "SKIP",
                  "no hay editor sandbox instalado (gedit/kate/mousepad/"
                  "pluma/xed/leafpad)")
        return

    vivo = subprocess.run(["pgrep", "-x", editor], capture_output=True)
    if vivo.returncode == 0:
        for nombre in W:
            linea(nombre, "sandbox", "SKIP",
                  "%s ya esta corriendo: cierralo y relanza (el sandbox no "
                  "toca trabajo ajeno)" % editor)
        return
    linea(W[0], "pgrep -x %s" % editor, "OK", "0 procesos antes del ciclo")

    pid = None
    try:
        rc, _o, err, d = run(["ventanas.py", "abrir", editor, "--esperar", "10",
                              "--titulo", editor], timeout=60)
        ok = rc == 0 and isinstance(d, dict) and d.get("ok")
        pid = d.get("pid") if isinstance(d, dict) else None
        linea(W[1], comando_de(["ventanas.py", "abrir", editor, "--esperar",
                                "10", "--titulo", editor]),
              "OK" if ok else "FAIL",
              ("pid=%s via=%s" % (pid, d.get("mecanica"))) if ok
              else _resumen_fallo(rc, err, d))
        if not ok:
            for nombre in W[2:]:
                linea(nombre, "sandbox", "SKIP", "abrir fallo: ciclo abortado")
            return

        ventana = None
        if isinstance(d, dict) and d.get("ventana"):
            ventana = d["ventana"]
        else:
            for _ in range(12):
                nuevos = _vidas(editor) or []
                if nuevos:
                    ventana = nuevos[0]
                    break
                time.sleep(0.5)
        if ventana is None:
            linea(W[2], "ventanas.py listar (diff)", "FAIL",
                  "sin ventana nueva de %s en 6 s (¿compositor sin soporte?)"
                  % editor)
            for nombre in W[3:]:
                linea(nombre, "sandbox", "SKIP", "sin ventana: ciclo abortado")
            return
        titulo = ventana["titulo"]
        # P1-2: item canonico anidado (rect puede ser null en tiling/minimiz.)
        rect = ventana.get("rect") or {}
        left = rect.get("left") or 0
        top = rect.get("top") or 0
        ancho = rect.get("ancho") or 600
        alto = rect.get("alto") or 400
        cx, cy = left + max(ancho // 2, 50), top + max(alto // 2, 50)
        linea(W[2], "ventanas.py listar (diff)", "OK",
              "'%s' %dx%d en (%d,%d)" % (titulo, ancho, alto, left, top))

        def v_ok(rc2, err2, d2):
            return esperar_ok("ok")(rc2, err2, d2)

        rc_a, _o, err_a, d_a = run(["ventanas.py", "activar", titulo])
        rc_f, _o, err_f, d_f = run(["ventanas.py", "foco"])
        foco_ev = (d_f or {}).get("titulo") if isinstance(d_f, dict) else None
        foco_ok = (rc_a == 0 and isinstance(d_a, dict) and d_a.get("ok")
                   and rc_f == 0 and isinstance(d_f, dict)
                   and str(foco_ev or "").lower() in titulo.lower())
        linea(W[3], comando_de(["ventanas.py", "activar", titulo]) + " + foco",
              "OK" if foco_ok else "FAIL", "foco=%r" % foco_ev)

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

        check(W[12], ["raton.py", "mover", "999999", "999999"],
              esperar_error(), limite_comprob=False, timeout=15)

        rc, _o, err, dpix = run(["pantalla.py", "pixel", cx, cy])
        if isinstance(dpix, dict) and "r" in dpix:
            color = "%d,%d,%d" % (dpix["r"], dpix["g"], dpix["b"])
            check(W[13], ["pantalla.py", "esperar", "--pixel", cx, cy,
                          "--color", color, "--estable", "200", "--timeout",
                          "3"], esperar_ok("cumplida", "modo"), timeout=20)
        else:
            linea(W[13], "pantalla.py esperar --pixel", "SKIP",
                  "sin pixel base: " + _resumen_fallo(rc, err, dpix))

        rc, _o, err, d5 = run(["ventanas.py", "cerrar", titulo])
        if not (rc == 0 and isinstance(d5, dict) and d5.get("ok")):
            linea(W[14], comando_de(["ventanas.py", "cerrar", titulo]), "FAIL",
                  _resumen_fallo(rc, err, d5))
            return
        time.sleep(0.8)
        restantes = _vidas(editor)
        via = "cerrado; sin ventanas restantes"
        if restantes:
            run(["teclado.py", "tecla", "esc"])   # descarta dialogo de guardado
            time.sleep(0.5)
            _matar(pid)                            # SOLO el proceso del sandbox
            via = "quedaba ventana/dialogo: ESC + SIGTERM pid %s" % pid
            time.sleep(0.5)
        finales = _vidas(editor)
        if isinstance(finales, list) and not finales:
            linea(W[14], comando_de(["ventanas.py", "cerrar", titulo])
                  + " + limpieza", "OK", via)
        else:
            linea(W[14], comando_de(["ventanas.py", "cerrar", titulo]), "FAIL",
                  "quedan ventanas: %s" % [v["titulo"] for v in (finales or [])][:3])
    finally:
        try:
            restantes = _vidas(editor)
            if restantes is None or restantes:
                _matar(pid)
        except Exception:
            pass


# --- ejecucion ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        prog="autotest.py (linux)",
        description="Autovalidacion de la skill computer-use-py (rama LINUX). "
                    "Por defecto SOLO LECTURA. --con-escritura corre el ciclo "
                    "sandbox con un editor (exige el editor sin ventanas).")
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

    print("# autotest computer-use-py (LINUX) — %s" % (
        "LECTURA + ESCRITURA" if args.con_escritura else "modo seguro (lectura)"))
    print("sesion: %s | python: %s | raiz: %s" % (_sesion(), PY, RAIZ))
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
        "nota": "SKIP = limitacion de entorno documentada (herramienta/"
                "compositor/sesion/permiso) con motivo del JSON; FAIL en "
                "modo lectura = bug de scripts/linux/: reportar, no parchar",
    }
    print("\n" + "-" * 130)
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    sys.exit(0 if CONT["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
