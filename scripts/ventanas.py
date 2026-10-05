# -*- coding: utf-8 -*-
"""ventanas.py — Ventanas de Windows via pygetwindow (skill computer-use-py).

PyAutoGUI retiro su propia API de ventanas en 0.9.54: lo unico que existe
es la re-exportacion Windows-only de pygetwindow, asi que este script usa
`pygetwindow` directamente (viene instalada con pyautogui).

Notas verificadas:
- Los rectangulos vienen de GetWindowRect: coordenadas del ESPACIO DE
  PANTALLA VIRTUAL (negativas con monitores a la izquierda/arriba del
  primario), el mismo marco de las capturas multi-monitor y de raton.py
  (VERIFICADO en la fuente de pygetwindow; ver references/monitores-multi.md).
  Una ventana minimizada reporta la posicion fuera de pantalla tipica
  (-32000,-32000): no es un monitor, es el estado minimizado.
- getWindowsWithTitle hace coincidencia por SUBCADENA: si hay varias
  ventanas que contienen el titulo pedido, este script NO elige — devuelve
  un error JSON pidiendo el titulo exacto.
- activate() existe en pygetwindow 0.0.9 (verificado en runtime; la doc
  oficial mostraba focus()). Verificado en escritorio real: sobre una ventana
  MINIMIZADA activate() puede lanzar error de Windows 6
  (ERROR_INVALID_HANDLE) o segun la app no hacer nada visible (tkinter:
  ok=true y sigue minimizada). Patron seguro: ejecutar antes "restaurar"
  (o clic en la barra de tareas) y re-verificar el foco con capturar.
  Cuando este script detecta ese codigo en "activar" anade una "pista" al
  JSON de error (solo informativo: el flujo y la salida no cambian).
- close() puede dejar un dialogo modal de confirmacion abierto (depende de
  la app): verificar despues con pantalla.py capturar.
- abrir NO pasa por cmd ni powershell: el loop del agente NUNCA necesita
  `start`. DOS mecanicas distintas, documentadas:
  * PROGRAMA (resuelto con shutil.which => PATH + PATHEXT; "notepad" =>
    notepad.EXE): subprocess.Popen([ruta], shell=False) — CreateProcess
    DIRECTO sin shell (los meta-caracteres no se interpretan) y con
    CREATE_NO_WINDOW para que una consola heredada no ensucie el JSON. Los
    .bat/.cmd se desvian a startfile porque Popen con shell=False los
    rechaza. El "pid" reportado puede no ser el de la ventana final (apps
    empaquetadas): por eso la busqueda de ventana usa titulo + hWnd, no pid.
  * URL o ARCHIVO: os.startfile — ShellExecute "open", respeta las
    ASOCIACIONES del registro (https => navegador por defecto, .txt =>
    editor): misma semantica que `start` en cmd pero sin shell.
  * clasificacion en ese orden: esquema "letras:" (>=2: "C:\\ruta" NO es
    URL) o "www." => URL; si no, which => programa; si no, ruta existente =>
    archivo; nada de eso => error JSON.
- Con --esperar se sondea pygetwindow cada 0.25 s hasta que aparezca una
  ventana NUEVA (snapshot de hWnd ANTES de lanzar) cuyo titulo contenga la
  pista: --titulo si se da; si no, se deriva del objetivo — OJO: los titulos
  localizados exigen --titulo explicito (en español Notepad titula "Bloc de
  notas" => pista "Bloc"). Timeout = JSON ok:true con "ventana": null y
  nota, NO error: la app pudo abrir sin ventana, ser lenta o REUTILIZAR su
  ventana (navegador, o sesion restaurada de Bloc de notas: para ventana
  nueva usa ctrl+shift+n dentro de la app o cierra y re-abre).

Salida: JSON por stdout; errores JSON con "error".

Subcomandos:
  listar      Todas las ventanas: titulo + rectangulo + estado.
  foco        Ventana foreground activa (quien recibe el teclado).
  activar     Traer y enfocar la ventana ("activate").
  minimizar   Minimizar.
  restaurar   Restaurar desde minimizada/maximizada.
  maximizar   Maximizar.
  cerrar      Cerrar (equivalente a pulsar la X).
  abrir       Lanza app/URL/archivo y (opcional) espera su ventana nueva.

Ejemplos (desde la carpeta computer-use-py):
  py scripts/ventanas.py listar
  py scripts/ventanas.py foco
  py scripts/ventanas.py activar "Bloc de notas"
  py scripts/ventanas.py cerrar "Ventana de confirmacion"
  py scripts/ventanas.py abrir notepad --esperar 8 --titulo "Bloc"
  py scripts/ventanas.py abrir "https://example.com"
  py scripts/ventanas.py abrir "C:\\datos\\informe.xlsx" --esperar 5 --titulo "informe"
"""

