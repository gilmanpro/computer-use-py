# macOS — control del escritorio desde Python (referencia computer-use-py)

> Investigación 05/10/2026, 10 fetches (7 con contenido): man pages Apple vía
> mirror keith.github.io/xcode-man-pages (screencapture/osascript/open), guía
> Apple "Mac Automation Scripting Guide" (archive, cap. Automating the UI),
> docs pynput y FUENTE LOCAL LEÍDA: pynput 1.8.2 (`mouse/_darwin.py`,
> `keyboard/_darwin.py`, `mouse/_base.py`, `_util/darwin.py`) y pyautogui
> 0.9.54 `_pyautogui_osx.py` (mismo árbol que publica PyPI). **VERIFICADO** =
> cita de doc/fuente leída · **[runtime]** = probar en un Mac real (se indica
> cómo) · **[3p]** = tercero no auditado. Nada se ejecutó aquí (Windows).

## Contrato central: TODO se ejecuta sobre Python

La superficie del agente es **Python + JSON idéntico al dominio Windows**
(`scripts/macos/`). Cuando un script llama por subprocess a `screencapture`,
`osascript` u `open`, sigue siendo código Python quien las invoca: el agente
solo corre `python3 scripts/macos/X.py <verbo>` y lee JSON.

## Índice

1 Pirámide · 2 Coordenadas/RETINA · 3 TCC · 4 screencapture · 5 Ratón ·
6 Teclado · 7 osascript/open · 8 Multi-monitor · 9 SSH · 10 Tabla ·
11 Setup · 12 VERIFICADO vs INCERTO

## 1. Pirámide de rutas

1. **pynput 1.8.2** — Controller ratón/teclado y Listener funcionan en macOS
   vía Quartz: todo emite `CGEventCreate*Event` + `CGEventPost(kCGHIDEventTap)`
   y el Listener crea un tap en `kCGSessionEventTap` (VERIFICADO fuente
   `_darwin.py`/`_util/darwin.py:272-279`). El MONITOREO de teclado exige
   whitelist de Accesibilidad/root (VERIFICADO limitations.html; ratón NO
   afectado); el estado se lee con `Listener.IS_TRUSTED` (VERIFICADO).
2. **pyobjc-framework-Quartz/AppKit** — CoreGraphics directo:
   `CGEventCreateMouseEvent` con coords ABSOLUTAS del espacio global top-left,
   `CGEventPost`, `CGEventSetIntegerValueField(kCGMouseEventClickState)`,
   `CGEventCreateScrollWheelEvent`, `CGDisplayBounds`/`CGMainDisplayID`/
   `CGDisplayPixelsHigh` (VERIFICADO uso en fuentes `_darwin.py` y
   `_pyautogui_osx.py:301,431,446-448`).
3. **osascript + System Events + CLI nativas** — sin instalar nada:
   `application process` = app corriendo, `set frontmost to true`, `click` de
   ELEMENTOS y `click menu item` (VERIFICADO guía Apple); `keystroke`/
   `key code`/acciones AX **[runtime]** (diccionario System Events no
   fetcheado). Capturas: `screencapture`; lanzar: `open`.
   **Límite real: AppleScript NO tiene clic absoluto en (x,y)** — `click`
   exige UI element (VERIFICADO: la guía solo documenta click sobre
   botones/items). El ratón en coordenadas va por pynput/Quartz.

## 2. Coordenadas, RETINA y origen (la regla)

- Marco: **PUNTOS LÓGICOS del espacio global**, (0,0) = vértice sup-izq del
  display PRINCIPAL, +y abajo. VERIFICADO fuente: pynput revierte el y de
  Cocoa (`CGDisplayPixelsHigh(0) - NSEvent.mouseLocation().y`,
  `mouse/_darwin.py:73-76`); pyautogui-osx hace el mismo flip (:297-300).
- **RETINA**: `screencapture` produce ~2× píxeles por punto en paneles retina
  **[runtime por panel]**; `-r` desactiva la metadata DPI del fichero
  (VERIFICADO man). `CGDisplayBounds` da PUNTOS.
