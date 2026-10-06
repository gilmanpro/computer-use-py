# Pantalla virtual y multi-monitor en Windows 11 — API verificada (referencia computer-use-py)

> Derivado de la SPEC multi-monitor de la fase H (investigación 05/10/2026:
> Microsoft Learn + Pillow + fuentes locales de pyautogui 0.9.54, pyscreeze,
> pynput 1.8.2 y pygetwindow 0.0.9). Solo afirmaciones VERIFICADAS (doc
> oficial o línea de código leída); lo marcado [runtime] debe confirmarse
> ejecutando en la máquina de destino. Máquina de referencia de la spec:
> Win11, primario 1920x1200 + secundario a la IZQUIERDA ⇒ virtual
> x ∈ [-1920, 1919]. Leer este archivo al trabajar con dos o más monitores;
> el flujo normal usa los scripts (`monitores.py`, `pantalla.py`,
> `raton.py`, `ventanas.py`).

## Índice

- 1. Espacio virtual y coordenadas negativas
- 2. Cómo listar monitores (ctypes y PowerShell)
- 3. Capturas: ImageGrab all_screens y la trampa de `region=`
- 4. Ratón: pynput garantizado vs pyautogui no documentado
- 5. Teclado y foco (igual en todos los monitores)
- 6. FAILSAFE: esquinas del primario y freno en el secundario
- 7. Ventanas en el espacio virtual y moverlas de monitor
- 8. DPI: qué está verificado y qué queda pendiente
- 9. Tabla tarea → comando (multi-monitor)
- 10. Límites y riesgos
- 11. Lecciones runtime verificadas (05/10/2026, 3 monitores)

## 1. Espacio virtual y coordenadas negativas

- El bounding de TODOS los monitores se lee con `GetSystemMetrics`:
  `SM_XVIRTUALSCREEN=76`, `SM_YVIRTUALSCREEN=77` (origen),
  `SM_CXVIRTUALSCREEN=78`, `SM_CYVIRTUALSCREEN=79` (tamaño) y
  `SM_CMONITORS=80`; `SM_CXSCREEN/SM_CYSCREEN` (0/1) son SOLO del primario.
  "all dimensions retrieved by GetSystemMetrics are in pixels".
  https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getsystemmetrics
- El origen lógico (0,0) de la pantalla virtual es el vértice
  superior-izquierdo del monitor PRIMARIO; con un monitor a la izquierda,
  el virtual arranca en x = −1920 (en la máquina de la spec). VERIFICADO.
- VERIFICADO (verbatim de la doc de `MONITORINFO`): "rcMonitor ... expressed
  in virtual-screen coordinates. Note that if the monitor is not the primary
  display monitor, some of the rectangle's coordinates may be negative
  values" — igual para `rcWork`. Único `dwFlags` definido:
  `MONITORINFOF_PRIMARY` (=1).
  https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-monitorinfo
- Marco de la skill: las coordenadas son píxeles absolutos del ESPACIO
  VIRTUAL. En un equipo de un solo monitor coincide con el marco histórico
  del primario (retrocompatible). Mapa exacto: `py scripts/monitores.py listar`.

## 2. Cómo listar monitores (ctypes y PowerShell)

- `EnumDisplayMonitors(hdc, lprcClip, lpfnEnum, dwData)` con NULL/NULL
  "Enumerates all display monitors"; el clip usa coordenadas de pantalla
  virtual.
  https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumdisplaymonitors
- `GetMonitorInfo(hMonitor, lpmi)`: hay que fijar `cbSize` ANTES de la
  llamada; usar `GetMonitorInfoW` (Unicode) para poblar `szDevice`
  (nombre `\\.\DISPLAY1`). `MONITORINFOEXW` = `MONITORINFO {cbSize,
  rcMonitor, rcWork, dwFlags}` + `WCHAR szDevice[CCHDEVICENAME]` (=32).
  https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getmonitorinfoa
  https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-monitorinfoexw
- Implementado en `scripts/glue_windows.py` (`monitores()`, `tamano_virtual()`,
  `_monitor_contiene(x, y)`, `dentro_de_virtual(x, y)`) con ctypes puro y el
  DPI per-monitor fijado ANTES de medir; la CLI es `scripts/monitores.py`
  (`listar`, `cursor` — el cursor se lee con `GetCursorPos`, coordenadas
  virtuales).
