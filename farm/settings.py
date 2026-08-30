"""Constantes globais do jogo. Sem logica, apenas valores."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "Assets"
LOGS_DIR = ROOT_DIR / "logs"

# O mapa inteiro e sempre visivel. Com a janela do mesmo tamanho do mundo,
# VIEW_SCALE fica em 1.0 (render 1:1, sem perda de nitidez); mudar SCREEN_SIZE
# para 1000x500 continua funcionando, so reduz o desenho.
WORLD_SIZE = (2000, 1000)
SCREEN_SIZE = (2000, 1000)
VIEW_SCALE = SCREEN_SIZE[0] / WORLD_SIZE[0]
assert SCREEN_SIZE[1] / WORLD_SIZE[1] == VIEW_SCALE, "janela e mundo com proporcoes diferentes"

TILE = 50
GRID_COLS = WORLD_SIZE[0] // TILE
GRID_ROWS = WORLD_SIZE[1] // TILE
assert GRID_COLS * TILE == WORLD_SIZE[0], "largura do mundo deve ser multipla de TILE"
assert GRID_ROWS * TILE == WORLD_SIZE[1], "altura do mundo deve ser multipla de TILE"

FPS = 60

BACKGROUND_IMAGE = "main-background.png"
CHARACTER_DIR = "character"

# Jogador
PLAYER_START_CELL = (17, 12)
PLAYER_HEIGHT = 110       # altura do sprite em pixels de mundo (~2 celulas)
PLAYER_SPEED = 396        # pixels de mundo por segundo (~0,13s por celula)
PLAYER_ANIM_FPS = 15      # acompanha PLAYER_SPEED, senao a passada patina

# Acoes do jogador (plantar/colher): 4 quadros, ~0,5s cada animacao
ACTION_ANIM_FPS = 8
ACTION_FRAMES = 4

# Estamina
STAMINA_MAX = 150
STAMINA_WALK = 1        # cobrado ao concluir cada celula
STAMINA_PLANT = 2
STAMINA_HARVEST = 1
STAMINA_CLEAR = 2        # arrancar uma planta estragada
STAMINA_FERTILIZE = 2
FERTILIZERS_PER_DAY = 3  # quantos o jogador pode usar por dia

# Inventario inicial
STARTING_SEEDS = 1      # de cada tipo
STARTING_FERTILIZER = 2

# Mercado
PROMO_ONE_ITEM_CHANCE = 0.3     # so 1 item em promocao
PROMO_TWO_ITEMS_CHANCE = 0.15    # exatamente 2 itens
PROMO_DISCOUNTS = ((1, 0.60), (2, 0.20), (3, 0.15), (5, 0.05))
PROMO_SMALL_PRICE = 3            # abaixo disso o desconto e sempre o menor
MIN_PRICE = 1                    # nenhum item pode sair de graca

MARKET_DAILY_BUDGET = 200        # moedas que a loja tem por dia para pagar colheita

SUPPLY_DEMAND_START_DAY = 11     # oferta/demanda so vale depois do dia 10
SUPPLY_DEMAND_DROP = 1           # moedas a menos por unidade vendida
SUPPLY_DEMAND_RECOVERY = 1       # moedas de volta por dia sem vender

# Dias
FIRST_DAY = 1
SLEEP_TRANSITION = 0.6  # segundos da tela entre um dia e outro

# Zonas do mapa, em celulas do grid. Cada area e um par de cantos (inclusivo),
# em qualquer ordem. A uniao de todas define onde o jogador pode pisar.
PLANTABLE_AREAS = (
    ((3, 2), (9, 8)),      # horta esquerda
    ((30, 8), (36, 2)),    # horta direita
)
WALKABLE_AREAS = {
    "casa": (((17, 12), (17, 12)),),
    "comercio": (((21, 12), (21, 12)),),
    "caminho": (
        ((6, 9), (6, 13)),     # descida da horta esquerda
        ((7, 13), (32, 13)),   # caminho horizontal em frente as construcoes
        ((33, 9), (33, 13)),   # descida da horta direita
    ),
}
ZONE_PLANTABLE_COLOR = (60, 200, 60, 89)    # verde, 35% de opacidade
ZONE_WALKABLE_COLOR = (150, 150, 150, 89)   # cinza, 35% de opacidade

# Barrinha de crescimento sob a planta, no rodape da celula
GROWTH_BAR_SIZE = (40, 6)
GROWTH_BAR_MARGIN = 4           # distancia ate a base da celula
GROWTH_BAR_BACK = (25, 22, 20)
GROWTH_BAR_COLOR = (240, 175, 60)   # ambar enquanto cresce
GROWTH_BAR_READY = (110, 205, 90)   # verde quando esta pronta para colher
GROWTH_BAR_BORDER = (10, 8, 6)

# Quadro de precos, alinhado ao grid nas linhas livres acima do comercio
BOARD_COLS = (19, 26)            # inclusivo
BOARD_ROWS = (0, 4)              # inclusivo
BOARD_ITEM_COL = 21              # primeira coluna de item
BOARD_BG_COLOR = (12, 10, 8, 205)
BOARD_BORDER_COLOR = (255, 235, 170, 90)
BOARD_TITLE_COLOR = (255, 235, 170)
BOARD_PRICE_COLOR = (255, 255, 255)
BOARD_PROMO_COLOR = (255, 205, 70)     # preco de compra em promocao
BOARD_SATURATED_COLOR = (240, 120, 105)  # preco de venda saturado
BOARD_OLD_PRICE_COLOR = (150, 145, 140)
BOARD_BUDGET_COLOR = (225, 225, 220)
BOARD_BUDGET_LOW_COLOR = (240, 120, 105)   # caixa do dia nao cobre nem o mais barato

# Barrinha de validade, acima da planta crescida
FRESH_BAR_SIZE = (40, 6)
FRESH_BAR_MARGIN = 4            # distancia ate o topo do sprite
FRESH_BAR_GOOD = (110, 205, 90)      # 3 dias ou mais
FRESH_BAR_WARN = (240, 175, 60)      # 2 dias
FRESH_BAR_URGENT = (240, 100, 90)    # ultimo dia

SPOILED_LOG = "celulas_estragadas.csv"

GRID_LINE_COLOR = (255, 255, 255, 70)
GRID_MAJOR_COLOR = (255, 255, 255, 130)  # linhas a cada MAJOR_EVERY celulas
GRID_MAJOR_EVERY = 5
GRID_HOVER_COLOR = (255, 240, 150, 60)
GRID_HOVER_BORDER = (255, 240, 150, 200)

HUD_COLOR = (255, 255, 255)
HUD_SHADOW = (0, 0, 0)
HUD_DIM_COLOR = (150, 150, 150)
HUD_FONT_SIZE = max(12, round(SCREEN_SIZE[1] * 0.026))
HUD_MARGIN = round(SCREEN_SIZE[1] * 0.016)

# Painel inferior, desenhado por cima do mapa (linhas 17-19 sao so grama).
PANEL_HEIGHT = 170
PANEL_TOP = SCREEN_SIZE[1] - PANEL_HEIGHT
PANEL_COLOR = (12, 10, 8, 190)
PANEL_BORDER = (255, 255, 255, 40)

SLOT_ICON_HEIGHT = 56
SLOT_WIDTH = 118
SLOTS_LEFT = 420
SLOTS_TOP = PANEL_TOP + 22

STAMINA_BAR = (24, PANEL_TOP + 80, 340, 26)
STAMINA_FULL_COLOR = (110, 205, 90)
STAMINA_LOW_COLOR = (215, 80, 60)
STAMINA_LOW_RATIO = 0.25
STAMINA_BACK_COLOR = (40, 40, 40)

MENU_BG_COLOR = (18, 16, 14, 235)
MENU_BORDER_COLOR = (255, 255, 255, 70)
MENU_SELECTED_COLOR = (255, 205, 90, 255)   # opaco: translucido sumia no fundo
MENU_SELECTED_TEXT = (25, 20, 15)           # texto escuro sobre o realce claro
MENU_DISABLED_COLOR = (130, 130, 130)

OVERLAY_COLOR = (0, 0, 0, 190)
