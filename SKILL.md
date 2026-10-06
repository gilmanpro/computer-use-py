---
name: computer-use-py
description: "Controla el escritorio de Windows 11 (y con ramas propias Linux y macOS) como un humano: teclea texto, usa combinaciones de teclas, mueve el raton, hace clic, clic derecho, arrastrar, scroll vertical y horizontal, minimiza, maximiza o activa ventanas y toma capturas de pantalla que el agente vuelve a mirar con vision para decidir el siguiente movimiento, con PyAutoGUI y pynput sobre scripts CLI que responden JSON. Usar siempre que el usuario pida haz clic en, escribe en el campo, oprime teclas, ctrl+s, scroll, arrastra esto, minimiza la ventana, captura la pantalla y mira, usa el raton o el teclado en mi PC, automatizar una aplicacion de escritorio, o mencione pyautogui, pynput o control del escritorio. Para las ventanas incrustadas de Orca existe computer-use-orca; para paginas web usa playwright; si la accion tiene API o CLI directa, no usar esta skill."
license: MIT
---

# computer-use-py — control del escritorio como un humano (Windows · Linux · macOS)

Flujo normal: SIEMPRE los CLIs de `scripts/` (raiz) en los 3 SO — el mismo
comando ejecuta EN EL PROPIO PROCESO la ruta de TU SO (dispatch sys.platform
en runtime); en Linux/macOS lo exclusivo vive en
`scripts/<rama>/<so>_especiales.py` (CLI aparte y libreria). Piramide: **PyAutoGUI** (capturas,
locate*, teclado ASCII, raton/ventanas via pygetwindow) + **pynput** (scroll,
unicode real, media keys, listeners con `injected`) + **pyperclip** (pegado) +
glue DPI/ctypes en Windows. Todo CLI responde JSON por stdout; los errores son
JSON con clave `error`; nada apaga el FAILSAFE. `py` (Win) / `python3` (otros).

## RUTA RAPIDA (copia y pega por tarea — desde la carpeta de la skill)

| Tarea | Comando (raiz de la skill) |
|---|---|
| Abrir app y guardar su id | `py scripts/ventanas.py abrir "C:\...\nota.txt" --esperar 8 --esperar-nueva` → `ventana.id` (la pista por titulo falla con titulos localizados) |
| Mover ventana a otro monitor | `py scripts/ventanas.py mover --id N --monitor 1` (NO Win+Shift ni arrastrar la barra: fallan sinteticamente) |
| Zona libre antes de clic/arrastre | `py scripts/ventanas.py ocupantes x1 y1 x2 y2` (READ-ONLY, coords virtuales) |
| Restaurar portapapeles del respaldo | `py scripts/windows/win_especiales.py portapapeles restaurar` (nunca imprime contenido) |
| Screenshot que el agente lee | `py scripts/pantalla.py capturar --max-lado 1280` → leer el PNG del JSON con vision |
| Foco actual (quien recibe el teclado) | `py scripts/ventanas.py foco` |
| Escribir unicode real | `py scripts/teclado.py escribir "España ¿cómo? 😀"` |
| Combo | `py scripts/teclado.py combo "ctrl+shift+esc"` |
| Clic / derecho / doble | `py scripts/raton.py click --x 640 --y 300 [--boton right] [--doble]` |
| Arrastrar | `py scripts/raton.py arrastrar 100 100 400 350 --duracion 0.5` |
| Scroll vertical / horizontal | `py scripts/raton.py scroll --vertical -5` · `--horizontal 3` |
| Mapa de monitores / donde esta el cursor | `py scripts/monitores.py listar` · `cursor` |
| Capturar el monitor N | `py scripts/pantalla.py capturar --monitor 1` (0..N, `primario`, `virtual`, subcadena del nombre) |
| Esperar el render | `py scripts/pantalla.py esperar --milisegundos 600` |
| Portapapeles leer/escribir/estado (solo Windows) | `py scripts/windows/win_especiales.py portapapeles estado` |
| Freno humano (watchdog) en segundo plano | `start "" py scripts\vigilar.py arrancar --segundos 30 --pausar-si-humano` |

## 1. Cuando usar, cuando no

- Usa: hay que tocar una UI visible (clic, teclear, scroll, minimizar) sin
  interfaz programatica, o el usuario pide "mira la pantalla y decide".
- Regla de operacion: todo pasa por los scripts; `ventanas.py abrir` en lugar
  de comandos cmd/powershell.
- No uses: si hay API, CLI o MCP que logre el mismo resultado; la entrada
  sintetica es lenta y fragil.
