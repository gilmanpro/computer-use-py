# PyAutoGUI 0.9.54 en Windows 11 — API verificada (referencia computer-use-py)

> Derivado del digest de investigación del 03/10/2026 (docs readthedocs +
> código fuente master + pygetwindow). SOLO afirmaciones VERIFICADAS; lo
> marcado [runtime] debe comprobarse en la máquina antes de fiarse. Recortado
> a lo que usa esta skill. Leer este archivo solo si un script falla o hay que
> escribir código ad-hoc — el flujo normal va por `scripts/`.

## Índice

- 1. Versión y setup
- 2. Captura, tamaño, posición (marco de coordenadas)
- 3. Teclado (y por qué el no-ASCII se pierde)
- 4. Ratón y scroll
- 5. locate* (búsqueda de imágenes)
- 6. Ventanas: pygetwindow
- 7. Seguridad: FAILSAFE, PAUSE, límites de Windows
- 8. Anti-patrones verificados
- 9. Verificado vs pendiente-de-runtime

## 1. Versión y setup

- Versión: `__version__ = "0.9.54"` en `pyautogui/__init__.py:20` (master).
- `pip install pyautogui` arrastra PyTweening, PyScreeze, PyGetWindow,
  PyMsgBox, MouseInfo. Pillow para capturas. En Windows NO usa pywin32:
  ctypes contra la WinAPI ("Windows has no dependencies").
- `confidence=` en `locate*` REQUIERE `pip install opencv-python` (+numpy).
- `pyperclip` no es dependencia: instalar aparte para el respaldo unicode.
- Ayuda visual: `py -m mouseinfo` (XY + RGB en ventana).

## 2. Captura, tamaño, posición

```python
im  = pyautogui.screenshot()                        # PIL Image RGB
im  = pyautogui.screenshot('ruta.png')              # además guarda (formato = extensión)
im  = pyautogui.screenshot(region=(x, y, w, h))     # region: 4 enteros (left, top, ancho, alto)
w, h = pyautogui.size()      # Size; SOLO monitor primario, píxeles físicos (GetSystemMetrics)
x, y = pyautogui.position()  # Point del cursor
pyautogui.onScreen(x, y)     # bool
```

- Coste de captura ~100 ms en 1920×1080 (doc screenshot.rst).
- Multi-monitor: FAQ oficial — "only handles the primary monitor";
  coordenadas fuera de [0, w-1]×[0, h-1] no son direccionables.
- DPI: al importarse pyautogui ejecuta `SetProcessDPIAware()` (system-aware).
  Los scripts de la skill llaman ANTES `SetProcessDpiAwareness(2)`
  (process-per-monitor, API shcore) para unificar con pynput; el orden
  importa porque la consciencia DPI se fija una sola vez por proceso.
  Efectos de escalas mixtas por monitor con per-monitor: [runtime].

## 3. Teclado

```python
pyautogui.write('hola', interval=0.25)   # alias typewrite; SOLO caracteres de 1 tecla
pyautogui.write(['a','left','backspace'])# lista = nombres KEYBOARD_KEYS
pyautogui.press('enter', presses=3, interval=0.2)
pyautogui.keyDown(k); pyautogui.keyUp(k)
with pyautogui.hold('shift'): ...        # context manager (v0.9.51+)
pyautogui.hotkey('ctrl', 'shift', 'esc') # press en orden, release en REVERSA
pyautogui.isValidKey(nombre)             # validar antes de pulsar
```

- NO existe `holdKeyOn` ni parámetro de modo: mantener = keyDown+sleep+keyUp.
- NO-ASCII (ñ, á, ¿, 😀): en Windows el mapa se rellena solo con `chr(32..127)`
  (`_pyautogui_win.py:243-245`) y `_keyDown/_keyUp` hacen `return` sin excepción
  para lo no mapeado → **se descarta en silencio**. Respaldo comunitario
  (no doc oficial): `pyperclip.copy(texto); pyautogui.hotkey('ctrl','v')`.
- Teclas multimedia por nombre: `volumemute, volumedown, volumeup, playpause,
  nexttrack, prevtrack, stop`; Windows: `win, winleft, winright, apps`.
- El teclado va a la ventana con el FOCO; nada de "escribir a una ventana X"
  sin activarla antes.

## 4. Ratón y scroll

```python
pyautogui.moveTo(x, y, duration=0.0, tween=linear)
pyautogui.click(x=None, y=None, clicks=1, interval=0.0, button='left', duration=0.0)
pyautogui.rightClick(...); middleClick(...); doubleClick(...); tripleClick(...)
pyautogui.mouseDown(x, y, button=...); pyautogui.mouseUp(...)
pyautogui.dragTo(x, y, duration=0.0, button='left', mouseDownUp=True)
pyautogui.scroll(clicks, x=None, y=None)   # 1er arg = clicks, NO amount
```

- Signo del scroll: positivo = rueda adelante = ARRIBA; negativo = abajo
  (docstring `_scroll`, `_pyautogui_win.py:512-513`; coincide con pynput).
- `dwData = clicks` pasa CRUDO a `mouse_event(MOUSEEVENTF_WHEEL)` (`:538`):
  Windows mide en WHEEL_DELTA=120 → un `scroll(1)` casi no mueve nada;
  valores útiles típicos 100-500 por notcha. La escala exacta por app:
  [runtime]. **Nota: la skill usa pynput para scroll** (ver §8 y raton.py).
- `hscroll` en Windows NO existe como horizontal: `_hscroll` es
  `return _scroll(...)` (`:544-557`) → rueda vertical sin avisar; docstring:
  "Currently just Linux". Usarlo es siempre una acción incorrecta.
