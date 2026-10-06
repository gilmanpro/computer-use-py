# pynput 1.8.2 en Windows 11 — API verificada (referencia computer-use-py)

> Derivado del digest de investigación del 03/10/2026 (PyPI + fuente master
> `lib/pynput/**` + docs readthedocs + CHANGES.rst + MSDN). Solo afirmaciones
> VERIFICADAS; lo marcado [runtime] queda pendiente de prueba en máquina.
> Leer este archivo SOLO si un script falla o hay que escribir código ad-hoc;
> el flujo normal va por los CLIs de `scripts/` (raiz multi-OS). La copia `pythonhosted.org/pynput` está
> congelada en v1.1.2 (2016): NO usarla.

## Índice

- 1. Versión mínima obligatoria y setup
- 2. Mouse: position, click, press/release, SCROLL (el motivo de la pirámide)
- 3. Teclado: press/tap/pressed/type y el UNICODE real
- 4. Combos inyectados (no existe hotkey)
- 5. Listeners: `injected`, ciclo de vida, callbacks
- 6. Supresión: por qué la skill nunca suppress
- 7. Anti-patrones verificados
- 8. Verificado vs pendiente-de-runtime

## 1. Versión mínima obligatoria y setup

- `pip install pynput` → 1.8.2. Dependencia runtime: solo `six`; el backend
  `_win32` es 100 % ctypes (`SendInput`, `SetCursorPos`/`GetCursorPos`); sin
  pywin32 y sin permisos especiales para controllers y listeners.
- Regla de versión (CHANGES.rst): ≤1.8.1 EMITÍA EVENTOS SCROLL DUPLICADOS en
  Windows; ≤1.7.6 rompía emojis; ≤1.7.7 rompía Python 3.12. Mínimo 1.8.2.
- DPI (crítico al 125-150 %): el listener recibe coordenadas FÍSICAS y el
  controller trabaja en ESCALADAS si el proceso no es aware → desajuste.
  Fix oficial (global al proceso, pynput no lo hace solo):
  `ctypes.windll.shcore.SetProcessDpiAwareness(2)` — lo que aplica
  `glue_windows.py` (glue Windows de la raiz) antes de importar nada.
- Correcciones a premisas frecuentes (verificadas contra el fuente master):
  en Windows `mouse.position` NO está normalizada −1..1 (son píxeles);
  NO existen `press_and_wait`, `KeyCode.from_virtual_key` ni el parámetro
  `delay` de `type()`; el comentario de docs `mouse.scroll(0, 2)  # two
  steps down` es un ERROR de documentación (el código sube).

## 2. Mouse — `pynput.mouse.Controller`

```python
from pynput.mouse import Button, Controller
m = Controller()
m.position = (x, y)          # ABSOLUTO en píxeles (SetCursorPos); PANTALLA VIRTUAL:
                             # (0,0)=vértice sup-izq del monitor PRIMARIO, pero con
                             # monitores a la izquierda/arriba x,y pueden ser NEGATIVOS
x, y = m.position            # GetCursorPos -> (int, int)
m.move(dx, dy)               # RELATIVO (suma delta a la posición actual)
m.click(Button.left, 2)      # click(button, count=1): NO acepta x,y (position primero)
m.press(Button.left); m.release(Button.left)
m.scroll(dx, dy)             # UNIDAD = notcha = 120 (WHEEL_DELTA)
```

- Botones: `left, middle, right, x1, x2` (y `unknown`). Usar solo nombres:
  los valores del enum son específicos de plataforma.
- SCROLL, signos confirmados en `mouse/_win32.py` + MSDN: `dy > 0` = rueda
  adelante = ARRIBA; `dy < 0` = abajo; `dx > 0` = DERECHA (HWHEEL). Coincide
  con el signo vertical de pyautogui; la diferencia decisiva: pynput rueda en
  HORIZONTAL en Windows, y pyautogui.hscroll NO (es vertical disfrazado).
  `scroll` no acepta x,y → posicionarse antes.
- No existe método drag → patrón: `position = (x0,y0); press; [position=…;
  sleep]…; release` (implementado en `raton.py arrastrar` con pyautogui).
- `move`/`scroll` pueden lanzar `ValueError`.

## 3. Teclado — `pynput.keyboard.Controller`

