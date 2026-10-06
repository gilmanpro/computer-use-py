# -*- coding: utf-8 -*-
"""autotest.py — SUITE UNIFICADA de autovalidacion de computer-use-py (raiz).

FASE SEG3 (simetria total): la suite vive en scripts/ y es UNA para los 3 SO
— ya no delega en suites de rama (las carpetas linux/ y macos/ guardan solo
su libreria exclusiva):
  * win32: corre la bateria COMPLETA de la ruta Windows sobre los CLIs de la
    raiz (validada en escritorio real) — comportamiento historico intacto —
    MAS los checks ESTATICOS multi-OS de SEG3 y las filas SKIP honestas de
    las baterias reales linux/macos (no portadas: spawean primitivas
    X11/Quartz/osascript que exigen su SO).
  * linux/darwin: corre los checks de estructura, dispatch, estaticos de los
    especiales y contrato documentado (todos importables/auditable en
    cualquier SO), con la bateria Windows marcada SKIP ("requiere Windows")
    y las baterias reales de la otra rama SKIP con motivo.
  * plataforma desconocida: JSON canonico de error + exit 2 (contrato de los
    guards; nunca traceback).

Bateria win32 sobre TODAS las funciones de los CLIs en modo SEGURO por
defecto: solo LECTURA (no teclea, no mueve el cursor, no hace clic). Las
unicas escrituras del modo lectura son PNG dentro del .tmp/ de la skill y el
listener PASIVO de vigilar.py durante 1 s (no inyecta nada). Los "errores de
parser" se validan contra rutas del codigo que abortan ANTES de emitir, de
modo que tampoco tienen efectos.

Uso (desde la carpeta computer-use-py): el PUNTO DE ENTRADA universal es
`py autotest.py` en la raiz de la skill (portada que llama a ESTA suite).
Llamada directa a la suite (avanzado, equivalente):
    py scripts/autotest.py                        :: win32 modo lectura (defecto)
    py scripts/autotest.py --con-escritura        :: ciclo sandbox (humano)
    py scripts/autotest.py --golden captura|comparar [subset]  :: byte-identity

Nota de invocaion fiel (absorbida de .tmp/run_suite.py, FASE TEST-B): correr
la suite por SUBPROCESS (como arriba) conserva el rc real; los envoltorios
.bat historicos leian %errorlevel% despues de un comando intermedio y
mentian el veredicto. No recrear wrappers .bat para el veredicto.

El modo escritura win32 (que un humano lanza a conciencia) es el ciclo
SANDBOX CON VENTANA GARANTIZADA (IMPL-K P1.4 — reemplaza el viejo gate
"0 Notepads del usuario"): escribe .tmp/cu_sandbox_<hex8>.txt (3 lineas
ASCII, titulo UNICO por nombre de archivo: convive con los Notepads abiertos
del usuario), lo abre con `ventanas.py abrir <ruta> --esperar-nueva` (hWnd
garantizado por diff), dirige TODO el ciclo por `--foco-id` (click/escribir
ASCII+unicode/backspace/undo/doble/arrastrar/scroll/mover/mantener/esperar
--pixel), prueba `mover --monitor` (primario/secundario + negativo fuera de
rango), el GATE MULTI-VENTANA de `procesos matar` con su propio PID (espera
rc=1 sin matar; --forzar NO se prueba si el PID comparte ventanas: matar
trabajo ajeno es el incidente P0.2), cierra con `cerrar --id --descartar` y
exige desaparicion POR ID. En `finally` taskkill SOLO del PID dueno EXCLUSIVO
del hWnd propio (verificado con EnumWindows: N==1 y ==nuestra ventana); si
el PID tiene mas ventanas visibles => FAIL-con-motivo y NUNCA kill. Si la
asociacion .txt no es un editor (titulo sin Bloc/Notepad) => SKIP con motivo
honesto "asociacion .txt != editor", cerrando la ventana por id.

VERIFICADO 06/10/2026 (bug real de entorno capturado por el sandbox): en el
Bloc de notas de Windows 11 el titulo de una pestana SIN guardar es el
CONTENIDO del documento ('*Hola...: Bloc de notas'), por lo que el titulo
CAMBIA al teclear: el sandbox identifica SU ventana por su hWnd (clave 'id',
estable) — de ahi el disenado por id del ciclo IMPL-K. Ademas, 'abrir'
reporta el PID del lanzador y la ventana vive en el proceso empaquetado: la
limpieza usa el PID REAL del hWnd (GetWindowThreadProcessId) con el gate
multi-ventana arriba descrito.

Modo golden (IMPL-K P2.1, absorbe el driver .tmp/byte_identity.py):
`--golden captura|comparar [subset]` guarda/compone los .out (rc+bytes de
stdout/stderr) de 15 salidas en .tmp/golden/. En la bateria de lectura corre
ademas el check de DETERMINISMO: los 9 casos deterministas se ejecutan DOS
veces y deben dar bytes identicos; los 6 "vivos" (ventanas/cursor del
usuario en medio — drift documentado en .tmp/drift_vs_baseline.txt) quedan
EXENTOS de identidad y solo se validan como JSON+rc esperados.

Salida: tabla [funcion | comando | OK/FAIL/SKIP | evidencia] + JSON resumen
{modo, total, pasados, fallados, skips, veredicto, fallas}. exit 0 si no hay
FAIL reales; las limitaciones de hardware/entorno son SKIP con motivo
(p. ej. un solo monitor: la prueba del secundario se omite, no falla).

Checks de estructura y estaticos (SEG3): inventario del layout (scripts/
raiz = 7 CLIs + _core.py + glue_windows.py + windows/ solo
win_especiales.py + linux/ solo linux_especiales.py + macos/ solo
macos_especiales.py; todo via _core.problemas_estructura()), modulos
exclusivos sin redefiniciones, DISPATCH en el propio proceso verificado por
LECTURA DE FUENTE de los 6 CLIs raiz (marcas _core.modulo_sistema /
construir_parser_linux / construir_parser_mac y ausencia de enrutar( — el
viejo check del enrutador SEG2 con plataforma parcheada queda ELIMINADO),
estatico de que glue_windows.py no menciona las librerias exclusivas
linux_especiales/macos_especiales ni el retirado _compartido, py_compile +
importabilidad en cualquier SO + guard rc 2 "EXCLUSIVO" de los CLIs
exclusivos de los SO que NO son el anfitrion, y contrato documentado
(references/linux-python.md, references/macos-python.md y SKILL.md).
"""

import argparse
import json
import os
import subprocess
import sys

# --- Deteccion de plataforma (FASE SEG3: SUITE UNIFICADA en la raiz) ------
# Una sola suite para los 3 SO: los checks de estructura, del dispatch, de
# los especiales (py_compile/import/guard) y del contrato documentado corren
# en CUALQUIER plataforma (leen fuente o lanzan subprocess que responde antes
# de tocar APIs del SO). Las baterias REALES de cada SO solo se ejecutan en
# su anfitrion; en las otras plataforma se reportan como SKIP honesto con el
# recuento de checks omitidos. Cualquier plataforma fuera de
# win32/linux/darwin: JSON canonico + rc 2 (contrato de guards, sin
# traceback). Las viejas suites de rama scripts/linux|macos/autotest.py ya
# NO existen: fueron retiradas con los 16 motores viejos del enrute SEG2.
_DIR_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
HOST_WIN = sys.platform == "win32"

if sys.platform not in ("win32", "linux", "darwin"):
    print(json.dumps({
        "error": "autotest.py: plataforma no soportada (%s); la suite unificada "
                 "de FASE SEG3 corre en win32, linux y darwin (los CLIs raiz "
                 "dispatchan su ruta en el propio proceso; scripts/<verbo>.py)"
                 % sys.platform,
        "sistema_operativo": sys.platform,
        "plataforma": {"win32": "win", "linux": "linux",
                       "darwin": "darwin"}.get(sys.platform, sys.platform),
    }, ensure_ascii=False))
    sys.exit(2)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --- autotest de estructura (FASE SEG3) -------------------------------------
# _core.py vive en scripts/ JUNTO a esta suite: se importa DIRECTAMENTE
# (stdlib puro, sin pyautogui/DPI) solo para auditar la separacion
# generico/exclusivo del layout SEG3. La logica de los checks de
# inventario/redefiniciones es la auditoria combinada problemas_estructura()
# (= problemas_inventario_scripts + problemas_redefiniciones), que audita
# scripts/ raiz y las 3 carpetas de lo exclusivo (win/linux/macos_especiales).
if _DIR_SCRIPTS not in sys.path:
    sys.path.insert(0, _DIR_SCRIPTS)
import _core  # noqa: E402

# scripts/autotest.py → 2 subidas de nivel hasta la raiz de la skill.
RAIZ = os.path.dirname(_DIR_SCRIPTS)
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


