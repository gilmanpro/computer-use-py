# LINUX — automatizacion de escritorio SIEMPRE via Python (referencia computer-use-py, FASE LX2)

> Dominio LINUX (investigacion 05/10/2026; 10 `webfetch`, uno fallido — fuentes
> en §VERIFICADO). Regla dura: afirmacion sin URL/verbatim lleva [runtime] =
> confirmar en la maquina Linux destino (NO se valido en escritorio desde
> Windows). Los CLIs de la raiz `scripts/<verbo>.py` replican el contrato JSON
> Windows en Linux (FASE SEG3: ejecutan la ruta de Linux en el propio proceso);
> las primitivas exclusivas X11/Wayland viven en la libreria
> `scripts/linux/linux_especiales.py`, que tiene ademas su CLI propio solo-Linux
> (`sesion`, `xrandr`, `grim`, `portapapeles leer|escribir`, `wayland-status`).

## Indice

§1 TODO-via-Python · §2 deteccion · §3 piramide X11 · §4 piramide Wayland ·
§5 ventanas X11 · §6 monitores X11 + quirk X-screens · §7 marco de coords ·
§8 ventanas/compositores Wayland · §9 captura · §10 teclado · §11 raton ·
§12 portapapeles · §13 quirks · §14 tabla tarea→ruta · §15 VERIFICADO/INCERTO ·
§16 DEPENDENCIAS (setup)

## 1. Supuesto base: TODO se ejecuta sobre Python

- El AGENTE solo invoca `python3 scripts/<script>.py <subcomando>` (CLIs de la
  RAIZ, multi-OS desde SEG3): verbos, JSON UTF-8 por stdout y error con
  "error" + exit 1, identicos al
  contrato Windows. En Linux ese CLI raiz ejecuta su ruta EN EL PROPIO PROCESO
  cargando como LIBRERIA `scripts/linux/linux_especiales.py`: por X11 usa
  xdotool/wmctrl/xrandr y por Wayland la ruta se resuelve VIA esa libreria
  (grim/wtype/ydotool/swaymsg/hyprctl orquestados desde el CLI raiz). Los
  `subprocess` internos (xdotool, wmctrl, grim, wtype,
  ydotool...) son IMPLEMENTACION, no "ejecucion del agente". X11 y Wayland se
  atienden desde los MISMOS verbos: el script elige la ruta por sesion (§2) y
  lo declara en el campo "via".

## 2. Deteccion X11 vs Wayland

- `XDG_SESSION_TYPE` (publicada por logind) = `x11|wayland`; reserva:
  `WAYLAND_DISPLAY` puesta ⇒ wayland; `DISPLAY` puesta ⇒ x11; nada ⇒ incognito.
  [runtime] (no fetcheado aqui). Implementado en
  `linux_especiales.deteccion_sesion()` (libreria; el CLI `linux_especiales.py
  sesion` la expone); toda salida trae "sesion".

## 3. Piramide X11: pyautogui/pynput SI funcionan

