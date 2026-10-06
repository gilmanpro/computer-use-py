# ARQUITECTURA — computer-use-py (control del escritorio como un humano)

Documento de arquitectura para humanos y agentes: qué hace CADA archivo de la
skill y POR QUÉ existe, además del FLUJO IDEAL en cada SO. Estado: post-IMPL-K
(FASE SEG3 + cosecha IMPL-K). Rutas relativas a la raíz de la skill.

## Índice

1. Qué es esta skill
2. Mapa de archivos (qué hace · por qué existe · quién lo usa)
3. El contrato JSON
4. Flujo ideal por SO (Windows 11 · Linux X11 · Linux Wayland · macOS)
5. Cómo se prueba a sí misma
6. Decisiones que ya no están (anti-regresión)
7. Cierre

---

## 1. Qué es esta skill

`computer-use-py` permite que un agente maneje el escritorio REAL de su propia
máquina como lo haría un humano, en un bucle de `captura → visión → acción →
verificación`: el agente toma una captura, LA LEE con visión (el PNG vuelve al
agente como archivo), decide la siguiente coordenada o tecla, la emite, espera
el render, vuelve a capturar y compara. La salida 0 NO prueba el efecto (una
app elevada o un toast de foco se tragan la inyección en silencio): por eso la
verificación visual es parte obligatoria del bucle, junto con frenos humanos
deliberados — FAILSAFE de esquinas, bandera `ABORT`/`PAUSA`, watchdog de
tecla de pánico y confirmación humana antes de acciones irreversibles.

La superficie es UNA CLI JSON por verbo: `scripts/monitores.py`, `pantalla.py`,
`teclado.py`, `raton.py`, `ventanas.py`, `vigilar.py` — los mismos comandos
valen en los 3 SO (Windows · Linux · macOS) porque cada CLI ejecuta EN EL
PROPIO PROCESO la ruta de tu sistema (dispatch por `sys.platform` en tiempo de
ejecución, FASE SEG3); todo imprime JSON por stdout (errores JSON con clave
`error`, rc 1; guards rc 2) y las primitivas exclusivas de cada SO viven en un
único módulo por rama. No es un framework para terceros ni para web: si hay
API, CLI o MCP que logra el mismo resultado, se usa eso en lugar de simular
clics.

## 2. Mapa de archivos

```
computer-use-py/
  SKILL.md · README.md · ARQUITECTURA.md · autotest.py
  scripts/           # 7 CLIs multi-OS + genericos + glue Windows
    _core.py · glue_windows.py · autotest.py
    monitores.py · pantalla.py · teclado.py · raton.py · ventanas.py · vigilar.py
    windows/win_especiales.py · linux/linux_especiales.py · macos/macos_especiales.py
  references/        # conocimiento verificado por SO/libreria (7 archivos)
  .tmp/.gitignore    # guard de privacidad del directorio temporal
```

