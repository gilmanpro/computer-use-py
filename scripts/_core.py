# -*- coding: utf-8 -*-
"""_core.py — helpers GENERICOS multi-OS de computer-use-py.

Desde FASE SEG3 la skill es MULTI-OS SIMETRICA EN LA RAIZ: los 7 CLIs de
scripts/ (monitores/pantalla/teclado/raton/ventanas/vigilar/autotest) son LA
IMPLEMENTACION de los 3 SO dentro del propio proceso (dispatch por
sys.platform EN TIEMPO DE EJECUCION via modulo_sistema(), seccion 0c), y las
subcarpetas windows/ (solo win_especiales.py), linux/ (solo
linux_especiales.py) y macos/ (solo macos_especiales.py) guardan SOLO lo
exclusivo de cada SO: librerias importables en CUALQUIER SO cuyo guard de
plataforma vive unicamente en el __main__ de su CLI propio. Este modulo vive
en scripts/ raiz y lo importan tanto los CLIs (para resolver el dispatch)
como los 3 modulos exclusivos (glue_windows.py, linux_especiales.py y
macos_especiales.py), que le reexportan sus helpers.

QUE ES GENERICO Y POR QUE: todo lo que vive aqui es STDLIB PURO y no toca
ninguna API del SO: sin pyautogui, sin pynput, sin ctypes.windll, sin X11/
Quartz, sin subprocess de herramientas DEL SO — y desde SEG3 este modulo no
lance NINGUN proceso (el viejo enrutador SEG2 que re-lanzaba el Python de la
rama fue ELIMINADO: el dispatch ocurre en el propio proceso), sin DPI ni
guards de plataforma. Por eso puede vivir en scripts/ —RAIZ de los
dominios— e importarse desde cualquier SO sin efectos secundarios. Es
codigo que estaba DUPLICADO palabra-por-palabra (o
esencialmente igual) en los tres _compartido* y en los scripts de rama; la
segmentacion (FASE SEG) lo subio a esta unica copia:

  0c. DISPATCH DE PLATAFORMA EN EL PROCESO (SEG3): modulo_sistema()/
      so_no_soportado() — los CLIs raiz bindean `c = _core.modulo_sistema()`
      en TIEMPO DE EJECUCION (no de import, para poder parchar
      sys.platform en pruebas): win32 -> glue_windows.py, linux ->
      linux/linux_especiales.py, darwin -> macos/macos_especiales.py; otra
      plataforma responde el JSON de error rc 2 con el texto contractual
      heredado del viejo enrute SEG2.
  1. SALIDA Y ERRORES: json_out/fail/plataforma (contrato P0-4: "plataforma"
     SIEMPRE presente), tocar/borrar/asegurar_capturas y la clase Parser
     (errores de argparse como JSON canonico, P1-7).
  2. BANDERAS ABORT/PAUSA (P1-5): checar_abort, checar_pausa y
     checar_aborto_espera. Leen los archivos-bandera del .tmp/ de la skill.
  3. VALIDACION DE ARGS comun a las 3 ramas: validar_segundos,
     validar_tolerancia, validar_confidence, checar_args_esperar, y los caps
     cap_ms, cap_timeout_esperar, cap_segundos_mantener, checar_max_lado.
  4. ESPERAS portables: dormir (sueno fijo troceado con check ABORT por
     trozo) y esperar_color (bucle poll cambia/estable) — lo propio de cada
     SO (como leer el pixel) LLEGA POR CALLBACK desde la rama; el bucle y la
     contabilidad de ms son identicos en las 3.
  5. COLOR/TECLAS genericos: parsear_color ('r,g,b'), tiene_no_ascii y
     partes_combo (el ejemplo del mensaje es parametro de la rama: 'ctrl...'
     en win/linux, 'cmd...' en mac).
  6. GEOMETRIA de monitores (rects {izq,top,der,bot,primario,nombre}):
     monitor_contiene, dentro_del_bounding, bounding_de y resolver_monitor
     (algoritmo --monitor: 'virtual'|'primario'|indice|subcadena). La FUENTE
     de la lista (ctypes/xrandr/Quartz) y los TEXTOS con jerga del SO
     (szDevice/dwFlags vs xrandr/sway) los pasa la rama; el algoritmo no.
  7. CONTRATO DE CAPTURAS: ruta_destino_captura (convencion "nombre pelado
     cae en .tmp/capturas") y escalas_thumbnail (factor {escala} del
     --max-lado). La formula propia de cada SO para `px_por_unidad_coord`
     (grim/Retina/DPI) NO es generica: queda en la rama.
  8. DATOS compartidos: ALIAS_TECLAS_PYNPUT (tabla espanol->nombres pynput
     Key para win/linux; mac tiene su propia ALIAS_TECLAS_MAC por ser otro
     enum), ESQUEMA_URL (clasificador URL vs archivo) y BOTONES.
    9. AUTOTEST DE ESTRUCTURA: problemas_estructura() audita esta separacion
       (scripts/ raiz = los 7 CLIs multi-OS + _core.py + glue_windows.py + las
       3 carpetas de lo exclusivo; windows/ = SOLO win_especiales.py, linux/ =
       SOLO linux_especiales.py, macos/ = SOLO macos_especiales.py; ningun
       modulo exclusivo redefina un helper movido). Lo invocan la suite raiz
       unificada (scripts/autotest.py) de FASE SEG3.

QUE NO VIVE AQUI (por SO): guards de plataforma y DPI (SetProcessDpiAwareness
— en el glue_windows.py de esta misma raiz, exclusivo win32),
pyautogui/pynput/ctypes.windll, GetMonitorInfo e ImageGrab all_screens
(windows), xrandr/xdotool/wmctrl/grim/ydotool (linux),
osascript/screencapture/Quartz (macos), la construccion de la lista de
monitores con su `via`, el `MARCO` de cada rama, los textos `regla`/`nota`
por OS, fallar_por_failsafe (semantica de esquinas distinta por SO) y
win_especiales.py (scripts/windows/).

TEXTOS CANONICOS: los mensajes compartidos usan el texto de la rama WINDOWS
(validada en escritorio real). Donde linux/mac diferian solo ortograficamente
("reanuda" vs "relanza", "pequeno" vs "pequeño") windows quedo como canonico
(anotado en el reporte FASE SEG); cuando el texto contenia jerga propia del
SO (xrandr, szDevice, cmd+shift+esc) la rama lo sigue pasando como parametro
y su salida NO cambia.

Uso: los 7 CLIs de la raiz lo importan DIRECTO (viven en su misma carpeta) y
resuelven el dispatch con modulo_sistema(); glue_windows.py (raiz) y los
modulos exclusivos scripts/linux/linux_especiales.py y
scripts/macos/macos_especiales.py lo importan tras insertar scripts/ en su
sys.path y REEXPORTAN los helpers de este modulo con la forma exacta
`nombre = _core.nombre`, de modo que las secciones de cada SO en los CLIs
raiz pueden llamar c.nombre(...) con el MISMO alias en cualquier plataforma
(la auditoria problemas_redefiniciones() impone esa forma; el self-alias
`c = sys.modules[__name__]` de los modulos exclusivos es legal: 'c' no es un
helper movido).
"""

