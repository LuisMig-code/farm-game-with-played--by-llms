"""Camada para jogar o farm game por codigo, pensada para agentes de IA.

    from scripting import Session

    with Session(seed=42, record="logs/partida.mp4") as s:
        s.walk_to((6, 8))
        s.plant("batata")
        print(s.observe().as_text())

Nada aqui modifica o jogo: `farm/` continua exatamente como esta, e a sessao
joga pelos mesmos menus e regras que um humano no teclado.
"""

from scripting.errors import (Aborted, Blocked, GameOver, NoRoute,
                              RecorderUnavailable, ScriptingError)
from scripting.observation import Observation
from scripting.recorder import Recorder
from scripting.route import shortest_path
from scripting.session import HOUSE, SHOP, Session

__all__ = [
    "Session", "Observation", "Recorder", "shortest_path", "HOUSE", "SHOP",
    "ScriptingError", "Blocked", "NoRoute", "GameOver", "Aborted",
    "RecorderUnavailable",
]