| Archivo | Qué hace | Por qué existe (decisión / lección) | Quién lo usa |
|---|---|---|---|
| [SKILL.md](SKILL.md) | Frontmatter + guía operativa del agente: ruta rápida, bucle, mapa tarea→verbo, seguridad, anti-patrones, contrato de coordenadas (§8) | Es la unica inyección de contexto del agente: el flujo normal NO debe leer referencias; los triggers de activación y la regla "description sin `<`/`>`" siguen la doc estable de skills | El agente (carga de skill) |
| [README.md](README.md) | Presentación humana: arquitectura SEG3, stack y porqué, instalación, punteros a SKILL.md como fuente normativa | Evita duplicar el mapa de verbos: la tabla vive en un solo sitio (SKILL.md §4) y el README explica el diseño | Humanos / agentes antes de instalar |
| `autotest.py` (raíz) | PORTADA de autovalidación: re-lanza la suite con el argv verbatim, hereda consola y exit code | Entrada UNICA e invariable en los 3 SO (`py autotest.py` / `python3 autotest.py`); es stdlib-pura (sin pyautogui) para poder correr ANTES de instalar dependencias; si falta la suite responde JSON + rc 2, nunca traceback | El humano/agente que valida la instalación; la suite real es `scripts/autotest.py` |
| `scripts/_core.py` | Código GENÉRICO multi-OS en stdlib puro: JSON/fallo con `plataforma`, banderas ABORT/PAUSA, validaciones y caps de args, esperas portables, color/combos, geometría de rects (`resolver_monitor`, `bounding_de`), convención de destino de capturas, tablas compartidas y AUDITORÍA de estructura (`problemas_estructura()`); `modulo_sistema()` resuelve el dispatch | Era triplicado palabra-por-palabra en los tres `_compartido*.py` (eliminados en FASE SEG); una sola copia con el texto de la rama Windows como CANÓNICO (es la validada en escritorio real); el dispatch ocurre en el propio proceso: desde SEG3 este módulo NO lanza ningún proceso (el viejo enrutador SEG2 fue ELIMINADO) | Los 7 CLIs raíz; los 3 módulos exclusivos lo reexportan; la suite invoca su auditoría |
| `scripts/glue_windows.py` | Glue EXCLUSIVO Windows: guard de plataforma (rc 2), fija `SetProcessDpiAwareness(2)` ANTES de importar pyautogui, `FAILSAFE=True` y `PAUSE=0.15` no negociables, mapa de monitores ctypes (EnumDisplayMonitors/GetSystemMetrics), `tecla_pynput`, `fallar_por_failsafe`; reexporta `_core` con forma exacta `nombre = _core.nombre` | La consciencia DPI de un proceso solo puede fijarse UNA vez y pynput necesita per-monitor para que sus coordenadas cuadren con las capturas: de ahí el orden de importación deliberado; los módulos exclusivos no pueden redefinir helpers (lo audita `problemas_redefiniciones()`) | Los CLIs raíz en win32 (bind `c`); `win_especiales.py` |
| `scripts/autotest.py` | SUITE UNIFICADA multi-OS (1742 L): checks de estructura/dinámicos de lectura, ciclo sandbox de escritura, modo golden, SKIPs honestos y JSON resumen con veredicto | Una sola suite para los 3 SO (las suites de rama murieron con los 16 motores viejos del enrute SEG2); en win32 corre la batería histórica completa + estáticos SEG3; en linux/darwin corre lo auditable sin hardware y marca las baterías ajenas como SKIP CON MOTIVO (nunca FAIL por limitación de entorno) | Relanzada por la portada; spawnea TODOS los CLIs por subprocess |
| `scripts/monitores.py` | Mapa de monitores y pantalla virtual: `listar` (rects + bloque `virtual` + `marco` + `via`) y `cursor` (qué monitor contiene el puntero) | Paso 1 del bucle (una vez por sesión): el agente no puede asumir geometría — resolución/monitores cambian entre sesiones y el orden del índice no está garantizado; en Windows usa ctypes puro, en Linux xrandr/swaymsg/hyprctl, en macOS Quartz (fallback system_profiler/osascript) | El agente; `pantalla.py`/`raton.py`/`ventanas.py` comparten su geometría vía `_core` |
| `scripts/pantalla.py` | Ojo de la skill: `capturar` (por monitor/región/`--max-lado` → PNG en `.tmp/capturas/` + JSON con `origen`, `px_por_unidad_coord`, `escala`, `marco`, `regla`), `tamano`, `posicion`, `pixel`, `esperar` (fijo o adaptativo por pixel; IMPL-K: `--mientras` lanza un disparador hijo y `--auto-pixel` escanea una región para elegir el pixel que cambia) y `localizar` (solo primario) | En Windows captura con `ImageGrab.grab(all_screens=True)` y NO con `pyautogui.screenshot(region=)`: con x negativa pyscreeze recorta sin restar el offset del bounding y produce imagen NEGRA (trampa verificada); `--max-lado` baja tokens de visión sin perder precisión porque la regla devuelve el factor TOTAL | El agente (visión); `--mientras` spawnea otros CLIs raíz; la suite lo ejerce en lectura y escritura |
| `scripts/teclado.py` | `escribir` (ASCII por pyautogui, unicode real por pynput con autodetección, o `--via portapapeles`; en Linux añade `wtype`/`ydotool`, en macOS `osascript`), `tecla`, `combo`, `mantener`; flags `--requiere-foco "sub"` y `--foco-id N` leen el foco ANTES de emitir y abortan sin teclear | Lección W11: pyautogui en Windows descarta en silencio los no-ASCII (mapea solo 32-127); y en apps multi-ventana (Notepad 11) el TITULO es contenido compartido y cambia al teclear: el incidente de la pestaña equivocada originó `--foco-id` (IMPL-K P0.1) — solo el hWnd es estable. En macOS `--foco-id` responde error honesto: la rama no tiene id estables | El agente; `win_especiales.py portapapeles --pegar` lo reinvoca para el ctrl+v |
| `scripts/raton.py` | `mover`, `click` (botón/doble), `arrastrar` (press→trayectoria→release garantizado), `scroll` vertical/horizontal, `posicion` (canon plano con `por_backend`) | Backend por destino: dentro del primario pyautogui (tween/PAUSE históricos); FUERA, siempre pynput — el clamp de pyautogui 0.9.54 está solo COMENTADO (conducta no documentada: prohibido depender); el scroll va SIEMPRE por pynput porque `pyautogui.hscroll` en Windows es alias del scroll VERTICAL (rueda sin avisar); checa FAILSAFE y banderas en cada paso interpolado | El agente; en Wayland orquesta `ydotool` (uinput: `mousemove --absolute`, clics 0xC0/0x4x/0x8x) |
| `scripts/ventanas.py` | `listar`, `foco` (`--con-dueno`: pid/owner del hWnd), `activar/minimizar/restaurar/maximizar/cerrar` (por título O `--id N`), `cerrar --descartar` (ladder anti-modal), `mover --monitor|--x --y` (SetWindowPos), `ocupantes x1 y1 x2 y2` (read-only) y `abrir` (programa/URL/archivo con `--esperar`, `--titulo`, `--esperar-nueva` por diff de hWnd) | Decisiones-incidente W11: (a) el sheet de guardado vive en la MISMA HWND → `cerrar` responde ok y la ventana persiste → ladder `cerrar→activar→alt+n→tab+enter→verificación POR ID`; (b) session-restore/tab-hijack: la "ventana nueva" a veces es pestaña en la ventana ajena → `--esperar-nueva` + id; (c) Win+Shift o arrastrar la barra FALLARON sintéticamente (rect inmutable) → verbo `mover` real; (d) `abrir` nunca pasa por cmd (Popen shell=False / `os.startfile`: el agente no necesita `start`) | El agente; el ciclo sandbox de la suite; `linux_especiales`/`macos_especiales` aportan las primitivas de su rama |
| `scripts/vigilar.py` | Watchdog humano: `arrancar --segundos N [--tecla-panic esc] [--pausar-si-humano]` — listener pynput que distingue entrada humana de la inyectada (`injected`) y crea `.tmp/ABORT` (dura) o `.tmp/PAUSA` (suave) | Sin el filtro `injected` el bot dispararía su propia pausa (bucle de realimentación); los callbacks SOLO marcan eventos (I/O en el hilo principal: un callback lento en el hook LL congela la entrada de TODO el equipo); NUNCA `suppress=True` (dejaría al usuario sin teclado); regla de lanzamiento: proceso APARTE (`start ""` sin `/b` o `DETACHED_PROCESS`) porque un heredado muere con el pipe del agente | El agente en segundo plano; los CLIs leen sus banderas vía `_core.checar_abort/checar_pausa` |
| `scripts/windows/win_especiales.py` | Único archivo de `scripts/windows/`: `portapapeles leer/escribir --respaldar/estado/restaurar` (nunca imprime contenido), `procesos listar/matar --pid N --confirmar [--arbol] [--forzar]`, `ejecutar --elevado` (UAC), `dpi listar` | Existe porque Windows tiene primitivas SIN parangón en las otras ramas y huecos que el flujo genérico no cubre: `teclado --via portapapeles` destruía el contenido del usuario (de ahí el respaldo rotativo + `restaurar`); el GATE MULTI-VENTANA de `procesos matar` (>1 ventana visible del PID = bloqueado) nace del INCIDENTE VERIFICADO: `taskkill` sobre el proceso compartido de Notepad 11 cerró 3 ventanas del usuario con rc=0 (P0.2); rc 2 con JSON si se ejecuta fuera de Windows (vía guard de `glue_windows`) | El agente; la suite prueba el gate con su propio PID |
| `scripts/linux/linux_especiales.py` | Único archivo de `scripts/linux/`: LIBRERÍA de primitivas X11/Wayland (xrandr/swaymsg/hyprctl monitores, grim captura, wtype/ydotool input, wmctrl/xdotool ventanas, xclip portapapeles, detección de sesión, `run_ok` JSON-safe) + CLI solo-Linux (`sesion`, `xrandr`, `grim`, `portapapeles`, `wayland-status`) | Contract "TODO se ejecuta sobre Python": los subprocess son IMPLEMENTACIÓN, no superficie del agente; X11 y Wayland se resuelven AQUÍ (no hay motor aparte) y el CLI raíz declara la ruta en `via`; el guard de plataforma vive SOLO en su `__main__` (rc 2 "dominio EXCLUSIVO") porque como librería debe ser importable en cualquier SO para que la suite la audite | Las secciones linux de los 6 CLIs raíz (bind `c`); el agente para diagnóstico del dominio |
| `scripts/macos/macos_especiales.py` | Único archivo de `scripts/macos/`: LIBRERÍA de primitivas (osascript `on run argv` anti-inyección, System Events, `screencapture`, Quartz monitores/cursor, tablas kVK_/alias darwin, hints TCC, escala Retina, failsafe emulado) + CLI solo-macOS (`tcc`, `screencapture`, `monitores-quartz`, `ventanas-se`, `open`) | Los datos del usuario viajan SIEMPRE por argv de `osascript`, nunca interpolados en el AppleScript (riesgo de inyección; VERIFICADO man); el equivalente del problema DPI de Windows aquí es RETINA 2x: lo resuelve `escala_retina()` + la regla del JSON; sin pyautogui en mac la superficie se fija en pynput+Quartz+CLI para que el JSON sea idéntico al dominio Windows | Las secciones mac de los 6 CLIs raíz; el agente para diagnóstico/TCC |
| [references/windows-python.md](references/windows-python.md) | Pirámide del SO Windows (qué capa hace qué y por qué): DPI, monitores, ImageGrab, portapapeles, procesos, FAILSAFE, UIPI/apps elevadas, unicode/scroll + lecciones runtime W11 (3 monitores, 06/10/2026) | Doc de SO, no de librería: se abre al escribir código ad-hoc en Windows o dudar de la pirámide; sus URLs son CITAS (no las descargues ni ejecutes) | El agente cuando SKILL.md §7 lo indica |
| [references/monitores-multi.md](references/monitores-multi.md) | Spec multi-monitor Windows verificada: espacio virtual y negativos, cómo listar, trampa `region=`, pynput vs clamp pyautogui, FAILSAFE en secundario, mover ventanas (SetWindowPos), DPI | Origen de la fase H (investigación + fetches Microsoft Learn/Pillow) que fijó el marco `px_fisicos_virtual` de toda la skill; leerla con ≥2 monitores o coords negativas | El agente en multi-monitor |
| [references/pyautogui-api.md](references/pyautogui-api.md) | Digest de PyAutoGUI 0.9.54 verificado contra fuente: firma, mapa ASCII 32-127 (no-ASCII descartado en silencio), `hscroll`=vertical disfrazado, FAILSAFE/PAUSE, límites de Windows | Existe para verificar la LIBRERÍA cuando un script falla o hay código ad-hoc — no para el flujo normal; justifica la pirámide (por qué pynput para unicode/scroll/exterior) | El agente ante duda de API |
| [references/pynput-api.md](references/pynput-api.md) | Digest de pynput 1.8.2: SetCursorPos sin clamp sobre el virtual, scroll V/H con signos, KEYEVENTF_UNICODE, listeners con `injected` y `IS_TRUSTED`, por qué nunca `suppress` | Fija la versión mínima 1.8.2 (≤1.8.1 duplicaba el scroll en Windows) y el contrato del watchdog (`injected`) | El agente ante duda de API |
| [references/linux-python.md](references/linux-python.md) | Dominio Linux: detección de sesión, pirámides X11 (XTEST) y Wayland (grim/wtype/ydotool/sway/hypr), marcos, límites honestos y §VERIFICADO/[runtime] con manpages citadas | Regla dura documental: afirmación sin URL va marcada [runtime] (nada se validó en Linux real desde esta máquina); documenta el estado "VERIFICADO [pendiente runtime]" de la fórmula ppu corregida | El agente en Linux |
| [references/macos-python.md](references/macos-python.md) | Dominio macOS: pirámide pynput/Quartz/osascript, TCC (3 permisos), Retina y la regla, screencapture, kVK_/media keys, anti-inyección argv, setup | Mismo protocolo de honestidad [runtime]; documenta los límites reales (AppleScript no tiene clic absoluto; "maximizar" no existe — zoom) | El agente en macOS |
| [references/comandos-sistema.md](references/comandos-sistema.md) | Rutas NATIVAS sin Python por SO (PowerShell SendKeys/CopyFromScreen/user32, xdotool/wmctrl/grim/ydotool, screencapture/osascript) + anti-patrones + VERIFICADO/INCERTO | Red de seguridad para el equipo donde NO se puede instalar Python/pip o para una tarea 100 % nativa sin ciclo de visión; su matriz §E es el mapa rápido | El agente sin stack Python disponible |
| `.tmp/.gitignore` | Guard del directorio temporal: `*` ignorado salvo el propio `.gitignore` | Privacidad por diseño: las capturas PNG son el ESCRITORIO REAL DEL USUARIO (ventanas, correos, datos sensibles) y las banderas/respaldos del portapapeles pueden contener secretos — JAMÁS deben commitearse; este guard viaja con la skill y es el único archivo del `.tmp` que se versiona | git (automático); la convención de ruta absoluta de los JSON apunta aquí |

