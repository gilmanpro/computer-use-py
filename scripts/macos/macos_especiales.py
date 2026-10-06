# -*- coding: utf-8 -*-
"""macos_especiales.py — Libreria EXCLUSIVA de macOS + CLI de diagnostico
solo-macos (skill computer-use-py, dominio mac; NO importa al glue_windows.py
de la raiz).

FASE SEG3 — UNICO archivo de scripts/macos/. La entrada normal es
scripts/<verbo>.py (raiz, multi-OS): en macOS ejecuta la ruta de tu SO EN EL
PROPIO PROCESO e importa ESTE modulo como libreria (via
_core.modulo_sistema(), bindeado por el CLI como `c`). Simetrico a
scripts/windows/win_especiales.py y scripts/linux/linux_especiales.py.
Contiene TODAS las primitivas exclusivas de macOS (osascript, screencapture,
system_profiler, cliclick, open, monitores Quartz, tablas kVK_/alias darwin,
escalas Retina, failsafe emulado y los cuerpos AppleScript de ventanas),
reexporta los genericos de scripts/_core.py y conserva VERBATIM los cuerpos
que bajaron de los antiguos CLIs de rama (particion, no reinvencion).
Los pyobjc/Quartz/pynput/PIL van SIEMPRE lazy dentro de funciones.

IMPORTABLE EN CUALQUIER SO: importar este modulo NO imprime ni hace
sys.exit; el guard "dominio EXCLUSIVO de MACOS" con rc=2 vive SOLO en el
__main__ de este CLI y responde ANTES de parsear.

CONTRACT: TODO corre sobre Python. Cuando un script invoca por subprocess a
herramientas del SO (screencapture, osascript, open) sigue siendo codigo
Python quien las llama: la superficie del agente es Python + JSON identico
al dominio Windows. Ver references/macos-python.md.

Efectos de borde deliberados:
1. Sin DPI: macOS no tiene API de DPI; Cocoa/Quartz trabajan en PUNTOS
   logicos. El equivalente del problema Windows es RETINA 2x: lo resuelve
   escala_retina() y la regla que TODAS las capturas exponen en JSON.
2. Marco de coordenadas: PUNTOS LOGICOS del espacio global. Origen (0,0) =
   vertice sup-izq del display PRINCIPAL (VERIFICADO fuente pynput 1.8.2
   mouse/_darwin.py:73-76: NSEvent.mouseLocation se revierte con
    CGDisplayPixelsHigh(0) al marco Quartz top-left). Monitores a la
    izquierda/arriba pueden dar origenes NEGATIVOS [runtime: verificar con
   monitores.py listar; NINGUN script asume el signo: lee los rects reales].
3. FAILSAFE pyautogui NO existe aqui (esta skill no usa pyautogui en mac).
   Freno humano equivalente: vigilar.py (listener pynput de ESC no inyectado
   que crea la bandera .tmp/ABORT [runtime en cuanto a TCC]) y la emulacion
   de esquinas del display principal en raton.py (guard de la skill, no API
   del SO [runtime]).
4. Salida: todo por stdout es JSON; los errores son JSON con la clave
   "error" y codigo de salida 1 (el guard del CLI en otro SO: rc 2).

Subcomandos:
  (CLI propio SOLO-macos; como libreria se importa, no se ejecuta)
  tcc              catalogo de hints de permisos TCC (HINT_ERRORES verbatim)
  screencapture    PNG crudo a archivo: --rect x y w h y/o --display N
                   [--archivo destino]
  monitores-quartz listado CRUDO via CGGetActiveDisplayList (sin fallback)
  ventanas-se      listado CRUDO de System Events via osascript
  open <objetivo>  lanzar via `open` nativo (--app usa open -a)

Ejemplos (desde la carpeta computer-use-py, en el Mac):
  python3 scripts/macos/macos_especiales.py tcc
  python3 scripts/macos/macos_especiales.py screencapture --rect 0 0 800 600
  python3 scripts/macos/macos_especiales.py monitores-quartz
  python3 scripts/macos/macos_especiales.py ventanas-se
  python3 scripts/macos/macos_especiales.py open "https://example.com"
"""

# FASE SEG3: lo identico a las otras ramas (Parser, banderas ABORT/PAUSA,
# validaciones de args, bucles de espera, color/combos, geometria de rects,
# convencion de destino de capturas, tablas comunes) vive en
# scripts/_core.py y se REEXPORTA abajo; aqui quedan los glue propios
# de macOS (osascript/screencapture/Quartz, tablas kVK_/alias darwin,
# escalas Retina y el failsafe emulado) y —desde SEG3— las primitivas
# exclusivas que los CLIs de rama (monitores/pantalla/raton/teclado/
# ventanas) bajaron a esta libreria por la regla de frontera, con sus
# cuerpos VERBATIM. Los textos canonicos compartidos son los de la rama
# WINDOWS (validada en vivo): donde mac decia "reanuda" ahora el mensaje
# unico dice "relanza" (anotado en el reporte FASE SEG).

import argparse
import json
import os
import re  # (SEG3) requerido por _mons_profiler/_mons_osascript, movados
import subprocess
import sys
import time  # reexportado: los scripts duermen con `c.time.sleep(...)`

# --- Guard de plataforma (SEG3: SOLO en el CLI, NUNCA en el import) --------
# scripts/macos/ es el MOTOR EXCLUSIVO de macOS, pero desde SEG3 este modulo
# es LIBRERIA importable en cualquier SO (los pyobjc/pynput/PIL van lazy y
# _core es stdlib puro): al importarse no imprime ni sys.exit. El guard que
# en otro SO responde el JSON canonico con rc 2 vive en el bloque __main__
# al final del archivo (los CLIs raiz ejecutan la ruta de tu SO en el propio
# proceso y llaman a esta libreria; nunca al reves).

# La consola arranca en codepage local y los JSON llevan tildes, enes y
# titulos de ventana variados: forzar UTF-8 con reemplazo.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --- Helpers stdlib-puro compartidos (SPEC P2-1) --------------------------
# _core.py vive en scripts/ (padre de linux/ y macos/): stdlib-puro, seguro
# en cualquier SO. Se reexporta aqui (comportamiento IDENTICO al historico);
# json_out/fail inyectan `plataforma: "darwin"` automaticamente (P0-4).
_DIR_PADRE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _DIR_PADRE not in sys.path:
    sys.path.insert(0, _DIR_PADRE)
import _core  # noqa: E402

RAIZ_SKILL = _core.RAIZ_SKILL
DIR_TMP = _core.DIR_TMP
DIR_CAPTURAS = _core.DIR_CAPTURAS
ARCHIVO_ABORT = _core.ARCHIVO_ABORT
ARCHIVO_PAUSA = _core.ARCHIVO_PAUSA

json_out = _core.json_out
fail = _core.fail
tocar = _core.tocar
borrar = _core.borrar
asegurar_capturas = _core.asegurar_capturas
plataforma = _core.plataforma
Parser = _core.Parser
checar_abort = _core.checar_abort
checar_pausa = _core.checar_pausa
checar_aborto_espera = _core.checar_aborto_espera
dormir = _core.dormir
esperar_color = _core.esperar_color
cap_ms = _core.cap_ms
cap_timeout_esperar = _core.cap_timeout_esperar
cap_segundos_mantener = _core.cap_segundos_mantener
cap_duracion = _core.cap_duracion
validar_segundos = _core.validar_segundos
validar_tolerancia = _core.validar_tolerancia
validar_confidence = _core.validar_confidence
checar_max_lado = _core.checar_max_lado
checar_args_esperar = _core.checar_args_esperar
parsear_color = _core.parsear_color
tiene_no_ascii = _core.tiene_no_ascii
partes_combo = _core.partes_combo
resolver_monitor = _core.resolver_monitor
monitor_contiene = _core.monitor_contiene
dentro_del_bounding = _core.dentro_del_bounding
bounding_de = _core.bounding_de
escalas_thumbnail = _core.escalas_thumbnail
ruta_destino_captura = _core.ruta_destino_captura
ALIAS_TECLAS_PYNPUT = _core.ALIAS_TECLAS_PYNPUT
ESQUEMA_URL = _core.ESQUEMA_URL
BOTONES = _core.BOTONES

