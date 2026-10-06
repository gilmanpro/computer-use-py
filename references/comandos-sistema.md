# Comandos nativos del SO para control de escritorio (multiplataforma) — referencia computer-use-py

> Derivado del digest de investigación del 05/10/2026 (Microsoft Learn/MSDN, manpages Debian,
> Arch wiki, mirror del man de Apple). Solo hay afirmación sin URL en §G si está marcada [INC].
> Leyenda: `[pre]` = preinstalado/estándar del SO · `[inst]` = requiere instalar · `[3p]` = tercero
> no verificado · `[INC]` = no verificado en esta investigación (ver §G antes de hardcodear).

**CUÁNDO leer este archivo**: (a) equipo que no permite instalar Python/pip; (b) tarea 100 % nativa
del SO (captura, portapapeles, procesos, ventanas) sin ciclo de visión; (c) objetivo en macOS o Linux.

## Índice
- §A Windows (PowerShell como capa nativa)
- §B Linux X11 (xdotool, wmctrl, capturas)
- §C Linux Wayland (grim, slurp, ydotool, wtype)
- §D macOS (screencapture, osascript)
- §E Matriz tarea → comando por OS
- §F Anti-patrones multi-OS
- §G VERIFICADO (URLs) vs INCERTO
- §H Otros caminos considerados [3p]

---

## A. WINDOWS — PowerShell como capa nativa `[pre]`

PowerShell viene con Windows; no necesita pip. Es la alternativa cuando el equipo gestionado **no permite instalar Python/PyAutoGUI**.

### A.1 Teclado: `[System.Windows.Forms.SendKeys]` `[pre]`
Envía teclas **solo a la aplicación ACTIVA** (no hay API gestionada para activar otra ventana: hay
que combinar con `FindWindow`/`SetForegroundWindow` vía user32, A.3).

```powershell
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.SendKeys]::SendWait("^%s")        # Ctrl+Alt+S
[System.Windows.Forms.SendKeys]::SendWait("Hola{ENTER}")
[System.Windows.Forms.SendKeys]::SendWait("+{TAB 3}")   # Shift+Tab x3
[System.Windows.Forms.SendKeys]::SendWait("^(ec)")      # Ctrl mantenido sobre e,c
```

Sintaxis exacta, cita textual de la doc oficial (aplicada a `Send`, misma semántica que `SendWait`):

> "The plus sign (+), caret (^), percent sign (%), tilde (~), and parentheses () have special
> meanings to SendKeys. To specify one of these characters, enclose it within braces ({}). For
> example, to specify the plus sign, use "{+}". To specify brace characters, use "{{}" and "{}}"."
> — https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms.sendkeys.send

> Modificadores: "To specify keys combined with any combination of the SHIFT, CTRL, and ALT keys,
> precede the key code with one or more of the following codes: SHIFT +, CTRL ^, ALT %." Repetición:
> "{key number}... {LEFT 42}". Teclas nombradas: `{ENTER} o ~`, `{ESC}`, `{TAB}`,
> `{BACKSPACE}|{BS}|{BKSP}`, `{F1}–{F16}`, `{ADD}`, `{SUBTRACT}`, `{MULTIPLY}`, `{DIVIDE}`, etc.
> (tabla completa en la URL citada).

Pitfalls documentados en la misma página:
- `SendKeys` es **"susceptible a problemas de timing"**; intenta primero la implementación antigua y
  si falla usa la nueva, así que "puede comportarse de forma distinta según el sistema operativo".
- Con la implementación nueva, **`SendWait` no espera a que se procesen los mensajes enviados a OTRO
  proceso** (escribir desde PS hacia otra app es asíncrono en la práctica).
- `UAC/Vista`: la seguridad mejorada "previene que la implementación anterior funcione como se
  esperaba" (base del bloqueo a apps elevadas; la consecuencia práctica — no inyecta a una ventana
  elevated sin estar elevado — verificada en esta máquina: `SKILL.md` §1, "No uses: apps elevadas").
- Advertencia textual: "If your application is intended for international use with a variety of
  keyboards, the use of Send could yield unpredictable results and should be avoided." → para
  unicode/ñ/acentos sigue ganando pynput (`SKILL.md` §6, anti-patrón no-ASCII).
- `{PRTSC}` está **"reserved for future use"** en la tabla oficial → PrintScreen NO se puede mandar
  con SendKeys.
