# -*- coding: utf-8 -*-
"""_compartido_linux.py — utilidades comunes del dominio LINUX de computer-use-py.

CONTRACT CENTRAL "TODO se ejecuta sobre Python": el agente llama solo a
python3 scripts/linux/<script>.py; los subprocess internos (xdotool, wmctrl,
xrandr, grim, wtype, ydotool, swaymsg...) son IMPLEMENTACION, no superficie
del agente. La superficie JSON es IDENTICA al dominio Windows (padre
scripts/_compartido.py): stdout siempre JSON UTF-8; error canonico = JSON con
clave "error" + exit 1.

Diferencias de marco con Windows (leer references/linux-python.md):
- X11: el espacio de coordenadas es el del SERVIDOR X; el origen (0,0) es el
  vertice sup-izq del SCREEN completo (no del primario). Negativos: no
  documentados por xrandr => INCERTO; no los asumas.
- Wayland: grim trabaja "in layout coordinates" (man); sway/hypr pueden
  reportar offsets negativos [runtime].
- pyautogui se importa LAZY (funcion _pyautogui() de pantalla/raton/teclado):
  en Wayland o sin DISPLAY el import de pyautogui lanzaria traceback; aqui se
  responde JSON accionable. Donde pyautogui se usa, se fijan FAILSAFE=True y
  PAUSE=0.15 como en el padre (no negociable).

Ejecutar SOLO en Linux. Desde Windows este archivo solo se lee/compila.
"""

import json
import os
import shutil
import subprocess
import sys
import time  # reexportado: los scripts duermen con `c.time.sleep(...)`

# --- Guard de plataforma (inverso al del padre Windows) -------------------
# scripts/linux/ es la rama LINUX: ejecutada en otro SO debe responder el
# JSON canonico de la skill y salir con 2 (mal uso del CLI), nunca un
# traceback o un fallo opaco de las herramientas del dominio.
if sys.platform != "linux":
    print(json.dumps({
        "error": "scripts/linux/ es la rama LINUX; en Windows usa scripts/ "
                 "y en macOS scripts/macos/ (el autotest corre en tu SO)",
        "sistema_operativo": sys.platform,
        # contrato P0-4: `plataforma` canonica tambien en el guard
        "plataforma": {"win32": "win", "linux": "linux",
                       "darwin": "darwin"}.get(sys.platform, sys.platform),
    }, ensure_ascii=False))
    sys.exit(2)

import argparse

# La salida puede llevar titulos UTF-8 con tildes/emojis: forzar UTF-8 con
# reemplazo (mismo borde que el padre en Windows).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --- Helpers stdlib-puro compartidos (SPEC P2-1) --------------------------
# _core.py vive en scripts/ (padre de linux/ y macos/): stdlib-puro, seguro
# en cualquier SO. Se reexporta aqui para que los scripts de la rama sigan
# usando c.json_out/c.fail/... con comportamiento IDENTICO. json_out/fail de
# _core inyectan `plataforma: "linux"` automaticamente (P0-4).
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

# Marco canonico de la rama (P0-4): pixeles de layout del servidor X / grim.
MARCO = "px_layout"


class Parser(argparse.ArgumentParser):
    """argparse cuyos errores salen como JSON canonico (P1-7): subcomando o
    flag invalido => {"error": "argumentos invalidos: ...", "uso": ...} rc 1."""

    def error(self, message):
        fail("argumentos invalidos: %s" % message,
             uso=self.format_usage().strip())


def checar_abort(motivo="interrumpido"):
    """Bandera dura: si existe .tmp/ABORT (vigilar.py) la accion NO se emite."""
    if os.path.exists(ARCHIVO_ABORT):
        fail("%s: existe la bandera ABORT del .tmp de ESTA skill "
             "(vigilar.py): un humano pidio parar. Captura la pantalla y "
             "pregunta antes de continuar." % motivo,
             bandera=ARCHIVO_ABORT)


def checar_pausa(espera_max=300.0):
    """Bandera suave (P1-5): con .tmp/PAUSA la accion se ESPERA (poll 0.2 s,
    tope 300 s) hasta que se borre; ABORT tiene prioridad. Sin bandera: un
    os.path.exists, sin alterar tiempos validados."""
    if not os.path.exists(ARCHIVO_PAUSA):
        return
    inicio = time.time()
    while os.path.exists(ARCHIVO_PAUSA):
        checar_abort("pausa interrumpida")
        if time.time() - inicio > espera_max:
            fail("PAUSA activa mas de %d s (bandera %s): atiende al usuario, "
                 "borra la bandera y reanuda, o usa ABORT para cortar la "
                 "secuencia." % (int(espera_max), ARCHIVO_PAUSA),
                 bandera_pausa=ARCHIVO_PAUSA)
        time.sleep(0.2)


