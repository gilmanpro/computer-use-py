---
name: computer-use-py
description: "Controla el escritorio de Windows 11 como un humano: teclea texto, usa combinaciones de teclas, mueve el raton, hace clic, clic derecho, arrastrar, scroll vertical y horizontal, minimiza, maximiza o activa ventanas y toma capturas de pantalla que el agente vuelve a mirar con vision para decidir el siguiente movimiento, con PyAutoGUI y pynput sobre scripts CLI que responden JSON. Usar siempre que el usuario pida haz clic en, escribe en el campo, oprime teclas, ctrl+s, scroll, arrastra esto, minimiza la ventana, captura la pantalla y mira, usa el raton o el teclado en mi PC, automatizar una aplicacion de escritorio, o mencione pyautogui, pynput o control del escritorio. Para las ventanas incrustadas de Orca existe computer-use-orca; para paginas web usa playwright; si la accion tiene API o CLI directa, no usar esta skill."
license: MIT
---

# computer-use-py — control del escritorio de Windows 11 como un humano

Pirámide: **PyAutoGUI** (capturas, locate*, teclado ASCII, ratón/ventanas vía
pygetwindow — dentro del primario) + **pynput** (scroll, tipeo unicode real,
media keys, listeners con `injected` y motor de ratón garantizado fuera del
primario) + **pyperclip** (pegado). Todo vía `scripts/`: JSON por stdout,
errores con clave `error`, y nada apaga el FAILSAFE. Ejemplos con `py`.

## 1. Cuándo usar, cuándo no

- Regla de operación: todas las ejecuciones pasan por los scripts de esta
  skill; usa `ventanas.py abrir` en lugar de comandos cmd/powershell.
- Usa: hay que tocar una UI visible (clic, teclear, scroll, minimizar) sin
  interfaz programática, o el usuario pide "mira la pantalla y decide": el
  ciclo captura→visión→acción es el patrón central (§3).
- No uses: si hay API, CLI o MCP que logre el mismo resultado; la entrada
  sintética es lenta y frágil en comparación.
- No uses: contra apps elevadas («ejecutar como administrador»): Windows
  descarta en silencio lo inyectado (pyautogui atraga `PermissionError` y
  finge que no pasó); sin Python elevado es escribir a ciegas.
- Multi-monitor: SÍ se soporta — coordenadas del ESPACIO VIRTUAL (§8), mapa
  con `monitores.py listar`, y fuera del primario el ratón va por pynput.
- No uses: juegos a pantalla completa ni apps DirectInput (leen scancodes y
  aquí solo llegan teclas virtuales; alternativa documentada: pydirectinput).
- Core Windows: en X11/macOS funciona con límites; multi-OS sin Python ni pip → `references/comandos-sistema.md` (§7).
- Alternativas de alcance distinto (NO dependencias — la skill no las invoca ni
  las necesita): Orca embebido → `computer-use-orca`; web → `playwright-cli`.

## 2. Setup

```bat
py -m pip install pyautogui pynput pyperclip pygetwindow
py -m pip install opencv-python   :: opcional, solo para localizar --confidence
```

Versiones verificadas: pyautogui 0.9.54, pynput 1.8.2, pygetwindow 0.0.9, pyperclip 1.11.0,
Pillow 12.2.0 (`all_screens` exige ≥ 6.2.0). Con pynput ≤ 1.8.1 el scroll se duplica: mínimo 1.8.2.

## 3. El loop agéntico (patrón central)

Capturar → leer el PNG con visión (herramienta read) → decidir coordenadas →
actuar → esperar el render → capturar de verificación.

```bat
py scripts/monitores.py listar
py scripts/pantalla.py capturar   :: JSON "archivo": ruta absoluta del .tmp de ESTA skill
py scripts/ventanas.py foco
py scripts/raton.py click --x 640 --y 300
py scripts/pantalla.py esperar --milisegundos 500
py scripts/pantalla.py capturar
```

- Tras cada acción espera el render: `esperar --milisegundos 400-1000` o
  adaptativo `esperar --pixel X Y --color r,g,b --cambia` (PAUSE=0.15 NO cubre animaciones ni modales).
- Mini-bitácora: tras cada verificación escribe UNA línea "acción→resultado"
  (p. ej. `clic(640,300)→modal abierto`) y decide sobre ella.
- Antes de acciones IRREVERSIBLES (borrar, enviar, pagar, loguear,
  credenciales) pide confirmación humana explícita y espera el OK.
