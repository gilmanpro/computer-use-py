# -*- coding: utf-8 -*-
"""ventanas.py — Ventanas (skill computer-use-py; ruta Windows via pygetwindow).

ENTRADA MULTI-OS (FASE SEG3): `python scripts/ventanas.py ...` vale en los 3
SO — en Windows ejecuta esta ruta nativa (validada en escritorio real); en
Linux/macOS ejecuta EN EL PROPIO PROCESO la ruta de su SO (las primitivas
exclusivas viven en scripts/linux/linux_especiales.py y
scripts/macos/macos_especiales.py; el dispatch es por sys.platform en main());
plataforma desconocida responde JSON + rc 2.

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
- IMPL-K P0.1: en apps multi-ventana/multi-tab (Notepad 11, navegadores) el
  titulo es COMPARTIDO y ademas cambia al teclear (W11 titula la pestana con
  el contenido). Las acciones aceptan `--id N` (hWnd de listar/foco/abrir):
  flujos seguros = `abrir --esperar-nueva` → guardar ventana.id →
  `activar/mover/cerrar --id` + `teclado.py --foco-id`.
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

Campo "via" (decision FASE TEST-A, aditivo): los JSON de listar/foco/acciones
incluyen "via": "pygetwindow" — declara la fuente real de los datos (en esta
rama Windows es pygetwindow sobre Win32), igual que raton.py posicion ya
declara su via. Ningun consumidor existente se rompe: es una clave MAS.

Subcomandos (IMPL-K: las acciones aceptan --id N por hWnd, el destino
estable — el titulo es compartido y cambia al teclear en apps multi-ventana):
  listar      Todas las ventanas: id + titulo + rectangulo + estado.
  foco        Ventana foreground activa (--con-dueno: pid/owner, P2.5).
  activar     Traer y enfocar la ventana ("activate").
  minimizar   Minimizar.
  restaurar   Restaurar desde minimizada/maximizada.
  maximizar   Maximizar.
  cerrar      Cerrar (X). --descartar: ladder anti-modal W11 por id.
  mover       Mover a --monitor N|primario|nombre o --x --y (--ancho --alto).
  ocupantes   Que ventanas solapan una zona (READ-ONLY, x1 y1 x2 y2).
  abrir       Lanza app/URL/archivo y (opcional) espera su ventana nueva;
              --esperar-nueva: diff de hWnd sin pista + ids_nuevas[].

Ejemplos (desde la carpeta computer-use-py):
  py scripts/ventanas.py listar              # Windows (python3 en otros SO)
  py scripts/ventanas.py foco
  py scripts/ventanas.py activar "Bloc de notas"
  py scripts/ventanas.py activar --id 199262
  py scripts/ventanas.py cerrar --id 199262 --descartar
  py scripts/ventanas.py mover --id 199262 --monitor 1
  py scripts/ventanas.py ocupantes -1400 480 -700 800
  py scripts/ventanas.py abrir "C:\\tmp\\nota.txt" --esperar 8 --esperar-nueva
  py scripts/ventanas.py abrir "https://example.com"
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time

_DIR_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _DIR_SCRIPTS not in sys.path:
    sys.path.insert(0, _DIR_SCRIPTS)
import _core


# ===========================================================================
# SECCION WINDOWS — cmd_*/helpers/parser VERBATIM del CLI raiz historico.
# `c` (glue_windows), `pyautogui` y `gw` (pygetwindow) se bind-eaban en el top;
# en SEG3 se bind-ean en main() (global) ANTES de parsear = mismo
# comportamiento. _ESQUEMA_URL era `= c.ESQUEMA_URL` en el top actual: igual
# que _BOTONES en raton.py, la asignacion se movio a la rama win de main() con
# `global` (desviacion obligada; el placeholder no se usa en linux/mac, cuyas
# secciones llaman c.ESQUEMA_URL directo).
# ===========================================================================

_ESQUEMA_URL = None  # reasignado a c.ESQUEMA_URL en la rama win de main()
_LOTE = (".bat", ".cmd")  # Popen shell=False las rechaza: van por startfile


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


def _item_ventana(ventana):
    """Item CANONICO multi-rama (P1-2): rect+estado ANIDADADOS y claves
    comunes (titulo/id/app). Windows conserva ADEMAS las claves planas
    historicas dentro del item (superset: salida vieja intacta como
    subconjunto)."""
    item = {"titulo": ventana.title,
            "rect": _rect(ventana),
            "estado": _estado(ventana),
            "id": getattr(ventana, "_hWnd", None),
            "app": None}
    item.update(_rect(ventana))    # left/top/ancho/alto (ruta historica)
    item.update(_estado(ventana))  # minimizada/maximizada/activa (ruta historica)
    return item


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


def _buscar_por_id(hwnd):
    """Ventana con ese hWnd EXACTO (IMPL-K P0.1: el helper by-id que los
    drivers de prueba reinventaron 12 veces). El id es el unico identificador
    estable en apps multi-ventana/multi-tab (Notepad 11 comparte titulo y el
    titulo ademas cambia al teclear)."""
    try:
        objetivo = int(hwnd)
    except (TypeError, ValueError):
        c.fail("--id debe ser el hWnd entero que devuelven listar/foco/abrir "
               "en la clave 'id' (recibido %r)." % hwnd)
    for v in gw.getAllWindows():
        if getattr(v, "_hWnd", None) == objetivo:
            return v
    ids = [getattr(v, "_hWnd", None) for v in gw.getAllWindows()
           if getattr(v, "_hWnd", None) is not None]
    c.fail("Ninguna ventana tiene el id (hWnd) %d. Pudo cerrarse: repite "
           "listar (los ids vivos son %d con titulo)." % (objetivo, len(ids)),
           coincidencias=0, ventana_id=objetivo, ids_vivos=ids[:25])


def _buscar_objetivo(args, accion):
    """Resuelve la ventana destino de una accion: --id N (estable, P0.1) o
    titulo por subcadena (ruta historica, intacta sin --id)."""
    if getattr(args, "id", None) is not None:
        if args.titulo:
            c.fail("%r: pasa SOLO un destino: el titulo posicional o --id N "
                   "(nunca ambos)." % accion)
        return _buscar_por_id(args.id)
    if args.titulo is None:
        c.fail("%r exige el titulo posicional (subcadena unica) o --id N "
               "(hWnd de listar/foco/abrir)." % accion)
    return _buscar(args.titulo)


def _resolver_monitor(valor):
    """--monitor para `mover`: dict del monitor (indice, 'primario' o
    subcadena del nombre; 'virtual' no tiene sentido y falla). Mismo
    generico _core.resolver_monitor y misma jerga de la rama Windows."""
    if valor.strip().lower() in ("virtual", "toda", "todas", "todo"):
        c.fail("'mover --monitor' no acepta 'virtual': exige un monitor "
               "concreto (indice, 'primario' o subcadena del nombre).")
    return c.resolver_monitor(
        valor, c.monitores,
        sin_primario="Ningun monitor figura como primario (dwFlags inesperado). "
                     "Revisa monitores.py listar.",
        indice_rango="Indice de monitor %d fuera de rango (0..%d). "
                     "Mapa: monitores.py listar.",
        ambiguo="La subcadena %r coincide con varios monitores (%s): usa el "
                "indice.",
        sin_nombre="Ningun monitor tiene el nombre %r (subcadena de szDevice). "
                   "Mapa: monitores.py listar.")


def cmd_listar(args):
    vacios = 0
    ventanas = []
    for v in gw.getAllWindows():
        if not v.title:
            vacios += 1  # ventanas sin titulo (propias del sistema): se omiten
            continue
        ventanas.append(_item_ventana(v))
    c.json_out({
        "total": len(ventanas),
        "sin_titulo_omitidas": vacios,
        "ventanas": ventanas,
        "via": "pygetwindow",
        "marco": c.MARCO,
        "nota": "rectangulo en el ESPACIO DE PANTALLA VIRTUAL (GetWindowRect: "
                "negativo hacia la izquierda/arriba con monitores vecinos); "
                "los estados se leen con getattr (0.0.9); item canonico: "
                "'rect'+'estado' anidados (y claves planas legacy)",
    })


def _dueno_ventana(hwnd):
    """{pid, owner{id,titulo}} del hWnd (IMPL-K P2.5, via GetWindowThread-
    ProcessId + GetWindow GW_OWNER=4): diagnostico de modales con dueño —
    el driver b3_diag_modal.py del incidente lo escribio a mano 36 lineas.
    ctypes se importa aqui (solo donde se usa)."""
    import ctypes
    user32 = ctypes.windll.user32
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
    owner = None
    try:
        howner = user32.GetWindow(int(hwnd), 4)  # GW_OWNER = 4
    except Exception:
        howner = 0
    if howner:
        n = user32.GetWindowTextLengthW(int(howner))
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(int(howner), buf, n + 1)
        owner = {"id": int(howner), "titulo": buf.value}
    return {"pid": int(pid.value), "owner": owner}


def cmd_foco(args):
    """Subcomando 'foco': la ventana foreground (la que recibe el teclado).

    pygetwindow 0.0.9 implementa getActiveWindow() sobre GetForegroundWindow
    (VERIFICADO en la fuente): por eso funciona tambien desde un proceso de
    consola sin ventanas. Con --con-dueno (P2.5) anade pid/owner del hWnd
    (superset aditivo: sin el flag, salida identica a la historica).
    """
    ventana = gw.getActiveWindow()
    if ventana is None:
        c.json_out({
            "activa": None,
            "ventana": None,
            "via": "pygetwindow",
            "marco": c.MARCO,
            "nota": "no hay ventana foreground (pantalla de bloqueo/UAC?): NO "
                    "teclees aun; re-verifica con pantalla.py capturar",
        })
        return
    item = {
        "activa": True,
        "via": "pygetwindow",
        "titulo": ventana.title,
        "rect": _rect(ventana),
        "estado": _estado(ventana),
        # P1-2: forma canonica anidada, identica en las 3 ramas (el bloque
        # "ventana" es lo que debe leer un consumidor portabl; lo de arriba
        # queda como ruta historica superset).
        "ventana": _item_ventana(ventana),
        "marco": c.MARCO,
        "nota": "rect en coordenadas del ESPACIO VIRTUAL; verifica con "
                "pantalla.py capturar despues de teclear (un toast puede "
                "robar el foco entre el foco y la emision)",
    }
    if getattr(args, "con_dueno", False):
        item["dueno"] = _dueno_ventana(getattr(ventana, "_hWnd", 0))
        item["nota"] += ("; 'dueno' = pid del proceso dueno del hWnd y owner "
                        "(GetWindow GW_OWNER) para diagnosticar modales "
                        "(P2.5)")
    c.json_out(item)


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


def _accion_resuelta(ventana, nombre_metodo, mensaje_aviso):
    """Ejecuta `nombre_metodo` sobre la ventana YA resuelta y emite el JSON
    canonico. `titulo` del mensaje de error se lee de la propia ventana
    (asi el camino --id N responde con el titulo actual, que en Notepad W11
    es el contenido y cambia al teclear)."""
    c.checar_abort(nombre_metodo)  # banderas de vigilar.py (P1-5/P1-6)
    c.checar_pausa()
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
               % (nombre_metodo, ventana.title, type(exc).__name__, exc),
               **extra)
    item = {
        "ok": True,
        "accion": nombre_metodo,
        "via": "pygetwindow",
        "titulo": ventana.title,
        "rect": _rect(ventana),
        "estado": _estado(ventana),
        "ventana": _item_ventana(ventana),
        "marco": c.MARCO,
        "aviso": mensaje_aviso,
    }
    c.json_out(item)


def _accion(titulo, nombre_metodo, mensaje_aviso):
    """Ruta historica por titulo (intacta: _buscar por subcadena)."""
    _accion_resuelta(_buscar(titulo), nombre_metodo, mensaje_aviso)


def cmd_activar(args):
    """Subcomando 'activar'.

    Nota (escritorio real): sobre una ventana MINIMIZADA, activate() puede
    fallar con error de Windows 6 (ERROR_INVALID_HANDLE). Patron: ejecutar
    antes 'restaurar' (o clic en la barra de tareas) y re-verificar el foco
    con pantalla.py capturar. El error JSON incluye "pista" en ese caso.
    IMPL-K P0.1: con --id N la accion va por hWnd (estable).
    """
    _accion_resuelta(_buscar_objetivo(args, "activar"), "activate",
                     "el foco decide quien recibe el teclado: verifica con capturar")


def cmd_minimizar(args):
    _accion_resuelta(_buscar_objetivo(args, "minimizar"), "minimize",
                     "comportamiento de minimize() por app sin garantias (verificar en runtime)")


def cmd_restaurar(args):
    _accion_resuelta(_buscar_objetivo(args, "restaurar"), "restore",
                     "comportamiento de restore() por app sin garantias (verificar en runtime)")


def cmd_maximizar(args):
    _accion_resuelta(_buscar_objetivo(args, "maximizar"), "maximize",
                     "comportamiento de maximize() por app sin garantias (verificar en runtime)")


def _vive(hwnd):
    """True si sigue habiendo una ventana con ese hWnd (verificacion por id:
    patron de los 8 drivers del incidente W11, hoy verbo propio)."""
    return any(getattr(v, "_hWnd", None) == hwnd for v in gw.getAllWindows())


def _cerrar_descartar(ventana):
    """Ladder P1.2-a IMPL-K (cosecha de b3_ciclo*.py/b3_cierre_junk.py):
    cerrar -> ¿vive? -> activar -> alt+n -> tab+enter -> verificacion POR ID.

    Justificacion VERIFICADA W11: el sheet de guardado de Notepad 11 es una
    hoja DENTRO de la misma HWND — close() responde ok:true y la ventana
    PERSISTE (ventanas.py ya avisa generico en el aviso de `cerrar`). Las
    apps con modal en HWND aparte se detectan por diff de hWnd. Nunca se
    recurre a taskkill aqui (P0.2: el gate de procesos manda).
    """
    c.checar_abort("cerrar")
    c.checar_pausa()
    hwnd = getattr(ventana, "_hWnd", None)
    titulo_res = ventana.title
    ids_antes = {getattr(v, "_hWnd", None) for v in gw.getAllWindows()}
    ids_antes.discard(None)
    try:
        ventana.close()
    except Exception as exc:
        c.fail("close() fallo sobre id %s (%r): %s: %s"
               % (hwnd, titulo_res, type(exc).__name__, exc),
               pista="reintenta sin --descartar y resuelve el modal a mano")
    time.sleep(0.8)  # TIEMPOS-K: 1.0->0.8 (-20%, piso ok): margen post-close()
    # para que la ventana desaparezca antes del chequeo POR ID (sandbox W18 ok).
    cerrado = not _vive(hwnd)
    tipo = None
    def _modales_aparte():
        nuevos = []
        for v in gw.getAllWindows():
            hid = getattr(v, "_hWnd", None)
            if hid is not None and hid not in ids_antes and hid != hwnd and v.title:
                nuevos.append({"id": hid, "titulo": v.title})
        return nuevos
    nuevos = _modales_aparte()
    if not cerrado:
        tipo = "hwnd-aparte" if nuevos else "sheet-mismo-hwnd"
        # ladder 2 rondas: alt+n (acelerador "No guardar" W11 ES/EN), luego
        # tab+enter (hoja del sheet mismo-hwnd); reintentar si sigue viva.
        for _ronda in range(2):
            if not _vive(hwnd):
                break
            vivo = next((v for v in gw.getAllWindows()
                         if getattr(v, "_hWnd", None) == hwnd), None)
            if vivo is not None:
                try:
                    vivo.activate()
                    time.sleep(0.3)  # TIEMPOS-K: 0.4->0.3 (-20%, piso ok): asentado
                    # del activate antes de alt+n; si aun no hay foco el guard lo dice.
                except Exception:
                    pass  # sin foco: igual se emite; la verificacion diria
            pyautogui.hotkey("alt", "n")
            time.sleep(0.8)  # TIEMPOS-K: 1.0->0.8 (-20%, piso ok): respuesta del
            # sheet "No guardar" antes de re-verificar vida por id.
            if _vive(hwnd):
                pyautogui.press("tab")
                pyautogui.press("enter")
                time.sleep(0.8)  # TIEMPOS-K: 1.0->0.8 (-20%, piso ok): cierre del
                # sheet via tab+enter antes de la re-verificacion por id.
        nuevos = _modales_aparte()
        if nuevos and tipo == "sheet-mismo-hwnd":
            tipo = "hwnd-aparte"
    cerrado = not _vive(hwnd)
    if not cerrado:
        c.fail("cerrar --descartar NO logro cerrar: la ventana id %s sigue "
               "viva tras el ladder (cerrar -> activar -> alt+n -> tab+enter)."
               % hwnd,
               ventana={"id": hwnd, "titulo": titulo_res},
               modal={"tipo": tipo, "titulos_aparte": [n["titulo"] for n in nuevos]},
               pista="resuelve el modal a mano (pantalla.py capturar + clic) o, "
                     "si es proceso propio, win_especiales.py procesos matar "
                     "--pid N --confirmar (gate multi-ventana P0.2)")
    item = {
        "ok": True,
        "accion": "cerrar",
        "descartar": True,
        "via": "pygetwindow.close+ladder(alt+n/tab+enter)",
        "modal": {"tipo": tipo,
                  "titulos_aparte": [n["titulo"] for n in nuevos]}
                 if tipo else None,
        "desaparecio": True,
        "ventana": {"id": hwnd, "titulo": titulo_res},
        "marco": c.MARCO,
        "aviso": "verificacion por id (hWnd): unico identificador estable en "
                 "apps multi-ventana; sin ladder necesario si no habia "
                 "cambios que preguntar",
    }
    c.json_out(item)


def cmd_cerrar(args):
    if args.descartar:
        _cerrar_descartar(_buscar_objetivo(args, "cerrar"))
        return
    _accion_resuelta(
        _buscar_objetivo(args, "cerrar"), "close",
        "muchas apps abren un dialogo modal al cerrar (guardar cambios?): "
        "verifica SIEMPRE con pantalla.py capturar; en W11 el sheet de "
        "guardado vive en la MISMA HWND (usa cerrar --id N --descartar)")


def cmd_mover(args):
    """Subcomando 'mover' (IMPL-K P1.1 — verbo que NO existia y los 4 drivers
    de W11 intentaron sin exito por vias sinteticas): ventana a un monitor o a
    una coordenada. Win: pygetwindow.moveTo/resizeTo = SetWindowPos directo
    (monitores-multi.md §7) preservando tamano por defecto, con clamp al
    destino en --monitor. Validacion de --monitor ANTES de resolver la
    ventana: el fallo de rango no toca nada."""
    destino_monitor = None
    if args.monitor is not None:
        destino_monitor = _resolver_monitor(args.monitor)
    elif args.x is None or args.y is None:
        c.fail("mover exige --monitor <indice|primario|nombre> O el par "
               "--x --y (coords del ESPACIO VIRTUAL, negativos validos).")
    if args.x is not None and args.monitor is not None:
        c.fail("mover: --monitor y --x/--y son excluyentes (elige destino).")
    if args.x is not None and args.y is None:
        c.fail("mover: --x e --y van juntos.")
    if args.y is not None and args.x is None:
        c.fail("mover: --x e --y van juntos.")
    if args.ancho is not None and args.ancho <= 0:
        c.fail("--ancho debe ser > 0.")
    if args.alto is not None and args.alto <= 0:
        c.fail("--alto debe ser > 0.")
    c.checar_abort("mover")
    c.checar_pausa()
    ventana = _buscar_objetivo(args, "mover")
    ancho = args.ancho if args.ancho is not None else int(ventana.width or 0)
    alto = args.alto if args.alto is not None else int(ventana.height or 0)
    if destino_monitor is not None:
        m = destino_monitor
        # vértice sup-izq del monitor destino + clamp para que quepa entero
        nx, ny = m["izq"], m["top"]
        if ancho > 0 and alto > 0:
            nx = max(m["izq"], min(nx, m["der"] - ancho))
            ny = max(m["top"], min(ny, m["bot"] - alto))
        x_final, y_final = nx, ny
    else:
        x_final, y_final = int(args.x), int(args.y)
    try:
        if (args.ancho is not None or args.alto is not None) and ancho and alto:
            ventana.resizeTo(ancho, alto)
        ventana.moveTo(x_final, y_final)
    except Exception as exc:
        c.fail("mover fallo sobre id %s (%r): %s: %s"
               % (getattr(ventana, "_hWnd", None), ventana.title,
                  type(exc).__name__, exc),
               pista="apps minimizadas: restaurar primero; apps con rect "
                     "inmutable (menu sistema/overlay): no aceptan "
                     "SetWindowPos (comandos-sistema.md §F)")
    monitor_json = None
    if destino_monitor is not None:
        m = destino_monitor
        monitor_json = {"indice": m["indice"], "nombre": m["nombre"],
                        "origen": [m["izq"], m["top"]],
                        "ancho": m["ancho"], "alto": m["alto"],
                        "primario": m["primario"],
                        "bounds": [m["izq"], m["top"], m["der"], m["bot"]]}
    rect = _rect(ventana)
    centro = (rect["left"] + rect["ancho"] // 2,
              rect["top"] + rect["alto"] // 2)
    c.json_out({
        "ok": True,
        "accion": "mover",
        "via": "pygetwindow.moveTo",
        "ventana": _item_ventana(ventana),
        "monitor": monitor_json,
        "centro_nuevo": list(centro),
        "marco": c.MARCO,
        "aviso": "verifica con listar (rect post-SetWindowPos) y capturar; "
                 "con --monitor la ventana queda en el vertice sup-izq del "
                 "destino (clamp a sus bounds); con --x/--y va EXACTA a esa "
                 "coordenada virtual (sin clamp)",
    })


def cmd_ocupantes(args):
    """Subcomando 'ocupantes' (IMPL-K P1.2-f, READ-ONLY): que ventanas
    solapan la zona x1 y1 x2 y2 (coords VIRTUALES, negativos validos).
    Leccion B5d/checklist-W11: antes de un clic/arrastre de limpieza sobre un
    secundario hay que saber si la zona esta LIBRE (no tocaba WhatsApp)."""
    if args.x2 <= args.x1 or args.y2 <= args.y1:
        c.fail("ocupantes exige x2 > x1 e y2 > y1 (la zona es el rectangulo "
               "[x1,y1]..[x2,y2) del espacio virtual).")
    cx, cy = (args.x1 + args.x2) // 2, (args.y1 + args.y2) // 2
    items = []
    total_visibles = 0
    for v in gw.getAllWindows():
        if not v.title:
            continue
        total_visibles += 1
        r = _rect(v)
        l, t = r["left"], r["top"]
        rr, bb = l + r["ancho"], t + r["alto"]
        ox1, oy1 = max(l, args.x1), max(t, args.y1)
        ox2, oy2 = min(rr, args.x2), min(bb, args.y2)
        solapa = (ox2 - ox1) * (oy2 - oy1) if (ox2 > ox1 and oy2 > oy1) else 0
        cubre = l <= cx < rr and t <= cy < bb
        if solapa > 0 or cubre:
            items.append({"id": getattr(v, "_hWnd", None), "titulo": v.title,
                          "rect": [l, t, rr, bb], "solapa_px2": solapa,
                          "cubre_centro_zona": cubre})
    c.json_out({
        "ok": True,
        "accion": "ocupantes",
        "zona": [args.x1, args.y1, args.x2, args.y2],
        "centro_zona": [cx, cy],
        "totales_visibles": total_visibles,
        "ventanas": items,
        "via": "pygetwindow",
        "marco": c.MARCO,
        "nota": "READ-ONLY (no emite accion): usa esto para elegir zonas "
                "LIBRES de clic/arrastre; un 'clic en el wallpaper' que "
                "resulta ser una ventana ajena puede restaurar/activar "
                "trabajo del usuario (VERIFICADO W11, incidente B3d/B5d)",
    })


# Esquema de URL: >=2 letras/digitos y +-. antes de ':' (descarta "C:\ruta")
# o prefijo "www.". VERIFICADO en runtime: startfile maneja ambos.
# (_ESQUEMA_URL = c.ESQUEMA_URL: se bind-ea en la rama win de main(); el
# clasificador generico vive en _core.)


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
    if args.esperar_nueva and args.esperar <= 0:
        c.fail("--esperar-nueva exige --esperar N con N en 1..120 (es un "
               "sondeo por diff de hWnd, no un sueno).")
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
        "marco": c.MARCO,
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
    ids_nuevas = []
    c.checar_abort("espera de ventana")  # P1-6: el freno dura también aquí
    c.checar_pausa()                     # P1-5: con PAUSA, la espera se posterga
    limite = c.time.time() + args.esperar
    if args.esperar_nueva:
        # IMPL-K P1.2-b: IGNORA la pista y elige por diff de hWnd (el diff
        # manual que reescribieron 7 drivers; leccion P0.4: la pista falla
        # con titulos localizados). ids_nuevas reporta TODO lo aparecido.
        while c.time.time() < limite:
            try:
                nuevas = [v for v in gw.getAllWindows()
                          if getattr(v, "_hWnd", None) is not None
                          and getattr(v, "_hWnd", None) not in previos
                          and v.title]
            except Exception:
                nuevas = []  # pygetwindow fallo puntual: seguir sondeando
            if nuevas:
                ventana = nuevas[0]
                ids_nuevas = [getattr(v, "_hWnd", None) for v in nuevas]
                break
            c.checar_abort("espera de ventana nueva")
            c.time.sleep(0.25)
    else:
        while c.time.time() < limite:
            try:
                nuevas = [v for v in gw.getWindowsWithTitle(pista)
                          if getattr(v, "_hWnd", None) not in previos]
            except Exception:
                nuevas = []  # pygetwindow fallo puntual: seguir sondeando
            if nuevas:
                ventana = nuevas[0]
                break
            c.checar_abort("espera de ventana")
            c.time.sleep(0.25)

    if ventana is not None and args.esperar_nueva:
        resultado["ids_nuevas"] = ids_nuevas
        resultado["ventana"] = _item_ventana(ventana)
        resultado["nota"] = ("ventana NUEVA por diff de hWnd (con "
                             "--esperar-nueva la pista %r se IGNORA): guarda "
                             "ventana.id y dirige la entrada con --foco-id "
                             "(las apps multi-ventana comparten titulo)" % pista)
        c.json_out(resultado)
        return
    if ventana is not None:
        resultado["ventana"] = _item_ventana(ventana)
        resultado["nota"] = ("ventana NUEVA con pista %r; rect en el ESPACIO "
                             "VIRTUAL y 'activa' dice si ya recibe el teclado "
                             "(re-verifica con pantalla.py capturar)" % pista)
    else:
        try:
            pre = len(gw.getWindowsWithTitle(pista))
        except Exception:
            pre = None
        resultado["ventana"] = None
        if args.esperar_nueva:
            resultado["ids_nuevas"] = []
        resultado["preexistentes_con_pista"] = pre
        nota = ("timeout de %d s sin ventana NUEVA con pista %r (NO es "
                "error): la app pudo abrir sin ventana, tardar mas, o "
                "reutilizar/reabrir su ventana (sesiones de Bloc de notas, "
                "tabs de navegador). Verifica con listar o capturar; para "
                "ventana nueva usa ctrl+shift+n dentro de la app o cierra y "
                "re-abre." % (args.esperar, pista))
        if args.esperar_nueva:
            nota += (" Sin --esperar-nueva tampoco aparecio NINGUN hWnd nuevo "
                     "(la app reutilizo ventana existente).")
        if proc is not None and proc.poll() is not None:
            resultado["proceso_termino"] = proc.returncode
            nota += " El proceso lanzado ya termino (rc=%s)." % proc.returncode
        resultado["nota"] = nota
    c.json_out(resultado)


def construir_parser():
    parser = c.Parser(
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

    p = sub.add_parser("foco", help="ventana foreground: titulo, rectangulo y "
                       "estado")
    p.add_argument("--con-dueno", dest="con_dueno", action="store_true",
                   help="anade 'dueno' {pid, owner{id,titulo}} al JSON "
                        "(diagnostico de modales, P2.5)")
    p.set_defaults(func=cmd_foco)

    for nombre, ayuda, funcion in (
        ("activar", "traer y enfocar la ventana", cmd_activar),
        ("minimizar", "minimizar la ventana", cmd_minimizar),
        ("restaurar", "restaurar la ventana", cmd_restaurar),
        ("maximizar", "maximizar la ventana", cmd_maximizar),
        ("cerrar", "cerrar la ventana (ojo: posibles modales)", cmd_cerrar),
    ):
        p = sub.add_parser(nombre, help=ayuda)
        p.add_argument("titulo", nargs="?",
                       help="titulo (o parte) de la ventana; debe ser unico "
                            "(o sustituirlo por --id N)")
        p.add_argument("--id", type=int, metavar="N",
                       help="hWnd de la ventana (clave 'id' de listar/foco/"
                            "abrir): unico destino estable en apps "
                            "multi-ventana/multi-tab")
        if nombre == "cerrar":
            p.add_argument("--descartar", action="store_true",
                           help="ladder anti-modal W11: cerrar -> ¿vive? -> "
                                "activar -> alt+n -> tab+enter -> "
                                "verificacion POR ID (el sheet de guardado "
                                "de Notepad 11 vive en la misma HWND)")
        p.set_defaults(func=funcion)

    p = sub.add_parser("mover", help="mover la ventana a un monitor o a unas "
                       "coordenadas (SetWindowPos; NO uses Win+Shift ni "
                       "arrastrar la barra: fallan sinteticamente — W11)")
    p.add_argument("titulo", nargs="?",
                   help="titulo (o parte) unico, o sustituirlo por --id N")
    p.add_argument("--id", type=int, metavar="N",
                   help="hWnd de la ventana (alternativa al titulo)")
    p.add_argument("--monitor", metavar="DESTINO",
                   help="indice (0..N), 'primario' o subcadena del nombre: "
                        "la ventana queda en el vertice sup-izq del destino "
                        "(clamp a sus bounds)")
    p.add_argument("--x", type=int, metavar="X",
                   help="coordenada X virtual destino (con --y; negativos "
                        "validos; SIN clamp: va exacta ahi)")
    p.add_argument("--y", type=int, metavar="Y", help="coordenada Y virtual")
    p.add_argument("--ancho", type=int, metavar="PX",
                   help="nuevo ancho (por defecto conserva el tamano)")
    p.add_argument("--alto", type=int, metavar="PX",
                   help="nuevo alto (por defecto conserva el tamano)")
    p.set_defaults(func=cmd_mover)

    p = sub.add_parser("ocupantes", help="que ventanas solapan la zona x1 y1 "
                       "x2 y2 (READ-ONLY: elegir zonas libres antes de "
                       "clickear/arrastrar) — coords del espacio virtual")
    p.add_argument("x1", type=int, help="x izquierda de la zona")
    p.add_argument("y1", type=int, help="y superior de la zona")
    p.add_argument("x2", type=int, help="x derecha de la zona (> x1)")
    p.add_argument("y2", type=int, help="y inferior de la zona (> y1)")
    p.set_defaults(func=cmd_ocupantes)

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
    p.add_argument("--esperar-nueva", dest="esperar_nueva",
                   action="store_true",
                   help="con --esperar N: IGNORA la pista y elige por diff de "
                        "hWnd (garantiza ventana NUEVA aunque el titulo este "
                        "localizado o se reutilice sesion); JSON con "
                        "ventana.id e ids_nuevas[]")
    p.set_defaults(func=cmd_abrir)

    return parser


# ===========================================================================
# SECCION LINUX — cmd_*/helpers de scripts/linux/ventanas.py (FASE SEG3) con
# sufijo _linux. BAJARON a scripts/linux/linux_especiales.py (executan
# wmctrl/xdotool/xprop/swaymsg/hyprctl) y se llaman via c.<nombre>():
# _HAY_XPROP, _rect_shell, _item_canon, _maximizada_x11, _nodo_json,
# _listar_x11, _buscar_x11, _rect_x11, _cmd_x11, _sway_nodos, _listar_sway,
# _sway_foco, _accion_sway, _hypr_listar, _wayland_listar, _wayland_foco,
# _ids_conocidas, _nueva_ventana. NO bajan (orquestacion + JSON + clasificador
# puro): los cmd_*, _clasificar_linux y _pista_por_defecto_linux; el
# clasificador URL se usa via c.ESQUEMA_URL (alias de rama, sin constante).
# ===========================================================================

_DOC_LINUX = """ventanas.py — Ventanas del dominio LINUX (skill computer-use-py).

