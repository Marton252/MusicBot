from __future__ import annotations

from enum import Enum


class PlaybackState(Enum):
    IDLE = "idle"
    RESOLVING = "resolving"
    PLAYING = "playing"
    PAUSED = "paused"
    RECOVERING = "recovering"
    FAILED = "failed"


class AudioFilter(Enum):
    NONE = "none"
    BASSBOOST = "bassboost"
    NIGHTCORE = "nightcore"
    VAPORWAVE = "vaporwave"
    KARAOKE = "karaoke"
    EIGHT_D = "8d"


FILTERS: dict[AudioFilter, str] = {
    AudioFilter.BASSBOOST: "bass=g=12",
    AudioFilter.NIGHTCORE: "aresample=48000,asetrate=48000*1.20",
    AudioFilter.VAPORWAVE: "aresample=48000,asetrate=48000*0.85",
    AudioFilter.KARAOKE: "stereotools=mlev=0.03",
    AudioFilter.EIGHT_D: "apulsator=hz=0.09",
}


def coerce_filter(value: str | AudioFilter) -> AudioFilter:
    if isinstance(value, AudioFilter):
        return value
    try:
        return AudioFilter(value)
    except ValueError:
        return AudioFilter.NONE


def ffmpeg_filter_options(value: str | AudioFilter) -> str:
    audio_filter = coerce_filter(value)
    if audio_filter is AudioFilter.NONE:
        return "-vn"
    return f"-vn -af {FILTERS[audio_filter]}"