## 3. El contrato JSON

### Campos comunes

- TODO lo que sale por stdout es JSON UTF-8 (dicts anidados, `ensure_ascii=false`);
  `json_out()`/`fail()` de `_core` son la ÚNICA vía de salida.
- `plataforma` (`win|linux|darwin`) está SIEMPRE presente (P0-4), incluso en
  los guards; los errores son `{"error": ...}` (+`pista`, `ventana_actual`,
  `uso`...) con rc 1. Los errores de argparse salen como JSON canónico
  (clase `Parser`), nunca como stderr de argparse.
- Donde hay coordenadas: `marco` (enum, abajo), `via` (fuente real de los
  datos: `ctypes EnumDisplayMonitors`, `xrandr/swaymsg`, `pygetwindow`,
  `pynput`...), `nota`/`regla` con la jerga del SO.
- El objeto `ventana` es canónico ANIDADO `rect{left,top,ancho,alto}` +
  `estado{minimizada,maximizada,activa}` + `id` + `app` (P1-2); Windows
  conserva además las claves planas históricas (superset: salida vieja
  intacta).
- Toda captura: `archivo` (ruta absoluta del PNG en `.tmp/capturas/`),
  `ancho/alto` de la imagen, `fisico`, `origen`, `escala`/`escala_y`,
  `px_por_unidad_coord`, `marco`, `regla`, `nota`.