MISMO contrato JSON del dominio Windows; superficie 100 % Python. Rutas:
  X11     wmctrl (EWMH/NetWM; -l/-p/-G, -a, -c, -r -b add,maximized_vert,
          maximized_horz VERIFICADOS en su man) + xdotool (search --name,
          getactivewindow, getwindowname/getwindowgeometry --shell,
          windowminimize/windowmap/windowactivate — todos verificados en su
          man). Foco = _NET_ACTIVE_WINDOW gestionado por el WM. Ojo §13 de
          refs/linux-python.md: con focus-stealing prevention (GNOME)
          "activar" puede solo parpadear: SIEMPRE re-verifica con foco +
          capturar. El maximize por xdotool windowstate --toggle NO aparece
          en la manpage de Debian: se usa wmctrl -b (verbatim) y windowstate
          queda como alternativa [runtime].
  Wayland sway (y WMs i3-compatible): swaymsg -t get_tree (man verbatim:
          "JSON-encoded layout tree") para listar/foco, y COMANDOS sway por
          IPC (man: "The message is a sway command... executed immediately")
          para focus/kill/move scratchpad/fullscreen — la sintaxis exacta de
          selectores [con_id=...] es sway(5) [runtime]. Hyprland: listar/foco
          via hyprctl -j [runtime]; las acciones exigen dispatches propios →
          error honesto. GNOME/KDE sin kdotool: error honesto "usa los atajos
          del compositor".

