"""Jogador: movimento celula a celula no grid e animacao por sprites."""

import logging

import pygame

from farm import assets, settings
from farm.view import View
from farm.zones import Zones

logger = logging.getLogger(__name__)

# Todos os sprites tem 159x239, exceto os de "run right" (159x244). Uso essa
# altura como referencia e escalo todos pelo mesmo fator, para o corpo nao
# mudar de tamanho ao virar para a direita.
SPRITE_SIZE = (159, 239)

IDLE = "idle"
DIRECTIONS = ("down", "up", "left", "right")
ACTIONS = ("planting", "harvest", "fertilizing")   # 4 quadros cada, de frente
FACING_BY_STEP = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}


class Player:
    """Ocupa sempre uma celula: cada passo vai do centro de uma ao centro da vizinha."""

    def __init__(self, view: View, zones: Zones, start_cell: tuple[int, int],
                 on_step=None):
        self.animations = self._load_animations(view)
        self.zones = zones

        # Escala em pixels de MUNDO (a logica do jogo ignora a escala da tela).
        self.height = settings.PLAYER_HEIGHT
        self.width = settings.PLAYER_HEIGHT * SPRITE_SIZE[0] / SPRITE_SIZE[1]

        # pos = ponto onde o personagem pisa (centro-base do sprite).
        self.pos = cell_center(*start_cell)
        self.facing = "down"
        self.moving = False
        self._target: pygame.Vector2 | None = None
        self._anim_time = 0.0

        self.max_stamina = settings.STAMINA_MAX
        self.stamina = self.max_stamina
        self.action: str | None = None
        self._action_time = 0.0
        self._idle_time = 0.0
        self.on_step = on_step          # avisado a cada celula concluida
        self._step_origin = start_cell

        if not zones.is_walkable(start_cell):
            logger.warning("celula inicial %s nao e andavel", start_cell)
        logger.info("jogador comeca na celula %s (%s)", start_cell, zones.zone_of(start_cell))

    # --------------------------------------------------------------- sprites

    @staticmethod
    def _load_animations(view: View) -> dict[str, list[pygame.Surface]]:
        """Carrega e ja redimensiona os quadros para o tamanho final em tela."""
        factor = settings.PLAYER_HEIGHT / SPRITE_SIZE[1]
        folder = settings.CHARACTER_DIR

        sources = {IDLE: [f"{folder}/stay {i}.png" for i in range(1, 5)]}
        for direction in DIRECTIONS:
            sources[f"run_{direction}"] = [
                f"{folder}/run {direction} {i}.png" for i in range(1, 5)
            ]
        for action in ACTIONS:
            sources[action] = [f"{folder}/{action} {i}.png" for i in range(1, 5)]

        return {
            name: [view.scale_surface(frame, factor) for frame in assets.load_frames(names)]
            for name, names in sources.items()
        }

    # ------------------------------------------------------------ propriedades

    @property
    def cell(self) -> tuple[int, int]:
        """Celula do grid onde o personagem esta pisando."""
        return (int(self.pos.x // settings.TILE), int(self.pos.y // settings.TILE))

    @property
    def busy(self) -> bool:
        """Executando uma animacao de plantar/colher: nao anda nem aceita outra acao."""
        return self.action is not None

    @property
    def exhausted(self) -> bool:
        return self.stamina <= 0

    @property
    def world_rect(self) -> pygame.Rect:
        rect = pygame.Rect(0, 0, round(self.width), round(self.height))
        rect.midbottom = (round(self.pos.x), round(self.pos.y))
        return rect

    # ------------------------------------------------------------- estamina

    def spend(self, amount: int) -> None:
        self.stamina = max(0, self.stamina - amount)

    def restore(self) -> None:
        self.stamina = self.max_stamina

    # ------------------------------------------------------------- atualizacao

    def start_action(self, action: str) -> None:
        """Comeca a animacao de plantar ou colher. So vale com o jogador parado."""
        self.action = action
        self._action_time = 0.0

    @property
    def action_duration(self) -> float:
        return settings.ACTION_FRAMES / settings.ACTION_ANIM_FPS

    def update(self, direction: pygame.Vector2, dt: float) -> None:
        """Consome o deslocamento do frame em passos de uma celula.

        O laco existe para o caso de sobrar distancia ao chegar numa celula:
        com a tecla ainda pressionada, o passo seguinte comeca no mesmo frame
        e a caminhada nao engasga a cada celula.
        """
        if self.busy:
            self._action_time += dt
            if self._action_time >= self.action_duration:
                self.action = None
                self._action_time = 0.0
            return

        budget = settings.PLAYER_SPEED * dt
        while budget > 0 and not self.exhausted:
            if self._target is None and not self._start_step(direction):
                break
            budget = self._advance(budget)

        self.moving = self._target is not None
        # Cada estado tem seu relogio: zerar o da corrida faz o passo comecar
        # sempre no mesmo quadro, e o de parado segue correndo por baixo.
        if self.moving:
            self._anim_time += dt
            self._idle_time = 0.0
        else:
            self._anim_time = 0.0
            self._idle_time += dt

    def _start_step(self, direction: pygame.Vector2) -> bool:
        """Mira na celula vizinha. False se nao ha direcao ou se ela e bloqueada."""
        step = self._step_for(direction)
        if step is None:
            return False

        # Vira para o lado mesmo quando esbarra, para o passo bloqueado nao
        # deixar o personagem olhando para a direcao anterior.
        self.facing = FACING_BY_STEP[step]
        origin = self.cell
        target = (origin[0] + step[0], origin[1] + step[1])
        if not self.zones.is_walkable(target):
            return False

        self._step_origin = origin
        self._target = cell_center(*target)
        return True

    @staticmethod
    def _step_for(direction: pygame.Vector2) -> tuple[int, int] | None:
        """Uma celula por vez, nas 4 direcoes. Na diagonal, a horizontal ganha."""
        if direction.x and abs(direction.x) >= abs(direction.y):
            return (1 if direction.x > 0 else -1, 0)
        if direction.y:
            return (0, 1 if direction.y > 0 else -1)
        return None

    def _advance(self, budget: float) -> float:
        """Anda em direcao ao alvo e devolve a distancia que sobrou do frame."""
        to_target = self._target - self.pos
        distance = to_target.length()
        if distance > budget:
            self.pos += to_target * (budget / distance)
            return 0.0

        self.pos.update(self._target)  # encaixa exatamente no centro da celula
        self._target = None
        self.spend(settings.STAMINA_WALK)   # so a celula concluida custa estamina
        if self.on_step is not None:
            self.on_step(self._step_origin, self.cell)
        return budget - distance

    # ---------------------------------------------------------------- desenho

    def current_frame(self) -> pygame.Surface:
        if self.busy:
            frames = self.animations[self.action]
            index = min(int(self._action_time * settings.ACTION_ANIM_FPS), len(frames) - 1)
            return frames[index]

        # Os quadros de "stay" sao todos de frente: parado ele olha para frente,
        # seja qual for a direcao em que estava correndo.
        if self.moving:
            frames = self.animations[f"run_{self.facing}"]
            index = int(self._anim_time * settings.PLAYER_ANIM_FPS)
        else:
            frames = self.animations[IDLE]
            index = int(self._idle_time * settings.PLAYER_IDLE_FPS)
        return frames[index % len(frames)]

    def draw(self, surface: pygame.Surface, view: View) -> None:
        frame = self.current_frame()
        screen_pos = view.world_to_screen(self.pos)
        surface.blit(frame, frame.get_rect(midbottom=(round(screen_pos[0]),
                                                      round(screen_pos[1]))))


def cell_center(col: int, row: int) -> pygame.Vector2:
    """Ponto de mundo onde o personagem pisa quando esta parado nessa celula."""
    return pygame.Vector2((col + 0.5) * settings.TILE, (row + 0.5) * settings.TILE)
