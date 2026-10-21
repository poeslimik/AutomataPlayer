import zipfile
from fractions import Fraction
from io import BytesIO
from pathlib import Path

import pytest

from automata_player.model import ScoreError
from automata_player.score.mscz import load_score, parse_mscx, parse_mscz

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "c_major_scale.mscx"


def _score(body: str, *, title: str = "Test") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<museScore version="4.20">
  <Score>
    <Division>480</Division>
    <metaTag name="workTitle">{title}</metaTag>
    <Part>
      <Staff id="1">
        {body}
      </Staff>
      <trackName>Piano</trackName>
    </Part>
  </Score>
</museScore>
""".encode()


def _voice(contents: str, *, length: str | None = None) -> str:
    attr = f' len="{length}"' if length else ""
    return f"<Measure{attr}><voice>{contents}</voice></Measure>"


def _chord(pitch: int, duration: str = "quarter", *, dots: int = 0, extra: str = "") -> str:
    dots_xml = f"<dots>{dots}</dots>" if dots else ""
    return (
        f"<Chord><durationType>{duration}</durationType>{dots_xml}"
        f"<Note><pitch>{pitch}</pitch>{extra}</Note></Chord>"
    )


def test_example_scale_is_eight_quarters_at_120():
    score = load_score(EXAMPLE)
    assert score.title == "C major scale"
    assert [note.pitch for note in score.notes] == [60, 62, 64, 65, 67, 69, 71, 72]
    assert score.notes[0].start == 0
    assert score.notes[1].start == 1
    assert score.notes[4].start == 4
    assert score.duration_seconds == pytest.approx(4.0)
    assert score.tempos[0].bpm == pytest.approx(120)
    assert score.parts[0].name == "Piano"


def test_chord_rest_and_second_voice_share_a_downbeat():
    xml = _score(
        _voice(
            _chord(60)
            + "<Rest><durationType>quarter</durationType></Rest>"
            + _chord(64, "half")
            + "</voice><voice>"
            + "<Chord><durationType>half</durationType>"
            + "<Note><pitch>48</pitch></Note><Note><pitch>55</pitch></Note></Chord>"
        )
    )
    score = parse_mscx(xml, title="choir")
    by_pitch = {note.pitch: note for note in score.notes}
    assert set(by_pitch) == {48, 55, 60, 64}
    assert by_pitch[60].start == 0 and by_pitch[60].duration == 1
    assert by_pitch[48].start == 0 and by_pitch[48].duration == 2
    assert by_pitch[55].duration == 2
    assert by_pitch[64].start == 2 and by_pitch[64].duration == 2
    assert score.duration_seconds == pytest.approx(2.0)


def test_dotted_quarter_and_eighth_triplet():
    xml = _score(
        _voice(
            _chord(60, dots=1)
            + "<Tuplet><normalNotes>2</normalNotes><actualNotes>3</actualNotes>"
            + "<baseNote>eighth</baseNote></Tuplet>"
            + _chord(62, "eighth")
            + _chord(64, "eighth")
            + _chord(65, "eighth")
            + "<endTuplet/>"
            + _chord(67, "quarter")
        )
    )
    score = parse_mscx(xml, title="rhythm")
    assert score.notes[0].duration == Fraction(3, 2)
    assert [note.start for note in score.notes[1:4]] == [
        Fraction(3, 2),
        Fraction(3, 2) + Fraction(1, 3),
        Fraction(3, 2) + Fraction(2, 3),
    ]
    assert score.notes[1].duration == Fraction(1, 3)
    assert score.notes[4].start == Fraction(3, 2) + 1
    assert score.notes[4].pitch == 67


def test_ties_become_one_held_note():
    start = (
        "<Spanner type=\"Tie\"><Tie><next><location>"
        "<fractions>1/4</fractions></location></next></Tie></Spanner>"
    )
    end = (
        "<Spanner type=\"Tie\"><Tie><prev><location>"
        "<fractions>-1/4</fractions></location></prev></Tie></Spanner>"
    )
    xml = _score(_voice(_chord(60, extra=start) + _chord(60, extra=end) + _chord(62)))
    score = parse_mscx(xml, title="tie")
    assert [(note.pitch, note.duration) for note in score.notes] == [
        (60, Fraction(2)),
        (62, Fraction(1)),
    ]
    assert score.notes[1].start == 2


def test_acciaccatura_at_the_start_does_not_sound():
    xml = _score(
        _voice(
            "<Chord><acciaccatura/><durationType>eighth</durationType>"
            "<Note><pitch>62</pitch></Note></Chord>"
            + _chord(60)
        )
    )
    score = parse_mscx(xml, title="ornament")
    assert [(note.pitch, note.start, note.duration) for note in score.notes] == [
        (60, Fraction(0), Fraction(1)),
    ]


def test_acciaccatura_takes_the_end_of_the_previous_note():
    xml = _score(
        _voice(
            _chord(60)
            + "<Chord><acciaccatura/><durationType>eighth</durationType>"
            "<Note><pitch>62</pitch></Note></Chord>"
            + _chord(64)
        )
    )
    score = parse_mscx(xml, title="before-beat")
    assert [(note.pitch, note.start, note.duration) for note in score.notes] == [
        (60, Fraction(0), Fraction(1, 2)),
        (62, Fraction(1, 2), Fraction(1, 2)),
        (64, Fraction(1), Fraction(1)),
    ]


def test_two_acciaccaturas_split_the_stolen_time():
    xml = _score(
        _voice(
            _chord(60)
            + "<Chord><acciaccatura/><durationType>eighth</durationType>"
            "<Note><pitch>64</pitch></Note></Chord>"
            + "<Chord><acciaccatura/><durationType>16th</durationType>"
            "<Note><pitch>65</pitch></Note></Chord>"
            + _chord(66)
        )
    )
    score = parse_mscx(xml, title="two-grace")
    assert [(note.pitch, note.start, note.duration) for note in score.notes] == [
        (60, Fraction(0), Fraction(1, 2)),
        (64, Fraction(1, 2), Fraction(1, 4)),
        (65, Fraction(3, 4), Fraction(1, 4)),
        (66, Fraction(1), Fraction(1)),
    ]


def test_appoggiatura_takes_half_of_the_main_note():
    xml = _score(
        _voice(
            "<Chord><appoggiatura/><durationType>quarter</durationType>"
            "<Note><pitch>62</pitch></Note></Chord>"
            + _chord(60)
        )
    )
    score = parse_mscx(xml, title="appoggiatura")
    assert [(note.pitch, note.start, note.duration) for note in score.notes] == [
        (62, Fraction(0), Fraction(1, 2)),
        (60, Fraction(1, 2), Fraction(1, 2)),
    ]


def test_two_appoggiaturas_share_half_the_main_note_equally():
    xml = _score(
        _voice(
            "<Chord><appoggiatura/><durationType>quarter</durationType>"
            "<Note><pitch>70</pitch></Note></Chord>"
            "<Chord><appoggiatura/><durationType>eighth</durationType>"
            "<Note><pitch>69</pitch></Note></Chord>"
            + _chord(58)
        )
    )
    score = parse_mscx(xml, title="two-appoggiatura")
    assert [(note.pitch, note.start, note.duration) for note in score.notes] == [
        (70, Fraction(0), Fraction(1, 4)),
        (69, Fraction(1, 4), Fraction(1, 4)),
        (58, Fraction(1, 2), Fraction(1, 2)),
    ]


def test_end_repeat_plays_the_section_twice():
    xml = _score(
        _voice(_chord(60) + '<BarLine><subtype>start-repeat</subtype></BarLine>', length="1/4")
        + _voice(_chord(62) + '<BarLine><subtype>end-repeat</subtype></BarLine>', length="1/4")
    )
    score = parse_mscx(xml, title="repeat")
    assert [note.pitch for note in score.notes] == [60, 62, 60, 62]
    assert [note.start for note in score.notes] == [0, 1, 2, 3]


def test_voltas_skip_the_ending_that_does_not_match_the_pass():
    first = (
        '<Spanner type="Volta"><Volta><endings>1</endings>'
        "<next><location><measures>1</measures></location></next></Volta></Spanner>"
        + _chord(62)
        + '<BarLine><subtype>end-repeat</subtype></BarLine>'
    )
    second = (
        '<Spanner type="Volta"><Volta><endings>2</endings>'
        "<next><location><measures>1</measures></location></next></Volta></Spanner>"
        + _chord(64)
    )
    xml = _score(
        _voice('<BarLine><subtype>start-repeat</subtype></BarLine>' + _chord(60))
        + _voice(first)
        + _voice(second)
    )
    score = parse_mscx(xml, title="volta")
    assert [note.pitch for note in score.notes] == [60, 62, 60, 64]


def test_da_capo_al_fine_returns_to_the_start_and_stops():
    fine = "<Marker><label>fine</label></Marker>" + _chord(62)
    jump = (
        _chord(65)
        + "<Jump><jumpTo></jumpTo><playUntil>fine</playUntil><continueAt></continueAt></Jump>"
    )
    xml = _score(_voice(_chord(60)) + _voice(fine) + _voice(_chord(64)) + _voice(jump))
    score = parse_mscx(xml, title="dc")
    assert [note.pitch for note in score.notes] == [60, 62, 64, 65, 60, 62]
    assert "flow" not in score.warnings


def test_dal_segno_al_coda_jumps_to_the_coda():
    segno = "<Marker><label>segno</label></Marker>" + _chord(62)
    to_coda = "<Marker><label>coda</label></Marker>" + _chord(64)
    jump = (
        _chord(65)
        + "<Jump><jumpTo>segno</jumpTo><playUntil>coda</playUntil>"
        + "<continueAt>codab</continueAt></Jump>"
    )
    coda = "<Marker><label>codab</label></Marker>" + _chord(67)
    xml = _score(_voice(_chord(60)) + _voice(segno) + _voice(to_coda) + _voice(jump) + _voice(coda))
    score = parse_mscx(xml, title="ds")
    assert [note.pitch for note in score.notes] == [60, 62, 64, 65, 62, 64, 67]


def test_pickup_and_mid_measure_segno_do_not_replay_the_opening():
    segno = _chord(62) + "<Marker><label>segno</label></Marker>" + _chord(64) + _chord(65)
    fine = _chord(67) + "<Marker><label>fine</label></Marker>" + "<Rest><durationType>quarter</durationType></Rest>" + _chord(71)
    jump = (
        _chord(69)
        + "<Jump><jumpTo>segno</jumpTo><playUntil>fine</playUntil><continueAt></continueAt></Jump>"
        + "<Rest><durationType>quarter</durationType></Rest>"
        + _chord(72)
    )
    xml = _score(
        _voice(_chord(60), length="1/4")
        + _voice(segno)
        + _voice(fine)
        + _voice(jump)
    )
    score = parse_mscx(xml, title="pickup-segno")
    assert [note.pitch for note in score.notes] == [60, 62, 64, 65, 67, 71, 69, 64, 65, 67]


def test_arpeggio_rolls_up_or_down_and_a_bracket_rolls_upward():
    rolled = (
        "<Chord><Arpeggio><subtype>0</subtype></Arpeggio><durationType>quarter</durationType>"
        "<Note><pitch>60</pitch></Note><Note><pitch>64</pitch></Note><Note><pitch>67</pitch></Note></Chord>"
    )
    downward = (
        "<Chord><Arpeggio><subtype>2</subtype></Arpeggio><durationType>quarter</durationType>"
        "<Note><pitch>60</pitch></Note><Note><pitch>64</pitch></Note><Note><pitch>67</pitch></Note></Chord>"
    )
    bracket = (
        "<Chord><Arpeggio><subtype>3</subtype></Arpeggio><durationType>quarter</durationType>"
        "<Note><pitch>60</pitch></Note><Note><pitch>67</pitch></Note></Chord>"
    )
    upward = parse_mscx(_score(_voice(rolled)), title="up")
    assert [note.pitch for note in upward.notes] == [60, 64, 67]
    assert [note.start for note in upward.notes] == [0, Fraction(133, 1000), Fraction(266, 1000)]
    assert upward.notes[0].duration == 1
    assert upward.notes[2].duration == Fraction(734, 1000)

    down = parse_mscx(_score(_voice(downward)), title="down")
    assert [note.pitch for note in down.notes] == [67, 64, 60]
    assert [note.start for note in down.notes] == [0, Fraction(133, 1000), Fraction(266, 1000)]

    together = parse_mscx(_score(_voice(bracket)), title="bracket")
    assert [note.pitch for note in together.notes] == [60, 67]
    assert [note.start for note in together.notes] == [0, Fraction(133, 1000)]


def test_glissando_and_portamento_fill_the_semitones_between_notes():
    glide = (
        "<Chord><durationType>quarter</durationType><Note><pitch>60</pitch>"
        '<Spanner type="Glissando"><Glissando><subtype>glissando</subtype>'
        "<next><location><fractions>1/4</fractions></location></next></Glissando></Spanner>"
        "</Note></Chord>"
        + _chord(64)
    )
    portamento = (
        "<Chord><durationType>quarter</durationType><Note><pitch>60</pitch>"
        '<Spanner type="Glissando"><Glissando><subtype>portamento</subtype>'
        "<next><location><fractions>1/4</fractions></location></next></Glissando></Spanner>"
        "</Note></Chord>"
        + _chord(64)
    )
    sibling = (
        "<Chord><durationType>quarter</durationType><Note><pitch>60</pitch>"
        '<Spanner type="Glissando"><Glissando><glissandoStyle>chromatic</glissandoStyle></Glissando>'
        "<next><location><fractions>1/4</fractions></location></next></Spanner>"
        "</Note></Chord>"
        + _chord(64)
    )
    for body, title in ((glide, "gliss"), (portamento, "port"), (sibling, "linked")):
        score = parse_mscx(_score(_voice(body)), title=title)
        assert [note.pitch for note in score.notes] == [60, 61, 62, 63, 64]
        assert [note.start for note in score.notes[:4]] == [0, Fraction(1, 4), Fraction(1, 2), Fraction(3, 4)]
        assert score.notes[4].start == 1


def test_enabled_trill_alternates_with_the_diatonic_note_above():
    trill = (
        "<Chord><durationType>quarter</durationType>"
        "<Ornament><subtype>trill</subtype></Ornament>"
        "<Note><pitch>60</pitch><tpc>14</tpc></Note></Chord>"
    )
    score = parse_mscx(_score(_voice(trill)), title="trill")
    assert [note.pitch for note in score.notes] == [60, 62, 60, 62, 60, 62, 60, 62]
    assert [note.duration for note in score.notes] == [Fraction(1, 8)] * 8

    minor = (
        "<Chord><durationType>quarter</durationType>"
        "<Ornament><subtype>trill</subtype>"
        "<intervalAbove>second,minor</intervalAbove>"
        "</Ornament><Note><pitch>60</pitch><tpc>14</tpc></Note></Chord>"
    )
    half = parse_mscx(_score(_voice(minor)), title="minor-trill")
    assert half.notes[1].pitch == 61

    major = (
        "<Chord><durationType>quarter</durationType>"
        "<Ornament><subtype>trill</subtype>"
        "<intervalAbove>second,major</intervalAbove>"
        "</Ornament><Note><pitch>64</pitch><tpc>18</tpc></Note></Chord>"
    )
    whole = parse_mscx(_score(_voice(major)), title="major-trill")
    assert whole.notes[1].pitch == 66

    muted = (
        "<Chord><durationType>quarter</durationType>"
        "<Ornament><subtype>trill</subtype><play>0</play></Ornament>"
        "<Note><pitch>60</pitch><tpc>14</tpc></Note></Chord>"
    )
    silent = parse_mscx(_score(_voice(muted)), title="muted-trill")
    assert [(note.pitch, note.duration) for note in silent.notes] == [(60, Fraction(1))]

    in_f = (
        "<KeySig><accidental>-1</accidental></KeySig>"
        "<Chord><durationType>quarter</durationType>"
        "<Articulation><subtype>ornamentTrill</subtype></Articulation>"
        "<Note><pitch>71</pitch><tpc>19</tpc></Note></Chord>"
    )
    flat_key = parse_mscx(_score(_voice(in_f)), title="f-trill")
    assert flat_key.notes[1].pitch == 72

    sharpened = (
        "<Chord><durationType>quarter</durationType>"
        "<Ornament><subtype>trill</subtype>"
        "<Accidental><subtype>accidentalSharp</subtype></Accidental></Ornament>"
        "<Note><pitch>60</pitch><tpc>14</tpc></Note></Chord>"
    )
    sharp = parse_mscx(_score(_voice(sharpened)), title="sharp-trill")
    assert sharp.notes[1].pitch == 63


def test_cadenza_measure_pushes_the_following_bar():
    notes = "".join(_chord(60 + index) for index in range(6))
    xml = _score("<Measure><cadenza/><voice>" + notes + "</voice></Measure>" + _voice(_chord(72)))
    score = parse_mscx(xml, title="cadenza")
    assert [note.start for note in score.notes] == list(range(7))
    assert score.notes[-1].pitch == 72


def test_missing_segno_is_reported():
    jump = "<Jump><jumpTo>segno</jumpTo><playUntil>fine</playUntil><continueAt></continueAt></Jump>"
    xml = _score(_voice(_chord(60) + jump))
    score = parse_mscx(xml, title="missing")
    assert "flow" in score.warnings
    assert [note.pitch for note in score.notes] == [60]


def test_text_tempo_and_missing_tempo():
    xml = _score(_voice("<Tempo><text>Allegro = 90</text></Tempo>" + _chord(60)))
    score = parse_mscx(xml, title="allegro")
    assert score.tempos[0].bpm == pytest.approx(90)

    bare = _score(_voice(_chord(60, "half")))
    assumed = parse_mscx(bare, title="bare")
    assert assumed.duration_seconds == pytest.approx(1.0)
    assert "tempo-default" in assumed.warnings


def test_tempo_change_between_measures():
    xml = _score(
        _voice("<Tempo><tempo>2</tempo></Tempo>" + _chord(60, "whole"))
        + _voice("<Tempo><tempo>1</tempo></Tempo>" + _chord(62, "quarter"))
    )
    score = parse_mscx(xml, title="rit")
    assert score.notes[1].start == 4
    assert score.seconds_at(score.notes[1].start) == pytest.approx(2.0)
    assert score.duration_seconds == pytest.approx(3.0)


def test_measure_rest_in_three_four_pushes_the_next_bar():
    xml = _score(
        _voice(
            "<TimeSig><sigN>3</sigN><sigD>4</sigD></TimeSig>"
            "<Rest><durationType>measure</durationType></Rest>"
        )
        + _voice(_chord(60))
    )
    score = parse_mscx(xml, title="rest")
    assert len(score.notes) == 1
    assert score.notes[0].start == 3


def test_pickup_measure_uses_len_attribute():
    xml = _score(_voice(_chord(60), length="1/4") + _voice(_chord(62)))
    score = parse_mscx(xml, title="pickup")
    assert score.notes[0].start == 0
    assert score.notes[1].start == 1


def test_percussion_staff_is_dropped():
    xml = _score(
        '<StaffType group="percussion"></StaffType>' + _voice(_chord(36))
    )
    score = parse_mscx(xml, title="drum")
    assert score.notes == ()
    assert "percussion" in score.warnings


def test_part_filter_uses_number_or_name():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<museScore version="4.20"><Score>
  <Part><Staff id="1"><Measure><voice>
    <Chord><durationType>quarter</durationType><Note><pitch>60</pitch></Note></Chord>
  </voice></Measure></Staff><trackName>Melody</trackName></Part>
  <Part><Staff id="2"><Measure><voice>
    <Chord><durationType>quarter</durationType><Note><pitch>48</pitch></Note></Chord>
  </voice></Measure></Staff><trackName>Bass</trackName></Part>
</Score></museScore>""".encode()
    score = parse_mscx(xml, title="duo")
    assert [note.pitch for note in score.select_parts(["2"]).notes] == [48]
    assert [note.pitch for note in score.select_parts(["Melody"]).notes] == [60]
    with pytest.raises(ScoreError):
        score.select_parts(["Brass"])