- **REGLA — el JSON de TODA captura trae `origen`, `px_por_unidad_coord`,
  `escala`, `escala_retina`, `marco` y `regla`**: el campo ÚNICO que necesita
  el agente es `px_por_unidad_coord = escala × escala_retina` (factor TOTAL
  imagen→punto: Retina y --max-lado ya absorbidos) →
  `coord_lógica = origen + coord_imagen / px_por_unidad_coord`; NO multipliques
  `escala` y `escala_retina` a mano (quedan como desglose). `escala` = solo el
  recorte --max-lado. Los CLICS van SIEMPRE en puntos lógicos, nunca en píxeles
  de la imagen. La escala Retina se mide en cada captura comparando
  `CGDisplayBounds` (puntos) vs tamaño PIL del PNG; si la vía `-D` sin mapa no
  permite medirla, `px_por_unidad_coord` sale `null` (verifica con una captura
  de prueba [runtime]).
- macOS no tiene API DPI-equivalente de Windows (no hay `SetProcessDpiAwareness`):
  el problema análogo es Retina, resuelto por la regla anterior.

## 3. TCC: los 3 permisos (crítico)

- **Accesibilidad** (input/escucha): VERIFICADO guía Apple: "accessibility
  control of apps is disabled... the user must manually enable it on an
  app-by-app basis" (prompt y error documentados). VERIFICADO limitations.html
  pynput: tras Mojave puede exigir blanquear también el terminal. TCC
  identifica al **binario firmante** (`python3` de Homebrew/Xcode pide una
  vez; venv sobre el mismo binario hereda **[runtime]**).
- **Grabación de pantalla**: sin ella, `screencapture` captura el escritorio
  sin el contenido de ventanas ajenas (negro) **[runtime: no está en el man;
  verificar capturando una ventana de Safari y midiendo píxeles]**.
- **Automatización**: osascript→System Events lanza prompt; denegado →
  err **-1743** [runtime: número comunitario, el man no lista errores].
  Reset: `tccutil reset AppleEvents`.
- **Fallo silencioso típico**: sin Accesibilidad la emisión CGEvent puede no
  llegar sin excepción (mismo principio que las apps elevadas de Windows):
  SIEMPRE re-verificar con captura. `vigilar.py` reporta `is_trusted`.

## 4. Capturas: `screencapture` (VERIFICADO man)

```
screencapture -x out.png                 # -x sin sonido
screencapture -x -R x,y,w,h reg.png      # -R rectángulo (puntos lógicos [runtime])
screencapture -x -D n mon.png            # -D <display>: "1 is main, 2 secondary, etc"
screencapture -l <windowid> -o v.png     # -l ventana; -o sin sombra (modo ventana)
screencapture -r -t png out.png          # -r sin metadata DPI; -t formato (default png)
screencapture -C ...                     # -C incluye cursor (solo no interactivo)
```
- "files: … **1 file per screen**" (VERIFICADO man): sin flags no hay un PNG
  único multi-monitor → `--monitor virtual` captura por monitor (`-D`/`-R`)
  y compone el mosaico con PIL.
- El orden `-D n` vs `CGGetActiveDisplayList` es **[runtime]**: los scripts
  priorizan `-R` con los bounds leídos por Quartz.
- `-R` con x/y negativos: **[runtime]** (el man no lo dice); los rects reales
  se leen de CGDisplayBounds y el JSON siempre expone `origen`.
- windowid para `-l`: requeriría `CGWindowListCopyWindowInfo` — fuera de fase.

## 5. Ratón: pynput → CGEvent (VERIFICADO fuente)

- `position = (x,y)`: `CGEventCreateMouseEvent(None, kCGEventMouseMoved, pos)`
  + Post; **con botón presionado el mismo setter emite `…MouseDragged`**
  (`_darwin.py:78-88`) → press→position→release es el drag nativo.
