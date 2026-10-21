"""게임 악기의 음역과 키보드 배치."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from automata_player.keys import parse_key
from automata_player.model import InstrumentError
from automata_player.pitch import midi_name


class AccidentalPolicy(Enum):
    """자연음만 있는 악기에서 샵·플랫을 어떻게 둘지."""

    SNAP = "snap"
    SKIP = "skip"


class RangePolicy(Enum):
    """음역 밖 음을 옥타브로 접어 넣을지, 버릴지."""

    FOLD = "fold"
    SKIP = "skip"


@dataclass(frozen=True)
class KeyBinding:
    pitch: int
    key: str


@dataclass(frozen=True)
class Instrument:
    """한 게임 악기의 연주 가능한 음과 그 음을 내는 키.

    새 악기는 키 표만 채워 등록하면 된다. 악보 로더와 입력 장치는 공통이다.
    """

    id: str
    name: str
    detail: str
    sustains: bool
    keys: tuple[KeyBinding, ...]
    accidental: AccidentalPolicy = AccidentalPolicy.SNAP
    out_of_range: RangePolicy = RangePolicy.FOLD
    tap_ms: int = 50
    retrigger_ms: int = 30
    verified: bool = True
    aliases: tuple[str, ...] = ()
    note_style: str = "chromatic"
    _by_pitch: dict[int, str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.keys:
            raise InstrumentError(f"{self.id}: 키가 없습니다.")
        pitches = [binding.pitch for binding in self.keys]
        key_names = [binding.key for binding in self.keys]
        if len(pitches) != len(set(pitches)):
            raise InstrumentError(f"{self.id}: 같은 음에 키가 두 개입니다.")
        if len(key_names) != len(set(key_names)):
            raise InstrumentError(f"{self.id}: 같은 키가 두 음에 쓰입니다.")
        try:
            for binding in self.keys:
                parse_key(binding.key)
        except ValueError as exc:
            raise InstrumentError(f"{self.id}: {exc}") from exc
        object.__setattr__(self, "_by_pitch", {binding.pitch: binding.key for binding in self.keys})

    @property
    def low(self) -> int:
        return min(binding.pitch for binding in self.keys)

    @property
    def high(self) -> int:
        return max(binding.pitch for binding in self.keys)

    def key_for(self, pitch: int) -> str | None:
        return self._by_pitch.get(pitch)

    @property
    def range_label(self) -> str:
        return f"{midi_name(self.low)}–{midi_name(self.high)}"

    @property
    def chromatic(self) -> bool:
        return len({binding.pitch % 12 for binding in self.keys}) == 12
