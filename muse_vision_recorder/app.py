from __future__ import annotations

import argparse
import threading
import time
from collections import deque
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import numpy as np

from muse_vision_recorder.eeg_features import compute_band_powers, summarize_bands_across_channels
from muse_vision_recorder.lsl_client import connect_first_lsl_stream, try_get_channel_labels
from muse_vision_recorder.recording import SessionWriter, create_session_folder


class App:
    def __init__(self, *, mode: str) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        self._inlet = None
        self._lsl_meta = None
        self._channel_labels: list[str] = []
        self._last_ts_lsl: float = 0.0

        self._writer: Optional[SessionWriter] = None
        self._recording = False

        # Rolling buffer for feature computation
        self._buffer = deque(maxlen=512)  # enough for ~2s at 256 Hz
        self._srate = 256.0  # will be overwritten if stream provides it

        self._mode = mode
        self.ui = None
        if mode == "gui":
            try:
                from muse_vision_recorder.ui_tk import MuseVisionUi
            except Exception as e:
                raise RuntimeError(
                    "GUI mode requires Tkinter. On Linux you may need to install a system "
                    "package like 'python3-tk'. Original error: "
                    f"{e}"
                ) from e

            self.ui = MuseVisionUi(
                on_start=self.start_recording,
                on_stop=self.stop_recording,
                on_mark_utterance=self.mark_utterance,
            )

    def run(self) -> None:
        self._ui_update(status="Connecting to LSL stream (type=EEG)...")
        try:
            inlet, meta = connect_first_lsl_stream(stype="EEG", timeout_s=10.0)
            self._inlet = inlet
            self._lsl_meta = meta
            self._srate = meta.nominal_srate or 256.0
            labels = try_get_channel_labels(inlet)
            if labels is None or len(labels) != meta.channel_count:
                labels = [f"ch{i}" for i in range(meta.channel_count)]
            self._channel_labels = labels
            self._ui_update(
                connected=True,
                status=f"Connected to LSL: name={meta.name!r}, type={meta.stype!r}, "
                f"channels={meta.channel_count}, srate={self._srate:.3g} Hz",
            )
        except Exception as e:
            self._ui_update(connected=False, status=f"Failed to connect: {e}")
            if self.ui is not None:
                self.ui.root.mainloop()
            return

        t = threading.Thread(target=self._reader_loop, daemon=True)
        t.start()

        if self.ui is None:
            # Headless mode: start recording immediately and accept utterances via stdin.
            self.start_recording()
            self._start_headless_input_thread()
            try:
                while not self._stop_event.is_set():
                    time.sleep(0.25)
            except KeyboardInterrupt:
                self._stop_event.set()
                self.stop_recording()
            return

        self.ui.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.ui.root.mainloop()

    def _on_close(self) -> None:
        self._stop_event.set()
        try:
            self.stop_recording()
        finally:
            if self.ui is not None:
                self.ui.root.destroy()

    def _ui_update(self, **kwargs) -> None:
        if self.ui is not None:
            self.ui.update_state(**kwargs)
            return
        # Minimal headless status
        if "status" in kwargs and kwargs["status"]:
            print(kwargs["status"], flush=True)

    def start_recording(self) -> None:
        with self._lock:
            if self._recording:
                return
            base_dir = Path(__file__).resolve().parent / "recordings"
            base_dir.mkdir(parents=True, exist_ok=True)
            paths = create_session_folder(base_dir)
            self._writer = SessionWriter(paths, channel_labels=self._channel_labels)
            meta = {
                "lsl": asdict(self._lsl_meta) if self._lsl_meta else None,
                "channel_labels": self._channel_labels,
                "nominal_srate_hz": self._srate,
                "notes": "Raw EEG + band-power features + labeled events (utterances).",
            }
            self._writer.write_metadata(meta)
            self._recording = True
            self._ui_update(recording=True, status=f"Recording to: {paths.root}")

    def stop_recording(self) -> None:
        with self._lock:
            if not self._recording:
                return
            if self._writer is not None:
                self._writer.close()
            self._writer = None
            self._recording = False
            self._ui_update(recording=False, status="Stopped recording.")

    def mark_utterance(self, label: str) -> None:
        with self._lock:
            if not self._recording or self._writer is None:
                self._ui_update(status="Not recording: utterance not saved.")
                return
            # Use last seen LSL timestamp (approx)
            if self.ui is not None:
                ts_lsl = float(self.ui.state.last_ts_lsl or 0.0)
            else:
                ts_lsl = float(self._last_ts_lsl or 0.0)
            self._writer.write_event(ts_lsl=ts_lsl, event_type="utterance", label=label)
            self._ui_update(status=f"Utterance saved: {label!r}")

    def _start_headless_input_thread(self) -> None:
        def _loop() -> None:
            print("Headless input: type an utterance label and press Enter.", flush=True)
            print("Type ':quit' to stop.", flush=True)
            while not self._stop_event.is_set():
                try:
                    line = input()
                except EOFError:
                    break
                except Exception:
                    continue
                line = line.strip()
                if not line:
                    continue
                if line == ":quit":
                    self._stop_event.set()
                    self.stop_recording()
                    break
                self.mark_utterance(line)

        threading.Thread(target=_loop, daemon=True).start()

    def _reader_loop(self) -> None:
        assert self._inlet is not None

        last_feature_ts = 0.0
        feature_period_s = 0.1  # 10 Hz updates; you can lower to 0.02 for ~50 Hz UI updates

        while not self._stop_event.is_set():
            chunk, timestamps = self._inlet.pull_chunk(timeout=0.25, max_samples=64)
            if timestamps is None or not timestamps:
                continue

            # chunk: list[list[float]] shape (n_samples, n_channels)
            for sample, ts in zip(chunk, timestamps):
                # store raw sample for windowing
                self._buffer.append((float(ts), list(map(float, sample))))
                self._last_ts_lsl = float(ts)

                with self._lock:
                    if self._recording and self._writer is not None:
                        self._writer.write_eeg_row(ts_lsl=float(ts), values=list(map(float, sample)))

                # update last-ts for event labeling
                if self.ui is not None:
                    self.ui.update_state(ts_lsl=float(ts))

            now = time.time()
            if now - last_feature_ts < feature_period_s:
                continue
            last_feature_ts = now

            # compute features over last ~1s
            buf = list(self._buffer)
            if len(buf) < 32:
                continue
            ts_last = buf[-1][0]
            data = np.array([v for _ts, v in buf], dtype=np.float64)  # (n, ch)

            # take last 1 second
            n_win = int(max(32, min(len(data), round(self._srate * 1.0))))
            win = data[-n_win:, :]

            bands_per_ch = compute_band_powers(win, srate_hz=self._srate)
            bands = summarize_bands_across_channels(bands_per_ch)
            band_dict = {
                "delta": bands.delta,
                "theta": bands.theta,
                "alpha": bands.alpha,
                "beta": bands.beta,
                "gamma": bands.gamma,
            }

            with self._lock:
                if self._recording and self._writer is not None:
                    self._writer.write_band_row(
                        ts_lsl=float(ts_last),
                        delta=bands.delta,
                        theta=bands.theta,
                        alpha=bands.alpha,
                        beta=bands.beta,
                        gamma=bands.gamma,
                    )

            # push to UI
            if self.ui is not None:
                self.ui.update_state(bands=band_dict)


def main() -> None:
    parser = argparse.ArgumentParser(description="Muse 2 EEG recorder + utterance markers (prototype).")
    parser.add_argument(
        "--mode",
        choices=["gui", "headless"],
        default="gui",
        help="Run with Tkinter GUI (default) or headless console mode.",
    )
    args = parser.parse_args()
    App(mode=args.mode).run()


if __name__ == "__main__":
    main()

