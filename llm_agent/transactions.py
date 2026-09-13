"""As transacoes que o jogador de fato fez no jogo, e nao as que o LLM pediu.

O executor sabe o que o plano mandou; o que aconteceu de verdade o jogo registra.
`Game._sell` e `Game._buy` so chamam `run_log.record("vender"|"comprar", ...)`
quando a unidade foi mesmo negociada, com o preco daquela unidade e depois de
mexer nas moedas. Aqui essa chamada e observada, sem tocar em `farm/`: um atributo
de instancia sombreia o metodo, o mesmo truque da `Session` com `_input_direction`.

Unidades seguidas da mesma operacao e do mesmo item formam uma transacao. Qualquer
outro evento que o jogo registre a fecha -- andar, plantar, dormir, negociar outro
item, abrir ou fechar um menu. Vender 5 batatas, sair da loja e voltar para vender
mais 17 sao duas transacoes.
"""

from dataclasses import dataclass

from farm.crops import COIN, crop_of_seed

KINDS = {"comprar": "compra", "vender": "venda"}


@dataclass
class Transaction:
    day: int
    kind: str              # "compra" ou "venda"
    item: str              # o cultivo, ou "fertilizante"
    quantity: int = 0
    price_min: int = 0
    price_max: int = 0
    total: int = 0         # moedas pagas (compra) ou recebidas (venda)
    coins_after: int = 0   # moedas do jogador depois da ultima unidade

    def add(self, price: int, amount: int, coins_after: int) -> None:
        self.price_min = price if not self.quantity else min(self.price_min, price)
        self.price_max = max(self.price_max, price)
        self.quantity += amount
        self.total += price * amount
        self.coins_after = coins_after


class TransactionLog:
    """Observa o registro do jogo e entrega cada transacao a `on_close` quando ela fecha."""

    def __init__(self, game, on_close):
        self._game = game
        self._on_close = on_close
        self._open: Transaction | None = None
        registrar = game.run_log.record

        def record(action, **kwargs):
            registrar(action, **kwargs)
            self._observe(action, kwargs)

        game.run_log.record = record

    def _observe(self, action: str, kwargs: dict) -> None:
        kind = KINDS.get(action)
        if kind is None:
            self.flush()
            return
        item = crop_of_seed(kwargs["item"])        # "semente melancia" -> "melancia"
        aberta = self._open
        if aberta is None or (aberta.day, aberta.kind, aberta.item) != (kwargs["day"], kind, item):
            self.flush()
            aberta = self._open = Transaction(kwargs["day"], kind, item)
        # O jogo registra uma linha por unidade (amount=1), com o preco dela.
        aberta.add(int(kwargs["price"]), int(kwargs.get("amount") or 1),
                   self._game.inventory.count(COIN))

    def flush(self) -> None:
        """Fecha a transacao aberta, se houver."""
        if self._open is not None:
            fechada, self._open = self._open, None
            self._on_close(fechada)