def test_section_break_inserts_three_seconds():
    xml = _score(
        "<Measure><voice><Tempo><tempo>2</tempo></Tempo>"
        + _chord(60)
        + "</voice><LayoutBreak><subtype>section</subtype></LayoutBreak></Measure>"
        + _voice(_chord(62))
    )
    score = parse_mscx(xml, title="section")
    assert score.seconds_at(score.notes[0].end, inclusive=False) == pytest.approx(0.5)
    assert score.seconds_at(score.notes[1].start) == pytest.approx(5.0)


def test_fermata_holds_its_note_and_delays_the_next():
    xml = _score(
        _voice(
            "<Tempo><tempo>2</tempo></Tempo>"
            "<Chord><durationType>quarter</durationType>"
            "<Fermata><subtype>fermataAbove</subtype></Fermata>"
            "<Note><pitch>60</pitch></Note></Chord>"
            + _chord(62)
        )
    )
    score = parse_mscx(xml, title="pause")
    assert len(score.stretches) == 1
    assert score.stretches[0].factor == 2.0
    assert score.seconds_at(score.notes[0].end) == pytest.approx(1.0)
    assert score.seconds_at(score.notes[1].start) == pytest.approx(1.0)
    assert score.duration_seconds == pytest.approx(1.5)


def test_explicit_fermata_stretch_overrides_the_symbol():
    xml = _score(
        _voice(
            "<Chord><durationType>quarter</durationType>"
            "<Fermata><subtype>fermataAbove</subtype><timeStretch>3</timeStretch></Fermata>"
            "<Note><pitch>60</pitch></Note></Chord>"
        )
    )
    score = parse_mscx(xml, title="long")
    assert score.stretches[0].factor == 3.0
    assert score.duration_seconds == pytest.approx(1.5)


