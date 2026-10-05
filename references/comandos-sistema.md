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
fetcheadas** → §G antes de usar flags finos (`/FI`, `/T`).
Legado: `WScript.Shell.SendKeys` (VBS) → desaconsejado: mismo canal de inyección, sin soporte
moderno, requiere `wscript/cscript`; no verificado aquí (§G).

### A.4 Portapapeles: `clip.exe` `[pre]`
Sintaxis textual (https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/clip):
```bat
dir | clip
clip < readme.txt
```
Escribe **texto** en el portapapeles (la doc solo describe "redirects the command output ... to the
Windows clipboard" y apps "that can receive text"). No documenta lectura ni formatos ricos →
leer/conservar unicode completo: sin solución en clip.exe → usar PowerShell
`Get-Clipboard/Set-Clipboard` `[INC]` o pyperclip (la skill ya usa este último).

### A.5 Cuándo gana/pierde PowerShell frente a la skill
- **Gana**: cero dependencias (ni Python, ni pip, ni permisos extra) en equipos gestionados;
  portapapeles por pipe; captura PNG para el loop de visión con 5 líneas de PS.
- **Pierde**: no ve la pantalla por sí misma (el PNG debe releerse con visión, igual que la skill);
  ratón inexistente en SendKeys; sin drag/scroll/clic sin P/Invoke extra (SendInput no verificado
  aquí); teclado solo a la ventana activa (la skill sí activa ventanas: `ventanas.py activar`); sin
  FAILSAFE (el de pyautogui está en `SKILL.md` §5, "FAILSAFE encendido siempre").

---

## B. LINUX X11 — xdotool / wmctrl `[inst]` (estándar del ecosistema; no preinstalados en imágenes base)

### B.1 xdotool (manpage oficial Debian bookworm: https://manpages.debian.org/bookworm/xdotool/xdotool.1.en.html)
Usa XTEST + Xlib; "some support for EWMH".

```bash
# Teclado (formato de tecla: alt+r, Control_L+J, ctrl+alt+n, BackSpace; aliases alt/ctrl/shift/super/meta)
xdotool key ctrl+alt+t
xdotool key --clearmodifiers --delay 25 ctrl+l BackSpace   # --delay default 12ms
xdotool type --clearmodifiers 'Hello world!'
xdotool keydown shift ; xdotool key A ; xdotool keyup shift

# Ratón (botones: left=1, middle=2, right=3, wheel up=4, wheel down=5)
xdotool mousemove 640 300 --sync
xdotool mousemove_relative 10 -5
xdotool click 3                    # derecho
xdotool click --repeat 2 1         # doble clic (--repeat 2 = documentado)
xdotool mousemove 800 200 click 4  # scroll vertical (rueda arriba/bajo por botones 4/5)
xdotool getmouselocation --shell   # X= Y= SCREEN= WINDOW=
# Drag (el man no define comando 'drag'; composición con comandos verificados):
xdotool mousedown 1 ; xdotool mousemove --sync 400 500 ; xdotool mouseup 1

# Ventanas
xdotool search --name "Mozilla Firefox"          # regex; default busca --name --class --classname
xdotool search --class --onlyvisible firefox windowactivate
xdotool search --class google-chrome && xdotool key --window %@ ctrl+c   # [window] default "%1"
xdotool getactivewindow windowminimize
xdotool getactivewindow windowclose              # también windowkill
xdotool getactivewindow windowmove 100 100 ; xdotool windowsize %1 100% 50%
xdotool getwindowgeometry --shell %1 ; xdotool getwindowpid ; xdotool selectwindow
```

Detalles citados del man: `--clearmodifiers` "clear any active input modifiers during the command
and restore them afterwards"; `mousemove --sync` espera a que el ratón **se mueva** (no a llegar al
destino); `search --sync` bloquea hasta que la ventana exista (patrón lanzar-app→esperar-ventana);
`windowactivate`/`getactivewindow` requieren `_NET_ACTIVE_WINDOW` del WM (sección EWMH). El man de
bookworm **no documenta un comando `scroll`**: el scroll es `click 4/5` (§G).

