# -*- coding: utf-8 -*-
"""glue_windows.py — GLUE EXCLUSIVO de Windows de la skill computer-use-py.

FASE SEG2: los CLIs (monitores/pantalla/teclado/raton/ventanas/vigilar) viven
en scripts/ raiz y son multi-OS: en win32 importan ESTE modulo (ruta historica
intacta); en linux/darwin enrutan a scripts/linux|macos sin llegar aqui. La
pieza exclusivamente Windows restante en scripts/windows/ es
win_especiales.py, que tambien importa este glue. Cada CLI lo importa PRIMERO.
Efectos de borde deliberados al importarse:

1. DPI: llama a SetProcessDpiAwareness(2) (process-per-monitor) ANTES de
   importar pyautogui. PyAutoGUI por defecto marca el proceso solo como
   System-DPI-aware al importarse, y pynput necesita per-monitor para que
   sus coordenadas cuadren con las capturas. La consciencia DPI de un
   proceso solo puede fijarse una vez: de ahi el orden.
2. Seguridad no negociable: pyautogui.FAILSAFE = True (llevar el cursor a
   CUALQUIERA de las 4 esquinas del monitor primario aborta con
   FailSafeException) y pyautogui.PAUSE = 0.15 (>= 0.1 s de aire entre
   llamadas). Ningun script expone opcion para desactivarlos.
3. Salida: todo lo que imprime la skill por stdout es JSON; los errores son
   JSON con la clave "error" y codigo de salida 1.

Convencion de coordenadas de la skill: pixeles ABSOLUTOS del ESPACIO DE
PANTALLA VIRTUAL. El origen logico (0,0) es el vertice sup-izq del monitor
PRIMARIO; con monitores a la izquierda o arriba del primario, x (o y) son
NEGATIVOS y siguen siendo validos. En un equipo de un solo monitor este
marco coincide con el del primario (retrocompatible). Mapa exacto de la
maquina: `monitores.py listar`. Donde importa, las salidas incluyen ambas
lecturas (primario y virtual) y su nota. Ver references/monitores-multi.md.

FAILSAFE: las 4 esquinas que abortan son las del monitor PRIMARIO (semantica
de pyautogui, no negociable). En un secundario NO hay esquina failsafe: el
freno alli es la tecla de panico de vigilar.py o Ctrl+C en la consola.

FASE SEG: lo que era identico en las 3 ramas (Parser, banderas ABORT/PAUSA,
validaciones de args, esperas, color/combos, geometria de rects, tablas y
convencion de destino de capturas) VIVE en scripts/_core.py —el generico
multi-OS— y aqui solo queda GLUE DE WINDOWS (guard, DPI, pyautogui, mapa de
monitores por ctypes, marco) que REEXPORTA _core para que los CLIs sigan
llamando c.<nombre> sin cambios. Comportamiento win32 IDENTICO al de la rama
validada en escritorio real (regla nº1 de FASE SEG2).
"""

import json
import sys

# --- Guard de plataforma (DEBE ir antes de ctypes.wintypes y de pyautogui) --
# Este glue es EXCLUSIVO Windows; el resto del flujo usa scripts/ (los CLIs de
# la raiz enrutan solos a su rama y nunca deberian llegar aqui). Si alguien lo
# importa directamente en otro SO, el fallo seria un AttributeError de windll o
# un traceback de pyautogui: este guard lo convierte en el JSON canonico (rc 2,
# mismo contrato que las ramas linux/ y macos/).
if sys.platform != "win32":
    print(json.dumps({
        "error": "glue_windows.py es exclusivo WINDOWS; el resto del flujo "
                 "usa scripts/ (los CLIs de la raiz enrutan a la rama de tu "
                 "SO; para la suite: python autotest.py)",
        "sistema_operativo": sys.platform,
        # P0-4: `plataforma` canonica tambien en el guard (contrato uniforme).
        "plataforma": {"win32": "win", "linux": "linux",
                       "darwin": "darwin"}.get(sys.platform, sys.platform),
    }, ensure_ascii=False))
    sys.exit(2)