- En secuencias de varios pasos, arranca el freno humano antes de empezar
  (segundo plano): `py scripts/vigilar.py arrancar --segundos 30
  --pausar-si-humano`, y entre paso y paso comprueba la bandera `ABORT` del
  `.tmp` de esta skill (el JSON de vigilar devuelve su ruta).

## 4. Mapa de tarea → herramienta

| Tarea | Comando |
|---|---|
| Mapa de monitores / dónde está el cursor | `monitores.py listar` · `monitores.py cursor` |
| Ver la pantalla: primario, región, un monitor o todo el virtual | `pantalla.py capturar` · `--region x y w h` (coords virtuales, acepta negativos) · `--monitor 0\|1\|primario\|virtual\|DISPLAY1` |
| Captura económica | `pantalla.py capturar --max-lado 1280` — RE-ESCALA con `origen`/`escala`/`regla` del JSON |
| Esperar render / pixel objetivo | `pantalla.py esperar --milisegundos N` · `esperar --pixel X Y --color r,g,b --cambia\|--estable M` |
| Resol. / cursor / color | `pantalla.py tamano [--virtual]` · `posicion` · `pixel x y` (virtuales) |
| Patrón visual conocido | `pantalla.py localizar icono.png --confidence 0.9` (SOLO primario; locate cuesta 1-2 s) |
| Texto (ñ, acentos, emojis) / pegar | `teclado.py escribir "España ¿cómo?"` · `--via portapapeles` |
| Teclear solo con el foco correcto | `teclado.py escribir/tecla/combo ... --requiere-foco "subcadena"` |
| Teclas, combos, multimedia, mantener | `teclado.py tecla enter --repeticiones 2` · `combo "ctrl+shift+esc"` · `tecla volumemute` · `mantener shift --segundos 1` |
| Mover el cursor | `raton.py mover x y --duracion 0.2` (negativos = secundario, pynput) |
| Clic / derecho / doble | `raton.py click [--x --y] [--boton right] [--doble]` |
| Arrastrar | `raton.py arrastrar x1 y1 x2 y2 --duracion 0.5` |
| Scroll vertical y horizontal | `raton.py scroll --vertical -5` · `--horizontal 3` |
| Ver ventanas / quién recibe el teclado | `ventanas.py listar` (rect virtual) · `ventanas.py foco` |
| Ventanas | `ventanas.py activar|minimizar|restaurar|maximizar|cerrar "titulo"` |
| Ventana minimizada | `restaurar` ANTES de `activar`: sobre una minimizada `activar` falla (error 6) o no hace nada; re-verifica el foco con captura |
| Abrir app/URL/archivo | `ventanas.py abrir "programa|url|ruta" [--esperar SEG] [--titulo "sub"]` — lanzar app/URL/archivo (con o sin esperar su ventana) |
| Botón de pánico | `vigilar.py arrancar --segundos N` → bandera `.tmp\ABORT` |

## 5. Seguridad

- FAILSAFE encendido siempre: arrastrar el ratón a cualquiera de las 4 esquinas
  del monitor PRIMARIO aborta la acción en curso con un JSON `error` (no existe
  flag para apagarlo). En un monitor SECUNDARIO no hay esquina failsafe: el
  freno es la tecla de pánico de vigilar.py (bandera ABORT) o Ctrl+C; la huida
  humana a (0,0) sigue válida.
- Tras un abort por FAILSAFE la acción puede estar PARCIAL (botón sin soltar,
  medio arrastrar): re-captura antes de reintentar.
- PAUSE fijo en 0.15 s; nunca bajarlo (subirlo sí, si la app va lenta).
- Salida 0 de un script solo significa "la llamada no lanzó excepción": en apps
  elevadas el clic desaparece sin error. Verifica con captura tras cada acción y
  confirma el foco (`ventanas.py foco` / `--requiere-foco`) antes de teclear.
- Si aparece `.tmp\ABORT`: para la secuencia, captura la pantalla y pregunta
  al usuario. Borra la bandera y relanza el watchdog al retomar.
- Nunca usar listeners con `suppress=True`: suprime el teclado a todo el
  sistema y deja al usuario indefenso (ni Ctrl+C).