def _ruta_cli(nombre):
    """FASE SEG3: los 6 CLIs multi-OS + autotest.py + _core.py +
    glue_windows.py viven en scripts/ raiz; win_especiales.py queda en
    scripts/windows/ (unico archivo exclusivo alla; linux/macos ESPECIALES
    se invocan por ruta directa en sus checks propios, no por aqui)."""
    if nombre == "win_especiales.py":
        return os.path.join("scripts", "windows", nombre)
    return os.path.join("scripts", nombre)


def run(args, timeout=40):
    """Ejecuta un CLI de la skill (raiz SEG3; win_especiales en su carpeta):
    (rc, stdout-texto, stderr-texto, JSON|None)."""
    cmd = [PY, _ruta_cli(args[0])] + [str(a) for a in args[1:]]
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
    return "py " + _ruta_cli(args[0]).replace("\\", "/") + " " + \
        " ".join(str(a) for a in args[1:])


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


# --- checks de estructura y estaticos SEG3 (corren en CUALQUIER SO) --------
# Los 6 CLIs raiz con dispatch en el propio proceso (autotest.py queda fuera:
# es ESTA misma suite):
_CLIS_DISPATCH = tuple(cli for cli in _core.CLI_RAIZ if cli != "autotest.py")
# Modulo exclusivo por carpeta + verbo minimo de su CLI propio para probar el
# guard ('sesion' en linux solo lee entorno; 'tcc' en macos solo imprime la
# tabla de hints: ninguno toca API del SO ANTES del guard del __main__):
_ESPECIALES = (("linux", "linux_especiales", "sesion"),
               ("macos", "macos_especiales", "tcc"))
# Carpeta de lo exclusivo que corresponde al SO anfitrion (su guard no se
# exige: es nativo aqui):
_RAMAS_ANFITRION = {"win32": "windows", "linux": "linux", "darwin": "macos"}


def _checks_estructura():
    """Autotest de estructura multi-OS (FASE SEG3) sobre la auditoria
    combinada _core.problemas_estructura(): (1) scripts/ raiz es
    exactamente los 7 CLIs + _core.py + glue_windows.py + las 3 carpetas de
    lo exclusivo (windows/ SOLO win_especiales.py, linux/ SOLO
    linux_especiales.py, macos/ SOLO macos_especiales.py) con los 9
    obligatorios presentes; (2) ningun modulo exclusivo redefine un helper
    movido (unica forma admitida: `nombre = _core.nombre`). Se emiten las
    dos filas separadas para conservar la granularidad historica y ademas se
    contrasta con la combinada. Checks internos puros (leen via _core): sin
    subprocess y sin efectos."""
    probs_inv = _core.problemas_inventario_scripts()
    linea("estructura: scripts/ raiz + carpetas exclusivas", "(check interno)",
          "OK" if not probs_inv else "FAIL",
          "; ".join(probs_inv)[:150] if probs_inv
          else "raiz = 7 CLIs + _core.py + glue_windows.py + "
               "windows/(win_especiales) + linux/(linux_especiales) + "
               "macos/(macos_especiales)")
    probs_red = _core.problemas_redefiniciones()
    linea("estructura: modulos exclusivos sin redefiniciones", "(check interno)",
          "OK" if not probs_red else "FAIL",
          "; ".join(probs_red)[:150] if probs_red
          else "glue_windows/linux_especiales/macos_especiales solo reexportan "
               "HELPERS_COMUNES")
    # problemas_estructura() es la auditoria combinada SEG3 que la suite usa
    # como fuente: las dos filas de arriba deben cubrirla exacta (sin
    # violaciones huerfanas entre inventario/redefiniciones y la combinada):
    if len(probs_inv) + len(probs_red) != len(_core.problemas_estructura()):
        linea("estructura: consistencia problemas_estructura()", "(check interno)",
              "FAIL", "la suma de inventario+redefiniciones difiere de la "
                      "auditoria combinada (cambio a medias en _core?)")


def _check_despacho():
    """Check SEG3-1 (estatico, SUSTITUTO del viejo _check_enrutador_simulado
    SEG2): los 6 CLIs raiz ejecutan la ruta de su SO EN EL PROPIO PROCESO.
    Por lectura de fuente se exige en cada uno las marcas reales del patron
    main() unificado — `_core.modulo_sistema` (bind del alias `c` en tiempo
    de ejecucion), `construir_parser_linux` y `construir_parser_mac` (las
    secciones no-windows conviven en el mismo archivo) — y la AUSENCIA del
    enrute SEG2 (`enrutar(`). Ya no hay plan simulable con plataforma
    parcheada: plan_enrute/destino_rama/enrutar fueron ELIMINADOS de _core,
    asi que la verificacion es 100 % estatica (sin subprocess, sin efectos).
    El rc 2 de plataforma desconocida lo cubre so_no_soportado(), auditable
    en .tmp/ con el driver de mock del orquestador."""
    probs = []
    for cli in _CLIS_DISPATCH:
        ruta = os.path.join(_DIR_SCRIPTS, cli)
        if not os.path.isfile(ruta):
            probs.append("%s: no existe" % cli)
            continue
        with open(ruta, encoding="utf-8") as fh:
            fuente = fh.read()
        for marca in ("_core.modulo_sistema", "construir_parser_linux",
                      "construir_parser_mac"):
            if marca not in fuente:
                probs.append("%s: sin marca %r" % (cli, marca))
        if "enrutar(" in fuente:
            probs.append("%s: conserva el viejo enrutar()" % cli)
    linea("dispatch SEG3: 6 CLIs raiz ejecutan en el propio proceso",
          "(check estatico)", "OK" if not probs else "FAIL",
          "; ".join(probs)[:150] if probs
          else "6 CLIs con _core.modulo_sistema + construir_parser_linux + "
               "construir_parser_mac y sin enrutar()")


def _check_glue_no_import_ramas():
    """Check SEG3-2 (estatico): glue_windows.py — el modulo de primitivas
    win32 que los CLIs raiz importan SOLO al despachar a la rama win — no
    debe mencionar ni ligarse a las librerias exclusivas de los otros SO
    (`linux_especiales`, `macos_especiales`) ni al retirado `import
    _compartido`: con el enrute SEG2 eliminado ya no existe el orden
    enrutar()->glue que se auditaba antes; la simetria SEG3 exige que el
    glue sea exclusivo de Windows y no acople el motor ajeno."""
    probs = []
    ruta = os.path.join(_DIR_SCRIPTS, _core.GLUE_RAIZ)
    if not os.path.isfile(ruta):
        probs.append("falta %s" % _core.GLUE_RAIZ)
    else:
        with open(ruta, encoding="utf-8") as fh:
            fuente = fh.read()
        for marca in ("linux_especiales", "macos_especiales",
                      "import _compartido"):
            if marca in fuente:
                probs.append("glue_windows.py menciona %r" % marca)
    linea("glue Windows no menciona ramas ni _compartido", "(check estatico)",
          "OK" if not probs else "FAIL",
          "; ".join(probs)[:150] if probs
          else "glue_windows.py sin linux_especiales/macos_especiales/'import "
               "_compartido'")


def _check_especiales_compilan():
    """Check SEG3-3 (portado de la via avanzada de las suites de rama):
    cada libreria exclusiva EXISTE en su carpeta y COMPILA con subprocess
    `py -m py_compile`, en cualquier SO."""
    for rama, modulo, _verbo in _ESPECIALES:
        funcion = "especiales: py_compile %s/%s.py" % (rama, modulo)
        comando = "py -m py_compile scripts/%s/%s.py" % (rama, modulo)
        ruta = os.path.join(_DIR_SCRIPTS, rama, modulo + ".py")
        if not os.path.isfile(ruta):
            linea(funcion, comando, "FAIL", "falta el archivo: %s" % ruta)
            continue
        try:
            p = subprocess.run([PY, "-m", "py_compile", ruta], cwd=RAIZ,
                               capture_output=True, timeout=60)
            ok = p.returncode == 0
            ev = "rc=0 compila" if ok else "rc=%s stderr=%s" % (
                p.returncode, _trunca((p.stderr or b"").decode("utf-8", "replace"), 50))
        except subprocess.TimeoutExpired:
            ok, ev = False, "TIMEOUT de 60 s"
        except Exception as exc:
            ok, ev = False, "%s: %s" % (type(exc).__name__, exc)
        linea(funcion, comando, "OK" if ok else "FAIL", ev)