import argparse
import json
import os
import re
import sys
import time

# ---------------------------------------------------------------------------
# 0) Rutas de la skill y banderas
# ---------------------------------------------------------------------------
# scripts/ es el padre fisico de este archivo; su padre es la raiz de la
# skill. Da el mismo resultado importado desde la raiz de scripts/, desde
# glue_windows.py o desde las ramas linux/ y macos/ porque la ruta se resuelve
# contra __file__, no contra CWD.
RAIZ_SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_TMP = os.path.join(RAIZ_SKILL, ".tmp")
DIR_CAPTURAS = os.path.join(DIR_TMP, "capturas")
ARCHIVO_ABORT = os.path.join(DIR_TMP, "ABORT")
ARCHIVO_PAUSA = os.path.join(DIR_TMP, "PAUSA")
# scripts/ = carpeta de ESTE modulo (donde viven los CLIs multi-OS de la raiz
# y las subcarpetas windows/ linux/ macos/).
_DIR_SCRIPTS = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 0c) DISPATCH DE PLATAFORMA EN EL PROCESO (FASE SEG3: simetria total)
# ---------------------------------------------------------------------------
# Desde SEG3 los CLIs de la raiz YA NO relanzan la rama: ejecutan en el propio
# proceso la ruta de su SO. El modulo de primitivas por plataforma es:
#   win32  -> glue_windows.py        (raiz, exclusivo Windows)
#   linux  -> linux/linux_especiales.py   (importable en cualquier SO: el guard
#            de plataforma vive SOLO en su CLI __main__, nunca en el import)
#   darwin -> macos/macos_especiales.py   (idem)
# El CLI raiz hace, en TIEMPO DE EJECUCION (no de import, para que el
# unittest.mock pueda parchar sys.platform):
#
#       c = _core.modulo_sistema()     # o modulo_sistema(plat=...) en pruebas
#
# y toda la seccion de ese SO llama c.<primitiva>() con el MISIMO alias: los
# tres modulos reexportan los helpers genericos de _core (json_out, fail,
# Parser, ...) y exponen MARCO + sus primitivas propias. Importable desde
# cualquier SO (los pyautogui/pynput/Quartz/X11 van lazy dentro de funciones).
_MODULO_SISTEMA = {"win32": ("", "glue_windows"),
                   "linux": ("linux", "linux_especiales"),
                   "darwin": ("macos", "macos_especiales")}