# Marco canonico de la rama (P0-4): puntos logicos de Cocoa/Quartz.
MARCO = "puntos_logicos"

# Parser/checar_abort/checar_pausa/checar_aborto_espera: movidos a _core como
# copias identicas de las 3 ramas (el default motivo='interrumpido' preserva
# el mensaje historico de mac, que llamaba a checar_abort() sin argumentos).
# ALIAS_TECLAS_PYNPUT reexportada NO se usa en esta rama: darwin tiene su
# propio enum Key (ALIAS_TECLAS_MAC + tecla_pynput_mac mas abajo, especficos).
# (argparse se importa arriba solo por RawDescriptionHelpFormatter del CLI
#  propio; la clase Parser generica vive en scripts/_core.py.)

# --- Alias propio (SEG3) ---------------------------------------------------
# Los cuerpos movados VERBATIM de los antiguos CLIs de rama llamaban a las
# primitivas como `c.X()` (donde c era _compartido_mac). Este modulo ES la
# continuacion de ese modulo, asi que `c` apunta al PROPIO modulo: las
# llamadas `c.monitores_logicos()`, `c.osascript()`, `c.fail()`, `c.MARCO`...
# siguen resolviendo sin reescribir los cuerpos (particion, no reinvencion).
# Solo cambian las referencias a funciones que eran de OTRO modulo de rama
# (p. ej. monitores._colectar() → c._colectar(): ahora conviven aqui).
c = sys.modules[__name__]

# --- osascript: argv SIEMPRE, nunca f-strings con texto del usuario ------
# VERIFICADO man osascript(1): "Any arguments following the script will be
# passed as a list of strings to the direct parameter of the 'run' handler"
# (ejemplo on run argv / item 1 of argv). Inyectar texto del usuario en el
# codigo AppleScript es riesgo de inyeccion: los datos viajan SOLO por argv.

HINT_ERRORES = (
    # (patron en stderr, pista para el agente). Numeros AppleScript [runtime:
    # el man no los lista; son la convencion comunitaria de AppleEvents].
    ("-1743", "TCC Automatizacion denegada: Preferencias del Sistema > Seguridad "
              "y privacidad > Automatizacion: permitir que este Python (o la app "
              "terminal) controle 'System Events'; si el checkbox no aparece, "
              "restaurar acceso con: tccutil reset AppleEvents"),
    ("-1712", "errAETimeout: System Events no contesto a tiempo. La app puede "
              "estar colgada o sin ventanas; reintenta y verifica con capturar"),
    ("-1719", "errAEEventNotHandled / no conectado: el evento o accion no es "
              "aplicable a ese elemento (p. ej. AXMinimize en apps sin ventanas "
              "miniaturizables); re-lista con ventanas.py listar"),
    ("-1728", "errOSASystemNotResponsive / 'no puede obtener' el objeto: la "
              "ventana o app ya no existe o TCC lo bloquea; re-lista ventanas"),
    ("-25211", "osascript sin permiso de Accesibilidad para enviar teclas: "
               "Seguridad y privacidad > Accesibilidad: habilita este binario "
               "Python (o Terminal) [numero reportado por la comunidad: runtime]"),
    ("(-600)", "errProcNotFound: la aplicacion destino no esta corriendo; "
               "lanza con ventanas.py abrir"),
)


def hint_error(texto):
    """Pista accionable si stderr de osascript contiene un numero conocido."""
    for patron, pista in HINT_ERRORES:
        if patron in texto:
            return pista
    return None


def osascript(codigo, args=None, timeout=60):
    """Ejecuta `codigo` AppleScript como cuerpo de `on run argv` con `args`.

    VERIFICADO man osascript(1): multiple -e construyen el script y los
    argumentos posteriores se pasan como lista de strings al handler run.
    Devuelve (rc, stdout, stderr) con stdout/stderr en UTF-8.
    """
    cmd = ["osascript", "-e", "on run argv", "-e", codigo, "-e", "end run"]
    for a in (args or []):
        cmd.append(str(a))
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        fail("osascript no esta en el PATH: estos scripts solo corren en macOS "
             "(herramienta preinstalada del SO).")
    except subprocess.TimeoutExpired:
        fail("osascript excedio %d s (errAETimeout tipico si el dialogo TCC "
             "espera respuesta humana): aprueba el permiso y reintenta." % timeout,
             pista=HINT_ERRORES[0][1])
    out = (p.stdout or b"").decode("utf-8", errors="replace").strip()
    err = (p.stderr or b"").decode("utf-8", errors="replace").strip()
    return p.returncode, out, err


def osascript_valor(codigo, args=None, accion="osascript", timeout=60):
    """osascript que DEVE devolver texto: si rc!=0, fail() JSON con hint mapeado."""
    rc, out, err = osascript(codigo, args, timeout=timeout)
    if rc != 0:
        fail("Error de %s: %s" % (accion, err or out or ("rc=%d" % rc)),
             rc=rc, hint=hint_error(err or out))
    return out


def osascript_ok(codigo_argv, args=None, accion="osascript", timeout=60):
    """Convencion OK:/ERR: para operaciones que deben reportar exito propio.

    `codigo_argv` es la PLANTILLA del cuerpo (usa `argv`), que debe retornar
    "OK:..." para el exito o "ERR:<num>:<msg>" en el try/on error. Se envuelve
    con try/on error para capturar excepciones AppleScript como ERR:.
    Devuelve (ok, payload_o_error_dict).
    """
    cuerpo = ("try\n" + codigo_argv +
              "\n on error errMsg number errNum\n"
              "  return \"ERR:\" & errNum & \":\" & errMsg\n"
              "end try")
    rc, out, err = osascript(cuerpo, args, timeout=timeout)
    if rc != 0:
        return False, {"error": err or out or ("rc=%d" % rc),
                       "hint": hint_error(err or out)}
    if out.startswith("OK:"):
        return True, out[3:]
    if out.startswith("ERR:"):
        partes = out[4:].split(":", 1)
        num = partes[0] if partes else "?"
        msg = partes[1] if len(partes) > 1 else ""
        return False, {"error": "AppleScript %s: %s" % (num, msg),
                       "numero": num, "hint": hint_error(out)}
    return False, {"error": "respuesta inesperada de osascript: %r" % out[:200]}


# --- Deteccion de librerias (piramide del dominio mac) ------------------

def try_pynput():
    """Importa pynput.keyboard o falla con el hint pip de la via pynput."""
    try:
        from pynput import keyboard
        return keyboard
    except ImportError:
        fail("Falta pynput (via primaria del teclado en macOS): "
             "python3 -m pip install pynput==1.8.2. Sin el, la via osascript "
             "requiere el diccionario de System Events y permiso TCC "
             "Automatizacion+Accesibilidad (references/macos-python.md §3).")


def try_quartz():
    """Importa Quartz (pyobjc) o falla con el hint pip de la via pyobjc."""
    try:
        import Quartz
        return Quartz
    except ImportError:
        fail("Falta pyobjc-framework-Quartz (via pyobjc del dominio mac): "
             "python3 -m pip install pyobjc-framework-Quartz (PyPI 12.2.2, "
             "requiere Python >= 3.10 en macOS; necesita Xcode Command Line "
             "Tools). references/macos-python.md §11.")


def pil_open(ruta):
    """Abre un PNG con PIL Image; fail con hint si falta Pillow."""
    try:
        from PIL import Image
    except ImportError:
        fail("Falta Pillow (lectura de PNG para escala/pixel): "
             "python3 -m pip install pillow")
    return Image.open(ruta)


