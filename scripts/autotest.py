# -*- coding: utf-8 -*-
"""autotest.py — autovalidacion de la skill computer-use-py (rama WINDOWS).

Bateria sobre TODAS las funciones de scripts/ en modo SEGURO por defecto:
solo LECTURA (no teclea, no mueve el cursor, no hace clic). Las unicas
escrituras del modo lectura son PNG dentro del .tmp/ de la skill y el
listener PASIVO de vigilar.py durante 1 s (no inyecta nada). Los "errores de
parser" se validan contra rutas del codigo que abortan ANTES de emitir, de
modo que tampoco tienen efectos.

Uso (desde la carpeta computer-use-py):
    py scripts/autotest.py                  :: modo lectura (defecto)
    py scripts/autotest.py --con-escritura  :: ciclo sandbox completo (humano)

El modo escritura (que un humano lanza a conciencia) abre el Bloc de notas,
activa su lienzo, teclea ASCII + unicode, borra con backspace, prueba
clic/doble/arrastre/scroll/mover/combo/dentro de la ventana, la espera
adaptativa por pixel y cierra SIN guardar (ESC al dialogo de guardado y, si
aun queda ventana, taskkill del proceso propio). Exige cero ventanas de
Notepad abiertas al empezar: si hay alguna, el ciclo completo se marca SKIP
(esto jams toca el trabajo del usuario).

Salida: tabla [funcion | comando | OK/FAIL/SKIP | evidencia] + JSON resumen
{modo, total, pasados, fallados, skips, veredicto, fallas}. exit 0 si no hay
FAIL reales; las limitaciones de hardware/entorno son SKIP con motivo
(p. ej. un solo monitor: la prueba del secundario se omite, no falla).

Equivalentes del mismo checklist: scripts/linux/autotest.py y
scripts/macos/autotest.py. Este archivo, ejecutado en otro SO, sale con el
guard de plataforma (error JSON + exit 2).
"""

import argparse
import json
import os
import subprocess
import sys

# --- Guard de plataforma --------------------------------------------------
if sys.platform != "win32":
    print(json.dumps({
        "error": "scripts/autotest.py es la rama WINDOWS; usa "
                 "scripts/linux/autotest.py o scripts/macos/autotest.py "
                 "segun tu SO",
        "sistema_operativo": sys.platform,
        # contrato P0-4: `plataforma` canonica tambien en el guard
        "plataforma": {"win32": "win", "linux": "linux",
                       "darwin": "darwin"}.get(sys.platform, sys.platform),
    }, ensure_ascii=False))
    sys.exit(2)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
ABORT = os.path.join(RAIZ, ".tmp", "ABORT")
PAUSA = os.path.join(RAIZ, ".tmp", "PAUSA")

CONT = {"ok": 0, "fail": 0, "skip": 0}
FALLAS = []
STATE = {}  # datos compartidos entre checks (monitores, tamanos, cursor)

_W = (26, 46, 4)  # anchos de column de la tabla


def _trunca(txt, n):
    txt = " ".join(str(txt).split())
    return txt if len(txt) <= n else txt[: n - 3] + "..."


def linea(funcion, comando, estado, evidencia):
    print("%-*s | %-*s | %-*s | %s"
          % (_W[0], _trunca(funcion, _W[0]), _W[1], _trunca(comando, _W[1]),
             _W[2], estado, _trunca(evidencia, 60)))
    if estado == "OK":
        CONT["ok"] += 1
    elif estado == "SKIP":
        CONT["skip"] += 1
    else:
        CONT["fail"] += 1
        FALLAS.append(funcion)


def run(args, timeout=40):
    """Ejecuta un script de la skill: (rc, stdout-texto, stderr-texto, JSON|None)."""
    cmd = [PY, os.path.join("scripts", args[0])] + [str(a) for a in args[1:]]
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
    return "py scripts/" + " ".join(str(a) for a in args)


def check(funcion, args, validar, timeout=40):
    """Corre un comando y emite la fila segun validar(rc, err, datos)->(bool, ev)."""
    rc, _out, err, datos = run(args, timeout)
    try:
        ok, ev = validar(rc, err, datos)
    except Exception as exc:  # bug del propio autotest al validar
        ok, ev = False, "el autotest no pudo validar (%s: %s); rc=%s" % (
            type(exc).__name__, exc, rc)
    linea(funcion, comando_de(args), "OK" if ok else "FAIL", ev)
    return datos


