"""
Optional Windows build with py2exe.

Usage (Windows, from repo root):

    pip install -r muse_vision_recorder\\requirements.txt
    pip install py2exe
    python muse_vision_recorder\\py2exe_setup.py py2exe

Output will land in `dist/`.
"""

from __future__ import annotations

from setuptools import setup


setup(
    name="MuseVisionRecorder",
    version="0.1.0",
    description="Muse 2 EEG recorder + utterance marker (prototype)",
    windows=[{"script": "muse_vision_recorder/app.py"}],
    options={
        "py2exe": {
            "includes": ["numpy", "scipy", "pylsl", "tkinter"],
        }
    },
)