# --- Mapa de monitores en PUNTOS LOGICOS (via pyobjc Quartz) ------------
# VERIFICADO patron de uso en pyautogui 0.9.54 _pyautogui_osx.py:301
# (CGDisplayPixelsWide/High + CGMainDisplayID) y en pynput _darwin.py
# (CGDisplayPixelsHigh(0) como alto del espacio a voltear). La forma exacta
# de la tupla devuelta por CGGetActiveDisplayList via pyobjc varia segun
# version: se lee de forma defensiva [runtime].

def quartz_disponible():
    try:
        import Quartz  # noqa: F401
        return True
    except ImportError:
        return False


def monitores_logicos():
    """Monitores activos via Quartz, en puntos logicos del espacio global.

    Cada entrada: numero (CGDirectDisplayID), nombre (NSScreen.localizedName
    si AppKit responde [runtime], else 'CGDisplay-<id>'), indice,
    izq/top/der/bot (CGDisplayBounds; negativos posibles [runtime]),
    ancho/alto, work (= bounds: no hay API publica de 'area util' en macOS
    [runtime]) y primario (CGDisplayIsMain). Orden: principal primero y luego
    el resto por numero [runtime: no garantizado estable entre sesiones].
    """
    Q = try_quartz()
    res = Q.CGGetActiveDisplayList(64, None, None)
    ids = None
    if isinstance(res, tuple):
        for elem in res:
            if isinstance(elem, (list, tuple)) and all(
                    isinstance(v, int) for v in elem) and len(elem) > 0:
                ids = [int(v) for v in elem]
                break
        if ids is None:
            # variante pyobjc: (status, [ids...]) o (status, ids, count)
            for elem in res:
                if isinstance(elem, (list, tuple)):
                    ids = [int(v) for v in elem]
                    break
    elif isinstance(res, (list, tuple)):
        ids = [int(v) for v in res]
    if not ids:
        fail("CGGetActiveDisplayList no devolvo displays (res=%r): sin sesion "
             "grafica Aqua o API degradada [runtime]." % (res,))
    nombres = _nombres_nsscreen()
    main_id = int(Q.CGMainDisplayID())
    out = []
    for d in ids:
        b = Q.CGDisplayBounds(d)
        x = int(round(float(b.origin.x)))
        y = int(round(float(b.origin.y)))
        w = int(round(float(b.size.width)))
        h = int(round(float(b.size.height)))
        out.append({
            "numero": d,
            "nombre": nombres.get(d, "CGDisplay-%d" % d),
            "izq": x, "top": y, "der": x + w, "bot": y + h,
            "ancho": w, "alto": h,
            "work": [x, y, x + w, y + h],
            "primario": d == main_id or bool(Q.CGDisplayIsMain(d)),
        })
    out.sort(key=lambda m: (not m["primario"], m["numero"]))
    for i, m in enumerate(out):
        m["indice"] = i
    return out


def _nombres_nsscreen():
    """{CGDirectDisplayID: localizedName} via AppKit [runtime]; {} si falla."""
    try:
        from AppKit import NSScreen
    except Exception:
        return {}
    mapa = {}
    try:
        for s in NSScreen.screens():
            try:
                did = int(s.deviceDescription()["NSScreenNumber"])
                mapa[did] = str(s.localizedName())
            except Exception:
                continue
    except Exception:
        return {}
    return mapa


def tamano_pantalla():
    """(ancho, alto) en PUNTOS LOGICOS del display principal."""
    Q = try_quartz()
    b = Q.CGDisplayBounds(Q.CGMainDisplayID())
    return int(round(float(b.size.width))), int(round(float(b.size.height)))


def tamano_virtual():
    """Bounding de TODOS los monitores (calculado desde los rects reales):
    dict {x, y, ancho, alto}. Ningun script asume el signo de los origenes:
    manda lo que CGDisplayBounds devuelva [runtime]. La formula min/max es
    generica (_core.bounding_de); CGGetActiveDisplayList es lo unico mac."""
    return _core.bounding_de(monitores_logicos())


def posicion_cursor():
    """(x, y) del cursor en puntos del espacio global.

    Via primaria Quartz: CGEventGetLocation(CGEventCreate(None)) (VERIFICADO:
    pynput usa CGEventGetLocation sobre eventos en _darwin.py:174; crear un
    evento 'combinado' nulo para leer el cursor es tecnica conocida
    [runtime]). Fallback: pynput mouse Controller (VERIFICADO fuente).
    """
    try:
        Q = Quartz_soft()
        if Q is not None:
            loc = Q.CGEventGetLocation(Q.CGEventCreate(None))
            return int(round(float(loc.x))), int(round(float(loc.y)))
    except Exception:
        pass
    try:
        from pynput.mouse import Controller as ControladorRaton
        x, y = ControladorRaton().position
        return int(x), int(y)
    except Exception:
        fail("Sin Quartz NI pynput: no se puede leer la posicion del cursor. "
             "pip3 install pyobjc-framework-Quartz o pynput==1.8.2")


def Quartz_soft():
    """Quartz si esta disponible, o None (no aborta)."""
    try:
        import Quartz
        return Quartz
    except ImportError:
        return None


def _monitor_contiene(x, y):
    """Monitor cuyo rect contiene a (x, y) en puntos globales, o None.

    None = hueco del bounding con monitores desalineados o fuera de todo.
    La comparacion es generica (_core.monitor_contiene); aqui solo la lista
    CGDisplayBounds de la rama."""
    return _core.monitor_contiene(monitores_logicos(), x, y)


def dentro_de_virtual(x, y):
    """True si (x, y) cae dentro del bounding de la pantalla virtual.

    Comparacion generica (_core.dentro_del_bounding) sobre el tamano_virtual
    de la rama."""
    return _core.dentro_del_bounding(tamano_virtual(), x, y)


# --- RETINA -------------------------------------------------------------

def escala_retina(ruta_png, ancho_puntos, alto_puntos):
    """Escala real de una captura: pixels del PNG / puntos de la region.

    Fuente de 'puntos': CGDisplayBounds / --region dados por el llamador;
    fuente de 'pixels': tamano PIL del PNG. Retina tipica => 2.0 (o 2.0 con
    -R y 3.0 en paneles 3x [runtime por display]).
    Devuelve (escala_x, escala_y, (ancho_px, alto_px)).
    """
    im = pil_open(ruta_png)
    w, h = im.width, im.height
    im.close()
    if ancho_puntos <= 0 or alto_puntos <= 0:
        return None, None, (w, h)
    return round(w / float(ancho_puntos), 6), round(h / float(alto_puntos), 6), (w, h)


# --- Teclas macOS: alias + tabla kVK_ ------------------------------------
# VERIFICADO fuente pynput 1.8.2 keyboard/_darwin.py:154-211 (enum Key con
# KeyCode.from_vk) = HIToolbox/Events.h. En darwin NO existen print_screen,
# pause, menu, insert, num_lock, scroll_lock ni media_stop (si hay en Win).

VK_MAC = {
    "enter": 0x24,            # 36  kVK_Return
    "tab": 0x30,              # 48  kVK_Tab
    "space": 0x31,            # 49  kVK_Space
    "backspace": 0x33,        # 51  kVK_Delete (retroceso)
    "esc": 0x35,              # 53  kVK_Escape
    "cmd": 0x37,              # 55  kVK_Command (cmd_l)
    "cmd_r": 0x36,            # 54  kVK_RightCommand
    "shift": 0x38,            # 56  kVK_Shift
    "caps_lock": 0x39,        # 57
    "alt": 0x3A,              # 58  kVK_Option
    "ctrl": 0x3B,             # 59
    "delete": 0x75,           # 117 kVK_ForwardDelete
    "home": 0x73,             # 115
    "end": 0x77,              # 119
    "page_up": 0x74,          # 116
    "page_down": 0x79,        # 121
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,  # 123-126
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60, "f6": 0x61,
    "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F,
    "f13": 0x69, "f14": 0x6B, "f15": 0x71, "f16": 0x6A, "f17": 0x40,
    "f18": 0x4F, "f19": 0x50, "f20": 0x5A,
}

