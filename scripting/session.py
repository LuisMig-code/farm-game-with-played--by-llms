"""O jogo dirigido por codigo.

`Session` monta um `Game` normal e roda o laco por fora, sem tocar em `farm/`.
Duas coisas exigem cuidado e explicam o desenho desta classe:

1. **Movimento nao passa por tecla.** `Game._on_key` trata Espaco, ESC e G, mas
   a direcao vem de `Game._input_direction()`, que le o teclado fisico. Como e
   um `staticmethod` (descritor nao-dado), um atributo de instancia tem
   prioridade -- e por isso `_tick` consegue injetar a direcao sem editar nada.

2. **Atalhar o menu deixa trapacear.** `_start_action` nao revalida nada: com
   zero sementes, plantar por ali funciona assim mesmo. As travas de regra vivem
   em `Option.enabled`. Entao aqui tudo passa pelo menu, como um humano faria, e
   uma opcao desabilitada vira `Blocked` com o motivo que o proprio jogo
   escreveu no rotulo.
"""

import logging

import pygame

from farm import settings
from farm.crops import CROPS, FERTILIZER, seed_key
from farm.game import (BUY_MENU, FERT_MENU, SEED_MENU, SELL_MENU, SHOP_MENU,
                       Game, State)
from scripting.errors import Aborted, Blocked, GameOver, NoRoute
from scripting.observation import Observation
from scripting.recorder import Recorder
from scripting.route import directions, shortest_path

logger = logging.getLogger(__name__)

Cell = tuple[int, int]

HOUSE: Cell = settings.PLAYER_START_CELL
SHOP: Cell = (21, 12)

# Teto do passo de simulacao. O relogio e real, entao enquanto o agente pensa
# nenhum quadro roda -- sem esta trava, o dt acumulado da pausa faria o jogador
# atravessar meio mapa num quadro so.
MAX_DT = 0.05
# Rede de seguranca para as esperas: 60s de jogo e muito mais do que qualquer
# acao precisa, e evita laco infinito se algo travar num estado inesperado.
MAX_FRAMES = 3600