- Botones darwin: **solo left/middle/right** (`_darwin.py:55-61`; no x1/x2).
- **Doble clic**: docs mouse.html VERIFICADO "Double click; this is different
  from pressing and releasing twice on macOS — click(Button.left, 2)"; fuente:
  `click()` abre `with self` (`_base.py:112-125`) e incrementa
  `kCGMouseEventClickState` por ciclo (`_darwin.py:105-133`). Ruta pyobjc
  manual: setear ClickState 1..2 en down/up **[runtime: replicar pynput y
  verificar en Finder]**.
- **Scroll**: `scroll(dx,dy)` → `CGEventCreateScrollWheelEvent(None,
  kCGScrollEventUnitPixel, 2, dy*10, dx*10)` (VERIFICADO fuente). Convención
  skill: dy>0=sube, dx>0=derecha — converge con el ejemplo del listener de
  docs (`dy<0`=down) y con el mapeo positivo→positivo de `_pyautogui_osx.py`.
  El "scroll natural" puede invertir la percepción por app **[runtime]**.
  Consejo Apple (citado por pyautogui desde su QuartzEventServicesRef):
  valores ±10 por evento, grandes = resultados impredecibles.
- **FAILSAFE pyautogui NO aplica** (no se usa pyautogui en mac). Equivalente:
  vigilar.py = listener pynput con filtro `injected` que crea `.tmp/ABORT`
  (VERIFICADO fuente: callbacks darwin reciben `injected`), y raton.py emula
  la guarda de las 4 esquinas del principal **[runtime: emulación de la skill,
  no API del SO]**.

## 6. Teclado

- **kVK_ VERIFICADO fuente `_darwin.py:154-211`** (= HIToolbox/Events.h):
  enter=36, tab=48, space=49, backspace=51, esc=53, cmd_l=55, cmd_r=54,
  shift=56, caps_lock=57, option/alt=58, ctrl=59, fwd-delete=117, home=115,
  end=119, pgup=116, pgdn=121, flechas 123/124/125/126 (left/right/down/up),
  F1=122 F2=120 F3=99 F4=118 F5=96 F6=97 F7=98 F8=100 F9=101 F10=109 F11=103
  F12=111, F13-16=105/107/113/106, F17-20=64/79/80/90.
- **Multimedia**: los códigos "100-103/111" del plan de tarea NO son media:
  son F8/F9/F11/F12 (posición física de las teclas con icono). La media real
  es `NSSystemDefined` subtype 8 con `NX_KEYTYPE` (VERIFICADO fuente:
  SOUND_UP=0, SOUND_DOWN=1, MUTE=7, PLAY=16, NEXT=17, PREVIOUS=18, EJECT=14;
  el propio fuente comenta "undocumented, but still widely known"). Usar
  `Key.media_volume_up/down/mute/play_pause/next/previous/eject`.
- En darwin no existen en `Key`: print_screen, pause, menu, insert, num_lock,
  scroll_lock, media_stop (VERIFICADO comparando enums `_darwin.py` vs
  `_win32.py`). **Unicode**: `CGEventKeyboardSetUnicodeString` cuando el char
  no tiene vk (VERIFICADO fuente `_darwin.py:147-148`) → ñ/acentos/emojis se
  tipean de verdad en apps normales [runtime en apps exóticas].
- `osascript keystroke/key code` y el formato `using {command down}`
  **[runtime]**. `pbcopy`/`pbpaste` (BSD preinstalado) **[runtime: página no
  fetcheada]**; `escribir --via portapapeles` los usa para no pasar secretos
  por argv (argv es visible en `ps`).

## 7. osascript y `open`

- VERIFICADO man osascript: `-e` múltiples construyen el script; "Any
  arguments following the script will be passed as a list of strings to the
  direct parameter of the run handler" (`on run argv`/`item 1 of argv`).
  REGLA ANTI-INYECCIÓN: el texto del usuario viaja SOLO por argv — nunca
  interpuesto en el código AppleScript.
- VERIFICADO guía Apple: habilitación Accesibilidad por app; `tell
  application "System Events"`; `process` = app corriendo; Processes Suite;
  `click` de botón/elemento; `set frontmost to true`; `click menu item`
  (requiere frontmost primero en el ejemplo).