def check_skip(funcion, args, motivo):
    linea(funcion, comando_de(args), "SKIP", motivo)


# --- validadores genericos -------------------------------------------------

def esperar_ok(*claves):
    """Validador basico: rc==0, JSON con claves y sin 'error'."""
    def _v(rc, err, d):
        if not isinstance(d, dict) or "error" in d or rc != 0:
            return False, _resumen_fallo(rc, err, d)
        faltan = [k for k in claves if k not in d]
        if faltan:
            return False, "faltan claves %s en el JSON" % faltan
        return True, _resumen_claves(d, claves)
    return _v


def esperar_error(pista=None):
    """Validador de rutas de error SIN efectos: rc==1 y JSON con 'error'
    (opcionalmente conteniendo `pista`, case-insensitive)."""
    def _v(rc, err, d):
        if isinstance(d, dict) and "error" in d:
            if rc == 1 and (pista is None or pista.lower() in str(d["error"]).lower()):
                return True, "error esperado: " + str(d["error"])
            return False, "error inesperado (rc=%s): %s" % (rc, d["error"])
        if rc == 1 and "error" in (err or ""):
            return True, "error esperado (stderr): " + err
        return False, "no hubo JSON de error (rc=%s): %s" % (rc, err or "stdout vacío")
    return _v


def esperar_parser_error():
    """(P1-7) Los errores de argparse AHORA salen como JSON canonico: rc==1 y
    {"error": "argumentos invalidos: ..."} — nunca stderr rc=2. Valida eso."""
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
    partes = []
    for k in list(claves)[:3]:
        partes.append("%s=%s" % (k, _trunca(d.get(k), 18)))
    return " ".join(partes)


# --- bateria modo lectura ---------------------------------------------------

