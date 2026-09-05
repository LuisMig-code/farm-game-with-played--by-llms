"""Loop principal e maquina de estados do jogo."""

import logging
from enum import Enum, auto

import pygame

from farm import assets, settings
from farm.crops import BUY_PRICES, COIN, CROPS, FERTILIZER, ITEM_LABELS, seed_key
from farm.field import Field
from farm.grid import Grid
from farm.hud import Hud
from farm.inventory import RunStats, starting_inventory
from farm.market import Market
from farm.menu import Menu, Option
from farm.player import Player
from farm.rng import resolve_seed
from farm.run_log import RunLog
from farm.seasons import Seasons
from farm.spoil_record import SpoiledCells
from farm.view import View
from farm.zones import Zones

logger = logging.getLogger(__name__)

MOVE_KEYS = {
    "left": (pygame.K_a, pygame.K_LEFT),
    "right": (pygame.K_d, pygame.K_RIGHT),
    "up": (pygame.K_w, pygame.K_UP),
    "down": (pygame.K_s, pygame.K_DOWN),
}
CONFIRM_KEYS = (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER)

HOUSE_ZONE, SHOP_ZONE = "casa", "comercio"
PLANT, HARVEST, CLEAR, FERTILIZE = "plantar", "colher", "remover", "fertilizar"

# Tipos de menu (viram a coluna `item` das linhas de menu no CSV)
SEED_MENU, FERT_MENU = "semente", "fertilizante"
SHOP_MENU, SELL_MENU, BUY_MENU = "comercio", "vender", "comprar"
# Remover reaproveita a animacao de colheita: e o mesmo gesto de arrancar.
ACTION_ANIMATION = {PLANT: "planting", HARVEST: "harvest", CLEAR: "harvest",
                    FERTILIZE: "fertilizing"}

Cell = tuple[int, int]


class State(Enum):
    PLAYING = auto()
    MENU = auto()
    BUSY = auto()        # animacao de plantar/colher rodando
    SLEEPING = auto()    # transicao entre dias
    GAME_OVER = auto()


