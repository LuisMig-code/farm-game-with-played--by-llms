"""Transformacao mundo -> tela.

O mapa inteiro esta sempre visivel, entao a view nao se move: ela apenas
reduz as coordenadas de mundo (2000x1000) para a janela (1000x500).
"""

import pygame


class View:
    def __init__(self, world_size: tuple[int, int], view_size: tuple[int, int]):
        self.world_size = world_size
        self.view_size = view_size
        self.scale = view_size[0] / world_size[0]

    def world_to_screen(self, world_pos: tuple[float, float]) -> tuple[float, float]:
        return (world_pos[0] * self.scale, world_pos[1] * self.scale)

    def screen_to_world(self, screen_pos: tuple[float, float]) -> tuple[float, float]:
        return (screen_pos[0] / self.scale, screen_pos[1] / self.scale)

    def apply(self, rect: pygame.Rect) -> pygame.Rect:
        """Converte um rect de mundo para coordenadas de tela."""
        return pygame.Rect(
            round(rect.x * self.scale), round(rect.y * self.scale),
            round(rect.w * self.scale), round(rect.h * self.scale),
        )

    def scale_surface(self, surface: pygame.Surface, factor: float = 1.0) -> pygame.Surface:
        """Reduz uma superficie de mundo para o tamanho com que sera desenhada."""
        s = self.scale * factor
        size = (max(1, round(surface.get_width() * s)), max(1, round(surface.get_height() * s)))
        return pygame.transform.smoothscale(surface, size)