import argparse
import os
import re
import shutil
import subprocess

import _compartido as c  # trae el DPI del proceso fijado antes de cualquier import
import pyautogui
import pygetwindow as gw


def _rect(ventana):
    return {
        "left": int(getattr(ventana, "left", 0) or 0),
        "top": int(getattr(ventana, "top", 0) or 0),
        "ancho": int(getattr(ventana, "width", 0) or 0),
        "alto": int(getattr(ventana, "height", 0) or 0),
    }


def _estado(ventana):
    return {
        "minimizada": bool(getattr(ventana, "isMinimized", False)),
        "maximizada": bool(getattr(ventana, "isMaximized", False)),
        "activa": bool(getattr(ventana, "isActive", False)),
    }


def _buscar(titulo):
    """Ventana unica que coincide con `titulo`, o error JSON con pistas."""
    try:
        coincidencias = gw.getWindowsWithTitle(titulo)
    except Exception as exc:
        c.fail("pygetwindow fallo al buscar ventanas: %s: %s"
               % (type(exc).__name__, exc))
    if not coincidencias:
        titulos = [t for t in gw.getAllTitles() if t]
        c.fail("Ninguna ventana contiene el titulo %r. Usa listar y pasa el "
               "titulo exacto." % titulo,
               coincidencias=0,
               ventanas_abiertas=titulos[:25])
    if len(coincidencias) > 1:
        c.fail("Varias ventanas coinciden con %r (%d): pide el titulo exacto y "
               "unico, o cierra las duplicadas." % (titulo, len(coincidencias)),
               coincidencias=[v.title for v in coincidencias])
    return coincidencias[0]


def cmd_listar(args):
    vacios = 0
    ventanas = []
    for v in gw.getAllWindows():
        if not v.title:
            vacios += 1  # ventanas sin titulo (propias del sistema): se omiten
            continue
        item = {"titulo": v.title}
        item.update(_rect(v))
        item.update(_estado(v))
        ventanas.append(item)
    c.json_out({
        "total": len(ventanas),
        "sin_titulo_omitidas": vacios,
        "ventanas": ventanas,
        "nota": "rectangulo en el ESPACIO DE PANTALLA VIRTUAL (GetWindowRect: "
                "negativo hacia la izquierda/arriba con monitores vecinos); "
                "los estados se leen con getattr (0.0.9)",
    })


def cmd_foco(args):
    """Subcomando 'foco': la ventana foreground (la que recibe el teclado).

    pygetwindow 0.0.9 implementa getActiveWindow() sobre GetForegroundWindow
    (VERIFICADO en la fuente): por eso funciona tambien desde un proceso de
    consola sin ventanas.
    """
    ventana = gw.getActiveWindow()
    if ventana is None:
        c.json_out({
            "activa": None,
            "nota": "no hay ventana foreground (pantalla de bloqueo/UAC?): NO "
                    "teclees aun; re-verifica con pantalla.py capturar",
        })
        return
    c.json_out({
        "activa": True,
        "titulo": ventana.title,
        "rect": _rect(ventana),
        "estado": _estado(ventana),
        "nota": "rect en coordenadas del ESPACIO VIRTUAL; verifica con "
                "pantalla.py capturar despues de teclear (un toast puede "
                "robar el foco entre el foco y la emision)",
    })


