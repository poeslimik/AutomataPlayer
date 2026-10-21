"""키 입력 백엔드.

실제 게임 연주는 포커스된 창에 키보드 입력만 보낸다.
프로세스에 붙거나 메모리를 읽지 않는다.
"""

from __future__ import annotations

import sys

from automata_player.i18n import t
from automata_player.model import BackendError


class InputBackend:
    def press(self, key: str) -> None:
        raise NotImplementedError

    def release(self, key: str) -> None:
        raise NotImplementedError

    def release_all(self) -> None:
        raise NotImplementedError

    def __enter__(self) -> InputBackend:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.release_all()
        return False


class DryRunBackend(InputBackend):
    """키를 누르지 않고 어떤 키가 나갈지만 기록한다."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []
        self.held: set[str] = set()

    def press(self, key: str) -> None:
        self.events.append(("down", key))
        self.held.add(key)

    def release(self, key: str) -> None:
        self.events.append(("up", key))
        self.held.discard(key)

    def release_all(self) -> None:
        for key in sorted(self.held):
            self.events.append(("up", key))
        self.held.clear()


def open_backend(name: str) -> InputBackend:
    key = name.casefold()
    if key in {"dry-run", "dryrun", "preview"}:
        return DryRunBackend()
    if key == "windows":
        from automata_player.playback.windows_input import WindowsBackend

        return WindowsBackend()
    if key == "pynput":
        from automata_player.playback.pynput_input import PynputBackend

        return PynputBackend()
    if key == "auto":
        if sys.platform == "win32":
            from automata_player.playback.windows_input import WindowsBackend

            return WindowsBackend()
        from automata_player.playback.pynput_input import PynputBackend

        return PynputBackend()
    raise BackendError(t("bad_backend"))


def windows_stop_key_down() -> bool:
    """게임 창이 앞에 있어도 F8이 눌렸는지 본다. Windows 전용."""
    if sys.platform != "win32":
        return False
    import ctypes

    return bool(ctypes.windll.user32.GetAsyncKeyState(0x77) & 0x8000)
