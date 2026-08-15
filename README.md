# klipper-tui

A terminal UI for Klipper 3D printers, talking to [Moonraker](https://moonraker.readthedocs.io/)
over its JSON-RPC websocket. Styled to follow Mainsail's dark theme and panel layout.

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
plus a selection of Textual's built-ins. Pick one with `--theme`, cycle with
`t`, or use the command palette (`ctrl+p`). The choice is saved.

Colours come from theme tokens rather than literals, so panels, charts, and
the 3D view all follow the active theme.

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

Override the URL with `--webcam-url` or `$KLIPPER_WEBCAM_URL` if the snapshot
endpoint is not at `http://<host>/webcam/?action=snapshot`.

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