- Inyectan por XTEST del servidor X — mismo mecanismo del man de xdotool ("It
  does this using X11's XTEST extension and other Xlib functions", VERIFICADO):
  el input llega a TODAS las ventanas X11/XWayland sin importar el WM.
  pyautogui 0.9.54 + pynput 1.8.2 funcionan en X11.
- Exigen `DISPLAY` exportada (§13). Captura pyautogui: debajo Pillow ImageGrab
  (Linux/XCB) o scrot/gnome-screenshot segun pyscreeze — arbol [runtime];
  puede pedir python3-tk [runtime]. FAILSAFE=True y PAUSE=0.15 se fijan como
  en Windows (pyautogui importado LAZY: JSON accionable, nunca traceback)
  [runtime] el area de las 4 esquinas en X11.
- Scroll X11 = botones de rueda: "Left mouse is 1, middle is 2, right is 3,
  wheel up is 4, wheel down is 5" (man xdotool verbatim); laterales 6/7
  [runtime]. pynput/pyautogui emiten esos botones desde Python [runtime los
  signos en Linux]. Portapapeles: xclip -selection clipboard / pyperclip
  (xclip/xsel) [runtime].

## 4. Piramide Wayland: pyautogui/pynput NO

- XTEST es del servidor X: en Wayland NATIVO lo inyectado por pyautogui/pynput
  solo alcanza a ventanas XWayland, nunca a clientes nativos (wlroots/GTK4/Qt)
  [runtime; inference de los manuales: xdotool=XTEST y ydotool existe como
  "/dev/uinput automation tool" precisamente porque XTEST no llega a Wayland].
- Rutas por subprocess (implementacion; superficie Python): `wtype` teclado
  — TODOS sus flags (texto posicional, `-k`, `-s layout`) son [runtime]: el
  fetch del repo (https://github.com/redecipex/wtype) fallo 403/404 aqui.
  `ydotool`: demonio `ydotoold` obligatorio, socket por `YDOTOOL_SOCKET` (man
  verbatim), permisos uinput — grupo `input` [runtime]. `grim` (VERIFICADO
  §9), `slurp` region interactiva y `wl-copy/wl-paste` [runtime].
- Ventanas: `swaymsg -t get_tree` (VERIFICADO), `hyprctl` [runtime], `kdotool`
  (KWin/KDE) [runtime]. Compositor sin API auditada (GNOME, KDE sin kdotool):
  los scripts devuelven error honesto y el agente usa atajos del compositor.

## 5. Ventanas X11 (xdotool/wmctrl) — VERIFICADO en sus manpages

- `xdotool search [options] pattern` (regex sobre nombre/clase): `--name`,
  `--class`, `--classname`, `--onlyvisible` ("map state IsViewable"), `--pid`,
  `--limit`, `--maxdepth`, `--sync` ("Block until there are results").
- Verbos (man xdotool): `windowactivate [--sync]` (_NET_ACTIVE_WINDOW; "switch
  to that desktop... recommend trying before windowfocus"), `getactivewindow`
  ("often more reliable than getwindowfocus"), `windowfocus` ("Uses
  XSetInputFocus which may be ignored"), `windowminimize` (iconify),
  `windowmap` ("making it visible"), `windowunmap`, `windowclose` ("destroy
  the window... will not kill the client"), `windowkill`, `windowraise`,
  `windowmove [--sync] [--relative]`, `getwindowname`, `getwindowgeometry
  --shell`, `getwindowpid` (_NET_WM_PID, "may not work for some X
  applications"), `set_window --urgency 1`.
- `windowstate --toggle MAXIMIZED_VERT/HORZ`: NO aparece en la manpage de
  Debian (3.20160805.1) → la skill maximiza con wmctrl `-b` y deja windowstate
  como alternativa upstream [runtime] (github.com/jordansissel/xdotool).
- `wmctrl` (EWMH/NetWM): `-l` lista (columnas con `-p`/`-G`: id-hex, desktop
  −1=sticky, [pid], x-offset, y-offset, width, height, cliente, titulo);
  `-a <WIN>` = "switch to the desktop containing the window, raise... give it
  focus"; `-c` "close gracefully"; `-r` objetivo; `-i` id numerico (0x=hex);
  `-F` exacto (por defecto subcadena case-insensitive); `-x` WM_CLASS;
  `:ACTIVE:`/`:SELECT:`; `-e g,x,y,w,h` (−1 = "do not modify"); `-b
  add|remove|toggle,prop1[,prop2]` con estados "modal, sticky,
  maximized_vert, maximized_horz, shaded, skip_taskbar, skip_pager, hidden,
  fullscreen, above, below" y "two properties are supported... maximizing a
  window to full screen mode" → maximizar = `wmctrl -i -r ID -b
  toggle,maximized_vert,maximized_horz`.
- Foco real = hint _NET_ACTIVE_WINDOW que el WM aplica como quiere (spec EWMH
  citada por el propio man de xdotool) — de ahi el quirk GNOME de §13.

## 6. Monitores X11 (xrandr) y el quirk "cada monitor = X screen"

- `xrandr --listmonitors` / `--listactivemonitors` documentados (RandR 1.5:
  "Report information about all defined monitors"). El FORMATO de salida
  (`0: +*HDMI-1 1920/508x1080/286+0+0 HDMI-1`; `*`=primario, `+`=activo) NO
  esta en el man → parser tolerante y [runtime].
- `--primary`: "Set the output as primary. It will be sorted first in
  Xinerama and RANDR geometry requests" (verbatim). Tambien `--current`,
  `--pos xxy` y `--fb` ("All configured monitors must fit within this size").
- QUIRK: con MULTIPLES X SCREENS sin Xinerama las coords absolutas se ROMPEN
  (VERIFICADO, man xdotool verbatim): `mousemove --screen` "only useful if you
  have multiple screens and ARE NOT using Xinerama"; `getmouselocation` "Screen
  numbers will be nonzero if you have multiple monitors and are not using
  Xinerama" — cada pantalla tiene su propio (0,0) y el marco unificado deja de
  valer. El layout RandR normal (pseudo-Xinerama, un solo screen) SI es unificado.
- Negativos en X11: el espacio del servidor arranca en (0,0) y el man de xrandr
  no documenta offsets negativos → INCERTO; no los asuma. En Wayland el layout
  SI puede ser negativo [runtime] (grim trabaja "in layout coordinates").

## 7. Marco de coordenadas en Linux vs el marco Windows

- Windows (padre): (0,0) = sup-izq del PRIMARIO, negativos validos. X11:
  (0,0) = sup-izq del SCREEN completo; si el primario no esta en el extremo su
  offset xrandr no es (0,0) — por eso TODO JSON de captura lleva "origen" y el
  guard usa el bounding del mapa. Wayland: layout del compositor, negativos
  posibles [runtime]. Regla igual que Windows: leer `monitores.py listar` en
  cada arranque; nunca hardcodear.
- CONTRATO multi-rama (SPEC P0-4/P1-1/P1-2): todo JSON lleva `plataforma:
  "linux"` y `marco: "px_layout"` donde hay coordenadas; `raton.py posicion`
  es plano canonico `{x, y, marco, via, monitor, por_backend{...}}`; el objeto
  `ventana` de listar/foco/abrir es anidado `rect`+`estado` (`maximizada` via
  xprop `_NET_WM_STATE` en X11, `null` si no declarable); los errores de
  subcomando/`--via`/`--boton` salen JSON rc=1, nunca argparse rc=2.

## 8. Ventanas/compositores Wayland

- `swaymsg -t get_tree` = "Gets a JSON-encoded layout tree of all open windows,
  containers, outputs, workspaces"; `-t get_outputs` "Gets a list of current
  outputs"; el modo por defecto envia UN COMANDO sway "executed immediately"
  (man verbatim) → focus/kill/move scratchpad/fullscreen via `swaymsg
  "[con_id=N] <cmd>"` (selectores: sway(5) [runtime]; el man avisa del doble
  parseo de comillas y del `--` ante guiones; exit 0 ok / 1 swaymsg / 2 sway).
- Hyprland (`hyprctl monitors/clients/activewindow -j`, `dispatch`) y kdotool
  (KDE/KWin): [runtime] (no fetcheables en la investigacion). GNOME/KDE sin API
  auditada: los scripts devuelven error honesto "usa los atajos del compositor".

## 9. Captura

- X11: `pyautogui.screenshot()` = screen completo y recorte por monitor/region
  con PIL SOBRE esa captura usando el offset xrandr. La traduccion de
  `region=` de pyscreeze en multi-monitor Linux NO esta verificada: se evita
  deliberadamente (en Windows esa ruta deja la imagen negra: crop sin restar
  el offset del bounding — leccion aprendida y verificada ahi).
- Wayland (grim, man verbatim): `-g "<x>,<y> <width>x<height>"` "Set the
  region to capture, in layout coordinates"; `-g -` lee la region de stdin
  (pipeline con slurp, `grim -g \"$(slurp)\" archivo` [runtime]); `-o
  <output>` por nombre de output; `-s factor` default "the highest of all
  outputs"; `-c` incluye cursor; `-` como destino = stdout. Para `pixel` los
  scripts escriben PNG temporal en .tmp + PIL en vez de stdout (la envoltura
  run() es texto-seguro; binario crudo seria factible [runtime]).
- JSON de TODA captura (SPEC P0-3/P0-4 + FIX IMPL-K P0.3): `origen`,
  `marco:"px_layout"`, `plataforma:"linux"`, `escala`/`escala_y` (factor
  fuente→imagen del recorte --max-lado), `factor_grim` (el factor global que
  grim aplica en Wayland, "highest of all outputs", man verbatim — `null` si
  la fuente swaymsg no lo informa [runtime]) y
  **`px_por_unidad_coord` = factor_grim / escala** (con escala=1.0 sin
  --max-lado): el campo UNICO para re-escalar con la regla que DIVIDE
  (`coord_layout = origen + px_imagen / px_por_unidad_coord`), como en las
  otras ramas. ANTES estaba invertido (`escala × factor_grim`) — era el espejo
  exacto del bug W11 corregido en Windows: con `--max-lado` el clic salia
  descolocado un factor ppu² (derivado algebraicamente de
  `_core.escalas_thumbnail` = fuente/imagen). **VERIFICADO [pendiente
  runtime]: la formula nueva queda marcada §VERIFICADO aqui SOLO tras la
  prueba `--max-lado` + clic por regla en SO Linux real** (no hay Linux en la
  máquina de las pruebas W11; la suite unificada la audita como check
  ESTATICO de lectura de formula).
- Banderas de freno (P1-5/P1-6): `vigilar.py arrancar` (port X11; en Wayland
  error JSON honesto) crea `.tmp/ABORT` (dura: corta acciones al inicio y en
  los interpolados) y con `--pausar-si-humano` `.tmp/PAUSA` (suave: el arranque
  de cada accion espera; tope 300 s; solo si el backend distingue eventos
  inyectados).
- Scroll X11 `--garantizar-direccion`: fuerza `xdotool click 4/5` (arriba/
  abajo VERIFICADOS en man) cuando el signo de pynput [runtime] no cuadra.

## 10. Teclado

- X11: pyautogui `write/press/hotkey` (ASCII) + pynput (unicode segun layout
  XKB [runtime]). xdotool (subprocess interno): `key/keydown/keyup/type` con
  `--clearmodifiers`, `--delay ms`, alias ctrl/alt/shift/super/meta; "xdotool
  will automatically find an unused keycode" si tu teclado no tiene la tecla
  (verbatim); BUG declarado: "Typing unusual symbols under non-us keybindings
  is known to occasionally send the wrong character" (man §BUGS).
- Wayland: wtype (flags [runtime]) e `ydotool key CODE:1 CODE:0` — sintaxis
  VERIFICADA ("28:1 28:0 means pressing on the Enter button"; "See
  /usr/include/linux/input-event-codes.h for available key codes (KEY_*)";
  ejemplo LOL: 38=L, 24=O, 42=shift). La tabla KEY_CODES de teclado.py sigue
  ese header del kernel; valores salvo 28/38/24/42 = [runtime].

## 11. Raton

- X11: pyautogui moveTo/click/dragTo (marco §7; FAILSAFE activo) o xdotool
  `mousemove x y` ('restore' incl.), `mousedown/mouseup/click` botones
  1/2/3/4/5, doble clic `--repeat 2` (verbatim), `getmouselocation --shell`.
- Wayland (ydotool man verbatim): `mousemove` es "RELATIVE" por defecto +
  bandera `--absolute` documentada (`ydotool mousemove --absolute 100 100`) →
  la skill usa SIEMPRE --absolute (soporte absoluto real del uinput:
  [runtime]). Click por mascara "0x40 Mouse down / 0x80 Mouse up", botones
  0x00 LEFT 0x01 RIGHT 0x02 MIDDLE; verbatim 0xC0 left click, 0x41 right
  down, 0x82 middle up → click 0xC0/0xC1/0xC2; drag 0x4x→moves→0x8x
  [runtime C1/C2, 0x40/0x80: derivados de la regla].
- SCROLL Wayland: ydotool 1.0.4 SOLO implementa "type key mousemove click"
  (man verbatim); la rueda es eje REL_WHEEL, no boton → NO hay ruta: error
  honesto con workaround Page_Up/Page_Down [runtime]. Sin FAILSAFE aqui:
  freno = bandera ABORT o Ctrl+C; tras abort a medio drag suelta 0x8x.

## 12. Portapapeles

- X11: `xclip -selection clipboard` + `ctrl+v` [runtime] (pyperclip usa
  xclip/xsel [runtime]). Wayland: `wl-copy` + pegar con `ydotool key 29:1
  47:1 47:0 29:0` (ctrl+v; codigos [runtime]) — la combinacion la decide la app.

## 13. Quirks operativos

- DISPLAY vacia en cron/SSH/headless: exporta `DISPLAY=:1` (X11) o
  `WAYLAND_DISPLAY` + `XDG_RUNTIME_DIR` (Wayland); sin ellas pyautogui falla AL
  IMPORTAR — los scripts linux lo importan LAZY (JSON accionable, no traceback)
  [runtime].
- Focus-stealing prevention (GNOME y afines): `windowactivate`/`wmctrl -a` es
  una SOLICITUD _NET_ACTIVE_WINDOW que el WM interpreta: puede SOLO
  resaltar/parpadear sin dar el foco (semantica EWMH verificada; comportamiento
  GNOME [runtime]) → patron: activar + `foco` + capturar antes de teclear.
- Modificadores: xdotool ofrece `--clearmodifiers` antes de key/type (man);
  pyautogui/pynput mantienen estado interno — tras abort a media pulsacion
  suelta (`keyUp`/`ydotool key CODE:0`) y re-captura [runtime].

## 14. Tabla tarea → ruta X11 → ruta Wayland (CLI raiz `scripts/<verbo>.py`; primitivas en `linux_especiales.py`)

| Tarea | X11 | Wayland |
|---|---|---|
| Mapa monitores | `monitores.py listar` (xrandr --listmonitors, formato [runtime]) | swaymsg -t get_outputs / hyprctl monitors -j [runtime] |
| Cursor | xdotool getmouselocation --shell | NO legible con tools auditadas → error honesto |
| Captura | pyautogui.screenshot + crop PIL | grim (completo/-o output/-g region) |
| Pixel | pyautogui.pixel [runtime] | grim -g "x,y 1x1" + PIL |
| Mover | pyautogui.moveTo | ydotool mousemove --absolute |
| Clic / doble | pyautogui.click / xdotool click --repeat 2 | ydotool click 0xC0/0xC1/0xC2 [--repeat 2] |
| Arrastrar | pyautogui down/move/up (FAILSAFE) | ydotool click 0x4x + moves + 0x8x (finally) |
| Scroll | pynput, respaldo xdotool click 4/5 (6/7 horiz [runtime]) | sin ruta → error + Page keys [runtime] |
| Escribir ASCII | pyautogui.write | wtype [runtime flags] |
| Unicode | pynput (layout [runtime]) o xclip+ctrl+v | wtype / ydotool type / wl-copy |
| Tecla / combo | pyautogui hotkey/press; pynput reserva | wtype -k [runtime]; ydotool key CODE:1/0 |
| Ventanas listar | wmctrl -lpG | swaymsg -t get_tree / hyprctl clients -j [runtime] |
| activar/cerrar | wmctrl -i -a / -i -c | swaymsg focus / kill [runtime selector] |
| maximizar | wmctrl -i -r -b add,maximized_vert,maximized_horz | sway fullscreen [runtime] |
| minimizar/restaurar | xdotool windowminimize / windowmap+activate | sway move scratchpad / show [runtime] |
| abrir app/URL/archivo | Popen start_new_session / xdg-open [runtime]; --esperar por snapshot de ventanas | idem; --esperar solo con sway/hypr visibles |
| Freno humano | `vigilar.py arrancar` (pynput + injected si el backend lo da) → .tmp/ABORT/PAUSA; ABORT/Ctrl+C siempre | sin listener global → error JSON honesto; toca .tmp/ABORT a mano o Ctrl+C |

## 15. §VERIFICADO (fuentes) / §INCERTO ([runtime])

VERIFICADO con fetch 05/10/2026 (citas verbatim en las secciones):
- man xdotool (Debian bookworm, 1:3.20160805.1-5):
  https://manpages.debian.org/bookworm/xdotool/xdotool.1.en.html
- man wmctrl (Debian bookworm, 1.07):
  https://manpages.debian.org/bookworm/wmctrl/wmctrl.1.en.html
- man xrandr (Debian bookworm, x11-xserver-utils 7.7):
  https://manpages.debian.org/bookworm/x11-xserver-utils/xrandr.1.en.html
- man grim (Debian bookworm, 1.4.0; upstream github.com/emersion/grim):
  https://manpages.debian.org/bookworm/grim/grim.1.en.html
- man ydotool (Debian testing/unstable 1.0.4; upstream github.com/ReimuNotMoe/ydotool; codigos: include/uapi/linux/input-event-codes.h):
  https://manpages.debian.org/unstable/ydotool/ydotool.1.en.html
- man swaymsg (Arch, extra/sway 1:1.12-4):
  https://man.archlinux.org/man/swaymsg.1.en
- Spec EWMH citada por el man de xdotool:
  http://standards.freedesktop.org/wm-spec/wm-spec-1.3.html

INCERTO / [runtime] (confirmar en la maquina destino; NO fiar resultados sin
prueba): formato real de `xrandr --listmonitors`, `getwindowgeometry --shell`
y `search --onlyvisible`; XDG_SESSION_TYPE/WAYLAND_DISPLAY/DISPLAY; TODO wtype
(https://github.com/redecipex/wtype no cargo en la investigacion); hyprctl -j y
dispatch; kdotool; slurp; wl-clipboard; xclip; scrot; Pillow ImageGrab XCB y
el fallback de pyscreeze (https://pillow.readthedocs.io/en/stable/reference/
ImageGrab.html); pyautogui/pynput fuera de X11 (se espera fallo o solo
XWayland); signos de scroll pynput en Linux; botones 6/7; pyperclip;
focus-stealing prevention GNOME; permisos/absoluto uinput de ydotool; scroll
Wayland; negativos de layout Wayland; auto-repeticion de teclas mantenidas.

## 16. DEPENDENCIAS (setup: pip + apt/dnf)

- pip — la rama Python usa el mismo set que el padre Windows (SKILL.md §2):
  `pip3 install pyautogui pynput pyperclip pillow` (versiones verificadas:
  pyautogui 0.9.54, pynput 1.8.2 —con <=1.8.1 el scroll se duplica—,
  pyperclip 1.11.0, Pillow >= 6.2.0). `pygetwindow` NO aplica (es de la rama
  Windows: las ventanas van por xdotool/wmctrl/swaymsg, §5/§8).
  `opencv-python` OPCIONAL, solo para `localizar --confidence`. La captura
  pyautogui puede pedir python3-tk (§3) [runtime]. En Wayland nativo
  pyautogui/pynput NO aplican (§4): la ruta vive solo de las herramientas del
  SO + Pillow (composicion del PNG de grim, §9).
- Herramientas del SO en PATH — los scripts las buscan con shutil.which y, si
  faltan, responden hint apt|dnf accionable; la fuente CANONICA es
  HINTS_PAQUETES de `scripts/linux/linux_especiales.py`. Nombres apt
  verificados en el rastreo de manpages (xdotool, wmctrl, xrandr=
  x11-xserver-utils, grim, ydotool, sway=swaymsg); el resto [runtime] (§15):

  | Herramienta | apt (Debian/Ubuntu) | dnf (Fedora/RHEL) |
  |---|---|---|
  | xdotool | xdotool | xdotool |
  | wmctrl | wmctrl | wmctrl |
  | xrandr | x11-xserver-utils | xorg-x11-utils |
  | scrot | scrot | scrot |
  | grim | grim | grim |
  | slurp | slurp | slurp |
  | wtype | wtype | wtype |
  | ydotool | ydotool (arranca `ydotoold`; grupo `input`) | idem |
  | kdotool | kdotool [runtime] | kdotool [runtime] |
  | swaymsg | sway | sway |
  | hyprctl | hyprland [runtime] | hyprland [runtime] |
  | xclip | xclip | xclip |
  | xdg-open | xdg-utils | xdg-utils |
