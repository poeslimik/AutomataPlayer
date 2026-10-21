"""기본으로 들어 있는 악기.

키를 고칠 때는 이 파일의 표만 바꾸면 된다.
음높이는 MIDI 번호다. C4(가운데 도)는 60이다.
"""

from __future__ import annotations

from automata_player.instruments.profile import (
    AccidentalPolicy,
    Instrument,
    KeyBinding,
    RangePolicy,
)
from automata_player.i18n import t
from automata_player.model import InstrumentError

# 바람의 노래 하프의 PC 배치. 키보드로 누르는 키는 21개다.
# 이환 피아노의 36키 화면도 같은 글쇠를 쓴다.
#   높은음 Q W E R T Y U  = C5–B5
#   가운데 A S D F G H J  = C4–B4
#   낮은음 Z X C V B N M  = C3–B3
# 샵·플랫 건반은 없다.
_DIATONIC_21: tuple[tuple[int, str], ...] = (
    (48, "z"),
    (50, "x"),
    (52, "c"),
    (53, "v"),
    (55, "b"),
    (57, "n"),
    (59, "m"),
    (60, "a"),
    (62, "s"),
    (64, "d"),
    (65, "f"),
    (67, "g"),
    (69, "h"),
    (71, "j"),
    (72, "q"),
    (74, "w"),
    (76, "e"),
    (77, "r"),
    (79, "t"),
    (81, "y"),
    (83, "u"),
)


def _bindings(pairs: tuple[tuple[int, str], ...]) -> tuple[KeyBinding, ...]:
    return tuple(KeyBinding(pitch, key) for pitch, key in pairs)


def _chromatic(start: int, rows: tuple[tuple[str, ...], ...]) -> tuple[KeyBinding, ...]:
    pitch = start
    bindings: list[KeyBinding] = []
    for row in rows:
        for key in row:
            bindings.append(KeyBinding(pitch, key))
            pitch += 1
    return tuple(bindings)


# 각 줄 12반음, E로 시작해 D#에서 끝난다.
# 낮은 줄 E3=a … D#4=Enter, 가운데 E4=q … D#5=], 높은 줄 E5=1 … D#6==.
_GUITAR_ROWS: tuple[tuple[str, ...], ...] = (
    ("a", "s", "d", "f", "g", "h", "j", "k", "l", ";", "'", "enter"),
    ("q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]"),
    ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "="),
)


def genshin_harp() -> Instrument:
    return Instrument(
        id="genshin-lyre",
        name="바람의 노래 하프",
        detail=(
            "C3–B5 자연음 21키. 아래줄 Z–M, 가운데 A–J, 위줄 Q–U. "
            "하프라 음 길이만큼 누르지 않고 짧게 튕긴다. "
            "자연음만 연주할 수 있다."
        ),
        sustains=False,
        keys=_bindings(_DIATONIC_21),
        accidental=AccidentalPolicy.SKIP,
        out_of_range=RangePolicy.SKIP,
        note_style="white",
        tap_ms=50,
        verified=True,
        aliases=("lyre", "genshin-harp", "windsong", "genshin"),
    )


# 낡은 하프. 글쇠 위치는 바람의 노래 하프와 같다.
# 낮은·가운데 옥타브는 C 도리안(C D Eb F G A Bb), 높은 옥타브는 C 프리기안(C Db Eb F G Ab Bb).
_VINTAGE_LYRE: tuple[tuple[int, str], ...] = (
    (48, "z"),
    (50, "x"),
    (51, "c"),
    (53, "v"),
    (55, "b"),
    (57, "n"),
    (58, "m"),
    (60, "a"),
    (62, "s"),
    (63, "d"),
    (65, "f"),
    (67, "g"),
    (69, "h"),
    (70, "j"),
    (72, "q"),
    (73, "w"),
    (75, "e"),
    (77, "r"),
    (79, "t"),
    (80, "y"),
    (82, "u"),
)


def genshin_vintage_lyre() -> Instrument:
    return Instrument(
        id="genshin-vintage-lyre",
        name="낡은 하프",
        detail=(
            "글쇠는 바람의 노래 하프와 같다. "
            "낮은·가운데 옥타브는 C 도리안(C D E♭ F G A B♭), "
            "높은 옥타브는 C 프리기안(C D♭ E♭ F G A♭ B♭). "
            "그 음만 연주할 수 있고, 짧게 튕긴다."
        ),
        sustains=False,
        keys=_bindings(_VINTAGE_LYRE),
        accidental=AccidentalPolicy.SKIP,
        out_of_range=RangePolicy.SKIP,
        note_style="white",
        tap_ms=50,
        verified=True,
        aliases=("vintage", "vintage-lyre"),
    )


def nte_piano() -> Instrument:
    return Instrument(
        id="nte-piano",
        name="이환 피아노",
        detail=(
            "이환 피아노의 PC 36키 연주 모드. "
            "화면에는 36키가 보이고, 키보드로 누르는 키는 21개다. "
            "21키 모드에서는 반음을 낼 수 없어 바람의 노래 하프와 같은 글쇠다. "
            "음 길이만큼 누른다. Shift는 C·F·G를 반음 올리고, Ctrl은 E·B를 반음 내린다."
        ),
        sustains=True,
        keys=_bindings(_DIATONIC_21),
        accidental=AccidentalPolicy.SKIP,
        out_of_range=RangePolicy.SKIP,
        note_style="nte-piano",
        tap_ms=40,
        verified=True,
        aliases=("nte-piano-36",),
    )


def nte_guitar() -> Instrument:
    return Instrument(
        id="nte-guitar",
        name="이환 기타",
        detail=(
            "이환에서 아카네 린으로 연주할 수 있는 기타의 피아노 건반 모드. "
            "3줄×12반음. 낮은 줄은 E3=A부터 D#4=Enter, "
            "가운데는 E4=Q부터 D#5=], 높은 줄은 E5=1부터 D#6==이다. "
            "음 길이만큼 누른다."
        ),
        sustains=True,
        keys=_chromatic(52, _GUITAR_ROWS),
        accidental=AccidentalPolicy.SNAP,
        tap_ms=40,
        verified=True,
        aliases=("nte-guitar-36",),
    )


_INSTRUMENTS = (genshin_harp(), genshin_vintage_lyre(), nte_piano(), nte_guitar())


def list_instruments() -> tuple[Instrument, ...]:
    return _INSTRUMENTS


def get_instrument(name: str) -> Instrument:
    key = name.casefold()
    for instrument in _INSTRUMENTS:
        names = {instrument.id.casefold(), *(alias.casefold() for alias in instrument.aliases)}
        if key in names:
            return instrument
    known = ", ".join(instrument.id for instrument in _INSTRUMENTS)
    raise InstrumentError(t("unknown_instrument", name=name, known=known))