# Las multimedia REALES no son kVK_: son eventos SystemDefined con
# NX_KEYTYPE (VERIFICADO fuente _darwin.py:61-68) y se emiten con
# pynput Key.media_*; nunca con "key code".
MEDIA_KEYS = ("media_play_pause", "media_volume_mute", "media_volume_down",
              "media_volume_up", "media_previous", "media_next",
              "media_eject")

# Alias habituales (pyautogui/espanol/Windows) -> nombre canonico mac.
# "windows"/"win"/"super"/"meta" -> cmd (VERIFICADO: en darwin cmd existe).
ALIAS_TECLAS_MAC = {
    "escape": "esc", "intro": "enter", "retorno": "enter",
    "espacio": "space",
    "ctr": "ctrl", "control": "ctrl",
    "windows": "cmd", "win": "cmd", "super": "cmd", "meta": "cmd",
    "command": "cmd",
    "option": "alt", "altgr": "alt_r",
    "del": "delete", "supr": "delete", "forwarddelete": "delete",
    "borrar": "backspace", "retroceso": "backspace",
    "pageup": "page_up", "pgup": "page_up",
    "pagedown": "page_down", "pgdn": "page_down",
    "volumemute": "media_volume_mute", "mute": "media_volume_mute",
    "volumedown": "media_volume_down", "volumeup": "media_volume_up",
    "playpause": "media_play_pause", "nexttrack": "media_next",
    "prevtrack": "media_previous", "eject": "media_eject",
}


def nombre_tecla_mac(nombre):
    """(canonico, es_media): alias->canonico, o (None, None) desconocida."""
    if nombre is None:
        return None, False
    n = str(nombre).strip().lower()
    n = ALIAS_TECLAS_MAC.get(n, n)
    if n in MEDIA_KEYS:
        return n, True
    if n in VK_MAC:
        return n, False
    return None, False


def tecla_pynput_mac(nombre):
    """Miembro pynput.keyboard.Key para un nombre dado, o None (darwin)."""
    keyboard = try_pynput()
    if nombre is None:
        return None
    n, _ = nombre_tecla_mac(nombre)
    if n is None:
        n = str(nombre).strip().lower()  # quizas sea un nombre Key canonico
    return getattr(keyboard.Key, n, None)


def vk_mac(nombre):
    """Codigo kVK_ (int) para el nombre canonico, o None (p. ej. media)."""
    n, es_media = nombre_tecla_mac(nombre)
    if n is None or es_media:
        return None
    return VK_MAC[n]


# --- Freno humano: banderas y esquinas -----------------------------------
# checar_abort/checar_pausa: genericos, reexportados desde _core arriba (el
# default motivo='interrumpido' conserva literal el mensaje historico de la
# rama). Lo exclusivo de mac: la EMULACION de esquinas (no hay FAILSAFE de
# pyautogui aqui).

def esquina_principal(x, y):
    """True si (x, y) es una de las 4 esquinas del display PRINCIPAL.

    EMULACION skill del FAILSAFE de pyautogui (no es API de macOS) [runtime].
    """
    Q = Quartz_soft()
    try:
        if Q is not None:
            b = Q.CGDisplayBounds(Q.CGMainDisplayID())
        else:
            return False
    except Exception:
        return False
    xi, yi = int(x), int(y)
    x0 = int(round(float(b.origin.x)))
    y0 = int(round(float(b.origin.y)))
    x1 = x0 + int(round(float(b.size.width))) - 1
    y1 = y0 + int(round(float(b.size.height))) - 1
    return (xi in (x0, x1)) and (yi in (y0, y1))


def fail_safe_check():
    """Aborta si el cursor ESTA en una esquina del principal (semantica
    pyautogui replicada: la huida humana a la esquina frena la secuencia)."""
    x, y = posicion_cursor()
    if esquina_principal(x, y):
        fail("FAILSAFE (emulado por la skill): el cursor toco una esquina del "
             "display principal y la secuencia se aborto; comportamiento "
             "intencional, no un bug. Re-captura con pantalla.py capturar "
             "antes de continuar (la accion pudo quedar parcial).",
             cursor=[x, y], tipo="failsafe-emulado-macos")


# =========================================================================
# PRIMITIVAS MOVADAS DE LOS CLIs DE RAMA (FASE SEG3)
# Cuerpos VERBATIM desde scripts/macos/<cli>.py (particion, no reinvencion):
# los cmd_* correspondientes quedan en los CLIs raiz unificados y llaman a
# estas funciones via `c.<nombre>()`. No baja NINGUN cmd_*.
# =========================================================================

# --- Movado de scripts/macos/monitores.py --------------------------------
# (El fallback de la cabecera del viejo monitores.py: quartz >
# system_profiler > osascript.) _bounding NO baja: solo lo llamaban
# cmd_listar y el helper _bounding_de de pantalla.py (ambos quedan en la
# raiz con sufijo _mac).

def _mons_quartz():
    """Monitores via pyobjc Quartz o None (no aborta)."""
    try:
        return c.monitores_logicos()
    except SystemExit:
        raise
    except Exception:
        return None


def _mons_profiler():
    """Monitores via `system_profiler SPDisplaysDataType -json` [runtime].

    Datos disponibles: nombre y resolucion; POSICIONES NO: se dejan en None
    y el JSON avisa que hace falta pyobjc-framework-Quartz para el mapa
    virtual. Los claves exactas del JSON varian por macOS: se busca de forma
    tolerante (cualquier cadena "A x B" y flags 'main'). [runtime]
    """
    try:
        p = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        return None
    try:
        data = json.loads((p.stdout or b"").decode("utf-8", errors="replace"))
        entradas = data.get("SPDisplaysDataType", [])
    except Exception:
        return None
    out = []
    for e in entradas:
        for d in (e.get("spdisplays_displays") or []):
            if not isinstance(d, dict):
                continue
            nombre = d.get("_name") or d.get("spdisplays_display-name") or \
                d.get("seldisplay") or "pantalla"
            res = d.get("spdisplays_resolution") or \
                d.get("kCGDisplayResolution") or ""
            w = h = None
            m = re.search(r"(\d+)\s*x\s*(\d+)", str(res))
            if m:
                w, h = int(m.group(1)), int(m.group(2))
            main = str(d.get("spdisplays_main", "")).lower() in (
                "yes", "spdisplays_yes", "1", "true")
            out.append({
                "numero": None, "nombre": str(nombre),
                "izq": None, "top": None, "der": None, "bot": None,
                "ancho": w, "alto": h, "work": None, "primario": bool(main),
            })
    # variantes sin sublista "spdisplays_displays": tratar la entrada misma
    if not out:
        for e in entradas:
            if not isinstance(e, dict):
                continue
            nombre = e.get("_name") or "GPU"
            out.append({
                "numero": None, "nombre": str(nombre),
                "izq": None, "top": None, "der": None, "bot": None,
                "ancho": None, "alto": None, "work": None,
                "primario": not out,
            })
    if not out:
        return None
    for i, m in enumerate(out):
        m["indice"] = i
    return out


def _mons_osascript():
    """Unico monitor (principal) via bounds del desktop [runtime].

    VERIFICADO solo en la sintaxis general de System Events (guia Apple);
    'desktop picture'/bounds no esta en el capitulo leido: ruta de último
    recurso marcada [runtime].
    """
    rc, out, err = c.osascript(
        'return "OK:" & (bounds of desktop picture of desktop 1)', [])
    if rc != 0 or not out.startswith("OK:"):
        rc, out, err = c.osascript(
            'tell application "Finder" to return '
            'bounds of window of desktop', [])
    if rc != 0 or not out:
        return None
    cuerpo = out[3:] if out.startswith("OK:") else out
    nums = [int(n) for n in re.findall(r"-?\d+", cuerpo)]
    if len(nums) < 4:
        return None
    x0, y0, x1, y1 = nums[:4]
    w, h = x1 - x0, y1 - y0
    return [{
        "numero": None, "nombre": "Principal (via osascript)",
        "izq": x0, "top": y0, "der": x1, "bot": y1,
        "ancho": w, "alto": h, "work": [x0, y0, x1, y1],
        "primario": True, "indice": 0,
    }]


