"""키 동작을 시간에 맞춰 입력 백엔드로 보낸다."""

from __future__ import annotations

import time
from collections.abc import Callable

from automata_player.i18n import t
from automata_player.model import AutomataError
from automata_player.playback.arrange import KeyAction
from automata_player.playback.backend import InputBackend


def play(
    actions: list[KeyAction] | tuple[KeyAction, ...],
    backend: InputBackend,
    *,
    speed: float = 1.0,
    countdown: float = 0.0,
    immediate: bool = False,
    should_stop: Callable[[], bool] | None = None,
    on_action: Callable[[KeyAction], None] | None = None,
    on_countdown: Callable[[int], None] | None = None,
    clock: Callable[[], float] = time.perf_counter,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """동작을 순서대로 보낸다. 끝까지 치면 True, 중지면 False.

    `immediate`면 대기 없이 기록만 한다. 실제 연주는 게임 창을 고른 뒤
    countdown 초를 세고, speed로 박자를 늘이거나 줄인다.
    """
    if speed <= 0:
        raise AutomataError(t("bad_speed"))
    stop = should_stop or (lambda: False)

    if not immediate and countdown > 0:
        if not _countdown(countdown, stop, on_countdown, clock, sleep):
            return False

    origin = clock()
    for action in actions:
        when = action.time / speed
        if not immediate and not _wait_until(origin + when, stop, clock, sleep):
            return False
        if stop():
            return False
        if on_action is not None:
            on_action(action)
        if action.down:
            backend.press(action.key)
        else:
            backend.release(action.key)
    return True


def _countdown(
    countdown: float,
    stop: Callable[[], bool],
    on_countdown: Callable[[int], None] | None,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> bool:
    deadline = clock() + countdown
    announced: int | None = None
    while True:
        if stop():
            return False
        remaining = deadline - clock()
        if remaining <= 0:
            return True
        second = int(remaining + 0.999)
        if second != announced and on_countdown is not None:
            on_countdown(second)
            announced = second
        sleep(remaining if remaining < 0.05 else 0.05)


def _wait_until(
    deadline: float,
    stop: Callable[[], bool],
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> bool:
    while True:
        if stop():
            return False
        remaining = deadline - clock()
        if remaining <= 0:
            return True
        sleep(remaining if remaining < 0.05 else 0.05)