Rectangulos: coordenadas de LAYOUT (screen X11 / layout del compositor), el
mismo marco de pantalla.py y raton.py. Ventanas minimizadas: X11 las lista
wmctrl sin geometria utilizable [runtime]; sway las saca del arbol (solo se
ven en scratchpad/workspace oculto): el JSON puede traer "rect": null.

Salida: JSON por stdout; errores JSON con "error".

Subcomandos (acciones con --id N: destino estable por id de listar — X11
acepta decimal xdotool o 0x... de wmctrl; sway usa con_id):
  listar      Todas las ventanas: id, titulo, rectangulo, pid, activa.
  foco        Ventana foreground activa (quien recibe el teclado).
  activar     Traer y enfocar la ventana (wmctrl -a / sway focus).
  minimizar   Minimizar (xdotool windowminimize / sway move scratchpad).
  restaurar   Volver del minimizado (windowmap+activate / scratchpad show).
  maximizar   Maximizar (wmctrl -b add,maximized_vert,maximized_horz /
              sway fullscreen enable).
  cerrar      Cerrar (wmctrl -c gracefully / sway kill).
  mover       X11 xdotool windowmove / sway 'move container to output'
              (--monitor N o --x --y en coords de layout) [runtime].
  ocupantes   Solapes de la zona x1 y1 x2 y2 (READ-ONLY, coords de layout).
  abrir       Lanza app/URL/archivo (Popen start_new_session o xdg-open;
              log del hijo en .tmp) y opcional --esperar por xdotool search
              --name (X11) o arbol sway; --esperar-nueva: diff de ids.