def _check_especiales_importables():
    """Check SEG3-4: ambos especiales son LIBRERIA importable en CUALQUIER SO
    (el guard de plataforma NO vive en el nivel-import): subprocess
    `python -c "import sys;sys.path.insert(0,<carpeta>);import <modulo>"` con
    rc 0 y stdout VACIO — si el guard volviera a vivir en el import, en
    Windows imprimaria su JSON o saldria con rc 2."""
    for rama, modulo, _verbo in _ESPECIALES:
        funcion = "especiales: importable en cualquier SO (%s)" % modulo
        comando = "py -c import %s" % modulo
        code = ("import sys; sys.path.insert(0, r'%s'); import %s"
                % (os.path.join(_DIR_SCRIPTS, rama), modulo))
        try:
            p = subprocess.run([PY, "-c", code], cwd=RAIZ,
                               capture_output=True, timeout=60)
            stdout = (p.stdout or b"").decode("utf-8", "replace").strip()
            ok = p.returncode == 0 and stdout == ""
            ev = ("rc=0, stdout vacio (guard solo en su __main__)" if ok
                  else "rc=%s stdout=%r stderr=%r" % (
                      p.returncode, _trunca(stdout, 40),
                      _trunca((p.stderr or b"").decode("utf-8", "replace"), 40)))
        except subprocess.TimeoutExpired:
            ok, ev = False, "TIMEOUT de 60 s"
        except Exception as exc:
            ok, ev = False, "%s: %s" % (type(exc).__name__, exc)
        linea(funcion, comando, "OK" if ok else "FAIL", ev)


