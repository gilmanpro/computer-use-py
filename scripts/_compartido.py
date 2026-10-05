# -*- coding: utf-8 -*-
"""Utilidades comunes de los scripts CLI de la skill computer-use-py.

Cada script de la skill importa este modulo PRIMERO. Efectos de borde
deliberados al importarse:

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
"""

import ctypes
import json
import os
import sys
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

# --- Rutas de la skill -------------------------------------------------
RAIZ_SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_TMP = os.path.join(RAIZ_SKILL, ".tmp")
DIR_CAPTURAS = os.path.join(DIR_TMP, "capturas")
ARCHIVO_ABORT = os.path.join(DIR_TMP, "ABORT")
ARCHIVO_PAUSA = os.path.join(DIR_TMP, "PAUSA")


def json_out(datos):
    """Unica via de salida de los scripts: JSON legible por stdout."""
    print(json.dumps(datos, ensure_ascii=False, indent=2))


def fail(mensaje, **extra):
    """Error canonico de la skill: imprime JSON con 'error' y sale con 1."""
    json_out({"error": mensaje, **extra})
    sys.exit(1)


def tocar(archivo):
    """Crea o refresca un archivo-bandera vacio dentro de .tmp (no bloquea)."""
    os.makedirs(DIR_TMP, exist_ok=True)
    with open(archivo, "w", encoding="utf-8"):
        pass


def borrar(archivo):
    """Elimina un archivo-bandera si existe (estado limpio al arrancar)."""
    try:
        os.remove(archivo)
    except OSError:
        pass


def asegurar_capturas():
    """Crea .tmp/capturas si falta y devuelve su ruta."""
    os.makedirs(DIR_CAPTURAS, exist_ok=True)
    return DIR_CAPTURAS


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
    en monitores desalineados, o coordenadas fuera del todo).
    """
    xi, yi = int(x), int(y)
    for m in monitores():
        if m["izq"] <= xi < m["der"] and m["top"] <= yi < m["bot"]:
            return m
    return None


def dentro_de_virtual(x, y):
    """True si (x, y) cae dentro del bounding de la pantalla virtual.

    Marco nuevo de la skill: NO validar ya contra el primario. En un equipo
    de un solo monitor coincide con dentro_de_pantalla().
    """
    v = tamano_virtual()
    return (v["x"] <= int(x) < v["x"] + v["ancho"]
            and v["y"] <= int(y) < v["y"] + v["alto"])


# Nombres de tecla de pyautogui (Windows) -> miembros del enum Key de pynput
# 1.8.2 (lista verificada en el backend _win32 del digest de pynput). Sirve
# como reserva cuando pyautogui no reconoce una tecla (p. ej. variantes
# multimedia con otro nombre).
_ALIAS_TECLAS_PYNPUT = {
    "escape": "esc", "control": "ctrl", "ctr": "ctrl",
    "windows": "cmd", "win": "cmd", "super": "cmd", "meta": "cmd",
    "winleft": "cmd_l", "winright": "cmd_r",
    "del": "delete", "supr": "delete",
    "espacio": "space", "intro": "enter", "retorno": "enter",
    "pageup": "page_up", "pagedown": "page_down", "pgup": "page_up",
    "pgdn": "page_down",
    "printscreen": "print_screen", "prtsc": "print_screen", "sysrq": "print_screen",
    "apps": "menu", "altgr": "alt_gr",
    "break": "pause",
    # Teclas multimedia nombradas por pyautogui en Windows (digest pyautogui
    # seccion 3) -> equivalentes Key.media_* de pynput (digest pynput seccion 3).
    "volumemute": "media_volume_mute", "mute": "media_volume_mute",
    "volumedown": "media_volume_down", "volumeup": "media_volume_up",
    "playpause": "media_play_pause", "nexttrack": "media_next",
    "prevtrack": "media_previous", "stop": "media_stop",
}


def tecla_pynput(nombre):
    """Devuelve el miembro pynput.keyboard.Key para un nombre dado, o None.

    Acepta el nombre canonico de Key (ej. 'esc', 'ctrl_l',
    'media_play_pause') o alias habituales de pyautogui/espanol.
    """
    from pynput import keyboard

    if nombre is None:
        return None
    n = str(nombre).strip().lower()
    n = _ALIAS_TECLAS_PYNPUT.get(n, n)
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