def _es_error_seis(exc):
    """True si exc es el error de Windows 6 (ERROR_INVALID_HANDLE).

    Nota (escritorio real): es el fallo tipico de activate() sobre una
    ventana MINIMIZADA. Patron correcto: ejecutar antes 'restaurar' (o clic
    en la barra de tareas) y re-verificar el foco con una captura. Solo
    informativo: se usa para anadir una "pista" al JSON de error; no cambia
    el flujo ni el codigo de salida.
    """
    try:
        if getattr(exc, "winerror", None) == 6:
            return True
        if 6 in (getattr(exc, "args", None) or ()):
            return True
        return "WinError 6]" in str(exc)
    except Exception:
        return False


def _accion(titulo, nombre_metodo, mensaje_aviso):
    ventana = _buscar(titulo)
    metodo = getattr(ventana, nombre_metodo, None)
    if metodo is None:
        c.fail("pygetwindow 0.0.9 no expone %s(); verificar en runtime con una "
               "captura." % nombre_metodo)
    try:
        metodo()
    except Exception as exc:
        extra = {}
        if nombre_metodo == "activate" and _es_error_seis(exc):
            extra["pista"] = ("ventana minimizada? prueba restaurar primero "
                              "(o clic en la barra de tareas) y re-verifica "
                              "el foco con pantalla.py capturar")
        c.fail("%s() fallo sobre %r: %s: %s"
               % (nombre_metodo, titulo, type(exc).__name__, exc), **extra)
    item = {
        "ok": True,
        "accion": nombre_metodo,
        "titulo": ventana.title,
        "rect": _rect(ventana),
        "estado": _estado(ventana),
        "aviso": mensaje_aviso,
    }
    c.json_out(item)


def cmd_activar(args):
    """Subcomando 'activar'.

    Nota (escritorio real): sobre una ventana MINIMIZADA, activate() puede
    fallar con error de Windows 6 (ERROR_INVALID_HANDLE). Patron: ejecutar
    antes 'restaurar' (o clic en la barra de tareas) y re-verificar el foco
    con pantalla.py capturar. El error JSON incluye "pista" en ese caso.
    """
    _accion(args.titulo, "activate",
            "el foco decide quien recibe el teclado: verifica con capturar")


def cmd_minimizar(args):
    _accion(args.titulo, "minimize",
            "comportamiento de minimize() por app sin garantias (verificar en runtime)")


def cmd_restaurar(args):
    _accion(args.titulo, "restore",
            "comportamiento de restore() por app sin garantias (verificar en runtime)")


def cmd_maximizar(args):
    _accion(args.titulo, "maximize",
            "comportamiento de maximize() por app sin garantias (verificar en runtime)")


def cmd_cerrar(args):
    _accion(args.titulo, "close",
            "muchas apps abren un dialogo modal al cerrar (guardar cambios?): "
            "verifica SIEMPRE con pantalla.py capturar")


# Esquema de URL: >=2 letras/digitos y +-. antes de ':' (descarta "C:\ruta")
# o prefijo "www.". VERIFICADO en runtime: startfile maneja ambos.
_ESQUEMA_URL = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.\-]{1,}:|www\.)")
_LOTE = (".bat", ".cmd")  # Popen shell=False las rechaza: van por startfile


def _clasificar(objetivo):
    """(tipo, resuelto): 'url' | 'programa' | 'archivo' | (None, None).

    Orden documentado en el docstring: URL por esquema/www.; luego
    shutil.which (PATH + PATHEXT); luego ruta de archivo existente.
    """
    if _ESQUEMA_URL.match(objetivo):
        return "url", objetivo
    resuelto = shutil.which(objetivo)
    if resuelto:
        return "programa", resuelto
    if os.path.exists(objetivo):
        return "archivo", os.path.abspath(objetivo)
    return None, None