# --- pyautogui lazy (P2-2: unica copia para pantalla/teclado/raton) --------
def pyautogui_lazy():
    """Import perezoso de pyautogui con FAILSAFE/PAUSE del padre (X11-only).

    Consolida las 3 copias de la rama (pantalla/raton/teclado) conservando el
    MENSAJE CANONICO de pantalla.py (el mas detallado): cualquier fallo de
    import responde JSON accionable (Wayland nativo, DISPLAY vacia, librerias
    sin instalar), nunca traceback. FAILSAFE=True y PAUSE=0.15 no negociables
    (igual que el dominio Windows)."""
    try:
        import pyautogui
    except ImportError as exc:
        fail("pyautogui no esta instalado o no se puede importar en esta "
             "ruta: %s. Instalar: python3 -m pip install pyautogui "
             "(y pillow; en Debian/Ubuntu puede exigir python3-tk "
             "[runtime])." % exc)
    except Exception as exc:
        fail("pyautogui no pudo conectarse al display (X11): %s: %s. "
             "Exporta DISPLAY (p. ej. DISPLAY=:1) o confirma la sesion; en "
             "Wayland NATIVO pyautogui no aplica (refs linux-python.md §4)."
             % (type(exc).__name__, exc))
    pyautogui.FAILSAFE = True   # NO NEGOCIABLE (mismo que el dominio Windows)
    pyautogui.PAUSE = 0.15      # >= 0.1 s entre funciones publicas
    return pyautogui