def _colectar():
    """(monitores, via) con la cadena de fallback de la cabecera."""
    if c.quartz_disponible():
        mons = _mons_quartz()
        if mons:
            return mons, "quartz"
    mons = _mons_profiler()
    if mons:
        return mons, "system_profiler"
    mons = _mons_osascript()
    if mons:
        return mons, "osascript"
    c.fail("Sin Quartz NI system_profiler NI osascript utiles: instala "
           "pyobjc-framework-Quartz (pip3 install pyobjc-framework-Quartz) "
           "para el mapa virtual completo.")


# --- Movado de scripts/macos/pantalla.py ----------------------------------
# Quedan en la RAIZ (solo los llaman cmd_*): _REGLA_MAC (la usa
# cmd_capturar), _resolver_monitor (algoritmo generico c.resolver_monitor +
# textos propios), _bounding_de (delega en _bounding de monitores),
# _color_coincide (solo compara; lee via c._pixel_punto) y los cmd_*.

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


def _mon_listar():
    """Reutiliza la cadena de fallback sin duplicarla (SEG3: _colectar ya no
    vive en el viejo monitores.py: esta en ESTE modulo)."""
    return c._colectar()


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


# --- Movado de scripts/macos/raton.py -------------------------------------
# Quedan en la RAIZ: _pynput_mouse, _raton_ruta, _guard_destino,
# _monitor_dict, _aviso_guard, _DARWIN_CATCH_UP y los cmd_* (la cadena de
# rutas pynput>quartz>cliclick se orquesta desde el CLI; aqui vive SOLO la
# emision exclusiva). _aviso_guard llama c.hint_error/la tabla desde la raiz.

# --- primitives Quartz manuales (respaldo) -------------------------------

def _q_move(Q, x, y):
    Q.CGEventPost(Q.kCGHIDEventTap, Q.CGEventCreateMouseEvent(
        None, Q.kCGEventMouseMoved, (x, y), 0))


def _q_button_events(Q, boton):
    """(down, up, dragged, btn_id) segun el boton, replicando la tabla del
    fuente pynput _darwin.py:36-61 y _pyautogui_osx.py:355-373 [runtime]."""
    base = {"left": "kCGEventLeft", "right": "kCGEventRight",
            "middle": "kCGEventOther"}[boton]
    btn_id = {"left": Q.kCGMouseButtonLeft, "right": Q.kCGMouseButtonRight,
              "middle": Q.kCGMouseButtonCenter}[boton]
    return (getattr(Q, base + "MouseDown"), getattr(Q, base + "MouseUp"),
            getattr(Q, base + "MouseDragged"), btn_id)


def _q_click(Q, x, y, boton, doble):
    """Clic manual: down/up; para doble, kCGMouseEventClickState=1 y 2 en
    cada ciclo — patron exactamente leido en mouse/_darwin.py:105-133
    (efecto en Finder/AppKit [runtime: verificar apertura])."""
    down, up, _dr, btn_id = _q_button_events(Q, boton)
    ciclos = 2 if doble else 1
    for i in range(1, ciclos + 1):
        ev = Q.CGEventCreateMouseEvent(None, down, (x, y), btn_id)
        try:
            Q.CGEventSetIntegerValueField(
                ev, Q.kCGMouseEventClickState, i)
        except AttributeError:
            pass
        Q.CGEventPost(Q.kCGHIDEventTap, ev)
        ev2 = Q.CGEventCreateMouseEvent(None, up, (x, y), btn_id)
        try:
            Q.CGEventSetIntegerValueField(
                ev2, Q.kCGMouseEventClickState, i)
        except AttributeError:
            pass
        Q.CGEventPost(Q.kCGHIDEventTap, ev2)
        if i < ciclos:
            time.sleep(0.05)


def _cliclick(x, y, boton, doble):
    """Ultima ruta [3p]: cliclick sin auditar, solo si no hay Python
    grafico. Sintaxis c:/dc: segun la herramienta [3p: no fetcheada]."""
    if boton != "left":
        c.fail("cliclick [3p] como unica ruta: la skill solo define su "
               "sintaxis para boton left; para right/doble instala "
               "pynput==1.8.2 o pyobjc-framework-Quartz.")
    accion = "dc:" if doble else "c:"
    p = subprocess.run(["cliclick", "%s%d,%d" % (accion, x, y)],
                       capture_output=True)
    if p.returncode != 0:
        c.fail("cliclick fallo (rc=%d): %s" % (
            p.returncode, (p.stderr or b"").decode("utf-8", "replace")))


# --- Movado de scripts/macos/teclado.py -----------------------------------
# Bajan SOLO los caminos osascript (regla de frontera). Quedan en la RAIZ:
# _MAPA_USING y _MOD_KEY (solo las usan cmd_tecla/cmd_combo y
# _emitir_combo_pynput_or_quartz, funciones que quedan; _MOD_KEY ademas
# alimenta la via pynput, NO la de osascript), _verificar_foco_requerido
# (lo llaman solo cmd_*; lee via c._foco_actual), _escribir_pynput y
# _escribir_portapapeles (pynput/pbcopy: ni subprocess de las utilidades
# fronterizas ni Quartz; y _emitir_combo_pynput_or_quartz, que recibe por
# clausura explicita, queda), _pynput_disponible, _VIAS y los cmd_*.

def _foco_actual():
    """(app_frontmost, titulo_ventana_o_None) via System Events [runtime]."""
    cuerpo = ('tell application "System Events"\n'
              '\tset p to first application process whose frontmost is true\n'
              '\tset t to ""\n'
              '\ttry\n'
              '\t\tset t to name of window 1 of p\n'
              '\tend try\n'
              '\treturn "OK:" & (name of p) & "||" & t')
    rc, out, err = c.osascript(cuerpo, [])
    if rc != 0 or not out.startswith("OK:"):
        return None, None
    payload = out[3:]
    app, _, titulo = payload.partition("||")
    return app or None, (titulo or None)


def _escribir_osascript(texto):
    """Respaldo System Events: keystroke con el texto por argv (NUNCA dentro
    del codigo AppleScript). \\n se emite como tecla return aparte [runtime:
    si keystroke existiera con \\n, se delegaria]."""
    lineas = texto.split("\n")
    cuerpo = ('tell application "System Events"\n'
              '\tkeystroke (item 1 of argv)\n'
              'end tell')
    ultimo = len(lineas) - 1
    for i, ln in enumerate(lineas):
        if ln:
            c.osascript_valor(cuerpo, [ln], accion="keystroke")
        if i < ultimo:
            # return entre lineas (kVK_Return=36 VERIFICADO fuente pynput)
            c.osascript_valor(
                'tell application "System Events" to key code 36', [],
                accion="key code return")


# --- Movado de scripts/macos/ventanas.py ----------------------------------
# Bajan los ejecutores de osascript y sus cuerpos/tablas por clausura.
# Quedan en la RAIZ: cmd_* (orquestacion + JSON, DELEGAN aqui — no
# reimplementan AppleScript), _clasificar, _pista_por_defecto y el alias
# _ESQUEMA_URL (no ejecutan nada del SO).

_SEP = chr(31)   # unit separator entre campos
_LF = chr(30)    # record separator por linea (titulos con \n se rompen antes)