```python
from pynput.keyboard import Key, KeyCode, Controller
k = Controller()
k.press('a'); k.release('a')
k.tap(Key.enter)                       # press+release (desde 1.7.0)
k.touch(KeyCode.from_vk(0x41), True)   # True=pulsar / False=soltar
with k.pressed(Key.ctrl):              # suelta en orden INVERSO (finally)
    k.tap('a')
k.type('Hola\n')                       # SIN parámetro delay (1.8.2)
```

- `type(string)`: convierte `\n`/`\r`→enter y `\t`→tab; otros caracteres de
  control → `Controller.InvalidCharacterException(index, char)`. Retardo por
  carácter: bucle `tap` + `time.sleep` (así lo hace `teclado.py`).
- `press/release`: cadena de longitud 1, miembro `Key` o `KeyCode`;
  `Controller.InvalidKeyException` si es inválida; `ValueError` si la cadena
  no es de longitud 1.
- Enum `Key` en Windows (fuente `_win32.py`): `alt, alt_l, alt_r, alt_gr,
  backspace, caps_lock, cmd/cmd_l/cmd_r (=tecla Windows), ctrl/ctrl_l/ctrl_r,
  delete, down, end, enter, esc, f1–f24, home, insert, left, menu (=APPS),
  num_lock, page_down, page_up, pause, print_screen, right, scroll_lock,
  shift/shift_l/shift_r, space, tab, up` + multimedia: `media_play_pause,
  media_stop, media_volume_mute, media_volume_down, media_volume_up,
  media_previous, media_next`.
- `KeyCode`: `from_char(c)`, `from_vk(vk)`, `from_dead(c)`. NO
  `from_virtual_key`.
- UNICODE real (mecanismo verificado en `_win32.py`): si `VkKeyScan` no mapea
  el carácter sin modificador (ñ, ¿, 😀), pynput inyecta `KEYEVENTF_UNICODE`
  (VK_PACKET); para >U+FFFF (emojis) emite el par sustituto UTF-16 (fix
  v1.7.7). Resultado: `type('España ¿cómo? 😀')` escribe de verdad en apps
  normales (Office, navegadores, Explorador). Dónde puede fallar: apps que
  leen scancodes/DirectInput, consolas legacy [runtime]. Respaldo robusto:
  portapapeles (`pyperclip.copy` + `pressed(Key.ctrl)+tap('v')`) — implementado
  en `teclado.py --via portapapeles`.

## 4. Combos inyectados (no existe hotkey)

- `HotKey`/`GlobalHotKeys` solo DETECTAN pulsaciones del usuario; para
  INYECTAR: presión en orden y liberación en orden INVERSO, idealmente con
  `with k.pressed(*modificadores): k.tap(final)` (libera en `finally`,
  a prueba de excepciones — `_base.py:470-477`).
- El estado de modificadores (`ctrl_pressed`, …) es SOLO interno del
  Controller: si una excepción deja ctrl sin soltar, queda corrupto → siempre
  `pressed()` o `try/finally`.
- Sin auto-repetición (limitations.html oficial): mantener una tecla inyectada
  NO repite como una física → emitir pulsaciones separadas.
- Sin delay interno (`SendInput` inmediato): entre down/up, `sleep(0.01-0.05)`
  para apps lentas (práctica, no API).
- Ctrl+Alt+Supr (SAS) y combos de shell privilegiados: no inyectables por
  Windows (no de pynput) [runtime].
- Los aceleradores de menú de la app pueden reclamar el combo: en el Notepad en
  español `ctrl+a` abre "Abrir" en vez de seleccionar todo [runtime] — SIEMPRE
  verificar el efecto con una captura (alternativas: arrastre, shift+flechas, menú contextual).

## 5. Listeners — la ventaja clave sobre PyAutoGUI

```python
from pynput import keyboard, mouse
def on_press(key, injected): ...   # callbacks con injected desde 1.8.0
def on_release(key, injected): ...
# ratón: on_move(x, y, injected), on_click(x, y, button, pressed, injected),
#        on_scroll(x, y, dx, dy, injected)
l = keyboard.Listener(on_press=on_press)
l.start(); l.wait()    # wait() = hook instalado
...
l.stop(); l.join()     # stop() desde cualquier hilo; UN LISTENER PARADO NO SE
                       # REINICIA: crear uno nuevo por secuencia
```