- **[runtime]**: `name/position/size/minimized` de ventanas System Events y
  acciones "AXMinimize"/"AXRaise" (capítulo fetcheado no los lista; cotejar
  el diccionario en el Mac). "maximizar" no existe en macOS (botón verde =
  zoom).
- VERIFICADO man open: abre archivo/directorio/URL "como un doble clic";
  `-a application`, `-b bundle-id`, `--args` (argv directo a la app, open no
  lo interpreta), `-n`, `-W`, `-g`, `-e/-t`; `open http://…` → navegador por
  defecto. Lanzado con `start_new_session=True` (POSIX) para desvincularlo
  del proceso del agente.
- CONTRATO multi-rama (SPEC P0-2/P1-2): `abrir` emite `tipo` en el enum
  canónico `{url, programa, archivo}` — la clasificación interna mac por
  `open -a` se mapea `app → programa` y se conserva como extensión `tipo_mac`.
  El objeto `ventana` de `listar/foco/abrir` usa la forma canónica anidada
  `rect`+`estado`, con `maximizada: null` (macOS no maximiza: zoom) e `id:
  null` (no hay hWnd; la identidad del `--esperar` es el par app+titulo).
  Todo JSON lleva `plataforma: "darwin"` y `marco: "puntos_logicos"`.

## 8. Multi-monitor

- `CGGetActiveDisplayList` + `CGDisplayBounds`: rects en puntos del espacio
  global; principal por `CGMainDisplayID`/`CGDisplayIsMain` (VERIFICADO el
  patrón de uso en fuente pynput/pyautogui-osx).
- Display a la IZQUIERDA/ARRIBA del principal → orígenes NEGATIVOS como en
  Windows **[runtime: la doc de CGDisplayBounds exige JS y no se pudo leer;
  verificar con `monitores.py listar` — los scripts calculan el bounding de
  los rects leídos y NUNCA asumen el signo]**.
- Orden de las listas no garantizado estable entre sesiones → volver a
  listar tras reconectar (igual que Windows).
- Sin API pública de "área útil" (menú/Dock): `work = bounds` + nota
  **[runtime]**. Nombres: `NSScreen.localizedName` vía `NSScreenNumber`
  **[runtime]**; fallback `system_profiler SPDisplaysDataType -json`
  (parse tolerante **[runtime]**) y `osascript … desktop picture bounds`
  (solo principal) **[runtime]**.

## 9. Sesión SSH / headless

- VERIFICADO man: para capturar por SSH hay que lanzar en la jerarquía mach
  de loginwindow: `sudo launchctl bsexec <pid_loginwindow> screencapture …`
  (SECURITY CONSIDERATIONS del propio man).
- Sin sesión Aqua del usuario no hay escritorio que controlar: input CGEvent
  y capturas no aplican **[runtime]**.

## 10. Tabla tarea → ruta

| Tarea | Primaria | Respaldo | Estado |
|---|---|---|---|
| Captura (pantalla/monitor/región) | screencapture -x -R/-D | mosaico PIL | man VERIFICADO; unidades/negativos [runtime] |
| Mapa monitores | Quartz CGGetActiveDisplayList/Bounds | system_profiler, osascript | fuente VERIFICADO; signos [runtime] |
| Mover cursor | pynput `position=` | pyobjc MouseMoved; cliclick[3p] último | fuente VERIFICADO |
| Clic simple/derecho | pynput `click(Button,n)` | pyobjc clickState; cliclick[3p] | docs+fuente VERIFICADO |
| Doble clic | pynput `click(Button,2)` (clickState) | pyobjc manual | docs VERIFICADO ("different on macOS") |
| Arrastrar | pynput press→position(Dragged)→release | pyobjc MouseDragged | fuente VERIFICADO |
| Scroll V/H | pynput `scroll(dx,dy)` | pyobjc ScrollWheelEvent | fuente VERIFICADO; signo por app [runtime] |
| Tipear (ñ/emoji) | pynput tap() (SetUnicodeString) | osascript keystroke argv; pbcopy+cmd+v | fuente VERIFICADO; keystroke [runtime] |
| Teclas nombradas | pynput Key (tabla §6) | osascript key code vk | fuente VERIFICADO |
| Media keys | pynput Key.media_* (SystemDefined) | — | fuente VERIFICADO; hardware [runtime] |
| Ventanas listar/foco/activar/cerrar | osascript System Events argv | — | guía VERIFICADO (process/frontmost/click); position/size [runtime] |
| Minimizar/restaurar | perform "AXMinimize" / AXMinimized=false | Dock/cmd+M | [runtime] |
| Lanzar app/URL/archivo | open -a App / open ruta-o-URL | — | man VERIFICADO |
| Freno humano | pynput Listener + injected → .tmp/ABORT (dura) y .tmp/PAUSA (suave: pausa el arranque de acciones) | Ctrl+C | fuente+docs VERIFICADO; TCC [runtime] |