class Session:
    """Uma partida dirigida por script.

    >>> with Session(seed=42, record="logs/partida.mp4") as s:
    ...     s.walk_to((6, 8))
    ...     s.plant("batata")
    """

    def __init__(self, seed: int | None = None, record: str | None = None,
                 fps: int = settings.FPS):
        self.game = Game(seed=seed)
        self.game.running = True          # nao chamamos run(): o laco e nosso
        self.fps = fps
        self.recorder = Recorder(record) if record else None
        logger.info("sessao de script iniciada | semente %s", self.game.seed)

    # ------------------------------------------------------------ ciclo de vida

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        """Fecha video e logs. E o que o `finally` de `Game.run()` faria.

        Nao encerra o pygame de proposito: assim varias sessoes podem rodar no
        mesmo processo.
        """
        if self.recorder is not None:
            self.recorder.close()
            self.recorder = None
        if not self.game.run_log._closed:
            self.game._record("saiu", cell=self.game.player.cell)
            self.game.run_log.close()
        self.game.running = False

    # ------------------------------------------------------------------ estado

    @property
    def day(self) -> int:
        return self.game.day

    @property
    def cell(self) -> Cell:
        return self.game.player.cell

    @property
    def stamina(self) -> int:
        return self.game.player.stamina

    @property
    def coins(self) -> int:
        from farm.crops import COIN
        return self.game.inventory.count(COIN)

    @property
    def over(self) -> bool:
        return self.game.state is State.GAME_OVER or self.game.player.exhausted

    @property
    def stats(self):
        return self.game.stats

    def observe(self) -> Observation:
        return Observation.of(self.game)

    def count(self, item: str) -> int:
        return self.game.inventory.count(item)

    # -------------------------------------------------------------------- laco

    def tick(self, frames: int = 1, direction: Cell = (0, 0)) -> None:
        """Avanca `frames` quadros em tempo real, com a direcao pedida."""
        for _ in range(frames):
            self._tick(direction)

    def breathe(self, seconds: float) -> None:
        """Mantem a janela viva sem agir -- util antes de uma espera longa."""
        gasto = 0.0
        while gasto < seconds:
            gasto += self._tick()

    def _tick(self, direction: Cell = (0, 0)) -> float:
        game = self.game
        # Sombreia o leitor de teclado: e o unico jeito de comandar o movimento
        # sem editar farm/game.py.
        game._input_direction = lambda d=pygame.Vector2(direction): d

        dt = min(game.clock.tick(self.fps) / 1000.0, MAX_DT)
        game._handle_events()
        if not game.running:
            raise Aborted("a janela do jogo foi fechada")

        game._update(dt)
        game._draw()
        pygame.display.flip()
        if self.recorder is not None:
            self.recorder.capture(game.screen, dt)
        return dt

    def _wait(self, pronto, motivo: str) -> None:
        """Roda quadros ate `pronto()`, vigiando derrota e travamento."""
        for _ in range(MAX_FRAMES):
            if pronto():
                return
            self._tick()
            if self.game.state is State.GAME_OVER:
                raise GameOver(f"a estamina acabou durante: {motivo}")
        raise Aborted(f"o jogo nao saiu do estado {self.game.state.name} em {motivo}")

    # --------------------------------------------------------------- movimento

    def walk_to(self, cell: Cell) -> "Session":
        """Anda ate a celula pelo menor caminho andavel."""
        self._require_playing()
        caminho = shortest_path(self.cell, cell, self.game.zones.walkable)
        if caminho is None:
            raise NoRoute(f"nao ha caminho andavel de {self.cell} ate {cell}")
        for passo in directions(caminho, self.cell):
            self.step(passo)
        return self

    def step(self, direction: Cell) -> "Session":
        """Um passo de celula. Bater na parede falha em silencio no jogo, aqui nao."""
        self._require_playing()
        origem = self.cell
        # A direcao vale so no primeiro quadro: mante-la ligada emendaria o passo
        # seguinte com a sobra de deslocamento, como acontece segurando a tecla.
        self._tick(direction)
        self._wait(lambda: not self.game.player.moving, f"passo {direction}")
        if self.cell == origem:
            raise Blocked(f"{origem} nao tem celula andavel na direcao {direction}")
        return self

    # ------------------------------------------------------------------- campo

    def plant(self, crop: str) -> "Session":
        """Planta uma semente na celula onde o jogador esta."""
        if crop not in CROPS:
            raise Blocked(f"cultura desconhecida: {crop!r}")
        self._require_playing()
        if self.game.field.at(self.cell) is not None:
            raise Blocked(f"{self.cell} ja tem uma planta")
        self._open_here(SEED_MENU)
        self._choose(crop, faltando=f"nao ha semente de {crop} no inventario")
        self._wait_action("plantar")
        return self

    def fertilize(self) -> "Session":
        """Usa fertilizante na planta sob o jogador."""
        self._require_playing()
        self._require_plot("fertilizar")
        self._open_here(FERT_MENU)
        self._choose(FERTILIZER, faltando="o menu de fertilizante veio vazio")
        self._wait_action("fertilizar")
        return self

    def harvest(self) -> "Session":
        """Colhe a planta pronta sob o jogador. Sem menu: e um Espaco direto."""
        self._require_playing()
        cell = self._require_plot("colher")
        if self.game.field.is_spoiled(cell, self.day):
            raise Blocked(f"a planta em {cell} esta estragada: use clear()")
        if not self.game.field.is_grown(cell, self.day):
            faltam = self.observe().plots
            dias = next(p["days_to_grow"] for p in faltam if tuple(p["cell"]) == cell)
            raise Blocked(f"a planta em {cell} ainda nao esta pronta ({dias} dia(s))")
        self.press(pygame.K_SPACE)
        self._wait_action("colher")
        return self

    def clear(self) -> "Session":
        """Arranca a planta estragada sob o jogador."""
        self._require_playing()
        cell = self._require_plot("remover")
        if not self.game.field.is_spoiled(cell, self.day):
            raise Blocked(f"a planta em {cell} nao esta estragada")
        self.press(pygame.K_SPACE)
        self._wait_action("remover")
        return self

    # --------------------------------------------------------------- casa/loja

    def sleep(self) -> "Session":
        """Dorme e avanca um dia. So funciona em cima da casa."""
        self._require_playing()
        if self.cell != HOUSE:
            raise Blocked(f"so da para dormir na casa {HOUSE}, e o jogador esta em {self.cell}")
        anterior = self.day
        self.press(pygame.K_SPACE)
        self._wait(lambda: self.game.state is State.PLAYING and self.day > anterior,
                   "dormir")
        return self

    def sleep_until(self, day: int) -> "Session":
        """Dorme quantas vezes for preciso ate chegar no dia pedido."""
        while self.day < day:
            self.sleep()
        return self

    def sell(self, crop: str, amount: int = 1) -> "Session":
        """Vende unidades da colheita. Abre e fecha o menu da loja sozinho."""
        self._trade(SELL_MENU, crop, amount, f"vender {crop}")
        return self

    def buy(self, item: str, amount: int = 1) -> "Session":
        """Compra sementes ou fertilizante. `item` e a chave (ex: 'semente batata')."""
        self._trade(BUY_MENU, item, amount, f"comprar {item}")
        return self

    def seed_of(self, crop: str) -> str:
        """Atalho: a chave de semente de uma cultura, para usar em buy()."""
        return seed_key(crop)

    def leave_shop(self) -> "Session":
        """Fecha o menu da loja, de qualquer nivel."""
        while self.game.state is State.MENU:
            self.press(pygame.K_ESCAPE)
        return self

    def _trade(self, kind: str, value: str, amount: int, o_que: str) -> None:
        self._require_playing()
        if self.cell != SHOP:
            raise Blocked(f"a loja fica em {SHOP}, e o jogador esta em {self.cell}")
        if amount < 1:
            raise Blocked(f"quantidade invalida para {o_que}: {amount}")

        self._open_here(SHOP_MENU)
        self._choose(kind, faltando=f"a loja nao ofereceu {kind}")   # vender/comprar
        self._expect(kind)
        try:
            for _ in range(amount):
                self._choose(value, faltando=f"a loja nao lista {value}")
        finally:
            self.leave_shop()

    # ------------------------------------------------------------------ teclas

    def press(self, key: int) -> "Session":
        """Manda uma tecla ao jogo e roda um quadro."""
        if key == pygame.K_ESCAPE and self.game.state is not State.MENU:
            raise Blocked("ESC fora de menu encerra o jogo; use close()")
        self.game._on_key(key)
        self._tick()
        return self

    # ------------------------------------------------------------------ menus

    def _open_here(self, kind: str) -> None:
        """Espaco na celula atual e confere que abriu o menu esperado."""
        self.press(pygame.K_SPACE)
        self._expect(kind)

    def _expect(self, kind: str) -> None:
        menu = self.game.menu
        if self.game.state is not State.MENU or menu is None:
            raise Blocked(f"esperava o menu '{kind}' em {self.cell}, "
                          f"mas o jogo ficou em {self.game.state.name}")
        if menu.kind != kind:
            self.leave_shop()
            raise Blocked(f"esperava o menu '{kind}', veio '{menu.kind}'")

    def _choose(self, value: str, faltando: str) -> None:
        """Seleciona a opcao pelo valor e confirma, respeitando `enabled`.

        Ler `enabled` antes de confirmar e o que impede o script de trapacear:
        e ali que moram todas as travas de regra do jogo.
        """
        menu = self.game.menu
        escolha = next(((i, o) for i, o in enumerate(menu.options) if o.value == value), None)
        if escolha is None:
            motivos = [o.label for o in menu.options if not o.enabled]
            self._abort_menu()
            raise Blocked(f"{faltando}" + (f" | menu diz: {'; '.join(motivos)}" if motivos else ""))

        indice, opcao = escolha
        if not opcao.enabled:
            self._abort_menu()
            raise Blocked(f"o jogo recusou: {opcao.label.strip()}")

        menu.index = indice          # equivale a andar com as setas ate ali
        self.press(pygame.K_SPACE)

    def _abort_menu(self) -> None:
        """Fecha o menu sem escolher nada, para o jogo nao ficar preso nele."""
        while self.game.state is State.MENU:
            self.game._on_key(pygame.K_ESCAPE)

    def _wait_action(self, o_que: str) -> None:
        self._wait(lambda: self.game.state is State.PLAYING, o_que)

    # ------------------------------------------------------------------ guardas

    def _require_playing(self) -> None:
        if self.over:
            raise GameOver(f"a partida acabou no dia {self.day}")
        if self.game.state is State.MENU:
            raise Blocked(f"ha um menu '{self.game.menu.kind}' aberto; use leave_shop()")

    def _require_plot(self, o_que: str) -> Cell:
        cell = self.cell
        if self.game.field.at(cell) is None:
            raise Blocked(f"nao ha planta em {cell} para {o_que}")
        return cell
