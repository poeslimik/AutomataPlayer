"""pynput으로 키를 보낸다. Windows가 아닌 곳의 기본 입력 경로다."""

from __future__ import annotations

from automata_player.i18n import t
from automata_player.keys import parse_key
from automata_player.model import BackendError
from automata_player.playback.backend import InputBackend


class PynputBackend(InputBackend):
    def __init__(self) -> None:
        try:
            from pynput.keyboard import Controller
            from pynput.keyboard import Key
            from pynput.keyboard import KeyCode
        except ImportError as exc:
            raise BackendError(t("pynput_missing")) from exc
        self._controller = Controller()
        self._key = Key
        self._key_code = KeyCode
        self._held: dict[str, int] = {}

    def press(self, key: str) -> None:
        for name in parse_key(key):
            self._change(name, down=True)

    def release(self, key: str) -> None:
        for name in reversed(parse_key(key)):
            self._change(name, down=False)

    def release_all(self) -> None:
        for name in list(self._held):
            self._controller.release(self._convert(name))
        self._held.clear()

    def _change(self, name: str, *, down: bool) -> None:
        count = self._held.get(name, 0)
        converted = self._convert(name)
        if down:
            self._held[name] = count + 1
            if count == 0:
                self._controller.press(converted)
            return
        if count > 1:
            self._held[name] = count - 1
            return
        if count == 1:
            self._controller.release(converted)
        self._held.pop(name, None)

    def _convert(self, name: str):
        special = {
            "shift": self._key.shift,
            "ctrl": self._key.ctrl,
            "alt": self._key.alt,
            "space": self._key.space,
            "enter": self._key.enter,
            "tab": self._key.tab,
        }
        if name in special:
            return special[name]
        if len(name) != 1:
            raise BackendError(t("bad_pynput_key", name=name))
        return self._key_code.from_char(name)