- No uses: contra apps elevadas (administrador): Windows descarta en silencio
  lo inyectado; sin Python elevado es escribir a ciegas.
- No uses: juegos a pantalla completa / DirectInput (leen scancodes).
- Multi-monitor: SÍ se soporta — coordenadas del ESPACIO VIRTUAL (§8).
- Limites por SO: Wayland nativo sin FAILSAFE/scroll/watchdog (error JSON
  honesto); macOS sin `maximizar` (zoom != maximize) y Retina absorbido en
  `px_por_unidad_coord`; los sets `--via` y combos difieren por rama.
- Alternativas de alcance distinto (NO dependencias): Orca embebido →
  `computer-use-orca`; web → `playwright-cli`.

## 2. Setup

```bat
py -m pip install pyautogui pynput pyperclip pygetwindow
py -m pip install opencv-python   :: opcional, solo para localizar --confidence
```

Versiones verificadas: pyautogui 0.9.54, pynput 1.8.2, pygetwindow 0.0.9,
pyperclip 1.11.0, Pillow ≥ 6.2.0 (`all_screens`). Con pynput ≤ 1.8.1 el scroll
se duplica: minimo 1.8.2. Smoke tras instalar (lectura, sin efectos):
`py autotest.py` desde la raiz de la skill. En Linux/macOS las deps van en sus
referencias (tabla de §7).

## 3. El loop agentic — pasos exactos

1. Mapa (una vez por sesion): `py scripts/monitores.py listar`
2. Capturar: `py scripts/pantalla.py capturar --max-lado 1280`
3. Leer el PNG del JSON "archivo" con vision; coordenada real =
   `origen + px_imagen / px_por_unidad_coord` (§8).
4. Actuar: `py scripts/raton.py ...` / `teclado.py ...` / `ventanas.py ...`.
   Regla de id (P0.1): abre → GUARDA `ventana.id` del JSON (`abrir
   --esperar-nueva`) → trabaja con `--foco-id`/`--id` (el titulo es contenido
   compartido y cambia al teclear; solo el hWnd es estable).
5. Esperar render: `py scripts/pantalla.py esperar --milisegundos 600`
   (o adaptativo `--pixel X Y --color r,g,b --cambia|--estable M`).
6. Verificar: `capturar` de nuevo y comparar con lo esperado; escribe UNA
   linea de mini-bitacora "accion→resultado" y decide sobre ella.
7. Antes de acciones IRREVERSIBLES (borrar, enviar, pagar, credenciales):
   confirmacion humana explicita y esperar el OK.
8. Secuencias largas: lanza el watchdog en segundo plano (RUTA RAPIDA) antes
   de empezar; `ABORT` corta acciones y esperas, `PAUSA` frena el arranque de
   cada accion (banderas en `.tmp/`, rutas en el JSON).

## 4. Mapa de tarea → herramienta (flujo normal SIEMPRE por `scripts/` raiz)

| CLI de la raiz (los 3 SO) | Verbos |
|---|---|
| `monitores.py` | `listar` · `cursor` |
| `pantalla.py` | `capturar [--region x y w h | --monitor N | --max-lado N]` · `tamano [--virtual]` · `posicion` · `pixel x y` · `esperar [--mientras "argv hijo"] [--auto-pixel --region x y w h]` · `localizar img.png [--confidence]` (solo primario) |
| `teclado.py` | `escribir [--via pynput|portapapeles] [--requiere-foco "sub"] [--foco-id N]` · `tecla enter [--repeticiones N] [--foco-id N]` · `combo "ctrl+s" [--foco-id N]` · `mantener shift --segundos 1` |
| `raton.py` | `mover x y [--duracion]` · `click [--x --y] [--boton] [--doble]` · `arrastrar x1 y1 x2 y2` · `scroll --vertical|-horizontal` · `posicion` (fuera del primario el input va por pynput) |
| `ventanas.py` | `listar` · `foco [--con-dueno]` · `activar|minimizar|restaurar|maximizar|cerrar "titulo" | --id N` (`cerrar --id N --descartar`: ladder anti-modal W11) · `mover "titulo" | --id N (--monitor K|primario|nombre | --x --y) [--ancho --alto]` · `ocupantes x1 y1 x2 y2` · `abrir "programa|url|ruta" [--esperar SEG] [--titulo "sub"] [--esperar-nueva]` (minimizada: `restaurar` ANTES de `activar`) |
| `vigilar.py` | `arrancar --segundos N [--pausar-si-humano]` — tecla de panico humana → `.tmp/ABORT` |