Ejemplos (desde la carpeta computer-use-py, en la maquina Linux):
  python3 scripts/ventanas.py listar
  python3 scripts/ventanas.py foco
  python3 scripts/ventanas.py activar "Firefox"
  python3 scripts/ventanas.py cerrar "Confirmacion"
  python3 scripts/ventanas.py abrir firefox --esperar 8 --titulo "Firefox"
  python3 scripts/ventanas.py abrir "https://example.com"
  python3 scripts/ventanas.py abrir "/datos/informe.ods"
"""


# ---------------------------------------------------------------- X11
# _listar_x11, _buscar_x11, _rect_x11 y _cmd_x11 BAJARON a linux_especiales
# (wmctrl/xdotool/xprop) => c._listar_x11(), c._buscar_x11(), c._rect_x11(),
# c._cmd_x11(). _rect_shell, _item_canon, _maximizada_x11, _nodo_json e
# _HAY_XPROP idem.


def _validar_destino(args, accion):
    """IMPL-K P0.1: una accion apunta a UN destino — titulo posicional O
    --id N (nunca ambos; ninguno es error JSON). El id es estable entre
    cambios de titulo (apps multi-ventana) y es el que devuelve
    listar/foco/abrir."""
    vid = getattr(args, "id", None)
    if vid is not None and args.titulo:
        c.fail("%r: pasa SOLO un destino: el titulo posicional o --id N." %
               accion)
    if vid is None and args.titulo is None:
        c.fail("%r exige el titulo posicional (subcadena unica) o --id N "
               "(id de listar/foco/abrir)." % accion)
    return vid


def cmd_activar_linux(args):
    c.checar_abort("activar")
    c.checar_pausa()
    vid = _validar_destino(args, "activar")
    if c.deteccion_sesion() == "wayland":
        c._accion_sway(None if vid else args.titulo, "focus",
                     "el foco decide quien recibe el teclado: verifica con "
                     "pantalla.py capturar", con_id=vid)
        return
    v = c._buscar_por_id(vid) if vid is not None else c._buscar_x11(args.titulo)
    c._cmd_x11(v["id"], "wmctrl", ["-i", "-a", v["id"]], "activar",
             "focus-stealing prevention (GNOME) puede SOLO resaltar la "
             "ventana: re-verifica con ventanas.py foco + capturar (refs "
             "linux-python.md §13)")


def cmd_minimizar_linux(args):
    c.checar_abort("minimizar")
    c.checar_pausa()
    vid = _validar_destino(args, "minimizar")
    if c.deteccion_sesion() == "wayland":
        c._accion_sway(None if vid else args.titulo, "move scratchpad",
                     "en sway 'minimizar' = mandar al scratchpad: vuelve con "
                     "restaurar (scratchpad show) [runtime]", con_id=vid)
        return
    v = c._buscar_por_id(vid) if vid is not None else c._buscar_x11(args.titulo)
    c._cmd_x11(v["id"], "xdotool", ["windowminimize", v["id"]], "minimizar",
             "comportamiento del iconify segun WM sin garantias: verificar "
             "en runtime")

def cmd_restaurar_linux(args):
    c.checar_abort("restaurar")
    c.checar_pausa()
    vid = _validar_destino(args, "restaurar")
    if c.deteccion_sesion() == "wayland":
        if vid is not None:
            c._accion_sway(None, "scratchpad show",
                         "muestra el ultimo contenedor del scratchpad "
                         "[runtime]; si hay varios, sway decide cual",
                         con_id=vid)
        else:
            c._accion_sway(None, "scratchpad show",
                         "muestra el ultimo contenedor del scratchpad "
                         "[runtime]; si hay varios, sway decide cual",
                         titulo=args.titulo)
        return
    v = c._buscar_por_id(vid) if vid is not None else c._buscar_x11(args.titulo)
    # windowmap puede fallar si la ventana ya esta mapeada: se tolera y se
    # activa igual ([runtime]: windowmap + windowactivate es el patron del
    # man para "hacer visible" y enfocar).
    c.run("xdotool", ["windowmap", v["id"]], timeout=15.0)
    c._cmd_x11(v["id"], "xdotool", ["windowactivate", "--sync", v["id"]],
             "restaurar",
             "tras restaurar, re-verifica el foco con capturar: algunos WMs "
             "remapean sin activar [runtime]")

def cmd_maximizar_linux(args):
    c.checar_abort("maximizar")
    c.checar_pausa()
    vid = _validar_destino(args, "maximizar")
    if c.deteccion_sesion() == "wayland":
        c._accion_sway(None if vid else args.titulo, "fullscreen enable",
                     "'maximizar' en tiling = fullscreen del contenedor "
                     "[runtime]; la alternativa es mover a un workspace vacio",
                     con_id=vid)
        return
    v = c._buscar_por_id(vid) if vid is not None else c._buscar_x11(args.titulo)
    # -b con dos propiedades: verbatim del man ("Two properties are supported
    # to allow operations like maximizing a window to full screen mode")
    c._cmd_x11(v["id"], "wmctrl",
             ["-i", "-r", v["id"], "-b", "add,maximized_vert,maximized_horz"],
             "maximizar",
             "toggle por xdotool windowstate --toggle MAXIMIZED_VERT/HORZ NO "
             "esta en la manpage de Debian: si necesitas DEsmaximizar usa "
             "wmctrl -b remove,... (mismos estados verificados)")

def cmd_cerrar_linux(args):
    c.checar_abort("cerrar")
    c.checar_pausa()
    vid = _validar_destino(args, "cerrar")
    if args.descartar:
        c.fail("--descartar (ladder anti-modal W11 por teclado) es exclusivo "
               "de la rama Windows: en Linux el modal es una ventana aparte "
               "visible en listar y se cierra con su propio titulo/--id "
               "(VERIFICADO en W11 que aqui no aplica) [runtime]")
        return
    if c.deteccion_sesion() == "wayland":
        c._accion_sway(None if vid else args.titulo, "kill",
                     "muchas apps abren modal al cerrar: verifica SIEMPRE "
                     "con pantalla.py capturar", con_id=vid)
        return
    v = c._buscar_por_id(vid) if vid is not None else c._buscar_x11(args.titulo)
    c._cmd_x11(v["id"], "wmctrl", ["-i", "-c", v["id"]], "cerrar",
             "muchas apps abren modal al cerrar (guardar cambios?): verifica "
             "SIEMPRE con pantalla.py capturar")


def cmd_mover_linux(args):
    """Mover al monitor destino o a coords de LAYOUT (IMPL-K P1.1).

    X11: primitiva xdotool windowmove --sync (man verbatim; [runtime] WM).
    Wayland/sway: 'move container to output <nombre>' por IPC (el layout
    decide la geometria final; --x/--y NO es la via tiling — error honesto).
    Hyprland: sin dispatch auditado => error honesto."""
    c.checar_abort("mover")
    c.checar_pausa()
    vid = _validar_destino(args, "mover")
    if args.ancho is not None or args.alto is not None:
        c.fail("--ancho/--alto no tienen primitiva auditada en Linux "
               "(xdotool windowresize [runtime]): usa el gesto del WM o "
               "quita los flags (mover conserva el tamano).")
    if args.monitor is not None and args.x is not None:
        c.fail("mover: --monitor y --x/--y son excluyentes (elige destino).")
    if args.monitor is None:
        if args.x is None or args.y is None:
            c.fail("mover exige --monitor <indice|primario|nombre> O el par "
                   "--x --y (coords de LAYOUT).")
        x, y = int(args.x), int(args.y)
        m = None
    else:
        m = c._resolver_monitor(args.monitor)
        if m is None:
            c.fail("'mover --monitor' no acepta 'virtual': exige un monitor "
                   "concreto.")
        x, y = m["izq"], m["top"]
    sesion = c.deteccion_sesion()
    if sesion == "x11":
        v = c._buscar_por_id(vid) if vid is not None else c._buscar_x11(args.titulo)
        c._mover_x11(v["id"], x, y)
        return
    if sesion == "wayland":
        if not shutil.which("swaymsg"):
            c.fail("mover en Wayland exige sway/i3-compatible ('move "
                   "container to output'); en Hyprland usa los dispatches "
                   "del compositor (sin ruta auditada aqui) [runtime].",
                   sesion=sesion)
        if args.monitor is None:
            c.fail("En tiling el destino es un OUTPUT: usa --monitor "
                   "(--x --y no es la via; el layout decide la geometria) "
                   "[runtime].")
        if vid is not None:
            c._mover_sway_output(vid, m["nombre"])
        else:
            c._accion_sway(args.titulo, "move container to output %s"
                          % m["nombre"],
                          "en tiling la posicion final la decide el layout "
                          "del workspace destino [runtime]")
        return
    c.fail("Sesion grafica sin detectar: no hay forma de mover (refs "
           "linux-python.md §2/§13).", sesion=sesion)


def cmd_ocupantes_linux(args):
    """Ventanas que solapan la zona (READ-ONLY; IMPL-K P1.2-f)."""
    if args.x2 <= args.x1 or args.y2 <= args.y1:
        c.fail("ocupantes exige x2 > x1 e y2 > y1 (rectangulo [x1,y1]..[x2,y2) "
               "en coords de LAYOUT).")
    sesion = c.deteccion_sesion()
    if sesion == "x11":
        crudas, via = c._listar_x11(), "wmctrl -lpG"
    elif sesion == "wayland":
        crudas, via = c._wayland_listar()
    else:
        c.fail("Sesion grafica sin detectar: sin lista de ventanas.",
               sesion=sesion)
    cx, cy = (args.x1 + args.x2) // 2, (args.y1 + args.y2) // 2
    items = []
    for v in crudas:
        l, t = v.get("left"), v.get("top")
        a, h = v.get("ancho"), v.get("alto")
        if l is None or t is None or a is None or h is None:
            continue  # sway puede dar rect null: sin geometria no hay solape
        rr, bb = l + a, t + h
        ox1, oy1 = max(l, args.x1), max(t, args.y1)
        ox2, oy2 = min(rr, args.x2), min(bb, args.y2)
        solapa = (ox2 - ox1) * (oy2 - oy1) if (ox2 > ox1 and oy2 > oy1) else 0
        cubre = l <= cx < rr and t <= cy < bb
        if solapa > 0 or cubre:
            items.append({"id": v.get("id"), "titulo": v.get("titulo"),
                          "rect": [l, t, rr, bb], "solapa_px2": solapa,
                          "cubre_centro_zona": cubre})
    c.json_out({
        "ok": True,
        "accion": "ocupantes",
        "zona": [args.x1, args.y1, args.x2, args.y2],
        "centro_zona": [cx, cy],
        "totales_visibles": len([v for v in crudas if v.get("titulo")]),
        "ventanas": items,
        "via": via,
        "sesion": sesion,
        "marco": c.MARCO,
        "nota": "READ-ONLY (no emite accion): zonas con solapa NO son libres "
                "para clic/arrastre sin revisar (leccion W11 portada: un clic "
                "creido 'de escritorio' podia ser ventana ajena)",
    })

# ------------------------------------------------------- Wayland (sway)
# _sway_nodos, _listar_sway, _sway_foco, _accion_sway, _hypr_listar,
# _wayland_listar y _wayland_foco BAJARON a linux_especiales (swaymsg/hyprctl)
# => se invocan via c.<nombre>.


# ---------------------------------------------------------------- común

def cmd_listar_linux(args):
    sesion = c.deteccion_sesion()
    if sesion == "x11":
        crudas, via = c._listar_x11(), "wmctrl -lpG + xdotool getactivewindow"
        nota = ("rectangulos del screen X11 (coordenadas de LAYOUT: el mismo "
                "marco de pantalla.py/raton.py); item canonico rect+estado "
                "(P1-2); 'minimizada' deducida por xdotool search "
                "--onlyvisible [runtime]; 'maximizada' via xprop "
                "_NET_WM_STATE" + ("" if c._HAY_XPROP else " (xprop AUSENTE: "
                "siempre null)") + "; ventana minimizada puede reportar rect "
                "sin geometria utilizable [runtime]")
    elif sesion == "wayland":
        crudas, via = c._wayland_listar()
        nota = ("layout del compositor; item canonico rect+estado; "
                "'minimizada'/'maximizada' null: el tiling no las modela "
                "(scratchpad/fullscreen hacen su papel); minimizadas/ocultas "
                "pueden no aparecer")
    else:
        c.fail("Sesion grafica sin detectar: no hay forma de listar ventanas. "
               "En cron/SSH exporta DISPLAY=:1 o el socket Wayland (refs "
               "linux-python.md §13).", sesion=sesion)
    ventanas = []
    for v in crudas:
        item = c._item_canon(v, maximizada=v.get("maximizada"))
        if "floating" in v:
            item["floating"] = v["floating"]
        ventanas.append(item)
    c.json_out({
        "total": len(ventanas),
        "ventanas": ventanas,
        "sesion": sesion,
        "marco": c.MARCO,
        "via": via,
        "nota": nota,
    })


def cmd_foco_linux(args):
    sesion = c.deteccion_sesion()
    if sesion == "x11":
        r = c.run("xdotool", ["getactivewindow", "getwindowname"],
                  timeout=10.0)
        if r["rc"] != 0:
            c.json_out({
                "activa": None,
                "ventana": None,
                "sesion": sesion,
                "marco": c.MARCO,
                "via": "xdotool getactivewindow getwindowname",
                "nota": "sin ventana activa (xdotool rc=%d: %s): NO teclee "
                        "aun; re-verifica con pantalla.py capturar"
                        % (r["rc"], r["stderr"].strip()),
            })
            return
        # run_ok/run devuelven DICT {rc,stdout,stderr,cmd} (contrato de la
        # libreria linux_especiales): acceso por clave, no por atributo.
        vid = c.run_ok("xdotool", ["getactivewindow"], timeout=10.0)["stdout"].strip()
        rect = c._rect_x11(vid)
        pid = None
        rp = c.run("xdotool", ["getwindowpid", vid], timeout=10.0)
        if rp["rc"] == 0:
            try:
                pid = int(rp["stdout"].strip())
            except ValueError:
                pid = None
        item = c._item_canon({"titulo": r["stdout"].strip(), "id": vid,
                            "pid": pid, "activa": True, "minimizada": False},
                           maximizada=c._maximizada_x11(vid) if c._HAY_XPROP else None,
                           rect=rect)
        c.json_out({
            "activa": True,
            "titulo": item["titulo"],
            "id": item["id"],
            "rect": item["rect"],
            "ventana": item,
            "sesion": sesion,
            "marco": c.MARCO,
            "via": "xdotool getactivewindow (+ getwindowgeometry --shell "
                   "[runtime])",
            "nota": ("rect en coords de LAYOUT; 'estado.maximizada' via xprop "
                     "_NET_WM_STATE" + ("" if c._HAY_XPROP else
                                        " (xprop ausente: null)") +
                     "; verifica con capturar despues de teclear (una "
                     "notificacion puede robar el foco entre la lectura y la "
                     "emision)"),
        })
        return
    if sesion == "wayland":
        n, via = c._wayland_foco()
        if via is None:
            c._wayland_listar()  # falla con el error honesto de compositor
        if n is None:
            c.json_out({"activa": None, "ventana": None, "sesion": sesion,
                        "marco": c.MARCO, "via": via,
                        "nota": "el compositor no reporto ventana enfocada: "
                                "NO teclees aun; re-verifica con capturar"})
            return
        item = c._item_canon(n, maximizada=None)
        c.json_out({
            "activa": True,
            "titulo": item["titulo"],
            "id": item["id"],
            "rect": item["rect"],
            "ventana": item,
            "sesion": sesion,
            "marco": c.MARCO,
            "via": via,
            "nota": "rect en coords de LAYOUT; maximizada null: el tiling no "
                    "la modela (fullscreen es otro estado); re-verifica con "
                    "capturar tras teclear",
        })
        return
    c.fail("Sesion grafica sin detectar: sin foco legible (refs "
           "linux-python.md §2/§13).", sesion=sesion)


def _clasificar_linux(objetivo):
    """(tipo, resuelto): 'url' | 'programa' | 'archivo' | (None, None).
    Mismo orden que el padre Windows: esquema/www. => URL; shutil.which =>
    programa; ruta existente => archivo."""
    if c.ESQUEMA_URL.match(objetivo):
        return "url", objetivo
    resuelto = shutil.which(objetivo)
    if resuelto:
        return "programa", resuelto
    if os.path.exists(objetivo):
        return "archivo", os.path.abspath(objetivo)
    return None, None


def _pista_por_defecto_linux(objetivo, tipo):
    if tipo == "url":
        resto = re.sub(r"^[A-Za-z][A-Za-z0-9+.\-]{1,}:/*", "", objetivo)
        return re.split(r"[/?#]", resto, maxsplit=1)[0] or objetivo
    base = os.path.basename(os.path.normpath(objetivo))
    return os.path.splitext(base)[0] if tipo == "programa" else base


# _ids_conocidas y _nueva_ventana BAJARON a linux_especiales (leen el arbol
# wmctrl/xdotool/swaymsg) => c._ids_conocidas() / c._nueva_ventana(...).


def cmd_abrir_linux(args):
    """Lanza app/URL/archivo SIN shell y (opcional) espera su ventana nueva.

    Mecanica (equivalente funcional del padre, refs linux-python.md §1):
      * PROGRAMA resuelto por shutil.which (PATH): subprocess.Popen
        [ruta] con start_new_session=True (desvinculado del terminal) y
        stdout/stderr → log en .tmp (cero mezclas con el JSON).
      * URL o ARCHIVO: xdg-open (xdg-utils: respeta asociaciones; maneja
        URL y archivo [runtime] en Wayland depende del portal/binario).
      * --esperar: sondeo 0.25 s de la lista de ventanas exigiendo id NUEVO
        con la pista en el titulo (xdotool search --name no se usa directo:
        se reutiliza _nueva_ventana, misma idea del snapshot hWnd de Windows).
    """
    if not (0 <= args.esperar <= 120):
        c.fail("--esperar debe estar entre 0 y 120 segundos (0 = no esperar).")
    if args.esperar_nueva and args.esperar <= 0:
        c.fail("--esperar-nueva exige --esperar N con N en 1..120 (es un "
               "sondeo por diff de ids, no un sueno).")
    tipo, resuelto = _clasificar_linux(args.objetivo)
    if tipo is None:
        c.fail("%r no es URL (esquema 'algo:' o 'www.'), ni programa "
               "resolvable por PATH, ni archivo existente. Revisa la "
               "ortografia o pasa la ruta absoluta." % args.objetivo)

    usar_popen = tipo == "programa"
    mecanica = ("Popen(shell=False, start_new_session=True)" if usar_popen
                else "xdg-open (asociaciones del escritorio)")
    pista = (args.titulo or "").strip() or _pista_por_defecto_linux(args.objetivo, tipo)
    previos = c._ids_conocidas() if args.esperar > 0 else set()

    proc = None
    log = None
    try:
        if usar_popen:
            os.makedirs(c.DIR_TMP, exist_ok=True)
            log = open(os.path.join(c.DIR_TMP, "abrir.log"), "ab")
            proc = subprocess.Popen([resuelto], shell=False,
                                    start_new_session=True,
                                    stdout=log, stderr=subprocess.STDOUT)
        else:
            ruta_xdg = c.require("xdg-open")
            proc = subprocess.Popen([ruta_xdg, resuelto], shell=False,
                                    start_new_session=True,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
    except OSError as exc:
        c.fail("Fallo al lanzar %r via %s: %s: %s"
               % (resuelto, mecanica, type(exc).__name__, exc),
               nota="si es una asociacion rota, probar el ejecutable real "
                    "directo")
    finally:
        if log is not None:
            log.close()

    resultado = {
        "ok": True,
        "accion": "abrir",
        "objetivo": args.objetivo,
        "tipo": tipo,
        "resuelto": resuelto,
        "mecanica": mecanica,
        "pid": proc.pid if proc else None,
        "log_hijo": os.path.join(c.DIR_TMP, "abrir.log") if usar_popen else None,
        "esperar_segundos": args.esperar,
        "sesion": c.deteccion_sesion(),
        "marco": c.MARCO,
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
    ids_nuevas = []
    c.checar_abort("espera de ventana")  # P1-6: el freno dura también aquí
    c.checar_pausa()                     # P1-5: con PAUSA la espera se posterga
    limite = time.time() + args.esperar
    if args.esperar_nueva:
        # IMPL-K P1.2-b: diff de ids sin pista (funciona con titulos
        # localizados; el patron que los drivers reescribieron 7 veces).
        while time.time() < limite:
            nuevas = c._nuevas_por_diff(previos)
            if nuevas:
                ventana = nuevas[0]
                ids_nuevas = [v.get("id") for v in nuevas]
                break
            c.checar_abort("espera de ventana nueva")
            time.sleep(0.25)
    else:
        while time.time() < limite:
            ventana = c._nueva_ventana(pista, previos)
            if ventana is not None:
                break
            c.checar_abort("espera de ventana")
            time.sleep(0.25)

    if ventana is not None and args.esperar_nueva:
        resultado["ids_nuevas"] = ids_nuevas
        resultado["ventana"] = c._item_canon(ventana,
                                           maximizada=ventana.get("maximizada"))
        resultado["nota"] = ("ventana NUEVA por diff de id (con "
                             "--esperar-nueva la pista %r se IGNORA): guarda "
                             "ventana.id y dirige la entrada con --foco-id / "
                             "las acciones con --id" % pista)
        c.json_out(resultado)
        return
    if ventana is not None:
        resultado["ventana"] = c._item_canon(ventana,
                                           maximizada=ventana.get("maximizada"))
        resultado["nota"] = ("ventana NUEVA con pista %r; rect en coords de "
                             "LAYOUT; item canonico rect+estado (maximizada "
                             "null en wayland/tiling); re-verifica el foco con "
                             "capturar" % pista)
    else:
        resultado["ventana"] = None
        if args.esperar_nueva:
            resultado["ids_nuevas"] = []
        nota = ("timeout de %d s sin ventana NUEVA con pista %r (NO es "
                "error): la app pudo abrir sin ventana, tardar mas, o "
                "REUTILIZAR su ventana (navegador con sesion). Verifica con "
                "listar o capturar." % (args.esperar, pista))
        if args.esperar_nueva:
            nota += " Tampoco aparecio NINGUN id nuevo: la app reutilizo " \
                    "ventana existente."
        if proc is not None and proc.poll() is not None:
            resultado["proceso_termino"] = proc.returncode
            nota += " El proceso lanzado ya termino (rc=%s)." % proc.returncode
        if not shutil.which("wmctrl") and c.deteccion_sesion() == "x11":
            nota += " (sin wmctrl/xdotool el sondeo de ventanas es ciego)"
        resultado["nota"] = nota
    c.json_out(resultado)

def construir_parser_linux():
    parser = c.Parser(
        prog="ventanas.py (linux)",
        description="Ventanas en Linux: X11 por wmctrl/xdotool (EWMH) y "
                    "Wayland por swaymsg/hyprctl. La coincidencia de titulo "
                    "es por subcadena; si hay varias, se exige el exacto. "
                    "Rectangulos en coords de LAYOUT.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_DOC_LINUX.split("Subcomandos:")[1] if _DOC_LINUX and "Subcomandos:" in _DOC_LINUX else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    sub.add_parser("listar", help="todas las ventanas con id, titulo, rect y "
                   "estado") .set_defaults(func=cmd_listar_linux)

    sub.add_parser("foco", help="ventana foreground: titulo, rect y estado") \
       .set_defaults(func=cmd_foco_linux)

    for nombre, ayuda, funcion in (
        ("activar", "traer y enfocar la ventana", cmd_activar_linux),
        ("minimizar", "minimizar (sway: move scratchpad)", cmd_minimizar_linux),
        ("restaurar", "volver del minimizado", cmd_restaurar_linux),
        ("maximizar", "maximizar (sway: fullscreen)", cmd_maximizar_linux),
        ("cerrar", "cerrar (ojo: posibles modales)", cmd_cerrar_linux),
    ):
        p = sub.add_parser(nombre, help=ayuda)
        p.add_argument("titulo", nargs="?",
                       help="titulo (o parte) unico (o sustituirlo por --id)")
        p.add_argument("--id", metavar="ID",
                       help="id de la ventana (clave 'id' de listar/foco: "
                            "X11 wmctrl 0x.../xdotool decimal; sway con_id): "
                            "comparacion numerica base 0, unico destino "
                            "estable")
        if nombre == "cerrar":
            p.add_argument("--descartar", action="store_true",
                           help="(solo Windows: el ladder anti-modal W11; en "
                                "Linux el modal es ventana aparte: cierrala "
                                "por su propio id)")
        p.set_defaults(func=funcion)

    p = sub.add_parser("mover", help="mover al monitor destino (xdotool "
                       "windowmove / sway 'move container to output') o a "
                       "--x --y en coords de LAYOUT")
    p.add_argument("titulo", nargs="?", help="titulo unico o --id")
    p.add_argument("--id", metavar="ID", help="id de la ventana (listar)")
    p.add_argument("--monitor", metavar="DESTINO",
                   help="indice, 'primario' o subcadena del nombre: vertice "
                        "sup-izq del output")
    p.add_argument("--x", type=int, metavar="X", help="X de layout (con --y; "
                   "X11)")
    p.add_argument("--y", type=int, metavar="Y", help="Y de layout")
    p.add_argument("--ancho", type=int, metavar="PX",
                   help="(sin primitiva auditada en Linux: error honesto)")
    p.add_argument("--alto", type=int, metavar="PX",
                   help="(sin primitiva auditada en Linux: error honesto)")
    p.set_defaults(func=cmd_mover_linux)

    p = sub.add_parser("ocupantes", help="que ventanas solapan la zona x1 y1 "
                       "x2 y2 en coords de LAYOUT (READ-ONLY)")
    p.add_argument("x1", type=int)
    p.add_argument("y1", type=int)
    p.add_argument("x2", type=int)
    p.add_argument("y2", type=int)
    p.set_defaults(func=cmd_ocupantes_linux)

    p = sub.add_parser("abrir", help="lanzar app/URL/archivo (Popen/xdg-open, "
                       "sin shell) y opcionalmente esperar su ventana nueva")
    p.add_argument("objetivo",
                   help="programa en PATH, URL ('https://...', 'mailto:...', "
                        "'www. ...') o ruta de archivo (se abre con su "
                        "asociacion)")
    p.add_argument("--esperar", type=int, default=0, metavar="SEGUNDOS",
                   help="sondear hasta que aparezca una ventana NUEVA con la "
                        "pista en el titulo (0 = no esperar; 1-120)")
    p.add_argument("--titulo", metavar="SUBCADENA",
                   help="pista del titulo a esperar; si se omite se deriva "
                        "del objetivo")
    p.add_argument("--esperar-nueva", dest="esperar_nueva",
                   action="store_true",
                   help="con --esperar N: elige por diff de id (ignora la "
                        "pista; titulos localizados ok); JSON con ventana.id "
                        "e ids_nuevas[]")
    p.set_defaults(func=cmd_abrir_linux)

    return parser


# ===========================================================================
# SECCION macOS — cmd_*/helpers de scripts/macos/ventanas.py (FASE SEG3) con
# sufijo _mac. BAJARON a scripts/macos/macos_especiales.py (ejecutan osascript
# y sus cuerpos AppleScript por clausura) y se llaman via c.<nombre>():
# _SEP, _LF, _CUERPO_LISTAR, _rmt_handler, osascript_multi, _listar_crudo,
# _buscar, _estado_item, _CUERPO_ACTIVAR/MINIMIZAR/RESTAURAR/CERRAR,
# _accion_ventana, _snapshot_pares. Los cmd_listar/cmd_foco DELEGAN en la
# libreria (no re-implementan AppleScript). NO bajan: los cmd_*,
# _clasificar_mac y _pista_por_defecto_mac (puros); el clasificador URL se usa
# via c.ESQUEMA_URL. NOTA VERBATIM: construir_parser_mac usaba —y conserva—
# argparse.ArgumentParser pelado (no c.Parser): los errores de parseo mac van
# por stderr historico, sin unificar.
# ===========================================================================

_DOC_MAC = """ventanas.py — Ventanas de macOS via osascript/System Events y `open`
(skill computer-use-py, dominio mac).

