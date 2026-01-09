## Muse 2 “thought recorder” (realistic prototype)

This is a **practical** Muse 2 recorder + visualizer:

- Connects to a Muse EEG stream via **LSL** (Lab Streaming Layer)
- Records **raw EEG** channels
- Computes common EEG band powers (**delta/theta/alpha/beta/gamma**) from the raw stream
- Lets you mark an **“utterance” event** (hotkey or button) and type what was said/thought
- Saves everything to `recordings/<session>/` as CSV + JSON

### Important limitation (the “RGB pixel grid from vision” idea)

What you described (reconstructing what you see as a pixel grid / images from EEG at 50–100 Hz) is **not realistically achievable** with a Muse 2 (4 EEG channels, consumer-grade).

Reasons:

- **Spatial resolution**: Muse 2 has 4 EEG channels. Image reconstruction research typically uses **very high-density EEG**, **fMRI**, or **intracranial recordings (ECoG/Utah arrays)**.
- **Signal type**: Scalp EEG is dominated by low-frequency, mixed-source activity; it does not contain enough information to recover pixel-level visuals.
- **Training data**: Even in cutting-edge research, reconstruction requires **many hours of labeled training data** per subject and a powerful model. Muse-quality data is far below what those pipelines assume.

This project therefore implements a **record + label** pipeline (what *is* feasible), plus a “dot grid” visualization that is **just a live feature visualization**, not a real decoded image.

---

## Quickstart

### 1) Start Muse → LSL streaming

This app expects an LSL stream from Muse. The most common path is [`muselsl`](https://github.com/alexandrebarachant/muse-lsl).

Typical workflow:

1. Pair your Muse 2 via Bluetooth.
2. Start streaming (commands vary by OS; see muselsl docs).
3. Confirm an LSL stream exists (e.g. type `EEG`).

### 2) Install dependencies

From repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r muse_vision_recorder/requirements.txt
```

Or auto-install + run (source only):

```bash
python3 muse_vision_recorder/run_bootstrap.py
```

### Linux note (GUI)

The default GUI uses **Tkinter**. On some Linux distros you must install it separately (example):

```bash
sudo apt-get update && sudo apt-get install -y python3-tk
```

### 3) Run

```bash
python3 -m muse_vision_recorder
```

Or headless (no GUI):

```bash
python3 -m muse_vision_recorder --mode headless
```

---

## Controls

- **Start/Stop Recording**: starts writing CSV files to a new session folder.
- **Mark utterance**: prompts for a text label; also bound to **Space**.

---

## Output format

Each session writes:

- `metadata.json`: session info (sample rate, channel names, etc.)
- `eeg.csv`: timestamp + raw EEG per channel
- `bands.csv`: timestamp + band-power features
- `events.csv`: timestamp + event_type + label

---

## Build a Windows EXE

### Recommended: PyInstaller (simplest)

Build on **Windows** (PyInstaller does not cross-compile cleanly from Linux → Windows):

Use the provided spec (bundles `pylsl` / `liblsl` correctly, and includes lazy tkinter imports):

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r muse_vision_recorder\requirements.txt
pip install pyinstaller
pyinstaller --clean muse_vision_recorder\pyinstaller.spec
```

Output will be in `dist\MuseVisionRecorder\MuseVisionRecorder.exe`.

One-command PowerShell build:

```powershell
powershell -ExecutionPolicy Bypass -File muse_vision_recorder\build_windows_pyinstaller.ps1
```

If it “crashes instantly”, rebuild once with `console=True` in `muse_vision_recorder/pyinstaller.spec` to see logs.

### Optional: py2exe (if you specifically need it)

`py2exe` works on Windows and usually requires a `setup.py`. See `muse_vision_recorder/py2exe_setup.py`.

