"""MIDI 음높이 표기와 MuseScore TPC(음이름 철자)."""

from __future__ import annotations

_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def midi_name(pitch: int) -> str:
    """60 -> C4. MIDI 옥타브는 C4가 가운데 도다."""
    return f"{_NAMES[pitch % 12]}{pitch // 12 - 1}"


def tpc_alter(tpc: int) -> int:
    """MuseScore tpc2alter. 0은 제자리, 양수는 샵, 음수는 플랫."""
    return (tpc + 1) // 7 - 2