Ruta (contrato: todo corre sobre Python): subprocess propio a `osascript`
con datos de usuario SIEMPRE por argv — VERIFICADO man: los argumentos se
pasan como lista de strings al handler `run` (`on run argv` / `item 1 of
argv`); NUNCA se interpola texto en el codigo AppleScript (inyeccion). La
terminologia base es VERIFICADA en la guia Apple "Automating the User
Interface": `application process` (la clase process = app corriendo),
Processes Suite de System Events, `set frontmost to true`, `click` de
elementos; `name/position/size`, `minimized` y acciones "AXMinimize"/
"AXRaise" quedan [runtime] hasta cotejar el diccionario de System Events
del Mac.

Lanzar NO pasa por Terminal ni sh -c: `open` nativo (VERIFICADO man):
* APP:  open -a <app> (LaunchServices; tambien -b bundle-id)
* ARCHIVO/URL: open <ruta|URL> ("just as if you had double-clicked"),
  --args para pasar argv a la app sin que open lo interprete.
Popen con start_new_session=True: proceso desvinculado de la consola del
agente (su stdout no ensucia el JSON).

Limitaciones honestas del dominio:
* "maximizar" no existe en macOS: el boton verde hace ZOOM; sin accion
  documentada en la guia leida → el verbo existe (superficie identica) pero
  devuelve error JSON con la explicacion. [runtime]
