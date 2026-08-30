"""Precos da loja: promocao diaria e saturacao por excesso de venda."""

import logging
import random
from collections import Counter

from farm import settings
from farm.crops import BUY_PRICES, CROPS, STOCK_RANGES

logger = logging.getLogger(__name__)


class Market:
    """Guarda o que muda de preco no dia: promocoes e saturacao das culturas.

    Os precos base ficam no catalogo (`farm/crops.py`); aqui so vive o desvio.
    O `rng` e injetavel para os testes poderem semear o sorteio.
    """

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.promos: dict[str, int] = {}       # item de compra -> desconto do dia
        self.saturation: dict[str, int] = {}   # cultura -> moedas ja descontadas
        self._sold_today: Counter[str] = Counter()
        self._sold_yesterday: Counter[str] = Counter()
        self._paid_today = 0                   # moedas que a loja pagou hoje
        self._spent_today = 0                  # moedas que o jogador gastou hoje
        self.stock: dict[str, int] = {}
        self.roll_stock()                      # antes da promocao: ela depende dele
        self.roll_promotions()

    # --------------------------------------------------------------- estoque

    def roll_stock(self) -> dict[str, int]:
        """Estoque do dia, uniforme dentro da faixa de cada item. Nao acumula."""
        self.stock = {item: self.rng.randint(*faixa)
                      for item, faixa in STOCK_RANGES.items()}
        return dict(self.stock)

    def stock_left(self, item: str) -> int:
        return self.stock.get(item, 0)

    # ----------------------------------------------------------- caixa do dia

    @property
    def budget_left(self) -> int:
        """Quanto a loja ainda pode pagar hoje.

        Comprar devolve caixa ao mercado, entao gastar na loja levanta o teto do
        dia -- inclusive depois de ele ter zerado.
        """
        return settings.MARKET_DAILY_BUDGET + self._spent_today - self._paid_today

    def can_sell(self, crop: str, day: int) -> bool:
        return self.sell_price(crop, day) <= self.budget_left

    def register_purchase(self, item: str, price: int) -> None:
        self.stock[item] = max(0, self.stock_left(item) - 1)
        self._spent_today += price

    # ---------------------------------------------------------------- precos

    def buy_price(self, item: str) -> int:
        """Preco de compra do dia, ja com a promocao. Nunca abaixo de MIN_PRICE."""
        return BUY_PRICES[item] - self.promos.get(item, 0)

    def sell_price(self, crop: str, day: int) -> int:
        """Preco de venda do dia. So cai depois que a oferta/demanda liga."""
        base = CROPS[crop].sell_price
        if not self.supply_demand_active(day):
            return base
        return max(CROPS[crop].seed_price, base - self.saturation.get(crop, 0))

    @staticmethod
    def supply_demand_active(day: int) -> bool:
        return day >= settings.SUPPLY_DEMAND_START_DAY

    def is_promo(self, item: str) -> bool:
        return item in self.promos

    def is_saturated(self, crop: str, day: int) -> bool:
        return self.sell_price(crop, day) < CROPS[crop].sell_price

    # ----------------------------------------------------------------- venda

    def register_sale(self, crop: str, day: int) -> None:
        """Registra a venda: consome caixa do dia e pode saturar a cultura.

        O caixa e cobrado sempre. A saturacao depende da trava de dia mais um
        dos gatilhos de `saturates`. Antes do dia de largada nada e sequer
        contado: guardar em silencio faria o jogador levar a conta inteira de
        uma vez quando o sistema ligasse.
        """
        self._paid_today += self.sell_price(crop, day)

        if not self.supply_demand_active(day):
            return

        self._sold_today[crop] += 1
        if not self.saturates(crop):
            return

        # O teto e a distancia ate o piso: sem isso, um despejo de 30 melancias
        # viraria uma divida de 30 dias e a recuperacao pareceria quebrada.
        teto = CROPS[crop].sell_price - CROPS[crop].seed_price
        atual = self.saturation.get(crop, 0) + settings.SUPPLY_DEMAND_DROP
        self.saturation[crop] = min(teto, atual)

    def saturates(self, crop: str) -> bool:
        """Um dos dois gatilhos basta: despejo num dia so, ou repeticao.

        A contagem comeca quando o gatilho dispara, nao retroativamente: numa
        venda isolada as 6 primeiras saem pelo preco cheio e a 7a e a primeira
        a derrubar.
        """
        return (self._sold_today[crop] >= settings.SUPPLY_DEMAND_DAILY_UNITS
                or self.sold_two_days_running(crop))

    def sold_two_days_running(self, crop: str) -> bool:
        """Vendeu essa cultura ontem E hoje, em qualquer quantidade.

        Uma unidade em cada dia ja basta: o que o mercado pune e a repeticao,
        nao o volume.
        """
        return bool(self._sold_today[crop] and self._sold_yesterday[crop])

    def sold_today(self, crop: str) -> int:
        return self._sold_today[crop]

    # -------------------------------------------------------------- novo dia

    def new_day(self, day: int) -> None:
        self._recover()
        self._sold_yesterday = self._sold_today
        self._sold_today = Counter()
        self._paid_today = self._spent_today = 0   # caixa nao acumula entre dias
        self.roll_stock()
        self.roll_promotions()

    def _recover(self) -> None:
        """Cultura que nao foi vendida ontem recupera parte do preco."""
        for crop in list(self.saturation):
            if crop in self._sold_today:
                continue
            restante = self.saturation[crop] - settings.SUPPLY_DEMAND_RECOVERY
            if restante > 0:
                self.saturation[crop] = restante
            else:
                del self.saturation[crop]

    # ------------------------------------------------------------- promocoes

    def roll_promotions(self) -> dict[str, int]:
        """Sorteia as promocoes do dia e devolve as que sairam.

        Sao tres sorteios: quantos itens, quais itens (uniforme, sem peso) e o
        tamanho de cada desconto (esse sim, com peso).
        """
        self.promos = {}
        for item in self._draw_items():
            self.promos[item] = self._draw_discount(BUY_PRICES[item])

        if self.promos:
            logger.info("promocao do dia: %s", {k: f"-{v}" for k, v in self.promos.items()})
        return dict(self.promos)

    def _draw_items(self) -> list[str]:
        """Quantos e quais itens entram em promocao hoje.

        So concorrem itens com estoque: nao adianta anunciar desconto em semente
        que a loja nao tem para vender. Entre os disponiveis a escolha e
        uniforme, sem peso.
        """
        disponiveis = [item for item in BUY_PRICES if self.stock_left(item) > 0]
        if not disponiveis:
            return []

        chance = self.rng.random()
        acumulado = 0.0
        for quantidade, peso in settings.PROMO_ITEM_CHANCES:
            acumulado += peso
            if chance < acumulado:
                return self.rng.sample(disponiveis, min(quantidade, len(disponiveis)))
        return []

    def _draw_discount(self, base_price: int) -> int:
        if base_price < settings.PROMO_SMALL_PRICE:
            desconto = settings.PROMO_DISCOUNTS[0][0]   # item barato: o menor desconto
        else:
            valores = [v for v, _ in settings.PROMO_DISCOUNTS]
            pesos = [p for _, p in settings.PROMO_DISCOUNTS]
            desconto = self.rng.choices(valores, weights=pesos, k=1)[0]
        # Guardar o desconto ja limitado deixa o "nunca de graca" estrutural.
        return min(desconto, base_price - settings.MIN_PRICE)