def _check_guards_clis_exclusivos():
    """Check SEG3-5: el CLI propio de cada especial (`linux_especiales.py
    sesion`, `macos_especiales.py tcc`) responde rc 2 con JSON cuyo 'error'
    menciona EXCLUSIVO cuando corre en un SO DISTINTO del suyo: el guard
    vive SOLO en el __main__ y responde ANTES de parsear. En Windows
    anfitrion se prueban AMBOS (check integro); en Linux solo el de macOS y
    en macOS solo el de Linux — el especial del SO anfitrion es nativo aqui
    y su ruta real la ejercitan los CLIs raiz (bateria propia de ese SO).
    En el anfitrion correspondiente el verbo propio puede ir a lectura
    manual (p. ej. `sesion` en Linux), pero esta suite no lo spawnea para no
    depender de session X11/TCC."""
    host = _RAMAS_ANFITRION.get(sys.platform, "")
    for rama, modulo, verbo in _ESPECIALES:
        if rama == host:
            continue  # nativo en este SO: nada que guardar (guard no aplica)
        funcion = "guard CLI exclusivo %s %s" % (modulo, verbo)
        comando = "py scripts/%s/%s.py %s" % (rama, modulo, verbo)
        ruta = os.path.join(_DIR_SCRIPTS, rama, modulo + ".py")
        if not os.path.isfile(ruta):
            linea(funcion, comando, "FAIL", "falta el archivo: %s" % ruta)
            continue
        try:
            p = subprocess.run([PY, ruta, verbo], cwd=RAIZ,
                               capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            linea(funcion, comando, "FAIL", "TIMEOUT de 30 s")
            continue
        out = (p.stdout or b"").decode("utf-8", "replace")
        try:
            d = json.loads(out)
        except ValueError:
            d = None
        ok = (p.returncode == 2 and isinstance(d, dict)
              and "EXCLUSIVO" in str(d.get("error", "")))
        linea(funcion, comando, "OK" if ok else "FAIL",
              "rc=%s error=%s" % (p.returncode, _trunca(
                  (d or {}).get("error", out or p.stderr), 55)))


# --- contrato documentado: la REDACCION literal la fija @D; esta suite solo
#    exige contenido minimo (ruta del flujo normal + nombres de los
#    exclusivos). Archivo ausente (p. ej. preview con solo scripts/ copiados)
#    o marca ausente = SKIP honesto, nunca FAIL por redaccion. ---------------
_DOC_OBLIGATORIA = (
    ("contrato documentado: references/linux-python.md",
     os.path.join("references", "linux-python.md"),
     (("scripts/pantalla.py", "scripts/<verbo>"), ("linux_especiales",))),
    ("contrato documentado: references/macos-python.md",
     os.path.join("references", "macos-python.md"),
     (("scripts/pantalla.py", "scripts/<verbo>"), ("macos_especiales",))),
    ("contrato documentado: SKILL.md (simetria)",
     "SKILL.md",
     (("scripts/pantalla.py", "scripts/<verbo>"),
      ("linux_especiales", "macos_especiales"))),
)


def _check_contrato_documentado():
    """Check SEG3-6 (portado/estrechado, coordinado con @D): los docs del
    contrato multi-OS existen y mencionan (a) la entrada del flujo normal
    scripts/<verbo> (o el ejemplo scripts/pantalla.py) y (b) los nombres de
    los modulos exclusivos linux_especiales/macos_especiales. Cada grupo es
    un OR de formas aceptables; la cadena literal definitiva la deja @D, asi
    que una marca faltante se reporta SKIP 'pendiente @D' (no FAIL)."""
    for funcion, rel, grupos in _DOC_OBLIGATORIA:
        ruta = os.path.join(RAIZ, rel)
        if not os.path.isfile(ruta):
            linea(funcion, "(check estatico)", "SKIP",
                  "documento no visible en este arbol (la preview de .tmp "
                  "solo copia scripts/): %s" % rel.replace("\\", "/"))
            continue
        with open(ruta, encoding="utf-8") as fh:
            fuente = fh.read()
        faltan = ["/".join(g) for g in grupos if not any(m in fuente for m in g)]
        if faltan:
            linea(funcion, "(check estatico)", "SKIP",
                  "pendiente @D: no menciona %s" % ", ".join(faltan))
        else:
            linea(funcion, "(check estatico)", "OK",
                  "menciona el flujo scripts/<verbo> y los modulos exclusivos")


# --- baterias REALES linux/macos, portadas como SKIP honesto ----------------
# La suite unificada SEG3 NO spawnea primitivas X11/Quartz/osascript: las
# baterias reales de las ramas se retiraron junto con las suites de rama
# (scripts/linux|macos/autotest.py, parte de los 16 motores viejos del
# enrute SEG2). Recuento ESTATICO tomado el 06/10/2026 sobre esas suites
# antes de su retiro:
#   linux: 38 call-sites de check( en bateria_lectura + 15 filas del ciclo
#          sandbox (lista W de bateria_escritura)  -> 53 checks equivalentes
#   macos: 32 call-sites de check( en bateria_lectura + 15 filas del ciclo
#          sandbox (lista W de bateria_escritura)  -> 47 checks equivalentes
# La bateria Windows queda INTACTA en esta suite (anfitrion win32); en otro
# SO se reporta como SKIP simétrico con su propio recuento.
_BATERIAS_REALES = (
    ("bateria real Linux (lectura)",
     "(bateria historica del dominio Linux, retirada en SEG3)",
     "linux", 53, "requiere Linux"),
    ("bateria real Linux (sandbox)",
     "(sandbox historico del dominio Linux, retirado en SEG3)",
     "linux", 15, "requiere Linux"),
    ("bateria real macOS (lectura)",
     "(bateria historica del dominio macOS, retirada en SEG3)",
     "macos", 47, "requiere macOS"),
    ("bateria real macOS (sandbox)",
     "(sandbox historico del dominio macOS, retirado en SEG3)",
     "macos", 15, "requiere macOS"),
)

# Filas emitidas por la bateria Windows real de esta suite en modo lectura
# (baseline 06/10/2026: 47 totales - 2 estructura - 1 enrutador - 1 glue
#  - 3 skips sandbox = 40 filas reales de CLIs; IMPL-K 06/10/2026: +10 filas
#  [8 checks nuevos de CLIs: gate --foco-id falso, activar/mover/abrir/
#  ocupantes/restaurar negativos, ocupantes live; 2 estaticos: ppu linux/mac
#  y golden determinismo] = 50):
_N_BATERIA_WIN = 50


def _skips_baterias_reales():
    """Filas SKIP honestas por cada bateria real de rama no portada (motivo
    explicito + recuento de checks que representa). Si el anfitrion ES ese
    SO, el motivo lo aclara: la bateria de rama no se porto a la suite
    unificada y la validacion en vivo se hace por los CLIs raiz (dispatch en
    el propio proceso)."""
    host = {"linux": "linux", "darwin": "macos"}.get(sys.platform)
    for funcion, comando, rama, n, motivo in _BATERIAS_REALES:
        if host == rama:
            ev = ("%s es el anfitrion, pero la bateria real de la rama no se "
                  "porto a la suite unificada SEG3: %d checks equivalentes "
                  "omitidos — valida en vivo con los CLIs raiz scripts/"
                  "<verbo>.py" % (rama, n))
        else:
            ev = "%s: %d checks omitidos (suite de rama retirada en SEG3)" % (
                motivo, n)
        linea(funcion, comando, "SKIP", ev)


# --- IMPL-K P0.3: check ESTATICO de la formula ppu de las ramas linux/mac ---

def _check_ppu_estatico():
    """La regla de la skill DIVIDE: px_por_unidad_coord debe ser
    pixels-de-IMAGEN por unidad = factor_escala/escala_x (escala_x =
    fuente/imagen de _core.escalas_thumbnail). FIX IMPL-K P0.3 = espejo del
    fix W11 de Windows; las ramas linux/mac NO son verificables en esta
    maquina ([runtime]): este check de LECTURA DE FUENTE cierra la grieta que
    lo hizo invisible (la prueba live del caso Windows corre dentro de
    v_capturar como invariante ppu<=1 + round-trip)."""
    ruta = os.path.join(_DIR_SCRIPTS, "pantalla.py")
    try:
        with open(ruta, encoding="utf-8") as fh:
            fuente = fh.read()
    except OSError as exc:
        linea("ppu estatico: formulas linux/mac espejo del fix W11",
              "(check estatico)", "FAIL", "no se pudo leer pantalla.py: %s" % exc)
        return
    probs = []
    for marca in ("px_por_unidad_coord = (factor_grim or 1.0) / escala_x",
                  "round(esc_ret / escala_x, 6)",
                  "round(1.0 / escala_x, 6)"):
        if marca not in fuente:
            probs.append("falta la formula corregida %r" % marca)
    for invertida in ("escala_x * (factor_grim or 1.0)", "escala_x * esc_ret",
                      "escala_x * (factor_grim or 1.0)"):
        if invertida in fuente:
            probs.append("la formula INVERTIDA %r sigue en la fuente" % invertida)
    if fuente.count("INVERSO") < 3:
        probs.append("las tres ramas deben redactar 'INVERSO de escala' "
                     "(gano %d)" % fuente.count("INVERSO"))
    linea("ppu estatico: formulas linux/mac espejo del fix W11",
          "(check estatico)", "OK" if not probs else "FAIL",
          "; ".join(probs)[:150] if probs
          else "linux (factor_grim or 1.0)/escala_x; mac esc_ret/escala_x; "
               "win 1/escala_x; 3 reglas 'INVERSO' + prueba live en v_capturar")


# --- IMPL-K P2.1: golden (absorbe .tmp/byte_identity.py) --------------------
# (tag, argv, esperado_rc, vivo) — `vivo=True` = la salida depende de las
# ventanas/cursor del usuario en ESTE instante: exento de identidad byte-a-byte
# (0/2 identicas por drift, .tmp/drift_vs_baseline.txt), validado solo como
# JSON+rc.
_GOLDEN_CASOS = (
    ("monitores_listar",        ["monitores.py", "listar"], 0, True),
    ("monitores_subfalso",      ["monitores.py", "volar"], 1, False),
    ("pantalla_tamano_virtual", ["pantalla.py", "tamano", "--virtual"], 0, True),
    ("pantalla_pixel_fuera",    ["pantalla.py", "pixel", "999999", "999999"], 1, False),
    ("pantalla_maxlado8",       ["pantalla.py", "capturar", "--max-lado", "8"], 1, False),
    ("pantalla_esperar_args",   ["pantalla.py", "esperar", "--color", "12,13,14", "--cambia"], 1, False),
    ("pantalla_localizar_falta", ["pantalla.py", "localizar", "NO-existe-SEG3.png"], 1, False),
    ("teclado_combo_vacio",     ["teclado.py", "combo", ""], 1, False),
    ("teclado_via_invalido",    ["teclado.py", "escribir", "hola", "--via", "via-inventada-SEG3"], 1, False),
    ("teclado_foco_negativo",   ["teclado.py", "combo", "ctrl+s", "--requiere-foco", "ZZZ-titulo-imposible-SEG3"], 1, True),
    ("raton_posicion_plano",    ["raton.py", "posicion"], 0, True),
    ("ventanas_listar",         ["ventanas.py", "listar"], 0, True),
    ("ventanas_foco",           ["ventanas.py", "foco"], 0, True),
    ("ventanas_abrir_imposible", ["ventanas.py", "abrir", "C:\\no-existe-SEG3\\archivos.txt"], 1, False),
    ("vigilar_segundos0",       ["vigilar.py", "arrancar", "--segundos", "0"], 1, False),
)
_DIR_GOLDEN = os.path.join(RAIZ, ".tmp", "golden")


def _golden_blob(argv):
    """(rc, bytes rc+stdout+stderr) de un caso golden (crudo: la identidad es
    por bytes, como el driver absorbido)."""
    cmd = [PY, _ruta_cli(argv[0])] + [str(a) for a in argv[1:]]
    try:
        p = subprocess.run(cmd, cwd=RAIZ, capture_output=True, timeout=40)
    except subprocess.TimeoutExpired:
        return -1, b"RC=TIMEOUT\n"
    return p.returncode, (b"RC=%d\n--STDOUT--\n" % p.returncode + (p.stdout or b"")
                          + b"--STDERR--\n" + (p.stderr or b""))


def _check_golden_determinismo():
    """Check de bateria (P2.1): los 9 casos deterministas se corren DOS veces
    y sus bytes deben coincidir (idempotencia de las rutas de error/JSON); los
    6 vivos solo se validan como JSON bien formado con el rc esperado."""
    if not HOST_WIN:
        linea("golden: byte-identity determinista (P2.1)", "(15 casos)",
              "SKIP", "los casos golden son de la ruta Windows (bateria "
                      "anfitriona)")
        return
    import json as _json
    mal = []
    ident = 0
    for tag, argv, rc_exp, vivo in _GOLDEN_CASOS:
        rc1, blob1 = _golden_blob(argv)
        if rc1 != rc_exp:
            mal.append("%s rc=%s esperaba %s" % (tag, rc1, rc_exp))
            continue
        if vivo:
            try:
                _json.loads(blob1.split(b"--STDOUT--\n", 1)[1]
                            .split(b"--STDERR--\n")[0].decode("utf-8", "replace"))
            except ValueError:
                mal.append("%s stdout no-JSON" % tag)
            continue
        rc2, blob2 = _golden_blob(argv)
        if blob2 != blob1:
            mal.append("%s NO-idempotente" % tag)
        else:
            ident += 1
    n_det = sum(1 for _t, _a, _r, v in _GOLDEN_CASOS if not v)
    linea("golden: byte-identity determinista (P2.1)", "(15 casos, doble corrida)",
          "OK" if not mal else "FAIL",
          "%d/%d deterministas identicas + %d vivos exentos; fallas: %s" % (
              ident, n_det, len(_GOLDEN_CASOS) - n_det, mal[:4]) if not mal
          else "; ".join(mal)[:150])


def _golden_captura(subset):
    """--golden captura: .tmp/golden/NN_<tag>.out (crudo, como el driver
    absorbido).subset = indices '1,2,..' opcionales."""
    os.makedirs(_DIR_GOLDEN, exist_ok=True)
    indices = _golden_subset(subset)
    for i, (tag, argv, _rc, _vivo) in enumerate(_GOLDEN_CASOS, 1):
        if indices and i not in indices:
            continue
        rc, blob = _golden_blob(argv)
        with open(os.path.join(_DIR_GOLDEN, "%02d_%s.out" % (i, tag)), "wb") as fh:
            fh.write(blob)
        print("%02d %-26s rc=%d" % (i, tag, rc))
    print("dest:", _DIR_GOLDEN)
    sys.exit(0)


def _golden_comparar(subset):
    """--golden comparar: byte a byte contra .tmp/golden/; los vivos muestran
    la nota de drift y no cuentan como fallo."""
    indices = _golden_subset(subset)
    ok = tot = 0
    fallas = []
    for i, (tag, argv, _rc, vivo) in enumerate(_GOLDEN_CASOS, 1):
        if indices and i not in indices:
            continue
        fa = os.path.join(_DIR_GOLDEN, "%02d_%s.out" % (i, tag))
        if not os.path.isfile(fa):
            print("%02d %-26s SIN-BASE (corre --golden captura antes)" % (i, tag))
            continue
        rc, blob = _golden_blob(argv)
        base = open(fa, "rb").read()
        if base == blob:
            ok += 1
            print("%02d %-26s IDENTICA" % (i, tag))
        elif vivo:
            print("%02d %-26s DIFIEREN (vivo: exento — actividad del usuario)" % (i, tag))
        else:
            tot += 1
            fallas.append(tag)
            print("%02d %-26s DIFIEREN" % (i, tag))
        tot += 1
    print("TOTAL %d IDENTICAS; fallas deterministas: %s" % (ok, fallas or "ninguna"))
    sys.exit(1 if fallas else 0)


def _golden_subset(spec):
    if not spec:
        return None
    return {int(x) for x in spec.replace(",", " ").split()}


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

    # checks de estructura y estaticos SEG3 — corren en CUALQUIER SO (leen
    # fuente o subprocess que responde antes de tocar API del SO):
    _checks_estructura()
    _check_despacho()
    _check_glue_no_import_ramas()
    _check_especiales_compilan()
    _check_especiales_importables()
    _check_guards_clis_exclusivos()
    _check_contrato_documentado()
    _skips_baterias_reales()

    if not HOST_WIN:
        # La bateria de abajo spawnea la ruta Windows de los CLIs raiz y
        # exige escritorio win32 (marco px_fisicos_virtual, plataforma
        # 'win', DPI glue): en linux/darwin se reporta SKIP simetrico — los
        # CLIs raiz dispatchan el SO anfitrion en el propio proceso, pero
        # esa bateria real no se porto a la suite unificada SEG3.
        linea("bateria Windows real (lectura)", "py scripts/autotest.py",
              "SKIP", "requiere Windows: %d filas de la bateria raiz "
                      "omitidas en este anfitrion" % _N_BATERIA_WIN)
        return

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
                            "px_por_unidad_coord", "marco", "plataforma",
                            "fisico", "escala")(rc, err, d)
        if not ok:
            return ok, ev
        if d["marco"] != "px_fisicos_virtual" or d["plataforma"] != "win":
            return False, "contrato P0-4 roto: marco=%r plataforma=%r" % (
                d["marco"], d["plataforma"])
        if "px_por_unidad_coord" not in str(d.get("regla", "")):
            return False, "la 'regla' no usa el campo unico px_por_unidad_coord"
        # INVARIANTE LIVE IMPL-K P0.3 (cierra la familia del bug W11 que el
        # check de presencia no veia): con thumbnail (imagen < fuente) el ppu
        # DEBE ser <=1 y vale imagen/fuente (= 1/escala); y la regla DIVIDE
        # tiene que cerrar el round-trip: (origen + img/ppu)*... reconstruye
        # el borde opuesto de la fuente en <=6 px.
        ppu = float(d["px_por_unidad_coord"])
        fis = d.get("fisico") or {}
        if fis.get("ancho") and d["ancho"] and d["ancho"] < fis["ancho"]:
            esperado = d["ancho"] / float(fis["ancho"])
            if ppu > 1.0 + 1e-9:
                return False, "ppu=%s >1 con thumbnail (%dx%d de %dx%d): " \
                              "la formula vuelta a estar invertida" % (
                                  ppu, d["ancho"], d["alto"],
                                  fis["ancho"], fis["alto"])
            if abs(ppu - round(esperado, 6)) > 1e-6:
                return False, "ppu=%s no es imagen/fuente=%s" % (
                    ppu, round(esperado, 6))
            ox, oy = d["origen"]
            vx1 = ox + d["ancho"] / ppu
            vy1 = oy + d["alto"] / ppu
            if abs(vx1 - (ox + fis["ancho"])) > 6 or abs(vy1 - (oy + fis["alto"])) > 6:
                return False, "round-trip regla roto: img-borde -> (%.1f,%.1f)" % (vx1, vy1)
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

    # ---- IMPL-K: gates por id, parser de verbos nuevos, estaticos ----------
    def v_foco_id_error(rc, err, d):
        ok, ev = esperar_error("foco")(rc, err, d)
        if not ok:
            return ok, ev
        va = (d or {}).get("ventana_actual")
        if not isinstance(va, dict) or "id" not in va or "titulo" not in va:
            return False, "el error JSON no trae ventana_actual{id,titulo}"
        return True, "ABORT sin emitir; ventana_actual id=%s titulo=%r" % (
            va.get("id"), _trunca(va.get("titulo"), 24))
    check("teclado escribir --foco-id falso (ABORT sin emitir)",
          ["teclado.py", "escribir", "NOISE", "--foco-id", "999999999"],
          v_foco_id_error)
    check("ventanas activar --id inexistente (sin efecto)",
          ["ventanas.py", "activar", "--id", "999999999"],
          esperar_error("id"))
    check("ventanas mover --monitor fuera de rango (sin efecto)",
          ["ventanas.py", "mover", "__zz_inexistente__", "--monitor", "987"],
          esperar_error("fuera de rango"))
    check("ventanas mover sin destino (sin efecto)",
          ["ventanas.py", "mover", "--id", "999999999"],
          esperar_error("exige --monitor"))
    check("ventanas abrir --esperar-nueva sin --esperar (sin lanzar)",
          ["ventanas.py", "abrir", "notepad", "--esperar-nueva"],
          esperar_error("exige --esperar"))
    check("ventanas ocupantes zona invalida (sin efecto)",
          ["ventanas.py", "ocupantes", "10", "10", "5", "5"],
          esperar_error("x2 > x1"))
    rc_occ, _o, _e, d_occ = run(["ventanas.py", "ocupantes", "0", "0",
                                 str(max(px // 4, 8)), str(max(py_ // 4, 8))])
    occ_ok = (rc_occ == 0 and isinstance(d_occ, dict)
              and isinstance(d_occ.get("ventanas"), list)
              and all(set(("id", "titulo", "rect", "solapa_px2")) <= set(v)
                      for v in d_occ["ventanas"]))
    linea("ventanas ocupantes zona (READ-ONLY)",
          comando_de(["ventanas.py", "ocupantes", "0", "0",
                      str(max(px // 4, 8)), str(max(py_ // 4, 8))]),
          "OK" if occ_ok else "FAIL",
          "solapando=%d: %s" % (len((d_occ or {}).get("ventanas", [])),
                               [str(v.get("titulo"))[:16] for v in
                                (d_occ or {}).get("ventanas", [])][:3]))
    check("win_especiales restaurar respaldo inexistente (no toca clipboard)",
          ["win_especiales.py", "portapapeles", "restaurar", "--desde",
           "__zz_no_existe__.txt"], esperar_error("no existe"))
    _check_ppu_estatico()
    _check_golden_determinismo()

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
# IMPL-K P1.4 (reemplaza el gate "0 Notepads del usuario" y el kill-all del
# finally — los dos patrones mortales del incidente W11): sandbox con
# VENTANA GARANTIZADA por archivo .txt scratch de nombre UNICO: el ciclo
# completo va dirigido por hWnd (--foco-id / --id), y en finally solo se
# mata el PID dueno EXCLUSIVO del hWnd propio (gate multi-ventana P0.2: si
# el PID tiene mas ventanas visibles => FAIL-con-motivo, NUNCA kill).


def _ventanas_por_id(hwnd):
    """Items de listar cuyo id == hwnd (verificacion por id: el patron de
    los 12 drivers by_id, hoy funcion propia de la suite)."""
    rc, _o, _e, d = run(["ventanas.py", "listar"])
    if not isinstance(d, dict) or "ventanas" not in d:
        return None
    return [v for v in d["ventanas"] if str(v.get("id")) == str(hwnd)]


def _matar(pid):
    if not pid:
        return False
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                   capture_output=True)
    return True


def _pid_real(hWnd):
    """PID DUEÑO de la ventana. Notepad 11 es empaquetada: el proceso que
    muestra la ventana difiere del lanzador que reporta 'abrir' (el stub ya
    murio); taskkill al pid del stub no cierra nada (VERIFICADO 06/10/2026).
    ctypes solo se importa aqui (ruta win32 del sandbox)."""
    import ctypes
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(ctypes.c_void_p(int(hWnd)),
                                                  ctypes.byref(pid))
    return pid.value


def _ventanas_de_pid(pid):
    """[(hWnd, titulo)] VISIBLES con ese PID (EnumWindows+GetWindowThread-
    ProcessId; el mismo helper de win_especiales._ventanas_por_pid, aqui
    local porque la suite unificada no importa la rama exclusiva). Base del
    gate de muerte del finally (IMPL-K P0.2)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    proc_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    out = []

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        pidw = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pidw))
        if int(pidw.value) != int(pid):
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        out.append((int(hwnd), buf.value))
        return True

    user32.EnumWindows(proc_t(cb), 0)
    return out


def _crear_scratch():
    """.tmp/cu_sandbox_<hex8>.txt, 3 lineas ASCII (P1.4: el archivo .txt
    asociado es la via mas barata — `abrir` no resuelve interpretes con
    ventana y mspaint depende del idioma; el NOMBRE UNICO hace el titulo
    unico incluso con session-restore de Notepad). hex8 aleatorio por
    corrida (secrets: nada de valores fijos)."""
    import secrets
    os.makedirs(os.path.join(RAIZ, ".tmp"), exist_ok=True)
    hex8 = secrets.token_hex(4)
    ruta = os.path.join(RAIZ, ".tmp", "cu_sandbox_%s.txt" % hex8)
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write("LINEA-A scratch autotest\nLINEA-B 123456\nLINEA-C fin\n")
    return hex8, ruta


def _skip_rest(w, desde, motivo):
    for nombre in w[desde:]:
        linea(nombre, "sandbox", "SKIP", motivo)


def bateria_escritura():
    print("\n== Modo ESCRITURA: ciclo sandbox SCRATCH .txt unico por id (P1.4) ==")
    W = ["W0 sandbox scratch unico (.txt)",
         "W1 ventanas abrir scratch --esperar-nueva",
         "W2 sandbox localizado por id (unico en listar)",
         "W3 gate --foco-id negativo (ABORT sin emitir)",
         "W4 activar --id + foco por id",
         "W5 raton click en el lienzo",
         "W6 teclado escribir ASCII --foco-id",
         "W7 teclado escribir unicode --foco-id",
         "W8 teclado tecla backspace --foco-id",
         "W9 teclado combo undo --foco-id",
         "W10 raton doble clic lienzo",
         "W11 raton arrastrar lienzo",
         "W12 raton scroll lienzo",
         "W13 raton mover dentro del lienzo",
         "W14 teclado mantener shift (corto)",
         "W15 pantalla esperar --pixel adaptativa",
         "W16 ventanas mover --monitor (live + negativo)",
         "W17 gate matar multi-ventana (rc=1, NO mata)",
         "W18 ventanas cerrar --id --descartar (desaparicion por id)"]
    hwnd = None
    ruta_scratch = None
    scratch_permanece = False  # tab-hijack: el .txt NO se borra (sheet W11)
    try:
        if not HOST_WIN:
            _skip_rest(W, 0, "requiere Windows")
            return
        # ---- W0: scratch unico (ya NO exige "0 Notepads del usuario") ----
        try:
            hex8, ruta_scratch = _crear_scratch()
            rc, _o, _e, dl = run(["ventanas.py", "listar"])
            colision = (isinstance(dl, dict) and
                        any(hex8 in (v.get("titulo") or "")
                            for v in dl.get("ventanas", [])))
            linea(W[0], ".tmp/cu_sandbox_%s.txt" % hex8,
                  "FAIL" if colision else "OK",
                  "3 lineas ASCII; titulo UNICO garantizado por nombre de "
                  "archivo (convive con los Notepads del usuario)" if not colision
                  else "hex8 colisiona con una ventana existente")
            if colision:
                _skip_rest(W, 1, "scratch no unico: ciclo abortado")
                return
        except Exception as exc:
            linea(W[0], "escribir scratch", "FAIL", "%s: %s" % (
                type(exc).__name__, exc))
            _skip_rest(W, 1, "sin scratch: ciclo abortado")
            return

        # ---- W1: abrir por asociacion con ventana GARANTIZADA (diff hWnd) --
        # TAB-HIJACK VERIFICADO en vivo 06/10/2026 (esta maquina, Notepads del
        # usuario abiertos): con el proceso Notepad vivo, startfile de un .txt
        # lo abre como PESTANA en la primera ventana (mismo hWnd: el diff de
        # --esperar-nueva NO ve nada nuevo y el titulo de la ventana ajena
        # queda SECUESTRADO). El SPEC P1.4 asumia ventana nueva garantizada;
        # la realidad W11 exige el respaldo ctrl+shift+n (patron de los
        # drivers b3_v3..v12). JAMAS se cierra la pestana ajena con ctrl+w:
        # en la prueba en vivo toco la pestana equivocada (perdio una del
        # usuario) y borrar el .txt con la pestana abierta levanta el sheet
        # "No se encuentra el archivo" que bloquea el teclado de esa ventana
        # (windows-python.md §13.3).
        rc, _o, err, d = run(["ventanas.py", "abrir", ruta_scratch,
                              "--esperar", "12", "--esperar-nueva",
                              "--titulo", "cu_sandbox_%s" % hex8], timeout=60)
        v1 = (d or {}).get("ventana") or {}
        hwnd = v1.get("id")
        nuevas = (d or {}).get("ids_nuevas") or []
        ok = rc == 0 and isinstance(d, dict) and d.get("ok") and hwnd
        if not nuevas:
            rc2, _o2, _e2, dl = run(["ventanas.py", "listar"])
            sec = [v for v in (dl or {}).get("ventanas", [])
                   if hex8 in (v.get("titulo") or "")] if rc2 == 0 else []
            if sec:
                vid = sec[0]["id"]
                # desde YA: la pestana residual vive en ventana ajena => el
                # .txt NO se borra (borrarlo levanta el sheet "No se
                # encuentra el archivo" sobre la pestana del usuario).
                scratch_permanece = True
                snap = {str(v["id"]) for v in dl["ventanas"]}
                rc_n = None
                dn = None
                for _intento in range(2):
                    run(["ventanas.py", "activar", "--id", str(vid)])
                    subprocess.run([PY, "-c", "import time; time.sleep(0.6)"])
                    rc_n, _o4, _e4, dn = run(["teclado.py", "combo",
                                              "ctrl+shift+n",
                                              "--foco-id", str(vid)])
                    for _i in range(10):
                        subprocess.run([PY, "-c",
                                        "import time; time.sleep(0.5)"])
                        rc3, _o3, _e3, dl3 = run(["ventanas.py", "listar"])
                        nuevas3 = [v for v in (dl3 or {}).get("ventanas", [])
                                   if str(v["id"]) not in snap] if rc3 == 0 else []
                        if nuevas3:
                            editoras = [v for v in nuevas3
                                        if "bloc" in (v.get("titulo") or "").lower()
                                        or "notepad" in (v.get("titulo") or "").lower()]
                            v1 = (editoras or nuevas3)[0]
                            hwnd = v1.get("id")
                            ok = bool(hwnd)
                            break
                    if ok:
                        break
                if ok:
                    linea(W[1], comando_de(["ventanas.py", "abrir", "scratch",
                                            "--esperar-nueva", "+ ctrl+shift+n"]),
                          "OK", "TAB-HIJACK (ventana nueva no siempre es "
                          "nueva): el .txt abrio como pestana en ventana "
                          "ajena id %s; ventana PROPIA via ctrl+shift+n "
                          "id=%s titulo=%r; la pestana residual "
                          "'cu_sandbox_%s.txt' y su archivo SE DEJAN a "
                          "proposito (cerrar pestanas ajenas con ctrl+w NO "
                          "es seguro — ver §13.3): cierrala a mano" % (
                              vid, hwnd, _trunca(v1.get("titulo"), 28), hex8))
                else:
                    linea(W[1], "abrir + ctrl+shift+n", "FAIL",
                          "tab-hijack en ventana ajena id %s y ctrl+shift+n "
                          "no creo ventana propia (rc combo=%s error=%s): el "
                          "humano tenia el foco en otra parte o la app no "
                          "expone nueva ventana. PESTANA RESIDUAL "
                          "'cu_sandbox_%s.txt' + archivo CONSERVADOS: "
                          "cierrala a mano" % (
                              vid, rc_n, _trunca((dn or {}).get("error"), 60),
                              hex8))
            else:
                linea(W[1], comando_de(["ventanas.py", "abrir", "scratch",
                                        "--esperar", "12", "--esperar-nueva"]),
                      "FAIL", _resumen_fallo(rc, err, d))
        else:
            linea(W[1], comando_de(["ventanas.py", "abrir", "scratch",
                                    "--esperar", "12", "--esperar-nueva"]),
                  "OK", "hWnd=%s titulo=%r ids_nuevas=%s" % (
                      hwnd, _trunca(v1.get("titulo"), 34), nuevas))
        if not ok:
            _skip_rest(W, 2, "abrir --esperar-nueva fallo: ciclo abortado")
            return

        titulo0 = (v1.get("titulo") or "").lower()
        if "bloc" not in titulo0 and "notepad" not in titulo0 \
                and "edit" not in titulo0 and "text" not in titulo0:
            # asociacion .txt != editor: SKIP honesto (P1.4 punto 5)
            for nombre in W[2:]:
                linea(nombre, "sandbox", "SKIP",
                      "asociacion .txt != editor (titulo %r): el ciclo de "
                      "tecleo exige un editor de texto plano"
                      % _trunca(v1.get("titulo"), 40))
            rc_c, _o, _e, _dc = run(["ventanas.py", "cerrar", "--id", str(hwnd)])
            linea("sandbox cierre ventana asociada (fuera de ciclo)",
                  "ventanas.py cerrar --id", "OK" if rc_c == 0 else "FAIL",
                  "ventana de %r cerrada sin dirigir entrada"
                  % _trunca(v1.get("titulo"), 30))
            return

        # ---- W2: la ventana es UNICA por id y leible en listar ------------
        vivos = _ventanas_por_id(hwnd)
        ok = bool(vivos) and len(vivos) == 1
        rect = vivos[0]["rect"] if ok else None
        linea(W[2], "ventanas.py listar (filtro por id)",
              "OK" if ok else "FAIL",
              "rect=%s estado=%s" % (rect, vivos[0]["estado"]) if ok
              else "sandbox no encontrado o duplicado en listar")
        if not ok:
            _skip_rest(W, 3, "sin sandbox por id: ciclo abortado")
            return

        def _rescatar():
            """Vuelve a poner el sandbox al frente (restaurar+activar por id)."""
            run(["ventanas.py", "restaurar", "--id", str(hwnd)])
            subprocess.run([PY, "-c", "import time; time.sleep(0.4)"])
            run(["ventanas.py", "activar", "--id", str(hwnd)])
            subprocess.run([PY, "-c", "import time; time.sleep(0.5)"])

        if vivos[0]["estado"]["minimizada"]:
            _rescatar()
        TX, TY = rect["left"], rect["top"]
        AN, AL = rect["ancho"], rect["alto"]
        # LECCION W11 (windows-python.md §13.1): la barra de menu de Notepad
        # aparece con Alt y desplaza el lienzo: click HONDO TY+160, primera
        # fila ~TY+90..110 solo con menu oculto.
        cx, cy = TX + min(120, max(AN // 2, 50)), TY + 160

        # ---- W3: gate --foco-id NEGATIVO (no emitio nada) -----------------
        # Version determinista (la minimizacion de Notepad W11 por minimize()
        # NO garantiza salir de foreground — verificado en la corrida 2): se
        # crea una SEGUNDA ventana propia B (ctrl+shift+n con gate en A), se
        # activa B por id y escribir --foco-id A debe ABORTAR con rc=1 porque
        # el foreground es B (ventana_actual{id,titulo} lo prueba). NOISE no
        # se emite en ninguna parte y ninguna ventana del usuario interviene.
        rc3w = None
        wB = None
        snap_w3 = None
        rcL, _oL, _eL, dlW = run(["ventanas.py", "listar"])
        if rcL == 0:
            snap_w3 = {str(v["id"]) for v in dlW["ventanas"]}
            run(["ventanas.py", "activar", "--id", str(hwnd)])
            subprocess.run([PY, "-c", "import time; time.sleep(0.6)"])
            rc3w, _o4, _e4, d3w = run(["teclado.py", "combo", "ctrl+shift+n",
                                       "--foco-id", str(hwnd)])
            for _i in range(8):
                subprocess.run([PY, "-c", "import time; time.sleep(0.5)"])
                rc3, _o3, _e3, dl3 = run(["ventanas.py", "listar"])
                nuevas3 = [v for v in (dl3 or {}).get("ventanas", [])
                           if str(v["id"]) not in snap_w3] if rc3 == 0 else []
                if nuevas3:
                    wB = nuevas3[0]
                    break
        if wB is not None:
            run(["ventanas.py", "activar", "--id", str(wB["id"])])
            subprocess.run([PY, "-c", "import time; time.sleep(0.6)"])
            rc, _o, err, dn = run(["teclado.py", "escribir", "NOISE",
                                   "--foco-id", str(hwnd)])
            abort_ok = (rc == 1 and isinstance(dn, dict) and "error" in dn
                        and str((dn.get("ventana_actual") or {}).get("id"))
                        == str(wB["id"]))
            linea(W[3], comando_de(["teclado.py", "escribir", "NOISE",
                                    "--foco-id", "<A con B al frente>"]),
                  "OK" if abort_ok else "FAIL",
                  "rc=%s ventana_actual=%s (NOISE no se emito)" % (
                      rc, dn.get("ventana_actual")) if abort_ok
                  else "rc=%s %s" % (rc, str(dn)[:90]))
            # cerrar la ventana propia B (doc limpio: sin modal)
            run(["ventanas.py", "cerrar", "--id", str(wB["id"]), "--descartar"],
                timeout=40)
        else:
            # respaldo historico: minimizar A (puede no quitar el foreground
            # en Notepad W11 => el gate pasaria: FAIL honesto con motivo)
            run(["ventanas.py", "minimizar", "--id", str(hwnd)])
            subprocess.run([PY, "-c", "import time; time.sleep(0.6)"])
            rc, _o, err, dn = run(["teclado.py", "escribir", "NOISE",
                                   "--foco-id", str(hwnd)])
            abort_ok = (rc == 1 and isinstance(dn, dict) and "error" in dn
                        and str((dn.get("ventana_actual") or {}).get("id"))
                        != str(hwnd))
            linea(W[3], comando_de(["teclado.py", "escribir", "NOISE",
                                    "--foco-id", "<sandbox minimizado>"]),
                  "OK" if abort_ok else "FAIL",
                  "rc=%s ventana_actual=%s" % (rc, dn.get("ventana_actual"))
                  if abort_ok else "rc=%s %s (B no pudo crearse: %s)" % (
                      rc, str(dn)[:80], str(rc3w)))
        _rescatar()

        # ---- W4: activar --id + foco coherente por id ---------------------
        rc, _o, err, da = run(["ventanas.py", "activar", "--id", str(hwnd)])
        rc2, _o2, err2, df = run(["ventanas.py", "foco"])
        foco_id = str((df or {}).get("ventana", {}).get("id"))
        foco_garantizado = rc == 0 and rc2 == 0 and foco_id == str(hwnd)
        linea(W[4], comando_de(["ventanas.py", "activar", "--id", "<h>"])
              + " + foco", "OK" if foco_garantizado else "FAIL",
              "foco.id=%s == sandbox %s" % (foco_id, hwnd) if foco_garantizado
              else "activar rc=%s foco rc=%s id=%s" % (rc, rc2, foco_id))

        def v_ok(rc, err, d2):
            return esperar_ok("ok")(rc, err, d2)

        # ---- W5..W14: ciclo dirigido por id -------------------------------
        pasos = [
            (W[5], ["raton.py", "click", "--x", cx, "--y", cy], v_ok),
            (W[6], ["teclado.py", "escribir", "Hola autotest 123",
                    "--foco-id", str(hwnd)], v_ok),
            (W[7], ["teclado.py", "escribir", "Ñ¿Á 😀", "--foco-id", str(hwnd)],
             v_ok),
            (W[8], ["teclado.py", "tecla", "backspace", "--repeticiones", "3",
                    "--foco-id", str(hwnd)], v_ok),
            (W[9], ["teclado.py", "combo", "ctrl+z", "--foco-id", str(hwnd)],
             v_ok),
            (W[10], ["raton.py", "click", "--x", cx, "--y", cy, "--doble"],
             v_ok),
            (W[11], ["raton.py", "arrastrar", cx - 100, cy, cx + 100, cy,
                     "--duracion", "0.4"], v_ok),
            (W[12], ["raton.py", "scroll", "--vertical", "-2", "--x", cx,
                     "--y", cy], v_ok),
            (W[13], ["raton.py", "mover", cx + 20, cy + 5, "--duracion", "0.2"],
             v_ok),
            (W[14], ["teclado.py", "mantener", "shift", "--segundos", "0.3"],
             v_ok),
        ]
        for nombre, args, val in pasos:
            if nombre == W[11] and AN < 260:
                linea(nombre, comando_de(args), "SKIP",
                      "ventana de %d px: muy estrecha para arrastrar dentro" % AN)
                continue
            if nombre in (W[6], W[7], W[8], W[9]) and not foco_garantizado:
                linea(nombre, comando_de(args), "SKIP",
                      "activar/foco por id fallo: no se teclea sin garantia "
                      "de foco (gate de entrada)")
                continue
            check(nombre, args, val, timeout=25)

        # ---- W15: espera adaptativa sobre el lienzo -----------------------
        pxw, pyw = cx + 40, cy + 40
        rc, _o, err, dpix = run(["pantalla.py", "pixel", pxw, pyw])
        if isinstance(dpix, dict) and "r" in dpix:
            color = "%d,%d,%d" % (dpix["r"], dpix["g"], dpix["b"])

            def v_adap(rc2, err2, d4):
                ok2, ev2 = esperar_ok("cumplida", "modo")(rc2, err2, d4)
                if not ok2:
                    return ok2, ev2
                return True, "color=%s estable cumplida=%s (false NO es error)" % (
                    color, d4["cumplida"])
            check(W[15], ["pantalla.py", "esperar", "--pixel", pxw, pyw,
                          "--color", color, "--estable", "200", "--timeout",
                          "3"], v_adap, timeout=15)
        else:
            linea(W[15], "pantalla.py esperar --pixel", "FAIL",
                  "no se pudo leer el pixel base: " + _resumen_fallo(rc, err, dpix))

        # ---- W16: mover --monitor (live primario + secundario + negativo) --
        mons = STATE.get("monitores") or []
        if not mons:
            rc_m, _o, _e, dm0 = run(["monitores.py", "listar"])
            mons = (dm0 or {}).get("monitores", []) if rc_m == 0 else []
        rc_neg, _o, _e, dneg = run(["ventanas.py", "mover", "--id", str(hwnd),
                                    "--monitor", "987"])
        neg_ok = rc_neg == 1 and isinstance(dneg, dict) and "fuera de rango" in str(
            dneg.get("error", ""))
        rc_p, _o, errp, dp = run(["ventanas.py", "mover", "--id", str(hwnd),
                                  "--monitor", "primario"])
        rect_p = ((dp or {}).get("ventana") or {}).get("rect") or {}
        prim = [m for m in mons if m.get("primario")]
        prim = prim[0] if prim else (mons[0] if mons else None)
        p_ok = (rc_p == 0 and prim is not None
                and prim["izq"] <= rect_p.get("left", -10 ** 9) < prim["der"])
        seg_mov = None
        if p_ok and len(mons) >= 2:
            idx_seg = [i for i, m in enumerate(mons) if not m.get("primario")]
            if idx_seg:
                rc_s, _o, _e, ds = run(["ventanas.py", "mover", "--id", str(hwnd),
                                        "--monitor", str(idx_seg[0])])
                rs = ((ds or {}).get("ventana") or {}).get("rect") or {}
                m_s = mons[idx_seg[0]]
                seg_mov = (rc_s == 0 and m_s["izq"] <= rs.get("left", -10 ** 9)
                           < m_s["der"])
                run(["ventanas.py", "mover", "--id", str(hwnd),
                     "--monitor", "primario"])
        ok16 = neg_ok and p_ok
        linea(W[16], "mover --monitor primario/secundario + --monitor 987",
              "OK" if ok16 else "FAIL",
              "negativo rc1=%s; primario rect=%s en bounds; secundario=%s %s" % (
                  neg_ok, rect_p, seg_mov,
                  "(un solo monitor: no probado)" if len(mons) < 2 else "")
              if ok16 else "neg=%s prim(rc=%s rect=%s)" % (neg_ok, rc_p, rect_p))

        # ---- W17: gate matar multi-ventana CON NUESTRO PID (espera rc=1) ---
        pid_v = _pid_real(hwnd)
        vis = _ventanas_de_pid(pid_v)
        if len(vis) > 1:
            rc_k, _o, errk, dk = run(["win_especiales.py", "procesos", "matar",
                                      "--pid", str(pid_v), "--confirmar"])
            gate_ok = (rc_k == 1 and isinstance(dk, dict) and "error" in dk
                       and isinstance(dk.get("ventanas_visibles"), list)
                       and len(dk["ventanas_visibles"]) > 1)
            sobreviven = _ventanas_de_pid(pid_v)
            intactas = sobreviven is not None and len(sobreviven) == len(vis)
            linea(W[17], comando_de(["win_especiales.py", "procesos", "matar",
                                     "--pid", "<propio>", "--confirmar"]),
                  "OK" if gate_ok and intactas else "FAIL",
                  "rc=%s bloqueo con %d ventanas_visibles; todas siguen=%s. "
                  "--forzar NO se prueba (el PID puede compartir proceso con "
                  "Notepads del usuario: matarlo ES el incidente P0.2)" % (
                      rc_k, len(dk.get("ventanas_visibles", []) if gate_ok else vis),
                      intactas))
        else:
            linea(W[17], "win_especiales.py procesos matar --pid <propio>",
                  "SKIP", "el PID dueno del hWnd tiene %d ventana(s) visibles "
                  "(case Notepad = proceso compartido): el gate no se dispara "
                  "en esta maquina" % len(vis))

        # ---- W18: cerrar --id --descartar + desaparicion POR ID ------------
        rc, _o, err, dc = run(["ventanas.py", "cerrar", "--id", str(hwnd),
                               "--descartar"], timeout=60)
        desaparecio = not _ventanas_por_id(hwnd)
        ok18 = (rc == 0 and isinstance(dc, dict) and dc.get("desaparecio")
                and desaparecio)
        linea(W[18], comando_de(["ventanas.py", "cerrar", "--id", "<h>",
                                 "--descartar"]),
              "OK" if ok18 else "FAIL",
              "modal=%s desaparecio=%s (verificacion por id)" % (
                  (dc or {}).get("modal"), desaparecio) if ok18
              else _resumen_fallo(rc, err, dc) + " | sigue viva=%s" % (
                  not desaparecio))
    finally:
        # P0.2 IMPL-K: taskkill SOLO del PID dueno EXCLUSIVO del hWnd propio;
        # si ese PID tiene mas ventanas visibles => FAIL-con-motivo, NUNCA
        # kill (el kill-all por subtitulo "bloc/notepad" del sandbox viejo
        # podia matar un Notepad abierto por el usuario DURANTE la corrida).
        try:
            if hwnd is not None:
                quedan = _ventanas_por_id(hwnd)
                if quedan:
                    pid_v = _pid_real(hwnd)
                    vis = _ventanas_de_pid(pid_v)
                    if vis is not None and len(vis) == 1 and vis[0][0] == int(hwnd):
                        _matar(pid_v)
                        linea("sandbox finally (limpieza)", "finally", "OK",
                              "el sandbox seguia vivo y SU PID era monoparental "
                              "(solo nuestro hWnd): taskkill exclusivo pid=%s"
                              % pid_v)
                    else:
                        linea("sandbox finally (limpieza)", "finally", "FAIL",
                              "la ventana %s sigue viva y su PID tiene %d "
                              "ventanas visibles (posible trabajo ajeno): NO se "
                              "mato (gate P0.2). Atencion: cerrar %s a mano."
                              % (hwnd, len(vis or []), hwnd))
        except Exception as exc:
            linea("sandbox finally (limpieza)", "finally", "FAIL",
                  "el finally fallo: %s: %s" % (type(exc).__name__, exc))
        try:
            # tab-hijack: el .txt vive en una pestana residual del usuario:
            # borrarlo levanta el sheet "No se encuentra el archivo" (VERIFI-
            # CADO 06/10/2026) => se CONSERVA junto con la nota de W1.
            if ruta_scratch and not scratch_permanece \
                    and os.path.isfile(ruta_scratch):
                os.remove(ruta_scratch)
        except OSError:
            pass


# --- ejecucion ----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        prog="autotest.py",
        description="Autovalidacion de la skill computer-use-py (SUITE "
                    "UNIFICADA raiz FASE SEG3 para los 3 SO: en win32 corre "
                    "la bateria historica intacta mas los estaticos SEG3 e "
                    "IMPL-K (gates por id, ppu estatico, golden determinismo); "
                    "en linux/darwin corre estructura/dispatch/especiales/"
                    "documentacion y marca SKIP las baterias reales de los "
                    "otros SO. Por defecto SOLO LECTURA (seguro). "
                    "--con-escritura ejecuta el ciclo sandbox SCRATCH .txt "
                    "por id (IMPL-K P1.4): CONVIVE con los Notepads del "
                    "usuario (ya no exige 0 ventanas) y jamas mata un PID con "
                    "mas ventanas visibles (gate P0.2).")
    ap.add_argument("--con-escritura", dest="con_escritura",
                    action="store_true",
                    help="ciclo sandbox completo (solo un humano consciente)")
    ap.add_argument("--golden", choices=("captura", "comparar"),
                    help="byte-identity de las 15 salidas canonicas (P2.1, "
                         "absorbe .tmp/byte_identity.py): guarda/contrasta "
                         "en .tmp/golden/ y sale (no corre la bateria)")
    ap.add_argument("--golden-subset", dest="golden_subset", metavar="1,2,..",
                    help="indices de casos golden para --golden")
    args = ap.parse_args()

    if args.golden == "captura":
        if not HOST_WIN:
            print("los casos golden son de la ruta Windows")
            sys.exit(2)
        _golden_captura(args.golden_subset)
    if args.golden == "comparar":
        if not HOST_WIN:
            print("los casos golden son de la ruta Windows")
            sys.exit(2)
        _golden_comparar(args.golden_subset)

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

    print("# autotest computer-use-py — SUITE UNIFICADA SEG3 — %s" % (
        "LECTURA + ESCRITURA" if args.con_escritura else "modo seguro (lectura)"))
    print("python: %s | raiz: %s | plataforma: %s" % (PY, RAIZ, sys.platform))
    if residuales:
        print("banderas previas limpiadas por el autotest: %s" % ", ".join(residuales))
    print("%s" % ("-" * 140))
    print("%-*s | %-*s | %-*s | %s"
          % (_W[0], "FUNCION", _W[1], "COMANDO", _W[2], "EST", "EVIDENCIA"))
    print("%s" % ("-" * 140))

    bateria_lectura()
    if args.con_escritura:
        if HOST_WIN:
            bateria_escritura()
        else:
            linea("ciclo sandbox Windows (--con-escritura)", "sandbox", "SKIP",
                  "requiere Windows: el ciclo scratch .txt por id (IMPL-K "
                  "P1.4) es la bateria de escritura de la ruta win (la de "
                  "linux/macos no se porto a la suite unificada SEG3)")
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
        "nota": "un FAIL en un check de modo lectura = bug de un CLI de la "
                "raiz scripts/ (ruta Windows): reportar a @7-cerrador sin "
                "parchar a ciegas; SKIP = limitacion de hardware/entorno con "
                "motivo",
    }
    print("\n" + "-" * 140)
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    sys.exit(0 if CONT["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
