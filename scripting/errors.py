"""Erros da camada de scripting.

Todos herdam de `ScriptingError`, entao um agente pode capturar so a base e
tratar qualquer recusa do jogo de uma vez.
"""


class ScriptingError(Exception):
    """Base de tudo que esta camada levanta."""


class Blocked(ScriptingError):
    """A acao existe, mas o jogo a recusou agora.

    A mensagem carrega o motivo escrito pelo proprio jogo no rotulo da opcao
    ("(sem saldo)", "esgotado hoje", "Nada cresce no inverno"...), porque e ele
    que sabe por que a regra barrou.
    """


class NoRoute(ScriptingError):
    """Nao existe caminho andavel ate a celula pedida."""


class GameOver(ScriptingError):
    """A partida acabou: a estamina chegou a zero."""


class Aborted(ScriptingError):
    """O laco parou por fora: janela fechada ou estado que nao avanca."""


class RecorderUnavailable(ScriptingError):
    """Faltou a dependencia de video."""
