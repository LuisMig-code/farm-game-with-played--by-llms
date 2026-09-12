"""Executa o plano no jogo de verdade, com a rede de seguranca de estamina.

Regras do executor:

- **Ordem literal.** Nada e reordenado: a sequencia de IR e a rota.
- **Guloso dentro do canteiro.** Vai a celula-alvo mais proxima (empate: menor
  coluna, depois menor linha), age, repete. So celulas-alvo entram na rota.
- **Rede de seguranca.** Antes de cada trecho de caminhada e de cada acao de
  campo confere se, depois dela, ainda da para voltar a cama chegando com
  `STAMINA_RESERVE`. O jogo declara derrota com estamina 0 mesmo em cima da
  cama, entao chegar com zero nao serve. Se nao da, a acao vira TRUNCADO /
  SEM_ESTAMINA, o resto do plano NAO_EXECUTADO, e o jogador volta e dorme.
- **Tudo pela Session**, ou seja, pelos menus do jogo: nada de trapaca.
"""

import logging
from dataclasses import dataclass, field

from farm import seasons, settings as game_settings
from farm.crops import COIN, CROPS, FERTILIZER, seed_key
from llm_agent import settings
from llm_agent.grammar import (FIELD_VERBS, PLOT_ZONES, SHOP_VERBS, STORE,
                               ZONE_CELLS, Action, plot_zone_of)
from scripting import HOUSE, Blocked, Session, shortest_path
from scripting.route import STEPS

logger = logging.getLogger(__name__)

Cell = tuple[int, int]

DONE, PARTIAL, SKIPPED = "EXECUTADO", "TRUNCADO", "NAO_EXECUTADO"

NO_STAMINA = "SEM_ESTAMINA"
NO_STOCK = "SEM_ESTOQUE"
NO_CASH = "SEM_CAIXA_LOJA"
INVENTORY_LIMIT = "LIMITE_INVENTARIO"
NO_FREE_CELL = "SEM_CELULA_LIVRE"
NO_TARGET = "SEM_ALVO"
DAILY_FERT_LIMIT = "LIMITE_FERTILIZANTE_DIARIO"
NO_COINS = "SEM_MOEDAS"
NO_RESOURCE = "SEM_RECURSO"
WRONG_ZONE = "ZONA_ERRADA"
SEASON = "ESTACAO"
GAME_REFUSED = "RECUSADO_PELO_JOGO"

COST = {"PLANTAR": game_settings.STAMINA_PLANT, "COLHER": game_settings.STAMINA_HARVEST,
        "LIMPAR": game_settings.STAMINA_CLEAR, "FERTILIZAR": game_settings.STAMINA_FERTILIZE}


@dataclass
class ActionResult:
    action: str
    status: str
    requested: int | None = None
    effective: int | None = None
    reason: str | None = None
    detail: str | None = None
    stamina_before: int = 0
    stamina_after: int = 0
    steps: int = 0
    coins: int = 0                                   # ganhas (+) ou gastas (-)
    unit_prices: list[int] = field(default_factory=list)
    below_base: int = 0                               # unidades vendidas abaixo do base
    stamina_needed: int | None = None                 # quando faltou estamina

    def as_dict(self) -> dict:
        d = {"acao": self.action, "status": self.status,
             "custo_estamina": self.stamina_before - self.stamina_after}
        if self.requested is not None:
            d["pedido"] = self.requested
        if self.effective is not None:
            d["efetivo"] = self.effective
        if self.reason:
            d["motivo"] = self.reason
        if self.detail:
            d["detalhe"] = self.detail
        if self.steps:
            d["passos"] = self.steps
        if self.coins:
            d["moedas"] = self.coins
        if self.unit_prices:
            d["precos_unitarios"] = self.unit_prices
        if self.stamina_needed is not None:
            d["estamina_necessaria"] = self.stamina_needed
            d["estamina_disponivel"] = self.stamina_after
        return d


