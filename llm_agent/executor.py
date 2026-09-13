"""O interpretador: expande o plano em acoes do jogo e classifica cada comando.

O LLM decide, o interpretador conta:

- **Ordem literal.** Os comandos rodam de cima para baixo; a sequencia de IR e a rota.
- **Guloso dentro do canteiro.** Vai a celula-alvo mais proxima (empate: menor
  coluna, depois menor linha), age e repete. So celulas-alvo entram na rota.
- **Comando invalido nao para o plano.** E descartado com o codigo do erro, e
  os seguintes rodam. Nunca se pede reenvio: o erro volta no feedback de amanha.
- **Rede de seguranca.** Antes de cada trecho de caminhada e de cada acao de
  campo confere se, depois dela, ainda da para voltar a cama chegando com
  `STAMINA_RESERVE`. O jogo declara derrota com estamina 0 mesmo em cima da
  cama. Se nao da, o comando vira TRUNCADO_STAMINA, o resto do plano tambem, e
  o jogador volta e dorme.
- **Tudo pela Session**, ou seja, pelos menus do jogo: nada de trapaca.

Codigos: OK, PARCIAL, ERRO_GRAMATICA, ERRO_CONTEXTO, ERRO_RECURSO, TRUNCADO_STAMINA.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field

from farm import seasons, settings as game_settings
from farm.crops import COIN, FERTILIZER, seed_key
from farm.game import BUY_MENU, SELL_MENU
from llm_agent import settings
from llm_agent.grammar import (FIELD_VERBS, PLOT_ZONES, SHOP_VERBS, STORE, ZONE_CELLS,
                               Command, GrammarError, parse, plot_zone_of)
from scripting import HOUSE, Blocked, Session, shortest_path
from scripting.route import STEPS

logger = logging.getLogger(__name__)

Cell = tuple[int, int]

OK, PARTIAL = "OK", "PARCIAL"
GRAMMAR, CONTEXT, RESOURCE, TRUNCATED = ("ERRO_GRAMATICA", "ERRO_CONTEXTO", "ERRO_RECURSO",
                                         "TRUNCADO_STAMINA")
CODES = (OK, PARTIAL, GRAMMAR, CONTEXT, RESOURCE, TRUNCATED)

COST = {"PLANTAR": game_settings.STAMINA_PLANT, "COLHER": game_settings.STAMINA_HARVEST,
        "LIMPAR": game_settings.STAMINA_CLEAR, "FERTILIZAR": game_settings.STAMINA_FERTILIZE}
# Nome de cada fatia da estamina, na ordem em que aparece no feedback.
STAMINA_PARTS = ("andando", "plantando", "colhendo", "fertilizando", "limpando")
PART_OF = {"PLANTAR": "plantando", "COLHER": "colhendo", "FERTILIZAR": "fertilizando",
           "LIMPAR": "limpando"}


@dataclass
class CommandResult:
    index: int
    raw: str
    code: str
    detail: str = ""
    verb: str | None = None
    crop: str | None = None
    requested: int | None = None
    effective: int | None = None
    steps: int = 0
    coins: int = 0                      # ganhas (+) ou gastas (-)
    below_base: int = 0                 # unidades vendidas abaixo do preco base
    stamina_before: int = 0
    stamina_after: int = 0
    stamina_needed: int | None = None   # so no TRUNCADO_STAMINA

    def as_dict(self) -> dict:
        d = {"ordem": self.index, "comando": self.raw, "codigo": self.code, "detalhe": self.detail,
             "estamina_gasta": self.stamina_before - self.stamina_after}
        for chave, valor in (("pedido", self.requested), ("efetivo", self.effective),
                             ("estamina_necessaria", self.stamina_needed)):
            if valor is not None:
                d[chave] = valor
        if self.steps:
            d["passos"] = self.steps
        if self.coins:
            d["moedas"] = self.coins
        return d


@dataclass
class DayExecution:
    results: list[CommandResult] = field(default_factory=list)
    truncated: bool = False
    truncated_at: str | None = None
    stamina_start: int = 0
    stamina_at_bed: int = 0
    steps_home: int = 0
    stamina_parts: Counter = field(default_factory=Counter)
    plot_zones_visited: set = field(default_factory=set)

    def count(self, code: str) -> int:
        return sum(r.code == code for r in self.results)

    @property
    def completed(self) -> bool:
        return bool(self.results) and all(r.code == OK for r in self.results)


class _OutOfStamina(Exception):
    """Interno: a rede de seguranca barrou; o resto do plano nao roda."""


class Executor:
    def __init__(self, session: Session):
        self.s = session
        self.walkable = session.game.zones.walkable
        self._home = self._distances_from(HOUSE)
        self.zone = "cama"
        self._day: DayExecution | None = None

    # ---------------------------------------------------------- rede de seguranca

    def _distances_from(self, origem: Cell) -> dict[Cell, int]:
        dist, fila = {origem: 0}, [origem]
        for cell in fila:
            for dc, dr in STEPS:
                nxt = (cell[0] + dc, cell[1] + dr)
                if nxt in self.walkable and nxt not in dist:
                    dist[nxt] = dist[cell] + 1
                    fila.append(nxt)
        return dist

    def home_distance(self, cell: Cell) -> int:
        return self._home[cell]

    def needed(self, path_len: int, cost: int, end: Cell) -> int:
        """Estamina para andar, agir e ainda chegar em casa com a reserva."""
        return path_len + cost + self.home_distance(end) + settings.STAMINA_RESERVE

    def affordable(self, path_len: int, cost: int, end: Cell) -> bool:
        return self.s.stamina >= self.needed(path_len, cost, end)

    # -------------------------------------------------------------------- plano

    def run(self, plan) -> DayExecution:
        dia = self._day = DayExecution(stamina_start=self.s.stamina)
        self.zone = "cama" if self.s.cell == HOUSE else self.zone

        if not isinstance(plan, list):
            dia.results.append(CommandResult(1, str(plan)[:200], GRAMMAR,
                                             "o plano precisa ser uma lista de comandos"))
            return dia

        for i, linha in enumerate(plan, 1):
            antes = self.s.stamina
            if dia.truncated:
                dia.results.append(CommandResult(i, _raw(linha), TRUNCATED,
                                                 "descartado: o plano já tinha sido cortado",
                                                 stamina_before=antes, stamina_after=antes))
                continue
            try:
                cmd = parse(linha)
            except GrammarError as erro:
                dia.results.append(CommandResult(i, _raw(linha), GRAMMAR, str(erro),
                                                 stamina_before=antes, stamina_after=antes))
                continue

            r = CommandResult(i, cmd.raw, OK, verb=cmd.verb, crop=cmd.crop, stamina_before=antes)
            try:
                if cmd.verb == "IR":
                    self._go(cmd, r)
                elif cmd.verb in FIELD_VERBS:
                    self._field(cmd, r)
                else:
                    self._shop(cmd, r)
            except _OutOfStamina:
                dia.truncated, dia.truncated_at = True, self.zone
                r.code = TRUNCATED
                logger.info("rede de seguranca: '%s' cortado (%s)", cmd.raw, r.detail)
            r.stamina_after = self.s.stamina
            dia.results.append(r)
        return dia

    def go_home(self, dia: DayExecution) -> None:
        """Volta para a cama. Pela invariante da rede, sempre cabe na estamina."""
        dia.steps_home = self.home_distance(self.s.cell)
        self._walk(HOUSE, guarded=False)
        self.zone = "cama"
        dia.stamina_at_bed = self.s.stamina

    # ------------------------------------------------------------------ IR

    def _go(self, c: Command, r: CommandResult) -> None:
        destino = ZONE_CELLS[c.zone]
        caminho = shortest_path(self.s.cell, destino, self.walkable) or []
        r.requested = len(caminho)
        # A ida inteira e conferida antes de sair: andar meio caminho so para
        # voltar desperdicaria estamina. A guarda por passo continua abaixo.
        if not self.affordable(len(caminho), 0, destino):
            r.effective = 0
            r.stamina_needed = self.needed(len(caminho), 0, destino)
            r.detail = (f"ir até {c.zone} custa {len(caminho)} passos e voltar para a cama "
                        f"mais {self.home_distance(destino)} (+{settings.STAMINA_RESERVE}) = "
                        f"{r.stamina_needed}; havia {self.s.stamina}")
            raise _OutOfStamina()
        r.effective = r.steps = self._walk(destino, guarded=True, result=r)
        self.zone = c.zone
        if c.zone in PLOT_ZONES:
            self._day.plot_zones_visited.add(c.zone)
        r.detail = f"{r.steps} passos"

    def _walk(self, destino: Cell, guarded: bool, result: CommandResult | None = None) -> int:
        caminho = shortest_path(self.s.cell, destino, self.walkable) or []
        andados = 0
        for cell in caminho:
            if guarded and not self.affordable(1, 0, cell):
                if result is not None:
                    result.steps = result.effective = andados
                    result.stamina_needed = self.needed(len(caminho) - andados, 0, destino)
                    result.detail = (f"andou {andados} de {len(caminho)} passos; faltou stamina "
                                     "para seguir e ainda voltar")
                raise _OutOfStamina()
            atual = self.s.cell
            self.s.step((cell[0] - atual[0], cell[1] - atual[1]))
            andados += 1
            self._day.stamina_parts["andando"] += game_settings.STAMINA_WALK
        return andados

    # ---------------------------------------------------------------- campo

    def _field(self, c: Command, r: CommandResult) -> None:
        if self.zone not in PLOT_ZONES:
            r.code = CONTEXT
            r.detail = f"{c.verb} exige estar num canteiro; você estava em {self.zone}"
            return
        estacao = seasons.season_at(self.s.day)
        if c.verb == "PLANTAR" and not estacao.can_plant:
            r.code, r.detail = CONTEXT, f"não se planta no {estacao.label.lower()}"
            return
        if c.verb == "FERTILIZAR" and not estacao.fertilizer_works:
            r.code, r.detail = CONTEXT, f"fertilizante não funciona no {estacao.label.lower()}"
            return

        alvos = self._targets(c)
        cabe, falta = self._available(c, len(alvos))
        if cabe == 0:
            r.code, r.requested, r.effective, r.detail = RESOURCE, c.limit, 0, falta
            return

        # PLANTAR TUDO e COLHER/LIMPAR/FERTILIZAR sem LIMITE pedem o que da.
        pedido = c.cap(len(alvos) if c.verb == "FERTILIZAR" else cabe)
        r.requested = pedido
        feitos, restantes, corte = 0, set(alvos), None
        while feitos < pedido:
            cabe, corte = self._available(c, len(restantes))
            if cabe == 0:
                break
            alvo = self._nearest(restantes)
            caminho = shortest_path(self.s.cell, alvo, self.walkable) or []
            if not self.affordable(len(caminho), COST[c.verb], alvo):
                r.effective = feitos
                r.stamina_needed = self.needed(len(caminho), COST[c.verb], alvo)
                r.detail = (f"{_verbo_passado(c.verb)} {feitos} de {pedido}; a próxima exigia "
                            f"{r.stamina_needed} de stamina (andar {len(caminho)} + "
                            f"{c.verb.lower()} {COST[c.verb]} + voltar "
                            f"{self.home_distance(alvo)} + reserva {settings.STAMINA_RESERVE}), "
                            f"havia {self.s.stamina}")
                raise _OutOfStamina()
            r.steps += self._walk(alvo, guarded=False)
            try:
                self._act(c)
            except Blocked as erro:
                corte = f"o jogo recusou: {erro}"
                break
            self._day.stamina_parts[PART_OF[c.verb]] += COST[c.verb]
            restantes.discard(alvo)
            feitos += 1

        r.effective = feitos
        r.detail = self._field_detail(c, feitos, pedido, len(alvos))
        if feitos < pedido and corte:
            r.code = PARTIAL
            r.detail = f"{_verbo_passado(c.verb)} {feitos} de {pedido}: {corte}"

    @staticmethod
    def _field_detail(c: Command, feitos: int, pedido: int, alvos: int) -> str:
        if c.verb == "PLANTAR":
            return f"{feitos} de {_n(alvos, 'célula livre', 'células livres')}"
        if c.verb == "FERTILIZAR":
            return _n(feitos, "planta", "plantas")
        texto = _n(feitos, "célula", "células")
        sobra = alvos - feitos
        if c.verb == "COLHER" and sobra:
            texto += "; " + (_n(sobra, "pronta ficou", "prontas ficaram"))
        return texto

    def _targets(self, c: Command) -> list[Cell]:
        game, day, campo = self.s.game, self.s.day, self.s.game.field
        celulas = [x for x in game.zones.plantable if plot_zone_of(x) == self.zone]
        if c.verb == "PLANTAR":
            return [x for x in celulas if campo.at(x) is None]
        alvos = []
        for x in celulas:
            plot = campo.at(x)
            if plot is None:
                continue
            podre, pronta = campo.is_spoiled(x, day), campo.is_grown(x, day)
            if c.verb == "LIMPAR" and podre:
                alvos.append(x)
            elif c.verb == "COLHER" and pronta and not podre:
                alvos.append(x)
            elif c.verb == "FERTILIZAR" and not pronta and not podre and not plot.fertilized:
                alvos.append(x)
        return alvos

    def _available(self, c: Command, alvos: int) -> tuple[int, str | None]:
        """Quantas unidades cabem agora e, se nao couber tudo, o motivo."""
        game = self.s.game
        if c.verb == "PLANTAR":
            sementes = game.inventory.count(seed_key(c.crop))
            if sementes == 0:
                return 0, f"0 sementes de {c.crop}"
            if alvos == 0:
                return 0, f"nenhuma célula livre em {self.zone}"
            if sementes < alvos:
                return sementes, "acabaram as sementes"
            return alvos, None
        if c.verb == "FERTILIZAR":
            estoque = game.inventory.count(FERTILIZER)
            diario = max(0, game_settings.FERTILIZERS_PER_DAY - game.fertilizers_today)
            if alvos == 0:
                return 0, f"nenhuma planta crescendo sem fertilizante em {self.zone}"
            if diario == 0:
                return 0, f"limite de {game_settings.FERTILIZERS_PER_DAY} fertilizantes por dia já usado"
            if estoque == 0:
                return 0, "0 fertilizantes"
            n = min(alvos, estoque, diario)
            if n < alvos:
                return n, (f"limite de {game_settings.FERTILIZERS_PER_DAY} por dia"
                           if diario <= estoque else "acabou o fertilizante")
            return n, None
        if alvos == 0:
            return 0, (f"nada pronto para colher em {self.zone}" if c.verb == "COLHER"
                       else f"nenhuma planta podre em {self.zone}")
        return alvos, None

    def _nearest(self, cells) -> Cell:
        dist = self._distances_from(self.s.cell)
        return min(cells, key=lambda x: (dist[x], x[0], x[1]))

    def _act(self, c: Command) -> None:
        {"PLANTAR": lambda: self.s.plant(c.crop), "COLHER": self.s.harvest,
         "LIMPAR": self.s.clear, "FERTILIZAR": self.s.fertilize}[c.verb]()

    # ------------------------------------------------------------------ loja

    def _shop(self, c: Command, r: CommandResult) -> None:
        if self.zone != STORE:
            r.code = CONTEXT
            r.detail = f"{c.verb} exige estar na loja; voce estava em {self.zone}"
            return
        (self._buy if c.verb == "COMPRAR" else self._sell)(c, r)

    def _buy(self, c: Command, r: CommandResult) -> None:
        game, nome = self.s.game, ("fertilizantes" if c.item == FERTILIZER
                                   else f"sementes de {c.crop}")
        r.requested, feitos = c.amount, 0
        motivo = self._buy_blocker(c)
        if motivo is None:
            try:
                # Uma visita ao menu para o comando inteiro, nao uma por unidade.
                with self.s.trading(BUY_MENU) as escolher:
                    while feitos < c.amount and (motivo := self._buy_blocker(c)) is None:
                        preco = game.market.buy_price(c.item)
                        escolher(c.item)
                        r.coins -= preco
                        feitos += 1
            except Blocked as erro:
                motivo = f"o jogo recusou: {erro}"
        r.effective = feitos
        if feitos == c.amount:
            r.detail = f"{feitos} {nome} -> {-r.coins} moedas"
        elif feitos == 0:
            r.code, r.detail = RESOURCE, f"não comprou nenhuma: {motivo}"
        else:
            r.code, r.detail = PARTIAL, f"comprou {feitos} de {c.amount} ({-r.coins} moedas): {motivo}"

    def _buy_blocker(self, c: Command) -> str | None:
        """Por que a proxima unidade nao pode ser comprada, ou None se pode."""
        loja, inv = self.s.game.market, self.s.game.inventory
        preco = loja.buy_price(c.item)
        if loja.stock_left(c.item) == 0:
            return "o estoque da loja acabou"
        if inv.is_full(c.item):
            return f"o limite de {inv.limit_for(c.item)} no inventário"
        if inv.count(COIN) < preco:
            return f"{inv.count(COIN)} moedas não pagam mais uma a {preco}"
        return None

    def _sell(self, c: Command, r: CommandResult) -> None:
        game = self.s.game
        tem = game.inventory.count(c.crop)
        r.requested = tem if c.all_ else c.amount
        if tem == 0:
            r.code, r.effective, r.detail = RESOURCE, 0, f"0 unidades de {c.crop} na mochila"
            return
        feitos = 0
        motivo = self._sell_blocker(c, tem)
        if motivo is None:
            try:
                # Uma visita ao menu para o comando inteiro, nao uma por unidade.
                with self.s.trading(SELL_MENU) as escolher:
                    while feitos < r.requested and (motivo := self._sell_blocker(c, tem)) is None:
                        loja, dia = game.market, self.s.day
                        preco, base = loja.sell_price(c.crop, dia), loja.base_price(c.crop, dia)
                        escolher(c.crop)
                        r.coins += preco
                        r.below_base += preco < base
                        feitos += 1
            except Blocked as erro:
                motivo = f"o jogo recusou: {erro}"
        r.effective = feitos
        if feitos == r.requested:
            r.detail = f"{feitos} un -> {r.coins} moedas"
        elif feitos == 0:
            r.code, r.detail = RESOURCE, f"não vendeu nenhuma: {motivo}"
        else:
            r.code, r.detail = PARTIAL, f"vendeu {feitos} de {r.requested} ({r.coins} moedas): {motivo}"

    def _sell_blocker(self, c: Command, tinha: int) -> str | None:
        """Por que a proxima unidade nao pode ser vendida, ou None se pode."""
        game, dia = self.s.game, self.s.day
        if game.inventory.count(c.crop) == 0:
            return f"só havia {tinha} na mochila"
        if not game.market.can_sell(c.crop, dia):
            return f"o caixa da loja acabou ({game.market.budget_left(dia)} moedas)"
        return None


def _n(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _raw(linha) -> str:
    return " ".join(linha.split()) if isinstance(linha, str) else str(linha)[:200]


def _verbo_passado(verbo: str) -> str:
    return {"PLANTAR": "plantou", "COLHER": "colheu", "FERTILIZAR": "fertilizou",
            "LIMPAR": "limpou"}[verbo]
