"""O estado da partida do ponto de vista de quem joga por codigo.

Duas saidas do mesmo conteudo: `as_dict` para um agente programatico e
`as_text` para entrar num prompt. Nada aqui calcula regra -- tudo vem de metodo
publico do jogo, para a observacao nunca discordar da partida.
"""

from dataclasses import dataclass, field
from typing import Any

from farm import seasons, settings
from farm.crops import BUY_PRICES, COIN, CROPS, ITEM_LABELS

STAGES = ("plantada", "germinando", "pronta", "estragada")


@dataclass(frozen=True)
class Observation:
    """Retrato do jogo num instante. Serializavel e sem referencia ao pygame."""

    day: int
    season: str
    days_to_next_season: int
    season_effect: str
    stamina: int
    max_stamina: int
    coins: int
    cell: tuple[int, int]
    zone: str
    over: bool
    fertilizers_left: int
    inventory: dict[str, dict[str, Any]] = field(default_factory=dict)
    plots: list[dict[str, Any]] = field(default_factory=list)
    market: dict[str, Any] = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)

    # ------------------------------------------------------------- construcao

    @classmethod
    def of(cls, game) -> "Observation":
        day, campo, loja = game.day, game.field, game.market
        estacao = seasons.season_at(day)
        cell = game.player.cell

        return cls(
            day=day,
            season=estacao.label,
            days_to_next_season=seasons.days_to_next(day),
            season_effect=estacao.effect,
            stamina=game.player.stamina,
            max_stamina=game.player.max_stamina,
            coins=game.inventory.count(COIN),
            cell=cell,
            zone=game.zones.zone_of(cell),
            over=game.player.exhausted,
            fertilizers_left=max(0, settings.FERTILIZERS_PER_DAY - game.fertilizers_today),
            inventory=cls._inventory(game),
            plots=cls._plots(campo, day),
            market=cls._market(loja, day),
            actions=cls._actions(game),
        )

    @staticmethod
    def _inventory(game) -> dict[str, dict[str, Any]]:
        inv = game.inventory
        return {
            item: {"count": quantidade, "limit": inv.limit_for(item),
                   "label": ITEM_LABELS.get(item, item)}
            for item, quantidade in inv.slots() if item != COIN
        }

    @staticmethod
    def _plots(campo, day: int) -> list[dict[str, Any]]:
        linhas = []
        for cell, plot in sorted(campo.plots.items()):
            idade = campo.age(cell, day)
            crescer, validade = campo.timing(plot)
            linhas.append({
                "cell": list(cell),
                "crop": plot.crop,
                "stage": STAGES[campo.stage_index(cell, day)],
                "fertilized": plot.fertilized,
                # Negativo nao existe: uma vez pronta, faltam zero dias.
                "days_to_grow": max(0, crescer - idade),
                "days_to_spoil": max(0, crescer + validade - idade),
            })
        return linhas

    @staticmethod
    def _market(loja, day: int) -> dict[str, Any]:
        return {
            "budget_left": loja.budget_left(day),
            "daily_budget": loja.daily_budget(day),
            "sell": {crop: {"price": loja.sell_price(crop, day),
                            "base": loja.base_price(crop, day),
                            "saturated": loja.is_saturated(crop, day)}
                     for crop in CROPS},
            "buy": {item: {"price": loja.buy_price(item),
                           "full_price": BUY_PRICES[item],
                           "stock": loja.stock_left(item),
                           "promo": loja.is_promo(item)}
                    for item in BUY_PRICES},
        }

    @staticmethod
    def _actions(game) -> list[str]:
        """O que a Session aceitaria agora. Nao inventa regra: espelha o jogo."""
        if game.player.exhausted:
            return []

        cell = game.player.cell
        zona = game.zones.zone_of(cell)
        acoes = ["walk_to"]
        if zona == "casa":
            acoes.append("sleep")
        elif zona == "comercio":
            acoes += ["sell", "buy"]
        elif game.zones.is_plantable(cell):
            if game.field.at(cell) is None:
                acoes.append("plant")
            elif game.field.is_spoiled(cell, game.day):
                acoes.append("clear")
            elif game.field.is_grown(cell, game.day):
                acoes.append("harvest")
            else:
                acoes.append("fertilize")
        return acoes

    # ----------------------------------------------------------------- saidas

    def as_dict(self) -> dict[str, Any]:
        """Tudo em tipos que o json aceita."""
        return {
            "day": self.day,
            "season": self.season,
            "days_to_next_season": self.days_to_next_season,
            "season_effect": self.season_effect,
            "stamina": self.stamina,
            "max_stamina": self.max_stamina,
            "coins": self.coins,
            "cell": list(self.cell),
            "zone": self.zone,
            "over": self.over,
            "fertilizers_left": self.fertilizers_left,
            "inventory": self.inventory,
            "plots": self.plots,
            "market": self.market,
            "actions": self.actions,
        }

    def as_text(self) -> str:
        """O mesmo estado em texto curto, pronto para um prompt."""
        linhas = [
            f"Dia {self.day} | {self.season} (muda em {self.days_to_next_season} dia(s)): "
            f"{self.season_effect}",
            f"Estamina {self.stamina}/{self.max_stamina} | {self.coins} moeda(s) | "
            f"jogador em {tuple(self.cell)} ({self.zone}) | "
            f"fertilizantes hoje: {self.fertilizers_left} de {settings.FERTILIZERS_PER_DAY}",
            "",
            "Inventario: " + (self._inventory_text() or "vazio"),
            "",
            "Plantacao: " + (f"{len(self.plots)} celula(s)" if self.plots else "nada plantado"),
        ]
        linhas += [f"  {self._plot_text(plot)}" for plot in self.plots]

        loja = self.market
        linhas += ["", f"Loja (caixa {loja['budget_left']}/{loja['daily_budget']}):"]
        for crop, dados in loja["sell"].items():
            aviso = " [saturado]" if dados["saturated"] else ""
            linhas.append(f"  vender {CROPS[crop].label}: {dados['price']}{aviso}")
        for item, dados in loja["buy"].items():
            linhas.append("  " + self._buy_text(item, dados))

        linhas += ["", "Acoes possiveis aqui: " + (", ".join(self.actions) or "nenhuma")]
        return "\n".join(linhas)

    def _inventory_text(self) -> str:
        partes = []
        for dados in self.inventory.values():
            if not dados["count"]:
                continue
            teto = f"/{dados['limit']}" if dados["limit"] else ""
            partes.append(f"{dados['label']} x{dados['count']}{teto}")
        return ", ".join(partes)

    @staticmethod
    def _plot_text(plot: dict[str, Any]) -> str:
        if plot["stage"] == "estragada":
            detalhe = "estragada, precisa ser removida"
        elif plot["stage"] == "pronta":
            detalhe = f"pronta, estraga em {plot['days_to_spoil']} dia(s)"
        else:
            detalhe = f"{plot['stage']}, pronta em {plot['days_to_grow']} dia(s)"
        marca = " (fertilizada)" if plot["fertilized"] else ""
        return f"{tuple(plot['cell'])} {CROPS[plot['crop']].label}: {detalhe}{marca}"

    @staticmethod
    def _buy_text(item: str, dados: dict[str, Any]) -> str:
        nome = ITEM_LABELS.get(item, item)
        if dados["stock"] == 0:
            return f"comprar {nome}: esgotado hoje"
        promo = f" [promocao, era {dados['full_price']}]" if dados["promo"] else ""
        return f"comprar {nome}: {dados['price']} (estoque {dados['stock']}){promo}"