def _pista_por_defecto(objetivo, tipo):
    """Pista de titulo derivada del objetivo (orientativa: ante titulos
    localizados conviene --titulo explicito, p. ej. "Bloc")."""
    if tipo == "url":
        # quita esquema y BARRAS: "file:///C:\x" => "C:/x" (VERIFICADO en
        # smoke: con {0,2} quedaba "/C:/x" y la pista salia entera)
        resto = re.sub(r"^[A-Za-z][A-Za-z0-9+.\-]{1,}:/*", "", objetivo)
        if re.match(r"^[A-Za-z]:[\\/]", resto):  # file:///C:\x => nombre
            return os.path.basename(resto) or objetivo
        return re.split(r"[/?#]", resto, maxsplit=1)[0] or objetivo  # dominio
    base = os.path.basename(os.path.normpath(objetivo))
    return os.path.splitext(base)[0] if tipo == "programa" else base


def _snapshot_previos():
    """hWnd de las ventanas visibles AHORA, para exigir ventana NUEVA.

    getWindowsWithTitle construye un Win32Window NUEVO por llamada: la
    identidad del objeto no sirve, el hWnd si (VERIFICADO en la fuente
    0.0.9; atributo privado tolerado porque la busqueda degrada a
    "cualquier coincidencia" si desapareciera).
    """
    try:
        handles = {getattr(v, "_hWnd", None) for v in gw.getAllWindows()}
    except Exception:
        return set()  # sin snapshot: toda coincidencia cuenta como nueva
    handles.discard(None)
    return handles


