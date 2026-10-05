# computer-use-py — control del escritorio de Windows 11 como un humano

Skill para agentes: manejar el escritorio real (ratón, teclado, ventanas,
capturas) **como lo haría un humano**, con un loop de
`captura → visión → acción → verificación`. Cada acción pasa por un script
CLI que responde **JSON por stdout** (errores con clave `error` y salida 1),
así que el agente siempre puede releer el estado antes del siguiente paso.

No es un framework de automatización para terceros: es control del *propio*
escritorio con frenos humanos deliberados (FAILSAFE, watchdog, verificación
de foco).

## Stack (y por qué)

- **PyAutoGUI** — pirámide principal: capturas, teclado ASCII, ratón y
  ventanas (pygetwindow). Solo direcciona el monitor primario (FAQ oficial).
- **pynput** — tres cosas que PyAutoGUI no da bien en Windows: tipeo
  **unicode real** (ñ, acentos, emojis vía `KEYEVENTF_UNICODE`), **scroll
  horizontal** (el `hscroll` de pyautogui rueda vertical en silencio) y
  **listeners** que distinguen entrada humana de la inyectada (`injected`)
  para el botón de pánico. Además es el motor de ratón **garantizado** fuera
  del primario (coordenadas virtuales negativas).
- **pyperclip** — respaldo de tipeo por portapapeles (`ctrl+v`).

## Instalación

```bat
py -m pip install pyautogui pynput pyperclip pygetwindow
py -m pip install opencv-python   :: opcional, solo para localizar --confidence
```

Versiones de referencia: pyautogui 0.9.54, pynput 1.8.2, pygetwindow 0.0.9,
Pillow ≥ 6.2.0 (las capturas multi-monitor usan `ImageGrab` con
`all_screens=True`). Con pynput ≤ 1.8.1 el scroll de Windows se emite
duplicado: usar 1.8.2 como mínimo. Requiere Windows (los scripts fijan DPI
per-monitor antes de importar nada).

## El loop, con comandos reales

```bat
py scripts/monitores.py listar
py scripts/pantalla.py capturar
:: el JSON devuelve "archivo" con la ruta absoluta del PNG: leerlo con vision
py scripts/ventanas.py foco
py scripts/ventanas.py activar "Nombre de la ventana"
py scripts/raton.py click --x 640 --y 300
py scripts/pantalla.py esperar --milisegundos 500
py scripts/pantalla.py capturar   :: verificacion: ¿ocurrio lo esperado?
```

Reglas del loop: tras cada acción, **verificar con una captura** (la salida 0
no prueba que el clic haya existido); mantener una **mini-bitácora** de una
línea `acción→resultado`; y pedir **confirmación humana antes de acciones
irreversibles** (borrar, enviar, pagar, loguear, credenciales).

## Scripts y subcomandos

| Script | Subcomandos (ejemplos) |
|---|---|
| `monitores.py` | `listar` (mapa de monitores + bounding virtual) · `cursor` (monitor que contiene el cursor) |
| `pantalla.py` | `capturar` · `capturar --monitor 0\|primario\|virtual\|DISPLAY2` · `capturar --region -800 0 600 400` · `capturar --max-lado 1280` · `tamano [--virtual]` · `posicion` · `pixel x y` · `esperar --milisegundos 600` · `esperar --pixel 300 200 --color 255,255,255 --cambia --timeout 5` · `localizar icono.png --confidence 0.9` (solo primario) |
| `raton.py` | `mover 640 300 --duracion 0.2` · `click --x -800 --y 300` (fuera del primario = pynput) · `click --boton right --doble` · `arrastrar 100 100 400 350` · `arrastrar -800 400 300 400` (cruza monitores) · `scroll --vertical -5 --x -800 --y 300` · `posicion` |
| `teclado.py` | `escribir "España ¿cómo?"` (auto pynput si hay no-ASCII) · `escribir "..." --via portapapeles` · `tecla enter --repeticiones 2` · `combo "ctrl+shift+esc"` · `mantener shift --segundos 1` — todos con `--requiere-foco "sub"` opcional |
| `ventanas.py` | `listar` · `foco` · `abrir "app|URL|archivo" [--esperar s] [--titulo pista]` (lanza sin cmd; con `--esperar` aguarda su ventana nueva) · `activar|minimizar|restaurar|maximizar|cerrar "titulo"` |
| `vigilar.py` | `arrancar --segundos 30 --pausar-si-humano` (watchdog: tecla de pánico → bandera `ABORT`) |

## Seguridad

- **FAILSAFE siempre encendido**: arrastrar el ratón a cualquiera de las 4
  esquinas del monitor **primario** aborta la acción con un JSON `error`. No
  existe flag para desactivarlo.
- **`--requiere-foco "sub"`** en teclado: lee la ventana foreground ANTES de
  emitir y aborta sin teclear si el título no coincide (el título real va en
  el error).
- **`vigilar.py`** (botón de pánico): un listener pynput distingue entrada
  humana de la inyectada; la tecla de pánico (ESC por defecto) crea la
  bandera `ABORT` para que el agente pare, capture y pregunte.
- Nunca `suppress=True` (dejaría al usuario sin teclado) ni I/O dentro de un
  callback del listener.
- En un monitor **secundario no hay esquina failsafe**: allí el freno es la
  tecla de pánico de `vigilar.py` o Ctrl+C. Tras un abort, la acción puede
  haber quedado parcial: re-capturar antes de reintentar.

## Multi-monitor

Las coordenadas son del **espacio virtual** (origen = monitor primario;
negativos hacia la izquierda/arriba) y el input fuera del primario se enruta
solo por pynput. Detalle, verificaciones y trampas (como el `region=` que da
negro): ver `references/monitores-multi.md`.

## Notas del repo

- Los archivos temporales (capturas PNG, banderas `ABORT`/`PAUSA`, pruebas)
  viven en `.tmp/` de esta skill y **no se commitean** (guard en
  `.tmp/.gitignore`).
- `SKILL.md` es la guía de uso para el agente; `references/` guarda el
  conocimiento verificado (API, multi-monitor, comandos nativos multi-OS).