### marco y unidades POR SO

| SO | `marco` | Origen y unidades | Captura → escala absorbida |
|---|---|---|---|
| Windows | `px_fisicos_virtual` | (0,0) = vértice sup-izq del monitor PRIMARIO; PIXELES FÍSICOS del espacio virtual; un monitor a la izquierda/arriba da coordenadas NEGATIVAS válidas | `ImageGrab all_screens` traduce negativos; DPI per-monitor unifica métricas/captura/inyección |
| Linux X11 | `px_layout` | (0,0) = vértice sup-izq del SCREEN completo (no del primario); negativos no documentados por xrandr ⇒ INCERTO, no los asumas | pyautogui + recorte PIL con offset xrandr |
| Linux Wayland | `px_layout` | layout del compositor (sway/hypr): offsets negativos posibles [runtime] | `grim` captura en coords de layout con `factor_grim` (2x si hay output HiDPI) |
| macOS | `puntos_logicos` | PUNTOS LÓGICOS del espacio global; (0,0) = sup-izq del display PRINCIPAL; monitores a la izquierda/arriba pueden dar negativos [runtime] | `screencapture` produce ~2× px por punto en Retina (`escala_retina`) |

### Regla de reescalado (campo único)

La fórmula que devuelve cada captura en `regla` es idéntica en los 3 SO:

