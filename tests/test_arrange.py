from fractions import Fraction
from pathlib import Path

import pytest

from automata_player.instruments import get_instrument, list_instruments
from automata_player.keys import parse_key
from automata_player.model import Note, Score, TempoMark
from automata_player.playback import arrange, map_pitch
from automata_player.score import load_score

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "c_major_scale.mscx"


def _score(notes: list[Note], bpm: float = 120.0) -> Score:
    return Score("t", tuple(notes), (TempoMark(Fraction(0), bpm),), ())


def _note(pitch: int, start: int = 0, duration: int = 1, alter: int | None = None) -> Note:
    return Note(Fraction(start), Fraction(duration), pitch, 0, "Piano", 0, alter)


def test_every_builtin_key_parses():
    seen = set()
    for instrument in list_instruments():
        assert instrument.id not in seen
        seen.add(instrument.id)
        assert instrument.keys
        for binding in instrument.keys:
            parse_key(binding.key)


def test_scale_maps_onto_the_genshin_harp():
    result = arrange(load_score(EXAMPLE), get_instrument("lyre"))
    downs = [action for action in result.actions if action.down]
    assert [action.key for action in downs] == ["a", "s", "d", "f", "g", "h", "j", "q"]
    assert [action.label for action in downs] == ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]
    assert downs[0].time == 0
    assert downs[1].time == 0.5
    assert result.actions[1].time == 0.05  # 짧은 튕김
    assert result.skipped == ()


def test_harp_does_not_snap_or_fold_unplayable_notes():
    harp = get_instrument("lyre")
    result = arrange(_score([_note(61), _note(84, start=1)]), harp)
    assert result.actions == ()
    assert result.skipped == (61, 84)


def test_piano_plays_shift_and_ctrl_semitones():
    piano = get_instrument("nte-piano")
    score = _score([_note(61), _note(63, start=1), _note(68, start=2), _note(70, start=3)])
    downs = [action for action in arrange(score, piano).actions if action.down]
    assert [action.key for action in downs] == ["shift+a", "ctrl+d", "shift+g", "ctrl+j"]


def test_piano_holds_and_retrigger_leaves_a_gap():
    piano = get_instrument("nte-piano")
    score = _score([_note(60, 0, 1), _note(60, 1, 1)])
    actions = arrange(score, piano).actions
    downs = [action.time for action in actions if action.down]
    ups = [action.time for action in actions if not action.down]
    assert downs == [0.0, 0.5]
    assert ups[0] == pytest.approx(0.47)
    assert ups[1] == pytest.approx(1.0)


def test_overlapping_same_key_is_retriggered_and_released_with_the_longer_note():
    piano = get_instrument("nte-piano")
    # 0–2초를 누르던 중 1초에 더 짧은 같은 음이 다시 나온다. 최종 뗌은 2초.
    shorter = _score([_note(60, 0, 4), _note(60, 2, 1)])
    actions = arrange(shorter, piano).actions
    assert [action.time for action in actions if action.down] == [0.0, 1.0]
    ups = [action.time for action in actions if not action.down]
    assert ups[0] == pytest.approx(0.97)
    assert ups[1] == pytest.approx(2.0)

    # 뒤에 나온 음이 더 길면 그 끝에서 뗀다.
    longer = _score([_note(60, 0, 2), _note(60, 1, 4)])
    later = [action.time for action in arrange(longer, piano).actions if not action.down]
    assert later[-1] == pytest.approx(2.5)


def test_tied_score_is_one_press_on_a_sustaining_instrument():
    from automata_player.score.mscz import parse_mscx

    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<museScore version="4.20"><Score><Division>480</Division>
  <Part><Staff id="1"><Measure><voice>
    <Tempo><tempo>2</tempo></Tempo>
    <Chord><durationType>quarter</durationType><Note><pitch>60</pitch>
      <Spanner type="Tie"><Tie><next><location><fractions>1/4</fractions></location></next></Tie></Spanner>
    </Note></Chord>
    <Chord><durationType>quarter</durationType><Note><pitch>60</pitch>
      <Spanner type="Tie"><Tie><prev><location><fractions>-1/4</fractions></location></prev></Tie></Spanner>
    </Note></Chord>
  </voice></Measure></Staff><trackName>Piano</trackName></Part>
</Score></museScore>"""
    result = arrange(parse_mscx(xml, title="tie"), get_instrument("nte-piano"))
    assert [action.down for action in result.actions] == [True, False]
    assert result.actions[0].time == 0
    assert result.actions[1].time == pytest.approx(1.0)


def test_guitar_is_chromatic_from_e3_and_folds_octaves():
    guitar = get_instrument("nte-guitar")
    assert guitar.low == 52 and guitar.high == 87
    assert guitar.verified is True
    assert guitar.key_for(52) == "a"  # E3
    assert guitar.key_for(63) == "enter"  # D#4
    assert guitar.key_for(60) == "l"  # C4
    assert guitar.key_for(64) == "q"  # E4
    assert guitar.key_for(75) == "]"  # D#5
    assert guitar.key_for(76) == "1"  # E5
    assert guitar.key_for(87) == "="  # D#6
    assert map_pitch(36, guitar) == 60  # C2 -> C4
    assert map_pitch(61, guitar) == 61


def test_a_chord_presses_every_key_at_the_same_time():
    score = _score(
        [
            _note(60),
            _note(64),
        ]
    )
    downs = [action for action in arrange(score, get_instrument("lyre")).actions if action.down]
    assert [(action.key, action.time) for action in downs] == [("a", 0.0), ("d", 0.0)]