_CUERPO_LISTAR = (
    'tell application "System Events"\n'
    '\tset sep to (character id %d)\n'
    '\tset eol to (character id %d)\n'
    '\tset out to ""\n'
    '\tset procs to (every application process whose background only is '
    'false)\n'
    '\trepeat with p in procs\n'
    '\t\ttry\n'
    '\t\t\tset nm to name of p\n'
    '\t\t\tset fm to (frontmost of p) as text\n'
    '\t\t\trepeat with w in (windows of p)\n'
    '\t\t\t\ttry\n'
    '\t\t\t\t\tset t to name of w\n'
    '\t\t\t\t\tset pos to position of w\n'
    '\t\t\t\t\tset sz to size of w\n'
    '\t\t\t\t\tset mn to "false"\n'
    '\t\t\t\t\ttry\n'
    '\t\t\t\t\t\tset mn to (value of attribute "AXMinimized" of w) as text\n'
    '\t\t\t\t\tend try\n'
    '\t\t\t\t\tset t to my rmt(t, sep)\n'
    '\t\t\t\t\tset t to my rmt(t, eol)\n'
    '\t\t\t\t\tset nm to my rmt(nm, sep)\n'
    '\t\t\t\t\tset out to out & nm & sep & t & sep & (item 1 of pos) & sep '
    '& (item 2 of pos) & sep & (item 1 of sz) & sep & (item 2 of sz) & sep '
    '& mn & sep & fm & eol\n'
    '\t\t\t\tend try\n'
    '\t\t\tend repeat\n'
    '\t\tend try\n'
    '\tend repeat\n'
    '\treturn "OK:" & out\n'
    'end tell\n'
)


def _rmt_handler():
    """Handler AppleScript rmt(txt, char) que quita el caracter dado."""
    return ('on rmt(txt, ch)\n'
            '\tset AppleScript\'s text item delimiters to ch\n'
            '\tset parts to text items of txt\n'
            '\tset AppleScript\'s text item delimiters to ""\n'
            '\tset out to parts as text\n'
            '\tset AppleScript\'s text item delimiters to ""\n'
            '\treturn out\n'
            'end rmt')


def osascript_multi(estamentos, args=None, accion="osascript", timeout=60):
    """osascript con VARIOS -e (handler + run) y argv para el handler run.

    VERIFICADO man: multiples -e construyen el script; args -> run handler.
    """
    cmd = ["osascript"]
    for e in estamentos:
        cmd += ["-e", e]
    for a in (args or []):
        cmd.append(str(a))
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        c.fail("osascript no existe (dominio mac solo corre en macOS).")
    except subprocess.TimeoutExpired:
        c.fail("%s excedio %d s (errAETimeout o dialogo TCC esperando)."
               % (accion, timeout))
    out = (p.stdout or b"").decode("utf-8", errors="replace").strip()
    err = (p.stderr or b"").decode("utf-8", errors="replace").strip()
    return p.returncode, out, err


def _listar_crudo():
    """[(app, titulo, x, y, w, h, minimizada, frontmost)] via System Events."""
    cuerpo = _CUERPO_LISTAR % (ord(_SEP), ord(_LF))
    rc, out, err = osascript_multi([_rmt_handler(),
                                    "on run argv", cuerpo, "end run"],
                                   accion="listar ventanas")
    if rc != 0:
        c.fail("Error de osascript (listar): %s" % (err or out)[:300],
               hint=c.hint_error(err or out))
    if not out.startswith("OK:"):
        c.fail("respuesta inesperada de osascript: %r" % out[:200])
    regs = []
    for linea in out[3:].split(_LF):
        linea = linea.strip("\r\n")
        if not linea:
            continue
        campos = linea.split(_SEP)
        if len(campos) < 8:
            continue
        try:
            regs.append({
                "app": campos[0],
                "titulo": campos[1],
                "x": int(float(campos[2])),
                "y": int(float(campos[3])),
                "w": int(float(campos[4])),
                "h": int(float(campos[5])),
                "minimizada": campos[6] == "true",
                "frontmost": campos[7] == "true",
            })
        except ValueError:
            continue  # linea malformada [runtime]: se omite, no se inventa
    return regs


def _buscar(titulo):
    """Registro unico cuya ventana contiene `titulo` (subcadena,
    case-insensitive) o error JSON con pistas (semantica del padre Windows)."""
    regs = _listar_crudo()
    cand = [r for r in regs if titulo.lower() in r["titulo"].lower()]
    if not cand:
        c.fail("Ninguna ventana contiene el titulo %r. Usa listar y pasa el "
               "titulo exacto." % titulo,
               coincidencias=0,
               ventanas_abiertas=[r["titulo"] for r in regs][:25])
    if len(cand) > 1:
        c.fail("Varias ventanas coinciden con %r (%d): pide el titulo exacto "
               "y unico, o cierra las duplicadas."
               % (titulo, len(cand)),
               coincidencias=["%s / %s" % (r["app"], r["titulo"])
                              for r in cand])
    return cand[0]


def _estado_item(r):
    """Item CANONICO multi-rama (P1-2): rect+estado ANIDADADOS. 'maximizada'
    siempre None: macOS no maximiza (el boton verde es ZOOM); 'id' null: no
    hay hWnd. 'app' va en su clave comun."""
    return {
        "titulo": r["titulo"],
        "app": r["app"],
        "id": None,
        "rect": {"left": r["x"], "top": r["y"],
                 "ancho": r["w"], "alto": r["h"]},
        "estado": {
            "minimizada": r["minimizada"],
            "maximizada": None,
            "activa": r["frontmost"],
        },
    }


def _accion_ventana(titulo, accion, cuerpo, mensaje_aviso):
    """Busca la ventana (subcadena unica), ejecuta `cuerpo` con
    (app, titulo) por argv y reporta."""
    c.checar_abort()
    c.checar_pausa()  # P1-5: banderas de vigilar antes de accionar
    r = _buscar(titulo)
    ok, payload = c.osascript_ok(cuerpo, [r["app"], r["titulo"]],
                                 accion=accion)
    if not ok:
        payload.setdefault("ventana", _estado_item(r))
        c.fail("%s fallo sobre %r: %s" % (accion, titulo,
                                          payload.get("error")),
               **{k: v for k, v in payload.items() if k != "error"})
    item = {
        "ok": True,
        "accion": accion,
        "via": "osascript",
        "titulo": r["titulo"],
        "app": r["app"],
        "rect": {"left": r["x"], "top": r["y"],
                 "ancho": r["w"], "alto": r["h"]},
        "estado": {"minimizada": r["minimizada"], "maximizada": None,
                   "activa": r["frontmost"]},
        "ventana": _estado_item(r),
        "marco": c.MARCO,
        "unidad": "puntos logicos",
        "aviso": mensaje_aviso,
    }
    if payload not in (True, "OK:", ""):
        item["detalle"] = payload
    c.json_out(item)


# Cuerpos AppleScript (los datos viajan por argv: item 1 = app, item 2 =
# titulo de la ventana objetivo; match exacto del titulo ya resuelto por
# Python en _buscar).
_CUERPO_ACTIVAR = (
    'tell application "System Events"\n'
    '\ttell (first application process whose name is (item 1 of argv))\n'
    '\t\tset frontmost to true\n'
    '\t\ttry\n'
    '\t\t\tperform action "AXRaise" of (first window whose name is '
    '(item 2 of argv))\n'
    '\t\tend try\n'
    '\tend tell\n'
    '\treturn "OK:frontmost"\n'
)
_CUERPO_MINIMIZAR = (
    'tell application "System Events"\n'
    '\ttell (first application process whose name is (item 1 of argv))\n'
    '\t\tperform action "AXMinimize" of (first window whose name is '
    '(item 2 of argv))\n'
    '\tend tell\n'
    '\treturn "OK:minimizada"\n'
)
_CUERPO_RESTAURAR = (
    'tell application "System Events"\n'
    '\ttell (first application process whose name is (item 1 of argv))\n'
    '\t\tset w to first window whose name is (item 2 of argv)\n'
    '\t\ttry\n'
    '\t\t\tset value of attribute "AXMinimized" of w to false\n'
    '\t\t\treturn "OK:AXMinimized-false"\n'
    '\t\ton error\n'
    '\t\t\tset frontmost to true\n'
    '\t\t\treturn "OK:frontmost-only"\n'
    '\t\tend try\n'
    '\tend tell\n'
)
_CUERPO_CERRAR = (
    'tell application "System Events"\n'
    '\ttell (first application process whose name is (item 1 of argv))\n'
    '\t\tclose (first window whose name is (item 2 of argv))\n'
    '\tend tell\n'
    '\treturn "OK:cerrada"\n'
)
# IMPL-K P1.1: mover = `set position {x, y}` de System Events (position/size
# leidos por _CUERPO_LISTAR [runtime]; la guia Apple leida documenta la clase
# window y sus atributos position/size como [runtime] — cuerpo nuevo, NO
# verificado en Mac real). argv: 1 app, 2 titulo, 3 x, 4 y [, 5 w, 6 h].
_CUERPO_MOVER = (
    'tell application "System Events"\n'
    '\ttell (first application process whose name is (item 1 of argv))\n'
    '\t\tset w to first window whose name is (item 2 of argv)\n'
    '\t\tset position of w to {(item 3 of argv) as integer, '
    '(item 4 of argv) as integer}\n'
    '\t\tif (count of argv) > 5 then\n'
    '\t\t\tset size of w to {(item 5 of argv) as integer, '
    '(item 6 of argv) as integer}\n'
    '\t\tend if\n'
    '\tend tell\n'
    '\treturn "OK:movida"\n'
)


