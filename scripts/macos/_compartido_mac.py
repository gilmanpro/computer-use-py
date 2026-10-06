# -*- coding: utf-8 -*-
"""_compartido_mac.py — Utilidades comunes de los scripts macOS de la skill
computer-use-py (dominio mac; NO importa al glue_windows.py de la raiz).

FASE SEG2 — EL PUNTO DE ENTRADA NORMAL es scripts/<verbo>.py (raiz, multi-OS:
los CLIs de la raiz enrutan aqui en macOS); ESTA CARPETA es el motor exclusivo
de macOS. Llamar directamente a scripts/macos/<script>.py sigue funcionando
(via avanzada; los CLIs raiz hacen exactamente esto).

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
   "error" y codigo de salida 1.
"""

# FASE SEG: lo identico a las otras ramas (Parser, banderas ABORT/PAUSA,
# validaciones de args, bucles de espera, color/combos, geometria de rects,
# convencion de destino de capturas, tablas comunes) vive en
# scripts/_core.py y se REEXPORTA abajo; aqui quedan solo los glue propios
# de macOS (osascript/screencapture/Quartz, tablas kVK_/alias darwin,
# escalas Retina y el failsafe emulado). Los textos canonicos compartidos
# son los de la rama WINDOWS (validada en vivo): donde mac decia "reanuda"
# ahora el mensaje unico dice "relanza" (anotado en el reporte FASE SEG).

import json
import os
import subprocess
import sys
import time  # reexportado: los scripts duermen con `c.time.sleep(...)`

# --- Guard de plataforma ---------------------------------------------------
# scripts/macos/ es el MOTOR EXCLUSIVO de macOS (la entrada normal es
# scripts/<verbo>.py en la raiz, que enruta aqui): ejecutado en otro SO debe
# responder el JSON canonico con "corre en tu SO", no un fallo raro de
# osascript/Quartz.
if sys.platform != "darwin":
    print(json.dumps({
        "error": "scripts/macos/ es el motor EXCLUSIVO de MACOS; el punto de "
                 "entrada normal es scripts/<verbo>.py (raiz, multi-OS, "
                 "enruta solo). Autotest: python autotest.py en tu SO",
        "sistema_operativo": sys.platform,
        # contrato P0-4: `plataforma` canonica tambien en el guard
        "plataforma": {"win32": "win", "linux": "linux",
                       "darwin": "darwin"}.get(sys.platform, sys.platform),
    }, ensure_ascii=False))
    sys.exit(2)

# (argparse ya no se importa aqui: la clase Parser es generica y vive en
#  scripts/_core.py; cada script trae su propio argparse.)

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
