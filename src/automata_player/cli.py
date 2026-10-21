"""명령줄 진입점.

기본 백엔드는 dry-run이라 키를 누르지 않고 어떤 글쇠가 나갈지만 보여 준다.
게임에 실제로 넣으려면 --backend windows 로 바꾸고, 카운트다운 동안 게임 창을 선택한다.
"""

from __future__ import annotations

import argparse
import sys

from automata_player.i18n import instrument_detail, instrument_name, t, translate_warning
from automata_player.instruments import get_instrument, list_instruments
from automata_player.model import AutomataError, Score
from automata_player.pitch import midi_name
from automata_player.playability import assess
from automata_player.playback import arrange, open_backend, play
from automata_player.playback.arrange import KeyAction
from automata_player.playback.backend import windows_stop_key_down
from automata_player.score import load_score

_DRY_RUN = frozenset({"dry-run", "dryrun", "preview"})


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    if argv is None:
        argv = sys.argv[1:]
    if not argv or argv == ["gui"]:
        from automata_player.ui.app import run_gui

        return run_gui()
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except AutomataError as exc:
        print(t("error", message=exc), file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="automata-player",
        description="MuseScore 악보를 게임 악기 키 입력으로 연주합니다.",
        epilog=(
            "예시:\n"
            "  automata-player\n"
            "  automata-player instruments\n"
            "  automata-player inspect examples/c_major_scale.mscx\n"
            "  automata-player play examples/c_major_scale.mscx --instrument genshin-lyre\n"
            "  automata-player play song.mscz --instrument nte-piano --backend windows\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    instruments = sub.add_parser("instruments", help="사용할 수 있는 악기")
    instruments.set_defaults(handler=_show_instruments)

    inspect = sub.add_parser("inspect", help="악보의 음표 수, 템포, 음역을 봅니다")
    inspect.add_argument("score", help=".mscz 또는 .mscx 파일")
    inspect.set_defaults(handler=_inspect)

    play_parser = sub.add_parser("play", help="악보를 연주하거나 키 입력을 미리 봅니다")
    play_parser.add_argument("score", help=".mscz 또는 .mscx 파일")
    play_parser.add_argument(
        "--instrument",
        "-i",
        required=True,
        help="genshin-lyre, genshin-vintage-lyre, nte-piano, nte-guitar",
    )
    play_parser.add_argument(
        "--backend",
        "-b",
        default="dry-run",
        help="dry-run(기본, 키를 누르지 않음), windows, pynput, auto",
    )
    play_parser.add_argument("--speed", type=float, default=1.0, help="1보다 크면 빨라집니다")
    play_parser.add_argument("--transpose", type=int, default=0, help="반음 단위 이조")
    play_parser.add_argument(
        "--part",
        action="append",
        help="파트 번호(1부터) 또는 이름. 여러 번 지정할 수 있습니다",
    )
    play_parser.add_argument(
        "--countdown",
        type=float,
        default=None,
        help="실제 입력 전 대기 초. 기본 3초",
    )
    play_parser.add_argument("--tap-ms", type=int, default=None, help="짧게 누르는 시간(ms)")
    play_parser.add_argument(
        "--realtime",
        action="store_true",
        help="미리보기에서도 박자대로 기다립니다",
    )
    play_parser.set_defaults(handler=_play)
    return parser


def _show_instruments(_args: argparse.Namespace) -> int:
    for instrument in list_instruments():
        state = t("verified") if instrument.verified else t("unverified")
        touch = t("touch_hold") if instrument.sustains else t("touch_tap")
        scale = t("scale_chromatic") if instrument.chromatic else t("scale_white")
        print(instrument.id)
        print(f"  {instrument_name(instrument)}")
        print(
            t(
                "instrument_summary",
                count=len(instrument.keys),
                range=instrument.range_label,
                scale=scale,
                touch=touch,
                state=state,
            )
        )
        print(f"  {instrument_detail(instrument)}")
        print()
    return 0


def _inspect(args: argparse.Namespace) -> int:
    print(format_score(load_score(args.score)))
    return 0


def format_score(score: Score) -> str:
    parts = ", ".join(f"{part.index + 1}. {part.name}" for part in score.parts) or t("score_no_parts")
    lines = [
        t("score_title", title=score.title),
        t("score_parts", parts=parts),
        t("score_notes", count=len(score.notes)),
        t("score_length", seconds=score.duration_seconds),
    ]
    if score.notes:
        low = min(note.pitch for note in score.notes)
        high = max(note.pitch for note in score.notes)
        lines.append(t("score_range", low=midi_name(low), high=midi_name(high)))
    lines.append(t("score_tempo"))
    for mark in score.tempos[:8]:
        lines.append(t("score_tempo_mark", beat=float(mark.position), bpm=mark.bpm))
    if len(score.tempos) > 8:
        lines.append(t("score_more", count=len(score.tempos) - 8))
    if score.stretches:
        lines.append(t("score_fermata", count=len(score.stretches)))
    if score.warnings:
        lines.append(t("score_warnings"))
        lines.extend(f"  {translate_warning(warning)}" for warning in score.warnings)
    return "\n".join(lines)


def _play(args: argparse.Namespace) -> int:
    score = load_score(args.score).select_parts(list(args.part or []))
    instrument = get_instrument(args.instrument)
    check = assess(score.notes, instrument, args.transpose)
    if not check.ok:
        print(check.notice, file=sys.stderr)
        return 1
    result = arrange(score, instrument, transpose=args.transpose, tap_ms=args.tap_ms)
    if not result.actions:
        print(t("no_keys"), file=sys.stderr)
        return 1

    real_input = args.backend.casefold() not in _DRY_RUN
    immediate = not (args.realtime or real_input)
    countdown = args.countdown
    if countdown is None:
        countdown = 0.0 if not real_input else 3.0

    print(t("log_title", title=score.title))
    print(t("log_instrument", name=instrument_name(instrument), id=instrument.id))
    if not instrument.verified:
        print(t("log_unverified"))
    print(t("log_stats", count=len(score.notes), seconds=score.duration_seconds, speed=args.speed))
    if args.transpose:
        print(t("log_transpose", semitones=args.transpose))
    if result.skipped:
        shown = ", ".join(midi_name(pitch) for pitch in result.skipped[:6])
        extra = "" if len(result.skipped) <= 6 else t("log_skipped_more", count=len(result.skipped) - 6)
        print(t("log_skipped", count=len(result.skipped), shown=shown, extra=extra))
    for warning in score.warnings:
        print(t("log_warning", warning=translate_warning(warning)))
    if real_input and countdown <= 0:
        print(t("log_no_wait"))
    if not real_input:
        print(t("log_header"))

    try:
        with open_backend(args.backend) as backend:
            finished = play(
                result.actions,
                backend,
                speed=args.speed,
                countdown=countdown,
                immediate=immediate,
                should_stop=(lambda: False) if immediate else windows_stop_key_down,
                on_action=None if real_input else _print_action,
                on_countdown=lambda second: print(t("countdown_tick", second=second)),
            )
    except KeyboardInterrupt:
        print("\n" + t("stopped_play"))
        return 130
    if not finished:
        print(t("stopped_play"))
        return 130
    print(t("finished") if real_input else t("preview_done", count=len(result.actions)))
    return 0


def _print_action(action: KeyAction) -> None:
    # '뗌'은 화면에서 '누름'보다 좁아서 칸을 맞춘다.
    verb = t("key_down") if action.down else t("key_up")
    print(f"{action.time:8.3f}  {verb}  {action.key:<6}  {action.label}")


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
