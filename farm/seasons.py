"""Ciclo das estacoes do ano. Por enquanto so muda o visual do jogo.

A estacao sai do dia, sem estado guardado, do mesmo jeito que o estagio das
plantas sai da idade delas. Nos ultimos dias da estacao o fundo da proxima
aparece por cima, com opacidade crescente, dando a sensacao de virada.
"""

import logging
from dataclasses import dataclass

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


SEASONS: tuple[Season, ...] = (
    Season("primavera", "Primavera", "main-background.png", "icons/icon primavera.png"),
    Season("verao", "Verão", "main-background-summer.png", "icons/icon verao.png"),
    Season("outono", "Outono", "main-background-fall.png", "icons/icon outono.png"),
    Season("inverno", "Inverno", "main-background-winter.png", "icons/icon inverno.png"),
)


class Seasons:
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
    def _elapsed(day: int) -> int:
        return day - settings.FIRST_DAY

    def current(self, day: int) -> Season:
        return SEASONS[(self._elapsed(day) // settings.SEASON_DAYS) % len(SEASONS)]

    def upcoming(self, day: int) -> Season:
        indice = (self._elapsed(day) // settings.SEASON_DAYS) + 1
        return SEASONS[indice % len(SEASONS)]

    def days_to_next(self, day: int) -> int:
        """Dias ate a virada: SEASON_DAYS no primeiro dia da estacao e 1 no ultimo."""
        return settings.SEASON_DAYS - (self._elapsed(day) % settings.SEASON_DAYS)

    def blend(self, day: int) -> float:
        """Opacidade do fundo da proxima estacao, de 0 a 1."""
        return settings.SEASON_BLEND.get(self.days_to_next(day), 0.0)

    # ---------------------------------------------------------------- desenho

    def background(self, day: int) -> pygame.Surface:
        atual = self.current(day)
        opacidade = self.blend(day)
        if not opacidade:
            return self._backgrounds[atual.key]   # fora da transicao, sem copia

        chave = (atual.key, opacidade)
        if chave != self._composed_key:
            self._composed = self._compose(atual, self.upcoming(day), opacidade)
            self._composed_key = chave
        return self._composed

    def _compose(self, atual: Season, proxima: Season, opacidade: float) -> pygame.Surface:
        composto = self._backgrounds[atual.key].copy()
        entrando = self._backgrounds[proxima.key].copy()
        entrando.set_alpha(round(255 * opacidade))
        composto.blit(entrando, (0, 0))
        logger.debug("fundo de %s com %s a %.0f%%", atual.key, proxima.key, opacidade * 100)
        return composto
