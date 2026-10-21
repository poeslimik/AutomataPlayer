"""악보를 연주 시각으로 다루는 공통 모델.

로더는 Note, TempoMark, TimeStretch, Pause를 채우고,
악기와 입력 장치는 이 모델 이후의 단계에서 붙는다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction

from automata_player.i18n import t


class AutomataError(Exception):
    """사용자가 고칠 수 있는 실행 오류."""


class ScoreError(AutomataError):
    """악보를 열거나 해석하지 못했을 때."""


class InstrumentError(AutomataError):
    """악기 이름이나 키 배치가 잘못되었을 때."""


class BackendError(AutomataError):
    """키 입력 백엔드를 쓸 수 없을 때."""


@dataclass(frozen=True)
class Note:
    """한 음의 시작과 길이. 시간은 4분음표 개수다."""

    start: Fraction
    duration: Fraction
    pitch: int
    part_index: int
    part_name: str
    staff_index: int
    alter: int | None = None
    tie_forward: bool = False
    tie_back: bool = False

    @property
    def end(self) -> Fraction:
        return self.start + self.duration


@dataclass(frozen=True)
class TempoMark:
    """`position` 4분음표 지점부터 적용되는 BPM."""

    position: Fraction
    bpm: float


@dataclass(frozen=True)
class TimeStretch:
    """한 구간의 박을 `factor`배 늘린다. 페르마타가 대표적이다."""

    start: Fraction
    duration: Fraction
    factor: float


@dataclass(frozen=True)
class Pause:
    """`position` 4분음표 지점 뒤에 붙는 절대 시간. 구간 나누기가 대표적이다."""

    position: Fraction
    seconds: float


@dataclass(frozen=True)
class PartInfo:
    index: int
    name: str
    staves: int


@dataclass(frozen=True)
class Score:
    title: str
    notes: tuple[Note, ...]
    tempos: tuple[TempoMark, ...]
    parts: tuple[PartInfo, ...]
    warnings: tuple[str, ...] = ()
    stretches: tuple[TimeStretch, ...] = ()
    pauses: tuple[Pause, ...] = ()

    def seconds_at(self, position: Fraction, *, inclusive: bool = True) -> float:
        from automata_player.timing import quarters_to_seconds

        return quarters_to_seconds(
            position,
            tuple((mark.position, mark.bpm) for mark in self.tempos),
            tuple((item.start, item.duration, item.factor) for item in self.stretches),
            tuple((item.position, item.seconds) for item in self.pauses),
            inclusive=inclusive,
        )

    @property
    def duration_seconds(self) -> float:
        if not self.notes:
            return 0.0
        end = max(note.end for note in self.notes)
        return self.seconds_at(end)

    def select_parts(self, tokens: list[str]) -> Score:
        """파트 번호(1부터) 또는 이름 일부로 음을 고른다."""
        if not tokens:
            return self

        def matches(note: Note) -> bool:
            for token in tokens:
                if token.isdigit() and note.part_index == int(token) - 1:
                    return True
                if not token.isdigit() and token.casefold() in note.part_name.casefold():
                    return True
            return False

        chosen = tuple(note for note in self.notes if matches(note))
        if not chosen:
            listed = ", ".join(f"{part.index + 1}:{part.name}" for part in self.parts) or t("score_no_parts")
            raise ScoreError(t("missing_part", listed=listed))
        return replace(self, notes=chosen)


def merge_ties(notes: list[Note]) -> tuple[Note, ...]:
    """같은 음높이로 이음줄이 이어진 음표를 하나의 음으로 합친다."""
    groups: dict[tuple[int, int, int], list[Note]] = {}
    for note in notes:
        key = (note.part_index, note.staff_index, note.pitch)
        groups.setdefault(key, []).append(note)

    merged: list[Note] = []
    for group in groups.values():
        group.sort(key=lambda item: (item.start, item.duration))
        current: Note | None = None
        for note in group:
            if current is not None and _continues(current, note):
                current = replace(
                    current,
                    duration=max(current.end, note.end) - current.start,
                    tie_forward=note.tie_forward,
                )
                continue
            if current is not None:
                merged.append(current)
            current = note
        if current is not None:
            merged.append(current)

    merged.sort(key=lambda item: (item.start, item.part_index, item.staff_index, item.pitch))
    return tuple(
        replace(note, tie_forward=False, tie_back=False)
        for note in merged
    )


def _continues(previous: Note, note: Note) -> bool:
    tied = note.tie_back or previous.tie_forward
    if not tied:
        return False
    return note.start <= previous.end
