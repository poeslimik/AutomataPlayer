from automata_player.keys import parse_key
from automata_player.pitch import midi_name, tpc_alter


def test_parse_key_splits_modifiers():
    assert parse_key("A") == ("a",)
    assert parse_key("ctrl+shift+a") == ("ctrl", "shift", "a")
    assert parse_key(";") == (";",)
    assert parse_key("\\") == ("\\",)


def test_unknown_key_is_rejected():
    try:
        parse_key("not-a-key")
    except ValueError as exc:
        assert "not-a-key" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_midi_octave_and_tpc_spelling():
    assert midi_name(60) == "C4"
    assert midi_name(48) == "C3"
    assert midi_name(83) == "B5"
    assert tpc_alter(14) == 0
    assert tpc_alter(21) == 1
    assert tpc_alter(9) == -1
