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
| `m` | Move | Homing and jog controls with selectable step size |
| `f` | Files | G-code file browser plus print/pause/resume/cancel |
| `b` | Mesh | Bed mesh calibration and a colour heightmap |

`Ctrl+E` sends an emergency stop. `q` quits.

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