- Defaults instantáneos: `duration=0.0`, `tween=linear`; `MINIMUM_DURATION=0.1`
  (duraciones menores se mueven instantáneas). Botones válidos: 'left',
  'middle', 'right' (PRIMARY/SECONDARY según swap; inválido → excepción).

## 5. locate*

```python
box = pyautogui.locateOnScreen('btn.png', confidence=0.9, region=(x, y, w, h), grayscale=None)
pt  = pyautogui.locateCenterOnScreen('btn.png')
pyautogui.center(box); pyautogui.pixel(x, y)
pyautogui.pixelMatchesColor(x, y, (r, g, b), tolerance=0)
```

- Sin OpenCV, `confidence=` lanza `NotImplementedError` (`_locateAll_pillow:268`).
- Desde 0.9.41 existe `ImageNotFoundException`; sin opt-in, locate devuelve
  `None` si no encuentra. Gestionar AMBOS caminos.
- Contradicción verificada en docs: `grayscale` default `False` en la doc
  pública vs `GRAYSCALE_DEFAULT = True` en pyscreeze 1.0.0 master → pasar
  `grayscale=` explícito en código ad-hoc si el color importa.
- Coste: 1-2 s por locate en 1080p (docs); exigir píxeles casi idénticos →
  sensible a tema oscuro, antialiasing, escala. Reducir SIEMPRE con `region`.

## 6. Ventanas: pygetwindow

- La API propia de ventanas de pyautogui desapareció en 0.9.54 (0 coincidencias
  en el fuente); quedan solo re-exports Windows-only de pygetwindow.
- Uso:

```python
import pygetwindow as gw
ws = gw.getAllWindows(); ts = gw.getAllTitles()
gw.getWindowsWithTitle('Bloc')      # coincidencia por SUBCADENA
gw.getActiveWindow(); gw.getFocusedWindow()
v.title; v.left; v.top; v.width; v.height
v.activate(); v.minimize(); v.restore(); v.maximize(); v.close()
v.moveTo(x, y); v.resizeTo(w, h)    # move()/resize() son INCREMENTALES
```

- Verificado en runtime con pygetwindow 0.0.9 instalada: existen `activate`,
  `isMinimized`, `isMaximized`, `isActive`, `restore`, `show`, `hide`. La doc
  oficial usa `focus()` (no existe en 0.0.9) → [runtime] el comportamiento de
  activate/minimize/close por app (diálogos modales incluidos).

## 7. Seguridad: FAILSAFE, PAUSE, límites de Windows

- `FAILSAFE = True` por defecto (`:572`); `FAILSAFE_POINTS` = las 4 esquinas
  del primario (`:573, :2169-2171`). Se comprueba la posición ANTES de cada
  llamada pública (`failSafeCheck()`); lanza `FailSafeException`. La doc que
  solo menciona la esquina superior izquierda está desactualizada.
- `PAUSE = 0.1` s tras cada función pública (`:562`); la skill lo fija en 0.15.
  Subir PAUSE es legítimo; JAMAS bajarlo ni `FAILSAFE=False` (docs: "I HIGHLY
  RECOMMEND YOU DO NOT DISABLE THE FAILSAFE").
- Apps elevadas ("como administrador"): `_mouseDown/_mouseUp/_click` capturan
  `PermissionError/OSError` y siguen de largo — el click NO ocurre y nadie se
  entera (fuente, issue #60). El teclado inyectado también se ignora en
  silencio (mecanismo UIPI: inferencia estándar, no nombrada en docs).
- Ctrl+Alt+Supr (SAS) y la pantalla de bloqueo/UAC: no inyectables; el agente
  debe detectar el bloqueo visualmente y abortar.
- Juegos/DirectInput: pyautogui usa `keybd_event`/`mouse_event` (virtual keys,
  no scan codes) → pueden ignorarse; alternativa documentada: PyDirectInput.
- No hay keylogging ni "API de detener": abortar = esquina + FAILSAFE, Ctrl+C
  en la terminal, o listener pynput propio (vigilar.py).

## 8. Anti-patrones verificados (tabla del digest, recortada)

| Anti-patrón | Por qué |
|---|---|
| Escribir sin confirmar el foco | el teclado va a la ventana enfocada; un toast de W11 lo roba |
| `interval=0.0` y PAUSE mínimo | defaults instantáneos; las UIs lentas pierden teclas |
| Clic sin captura de verificación | `PermissionError` silenciado: el click puede no existir |
| `locateOnScreen` en cada iteración | 1-2 s por llamada; usar visión sobre la captura |
| Hardcodear coordenadas | absolutas + primario + escala DPI + tema lo cambian todo |
| `hscroll` en Windows | rueda vertical en silencio (§4) |
| `write('ñ émoji')` | descartado en silencio (§3); usar pynput o portapapeles |
| `FAILSAFE=False` | elimina el único freno humano |
| Automatizar sobre app elevada | input ignorado en silencio (§7) |
| `screenshot()` justo tras una acción sin dormir | PAUSE no cubre animaciones/diálogos: dormir ~0.4 s |

## 9. Verificado vs pendiente-de-runtime

- VERIFICADO (docs/fuente + probes de esta máquina): todo lo anterior con
  línea de fuente o doc citada; pyautogui 0.9.54 instalado y funcionando.
- [runtime]: escala práctica del scroll por notcha según app; efectos de
  per-monitor-v2 con escalas mixtas; fiabilidad de activate()/minimize()/
  close() por aplicación; Windows 11 24H2 específico (sin declaración oficial).
