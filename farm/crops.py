"""Catalogo das culturas e das chaves de item. So dados, sem logica de jogo."""

from dataclasses import dataclass

ICONS_DIR = "icons"
PROPS_DIR = "props"

# Itens que nao vem de uma cultura.
FERTILIZER = "fertilizante"
COIN = "moeda"
FERTILIZER_PRICE = 21
FERTILIZER_STOCK = (1, 6)     # faixa do estoque diario da loja
FERTILIZER_LIMIT = 9          # quanto o jogador consegue carregar
SEED_LIMIT = 20               # de cada tipo de semente

SEED_PREFIX = "semente "


@dataclass(frozen=True)
class Crop:
    """Uma cultura plantavel. Os caminhos saem do nome, que e igual em todas as pastas."""

    key: str
    label: str
    grow_days: int
    shelf_days: int     # dias que aguenta depois de crescida, antes de estragar
    fert_grow_cut: int      # dias a menos para crescer, se fertilizada
    fert_shelf_bonus: int   # dias a mais de validade, se fertilizada
    sell_price: int     # o que a loja paga pelo vegetal
    seed_price: int     # o que a loja cobra pela semente
    stock_range: tuple[int, int]   # sementes que a loja tem por dia (min, max)

    @property
    def seed_icon(self) -> str:
        return f"{ICONS_DIR}/seed {self.key}.png"

    @property
    def item_icon(self) -> str:
        return f"{ICONS_DIR}/icon {self.key}.png"

    @property
    def stages(self) -> tuple[str, str, str, str]:
        """Sprites de plantado, germinando, crescido e estragado."""
        return tuple(f"{PROPS_DIR}/{self.key} {i}.png" for i in (1, 2, 3, 4))


CROPS: dict[str, Crop] = {
    crop.key: crop
    for crop in (
        Crop("batata", "Batata", grow_days=3, shelf_days=3, fert_grow_cut=2,
             fert_shelf_bonus=2, sell_price=6, seed_price=4, stock_range=(1, 35)),
        Crop("cenoura", "Cenoura", grow_days=2, shelf_days=3, fert_grow_cut=1,
             fert_shelf_bonus=2, sell_price=3, seed_price=2, stock_range=(1, 30)),
        Crop("beterraba", "Beterraba", grow_days=5, shelf_days=3, fert_grow_cut=2,
             fert_shelf_bonus=4, sell_price=9, seed_price=6, stock_range=(0, 25)),
        Crop("trigo", "Trigo", grow_days=7, shelf_days=4, fert_grow_cut=2,
             fert_shelf_bonus=4, sell_price=12, seed_price=7, stock_range=(0, 25)),
        Crop("melancia", "Melancia", grow_days=9, shelf_days=4, fert_grow_cut=3,
             fert_shelf_bonus=4, sell_price=18, seed_price=11, stock_range=(0, 15)),
    )
}


def seed_key(crop_key: str) -> str:
    return SEED_PREFIX + crop_key


def crop_of_seed(item_key: str) -> str:
    return item_key.removeprefix(SEED_PREFIX)


# Ordem fixa dos slots do inventario: sementes, vegetais, fertilizante, moeda.
INVENTORY_ORDER: tuple[str, ...] = (
    *(seed_key(k) for k in CROPS),
    *CROPS,
    FERTILIZER,
    COIN,
)

# Faixa do estoque diario, na mesma ordem do quadro de precos.
STOCK_RANGES: dict[str, tuple[int, int]] = {
    **{seed_key(k): c.stock_range for k, c in CROPS.items()},
    FERTILIZER: FERTILIZER_STOCK,
}

# Teto do inventario. Vegetais e moedas nao tem limite: nao aparecem aqui.
ITEM_LIMITS: dict[str, int] = {
    **{seed_key(k): SEED_LIMIT for k in CROPS},
    FERTILIZER: FERTILIZER_LIMIT,
}

ITEM_ICONS: dict[str, str] = {
    **{seed_key(k): c.seed_icon for k, c in CROPS.items()},
    **{k: c.item_icon for k, c in CROPS.items()},
    FERTILIZER: f"{ICONS_DIR}/icon {FERTILIZER}.png",
    COIN: f"{ICONS_DIR}/icon coin.png",
}

# Itens que a loja vende, na ordem em que aparecem no quadro de precos.
BUY_PRICES: dict[str, int] = {
    **{seed_key(k): c.seed_price for k, c in CROPS.items()},
    FERTILIZER: FERTILIZER_PRICE,
}

ITEM_LABELS: dict[str, str] = {
    **{seed_key(k): f"Semente de {c.label}" for k, c in CROPS.items()},
    **{k: c.label for k, c in CROPS.items()},
    FERTILIZER: "Fertilizante",
    COIN: "Moeda",
}
