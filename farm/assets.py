"""Carregamento e cache de imagens.

As funcoes daqui so devem ser chamadas depois de pygame.display.set_mode(),
porque convert()/convert_alpha() precisam de um display ativo.
"""

import logging

import pygame

from farm import settings

logger = logging.getLogger(__name__)

_cache: dict[tuple[str, bool], pygame.Surface] = {}


def load_image(name: str, alpha: bool = True) -> pygame.Surface:
    """Carrega uma imagem de Assets/ pelo caminho relativo, com cache."""
    key = (name, alpha)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    path = settings.ASSETS_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"asset nao encontrado: {path}")

    surface = pygame.image.load(path)
    surface = surface.convert_alpha() if alpha else surface.convert()
    _cache[key] = surface
    logger.debug("imagem carregada: %s (%dx%d)", name, *surface.get_size())
    return surface


def load_frames(names: list[str], alpha: bool = True) -> list[pygame.Surface]:
    """Carrega uma sequencia de quadros de animacao na ordem dada."""
    return [load_image(name, alpha) for name in names]


def load_background() -> pygame.Surface:
    """Mapa do jogo em resolucao original; a View reduz na hora de desenhar."""
    surface = load_image(settings.BACKGROUND_IMAGE, alpha=False)
    if surface.get_size() != settings.WORLD_SIZE:
        logger.warning(
            "background tem %dx%d, mas WORLD_SIZE e %dx%d",
            *surface.get_size(),
            *settings.WORLD_SIZE,
        )
    return surface


def clear_cache() -> None:
    _cache.clear()