- Atajo de diagnóstico sin Python:
  `powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Screen]::AllScreens | Select-Object DeviceName, Primary, Bounds, WorkingArea | Format-List"`
  ("Gets an array of all displays on the system").
  https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms.screen.allscreens
  OJO: la DPI-awareness del host powershell.exe no está verificada ⇒ Bounds
  pueden venir escalados; la fuente de verdad del marco es `monitores.py`.
  [runtime]

## 3. Capturas: ImageGrab all_screens y la trampa de `region=`

- `PIL.ImageGrab.grab(bbox=None, include_layered_windows=False,
  all_screens=False, xdisplay=None, window=None, scale_down=False)`;
  `all_screens`: "Capture all monitors. Windows OS only. Added in version
  6.2.0" ⇒ mínimo Pillow 6.2.0 (la máquina de la spec tiene 12.2.0). En
  Windows devuelve RGB. Sin `bbox`, con `all_screens=True` devuelve el
  bounding virtual completo.
  https://pillow.readthedocs.io/en/stable/reference/ImageGrab.html
- VERIFICADO (doc + código `PIL\ImageGrab.py:90-112`): "On Windows, the
  top-left point may be negative if `all_screens=True` is used" — el `bbox`
  usa coordenadas VIRTUALES y la implementación descuenta el offset
  internamente (`im.crop((left-x0, top-y0, right-x0, bottom-y0))`). Recorte
  de un monitor: `ImageGrab.grab(bbox=(izq, top, der, bot), all_screens=True)`.
- TRAMPA VERIFICADA (código): `pyautogui.screenshot` es re-export directo de
  pyscreeze (`pyautogui/__init__.py:181`; bind Windows a `_screenshot_win32`,
  `pyscreeze/__init__.py:774`), que hace `ImageGrab.grab(all_screens=...)` y
  luego `im.crop((x, y, x+w, y+h))` **sin restar el offset virtual** (:538-542).
  Con `region` de x<0: (a) `allScreens=False` ⇒ crop fuera del primario ⇒
  PIL rellena 0 ⇒ imagen NEGRA sin excepción; (b) `allScreens=True` ⇒ sigue
  mal (el crop no se desplaza): monitor equivocado o negro. ⇒ Prohibido
  `pyautogui.screenshot(region=)` en coordenadas virtuales: la skill captura
  monitores/región SIEMPRE con `ImageGrab.grab(bbox=..., all_screens=True)`
  (`pantalla.py capturar --monitor|--region`).
- `pantalla.py capturar --max-lado N`: thumbnail LANCZOS ANTES de guardar;
  el JSON trae `origen` [x, y] (esquina sup-izq de la captura, coords
  virtuales), `fisico`, `escala` (solo el recorte --max-lado),
  `px_por_unidad_coord` (factor TOTAL imagen→coordenada) y la `regla`:
  `coord_virtual = origen + coord_imagen / px_por_unidad_coord` — sin
  re-escalar, los clics salen desplazados. Rendimiento de `all_screens` en
  3840x1200: no publicado [runtime].
- `localizar` (locateOnScreen de pyscreeze) captura solo el primario
  internamente: sigue siendo primario-only (documentado en el JSON de la
  skill). Buscar en un secundario: capturar con ImageGrab y buscar sobre la
  imagen propia [runtime].

## 4. Ratón: pynput garantizado vs pyautogui no documentado

- pynput (VERIFICADO en `mouse/_win32.py` instalado 1.8.2): `_position_set`
  = `int(x), int(y) → SetCursorPos(*pos)` SIN clamp (:72-75); `_position_get`
  = GetCursorPos; `press/release/click` = `SendInput` de botón sin
  coordenadas (:112-142) ⇒ el evento ocurre en la POSICIÓN actual del cursor
  (por eso el patrón es `position = (x, y)` y luego press/release/click).
  Coordenadas negativas = válidas (espacio virtual). Única ruta
  documentada-garantizada fuera del primario.
- PyAutoGUI 0.9.54 (VERIFICADO en código): el clamp general está
  **comentado** (`pyautogui/__init__.py:1474-1475`) y `_moveTo` llama a
  `SetCursorPos` sin recorte (`_pyautogui_win.py:357-369`) ⇒ mover/clicar en
  x<0 probablemente ya funciona, PERO los docstrings públicos
  (`__init__.py:1266-1267, 886-889`), la FAQ oficial y `onScreen()`
  (:790-792, 808-809: "doesn't work for secondary screens") siguen
  declarando "solo primario": conducta NO documentada; un upstream puede
  re-activar el clamp. PROHIBIDO depender de ello. El clamp que sí existe en
  pyautogui es el de `_scroll()` (posición del scroll al rango del primario,
  `_pyautogui_win.py:520-536`), no el del movimiento.
  https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-mouse_event
  (sin `MOUSEEVENTF_ABSOLUTE`, los flags de botón actúan en la posición
  actual: coherente con SetCursorPos previo).