- Capturas y banderas viven en el `.tmp\` de ESTA skill (ruta absoluta en el
  JSON) — contenido jamás commiteable (hay guard en `.tmp\.gitignore`).

## 6. Anti-patrones (con el porqué)

- Clic a ciegas sin captura después: en apps elevadas pyautogui silencia el
  `PermissionError` y el clic puede no haber existido.
- Clicar sobre una captura `--max-lado` sin re-escalar: la coordenada golpea
  desplazada — aplica `origen + coord_imagen × físico/ancho_imagen` (regla del JSON).
- Dropdown/scroll que no responde e insistir con el ratón: pasa al teclado
  (`page_down`, `tab`, flechas, letra inicial).
- Reintentar tras un FAILSAFE sin re-capturar: la acción pudo quedar parcial
  (botón sin soltar, medio arrastre).
- `pyautogui.screenshot(region=...)` con x negativa: pyscreeze recorta sin
  traducir el offset virtual ⇒ imagen NEGRA; usa `capturar --region/--monitor`
  (ImageGrab `all_screens=True`).
- Mandar no-ASCII por pyautogui: su mapa Windows (32-127) descarta ñ/á/emojis
  en silencio; `escribir` auto deriva a pynput o usa `--via portapapeles`.
- Scroll horizontal con pyautogui: `hscroll` en Windows rueda VERTICAL sin
  avisar; la skill lo implementa siempre con pynput.
- `locateOnScreen` en cada iteración del loop: 1-2 s por llamada y exige píxeles
  casi idénticos (tema/DPI/antialiasing lo rompen); usa visión sobre la captura
  y locate solo para patrones estables, con `--region` pequeña y SOLO en primario.
- Hardcodear coordenadas de otra sesión: resolución, escala, tema, ventanas y
  nº de monitores cambian todo; decide sobre la captura actual.
- Capturar justo tras actuar sin dormir: verás el estado viejo; usa `esperar`.
- Mantener una tecla esperando auto-repetición: Windows no la considera
  pulsada de verdad; emite pulsaciones separadas.
- Dormir o hacer I/O dentro de un callback de listener: corre en el hilo del
  hook del SO y puede congelar la entrada de todo el equipo.
- Escribir sin verificar el foco: un toast de Windows 11 lo roba y el texto
  acaba en otra app (`ventanas.py foco` / `--requiere-foco`).
- Creer que `ctrl+letra` hará lo esperado: colisiona con aceleradores de menú
  (en el Notepad en español `ctrl+a` abre "Abrir"); verifica con captura y
  para seleccionar usa arrastre, `shift+flechas` o el menú contextual.
- Abrir apps/URLs/archivos con cmd en vez de `ventanas.py abrir`: se pierde
  el JSON, el `--esperar` de ventana y la portabilidad del loop.

## 7. Referencias

Lee `references/pyautogui-api.md` / `references/pynput-api.md` (firmas verificadas, dudoso
[runtime]) solo si un script falla o toca código ad-hoc que ningún CLI cubre: el flujo normal
va por los scripts. Con DOS o más monitores lee `references/monitores-multi.md` (espacio
virtual, trampa del `region=`, regla pynput, FAILSAFE y límites). Lee
`references/comandos-sistema.md` si el objetivo NO es Windows, no hay Python/pip o la tarea
cabe en comandos nativos del SO (matriz y URLs §G).

## 8. Coordenadas y DPI (marco único)

- Unidades: píxeles absolutos del ESPACIO DE PANTALLA VIRTUAL — origen (0,0)
  = vértice sup-izq del monitor **PRIMARIO**; con monitores a la
  izquierda/arriba las coordenadas NEGATIVAS son válidas. Mapa exacto:
  `monitores.py listar`; tamaños: `tamano` (primario) / `tamano --virtual`.
  Con un solo monitor coincide con el marco histórico del primario.
- Los scripts fijan `SetProcessDpiAwareness(2)` (process-per-monitor) antes de
  importar pyautogui (por sí solo solo es System-aware): capturas, coordenadas
  e inyección comparten el mismo marco físico.
- Backend (VERIFICADO en el fuente): dentro del primario, pyautogui (tween y
  PAUSE, comportamiento histórico); fuera del primario —o cualquier coord
  negativa—, pynput (`SetCursorPos` sobre la pantalla virtual garantizado por
  código; en pyautogui 0.9.54 el clamp está solo COMENTADO: conducta no
  documentada, prohibido depender). `raton.py` enruta solo; teclado y foco no
  cambian (las teclas van al foco, sin coordenadas).
- FAILSAFE: las 4 esquinas que abortan son las del PRIMARIO (§5).