### B.2 wmctrl (manpage oficial Debian bookworm: https://manpages.debian.org/bookworm/wmctrl/wmctrl.1.en.html)
"Solo interactúa con un WM compatible EWMH/NetWM" (NAME). Una acción por invocación.
```bash
wmctrl -l                 # listar (con wmctrl -p -G -l añade PID y geometría)
wmctrl -a firefox         # cambiar desktop si hace falta + raise + FOCUS
wmctrl -c 'Título'        # cerrar gracefully (con -i -r 0xID por id numérico)
wmctrl -r 'Título' -e 0,100,100,800,600    # mover/redimensionar (g,x,y,w,h; -1 = no cambiar)
wmctrl -r :ACTIVE: -b add,maximized_vert,maximized_horz   # maximizar
wmctrl -r :ACTIVE: -b add,fullscreen       # fullscreen
wmctrl -s 2 ; wmctrl -t 2 -r 'Título'      # desktop
```
**Corrección verificada**: las variantes "`-ir`/`-ic`/`-xx`" citadas en la solicitud original **no
existen como acciones** en el man: `-i` es opción (ID numérico), `-r` es objetivo, `-c` es cerrar;
`-x` incluye/interpreta WM_CLASS. **No hay acción iconify/minimizar** — para minimizar usa `xdotool
windowminimize` (B.1, verificado).

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

Herramientas verificadas (Arch wiki Wayland "Automation" y Screen capture):
- **ydotool** — "generic command-line automation tool (not limited to Wayland). Enable/start the
  `ydotool.service` user unit" (wiki Wayland). Repo oficial citado:
  https://github.com/ReimuNotMoe/ydotool. Sintaxis concreta de subcomandos `key/type/click` y
  permisos (grupo `input`/uinput/`ydotoold`): **no verificados** → §G [INC].
- **wtype** — "xdotool type for Wayland" (wiki Wayland). Repo citado: https://github.com/atx/wtype.
  Flags → §G [INC].