def _mover_ventana_mac(titulo, x, y, ancho=None, alto=None):
    """Mueve (y opcionalmente redimensiona) la ventana `titulo` y emite el
    JSON canonico con el rect POST (vuelve a listar: position es [runtime])."""
    c.checar_abort()
    c.checar_pausa()
    r = _buscar(titulo)
    argv = [r["app"], r["titulo"], int(x), int(y)]
    if ancho is not None and alto is not None:
        argv += [int(ancho), int(alto)]
    ok, payload = c.osascript_ok(_CUERPO_MOVER, argv, accion="mover")
    if not ok:
        payload.setdefault("ventana", _estado_item(r))
        c.fail("mover fallo sobre %r: %s" % (titulo, payload.get("error")),
               **{k: v for k, v in payload.items() if k != "error"})
    nueva = r
    try:
        for reg in _listar_crudo():
            if reg["app"] == r["app"] and reg["titulo"] == r["titulo"]:
                nueva = reg
                break
    except SystemExit:
        raise
    except Exception:
        pass  # sin re-lectura: se reporta el rect pre (honesto en detalle)
    item = {
        "ok": True,
        "accion": "mover",
        "via": "osascript (System Events set position)",
        "titulo": nueva["titulo"],
        "app": nueva["app"],
        "rect": {"left": nueva["x"], "top": nueva["y"],
                 "ancho": nueva["w"], "alto": nueva["h"]},
        "estado": {"minimizada": nueva["minimizada"], "maximizada": None,
                   "activa": nueva["frontmost"]},
        "ventana": _estado_item(nueva),
        "pedido": {"x": int(x), "y": int(y),
                   "ancho": int(ancho) if ancho else None,
                   "alto": int(alto) if alto else None},
        "marco": c.MARCO,
        "unidad": "puntos logicos",
        "aviso": "'set position' mueve el VERTICE SUP-IZQ en puntos logicos "
                 "[runtime: sin verificacion en Mac real]; el rect reportado "
                 "es la re-lectura de System Events (el window origin de "
                 "Cocoa puede desviar la barra de titulo); verifica con "
                 "capturar",
    }
    if payload not in (True, "OK:", ""):
        item["detalle"] = payload
    c.json_out(item)


def _ocupantes_mac_zona(crudas, x1, y1, x2, y2):
    """Items de solape sobre la zona (geometria pura; reutilizable por el
    CLI raiz en su rama mac)."""
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    items = []
    for r in crudas:
        l, t = r["x"], r["y"]
        rr, bb = l + r["w"], t + r["h"]
        ox1, oy1 = max(l, x1), max(t, y1)
        ox2, oy2 = min(rr, x2), min(bb, y2)
        solapa = (ox2 - ox1) * (oy2 - oy1) if (ox2 > ox1 and oy2 > oy1) else 0
        cubre = l <= cx < rr and t <= cy < bb
        if solapa > 0 or cubre:
            items.append({"id": None, "app": r["app"], "titulo": r["titulo"],
                          "rect": [l, t, rr, bb], "solapa_px2": solapa,
                          "cubre_centro_zona": cubre})
    return items


def _snapshot_pares():
    """{(app, titulo)} actuales para exigir ventana NUEVA en --esperar.

    Sin hWnd en mac: la identidad es (app, titulo) — titulos duplicados o
    reutilizados (navegadores) pueden no contar como nuevos (nota JSON).
    """
    try:
        return {(r["app"], r["titulo"]) for r in _listar_crudo()}
    except SystemExit:
        raise
    except Exception:
        return set()  # sin snapshot: toda coincidencia cuenta como nueva


# =========================================================================
# CLI PROPIO SOLO-MACOS (diagnostico del dominio; simetrico a
# win_especiales.py). Los verbos usan las primitivas de arriba y responden
# el JSON canonico de la skill. En otro SO el guard del __main__ responde
# ANTES de parsear (rc 2).
# =========================================================================

def cmd_tcc(args):
    """Catalogo de hints de permisos: la tabla HINT_ERRORES verbatim."""
    c.json_out({
        "ok": True,
        "hint_errores": [{"patron": patron, "pista": pista}
                         for patron, pista in c.HINT_ERRORES],
        "nota": "catalogo de numeros de AppleScript/TCC que hint_error() "
                "mapea desde el stderr de osascript (-1743 Automatizacion, "
                "-25211 Accesibilidad, -1712 errAETimeout, -1719, -1728, "
                "-600). Conceder en Preferencias del Sistema > Seguridad y "
                "privacidad; el reset de Automatizacion es tccutil reset "
                "AppleEvents (ver pista -1743; references/macos-python.md "
                "§3). El watchdog vigilar.py reporta IS_TRUSTED "
                "(Accesibilidad).",
    })


def cmd_screencapture(args):
    """Captura cruda a archivo via las primitivas movadas (-R y/o -D)."""
    if args.rect is None and args.display is None:
        c.fail("screencapture crudo: indica --rect X Y ANCHO ALTO y/o "
               "--display N (1 = principal, '1 is main' VERIFICADO man). "
               "Para capturar con mapa de monitores, fallback y --max-lado "
               "usa pantalla.py capturar.")
    destino = c.ruta_destino_captura(args.archivo)
    origen = [0, 0]  # default historico de la rama (sup-izq del principal)
    puntos = None
    if args.rect is not None:
        x, y, w, h = args.rect
        if w <= 0 or h <= 0:
            c.fail("Region invalida: ancho/alto deben ser > 0 (x e y ACEPTAN "
                   "negativos si tu arrangement los da: coordenadas del "
                   "espacio global).")
        origen = [x, y]
        puntos = {"ancho": w, "alto": h}
        via, aviso = _capturar_rect(destino, (x, y, w, h),
                                    display_fallback=args.display)
    else:
        via, aviso = _capturar_rect(destino, None,
                                    display_fallback=args.display)
    im = c.pil_open(destino)
    fis_w, fis_h = int(im.width), int(im.height)
    im.close()
    esc_ret = None
    if puntos:
        esc_ret, _ey, _sz = c.escala_retina(destino, puntos["ancho"],
                                            puntos["alto"])
    # sin --max-lado aqui: el factor TOTAL imagen->punto es la retina medida
    px_por_unidad_coord = esc_ret
    item = {
        "ok": True,
        "archivo": destino,
        "ancho": fis_w,
        "alto": fis_h,
        "fisico": {"ancho": fis_w, "alto": fis_h},
        "origen": origen if puntos else [0, 0],
        "puntos": puntos,
        "escala": 1.0,
        "px_por_unidad_coord": px_por_unidad_coord,
        "marco": c.MARCO,
        "escala_retina": esc_ret,
        "unidad": "puntos logicos (clics AQUI, no en pixeles de la imagen)",
        "via": via,
        "nota": "captura CRUDA via screencapture (sin mapa de monitores ni "
                "thumbnail); la 'regla' canonica de re-escalado y el JSON "
                "completo van por pantalla.py capturar. " + (
                    "px_por_unidad_coord null: la via -D sin mapa de "
                    "posiciones no permite medir Retina aqui [runtime]: "
                    "verifica el factor con una captura -R de region "
                    "conocida."
                    if px_por_unidad_coord is None else
                    "px_por_unidad_coord = imagen_px / punto_logico (Retina "
                    "incluida; sin --max-lado en este verbo)."),
    }
    if aviso:
        item["aviso"] = aviso
    c.json_out(item)


