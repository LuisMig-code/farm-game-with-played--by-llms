"""O que esta plantado em cada celula, e o desenho das plantas no mapa."""

import logging
from dataclasses import dataclass

import pygame

from farm import assets, settings
from farm.crops import CROPS
from farm.grid import Grid
from farm.view import View

logger = logging.getLogger(__name__)

Cell = tuple[int, int]


@dataclass
class Plot:
    crop: str
    planted_day: int
    fertilized: bool = False


class Field:
    """Plantacoes por celula.

    O estagio nao e guardado: ele sai da diferenca entre o dia atual e o dia do
    plantio, entao dormir um dia faz todas as plantas avancarem sozinhas.
    """

    def __init__(self, grid: Grid, view: View):
        self.plots: dict[Cell, Plot] = {}
        self._grid = grid
        self._sprites = {
            key: [view.scale_surface(assets.load_image(path)) for path in crop.stages]
            for key, crop in CROPS.items()
        }

    # --------------------------------------------------------------- consultas

    def at(self, cell: Cell) -> Plot | None:
        return self.plots.get(cell)

    def age(self, cell: Cell, day: int) -> int:
        plot = self.plots[cell]
        return day - plot.planted_day

    @staticmethod
    def timing(plot: Plot) -> tuple[int, int]:
        """Dias para crescer e de validade, ja com o efeito do fertilizante."""
        crop = CROPS[plot.crop]
        if not plot.fertilized:
            return crop.grow_days, crop.shelf_days
        return (max(0, crop.grow_days - crop.fert_grow_cut),
                crop.shelf_days + crop.fert_shelf_bonus)

    def stage_index(self, cell: Cell, day: int) -> int:
        """0 plantado, 1 germinando, 2 crescido, 3 estragado (imagens 1 a 4)."""
        plot = self.plots[cell]
        grow, shelf = self.timing(plot)
        age = day - plot.planted_day
        if age >= grow + shelf:
            return 3
        # `age >= grow` vem antes de `age <= 0` de proposito: fertilizar pode
        # zerar o prazo e a planta fica pronta no mesmo dia em que foi plantada.
        if age >= grow:
            return 2
        return 0 if age <= 0 else 1

    def is_grown(self, cell: Cell, day: int) -> bool:
        """Pronta para colher. Estragada nao conta: o estagio 3 fica de fora."""
        return cell in self.plots and self.stage_index(cell, day) == 2

    def is_spoiled(self, cell: Cell, day: int) -> bool:
        return cell in self.plots and self.stage_index(cell, day) == 3

    def is_fertilized(self, cell: Cell) -> bool:
        plot = self.plots.get(cell)
        return plot is not None and plot.fertilized

    def days_left(self, cell: Cell, day: int) -> int:
        """Dias que a planta crescida ainda aguenta antes de estragar."""
        return sum(self.timing(self.plots[cell])) - self.age(cell, day)

    def newly_spoiled(self, day: int) -> list[tuple[Cell, str]]:
        """Plantas que apodreceram exatamente hoje."""
        estragadas = []
        for cell, plot in self.plots.items():
            if self.age(cell, day) == sum(self.timing(plot)):
                estragadas.append((cell, plot.crop))
        return estragadas

    def progress(self, cell: Cell, day: int) -> float:
        """Quanto falta para colher, de 0 (recem plantado) a 1 (pronto)."""
        grow_days = self.timing(self.plots[cell])[0]
        if grow_days <= 0:
            return 1.0
        return min(1.0, max(0.0, self.age(cell, day) / grow_days))

    # ------------------------------------------------------------------ acoes

    def plant(self, cell: Cell, crop: str, day: int) -> None:
        self.plots[cell] = Plot(crop=crop, planted_day=day)
        logger.info("plantou %s em %s no dia %d", crop, cell, day)

    def fertilize(self, cell: Cell) -> None:
        plot = self.plots[cell]
        plot.fertilized = True
        grow, shelf = self.timing(plot)
        logger.info("fertilizou %s em %s: cresce em %d dia(s), dura %d",
                    plot.crop, cell, grow, shelf)

    def harvest(self, cell: Cell) -> str:
        """Tira a planta da celula e devolve a cultura colhida."""
        crop = self.plots.pop(cell).crop
        logger.info("colheu %s em %s", crop, cell)
        return crop

    def remove(self, cell: Cell) -> str:
        """Arranca a planta estragada. Nao rende nada, so libera a celula."""
        crop = self.plots.pop(cell).crop
        logger.info("removeu %s estragada em %s", crop, cell)
        return crop

    # ---------------------------------------------------------------- desenho

    def draw(self, surface: pygame.Surface, view: View, day: int) -> None:
        # De cima para baixo: uma planta alta na linha de baixo passa por cima
        # da que esta atras dela.
        for cell, plot in sorted(self.plots.items(), key=lambda item: item[0][1]):
            estagio = self.stage_index(cell, day)
            sprite = self._sprites[plot.crop][estagio]
            # Os sprites tem a largura de uma celula e crescem para cima:
            # ancorar pela base mantem a planta plantada no chao da celula.
            rect = view.apply(self._grid.cell_rect_world(*cell))
            sprite_rect = sprite.get_rect(midbottom=rect.midbottom)
            surface.blit(sprite, sprite_rect)

            if estagio == 3:
                continue    # planta podre nao mostra barra: o sprite ja diz tudo
            self._draw_growth_bar(surface, rect, self.progress(cell, day))
            if estagio == 2:
                self._draw_fresh_bar(surface, sprite_rect, self.days_left(cell, day),
                                     self.timing(plot)[1])

    @staticmethod
    def _draw_fresh_bar(surface: pygame.Surface, sprite_rect: pygame.Rect,
                        days_left: int, shelf_days: int) -> None:
        """Validade, acima da planta: esvazia conforme o dia de estragar chega."""
        width, height = settings.FRESH_BAR_SIZE
        bar = pygame.Rect(0, 0, width, height)
        bar.midbottom = (sprite_rect.centerx, sprite_rect.top - settings.FRESH_BAR_MARGIN)

        if days_left >= 3:
            color = settings.FRESH_BAR_GOOD
        elif days_left == 2:
            color = settings.FRESH_BAR_WARN
        else:
            color = settings.FRESH_BAR_URGENT

        pygame.draw.rect(surface, settings.GROWTH_BAR_BACK, bar)
        filled = round((width - 2) * max(0, days_left) / shelf_days)
        if filled:
            pygame.draw.rect(surface, color, (bar.x + 1, bar.y + 1, filled, height - 2))
        pygame.draw.rect(surface, settings.GROWTH_BAR_BORDER, bar, 1)

    @staticmethod
    def _draw_growth_bar(surface: pygame.Surface, cell_rect: pygame.Rect,
                         progress: float) -> None:
        """Barrinha no rodape da celula, dourada quando a planta esta pronta."""
        width, height = settings.GROWTH_BAR_SIZE
        bar = pygame.Rect(0, 0, width, height)
        bar.midbottom = (cell_rect.centerx, cell_rect.bottom - settings.GROWTH_BAR_MARGIN)

        pygame.draw.rect(surface, settings.GROWTH_BAR_BACK, bar)
        filled = round((width - 2) * progress)
        if filled:
            color = (settings.GROWTH_BAR_READY if progress >= 1
                     else settings.GROWTH_BAR_COLOR)
            pygame.draw.rect(surface, color, (bar.x + 1, bar.y + 1, filled, height - 2))
        pygame.draw.rect(surface, settings.GROWTH_BAR_BORDER, bar, 1)
