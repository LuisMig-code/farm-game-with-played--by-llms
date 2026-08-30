"""Ponto de entrada do jogo de fazenda."""

import logging
import sys

import pygame

from farm import settings
from farm.game import Game


def setup_logging() -> None:
    """So o console: o arquivo de texto e criado por run, em farm/run_log.py."""
    settings.LOGS_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main() -> None:
    setup_logging()
    try:
        Game().run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
