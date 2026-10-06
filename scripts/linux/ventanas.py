# -*- coding: utf-8 -*-
"""ventanas.py — Ventanas del dominio LINUX (skill computer-use-py).

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

Subcomandos:
  listar      Todas las ventanas: id, titulo, rectangulo, pid, activa.
  foco        Ventana foreground activa (quien recibe el teclado).
  activar     Traer y enfocar la ventana (wmctrl -a / sway focus).
  minimizar   Minimizar (xdotool windowminimize / sway move scratchpad).
  restaurar   Volver del minimizado (windowmap+activate / scratchpad show).
  maximizar   Maximizar (wmctrl -b add,maximized_vert,maximized_horz /
              sway fullscreen enable).
  cerrar      Cerrar (wmctrl -c gracefully / sway kill).
  abrir       Lanza app/URL/archivo (Popen start_new_session o xdg-open;
              log del hijo en .tmp) y opcional --esperar por xdotool search
              --name (X11) o arbol sway.

Ejemplos (desde la carpeta computer-use-py, en la maquina Linux):
  python3 scripts/linux/ventanas.py listar
  python3 scripts/linux/ventanas.py foco
  python3 scripts/linux/ventanas.py activar "Firefox"
  python3 scripts/linux/ventanas.py cerrar "Confirmacion"
  python3 scripts/linux/ventanas.py abrir firefox --esperar 8 --titulo "Firefox"
  python3 scripts/linux/ventanas.py abrir "https://example.com"
  python3 scripts/linux/ventanas.py abrir "/datos/informe.ods"
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import time

import _compartido_linux as c

# Esquema de URL: >=2 letras/digitos y +-. antes de ':' (descarta "/ruta" y
# "C:\ruta") o prefijo "www." — misma regla del dominio Windows.
_ESQUEMA_URL = c.ESQUEMA_URL  # clasificador URL generico (vive en _core)

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


def cmd_activar(args):
    c.checar_abort("activar")
    c.checar_pausa()
    if c.deteccion_sesion() == "wayland":
        _accion_sway(args.titulo, "focus",
                     "el foco decide quien recibe el teclado: verifica con "
                     "pantalla.py capturar")
        return
    v = _buscar_x11(args.titulo)
    _cmd_x11(v["id"], "wmctrl", ["-i", "-a", v["id"]], "activar",
             "focus-stealing prevention (GNOME) puede SOLO resaltar la "
             "ventana: re-verifica con ventanas.py foco + capturar (refs "
             "linux-python.md §13)")


def cmd_minimizar(args):
    c.checar_abort("minimizar")
    c.checar_pausa()
    if c.deteccion_sesion() == "wayland":
        _accion_sway(args.titulo, "move scratchpad",
                     "en sway 'minimizar' = mandar al scratchpad: vuelve con "
                     "restaurar (scratchpad show) [runtime]")
        return
    v = _buscar_x11(args.titulo)
    _cmd_x11(v["id"], "xdotool", ["windowminimize", v["id"]], "minimizar",
             "comportamiento del iconify segun WM sin garantias: verificar "
             "en runtime")


def cmd_restaurar(args):
    c.checar_abort("restaurar")
    c.checar_pausa()
    if c.deteccion_sesion() == "wayland":
        _accion_sway(None, "scratchpad show",
                     "muestra el ultimo contenedor del scratchpad [runtime]; "
                     "si hay varios, sway decide cual", titulo=args.titulo)
        return
    v = _buscar_x11(args.titulo)
    # windowmap puede fallar si la ventana ya esta mapeada: se tolera y se
    # activa igual ([runtime]: windowmap + windowactivate es el patron del
    # man para "hacer visible" y enfocar).
    c.run("xdotool", ["windowmap", v["id"]], timeout=15.0)
    _cmd_x11(v["id"], "xdotool", ["windowactivate", "--sync", v["id"]],
             "restaurar",
             "tras restaurar, re-verifica el foco con capturar: algunos WMs "
             "remapean sin activar [runtime]")


def cmd_maximizar(args):
    c.checar_abort("maximizar")
    c.checar_pausa()
    if c.deteccion_sesion() == "wayland":
        _accion_sway(args.titulo, "fullscreen enable",
                     "'maximizar' en tiling = fullscreen del contenedor "
                     "[runtime]; la alternativa es mover a un workspace vacio")
        return
    v = _buscar_x11(args.titulo)
    # -b con dos propiedades: verbatim del man ("Two properties are supported
    # to allow operations like maximizing a window to full screen mode")
    _cmd_x11(v["id"], "wmctrl",
             ["-i", "-r", v["id"], "-b", "add,maximized_vert,maximized_horz"],
             "maximizar",
             "toggle por xdotool windowstate --toggle MAXIMIZED_VERT/HORZ NO "
             "esta en la manpage de Debian: si necesitas DEsmaximizar usa "
             "wmctrl -b remove,... (mismos estados verificados)")


def cmd_cerrar(args):
    c.checar_abort("cerrar")
    c.checar_pausa()
    if c.deteccion_sesion() == "wayland":
        _accion_sway(args.titulo, "kill",
                     "muchas apps abren modal al cerrar: verifica SIEMPRE "
                     "con pantalla.py capturar")
        return
    v = _buscar_x11(args.titulo)
    _cmd_x11(v["id"], "wmctrl", ["-i", "-c", v["id"]], "cerrar",
             "muchas apps abren modal al cerrar (guardar cambios?): verifica "
             "SIEMPRE con pantalla.py capturar")


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


def _accion_sway(titulo, comando_sway, aviso, titulo_arg=None):
    """Aplica un comando sway al contenedor (por titulo) o global (sin
    selector). Selectores [con_id=] segun sway(5) [runtime]."""
    c.require("swaymsg")
    objetivo = None
    if titulo:
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

def cmd_listar(args):
    sesion = c.deteccion_sesion()
    if sesion == "x11":
        crudas, via = _listar_x11(), "wmctrl -lpG + xdotool getactivewindow"
        nota = ("rectangulos del screen X11 (coordenadas de LAYOUT: el mismo "
                "marco de pantalla.py/raton.py); item canonico rect+estado "
                "(P1-2); 'minimizada' deducida por xdotool search "
                "--onlyvisible [runtime]; 'maximizada' via xprop "
                "_NET_WM_STATE" + ("" if _HAY_XPROP else " (xprop AUSENTE: "
                "siempre null)") + "; ventana minimizada puede reportar rect "
                "sin geometria utilizable [runtime]")
    elif sesion == "wayland":
        crudas, via = _wayland_listar()
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
        item = _item_canon(v, maximizada=v.get("maximizada"))
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


def cmd_foco(args):
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
        vid = c.run_ok("xdotool", ["getactivewindow"], timeout=10.0).stdout.strip()
        rect = _rect_x11(vid)
        pid = None
        rp = c.run("xdotool", ["getwindowpid", vid], timeout=10.0)
        if rp["rc"] == 0:
            try:
                pid = int(rp["stdout"].strip())
            except ValueError:
                pid = None
        item = _item_canon({"titulo": r["stdout"].strip(), "id": vid,
                            "pid": pid, "activa": True, "minimizada": False},
                           maximizada=_maximizada_x11(vid) if _HAY_XPROP else None,
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
                     "_NET_WM_STATE" + ("" if _HAY_XPROP else
                                        " (xprop ausente: null)") +
                     "; verifica con capturar despues de teclear (una "
                     "notificacion puede robar el foco entre la lectura y la "
                     "emision)"),
        })
        return
    if sesion == "wayland":
        n, via = _wayland_foco()
        if via is None:
            _wayland_listar()  # falla con el error honesto de compositor
        if n is None:
            c.json_out({"activa": None, "ventana": None, "sesion": sesion,
                        "marco": c.MARCO, "via": via,
                        "nota": "el compositor no reporto ventana enfocada: "
                                "NO teclees aun; re-verifica con capturar"})
            return
        item = _item_canon(n, maximizada=None)
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


def _clasificar(objetivo):
    """(tipo, resuelto): 'url' | 'programa' | 'archivo' | (None, None).
    Mismo orden que el padre Windows: esquema/www. => URL; shutil.which =>
    programa; ruta existente => archivo."""
    if _ESQUEMA_URL.match(objetivo):
        return "url", objetivo
    resuelto = shutil.which(objetivo)
    if resuelto:
        return "programa", resuelto
    if os.path.exists(objetivo):
        return "archivo", os.path.abspath(objetivo)
    return None, None


def _pista_por_defecto(objetivo, tipo):
    if tipo == "url":
        resto = re.sub(r"^[A-Za-z][A-Za-z0-9+.\-]{1,}:/*", "", objetivo)
        return re.split(r"[/?#]", resto, maxsplit=1)[0] or objetivo
    base = os.path.basename(os.path.normpath(objetivo))
    return os.path.splitext(base)[0] if tipo == "programa" else base


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


def cmd_abrir(args):
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
    tipo, resuelto = _clasificar(args.objetivo)
    if tipo is None:
        c.fail("%r no es URL (esquema 'algo:' o 'www.'), ni programa "
               "resolvable por PATH, ni archivo existente. Revisa la "
               "ortografia o pasa la ruta absoluta." % args.objetivo)

    usar_popen = tipo == "programa"
    mecanica = ("Popen(shell=False, start_new_session=True)" if usar_popen
                else "xdg-open (asociaciones del escritorio)")
    pista = (args.titulo or "").strip() or _pista_por_defecto(args.objetivo, tipo)
    previos = _ids_conocidas() if args.esperar > 0 else set()

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
    c.checar_abort("espera de ventana")  # P1-6: el freno dura también aquí
    c.checar_pausa()                     # P1-5: con PAUSA la espera se posterga
    limite = time.time() + args.esperar
    while time.time() < limite:
        ventana = _nueva_ventana(pista, previos)
        if ventana is not None:
            break
        c.checar_abort("espera de ventana")
        time.sleep(0.25)

    if ventana is not None:
        resultado["ventana"] = _item_canon(ventana,
                                           maximizada=ventana.get("maximizada"))
        resultado["nota"] = ("ventana NUEVA con pista %r; rect en coords de "
                             "LAYOUT; item canonico rect+estado (maximizada "
                             "null en wayland/tiling); re-verifica el foco con "
                             "capturar" % pista)
    else:
        resultado["ventana"] = None
        nota = ("timeout de %d s sin ventana NUEVA con pista %r (NO es "
                "error): la app pudo abrir sin ventana, tardar mas, o "
                "REUTILIZAR su ventana (navegador con sesion). Verifica con "
                "listar o capturar." % (args.esperar, pista))
        if proc is not None and proc.poll() is not None:
            resultado["proceso_termino"] = proc.returncode
            nota += " El proceso lanzado ya termino (rc=%s)." % proc.returncode
        if not shutil.which("wmctrl") and c.deteccion_sesion() == "x11":
            nota += " (sin wmctrl/xdotool el sondeo de ventanas es ciego)"
        resultado["nota"] = nota
    c.json_out(resultado)


def construir_parser():
    parser = c.Parser(
        prog="ventanas.py (linux)",
        description="Ventanas en Linux: X11 por wmctrl/xdotool (EWMH) y "
                    "Wayland por swaymsg/hyprctl. La coincidencia de titulo "
                    "es por subcadena; si hay varias, se exige el exacto. "
                    "Rectangulos en coords de LAYOUT.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1] if __doc__ and "Subcomandos:" in __doc__ else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True, metavar="SUBCOMANDO")

    sub.add_parser("listar", help="todas las ventanas con id, titulo, rect y "
                   "estado") .set_defaults(func=cmd_listar)

    sub.add_parser("foco", help="ventana foreground: titulo, rect y estado") \
       .set_defaults(func=cmd_foco)

    for nombre, ayuda, funcion in (
        ("activar", "traer y enfocar la ventana", cmd_activar),
        ("minimizar", "minimizar (sway: move scratchpad)", cmd_minimizar),
        ("restaurar", "volver del minimizado", cmd_restaurar),
        ("maximizar", "maximizar (sway: fullscreen)", cmd_maximizar),
        ("cerrar", "cerrar (ojo: posibles modales)", cmd_cerrar),
    ):
        p = sub.add_parser(nombre, help=ayuda)
        p.add_argument("titulo", help="titulo (o parte) de la ventana; debe "
                       "ser unico")
        p.set_defaults(func=funcion)

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
    p.set_defaults(func=cmd_abrir)

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