- **SendKeys no controla ratón** — clic/drag/scroll nativamente no existen aquí.

### A.2 Capturas: `System.Drawing.Graphics.CopyFromScreen` `[pre]`
Sobrecargas verificadas: `(Point,Point,Size)`, `(Int32 sourceX, sourceY, destX, destY, Size)` y
variantes con `CopyPixelOperation` —
https://learn.microsoft.com/en-us/dotnet/api/system.drawing.graphics.copyfromscreen

```powershell
# Pantalla completa
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap 1920,1080
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen(0,0,0,0,$bmp.Size)      # region: (x,y,x,y,(w,h))
$bmp.Save("$env:TEMP\captura.png")
$g.Dispose(); $bmp.Dispose()
```

`CopyFromScreen` lanza `Win32Exception` si falla (documentado). Nota DPI-awareness del host
PowerShell: comportamiento no verificado → §G. Alternativa interactiva sin escribir código: tecla
PrintScreen (requiere concentración; sin flags que inventar).

### A.3 Ventanas: user32.dll desde PowerShell
Firma verificada: `BOOL SetForegroundWindow(HWND)` —
https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow

```powershell
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class Win {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
}
'@
$p = Get-Process notepad | Select-Object -First 1
[Win]::SetForegroundWindow($p.MainWindowHandle)   # activa
[Win]::ShowWindow($p.MainWindowHandle, 6)         # minimizar  [INC: n=6/9 — constantes winuser.h no re-verificadas]
```

Restricción crítica (textual de la doc): el sistema **limita qué procesos pueden poner ventana en
primer plano** (foreground lock timeout, que el llamador sea el proceso foreground o recibió el
último input…); si el usuario está trabajando en otra ventana, "Windows flashes the taskbar button"
en lugar de activar → el `return` es engañoso para scripts; re-verificar con captura.
Gestión de proceso: `tasklist` / `taskkill /IM nombre.exe /F` `[pre]` — formas comunes, **páginas no
fetcheadas** → §G antes de usar flags finos (`/FI`, `/T`). En la skill ya son verbos JSON:
`scripts/win_especiales.py procesos listar|matar --confirmar` (el matar gatea humano).
Legado: `WScript.Shell.SendKeys` (VBS) → desaconsejado: mismo canal de inyección, sin soporte
moderno, requiere `wscript/cscript`; no verificado aquí (§G).

