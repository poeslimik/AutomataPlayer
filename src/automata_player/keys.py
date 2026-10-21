"""'a'나 'shift+a' 같은 키 표기를 토큰으로 나눈다."""

from __future__ import annotations

from automata_player.i18n import t

NAMED_KEYS = frozenset(
    {
        "shift",
        "ctrl",
        "alt",
        "space",
        "enter",
        "tab",
        "-",
        "=",
        "[",
        "]",
        "\\",
        ";",
        "'",
        ",",
        ".",
        "/",
        "`",
    }
)


def parse_key(spec: str) -> tuple[str, ...]:
    """'ctrl+shift+a'를 ('ctrl', 'shift', 'a')로 바꾼다.

    앞쪽 토큰은 수정자고 마지막 토큰이 본 키다. 악기 표에 적힌 문자열이
    나중에 입력 백엔드로 그대로 전달된다.
    """
    parts = [part.strip().lower() for part in spec.split("+")]
    if not parts or any(not part for part in parts):
        raise ValueError(t("empty_key", spec=repr(spec)))
    for part in parts:
        if part in NAMED_KEYS:
            continue
        if len(part) == 1 and part.isascii() and part.isalnum():
            continue
        raise ValueError(t("unknown_key", name=part))
    return tuple(parts)
