"""Precos da loja: promocao diaria e saturacao por excesso de venda."""

import logging
from collections import Counter

from farm import settings
from farm.crops import BUY_PRICES, CROPS, STOCK_RANGES
from farm.rng import MARKET, stream
from farm.seasons import (daily_budget, promo_discounts, promo_item_chances,
                          season_at)

logger = logging.getLogger(__name__)


class Market:
    """Guarda o que muda de preco no dia: promocoes e saturacao das culturas.

    Os precos base ficam no catalogo (`farm/crops.py`); aqui so vive o desvio.
    A `seed` fixa o cenario: a mesma semente da o mesmo estoque e a mesma
    promocao em cada dia, em qualquer partida.
    """

    def __init__(self, seed: int):
        self.seed = seed
        self.promos: dict[str, int] = {}       # item de compra -> desconto do dia
        self.saturation: dict[str, int] = {}   # cultura -> moedas ja descontadas
        self._sold_today: Counter[str] = Counter()
        self._sold_yesterday: Counter[str] = Counter()
        self._paid_today = 0                   # moedas que a loja pagou hoje
        self._spent_today = 0                  # moedas que o jogador gastou hoje
        self.stock: dict[str, int] = {}
        self._roll_day(settings.FIRST_DAY)

    # --------------------------------------------------------------- estoque

    def roll_stock(self) -> dict[str, int]:
        """Estoque do dia, uniforme dentro da faixa de cada item. Nao acumula."""
        self.stock = {item: self.rng.randint(*faixa)
                      for item, faixa in STOCK_RANGES.items()}
        return dict(self.stock)

    def stock_left(self, item: str) -> int:
        return self.stock.get(item, 0)

    # ----------------------------------------------------------- caixa do dia

    @staticmethod
    def daily_budget(day: int) -> int:
        """Teto do dia. O inverno paga mais, entao tambem tem mais caixa."""
        return daily_budget(day)

    def budget_left(self, day: int) -> int:
        """Quanto a loja ainda pode pagar hoje.

        Comprar devolve caixa ao mercado, entao gastar na loja levanta o teto do
        dia -- inclusive depois de ele ter zerado.
        """
        return self.daily_budget(day) + self._spent_today - self._paid_today

    def can_sell(self, crop: str, day: int) -> bool:
        return self.sell_price(crop, day) <= self.budget_left(day)

    def register_purchase(self, item: str, price: int) -> None:
        self.stock[item] = max(0, self.stock_left(item) - 1)
        self._spent_today += price

    # ---------------------------------------------------------------- precos

    def buy_price(self, item: str) -> int:
        """Preco de compra do dia, ja com a promocao. Nunca abaixo de MIN_PRICE."""
        return BUY_PRICES[item] - self.promos.get(item, 0)

    def base_price(self, crop: str, day: int) -> int:
        """Preco cheio do dia, ja com o multiplicador da estacao."""
        multiplicador = season_at(day).sell_multiplier.get(crop, 1)
        return round(CROPS[crop].sell_price * multiplicador)

    def sell_price(self, crop: str, day: int) -> int:
        """Preco de venda do dia. So cai depois que a oferta/demanda liga."""
        base = self.base_price(crop, day)
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
        self._roll_day(day)

    def _roll_day(self, day: int) -> None:
        """Os sorteios do dia, sobre um RNG refeito a partir de (semente, dia).

        Recomecar o fluxo todo dia e o que faz o cenario do dia 30 ser o mesmo
        dia 30 sempre -- nao importa por quais dias a partida passou antes, nem
        o que for sorteado por outros sistemas no futuro.
        """
        self.rng = stream(self.seed, MARKET, day)
        self.roll_stock()                      # antes da promocao: ela depende dele
        self.roll_promotions(day)

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

    def roll_promotions(self, day: int) -> dict[str, int]:
        """Sorteia as promocoes do dia e devolve as que sairam.

        Sao tres sorteios: quantos itens, quais itens (uniforme, sem peso) e o
        tamanho de cada desconto (esse sim, com peso).
        """
        self.promos = {}
        for item in self._draw_items(day):
            self.promos[item] = self._draw_discount(BUY_PRICES[item], day)

        if self.promos:
            logger.info("promocao do dia: %s", {k: f"-{v}" for k, v in self.promos.items()})
        return dict(self.promos)

    def _draw_items(self, day: int) -> list[str]:
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
        for quantidade, peso in promo_item_chances(day):
            acumulado += peso
            if chance < acumulado:
                return self.rng.sample(disponiveis, min(quantidade, len(disponiveis)))
        return []

    def _draw_discount(self, base_price: int, day: int) -> int:
        tabela = promo_discounts(day)
        if base_price < settings.PROMO_SMALL_PRICE:
            desconto = tabela[0][0]                    # item barato: o menor desconto
        else:
            valores = [v for v, _ in tabela]
            pesos = [p for _, p in tabela]
            desconto = self.rng.choices(valores, weights=pesos, k=1)[0]
        # Guardar o desconto ja limitado deixa o "nunca de graca" estrutural.
        return min(desconto, base_price - settings.MIN_PRICE)
