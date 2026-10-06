# -*- coding: utf-8 -*-
"""win_especiales.py — Funciones EXCLUSIVAS de Windows (skill computer-use-py).

Unico archivo que queda en scripts/windows/ (FASE SEG2): el resto del flujo,
incluido este CLI en Windows, pasa por los CLIs de scripts/ raiz. Entregable de
la SECCION 4 del SPEC de integracion: lo unicamente-ventana/proceso/
portapapeles/DPI de Windows que NO es alcanzable con los scripts actuales de la
skill. Todo responde el JSON canonico de la skill (plataforma/marco incluidos
via glue_windows) y los errores son SIEMPRE JSON (nunca stderr de argparse).
Guard de plataforma: en Linux/macOS sale JSON "exclusivo WINDOWS; el resto del
flujo usa scripts/" con exit 2 (importa glue_windows antes que cualquier
wintypes, para que el guard responda JSON y no un traceback de import).

Verbos (y por que no existen hoy, segun el spec):
  portapapeles   teclado.py --via portapapeles solo COPIA+PEGABA y destruia el
                 contenido del usuario: aqui hay LEER (unico verbo que lee),
                 ESCRIBIR con --respaldar (backup en .tmp) y ESTADO sin exponer
                 el contenido. NUNCA se imprime texto del portapapeles salvo
                 `leer` explicito.
  procesos       ventanas.py lista VENTANAS y `cerrar` es graceful-close; aqui
                 tasklist/taskkill por PID con gate --confirmar (tarea real:
                 "cierra la app colgada"). Se rechaza el propio PID.
  ejecutar       ventanas.py abrir lanza SIN elevacion; --elevado usa
                 ShellExecuteW "runas" (UAC). Ojo (SKILL 1): elevar una app no
                 permite seguir inyectandole teclas desde este proceso NO
                 elevado.
  dpi            _compartido solo FIJA el awareness; aqui se CONSULTA
                 GetDpiForMonitor por monitor (complementa monitores.py listar).

Rutas paralelas documentadas (no interferir):
  - `teclado.py escribir --via portapapeles` = copia+pega en un solo paso
    (destruye el portapapeles). `win_especiales.py portapapeles escribir` es
    otro camino: escribe y (opcional) respalda; solo pega si se pasa --pegar
    (que reutiliza teclado.py combo ctrl+v, sin duplicar la emision).

Subcomandos:
  portapapeles leer     [--formato auto|text]
  portapapeles escribir "TEXTO" [--respaldar] [--pegar]
  portapapeles estado
  procesos listar       [--nombre X] [--con-ventana]
  procesos matar        --pid N [--arbol] [--forzar] --confirmar
  ejecutar              "OBJ" [--args ...] [--elevado] [--dir D]
  dpi listar

Ejemplos (desde la carpeta computer-use-py):
  py scripts/windows/win_especiales.py portapapeles estado
  py scripts/windows/win_especiales.py portapapeles escribir "hola" --respaldar
  py scripts/windows/win_especiales.py procesos listar --nombre notepad.exe --con-ventana
  py scripts/windows/win_especiales.py procesos matar --pid 4321 --confirmar
  py scripts/windows/win_especiales.py ejecutar notepad --elevado
  py scripts/windows/win_especiales.py dpi listar
"""

import argparse
import csv
import io
import os
import re
import shutil
import subprocess
import sys

# El glue WINDOWS vive en scripts/ (padre de esta rama): se importa ANTES que
# ctypes.wintypes (exclusivo win32) para que en otro SO responda el guard JSON
# con rc 2 y no un traceback de import.
_DIR_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _DIR_SCRIPTS not in sys.path:
    sys.path.insert(0, _DIR_SCRIPTS)
import glue_windows as c  # guard de plataforma + JSON canonico + Parser + monitores()

import ctypes
from ctypes import wintypes

_ESQUEMA_URL = c.ESQUEMA_URL  # clasificador URL generico (vive en _core)


# --- portapapeles -------------------------------------------------------------

def _clipboard_actual():
    """Contenido texto del portapapeles ('' si vacio/no-texto), o error JSON.

    pyperclip es la dependencia ya instalada de la skill; si falla (bloqueo
    transitorio del clipboard), respaldo propio con ctypes OpenClipboard/
    GetClipboardTextW (CF_UNICODETEXT)."""
    try:
        import pyperclip

        return pyperclip.paste()
    except Exception:
        return _clipboard_ctypes()


