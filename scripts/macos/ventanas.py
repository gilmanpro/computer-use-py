# -*- coding: utf-8 -*-
"""ventanas.py — Ventanas de macOS via osascript/System Events y `open`
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
  restaurar   intentos: AXMinimized=false / activar app [runtime].
  maximizar   sin equivalente en macOS: error honesto.
  cerrar      close window.
  abrir       open -a|open <archivo|URL> + opcional --esperar ventana nueva.

Ejemplos (desde la carpeta computer-use-py, en el Mac):
  python3 scripts/macos/ventanas.py listar
  python3 scripts/macos/ventanas.py foco
  python3 scripts/macos/ventanas.py activar "Sin título — TextEdit"
  python3 scripts/macos/ventanas.py abrir TextEdit --esperar 8
  python3 scripts/macos/ventanas.py abrir "https://example.com"
  python3 scripts/macos/ventanas.py abrir "/tmp/informe.pdf" --esperar 8 --titulo informe
"""

import argparse
import os
import re
import subprocess

import _compartido_mac as c

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


def cmd_listar(args):
    regs = _listar_crudo()
    c.json_out({
        "total": len(regs),
        "ventanas": [_estado_item(r) for r in regs],
        "marco": c.MARCO,
        "unidad": "puntos logicos del espacio global",
        "nota": "rectangulos en PUNTOS (position/size de System Events "
                "[runtime]); item canonico rect+estado anidados; "
                "'maximizada' siempre null: macOS no maximiza (zoom con "
                "boton verde); 'activa' = proceso frontmost; los titulos se "
                "sanitizan sin los separadores \\x1f/\\x1e",
    })


def cmd_foco(args):
    regs = _listar_crudo()
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
    item = _estado_item(r)
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


def cmd_activar(args):
    _accion_ventana(
        args.titulo, "activar", _CUERPO_ACTIVAR,
        "el foco decide quien recibe el teclado: verifica con capturar; "
        "'AXRaise' es [runtime] y se omite en silencio si la app no lo "
        "soporta (el frontmost igual se aplico)")


def cmd_minimizar(args):
    _accion_ventana(
        args.titulo, "minimizar", _CUERPO_MINIMIZAR,
        "accion AXMinimize [runtime: string por cotejar con el diccionario "
        "de System Events]; muchas apps minimizan al Dock: verifica con "
        "capturar")


def cmd_restaurar(args):
    _accion_ventana(
        args.titulo, "restaurar", _CUERPO_RESTAURAR,
        "restaurar no es una primitiva de AppleScript: se probo "
        "AXMinimized=false [runtime]; si 'detalle' dice frontmost-only la "
        "ventana puede seguir en el Dock: clic en el Dock o menú Ventana "
        "de la app")


def cmd_maximizar(args):
    c.fail("macOS no tiene 'maximizar': el boton verde hace ZOOM y no hay "
           "commando de System Events documentado en la guia leida. "
           "Alternativas: arrastrar la barra de titulo a tope (raton.py "
           "arrastrar), doble clic en la barra (zoom, segun ajuste del "
           "sistema [runtime]) o full-screen con cmd+ctrl+f (teclado.py "
           "combo). El rect se lee con listar.",
           pista="teclado.py combo \"cmd+ctrl+f\" para full-screen real")


def cmd_cerrar(args):
    _accion_ventana(
        args.titulo, "cerrar", _CUERPO_CERRAR,
        "muchas apps abren un dialogo modal al cerrar (guardar cambios?): "
        "verifica SIEMPRE con pantalla.py capturar")


# --- abrir ---------------------------------------------------------------

# Esquema de URL: >=2 letras/digitos y +-. antes de ':' (descarta "C:\\ruta"
# del dominio Windows; en mac tambien "file:") o prefijo "www.".
_ESQUEMA_URL = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.\-]{1,}:|www\.)")


def _clasificar(objetivo):
    """(tipo, resuelto): 'url' | 'archivo' | 'app' | (None, None).

    Orden: esquema URL o 'www.' (man: URL se abre como URL); ruta existente
    (man: open abre archivos/directorios con su app por defecto); si no, se
    intenta como app via open -a (LaunchServices resuelve nombre o ruta de
    .app). Devuelve (None, None) si no existe ni como archivo: el error de
    open -a con nombre inexistente se captura al ejecutar.
    """
    if _ESQUEMA_URL.match(objetivo):
        return "url", objetivo
    if os.path.exists(objetivo):
        return "archivo", os.path.abspath(objetivo)
    return "app", objetivo