def cmd_abrir(args):
    """Subcomando 'abrir': lanza app/URL/archivo sin cmd y con --esperar
    sondea hasta su ventana NUEVA (mecanicas en el docstring)."""
    if not (0 <= args.esperar <= 120):
        c.fail("--esperar debe estar entre 0 y 120 segundos (0 = no esperar).")
    tipo, resuelto = _clasificar(args.objetivo)
    if tipo is None:
        c.fail("%r no es URL (esquema 'algo:' o 'www.'), ni programa "
               "resolvable por PATH/PATHEXT, ni archivo existente. Revisa la "
               "ortografia o pasa la ruta completa." % args.objetivo)

    es_lote = tipo == "programa" and \
        os.path.splitext(resuelto)[1].lower() in _LOTE
    usar_popen = tipo == "programa" and not es_lote
    mecanica = ("Popen(shell=False)" if usar_popen
                else "os.startfile (ShellExecute: asociaciones)")
    pista = (args.titulo or "").strip() or _pista_por_defecto(args.objetivo, tipo)
    previos = _snapshot_previos() if args.esperar > 0 else set()

    proc = None
    try:
        if usar_popen:
            # CREATE_NO_WINDOW: si el objetivo es una app de consola, su
            # stdout NO se mezcla con el JSON de este script.
            proc = subprocess.Popen(
                [resuelto], shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            os.startfile(resuelto)
    except OSError as exc:
        c.fail("Fallo al lanzar %r via %s: %s: %s"
               % (resuelto, mecanica, type(exc).__name__, exc),
               nota="si es un acceso directo o una asociacion rota, probar la "
                    "ruta del ejecutable real")

    resultado = {
        "ok": True,
        "accion": "abrir",
        "objetivo": args.objetivo,
        "tipo": tipo,
        "resuelto": resuelto,
        "mecanica": mecanica,
        "pid": proc.pid if proc else None,
        "esperar_segundos": args.esperar,
    }

    if args.esperar == 0:
        resultado["ventana"] = None
        resultado["nota"] = ("lanzado sin esperar la ventana (--esperar 0): "
                             "verifica con pantalla.py capturar o ventanas.py "
                             "listar")
        c.json_out(resultado)
        return

    resultado["pista_titulo"] = pista
    ventana = None
    limite = c.time.time() + args.esperar
    while c.time.time() < limite:
        try:
            nuevas = [v for v in gw.getWindowsWithTitle(pista)
                      if getattr(v, "_hWnd", None) not in previos]
        except Exception:
            nuevas = []  # pygetwindow fallo puntual: seguir sondeando
        if nuevas:
            ventana = nuevas[0]
            break
        c.time.sleep(0.25)

    if ventana is not None:
        item = {"titulo": ventana.title}
        item.update(_rect(ventana))
        item.update(_estado(ventana))
        resultado["ventana"] = item
        resultado["nota"] = ("ventana NUEVA con pista %r; rect en el ESPACIO "
                             "VIRTUAL y 'activa' dice si ya recibe el teclado "
                             "(re-verifica con pantalla.py capturar)" % pista)
    else:
        try:
            pre = len(gw.getWindowsWithTitle(pista))
        except Exception:
            pre = None
        resultado["ventana"] = None
        resultado["preexistentes_con_pista"] = pre
        nota = ("timeout de %d s sin ventana NUEVA con pista %r (NO es "
                "error): la app pudo abrir sin ventana, tardar mas, o "
                "reutilizar/reabrir su ventana (sesiones de Bloc de notas, "
                "tabs de navegador). Verifica con listar o capturar; para "
                "ventana nueva usa ctrl+shift+n dentro de la app o cierra y "
                "re-abre." % (args.esperar, pista))
        if proc is not None and proc.poll() is not None:
            resultado["proceso_termino"] = proc.returncode
            nota += " El proceso lanzado ya termino (rc=%s)." % proc.returncode
        resultado["nota"] = nota
    c.json_out(resultado)


def construir_parser():
    parser = argparse.ArgumentParser(
        prog="ventanas.py",
        description="Listar y manejar ventanas de Windows (pygetwindow). "
                    "La coincidencia de titulo es por subcadena; si hay "
                    "varias, se exige el titulo exacto. Rectangulos en el "
                    "ESPACIO DE PANTALLA VIRTUAL (negativos posibles).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1] if __doc__ and "Subcomandos:" in __doc__ else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    sub.add_parser("listar", help="todas las ventanas con titulo, rectangulo y estado") \
       .set_defaults(func=cmd_listar)

    sub.add_parser("foco", help="ventana foreground: titulo, rectangulo y estado") \
       .set_defaults(func=cmd_foco)

    for nombre, ayuda, funcion in (
        ("activar", "traer y enfocar la ventana", cmd_activar),
        ("minimizar", "minimizar la ventana", cmd_minimizar),
        ("restaurar", "restaurar la ventana", cmd_restaurar),
        ("maximizar", "maximizar la ventana", cmd_maximizar),
        ("cerrar", "cerrar la ventana (ojo: posibles modales)", cmd_cerrar),
    ):
        p = sub.add_parser(nombre, help=ayuda)
        p.add_argument("titulo", help="titulo (o parte) de la ventana; debe ser unico")
        p.set_defaults(func=funcion)

    p = sub.add_parser(
        "abrir", help="lanzar app/URL/archivo (Popen/startfile, sin cmd) y "
                      "opcionalmente esperar su ventana nueva")
    p.add_argument("objetivo",
                   help="programa en PATH (via PATHEXT), URL ('https://...', "
                        "'mailto:...', 'www. ...') o ruta de archivo (se abre "
                        "con su asociacion de Windows)")
    p.add_argument("--esperar", type=int, default=0, metavar="SEGUNDOS",
                   help="sondear hasta que aparezca una ventana NUEVA con la "
                        "pista en el titulo (0 = no esperar; 1-120)")
    p.add_argument("--titulo", metavar="SUBCADENA",
                   help="pista del titulo a esperar; si se omite se deriva "
                        "del objetivo (ej. 'Bloc' para el Bloc de notas)")
    p.set_defaults(func=cmd_abrir)

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
