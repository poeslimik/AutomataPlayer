"""창에서 부르는 연주 세션.

악보를 읽고 키 입력을 보내는 일은 창 스레드 밖에서 돈다.
창은 콜백으로 받은 문장만 표시하면 된다.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass

from automata_player.i18n import instrument_name, t, translate_warning
from automata_player.instruments import get_instrument
from automata_player.model import AutomataError
from automata_player.playability import assess
from automata_player.pitch import midi_name
from automata_player.playback import arrange, open_backend, play
from automata_player.playback.arrange import KeyAction
from automata_player.playback.backend import windows_stop_key_down
from automata_player.score import load_score

MessageCallback = Callable[[str], None]
FinishedCallback = Callable[[bool], None]


@dataclass(frozen=True)
class PlayRequest:
    path: str
    instrument_id: str
    backend: str
    speed: float = 1.0
    transpose: int = 0
    countdown: float = 3.0
    parts: tuple[str, ...] = ()
    immediate: bool = True


def live_backend_name() -> str:
    """배포용 창에서 '게임에 입력'이 고르는 백엔드."""
    return "windows" if sys.platform == "win32" else "auto"


class PlaySession:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def thread(self) -> threading.Thread | None:
        return self._thread

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()

    def start(
        self,
        request: PlayRequest,
        on_message: MessageCallback,
        on_finished: FinishedCallback,
    ) -> None:
        if self.running():
            raise AutomataError(t("already_playing"))
        self._stop = threading.Event()

        def worker() -> None:
            try:
                self._execute(request, on_message)
            except AutomataError as exc:
                on_message(t("error", message=exc))
            except Exception as exc:
                on_message(t("error", message=exc))
            finally:
                on_finished(self._stop.is_set())

        self._thread = threading.Thread(target=worker, name="automata-play", daemon=True)
        self._thread.start()

    def _execute(self, request: PlayRequest, on_message: MessageCallback) -> None:
        score = load_score(request.path).select_parts(list(request.parts))
        instrument = get_instrument(request.instrument_id)
        check = assess(score.notes, instrument, request.transpose)
        if not check.ok:
            raise AutomataError(check.notice)
        result = arrange(
            score,
            instrument,
            transpose=request.transpose,
            tap_ms=None,
        )
        if not result.actions:
            raise AutomataError(t("no_keys"))

        real_input = request.backend.casefold() not in {"dry-run", "dryrun", "preview"}
        on_message(t("log_title", title=score.title))
        on_message(t("log_instrument", name=instrument_name(instrument), id=instrument.id))
        if not instrument.verified:
            on_message(t("log_unverified"))
        on_message(t("log_stats", count=len(score.notes), seconds=score.duration_seconds, speed=request.speed))
        if request.transpose:
            on_message(t("log_transpose", semitones=request.transpose))
        if result.skipped:
            shown = ", ".join(midi_name(pitch) for pitch in result.skipped[:6])
            extra = "" if len(result.skipped) <= 6 else t("log_skipped_more", count=len(result.skipped) - 6)
            on_message(t("log_skipped", count=len(result.skipped), shown=shown, extra=extra))
        for warning in score.warnings:
            on_message(t("log_warning", warning=translate_warning(warning)))
        if real_input:
            on_message(t("log_focus"))
            on_message(t("log_stop_hint"))
        else:
            on_message(t("log_header"))

        def should_stop() -> bool:
            if self._stop.is_set():
                return True
            if request.immediate:
                return False
            return windows_stop_key_down()

        with open_backend(request.backend) as backend:
            finished = play(
                result.actions,
                backend,
                speed=request.speed,
                countdown=0.0 if request.immediate else request.countdown,
                immediate=request.immediate,
                should_stop=should_stop,
                on_action=None if real_input else lambda action: on_message(format_action(action)),
                on_countdown=lambda second: on_message(t("countdown_tick", second=second)),
            )
        if finished:
            if real_input:
                on_message(t("finished"))
            else:
                on_message(t("preview_done", count=len(result.actions)))
        else:
            on_message(t("stopped_play"))


def format_action(action: KeyAction) -> str:
    verb = t("key_down") if action.down else t("key_up")
    return f"{action.time:8.3f}  {verb}  {action.key:<6}  {action.label}"
