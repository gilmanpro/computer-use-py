# computer-use-py — control del escritorio como un humano (Windows · Linux · macOS)

Skill para agentes: manejar el escritorio real (ratón, teclado, ventanas,
capturas) **como lo haría un humano**, con un loop de
`captura → visión → acción → verificación`. Cada acción pasa por un script
CLI que responde **JSON por stdout** (errores con clave `error` y salida 1),
así que el agente siempre puede releer el estado antes del siguiente paso.
La ruta **Windows** está validada en escritorio real; **Linux** (X11/Wayland)
y **macOS** replican los verbos y el contrato con límites honestos (sección
Arquitectura y `references/linux-python.md` / `references/macos-python.md`).

No es un framework de automatización para terceros: es control del *propio*
escritorio con frenos humanos deliberados (FAILSAFE, watchdog, verificación
de foco).

## Arquitectura (FASE SEG3): flujo normal por `scripts/` raíz — los 3 SO

| Elemento | Qué es |
|---|---|
| `scripts/monitores.py` · `pantalla.py` · `teclado.py` · `raton.py` · `ventanas.py` · `vigilar.py` · `autotest.py` | los 7 CLIs multi-OS: cada uno **ejecuta en el propio proceso la ruta de tu SO** (dispatch por `sys.platform` en tiempo de ejecución). En **Windows** usan la ruta nativa (DPI + pyautogui/pynput vía `glue_windows.py`); en **Linux/macOS** orquestan las primitivas de `linux_especiales.py`/`macos_especiales.py`; plataforma desconocida → JSON de error + rc 2 |
| `scripts/_core.py` | código **genérico** multi-OS (stdlib puro: JSON, banderas, validaciones, esperas, geometría, **dispatch de plataforma** `modulo_sistema()`) |
| `scripts/glue_windows.py` | **glue exclusivo Windows** (guard, DPI, pyautogui, monitores ctypes) que reexporta `_core` |
| `scripts/windows/win_especiales.py` | lo **únicamente Windows** (único archivo de la carpeta): portapapeles leer/escribir/estado, procesos (tasklist/taskkill gateado), `ejecutar --elevado` (UAC), `dpi listar` |
| `scripts/linux/linux_especiales.py` | **único archivo** de `scripts/linux/`: CLI solo-Linux (`sesion`, `xrandr`, `grim`, `portapapeles leer|escribir`, `wayland-status`) **y librería** de primitivas X11/Wayland (xrandr/swaymsg/hyprctl monitores, grim captura, wtype/ydotool input, wmctrl/xdotool ventanas, xclip portapapeles) que los CLIs raíz usan en su rama |
| `scripts/macos/macos_especiales.py` | **único archivo** de `scripts/macos/`: CLI solo-macOS (`tcc`, `screencapture`, `monitores-quartz`, `ventanas-se`, `open`) **y librería** de primitivas (osascript/System Events, screencapture, Quartz, kVK/alias teclado, hints TCC, escala Retina) que los CLIs raíz usan en su rama |

Autotest — **entrada única e invariable**: `py autotest.py` (Windows) o
`python3 autotest.py` (Linux/macOS) desde esta carpeta raíz: corre la **única
suite unificada** `scripts/autotest.py` — batería completa del SO anfitrión +
checks estáticos de la simetría SEG3 (los `<so>_especiales` existen/compilan/
son importables, dispatch presente en los 6 CLIs, guard del CLI exclusivo,
contrato documentado); los checks que exigen un SO ajeno real salen SKIP con
motivo. `--con-escritura` (sandbox) solo en el SO anfitrión y solo para un
humano. Correr el CLI **exclusivo** del SO equivocado responde un JSON de
error (exit 2), nunca traceback — exacto por rama: linux/mac con el guard en
su `__main__` ("dominio EXCLUSIVO") y `win_especiales` muriendo ya en el
import de `glue_windows` (guard de import, mismo JSON+rc 2); las librerías
especiales sí se importan en cualquier SO.

Contrato uniforme: `plataforma` en todo JSON, `marco` enum
(`px_fisicos_virtual`/`px_layout`/`puntos_logicos`), campo único de re-escalado
`px_por_unidad_coord`, objeto `ventana` anidado `rect`+`estado`, errores JSON.

## Stack (y por qué)

