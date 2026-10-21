from automata_player.playback import KeyAction, play
from automata_player.playback.backend import DryRunBackend


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def _actions() -> list[KeyAction]:
    return [
        KeyAction(1.0, "a", True, 60, 60, "Piano", "C4"),
        KeyAction(1.5, "a", False, 60, 60, "Piano", "C4"),
    ]


def test_playback_scales_time_and_presses_in_order():
    clock = Clock()
    backend = DryRunBackend()
    finished = play(
        _actions(),
        backend,
        speed=2,
        clock=clock,
        sleep=clock.sleep,
    )
    assert finished is True
    assert clock.value == 0.75
    assert backend.events == [("down", "a"), ("up", "a")]
    assert backend.held == set()


def test_immediate_playback_does_not_sleep():
    clock = Clock()
    backend = DryRunBackend()
    play(_actions(), backend, immediate=True, clock=clock, sleep=clock.sleep)
    assert clock.value == 0
    assert [event[0] for event in backend.events] == ["down", "up"]


def test_stop_prevents_the_first_key():
    backend = DryRunBackend()
    finished = play(
        _actions(),
        backend,
        should_stop=lambda: True,
        clock=lambda: 0.0,
        sleep=lambda _seconds: None,
    )
    assert finished is False
    assert backend.events == []


def test_dry_run_context_releases_a_stuck_key():
    backend = DryRunBackend()
    with backend:
        backend.press("a")
    assert backend.events[-1] == ("up", "a")
    assert backend.held == set()
