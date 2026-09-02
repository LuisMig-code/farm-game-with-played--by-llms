"""Ciclo das estacoes do ano: o visual e as regras de cada uma.

A estacao sai do dia, sem estado guardado, do mesmo jeito que o estagio das
plantas sai da idade delas. Nos ultimos dias da estacao o fundo da proxima
aparece por cima, com opacidade crescente, dando a sensacao de virada.

As regras vivem na propria `Season`, como uma tabela que se le de cima a baixo.
`season_at` e funcao de modulo de proposito: `Field` e `Market` precisam da
estacao sem ter a instancia de `Seasons`, que e dona das superficies e so existe
dentro do `Game`.
"""

import logging
from dataclasses import dataclass, field

import pygame

from farm import assets, settings
from farm.view import View

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Season:
    key: str
    label: str
    background: str
    icon: str
    effect: str = ""                      # frase curta mostrada no indicador

    grow_delta: int = 0                   # dias a mais para crescer
    shelf_days: dict[str, int] = field(default_factory=dict)   # sobrepoe o padrao
    can_plant: bool = True
    fertilizer_works: bool = True
    sell_multiplier: dict[str, float] = field(default_factory=dict)
    daily_budget: int | None = None            # None = usa o do settings
    promo_item_chances: tuple | None = None    # None = usa a tabela do settings
    promo_discounts: tuple | None = None


SEASONS: tuple[Season, ...] = (
    Season(
        "primavera", "Primavera", "main-background.png", "icons/icon primavera.png",
        effect="ritmo padrão o mês inteiro",
    ),
    Season(
        "verao", "Verão", "main-background-summer.png", "icons/icon verao.png",
        effect="a colheita estraga rápido",
        shelf_days={"cenoura": 1, "batata": 1, "beterraba": 2, "trigo": 2, "melancia": 2},
    ),
    Season(
        "outono", "Outono", "main-background-fall.png", "icons/icon outono.png",
        effect="crescimento +1 dia",
        grow_delta=1,
    ),
    Season(
        "inverno", "Inverno", "main-background-winter.png", "icons/icon inverno.png",
        effect="sem plantio, venda vale mais",
        can_plant=False,
        fertilizer_works=False,
        sell_multiplier={"cenoura": 2, "batata": 2, "beterraba": 2,
                         "trigo": 2.5, "melancia": 3},
        daily_budget=300,
        promo_item_chances=((1, 0.50), (2, 0.30), (3, 0.20)),
        promo_discounts=((1, 0.30), (2, 0.35), (3, 0.25), (5, 0.10)),
    ),
)


def _elapsed(day: int) -> int:
    return day - settings.FIRST_DAY


def season_at(day: int) -> Season:
    return SEASONS[(_elapsed(day) // settings.SEASON_DAYS) % len(SEASONS)]


def season_after(day: int) -> Season:
    indice = (_elapsed(day) // settings.SEASON_DAYS) + 1
    return SEASONS[indice % len(SEASONS)]


def days_to_next(day: int) -> int:
    """Dias ate a virada: SEASON_DAYS no primeiro dia da estacao e 1 no ultimo."""
    return settings.SEASON_DAYS - (_elapsed(day) % settings.SEASON_DAYS)


def daily_budget(day: int) -> int:
    """Caixa que a loja tem naquele dia para pagar por colheita."""
    return season_at(day).daily_budget or settings.MARKET_DAILY_BUDGET


def promo_item_chances(day: int) -> tuple:
    return season_at(day).promo_item_chances or settings.PROMO_ITEM_CHANCES


def promo_discounts(day: int) -> tuple:
    return season_at(day).promo_discounts or settings.PROMO_DISCOUNTS


class Seasons:
    """Os fundos e a transicao. As regras estao nas funcoes de modulo acima."""

    def __init__(self, view: View):
        self._backgrounds = {
            season.key: view.scale_surface(assets.load_image(season.background, alpha=False))
            for season in SEASONS
        }
        # Cache de uma entrada so: a composicao muda no maximo uma vez por dia,
        # e misturar 2 milhoes de pixels a cada frame comeria o orcamento todo.
        self._composed: pygame.Surface | None = None
        self._composed_key: tuple[str, float] | None = None

        logger.info("estacoes: %d dias cada, na ordem %s", settings.SEASON_DAYS,
                    " -> ".join(s.label for s in SEASONS))

    # --------------------------------------------------------------- consultas

    @staticmethod
    def current(day: int) -> Season:
        return season_at(day)

    @staticmethod
    def upcoming(day: int) -> Season:
        return season_after(day)

    @staticmethod
    def days_to_next(day: int) -> int:
        return days_to_next(day)

    def blend(self, day: int) -> float:
        """Opacidade do fundo da proxima estacao, de 0 a 1."""
        return settings.SEASON_BLEND.get(days_to_next(day), 0.0)

    # ---------------------------------------------------------------- desenho

    def background(self, day: int) -> pygame.Surface:
        atual = season_at(day)
        opacidade = self.blend(day)
        if not opacidade:
            return self._backgrounds[atual.key]   # fora da transicao, sem copia

        chave = (atual.key, opacidade)
        if chave != self._composed_key:
            self._composed = self._compose(atual, season_after(day), opacidade)
            self._composed_key = chave
        return self._composed

    def _compose(self, atual: Season, proxima: Season, opacidade: float) -> pygame.Surface:
        composto = self._backgrounds[atual.key].copy()
        entrando = self._backgrounds[proxima.key].copy()
        entrando.set_alpha(round(255 * opacidade))
        composto.blit(entrando, (0, 0))
        logger.debug("fundo de %s com %s a %.0f%%", atual.key, proxima.key, opacidade * 100)
        return composto