```
coordenada = origen + px_en_la_imagen / px_por_unidad_coord   (DIVIDE)
```

`px_por_unidad_coord` es el factor TOTAL imagen→coordenada (ya incluye
`--max-lado`, grim y Retina): son píxeles-de-imagen por unidad de coordenada,
el INVERSO de `escala` (fuente→imagen). Cada rama lo construye a su manera:
Windows `1/escala_x`; Linux `factor_grim/escala_x`; macOS
`escala_retina/escala_x` (`null` si la vía `-D` sin mapa no permite medir la
escala: error honesto de reescalado).

Ejemplo numérico real (máquina W11 de la validación: primario 1920x1200 +
secundario de 1920x1080 a la IZQUIERDA ⇒ virtual x ∈ [-1920, 1919]):

1. `pantalla.py capturar --monitor 1 --max-lado 960`: la imagen mide 960 px de
   ancho sobre 1920 físicos ⇒ `escala_x = 2.0`, `px_por_unidad_coord = 0.5`,
   `origen = [-1920, 0]`.
2. La visión ubica un botón en la imagen (480, 300):
   `x = -1920 + 480 / 0.5 = -960`; `y = 0 + 300 / 0.5 = 600` ⇒ se clica en
   `(-960, 600)`, dentro del secundario.
3. Si el factor se reportaba INVERTIDO (usar `escala` en lugar de su inverso,
   como estaba antes del FIX W11), el clic caería en `-1920 + 480/2 = -1680`:
   descolocado un factor ppu² — este bug hubiese desviado todos los clics sobre
   capturas con `--max-lado` en multi-monitor. Con captura nativa ambos campos
   valen 1.0 y el error quedaba invisible.

### Errores y códigos de salida

- `rc 0`: éxito JSON. OJO: solo significa "no lancé excepción" — en apps
  elevadas el clic desaparece sin error; verifica SIEMPRE con captura.
- `rc 1`: error operativo canónico (`{"error": ...}`): fuera de la pantalla
  virtual, foco incorrecto (no se emitió nada), PID bloqueado por el gate,
  bandera ABORT activa, FAILSAFE disparado, herramienta ausente (con hint
  `apt/dnf`), etc.
- `rc 2`: GUARD DE RAMA — el CLI exclusivo de otro SO responde JSON ANTES de
  actuar, con el mecanismo exacto por rama: `linux_especiales.py`/
  `macos_especiales.py` llevan el guard en su `__main__` ("dominio EXCLUSIVO"
  antes de parsear, ya que como librería se importan en cualquier SO), mientras
  que `win_especiales.py` muere YA en el import de `glue_windows` (allí vive su
  guard de plataforma: JSON "exclusivo WINDOWS" + rc 2 en SO ajeno; sin
  `__main__` propio), plataforma desconocida, o la suite ausente.
  Nunca traceback.

### Flags de seguridad

- `--requiere-foco "SUBCADENA"` (teclado): el título foreground debe
  contenerla o ABORTA sin teclear. `--foco-id N`: el hWnd exacto del campo
  `id` de listar/foco/abrir — obligatorio en apps multi-ventana (el título es
  compartido y cambia al teclear; incidente Notepad multi-tab). En Linux el id
  es el de wmctrl/xdotool/sway; en macOS `--foco-id` responde error honesto
  (no hay id estables: identidad = par app+titulo).
- `--id N` (ventanas): destino por identificador estable en lugar del título
  (Windows hWnd, Linux id X11/Wayland; macOS: no disponible).
- `cerrar --descartar`: ladder anti-modal EXCLUSIVO Windows (error honesto en
  linux/mac; el sheet W11 vive en la misma HWND).