def bateria_lectura():
    print("\n== Modo SEGURO (solo lectura) ==")

    # monitores --------------------------------------------------------------
    def v_listar(rc, err, d):
        ok, ev = esperar_ok("monitores", "virtual", "marco", "via")(rc, err, d)
        if not ok:
            return ok, ev
        if d["marco"] != "px_fisicos_virtual":
            return False, "marco no canonico: %r" % d["marco"]
        STATE["monitores"] = d["monitores"]
        STATE["virtual"] = d["virtual"]
        prim = [m for m in d["monitores"] if m.get("primario")]
        STATE["primario"] = prim[0] if prim else d["monitores"][0]
        return True, "%d monitor(es) primario=%dx%d virtual=%dx%d origen=%s" % (
            len(d["monitores"]), STATE["primario"]["ancho"],
            STATE["primario"]["alto"], d["virtual"]["ancho"],
            d["virtual"]["alto"], d["virtual"]["origen"])
    check("monitores listar", ["monitores.py", "listar"], v_listar)

    if "primario" not in STATE:
        for f in ("monitores cursor", "pantalla tamano", "pantalla capturar"):
            check_skip(f, ["(sin mapa de monitores)"],
                       "monitores.py listar fallo: el resto no puede resolverse")
        return

    n_mons = len(STATE["monitores"])
    check("monitores cursor", ["monitores.py", "cursor"],
          esperar_ok("x", "y", "marco"))
    check("monitores subcomando falso", ["monitores.py", "zz-falso"],
          esperar_parser_error())

    # pantalla ---------------------------------------------------------------
    def v_tamano(rc, err, d):
        ok, ev = esperar_ok("ancho", "alto")(rc, err, d)
        if ok:
            STATE["tamano"] = (d["ancho"], d["alto"])
        return ok, ev
    check("pantalla tamano", ["pantalla.py", "tamano"], v_tamano)
    check("pantalla tamano --virtual", ["pantalla.py", "tamano", "--virtual"],
          esperar_ok("ancho", "alto", "origen"))

    def _limpiar(ruta):
        try:
            os.remove(ruta)
        except OSError:
            pass

    def v_capturar(rc, err, d):
        ok, ev = esperar_ok("archivo", "ancho", "origen",
                            "px_por_unidad_coord", "marco", "plataforma")(rc, err, d)
        if not ok:
            return ok, ev
        if d["marco"] != "px_fisicos_virtual" or d["plataforma"] != "win":
            return False, "contrato P0-4 roto: marco=%r plataforma=%r" % (
                d["marco"], d["plataforma"])
        if "px_por_unidad_coord" not in str(d.get("regla", "")):
            return False, "la 'regla' no usa el campo unico px_por_unidad_coord"
        if not (os.path.isfile(d["archivo"]) and os.path.getsize(d["archivo"]) > 0):
            return False, "el PNG no existe o esta vacio: " + str(d["archivo"])
        _limpiar(d["archivo"])
        return True, "PNG %dx%d origen=%s px/coord=%s (borrado tras verificar)" % (
            d["ancho"], d["alto"], d["origen"], d["px_por_unidad_coord"])
    check("pantalla capturar", ["pantalla.py", "capturar"], v_capturar)

    check("pantalla capturar virtual", ["pantalla.py", "capturar",
                                        "--monitor", "virtual",
                                        "--max-lado", "640"], v_capturar)

    px, py_ = STATE["tamano"]
    check("pantalla capturar region", ["pantalla.py", "capturar", "--region",
                                       "0", "0", str(px // 4), str(py_ // 4)],
          v_capturar)

    if n_mons >= 2:
        check("pantalla capturar --monitor 1", ["pantalla.py", "capturar",
                                                "--monitor", "1"], v_capturar)
    else:
        check_skip("pantalla capturar --monitor 1",
                   ["pantalla.py", "capturar", "--monitor", "1"],
                   "limitacion de hardware: hay %d monitor(es); se requiere >=2"
                   % n_mons)

    def v_posicion(rc, err, d):
        ok, ev = esperar_ok("x", "y")(rc, err, d)
        if ok:
            STATE["cursor"] = (d["x"], d["y"])
        return ok, ev
    check("pantalla posicion", ["pantalla.py", "posicion"], v_posicion)

    cx, cy = STATE["primario"]["izq"] + px // 2, STATE["primario"]["top"] + py_ // 2
    check("pantalla pixel (centro primario)", ["pantalla.py", "pixel", cx, cy],
          esperar_ok("r", "g", "b"))
    check("pantalla pixel fuera de bounding", ["pantalla.py", "pixel",
                                               "999999", "999999"],
          esperar_error("fuera de la pantalla virtual"))

    def v_esperar(rc, err, d):
        ok, ev = esperar_ok("cumplida", "ms_esperados")(rc, err, d)
        if ok and not d["cumplida"]:
            return False, "espera fija no devolvio cumplida=true"
        return ok, ev
    check("pantalla esperar --milisegundos 50", ["pantalla.py", "esperar",
                                                 "--milisegundos", "50"],
          v_esperar)

    def v_pixel_color(rc, err, d):
        ok, ev = esperar_ok("r", "g", "b")(rc, err, d)
        if ok:
            STATE["color_centro"] = "%d,%d,%d" % (d["r"], d["g"], d["b"])
        return ok, ev
    check("pantalla pixel para adaptativa", ["pantalla.py", "pixel", cx, cy],
          v_pixel_color)
    if "color_centro" in STATE:
        def v_adaptativa(rc, err, d):
            ok, ev = esperar_ok("cumplida", "modo")(rc, err, d)
            if not ok:
                return ok, ev
            return True, "modo=%s cumplida=%s (%s)" % (
                d["modo"], d["cumplida"],
                "estable cumplida: el pixel no cambio" if d["cumplida"]
                else "cumplida=false NO es error: algo re-pinto el centro")
        check("pantalla esperar --pixel adaptativa", ["pantalla.py", "esperar",
                                                      "--pixel", cx, cy,
                                                      "--color", STATE["color_centro"],
                                                      "--estable", "200",
                                                      "--timeout", "3"],
              v_adaptativa, timeout=15)
    check("pantalla esperar --pixel sin color", ["pantalla.py", "esperar",
                                                 "--pixel", "5", "5"],
          esperar_error("requiere"))
    check("pantalla localizar archivo inexistente", ["pantalla.py", "localizar",
                                                     "__no_existe__.png"],
          esperar_error("no existe"))

    # ventanas -----------------------------------------------------------------
    def v_listar_v(rc, err, d):
        ok, ev = esperar_ok("ventanas", "total")(rc, err, d)
        if not ok:
            return ok, ev
        # P1-2: el item canonico trae rect+estado ANIDADADOS (y el planas
        # legacy como superset). Validar en el primer item si hay ventanas.
        if d["ventanas"]:
            it = d["ventanas"][0]
            for k in ("rect", "estado", "titulo"):
                if k not in it:
                    return False, "item de listar sin clave canonica %r" % k
            for k in ("left", "top", "ancho", "alto"):
                if k not in it.get("rect", {}):
                    return False, "rect sin clave %r" % k
            for k in ("minimizada", "maximizada", "activa"):
                if k not in it.get("estado", {}):
                    return False, "estado sin clave %r" % k
            if "minimizada" not in it:  # superset legacy exigido en Windows
                return False, "se perdio la clave plana legacy 'minimizada'"
        STATE["ventanas_totales"] = d["total"]
        return True, "total=%s items con rect/estado anidados" % d["total"]
    check("ventanas listar", ["ventanas.py", "listar"], v_listar_v)
    check("ventanas foco", ["ventanas.py", "foco"],
          lambda rc, err, d: (rc == 0 and isinstance(d, dict) and
                              ("ventana" in d or d.get("activa") is None) and
                              ("titulo" in d or d.get("activa") is None),
                              _trunca(str(d or err), 55)))
    check("ventanas activar inexistente", ["ventanas.py", "activar",
                                           "__zz_inexistente__"],
          esperar_error("ninguna ventana contiene"))
    check("ventanas abrir objetivo imposible", ["ventanas.py", "abrir",
                                                "__zz.inexistente.qqq__"],
          esperar_error("no es url"))
    check("ventanas subcomando falso", ["ventanas.py", "zz-falso"],
          esperar_parser_error())

    # raton ---------------------------------------------------------------------
    def v_posicion_raton(rc, err, d):
        # P1-1: forma canónica plana (x/y/marco/via/por_backend), sin claves
        # top-level pyautogui/pynput (mudadas a por_backend).
        ok, ev = esperar_ok("x", "y", "marco", "via", "por_backend")(rc, err, d)
        if not ok:
            return ok, ev
        if d["marco"] != "px_fisicos_virtual":
            return False, "marco no canonico: %r" % d["marco"]
        for k in ("pyautogui", "pynput"):
            if k not in d["por_backend"]:
                return False, "por_backend sin %s" % k
        if "monitor" not in d:
            return False, "posicion sin clave 'monitor' (P1-3)"
        STATE["cursor2"] = (d["por_backend"]["pynput"]["x"],
                            d["por_backend"]["pynput"]["y"])
        return True, "x=%s y=%s via=%s monitor=%s" % (
            d["x"], d["y"], d["via"],
            (d["monitor"] or {}).get("indice") if d.get("monitor") else None)
    check("raton posicion", ["raton.py", "posicion"], v_posicion_raton)
    check("raton click solo --x (sin efecto)", ["raton.py", "click",
                                                "--x", "100"],
          esperar_error("--x e --y juntos"))
    check("raton click --boton invalido (sin efecto)", ["raton.py", "click",
                                                        "--boton", "zz-falso"],
          esperar_error("invalido"))
    check("raton scroll sin eje (sin efecto)", ["raton.py", "scroll"],
          esperar_error("--vertical"))

    # mover fuera del bounding: debe fallar ANTES de tocar el cursor.
    # El desktop es vivo: si el cursor humano se mueve entre lecturas, la
    # comparacion es raciosa por naturaleza -> se muestrea dos veces ANTES y
    # solo se exige inmovilidad si la base era estable (si no, SKIP honesto).
    def _pb(x):
        return ((x or {}).get("por_backend") or {}).get("pynput")
    rc_a, _o, _e, antes = run(["raton.py", "posicion"])
    rc_a2, _oa, _ea, antes2 = run(["raton.py", "posicion"])
    rc, _o, err, d = run(["raton.py", "mover", "999999", "999999"])
    rc_b, _o2, _e2, despues = run(["raton.py", "posicion"])
    error_ok = (rc == 1 and isinstance(d, dict) and
                "fuera de la pantalla virtual" in str(d.get("error", "")))
    base_estable = _pb(antes) is not None and _pb(antes) == _pb(antes2)
    if not error_ok:
        linea("raton mover fuera (sin efecto)",
              comando_de(["raton.py", "mover", "999999", "999999"]), "FAIL",
              "rc=%s err=%s" % (rc, _trunca((d or {}).get("error", err), 50)))
    elif not base_estable:
        linea("raton mover fuera (sin efecto)",
              comando_de(["raton.py", "mover", "999999", "999999"]), "SKIP",
              "error esperado OK; el cursor se movia entre lecturas (humano/"
              "OS activo): no se puede exigir inmovilidad")
    else:
        si_quieto = _pb(despues) == _pb(antes)
        linea("raton mover fuera (sin efecto)",
              comando_de(["raton.py", "mover", "999999", "999999"]),
              "OK" if si_quieto else "FAIL",
              "error esperado + cursor intacto %s" % (
                  _pb(antes) if si_quieto
                  else "MOVIDO: %s->%s" % (_pb(antes), _pb(despues))))
    if n_mons < 2:
        check_skip("raton clic en secundario",
                   ["raton.py", "click --x <secundario>"],
                   "limitacion de hardware: %d monitor(es); se requiere >=2"
                   % n_mons)

    # teclado (todo de inyeccion queda fuera del modo lectura; solo rutas
    # de validacion que abortan ANTES de emitir) -------------------------------
    check("teclado escribir foco invalido (sin efecto)",
          ["teclado.py", "escribir", "hola", "--requiere-foco",
           "__zz_imposible__"], esperar_error("foco"))
    check("teclado tecla desconocida (sin efecto)",
          ["teclado.py", "tecla", "__zz_falsa__"],
          esperar_error("ninguna libreria reconoce"))
    check("teclado combo vacio (sin efecto)", ["teclado.py", "combo", ""],
          esperar_error("vacia"))
    check("teclado mantener tecla desconocida (sin efecto)",
          ["teclado.py", "mantener", "__zz_falsa__", "--segundos", "0.1"],
          esperar_error("ninguna libreria reconoce"))
    def v_via_invalido(rc, err, d):
        ok, ev = esperar_error("invalido")(rc, err, d)
        if not ok:
            return ok, ev
        if "validos" not in (d or {}):
            return False, "falta la clave 'validos' en el error JSON"
        return ok, ev
    check("teclado escribir --via invalido (sin efecto)",
          ["teclado.py", "escribir", "hola", "--via", "zz-falso"],
          v_via_invalido)

    # win_especiales (P2-4): solo rutas de lectura; matar/leer/escribir NO se
    # tocan aqui (efectos o contenido ajeno).
    check("win_especiales portapapeles estado (sin exponer contenido)",
          ["win_especiales.py", "portapapeles", "estado"],
          esperar_ok("ok", "tiene_texto", "largo"))
    check("win_especiales portapapeles accion invalida (sin efecto)",
          ["win_especiales.py", "portapapeles", "zz-accion"],
          esperar_parser_error())

    def v_procesos(rc, err, d):
        ok, ev = esperar_ok("ok", "total", "procesos")(rc, err, d)
        if not ok:
            return ok, ev
        if d["total"] < 1 or not d["procesos"]:
            return False, "tasklist no devolvio procesos (filtro roto?)"
        p0 = d["procesos"][0]
        for k in ("nombre", "pid", "sesion"):
            if k not in p0:
                return False, "proceso sin clave %r" % k
        return True, "total=%s ej=%s pid=%s mem=%s" % (
            d["total"], p0["nombre"], p0["pid"], p0.get("mem_mb"))
    check("win_especiales procesos listar", ["win_especiales.py", "procesos",
                                             "listar", "--nombre",
                                             "svchost.exe"], v_procesos)
    check("win_especiales procesos matar sin confirmar (gate)",
          ["win_especiales.py", "procesos", "matar", "--pid", "4"],
          esperar_error("--confirmar"))
    check("win_especiales procesos matar pid inexistente (sin efecto)",
          ["win_especiales.py", "procesos", "matar", "--pid", "999999",
           "--confirmar"], esperar_error("no existe"))

    def v_dpi(rc, err, d):
        ok, ev = esperar_ok("ok", "monitores", "marco")(rc, err, d)
        if not ok:
            return ok, ev
        if len(d["monitores"]) != len(STATE.get("monitores", [])):
            return False, "dpi ve %d monitores, monitores.py ve %d" % (
                len(d["monitores"]), len(STATE.get("monitores", [])))
        if not all("escala_pct" in m and "dpi_x" in m for m in d["monitores"]):
            return False, "faltan dpi_x/escala_pct en alguno"
        return True, "escalas: %s" % [m["escala_pct"] for m in d["monitores"]]
    check("win_especiales dpi listar", ["win_especiales.py", "dpi", "listar"],
          v_dpi)

    # vigilar: 1 s de escucha pasiva (no inyecta nada; limpia banderas) ------
    def v_vigilar_final(rc, err, d):
        if isinstance(d, dict) and d.get("abortado"):
            return True, "un humano pulso la tecla de panico durante la " \
                         "escucha (bandera creada): no es un fallo"
        return esperar_ok("escuchado_segundos", "abortado")(rc, err, d)
    check("vigilar arrancar 1 s (escucha pasiva)",
          ["vigilar.py", "arrancar", "--segundos", "1"], v_vigilar_final,
          timeout=15)
    check("vigilar segundos invalido", ["vigilar.py", "arrancar",
                                        "--segundos", "0"],
          esperar_error("entre 1 y 900"))


# --- ciclo sandbox (--con-escritura) -----------------------------------------

def _ventanas_notepad():
    """Ventanas cuyo titulo insinua el Bloc de notas (locale-agnostic)."""
    rc, _o, _e, d = run(["ventanas.py", "listar"])
    if not isinstance(d, dict) or "ventanas" not in d:
        return None
    return [v for v in d["ventanas"]
            if "bloc" in v["titulo"].lower() or "notepad" in v["titulo"].lower()]


def _matar(pid):
    if not pid:
        return False
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                   capture_output=True)
    return True


def bateria_escritura():
    print("\n== Modo ESCRITURA: ciclo sandbox Bloc de notas (humano consciente) ==")
    W = ["sandbox pre-check (0 Notepad abiertos)", "ventanas abrir notepad",
         "ventana nueva del Bloc", "ventanas activar + foco",
         "raton click en el lienzo", "teclado escribir ASCII",
         "teclado escribir unicode", "teclado tecla backspace",
         "teclado combo undo", "raton doble clic lienzo",
         "raton arrastrar lienzo", "raton scroll lienzo",
         "raton mover dentro del lienzo", "teclado mantener shift (corto)",
         "pantalla esperar --pixel adaptativa", "ventanas cerrar sin guardar"]

    # W0: solo arrancamos el ciclo si NO hay Notepad (propios o del usuario)
    try:
        p = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Notepad.exe", "/NH"],
                           capture_output=True, timeout=15)
        salida = (p.stdout or b"").decode("utf-8", "replace")
    except Exception as exc:
        salida = ""
        linea(W[0], "tasklist /FI IMAGENAME eq Notepad.exe", "FAIL",
              "tasklist fallo: %s" % exc)
        return
    if "Notepad.exe" in salida or "notepad.exe" in salida.lower():
        for nombre in W:
            linea(nombre, "sandbox", "SKIP",
                  "hay Notepad en ejecucion: cierra sus ventanas y relanza "
                  "(el sandbox no toca trabajo ajeno)")
        return
    linea(W[0], "tasklist /FI IMAGENAME eq Notepad.exe", "OK",
          "0 procesos Notepad antes del ciclo")

    pid = None
    try:
        # W1: abrir esperando la ventana (la pista "Bloc" vale en Windows ES;
        # en otros idiomas se resuelve por diff de titulos mas abajo)
        rc, _o, err, d = run(["ventanas.py", "abrir", "notepad", "--esperar",
                              "10", "--titulo", "Bloc"], timeout=60)
        ok = rc == 0 and isinstance(d, dict) and d.get("ok")
        pid = d.get("pid") if isinstance(d, dict) else None
        linea(W[1], comando_de(["ventanas.py", "abrir", "notepad", "--esperar",
                                "10", "--titulo", "Bloc"]),
              "OK" if ok else "FAIL",
              ("pid=%s ventana=%s" % (pid, (d.get("ventana") or {}).get("titulo")
                                      if d else None)) if ok
              else _resumen_fallo(rc, err, d))
        if not ok:
            for nombre in W[2:]:
                linea(nombre, "sandbox", "SKIP", "abrir fallo: ciclo abortado")
            return

        # W2: localizar la ventana nueva (por diff de titulos: robusto al locale)
        ventana = None
        for _ in range(12):
            nuevos = _ventanas_notepad()
            if nuevos:
                ventana = nuevos[0]
                break
            subprocess.run([PY, "-c", "import time; time.sleep(0.5)"])
        if ventana is None:
            linea(W[2], "ventanas.py listar (diff)", "FAIL",
                  "no aparecio ventana del Bloc en 6 s")
            for nombre in W[3:]:
                linea(nombre, "sandbox", "SKIP", "sin ventana: ciclo abortado")
            return
        titulo = ventana["titulo"]
        rect = ventana
        cx = rect["left"] + max(rect["ancho"] // 2, 50)
        cy = rect["top"] + max(rect["alto"] // 2, 50)
        STATE["sandbox"] = {"titulo": titulo, "cx": cx, "cy": cy}
        linea(W[2], "ventanas.py listar (diff)", "OK",
              "'%s' rect=%dx%d en (%d,%d)" % (titulo, rect["ancho"],
                                              rect["alto"], rect["left"],
                                              rect["top"]))

        def v_ok(rc, err, d2):
            return esperar_ok("ok")(rc, err, d2)

        # activar + foco (la ventana debe recibir el teclado)
        rc, _o, err, d2 = run(["ventanas.py", "activar", titulo])
        rc2, _o2, err2, d3 = run(["ventanas.py", "foco"])
        foco_ok = (rc == 0 and isinstance(d2, dict) and d2.get("ok")
                   and rc2 == 0 and isinstance(d3, dict)
                   and str(d3.get("titulo", "")).lower() in titulo.lower()
                   or (isinstance(d3, dict) and titulo.lower() in
                       str(d3.get("titulo", "")).lower()))
        linea(W[3], comando_de(["ventanas.py", "activar", "'%s'" % titulo]) +
              " + foco", "OK" if foco_ok else "FAIL",
              "foco='%s'" % ((d3 or {}).get("titulo") if isinstance(d3, dict)
                              else err2))

        pasos = [
            (W[4], ["raton.py", "click", "--x", cx, "--y", cy], v_ok),
            (W[5], ["teclado.py", "escribir", "Hola autotest 123",
                    "--requiere-foco", titulo], v_ok),
            (W[6], ["teclado.py", "escribir", "Ñ¿Á 😀"], v_ok),
            (W[7], ["teclado.py", "tecla", "backspace", "--repeticiones", "3"],
             v_ok),
            (W[8], ["teclado.py", "combo", "ctrl+z"], v_ok),
            (W[9], ["raton.py", "click", "--x", cx, "--y", cy, "--doble"],
             v_ok),
            (W[10], ["raton.py", "arrastrar", cx - 100, cy, cx + 100, cy,
                     "--duracion", "0.4"], v_ok),
            (W[11], ["raton.py", "scroll", "--vertical", "-2", "--x", cx,
                     "--y", cy], v_ok),
            (W[12], ["raton.py", "mover", cx + 20, cy + 5, "--duracion", "0.2"],
             v_ok),
            (W[13], ["teclado.py", "mantener", "shift", "--segundos", "0.3"],
             v_ok),
        ]
        for nombre, args, val in pasos:
            if nombre == W[10] and rect["ancho"] < 260:
                linea(nombre, comando_de(args), "SKIP",
                      "ventana de %d px: muy estrecha para arrastrar dentro"
                      % rect["ancho"])
                continue
            check(nombre, args, val, timeout=25)

        # W14: espera adaptativa sobre un punto estable del lienzo
        rc, _o, err, dpix = run(["pantalla.py", "pixel", cx, cy])
        if isinstance(dpix, dict) and "r" in dpix:
            color = "%d,%d,%d" % (dpix["r"], dpix["g"], dpix["b"])
            def v_adap(rc2, err2, d4):
                ok2, ev2 = esperar_ok("cumplida", "modo")(rc2, err2, d4)
                if not ok2:
                    return ok2, ev2
                return True, "color=%s estable cumplida=%s (false NO es error)" % (
                    color, d4["cumplida"])
            check(W[14], ["pantalla.py", "esperar", "--pixel", cx, cy,
                          "--color", color, "--estable", "200", "--timeout",
                          "3"], v_adap, timeout=15)
        else:
            linea(W[14], "pantalla.py esperar --pixel", "FAIL",
                  "no se pudo leer el pixel base: " + _resumen_fallo(rc, err, dpix))

        # W15: cerrar SIN guardar (cerrar -> posible modal -> ESC -> kill propio)
        rc, _o, err, d5 = run(["ventanas.py", "cerrar", titulo])
        if not (rc == 0 and isinstance(d5, dict) and d5.get("ok")):
            linea(W[15], comando_de(["ventanas.py", "cerrar", "'%s'" % titulo]),
                  "FAIL", _resumen_fallo(rc, err, d5))
            return
        subprocess.run([PY, "-c", "import time; time.sleep(0.8)"])
        quedan = _ventanas_notepad()
        via = "cerrar sin dialogo (no habia cambios que preguntar)"
        if quedan:
            run(["teclado.py", "tecla", "esc"])  # descarta el modal de guardado
            subprocess.run([PY, "-c", "import time; time.sleep(0.6)"])
            _matar(pid)  # mata SOLO el proceso que el sandbox lanzo
            via = "hubo ventana/modal restante: ESC al guardado + taskkill PID %s" % pid
            subprocess.run([PY, "-c", "import time; time.sleep(0.6)"])
        quedan = _ventanas_notepad()
        if isinstance(quedan, list) and not quedan:
            linea(W[15], comando_de(["ventanas.py", "cerrar", "'%s'" % titulo])
                  + " + limpieza", "OK", via + "; sin ventanas Notepad restantes")
        else:
            linea(W[15], comando_de(["ventanas.py", "cerrar", "'%s'" % titulo]),
                  "FAIL", "quedan ventanas tras cerrar/limpiar: %s" % (
                      [v["titulo"] for v in (quedan or [])][:3]))
    finally:
        # seguridad del sandbox: NO dejar el Bloc abierto ni a medio teclear
        try:
            restantes = _ventanas_notepad()
            if restantes is None or restantes:
                _matar(pid)
        except Exception:
            pass


# --- ejecucion ----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        prog="autotest.py",
        description="Autovalidacion de la skill computer-use-py (rama Windows). "
                    "Por defecto SOLO LECTURA (seguro). --con-escritura ejecuta "
                    "el ciclo sandbox completo (lanza y cierra el Bloc de notas; "
                    "exige 0 Notepad abiertos).")
    ap.add_argument("--con-escritura", dest="con_escritura",
                    action="store_true",
                    help="ciclo sandbox completo (solo un humano consciente)")
    args = ap.parse_args()

    # estado limpio: banderas ABORT/PAUSA de sesiones previas no deben
    # contaminar la corrida (el sandbox/expectar las trataria como parada)
    residuales = []
    for b in (ABORT, PAUSA):
        if os.path.exists(b):
            residuales.append(os.path.basename(b))
            try:
                os.remove(b)
            except OSError:
                pass

    print("# autotest computer-use-py — %s" % (
        "LECTURA + ESCRITURA" if args.con_escritura else "modo seguro (lectura)"))
    print("python: %s | raiz: %s" % (PY, RAIZ))
    if residuales:
        print("banderas previas limpiadas por el autotest: %s" % ", ".join(residuales))
    print("%s" % ("-" * 140))
    print("%-*s | %-*s | %-*s | %s"
          % (_W[0], "FUNCION", _W[1], "COMANDO", _W[2], "EST", "EVIDENCIA"))
    print("%s" % ("-" * 140))

    bateria_lectura()
    if args.con_escritura:
        bateria_escritura()
    else:
        for nombre in ("sandbox pre-check", "ventanas abrir notepad",
                       "ciclo de escritura completo"):
            linea(nombre, "sandbox", "SKIP",
                  "modo seguro: relanza con --con-escritura (humano consciente)")

    total = sum(CONT.values())
    veredicto = "PASS" if CONT["fail"] == 0 else "FAIL"
    resumen = {
        "modo": "lectura+escritura" if args.con_escritura else "lectura",
        "total": total,
        "pasados": CONT["ok"],
        "fallados": CONT["fail"],
        "skips": CONT["skip"],
        "veredicto": veredicto,
        "fallas": FALLAS,
        "nota": "un FAIL en un check de modo lectura = bug de un script de la "
                "rama Windows: reportar a @7-cerrador sin parchar a ciegas; "
                "SKIP = limitacion de hardware/entorno con motivo",
    }
    print("\n" + "-" * 140)
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    sys.exit(0 if CONT["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