* restaurar de minimizada: AppleScript no lo documenta; se intenta
  `set value of attribute "AXMinimized" to false` y, si falla, la via real
  es activar la app (macOS reintegra ventanas al activar [runtime]).
* la identidad de ventana no tiene hWnd: el snapshot de --esperar usa el
  par (app, titulo) — titulos duplicados pueden confundirlo (nota en JSON).

Salida: JSON por stdout; errores JSON con "error". Rectangulos en PUNTOS
LOGICOS del espacio global (mismo marco que capturas y raton.py).

Subcomandos:
  listar      Ventanas de apps visibles: app, titulo, rect, estado.
  foco        Proceso frontmost + ventana 1 (quien recibe el teclado).
  activar     set frontmost del proceso dueno de la ventana.
  minimizar   perform action "AXMinimize" [runtime].
  restaurar   Volver del minimizado (AXMinimized=false / activar app [runtime]).
  maximizar   sin equivalente en macOS: error honesto.
  cerrar      close window (--descartar: exclusivo Windows, error honesto).
  mover       set position de la ventana a --monitor o --x --y [runtime].
  ocupantes   solapes de una zona en puntos logicos (READ-ONLY).
  abrir       open -a|open <archivo|URL> + opcional --esperar ventana nueva
              (--esperar-nueva: diff del par app+titulo, sin pista).

