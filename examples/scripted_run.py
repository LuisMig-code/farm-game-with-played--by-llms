"""Roteiro fixo: planta, espera crescer, colhe e vende -- gravando em video.

    venv/Scripts/python.exe examples/scripted_run.py
    venv/Scripts/python.exe examples/scripted_run.py --seed 7 --no-video

E o "ola mundo" da camada de scripting: mostra o ciclo completo do jogo em
poucas linhas e deixa um MP4 em logs/ para assistir depois.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from farm import settings
from farm.crops import CROPS
from scripting import HOUSE, SHOP, Session

# Duas celulas de horta coladas na descida da esquerda: perto da casa, barato
# de alcancar em estamina. O jogo comeca com UMA semente de cada tipo, entao o
# roteiro planta culturas diferentes em vez de repetir a mesma.
CANTEIROS = {(6, 8): "batata", (6, 7): "cenoura"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=None, help="semente do cenario")
    parser.add_argument("--no-video", action="store_true", help="nao gravar MP4")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    video = None if args.no_video else settings.LOGS_DIR / "scripted_run.mp4"
    with Session(seed=args.seed, record=video) as s:
        print(f"semente {s.game.seed} | plantando {CANTEIROS}")
        for canteiro, cultura in CANTEIROS.items():
            s.walk_to(canteiro).plant(cultura)

        # Espera a mais lenta ficar pronta; as outras so ganham dias de sobra.
        maior = max(CROPS[c].grow_days for c in CANTEIROS.values())
        s.walk_to(HOUSE).sleep_until(day=s.day + maior)
        print(f"dia {s.day}: hora de colher")

        for canteiro in CANTEIROS:
            s.walk_to(canteiro).harvest()

        s.walk_to(SHOP)
        for cultura in set(CANTEIROS.values()):
            s.sell(cultura, s.count(cultura))
        print(f"vendeu a colheita | {s.coins} moeda(s) | estamina {s.stamina}")

        print()
        print(s.observe().as_text())
        if video:
            print(f"\nvideo: {video}")


if __name__ == "__main__":
    main()
