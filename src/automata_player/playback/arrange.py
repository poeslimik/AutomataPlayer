"""음표를 악기 키 입력으로 바꾼다."""

from __future__ import annotations

from dataclasses import dataclass

from automata_player.instruments.profile import AccidentalPolicy, Instrument, RangePolicy
from automata_player.model import Score
from automata_player.pitch import midi_name
from automata_player.playability import piano_key


@dataclass(frozen=True)
class KeyAction:
    """한 번의 키를 누르거나 떼는 동작. time은 초."""

    time: float
    key: str
    down: bool
    source_pitch: int
    played_pitch: int
    part_name: str
    label: str


@dataclass(frozen=True)
class ArrangeResult:
    actions: tuple[KeyAction, ...]
    skipped: tuple[int, ...]


@dataclass
class _Hit:
    start: float
    end: float
    key: str
    source: int
    played: int
    part: str
    label: str


def arrange(
    score: Score,
    instrument: Instrument,
    *,
    transpose: int = 0,
    tap_ms: int | None = None,
) -> ArrangeResult:
    """악보의 음을 악기 음역에 접어 넣고, 누르고 떼는 시각으로 펼친다."""
    hold_ms = instrument.tap_ms if tap_ms is None else tap_ms
    min_hold = max(hold_ms, 1) / 1000
    hits: list[_Hit] = []
    skipped: list[int] = []

    for note in score.notes:
        source = note.pitch + transpose
        alter = note.alter if transpose == 0 else None
        resolved = _resolve(source, instrument, alter)
        if resolved is None:
            skipped.append(source)
            continue
        key, played = resolved
        start = score.seconds_at(note.start)
        end = score.seconds_at(note.end, inclusive=False)
        if not instrument.sustains:
            end = start + min_hold
        else:
            end = max(end, start + min_hold)
        hits.append(
            _Hit(
                start=start,
                end=end,
                key=key,
                source=source,
                played=played,
                part=note.part_name,
                label=_label(source, played),
            )
        )

    actions = _schedule(hits, instrument.retrigger_ms / 1000)
    return ArrangeResult(actions=tuple(actions), skipped=tuple(skipped))


def _resolve(pitch: int, instrument: Instrument, alter: int | None) -> tuple[str, int] | None:
    if instrument.note_style == "white":
        key = instrument.key_for(pitch)
        if key is None:
            return None
        return key, pitch
    if instrument.note_style == "nte-piano":
        key = piano_key(pitch, instrument)
        if key is None:
            return None
        return key, pitch
    played = map_pitch(pitch, instrument, alter)
    if played is None:
        return None
    key = instrument.key_for(played)
    if key is None:
        return None
    return key, played


def map_pitch(pitch: int, instrument: Instrument, alter: int | None = None) -> int | None:
    """악기에서 실제로 누를 MIDI 음. 없으면 None.

    음역 접기가 켜져 있으면 음역 밖은 옥타브 단위로 접는다.
    """
    folded = _fold(pitch, instrument) if instrument.out_of_range is RangePolicy.FOLD else pitch
    if folded is None:
        return None
    if instrument.key_for(folded) is not None:
        return folded
    if instrument.accidental is AccidentalPolicy.SKIP:
        return None
    return _snap(folded, instrument, alter)


def _fold(pitch: int, instrument: Instrument) -> int | None:
    low, high = instrument.low, instrument.high
    if low <= pitch <= high:
        return pitch
    folded = pitch
    while folded > high:
        folded -= 12
    while folded < low:
        folded += 12
    if folded < low or folded > high:
        return None
    return folded


def _snap(pitch: int, instrument: Instrument, alter: int | None) -> int | None:
    for delta in range(1, 128):
        down = pitch - delta
        up = pitch + delta
        down_ok = instrument.key_for(down) is not None
        up_ok = instrument.key_for(up) is not None
        if down_ok and up_ok:
            if alter is not None and alter > 0:
                return up
            return down
        if down_ok:
            return down
        if up_ok:
            return up
    return None


def _release_before(previous: _Hit, next_start: float, gap: float) -> None:
    desired = next_start - gap
    latest = next_start - 0.005
    if desired < previous.start + 0.005:
        desired = latest if latest > previous.start else previous.start + 0.005
    previous.end = min(previous.end, desired)
    if previous.end <= previous.start:
        previous.end = previous.start + 0.005
    if previous.end >= next_start:
        previous.end = max(previous.start + 0.001, latest)


def _label(source: int, played: int) -> str:
    if source == played:
        return midi_name(played)
    return f"{midi_name(source)}→{midi_name(played)}"


def _schedule(hits: list[_Hit], gap: float) -> list[KeyAction]:
    grouped: dict[str, list[_Hit]] = {}
    for hit in hits:
        grouped.setdefault(hit.key, []).append(hit)

    actions: list[KeyAction] = []
    for key, group in grouped.items():
        group.sort(key=lambda item: (item.start, item.source))
        resolved: list[_Hit] = []
        for hit in group:
            if not resolved:
                resolved.append(hit)
                continue
            previous = resolved[-1]
            if hit.start < previous.end - 1e-6:
                # 이미 누르고 있는 같은 키를 다시 친다. 최종 뗌은 더 길게 남는 쪽이다.
                longer_end = max(previous.end, hit.end)
                _release_before(previous, hit.start, gap)
                hit.end = longer_end
            elif hit.start - previous.end < gap:
                _release_before(previous, hit.start, gap)
            resolved.append(hit)
        for hit in resolved:
            actions.append(
                KeyAction(hit.start, key, True, hit.source, hit.played, hit.part, hit.label)
            )
            actions.append(
                KeyAction(hit.end, key, False, hit.source, hit.played, hit.part, hit.label)
            )

    actions.sort(key=lambda action: (action.time, 0 if not action.down else 1, action.key))
    return actions
