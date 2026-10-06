# -*- coding: utf-8 -*-
"""linux_especiales.py — Primitivas EXCLUSIVAS de LINUX + CLI del dominio
(skill computer-use-py). FASE SEG3.

UNICO archivo de scripts/linux/: es una LIBRERIA con lo exclusivamente-Linux
(xrandr/xdotool/wmctrl/xprop/grim/wtype/ydotool/swaymsg/hyprctl/xclip, la
deteccion de sesion y las herramientas del SO) que los CLIs de la raiz
scripts/<verbo>.py usan como modulo de primitivas. Desde SEG3 NO existe el
enrutador SEG2 que relanzaba la rama: la entrada NORMAL es scripts/<verbo>.py
(raiz, multi-OS) y, en Linux, ese CLI ejecuta SU ruta en el PROPIO PROCESO
importando ESTE modulo via _core.modulo_sistema() (bind `c = linux_especiales`;
las primitivas bajadas conservan sus llamadas `c.X()` gracias al self-alias
documentado mas abajo).

REGLA SEG3 DEL GUARD: como LIBRERIA este modulo se importa en CUALQUIER SO
(Windows/macOS incluidos) sin imprimir nada ni sys.exit — el guard de
plataforma NO vive en el nivel-import sino SOLO en el main() del CLI: ejecutado
como script fuera de Linux responde ANTES de parsear un JSON con clave "error"
(linux_especiales como CLI es el dominio EXCLUSIVO de LINUX; la libreria si es
importable), "sistema_operativo" y "plataforma" canonica, y sale con rc 2.

CONTRACT CENTRAL "TODO se ejecuta sobre Python": el agente llama solo a
python3 scripts/<script>.py (CLI raiz multi-OS); los subprocess internos
(xdotool, wmctrl, xrandr, grim, wtype, ydotool, swaymsg...) son IMPLEMENTACION,
no superficie del agente. La superficie JSON es IDENTICA al dominio Windows
(glue_windows.py en la raiz de scripts/): stdout siempre JSON UTF-8; error
canonico = JSON con clave "error" + exit 1.

Diferencias de marco con Windows (leer references/linux-python.md):
- X11: el espacio de coordenadas es el del SERVIDOR X; el origen (0,0) es el
  vertice sup-izq del SCREEN completo (no del primario). Negativos: no
  documentados por xrandr => INCERTO; no los asumas.
- Wayland: grim trabaja "in layout coordinates" (man); sway/hypr pueden
  reportar offsets negativos [runtime].
- pyautogui/pynput se importan LAZY (dentro de funciones): en Wayland o sin
  DISPLAY el import lanzaria traceback; aqui se responde JSON accionable.
  Donde pyautogui se usa, se fijan FAILSAFE=True y PAUSE=0.15 como en el padre
  (no negociable).

Contenido (particion SEG3, cuerpos VERBATIM, nombres exactos):
1. Base integra del viejo _compartido_linux.py (reexports de _core, MARCO,
   primitivas propias: pyautogui_lazy, deteccion_sesion, HERRAMIENTAS,
   HINTS_PAQUETES, herramientas, require, run, run_ok, _shell_kv,
   _monitores_x11, _monitores_wayland, monitores, tamano_virtual,
   _monitor_contiene, dentro_de_virtual, tamano_pantalla, tecla_pynput,
   KEY_CODES, _MODS_YDOTOOL, fallar_por_failsafe).
2. Primitivas que BAJARON de los CLIs de rama por la regla de frontera
   (ejecutan herramientas del SO) y por clausura: de pantalla.py
   (_grim_factor, _grim_abrir, _cursor_layout, _captura_wayland + _pillow y
   _resolver_monitor por clausura de sus cuerpos), de teclado.py
   (_escribir_wtype, _tecla_wtype, _KEYSYMS, _ydotool_seq, _code_de,
   _emitir_combo_ydotool, _titulo_foco, _buscar_foco,
   _verificar_foco_requerido + _escribir_portapapeles [helper xclip de la
   regla portapapeles] y su _pyautogui por clausura), de raton.py (_ydotool,
   _CLICK_YDOTOOL, _DOWN_YDOTOOL, _UP_YDOTOOL, _AVISO_WAYLAND, _cursor) y de
   ventanas.py (_HAY_XPROP, _rect_shell, _item_canon, _maximizada_x11,
   _nodo_json, _listar_x11, _buscar_x11, _rect_x11, _cmd_x11, _sway_nodos,
   _listar_sway, _sway_foco, _accion_sway, _hypr_listar, _wayland_listar,
   _wayland_foco, _ids_conocidas, _nueva_ventana). Los cmd_* y lo demas
   generico NO bajan: viven en la seccion linux de los CLIs raiz.

CLI propio SOLO-LINUX (modelo: scripts/windows/win_especiales.py): estado del
dominio y primitivas puntuales que no tienen verbo generico.

Subcomandos:
  sesion                deteccion de sesion + herramientas del SO disponibles
  xrandr                lista CRUDA de monitores (xrandr/swaymsg/hyprctl)
  grim                  captura Wayland del layout completo hacia --archivo
  portapapeles leer     texto del clipboard (pyperclip/xclip, como la rama)
  portapapeles escribir "TEXTO" (sin pegar: pegar es teclado.py)
  wayland-status        sesion + tools + verbos genericos resueltos en Wayland

Ejemplos (desde la carpeta computer-use-py, en la maquina Linux):
  python3 scripts/linux/linux_especiales.py sesion
  python3 scripts/linux/linux_especiales.py xrandr
  python3 scripts/linux/linux_especiales.py grim --archivo prueba.png
  python3 scripts/linux/linux_especiales.py portapapeles leer
  python3 scripts/linux/linux_especiales.py portapapeles escribir "hola"
  python3 scripts/linux/linux_especiales.py wayland-status
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time  # reexportado: los scripts duermen con `c.time.sleep(...)`

# --- Guard de plataforma: SOLO en el CLI (FASE SEG3) -----------------------
# Antes este guard vivia en el nivel-import de _compartido_linux.py y cortaba
# el import en otro SO. En SEG3 el modulo es LIBRERIA importable en cualquier
# SO (los CLIs raiz lo bind-ean via _core.modulo_sistema), asi que el guard
# bajo al main() del CLI propio (`_guard_cli`): ejecutado como script fuera de
# Linux responde JSON canonico y rc 2 ANTES de parsear; importado, no imprime
# ni sale.

# (argparse: desde SEG3 este modulo SI trae su propio CLI solo-Linux abajo;
#  la clase Parser generica sigue viviendo en scripts/_core.py.)

# La salida puede llevar titulos UTF-8 con tildes/emojis: forzar UTF-8 con
# reemplazo (mismo borde que el padre en Windows).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --- Helpers GENERICOS multi-OS (scripts/_core.py) — reexportados ----------
# _core.py vive en scripts/ (padre de linux/ y macos/): stdlib-puro, seguro
# en cualquier SO. Se reexporta aqui para que los CLIs raiz (que bind c =
# este modulo) y el CLI propio sigan usando c.json_out/c.fail/... con
# comportamiento IDENTICO. json_out/fail de _core inyectan `plataforma:
# "linux"` automaticamente (P0-4).
# FASE SEG: a _core se movio TODO lo que estaba duplicado palabra-por-palabra
# con las otras ramas (Parser, banderas ABORT/PAUSA, validaciones de args,
# bucles de espera, color/combos, geometria de rects, tablas y destino de
# capturas). En los mensajes donde linux divergia solo ortograficamente del
# padre Windows ("reanuda" vs "relanza", "pequeno" vs "pequeño") gana el
# texto WINDOWS, canonico por ser la rama validada en escritorio real.
# El autotest de estructura exige no redefinir aqui ningun HELPERS_COMUNES.
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

# Marco canonico de la rama (P0-4): pixeles de layout del servidor X / grim.
MARCO = "px_layout"


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
             hint="instalar: %s | o bien: %s" % (apt, dnf))
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
    """Bounding de todos los monitores: dict {x, y, ancho, alto} (layout).

    La formula min/max es generica (_core.bounding_de); la fuente xrandr/
    sway/hypr es lo unico linux de aqui."""
    return _core.bounding_de(monitores())


def _monitor_contiene(x, y):
    """Monitor cuyo rectangulo contiene a (x, y) de layout, o None.

    Comparacion generica (_core.monitor_contiene); aqui solo la lista X11/
    Wayland de la rama."""
    return _core.monitor_contiene(monitores(), x, y)


def dentro_de_virtual(x, y):
    """True si (x, y) cae dentro del bounding de layout.

    Comparacion generica (_core.dentro_del_bounding) sobre el tamano_virtual
    de la rama."""
    return _core.dentro_del_bounding(tamano_virtual(), x, y)


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
# nombres propios. La tabla ALIAS_TECLAS_PYNPUT que traduce alias frecuentes
# era copia IDENTICA a la del padre Windows (win/linux comparten esos miembros
# del enum Key) y vivo a scripts/_core.py: se reexporta arriba. Este
# envoltorio se queda en la rama: pynput no es stdlib-pura (tecla_pynput_mac
# en macOS usa SU propia tabla porque darwin no tiene print_screen/pause/menu).


def tecla_pynput(nombre):
    """Miembro pynput.keyboard.Key para un nombre/alias, o None (X11 only)."""
    from pynput import keyboard

    if nombre is None:
        return None
    n = str(nombre).strip().lower()
    n = ALIAS_TECLAS_PYNPUT.get(n, n)
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


# --- Self-alias (FASE SEG3) ------------------------------------------------
# Las primitivas que bajaron de los CLIs de rama traen cuerpos VERBATIM que se
# llamaban entre si `c.X()` (convencion de la rama SEG2, donde c era
# _compartido_linux). Bind-ear `c` a ESTE mismo modulo deja los cuerpos
# INTACTOS: c.<primitiva>() resuelve al nombre definido aqui, tanto al
# importarse como `linux_especiales` (binding de los CLIs raiz via
# _core.modulo_sistema) como al ejecutarse este archivo como script (__main__).
c = sys.modules[__name__]


# ===========================================================================
# PRIMITIVAS BAJADAS DE LOS CLIs DE RAMA (FASE SEG3)
# Regla de frontera: solo baja lo que ejecuta herramientas del SO (o cae por
# clausura). Cuerpos VERBATIM de scripts/linux/<cli>.py con sus nombres
# exactos; los archivos originales NO se tocan aqui (R1/R2 los particiona).
# ===========================================================================

# --- de scripts/linux/pantalla.py ------------------------------------------


def _grim_factor():
    """Factor de escala global que grim aplica en Wayland (man grim: escala
    max. de los outputs [runtime]). Fuente honesta: swaymsg -t get_outputs
    campo 'scale'. Sin dato => None (no inventar; la nota/`regla` avisan)."""
    if not shutil.which("swaymsg"):
        return None
    r = c.run("swaymsg", ["-t", "get_outputs"], timeout=10.0)
    if r["rc"] != 0:
        return None
    try:
        datos = json.loads(r["stdout"])
        scales = []
        for o in datos:
            if isinstance(o, dict) and o.get("active") is not False:
                try:
                    scales.append(float(o.get("scale", 1) or 1))
                except (TypeError, ValueError):
                    pass
        return max(scales) if scales else None
    except ValueError:
        return None


def _pillow():
    """Import perezoso de (Image, ImageGrab) con hint accionable.

    SEG3: la spec la dejaba en la raiz, pero el cuerpo verbatim de _grim_abrir
    la llama desnuda => baja por clausura para que la libreria sea
    autocontenida; la raiz conserva su copia sufijada para _captura_x11."""
    try:
        from PIL import Image, ImageGrab
    except ImportError as exc:
        c.fail("Falta Pillow: %s. Instalar: python3 -m pip install pillow "
               ">= 9.2 (ImageGrab Linux usa XCB [runtime])." % exc)
    return Image, ImageGrab


def _cursor_layout():
    """(x, y) del cursor solo en X11 (xdotool shell); None fuera de X11."""
    if c.deteccion_sesion() != "x11":
        return None
    r = c.run("xdotool", ["getmouselocation", "--shell"], timeout=10.0)
    if r["rc"] != 0:
        return None
    kv = c._shell_kv(r["stdout"])
    try:
        return int(kv["X"]), int(kv["Y"])
    except (KeyError, ValueError):
        return None


def _resolver_monitor(valor):
    """--monitor: None si 'virtual' (bounding) | dict del monitor (mismo
    contrato que el padre: indice, 'primario' o subcadena del nombre).

    El algoritmo es el generico de _core.resolver_monitor; aqui quedan la
    FUENTE de la lista (xrandr/sway/hypr) y los TEXTOS con jerga de Linux
    ("*" de xrandr, primary de sway/hypr).

    SEG3: la spec lo dejaba en la raiz, pero el cuerpo verbatim de
    _captura_wayland lo llama desnudo => baja por clausura (los TEXTOS son
    jerga Linux = primitiva-SO, no generico puro); la raiz conserva su copia
    sufijada para _captura_x11."""
    return c.resolver_monitor(
        valor, c.monitores,
        sin_primario="Ningun monitor figura como primario (ni xrandr '*' ni "
                     "sway/hypr primary): trata el primero como tal o revisa "
                     "monitores.py listar.",
        indice_rango="Indice de monitor %d fuera de rango (0..%d). "
                     "Mapa: monitores.py listar.",
        ambiguo="La subcadena %r coincide con varios monitores (%s): usa el "
                "indice.",
        sin_nombre="Ningun monitor tiene el nombre %r. Mapa: monitores.py "
                   "listar.")


def _grim_abrir(ruta):
    """PIL abre el PNG de grim y lo CARGA en memoria: permitiria sobreescribir
    el mismo ruta (crop/reescalado) sin escribir sobre un archivo abierto."""
    Image, _ = _pillow()
    im = Image.open(ruta)
    im.load()
    return im


def _captura_wayland(args, ruta):
    """(imagen PIL, origen_layout, via, en_ruta_final) en Wayland con grim.
    en_ruta_final=True cuando el PNG ya esta en `ruta` sin recortar/reescalar.
    """
    v = c.tamano_virtual()
    if args.monitor is not None:
        m = _resolver_monitor(args.monitor)
        if m is None:  # bounding de layout = captura completa
            c.run_ok("grim", [ruta], timeout=20.0)
            return _grim_abrir(ruta), [v["x"], v["y"]], \
                "grim (layout completo)", True
        # captura por output (man verbatim: "-o <output> Set the output name")
        r = c.run("grim", ["-o", m["nombre"], ruta], timeout=20.0)
        if r["rc"] == 0:
            return _grim_abrir(ruta), [m["izq"], m["top"]], \
                "grim -o %s" % m["nombre"], True
        # respaldo: layout completo + crop (grim -o no soportado por el
        # compositor) [runtime]
        c.run_ok("grim", [ruta], timeout=20.0)
        imagen = _grim_abrir(ruta)
        bbox = (m["izq"] - v["x"], m["top"] - v["y"],
                m["der"] - v["x"], m["bot"] - v["y"])
        if not (0 <= bbox[0] and 0 <= bbox[1]
                and bbox[2] <= imagen.width and bbox[3] <= imagen.height):
            c.fail("Rectangulo de %r (%s) cae fuera de la captura de grim: "
                   "desajuste entre el mapa de monitores y el layout real. "
                   "Mapa: monitores.py listar."
                   % (m["nombre"], str(bbox)))
        return imagen.crop(bbox), [m["izq"], m["top"]], \
            "grim completo + crop PIL (respaldo; grim -o fallo)", False
    if args.region is not None:
        x, y, w, h = args.region
        if w <= 0 or h <= 0:
            c.fail("Region invalida: ancho/alto deben ser > 0.")
        r = c.run("grim", ["-g", "%d,%d %dx%d" % (x, y, w, h), ruta],
                  timeout=20.0)
        if r["rc"] != 0:
            c.fail("grim -g rechazo la region (%d, %d, %d, %d): %s"
                   % (x, y, w, h, r["stderr"].strip()),
                   region_formato="grim -g \"<x>,<y> <W>x<H>\" (man verbatim)")
        return _grim_abrir(ruta), [x, y], "grim -g region", True
    # default historico del padre: "la pantalla" = monitor PRIMARIO
    primario = None
    for m in c.monitores():
        if m["primario"]:
            primario = m
            break
    if primario is not None:
        r = c.run("grim", ["-o", primario["nombre"], ruta], timeout=20.0)
        if r["rc"] == 0:
            return _grim_abrir(ruta), [primario["izq"], primario["top"]], \
                "grim -o %s (primario)" % primario["nombre"], True
        c.run_ok("grim", [ruta], timeout=20.0)
        imagen = _grim_abrir(ruta)
        bbox = (primario["izq"] - v["x"], primario["top"] - v["y"],
                primario["der"] - v["x"], primario["bot"] - v["y"])
        return imagen.crop(bbox), [primario["izq"], primario["top"]], \
            "grim completo + crop PIL (primario; grim -o fallo)", False
    c.run_ok("grim", [ruta], timeout=20.0)
    return _grim_abrir(ruta), [v["x"], v["y"]], \
        "grim (layout completo; sin primario)", True


# --- de scripts/linux/teclado.py -------------------------------------------


def _pyautogui():
    """Import LAZY delegado al helper unico de la rama (P2-2).

    SEG3: baja por clausura desde _escribir_portapapeles (su cuerpo lo llama
    desnudo); resuelve al pyautogui_lazy de ESTE modulo via el self-alias c."""
    return c.pyautogui_lazy()


def _titulo_foco():
    """Titulo de la ventana activa o None (best effort por sesion)."""
    sesion = c.deteccion_sesion()
    if sesion == "x11":
        r = c.run("xdotool", ["getactivewindow", "getwindowname"], timeout=10.0)
        if r["rc"] != 0:
            return None
        return r["stdout"].strip() or None
    if sesion == "wayland":
        import json as _json
        import shutil
        if shutil.which("swaymsg"):
            r = c.run("swaymsg", ["-t", "get_tree"], timeout=15.0)
            if r["rc"] == 0:
                try:
                    nodo = _buscar_foco(_json.loads(r["stdout"]))
                except ValueError:
                    nodo = None
                if nodo is not None:
                    return nodo
        elif shutil.which("hyprctl"):
            r = c.run("hyprctl", ["activewindow", "-j"], timeout=15.0)
            if r["rc"] == 0:
                try:
                    d = _json.loads(r["stdout"])
                    return d.get("title")  # [runtime] hyprctl -j no fetcheado
                except ValueError:
                    return None
        return None
    return None


def _buscar_foco(nodo):
    """Recorre el arbol sway buscando el primer nodo focused con nombre."""
    import json  # noqa: F401 (el llamador ya parseo; recursion pura)
    if isinstance(nodo, dict):
        if nodo.get("focused") and nodo.get("name"):
            return nodo["name"]
        for clave in ("nodes", "floating_nodes", "window", "contents"):
            hijo = nodo.get(clave)
            if isinstance(hijo, list):
                for sub in hijo:
                    t = _buscar_foco(sub)
                    if t:
                        return t
    return None


def _foco_id_actual():
    """(id|None) de la ventana activa segun sesion (IMPL-K P0.1).

    X11: xdotool getactivewindow (decimal, _NET_ACTIVE_WINDOW); Wayland:
    nodo focused de sway (con_id entero) o hyprctl activewindow (address).
    El id se devuelve como str para comparar con int(x, 0) en el gate."""
    sesion = c.deteccion_sesion()
    if sesion == "x11":
        r = c.run("xdotool", ["getactivewindow"], timeout=10.0)
        if r["rc"] != 0:
            return None
        try:
            return str(int(r["stdout"].strip(), 0))
        except (TypeError, ValueError):
            return None
    if sesion == "wayland":
        try:
            n, _via = _wayland_foco()
        except SystemExit:
            raise
        except Exception:
            return None
        if n is None or n.get("id") is None:
            return None
        return str(n["id"])
    return None


def _verificar_foco_requerido(subcadena, foco_id=None):
    """Comprueba el foco ANTES de emitir (flags --requiere-foco/--foco-id).

    Con --foco-id exige que la ventana activa tenga EXACTAMENTE ese id
    (comparacion numerica base 0: "123" y "0x7b" valen lo mismo, porque
    xdotool imprime decimal y wmctrl hex). Con ambos flags exige ambos.
    El error JSON trae ventana_actual{id,titulo} (contrato IMPL-K P0.1)."""
    actual = {"id": _foco_id_actual() if foco_id is not None else None,
              "titulo": _titulo_foco() if subcadena else None}
    if foco_id is not None:
        igual = False
        if actual["id"] is not None:
            try:
                igual = int(str(actual["id"]), 0) == int(str(foco_id), 0)
            except (TypeError, ValueError):
                igual = str(actual["id"]) == str(foco_id)
        if not igual:
            c.fail("Foco incorrecto: NO se emitio nada. La ventana activa "
                   "tiene id %r y --foco-id pedia %r. Pon el foco correcto "
                   "(ventanas.py activar --id %s / clic) o retira el flag "
                   "asumiendo el riesgo." % (actual["id"], foco_id, foco_id),
                   ventana_actual=actual, requiere=subcadena,
                   requiere_id=foco_id,
                   pista="ventanas.py foco/listar muestran el id por sesion "
                         "(X11 decimal/hex segun la fuente)")
    if subcadena and (actual["titulo"] is None or
                      subcadena.lower() not in actual["titulo"].lower()):
        c.fail("Foco incorrecto: NO se emitio nada. La ventana activa es %r y "
               "--requiere-foco pedia contener %r. Pon el foco correcto "
               "(ventanas.py activar / clic) o retira el flag asumiendo el "
               "riesgo." % (actual["titulo"], subcadena),
               ventana_actual=actual, titulo_actual=actual["titulo"],
               requiere=subcadena,
               pista="ventanas.py foco muestra la ventana foreground actual")
    return actual["titulo"] if subcadena else actual["id"]


def _buscar_por_id(valor):
    """Ventana con id estable EXACTO (IMPL-K P0.1 --id N): compara como
    enteros base 0 (xdotool decimal == wmctrl hex == sway con_id == hypr
    address). Devuelve el dict crudo de la sesion o error JSON con pistas."""
    sesion = c.deteccion_sesion()
    if sesion == "x11":
        ventanas = _listar_x11()
    elif sesion == "wayland":
        ventanas = _wayland_listar()[0]
    else:
        c.fail("Sesion grafica sin detectar: no hay ids de ventana que "
               "resolver (refs linux-python.md §2/§13).", sesion=sesion)
    try:
        objetivo = int(str(valor), 0)
    except (TypeError, ValueError):
        objetivo = None
    for v in ventanas:
        try:
            if objetivo is not None and int(str(v["id"]), 0) == objetivo:
                return v
        except (TypeError, ValueError):
            if str(v["id"]) == str(valor):
                return v
    c.fail("Ninguna ventana tiene el id %r. Usa listar: los ids por sesion "
           "son X11 (wmctrl/xdotool), sway con_id o hypr address." % valor,
           coincidencias=0,
           ventanas_abiertas=["%s: %s" % (v["id"], v["titulo"])
                              for v in ventanas][:25])


def _xclip_escribir(texto):
    """Escribe TEXTO en el clipboard via xclip SIN bloquear (fix A2-W11).

    Por que NO `run()` (subprocess.run con PIPE): al escribir, xclip se FORKEA
    (demoniza) para retener la propiedad de la seleccion CLIPBOARD y seguirla
    sirviendo a las demas aplicaciones; el demonio hereda los descriptores de
    las PIPE de stdout/stderr y subprocess.run espera su cierre => bloquea
    hasta el timeout (10 s) aunque la escritura ya fue exitosa. Por eso:
      * stdout/stderr = DEVNULL: cero tuberias que el demonio pueda retener;
      * stdin = PIPE: se escribe el texto y se CIERRA (EOF => xclip ya leyo
        todo y hace el fork);
      * NO wait()/communicate(): el fork sigue vivo sirviendo la seleccion y
        esperarlo volveria a colgar. Se pierde el rc a proposito (trade-off
        documentado): xclip ausente lo atrapa require() y un xclip que muere
        al recibir el texto (p. ej. sin DISPLAY) se manifiesta como
        BrokenPipeError/OSError en el write.

    Devuelve el Popen (solo para assertions de pruebas/mock; los cmd_* no lo
    usan)."""
    ruta = require("xclip")
    try:
        proc = subprocess.Popen([ruta, "-selection", "clipboard"],
                                stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except OSError as exc:
        fail("No se pudo lanzar xclip (%s: %s). Instalar: apt install xclip "
             "/ dnf install xclip." % (type(exc).__name__, exc))
    try:
        proc.stdin.write(texto.encode("utf-8"))
    except (BrokenPipeError, OSError) as exc:
        fail("xclip murio al recibir el texto (%s: %s): revisa DISPLAY/sesion "
             "X11. Instalar: apt install xclip / dnf install xclip."
             % (type(exc).__name__, exc))
    finally:
        try:
            proc.stdin.close()  # EOF: xclip lee todo y demoniza
        except OSError:
            pass
    return proc


def _escribir_portapapeles(texto):
    """X11: pyperclip (usa xclip/xsel por debajo [runtime]) o xclip directo;
    pegar con ctrl+v de pyautogui.

    SEG3: helper de portapapeles (xclip) => baja con el nombre que tenia
    (regla portapapeles de la spec)."""
    pa = _pyautogui()
    try:
        import pyperclip

        pyperclip.copy(texto)
        via_clip = "pyperclip"
    except Exception:
        # xclip directo por Popen sin wait: run()+PIPE colgaria 10 s porque
        # xclip demoniza (ver _xclip_escribir, fix A2-W11).
        _xclip_escribir(texto)
        via_clip = "xclip -selection clipboard"
    time.sleep(0.05)  # asentar el portapapeles antes de pegar
    pa.hotkey("ctrl", "v")
    return via_clip


def _escribir_wtype(texto):
    """wtype emite el texto por la capa del compositor (unicode nativo).
    FLAGS [runtime] (el fetch del repo fallo en la investigacion): se pasa el
    texto posicional; si empieza con '-' se protege con '--'."""
    argv = ["--", texto] if texto.startswith("-") else [texto]
    r = c.run("wtype", argv, timeout=30.0)
    if r["rc"] != 0:
        c.fail("wtype fallo (rc=%d): %s. Verifica `wtype -h` (flags "
               "[runtime] en references/linux-python.md) o usa --via ydotool "
               "type." % (r["rc"], r["stderr"].strip()))


def _tecla_wtype(nombre):
    """wtype -k <keysym>: sintaxis [-k] NO verificada [runtime]; keysym por
    nombre XKB."""
    keysym = _KEYSYMS.get(nombre, nombre)
    r = c.run("wtype", ["-k", keysym], timeout=15.0)
    if r["rc"] != 0:
        c.fail("wtype -k %r fallo (rc=%d): %s (flags wtype = [runtime]; "
               "alternativa: ydotool key CODE:1 CODE:0 con la tabla de "
               "teclado.py)" % (nombre, r["rc"], r["stderr"].strip()))


def _ydotool_seq(tokens):
    """ydotool key <CODE:1/0 ...> (sintaxis man-verified en 1 lote)."""
    r = c.run("ydotool", ["key"] + tokens, timeout=30.0)
    if r["rc"] != 0:
        c.fail("ydotool key fallo (rc=%d): %s. Requiere el demonio ydotoold "
               "corriendo, YDOTOOL_SOCKET/permisos correctos y pertenecer al "
               "grupo input [runtime] (refs linux-python.md §4)."
               % (r["rc"], r["stderr"].strip()))


def _code_de(nombre):
    """Codigo ydotool para un nombre/alias, o None."""
    n = str(nombre).strip().lower()
    n = c.ALIAS_TECLAS_PYNPUT.get(n, n)
    return c.KEY_CODES.get(n)


_KEYSYMS = {
    "enter": "Enter", "intro": "Enter", "return": "Enter",
    "esc": "Escape", "escape": "Escape",
    "tab": "Tab", "espacio": "space", "space": "space",
    "backspace": "BackSpace", "supr": "Delete", "del": "Delete",
    "delete": "Delete", "home": "Home", "end": "End",
    "pageup": "Page_Up", "pgup": "Page_Up",
    "pagedown": "Page_Down", "pgdn": "Page_Down",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "ctrl": "Control_L", "shift": "Shift_L", "alt": "Alt_L",
    "win": "Super_L", "super": "Super_L", "meta": "Super_L",
    "printscreen": "Print", "prtsc": "Print",
}


def _emitir_combo_ydotool(cadena):
    """Combo Wayland por ydotool: mods down -> tecla down/up -> mods up en
    orden inverso, en una sola invocacion. SINTAXIS CODE:1/0 verificada
    (man); CODIGOS de la tabla KEY_CODES = [runtime] salvo 28/38/24/42."""
    partes = c.partes_combo(cadena, "ctrl+shift+esc")
    if len(partes) < 2:
        c.fail("Un combo necesita al menos un modificador y una tecla: "
               '"ctrl+s". Para una tecla suelta usa tecla.')
    mod_codes = []
    for p in partes[:-1]:
        n = c.ALIAS_TECLAS_PYNPUT.get(p, p)
        if n not in c._MODS_YDOTOOL:
            c.fail("Modificador no reconocido para ydotool: %r (validos: "
                   "ctrl, shift, alt, super y sus variantes _l/_r)." % p)
        mod_codes.append(c.KEY_CODES[n])
    final = _code_de(partes[-1])
    if final is None:
        c.fail("Tecla final no esta en la tabla KEY_CODES (ydotool): %r. "
               "La tabla cubre letras, numeros, funciones y navegacion; "
               "confirma codigos en /usr/include/linux/input-event-codes.h "
               "[runtime]." % partes[-1])
    tokens = ["%d:1" % m for m in mod_codes]
    tokens.append("%d:1" % final)
    tokens.append("%d:0" % final)
    tokens += ["%d:0" % m for m in reversed(mod_codes)]
    _ydotool_seq(tokens)


# --- de scripts/linux/raton.py ---------------------------------------------

# Codigos de click ydotool (man): 0x00 LEFT / 0x01 RIGHT / 0x02 MIDDLE mas
# mascara 0x40 down | 0x80 up. 0xC0 verbatim; 0xC1/0xC2/0x4x/0x8x derivados
# de la regla documentada [runtime].
_CLICK_YDOTOOL = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}
_DOWN_YDOTOOL = {"left": "0x40", "right": "0x41", "middle": "0x42"}
_UP_YDOTOOL = {"left": "0x80", "right": "0x81", "middle": "0x82"}

_AVISO_WAYLAND = ("WAYLAND: no existe el FAILSAFE de pyautogui en esta ruta "
                  "(uinput via ydotool): el freno humano es la bandera ABORT "
                  "del .tmp o Ctrl+C; tras un abort a medio arrastre el boton "
                  "puede quedar pulsado — sueltalo con click 0x8x")


def _ydotool(argv, timeout=30.0):
    r = c.run("ydotool", argv, timeout=timeout)
    if r["rc"] != 0:
        c.fail("ydotool %s fallo (rc=%d): %s. Requiere ydotoold corriendo, "
               "YDOTOOL_SOCKET/permisos y grupo input [runtime] (refs "
               "linux-python.md §4)." % (" ".join(argv), r["rc"],
                                          r["stderr"].strip()))


def _cursor():
    """(x, y) actual si es legible (X11), else None."""
    if c.deteccion_sesion() != "x11":
        return None
    r = c.run("xdotool", ["getmouselocation", "--shell"], timeout=10.0)
    if r["rc"] != 0:
        return None
    kv = c._shell_kv(r["stdout"])
    try:
        return int(kv["X"]), int(kv["Y"])
    except (KeyError, ValueError):
        return None


# --- de scripts/linux/ventanas.py -------------------------------------------

# xprop existe => se puede leer _NET_WM_STATE (MAXIMIZED_*) por ventana (P1-2);
# sin xprop, 'maximizada' sale null honesto (NUNCA inventar).
_HAY_XPROP = bool(shutil.which("xprop"))


def _rect_shell(kv):
    """Rect desde xdotool getwindowgeometry --shell (WIDTH/HEIGHT/X/Y)."""
    try:
        return {"left": int(kv.get("X", 0)), "top": int(kv.get("Y", 0)),
                "ancho": int(kv.get("WIDTH", 0)),
                "alto": int(kv.get("HEIGHT", 0))}
    except (TypeError, ValueError):
        return {"left": 0, "top": 0, "ancho": 0, "alto": 0}


def _item_canon(v, maximizada=None, rect=None):
    """Item de ventana CANONICO multi-rama (P1-2): titulo/app/id + rect y
    estado ANIDADOS (maximizada nullable: null cuando el WM/compositor no lo
    modela, nunca inventado)."""
    if rect is None:
        if v.get("left") is None and v.get("ancho") is None:
            rect = None
        else:
            rect = {"left": v.get("left"), "top": v.get("top"),
                    "ancho": v.get("ancho"), "alto": v.get("alto")}
    return {
        "titulo": v.get("titulo"),
        "app": v.get("app_id"),
        "id": v.get("id"),
        "rect": rect,
        "estado": {
            "minimizada": v.get("minimizada"),
            "maximizada": maximizada,
            "activa": bool(v.get("activa", False)),
        },
        "pid": v.get("pid"),
        "escritorio": v.get("escritorio"),
    }


def _maximizada_x11(vid):
    """True/False/None leyendo _NET_WM_STATE con xprop (EWMH; valores
    MAXIMIZED_VERT/HORZ documentados porwmctrl -b en su man). None si xprop
    ausente, falla o el estado es parcial no modelable [runtime]."""
    if not shutil.which("xprop"):
        return None
    r = c.run("xprop", ["-id", str(vid), "_NET_WM_STATE"], timeout=10.0)
    if r["rc"] != 0:
        return None
    est = (r["stdout"] or "").upper()
    vert = "MAXIMIZED_VERT" in est
    horz = "MAXIMIZED_HORZ" in est
    if vert and horz:
        return True
    if not vert and not horz:
        return False
    return None


def _nodo_json(texto):
    try:
        return json.loads(texto)
    except ValueError:
        return None


# ---------------------------------------------------------------- X11

def _listar_x11():
    """wmctrl -lpG → lista de dicts (columnas verificadas en man wmctrl:
    id-hex, desktop, [pid], [x, y, w, h], cliente, titulo)."""
    r = c.run_ok("wmctrl", ["-lpG"], timeout=15.0)
    # xdotool imprime ids DECIMALES y wmctrl hex: se comparan como enteros.
    visibles = None
    rv = c.run("xdotool", ["search", "--onlyvisible", "."], timeout=15.0)
    if rv["rc"] == 0:
        visibles = set()
        for tok in rv["stdout"].split():
            try:
                visibles.add(int(tok, 0))
            except ValueError:
                pass
    act = c.run("xdotool", ["getactivewindow"], timeout=10.0)
    try:
        activo = int(act["stdout"].strip(), 0) if act["rc"] == 0 else None
    except ValueError:
        activo = None
    out = []
    for linea in r["stdout"].splitlines():
        partes = linea.split(None, 8)
        if len(partes) < 9:
            continue
        vid, desk, pid, x, y, w, h, _host, titulo = partes
        try:
            vid_int = int(vid, 16)
        except ValueError:
            continue
        out.append({
            "id": vid,
            "escritorio": int(desk),
            "pid": int(pid),
            "left": int(x), "top": int(y),
            "ancho": int(w), "alto": int(h),
            "titulo": titulo,
            "activa": (vid_int == activo),
            # minimizada = gestionada por el WM pero no IsViewable (man
            # xdotool --onlyvisible); deducion [runtime] segun WM
            "minimizada": None if visibles is None else vid_int not in visibles,
            # maximizada: xprop _NET_WM_STATE (EWMH) cuando xprop existe y la
            # lista es acotada; null en otro caso (nunca inventar)
            "maximizada": _maximizada_x11(vid) if _HAY_XPROP and len(out) < 60
            else None,
        })
    return out


def _buscar_x11(titulo):
    """Ventana unica cuyo titulo contiene `titulo` (subcadena
    case-insensitive; preferencia por coincidencia exacta). Igual semantica
    que el padre Windows: si hay varias, exige el titulo exacto."""
    ventanas = _listar_x11()
    exactas = [v for v in ventanas if v["titulo"] == titulo]
    coincidencias = exactas or [v for v in ventanas
                                if titulo.lower() in v["titulo"].lower()]
    if not coincidencias:
        c.fail("Ninguna ventana contiene el titulo %r. Usa listar y pasa el "
               "titulo exacto." % titulo,
               coincidencias=0,
               ventanas_abiertas=[v["titulo"] for v in ventanas][:25])
    if len(coincidencias) > 1:
        c.fail("Varias ventanas coinciden con %r (%d): pide el titulo exacto "
               "y unico, o cierra las duplicadas."
               % (titulo, len(coincidencias)),
               coincidencias=[v["titulo"] for v in coincidencias])
    return coincidencias[0]


def _rect_x11(vid):
    """Rectangulo actual por xdotool getwindowgeometry --shell [formato
    empirico X=/Y=/WIDTH=/HEIGHT=: runtime]."""
    r = c.run("xdotool", ["getwindowgeometry", "--shell", vid], timeout=10.0)
    if r["rc"] != 0:
        return None
    return _rect_shell(c._shell_kv(r["stdout"]))


def _cmd_x11(vid, binario, argv, accion, aviso):
    """Ejecuta la accion y devuelve el JSON con estado post-accion."""
    c.run_ok(binario, argv, timeout=15.0)
    rect = _rect_x11(vid)
    act = c.run("xdotool", ["getactivewindow"], timeout=10.0)
    try:
        activa = act["rc"] == 0 and int(act["stdout"].strip(), 0) == int(vid, 16)
    except (ValueError, TypeError):
        activa = None
    rn = c.run("xdotool", ["getwindowname", vid], timeout=10.0)
    titulo = rn["stdout"].strip() if rn["rc"] == 0 else None
    item = _item_canon({"titulo": titulo, "id": vid, "activa": bool(activa),
                        "minimizada": None},
                       maximizada=_maximizada_x11(vid) if _HAY_XPROP else None,
                       rect=rect)
    out = {
        "ok": True,
        "accion": accion,
        "id": vid,
        "rect": rect,
        "ventana": item,
        "via": "%s %s" % (binario, " ".join(argv[:2])),
        "sesion": "x11",
        "marco": c.MARCO,
        "aviso": aviso,
    }
    if titulo is not None:
        out["titulo"] = titulo
    c.json_out(out)


# ------------------------------------------------------- Wayland (sway)

def _sway_nodos(arbol):
    """Generador de contenedores hoja del arbol sway."""
    pila = [arbol]
    while pila:
        n = pila.pop()
        if isinstance(n, dict):
            hijos = n.get("nodes") or []
            flotantes = n.get("floating_nodes") or []
            if not (hijos or flotantes) and ("pid" in n or "app_id" in n):
                yield n
            for h in list(hijos) + list(flotantes):
                pila.append(h)


def _listar_sway():
    r = c.run_ok("swaymsg", ["-t", "get_tree"], timeout=20.0)
    arbol = _nodo_json(r["stdout"])
    if arbol is None:
        c.fail("swaymsg -t get_tree no devolvio JSON valido.",
               salida=r["stdout"][:300])
    out = []
    for n in _sway_nodos(arbol):
        rect = n.get("rect") or {}
        out.append({
            "id": n.get("id"),
            "con_id": n.get("id"),
            "escritorio": (n.get("workspace") or {}).get("num")
            if isinstance(n.get("workspace"), dict) else None,
            "pid": n.get("pid"),
            "left": rect.get("x"), "top": rect.get("y"),
            "ancho": rect.get("width"), "alto": rect.get("height"),
            "titulo": n.get("name"),
            "app_id": n.get("app_id"),
            "activa": bool(n.get("focused")),
            "minimizada": None,   # sway no lo modela: scratchpad ~ minimizado
            "floating": bool(n.get("floating")),
        })
    return out


def _sway_foco():
    for n in _listar_sway():
        if n["activa"]:
            return n
    return None


def _accion_sway(titulo, comando_sway, aviso, titulo_arg=None, con_id=None):
    """Aplica un comando sway al contenedor (por titulo o por con_id IMPL-K
    P0.1) o global (sin selector). Selectores [con_id=] segun sway(5)
    [runtime]."""
    c.require("swaymsg")
    objetivo = None
    if con_id is not None:
        try:
            want = int(str(con_id), 0)
        except (TypeError, ValueError):
            c.fail("--id debe ser el con_id entero del arbol sway (recibido %r)."
                   % con_id)
        coincidencias = [n for n in _listar_sway() if n.get("con_id") == want]
        if not coincidencias:
            c.fail("Ningun contenedor sway tiene el id %r. Usa listar." % con_id,
                   coincidencias=0,
                   ventanas_abiertas=["%s: %s" % (n["id"], n["titulo"])
                                      for n in _listar_sway()][:25])
        objetivo = coincidencias[0]
    if objetivo is None and titulo:
        coincidencias = [n for n in _listar_sway()
                         if n["titulo"] and titulo.lower() in str(n["titulo"]).lower()]
        exactas = [n for n in coincidencias if n["titulo"] == titulo]
        coincidencias = exactas or coincidencias
        if not coincidencias:
            c.fail("Ninguna ventana del arbol sway contiene el titulo %r. "
                   "Usa listar." % titulo, coincidencias=0,
                   ventanas_abiertas=[n["titulo"] for n in _listar_sway()][:25])
        if len(coincidencias) > 1:
            c.fail("Varias ventanas coinciden con %r (%d): usa el titulo "
                   "exacto." % (titulo, len(coincidencias)),
                   coincidencias=[n["titulo"] for n in coincidencias])
        objetivo = coincidencias[0]
    if objetivo is None and titulo_arg:
        coincidencias = [n for n in _listar_sway()
                         if n["titulo"] and titulo_arg.lower()
                         in str(n["titulo"]).lower()]
        if coincidencias:
            objetivo = coincidencias[0]
    if objetivo is not None:
        mensaje = "[con_id=%s] %s" % (objetivo["con_id"], comando_sway)
    else:
        mensaje = comando_sway
    r = c.run_ok("swaymsg", [mensaje], timeout=15.0)
    item_canon = None
    if objetivo is not None:
        item_canon = _item_canon(objetivo, maximizada=None)
    c.json_out({
        "ok": True,
        "accion": comando_sway,
        "id": None if objetivo is None else objetivo["con_id"],
        "titulo": None if objetivo is None else objetivo["titulo"],
        "rect": None if objetivo is None else
              {"left": objetivo["left"], "top": objetivo["top"],
               "ancho": objetivo["ancho"], "alto": objetivo["alto"]},
        "ventana": item_canon,
        "via": "swaymsg \"%s\" (IPC comando sway)" % mensaje,
        "sesion": "wayland",
        "marco": c.MARCO,
        "aviso": aviso + " [runtime] sintaxis de selector segun sway(5)",
        "respuesta": r["stdout"].strip() or None,
    })


def _hypr_listar():
    r = c.run_ok("hyprctl", ["clients", "-j"], timeout=20.0)
    datos = _nodo_json(r["stdout"])
    if datos is None:
        c.fail("hyprctl clients -j no devolvio JSON valido [runtime].",
               salida=r["stdout"][:300])
    out = []
    for cl in datos:
        geom = cl.get("geometry") or {}
        out.append({
            "id": cl.get("address"),
            "pid": cl.get("pid"),
            "left": geom.get("x"), "top": geom.get("y"),
            "ancho": geom.get("width"), "alto": geom.get("height"),
            "titulo": " ".join([x for x in (cl.get("class"), cl.get("title"))
                                if x]),
            "activa": bool(cl.get("focused", False)),
            "minimizada": None,
        })
    return out


def _wayland_listar():
    if shutil.which("swaymsg"):
        return _listar_sway(), "swaymsg -t get_tree"
    if shutil.which("hyprctl"):
        return _hypr_listar(), "hyprctl clients -j [runtime]"
    c.fail("Wayland detectado sin swaymsg (sway/i3-compatible) ni hyprctl "
           "(Hyprland): esta skill no tiene API documentada para ventanas en "
           "tu compositor (kdotool para KDE existe [runtime] pero no fue "
           "auditado aqui). Usa los atajos de teclado del compositor o "
           "reporta cual es (refs linux-python.md §8).",
           sesion="wayland")


def _wayland_foco():
    if shutil.which("swaymsg"):
        return _sway_foco(), "swaymsg -t get_tree (nodo focused)"
    if shutil.which("hyprctl"):
        r = c.run("hyprctl", ["activewindow", "-j"], timeout=20.0)
        if r["rc"] != 0:
            return None, "hyprctl activewindow -j [runtime]"
        d = _nodo_json(r["stdout"])
        if not d:
            return None, "hyprctl activewindow -j [runtime]"
        geom = d.get("geometry") or {}
        return {"id": d.get("address"), "pid": d.get("pid"),
                "left": geom.get("x"), "top": geom.get("y"),
                "ancho": geom.get("width"), "alto": geom.get("height"),
                "titulo": " ".join([x for x in (d.get("class"), d.get("title"))
                                    if x]),
                "activa": True, "minimizada": None}, \
            "hyprctl activewindow -j [runtime]"
    return None, None


# ---------------------------------------------------------------- común

def _ids_conocidas():
    """Snapshot de ids visibles para exigir ventana NUEVA (patron del padre)."""
    try:
        sesion = c.deteccion_sesion()
        if sesion == "x11":
            return {str(v["id"]) for v in _listar_x11()}
        if sesion == "wayland" and shutil.which("swaymsg"):
            return {str(v["id"]) for v in _listar_sway()}
        if sesion == "wayland" and shutil.which("hyprctl"):
            return {str(v["id"]) for v in _hypr_listar()}
    except SystemExit:
        pass
    except Exception:
        pass
    return set()


def _nuevas_por_diff(previos):
    """Lista CRUDA de ventanas cuyo id no estaba en `previos` (IMPL-K P1.2-b:
    el diff de hWnds que reescribieron 7 drivers — ignora la pista y funciona
    con titulos localizados)."""
    try:
        sesion = c.deteccion_sesion()
        if sesion == "x11":
            actuales = _listar_x11()
        elif sesion == "wayland" and shutil.which("swaymsg"):
            actuales = _listar_sway()
        elif sesion == "wayland" and shutil.which("hyprctl"):
            actuales = _hypr_listar()
        else:
            return []
        return [v for v in actuales if str(v["id"]) not in previos]
    except Exception:
        return None  # fallo puntual de lectura: seguir sondeando


def _mover_x11(vid, x, y):
    """xdotool windowmove <id> <x> <y> (coords de LAYOUT; man verbatim
    'windowmove x y ... moves the window'; [runtime] WM sin reparenting).
    Emite el JSON canonico de accion via _cmd_x11."""
    c._cmd_x11(vid, "xdotool",
               ["windowmove", "--sync", vid, str(int(x)), str(int(y))],
               "mover",
               "windowmove mueve el VERTICE SUP-IZQ a las coords de layout "
               "pedidas; algunos WMs ignoran la posicion de ventanas "
               "maximizadas [runtime]: re-verifica con listar")


def _mover_sway_output(con_id, output_nombre):
    """sway: 'move container to output <nombre>' (man sway-input/commands
    [runtime] para el selector): en tiling 'mover de monitor' = mover el
    contenedor al output, el layout decide la geometria."""
    c._accion_sway(None, "move container to output %s" % output_nombre,
                   "en tiling la posicion final la decide el layout del "
                   "workspace destino", con_id=con_id)


def _nueva_ventana(pista, previos):
    """(dict|None) con ventana nueva cuyo titulo contiene pista."""
    try:
        sesion = c.deteccion_sesion()
        if sesion == "x11":
            nuevas = [v for v in _listar_x11()
                      if str(v["id"]) not in previos
                      and pista.lower() in v["titulo"].lower()]
        elif sesion == "wayland" and shutil.which("swaymsg"):
            nuevas = [v for v in _listar_sway()
                      if str(v["id"]) not in previos
                      and v["titulo"] and pista.lower()
                      in str(v["titulo"]).lower()]
        elif sesion == "wayland" and shutil.which("hyprctl"):
            nuevas = [v for v in _hypr_listar()
                      if str(v["id"]) not in previos
                      and pista.lower() in v["titulo"].lower()]
        else:
            nuevas = []
    except Exception:
        return None  # fallo puntual de lectura: seguir sondeando
    return nuevas[0] if nuevas else None


# ===========================================================================
# CLI PROPIO SOLO-LINUX (FASE SEG3; modelo: scripts/windows/win_especiales.py)
# Verbos de estado del dominio y primitivas puntuales sin verbo generico.
# ===========================================================================

# Tabla honesta de la ruta WAYLAND de los CLIs genericos de la raiz. (None) =
# SIN RUTA documentada: el CLI generic responde error honesto, no es un bug.
_VERBOS_WAYLAND = {
    "pantalla capturar": ("grim", "grim -o / grim -g (layout coordinates)"),
    "pantalla tamano": ("swaymsg", "swaymsg -t get_outputs o hyprctl "
                                   "monitors -j [runtime]"),
    "pantalla pixel": ("grim", "grim 1x1 + PIL"),
    "pantalla posicion": (None, "SIN RUTA: sin lectura documentada del cursor "
                                "en Wayland (usa capturar + vision)"),
    "pantalla esperar": ("grim", "poll ~100 ms con mini-captura 1 px por grim"),
    "pantalla localizar": (None, "SIN RUTA: pyautogui no ve el compositor "
                                 "nativo (XWayland only); usa capturar + vision"),
    "teclado escribir": ("wtype", "wtype (unicode nativo; --via ydotool type "
                                  "como respaldo)"),
    "teclado tecla": ("wtype", "wtype -k [runtime]; con --mods cae a ydotool"),
    "teclado combo": ("ydotool", "ydotool key CODE:1/CODE:0 (sintaxis "
                                 "man-verified; codigos [runtime])"),
    "teclado mantener": ("ydotool", "ydotool key CODE:1 ... CODE:0"),
    "raton mover": ("ydotool", "ydotool mousemove --absolute"),
    "raton click": ("ydotool", "ydotool click 0xCx (down|up)"),
    "raton arrastrar": ("ydotool", "down 0x4x -> move --absolute -> up 0x8x "
                                   "(freno: bandera ABORT, no hay FAILSAFE)"),
    "raton scroll": (None, "SIN RUTA: ydotool no implementa el eje de rueda "
                           "(workaround: tecla pageup/pagedown [runtime])"),
    "ventanas listar": ("swaymsg", "swaymsg -t get_tree (o hyprctl clients -j "
                                   "[runtime])"),
    "ventanas foco": ("swaymsg", "swaymsg get_tree nodo focused (o hyprctl "
                                 "activewindow -j)"),
    "ventanas activar/minimizar/maximizar/cerrar": ("swaymsg",
                                                    "comandos por IPC sway "
                                                    "[runtime]; Hyprland: SIN "
                                                    "RUTA (exige dispatches "
                                                    "propios)"),
    "ventanas restaurar": ("swaymsg", "sway: scratchpad show [runtime]"),
    "ventanas abrir": ("xdg-open", "Popen start_new_session (programa) / "
                                   "xdg-open (URL/archivo)"),
    "monitores cursor": (None, "SIN RUTA: sin lectura documentada del cursor "
                               "en Wayland"),
    "vigilar arrancar": (None, "SIN RUTA: pynput no tiene listener global sin "
                               "X11 (freno: .tmp/ABORT o Ctrl+C)"),
}


def cmd_sesion(args):
    """Sesion grafica + herramientas del SO disponibles/ausentes."""
    sesion = deteccion_sesion()
    rutas = herramientas()
    json_out({
        "ok": True,
        "sesion": sesion,
        "marco": MARCO,
        "herramientas": rutas,
        "disponibles": sorted(n for n, r in rutas.items() if r),
        "ausentes": sorted(n for n, r in rutas.items() if not r),
        "via": "os.environ (XDG_SESSION_TYPE/WAYLAND_DISPLAY/DISPLAY) + "
               "shutil.which(HERRAMIENTAS)",
        "nota": "hint de instalacion apt/dnf por herramienta en "
                "HINTS_PAQUETES de este modulo (references/linux-python.md "
                "§INCERTO para los nombres [runtime]).",
    })


def cmd_xrandr(args):
    """Lista CRUDA de monitores del mapa de la rama (sin recortar campos)."""
    mons = monitores()
    v = tamano_virtual()
    json_out({
        "ok": True,
        "sesion": deteccion_sesion(),
        "marco": MARCO,
        "monitores": mons,
        "virtual": {"x": v["x"], "y": v["y"], "ancho": v["ancho"],
                    "alto": v["alto"], "origen": [v["x"], v["y"]]},
        "nota": "campos por monitor: indice/nombre/izq/top/ancho/alto/der/bot/"
                "primario/activo/output/via. Fuente: xrandr --listmonitors "
                "(X11) o swaymsg -t get_outputs / hyprctl monitors -j "
                "(Wayland). El CLI generico es monitores.py listar.",
    })


def cmd_grim(args):
    """Captura Wayland del LAYOUT completo con grim hacia --archivo."""
    sesion = deteccion_sesion()
    if sesion != "wayland":
        fail("grim es EXCLUSIVO de Wayland: la sesion detectada es %r. Para "
             "capturar en X11 usa pantalla.py capturar (pyautogui/scrot); en "
             "sesion incognito exporta WAYLAND_DISPLAY+XDG_RUNTIME_DIR (refs "
             "linux-python.md §13)." % sesion, sesion=sesion)
    ruta = ruta_destino_captura(args.archivo)
    r = run("grim", [ruta], timeout=20.0)
    if r["rc"] != 0:
        fail("grim fallo (rc=%d): %s. Verifica WAYLAND_DISPLAY + "
             "XDG_RUNTIME_DIR e instala: apt install grim / dnf install grim "
             "(refs linux-python.md §8)."
             % (r["rc"], r["stderr"].strip()))
    ancho = alto = None
    try:
        im = _grim_abrir(ruta)
        ancho, alto = int(im.width), int(im.height)
    except Exception:
        pass  # Pillow ausente: el PNG quedo escrito en `ruta` (null honesto)
    factor = _grim_factor()
    json_out({
        "ok": True,
        "archivo": ruta,
        "ancho": ancho,
        "alto": alto,
        "factor_grim": factor,
        "marco": MARCO,
        "sesion": sesion,
        "via": "grim <archivo> (layout completo; man verbatim: coords de "
               "layout)",
        "nota": "captura del LAYOUT completo; 'ancho'/'alto' null si Pillow no "
                "esta instalado (el PNG si se escribio); 'factor_grim' = max "
                "scale de outputs sway (null si la fuente no informa "
                "[runtime]). Para recortes por monitor/region usa el CLI "
                "generico pantalla.py capturar --monitor/--region.",
    })


def cmd_portapapeles_leer(args):
    """Texto del clipboard: pyperclip primero, xclip -o de respaldo (la misma
    piramide de herramientas que _escribir_portapapeles de la rama)."""
    try:
        import pyperclip

        texto = pyperclip.paste()
        via = "pyperclip"
    except Exception:
        r = run("xclip", ["-selection", "clipboard", "-o"], timeout=10.0)
        if r["rc"] != 0:
            fail("Ni pyperclip ni xclip pudieron leer el portapapeles "
                 "(xclip: %s). Instalar: apt install xclip / python3 -m pip "
                 "install pyperclip." % r["stderr"].strip())
        texto = r["stdout"]
        via = "xclip -selection clipboard -o"
    json_out({
        "ok": True,
        "texto": texto,
        "largo": len(texto),
        "via": via,
        "seleccion": "clipboard",
        "nota": "lee la seleccion CLIPBOARD (no PRIMARY); texto vacio = "
                "clipboard vacio o sin formato texto. pyperclip usa "
                "xclip/xsel por debajo [runtime].",
    })


def cmd_portapapeles_escribir(args):
    """Escribe el clipboard SIN pegar (pegar es tarea de teclado.py --via
    portapapeles o combo ctrl+v): pyperclip primero, xclip directo de
    respaldo, como hace la rama hoy."""
    try:
        import pyperclip

        pyperclip.copy(args.texto)
        via = "pyperclip"
    except Exception:
        # Popen sin wait: xclip demoniza y run()+PIPE colgaria 10 s hasta el
        # timeout (ver _xclip_escribir, fix A2-W11).
        _xclip_escribir(args.texto)
        via = "xclip -selection clipboard"
    json_out({
        "ok": True,
        "escrito_chars": len(args.texto),
        "via": via,
        "seleccion": "clipboard",
        "nota": "escribe SIN pegar: para copiar+pegar en la ventana enfocada "
                "usa teclado.py escribir --via portapapeles; para pegar "
                "contenido ya escrito: teclado.py combo \"ctrl+v\" (exige "
                "foco correcto, verifica con pantalla.py capturar).",
    })


def cmd_wayland_status(args):
    """Sesion + tools + que verbos genericos estan RESUELTOS en la ruta
    Wayland (estado honesto del dominio)."""
    sesion = deteccion_sesion()
    rutas = herramientas()
    compositor = None
    if rutas.get("swaymsg"):
        compositor = "sway/i3-compatible (swaymsg -t get_tree/get_outputs)"
    elif rutas.get("hyprctl"):
        compositor = "Hyprland (hyprctl -j) [runtime]"
    verbos = {}
    for nombre, (herr, desc) in _VERBOS_WAYLAND.items():
        if herr is None:
            verbos[nombre] = desc
        elif rutas.get(herr):
            verbos[nombre] = "RESUELTO via %s: %s" % (herr, desc)
        else:
            verbos[nombre] = "BLOQUEADO (falta %s): %s" % (herr, desc)
    json_out({
        "ok": True,
        "sesion": sesion,
        "compositor": compositor,
        "marco": MARCO,
        "herramientas": rutas,
        "verbos": verbos,
        "via": "deteccion_sesion + shutil.which(HERRAMIENTAS) + tabla "
               "_VERBOS_WAYLAND",
        "nota": "la tabla describe la ruta WAYLAND de los CLIs genericos de la "
                "raiz scripts/<verbo>.py; si 'sesion' es 'x11' todos esos "
                "verbos tienen ruta pyautogui/pynput/xdotool/wmctrl y esta "
                "tabla solo sirve de referencia. 'SIN RUTA' = error honesto "
                "del CLI generic (documentado en references/"
                "linux-python.md), no un bug.",
    })


def construir_parser():
    parser = Parser(
        prog="linux_especiales.py",
        description="CLI SOLO-LINUX del dominio exclusivo (libreria de "
                    "primitivas importable en cualquier SO): sesion, xrandr, "
                    "grim, portapapeles leer/escribir (xclip) y wayland-"
                    "status. JSON canonico de la skill.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1] if __doc__ and "Subcomandos:" in __doc__ else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    sub.add_parser("sesion", help="sesion grafica + herramientas del SO") \
       .set_defaults(func=cmd_sesion)

    sub.add_parser("xrandr", help="lista cruda de monitores (xrandr/sway/"
                   "hypr)") .set_defaults(func=cmd_xrandr)

    p = sub.add_parser("grim", help="captura Wayland del layout completo")
    p.add_argument("--archivo", help="nombre o ruta destino del PNG: un "
                   "nombre pelado cae en .tmp/capturas de ESTA skill; con "
                   "directorio se respeta. Por defecto "
                   ".tmp/capturas/captura_<fecha_hora>.png")
    p.set_defaults(func=cmd_grim)

    p = sub.add_parser("portapapeles", help="leer/escribir el clipboard (xclip)")
    sp = p.add_subparsers(dest="accion", required=True, metavar="ACCION")
    a = sp.add_parser("leer", help="imprimir el texto del clipboard")
    a.set_defaults(func=cmd_portapapeles_leer)
    a = sp.add_parser("escribir", help="copiar TEXTO al clipboard (sin pegar)")
    a.add_argument("texto", help="contenido literal (usa comillas)")
    a.set_defaults(func=cmd_portapapeles_escribir)

    sub.add_parser("wayland-status", help="sesion + tools + verbos genericos "
                   "resueltos en Wayland") .set_defaults(func=cmd_wayland_status)

    return parser


def _guard_cli():
    """Guard de plataforma del CLI (FASE SEG3): ANTES de parsear.

    Hereda el estilo del guard viejo de nivel-import de _compartido_linux.py
    (SEG2), movido aqui porque en SEG3 el archivo es LIBRERIA importable en
    cualquier SO (los CLIs raiz bind c = este modulo en tiempo de ejecucion).
    Ejecutado como script fuera de Linux: JSON con "error" + rc 2, sin
    traceback."""
    if sys.platform != "linux":
        print(json.dumps({
            "error": "linux_especiales.py como CLI es el dominio EXCLUSIVO de "
                     "LINUX; la LIBRERIA si es importable en cualquier SO. El "
                     "punto de entrada normal es scripts/<verbo>.py (raiz, "
                     "multi-OS: ejecuta en el propio proceso la ruta de tu "
                     "SO). Autotest: python autotest.py en tu SO",
            "sistema_operativo": sys.platform,
            # contrato P0-4: `plataforma` canonica tambien en el guard
            "plataforma": {"win32": "win", "linux": "linux",
                           "darwin": "darwin"}.get(sys.platform, sys.platform),
        }, ensure_ascii=False))
        sys.exit(2)


def main():
    _guard_cli()  # rc 2 con JSON fuera de Linux, antes de parsear (--help inclusive)
    args = construir_parser().parse_args()
    try:
        args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        fail("%s: %s" % (type(exc).__name__, exc))


if __name__ == "__main__":
    main()