# --- Deteccion de sesion ------------------------------------------------
def deteccion_sesion():
    """Devuelve "x11" | "wayland" | "incognito".

    Orden (ver references/linux-python.md §2; valores XDG_SESSION_TYPE son
    los que publica logind — [runtime]):
      1. XDG_SESSION_TYPE (x11/wayland)
      2. WAYLAND_DISPLAY puesta => wayland
      3. DISPLAY puesta => x11
      4. nada => incognito
    """
    tipo = (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower()
    if tipo in ("x11", "wayland"):
        return tipo
    if (os.environ.get("WAYLAND_DISPLAY") or "").strip():
        return "wayland"
    if (os.environ.get("DISPLAY") or "").strip():
        return "x11"
    return "incognito"


# --- Herramientas del sistema -------------------------------------------
HERRAMIENTAS = ("xdotool", "wmctrl", "xrandr", "scrot", "grim", "slurp",
                "wtype", "ydotool", "kdotool", "swaymsg", "hyprctl",
                "xclip", "xdg-open")

# Hint de instalacion por herramienta: los nombres debian/ubuntu (apt) salen
# del propio rastreo de manpages (xdotool/wmctrl/x11-xserver-utils/grim/
# ydotool/sway); el resto son los habituales — verificar en la distro
# destino [runtime] (references/linux-python.md §INCERTO).
HINTS_PAQUETES = {
    "xdotool": ("apt install xdotool", "dnf install xdotool"),
    "wmctrl": ("apt install wmctrl", "dnf install wmctrl"),
    "xrandr": ("apt install x11-xserver-utils", "dnf install xorg-x11-utils"),
    "scrot": ("apt install scrot", "dnf install scrot"),
    "grim": ("apt install grim", "dnf install grim"),
    "slurp": ("apt install slurp", "dnf install slurp"),
    "wtype": ("apt install wtype", "dnf install wtype"),
    "ydotool": ("apt install ydotool (arranca ydotoold; grupo input)",
                "dnf install ydotool (arranca ydotoold; grupo input)"),
    "kdotool": ("apt install kdotool [runtime]", "dnf install kdotool [runtime]"),
    "swaymsg": ("apt install sway", "dnf install sway"),
    "hyprctl": ("apt install hyprland [runtime]", "dnf install hyprland [runtime]"),
    "xclip": ("apt install xclip", "dnf install xclip"),
    "xdg-open": ("apt install xdg-utils", "dnf install xdg-utils"),
}


def herramientas():
    """Dict nombre -> ruta absoluta o None (shutil.which sobre HERRAMIENTAS)."""
    return {nombre: shutil.which(nombre) for nombre in HERRAMIENTAS}


def require(nombre):
    """Ruta de la herramienta o fail() con hint apt/dnf accionable."""
    ruta = shutil.which(nombre)
    if ruta is None:
        apt, dnf = HINTS_PAQUETES.get(nombre, ("apt install %s" % nombre,
                                               "dnf install %s" % nombre))
        fail("La herramienta '%s' no esta en el PATH de Linux." % nombre,
             herramienta=nombre,
             hint="instalar: %s  |  o bien: %s" % (apt, dnf))
    return ruta


def run(cmd, args=None, timeout=10.0, entrada=None):
    """subprocess envuelto JSON-safe: NUNCA deja traceback.

    cmd: nombre del binario (se resuelve con require() => fail con hint) o
    lista [binario, ...]. args: lista de argumentos. entrada: bytes/str para
    stdin. Devuelve {"rc", "stdout", "stderr", "cmd"} con textos UTF-8
    (errors=replace). Timeout => fail con JSON (rc no lanzado).
    """
    if isinstance(cmd, (list, tuple)):
        binario, argv = cmd[0], list(cmd[1:])
    else:
        binario, argv = cmd, list(args or [])
    ruta = require(binario)
    if isinstance(entrada, str):
        entrada = entrada.encode("utf-8")
    try:
        proc = subprocess.run([ruta] + [str(a) for a in argv],
                              input=entrada,
                              stdin=None if entrada is not None else subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        fail("Tiempo de espera agotado (%s s) ejecutando: %s %s"
             % (timeout, ruta, " ".join(str(a) for a in argv)),
             cmd=[ruta] + [str(a) for a in argv])
    except OSError as exc:
        fail("No se pudo ejecutar %r: %s: %s" % (ruta, type(exc).__name__, exc),
             cmd=[ruta] + [str(a) for a in argv])
    return {
        "rc": proc.returncode,
        "stdout": (proc.stdout or b"").decode("utf-8", "replace"),
        "stderr": (proc.stderr or b"").decode("utf-8", "replace"),
        "cmd": [ruta] + [str(a) for a in argv],
    }


def run_ok(cmd, args=None, timeout=10.0, entrada=None):
    """run() + exigir rc==0: si rc!=0, fail() con stdout/stderr crudos."""
    r = run(cmd, args, timeout, entrada)
    if r["rc"] != 0:
        fail("El comando salio con rc=%d: %s" % (r["rc"], " ".join(r["cmd"])),
             stderr=r["stderr"].strip(), stdout=r["stdout"].strip())
    return r


def _shell_kv(texto):
    """Parsea bloques 'CLAVE=valor' (xdotool --shell / grim) en dict."""
    salida = {}
    for linea in texto.splitlines():
        linea = linea.strip()
        if "=" in linea:
            k, _, v = linea.partition("=")
            salida[k.strip()] = v.strip()
    return salida


# --- Mapa de monitores ----------------------------------------------------
# X11: xrandr --listmonitors (opcion verificada en man xrandr; el FORMATO de
# salida es empirico => parser tolerante, [runtime] ver
# references/linux-python.md §6). Wayland: swaymsg -t get_outputs (man
# swaymsg) o hyprctl monitors -j [runtime]. Las entradas traen SIEMPRE
# izq/top/ancho/alto en coords de layout y "via".

def _monitores_x11():
    r = run_ok("xrandr", ["--listmonitors"], timeout=15.0)
    import re
    mons = []
    # linea tipo:  0: +*HDMI-1 1920/508x1080/286+0+0  HDMI-1
    for linea in r["stdout"].splitlines():
        m = re.match(r"\s*(\d+):\s+([+*-]*)(\S+)\s+(\d+)(?:/\d+)?x(\d+)(?:/\d+)?"
                     r"([+-]\d+)([+-]\d+)\s+(\S+)", linea)
        if not m:
            continue
        flags, nombre = m.group(2), m.group(3)
        mons.append({
            "nombre": nombre,
            "izq": int(m.group(6)), "top": int(m.group(7)),
            "ancho": int(m.group(4)), "alto": int(m.group(5)),
            "primario": "*" in flags,
            "activo": "+" in flags,
            "output": m.group(8),
        })
    if not mons:
        fail("No pude parsear 'xrandr --listmonitors' (formato inesperado: "
             "ver references/linux-python.md §INCERTO). Volcar la salida a "
             "mano y reportar el formato.",
             salida=r["stdout"].strip()[:400])
    if not any(m["primario"] for m in mons):
        # sin '*' (RandR sin primario): el primero manda como primario a
        # efectos de --monitor primario [runtime]
        mons[0]["primario"] = True
    for i, m in enumerate(mons):
        m["indice"] = i
        m["der"] = m["izq"] + m["ancho"]
        m["bot"] = m["top"] + m["alto"]
        m["via"] = "xrandr --listmonitors"
    return mons


def _monitores_wayland():
    # sway / i3-compatible (man swaymsg: -t get_outputs "list of current
    # outputs"; campos rect/primary leidos defensivamente [runtime]).
    if shutil.which("swaymsg"):
        r = run("swaymsg", ["-t", "get_outputs"], timeout=15.0)
        if r["rc"] == 0:
            try:
                datos = json.loads(r["stdout"])
            except ValueError:
                datos = None
            if isinstance(datos, list):
                mons = []
                for o in datos:
                    if not isinstance(o, dict):
                        continue
                    if o.get("active") is False:
                        continue
                    rect = o.get("rect") or {}
                    if "width" not in rect:
                        continue
                    mons.append({
                        "nombre": o.get("name", "?"),
                        "izq": int(rect.get("x", 0)), "top": int(rect.get("y", 0)),
                        "ancho": int(rect.get("width", 0)),
                        "alto": int(rect.get("height", 0)),
                        "primario": bool(o.get("primary", False)),
                        "activo": True,
                        "output": o.get("name", "?"),
                        "via": "swaymsg -t get_outputs (sway-ipc [runtime])",
                    })
                    mons[-1]["der"] = mons[-1]["izq"] + mons[-1]["ancho"]
                    mons[-1]["bot"] = mons[-1]["top"] + mons[-1]["alto"]
                if mons:
                    for i, m in enumerate(mons):
                        m["indice"] = i
                    if not any(m["primario"] for m in mons):
                        # sin flag primary en el JSON: el primero manda como
                        # primario a efectos de --monitor primario [runtime]
                        mons[0]["primario"] = True
                    return mons
    # Hyprland [runtime] (no fetcheado; campos leidos defensivamente).
    if shutil.which("hyprctl"):
        r = run("hyprctl", ["monitors", "-j"], timeout=15.0)
        if r["rc"] == 0:
            try:
                datos = json.loads(r["stdout"])
            except ValueError:
                datos = None
            if isinstance(datos, list) and datos:
                mons = []
                for o in datos:
                    if o.get("disabled"):
                        continue
                    mons.append({
                        "nombre": o.get("name", "?"),
                        "izq": int(o.get("x", 0)), "top": int(o.get("y", 0)),
                        "ancho": int(o.get("width", 0)),
                        "alto": int(o.get("height", 0)),
                        "primario": bool(o.get("primary", False)),
                        "activo": not bool(o.get("disabled", False)),
                        "output": o.get("name", "?"),
                        "via": "hyprctl monitors -j [runtime]",
                    })
                    mons[-1]["der"] = mons[-1]["izq"] + mons[-1]["ancho"]
                    mons[-1]["bot"] = mons[-1]["top"] + mons[-1]["alto"]
                for i, m in enumerate(mons):
                    m["indice"] = i
                if not any(m["primario"] for m in mons):
                    mons[0]["primario"] = True
                return mons
    fail("Wayland detectado pero halle ni swaymsg -t get_outputs ni hyprctl "
         "monitors -j una lista de monitores utilizable. En GNOME/KDE "
         "Wayland esta skill no tiene API documentada: usa los atajos del "
         "compositor o reporta el compositor en uso (references/"
         "linux-python.md §8).",
         sesion="wayland",
         herramientas_disponibles=list(herramientas().items()))


def monitores():
    """Lista de monitores en coordenadas de LAYOUT (X11: screen; Wayland)."""
    sesion = deteccion_sesion()
    if sesion == "x11":
        return _monitores_x11()
    if sesion == "wayland":
        return _monitores_wayland()
    fail("Sesion grafica sin detectar (XDG_SESSION_TYPE/WAYLAND_DISPLAY/"
         "DISPLAY vacios): no hay forma de leer monitores. En cron/SSH "
         "exporta DISPLAY=:1 (X11) o WAYLAND_DISPLAY+XDG_RUNTIME_DIR "
         "(Wayland). Ver references/linux-python.md §13.", sesion=sesion)


def tamano_virtual():
    """Bounding de todos los monitores: dict {x, y, ancho, alto} (layout)."""
    mons = monitores()
    izq = min(m["izq"] for m in mons)
    top = min(m["top"] for m in mons)
    der = max(m["der"] for m in mons)
    bot = max(m["bot"] for m in mons)
    return {"x": izq, "y": top, "ancho": der - izq, "alto": bot - top}


def _monitor_contiene(x, y):
    """Monitor cuyo rectangulo contiene a (x, y) de layout, o None."""
    xi, yi = int(x), int(y)
    for m in monitores():
        if m["izq"] <= xi < m["der"] and m["top"] <= yi < m["bot"]:
            return m
    return None


def dentro_de_virtual(x, y):
    """True si (x, y) cae dentro del bounding de layout."""
    v = tamano_virtual()
    return (v["x"] <= int(x) < v["x"] + v["ancho"]
            and v["y"] <= int(y) < v["y"] + v["alto"])


def tamano_pantalla():
    """(ancho, alto) del monitor primario (o del primero si nadie marca
    primario [runtime])."""
    for m in monitores():
        if m["primario"]:
            return m["ancho"], m["alto"]
    m = monitores()[0]
    return m["ancho"], m["alto"]


# --- Alias de teclas -----------------------------------------------------
# pyautogui (X11) usa KEYBOARD_KEYS; pynput (X11) expone keyboard.Key con
# nombres propios; esta tabla traduce alias frecuentes (incluye la del padre
# duplicada a proposito: el parent es Windows-only y no se puede importar).
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
    "volumemute": "media_volume_mute", "mute": "media_volume_mute",
    "volumedown": "media_volume_down", "volumeup": "media_volume_up",
    "playpause": "media_play_pause", "nexttrack": "media_next",
    "prevtrack": "media_previous", "stop": "media_stop",
}


def tecla_pynput(nombre):
    """Miembro pynput.keyboard.Key para un nombre/alias, o None (X11 only)."""
    from pynput import keyboard

    if nombre is None:
        return None
    n = str(nombre).strip().lower()
    n = _ALIAS_TECLAS_PYNPUT.get(n, n)
    return getattr(keyboard.Key, n, None)


# --- Codigo de teclas para ydotool (Wayland) -----------------------------
# Sintaxis 'CODE:1 CODE:0' VERIFICADA en man ydotool (28=Enter, y el ejemplo
# LOL con 38=L, 24=O, 42=Shift). La tabla completa sigue
# /usr/include/linux/input-event-codes.h (referenciado por el propio man);
# valores distintos de 28/38/24/42: [runtime] en la distro destino.
KEY_CODES = {
    "esc": 1, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8,
    "8": 9, "9": 10, "0": 11, "minus": 12, "equal": 13, "backspace": 14,
    "tab": 15, "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21,
    "u": 22, "i": 23, "o": 24, "p": 25, "bracketleft": 26, "left": 105,
    "bracketright": 27, "enter": 28, "ctrl": 29, "ctrl_l": 29,
    "a": 30, "s": 31, "d": 32, "f": 33, "g": 34, "h": 35, "j": 36,
    "k": 37, "l": 38, "z": 39, "x": 40, "c": 41, "v": 47, "b": 48,
    "n": 49, "m": 50, "comma": 51, "dot": 52, "slash": 53,
    "shift": 42, "shift_l": 42, "shift_r": 54, "alt": 56, "alt_l": 56,
    "alt_r": 100, "space": 57, "capslock": 58,
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64,
    "f7": 65, "f8": 66, "f9": 67, "f10": 68, "f11": 87, "f12": 88,
    "super": 125, "super_l": 125, "super_r": 126, "menu": 139,
    "home": 102, "up": 103, "pageup": 104, "right": 106, "end": 107,
    "down": 108, "pagedown": 109, "insert": 110, "delete": 111,
    "mute": 113, "volumeup": 114, "volumedown": 115,
}

_MODS_YDOTOOL = ("ctrl", "ctrl_l", "ctrl_r", "shift", "shift_l", "shift_r",
                 "alt", "alt_l", "alt_r", "super", "super_l", "super_r")


# --- FAILSAFE (paridad con el padre) --------------------------------------
def fallar_por_failsafe(exc):
    """Traduce FailSafeException (pyautogui X11) a error JSON accionable."""
    fail(
        "FAILSAFE: el cursor toco una esquina de la pantalla y la secuencia "
        "se aborto (comportamiento intencional, no un bug). Revisa la "
        "pantalla con pantalla.py capturar antes de continuar.",
        tipo=type(exc).__name__,
        detalle=str(exc),
    )
