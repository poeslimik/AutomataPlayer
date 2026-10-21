import time
import tkinter as tk
from pathlib import Path

import pytest

from automata_player.i18n import set_language
from automata_player.ui.app import App
from automata_player.ui.session import PlayRequest, PlaySession, live_backend_name

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "c_major_scale.mscx"


def test_preview_session_logs_harp_keys():
    messages: list[str] = []
    finished = []
    session = PlaySession()
    session.start(
        PlayRequest(str(EXAMPLE), "lyre", "dry-run", immediate=True),
        messages.append,
        finished.append,
    )
    assert session.thread is not None
    session.thread.join(timeout=5)
    assert finished == [False]
    text = "\n".join(messages)
    assert "C4" in text
    assert "누름" in text
    assert "미리보기 끝" in text


def test_stop_interrupts_realtime_preview():
    finished: list[bool] = []
    session = PlaySession()
    session.start(
        PlayRequest(
            str(EXAMPLE),
            "nte-piano",
            "dry-run",
            immediate=False,
            countdown=0,
        ),
        lambda _message: None,
        finished.append,
    )
    time.sleep(0.05)
    session.stop()
    assert session.thread is not None
    session.thread.join(timeout=2)
    assert finished == [True]


def test_window_loads_score_and_previews():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("화면 없음")
    root.withdraw()
    try:
        app = App(root)
        app.load_path(str(EXAMPLE))
        root.update()
        assert "C major scale" in app.summary_var.get()
        assert "8개" in app.summary_var.get()
        assert app.part_combo["values"] == ("전체", "1. Piano")

        app.instrument_combo.current(0)
        app._on_instrument()
        app.mode_var.set("preview")
        app.realtime_var.set(False)
        app.start_play()
        deadline = time.time() + 5
        while time.time() < deadline:
            app.drain()
            root.update()
            if not app.session.running() and "미리보기 끝" in app.log_text.get("1.0", "end"):
                break
            time.sleep(0.02)
        log = app.log_text.get("1.0", "end")
        assert "하프" in log
        assert "C4" in log
        assert "미리보기 끝" in log
        assert str(app.play_button.cget("state")) != "disabled"
    finally:
        root.destroy()


def test_language_switch_updates_labels():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("화면 없음")
    root.withdraw()
    try:
        app = App(root)
        set_language("en")
        app._apply_language()
        assert app.play_button.cget("text") == "Play"
        assert app.browse_button.cget("text") == "Browse"
        assert app.summary_var.get() == "Choose a score file."
        set_language("ja")
        app._apply_language()
        assert app.browse_button.cget("text") == "参照"
        assert app.part_var.get() == "すべて"
        assert "ライアー" in app.instrument_var.get()
        set_language("zh")
        app._apply_language()
        assert app.score_caption.cget("text") == "乐谱"
        set_language("ko")
        app._apply_language()
        assert app.play_button.cget("text") == "연주"
        assert app.part_var.get() == "전체"
    finally:
        set_language("ko")
        root.destroy()


def test_live_backend_follows_the_os():
    if __import__("sys").platform == "win32":
        assert live_backend_name() == "windows"
    else:
        assert live_backend_name() == "auto"