- **PyAutoGUI** (Windows/X11) — capturas, teclado ASCII, ratón y ventanas
  (pygetwindow). En macOS la ruta del CLI raíz usa **pynput/Quartz +
  screencapture** vía la librería `macos_especiales.py`; en Wayland el CLI raíz
  orquesta **grim/ydotool/wtype/swaymsg/hyprctl** vía `linux_especiales.py`
  (subprocess interno; X11/Wayland se resuelve ahí, no en un motor aparte).
- **pynput** — tipeo unicode real, scroll en ambos ejes y listeners que
  distinguen entrada humana de la inyectada (`injected`) para el botón de
  pánico. En Windows es además el motor de ratón garantizado fuera del primario.
- **pyperclip / pbcopy / xclip** — respaldo por portapapeles según el SO.

## Instalación

```bat
py -m pip install pyautogui pynput pyperclip pygetwindow
py -m pip install opencv-python   :: opcional, solo para localizar --confidence
```

En Linux/macOS las dependencias (pynput, pillow, pyobjc-framework-Quartz,
opencv opcional; xdotool/wmctrl/grim/ydotool del sistema) están en
`references/linux-python.md` §16 y `references/macos-python.md` §11.
Tras instalar: corre `py autotest.py` desde la raíz de la skill (modo lectura)
como smoke; `--con-escritura` lanza un sandbox (Bloc de notas/editor/TextEdit)
solo para un humano consciente.

## El loop, con comandos reales (raíz multi-OS; idéntico en los 3 SO)

```bat
py scripts/monitores.py listar
py scripts/pantalla.py capturar
:: el JSON devuelve "archivo" con la ruta absoluta del PNG: leerlo con vision
py scripts/ventanas.py foco
py scripts/ventanas.py activar "Nombre de la ventana"
py scripts/raton.py click --x 640 --y 300
py scripts/pantalla.py esperar --milisegundos 400
py scripts/pantalla.py capturar   :: verificacion: ¿ocurrio lo esperado?
```

Reglas del loop: tras cada acción, **verificar con una captura** (la salida 0
no prueba que el clic haya existido); mantener una **mini-bitácora** de una
línea `acción→resultado`; y pedir **confirmación humana antes de acciones
irreversibles** (borrar, enviar, pagar, loguear, credenciales).

## Scripts

La tabla de verbos por SO vive en un solo sitio: **SKILL.md §4** (mapa
tarea→comando por CLI de la raíz + exclusivos). Estructura del código:
`scripts/_core.py` = **genérico multi-OS** (stdlib puro: salida JSON, banderas
ABORT/PAUSA, validaciones de args, bucles de espera, geometría de monitores,
tablas, convenciones y dispatch `modulo_sistema()`); los CLIs de `scripts/` =
**entrada normal en los 3 SO** (ejecutan en el propio proceso la ruta de tu
SO); `glue_windows.py` y las carpetas `windows/linux/macos` = **exclusivos de
cada SO**, con un único archivo `<so>_especiales.py` en cada una. El autotest
de la suite audita el layout (cada carpeta de SO = solo su `<so>_especiales.py`),
verifica los guards y simula el dispatch con la plataforma parcheada.

## Seguridad

El detalle normativo vive en **SKILL.md §5** (FAILSAFE siempre encendido,
banderas `.tmp/ABORT` dura y `.tmp/PAUSA` suave que frena el arranque de
acciones, `--requiere-foco` antes de teclear, prohibido `suppress=True`,
re-captura tras un abort). Resumen: el freno humano es parte del contrato,
no una opción; las cuatro esquinas del monitor primario abortan siempre.

## Multi-monitor

Las coordenadas son del **espacio virtual** (origen = monitor primario;
negativos hacia la izquierda/arriba) y el input fuera del primario va solo
por pynput (Windows). En Linux es el screen/compositor y en macOS los
puntos lógicos globales. Detalle, verificaciones y trampas (como el
`region=` que da negro): `references/monitores-multi.md`.

## Notas del repo

- Los archivos temporales (capturas PNG, banderas `ABORT`/`PAUSA`, pruebas)
  viven en `.tmp/` de esta skill y **no se commitean** (guard en
  `.tmp/.gitignore`).
- `SKILL.md` es la guía de uso para el agente; `references/` guarda el
  conocimiento verificado (pirámide Windows, API de librerías, multi-monitor,
  Linux/macOS por SO, comandos nativos sin Python).
- La skill **no se auto-mejora**: ante un defecto o idea, se **reporta** al
  usuario (con evidencia; nota opcional en `.tmp/`); editar `scripts/`,
  `references/` o estos docs durante el uso requiere un **pedido explícito**
  del usuario (el árbol está validado en escritorio real y publicado).