### A.4 Portapapeles: `clip.exe` `[pre]`
Sintaxis textual (https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/clip):
```bat
dir | clip
clip < readme.txt
```
Escribe **texto** en el portapapeles (la doc solo describe "redirects the command output ... to the
Windows clipboard" and apps "that can receive text"). No documenta lectura ni formatos ricos →
leer/conservar unicode completo: sin solución en clip.exe → usar PowerShell
`Get-Clipboard/Set-Clipboard` `[INC]` o pyperclip (la skill ya usa este último). DESDE LA SKILL:
el portapapeles ya está resuelto en Python con `scripts/win_especiales.py portapapeles
leer|escribir --respaldar|estado` (JSON del contrato; LEER existe ahora: era el hueco que esta
sección documentaba).

### A.5 Cuándo gana/pierde PowerShell frente a la skill
- **Gana**: cero dependencias (ni Python, ni pip, ni permisos extra) en equipos gestionados;
  portapapeles por pipe; captura PNG para el loop de visión con 5 líneas de PS.
- **Pierde**: no ve la pantalla por sí misma (el PNG debe releerse con visión, igual que la skill);
  ratón inexistente en SendKeys; sin drag/scroll/clic sin P/Invoke extra (SendInput no verificado
  aquí); teclado solo a la ventana activa (la skill sí activa ventanas: `ventanas.py activar`); sin
  FAILSAFE (el de pyautogui está en `SKILL.md` §5, "FAILSAFE encendido siempre").

---

## B. LINUX X11 — xdotool / wmctrl `[inst]` (estándar del ecosistema; no preinstalados en imágenes base)

### B.1 xdotool (teclado, ratón, ventanas) `[inst]` — man Debian bookworm VERIFICADO
Usa XTEST + Xlib; "some support for EWMH". Lista completa con citas verbatim del man
vive en `references/linux-python.md`: §5 (ventanas: `search [--name/--class/--onlyvisible/
--sync]`, `windowactivate`, `getactivewindow`, `windowminimize`, `windowmap`, `windowclose`,
`getwindowgeometry --shell`, SENDEVENT NOTES y el aviso `--window`), §10 (teclado: `key`,
`type`, `keydown/keyup`, `--clearmodifiers`, `--delay`, bug no-US) y §11 (ratón:
`mousemove [--sync]` — "--sync espera a que se MUEVA, no a llegar —, `mousemove_relative`,
`click 1/2/3/4/5` con `--repeat 2`, `mousedown/mouseup`, `getmouselocation --shell`).
Desde la shell sin Python se invocan literales: `xdotool <verbo> <args>` (p. ej.
`xdotool key ctrl+alt+t`, `xdotool mousemove 640 300 click 1`). El man de bookworm NO
documenta un comando `scroll`: la rueda son `click 4` (arriba) / `click 5` (abajo).

### B.2 wmctrl (EWMH/NetWM) `[inst]` — man Debian bookworm VERIFICADO
"Solo interactúa con un WM compatible EWMH/NetWM" (NAME); una acción por invocación.
Opciones con citas verbatim del man en `references/linux-python.md` §5: `-l` (+`-p -G`:
id-hex, desktop, PID, x, y, w, h, título), `-a <WIN>` (desktop+raise+focus), `-c`
(cerrar gracefully), objetivo `-r <TIT>/-i <ID>/:ACTIVE:/:SELECT:`, afinación `-F -x`,
mover/resize `-e g,x,y,w,h` (−1 = no cambiar) y estados `-b add|remove|toggle,
maximized_vert|maximized_horz, fullscreen, sticky, ...` (maximizar = `-b
add,maximized_vert,maximized_horz`). **Corrección crítica (índice del man): no hay
acción iconify/minimizar** — las variantes "`-ir`/`-ic`/`-xx`" que circulan por ahí no
existen; para minimizar usa `xdotool windowminimize` (B.1).

### B.3 Capturas X11 (Arch wiki "Screen capture": https://wiki.archlinux.org/title/Screen_capture)
- ImageMagick `[inst]`: `import -window root salida.png` ("import is part of the imagemagick
  package"). `import -window <id>` en forma general [INC] → §G.
- scrot `[inst]`: salva al directorio actual salvo indicación; `scrot ~/screenshots/%Y-%m-%d-%T.png`;
  `scrot -s` selección (con workaround `sleep 0.2; scrot -s` en dwm/xmonad). `scrot -u` [INC] → §G.
- gnome-screenshot `[inst]`: existe como paquete GNOME; flags CLI `-f/-w/-a` no vistos en la página
  → §G [INC].
- spectacle `[inst]`: KDE, "whole desktop, single window, region…; needs running plasma"; flags CLI
  sin verificar → §G [INC].
- `xwd | convert`: combinación clásica documentada fuera del alcance de los fetches → §G [INC].

### B.4 Cuándo X11-tools vs la skill Python
Los scripts de la skill (pyautogui/pynput) funcionan igual en X11 con Python disponible. El valor
del stack xdotool/wmctrl es **cuando no hay Python ni pip** (live-ISO, servidor mínimo, contenedor
con DISPLAY): un solo binario, chaining tipo `search --class X windowactivate key ctrl+t`, y
`getmouselocation --shell` para scripts. Contra X11 siempre requiere `DISPLAY` exportado + un WM/DE
EWMH corriendo.

---

## C. LINUX WAYLAND — honestidad primero: no hay comando universal "preinstalado"

"Wayland es solo el protocolo… no hay un display server común que instalar" (Arch wiki Wayland). La
inyección de entrada y la captura dependen del **compositor**; casi todo requiere instalar. Mapeo
desktop→herramienta con lo verificado:

| Entorno | Entrada | Captura |
|---|---|---|
| wlroots (sway/hyprland) | `ydotool` `[inst]`, `wlrctl` (virtual-keyboard/pointer) `[inst]` | `grim` `[inst]` (+ `slurp` `[inst]`) |
| KDE Plasma | `ydotool` (genérico) `[inst]`; kdotool §G [INC] | `spectacle` (también captura en Wayland "with kwin activated") `[inst]` |
| GNOME | sin herramienta CLI propia verificada; entrada vía `ydotool` `[inst]` | PrintScreen/GUI; captura CLI no verificada → §G [INC] |

Herramientas (uso nativo sin Python; detalle verbatim del man en `references/
linux-python.md`):
- **grim** — "grab images from a Wayland compositor": `grim salida.png` (layout
  completo); `slurp | grim -g - salida.png` (región interactiva); `-o <output>` por
  monitor. Man verbatim (`-g "<x>,<y> <W>x<H>"` en coords de layout, `-` = stdout,
  `-s` factor): `references/linux-python.md` §9.
- **ydotool** — automatización uinput genérica: habilitar/arrancar la unidad de usuario
  `ydotool.service` (ydotoold) y grupo `input`; sintaxis `key CODE:1 CODE:0`,
  `mousemove --absolute`, click por máscara 0x40/0x80: `references/linux-python.md`
  §10/§11 (repo: github.com/ReimuNotMoe/ydotool).
- **wtype** — "xdotool type for Wayland" (repo github.com/atx/wtype): flags exactos
  [INC] aquí; usados dentro de la skill en `references/linux-python.md` §4/§10.
- **Portapapeles Wayland**: `wl-copy`/`wl-paste` (paquete wl-clipboard `[inst]`,
  mencionado en la wiki); persistencia: "el clipboard vive en la memoria del cliente"
  (wiki, wl-clip-persist).
- **XWayland**: apps X11 bajo Wayland siguen alcanzables por xdotool; detectarlas con
  `xwininfo`/`xlsclients` (wiki). Ventanas **nativas** Wayland no: xdotool usa
  XTEST/Xlib, secc. VERIFICADO como causa.

---

## D. macOS

### D.1 `screencapture` `[pre]` — qué existe (el "cómo" vive en un solo sitio)
Uso nativo sin Python: `screencapture -x out.png` (toda la pantalla, sin sonido); variantes
por región/monitor/ventana/clipboard/interactiva. La tabla completa de flags verificados
(-x -R -D -l -o -r -t -C, con citas del man) y sus trampas: `references/macos-python.md` §4
(SPEC P2-3: este archivo no duplica el detalle).
"files: where to save the screen capture, **1 file per screen**" → sin flags no hay un
PNG único multi-monitor: capturar monitor a monitor y componer. Security considerations
textuales: para capturar **vía SSH** hay que lanzar en la jerarquía mach de
`loginwindow`: `sudo launchctl bsexec <pid_loginwindow> screencapture [options]`.

### D.2 AppleScript/System Events `[pre]`
La investigación sin-Python quedó 404 en la guía Apple; la verificación AVANZÓ en la
rama macOS con Python: `references/macos-python.md` §7 (man osascript VERIFICADO —
datos SIEMPRE por argv, nunca interpolados, anti-inyección; guía Apple VERIFICADA para
`process`/`set frontmost`/`click` de elemento; keystroke/key code/acciones AX quedan
[runtime] contra el diccionario del Mac). Sin permisos **Accesibilidad** (teclado/ratón)
y **Screen Recording** (contenido ajeno) los comandos fallan o devuelven negro. Para
clic/arrastre fino en coordenadas no hay AppleScript: la ruta real es pynput/Quartz
(macos-python.md §5) o cliclick `[3p]` (§H).

### D.3 Portapapeles e imágenes `[pre/INC]`
`pbcopy`/`pbpaste` (estándar BSD de macOS; página no fetcheada → §G [INC]). `sips` para medir/editar
imágenes (no fetcheado → §G [INC]).

---

## E. Matriz final — tarea → comando mínimo

| Tarea | Windows `[pre]` | Linux X11 | Linux Wayland | macOS `[pre]` |
|---|---|---|---|---|
| Tipear texto | `SendKeys.SendWait` (A.1) | `xdotool type` `[inst]` | `wtype`/`ydotool` `[inst]` | osascript `keystroke` [INC] |
| Hotkey | `SendWait("^%s")` | `xdotool key` | `ydotool key` [INC sintaxis] | osascript [INC] |
| Clic / derecho / doble | **sin opción nativa** → PyAutoGUI/pynput | `xdotool click 3` / `--repeat 2 1` | `ydotool` [INC] | **sin opción nativa** [INC; cliclick 3p] |
| Arrastrar | sin opción nativa | `mousedown 1; mousemove; mouseup 1` (B.1) | sin opción nativa verificada | sin opción nativa [INC] |
| Scroll V / H | sin opción nativa (pynput) | `click 4/5` ✓documentado; H (`6/7`) [INC, fuera del man] | sin opción nativa verificada | sin opción nativa (System Events sin scroll [INC]) |
| Captura pantalla | `CopyFromScreen` (A.2) | `import -window root` / `scrot` `[inst]` | `grim salida.png` `[inst]` | `screencapture -x f.png` |
| Captura ventana | CopyFromScreen + rect de la ventana (rect: sin verificar) | `import -window <id>` [INC forma general] / `scrot -s` | `swaymsg\|hyprctl ... \| grim -g -` (C) | `screencapture -l <id> -o f.png` |
| Captura región | `CopyFromScreen x,y,0,0 (w,h)` | `scrot -s` | `slurp \| grim -g -` | `screencapture -R x,y,w,h` |
| Listar ventanas | `tasklist` / `Get-Process` [INC] | `wmctrl -l` | compositor-specific (swaymsg get_tree ✓) | System Events `every window` [INC] |
| Activar ventana | `SetForegroundWindow` (A.3, con limites) | `wmctrl -a` / `xdotool windowactivate` | **sin opción universal** | `set frontmost` [INC] |
| Minimizar | `ShowWindow(h,6)` [constante INC] | `xdotool windowminimize` (wmctrl no puede) | sin opción universal | `perform action` [INC] |
| Cerrar ventana | `taskkill /IM x /F` [INC flags] | `wmctrl -c` / `xdotool windowclose` | sin opción universal | `quit` AppleScript [INC] |
| Portapapeles ESCRIBIR | `clip` (texto) · skill: `win_especiales.py portapapeles escribir` | `xclip/xsel` `[inst]` [INC flags] | `wl-copy` `[inst]` ✓mencionado | `pbcopy` [INC] |
| Portapapeles LEER | `Get-Clipboard` [INC] — clip.exe no lee · skill: `win_especiales.py portapapeles leer` | `xclip -o` [INC] | `wl-paste` ✓mencionado | `pbpaste` [INC] |
| Posición del cursor | sin opción simple nativa → PyAutoGUI | `xdotool getmouselocation --shell` | [INC] | [INC] |

Regla práctica: si hay Python, usa la skill (`computer-use-py`); estas tablas son para **cuando no lo hay** o para tareas 100 % nativas (captura, proceso, portapapeles de texto).

---

## F. Anti-patrones multi-OS (con por qué)

1. **SendKeys perdiendo teclas**: va "to the active application"; si cambia el foco a mitad de
   secuencia el resto se pierde en otra ventana (doc §A.1; `SKILL.md` §5 exige re-verificar el foco
   con captura). Activar antes con `SetForegroundWindow`/`ventanas.py`.
2. **Confiar en el bool de `SetForegroundWindow`**: el sistema restringe quién puede (foreground
   lock, etc.) y si el usuario está en otra ventana solo hace **parpadear la taskbar** — doc citada.
   Verifica con captura, no con el return.
3. **Inyectar a apps elevadas sin elevación**: UAC "previene que la implementación [de SendKeys]
   funcione como se esperaba" (doc A.1); en esta máquina confirmado también para pyautogui
   (descarte silencioso, `SKILL.md` §1 y §5).
4. **`{PRTSC}` con SendKeys**: reservado for future use (tabla oficial) → no captura.
5. **`clip.exe` para unicode/formatos o para LEER**: la doc solo define redirigir salida de comando
   como texto; no documenta lectura → `[INC]` su manejo BMP+; usa PowerShell/pyperclip.
6. **`xdotool --window` para escribir a apps que no usan ese hint**: "many programs observe the
   send_event flag and reject these events" (man, SENDEVENT NOTES) → prefiere windowactivate+entrada global.
7. **`windowactivate` sin `_NET_ACTIVE_WINDOW`** (WMs sin EWMH): el man lo lista como requisito de
   la sección EWMH → falla silenciosamente.
8. **wmctrl sin DISPLAY o sin WM EWMH/NetWM**: NAME lo declara; además **no hay minimizar** (B.2) —
   quien espere `-ir` obtiene error de sintaxis.
9. **xdotool en Wayland**: usa XTEST/Xlib (man B.1); solo funciona dentro de XWayland, no con
   ventanas nativas Wayland (causa citada; detección de apps XWayland por wiki §C).
10. **grim en sesión X11**: "grab images from a Wayland compositor" (wiki) → en Xorg usa
    `import/scrot`.
11. **Esperar que `--sync` de `mousemove` llegue al destino**: el man aclara que espera a que "se
    mueva", no a alcanzar x,y (apps con cursor atrapado).
12. **macOS sin TCC / `screencapture` por SSH sin bsexec**: SECURITY CONSIDERATIONS del man exige
    lanzar en la jerarquía de `loginwindow`; fallos por Accesibilidad/Screen Recording → §G.
13. **Asumir que Wayland tiene "el equivalente de xdotool" listo**: no existe; compositor-dependiente
    (wiki); instalar y configurar servicio (`ydotool.service`) es obligatorio.

---

## G. VERIFICADO vs INCERTO

**VERIFICADO (con URL):**
- `SendKeys.Send/SendWait`: definición, tabla de códigos `{...}`, modificadores `+ ^ %`, grupos
  `( )`, repeticiones, notas UAC/timing/SendInput, `{PRTSC}` reservado →
  https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms.sendkeys.send y `...sendwait`
- `Graphics.CopyFromScreen`: 4 sobrecargas (Point/Int32 + CopyPixelOperation), parámetros,
  `Win32Exception` → https://learn.microsoft.com/en-us/dotnet/api/system.drawing.graphics.copyfromscreen
- `SetForegroundWindow`: firma, condiciones de restricción, taskbar flash →
  https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow
- `clip` (sintaxis `<cmd> | clip`, `clip < archivo`) →
  https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/clip
- Linux (xdotool, wmctrl, xrandr, grim, ydotool, swaymsg, spec EWMH — con URLs y citas
  verbatim): `references/linux-python.md` §5/§6/§9/§10/§11 y §15.
- macOS (screencapture/osascript/open vía mirror del man + guía Apple — URLs y citas):
  `references/macos-python.md` §4/§7 y §12.

**INCERTO (reconocer ante el usuario; verificar antes de hardcodear):**
- `ShowWindow` y constantes nCmdShow (6=minimiza, 9=restaura): URL de la doc existe (winuser
  nf-winuser-showwindow) pero **no se fetcheó**.
- Flags de `taskkill/tasklist` (`/IM /F /T /FI`), `Get-Clipboard/Set-Clipboard`,
  `Get-CursorPosition`; VBS `WScript.Shell` legado; DPI del host PS en CopyFromScreen.
- Capturas X11 sin Python: `gnome-screenshot -f/-w`, `spectacle -b/-n` (existencia sí
  verificada en wiki), `scrot -u`, `import -window <id>`, `xwd|convert`.
- xdotool `scroll` (no documentado en el man de bookworm; solo click 4/5) y botones 6/7
  horizontales (fuera de la tabla del man).
- Linux Wayland y macOS sin Python: el inventario completo de [runtime]/INCERTOS (wtype,
  hyprctl, kdotool, permisos ydotoold; diccionario System Events, pbcopy/pbpaste, sips…)
  vive en `references/linux-python.md` §15 y `references/macos-python.md` §12.
- cliclick, AutoHotkey, NirCmd: existencia known, licencia/estado **sin verificar** (no fetcheados)
  → §H.

Limitaciones: 14 intentos de fetch en la capa sin-Python, 10 con contenido (los VERIFICADO
de arriba); fallidos: man7.org/xdotool y man7.org/wmctrl (404, sustituidos por
manpages.debian.org), developer.apple.com "AutomateYourApps" (404 → la verificación macOS
avanzó después, ver §D.2) y 1 URL propia mal formada (403). cliclick/nircmd/AutoHotkey nunca
se fetchearon → INCERTO por diseño.

---

## H. Otros caminos considerados [3p]

**nircmd, AutoHotkey, cliclick y kdotool** (y similares como wlrctl, citado en §C pero sin fuente)
son third-party `[3p]`: existencia conocida pero **ninguna fue verificada en esta investigación**
(0 fetches; licencia y estado sin comprobar) — figuran en §G como INCERTO. **No se recomiendan como
core**: el stack nativo de cada SO ya cubre lo esencial (captura, portapapeles de texto, procesos,
ventanas — matriz §E), y donde falta entrada fina de ratón/teclado sigue siendo más seguro el stack
Python de la skill o escalar el límite conocido (§F) antes que adoptar un [3p] no auditado.