class Game:
    def __init__(self, seed: int | None = None) -> None:
        pygame.init()
        # SCALED: se a janela nao couber no monitor, o SDL reduz sozinho
        # mantendo as coordenadas logicas em SCREEN_SIZE.
        self.screen = pygame.display.set_mode(settings.SCREEN_SIZE, pygame.SCALED)
        pygame.display.set_caption("Farm Game")

        self.clock = pygame.time.Clock()
        self.running = False

        self.view = View(settings.WORLD_SIZE, settings.SCREEN_SIZE)
        # O fundo agora depende do dia: quem cuida dele e o Seasons.
        self.seasons = Seasons(self.view)
        self.grid = Grid(settings.GRID_COLS, settings.GRID_ROWS, settings.TILE)
        self.zones = Zones(self.grid, self.view)
        self.hud = Hud(self.view)
        # Atravessa o R de proposito: o historico e acumulado entre partidas.
        self.spoiled_cells = SpoiledCells(settings.LOGS_DIR / settings.SPOILED_LOG)
        # Fora do _reset de proposito: assim o R repete o mesmo cenario em vez de
        # sortear outro -- inclusive quando a semente veio de um sorteio.
        self.seed = resolve_seed(seed)

        self._reset()

        logger.info(
            "mundo %dx%d | janela %dx%d (escala %.2f) | grid %dx%d celulas de %dpx",
            *settings.WORLD_SIZE, *settings.SCREEN_SIZE, self.view.scale,
            settings.GRID_COLS, settings.GRID_ROWS, settings.TILE,
        )

    def _reset(self) -> None:
        """Estado de uma partida nova. Nao recarrega assets nem o display.

        Cada run tem seus proprios arquivos de log, entao a anterior e fechada aqui.
        """
        anterior = getattr(self, "run_log", None)
        if anterior is not None:
            anterior.close("reiniciada")
        self.run_log = RunLog(settings.LOGS_DIR, self.seed)

        self.state = State.PLAYING
        self.day = settings.FIRST_DAY
        self.inventory = starting_inventory()
        self.stats = RunStats(days=self.day)
        self.field = Field(self.grid, self.view)
        self.market = Market(self.seed)
        self.player = Player(self.view, self.zones, settings.PLAYER_START_CELL,
                             on_step=self._on_step)
        self.menu: Menu | None = None
        self._pending: tuple[str, Cell, str | None] | None = None
        self._sleep_time = 0.0
        self.fertilizers_today = 0
        self._record("inicio", cell=self.player.cell)
        self._record_promotions()

    # -------------------------------------------------------------- registro

    def _record(self, action: str, **kwargs) -> None:
        self.run_log.record(action, day=self.day, stamina=self.player.stamina, **kwargs)

    def _on_step(self, origin: Cell, destination: Cell) -> None:
        """Chamado pelo Player a cada celula concluida."""
        self._record("mover", origin=origin, cell=destination)

    def _record_spoiled(self) -> None:
        """Guarda o que apodreceu hoje. Esse registro nao aparece para o jogador."""
        for cell, crop in self.field.newly_spoiled(self.day):
            self._record_spoilage(cell, crop)

    def _record_spoilage(self, cell: Cell, crop: str) -> None:
        """Ponto unico de gravacao: vale para o prazo vencido e para o inverno."""
        self.stats.spoiled[crop] += 1
        self.spoiled_cells.record(cell, crop, self.day, self.run_log.run_id)
        self._record("estragou", cell=cell, item=crop, amount=1)
        logger.info("estragou: %s em %s", crop, cell)

    def _freeze_if_blocked(self, anterior) -> None:
        """Virada para uma estacao sem plantio: o campo inteiro apodrece na hora."""
        atual = self.seasons.current(self.day)
        if atual is anterior or atual.can_plant:
            return
        for cell, crop in self.field.freeze_all():
            self._record_spoilage(cell, crop)

    def _record_promotions(self) -> None:
        for item, desconto in self.market.promos.items():
            self._record("promocao", item=item, amount=desconto,
                         price=self.market.buy_price(item))

    # ------------------------------------------------------------------- loop

    def run(self) -> None:
        self.running = True
        try:
            while self.running:
                dt = self.clock.tick(settings.FPS) / 1000.0
                self._handle_events()
                self._update(dt)
                self._draw()
                pygame.display.flip()
        finally:
            self._record("saiu", cell=self.player.cell)
            self.run_log.close()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._on_key(event.key)

    def _on_key(self, key: int) -> None:
        if self.state is State.GAME_OVER:
            if key == pygame.K_r:
                self._reset()
            elif key == pygame.K_ESCAPE:
                self.running = False
            return

        if self.state is State.MENU:
            # Com menu aberto o ESC so fecha o menu, nao sai do jogo.
            if key in MOVE_KEYS["up"]:
                self.menu.move(-1)
            elif key in MOVE_KEYS["down"]:
                self.menu.move(1)
            elif key in CONFIRM_KEYS:
                self._confirm_menu()
            elif key == pygame.K_ESCAPE:
                self._cancel_menu()
            return

        if key == pygame.K_ESCAPE:
            self.running = False
        elif key == pygame.K_g:
            self._toggle_overlays()
        elif key in CONFIRM_KEYS and self.state is State.PLAYING:
            self._interact()

    def _toggle_overlays(self) -> None:
        """G esconde/mostra as linhas do grid e o colorido das zonas juntos."""
        self.grid.toggle()
        self.zones.visible = self.grid.visible
        logger.debug("grid e zonas visiveis: %s", self.grid.visible)

    def _update(self, dt: float) -> None:
        if self.state is State.GAME_OVER:
            return

        if self.state is State.SLEEPING:
            self._sleep_time += dt
            if self._sleep_time >= settings.SLEEP_TRANSITION:
                self.state = State.PLAYING
            return

        direction = self._input_direction() if self.state is State.PLAYING else pygame.Vector2()
        self.player.update(direction, dt)

        if self.state is State.BUSY and not self.player.busy:
            self._finish_action()

        if self.player.exhausted:
            self._game_over()

    @staticmethod
    def _input_direction() -> pygame.Vector2:
        keys = pygame.key.get_pressed()
        return pygame.Vector2(
            any(keys[k] for k in MOVE_KEYS["right"]) - any(keys[k] for k in MOVE_KEYS["left"]),
            any(keys[k] for k in MOVE_KEYS["down"]) - any(keys[k] for k in MOVE_KEYS["up"]),
        )

    # ------------------------------------------------------------------ acoes

    def _interact(self) -> None:
        """Espaco: o que acontece depende da celula em que o jogador esta."""
        if self.player.moving:      # so age parado, no centro de uma celula
            return

        cell = self.player.cell
        zona = self.zones.zone_of(cell)
        if zona == HOUSE_ZONE:
            self._sleep()
        elif zona == SHOP_ZONE:
            self._open_menu(self._shop_menu(cell))
        elif not self.zones.is_plantable(cell):
            logger.debug("nada a fazer em %s", cell)
        elif self.field.at(cell) is None:
            self._open_seed_menu(cell)
        elif self.field.is_spoiled(cell, self.day):
            self._start_action(CLEAR, cell)
        elif self.field.is_grown(cell, self.day):
            self._start_action(HARVEST, cell)
        else:
            self._open_fertilizer_menu(cell)

    def _start_action(self, kind: str, cell: Cell, crop: str | None = None) -> None:
        """Roda a animacao; o efeito so e aplicado quando ela termina."""
        self.player.start_action(ACTION_ANIMATION[kind])
        self._pending = (kind, cell, crop)
        self.state = State.BUSY

    def _finish_action(self) -> None:
        kind, cell, crop = self._pending
        self._pending = None

        if kind == PLANT:
            self.inventory.take(seed_key(crop))
            self.field.plant(cell, crop, self.day)
            self.player.spend(settings.STAMINA_PLANT)
            self.stats.planted[crop] += 1
            self._record("plantar", cell=cell, item=crop, amount=1)
        elif kind == CLEAR:
            removida = self.field.remove(cell)      # nao rende nada
            self.player.spend(settings.STAMINA_CLEAR)
            self._record("remover", cell=cell, item=removida, amount=1)
        elif kind == FERTILIZE:
            self._use_fertilizer(cell)
        else:
            harvested = self.field.harvest(cell)
            self.inventory.add(harvested)
            self.player.spend(settings.STAMINA_HARVEST)
            self.stats.harvested[harvested] += 1
            self._record("colher", cell=cell, item=harvested, amount=1)

        self.state = State.PLAYING

    def _sleep(self) -> None:
        anterior = self.seasons.current(self.day)
        self.day += 1
        if self.seasons.current(self.day) is not anterior:
            logger.info("virou a estacao: %s -> %s", anterior.label,
                        self.seasons.current(self.day).label)
        self.stats.days = self.day
        self.player.restore()
        self.state = State.SLEEPING
        self._sleep_time = 0.0
        logger.info("dormiu: dia %d, estamina cheia", self.day)
        self._record("dormir", cell=self.player.cell)
        self.fertilizers_today = 0
        self.market.new_day(self.day)
        self._record_promotions()
        self._freeze_if_blocked(anterior)
        self._record_spoiled()

    def _game_over(self) -> None:
        self.state = State.GAME_OVER
        self.menu = None
        self._pending = None
        logger.info("fim de jogo no dia %d | plantado %s | colhido %s",
                    self.day, dict(self.stats.planted), dict(self.stats.harvested))
        self._record("derrota", cell=self.player.cell)

    # ------------------------------------------------------------------ menus

    def _shop_menu(self, cell: Cell) -> Menu:
        return Menu(SHOP_MENU, self._wallet("Comércio"), [
            Option("Vender colheita", value=SELL_MENU),
            Option("Comprar sementes e fertilizante", value=BUY_MENU),
        ], cell)

    def _sell_menu(self, cell: Cell) -> Menu:
        options = []
        for key, crop in CROPS.items():
            if not self.inventory.has(key):
                continue
            preco = self.market.sell_price(key, self.day)
            cabe = self.market.can_sell(key, self.day)
            aviso = "" if cabe else "  (sem saldo)"
            options.append(Option(f"{crop.label} ({self.inventory.count(key)})   "
                                  f"{preco} moedas{aviso}",
                                  value=key, icon=key, enabled=cabe))
        if not options:
            options = [Option("Nada para vender", enabled=False)]
        return Menu(SELL_MENU, self._wallet("Vender"), options, cell)

    def _buy_menu(self, cell: Cell) -> Menu:
        moedas = self.inventory.count(COIN)
        options = []
        for item in BUY_PRICES:
            estoque = self.market.stock_left(item)
            if not estoque:
                options.append(Option(f"{ITEM_LABELS[item]}   esgotado hoje",
                                      icon=item, enabled=False))
                continue
            if self.inventory.is_full(item):
                options.append(Option(f"{ITEM_LABELS[item]}   voce ja carrega "
                                      f"{self.inventory.limit_for(item)}, o maximo",
                                      icon=item, enabled=False))
                continue
            preco = self.market.buy_price(item)
            promo = "  (promo!)" if self.market.is_promo(item) else ""
            options.append(Option(f"{ITEM_LABELS[item]}   {preco} moedas{promo}   "
                                  f"{estoque} no estoque",
                                  value=item, icon=item, enabled=moedas >= preco))
        return Menu(BUY_MENU, self._wallet("Comprar"), options, cell)

    def _wallet(self, titulo: str) -> str:
        return f"{titulo} - {self.inventory.count(COIN)} moedas"

    def _refresh_menu(self) -> None:
        """Atualiza precos e quantidades sem reabrir o menu (nao gera log)."""
        novo = (self._sell_menu(self.menu.cell) if self.menu.kind == SELL_MENU
                else self._buy_menu(self.menu.cell))
        self.menu.title = novo.title
        self.menu.options = novo.options
        self.menu.index = min(self.menu.index, len(novo.options) - 1)
        if not self.menu.options[self.menu.index].enabled:
            self.menu.move(1)

    def _open_seed_menu(self, cell: Cell) -> None:
        estacao = self.seasons.current(self.day)
        if not estacao.can_plant:
            self._open_menu(Menu(SEED_MENU, f"{estacao.label} na fazenda",
                                 [Option(f"Nada cresce no {estacao.label.lower()}",
                                         enabled=False)], cell))
            return

        options = [
            Option(f"{crop.label} ({self.inventory.count(seed_key(key))})",
                   value=key, icon=seed_key(key))
            for key, crop in CROPS.items() if self.inventory.has(seed_key(key))
        ]
        if not options:
            options = [Option("Sem sementes", enabled=False)]
        self._open_menu(Menu(SEED_MENU, "Plantar o quê?", options, cell))

    def _open_fertilizer_menu(self, cell: Cell) -> None:
        """A opcao desabilitada diz o motivo, para o jogador nao ficar no escuro."""
        crop = CROPS[self.field.at(cell).crop]
        count = self.inventory.count(FERTILIZER)
        estacao = self.seasons.current(self.day)

        if not estacao.fertilizer_works:
            option = Option(f"Não funciona no {estacao.label.lower()}", enabled=False)
        elif self.field.is_fertilized(cell):
            option = Option("Já fertilizada", enabled=False)
        elif self.fertilizers_today >= settings.FERTILIZERS_PER_DAY:
            option = Option(f"Limite de {settings.FERTILIZERS_PER_DAY} por dia", enabled=False)
        else:
            option = Option(f"Usar fertilizante ({count})", value=FERTILIZER,
                            icon=FERTILIZER, enabled=count > 0)

        self._open_menu(Menu(FERT_MENU, f"{crop.label} crescendo", [option], cell))

    def _sell(self, crop: str, cell: Cell) -> None:
        """Vende uma unidade. Negociar nao custa estamina."""
        preco = self.market.sell_price(crop, self.day)
        if not self.market.can_sell(crop, self.day):
            logger.debug("mercado sem caixa para %s (%d moedas)", crop, preco)
            return
        if not self.inventory.take(crop):
            return
        self.inventory.add(COIN, preco)
        self.market.register_sale(crop, self.day)
        self.stats.sold[crop] += 1
        logger.info("vendeu %s por %d moedas", crop, preco)
        self._record("vender", cell=cell, item=crop, amount=1, price=preco)

    def _buy(self, item: str, cell: Cell) -> None:
        preco = self.market.buy_price(item)
        if not self.market.stock_left(item) or self.inventory.is_full(item):
            return
        if not self.inventory.take(COIN, preco):
            return
        self.market.register_purchase(item, preco)   # tambem devolve caixa ao mercado
        self.inventory.add(item)
        self.stats.bought[item] += 1
        logger.info("comprou %s por %d moedas", item, preco)
        self._record("comprar", cell=cell, item=item, amount=1, price=preco)

    def _use_fertilizer(self, cell: Cell) -> None:
        """Um por planta: acelera o crescimento e estica a validade."""
        self.inventory.take(FERTILIZER)
        self.field.fertilize(cell)
        self.player.spend(settings.STAMINA_FERTILIZE)
        self.fertilizers_today += 1
        self.stats.fertilized += 1
        self._record("fertilizar", cell=cell, item=FERTILIZER, amount=1)

    # ------------------------------------------------------------------ menus

    def _open_menu(self, menu: Menu) -> None:
        self.menu = menu
        self.state = State.MENU
        self._record("abrir_menu", cell=menu.cell, item=menu.kind)

    def _cancel_menu(self) -> None:
        cell, kind = self.menu.cell, self.menu.kind
        self._record("cancelar_menu", cell=cell, item=kind)
        if kind in (SELL_MENU, BUY_MENU):
            self._open_menu(self._shop_menu(cell))   # ESC volta um nivel
        else:
            self._close_menu()

    def _close_menu(self) -> None:
        self.menu = None
        self.state = State.PLAYING

    def _confirm_menu(self) -> None:
        value = self.menu.confirm()
        kind, cell = self.menu.kind, self.menu.cell

        if value is None:                       # opcao desabilitada
            if kind in (SEED_MENU, FERT_MENU):
                self._close_menu()              # no campo, fecha; na loja, fica
            return

        if kind == SEED_MENU:
            self._close_menu()
            self._start_action(PLANT, cell, value)
        elif kind == FERT_MENU:
            self._close_menu()
            self._start_action(FERTILIZE, cell)
        elif kind == SHOP_MENU:
            self._open_menu(self._sell_menu(cell) if value == SELL_MENU
                            else self._buy_menu(cell))
        else:                                   # vender/comprar: fica no menu
            if kind == SELL_MENU:
                self._sell(value, cell)
            else:
                self._buy(value, cell)
            self._refresh_menu()

    # ---------------------------------------------------------------- desenho

    def hovered_cell(self) -> Cell | None:
        """Celula do mundo sob o cursor, ou None se o mouse esta fora da janela."""
        if not pygame.mouse.get_focused():
            return None
        cell = self.grid.cell_at_world(self.view.screen_to_world(pygame.mouse.get_pos()))
        return cell if self.grid.contains(*cell) else None

    def _draw(self) -> None:
        self.screen.blit(self.seasons.background(self.day), (0, 0))
        self.zones.draw(self.screen)
        self.grid.draw(self.screen, self.view, self.hovered_cell())
        self.hud.draw_price_board(self.screen, self.market, self.day)
        self.hud.draw_season_board(self.screen, self.seasons, self.day)
        self.field.draw(self.screen, self.view, self.day)
        self.player.draw(self.screen, self.view)

        self.hud.draw_panel(self.screen, day=self.day, stamina=self.player.stamina,
                            max_stamina=self.player.max_stamina,
                            inventory=self.inventory, info=self._info_lines())
        if self.menu is not None:
            anchor = self.view.apply(self.grid.cell_rect_world(*self.menu.cell)).midtop
            self.menu.draw(self.screen, self.hud.fonts, self.hud.icons, anchor)

        if self.state is State.SLEEPING:
            self.hud.draw_sleep(self.screen, self.day,
                                self._sleep_time / settings.SLEEP_TRANSITION)
        elif self.state is State.GAME_OVER:
            self.hud.draw_game_over(self.screen, self.stats, self.inventory)

    def _info_lines(self) -> list[str]:
        cell = self.player.cell
        hover = self.hovered_cell()
        return [
            f"jogador {cell} {self.zones.zone_of(cell)}{self._plot_label(cell)}   "
            f"mouse {hover if hover else '--'}   "
            f"grid+zonas {'ON' if self.grid.visible else 'OFF'}   "
            f"semente {self.seed}",
            "WASD/setas: mover   Espaço: agir/dormir   G: grid   ESC: sair",
        ]

    def _plot_label(self, cell: Cell) -> str:
        """Descreve a planta sob os pes do jogador, se houver."""
        plot = self.field.at(cell)
        if plot is None:
            return ""
        nome = CROPS[plot.crop].label + (" fertilizada" if plot.fertilized else "")
        if self.field.is_spoiled(cell, self.day):
            return f" [{nome} estragada, Espaço remove]"
        if self.field.is_grown(cell, self.day):
            return f" [{nome} pronta, estraga em {self.field.days_left(cell, self.day)} dia(s)]"
        faltam = self.field.timing(plot)[0] - self.field.age(cell, self.day)
        return f" [{nome}, faltam {faltam} dia(s)]"
