"""Conferencia das respostas do modelo, antes de usar.

- Estrategia: o campo "estrategia" e reinjetado todo dia, entao tem teto duro de
  caracteres. Acima dele a resposta e rejeitada e pedida de novo.
- Dia: "leitura_do_dia", "conhecimento" e "plano" precisam existir. O conteudo do
  plano nao e conferido aqui -- comando invalido e descartado pelo executor e
  volta como feedback amanha, sem pedir reenvio.
- Conhecimento: reescrito inteiro todo dia, com teto de linhas. O excesso e
  cortado (as ultimas) e o corte e avisado no feedback.
"""

from dataclasses import dataclass, field

from llm_agent import settings

STRATEGY_KEYS = ("analise", "regras_de_bolso", "estrategia")
DAY_KEYS = ("leitura_do_dia", "conhecimento", "plano")


def strategy_problem(parsed: dict) -> str | None:
    estrategia = parsed.get("estrategia")
    if not isinstance(estrategia, str) or not estrategia.strip():
        return "o campo \"estrategia\" veio vazio ou não é texto"
    tamanho = len(estrategia.strip())
    if tamanho > settings.STRATEGY_MAX_CHARS:
        return (f"o campo \"estrategia\" tem {tamanho} caracteres; o máximo é "
                f"{settings.STRATEGY_MAX_CHARS}. Reescreva mais curto")
    if not isinstance(parsed.get("regras_de_bolso"), list):
        return "o campo \"regras_de_bolso\" precisa ser uma lista"
    return None


def day_problem(parsed: dict) -> str | None:
    if not isinstance(parsed.get("plano"), list):
        return "o campo \"plano\" precisa ser uma lista de comandos"
    return None


@dataclass
class Knowledge:
    lines: list[str] = field(default_factory=list)
    cut: int = 0          # linhas acima do teto, descartadas
    ignored: int = 0      # entradas que nao eram texto

    def new_since(self, anterior: list[str]) -> int:
        return len(set(self.lines) - set(anterior))

    def removed_since(self, anterior: list[str]) -> int:
        return len(set(anterior) - set(self.lines))


def curate(value) -> Knowledge:
    """Normaliza o bloco de conhecimento e aplica o teto de linhas."""
    k = Knowledge()
    if isinstance(value, str):
        value = value.splitlines()
    if not isinstance(value, list):
        return k
    linhas = []
    for item in value:
        if not isinstance(item, str):
            k.ignored += 1
            continue
        texto = " ".join(item.split()).lstrip("-• ").strip()
        if texto and texto not in linhas:
            linhas.append(texto)
    k.lines = linhas[:settings.KNOWLEDGE_MAX_LINES]
    k.cut = max(0, len(linhas) - settings.KNOWLEDGE_MAX_LINES)
    return k
