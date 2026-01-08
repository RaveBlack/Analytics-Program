## Controller Tools (safe / non-injecting)

This folder contains a small **controller input monitor** you can use to:

- Sample controller state at a fixed interval (default **0.1s**)
- Visualize axes + buttons
- Apply and tune **deadzone + response curve + smoothing** for *analysis*
- Log to CSV so you can graph inputs later

**Important**: this tool does **not** simulate/inject controller inputs into games.

---

## Install

```bash
python3 -m pip install -r controller_tools/requirements.txt
```

## Run

Default settings:

```bash
python3 controller_tools/controller_monitor.py
```

Use the example config:

```bash
python3 controller_tools/controller_monitor.py --config controller_tools/config.example.json
```

Override options:

```bash
python3 controller_tools/controller_monitor.py --sample 0.1 --deadzone 0.12 --gamma 1.6 --alpha 0.35 --log controller_log.csv
```

Quit with **ESC** (or close the window).

---

## Packaging as an executable (recommended: PyInstaller, Python 3)

If you want a standalone executable for personal use:

```bash
python3 -m pip install pyinstaller
pyinstaller --onefile --name controller-monitor controller_tools/controller_monitor.py
```

Your binary will be in `dist/`.

