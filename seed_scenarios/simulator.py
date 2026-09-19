"""O cenario de uma semente: o que a loja tem em cada dia, sem abrir o jogo.

Estoque e promocao sao funcao de (semente, dia) -- ver docs/SEMENTE.md. Por isso
a simulacao usa o proprio `Market` do jogo, com as mesmas chamadas que o `Game`
faz: `Market(seed)` na largada e `new_day(dia)` a cada noite. Nenhuma regra e
reescrita aqui, entao uma mudanca na loja chega sozinha ao simulador.

Saturacao e caixa gasto dependem do que o jogador vende e compra, e ficam de
fora: o cenario e a loja do comeco de cada dia, antes de qualquer compra.
"""

import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import farm
from farm import settings as game_settings
from farm.crops import BUY_PRICES
from farm.market import Market
from farm.seasons import SEASONS, season_at

# Os arquivos que decidem o sorteio da loja: os numeros e o codigo que os usa.
RULE_FILES = tuple(Path(farm.__file__).parent / nome
                   for nome in ("market.py", "rng.py", "crops.py", "seasons.py", "settings.py"))

ITEMS = tuple(BUY_PRICES)                                      # na ordem da loja
COLUMN = {item: item.replace(" ", "_") for item in ITEMS}      # como no precos.csv das runs

DAY_HEADER = ("semente", "dia", "estacao", "promocoes", "itens_em_promocao", "desconto_total",
              *(f"estoque_{COLUMN[item]}" for item in ITEMS),
              *(f"desconto_{COLUMN[item]}" for item in ITEMS),
              *(f"compra_{COLUMN[item]}" for item in ITEMS))

METRICS_HEADER = ("promocoes", "dias_com_promocao", "media_promocoes_dia", "max_promocoes_dia",
                  "desconto_total",
                  *(f"promocoes_{estacao.key}" for estacao in SEASONS),
                  *(f"promocoes_{COLUMN[item]}" for item in ITEMS),
                  *(f"estoque_medio_{COLUMN[item]}" for item in ITEMS),
                  *(f"dias_sem_estoque_{COLUMN[item]}" for item in ITEMS))


@dataclass(frozen=True)
class Day:
    """A loja no comeco de um dia."""

    day: int
    season: str
    stock: dict[str, int]      # item -> estoque
    promos: dict[str, int]     # item -> desconto, so os itens em promocao, na ordem da loja
    prices: dict[str, int]     # item -> preco de compra do dia, ja com o desconto

    def row(self, seed: int) -> list:
        """A linha do CSV da semente, na ordem de DAY_HEADER."""
        return [seed, self.day, self.season, len(self.promos),
                "; ".join(f"{item} -{desconto}" for item, desconto in self.promos.items()),
                sum(self.promos.values()),
                *(self.stock[item] for item in ITEMS),
                *(self.promos.get(item, 0) for item in ITEMS),
                *(self.prices[item] for item in ITEMS)]


def simulated_days(days: int) -> range:
    """Os dias simulados: do primeiro dia do jogo em diante, como numa run."""
    return range(game_settings.FIRST_DAY, game_settings.FIRST_DAY + days)


def simulate(seed: int, days: int) -> list[Day]:
    """A loja de cada dia da semente, do primeiro dia ate `days`."""
    if days < 1:
        raise ValueError(f"days precisa ser pelo menos 1 (recebeu {days})")
    loja = Market(seed)                     # ja sorteou o primeiro dia, como no Game._reset
    cenario = []
    for dia in simulated_days(days):
        if dia != game_settings.FIRST_DAY:
            loja.new_day(dia)               # a virada do Game._sleep
        cenario.append(Day(
            day=dia,
            season=season_at(dia).key,
            stock={item: loja.stock_left(item) for item in ITEMS},
            promos={item: loja.promos[item] for item in ITEMS if loja.is_promo(item)},
            prices={item: loja.buy_price(item) for item in ITEMS},
        ))
    return cenario


def summarize(cenario: list[Day]) -> dict:
    """As metricas da semente, com as chaves de METRICS_HEADER."""
    total = sum(len(dia.promos) for dia in cenario)
    por_estacao = Counter()
    por_item = Counter()
    for dia in cenario:
        por_estacao[dia.season] += len(dia.promos)
        por_item.update(dia.promos.keys())

    metricas = {
        "promocoes": total,
        "dias_com_promocao": sum(1 for dia in cenario if dia.promos),
        "media_promocoes_dia": round(total / len(cenario), 3),
        "max_promocoes_dia": max(len(dia.promos) for dia in cenario),
        "desconto_total": sum(sum(dia.promos.values()) for dia in cenario),
    }
    for estacao in SEASONS:
        metricas[f"promocoes_{estacao.key}"] = por_estacao[estacao.key]
    for item in ITEMS:
        metricas[f"promocoes_{COLUMN[item]}"] = por_item[item]
    for item in ITEMS:
        estoques = [dia.stock[item] for dia in cenario]
        metricas[f"estoque_medio_{COLUMN[item]}"] = round(sum(estoques) / len(estoques), 2)
    for item in ITEMS:
        metricas[f"dias_sem_estoque_{COLUMN[item]}"] = sum(1 for dia in cenario if not dia.stock[item])
    return metricas


def rules_fingerprint(files=RULE_FILES) -> str:
    """Impressao digital das regras do sorteio: 12 caracteres do sha256 dos arquivos.

    Qualquer mudanca nos numeros ou no codigo da loja muda o valor, e um cenario
    simulado antes deixa de valer. As quebras de linha sao normalizadas: o mesmo
    arquivo com CRLF (Windows) ou LF da o mesmo valor.
    """
    impressao = hashlib.sha256()
    for caminho in files:
        caminho = Path(caminho)
        impressao.update(caminho.name.encode() + b"\0")
        impressao.update(caminho.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return impressao.hexdigest()[:12]
