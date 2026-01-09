from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BandPowers:
    delta: float
    theta: float
    alpha: float
    beta: float
    gamma: float


def _band_power(freqs: np.ndarray, psd: np.ndarray, fmin: float, fmax: float) -> float:
    mask = (freqs >= fmin) & (freqs < fmax)
    if not np.any(mask):
        return 0.0
    # Integrate PSD over the band.
    return float(np.trapz(psd[mask], freqs[mask]))


def _simple_psd_fft(window_1d: np.ndarray, *, srate_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """
    Minimal PSD estimate using a Hann window + rFFT.

    This is not a full Welch implementation, but it is dependency-free and stable
    enough for live band-power features.
    """
    x = np.asarray(window_1d, dtype=np.float64)
    x = x - np.mean(x)
    n = x.shape[0]
    if n < 8:
        return np.array([0.0]), np.array([0.0])

    w = np.hanning(n)
    xw = x * w
    spec = np.fft.rfft(xw)
    freqs = np.fft.rfftfreq(n, d=1.0 / float(srate_hz))

    # Power spectrum (arbitrary scale); band power uses relative integration.
    psd = (np.abs(spec) ** 2) / (np.sum(w**2) + 1e-12)
    return freqs, psd


def compute_band_powers(
    window: np.ndarray,
    *,
    srate_hz: float,
    fmax_hz: float = 45.0,
) -> list[BandPowers]:
    """
    Compute band powers per channel for a window of EEG.

    Parameters
    - window: shape (n_samples, n_channels)
    - srate_hz: sampling rate
    """
    if window.ndim != 2:
        raise ValueError("window must be 2D: (n_samples, n_channels)")
    if window.shape[0] < 8:
        # Too small to be meaningful; keep stable output shape.
        return [BandPowers(0.0, 0.0, 0.0, 0.0, 0.0) for _ in range(window.shape[1])]

    bands: list[BandPowers] = []
    for ch in range(window.shape[1]):
        freqs, p = _simple_psd_fft(window[:, ch], srate_hz=srate_hz)
        keep = freqs <= fmax_hz
        freqs = freqs[keep]
        p = p[keep]
        bands.append(
            BandPowers(
                delta=_band_power(freqs, p, 1.0, 4.0),
                theta=_band_power(freqs, p, 4.0, 8.0),
                alpha=_band_power(freqs, p, 8.0, 12.0),
                beta=_band_power(freqs, p, 12.0, 30.0),
                gamma=_band_power(freqs, p, 30.0, 45.0),
            )
        )
    return bands


def summarize_bands_across_channels(bands: list[BandPowers]) -> BandPowers:
    if not bands:
        return BandPowers(0.0, 0.0, 0.0, 0.0, 0.0)
    return BandPowers(
        delta=float(np.mean([b.delta for b in bands])),
        theta=float(np.mean([b.theta for b in bands])),
        alpha=float(np.mean([b.alpha for b in bands])),
        beta=float(np.mean([b.beta for b in bands])),
        gamma=float(np.mean([b.gamma for b in bands])),
    )

