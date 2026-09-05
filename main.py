"""Ponto de entrada do jogo de fazenda."""

import argparse
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Farm Game")
    parser.add_argument(
        "--seed", type=int, default=None,
        help=(f"semente do cenario; sem ela vale {settings.SEED_ENV} e, por fim, "
              "settings.SEED. A mesma semente da o mesmo estoque e a mesma "
              "promocao em cada dia."))
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    setup_logging()
    try:
        Game(seed=args.seed).run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
