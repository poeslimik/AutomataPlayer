import ctypes
import sys

import pytest

from automata_player.playback.windows_input import INPUT, _KEYEVENTF_SCANCODE, _KeybdInput, key_event_fields, virtual_key


def test_letter_and_symbol_virtual_keys():
    assert virtual_key("a") == 0x41
    assert virtual_key("1") == 0x31
    assert virtual_key("-") == 0xBD
    assert virtual_key("[") == 0xDB


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_sendinput_struct_has_the_win32_size():
    expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    assert ctypes.sizeof(INPUT) == expected


def test_unreal_key_event_keeps_virtual_key_and_scan_code():
    vk, scan, flags = key_event_fields(0x41, 0x1E, down=True)
    assert vk == 0x41
    assert scan == 0x1E
    assert flags & _KEYEVENTF_SCANCODE == 0
    _vk, _scan, up_flags = key_event_fields(0x41, 0x1E, down=False)
    assert up_flags & _KEYEVENTF_SCANCODE == 0
    assert up_flags != flags


def test_keyboard_event_stores_the_scan_code_without_sending():
    event = INPUT(type=1)
    event.union.ki = _KeybdInput(0, 0x1E, 0x0008, 0, 0)
    assert event.type == 1
    assert event.union.ki.wScan == 0x1E
    assert event.union.ki.wVk == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_scan_code_for_the_a_key_exists_without_sending():
    scan = ctypes.windll.user32.MapVirtualKeyW(0x41, 0)
    assert scan != 0
