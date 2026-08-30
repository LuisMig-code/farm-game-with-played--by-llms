"""Menu de opcoes navegado pelo teclado (sementes, fertilizante)."""

from dataclasses import dataclass

import pygame

from farm import settings

PADDING = 14
ROW_HEIGHT = 46
ICON_HEIGHT = 34


@dataclass
class Option:
    label: str
    value: str | None = None      # None = opcao apenas informativa
    icon: str | None = None       # chave de item, para o icone
    enabled: bool = True


class Menu:
    def __init__(self, kind: str, title: str, options: list[Option], cell: tuple[int, int]):
        self.kind = kind          # "semente" ou "fertilizante"
        self.title = title
        self.options = options
        self.cell = cell          # celula do mapa que o menu esta afetando
        self.index = next((i for i, o in enumerate(options) if o.enabled), 0)

    # ---------------------------------------------------------------- teclado

    def move(self, delta: int) -> None:
        """Anda pelas opcoes habilitadas, dando a volta nas pontas."""
        usable = [i for i, o in enumerate(self.options) if o.enabled]
        if not usable:
            return
        if self.index in usable:
            position = usable.index(self.index)
            self.index = usable[(position + delta) % len(usable)]
        else:
            self.index = usable[0]

    def confirm(self) -> str | None:
        """Valor da opcao selecionada, ou None se ela nao e acionavel."""
        option = self.options[self.index]
        return option.value if option.enabled else None

    # ---------------------------------------------------------------- desenho

    def draw(self, surface: pygame.Surface, fonts, icons,
             anchor: tuple[int, int]) -> None:
        """Desenha ancorado acima da celula alvo, preso dentro da tela."""
        title = fonts.small.render(self.title, True, settings.HUD_COLOR)
        width = max(title.get_width(), *(fonts.normal.size(o.label)[0] for o in self.options))
        width += PADDING * 2 + ICON_HEIGHT + 10
        height = PADDING * 2 + title.get_height() + 6 + ROW_HEIGHT * len(self.options)

        rect = pygame.Rect(0, 0, width, height)
        rect.midbottom = anchor
        rect.clamp_ip(surface.get_rect().inflate(-16, -16))

        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill(settings.MENU_BG_COLOR)
        pygame.draw.rect(panel, settings.MENU_BORDER_COLOR, panel.get_rect(), 2)
        panel.blit(title, (PADDING, PADDING))

        top = PADDING + title.get_height() + 6
        for i, option in enumerate(self.options):
            row = pygame.Rect(PADDING // 2, top + i * ROW_HEIGHT,
                              rect.width - PADDING, ROW_HEIGHT - 4)
            selecionada = i == self.index and option.enabled
            if selecionada:
                panel.fill(settings.MENU_SELECTED_COLOR, row)

            x = row.x + 8
            if option.icon:
                icon = icons.get(option.icon, ICON_HEIGHT)
                panel.blit(icon, icon.get_rect(midleft=(x, row.centery)))
            x += ICON_HEIGHT + 10

            if selecionada:
                color = settings.MENU_SELECTED_TEXT
            elif option.enabled:
                color = settings.HUD_COLOR
            else:
                color = settings.MENU_DISABLED_COLOR
            label = fonts.normal.render(option.label, True, color)
            panel.blit(label, label.get_rect(midleft=(x, row.centery)))

        surface.blit(panel, rect)
