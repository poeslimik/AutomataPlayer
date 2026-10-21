from pathlib import Path

from automata_player.cli import main

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "c_major_scale.mscx"


def test_inspect_example(capsys):
    assert main(["inspect", str(EXAMPLE)]) == 0
    out = capsys.readouterr().out
    assert "C major scale" in out
    assert "8개" in out
    assert "4.00초" in out
    assert "120" in out
    assert "C4" in out


def test_instruments_lists_the_three_profiles(capsys):
    assert main(["instruments"]) == 0
    out = capsys.readouterr().out
    assert "lyre" in out
    assert "nte-piano" in out
    assert "nte-guitar" in out
    assert "키 배치 확인됨" in out
    assert "키 배치 미확인" not in out


def test_dry_run_play_prints_harp_keys(capsys):
    assert main(["play", str(EXAMPLE), "--instrument", "lyre"]) == 0
    out = capsys.readouterr().out
    assert "하프" in out
    assert "누름" in out
    assert "a" in out
    assert "q" in out
    assert "미리보기 끝" in out


def test_unknown_instrument_and_missing_score(capsys):
    assert main(["play", str(EXAMPLE), "--instrument", "theremin"]) == 1
    error = capsys.readouterr().err
    assert "알 수 없는 악기" in error

    assert main(["inspect", "missing.mscz"]) == 1
    assert "찾을 수 없습니다" in capsys.readouterr().err