def modulo_sistema(plat=None):
    """Modulo de primitivas del SO actual (o del indicado `plat` en pruebas).
    None si la plataforma no es win32/linux/darwin (el CLI responde entonces
    so_no_soportado()). Inserta scripts/<rama> en sys.path solo cuando toca."""
    import importlib
    plat = sys.platform if plat is None else plat
    entrada = _MODULO_SISTEMA.get(plat)
    if entrada is None:
        return None
    rama, nombre = entrada
    if rama:
        ruta = os.path.join(_DIR_SCRIPTS, rama)
        if ruta not in sys.path:
            sys.path.insert(0, ruta)
    return importlib.import_module(nombre)


def so_no_soportado(script):
    """Borde comun de los CLIs raiz para plataformas sin ruta (rc 2): mismo
    JSON contractual que producia el viejo enrutador SEG2. NO retorna."""
    datos = {"error": "%s: plataforma no soportada (%s); la entrada "
                      "multi-OS es scripts/<verbo>.py (raiz) solo en "
                      "win32, linux y darwin" % (script, sys.platform),
             "sistema_operativo": sys.platform,
             "plataforma": _PLAT_MAP.get(sys.platform, sys.platform)}
    print(json.dumps(datos, ensure_ascii=False, indent=2))
    sys.exit(2)

# ---------------------------------------------------------------------------
# 1) Salida JSON canonica (P0-4: "plataforma" SIEMPRE; json_out es la unica
#    via de salida) y errores
# ---------------------------------------------------------------------------
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


class Parser(argparse.ArgumentParser):
    """argparse cuyos errores salen como JSON canonico (P1-7).

    subprocess inviable: un `{"error"}` legible vale mas que un stderr de
    argparse con exit 2. `error()` se dispara en subcomando inexistente,
    flag invalido, valor de tipo erroneo o argumento requerido que falta.
    """

    def error(self, message):
        fail("argumentos invalidos: %s" % message,
             uso=self.format_usage().strip())


# ---------------------------------------------------------------------------
# 2) Banderas ABORT/PAUSA de vigilar.py (P1-5/P1-6) — copias identicas de los
#    tres _compartido*. Texto canonico: rama WINDOWS (validada en vivo).
# ---------------------------------------------------------------------------
def checar_abort(motivo="interrumpido"):
    """Corta la accion si el humano pidio parar (bandera ABORT de vigilar.py).

    Sin bandera, coste = un os.path.exists (comportamiento intacto). El
    motivo default ('interrumpido') conserva literal el mensaje historico de
    la rama mac, que llamaba a checar_abort() sin argumentos."""
    if os.path.exists(ARCHIVO_ABORT):
        fail("%s: existe la bandera ABORT del .tmp de ESTA skill "
             "(vigilar.py): un humano pidio parar. Captura la pantalla y "
             "pregunta antes de continuar." % motivo,
             bandera=ARCHIVO_ABORT)


