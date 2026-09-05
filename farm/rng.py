"""A semente da partida: mesma SEED, mesmo cenario.

O jogo sorteia pouco -- so o estoque e a promocao do dia. Todo o resto (estagio
da planta, estacao, preco, saturacao) ja e funcao do dia. Este modulo faz o
sorteio virar funcao do dia tambem, para que uma partida possa ser repetida.

Nao mora no `settings` de proposito: la e so valor, sem logica.
"""

import logging
import os
import random

from farm import settings

logger = logging.getLogger(__name__)

# Nome do fluxo de cada sistema que sorteia. Um sistema novo (clima, evento)
# ganha o seu, e assim nao desloca o cenario do mercado nas partidas antigas.
MARKET = "mercado"


def resolve_seed(explicit: int | None = None) -> int:
    """A semente da partida, na ordem: argumento, FARM_SEED, settings.SEED.

    Se nada definir um numero, sorteia um e devolve. Quem chamou grava o valor
    no log, entao um cenario "aleatorio" continua repetivel depois.
    """
    for valor, origem in ((explicit, "--seed"),
                          (os.environ.get(settings.SEED_ENV), settings.SEED_ENV),
                          (settings.SEED, "settings.SEED")):
        if valor is None or str(valor).strip() == "":
            continue
        try:
            return int(valor)
        except ValueError:
            logger.warning("%s=%r nao e um numero inteiro, ignorando", origem, valor)

    sorteada = random.SystemRandom().randrange(1_000_000_000)
    logger.info("nenhuma semente definida: sorteada %d", sorteada)
    return sorteada


def stream(seed: int, name: str, day: int) -> random.Random:
    """O RNG de um sistema num dia.

    A chave e **string**: desde o 3.11 uma tupla levanta TypeError, e a string
    passa por sha512 em vez de `hash()`, entao o resultado e o mesmo entre
    processos, com ou sem PYTHONHASHSEED.
    """
    return random.Random(f"{seed}:{name}:{day}")
