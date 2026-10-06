# computer-use-py — control del escritorio como un humano (Windows · Linux · macOS)

Skill para agentes: manejar el escritorio real (ratón, teclado, ventanas,
capturas) **como lo haría un humano**, con un loop de
`captura → visión → acción → verificación`. Cada acción pasa por un script
CLI que responde **JSON por stdout** (errores con clave `error` y salida 1),
así que el agente siempre puede releer el estado antes del siguiente paso.
La rama **Windows** está validada en escritorio real; **Linux** (X11/Wayland)
y **macOS** replican los verbos y el contrato con límites honestos (§Ramas).

No es un framework de automatización para terceros: es control del *propio*
escritorio con frenos humanos deliberados (FAILSAFE, watchdog, verificación
de foco).

## Ramas y enrutamiento

| SO | Carpeta | Ejecución | Smoke (sin efectos) |
|---|---|---|---|
| Windows | `scripts/` | `py scripts/<s>.py <verbo>` | `py scripts/autotest.py` |
| Linux | `scripts/linux/` | `python3 scripts/linux/<s>.py <verbo>` | `python3 scripts/linux/autotest.py` |
| macOS | `scripts/macos/` | `python3 scripts/macos/<s>.py <verbo>` | `python3 scripts/macos/autotest.py` |

Correr la rama equivocada responde un JSON "corre en tu SO" (exit 2), nunca
traceback. Contrato uniforme: `plataforma` en todo JSON, `marco` enum
(`px_fisicos_virtual`/`px_layout`/`puntos_logicos`), campo único de re-escalado
`px_por_unidad_coord`, objeto `ventana` anidado `rect`+`estado`, errores JSON.

## Stack (y por qué)

- **PyAutoGUI** (Windows/X11) — capturas, teclado ASCII, ratón y ventanas
  (pygetwindow). En macOS la rama usa **pynput/Quartz + screencapture**; en
  Wayland, **grim/ydotool/wtype** por subprocess interno.
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
`references/linux-python.md` §15 y `references/macos-python.md` §11.
Tras instalar: corre el `autotest.py` de tu SO (modo lectura) como smoke;
`--con-escritura` lanza un sandbox (Bloc de notas/editor/TextEdit) solo para
un humano consciente.

## El loop, con comandos reales (rama Windows; idéntico en las otras con su carpeta)

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

## Scripts

Los verbos por SO viven en un solo sitio: **SKILL.md §4** (mapa tarea→comando
con la tabla SO→carpeta). La rama Windows añade `win_especiales.py`:
portapapeles (`leer`/`escribir --respaldar`/`estado`), procesos (`listar`/
`matar --pid --confirmar`), `ejecutar --elevado` (UAC) y `dpi listar` —
el matar exige `--confirmar` humano y nunca imprime el portapapeles sin
pedido explícito.

## Seguridad

El detalle normativo vive en **SKILL.md §5** (FAILSAFE siempre encendido,
banderas `.tmp/ABORT` dura y `.tmp/PAUSA` suave que frena el arranque de
acciones, `--requiere-foco` antes de teclear, prohibido `suppress=True`,
re-captura tras un abort). Resumen: el freno humano es parte del contrato,
no una opción; las cuatro esquinas del monitor primario abortan siempre.

## Multi-monitor

Las coordenadas son del **espacio virtual** (origen = monitor primario;
negativos hacia la izquierda/arriba) y el input fuera del primario se enruta
solo por pynput (Windows). En Linux es el screen/compositor y en macOS los
puntos lógicos globales. Detalle, verificaciones y trampas (como el
`region=` que da negro): `references/monitores-multi.md`.

## Notas del repo

- Los archivos temporales (capturas PNG, banderas `ABORT`/`PAUSA`, pruebas)
  viven en `.tmp/` de esta skill y **no se commitean** (guard en
  `.tmp/.gitignore`).
- `SKILL.md` es la guía de uso para el agente; `references/` guarda el
  conocimiento verificado (API, multi-monitor, Linux/macOS por SO, comandos
  nativos sin Python).