def checar_pausa(espera_max=300.0):
    """Freno suave P1-5: mientras exista .tmp/PAUSA (vigilar --pausar-si-humano)
    la accion SE ESPERA (poll 0.2 s, tope 300 s) en vez de ejecutarse. ABORT
    manda sobre PAUSA. Sin bandera, coste = un os.path.exists: la temporizacion
    validada de inyeccion NO se altera (esto se llama en ARRANQUE de cada
    accion y en los polls de espera, nunca dentro de los pasos interpolados).
    """
    if not os.path.exists(ARCHIVO_PAUSA):
        return
    inicio = time.time()
    while os.path.exists(ARCHIVO_PAUSA):
        checar_abort("pausa interrumpida")  # ABORT tiene prioridad
        if time.time() - inicio > espera_max:
            fail("PAUSA activa mas de %d s (bandera %s): atiende al usuario, "
                 "borra la bandera y relanza, o usa ABORT para cortar la "
                 "secuencia." % (int(espera_max), ARCHIVO_PAUSA),
                 bandera_pausa=ARCHIVO_PAUSA)
        time.sleep(0.2)


def checar_aborto_espera():
    """Corta una espera larga si el humano pidio parar (bandera de vigilar.py).

    Wrapper con el motivo historico de las ramas win/linux; la rama mac sigue
    llamando a checar_abort() pelado (mensaje 'interrumpido:') para no alterar
    sus temporizaciones validadas."""
    checar_abort("esperar interrumpida")


# ---------------------------------------------------------------------------
# 3) Validacion de argumentos: los mensajes/limites eran copias 3x identicas
#    (vigilar --segundos; pantalla esperar --tolerancia/--timeout/
#    --milisegundos y coherencia --pixel/--color; localizar --confidence;
#    capturar --max-lado; teclado mantener --segundos).
# ---------------------------------------------------------------------------
def validar_segundos(segundos):
    """--segundos de vigilar.py: 1..900 (no es un demonio permanente)."""
    if not (1 <= segundos <= 900):
        fail("--segundos debe estar entre 1 y 900 (no es un demonio permanente).")


def validar_tolerancia(tol):
    """--tolerancia por canal de esperar --pixel: 0..255."""
    if not 0 <= tol <= 255:
        fail("--tolerancia debe estar entre 0 y 255.")


def validar_confidence(conf):
    """--confidence de localizar: 0.0..1.0."""
    if not (0.0 <= conf <= 1.0):
        fail("confidence debe estar entre 0.0 y 1.0.")


def checar_args_esperar(pixel, color, cambia, estable):
    """Coherencia --pixel/--color/--cambia/--estable de `esperar` (los tres
    fail() eran texto identico en las 3 ramas). Devuelve True si procede el
    modo adaptativo (pixel presente) y False para el sueno fijo."""
    if pixel is not None:
        if color is None:
            fail("El modo adaptativo requiere --pixel X Y y --color r,g,b juntos.")
        if not cambia and estable is None:
            fail("Indica --cambia o --estable M (ms de coincidencia "
                 "continua) junto a --pixel y --color.")
        return True
    if color is not None or cambia or estable is not None:
        fail("--color/--cambia/--estable solo valen con --pixel X Y; para "
             "una pausa fija usa solo --milisegundos N.")
    return False


def cap_duracion(d):
    """--duracion de arrastrar, acotada a [0.1, 30] s (la misma cifra en las
    3 ramas; mover usa semantica propia por SO y no se toca)."""
    return min(max(d, 0.1), 30.0)


def cap_ms(ms):
    """Milisegundos del sueno fijo, acotados a [0, 30000] (default 400)."""
    return min(max(int(ms), 0), 30000)


def cap_timeout_esperar(segundos):
    """Timeout del poll adaptativo, acotado a [0.5, 120] s (default 10)."""
    return min(max(segundos, 0.5), 120.0)


def cap_segundos_mantener(segundos):
    """Duracion de `mantener` tecla, acotada a [0.05, 60] s."""
    return min(max(segundos, 0.05), 60.0)


def checar_max_lado(n):
    """--max-lado del thumbnail: minimo 16 px (menos, la imagen es ilegible)."""
    if n < 16:
        fail("--max-lado demasiado pequeño (mínimo 16 px).")


# ---------------------------------------------------------------------------
# 4) Esperas portables: el bucle era identico en las 3 ramas; lo que cada SO
#    sabe hacer (leer el pixel, chequear su ABORT) llega por callback.
# ---------------------------------------------------------------------------
def dormir(ms, al_abortar=None, paso=200):
    """Sueno fijo troceado en pasos de `paso` ms con check de bandera tras
    cada trozo (bucle verbatim de las 3 ramas). `ms` ya acotado por cap_ms().
    `al_abortar`: callback cero-args que puede fail() (checar_aborto_espera
    en win/linux; checar_abort pelado en mac)."""
    restante = ms
    while restante > 0:
        tramo = min(restante, paso)
        time.sleep(tramo / 1000.0)
        restante -= tramo
        if al_abortar is not None:
            al_abortar()