import ctypes
import os
import time  # reexportado: los scripts duermen con `c.time.sleep(...)`
from ctypes import wintypes


def _inicializar_dpi():
    """Fija process-per-monitor DPI antes de cualquier import de pyautogui."""
    try:
        # 2 = PROCESS_PER_MONITOR_DPI_AWARE (shcore, Win8.1+).
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            # Degradacion a System-aware (lo que haria pyautogui por si solo).
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass  # API DPI no disponible: modo legado, puede descuadrar escala


_inicializar_dpi()

# La consola de Windows arranca en codepage local y los JSON llevan tildes,
# eñes y titulos de ventana variados: forzar UTF-8 con reemplazo.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pyautogui  # noqa: E402  (deliberado: despues de fijar el DPI)

pyautogui.FAILSAFE = True   # NO NEGOCIABLE: las 4 esquinas abortan.
pyautogui.PAUSE = 0.15      # >= 0.1 s entre funciones publicas.

# --- Helpers GENERICO multi-OS (scripts/_core.py) — reexportados -----------
# _core.py vive en scripts/ JUNTO a este glue (desde FASE SEG2 el glue tambien
# esta en la raiz de scripts/, no en la rama windows/) y es stdlib-puro (seguro
# en cualquier SO): aqui se reexporta para que los CLIs sigan llamando
# c.json_out/c.fail/... con comportamiento IDENTICO al historico. RAIZ_SKILL,
# DIR_TMP y las banderas las fija _core contra SU propio __file__ (scripts/),
# apuntando a computer-use-py/.tmp/. El sys.path.insert del propio directorio
# cubre el caso de import desde fuera (p. ej. win_especiales.py en la rama).
# json_out/fail inyectan `plataforma` (P0-4) en todo JSON que no la traiga.
# FASE SEG: a _core se movio TODO lo que estaba duplicado palabra-por-palabra
# con linux/ y macos/ (Parser, banderas, validaciones de args, bucles de
# espera, color/combos, geometria de rects, tablas y destino de capturas).
# El autotest de estructura exige que ningun nombre de HELPERS_COMUNES se
# redefina aqui: solo se reexporta con la forma `nombre = _core.nombre`.
_DIR_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _DIR_SCRIPTS not in sys.path:
    sys.path.insert(0, _DIR_SCRIPTS)
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

# Marco de coordenadas canonico de la rama (P0-4: enum cerrado).
MARCO = "px_fisicos_virtual"

# Parser, checar_abort, checar_pausa y checar_aborto_espera: moved a _core
# (copias identicas en las 3 ramas) y reexportados arriba; sus textos
# historicos de esta rama son ahora los CANONICOS del multiplete.


def tamano_pantalla():
    """(ancho, alto) fisicos del monitor primario (GetSystemMetrics)."""
    s = pyautogui.size()
    return int(s.width), int(s.height)


def posicion_cursor():
    """(x, y) del cursor en el marco de pyautogui (monitor primario)."""
    p = pyautogui.position()
    return int(p.x), int(p.y)


def dentro_de_pantalla(x, y):
    """True si (x, y) es direccionable por pyautogui (solo primario)."""
    return bool(pyautogui.onScreen(int(x), int(y)))


# --- Mapa de monitores (ctypes puro, sin dependencias nuevas) ------------
# VERIFICADO: rcMonitor/rcWork de MONITORINFO se expresan en coordenadas de
# la PANTALLA VIRTUAL y "may be negative values" si el monitor no es el
# primario (https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-monitorinfo).
# Detalle y URLs: references/monitores-multi.md.

MONITORINFOF_PRIMARY = 1  # unico dwFlags definido (doc MONITORINFO)


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),  # CCHDEVICENAME
    ]


_LPFNMONITORENUM = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
    ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)


