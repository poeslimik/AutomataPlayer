from fractions import Fraction

from automata_player.instruments import get_instrument
from automata_player.model import Note
from automata_player.playability import assess, piano_key


def _notes(*pitches: int, together: bool = False) -> list[Note]:
    found = []
    for index, pitch in enumerate(pitches):
        start = 0 if together else index
        found.append(Note(Fraction(start), Fraction(1), pitch, 0, "Piano", 0))
    return found


def test_harp_blocks_accidentals_and_suggests_a_white_key_transpose():
    harp = get_instrument("lyre")
    check = assess(_notes(66), harp)
    assert check.ok is False
    assert check.message == "연주할 수 없는 음이 포함돼 있습니다."
    assert check.suggestion in {1, -1}
    assert assess(_notes(66), harp, check.suggestion or 0).ok


def test_harp_transpose_direction_keeps_more_notes_inside_the_range():
    harp = get_instrument("lyre")
    # B5 때문에 올리면 음역 밖이고, 두 음 내리면 E5·A5가 된다.
    check = assess(_notes(78, 83), harp)
    assert check.suggestion == -2
    assert "내리면" in check.suggestion_text

    low = assess(_notes(48, 54), harp)
    assert low.suggestion == 5
    assert "올리면" in low.suggestion_text


def test_vintage_lyre_uses_dorian_and_phrygian_rows():
    lyre = get_instrument("genshin-vintage-lyre")
    assert lyre.key_for(51) == "c"  # E♭3
    assert lyre.key_for(58) == "m"  # B♭3
    assert lyre.key_for(63) == "d"  # E♭4
    assert lyre.key_for(73) == "w"  # D♭5
    assert lyre.key_for(80) == "y"  # A♭5
    assert lyre.key_for(52) is None  # E3는 낮은 옥타브에 없다
    assert lyre.key_for(74) is None  # D5는 높은 옥타브에 없다
    blocked = assess(_notes(64), lyre)
    assert blocked.ok is False
    assert blocked.message == "연주할 수 없는 음이 포함돼 있습니다."
    assert blocked.suggestion == 1
    assert assess(_notes(64), lyre, blocked.suggestion or 0).ok
    assert assess(_notes(83), lyre).suggestion == -1


def test_piano_folds_bass_notes_into_the_keyboard():
    piano = get_instrument("nte-piano")
    assert piano_key(45, piano) == "n"  # A2 → A3
    assert piano_key(47, piano) == "m"  # B2 → B3
    assert piano_key(42, piano) == "shift+v"  # F#2 → F#3
    assert piano_key(43, piano) == "b"  # G2 → G3
    assert assess(_notes(45, 47, 42, 43), piano).ok


def test_piano_modifier_chords():
    piano = get_instrument("nte-piano")
    assert assess(_notes(61), piano).ok
    assert assess(_notes(68, 66, together=True), piano).ok
    assert assess(_notes(64, 70, together=True), piano).ok is False
    assert assess(_notes(67, 68, together=True), piano).ok is False
    assert assess(_notes(65, 68, together=True), piano).ok is False
    assert assess(_notes(63, 70, together=True), piano).ok
    assert assess(_notes(63, 68, together=True), piano).ok


def test_piano_suggests_a_transpose_that_removes_the_conflict():
    piano = get_instrument("nte-piano")
    notes = _notes(64, 70, together=True)
    check = assess(notes, piano)
    assert check.ok is False
    assert check.suggestion is not None
    assert assess(notes, piano, check.suggestion).ok