def esperar_color(fn_coincide, cambia, estable_ms, limite_s, paso_s, inicio,
                  al_abortar):
    """Bucle poll --cambia|--estable sobre un pixel (verbatim de las 3 ramas):
    fn_coincide() lee el pixel del SO y dice si coincide con el color esperado
    (puede fail()); al_abortar() chequea la bandera ABORT (puede fail()).
    Devuelve (cumplida, ms_esperados) con `inicio` = time.monotonic() tomado
    por el script al arrancar el comando (el timeout agotado NO es error:
    cumplida=False)."""
    racha_ini = None
    cumplida = False
    while True:
        coincide = bool(fn_coincide())
        if cambia:
            cumplida = not coincide
        else:
            if coincide:
                if racha_ini is None:
                    racha_ini = time.monotonic()
                cumplida = (time.monotonic() - racha_ini) * 1000.0 >= estable_ms
            else:
                racha_ini = None
                cumplida = False
        if cumplida or (time.monotonic() - inicio) >= limite_s:
            break
        al_abortar()
        time.sleep(paso_s)
    al_abortar()
    return bool(cumplida), int((time.monotonic() - inicio) * 1000)


# ---------------------------------------------------------------------------
# 5) Color y combos genericos
# ---------------------------------------------------------------------------
def parsear_color(texto):
    """'r,g,b' -> tuple de 3 enteros 0-255; si no, fail() JSON (validacion
    verbatim, identica en las 3 ramas)."""
    partes = texto.split(",")
    if len(partes) != 3:
        fail('Color con formato "r,g,b" (tres enteros 0-255 separados por '
             'comas, sin espacios), no %r.' % texto)
    try:
        valores = [int(p) for p in partes]
    except ValueError:
        fail('Color con componentes no enteros: %r.' % texto)
    for v in valores:
        if not 0 <= v <= 255:
            fail("Color fuera de rango 0-255: %r." % texto)
    return tuple(valores)


def tiene_no_ascii(texto):
    """True si el texto tiene caracteres fuera de ASCII 0-127 (pyautogui
    descarta esos en silencio; la rama deriva a pynput/portapapeles)."""
    return any(ord(ch) > 127 for ch in texto)


def partes_combo(cadena, ejemplo):
    """'mod+tecla' -> lista normalizada; si vacia, fail() con el ejemplo de
    formato de la rama (`ejemplo`: 'ctrl+shift+esc' en win/linux,
    'cmd+shift+esc' en mac: la tecla canonica difiere por SO)."""
    partes = [p.strip().lower() for p in cadena.split("+") if p.strip()]
    if not partes:
        fail('Cadena de combo vacia. Formato: "%s" (separado por +).' % ejemplo)
    return partes


# ---------------------------------------------------------------------------
# 6) Geometria de monitores: los rects ya vienen normalizados por la rama
#    ({nombre, izq, top, der, bot, primario}); aqui solo aritmetica pura. La
#    fuente de la lista y la jerga del SO en los mensajes quedan en la rama.
# ---------------------------------------------------------------------------
PALABRAS_VIRTUAL = ("virtual", "toda", "todas", "todo")
PALABRAS_PRIMARIO = ("primario", "primary")


def monitor_contiene(mons, x, y):
    """Monitor cuyo rectangulo contiene a (x, y), o None.

    None = el punto cae fuera de todo monitor (hueco del bounding virtual
    en monitores desalineados, o coordenadas fuera del todo). Formula
    identica en las 3 ramas (der/bot exclusivos)."""
    xi, yi = int(x), int(y)
    for m in mons:
        if m["izq"] <= xi < m["der"] and m["top"] <= yi < m["bot"]:
            return m
    return None


def bounding_de(mons):
    """Bounding de todos los rects: dict {x, y, ancho, alto} (formula
    identica en las 3 ramas: min izq/top, max der/bot)."""
    x0 = min(m["izq"] for m in mons)
    y0 = min(m["top"] for m in mons)
    x1 = max(m["der"] for m in mons)
    y1 = max(m["bot"] for m in mons)
    return {"x": x0, "y": y0, "ancho": x1 - x0, "alto": y1 - y0}


