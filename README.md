# klipper-tui

A terminal UI for Klipper 3D printers. It does most of what you would open
Mainsail or Fluidd for — watch temperatures, run a print, jog the toolhead,
send gcode, look at the bed mesh, check the webcam — without leaving the
terminal.

It talks to [Moonraker](https://moonraker.readthedocs.io/), the API server that
already runs alongside Klipper on your printer's host (usually a Raspberry Pi).
Moonraker is what Mainsail and Fluidd talk to as well, so if either of those
works in your browser, this will work too. Nothing is installed on the printer
itself; this is a client you run on your own machine.

**What you need**

- A printer running Klipper with Moonraker, reachable over the network.
- Its address — the same host you type into your browser for Mainsail, e.g.
  `10.3.10.29` or `mainsailos.local`.
- Python 3.10 or newer on the machine you run this from.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Run

```bash
.venv/bin/klipper-tui 10.3.10.29
# or
KLIPPER_HOST=10.3.10.29 .venv/bin/klipper-tui
```

Use `-p/--port` if Moonraker is not on 7125.

## Tabs

| Key | Tab | Contents |
| --- | --- | --- |
| `d` | Dashboard | Printer state, job progress, position, temperatures, presets, extruder |
| `c` | Console | Live gcode responses and a command input with `↑`/`↓` history |
| `m` | Move | Homing, jog controls, and a rotating 3D view of the build volume |
| `f` | Files | G-code file browser plus print/pause/resume/cancel |
| `b` | Mesh | Bed mesh calibration and a colour heightmap |
| `w` | Webcam | Live MJPEG feed with pause and frame-rate control |
| `g` | Graph | Temperature history for hotend and bed, with target lines |

| `s` | Settings | Choose which panels appear on the dashboard |

`Ctrl+E` sends an emergency stop. `t` cycles themes. `q` quits.

## Themes

Ships with `ominous` (default, dark with burgundy), `mainsail`, and `forge`,
plus a selection of Textual's built-ins. Choose one on the Settings tab, pass
`--theme`, press `t` to cycle, or use the command palette (`ctrl+p`). The
choice is saved.

Colours come from theme tokens rather than literals, so panels, charts, and
the 3D view all follow the active theme.

### Writing your own

Themes live in `klipper_tui/theming.py`. A theme is a Textual `Theme` plus a
`variables` dict carrying the colours specific to this app. Copy an existing
one and change the values:

```python
MIDNIGHT = Theme(
    name="midnight",
    dark=True,
    background="#080b12",   # furthest back: the screen
    surface="#111722",      # panel cards sit on this
    panel="#1a2130",        # button faces, borders derive from it
    primary="#2f5d8a",      # filled buttons, progress bars
    secondary="#24455f",
    accent="#4d8fc4",       # panel titles, active tab, focused input
    foreground="#d3dae6",   # body text
    success="#4a7c59",      # homed axes, "at temperature"
    warning="#c08238",      # unhomed, cold nozzle, paused
    error="#cf3b3b",        # errors, e-stop, disconnected
    variables={
        "hot": "#e0754f",       # extruder trace on the graph
        "hot-dim": "#6b3020",   # its target line
        "bed": "#6f9bd1",       # bed trace
        "bed-dim": "#2f4a6b",   # its target line
        "vol-frame": "#4d8fc4", # build volume wireframe
        "vol-floor": "#4a5468", # bed plane and grid
        "vol-head": "#e8c25a",  # toolhead marker
        "vol-drop": "#cf6b5a",  # drop line and floor crosshair
    },
)
```

Then add it to the registry near the bottom of the file:

```python
CUSTOM = {t.name: t for t in (OMINOUS, MAINSAIL, FORGE, MIDNIGHT)}
```

That is all — it appears on the Settings tab, in `--theme`, and in the `t`
cycle. To make it the default, set `DEFAULT_THEME = "midnight"`.

### Notes

The eight `variables` entries are required. A theme missing them will fail to
render the graph or the 3D view, which is why built-in Textual themes get them
backfilled from `NEUTRAL_DOMAIN` when they are registered.

Textual derives a large set of tokens from the ones above — `$panel-lighten-2`
for borders, `$text-muted` for labels, `$surface-darken-1` for the chart
background, and so on — so the eleven colours here style the whole app.

Pick `background`, `surface`, and `panel` as three steps of the same hue
rather than pure greys; the separation between them is what makes panels read
as cards. `accent` should be legible against `surface`, since panel titles use
it.

Two colours deliberately do **not** come from the theme. The bed mesh
heightmap uses a fixed blue→green→red gradient, because it encodes measured
values and needs to stay comparable between themes. The console resolves
colours to concrete hex at write time, because `RichLog` renders Rich markup
and cannot read `$token` styles.

## Dashboard

Any panel can be shown on the dashboard as well as on its own tab — toggle
them on the Settings tab. Panels are created and destroyed as you toggle, so
one that is switched off does no work. Settings are saved to
`$XDG_CONFIG_HOME/klipper-tui/settings.json`.

## Webcam rendering

The webcam pulls MJPEG snapshots and draws them with
[textual-image](https://pypi.org/project/textual-image/). How good it looks
depends entirely on the terminal:

| Terminal | Best available | Flag |
| --- | --- | --- |
| xterm (`xterm -ti vt340`), konsole, foot, contour, mlterm, wezterm | true sixel | `--render sixel` |
| kitty, ghostty, wezterm | Kitty graphics protocol | `--render tgp` |
| gnome-terminal, most VTE terminals | unicode half-blocks | `--render halfcell` |

`--render auto` (the default) detects support and picks the best option.
**gnome-terminal has no sixel support**, so it falls back to half-blocks;
run under konsole or `xterm -ti vt340` for a true sixel image.

### Pointing it at your camera

The webcam tab asks your printer for one still image at a time and redraws it,
so it needs a URL that returns **a single JPEG** each time it is fetched — a
"snapshot" URL. It is not a video stream.

By default it tries:

```
http://<your-printer-host>/webcam/?action=snapshot
```

which is where MainsailOS and FluiddPi put it. If your camera shows up in
Mainsail, that address is usually already correct and you do not need to change
anything.

**If the tab shows a 404 or a connection error**, set the URL on the Settings
tab (`s`) — type it in, press Apply, and it is saved for next time. You can
also pass `--webcam-url`, or set `$KLIPPER_WEBCAM_URL`. Reset returns to the
default.

**Finding the right URL.** In Mainsail, go to Settings → Webcams and look at
the configured camera; the "Snapshot URL" field there is exactly what this
wants. Failing that, these are the common ones — try each in a browser, and use
whichever shows a still photo:

| Setup | Snapshot URL |
| --- | --- |
| MainsailOS / FluiddPi (default) | `http://HOST/webcam/?action=snapshot` |
| Second camera on the same host | `http://HOST/webcam2/?action=snapshot` |
| mjpg-streamer on its own port | `http://HOST:8080/?action=snapshot` |
| crowsnest / ustreamer | `http://HOST/webcam/snapshot` |
| Generic IP camera | often `http://HOST/snapshot.jpg` or `/jpg/image.jpg` |

Replace `HOST` with your printer's address. A URL ending in `action=stream` is
the *video* feed — this app wants `action=snapshot` instead.

**A camera bound to localhost.** Some setups run the camera server listening on
`127.0.0.1` only, so it is reachable from the printer but not from your desktop.
Those work in Mainsail because a proxy on the printer forwards `/webcam/` to it.
Use the proxied `http://HOST/webcam/?action=snapshot` form rather than the
port-specific one in that case.

**Frame rate** is set with the buttons on the tab (1–10 fps). Snapshots are
re-fetched and re-encoded every frame, so higher rates cost bandwidth and
redraw time; 2 fps is plenty for watching a print.

## Notes

- Jog and extrude commands are wrapped as `G91 … G90` and `M83 … M82`. Klipper keeps
  absolute/relative mode as persistent state, so a jog that errors out mid-script can
  otherwise leave the printer in relative mode and break the next print.
- Extrude, retract, and load/unload are blocked below `min_extrude_temp` (170°C), which
  Klipper would reject anyway.
- Load/unload use the printer's own `LOAD_FILAMENT` / `UNLOAD_FILAMENT` macros when they
  exist, and fall back to a plain relative extrude move when they do not.
- The mesh panel falls back to displaying a *saved* profile when no mesh is currently
  loaded, and labels it as inactive so a saved-but-unloaded mesh is not mistaken for
  an applied one.
