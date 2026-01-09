from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pylsl import StreamInlet  # pragma: no cover
else:
    StreamInlet = Any  # runtime fallback when pylsl isn't installed


@dataclass(frozen=True)
class LslStreamInfo:
    name: str
    stype: str
    channel_count: int
    nominal_srate: float


def connect_first_lsl_stream(
    *,
    stype: str = "EEG",
    timeout_s: float = 10.0,
) -> tuple[StreamInlet, LslStreamInfo]:
    """
    Connect to the first LSL stream of the given type.

    Muse via muse-lsl typically advertises type="EEG".
    """
    try:
        from pylsl import StreamInlet as _StreamInlet, resolve_stream
    except Exception as e:
        raise RuntimeError(
            "Missing dependency 'pylsl'. Install it with:\n"
            "  pip install -r muse_vision_recorder/requirements.txt\n"
            f"Original error: {e}"
        ) from e

    results = resolve_stream("type", stype, timeout_s)
    if not results:
        raise RuntimeError(
            f"No LSL stream found for type={stype!r}. "
            "Start Muse streaming first (e.g. muselsl)."
        )

    info = results[0]
    inlet = _StreamInlet(info, max_chunklen=64)
    meta = LslStreamInfo(
        name=info.name(),
        stype=info.type(),
        channel_count=info.channel_count(),
        nominal_srate=info.nominal_srate(),
    )
    return inlet, meta


def try_get_channel_labels(inlet: StreamInlet) -> Optional[list[str]]:
    """
    Best-effort channel label extraction from LSL stream metadata.

    If not present, returns None.
    """
    try:
        info = inlet.info()
        desc = info.desc()
        channels = desc.child("channels")
        if channels.empty():
            return None

        labels: list[str] = []
        ch = channels.child("channel")
        while not ch.empty():
            label = ch.child_value("label")
            labels.append(label or f"ch{len(labels)}")
            ch = ch.next_sibling()
        return labels or None
    except Exception:
        return None