def test_musescore_4_keeps_measures_beside_the_part():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<museScore version="4.70"><Score>
  <Division>480</Division>
  <metaTag name="workTitle">Clarinet</metaTag>
  <Part>
    <Staff><StaffType group="pitched"></StaffType></Staff>
    <trackName>Clarinet</trackName>
  </Part>
  <Staff id="1">
    <Measure len="1/4">
      <voice>
        <Tempo><tempo>2</tempo></Tempo>
        <Chord><durationType>quarter</durationType><Note><pitch>64</pitch></Note></Chord>
      </voice>
    </Measure>
  </Staff>
</Score></museScore>""".encode()
    score = parse_mscx(xml, title="fallback")
    assert score.title == "Clarinet"
    assert score.parts[0].name == "Clarinet"
    assert [(note.pitch, note.start) for note in score.notes] == [(64, 0)]
    assert score.tempos[0].bpm == pytest.approx(120)


def test_mscz_archive_round_trip():
    xml = _score(_voice(_chord(60)), title="Zipped")
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("folder/song.mscx", xml)
        archive.writestr("thumb.png", b"not-a-score")
    score = parse_mscz(buffer.getvalue(), title="ignored")
    assert score.title == "Zipped"
    assert score.notes[0].pitch == 60


def test_load_score_rejects_missing_and_unknown_files(tmp_path: Path):
    missing = tmp_path / "nope.mscz"
    with pytest.raises(ScoreError):
        load_score(missing)
    text = tmp_path / "notes.txt"
    text.write_text("hello", encoding="utf-8")
    with pytest.raises(ScoreError):
        load_score(text)


def test_unknown_duration_is_an_error():
    xml = _score(_voice("<Chord><durationType>semiquaver</durationType><Note><pitch>60</pitch></Note></Chord>"))
    with pytest.raises(ScoreError, match="semiquaver"):
        parse_mscx(xml, title="bad")


def test_csharp_tpc_is_kept_for_later_mapping():
    xml = _score(_voice(_chord(61, extra="<tpc>21</tpc>")))
    score = parse_mscx(xml, title="sharp")
    assert score.notes[0].alter == 1