- Compatibilidad: los handlers de firma antigua (`def on_press(key):`) siguen
  funcionando (`_wrap` recorta args) — pero la skill usa `injected` para
  filtrar la entrada del propio bot (anti-patrón #11).
- `injected` en Windows es real: flags `LLKHF_INJECTED/LLKHF_LOWER_IL_INJECTED`
  del hook (`_win32.py`).
- Ciclo de vida: es `threading.Thread` con `daemon=True`; `with Listener(...)`
  = start/wait/stop; `return False` desde un callback lo para; `join()`
  re-lanza excepciones de callbacks.
- LOS CALLBACKS CORREN EN EL HILO DEL HOOK LL (WH_KEYBOARD_LL=13,
  WH_MOUSE_LL=14): "long running procedures and blocking operations should not
  be invoked from the callback, as this risks freezing input for all
  processes" (doc oficial) → solo marcar eventos/encolar; el I/O, en el hilo
  principal (así lo hace `vigilar.py`).
- Síncrono sin listeners: `with keyboard.Events() as ev: ev.get(1.0)` → `None`
  si no hay evento (útil para "confirma en N segundos").
- Ventana de hook por proceso: los listeners pueden no recibir eventos de
  OTROS procesos según la nota "virtual events sent by other processes may not
  be received" (limitations.html) — el propio proceso sí se redespacha.

## 6. Supresión: por qué la skill nunca suppress

- `suppress=True` en un listener de teclado suprime TODOS los eventos de
  teclado a TODO el sistema (FAQ oficial): el usuario se queda sin teclado,
  ni Ctrl+C en su consola. Prohibido en esta skill.
- Si algún día hiciera falta bloquear teclas concretas: `win32_event_filter`
  + `listener.suppress_event()` solo para esas teclas (soportado en Windows;
  `darwin_intercept` en macOS). [runtime] si se usa.

## 7. Anti-patrones verificados (tabla del digest, recortada)

| # | Anti-patrón | Por qué |
|---|---|---|
| 1 | Tratar `position` como −1..1 o esperar `move` absoluto | SetCursorPos en píxeles; `move` suma delta |
| 2 | Creer el comentario de docs "scroll(0, 2) = two steps down" | el código envía `+2*120` = ARRIBA; el listener de docs lo confirma (`dy<0`=down) |
| 3 | Mezclar coords listener/controller sin SetProcessDpiAwareness(2) | listener físico vs controller escalado al 125 % |
| 4 | `suppress=True` global | deja al usuario sin teclado ni Ctrl+C (§6) |
| 5 | Sleep/I/O dentro de un callback | congela la entrada de todo el SO (hilo del hook LL) |
| 6 | Reutilizar un listener tras `stop()` | Thread parado no reinicia ("Toggling") |
| 7 | Automatizar apps elevadas desde proceso normal | UIPI bloquea SendInput/SetCursorPos en silencio [inferencia estándar] |
| 8 | pynput < 1.8.2 | scroll duplicado en Windows (CHANGES) |
| 9 | Esperar auto-repetición con press mantenida | "not truly pressed" (limitations.html) |
| 10 | Llamar `press_and_wait`/`from_virtual_key`/`type(delay=…)` | NO existen en 1.8.2 → AttributeError/TypeError |
| 11 | Watchdog sin filtrar `injected` | el bot se pausa a sí mismo (bucle) |
| 12 | `type()` con controles raros | solo `\n \r \t` mapeados; resto → InvalidCharacterException |
| 13 | `press(mod)` sin `release` en try | estado interno del Controller corrupto |
| 14 | PyInstaller sin hidden-imports de `pynput.mouse._win32`/`keyboard._win32` | backends se cargan con importlib en runtime (FAQ) |

## 8. Verificado vs pendiente-de-runtime

- VERIFICADO (fuente master + docs + PyPI + probes en esta máquina con
  1.8.2 instalado): todo lo anterior; enum completo (media keys, cmd, menu,
  print_screen presentes); firma del Listener en 1.8.2.
- [runtime]: KEYEVENTF_UNICODE/VK_PACKET en conhost legacy vs Windows
  Terminal; `LowLevelHooksTimeout` al bloquear callbacks; UIPI como nombre del
  bloqueo en apps elevadas (el síntoma sí está documentado para pyautogui);
  supresión selectiva con `win32_event_filter`.