def monitores():
    """Lista de monitores fisicos, en coordenadas del ESPACIO VIRTUAL.

    Cada entrada: nombre (szDevice, p. ej. '\\\\.\\DISPLAY1'), indice,
    izq/top/der/bot (rcMonitor; negativos posibles), ancho/alto, work
    (rcWork: area util sin barra de tareas) y primario (bool). Orden = el de
    EnumDisplayMonitors (no garantizado igual entre sesiones: leeer
    'monitores.py listar' en cada arranque).
    """
    user32 = ctypes.windll.user32
    out = []

    def _cb(hmon, hdc, lprc, dato):
        mi = _MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            raise ctypes.WinError()
        r = mi.rcMonitor
        out.append({
            "nombre": mi.szDevice,
            "izq": int(r.left), "top": int(r.top),
            "der": int(r.right), "bot": int(r.bottom),
            "ancho": int(r.right - r.left), "alto": int(r.bottom - r.top),
            "work": (int(mi.rcWork.left), int(mi.rcWork.top),
                     int(mi.rcWork.right), int(mi.rcWork.bottom)),
            "primario": bool(mi.dwFlags & MONITORINFOF_PRIMARY),
        })
        return True

    if not user32.EnumDisplayMonitors(None, None, _LPFNMONITORENUM(_cb), 0):
        raise ctypes.WinError()
    for i, m in enumerate(out):
        m["indice"] = i
    return out


def tamano_virtual():
    """Bounding de TODOS los monitores: dict {x, y, ancho, alto}.

    SM_XVIRTUALSCREEN=76, SM_YVIRTUALSCREEN=77, SM_CXVIRTUALSCREEN=78,
    SM_CYVIRTUALSCREEN=79 (tabla oficial de GetSystemMetrics).
    """
    m = ctypes.windll.user32.GetSystemMetrics
    return {"x": int(m(76)), "y": int(m(77)),
            "ancho": int(m(78)), "alto": int(m(79))}


def _monitor_contiene(x, y):
    """Monitor cuyo rcMonitor contiene a (x, y) virtuales, o None.

    None = el punto cae fuera de todo monitor (hueco del bounding virtual
    en monitores desalineados, o coordenadas fuera del todo). La formula del
    rectangulo es generica (_core.monitor_contiene); lo de aqui es la fuente
    ctypes de esta rama.
    """
    return _core.monitor_contiene(monitores(), x, y)


def dentro_de_virtual(x, y):
    """True si (x, y) cae dentro del bounding de la pantalla virtual.

    Marco nuevo de la skill: NO validar ya contra el primario. En un equipo
    de un solo monitor coincide con dentro_de_pantalla(). La comparacion es
    generica (_core.dentro_del_bounding); el SM_*virtual sigue siendo de aqui.
    """
    return _core.dentro_del_bounding(tamano_virtual(), x, y)


def tecla_pynput(nombre):
    """Devuelve el miembro pynput.keyboard.Key para un nombre dado, o None.

    Acepta el nombre canonico de Key (ej. 'esc', 'ctrl_l',
    'media_play_pause') o     alias habituales de pyautogui/espanol. La tabla de
    alias ALIAS_TECLAS_PYNPUT es la copia generica de _core (identica en
    win/linux); este envoltorio se queda en el glue porque pynput NO es
    stdlib-pura: importar pynput desde _core estaria prohibido.
    """
    from pynput import keyboard

    if nombre is None:
        return None
    n = str(nombre).strip().lower()
    n = ALIAS_TECLAS_PYNPUT.get(n, n)
    return getattr(keyboard.Key, n, None)


def fallar_por_failsafe(exc):
    """Traduce FailSafeException a un error JSON accionable y sale con 1."""
    fail(
        "FAILSAFE: el cursor toco una esquina del monitor primario y la "
        "secuencia se aborto (comportamiento intencional, no un bug). "
        "Revisa la pantalla con pantalla.py capturar antes de continuar.",
        tipo=type(exc).__name__,
        detalle=str(exc),
    )
