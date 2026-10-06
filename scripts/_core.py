# -*- coding: utf-8 -*-
"""_core.py — helpers stdlib-puro compartidos por las 3 ramas de computer-use-py.

NACIO del SPEC de integracion (P2-1): los 5 helpers triviales eran copias
100 % identicas en _compartido.py / _compartido_linux.py / _compartido_mac.py.
Este modulo NO importa pyautogui, ctypes.windll, Quartz ni X11: es SEGURO de
importar en cualquier SO (por eso puede vivir en scripts/ y reexportarse desde
las ramas linux/ y macos/ con un sys.path.insert del padre).

Regla dura: nada aqui puede tocar API del SO ni hacer guard de plataforma;
los guards (y el DPI) se quedan en el _compartido* de cada rama, que IMPORTA
este modulo y reexporta estas funciones/constantes para que los scripts
sigan llamando `c.json_out(...)`, `c.fail(...)`, etc. sin cambios.

Uso desde una rama:

    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import _core as _c
    json_out, fail, tocar, borrar, asegurar_capturas = (_c.json_out, _c.fail,
        _c.tocar, _c.borrar, _c.asegurar_capturas)
    DIR_TMP, DIR_CAPTURAS = _c.DIR_TMP, _c.DIR_CAPTURAS
    ARCHIVO_ABORT, ARCHIVO_PAUSA = _c.ARCHIVO_ABORT, _c.ARCHIVO_PAUSA
"""

import json
import os
import sys

# scripts/ es el padre fisico de este archivo; su padre es la raiz de la
# skill. Da el mismo resultado importado desde scripts/, scripts/linux/ o
# scripts/macos/ porque la ruta se resuelve contra __file__, no contra CWD.
RAIZ_SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_TMP = os.path.join(RAIZ_SKILL, ".tmp")
DIR_CAPTURAS = os.path.join(DIR_TMP, "capturas")
ARCHIVO_ABORT = os.path.join(DIR_TMP, "ABORT")
ARCHIVO_PAUSA = os.path.join(DIR_TMP, "PAUSA")

# Nombre canonico multi-rama de la plataforma (P0-4 del spec): win|linux|darwin.
_PLAT_MAP = {"win32": "win", "linux": "linux", "darwin": "darwin"}


def plataforma():
    """'win' | 'linux' | 'darwin' (crudos sys.platform caen como vienen)."""
    return _PLAT_MAP.get(sys.platform, sys.platform)


def _con_plataforma(datos):
    """Inyecta 'plataforma' en todo JSON de exito que no la traiga (P0-4:
    el campo debe estar SIEMPRE; json_out es la unica via de salida)."""
    if isinstance(datos, dict) and "plataforma" not in datos:
        datos["plataforma"] = plataforma()
    return datos


def json_out(datos):
    """Unica via de salida de los scripts: JSON legible por stdout."""
    print(json.dumps(_con_plataforma(datos), ensure_ascii=False, indent=2))


def fail(mensaje, **extra):
    """Error canonico de la skill: JSON con 'error' (+plataforma) y exit 1."""
    datos = _con_plataforma({"error": mensaje, **extra})
    print(json.dumps(datos, ensure_ascii=False, indent=2))
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
