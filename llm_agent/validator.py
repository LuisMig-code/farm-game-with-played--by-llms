"""Validacao estatica do plano, antes de executar.

Sequencial, nao linha a linha: uma compra no comeco do plano conta para o
plantio mais adiante, e a zona de cada acao depende dos IR anteriores. Estamina e
moedas ficam de fora de proposito -- so a execucao sabe quanto custou cada rota e
por quanto cada unidade foi vendida. O modelo aprende esses limites pelo
relatorio do dia seguinte.
"""

from dataclasses import dataclass, field

from farm import seasons, settings as game_settings
from farm.crops import CROPS, FERTILIZER, ITEM_LIMITS, seed_key
from llm_agent.grammar import (BED, FIELD_VERBS, PLOT_ZONES, SHOP_VERBS, STORE,
                               Action, GrammarError, parse_line, plot_zone_of)

GRAMMAR = "ERRO_GRAMATICA"
ZONE = "ERRO_ZONA"
SEASON = "ERRO_ESTACAO"
INVENTORY_LIMIT = "ERRO_LIMITE_INVENTARIO"
RESOURCE = "ERRO_RECURSO"
DAILY_LIMIT = "ERRO_LIMITE_DIARIO"


@dataclass
class PlanError:
    index: int
    line: str
    code: str
    message: str

    def as_dict(self) -> dict:
        return {"indice": self.index, "linha": self.line, "codigo": self.code,
                "mensagem": self.message}


@dataclass
class Validation:
    actions: list[Action | None]
    errors: list[PlanError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def valid_prefix(self) -> list[Action]:
        """As acoes antes do primeiro erro -- o que roda quando a correcao falha."""
        corte = self.errors[0].index if self.errors else len(self.actions)
        return [a for a in self.actions[:corte] if a is not None]


class _Sim:
    """Estado simulado: so o que da para saber sem executar."""

    def __init__(self, game):
        day, campo, inv = game.day, game.field, game.inventory
        self.zone = BED
        self.season = seasons.season_at(day)
        self.seeds = {k: inv.count(seed_key(k)) for k in CROPS}
        self.veggies = {k: inv.count(k) for k in CROPS}
        self.fertilizer = inv.count(FERTILIZER)
        self.fert_left = max(0, game_settings.FERTILIZERS_PER_DAY - game.fertilizers_today)

        self.empty = {z: 0 for z in PLOT_ZONES}
        self.spoiled = {z: 0 for z in PLOT_ZONES}
        self.grown = {z: {k: 0 for k in CROPS} for z in PLOT_ZONES}
        self.growing = {z: {k: 0 for k in CROPS} for z in PLOT_ZONES}   # fertilizaveis
        for cell in game.zones.plantable:
            zona = plot_zone_of(cell)
            plot = campo.at(cell)
            if plot is None:
                self.empty[zona] += 1
            elif campo.is_spoiled(cell, day):
                self.spoiled[zona] += 1
            elif campo.is_grown(cell, day):
                self.grown[zona][plot.crop] += 1
            elif not plot.fertilized:
                self.growing[zona][plot.crop] += 1


def validate(game, lines: list) -> Validation:
    sim = _Sim(game)
    actions: list[Action | None] = []
    errors: list[PlanError] = []

    if not isinstance(lines, list):
        return Validation([], [PlanError(0, str(lines)[:200], GRAMMAR,
                                         "o plano precisa ser uma lista de strings")])

    for i, linha in enumerate(lines):
        try:
            acao = parse_line(linha)
        except GrammarError as erro:
            actions.append(None)
            errors.append(PlanError(i, str(linha), GRAMMAR, str(erro)))
            continue
        actions.append(acao)
        erro = _check(sim, acao)
        if erro:
            code, msg = erro
            errors.append(PlanError(i, acao.raw, code, msg))
    return Validation(actions, errors)


def _check(sim: _Sim, a: Action) -> tuple[str, str] | None:
    """Confere e aplica a acao no estado simulado. Devolve (codigo, mensagem)."""
    if a.verb == "IR":
        sim.zone = a.zone
        return None

    if a.verb in FIELD_VERBS and sim.zone not in PLOT_ZONES:
        return ZONE, f"{a.verb} exige estar num canteiro, e o plano esta em '{sim.zone}' aqui"
    if a.verb in SHOP_VERBS and sim.zone != STORE:
        return ZONE, f"{a.verb} exige estar na loja, e o plano esta em '{sim.zone}' aqui"

    z = sim.zone
    if a.verb == "PLANTAR":
        if not sim.season.can_plant:
            return SEASON, f"nao da para plantar no(a) {sim.season.label.lower()}"
        if a.amount is not None:
            if sim.seeds[a.crop] < a.amount:
                return RESOURCE, (f"pede {a.amount} sementes de {a.crop}, "
                                  f"o plano tera {sim.seeds[a.crop]} nesse ponto")
            if sim.empty[z] < a.amount:
                return RESOURCE, (f"pede {a.amount} celulas vazias em {z}, "
                                  f"havera {sim.empty[z]} nesse ponto")
        n = a.cap(min(sim.seeds[a.crop], sim.empty[z]))
        sim.seeds[a.crop] -= n
        sim.empty[z] -= n
        return None

    if a.verb == "COLHER":
        culturas = [a.crop] if a.crop else list(CROPS)
        total = sum(sim.grown[z][c] for c in culturas)
        restante = a.cap(total)
        for c in culturas:
            n = min(restante, sim.grown[z][c])
            sim.grown[z][c] -= n
            sim.veggies[c] += n
            sim.empty[z] += n
            restante -= n
        return None

    if a.verb == "FERTILIZAR":
        if not sim.season.fertilizer_works:
            return SEASON, f"fertilizante nao funciona no(a) {sim.season.label.lower()}"
        if sim.fert_left == 0:
            return DAILY_LIMIT, (f"o limite de {game_settings.FERTILIZERS_PER_DAY} "
                                 "fertilizantes por dia ja foi usado nesse ponto do plano")
        culturas = [a.crop] if a.crop else list(CROPS)
        elegiveis = sum(sim.growing[z][c] for c in culturas)
        n = min(a.cap(elegiveis), sim.fertilizer, sim.fert_left)
        restante = n
        for c in culturas:
            k = min(restante, sim.growing[z][c])
            sim.growing[z][c] -= k
            restante -= k
        sim.fertilizer -= n
        sim.fert_left -= n
        return None

    if a.verb == "LIMPAR":
        n = a.cap(sim.spoiled[z])
        sim.spoiled[z] -= n
        sim.empty[z] += n
        return None

    if a.verb == "COMPRAR":
        if a.item == FERTILIZER:
            teto, atual = ITEM_LIMITS[FERTILIZER], sim.fertilizer
        else:
            crop = a.item.split(" ", 1)[1]
            teto, atual = ITEM_LIMITS[a.item], sim.seeds[crop]
        if atual + a.amount > teto:
            return INVENTORY_LIMIT, (f"comprar {a.amount} {a.item_id} deixaria {atual + a.amount}; "
                                     f"o teto e {teto} (o plano tera {atual} nesse ponto)")
        if a.item == FERTILIZER:
            sim.fertilizer += a.amount
        else:
            sim.seeds[a.item.split(" ", 1)[1]] += a.amount
        return None

    # VENDER
    if a.amount is not None and sim.veggies[a.crop] < a.amount:
        return RESOURCE, (f"pede para vender {a.amount} {a.crop}, "
                          f"o plano tera {sim.veggies[a.crop]} nesse ponto")
    sim.veggies[a.crop] -= a.cap(sim.veggies[a.crop])
    return None
