# LockMaker

Personaliza la **pantalla de bloqueo**, la **pantalla de inicio de sesión** y el **fondo de escritorio**
con un overlay estilo *reproductor* (día de la semana, fecha, hora, barra y controles), como en la imagen de referencia:

```
            S A T U R D A Y
            05 APRIL, 2025.
               - 13:27 -
      00:00 •──────────────── -00:00
             ◁◁    ▷    ▷▷
```

* **Ligero**: ~1 000 líneas de Python + una única dependencia (`Pillow`). Sin Electron, sin servicios residentes.
* **Editor visual** en tu navegador (servidor local en `127.0.0.1`, nunca sale de tu PC).
  Vista previa en ~0,1 s, arrastra el texto con el ratón, rueda para escalar.
* **Modo automático**: título/fecha/hora en `auto` → se rellenan con el día real. Con *Auto-actualizar*
  la imagen se vuelve a generar y aplicar sola (Programador de tareas en Windows, `systemd --user` en Linux).
* **Presets** incluidos (referencia Saturday, versión en español, centrado, minimal, oscuro con desenfoque) y los tuyos.
* **Exporta PNG** a la resolución que quieras (Full HD, QHD, 4K, ultrawide…).
* **16 wallpapers originales** incluidos (`wallpapers/`, 2560×1440, ~2 MB), generados proceduralmente por
  `tools/make_wallpapers.py` (regenerables a otra resolución: `python tools/make_wallpapers.py --size 3840x2160`).
  Los cuatro últimos (Iris azul, Bokeh violeta, Cristales, Mechones) usan la paleta de la imagen de referencia.
* **Buscar más**: el panel de wallpapers tiene un buscador que abre Wallhaven, Pixabay, Unsplash, Pexels, Pixiv o Google Imágenes
  con tu consulta; copias la dirección de la imagen y la pegas en "Desde URL".
* **Tus propios wallpapers**: pega una URL en el editor ("Desde URL") y se descarga a `wallpapers/`, o copia
  archivos (jpg/png/webp) a esa carpeta; aparecen en la galería con miniatura automática. Clic derecho para borrarlos.
  Para arte de terceros (p. ej. ilustraciones de anime) respeta la licencia del autor: úsalo en tu PC, no lo redistribuyas.

## Fondos animados (GIF / MP4 / WebM)

Sección **Animación** del editor. Origen: la imagen actual, un **GIF animado que subas** (se respeta su animación y se
le pone el overlay encima) o un fondo **procedural animado** (Aurora, Mesh, Olas). Efectos en bucle perfecto:
zoom/paneo suave (Ken Burns), punto de la barra recorriendo la línea, pulso del texto y partículas (bokeh, nieve,
lluvia, estrellas). Exporta a GIF (sin dependencias, pesado: ~5 MB por cada 3 s a 960×540) o a **MP4/WebM si tienes
`ffmpeg`** (20–40× más ligero; es lo que conviene para fondo de escritorio).

