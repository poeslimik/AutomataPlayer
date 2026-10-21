"""4분음표 위치를 초로 바꾼다."""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction

DEFAULT_BPM = 120.0


def quarters_to_seconds(
    position: Fraction,
    tempos: Sequence[tuple[Fraction, float]],
    stretches: Sequence[tuple[Fraction, Fraction, float]] = (),
    pauses: Sequence[tuple[Fraction, float]] = (),
    *,
    inclusive: bool = True,
) -> float:
    """템포 변화와 페르마타를 반영해 `position` 4분음표 지점의 시각(초)을 구한다.

    0 지점에 템포가 없으면 120 BPM으로 시작한다.
    MuseScore `<tempo>` 값은 4분음표/초이고, 여기 들어오는 값은 이미 BPM이다.
    `stretches`의 factor가 2이면 그 구간은 두 배로 늘어나고, 뒤 음도 그만큼 늦어진다.
    `pauses`는 그 지점 뒤에 더해지는 초이다. `inclusive`가 거짓이면 정확히 그 지점의 쉼은 빼서,
    거기서 끝나는 음이 쉼까지 붙잡히지 않게 한다.
    """
    if position <= 0:
        return 0.0

    points = [(pos, bpm) for pos, bpm in tempos if bpm > 0]
    points.sort(key=lambda item: item[0])
    collapsed: list[tuple[Fraction, float]] = []
    for pos, bpm in points:
        if collapsed and collapsed[-1][0] == pos:
            collapsed[-1] = (pos, bpm)
        else:
            collapsed.append((pos, bpm))
    if not collapsed or collapsed[0][0] > 0:
        collapsed.insert(0, (Fraction(0), DEFAULT_BPM))

    boundaries = {Fraction(0), position}
    for pos, _bpm in collapsed:
        if Fraction(0) < pos < position:
            boundaries.add(pos)
    active_stretches = [
        (start, duration, factor)
        for start, duration, factor in stretches
        if factor > 0 and duration > 0
    ]
    for start, duration, _factor in active_stretches:
        end = start + duration
        if Fraction(0) < start < position:
            boundaries.add(start)
        if Fraction(0) < end < position:
            boundaries.add(end)
    ordered = sorted(boundaries)

    elapsed = 0.0
    for index, start in enumerate(ordered[:-1]):
        end = ordered[index + 1]
        bpm = _bpm_at(start, collapsed)
        factor = _stretch_at(start, active_stretches)
        elapsed += float(end - start) * 60.0 / bpm * factor
    for pause_at, seconds in pauses:
        if seconds <= 0:
            continue
        if pause_at < position or (inclusive and pause_at == position):
            elapsed += seconds
    return elapsed


def _bpm_at(position: Fraction, tempos: Sequence[tuple[Fraction, float]]) -> float:
    bpm = DEFAULT_BPM
    for pos, mark in tempos:
        if pos <= position:
            bpm = mark
        else:
            break
    return bpm


def _stretch_at(
    position: Fraction,
    stretches: Sequence[tuple[Fraction, Fraction, float]],
) -> float:
    factor = 1.0
    for start, duration, stretch in stretches:
        if start <= position < start + duration:
            factor = max(factor, stretch)
    return factor