- `procesos matar --pid N --confirmar [--forzar]`: matar es IRREVERSIBLE y
  exige OK humano (`--confirmar`); GATE MULTI-VENTANA (P0.2, incidente
  taskkill/Notepad): >1 ventana visible del PID = BLOQUEADO, salvable solo con
  `--forzar` (el éxito queda con `aviso` en el JSON).
- FAILSAFE: siempre encendido, sin flag para apagarlo — llevar el cursor a
  CUALQUIERA de las 4 esquinas del monitor PRIMARIO aborta. En un secundario
  no hay esquina: el freno es `ABORT` o Ctrl+C. En Wayland nativo no aplica
  (no hay pyautogui); en macOS la skill EMULA la guarda de esquinas.
  Tras un abort la acción pudo quedar PARCIAL: re-captura antes de reintentar.
- `ABORT`/`PAUSA` (banderas en `.tmp/`, creadas por `vigilar.py`): ABORT corta
  acciones y esperas (chequeado al inicio y en cada paso interpolado); PAUSA
  (con `--pausar-si-humano`) frena solo el ARRANQUE de cada acción (tope 300 s,
  ABORT manda). Coste sin bandera: un `os.path.exists`.
- PAUSE fijo 0.15 s: subirlo es legítimo; bajarlo, no.

## 4. Flujo ideal por SO

### Windows 11 (ruta nativa validada en escritorio real)

Glue exclusivo: DPI per-monitor ANTES de pyautogui, `ImageGrab all_screens`
para monitores/región con negativos, `SetWindowPos` real en `mover`, y
`win_especiales` para portapapeles/procesos/UAC/DPI. Lecciones fijadas en el
diseño: la barra de menú de Notepad aparece con Alt y desplaza el lienzo
(clic hondo `TY+160`); el sheet de guardado es la MISMA HWND
(`cerrar --descartar`); session-restore/tab-hijack (guarda el `id` del diff de
`abrir --esperar-nueva` y dirige TODO con `--foco-id`); el autocorrect de W11
corrige lo inyectado (si un assert de texto falla: `--via portapapeles`); y
NUNCA `taskkill /IM notepad.exe` (comparte proceso: mata ventanas ajenas con
rc=0).

```bat
:: setup
py -m pip install pyautogui pynput pyperclip pygetwindow
py -m pip install opencv-python        :: opcional (localizar --confidence)

:: flujo abrir -> capturar -> leer -> actuar -> verificar -> cerrar
py scripts/ventanas.py abrir "<ruta\al\archivo.txt>" --esperar 8 --esperar-nueva
py scripts/pantalla.py capturar --max-lado 1280       :: leer el PNG con vision
py scripts/teclado.py escribir "Hola" --foco-id <id-del-json-abrir>
py scripts/raton.py click --x 640 --y 300
py scripts/pantalla.py esperar --milisegundos 600
py scripts/pantalla.py capturar                       :: verificacion
py scripts/ventanas.py cerrar --id <id> --descartar

:: valida tu instalacion
py autotest.py                    :: modo lectura (seguro)
py autotest.py --con-escritura    :: ciclo sandbox (SOLO un humano)
py autotest.py --golden comparar  :: byte-identity de las 15 salidas
```

### Linux X11 (pyautogui/pynput genéricos + primitivas xrandr/xdotool/wmctrl)

En X11 la entrada va por XTEST (pyautogui/pynput funcionan como en Windows) y
la librería `linux_especiales` orquesta xrandr (monitores), wmctrl/xdotool
(ventanas) y xclip (portapapeles). El marco es `px_layout` (ojo: (0,0) es del
SCREEN, no del primario; nunca asumas negativos). Requiere `DISPLAY` exportada
(cron/SSH headless es el fallo típico: el import de pyautogui es LAZY y
responde JSON accionable, no traceback).

```bash
# setup
python3 -m pip install pyautogui pynput pyperclip pillow   # [runtime] puede pedir python3-tk
sudo apt install xdotool wmctrl x11-xserver-utils xclip    # hints de linux_especiales.HINTS_PAQUETES

# flujo sesion -> mapear -> capturar -> leer -> actuar -> verificar
python3 scripts/linux/linux_especiales.py sesion
python3 scripts/monitores.py listar
python3 scripts/pantalla.py capturar --max-lado 1280       # leer el PNG con vision
python3 scripts/ventanas.py foco
python3 scripts/teclado.py escribir "Hola" --foco-id <id>  # id de listar (wmctrl/xdotool)
python3 scripts/raton.py click --x 640 --y 300
python3 scripts/pantalla.py capturar                        # verificacion

# valida tu instalacion
python3 autotest.py [--con-escritura] [--golden]   # la bateria Windows sale SKIP con motivo
```

### Linux Wayland (sin pyautogui: grim/wtype/ydotool/sway-hypr desde la raíz)

