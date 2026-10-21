"""MuseScore 악보를 게임 악기 키 입력으로 연주하는 틀."""

from automata_player.instruments import get_instrument, list_instruments
from automata_player.model import Score
from automata_player.playback import arrange, play
from automata_player.score import load_score

__all__ = [
    "Score",
    "arrange",
    "get_instrument",
    "list_instruments",
    "load_score",
    "play",
]
__version__ = "0.1.0"