Ejemplos (desde la carpeta computer-use-py, en el Mac):
  python3 scripts/ventanas.py listar
  python3 scripts/ventanas.py foco
  python3 scripts/ventanas.py activar "Sin título — TextEdit"
  python3 scripts/ventanas.py abrir TextEdit --esperar 8
  python3 scripts/ventanas.py abrir "https://example.com"
  python3 scripts/ventanas.py abrir "/tmp/informe.pdf" --esperar 8 --titulo informe
"""


# _CUERPO_LISTAR, _rmt_handler, osascript_multi, _listar_crudo, _buscar,
# _estado_item, _CUERPO_ACTIVAR/MINIMIZAR/RESTAURAR/CERRAR, _accion_ventana y
# _snapshot_pares BAJARON a macos_especiales (osascript) => c.<nombre>().


def cmd_listar_mac(args):
    regs = c._listar_crudo()
    c.json_out({
        "total": len(regs),
        "ventanas": [c._estado_item(r) for r in regs],
        "marco": c.MARCO,
        "unidad": "puntos logicos del espacio global",
        "nota": "rectangulos en PUNTOS (position/size de System Events "
                "[runtime]); item canonico rect+estado anidados; "
                "'maximizada' siempre null: macOS no maximiza (zoom con "
                "boton verde); 'activa' = proceso frontmost; los titulos se "
                "sanitizan sin los separadores \\x1f/\\x1e",
    })


def cmd_foco_mac(args):
    regs = c._listar_crudo()
    front = [r for r in regs if r["frontmost"]]
    if not front:
        c.json_out({
            "activa": None,
            "ventana": None,
            "marco": c.MARCO,
            "nota": "no hay ventana foreground (pantalla de bloqueo/permiso "
                    "TCC?): NO teclees aun; re-verifica con pantalla.py "
                    "capturar",
        })
        return
    r = front[0]
    item = c._estado_item(r)
    c.json_out({
        "activa": True,
        "titulo": item["titulo"],
        "app": item["app"],
        "rect": item["rect"],
        "estado": item["estado"],
        "ventana": item,
        "marco": c.MARCO,
        "unidad": "puntos logicos",
        "nota": "rect en puntos logicos; 'ventana' es el item canonico "
                "multi-rama; verifica con pantalla.py capturar despues de "
                "teclear (otro proceso puede robar el foco entre la lectura "
                "y la emision)",
    })


def _destino_mac(args, accion):
    """IMPL-K P0.1: la rama macOS NO expone id estable de ventana
    (System Events no tiene hWnd: ver macos_especiales._estado_item,
    'id': None; la identidad es el par (app, titulo)). --id N responde
    error JSON honesto [runtime]; el titulo sigue siendo el destino."""
    if getattr(args, "id", None) is not None:
        c.fail("%r --id no esta disponible en la rama macOS [runtime]: "
               "System Events no expone un id estable de ventana ('id' es "
               "null en el item canonico; la identidad es app+titulo). Usa "
               "el titulo posicional (preferiblemente UNICO, p. ej. el "
               "nombre del archivo)." % accion, requiere_id=args.id,
               hint="references/macos-python.md")
    if args.titulo is None:
        c.fail("%r exige el titulo posicional (la rama macOS no tiene "
               "destino por id)." % accion)
    return args.titulo


def cmd_activar_mac(args):
    c._accion_ventana(
        _destino_mac(args, "activar"), "activar", c._CUERPO_ACTIVAR,
        "el foco decide quien recibe el teclado: verifica con capturar; "
        "'AXRaise' es [runtime] y se omite en silencio si la app no lo "
        "soporta (el frontmost igual se aplico)")


def cmd_minimizar_mac(args):
    c._accion_ventana(
        _destino_mac(args, "minimizar"), "minimizar", c._CUERPO_MINIMIZAR,
        "accion AXMinimize [runtime: string por cotejar con el diccionario "
        "de System Events]; muchas apps minimizan al Dock: verifica con "
        "capturar")


def cmd_restaurar_mac(args):
    c._accion_ventana(
        _destino_mac(args, "restaurar"), "restaurar", c._CUERPO_RESTAURAR,
        "restaurar no es una primitiva de AppleScript: se probo "
        "AXMinimized=false [runtime]; si 'detalle' dice frontmost-only la "
        "ventana puede seguir en el Dock: clic en el Dock o menú Ventana "
        "de la app")


def cmd_maximizar_mac(args):
    c.fail("macOS no tiene 'maximizar': el boton verde hace ZOOM y no hay "
           "commando de System Events documentado en la guia leida. "
           "Alternativas: arrastrar la barra de titulo a tope (raton.py "
           "arrastrar), doble clic en la barra (zoom, segun ajuste del "
           "sistema [runtime]) o full-screen con cmd+ctrl+f (teclado.py "
           "combo). El rect se lee con listar.",
           pista="teclado.py combo \"cmd+ctrl+f\" para full-screen real")


def cmd_cerrar_mac(args):
    if args.descartar:
        c.fail("--descartar (ladder anti-modal) es de la rama Windows: el "
               "sheet de guardado de Notepad 11 vive en la misma HWND "
               "(leccion VERIFICADA W11). En macOS el sheet se ATTACH a la "
               "ventana "
               "y no hay ruta auditada aqui [runtime]: captura, resuelve el "
               "boton 'No Save' con teclado/clic y re-verifica con listar.",
               hint="teclado.py combo cmd+n / clic tras capturar")
        return
    c._accion_ventana(
        _destino_mac(args, "cerrar"), "cerrar", c._CUERPO_CERRAR,
        "muchas apps abren un dialogo modal al cerrar (guardar cambios?): "
        "verifica SIEMPRE con pantalla.py capturar")


def cmd_mover_mac(args):
    """Mover en mac = System Events `set position` (IMPL-K P1.1, [runtime]:
    sin verificacion en Mac real). Ojo la semantica del dominio: zoom !=
    maximizar; 'mover' aqui reposiciona el vertice sup-izq en PUNTOS."""
    titulo = _destino_mac(args, "mover")
    if args.monitor is not None and args.x is not None:
        c.fail("mover: --monitor y --x/--y son excluyentes (elige destino).")
    if args.monitor is not None:
        m = _resolver_monitor_mac(args.monitor)
        if m is None:
            c.fail("'mover --monitor' no acepta 'virtual': exige un display "
                   "concreto.")
        if m["izq"] is None:
            c.fail("El mapa de monitores (System Events sin Quartz) no da "
                   "posiciones: instala pyobjc-framework-Quartz o usa "
                   "--x --y con puntos medidos en capturar.")
        x, y = m["izq"], m["top"]
    elif args.x is not None or args.y is not None:
        if args.x is None or args.y is None:
            c.fail("mover: --x e --y van juntos (puntos logicos).")
        x, y = int(args.x), int(args.y)
    else:
        c.fail("mover exige --monitor <indice|primario|nombre> O el par "
               "--x --y (puntos logicos).")
    c._mover_ventana_mac(titulo, x, y, args.ancho, args.alto)


def cmd_ocupantes_mac(args):
    """Ventanas que solapan la zona en PUNTOS LOGICOS (READ-ONLY; IMPL-K
    P1.2-f)."""
    if args.x2 <= args.x1 or args.y2 <= args.y1:
        c.fail("ocupantes exige x2 > x1 e y2 > y1 (rectangulo de puntos "
               "logicos [x1,y1]..[x2,y2)).")
    regs = c._listar_crudo()
    items = c._ocupantes_mac_zona(regs, args.x1, args.y1, args.x2, args.y2)
    c.json_out({
        "ok": True,
        "accion": "ocupantes",
        "zona": [args.x1, args.y1, args.x2, args.y2],
        "centro_zona": [(args.x1 + args.x2) // 2, (args.y1 + args.y2) // 2],
        "totales_visibles": len(regs),
        "ventanas": items,
        "via": "osascript",
        "marco": c.MARCO,
        "unidad": "puntos logicos",
        "nota": "READ-ONLY (no emite accion): 'id' es null en mac (sin "
                "hWnd): identifica por app+titulo; zonas con solapa no son "
                "libres para clic/arrastre sin revisar",
    })


# --- abrir ---------------------------------------------------------------

# Esquema de URL: >=2 letras/digitos y +-. antes de ':' (descarta "C:\\ruta"
# del dominio Windows; en mac tambien "file:") o prefijo "www.". La seccion
# usa c.ESQUEMA_URL directo (alias del clasificador generico de _core).


def _clasificar_mac(objetivo):
    """(tipo, resuelto): 'url' | 'archivo' | 'app' | (None, None).

    Orden: esquema URL o 'www.' (man: URL se abre como URL); ruta existente
    (man: open abre archivos/directorios con su app por defecto); si no, se
    intenta como app via open -a (LaunchServices resuelve nombre o ruta de
    .app). Devuelve (None, None) si no existe ni como archivo: el error de
    open -a con nombre inexistente se captura al ejecutar.
    """
    if c.ESQUEMA_URL.match(objetivo):
        return "url", objetivo
    if os.path.exists(objetivo):
        return "archivo", os.path.abspath(objetivo)
    return "app", objetivo


def _pista_por_defecto_mac(objetivo, tipo):
    """Pista de titulo derivada del objetivo (orientativa; ante titulos
    localizados usa --titulo explicito)."""
    if tipo == "url":
        resto = re.sub(r"^[A-Za-z][A-Za-z0-9+.\-]{1,}:/*", "", objetivo)
        if re.match(r"^[A-Za-z]:[\\/]", resto) or resto.startswith("/"):
            return os.path.basename(resto) or objetivo
        return re.split(r"[/?#]", resto, maxsplit=1)[0] or objetivo
    base = os.path.basename(os.path.normpath(objetivo))
    return os.path.splitext(base)[0] if tipo == "app" else base


def cmd_abrir_mac(args):
    if not (0 <= args.esperar <= 120):
        c.fail("--esperar debe estar entre 0 y 120 segundos (0 = no "
               "esperar).")
    if args.esperar_nueva and args.esperar <= 0:
        c.fail("--esperar-nueva exige --esperar N con N en 1..120 (es un "
               "sondeo por diff de pares, no un sueno).")
    tipo, resuelto = _clasificar_mac(args.objetivo)
    if tipo == "app" and not resuelto:
        c.fail("%r no es URL, ni archivo existente, ni nombre de app."
               % args.objetivo)
    if tipo == "url":
        cmd = ["open", resuelto]
        mecanica = "open <URL> (LaunchServices: navegador por defecto; " \
                   "VERIFICADO man)"
    elif tipo == "archivo":
        cmd = ["open", resuelto]
        mecanica = "open <ruta> (asociacion LaunchServices; VERIFICADO man)"
    else:
        cmd = ["open", "-a", resuelto]
        if args.extra_args:
            cmd += ["--args"] + list(args.extra_args)
        mecanica = "open -a <app> (VERIFICADO man; -b si es bundle-id)"

    pista = (args.titulo or "").strip() or _pista_por_defecto_mac(args.objetivo,
                                                               tipo)
    previos = c._snapshot_pares() if args.esperar > 0 else set()

    proc = None
    try:
        # start_new_session: desvincular del proceso terminal del agente
        # (heredaria senales y su salida podria ensuciar el JSON).
        proc = subprocess.Popen(cmd, start_new_session=True)
    except OSError as exc:
        c.fail("Fallo al lanzar %r via %s: %s: %s"
               % (resuelto, mecanica, type(exc).__name__, exc),
               nota="si es una app: prueba el nombre exacto de /Applications "
                    "o la ruta completa del .app; si es bundle-id usa -b")
    if tipo == "app":
        # 'open' sin -W termina tras delegar en LaunchServices: si la app no
        # existe, su rc no-zero llega rapido (lo capturamos; en exito rc=0).
        try:
            rc_open = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            rc_open = None
        if rc_open:
            c.fail("open -a %r retorno %d: la app no existe o "
                   "LaunchServices no la resuelve." % (resuelto, rc_open),
                   nota="usa el nombre exacto de /Applications, la ruta "
                        "completa del .app, o el bundle-id via 'open -b' "
                        "(MAN verificado: -a app, -b bundle_identifier)")

    resultado = {
        "ok": True,
        "accion": "abrir",
        "objetivo": args.objetivo,
        # P0-2 (CRITICO): enum canónico tipo ∈ {url,programa,archivo} en las 3
        # ramas; la clasificación interna de mac ('app' via open -a) se mapea
        # a "programa" y se conserva como extension tipo_mac.
        "tipo": "programa" if tipo == "app" else tipo,
        "tipo_mac": tipo,
        "resuelto": resuelto,
        "mecanica": mecanica,
        "via": "open",
        "pid": proc.pid if proc else None,
        "pid_nota": "el pid es del proceso 'open': la app destino puede "
                    "ser otra (LaunchServices): busca la ventana por titulo",
        "esperar_segundos": args.esperar,
        "marco": c.MARCO,
    }
    if args.esperar == 0:
        resultado["ventana"] = None
        resultado["nota"] = ("lanzado sin esperar la ventana (--esperar 0): "
                             "verifica con pantalla.py capturar o "
                             "ventanas.py listar")
        c.json_out(resultado)
        return

    resultado["pista_titulo"] = pista
    nuevo = None
    pares_nuevos = []
    c.checar_abort()
    c.checar_pausa()  # P1-5/P1-6: el freno dura durante la espera
    limite = c.time.time() + args.esperar
    while c.time.time() < limite:
        try:
            regs = c._listar_crudo()
        except SystemExit:
            raise
        except Exception:
            regs = []  # osascript fallo puntual: seguir sondeando
        nuevas = [r for r in regs
                  if (r["app"], r["titulo"]) not in previos
                  and (args.esperar_nueva
                       or pista.lower() in r["titulo"].lower())]
        if nuevas:
            nuevo = nuevas[0]
            pares_nuevos = [[r["app"], r["titulo"]] for r in nuevas]
            break
        c.checar_abort()
        # TIEMPOS-K: 0.5->0.4 (-20%, piso ok): cadencia del sondeo abrir-mac
        # (diff del par app+titulo via osascript, caro: bajarlo mas no aporta).
        c.time.sleep(0.4)

    if nuevo is not None and args.esperar_nueva:
        resultado["ventana"] = c._estado_item(nuevo)
        resultado["ids_nuevas"] = None  # mac: sin hWnd honesto (P0.1)
        resultado["pares_nuevos"] = pares_nuevos
        resultado["via"] = "open|osascript"
        resultado["nota"] = ("ventana NUEVA por diff del par (app, titulo) "
                             "— con --esperar-nueva la pista se IGNORA. 'id' "
                             "sigue siendo null: macOS no expone hWnd; "
                             "identificate por app+titulo y verifica foco "
                             "con capturar")
        c.json_out(resultado)
        return
    if nuevo is not None:
        resultado["ventana"] = c._estado_item(nuevo)
        resultado["via"] = "open|osascript"
        resultado["nota"] = ("ventana NUEVA (par app+titulo no visto antes) "
                             "con pista %r; rect en puntos logicos y "
                             "'activa' dice si ya recibe el teclado "
                             "(re-verifica con pantalla.py capturar)" % pista)
    else:
        try:
            pre = len([r for r in c._listar_crudo()
                       if pista.lower() in r["titulo"].lower()])
        except Exception:
            pre = None
        resultado["ventana"] = None
        if args.esperar_nueva:
            resultado["ids_nuevas"] = None  # mac sin hWnd: honesto
            resultado["pares_nuevos"] = []
            nota_extra = " Tampoco aparecio NINGUN par (app, titulo) nuevo."
        else:
            nota_extra = ""
        resultado["preexistentes_con_pista"] = pre
        nota = ("timeout de %d s sin ventana NUEVA con pista %r (NO es "
                "error): la app pudo abrir sin ventana, tardar mas, o "
                "REUTILIZAR su ventana (navegador, documento ya abierto): "
                "en mac la identidad es (app, titulo), no hay hWnd. "
                "Verifica con listar o capturar." % (args.esperar, pista))
        nota += nota_extra
        if proc is not None and proc.poll() is not None and proc.returncode:
            resultado["open_rc"] = proc.returncode
            nota += " El proceso 'open' termino con rc=%s." % proc.returncode
        resultado["nota"] = nota
    c.json_out(resultado)

def construir_parser_mac():
    parser = argparse.ArgumentParser(
        prog="ventanas.py (macOS)",
        description="Listar y manejar ventanas de macOS via "
                    "osascript/System Events (datos siempre por argv) y "
                    "lanzar con `open` nativo. Coincidencia de titulo por "
                    "subcadena; si hay varias, se exige el titulo exacto. "
                    "Rectangulos en PUNTOS LOGICOS del espacio global.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_DOC_MAC.split("Subcomandos:")[1]
        if _DOC_MAC and "Subcomandos:" in _DOC_MAC else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True,
                                metavar="SUBCOMANDO")

    sub.add_parser("listar", help="todas las ventanas con app, titulo, "
                   "rectangulo y estado").set_defaults(func=cmd_listar_mac)

    sub.add_parser("foco", help="ventana foreground: app, titulo, rect y "
                   "estado").set_defaults(func=cmd_foco_mac)

    for nombre, ayuda, funcion in (
        ("activar", "set frontmost del proceso dueno", cmd_activar_mac),
        ("minimizar", "minimizar la ventana (AXMinimize [runtime])",
         cmd_minimizar_mac),
        ("restaurar", "restaurar desde minimizada (intentos AX)",
         cmd_restaurar_mac),
        ("maximizar", "no existe en macOS: error honesto con alternativas",
         cmd_maximizar_mac),
        ("cerrar", "cerrar la ventana (ojo: posibles modales)", cmd_cerrar_mac),
    ):
        p = sub.add_parser(nombre, help=ayuda)
        p.add_argument("titulo", nargs="?",
                       help="titulo (o parte) de la ventana; debe ser unico")
        p.add_argument("--id", type=int, metavar="N",
                       help="(sin ruta en macOS: error JSON honesto [runtime]"
                            " — no hay hWnd; usa el titulo)")
        if nombre == "cerrar":
            p.add_argument("--descartar", action="store_true",
                           help="(ladder anti-modal exclusivo de Windows: en "
                                "mac responde error honesto [runtime])")
        p.set_defaults(func=funcion)

    p = sub.add_parser("mover", help="mover a --monitor o a --x --y (System "
                       "Events 'set position' [runtime])")
    p.add_argument("titulo", nargs="?", help="titulo unico (no hay --id en mac)")
    p.add_argument("--id", type=int, metavar="N",
                   help="(sin ruta en macOS: error honesto [runtime])")
    p.add_argument("--monitor", metavar="DESTINO",
                   help="indice, 'primario' o subcadena del nombre")
    p.add_argument("--x", type=int, metavar="X", help="punto logico X (con --y)")
    p.add_argument("--y", type=int, metavar="Y", help="punto logico Y")
    p.add_argument("--ancho", type=int, metavar="PT",
                   help="nuevo ancho en puntos (con --alto)")
    p.add_argument("--alto", type=int, metavar="PT", help="nuevo alto")
    p.set_defaults(func=cmd_mover_mac)

    p = sub.add_parser("ocupantes", help="que ventanas solapan la zona x1 y1 "
                       "x2 y2 en puntos logicos (READ-ONLY)")
    p.add_argument("x1", type=int)
    p.add_argument("y1", type=int)
    p.add_argument("x2", type=int)
    p.add_argument("y2", type=int)
    p.set_defaults(func=cmd_ocupantes_mac)

    p = sub.add_parser(
        "abrir", help="lanzar app/archivo/URL con `open` y opcionalmente "
                      "esperar su ventana nueva (via open|osascript)")
    p.add_argument("objetivo",
                   help="app (nombre o ruta .app), URL ('https://...', "
                        "'mailto:...', 'www...') o ruta de archivo "
                        "(LaunchServices decide la app)")
    p.add_argument("--extra-args", dest="extra_args", nargs="*",
                   metavar="ARG",
                   help="argumentos para la app lanzada con open -a "
                        "(via --args del man open)")
    p.add_argument("--esperar", type=int, default=0, metavar="SEGUNDOS",
                   help="sondear hasta que aparezca una ventana NUEVA con "
                        "la pista en el titulo (0 = no esperar; 1-120)")
    p.add_argument("--titulo", metavar="SUBCADENA",
                   help="pista del titulo a esperar; si se omite se deriva "
                        "del objetivo")
    p.add_argument("--esperar-nueva", dest="esperar_nueva",
                   action="store_true",
                   help="con --esperar N: elige por diff del par (app, "
                        "titulo), ignora la pista; 'ids_nuevas' es null "
                        "(mac sin hWnd) y llega 'pares_nuevos'")
    p.set_defaults(func=cmd_abrir_mac)

    return parser


# ===========================================================================
# main() UNIFICADO (FASE SEG3): dispatch en tiempo de ejecucion por
# sys.platform; `c` se bind-ea al modulo de primitivas del SO.
# ===========================================================================


def main():
    global c, _ESQUEMA_URL
    mod = _core.modulo_sistema()            # lee sys.platform EN TIEMPO DE EJECUCION
    if mod is None:
        _core.so_no_soportado("ventanas.py") # JSON rc 2 (nunca retorna)
    c = mod
    plat = sys.platform
    if plat == "win32":
        global pyautogui, gw                 # imports exclusivos Windows (eran top)
        import pyautogui                     # glue ya fijo DPI + FAILSAFE + PAUSE
        import pygetwindow as gw
        _ESQUEMA_URL = c.ESQUEMA_URL         # era asignacion de top con c
        parser = construir_parser()
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
        # Historico por rama: solo la win capturaba pyautogui.FailSafeException.
        if plat == "win32" and isinstance(exc, pyautogui.FailSafeException):
            c.fallar_por_failsafe(exc)
        c.fail("%s: %s" % (type(exc).__name__, exc))


if __name__ == "__main__":
    main()
