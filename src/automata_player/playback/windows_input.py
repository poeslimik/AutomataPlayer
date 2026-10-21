"""Windows SendInput으로 키를 보낸다.

이환은 언리얼 엔진의 Raw Input으로 키보드를 읽는다.
가상 키만 있으면 스캔코드가 0이라 게임이 무시하고, 스캔코드만 있으면
다른 창에는 글자가 들어가도 기타는 반응하지 않는다.
그래서 가상 키와 하드웨어 스캔코드를 함께 보낸다.
관리자 권한으로 실행 중인 게임에는 이 프로그램도 같은 권한이어야 입력이 닿는다.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from automata_player.i18n import t
from automata_player.keys import parse_key
from automata_player.model import BackendError
from automata_player.playback.backend import InputBackend

_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_SCANCODE = 0x0008
_MAPVK_VK_TO_VSC = 0

_POINTER = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

_VK = {
    "shift": 0x10,
    "ctrl": 0x11,
    "alt": 0x12,
    "space": 0x20,
    "enter": 0x0D,
    "tab": 0x09,
    "-": 0xBD,
    "=": 0xBB,
    "[": 0xDB,
    "]": 0xDD,
    "\\": 0xDC,
    ";": 0xBA,
    "'": 0xDE,
    ",": 0xBC,
    ".": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
}


class _KeybdInput(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _POINTER),
    )


class _MouseInput(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _POINTER),
    )


class _HardwareInput(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _InputUnion(ctypes.Union):
    _fields_ = (
        ("mi", _MouseInput),
        ("ki", _KeybdInput),
        ("hi", _HardwareInput),
    )


class INPUT(ctypes.Structure):
    _fields_ = (
        ("type", wintypes.DWORD),
        ("union", _InputUnion),
    )


def key_event_fields(vk: int, scan: int, *, down: bool) -> tuple[int, int, int]:
    """언리얼 Raw Input이 읽는 (가상 키, 스캔코드, 플래그).

    KEYEVENTF_SCANCODE를 켜면 가상 키가 무시되므로 켜지 않는다.
    """
    flags = 0 if down else _KEYEVENTF_KEYUP
    return vk, scan, flags


def virtual_key(name: str) -> int:
    if len(name) == 1 and name.isalpha():
        return ord(name.upper())
    if len(name) == 1 and name.isdigit():
        return ord(name)
    try:
        return _VK[name]
    except KeyError as exc:
        raise BackendError(t("bad_windows_key", name=name)) from exc


class WindowsBackend(InputBackend):
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise BackendError(t("windows_only"))
        self._held: dict[str, int] = {}
        self._user32 = ctypes.windll.user32
        self._user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        self._user32.SendInput.restype = wintypes.UINT
        self._user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
        self._user32.MapVirtualKeyW.restype = wintypes.UINT

    def press(self, key: str) -> None:
        for name in parse_key(key):
            self._change(name, down=True)

    def release(self, key: str) -> None:
        for name in reversed(parse_key(key)):
            self._change(name, down=False)

    def release_all(self) -> None:
        for name in list(self._held):
            self._send(name, down=False)
        self._held.clear()

    def _change(self, name: str, *, down: bool) -> None:
        count = self._held.get(name, 0)
        if down:
            self._held[name] = count + 1
            if count == 0:
                self._send(name, down=True)
            return
        if count > 1:
            self._held[name] = count - 1
            return
        if count == 1:
            self._send(name, down=False)
        self._held.pop(name, None)

    def _send(self, name: str, *, down: bool) -> None:
        vk = virtual_key(name)
        scan = int(self._user32.MapVirtualKeyW(vk, _MAPVK_VK_TO_VSC))
        vk_out, scan_out, flags = key_event_fields(vk, scan, down=down)
        event = INPUT(type=_INPUT_KEYBOARD)
        event.union.ki = _KeybdInput(vk_out, scan_out, flags, 0, 0)
        sent = self._user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
        if sent != 1:
            raise BackendError(t("send_failed"))
