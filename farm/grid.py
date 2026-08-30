"""Grid logico do mundo.

E a base de coordenadas do jogo: plantio, colheita e colisao vao usar
cell_at_world()/cell_rect_world() em vez de pixels soltos.
"""

import pygame

from farm import settings
from farm.view import View


class Grid:
    def __init__(self, cols: int, rows: int, tile: int):
        self.cols = cols
        self.rows = rows
        self.tile = tile
        self.visible = True
        # Superficie com alpha reaproveitada entre frames (evita realocar por frame).
        self._overlay = pygame.Surface(settings.SCREEN_SIZE, pygame.SRCALPHA)

    # ------------------------------------------------------------------ estado

    def toggle(self) -> None:
        self.visible = not self.visible

    # ------------------------------------------------------------ coordenadas

    def contains(self, col: int, row: int) -> bool:
        return 0 <= col < self.cols and 0 <= row < self.rows

    def cell_at_world(self, world_pos: tuple[float, float]) -> tuple[int, int]:
        """Celula (col, row) que contem o ponto do mundo. Pode ficar fora do mapa."""
        return (int(world_pos[0] // self.tile), int(world_pos[1] // self.tile))

    def cell_rect_world(self, col: int, row: int) -> pygame.Rect:
        """Retangulo da celula em coordenadas de mundo."""
        return pygame.Rect(col * self.tile, row * self.tile, self.tile, self.tile)

    # ---------------------------------------------------------------- desenho

    def draw(self, surface: pygame.Surface, view: View,
             hover_cell: tuple[int, int] | None = None) -> None:
        if not self.visible:
            return

        self._overlay.fill((0, 0, 0, 0))
        view_w, view_h = surface.get_size()

        if hover_cell is not None and self.contains(*hover_cell):
            rect = view.apply(self.cell_rect_world(*hover_cell))
            self._overlay.fill(settings.GRID_HOVER_COLOR, rect)
            pygame.draw.rect(self._overlay, settings.GRID_HOVER_BORDER, rect, 2)

        for col in range(self.cols + 1):
            x = round(col * self.tile * view.scale)
            pygame.draw.line(self._overlay, self._line_color(col), (x, 0), (x, view_h))

        for row in range(self.rows + 1):
            y = round(row * self.tile * view.scale)
            pygame.draw.line(self._overlay, self._line_color(row), (0, y), (view_w, y))

        surface.blit(self._overlay, (0, 0))

    @staticmethod
    def _line_color(index: int) -> tuple[int, int, int, int]:
        if index % settings.GRID_MAJOR_EVERY == 0:
            return settings.GRID_MAJOR_COLOR
        return settings.GRID_LINE_COLOR