## 11. Setup y versiones

```bash
pip3 install pynput==1.8.2              # entrada (TCC Accesibilidad)
pip3 install pyobjc-framework-Quartz    # PyPI 12.2.2, requires_python>=3.10 (VERIFICADO PyPI)
pip3 install pillow                     # composición virtual + escala/pixel
pip3 install opencv-python              # opcional: pantalla.py localizar
```
pynput mínimo 1.8.2 también en mac (mismo umbral que Windows). La skill NO
usa pyautogui en macOS aunque su backend `_pyautogui_osx.py` exista (fuente
leída): la superficie se fija en pynput+Quartz+CLI para que el JSON sea
idéntico al dominio Windows.

## 12. VERIFICADO vs INCERTO

**VERIFICADO (URLs/fuentes):**
- Man pages (mirror del man de Apple; flags y textos citados verificados en
  cada §): screencapture → https://keith.github.io/xcode-man-pages/screencapture.1.html
  · osascript → https://keith.github.io/xcode-man-pages/osascript.1.html
  · open → https://keith.github.io/xcode-man-pages/open.1.html
- Guía Apple "Automating the User Interface" (archive): Accesibilidad off por
  defecto y alta por app (prompt/error), System Events, clase `process`,
  Processes Suite, click de elemento/menu item, set frontmost →
  https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/AutomatetheUserInterface.html
- Docs pynput (https://pynput.readthedocs.io/en/latest/): limitations.html
  (whitelist/root/terminal para monitor de teclado; ratón exento; IS_TRUSTED),
  mouse.html (doble clic macOS click(Button.left,2); listener dy<0=down;
  darwin_intercept/suppress), keyboard.html (press/tap/pressed/type,
  InvalidCharacter).
- Fuentes leídas (pynput 1.8.2 y pyautogui 0.9.54, árboles de PyPI instalados
  localmente): enum Key darwin + vks, NX_KEYTYPE media, botones 0/1/2, flip
  CGDisplayPixelsHigh, kCGMouseEventClickState, Dragged en drag,
  kCGHIDEventTap, CGEventKeyboardSetUnicodeString, AXIsProcessTrusted,
  kCGSessionEventTap, DARWIN_CATCH_UP_TIME=0.01 (`__init__.py:567`).
- pyobjc-framework-Quartz 12.2.2, requires_python >=3.10 →
  https://pypi.org/project/pyobjc-framework-Quartz/ (la descarga JSON de ese
  fetch era un scratch temporal de la fase de investigación; ya no se
  conserva en `.tmp/`).

**INCERTO/[runtime] (procedimiento en cada §):** unidades/negativos de -R;
orden -D n; 2×/3× retina por panel; Screen Recording negro; números -1743/
-25211; keystroke/key code/using; position/size/minimized/AXMinimize/
AXRaise/"AXMinimized" de System Events (el doc moderno de Apple requiere JS;
la API .md no se pudo leer con el presupuesto de fetches); scroll natural
por app; teclas F como media vía key code; negativos en CGDisplayBounds;
NSScreen.localizedName; pbcopy/pbpaste; input sin sesión Aqua; cliclick [3p]
(nunca auditado por la skill).