def cmd_monitores_quartz(args):
    """Listado CRUDO Quartz (sin la cadena de fallback)."""
    mons = c.monitores_logicos()  # fail con hint pip si falta pyobjc
    v = c.bounding_de(mons)
    c.json_out({
        "monitores": mons,
        "virtual": {"x": v["x"], "y": v["y"], "ancho": v["ancho"],
                    "alto": v["alto"]},
        "marco": c.MARCO,
        "unidad": "puntos logicos (espacio global; 0,0 = sup-izq del display "
                  "principal)",
        "via": "quartz",
        "nota": "listado CRUDO via CGGetActiveDisplayList/CGDisplayBounds "
                "(sin el fallback system_profiler/osascript): falla con "
                "error JSON si no hay pyobjc-framework-Quartz. El mapa "
                "completo con 'via' y nombres de pantalla va por "
                "monitores.py listar",
    })


def cmd_ventanas_se(args):
    """Listado CRUDO de System Events (sin item canonico)."""
    regs = _listar_crudo()
    c.json_out({
        "total": len(regs),
        "ventanas": regs,
        "marco": c.MARCO,
        "unidad": "puntos logicos del espacio global",
        "via": "osascript",
        "nota": "listado CRUDO de System Events (app, titulo, x, y, w, h, "
                "minimizada, frontmost; titulos sanitizados sin \\x1f/\\x1e): "
                "el item canonico rect+estado anidado, el foco y las "
                "acciones van por ventanas.py listar/foco/activar",
    })


def cmd_open(args):
    """Lanzar via `open` nativo sin clasificar ni esperar (verbo crudo).

    La mecanica de lanzamiento es la del viejo ventanas.py cmd_abrir
    (Popen start_new_session; open -a se sondea con wait(10) porque sin -W
    'open' termina tras delegar en LaunchServices). Para clasificar
    url/archivo/app y esperar la ventana nueva usa ventanas.py abrir."""
    if args.app:
        cmd = ["open", "-a", args.objetivo]
        mecanica = "open -a <app> (VERIFICADO man; -b si es bundle-id)"
    else:
        cmd = ["open", args.objetivo]
        mecanica = "open <archivo|URL> (LaunchServices; VERIFICADO man)"
    proc = None
    try:
        # start_new_session: desvincular del proceso terminal del agente
        # (heredaria senales y su salida podria ensuciar el JSON).
        proc = subprocess.Popen(cmd, start_new_session=True)
    except OSError as exc:
        c.fail("Fallo al lanzar %r via %s: %s: %s"
               % (args.objetivo, mecanica, type(exc).__name__, exc),
               nota="si es una app: prueba el nombre exacto de /Applications "
                    "o la ruta completa del .app; si es bundle-id usa -b")
    if args.app:
        # 'open' sin -W termina tras delegar en LaunchServices: si la app no
        # existe, su rc no-zero llega rapido (lo capturamos; en exito rc=0).
        try:
            rc_open = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            rc_open = None
        if rc_open:
            c.fail("open -a %r retorno %d: la app no existe o "
                   "LaunchServices no la resuelve." % (args.objetivo, rc_open),
                   nota="usa el nombre exacto de /Applications, la ruta "
                        "completa del .app, o el bundle-id via 'open -b' "
                        "(MAN verificado: -a app, -b bundle_identifier)")
    c.json_out({
        "ok": True,
        "accion": "abrir",
        "objetivo": args.objetivo,
        "mecanica": mecanica,
        "via": "open",
        "pid": proc.pid if proc else None,
        "pid_nota": "el pid es del proceso 'open': la app destino puede "
                    "ser otra (LaunchServices): busca la ventana por titulo",
        "marco": c.MARCO,
        "nota": "lanzamiento CRUDO sin clasificar y SIN esperar la ventana "
                "(--esperar vive en ventanas.py abrir); verifica con "
                "pantalla.py capturar o ventanas.py listar",
    })


def construir_parser():
    parser = c.Parser(
        prog="macos_especiales.py",
        description="Libreria exclusiva de macOS + CLI de diagnostico "
                    "solo-macos: tcc (permisos), screencapture crudo, "
                    "monitores-quartz, ventanas-se y open. JSON canonico de "
                    "la skill; la entrada normal es scripts/<verbo>.py "
                    "(raiz, multi-OS: ejecuta la ruta de tu SO en el propio "
                    "proceso).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1]
        if __doc__ and "Subcomandos:" in __doc__ else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True,
                                metavar="SUBCOMANDO")

    sub.add_parser("tcc",
                   help="catalogo de hints de permisos TCC (HINT_ERRORES)") \
       .set_defaults(func=cmd_tcc)

    p = sub.add_parser("screencapture",
                       help="PNG CRUDO a archivo: --rect x y w h y/o "
                            "--display N (1 = principal)")
    p.add_argument("--rect", type=int, nargs=4,
                   metavar=("X", "Y", "ANCHO", "ALTO"),
                   help="region en PUNTOS del espacio global "
                        "(screencapture -R; negativos segun arrangement "
                        "[runtime])")
    p.add_argument("--display", type=int, metavar="N",
                   help="ordinal de screencapture -D ('1 is main, 2 "
                        "secondary', VERIFICADO man)")
    p.add_argument("--archivo", help="nombre o ruta destino del PNG (nombre "
                   "pelado cae en .tmp/capturas; por defecto "
                   "captura_<fecha_hora>.png)")
    p.set_defaults(func=cmd_screencapture)

    sub.add_parser("monitores-quartz",
                   help="listado CRUDO via CGGetActiveDisplayList (sin "
                        "fallback)") \
       .set_defaults(func=cmd_monitores_quartz)

    sub.add_parser("ventanas-se",
                   help="listado CRUDO de System Events via osascript") \
       .set_defaults(func=cmd_ventanas_se)

    p = sub.add_parser("open",
                       help="lanzar objetivo via `open` nativo (crudo: sin "
                            "clasificar ni esperar)")
    p.add_argument("objetivo",
                   help="URL, ruta de archivo o .app; con --app, nombre o "
                        "ruta de la app (open -a)")
    p.add_argument("--app", action="store_true",
                   help="usar open -a (LaunchServices resuelve el nombre de "
                        "app; el rc se sondea 10 s como el viejo cmd_abrir)")
    p.set_defaults(func=cmd_open)

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
    # Guard de plataforma del CLI (SEG3): responde ANTES de parsear. La
    # LIBRERIA (este mismo modulo importado) si es valida en cualquier SO.
    if sys.platform != "darwin":
        print(json.dumps({
            "error": "macos_especiales.py (su CLI) es el dominio EXCLUSIVO "
                     "de MACOS; la LIBRERIA macos_especiales si es "
                     "importable en cualquier SO (guard solo al "
                     "ejecutarse). El punto de entrada normal es "
                     "scripts/<verbo>.py (raiz, multi-OS: ejecuta la ruta "
                     "de tu SO en el propio proceso). Autotest: python "
                     "autotest.py en tu SO",
            "sistema_operativo": sys.platform,
            # contrato P0-4: `plataforma` canonica tambien en el guard
            "plataforma": {"win32": "win", "linux": "linux",
                           "darwin": "darwin"}.get(sys.platform,
                                                   sys.platform),
        }, ensure_ascii=False))
        sys.exit(2)
    main()