def dentro_del_bounding(v, x, y):
    """True si (x, y) cae dentro del bounding v = bounding_de(...). Cada
    rama la expone como dentro_de_virtual() sobre su propio tamano_virtual()."""
    return (v["x"] <= int(x) < v["x"] + v["ancho"]
            and v["y"] <= int(y) < v["y"] + v["alto"])


def resolver_monitor(valor, obtener_mons, sin_primario, indice_rango, ambiguo,
                     sin_nombre):
    """Algoritmo generico de --monitor (identico en las 3 ramas): None si
    'virtual' (bounding completo), dict del monitor si 'primario'|indice|
    subcadena del nombre (case-insensitive). `obtener_mons` es un callable
    cero-args que produce la lista de la rama (se llama SOLO despues del
    short-circuit 'virtual', como antes). Los textos de error los pasa la
    rama porque llevan jerga propia del SO ('dwFlags/szDevice' en Windows,
    'xrandr/sway/hypr' en Linux...): sin_primario sin argumentos;
    indice_rango % (idx, max_idx); ambiguo % (valor, nombres); sin_nombre
    % valor."""
    v = valor.strip().lower()
    if v in PALABRAS_VIRTUAL:
        return None
    mons = obtener_mons()
    if v in PALABRAS_PRIMARIO:
        for m in mons:
            if m["primario"]:
                return m
        fail(sin_primario)
    try:
        idx = int(valor)
    except ValueError:
        idx = None
    if idx is not None:
        if 0 <= idx < len(mons):
            return mons[idx]
        fail(indice_rango % (idx, len(mons) - 1))
    coincidencias = [m for m in mons if v in str(m["nombre"]).lower()]
    if len(coincidencias) == 1:
        return coincidencias[0]
    if len(coincidencias) > 1:
        fail(ambiguo % (valor, [m["nombre"] for m in coincidencias]))
    fail(sin_nombre % valor)


# ---------------------------------------------------------------------------
# 7) Contrato de capturas: convencion de destino y matematica del thumbnail
#    (la formula OS-especifica de px_por_unidad_coord sigue en cada rama).
# ---------------------------------------------------------------------------
def ruta_destino_captura(archivo=None):
    """Ruta destino PNG con la convencion de la skill (identica en las 3
    ramas): un nombre pelado (sin separador de carpeta) se resuelve dentro
    de .tmp/capturas; una ruta con directorio (relativo o absoluto) se
    respeta tal cual para usos explicitos; sin nombre, captura_<fecha_hora>.png."""
    if archivo:
        destino = archivo
        if not (os.path.dirname(destino) or destino.startswith(("\\", "/"))):
            destino = os.path.join(asegurar_capturas(), destino)
        ruta = os.path.abspath(destino)
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
        return ruta
    return os.path.join(asegurar_capturas(),
                        "captura_%s.png" % time.strftime("%Y%m%d_%H%M%S"))


def escalas_thumbnail(fis_w, fis_h, ancho_final, alto_final):
    """(escala_x, escala_y) imagen->fuente tras --max-lado: fis/ancho_final.
    Sin thumbnail ancho_final==fis_w => (1.0, 1.0) exacto, como el default
    historico de las ramas. El round(*, 6) lo aplica cada rama al armar su
    JSON (los campos extra por SO — factor_grim, Retina — se calculan alli)."""
    return fis_w / float(ancho_final), fis_h / float(alto_final)


# ---------------------------------------------------------------------------
# 8) Datos compartidos: tabla de alias de teclas, esquema URL y botones
# ---------------------------------------------------------------------------
# Nombres de tecla pyautogui/espanol -> miembros del enum Key de pynput 1.8.2
# (verificado en el backend _win32 de Windows y valido igual en el backend
# X11 de Linux: esc, ctrl, cmd_l, print_screen, menu, pause y las media_*
# existen en ambos). La rama mac tiene SU propia tabla (ALIAS_TECLAS_MAC):
# en darwin no existen print_screen/pause/menu ni Key.media_stop. Cada rama
# construye su tecla con tecla_pynput() local (importar pynput aqui estaria
# prohibido: es API externa, no generica).
ALIAS_TECLAS_PYNPUT = {
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
    # Teclas multimedia nombradas por pyautogui -> equivalentes Key.media_*
    # de pynput (digests pyautogui §3 y pynput §3).
    "volumemute": "media_volume_mute", "mute": "media_volume_mute",
    "volumedown": "media_volume_down", "volumeup": "media_volume_up",
    "playpause": "media_play_pause", "nexttrack": "media_next",
    "prevtrack": "media_previous", "stop": "media_stop",
}

