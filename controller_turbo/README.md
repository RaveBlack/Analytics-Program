## Xbox Controller Turbo (Linux)

This tool reads your physical Xbox controller and exposes a **virtual controller** that:

- Replays selected buttons as **turbo** (presses every 0.1s while held)
- Samples analog sticks / triggers at a **0.1s (10Hz)** interval and forwards those values

It’s useful for **local testing/accessibility**. Don’t use it to violate a game’s rules/terms (especially online/competitive play).

---

### Requirements

- Linux
- Python 3.10+
- A controller that shows up under `/dev/input/event*`
- Permissions to read input devices + create a uinput device (typically `sudo`)

---

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r controller_turbo/requirements.txt
```

---

### Find your controller device

```bash
sudo .venv/bin/python controller_turbo/turbo_pad.py --list
```

Then pick either a device path:

```bash
sudo .venv/bin/python controller_turbo/turbo_pad.py --device /dev/input/eventXX --turbo-all
```

Or pick by name substring:

```bash
sudo .venv/bin/python controller_turbo/turbo_pad.py --name "Xbox" --turbo-all
```

---

### Common usage

Turbo all buttons at 10 presses/sec, and sample analog at 10Hz:

```bash
sudo .venv/bin/python controller_turbo/turbo_pad.py --name "Xbox" --interval 0.1 --turbo-all
```

Turbo only some buttons (A/B/X/Y + bumpers) while forwarding everything else normally:

```bash
sudo .venv/bin/python controller_turbo/turbo_pad.py \
  --name "Xbox" \
  --interval 0.1 \
  --turbo BTN_SOUTH BTN_EAST BTN_WEST BTN_NORTH BTN_TL BTN_TR
```

Notes:
- By default the tool **grabs** the real controller so your system/game only sees the virtual one.
- If you want to allow the real controller to still be seen, add `--no-grab` (you’ll likely get double-input).

---

### Stop

Press `Ctrl+C`.

