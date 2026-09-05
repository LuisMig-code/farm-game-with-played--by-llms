"""Uma politica boba jogando sozinha ate a estamina acabar.

    venv/Scripts/python.exe examples/random_agent.py --seed 7 --days 20

Serve de esqueleto para um agente de verdade: o laco le a observacao, escolhe
uma acao e trata a recusa. Trocar `decide()` por uma chamada de LLM -- passando
`observation.as_text()` no prompt -- e o passo seguinte.
"""

import argparse
import logging
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from farm import settings
from farm.crops import CROPS, seed_key
from scripting import HOUSE, SHOP, Blocked, GameOver, Session, shortest_path


def distance(session, destino: tuple[int, int]) -> int:
    """Passos ate o destino -- e, como cada passo custa 1, tambem a estamina."""
    caminho = shortest_path(session.cell, destino, session.game.zones.walkable)
    return 10 ** 6 if caminho is None else len(caminho)


def affordable(session, destinos, margem: int = 0):
    """So os destinos que dao para alcancar e ainda voltar para casa vivo.

    Andar custa 1 de estamina por celula e dormir e a unica forma de recuperar,
    entao toda ida precisa caber junto com a volta -- e essa e a decisao que
    separa um agente que sobrevive de um que morre no meio da horta.
    """
    orcamento = session.stamina - margem
    for destino in sorted(destinos, key=lambda c: distance(session, c)):
        ida = distance(session, destino)
        volta = len(shortest_path(destino, HOUSE, session.game.zones.walkable) or [])
        if ida + volta <= orcamento:
            return destino
    return None


def decide(session, rng: random.Random) -> tuple[str, tuple[int, int]]:
    """Escolhe o proximo destino e o que fazer la. Prioridade simples.

    Um agente de verdade decidiria com base em `session.observe()`; aqui a
    politica so olha o campo e a estamina, para o exemplo caber numa tela.
    """
    campo, dia = session.game.field, session.day

    prontas = [c for c in campo.plots if campo.is_grown(c, dia)
               and not campo.is_spoiled(c, dia)]
    alvo = affordable(session, prontas, margem=settings.STAMINA_HARVEST)
    if alvo:
        return "harvest", alvo

    estragadas = [c for c in campo.plots if campo.is_spoiled(c, dia)]
    alvo = affordable(session, estragadas, margem=settings.STAMINA_CLEAR)
    if alvo:
        return "clear", alvo

    colheita = [k for k in CROPS if session.count(k)]
    if colheita and affordable(session, [SHOP]):
        return "sell", SHOP

    tem_semente = any(session.count(seed_key(k)) for k in CROPS)
    vazias = [c for c in session.game.zones.plantable if campo.at(c) is None]
    alvo = affordable(session, vazias, margem=settings.STAMINA_PLANT) if tem_semente else None
    if alvo:
        return "plant", alvo

    return "sleep", HOUSE


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--days", type=int, default=15, help="para em que dia")
    parser.add_argument("--no-video", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    rng = random.Random(args.seed)
    video = None if args.no_video else settings.LOGS_DIR / "random_agent.mp4"

    with Session(seed=args.seed, record=video) as s:
        print(f"semente {s.game.seed} | jogando ate o dia {args.days}")
        try:
            while s.day < args.days and not s.over:
                acao, alvo = decide(s, rng)
                s.walk_to(alvo)
                try:
                    fazer(s, acao, rng)
                except Blocked as erro:
                    # Recusa e informacao, nao acidente: a politica tenta outra.
                    print(f"  dia {s.day}: {acao} recusado -- {erro}")
        except GameOver as erro:
            print(f"fim: {erro}")

        print(f"\nterminou no dia {s.day} | {s.coins} moeda(s) | "
              f"estamina {s.stamina}")
        print(f"plantou {sum(s.stats.planted.values())}, "
              f"colheu {sum(s.stats.harvested.values())}, "
              f"vendeu {sum(s.stats.sold.values())}")
        if video:
            print(f"video: {video}")


def fazer(s: Session, acao: str, rng: random.Random) -> None:
    if acao == "sleep":
        s.sleep()
    elif acao == "harvest":
        s.harvest()
    elif acao == "clear":
        s.clear()
    elif acao == "plant":
        s.plant(rng.choice([k for k in CROPS if s.count(seed_key(k))]))
    elif acao == "sell":
        for crop in CROPS:
            if s.count(crop):
                s.sell(crop, s.count(crop))
                return


if __name__ == "__main__":
    main()