# Clasificador de objetivo para `ventanas.py abrir` (man de cada SO abre URLs
# por esquema): texto con esquema 'algo:' o 'www.' adelante. Copia unica de la
# que estaba verbatim en ventanas.py (las 3 ramas) y win_especiales.py.
ESQUEMA_URL = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.\-]{1,}:|www\.)")

# Botones de raton del contrato JSON de la skill (raton.py click/arrastrar).
BOTONES = ("left", "right", "middle")


# ---------------------------------------------------------------------------
# 9) Autotest de estructura multi-OS (invocado por la suite raiz unificada
#    scripts/autotest.py de FASE SEG3): audita que la separacion
#    generico/exclusivo y el layout SEG3 se mantengan.
# ---------------------------------------------------------------------------
RAMAS = ("windows", "linux", "macos")
# FASE SEG3: los 7 CLIs multi-OS VIVEN en scripts/ raiz y son LA
# IMPLEMENTACION de los 3 SO en el propio proceso (dispatch sys.platform en
# runtime via modulo_sistema); las carpetas windows/ linux/ macos/ guardan
# SOLO el modulo exclusivo de su SO. __pycache__ es residuo de import, se
# tolera. Si creciera un modulo generico mas, anadirlo aqui y abajo en la
# evidencia del check.
CLI_RAIZ = ("autotest.py", "monitores.py", "pantalla.py", "raton.py",
            "teclado.py", "ventanas.py", "vigilar.py")
GLUE_RAIZ = "glue_windows.py"  # glue EXCLUSIVO Windows (DPI/pyautogui/ctypes)
CORE_RAIZ = "_core.py"
ESPERADO_RAIZ_SCRIPTS = (frozenset(RAMAS) | frozenset(CLI_RAIZ)
                         | {CORE_RAIZ, GLUE_RAIZ, "__pycache__"})
# Unico archivo que queda en cada carpeta de lo exclusivo (los demas subieron
# a la raiz o fueron retirados con el enrute SEG2):
ESPERADO_WINDOWS_RAMAS = frozenset({"win_especiales.py", "__pycache__"})
ESPERADO_LINUX_RAMAS = frozenset({"linux_especiales.py", "__pycache__"})
ESPERADO_MACOS_RAMAS = frozenset({"macos_especiales.py", "__pycache__"})
_RAMA_ESPERADA = {
    "windows": (ESPERADO_WINDOWS_RAMAS, "win_especiales.py"),
    "linux": (ESPERADO_LINUX_RAMAS, "linux_especiales.py"),
    "macos": (ESPERADO_MACOS_RAMAS, "macos_especiales.py"),
}
# Modulo exclusivo por rama (ruta relativa a scripts/): el de windows es el
# glue de la RAIZ; linux/macos tienen su libreria dentro de su carpeta. Los
# tres los resuelve modulo_sistema() en runtime.
_MODULO_COMUN = {"windows": GLUE_RAIZ,
                 "linux": os.path.join("linux", "linux_especiales.py"),
                 "macos": os.path.join("macos", "macos_especiales.py")}

# Nombres que VIVEN aqui. Ningun modulo exclusivo (glue_windows.py,
# linux_especiales.py, macos_especiales.py) puede redefinirlos
# (def/class propio o asignacion que no venga de _core): solo reexportarlos
# con la forma exacta `nombre = _core.nombre` para que los CLIs raiz sigan
# llamando c.nombre(...) en cualquier SO. HELPERS_COMUNES es la lista que
# audita el check. El self-alias `c = sys.modules[__name__]` de los modulos
# exclusivos es legal: 'c' no figura en esta lista.
HELPERS_COMUNES = (
    "json_out", "fail", "tocar", "borrar", "asegurar_capturas", "plataforma",
    "Parser", "checar_abort", "checar_pausa", "checar_aborto_espera",
    "dormir", "esperar_color", "cap_ms", "cap_timeout_esperar",
    "cap_segundos_mantener", "cap_duracion", "validar_segundos",
    "validar_tolerancia",
    "validar_confidence", "checar_max_lado", "checar_args_esperar",
    "parsear_color", "tiene_no_ascii", "partes_combo", "resolver_monitor",
    "monitor_contiene", "dentro_del_bounding", "bounding_de",
    "escalas_thumbnail", "ruta_destino_captura", "ALIAS_TECLAS_PYNPUT",
    "ESQUEMA_URL", "BOTONES",
)


