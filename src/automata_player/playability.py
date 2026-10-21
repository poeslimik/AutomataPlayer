"""악보를 악기에서 그대로 칠 수 있는지 판단한다.

바람의 노래 하프는 음역 안의 자연음만 친다.
이환 피아노는 Shift로 C·F·G를 올리고, Ctrl로 E·B를 내린다.
A♭은 G♯으로 친다. 같은 순간에 수정키가 서로 모순이면 칠 수 없다.
칠 수 없을 때, 음역 밖으로 덜 나가는 쪽의 이조를 하나 고른다.
"""

from __future__ import annotations

from dataclasses import dataclass

from automata_player.i18n import t
from automata_player.instruments.profile import Instrument
from automata_player.model import Note
_CONFLICT = object()


@dataclass(frozen=True)
class PlayCheck:
    ok: bool
    message: str = ""
    suggestion: int | None = None
    suggestion_text: str = ""

    @property
    def notice(self) -> str:
        if self.suggestion_text:
            return f"{self.message}\n{self.suggestion_text}"
        return self.message


def assess(notes: tuple[Note, ...] | list[Note], instrument: Instrument, transpose: int = 0) -> PlayCheck:
    if instrument.note_style == "chromatic" or _fits(notes, instrument, transpose):
        return PlayCheck(True)
    suggestion = suggest_transpose(notes, instrument)
    text = ""
    if suggestion is not None:
        text = _suggestion_text(suggestion)
    return PlayCheck(False, t("unplayable"), suggestion, text)


def suggest_transpose(notes: tuple[Note, ...] | list[Note], instrument: Instrument) -> int | None:
    """연주가 되는 이조 중, 이동이 작고 음역 밖으로 덜 나가는 값을 고른다."""
    if instrument.note_style == "chromatic" or not notes:
        return None
    found = [step for step in range(-36, 37) if step != 0 and _fits(notes, instrument, step)]
    if not found:
        return None
    found.sort(key=lambda step: (abs(step), _out_of_range_count(notes, instrument, step), 0 if step > 0 else 1))
    return found[0]


def piano_key(pitch: int, instrument: Instrument) -> str | None:
    """이환 피아노에서 이 음을 내는 키. 불가능하면 None."""
    resolved = _piano_resolution(pitch, instrument)
    if resolved is None:
        return None
    base, shift, ctrl = resolved
    key_name = instrument.key_for(base)
    if key_name is None:
        return None
    parts: list[str] = []
    if ctrl is True:
        parts.append("ctrl")
    if shift is True:
        parts.append("shift")
    parts.append(key_name)
    return "+".join(parts)


def _fits(notes: tuple[Note, ...] | list[Note], instrument: Instrument, transpose: int) -> bool:
    if instrument.note_style == "white":
        return all(instrument.key_for(note.pitch + transpose) is not None for note in notes)
    if instrument.note_style == "nte-piano":
        return all(_piano_chord_ok(group, instrument) for group in _sounding_groups(notes, transpose))
    return True


def _sounding_groups(notes: tuple[Note, ...] | list[Note], transpose: int) -> list[frozenset[int]]:
    """시간이 겹치는 음들의 묶음. 끝이 시작과 같으면 겹치지 않는다."""
    events: list[tuple[object, int, int, int]] = []
    for index, note in enumerate(notes):
        pitch = note.pitch + transpose
        events.append((note.end, 0, index, pitch))
        events.append((note.start, 1, index, pitch))
    events.sort(key=lambda item: (item[0], item[1], item[2]))
    active: dict[int, int] = {}
    groups: list[frozenset[int]] = []
    for _time, kind, index, pitch in events:
        if kind == 0:
            active.pop(index, None)
            continue
        active[index] = pitch
        groups.append(frozenset(active.values()))
    return groups


def _piano_chord_ok(pitches: frozenset[int], instrument: Instrument) -> bool:
    shift: bool | object | None = None
    ctrl: bool | object | None = None
    bases: set[int] = set()
    for pitch in pitches:
        resolved = _piano_resolution(pitch, instrument)
        if resolved is None:
            return False
        base, need_shift, need_ctrl = resolved
        if base in bases:
            return False
        bases.add(base)
        shift = _merge_modifier(shift, need_shift)
        ctrl = _merge_modifier(ctrl, need_ctrl)
        if shift is _CONFLICT or ctrl is _CONFLICT:
            return False
    return True


def _piano_resolution(pitch: int, instrument: Instrument) -> tuple[int, bool | None, bool | None] | None:
    """(흰 건반 MIDI, Shift 필요 여부, Ctrl 필요 여부).

    True는 그 수정키가 반드시 눌려 있어야 하고, False는 눌려 있으면 안 된다.
    None은 그 건반이 수정키의 영향을 받지 않는다.
    음역 밖은 기타와 같이 옥타브를 접어 건반 안으로 넣는다.
    """
    for candidate in _octave_candidates(pitch, instrument.low, instrument.high):
        resolved = _piano_resolution_in_place(candidate, instrument)
        if resolved is not None:
            return resolved
    return None


def _octave_candidates(pitch: int, low: int, high: int):
    folded = pitch
    while folded > high:
        folded -= 12
    while folded < low:
        folded += 12
    yield folded
    for step in range(1, 6):
        yield folded + 12 * step
        yield folded - 12 * step


def _piano_resolution_in_place(
    pitch: int, instrument: Instrument
) -> tuple[int, bool | None, bool | None] | None:
    pitch_class = pitch % 12
    if pitch_class in {1, 6, 8}:
        base, shift, ctrl = pitch - 1, True, None
    elif pitch_class in {3, 10}:
        base, shift, ctrl = pitch + 1, None, True
    elif pitch_class in {0, 5, 7}:
        base, shift, ctrl = pitch, False, None
    elif pitch_class in {4, 11}:
        base, shift, ctrl = pitch, None, False
    elif pitch_class in {2, 9}:
        base, shift, ctrl = pitch, None, None
    else:
        return None
    if instrument.key_for(base) is None:
        return None
    return base, shift, ctrl


def _merge_modifier(current: bool | object | None, needed: bool | None) -> bool | object | None:
    if needed is None:
        return current
    if current is None:
        return needed
    if current is _CONFLICT or current != needed:
        return _CONFLICT
    return current


def _out_of_range_count(notes: tuple[Note, ...] | list[Note], instrument: Instrument, transpose: int) -> int:
    return sum(1 for note in notes if not instrument.low <= note.pitch + transpose <= instrument.high)


def _suggestion_text(semitones: int) -> str:
    if semitones > 0:
        return t("transpose_up", n=semitones)
    return t("transpose_down", n=-semitones)
