"""Inventario do jogador e as estatisticas da partida."""

from collections import Counter
from dataclasses import dataclass, field

from farm import settings
from farm.crops import (COIN, CROPS, FERTILIZER, INVENTORY_ORDER, ITEM_LIMITS,
                        seed_key)


class Inventory:
    """Contagem por chave de item. Chaves ausentes valem zero."""

    def __init__(self, counts: dict[str, int] | None = None):
        self._counts: dict[str, int] = dict(counts or {})

    def count(self, item: str) -> int:
        return self._counts.get(item, 0)

    def has(self, item: str, amount: int = 1) -> bool:
        return self.count(item) >= amount

    def limit_for(self, item: str) -> int | None:
        """Teto desse item, ou None quando ele nao tem limite."""
        return ITEM_LIMITS.get(item)

    def room_for(self, item: str) -> int:
        """Quantas unidades ainda cabem. Sem limite, devolve um numero grande."""
        limite = self.limit_for(item)
        return 10 ** 9 if limite is None else max(0, limite - self.count(item))

    def is_full(self, item: str) -> bool:
        return self.room_for(item) == 0

    def add(self, item: str, amount: int = 1) -> None:
        """Nunca passa do teto: o limite e invariante do inventario."""
        self._counts[item] = self.count(item) + min(amount, self.room_for(item))

    def take(self, item: str, amount: int = 1) -> bool:
        """Tira do inventario. False (e nada muda) se nao houver o suficiente."""
        if not self.has(item, amount):
            return False
        self._counts[item] = self.count(item) - amount
        return True

    def slots(self) -> list[tuple[str, int]]:
        """Todos os itens do jogo na ordem de exibicao, inclusive os zerados."""
        return [(item, self.count(item)) for item in INVENTORY_ORDER]


def starting_inventory() -> Inventory:
    """Uma semente de cada tipo, alguns fertilizantes, nenhum vegetal ou moeda."""
    counts = {seed_key(k): settings.STARTING_SEEDS for k in CROPS}
    counts[FERTILIZER] = settings.STARTING_FERTILIZER
    counts[COIN] = 0
    return Inventory(counts)


@dataclass
class RunStats:
    """Resumo da partida, mostrado na tela de derrota."""

    planted: Counter[str] = field(default_factory=Counter)
    harvested: Counter[str] = field(default_factory=Counter)
    sold: Counter[str] = field(default_factory=Counter)
    bought: Counter[str] = field(default_factory=Counter)
    spoiled: Counter[str] = field(default_factory=Counter)
    fertilized: int = 0
    days: int = 1
