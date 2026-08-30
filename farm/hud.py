"""Painel inferior, transicao entre dias e tela de derrota."""

import pygame

from farm import assets, settings
from farm.crops import BUY_PRICES, COIN, CROPS, ITEM_ICONS, ITEM_LABELS
from farm.inventory import Inventory, RunStats
from farm.market import Market
from farm.view import View

FONT_NAME = "consolas,couriernew,monospace"


class Fonts:
    def __init__(self) -> None:
        self.small = pygame.font.SysFont(FONT_NAME, 20)
        self.normal = pygame.font.SysFont(FONT_NAME, 26)
        self.big = pygame.font.SysFont(FONT_NAME, 40, bold=True)
        self.huge = pygame.font.SysFont(FONT_NAME, 60, bold=True)


class IconSet:
    """Icones de item redimensionados sob demanda, com cache por altura."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int], pygame.Surface] = {}

    def get(self, item: str, height: int) -> pygame.Surface:
        key = (item, height)
        cached = self._cache.get(key)
        if cached is None:
            source = assets.load_image(ITEM_ICONS[item])
            width = round(source.get_width() * height / source.get_height())
            cached = pygame.transform.smoothscale(source, (width, height))
            self._cache[key] = cached
        return cached


def _shadowed(surface: pygame.Surface, font: pygame.font.Font, text: str,
              pos: tuple[int, int], color=settings.HUD_COLOR) -> None:
    surface.blit(font.render(text, True, settings.HUD_SHADOW), (pos[0] + 1, pos[1] + 1))
    surface.blit(font.render(text, True, color), pos)


class Hud:
    def __init__(self, view: View) -> None:
        self.view = view
        self.fonts = Fonts()
        self.icons = IconSet()
        self._panel = pygame.Surface((settings.SCREEN_SIZE[0], settings.PANEL_HEIGHT),
                                     pygame.SRCALPHA)

    # ------------------------------------------------------------ painel base

    def draw_panel(self, surface: pygame.Surface, *, day: int, stamina: int,
                   max_stamina: int, inventory: Inventory, info: list[str]) -> None:
        self._panel.fill(settings.PANEL_COLOR)
        pygame.draw.line(self._panel, settings.PANEL_BORDER, (0, 0),
                         (self._panel.get_width(), 0), 2)
        surface.blit(self._panel, (0, settings.PANEL_TOP))

        _shadowed(surface, self.fonts.big, f"Dia {day}", (24, settings.PANEL_TOP + 18))
        self._draw_stamina(surface, stamina, max_stamina)
        self._draw_slots(surface, inventory)

        for i, line in enumerate(info):
            _shadowed(surface, self.fonts.small, line,
                      (24, settings.PANEL_TOP + 116 + i * 24))

    def _draw_stamina(self, surface: pygame.Surface, stamina: int, max_stamina: int) -> None:
        x, y, width, height = settings.STAMINA_BAR
        _shadowed(surface, self.fonts.small, f"Estamina {stamina}/{max_stamina}", (x, y - 24))

        ratio = stamina / max_stamina if max_stamina else 0
        color = (settings.STAMINA_LOW_COLOR if ratio <= settings.STAMINA_LOW_RATIO
                 else settings.STAMINA_FULL_COLOR)
        pygame.draw.rect(surface, settings.STAMINA_BACK_COLOR, (x, y, width, height))
        if ratio > 0:
            pygame.draw.rect(surface, color, (x, y, round(width * ratio), height))
        pygame.draw.rect(surface, settings.HUD_COLOR, (x, y, width, height), 2)

    def _draw_slots(self, surface: pygame.Surface, inventory: Inventory) -> None:
        for i, (item, count) in enumerate(inventory.slots()):
            x = settings.SLOTS_LEFT + i * settings.SLOT_WIDTH
            icon = self.icons.get(item, settings.SLOT_ICON_HEIGHT)
            if count == 0:                      # itens zerados ficam esmaecidos
                icon = icon.copy()
                icon.set_alpha(90)
            surface.blit(icon, (x, settings.SLOTS_TOP))

            color = settings.HUD_COLOR if count else settings.HUD_DIM_COLOR
            _shadowed(surface, self.fonts.normal, f"x{count}",
                      (x + icon.get_width() + 6,
                       settings.SLOTS_TOP + settings.SLOT_ICON_HEIGHT // 2 - 16), color)

    # ------------------------------------------------------- quadro de precos

    def draw_price_board(self, surface: pygame.Surface, market: Market, day: int) -> None:
        """Placa da loja, alinhada ao grid nas linhas livres acima do comercio."""
        tile = round(settings.TILE * self.view.scale)
        col0, col1 = settings.BOARD_COLS
        row0, row1 = settings.BOARD_ROWS
        rect = pygame.Rect(col0 * tile, row0 * tile,
                           (col1 - col0 + 1) * tile, (row1 - row0 + 1) * tile)

        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill(settings.BOARD_BG_COLOR)
        pygame.draw.rect(panel, settings.BOARD_BORDER_COLOR, panel.get_rect(), 2)

        def cell(col: int, row: int) -> pygame.Rect:
            return pygame.Rect((col - col0) * tile, (row - row0) * tile, tile, tile)

        meio = panel.get_width() // 2
        titulo = self.fonts.normal.render("COMÉRCIO", True, settings.BOARD_TITLE_COLOR)
        panel.blit(titulo, titulo.get_rect(center=(meio, 16)))
        self._draw_budget(panel, market, day, (meio, 39))

        self._draw_board_section(
            panel, cell, market, row=1, label="VENDE",
            itens=[(k, market.sell_price(k, day), c.sell_price,
                    settings.BOARD_SATURATED_COLOR) for k, c in CROPS.items()])
        self._draw_board_section(
            panel, cell, market, row=3, label="COMPRA",
            itens=[(k, market.buy_price(k), base, settings.BOARD_PROMO_COLOR)
                   for k, base in BUY_PRICES.items()])

        surface.blit(panel, rect)

    def _draw_budget(self, panel: pygame.Surface, market: Market, day: int,
                     center: tuple[int, int]) -> None:
        """Caixa que a loja ainda tem hoje para pagar por colheita."""
        saldo = market.budget_left
        mais_barato = min(market.sell_price(k, day) for k in CROPS)
        cor = (settings.BOARD_BUDGET_COLOR if saldo >= mais_barato
               else settings.BOARD_BUDGET_LOW_COLOR)
        texto = self.fonts.small.render(
            f"caixa {saldo}/{settings.MARKET_DAILY_BUDGET}", True, cor)
        panel.blit(texto, texto.get_rect(center=center))

    def _draw_board_section(self, panel, cell, market: Market, *, row: int,
                            label: str, itens: list) -> None:
        """Uma faixa do quadro: rotulo, linha de icones e linha de precos."""
        texto = self.fonts.small.render(label, True, settings.BOARD_TITLE_COLOR)
        area = cell(settings.BOARD_COLS[0], row).union(cell(settings.BOARD_COLS[0] + 1, row + 1))
        panel.blit(texto, texto.get_rect(center=area.center))

        for i, (item, price, base, destaque) in enumerate(itens):
            col = settings.BOARD_ITEM_COL + i
            icone = self.icons.get(item, 34)
            panel.blit(icone, icone.get_rect(center=cell(col, row).center))
            self._draw_price(panel, cell(col, row + 1), price, base, destaque)

    def _draw_price(self, panel: pygame.Surface, rect: pygame.Rect,
                    price: int, base: int, destaque) -> None:
        if price == base:
            texto = self.fonts.normal.render(str(price), True, settings.BOARD_PRICE_COLOR)
            panel.blit(texto, texto.get_rect(center=rect.center))
            return

        # Preco alterado: o base fica riscado em cima, o atual em destaque embaixo.
        antigo = self.fonts.small.render(str(base), True, settings.BOARD_OLD_PRICE_COLOR)
        pos = antigo.get_rect(center=(rect.centerx, rect.centery - 11))
        panel.blit(antigo, pos)
        pygame.draw.line(panel, settings.BOARD_OLD_PRICE_COLOR,
                         (pos.left - 3, pos.centery), (pos.right + 3, pos.centery), 2)
        atual = self.fonts.normal.render(str(price), True, destaque)
        panel.blit(atual, atual.get_rect(center=(rect.centerx, rect.centery + 10)))

    # -------------------------------------------------------------- transicao

    def draw_sleep(self, surface: pygame.Surface, day: int, progress: float) -> None:
        """Escurece e mostra o novo dia; progress vai de 0 a 1."""
        fade = 1 - abs(progress * 2 - 1)        # sobe e desce
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, round(235 * fade)))
        text = self.fonts.huge.render(f"Dia {day}", True, settings.HUD_COLOR)
        text.set_alpha(round(255 * fade))
        overlay.blit(text, text.get_rect(center=overlay.get_rect().center))
        surface.blit(overlay, (0, 0))

    # ------------------------------------------------------------ fim de jogo

    def draw_game_over(self, surface: pygame.Surface, stats: RunStats,
                       inventory: Inventory) -> None:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill(settings.OVERLAY_COLOR)
        surface.blit(overlay, (0, 0))

        center_x = surface.get_width() // 2
        title = self.fonts.huge.render("Você desmaiou de exaustão", True, (255, 120, 100))
        surface.blit(title, title.get_rect(midtop=(center_x, 210)))

        lines = [
            f"Dia alcançado: {stats.days}",
            "",
            f"Plantado:  {self._by_counter(stats.planted, CROPS)}",
            f"Colhido:   {self._by_counter(stats.harvested, CROPS)}",
            f"Vendido:   {self._by_counter(stats.sold, CROPS)}",
            f"Comprado:  {self._by_counter(stats.bought, BUY_PRICES)}",
            f"Moedas:    {inventory.count(COIN)}",
        ]
        for i, line in enumerate(lines):
            text = self.fonts.normal.render(line, True, settings.HUD_COLOR)
            surface.blit(text, text.get_rect(midtop=(center_x, 320 + i * 36)))

        hint = self.fonts.normal.render("R: recomeçar     ESC: sair", True, (255, 215, 100))
        surface.blit(hint, hint.get_rect(midtop=(center_x, 600)))

    @staticmethod
    def _by_counter(counter, keys) -> str:
        parts = [f"{ITEM_LABELS[k]} {counter[k]}" for k in keys if counter[k]]
        return "   ".join(parts) if parts else "nada"