**Dónde se puede usar**
* Bloqueo e inicio de sesión: **no admiten animación** en ningún sistema; se aplica el primer fotograma.
* Escritorio animado: necesita un reproductor de fondo. LockMaker lo detecta y le envía el archivo con el botón
  *Aplicar como fondo animado*:
  * Windows → **Lively Wallpaper** (libre y gratuito, Microsoft Store o <https://github.com/rocksdanister/lively>).
  * Linux Wayland (Hyprland/Sway/…) → `mpvpaper`. Linux X11 → `xwinwrap` + `mpv`. Se añade al autoarranque de la sesión.
  * KDE → plugin *Smart Video Wallpaper Reborn*; GNOME → *Hidamari*. (Se avisa con el enlace si falta el reproductor.)
* El GIF/MP4 también sirve para el móvil, Discord, OBS o Wallpaper Engine.

Consumo: un MP4 de 1080p en Lively/mpv usa decodificación por hardware (≈1–3 % CPU); un GIF es mucho más pesado
de reproducir, por eso se recomienda MP4. Generar 6 s a 15 fps en 1080p tarda ~15–20 s.

CLI: `python lockmaker.py animate --image foto.jpg --out fondo.mp4 --particles bokeh --preset "Saturday ES" --apply`
     `python lockmaker.py animate --proc "Aurora animada" --out aurora.gif --size 960x540`
     `python lockmaker.py live-stop`

## ¿Reemplaza algo del sistema?

**No.** LockMaker no sustituye ningún archivo ni componente del sistema (ni LogonUI, ni GDM, ni temas).
Solo escribe *configuración* apuntando a una imagen que genera en tu carpeta de datos:

| | Qué toca | Cómo se deshace |
|---|---|---|
| Windows · escritorio | la misma llamada que usa Configuración → Personalización | elige otro fondo en Configuración |
| Windows · bloqueo/inicio | claves de registro `PersonalizationCSP` (método oficial de MDM) y desactiva Windows Spotlight para tu usuario | `LockMaker.bat restore` |
| Linux · escritorio/bloqueo | `gsettings` / `kwriteconfig` / `xfconf` / `hyprlock.conf` / `swaylock/config` | elige otro fondo en tu escritorio |
| Linux · inicio de sesión | un archivo de configuración del greeter (`theme.conf.user` de SDDM, `lightdm-gtk-greeter.conf`, o `gdm-settings`) + copia de la imagen en `/usr/share/backgrounds/lockmaker/` | borra esa línea/archivo o cambia el fondo en el greeter |

Los sistemas no permiten un reloj "vivo" en la pantalla de bloqueo, por eso la hora se pinta en la imagen y, si activas
*Auto-actualizar*, se regenera y se vuelve a aplicar cada N minutos.

## Consumo de recursos (medido)

| Situación | RAM | CPU |
|---|---|---|
| Editor abierto, sin imagen | 27 MB | 0 % |
| Imagen 2,5 K cargada, en reposo | ~45 MB | 0,00 % |
| Moviendo controles (vista previa 960 px) | ~60 MB | 1 núcleo durante 30–75 ms por cambio |
| Render final 1080p | — | ~150 ms |
| Render final 4K + PNG | pico ~100 MB | ~1,6 s |

El servidor local no hace nada entre peticiones (0 % CPU); la pestaña del navegador es el otro consumidor
(~50–100 MB, se libera al cerrarla). La auto-actualización es un proceso que arranca, renderiza (<1 s) y termina;
no hay nada residente. Paquete: ~700 KB de código + ~2 MB de wallpapers.


## Ajustes rápidos (pestaña principal)

Un solo panel con la personalización que el sistema tiene repartida entre Configuración, Panel de control y registro.
**Lee los valores actuales** y solo cambia algo cuando tú lo tocas. No se inicia con el equipo ni sustituye la
Configuración del sistema; es un atajo a ella. Cada ajuste que cambias guarda antes su valor original
(`ajustes_originales.json` en tu carpeta de datos) y **Restaurar originales** lo deshace todo.

| Windows 10/11 | Linux (se muestran solo los que existen en tu escritorio) |
|---|---|
| Modo claro/oscuro (apps y sistema), transparencia, color de énfasis (manual o automático), énfasis en barra/Inicio y títulos | GNOME: estilo claro/oscuro, color de énfasis (47+), tema GTK, iconos, puntero |
| Barra: alineación, búsqueda, Vista de tareas, Widgets, **segundos en el reloj** | GNOME: segundos, día de la semana y fecha en el reloj, 12/24 h, % batería |
| Inicio/Explorador: recientes, extensiones, archivos ocultos, carpeta inicial, **menú contextual clásico** | GNOME: botones de ventana, esquina activa, centrar ventanas, animaciones |
| Bloqueo: Windows destacado, datos curiosos, desenfoque del inicio de sesión (admin) | GNOME: bloqueo automático, notificaciones en bloqueo, tiempo de apagado |
| Animaciones, tamaño de texto, tamaño del puntero | Luz nocturna y temperatura, tamaño de texto y de puntero |
| Botón *Reiniciar Explorador* + 12 accesos directos a `ms-settings:` | KDE: esquema de colores, énfasis, tema global, puntero, animaciones, color nocturno, un clic · Cinnamon y XFCE: temas, iconos, reloj, efectos |

Se abre como ventana de aplicación (Edge/Chrome en modo `--app`) si están instalados; si no, en una pestaña del navegador.

---

## Windows 10 / 11

1. Instala Python 3 desde <https://www.python.org/downloads/> (marca **Add python.exe to PATH**).
2. Doble clic en **`LockMaker.bat`**. Instala Pillow si falta y abre el editor en el navegador.
3. Carga tu imagen, ajusta el overlay y pulsa **Aplicar ahora**.
   * *Escritorio* se aplica al instante.
   * *Bloqueo* e *Inicio de sesión* piden permisos de administrador (diálogo UAC) — en Windows 11 ambas
     pantallas usan la misma imagen. Se desactiva también el fondo borroso del inicio de sesión para que se vea nítida.
   * Bloquea con `Win + L` para verlo.

Cómo lo hace: `SystemParametersInfo` para el fondo y la clave oficial **PersonalizationCSP**
(`HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP`) para bloqueo/inicio —
el mismo método que usan Intune/MDM; funciona en Home y Pro.

Para volver a la pantalla de bloqueo normal: `LockMaker.bat restore`.

## Linux

```bash
chmod +x lockmaker.sh
./lockmaker.sh
```
(o copia `lockmaker.desktop` a `~/.local/share/applications/` para tenerlo en el menú).

| Objetivo | Escritorios soportados |
|---|---|
| Fondo de escritorio | GNOME/Ubuntu/Pop/Budgie, KDE Plasma 5-6, XFCE, Cinnamon, MATE, LXQt, Deepin, Sway, Hyprland, otros (feh / nitrogen / xwallpaper / swaybg) |
| Pantalla de bloqueo | GNOME, KDE (kscreenlocker), Cinnamon, MATE, XFCE, Hyprland (hyprlock), Sway (swaylock), i3lock |
| Inicio de sesión | SDDM, LightDM (gtk / slick greeter), GDM (requiere `gdm-settings`) — pide contraseña vía `pkexec` |

Todo lo de usuario se aplica sin root. Nada queda residente: la auto-actualización es un *timer* de `systemd --user`.

---

## Línea de comandos

```
python lockmaker.py                               # editor
python lockmaker.py info                          # qué detecta en tu sistema
python lockmaker.py render --image foto.jpg --out salida.png --preset "Saturday ES" --set y=12
python lockmaker.py apply  --preset "Saturday ES" --image foto.jpg --targets wallpaper,lock
python lockmaker.py autorefresh --preset current --every 1 --targets wallpaper,lock
python lockmaker.py autorefresh --remove
```

### Mantener fecha y hora al día (opciones)

| Opción | Cómo | Precisión | Consumo |
|---|---|---|---|
| **Auto-actualizar** (botón del editor) | tarea programada que ejecuta `apply` | cada N min; en Windows además al iniciar sesión, bloquear, desbloquear y despertar | un proceso de <1 s por ejecución, nada residente |
| **Comando manual / tu propio scheduler** | `python lockmaker.py apply --preset current --targets lock,wallpaper` | cuando lo lances (cron, atajo de teclado, script) | idem |
| **Solo día y fecha + reloj del sistema** | preset *Bloqueo con reloj del sistema* (`show_time=false`) y auto-actualizar cada día | el reloj de la pantalla de bloqueo de Windows/GNOME/KDE es siempre exacto | mínimo |
| **Fecha fija** | escribe el texto en Título/Fecha/Hora en vez de `auto` | — | ninguno |

`current` es el preset que el editor guarda cada vez que pulsas Aplicar (`%LOCALAPPDATA%\LockMaker\presets\current.json`
o `~/.local/share/lockmaker/presets/current.json`). Puedes sobrescribir cualquier ajuste al vuelo:
`python lockmaker.py apply --preset current --set title=HOY --set date="{D} {d} {M}" --targets lock`.

### Formatos de fecha/hora (modo auto)
* Fecha: `{d}` día · `{d:02d}` con cero · `{M}` mes · `{m}` nº mes · `{Y}` año · `{D}` día de la semana  
  ej. `{D}, {d} DE {M} DE {Y}` → `VIERNES, 23 DE OCTUBRE DE 2026`
* Hora: `{H}:{i}` 24 h · `{h}:{i} {p}` 12 h · `{s}` segundos

## Estructura
```
lockmaker.py          CLI + servidor del editor (stdlib http.server)
core/render.py        motor de render (Pillow)
core/animate.py       animación: GIF de entrada, efectos en bucle, partículas, GIF/MP4/WebM
core/platform_win.py  Windows: SPI + PersonalizationCSP + schtasks
core/platform_linux.py Linux: gsettings / kwriteconfig / xfconf / hyprlock / swaylock + DM helper + systemd timer
ui/                   editor web (HTML/CSS/JS sin frameworks)
fonts/                Poppins (SIL OFL)
presets/              presets incluidos
samples/              imagen de referencia
wallpapers/           16 fondos originales (+ miniaturas); aquí van también los tuyos
tools/make_wallpapers.py  generador de los fondos
```

Los datos del usuario (imagen fuente, renders, presets) se guardan en
`%LOCALAPPDATA%\LockMaker` (Windows) o `~/.local/share/lockmaker` (Linux).
