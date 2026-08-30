"""Zonas do mapa: onde o jogador pode pisar e onde pode plantar.

O jogador so anda pelas celulas listadas em settings; todo o resto e bloqueado.
O colorido das zonas e desenhado uma unica vez numa superficie e so reaproveitado,
porque as areas nao mudam durante o jogo.
"""

import logging

import pygame

from farm import settings
from farm.grid import Grid
from farm.view import View

logger = logging.getLogger(__name__)

PLANTABLE = "plantio"

Area = tuple[tuple[int, int], tuple[int, int]]


def cells_in(areas: tuple[Area, ...]) -> frozenset[tuple[int, int]]:
    """Expande pares de cantos (inclusivos, em qualquer ordem) em celulas."""
    cells = set()
    for (col_a, row_a), (col_b, row_b) in areas:
        for col in range(min(col_a, col_b), max(col_a, col_b) + 1):
            for row in range(min(row_a, row_b), max(row_a, row_b) + 1):
                cells.add((col, row))
    return frozenset(cells)


class Zones:
    def __init__(self, grid: Grid, view: View):
        self.plantable = cells_in(settings.PLANTABLE_AREAS)
        self.areas: dict[str, frozenset[tuple[int, int]]] = {
            name: cells_in(areas) for name, areas in settings.WALKABLE_AREAS.items()
        }
        self.areas[PLANTABLE] = self.plantable
        self.walkable = frozenset().union(*self.areas.values())

        self.visible = True
        self._overlay = self._build_overlay(grid, view)
        logger.info(
            "zonas: %d celulas andaveis (%d de plantio) de %d no mapa",
            len(self.walkable), len(self.plantable), grid.cols * grid.rows,
        )

    # --------------------------------------------------------------- consultas

    def is_walkable(self, cell: tuple[int, int]) -> bool:
        return cell in self.walkable

    def is_plantable(self, cell: tuple[int, int]) -> bool:
        return cell in self.plantable

    def zone_of(self, cell: tuple[int, int]) -> str:
        """Nome da zona da celula, ou 'bloqueado' se o jogador nao pode entrar."""
        for name, cells in self.areas.items():
            if cell in cells:
                return name
        return "bloqueado"

    # ---------------------------------------------------------------- desenho

    def _build_overlay(self, grid: Grid, view: View) -> pygame.Surface:
        overlay = pygame.Surface(settings.SCREEN_SIZE, pygame.SRCALPHA)
        for cell in self.walkable:
            color = (settings.ZONE_PLANTABLE_COLOR if cell in self.plantable
                     else settings.ZONE_WALKABLE_COLOR)
            overlay.fill(color, view.apply(grid.cell_rect_world(*cell)))
        return overlay

    def draw(self, surface: pygame.Surface) -> None:
        if self.visible:
            surface.blit(self._overlay, (0, 0))