@dataclass
class DayExecution:
    results: list[ActionResult] = field(default_factory=list)
    forced_return: bool = False
    forced_return_at: str | None = None
    forced_return_cell: Cell | None = None
    stamina_start: int = 0
    stamina_at_bed: int = 0
    steps_home: int = 0

    @property
    def completed(self) -> bool:
        return all(r.status == DONE for r in self.results) and not self.forced_return


class _OutOfStamina(Exception):
    """Interno: a rede de seguranca barrou; o resto do plano nao roda."""


class Executor:
    def __init__(self, session: Session):
        self.s = session
        self.walkable = session.game.zones.walkable
        self._home = self._distances_from(HOUSE)
        self.zone = "cama"

    # ---------------------------------------------------------- rede de seguranca

    def _distances_from(self, origem: Cell) -> dict[Cell, int]:
        """BFS uma vez so: distancia de toda celula andavel ate a origem."""
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

    def run(self, actions: list[Action]) -> DayExecution:
        dia = DayExecution(stamina_start=self.s.stamina)
        self.zone = "cama" if self.s.cell == HOUSE else self.zone
        parado = False
        for acao in actions:
            if parado:
                dia.results.append(ActionResult(acao.raw, SKIPPED, reason=NO_STAMINA,
                                                stamina_before=self.s.stamina,
                                                stamina_after=self.s.stamina))
                continue
            try:
                resultado = self._run_one(acao)
            except _OutOfStamina as barrou:
                resultado = barrou.args[0]
                parado = True
                dia.forced_return = True
                dia.forced_return_at = self.zone
                dia.forced_return_cell = self.s.cell
                logger.info("rede de seguranca: '%s' parou (%s)", acao.raw, resultado.detail)
            dia.results.append(resultado)
        return dia

    def go_home(self, dia: DayExecution) -> None:
        """Volta para a cama. Pela invariante da rede, sempre cabe na estamina."""
        dia.steps_home = self.home_distance(self.s.cell)
        self._walk(HOUSE, guarded=False)
        self.zone = "cama"
        dia.stamina_at_bed = self.s.stamina

    # ------------------------------------------------------------------ acoes

    def _run_one(self, a: Action) -> ActionResult:
        r = ActionResult(a.raw, DONE, stamina_before=self.s.stamina)
        try:
            if a.verb == "IR":
                self._go(a, r)
            elif a.verb in FIELD_VERBS:
                self._field(a, r)
            elif a.verb in SHOP_VERBS:
                self._shop(a, r)
        except _OutOfStamina:
            r.stamina_after = self.s.stamina
            raise _OutOfStamina(r)
        r.stamina_after = self.s.stamina
        return r

    def _go(self, a: Action, r: ActionResult) -> None:
        destino = ZONE_CELLS[a.zone]
        caminho = shortest_path(self.s.cell, destino, self.walkable) or []
        r.requested = len(caminho)
        # Confere a ida inteira antes de sair: andar meio caminho so para voltar
        # desperdicaria estamina. A guarda por passo continua valendo abaixo.
        if not self.affordable(len(caminho), 0, destino):
            r.status, r.reason, r.effective = SKIPPED, NO_STAMINA, 0
            r.stamina_needed = self.needed(len(caminho), 0, destino)
            r.detail = (f"ir ate {a.zone} custa {len(caminho)} passos e voltar para a cama "
                        f"mais {self.home_distance(destino)} (+{settings.STAMINA_RESERVE} de "
                        f"reserva) = {r.stamina_needed}; havia {self.s.stamina}")
            raise _OutOfStamina()
        andados = self._walk(destino, guarded=True, result=r)
        r.effective = r.steps = andados
        self.zone = a.zone

    def _walk(self, destino: Cell, guarded: bool, result: ActionResult | None = None) -> int:
        """Anda passo a passo. Com guarda, confere a rede antes de cada passo."""
        caminho = shortest_path(self.s.cell, destino, self.walkable) or []
        andados = 0
        for cell in caminho:
            if guarded and not self.affordable(1, 0, cell):
                if result is not None:
                    result.status = PARTIAL if andados else SKIPPED
                    result.reason = NO_STAMINA
                    result.stamina_needed = self.needed(len(caminho) - andados, 0, destino)
                    result.steps = result.effective = andados
                    result.detail = (f"andou {andados} de {len(caminho)} passos; faltaram "
                                     f"{len(caminho) - andados} passos e a volta para a cama")
                raise _OutOfStamina()
            atual = self.s.cell
            self.s.step((cell[0] - atual[0], cell[1] - atual[1]))
            andados += 1
        return andados

    # ----------------------------------------------------------------- campo

    def _field(self, a: Action, r: ActionResult) -> None:
        if self.zone not in PLOT_ZONES:
            r.status, r.reason = SKIPPED, WRONG_ZONE
            r.detail = f"{a.verb} exige estar num canteiro; o jogador estava em '{self.zone}'"
            return

        game, day = self.s.game, self.s.day
        estacao = seasons.season_at(day)
        if a.verb == "PLANTAR" and not estacao.can_plant:
            r.status, r.reason, r.detail = SKIPPED, SEASON, f"nao se planta no {estacao.label}"
            return
        if a.verb == "FERTILIZAR" and not estacao.fertilizer_works:
            r.status, r.reason = SKIPPED, SEASON
            r.detail = f"fertilizante nao funciona no {estacao.label}"
            return

        alvos = self._targets(a)
        if a.verb == "FERTILIZAR":
            # O pedido e o que esta elegivel; se o limite diario ou o estoque de
            # fertilizante cortarem, o relatorio mostra o truncamento com o motivo.
            pedido, motivo_zero = a.cap(len(alvos)), NO_TARGET
        else:
            # PLANTAR TUDO ja nasce limitado pelo menor entre celulas e sementes.
            disponivel, motivo_zero = self._available(a, len(alvos))
            pedido = a.cap(disponivel)
        r.requested = pedido
        if pedido == 0:
            r.status, r.effective = SKIPPED, 0
            r.reason = motivo_zero or NO_TARGET
            return

        feitos, restantes = 0, set(alvos)
        while feitos < pedido:
            cabe, motivo = self._available(a, len(restantes))
            if cabe == 0:
                r.reason = motivo
                break
            alvo = self._nearest(restantes)
            caminho = shortest_path(self.s.cell, alvo, self.walkable) or []
            if not self.affordable(len(caminho), COST[a.verb], alvo):
                r.effective = feitos
                r.status = PARTIAL if feitos else SKIPPED
                r.reason = NO_STAMINA
                r.stamina_needed = self.needed(len(caminho), COST[a.verb], alvo)
                r.detail = (f"fez {feitos} de {pedido}; a proxima ({alvo}) exigia "
                            f"{r.stamina_needed} de estamina (andar {len(caminho)} + acao "
                            f"{COST[a.verb]} + voltar {self.home_distance(alvo)} + reserva "
                            f"{settings.STAMINA_RESERVE}) e havia {self.s.stamina}")
                raise _OutOfStamina()
            r.steps += self._walk(alvo, guarded=False)
            try:
                self._act(a)
            except Blocked as erro:
                r.reason, r.detail = GAME_REFUSED, str(erro)
                break
            restantes.discard(alvo)
            feitos += 1

        r.effective = feitos
        if feitos < pedido:
            r.status = PARTIAL if feitos else SKIPPED

    def _targets(self, a: Action) -> list[Cell]:
        game, day, campo = self.s.game, self.s.day, self.s.game.field
        celulas = [c for c in game.zones.plantable if plot_zone_of(c) == self.zone]
        if a.verb == "PLANTAR":
            return [c for c in celulas if campo.at(c) is None]
        alvos = []
        for c in celulas:
            plot = campo.at(c)
            if plot is None:
                continue
            if a.crop and plot.crop != a.crop:
                continue
            podre = campo.is_spoiled(c, day)
            pronta = campo.is_grown(c, day)
            if a.verb == "LIMPAR" and podre:
                alvos.append(c)
            elif a.verb == "COLHER" and pronta and not podre:
                alvos.append(c)
            elif a.verb == "FERTILIZAR" and not pronta and not podre and not plot.fertilized:
                alvos.append(c)
        return alvos

    def _available(self, a: Action, alvos: int) -> tuple[int, str | None]:
        """Quantas unidades cabem agora e, se cortou, o que cortou."""
        game = self.s.game
        if alvos == 0:
            return 0, NO_FREE_CELL if a.verb == "PLANTAR" else NO_TARGET
        if a.verb == "PLANTAR":
            sementes = game.inventory.count(seed_key(a.crop))
            return min(alvos, sementes), (NO_RESOURCE if sementes < alvos else None)
        if a.verb == "FERTILIZAR":
            estoque = game.inventory.count(FERTILIZER)
            diario = max(0, game_settings.FERTILIZERS_PER_DAY - game.fertilizers_today)
            n = min(alvos, estoque, diario)
            if n == alvos:
                return n, None
            return n, DAILY_FERT_LIMIT if diario <= estoque else NO_RESOURCE
        return alvos, None

    def _nearest(self, cells) -> Cell:
        origem = self.s.cell
        dist = self._distances_from(origem) if len(cells) > 1 else None

        def chave(c):
            passos = dist[c] if dist is not None else 0
            return (passos, c[0], c[1])
        return min(cells, key=chave)

    def _act(self, a: Action) -> None:
        if a.verb == "PLANTAR":
            self.s.plant(a.crop)
        elif a.verb == "COLHER":
            self.s.harvest()
        elif a.verb == "LIMPAR":
            self.s.clear()
        else:
            self.s.fertilize()

    # ------------------------------------------------------------------ loja

    def _shop(self, a: Action, r: ActionResult) -> None:
        if self.zone != STORE:
            r.status, r.reason = SKIPPED, WRONG_ZONE
            r.detail = f"{a.verb} exige estar na loja; o jogador estava em '{self.zone}'"
            return
        if a.verb == "COMPRAR":
            self._buy(a, r)
        else:
            self._sell(a, r)

    def _buy(self, a: Action, r: ActionResult) -> None:
        game = self.s.game
        r.requested = a.amount
        feitos = 0
        while feitos < a.amount:
            loja, inv = game.market, game.inventory
            preco = loja.buy_price(a.item)
            if loja.stock_left(a.item) == 0:
                r.reason = NO_STOCK
                break
            if inv.is_full(a.item):
                r.reason = INVENTORY_LIMIT
                break
            if inv.count(COIN) < preco:
                r.reason = NO_COINS
                break
            try:
                self.s.buy(a.item, 1)
            except Blocked as erro:
                r.reason, r.detail = GAME_REFUSED, str(erro)
                break
            r.coins -= preco
            r.unit_prices.append(preco)
            feitos += 1
        r.effective = feitos
        if feitos < a.amount:
            r.status = PARTIAL if feitos else SKIPPED

    def _sell(self, a: Action, r: ActionResult) -> None:
        game = self.s.game
        tem = game.inventory.count(a.crop)
        r.requested = tem if a.all_ else a.amount
        feitos = 0
        while feitos < r.requested:
            loja, day = game.market, self.s.day
            if game.inventory.count(a.crop) == 0:
                r.reason = NO_RESOURCE
                break
            if not loja.can_sell(a.crop, day):
                r.reason = NO_CASH
                break
            preco, base = loja.sell_price(a.crop, day), loja.base_price(a.crop, day)
            try:
                self.s.sell(a.crop, 1)
            except Blocked as erro:
                r.reason, r.detail = GAME_REFUSED, str(erro)
                break
            r.coins += preco
            r.unit_prices.append(preco)
            r.below_base += preco < base
            feitos += 1
        r.effective = feitos
        if r.requested == 0:
            r.status, r.reason = SKIPPED, NO_RESOURCE
        elif feitos < r.requested:
            r.status = PARTIAL if feitos else SKIPPED