def _clipboard_ctypes():
    """Lectura CF_UNICODETEXT por user32 (fallback sin pyperclip)."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    if not user32.OpenClipboard(None):
        c.fail("OpenClipboard fallo (portapapeles ocupado u otra sesion): %s"
               % ctypes.WinError())
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        p = kernel32.GlobalLock(h)
        if not p:
            return ""
        try:
            return ctypes.wstring_at(p)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def _clipboard_escribir(texto):
    try:
        import pyperclip

        pyperclip.copy(texto)
    except Exception:
        _clipboard_escribir_ctypes(texto)


def _clipboard_escribir_ctypes(texto):
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    data = (texto + "\0").encode("utf-16-le")
    if not user32.OpenClipboard(None):
        c.fail("OpenClipboard fallo al escribir: %s" % ctypes.WinError())
    try:
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            c.fail("GlobalAlloc fallo: %s" % ctypes.WinError())
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            c.fail("SetClipboardData fallo: %s" % ctypes.WinError())
    finally:
        user32.CloseClipboard()


def cmd_portapapeles_leer(args):
    if args.formato not in ("auto", "text"):
        c.fail("--formato %r invalido." % args.formato,
               validos=["auto", "text"])
    texto = _clipboard_actual()
    if not texto:
        c.json_out({"ok": True, "formato": None, "texto": None, "largo": 0,
                    "nota": "portapapeles vacio o sin formato texto "
                            "(CF_UNICODETEXT ausente)"})
        return
    c.json_out({"ok": True, "formato": "text", "texto": texto,
                "largo": len(texto)})


def cmd_portapapeles_estado(args):
    texto = _clipboard_actual()
    c.json_out({"ok": True, "tiene_texto": bool(texto),
                "largo": len(texto) if texto else 0,
                "nota": "estado sin exponer el contenido (usa `leer` para eso)"})


def cmd_portapapeles_escribir(args):
    backup = None
    prev = None
    if args.respaldar:
        prev = _clipboard_actual()
        ruta = os.path.join(c.DIR_TMP, "clipboard_backup.txt")
        try:
            # SEG2 G1.4: el respaldo exige DIR_TMP exista (la skill puede
            # arrancar con .tmp/ casi vacia: los demas writes ya usan makedirs).
            os.makedirs(c.DIR_TMP, exist_ok=True)
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write(prev if prev is not None else "")
            backup = ruta
        except OSError as exc:
            c.fail("No se pudo escribir el respaldo del portapapeles: %s" % exc)
    _clipboard_escribir(args.texto)
    pegado = False
    pegado_rc = None
    if args.pegar:
        # Reutiliza ctrl+v de teclado.py (ruta unica de emision de combos).
        pegado_rc = _teclado_combo("ctrl+v")
        pegado = pegado_rc == 0
    c.json_out({
        "ok": True,
        "escrito_chars": len(args.texto),
        "respaldado": args.respaldar,
        "backup": backup,
        "backup_vacio": bool(args.respaldar) and not prev,
        "pegado": pegado,
        "pegado_rc": pegado_rc,
        "nota": "para RESTAURAR el contenido previo: portapapeles escribir "
                "<contenido del backup> (leelo con `portapapeles leer` o desde "
                "la ruta de 'backup'); `--pegar` exige el foco correcto de la "
                "app destino (verifica con pantalla.py capturar)",
    })


def _teclado_combo(combo):
    """ctrl+v via teclado.py (CLI de la raiz scripts/, subproceso con cwd raiz
    de la skill). Devuelve rc. En win32 teclado.py ejecuta su ruta nativa."""
    ruta = os.path.join(c.RAIZ_SKILL, "scripts", "teclado.py")
    try:
        p = subprocess.run(
            [sys.executable, ruta, "combo", combo],
            cwd=c.RAIZ_SKILL, capture_output=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return p.returncode
    except Exception as exc:
        c.fail("No se pudo lanzar teclado.py para pegar: %s: %s"
               % (type(exc).__name__, exc))


# --- procesos ---------------------------------------------------------------

def _tasklist(filto=None):
    """tasklist /FO CSV /NH -> filas parseadas; error JSON si el binario falla."""
    cmd = ["tasklist", "/FO", "CSV", "/NH"]
    if filto:
        cmd += ["/FI", filto]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except FileNotFoundError:
        c.fail("tasklist no esta en PATH (no es Windows util).")
    except Exception as exc:
        c.fail("tasklist fallo: %s: %s" % (type(exc).__name__, exc))
    texto = (p.stdout or b"").decode("utf-8", "replace") if p.returncode == 0 else ""
    filas = []
    for row in csv.reader(io.StringIO(texto)):
        if len(row) >= 5:
            filas.append(row)
    if p.returncode != 0:
        c.fail("tasklist rc=%s: %s" % (p.returncode, (p.stderr or b"").decode(
            "utf-8", "replace").strip()[:200]))
    return filas


def _mem_a_mb(valor):
    """'4,156 K' / '11.468 KB' / '0 K' -> MB float (o None si no parsea).

    locale-agnostico: se quedan solo los digitos (tasklist no usa decimales)
    y se exige que lleve unidad K/KB; el separador de miles (.,) varia con la
    config regional (verificado: 'X K' en en-US, 'X.XXX KB' en es-ES)."""
    v = valor.strip()
    if not re.search(r"\s*KB?\s*$", v, re.IGNORECASE):
        return None
    digitos = re.sub(r"[^0-9]", "", v)
    if not digitos:
        return None
    return round(int(digitos) / 1024.0, 1)


def _ventanas_por_pid():
    """{pid: [titulos visibles]} con EnumWindows+GetWindowThreadProcessId
    (pygetwindow 0.0.9 no expone pid: esta es la via win32 directa)."""
    user32 = ctypes.windll.user32
    proc_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    out = {}

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        out.setdefault(int(pid.value), []).append(buf.value)
        return True

    user32.EnumWindows(proc_t(cb), 0)
    return out


def cmd_procesos_listar(args):
    filto = ('IMAGENAME eq %s' % args.nombre) if args.nombre else None
    filas = _tasklist(filto)
    por_pid = _ventanas_por_pid() if args.con_ventana else {}
    procesos = []
    for row in filas:
        # columnas verificadas de tasklist /FO CSV: nombre, pid, sesion, num, mem
        pid = int(row[1]) if row[1].isdigit() else None
        item = {
            "nombre": row[0],
            "pid": pid,
            "sesion": row[2],
            "mem_mb": _mem_a_mb(row[4]),
        }
        if args.con_ventana:
            item["ventana"] = por_pid.get(pid) or None
        procesos.append(item)
    c.json_out({
        "ok": True,
        "total": len(procesos),
        "procesos": procesos,
        "nota": "mem_mb aproximado (tasklist informa working set en K); "
                "'ventana' via EnumWindows por pid (solo titulos visibles)",
    })


def cmd_procesos_matar(args):
    if not args.confirmar:
        c.fail("matar procesos es IRREVERSIBLE: exige --confirmar explicito "
               "(el agente debe pedir OK humano antes de pasarlo).")
    if args.pid <= 0:
        c.fail("--pid debe ser un entero positivo (recibido %r)." % args.pid)
    if args.pid == os.getpid():
        c.fail("No se puede matar el propio PID del script (%d)." % args.pid)
    existe = [r for r in _tasklist('PID eq %d' % args.pid)
              if len(r) > 1 and r[1] == str(args.pid)]
    if not existe:
        c.fail("No existe ningun proceso con PID %d (tasklist no lo encuentra)."
               % args.pid, procesado=False)
    cmd = ["taskkill", "/PID", str(args.pid)]
    if args.arbol:
        cmd.append("/T")
    if args.forzar:
        cmd.append("/F")
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as exc:
        c.fail("taskkill no pudo ejecutarse: %s: %s"
               % (type(exc).__name__, exc))
    salida = ((p.stdout or b"").decode("utf-8", "replace") + " " +
              (p.stderr or b"").decode("utf-8", "replace")).strip()
    if p.returncode != 0:
        c.fail("taskkill rc=%s sobre PID %d: %s"
               % (p.returncode, args.pid, salida[:300]),
               nota="si es 'access denied': la app corre con mas privilegios "
                    "que este proceso (relanzar elevado no es posible desde "
                    "aqui; usa ejecutar --elevado antes de que abra)")
    c.json_out({
        "ok": True,
        "matados": [args.pid],
        "arbol": bool(args.arbol),
        "forzado": bool(args.forzar),
        "salida_taskkill": salida[:300],
    })


# --- ejecutar ---------------------------------------------------------------

def cmd_ejecutar(args):
    obj = args.objetivo
    tipo = None
    resuelto = obj
    if _ESQUEMA_URL.match(obj):
        tipo = "url"
    else:
        w = shutil.which(obj)
        if w:
            tipo, resuelto = "programa", w
        elif os.path.exists(obj):
            tipo, resuelto = "archivo", os.path.abspath(obj)
    if tipo is None:
        c.fail("%r no es URL (esquema 'algo:' o 'www.'), ni programa "
               "resolvable por PATH/PATHEXT, ni archivo existente." % obj)
    args_str = " ".join(args.args) if args.args else None
    if args.elevado:
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", resuelto, args_str, args.dir, 1)  # SW_SHOWNORMAL
        if int(rc) <= 32:
            motivo = {5: "acceso denegado", 1223: "el usuario CANCELO el UAC",
                      2: "archivo no encontrado"}.get(int(rc), "ShellExecute "
                                                      "devolvio rc=%d" % int(rc))
            c.fail("No se pudo lanzar ELEVADO %r: %s" % (resuelto, motivo),
                   rc=int(rc))
        c.json_out({
            "ok": True, "objetivo": obj, "tipo": tipo, "resuelto": resuelto,
            "mecanica": 'ShellExecuteW "runas" (UAC)', "elevado": True,
            "pid": None,
            "nota": "recordatorio SKILL 1: las apps ELEVADAS NO reciben "
                    "inyeccion desde procesos no elevados (el clic "
                    'desaparece "sin error"); verificar con capturar siempre',
        })
        return
    proc = None
    if tipo == "programa":
        lote = os.path.splitext(resuelto)[1].lower() in (".bat", ".cmd")
        if lote:
            # Popen shell=False rechaza .bat/.cmd: desvio a startfile
            # (misma mecanica que ventanas.py abrir).
            try:
                os.startfile(resuelto)
                mecanica = "os.startfile (lote: no admite args via Popen)"
            except OSError as exc:
                c.fail("Fallo al lanzar lote %r: %s: %s"
                       % (resuelto, type(exc).__name__, exc))
        else:
            try:
                proc = subprocess.Popen(
                    [resuelto] + (args.args or []), shell=False, cwd=args.dir,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                mecanica = "Popen(shell=False)"
            except OSError as exc:
                c.fail("Fallo al lanzar %r via Popen: %s: %s"
                       % (resuelto, type(exc).__name__, exc))
    else:
        try:
            os.startfile(resuelto)
            mecanica = "os.startfile (ShellExecute: asociaciones)"
        except OSError as exc:
            c.fail("Fallo al abrir %r: %s: %s"
                   % (resuelto, type(exc).__name__, exc))
    item = {
        "ok": True, "objetivo": obj, "tipo": tipo, "resuelto": resuelto,
        "mecanica": mecanica, "elevado": False,
        "pid": proc.pid if proc else None, "dir": args.dir,
        "nota": "para ESPERAR la ventana usa ventanas.py abrir; aqui lo propio "
                "es lanzar con args/dir (shell=False: sin meta-caracteres)",
    }
    if tipo == "programa" and lote:
        item["nota"] += "; LOS ARGS de un .bat/.cmd no se pasaron (startfile no admite args)"
    c.json_out(item)


# --- dpi ---------------------------------------------------------------------

def cmd_dpi_listar(args):
    user32 = ctypes.windll.user32
    shcore = getattr(ctypes.windll, "shcore", None)
    via = "shcore.GetDpiForMonitor(MDT_EFFECTIVE_DPI)"
    out = []

    def cb(hmon, hdc, lprc, dato):
        mi = c._MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(c._MONITORINFOEXW)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            c.fail("GetMonitorInfoW fallo: %s" % ctypes.WinError())
        dx = wintypes.UINT()
        dy = wintypes.UINT()
        hr = -1
        if shcore is not None:
            try:
                hr = shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dx),
                                             ctypes.byref(dy))
            except Exception:
                hr = -1
        if hr != 0:
            # degradacion honesta: dpi del sistema (no por monitor)
            via_local = "GetDpiForSystem/GetDeviceCaps (degradado)"
            try:
                dpi_sys = user32.GetDpiForSystem()
                dx.value = dpi_sys
                dy.value = dpi_sys
            except Exception:
                dc = user32.GetDC(None)
                gdi = ctypes.windll.gdi32
                dx.value = gdi.GetDeviceCaps(dc, 88)  # LOGPIXELSX
                dy.value = gdi.GetDeviceCaps(dc, 90)  # LOGPIXELSY
                user32.ReleaseDC(None, dc)
            cb.degradado = True
        r = mi.rcMonitor
        idx = len(out)
        out.append({
            "indice": idx,
            "nombre": mi.szDevice,
            "primario": bool(mi.dwFlags & c.MONITORINFOF_PRIMARY),
            "dpi_x": int(dx.value), "dpi_y": int(dy.value),
            "escala_pct": int(round(dx.value * 100.0 / 96.0)),
            "marco": c.MARCO,
            "bounds": [int(r.left), int(r.top), int(r.right), int(r.bottom)],
        })
        return True

    cb.degradado = False
    if not user32.EnumDisplayMonitors(None, None, c._LPFNMONITORENUM(cb), 0):
        c.fail("EnumDisplayMonitors fallo: %s" % ctypes.WinError())
    c.json_out({
        "ok": True,
        "via": via + (" [degradado a DPI del sistema en alguno]"
                      if cb.degradado else ""),
        "marco": c.MARCO,
        "monitores": out,
        "nota": "escala_pct = dpi_x/96: 100=1.0x, 125=1.25x, 150=1.5x...; la "
                "skill YA unifica capturas/coordenadas/inyeccion en pixeles "
                "FISICOS (SetProcessDpiAwareness(2)): aqui solo se CONSULTA "
                "la escala para decidir --max-lado de la vision",
    })


def construir_parser():
    parser = c.Parser(
        prog="win_especiales.py",
        description="Funciones exclusivas de Windows: portapapeles "
                    "(leer/escribir con respaldo/estado), procesos "
                    "(tasklist/taskkill gateado), ejecutar (con --elevado "
                    "UAC) y dpi listar. JSON canonico de la skill.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1] if __doc__ and "Subcomandos:" in __doc__ else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="GRUPO")

    p = sub.add_parser("portapapeles", help="leer/escribir/estado del clipboard")
    sp = p.add_subparsers(dest="accion", required=True, metavar="ACCION")
    a = sp.add_parser("leer", help="imprimir SOLO el texto pedido")
    a.add_argument("--formato", default="auto", metavar="F",
                   help="auto|text (por defecto auto)")
    a.set_defaults(func=cmd_portapapeles_leer)
    a = sp.add_parser("escribir", help="copiar TEXTO al clipboard")
    a.add_argument("texto", help="contenido literal a copiar (usa comillas)")
    a.add_argument("--respaldar", action="store_true",
                   help="guardar el contenido previo en .tmp/clipboard_backup.txt")
    a.add_argument("--pegar", action="store_true",
                   help="ademas pegar (ctrl+v via teclado.py; exige foco)")
    a.set_defaults(func=cmd_portapapeles_escribir)
    a = sp.add_parser("estado", help="hay texto? cuanto? (NUNCA el contenido)")
    a.set_defaults(func=cmd_portapapeles_estado)

    p = sub.add_parser("procesos", help="listar/matar por PID (tasklist/taskkill)")
    sp = p.add_subparsers(dest="accion", required=True, metavar="ACCION")
    a = sp.add_parser("listar", help="procesos del sistema")
    a.add_argument("--nombre", metavar="X.exe", help="filtrar por imagen")
    a.add_argument("--con-ventana", dest="con_ventana", action="store_true",
                   help="cruzar pid->titulos visibles (EnumWindows)")
    a.set_defaults(func=cmd_procesos_listar)
    a = sp.add_parser("matar", help="taskkill gateado con --confirmar")
    a.add_argument("--pid", type=int, required=True, help="PID a matar")
    a.add_argument("--arbol", action="store_true", help="tambien hijos (/T)")
    a.add_argument("--forzar", action="store_true", help="forzar (/F)")
    a.add_argument("--confirmar", action="store_true",
                   help="gate explicito: sin esta bandera, NO mata")
    a.set_defaults(func=cmd_procesos_matar)

    p = sub.add_parser("ejecutar", help="lanzar programa/ruta/url (opcional elevado)")
    p.add_argument("objetivo", help="programa en PATH, ruta o URL")
    p.add_argument("--args", nargs="*", metavar="ARG",
                   help="argumentos literales (shell=False, sin meta-caracteres)")
    p.add_argument("--elevado", action="store_true",
                   help="ShellExecuteW 'runas' (prompt UAC; el PID no se reporta)")
    p.add_argument("--dir", metavar="D", help="directorio de trabajo")
    p.set_defaults(func=cmd_ejecutar)

    p = sub.add_parser("dpi", help="escala DPI por monitor (consulta)")
    sp = p.add_subparsers(dest="accion", required=True, metavar="ACCION")
    a = sp.add_parser("listar", help="dpi y escala de cada monitor")
    a.set_defaults(func=cmd_dpi_listar)

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