- Regla de eleccion de backend de la skill (`scripts/raton.py`): destino dentro del
  monitor primario ⇒ pyautogui (tween/duración/PAUSE, comportamiento
  histórico); destino fuera del primario (o cualquier coord negativa) ⇒
  pynput, con `pyautogui.failSafeCheck()` antes de actuar y en cada paso
  interpolado (pynput no tiene FAILSAFE propio). Clic sin `--x/--y` sigue
  siendo pyautogui en la posición actual del cursor.

## 5. Teclado y foco (igual en todos los monitores)

- VERIFICADO (modelo Windows): las teclas van al FOCO de ventana, sin
  coordenadas ⇒ `teclado.py` no cambia entre monitores. Verificación de
  foco: `ventanas.py foco` (getActiveWindow ⇒ GetForegroundWindow en
  pygetwindow 0.0.9) y el flag `--requiere-foco "SUBCADENA"` de
  escribir/tecla/combo, que aborta sin emitir si el título real no coincide.

## 6. FAILSAFE: esquinas del primario y freno en el secundario

- La base del FAILSAFE (pyautogui siempre con FAILSAFE=True, FAILSAFE_POINTS =
  las 4 esquinas del monitor PRIMARIO con `size()` = SM 0/1, `failSafeCheck()`
  antes de cada llamada; fuente `__init__.py:573 + 2169-2171`) está verificada
  en `references/pyautogui-api.md` §7 — no se repite aquí. Lo que aporta el
  multi-monitor: con un secundario a la izquierda, las esquinas VIRTUALES
  (−1920, 0), etc. NO abortan; en el secundario no hay esquina failsafe.
- La huida humana clásica a (0,0) (esquina del primario) SIGUE válida.
- Freno en el secundario: tecla de pánico de `vigilar.py` (bandera ABORT) o
  Ctrl+C en la consola. La spec recomendaba extender `FAILSAFE_POINTS` con
  las esquinas del bounding virtual como mitigación opcional [runtime]
  (riesgo: colisión con UI real en esas esquinas); NO adoptada en la skill:
  mantiene el comportamiento validado.
- Tras un FAILSAFE la acción puede haber quedado PARCIAL (botón sin soltar,
  medio arrastrar, clic a medias): re-capturar y verificar estado antes de
  reintentar.

## 7. Ventanas en el espacio virtual y moverlas de monitor

- VERIFICADO (código pygetwindow): el rectángulo viene de `GetWindowRect`
  (`_pygetwindow_win.py:182-199`) ⇒ coordenadas de pantalla VIRTUALES
  (negativas con monitores a la izquierda/arriba). El aviso antiguo de
  `ventanas.py` ("rectángulo del monitor primario") era incorrecto:
  corregido.
- `getAllWindows()` filtra `IsWindowVisible` (:163-173): una ventana
  MINIMIZADA conserva WS_VISIBLE y entra en listar; su estado real es
  `isMinimized` = `IsIconic` (:277-280). El rect de una minimizada suele ser
  la posición fuera de pantalla típica (−32000, −32000) — dato, [runtime]; no
  es un monitor.
- `moveTo(newLeft, newTop)` → `SetWindowPos(hWnd, HWND_TOP, x, y, w, h, 0)`
  (:270-274): sin validación de rango en la librería ⇒ mover una ventana a
  otro monitor con negativos funciona en la API. **VERIFICADO en máquina
  (IMPL-K, 06/10/2026, 3 monitores)**: ya es verbo propio —
  `py scripts/ventanas.py mover --id N --monitor <indice|primario|nombre>`
  (o `--x --y` exactos, con `--ancho/--alto` opcionales): JSON canónico con
  `ventana{rect,estado}` + `monitor{indice,nombre,origen,bounds,primario}`.
  Caso probado: `--monitor 2` (DISPLAY3, −1920..0) dejó `rect.left=-1920`;
  caso negativo: `--monitor 987` → error JSON "fuera de rango (0..2)" SIN
  tocar la ventana (el destino se valida primero). El autotest live corre
  `mover --monitor primario` (+ secundario si hay ≥2) en el sandbox.