- **grim** — "grab images from a Wayland compositor" (wiki Screen capture, repo
  https://gitlab.freedesktop.org/emersion/grim). Uso textual verificado:
  ```bash
  grim screenshot.png                                   # pantalla completa
  slurp | grim -g - screenshot.png                      # selección interactiva de región
  slurp | grim -g - - | wl-copy                         # región al portapapeles
  swaymsg -t get_tree | jq -r '.. | select(.focused?) | .rect | "\(.x),\(.y) \(.width)x\(.height)"' | grim -g - win.png
  hyprctl -j activewindow | jq -r '"\(.at[0]),\(.at[1]) \(.size[0])x\(.size[1])"' | grim -g - win.png
  ```
  (`grimshot` de sway-contrib también mencionado en la wiki.)
- **Portapapeles Wayland**: `wl-copy`/`wl-paste` aparecen en el pipe citado (wiki) — paquete `[inst]`
  (wl-clipboard); persistencia: "el clipboard vive en la memoria del cliente" (wiki, wl-clip-persist).
- **XWayland**: apps X11 bajo Wayland siguen alcanzables por xdotool; detectarlas con
  `xwininfo`/`xlsclients` (wiki). Ventanas **nativas** Wayland no: xdotool usa XTEST/Xlib (man B.1),
  secc. VERIFICADO como causa.

---

## D. macOS

### D.1 `screencapture` `[pre]` — manpage oficial (mirror del man de Apple:
https://keith.github.io/xcode-man-pages/screencapture.1.html)
Flags textuales verificados:
```bash
screencapture -x captura.png                     # -x sin sonido
screencapture -x -R 100,200,800,600 region.png   # -R x,y,width,height
screencapture -l <windowid> ventana.png          # -l <windowid>
screencapture -i -w ventana_sel.png              # -i interactiva; -w solo-ventana; -s solo-seleccion
screencapture -c -o png_no_sombra.png            # -c al portapapeles; -o sin sombra de ventana
screencapture -m -D 2 multimon.png               # -m solo monitor principal; -D <display>
screencapture -t jpg -T 10 ret.jpg               # -t formato; -T <seconds> delay
screencapture -C con_cursor.png                  # -C captura cursor (solo no-interactivo)
```
"files: where to save the screen capture, **1 file per screen**" → sin ruta, destino interactivo por
defecto (Escritorio: práctica no verificada → §G [INC]). Security considerations textuales: para
capturar **vía SSH** hay que lanzar en la jerarquía mach de `loginwindow`:
`sudo launchctl bsexec <pid_loginwindow> screencapture [options]`.

### D.2 AppleScript/System Events `[pre]` — TODO [INC]
**La fuente oficial que lo verifica (guía de automatización de Apple, developer.apple.com) falló con
404 en esta investigación.** Por tanto todo el §D.2 se marca INCERTO (§G): `osascript -e 'tell
application "System Events" to ...'`, `keystroke`/`key code`, `click at`, `set frontmost`, `perform
action "AXMinimizeButton"` → **[INC], verificar con `man osascript` y el diccionario de System
Events en un Mac antes de fiar automatizaciones.** Lo afirmable con lo leído: screencapture por sí
solo no mueve teclado ni ratón; la ruta estándar del ecosistema es osascript+System Events, y para
clic/arrastre fino se usa cliclick `[3p]` (tercero, sin verificar licencia/estado → §G y §H). Sin
permisos **Accesibilidad** (teclado/ratón) y **Screen Recording** (capturas de contenido de otras
apps), los comandos fallan o devuelven negro; el detalle del fallo "-600 silencioso" es experiencia
comunitaria no verificada → §G [INC].

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
| Portapapeles ESCRIBIR | `clip` (texto) | `xclip/xsel` `[inst]` [INC flags] | `wl-copy` `[inst]` ✓mencionado | `pbcopy` [INC] |
| Portapapeles LEER | `Get-Clipboard` [INC] — clip.exe no lee | `xclip -o` [INC] | `wl-paste` ✓mencionado | `pbpaste` [INC] |
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
- xdotool: key/type/mousemove(_relative)/click(1-5, --repeat)/mousedown-up/getmouselocation --shell/
  search/windowactivate/windowminimize/windowclose/windowmove/windowsize/getactivewindow/getwindowgeometry/
  getwindowpid/selectwindow, --clearmodifiers, SENDEVENT NOTES →
  https://manpages.debian.org/bookworm/xdotool/xdotool.1.en.html
- wmctrl: -l -a -c -r -R -e -b -s -t -i -F -x -p -G, :ACTIVE:/:SELECT: (y ausencia de iconify) →
  https://manpages.debian.org/bookworm/wmctrl/wmctrl.1.en.html
- screencapture flags: -c -b -C -d -i -m -D -o -p -M -P -B -s -S -J -t -T -w -W -x -a -r -l -R -v -V
  -G -g -k -U -u + mach bootstrap + 1 file/screen → mirror del man Apple
  https://keith.github.io/xcode-man-pages/screencapture.1.html
- Wayland: ydotool (servicio+repo), wtype (repo atx), grim ("Wayland compositor"+repo freedesktop),
  slurp|grim -g -, grimshot, swaymsg/hyprctl+jq, wl-copy/paste, portapapeles efímero, detección
  XWayland → https://wiki.archlinux.org/title/Wayland y https://wiki.archlinux.org/title/Screen_capture

**INCERTO (reconocer ante el usuario; verificar antes de hardcodear):**
- `ShowWindow` y constantes nCmdShow (6=minimiza, 9=restaura): URL de la doc existe (winuser
  nf-winuser-showwindow) pero **no se fetcheó**.
- Flags de `taskkill/tasklist` (`/IM /F /T /FI`), `Get-Clipboard/Set-Clipboard`,
  `Get-CursorPosition`; VBS `WScript.Shell` legado; DPI del host PS en CopyFromScreen.
- macOS `osascript` CLI (`-e`), System Events `keystroke/key code/click at/set frontmost/perform
  action minimize`, ausencia de scroll nativo, permisos TCC y error -600, destino por defecto del
  screencapture interactivo, `pbcopy/pbpaste`, `sips` — **la guía Apple de UI scripting devolvió 404**;
  verificar en un Mac con `man osascript` y el diccionario de System Events.
- `gnome-screenshot -f/-w`, `spectacle -b/-n` (existencia sí verificada en wiki), `scrot -u`,
  `import -window <id>`, `xwd|convert`.
- xdotool `scroll` (no documentado en el man de bookworm; solo click 4/5) y botones 6/7 horizontales
  (fuera de la tabla del man).
- ydotool subcomandos/sintaxis exactos, daemon `ydotoold`, permisos grupo `input`; wtype flags;
  kdotool (no apareció en ningún fetch); layer-shell (concepto, no verificado).
- cliclick, AutoHotkey, NirCmd: existencia known, licencia/estado **sin verificar** (no fetcheados)
  → §H.

Limitaciones: 14 intentos de fetch, 10 con contenido (los VERIFICADO de arriba); fallidos:
man7.org/xdotool y man7.org/wmctrl (404, no hospeda esos manpages — sustituidos por manpages.debian.org),
developer.apple.com "AutomateYourApps" (404) y 1 URL mal formada propia (403). cliclick/nircmd/AutoHotkey
nunca se fetchearon → INCERTO por diseño. Quien ejecute en Mac debe validar `man osascript` y TCC
localmente antes de fiar automatizaciones a System Events (celda crítica de la matriz E).

---

## H. Otros caminos considerados [3p]

**nircmd, AutoHotkey, cliclick y kdotool** (y similares como wlrctl, citado en §C pero sin fuente)
son third-party `[3p]`: existencia conocida pero **ninguna fue verificada en esta investigación**
(0 fetches; licencia y estado sin comprobar) — figuran en §G como INCERTO. **No se recomiendan como
core**: el stack nativo de cada SO ya cubre lo esencial (captura, portapapeles de texto, procesos,
ventanas — matriz §E), y donde falta entrada fina de ratón/teclado sigue siendo más seguro el stack
Python de la skill o escalar el límite conocido (§F) antes que adoptar un [3p] no auditado.