pyautogui/pynput NO alcanzan clientes nativos Wayland (XTEST es del servidor
X); el mismo CLI raíz resuelve la sesión y orquesta por subprocess interno:
`grim` (captura en coords de layout), `wtype`/`ydotool` (input: `mousemove
--absolute`, clics por máscara 0xC0/0x4x/0x8x), `swaymsg -t get_tree`/`hyprctl`
(ventanas). Limitaciones HONESTAS declaradas por el código: scroll inexistente
(ydotool 1.0.4 no implementa rueda → error + workaround Page_Up/Page_Down),
`vigilar.py` sin listener global (error JSON; toca crear `.tmp/ABORT` a mano o
Ctrl+C), cursor no legible (`monitores.py cursor` falla en Wayland), formato
de xrandr/negativos del compositor = [runtime]. ydotool exige el demonio
`ydotoold` y grupo `input`.

```bash
# setup
sudo apt install grim slurp wtype ydotool sway          # + arrancar ydotoold; hyprland si ese es tu WM
python3 -m pip install pillow                            # composicion/pixel sobre los PNG de grim

python3 scripts/linux/linux_especiales.py wayland-status  # sesion + tools + verbos resueltos
python3 scripts/pantalla.py capturar --monitor 1          # grim -o <output>
python3 scripts/raton.py mover 640 300                    # ydotool mousemove --absolute
python3 scripts/raton.py click --x 640 --y 300            # ydotool click 0xC0
python3 autotest.py                                       # estructura/dispatch/estaticos; baterias reales SKIP
```

### macOS (TCC como prerequisito; pynput/Quartz; puntos lógicos)

PREREQUISITO: los 3 permisos TCC sobre el binario Python (o el terminal que lo
lanza): **Accesibilidad** (input; el watchdog reporta `is_trusted` desde
`Listener.IS_TRUSTED`), **Grabación de pantalla** (sin él, `screencapture`
devuelve ventanas ajenas en negro) y **Automatización** (osascript → System
Events; denegado = err -1743; reset: `tccutil reset AppleEvents`). El ratón
va por pynput/Quartz (AppleScript NO tiene clic absoluto); el tipeo unicode por
`CGEventKeyboardSetUnicodeString`; los datos viajan SIEMPRE por argv de
osascript (anti-inyección); Retina se absorbe en `px_por_unidad_coord`.
"Maximizar" no existe (el botón verde es zoom): honesto; y sin hWnd estable:
`--foco-id`/`--id` responden error honesto → foco por `--requiere-foco` +
captura de verificación.

```bash
# setup
pip3 install pynput==1.8.2 pyobjc-framework-Quartz pillow
pip3 install opencv-python        # opcional (localizar)

python3 scripts/macos/macos_especiales.py tcc          # catalogo de hints de permisos
python3 scripts/monitores.py listar                     # Quartz o fallback system_profiler
python3 scripts/pantalla.py capturar --max-lado 1280    # leer el PNG con vision
python3 scripts/ventanas.py foco
python3 scripts/teclado.py escribir "España ñ" --requiere-foco "TextEdit"
python3 scripts/raton.py click --x 640 --y 300          # pynput (CGEvent) en puntos logicos
python3 scripts/pantalla.py capturar                    # verificacion
python3 autotest.py [--con-escritura] [--golden]        # bateria Windows/otras ramas: SKIP con motivo
```

## 5. Cómo se prueba a sí misma

El punto de entrada es la portada (`py autotest.py` / `python3 autotest.py`),
que delega en la suite UNIFICADA `scripts/autotest.py`. Tres modos:

- **Lectura (defecto, seguro)**: batería completa de la ruta del SO anfitrión
  sin teclear, sin mover el cursor y sin clic — las únicas escrituras son PNGs
  en `.tmp/` y el listener PASIVO de `vigilar.py` durante 1 s. Los errores de
  parser se prueban contra rutas que abortan ANTES de emitir. Corre además los
  checks estáticos multi-OS (en CUALQUIER SO): inventario del layout y ausencia
  de redefiniciones (`_core.problemas_estructura()`), dispatch verificado por
  LECTURA DE FUENTE de los 6 CLIs (marcas `_core.modulo_sistema` +
  `construir_parser_linux` + `construir_parser_mac`, y AUSENCIA del retirado
  `enrutar(`), que `glue_windows.py` no mencione las ramas ajenas, `py_compile`
  + importabilidad en cualquier SO de los especiales, guard rc 2 "EXCLUSIVO" de
  los CLIs exclusivos de los SO que no son el anfitrión, fórmula ppu de
  linux/mac como check ESTÁTICO, y contrato documentado. Corrida real en la
  máquina W11 (06/10/2026): 70 filas — 63 OK, 0 FAIL, 7 SKIP.