- Atajo nativo del SO para pasar la ventana activa al monitor vecino:
  Win+Shift+←/→ ⇒ `py scripts/teclado.py combo "win+shift+left"` — **NO
  cuenta: falló sintéticamente en la prueba W11 (rect inmutable, 4 intentos:
  combo ×2, arrastre de barra ×2, menú sistema — checklist-W11)**. Para
  mover ventanas entre monitores usa `ventanas.py mover` (SetWindowPos real).

## 8. DPI: qué está verificado y qué queda pendiente

- VERIFICADO (conceptual, doc de contextos): un proceso Per-Monitor aware
  "is not automatically scaled by the system"; UNWARE "will be automatically
  scaled by the system" (virtualización ⇒ métricas ESCALADAS). Con awareness
  per-monitor, las rectángulas de `GetMonitorInfo`/`GetSystemMetrics` están
  en píxeles físicos.
  https://learn.microsoft.com/en-us/windows/win32/hidpi/dpi-awareness-context
- `SetProcessDpiAwareness` (shcore) y `GetDpiForMonitor` devuelven 404 en
  Learn (slugs reubicados/retirados; sucesora documentada:
  `SetProcessDpiAwarenessContext`); su semántica queda verificada de forma
  indirecta + en runtime por la skill: `glue_windows.py` fija
  `SetProcessDpiAwareness(2)` ANTES de importar pyautogui. Decisión de la
  fase H: MANTENER el valor 2, no migrar a PER_MONITOR_AWARE_V2 (−4).
- Escalas mixtas entre monitores (p. ej. 100 % + 150 %): [runtime] revalidar
  antes de fiarse del marco. Con 100 % en ambos monitores no hay diferencia.

## 9. Tabla tarea → comando (multi-monitor)

COLLAPSED (SPEC P2-3): esta matriz era espejo del mapa de SKILL.md §4 (ruta
Windows con multi-monitor: `--monitor`, `--region` negativa, pynput fuera del
primario). La matriz canónica vive en **SKILL.md §4** — léela ahí; los detalles
de comportamiento multi-monitor están en §2-§8 de este archivo.

## 10. Límites y riesgos

- `pyscreeze` primario-only y el coste de `localizar` (1-2 s, primario-only):
  ya documentados en §3 de este archivo y en SKILL §4/§6 (SPEC P2-3: sin
  re-lista aquí).
- Un upstream de pyautogui puede re-activar el clamp en otra versión: por eso
  el input fuera del primario es SIEMPRE pynput (§4).
- Escala ≠ 100 % en alguno de los monitores: revalidar el DPI per-monitor
  antes de fiarse del marco (§8) [runtime].
- Monitores superpuestos hacia arriba/arriba (y negativos): mismos caminos
  (el guard virtual y `_monitor_contiene` los cubren); un hueco entre
  monitores desalineados NO es direccionable (error explícito).
- `capturar --monitor virtual` con monitores de escalas físicas distintas
  captura físico-a-físico (coherente con el proceso aware) [runtime].
- El índice de `monitores.py listar` sigue el orden de `EnumDisplayMonitors`:
  puede cambiar al reconectar monitores ⇒ volver a listar.
- Rendimiento real de `all_screens=True` (estimación de la spec ~2× el grab
  completo): [runtime] medir en máquina.

## 11. Lecciones runtime verificadas (05/10/2026, 3 monitores)

Pruebas en vivo H5-SEC (multi-monitor 18/18): el pixel y el scroll tienen
comportamientos que la API no documenta. Una lección por línea:

- El caret de Notepad en Windows 11 es color-acento y deja de repintarse tras reactivaciones de la ventana: pixel inútil para `pantalla.py esperar --cambia`.
- Los píxeles de borde ClearType sobre glifos son ESTÁTICOS: MUESTREA el pixel (`pantalla.py pixel`) antes de lanzar el watcher o tendrás falsos positivos.
- Ráfagas de rueda de ≥ ~12 notches sin pausa las coalesce el smooth-scroll de Windows: desplazamiento ≠ N × líneas; manda tandas cortas y re-verifica con captura.
- Soltar un arrastre FUERA de la ventana mapea a una línea app-dependiente (Notepad extiende la selección al borde): no asumas Ln/Col, lee la barra de estado en la captura.
