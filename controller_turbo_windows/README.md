## Xbox Controller Auto-Tap (Windows)

This tool makes a **virtual Xbox controller** on Windows and forwards your real controller input, with an optional **auto-tap** mode:

- When you press a button, it emits **one synthetic “tap”** (press now, release after `0.1s` by default).
- Sticks/triggers can be forwarded immediately or sampled at a fixed interval.

Use for local testing/accessibility. Don’t use it to violate a game’s rules/terms (especially online/competitive play).

---

### Requirements

- Windows 10/11
- Python 3.10+
- **ViGEmBus** driver installed (required to create a virtual Xbox controller)

Install ViGEmBus:
- Download/install from the ViGEmBus project releases (search “ViGEmBus release”).

---

### Install Python deps

```powershell
py -m venv .venv
.\.venv\Scripts\activate
pip install -r controller_turbo_windows\requirements.txt
```

---

### Build a standalone EXE (PyInstaller)

This produces `dist\turbo_pad_win.exe`.

PowerShell:

```powershell
.\controller_turbo_windows\build.ps1
```

Or CMD:

```bat
controller_turbo_windows\build.bat
```

---

### List controllers

```powershell
py controller_turbo_windows\turbo_pad_win.py --list
```

---

### Run (auto-tap selected buttons)

Auto-tap A/B/X/Y at 0.1s:

```powershell
py controller_turbo_windows\turbo_pad_win.py --interval 0.1 --auto BTN_SOUTH BTN_EAST BTN_WEST BTN_NORTH
```

Auto-tap “all common buttons”:

```powershell
py controller_turbo_windows\turbo_pad_win.py --interval 0.1 --auto-all
```

Pick a specific controller index from `--list`:

```powershell
py controller_turbo_windows\turbo_pad_win.py --index 0 --auto-all
```

---

### Important note (double input)

Windows will usually still expose your **real** controller to games *and* the **virtual** one, which can cause double input.

If you need only the virtual controller visible to a game, you’ll typically use a device-hiding tool (commonly “HidHide”). That’s optional and outside this script.

---

### Stop

Press `Ctrl+C`.

