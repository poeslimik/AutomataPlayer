# -*- mode: python ; coding: utf-8 -*-
"""더블클릭용 exe. 실행하면 사용자 계정 컨트롤로 관리자 권한을 요청한다."""

from pathlib import Path

root = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(root / "src" / "automata_player" / "exe_entry.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[],
    hiddenimports=[
        "automata_player.ui.app",
        "automata_player.ui.session",
        "automata_player.playback.windows_input",
        "automata_player.score.mscz",
        "automata_player.instruments.builtin",
        "automata_player.i18n",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pynput"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AutomataPlayer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
)