def _pista_por_defecto(objetivo, tipo):
    """Pista de titulo derivada del objetivo (orientativa; ante titulos
    localizados usa --titulo explicito)."""
    if tipo == "url":
        resto = re.sub(r"^[A-Za-z][A-Za-z0-9+.\-]{1,}:/*", "", objetivo)
        if re.match(r"^[A-Za-z]:[\\/]", resto) or resto.startswith("/"):
            return os.path.basename(resto) or objetivo
        return re.split(r"[/?#]", resto, maxsplit=1)[0] or objetivo
    base = os.path.basename(os.path.normpath(objetivo))
    return os.path.splitext(base)[0] if tipo == "app" else base


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


def cmd_abrir(args):
    if not (0 <= args.esperar <= 120):
        c.fail("--esperar debe estar entre 0 y 120 segundos (0 = no "
               "esperar).")
    tipo, resuelto = _clasificar(args.objetivo)
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

    pista = (args.titulo or "").strip() or _pista_por_defecto(args.objetivo,
                                                               tipo)
    previos = _snapshot_pares() if args.esperar > 0 else set()

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
    c.checar_abort()
    c.checar_pausa()  # P1-5/P1-6: el freno dura durante la espera
    limite = c.time.time() + args.esperar
    while c.time.time() < limite:
        try:
            regs = _listar_crudo()
        except SystemExit:
            raise
        except Exception:
            regs = []  # osascript fallo puntual: seguir sondeando
        nuevas = [r for r in regs
                  if (r["app"], r["titulo"]) not in previos
                  and pista.lower() in r["titulo"].lower()]
        if nuevas:
            nuevo = nuevas[0]
            break
        c.checar_abort()
        c.time.sleep(0.5)

    if nuevo is not None:
        resultado["ventana"] = _estado_item(nuevo)
        resultado["via"] = "open|osascript"
        resultado["nota"] = ("ventana NUEVA (par app+titulo no visto antes) "
                             "con pista %r; rect en puntos logicos y "
                             "'activa' dice si ya recibe el teclado "
                             "(re-verifica con pantalla.py capturar)" % pista)
    else:
        try:
            pre = len([r for r in _listar_crudo()
                       if pista.lower() in r["titulo"].lower()])
        except Exception:
            pre = None
        resultado["ventana"] = None
        resultado["preexistentes_con_pista"] = pre
        nota = ("timeout de %d s sin ventana NUEVA con pista %r (NO es "
                "error): la app pudo abrir sin ventana, tardar mas, o "
                "REUTILIZAR su ventana (navegador, documento ya abierto): "
                "en mac la identidad es (app, titulo), no hay hWnd. "
                "Verifica con listar o capturar." % (args.esperar, pista))
        if proc is not None and proc.poll() is not None and proc.returncode:
            resultado["open_rc"] = proc.returncode
            nota += " El proceso 'open' termino con rc=%s." % proc.returncode
        resultado["nota"] = nota
    c.json_out(resultado)


def construir_parser():
    parser = argparse.ArgumentParser(
        prog="ventanas.py (macOS)",
        description="Listar y manejar ventanas de macOS via "
                    "osascript/System Events (datos siempre por argv) y "
                    "lanzar con `open` nativo. Coincidencia de titulo por "
                    "subcadena; si hay varias, se exige el titulo exacto. "
                    "Rectangulos en PUNTOS LOGICOS del espacio global.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Subcomandos:")[1]
        if __doc__ and "Subcomandos:" in __doc__ else None,
    )
    sub = parser.add_subparsers(dest="comando", required=True,
                                metavar="SUBCOMANDO")

    sub.add_parser("listar", help="todas las ventanas con app, titulo, "
                   "rectangulo y estado").set_defaults(func=cmd_listar)

    sub.add_parser("foco", help="ventana foreground: app, titulo, rect y "
                   "estado").set_defaults(func=cmd_foco)

    for nombre, ayuda, funcion in (
        ("activar", "set frontmost del proceso dueno", cmd_activar),
        ("minimizar", "minimizar la ventana (AXMinimize [runtime])",
         cmd_minimizar),
        ("restaurar", "restaurar desde minimizada (intentos AX)",
         cmd_restaurar),
        ("maximizar", "no existe en macOS: error honesto con alternativas",
         cmd_maximizar),
        ("cerrar", "cerrar la ventana (ojo: posibles modales)", cmd_cerrar),
    ):
        p = sub.add_parser(nombre, help=ayuda)
        p.add_argument("titulo",
                       help="titulo (o parte) de la ventana; debe ser unico")
        p.set_defaults(func=funcion)

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