# `nombre = ...` en primera columna (excluye ==, y los nombres con guion bajo
# inicial como _DIR_PADRE quedan fuera de HELPERS_COMUNES de todos modos).
_RE_ASIGNACION = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)[ \t]*=(?!=)")


def problemas_inventario_scripts():
    """Check 1 de estructura (FASE SEG3): scripts/ raiz contiene SOLO los 7
    CLIs multi-OS + _core.py + glue_windows.py + las carpetas windows/ linux/
    macos/ (tolerado __pycache__); los 9 archivos obligatorios EXISTEN; y
    CADA carpeta de lo exclusivo conserva SOLO su modulo especial:
    windows/ = win_especiales.py, linux/ = linux_especiales.py y
    macos/ = macos_especiales.py. Devuelve lista de violaciones; vacio = OK.
    (Respecto a SEG2 se elimino la auditoria del enrute: ya no existe.)"""
    errores = []
    for nombre in sorted(os.listdir(_DIR_SCRIPTS)):
        if nombre not in ESPERADO_RAIZ_SCRIPTS:
            errores.append("scripts/ raiz tiene un elemento no esperado: %r "
                           "(solo se permite _core.py + glue_windows.py + los "
                           "7 CLIs + windows/ linux/ macos/)" % nombre)
    faltan = [n for n in (CORE_RAIZ, GLUE_RAIZ) + CLI_RAIZ
              if not os.path.isfile(os.path.join(_DIR_SCRIPTS, n))]
    if faltan:
        errores.append("faltan archivos obligatorios en scripts/ raiz: %s" % faltan)
    for rama in RAMAS:
        esperada, unico = _RAMA_ESPERADA[rama]
        carpeta = os.path.join(_DIR_SCRIPTS, rama)
        if os.path.isdir(carpeta):
            for nombre in sorted(os.listdir(carpeta)):
                if nombre not in esperada:
                    errores.append("scripts/%s/ debe conservar SOLO %s; sobra %r"
                                   % (rama, unico, nombre))
    return errores


def problemas_redefiniciones():
    """Check 2 de estructura: ningun modulo exclusivo (glue_windows.py en
    la raiz; linux/linux_especiales.py y macos/macos_especiales.py en sus
    carpetas) redefina un helper de
    HELPERS_COMUNES con def/class propio ni con una asignacion que no venga
    de _core (la unica forma admitida es `nombre = _core.nombre`). Devuelve
    lista de violaciones; vacio = OK."""
    errores = []
    for rama in RAMAS:
        ruta = os.path.join(_DIR_SCRIPTS, _MODULO_COMUN[rama])
        if not os.path.isfile(ruta):
            errores.append("rama %s: falta %s" % (rama, _MODULO_COMUN[rama]))
            continue
        with open(ruta, encoding="utf-8") as fh:
            lineas = fh.read().splitlines()
        # def/class top-level que redefinan un nombre movido:
        texto = "\n".join(lineas)
        for nombre in HELPERS_COMUNES:
            if re.search(r"^(?:def|class)[ \t]+%s\b" % nombre, texto, re.M):
                errores.append("rama %s: su modulo comun redefine %s (debe "
                               "reexportarlo desde _core)" % (rama, nombre))
        # asignaciones `nombre = ...` de primera columna: admitida SOLO la
        # forma de reexport `nombre = _core.<algo>`; cualquier otra se marca.
        for linea in lineas:
            m = _RE_ASIGNACION.match(linea)
            if not m:
                continue
            nombre = m.group(1)
            rhs = linea.split("=", 1)[1].strip()
            if nombre in HELPERS_COMUNES and not rhs.startswith("_core."):
                errores.append("rama %s: su modulo comun asigna %s sin venir "
                               "de _core.%s" % (rama, nombre, nombre))
    return errores


def problemas_estructura():
    """Auditoria combinada de la separacion generico/exclusivo (la invocan
    los checks de estructura de la suite raiz unificada scripts/autotest.py
    de FASE SEG3)."""
    return problemas_inventario_scripts() + problemas_redefiniciones()