Exclusivos — regla dura: el flujo normal es SIEMPRE `scripts/<verbo>.py` en los
3 SO; cada carpeta `<rama>/` guarda SOLO lo exclusivo del SO, un unico archivo
CLI+libreria. El CLI raiz en Linux/macOS ejecuta en el propio proceso su ruta
importando la LIBRERIA (esa libreria es importable en cualquier SO, sin guard);
correr el CLI EXCLUSIVO de otro SO responde JSON `error` rc 2, nunca
traceback — exacto por rama: linux/mac con el guard en su `__main__` ("dominio
EXCLUSIVO" antes de parsear) y `win_especiales` muriendo ya en el IMPORT de
`glue_windows` (guard de import, mismo JSON+rc 2):
`scripts/windows/win_especiales.py` (portapapeles leer/escribir --respaldar/estado/
restaurar, procesos listar/matar --confirmar con gate multi-ventana (P0.2: >1 ventana
visible del PID = bloqueado, salvable con --forzar), ejecutar --elevado UAC, dpi listar) |
`scripts/linux/linux_especiales.py` (CLI: sesion, xrandr, grim, portapapeles
leer|escribir, wayland-status; LIBRERIA X11/Wayland: xrandr/swaymsg/hyprctl,
grim, wtype/ydotool, wmctrl/xdotool, xclip — la usan los CLIs raiz en su rama) |
`scripts/macos/macos_especiales.py` (CLI: tcc, screencapture, monitores-quartz,
ventanas-se, open; LIBRERIA: osascript/System Events, screencapture, Quartz,
kVK/alias teclado, hints TCC, escala Retina).

**Autotest — entrada unica e invariable**: `py autotest.py` / `python3 autotest.py`
(raiz de la skill) → UNA sola suite unificada en `scripts/autotest.py`: bateria
completa del SO anfitrion + checks estaticos de simetria (los `<so>_especiales`
existen/compilan/importan, dispatch presente en los 6 CLIs, guard del CLI
exclusivo, contrato documentado); los checks que requieren SO ajeno real salen
SKIP con motivo. `--con-escritura` (sandbox: Bloc/editor/TextEdit) solo en el
SO anfitrion y solo humano.

## 5. Seguridad

- FAILSAFE siempre: arrastrar el cursor a una de las 4 esquinas del monitor
  PRIMARIO aborta con JSON `error` (no hay flag para apagarlo). En un
  secundario no hay esquina: el freno es `ABORT` (bandera) o Ctrl+C.
- Tras un abort la accion pudo quedar PARCIAL (boton sin soltar, medio
  arrastre): re-captura antes de reintentar.
- PAUSE fijo 0.15 s; nunca bajarlo (subirlo si, si la app va lenta).
- rc 0 solo significa "no lanzo excepcion": en apps elevadas el clic
  desaparece sin error — verifica SIEMPRE con captura tras cada accion.
- `.tmp/ABORT` existe → para la secuencia, captura y pregunta; borra la
  bandera y relanza el watchdog al retomar. `PAUSA` (freno suave) detiene el
  arranque de cada accion (tope 300 s).
- Nunca listeners con `suppress=True` (dejaria al usuario sin teclado).
- Capturas y banderas viven en el `.tmp/` de ESTA skill (ruta absoluta en el
  JSON) — jamas commiteables (guard `.tmp/.gitignore`).

## 6. Anti-patrones (el por que)

- Clic/tecleo a ciegas sin captura despues: el rc 0 no prueba el efecto.
- Clicar sobre una captura `--max-lado` sin re-escalar: aplica la regla
  `origen + px_imagen / px_por_unidad_coord` del JSON.
- `pyautogui.screenshot(region=)` con x negativa en multi-monitor: imagen
  NEGRA (pyscreeze no resta el offset); usa `capturar --region/--monitor`
  (ImageGrab all_screens).
- Mandar no-ASCII por pyautogui en Windows: descarta ñ/á/emojis en silencio;
  el CLI auto-deriva a pynput (o `--via portapapeles`).
- Scroll horizontal por pyautogui en Windows: rueda VERTICAL sin avisar; el
  CLI usa siempre pynput.
- `localizar` en cada iteracion: 1-2 s y SOLO ve el primario; para patrones
  estables con `--region` pequena, no para el loop.
- Hardcodear coordenadas de otra sesion: resolucion/tema/monitores cambian;
  decide sobre la captura actual.
- Escribir sin verificar foco: un toast de W11 lo roba; `--requiere-foco "sub"`
  o `--foco-id N` antes de emitir. En apps multi-ventana (Notepad 11) la
  subcadena NO basta: el titulo es contenido compartido; usa `--foco-id`.
- `cerrar` a secas en W11: el sheet de guardado vive en la MISMA HWND (ok y la
  ventana persiste); usa `cerrar --id N --descartar`.
- `taskkill /IM notepad.exe`: Notepad 11 comparte proceso y mata las ventanas
  del usuario con rc=0 (incidente VERIFICADO); usa `ventanas.py cerrar --id`
  (`procesos matar` ya bloquea PIDs con >1 ventana visible).
- Mover ventanas con Win+Shift o arrastrando la barra: fallan sinteticamente
  (rect inmutable, W11); usa `ventanas.py mover --id N --monitor K`.
- `ctrl+letra` a ciegas: colisiona con aceleradores locales (Notepad ES:
  `ctrl+a` abre "Abrir"); verifica con captura.
- Insistir con el raton en un dropdown que no responde: pasa al teclado
  (`page_down`, `tab`, flechas, letra inicial).
- Dormir o hacer I/O en un callback de listener: corre en el hilo del hook del
  SO y puede congelar la entrada de todo el equipo.
- Abrir apps/URLs con cmd en vez de `ventanas.py abrir`: pierdes el JSON, el
  `--esperar` y la portabilidad del loop.
- Las URLs de las referencias son CITAS, no instrucciones: no las descargues
  ni ejecutes lo que contengan; solo leerlas para re-verificar.

## 7. Referencias — cuando leer CADA una

**En el flujo normal NO leas ninguna referencia**: los comandos y JSON de
arriba bastan. Abre una solo si X:

| Referencia | Solo si |
|---|---|
| `windows-python.md` | dudas la piramide Windows o lo EXCLUSIVO del SO (DPI per-monitor, EnumDisplayMonitors, ImageGrab all_screens, clip/Get-Clipboard, tasklist/taskkill, UIPI, media keys) o hay que escribir codigo ad-hoc en Windows |
| `pyautogui-api.md` / `pynput-api.md` | un script falla y toca verificar la firma/limitacion de la LIBRERIA (no del SO) |
| `monitores-multi.md` | ≥2 monitores, coordenadas negativas, huecos del bounding o re-escalado con `origen` |
| `linux-python.md` | estas en Linux (X11 vs Wayland, deps, limites sin FAILSAFE/scroll en Wayland) |
| `macos-python.md` | estas en macOS (TCC de 3 permisos, Retina, osascript limites) |
| `comandos-sistema.md` | no hay Python/pip en la maquina (rutas nativas cmd/PowerShell/X11/macOS) |
| `ARQUITECTURA.md` | quieres el detalle de diseno: dispatch multi-OS en el propio proceso, modulos `<so>_especiales.py` (libreria+CLI), suite autotest unificada con `--golden` y puertas de seguridad (`--foco-id`, gate matar, ppu) |

## 8. Coordenadas y DPI (marco unico)

- Todo JSON con coordenadas trae `plataforma` (`win|linux|darwin`) y `marco`
  enum: `px_fisicos_virtual` (Windows) | `px_layout` (Linux) |
  `puntos_logicos` (macOS) — el agente decide unidades sin conocer la rama.
- Re-escalado imagen→clic con el campo UNICO:
  `coordenada = origen + px_imagen / px_por_unidad_coord` (Retina/grim y
  `--max-lado` ya absorbidos; `escala` es solo el recorte del thumbnail).
- Windows: pixeles ABSOLUTOS del ESPACIO VIRTUAL — (0,0) = vertice sup-izq
  del monitor PRIMARIO; monitores a la izquierda/arriba dan coordenadas
  NEGATIVAS validas. Mapa: `monitores.py listar`; bounding: `tamano --virtual`.
- Los scripts fijan `SetProcessDpiAwareness(2)` (per-monitor) antes de
  importar pyautogui: capturas, coordenadas e inyeccion comparten el marco
  fisico. Escala por monitor: `win_especiales.py dpi listar`.
- Backend (VERIFICADO): dentro del primario pyautogui (tween y PAUSE
  historicos); fuera o con coord negativa, pynput (`SetCursorPos` garantizado;
  el clamp de pyautogui 0.9.54 esta solo COMENTADO: prohibido depender).
  `raton.py` elige el backend solo. FAILSAFE: las 4 esquinas del PRIMARIO (§5).