- **Escritura (`--con-escritura`, solo humano)**: ciclo SANDBOX de 19 filas
  (W0–W18) con VENTANA GARANTIZADA (P1.4 — reemplazó al viejo gate "0 Notepads
  del usuario"): escribe `.tmp/cu_sandbox_<hex8>.txt` (nombre único ⇒ título
  único, CONVIVE con los Notepads del usuario), lo abre con
  `abrir --esperar-nueva`, dirige TODO el ciclo por `--foco-id`/`--id`
  (click/escribir ASCII+unicode/backspace/undo/doble/arrastrar/scroll/
  mover --monitor/mantener/esperar --pixel), prueba el GATE de `procesos matar`
  con su propio PID (exige rc=1 sin matar) y cierra con `cerrar --id
  --descartar` exigiendo desaparición POR ID. En `finally` solo mata el PID
  dueño EXCLUSIVO del hWnd propio (N==1 verificado con EnumWindows); si el PID
  comparte ventanas ⇒ FAIL-con-motivo y NUNCA kill (la corrida
lectura+escritura suma 86 filas: 70 − 3 SKIPs de sandbox + 19 de W).
- **Golden (`--golden captura|comparar`, ruta Windows)**: byte-identity de 15
  salidas canónicas guardadas en `.tmp/golden/` (rc + stdout + stderr); en
  lectura los 9 casos deterministas se ejecutan DOS veces y deben dar bytes
  idénticos; los 6 "vivos" (ventanas/cursor del usuario en medio) quedan
  EXENTOS de identidad y solo se validan como JSON+rc esperados.

Salida siempre: tabla `[funcion | comando | OK/FAIL/SKIP | evidencia]` + JSON
resumen `{modo, total, pasados, fallados, skips, veredicto, fallas}`; exit 0
solo si no hay FAIL reales. **Qué significa cada SKIP**: limitación de
hardware/entorno con motivo (un solo monitor ⇒ la prueba del secundario se
OMITE, no falla), batería real de otro SO no portada (Linux 53+15, macOS
47+15 checks equivalentes, retiradas con las suites de rama), modo seguro (el
sandbox espera `--con-escritura`), asociación `.txt` que no es un editor, o
"pendiente @D" en contrato documentado. Un FAIL en modo lectura = bug de un CLI
de la raíz: reportar, no parchar a ciegas.

## 6. Decisiones que ya no están (anti-regresión)

- **Enrutadores subprocess (FASE SEG2) → CLIs unificados en la raíz (SEG3)**:
  los 6 CLIs de rama relanzaban el Python del "motor" propio por subprocess.
  Se ELIMINÓ el enrute (`plan_enrute`/`destino_rama`/`enrutar(`): cada CLI raíz
  ejecuta la ruta de su SO EN EL PROPIO PROCESO bindeando `c =
  _core.modulo_sistema()` en tiempo de ejecución (parchable por pruebas). La
  suite exige ahora por lectura de fuente que ningún CLI conserve `enrutar(`;
  no recrear el patrón.
- **Motores por rama + suites de rama → un único `<so>_especiales.py` por
  carpeta y UNA suite**: los 16 motores viejos de linux/ y macos/ (con sus
  `autotest.py` de rama: 53/15 y 47/15 checks) fueron retirados; las
  primitivas que realmente hablaban con el SO BAJARON a la librería exclusiva
  (cuerpos VERBATIM, partición no reinvención) y cmd_*/genéricos quedaron en
  la sección del SO dentro del CLI raíz. El autotest audita el layout: cada
  carpeta guarda SOLO su especial.
- **Los tres `_compartido*.py` → `_core.py`**: todo lo idéntico (Parser,
  banderas, validaciones, esperas, geometría, tablas, destino de capturas)
  subió a una copia stdlib-pura; los exclusivos solo pueden REEXPORTAR
  (`nombre = _core.nombre`), lo audita `problemas_redefiniciones()`.
- **Qué se cosechó del `.tmp/` de la fase de pruebas y por qué el resto se
  borró**: los drivers de la validación W11 multi-monitor se convirtieron en
  verbos/código permanente — `b3_ciclo*.py`/`b3_cierre_junk.py` → ladder
  `cerrar --descartar`; patrón de 12 drivers *by_id* → ciclo sandbox por hWnd
  y `_ventanas_por_id()` de la suite; `p2_restaurar.py` (56 líneas) → verbo
  `portapapeles restaurar`; `.tmp/byte_identity.py` → `--golden` de la suite;
  `.tmp/run_suite.py` → la nota de invocación fiel del docstring (por
  subprocess, sin wrappers .bat que mentían el veredicto); las lecciones →
  `windows-python.md` §13. El resto (PNGs de prueba, scratch `.txt`, dry-runs)
  es RESIDUO REGENERABLE de ejecuciones: se borró porque `.tmp/` es
  intencionadamente descartable y su guard anti-commit lo mantiene fuera de
  git. No reconstruir esos drivers: su función vive hoy en la skill.
- **Gate "0 Notepads del usuario" y kill-all en `finally`** (mortales ambos en
  el incidente W11): sustituidos por sandbox con ventana GARANTIZADA por nombre
  único + muerte solo del PID dueño exclusivo, con el gate multi-ventana.

---

**Cierre**: basado en validación real Windows 11 multi-monitor — 86 filas en la
corrida completa lectura+--con-escritura (70 en solo lectura) — ramas linux/mac
pendientes de hardware real (06/10/2026).
