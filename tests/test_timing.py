from fractions import Fraction

from automata_player.model import TempoMark
from automata_player.timing import quarters_to_seconds


def test_default_tempo_is_120_bpm():
    assert quarters_to_seconds(Fraction(1), ()) == 0.5
    assert quarters_to_seconds(Fraction(0), ()) == 0.0


def test_tempo_change_splits_the_timeline():
    marks = (
        (Fraction(0), 120.0),
        (Fraction(4), 60.0),
    )
    assert quarters_to_seconds(Fraction(4), marks) == 2.0
    assert quarters_to_seconds(Fraction(5), marks) == 3.0


def test_later_mark_at_the_same_position_wins():
    marks = (
        (Fraction(0), 60.0),
        (Fraction(0), 120.0),
    )
    assert quarters_to_seconds(Fraction(2), marks) == 1.0


def test_fermata_stretch_slows_only_its_span():
    from automata_player.timing import quarters_to_seconds

    # 120 BPM에서 1박은 0.5초. 두 번째 박을 2배로 늘리면 그 박은 1초, 3박 지점은 2초.
    stretches = ((Fraction(1), Fraction(1), 2.0),)
    assert quarters_to_seconds(Fraction(1), ((Fraction(0), 120.0),), stretches) == 0.5
    assert quarters_to_seconds(Fraction(2), ((Fraction(0), 120.0),), stretches) == 1.5
    assert quarters_to_seconds(Fraction(3), ((Fraction(0), 120.0),), stretches) == 2.0


def test_score_seconds_follow_tempo_marks():
    from automata_player.model import Score

    score = Score("t", (), (TempoMark(Fraction(0), 60.0),), ())
    assert score.seconds_at(Fraction(1)) == 1.0
