"""O caderno: a memoria que o proprio modelo escreve, reescrita por inteiro todo dia.

Uma linha so entra se tiver um prefixo valido e alguma coisa concreta -- um
numero, ou o nome de uma cultura, zona, item ou verbo do jogo. Linha rejeitada e
descartada em silencio para o jogo (nao gasta a correcao), mas contada: e a
metrica de quanto o modelo tende a platitude.
"""

import re
from dataclasses import dataclass, field

from llm_agent import settings
from llm_agent.grammar import BUY_ITEMS, CROP_IDS, VERBS, ZONE_CELLS

PREFIXES = ("[REGRA]", "[NUMERO]", "[CALENDARIO]", "[ERRO]")
_CONCRETO = re.compile(
    r"\d|\b(" + "|".join(map(re.escape, (*CROP_IDS, *ZONE_CELLS, *BUY_ITEMS,
                                         *(v.lower() for v in VERBS),
                                         "estamina", "caixa", "fertilizante",
                                         "semente", "inverno", "verao", "verão",
                                         "outono", "primavera"))) + r")\b",
    re.IGNORECASE)


@dataclass
class NotebookCheck:
    accepted: list[str] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)

    def churn(self, anterior: list[str]) -> int:
        """Linhas trocadas em relacao ao caderno anterior (entradas + saidas)."""
        return len(set(self.accepted) ^ set(anterior))


def check(lines) -> NotebookCheck:
    resultado = NotebookCheck()
    if not isinstance(lines, list):
        if lines not in (None, ""):
            resultado.rejected.append({"linha": str(lines)[:200],
                                       "motivo": "o caderno precisa ser uma lista de strings"})
        return resultado

    for linha in lines:
        if not isinstance(linha, str):
            resultado.rejected.append({"linha": str(linha)[:200], "motivo": "nao e texto"})
            continue
        texto = " ".join(linha.split())
        if not texto:
            continue
        if not texto.upper().startswith(PREFIXES):
            resultado.rejected.append({"linha": texto, "motivo": "sem prefixo valido"})
        elif not _CONCRETO.search(texto.split("]", 1)[1]):
            resultado.rejected.append({"linha": texto, "motivo": "sem numero ou referencia concreta"})
        elif len(resultado.accepted) >= settings.NOTEBOOK_MAX_LINES:
            resultado.rejected.append({"linha": texto,
                                       "motivo": f"passou de {settings.NOTEBOOK_MAX_LINES} linhas"})
        elif texto not in resultado.accepted:
            resultado.accepted.append(texto)
    return resultado
