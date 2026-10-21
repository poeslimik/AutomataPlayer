"""더블클릭으로 켜는 창 진입점.

PyInstaller로 만든 exe는 관리자 권한을 요청한 뒤 이 창을 연다.
"""

from automata_player.playback import windows_input as _windows_input
from automata_player.ui.app import run_gui

del _windows_input


if __name__ == "__main__":
    raise SystemExit(run_gui())
