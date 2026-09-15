# Configurações

Tudo que dá para ajustar no jogo e no agente LLM, sem mexer na lógica: parâmetros de linha de
comando, variáveis de ambiente e os arquivos de configuração. No fim há receitas para os ajustes
mais comuns e os cuidados que evitam quebrar alguma coisa.

- [Onde fica cada ajuste](#onde-fica-cada-ajuste)
- [Linha de comando](#linha-de-comando)
- [Variáveis de ambiente e .env](#variáveis-de-ambiente-e-env)
- [Jogo: farm/settings.py](#jogo-farmsettingspy)
- [Cultivos: farm/crops.py](#cultivos-farmcropspy)
- [Estações: farm/seasons.py](#estações-farmseasonspy)
- [Agente LLM: llm_agent/settings.py](#agente-llm-llm_agentsettingspy)
- [Prompts: prompts/](#prompts-prompts)
- [Receitas](#receitas)
- [Cuidados](#cuidados)

## Onde fica cada ajuste

| O que você quer mudar | Onde |
| --- | --- |
| a semente de uma partida | `--seed`, `FARM_SEED` ou `SEED` em `farm/settings.py` |
| estamina, custos, inventário inicial | `farm/settings.py` |
| loja: promoções, caixa, saturação | `farm/settings.py` |
| duração das estações | `farm/settings.py` (`SEASON_DAYS`) |
| o que cada estação muda | `farm/seasons.py` |
| prazos, validade e preços dos cultivos, fertilizante | `farm/crops.py` |
| janela, cores, painel | `farm/settings.py` |
| modelo, timeout, dias, velocidade, pastas do agente | `llm_agent/settings.py` ou flags do `run_llm.py` |
| o texto que o LLM recebe | `prompts/prompt_inicial.md` e `prompts/prompt_gaming.md` |
| a chave do OpenRouter | `.env` na raiz |

**Ordem de prioridade:** a linha de comando ganha do ambiente, que ganha do arquivo de settings. Os
arquivos `settings.py` são só valores, sem lógica: edite, salve e rode de novo.

## Linha de comando

### `main.py` — jogar no teclado

| Parâmetro | Padrão | O que faz |
| --- | --- | --- |
| `--seed N` | `FARM_SEED`, depois `SEED` | semente do cenário da loja |

### `run_llm.py` — partida jogada por um LLM

| Parâmetro | Padrão (em `llm_agent/settings.py`) | O que faz |
| --- | --- | --- |
| `--seed N` | a do jogo | semente do cenário |
| `--days N` | `DAYS` = 121 | quantos dias jogar |
| `--model ID` | `MODEL` = `openai/gpt-5.6-luna` | id do modelo no OpenRouter |
| `--mode` | `MODE` = `principal` | `principal` ou `sem_memoria` |
| `--knowledge ARQ` | — | `.txt` de base de conhecimento, só na chamada de estratégia |
| `--timeout S` | `API_TIMEOUT_SECONDS` = 360 | espera máxima por chamada |
| `--attempts N` | `API_MAX_ATTEMPTS` = 3 | tentativas quando a resposta chega mas não serve |
| `--speed X` | `GAME_SPEED` = 2 | velocidade das ações na tela |
| `--no-video` | `VIDEO` = True | não grava o MP4 |
| `--realtime` | `REALTIME` = False | roda a 60 fps de verdade |
| `--headless` | — | sem janela (define `SDL_VIDEODRIVER=dummy`) |
| `--allow-sleep` | — | deixa o Windows suspender durante a run |
| `--runs-dir PASTA` | `RUNS_DIR` = `runs_llm/` | onde criar a pasta da run |

`venv/Scripts/python.exe run_llm.py --help` lista tudo com os padrões atuais.

### `examples/`

| Script | Parâmetros |
| --- | --- |
| `scripted_run.py` | `--seed N`, `--no-video` |
| `random_agent.py` | `--seed N`, `--days N` (padrão 15), `--no-video` |

## Variáveis de ambiente e .env

| Variável | Onde vale | O que faz |
| --- | --- | --- |
| `FARM_SEED` | jogo, scripts, agente | semente, quando não há `--seed` (nome configurável em `SEED_ENV`) |
| `OPEN_ROUTER_API_KEY` | agente | chave do OpenRouter; lida do ambiente ou do `.env` |
| `SDL_VIDEODRIVER=dummy` | jogo, scripts | roda sem janela; o `--headless` do `run_llm.py` já faz isso |

O `.env` fica na raiz, está no `.gitignore` e aceita uma variável por linha (`#` comenta; aspas são
removidas):

```
OPEN_ROUTER_API_KEY=sua-chave-aqui
```

## Jogo: `farm/settings.py`

Mudar estes valores **muda as regras** do jogo — para todas as formas de jogar, inclusive o agente
LLM, que lê os mesmos números para montar o prompt.

### Semente

| Nome | Padrão | O que faz |
| --- | --- | --- |
| `SEED` | `2026` | semente padrão; `None` sorteia uma a cada abertura e grava no nome do log |
| `SEED_ENV` | `"FARM_SEED"` | nome da variável de ambiente lida antes do `SEED` |

### Estamina e inventário

| Nome | Padrão | O que faz |
| --- | --- | --- |
| `STAMINA_MAX` | 160 | estamina por dia |
| `STAMINA_WALK` | 1 | custo de cada célula andada |
| `STAMINA_PLANT` | 2 | custo de plantar |
| `STAMINA_HARVEST` | 1 | custo de colher |
| `STAMINA_CLEAR` | 2 | custo de arrancar planta podre |
| `STAMINA_FERTILIZE` | 2 | custo de fertilizar |
| `FERTILIZERS_PER_DAY` | 3 | fertilizantes que dá para usar por dia |
| `STARTING_SEEDS` | 1 | sementes iniciais de cada tipo |
| `STARTING_FERTILIZER` | 2 | fertilizantes iniciais |

Os limites de inventário (20 sementes por tipo, 9 fertilizantes) ficam em `farm/crops.py`.

### Loja

| Nome | Padrão | O que faz |
| --- | --- | --- |
| `PROMO_ITEM_CHANCES` | `((1, .40), (2, .25), (3, .10))` | chance de 1, 2 ou 3 itens em promoção no dia; o que sobra é dia sem promoção |
| `PROMO_DISCOUNTS` | `((1, .50), (2, .30), (3, .15), (5, .05))` | peso de cada desconto, sorteado por item |
| `PROMO_SMALL_PRICE` | 3 | abaixo desse preço, o desconto é sempre o menor |
| `MIN_PRICE` | 1 | preço mínimo de qualquer item |
| `MARKET_DAILY_BUDGET` | 200 | moedas que a loja tem por dia para pagar colheita |
| `SUPPLY_DEMAND_START_DAY` | 11 | dia em que a saturação de preço passa a valer |
| `SUPPLY_DEMAND_DAILY_UNITS` | 7 | unidades do mesmo cultivo num dia que disparam a saturação |
| `SUPPLY_DEMAND_DROP` | 1 | moedas a menos por unidade vendida com o mercado saturado |
| `SUPPLY_DEMAND_RECOVERY` | 1 | moedas recuperadas por dia sem vender o cultivo |

As estações podem sobrepor caixa, chances de promoção e descontos (ver `farm/seasons.py`).

### Tempo, dias e estações

| Nome | Padrão | O que faz |
| --- | --- | --- |
| `SEASON_DAYS` | 30 | duração de cada estação |
| `SEASON_BLEND` | `{4: .2, 3: .4, 2: .6, 1: .8}` | opacidade do fundo da próxima estação nos últimos dias |
| `FIRST_DAY` | 1 | dia em que a partida começa |
| `SLEEP_TRANSITION` | 0.6 | segundos da tela de transição ao dormir |
| `FPS` | 60 | quadros por segundo |

### Personagem

| Nome | Padrão | O que faz |
| --- | --- | --- |
| `PLAYER_START_CELL` | `(17, 12)` | onde o jogador começa (a porta da casa) |
| `PLAYER_SPEED` | 396 | pixels por segundo (~0,13 s por célula) |
| `PLAYER_ANIM_FPS` | 15 | velocidade da animação de corrida; acompanhe o `PLAYER_SPEED` |
| `PLAYER_IDLE_FPS` | 5 | animação parado |
| `ACTION_ANIM_FPS` / `ACTION_FRAMES` | 8 / 4 | animação de plantar/colher/fertilizar (4/8 = 0,5 s) |
| `PLAYER_HEIGHT` | 110 | altura do sprite |
| `PLAYER_SHADOW_RATIO` / `PLAYER_SHADOW_ALPHA` | 0.9 / 0.8 | largura e opacidade da sombra |

### Janela e mundo

| Nome | Padrão | O que faz |
| --- | --- | --- |
| `SCREEN_SIZE` | `(2000, 1000)` | tamanho da janela; precisa manter a proporção 2:1 do mundo |
| `WORLD_SIZE` | `(2000, 1000)` | tamanho do mapa; é o tamanho das imagens de fundo — não mude |
| `TILE` | 50 | tamanho da célula; o mapa e as zonas foram desenhados para ele — não mude |

Se a janela não couber no monitor, o SDL já reduz sozinho (flag `SCALED`). O próprio `settings.py`
indica que `SCREEN_SIZE = (1000, 500)` continua funcionando e só reduz o desenho.

### Mapa

| Nome | O que faz |
| --- | --- |
| `PLANTABLE_AREAS` | as duas hortas, como pares de cantos inclusivos |
| `WALKABLE_AREAS` | casa, loja e caminhos; a união com as hortas é onde dá para pisar |

Ver o aviso sobre o mapa em [Cuidados](#cuidados) antes de mexer aqui.

### Logs e visual

| Nome | O que faz |
| --- | --- |
| `LOGS_DIR` | pasta dos logs das partidas (`logs/`) |
| `SPOILED_LOG` | nome do histórico de células estragadas |
| `ASSETS_DIR`, `BACKGROUND_IMAGE`, `CHARACTER_DIR` | de onde vêm as imagens |
| `GROWTH_BAR_*`, `FRESH_BAR_*` | barrinhas de crescimento e de validade |
| `BOARD_*`, `SEASON_BOARD_*` | quadro de preços e indicador de estação |
| `HUD_*`, `PANEL_*`, `SLOT_*`, `STAMINA_BAR*` | painel inferior, inventário e barra de estamina |
| `MENU_*`, `OVERLAY_COLOR`, `GRID_*`, `ZONE_*` | menus, tela de derrota, grid e zonas |

Cores são tuplas RGB ou RGBA (o quarto valor é a opacidade, de 0 a 255).

## Cultivos: `farm/crops.py`

Cada cultivo é uma linha em `CROPS`:

```python
Crop("batata", "Batata", grow_days=3, shelf_days=3, fert_grow_cut=2,
     fert_shelf_bonus=2, sell_price=6, seed_price=4, stock_range=(1, 35)),
```

| Campo | O que faz |
| --- | --- |
| `grow_days` | dias para ficar pronto |
| `shelf_days` | dias que aguenta pronto antes de apodrecer |
| `fert_grow_cut` | dias a menos para crescer com fertilizante |
| `fert_shelf_bonus` | dias a mais de validade com fertilizante |
| `sell_price` | quanto a loja paga por unidade |
| `seed_price` | quanto a semente custa; também é o piso da saturação |
| `stock_range` | faixa do estoque diário de sementes na loja |

| Constante | Padrão | O que faz |
| --- | --- | --- |
| `FERTILIZER_PRICE` | 21 | preço do fertilizante |
| `FERTILIZER_STOCK` | `(1, 6)` | faixa do estoque diário de fertilizante |
| `FERTILIZER_LIMIT` | 9 | quantos fertilizantes o jogador carrega |
| `SEED_LIMIT` | 20 | quantas sementes de cada tipo o jogador carrega |

Mudar números dos cultivos existentes é seguro. Criar um cultivo novo exige as imagens em
`Assets/props` e `Assets/icons` e ajustar os prompts (ver [Cuidados](#cuidados)).

## Estações: `farm/seasons.py`

Cada estação é uma `Season` em `SEASONS`, na ordem do ano:

| Campo | Exemplo | O que faz |
| --- | --- | --- |
| `grow_delta` | `1` no outono | dias a mais para crescer o que for plantado nela |
| `shelf_days` | `{"cenoura": 1, ...}` no verão | validade no lugar da padrão, por cultivo |
| `can_plant` | `False` no inverno | se dá para plantar; na virada para uma estação sem plantio, tudo no chão apodrece |
| `fertilizer_works` | `False` no inverno | se o fertilizante funciona |
| `sell_multiplier` | `{"trigo": 2.5, ...}` no inverno | multiplica o preço de venda |
| `daily_budget` | `300` no inverno | caixa da loja no lugar do `MARKET_DAILY_BUDGET` |
| `promo_item_chances`, `promo_discounts` | tabelas próprias no inverno | sobrepõem as do `settings.py` |
| `effect` | `"a colheita estraga rápido"` | frase curta do indicador na tela |

`None` ou dicionário vazio significa "usa o padrão".

## Agente LLM: `llm_agent/settings.py`

Tudo que tem flag no `run_llm.py` pode ser sobreposto na linha de comando.

### Modelo e chamadas

| Nome | Padrão | O que faz |
| --- | --- | --- |
| `MODEL` | `"openai/gpt-5.6-luna"` | modelo padrão (`--model`) |
| `TEMPERATURE` | `None` | `None` não envia; alguns modelos não aceitam o parâmetro |
| `REASONING_EFFORT` | `None` | `"low"`, `"medium"` ou `"high"` nos modelos que aceitam |
| `RESPONSE_FORMAT_JSON` | `True` | pede JSON ao provedor; se o modelo não aceitar, o parser extrai do texto |
| `MAX_TOKENS` | 16000 | teto de tokens da resposta |
| `INCLUDE_REASONING` | `True` | grava o raciocínio do modelo junto da resposta |
| `API_TIMEOUT_SECONDS` | 360 | espera por chamada (`--timeout`); estourou, o jogador dorme e não há nova tentativa |
| `API_MAX_ATTEMPTS` | 3 | tentativas para JSON inválido, 429 e 5xx (`--attempts`) |
| `API_RETRY_WAIT_SECONDS` | 5 | espera entre tentativas |
| `API_KEY_ENV` | `"OPEN_ROUTER_API_KEY"` | nome da variável da chave |
| `OPENROUTER_URL` | endpoint de chat do OpenRouter | para onde as chamadas vão |

### Partida

| Nome | Padrão | O que faz |
| --- | --- | --- |
| `DAYS` | 121 | dias da partida (`--days`) |
| `MODE` | `"principal"` | `sem_memoria` manda o conhecimento sempre vazio (`--mode`) |
| `STRATEGY_MAX_CHARS` | 200 | tamanho máximo da estratégia reinjetada todo dia |
| `KNOWLEDGE_MAX_LINES` | 15 | linhas do bloco de conhecimento |
| `DIARY_DAYS` | 5 | dias no diário que o prompt mostra |
| `STAMINA_RESERVE` | 1 | estamina que o jogador sempre guarda para chegar vivo na cama |

### Execução e pastas

| Nome | Padrão | O que faz |
| --- | --- | --- |
| `GAME_SPEED` | 2.0 | velocidade das ações e do vídeo (`--speed`); não muda regra; teto ~7,4 |
| `REALTIME` | `False` | `False` roda acelerado, sem esperar o relógio (`--realtime` liga) |
| `VIDEO` | `True` | grava `video.mp4` (`--no-video` desliga) |
| `RUNS_DIR` | `runs_llm/` | pasta das runs (`--runs-dir`) |
| `GAME_LOGS_DIR` | `logs/` | para onde vão as cópias dos logs do jogo ao fim da run |
| `GAME_LOGS_PREFIX` | `"IA_{modelo}_"` | prefixo dessas cópias |
| `PROMPT_STRATEGY` / `PROMPT_DAY` | `prompts/prompt_inicial.md` / `prompt_gaming.md` | templates usados |

## Prompts: `prompts/`

Os dois prompts do agente são Markdown lidos a cada run — editar o arquivo muda a próxima partida sem
tocar em Python. Cada um tem as seções `# SYSTEM` e `# USER`, e os `{PLACEHOLDERS}` em maiúsculas
são preenchidos com números calculados do jogo.

- Um placeholder que o código não conhece faz a run **falhar antes de abrir o jogo** — erro de
  digitação aparece na hora.
- Chaves do JSON de exemplo (`{"plano": ...}`) não são placeholders e ficam intactas.
- Cada run guarda uma cópia dos templates que usou em `runs_llm/<run>/prompts/`.

Os placeholders disponíveis estão listados em [prompts/README.md](../prompts/README.md).

## Receitas

**Um cenário diferente a cada partida**

```python
# farm/settings.py
SEED = None
```

O número sorteado aparece no nome do log; `--seed` com ele repete a partida.

**Jogo mais fácil ou mais difícil**

```python
# farm/settings.py
STAMINA_MAX = 200          # mais fôlego por dia
STARTING_SEEDS = 3         # começa com 3 de cada
MARKET_DAILY_BUDGET = 400  # a loja paga mais por dia
SUPPLY_DEMAND_START_DAY = 31   # sem saturação no primeiro mês
```

**Estações mais curtas**

```python
# farm/settings.py
SEASON_DAYS = 10
```

O prazo por cultivo que o agente recebe se ajusta sozinho; o texto "Cada estação dura 30 dias" em
`prompts/prompt_inicial.md` precisa ser editado à mão.

**Personagem mais rápido no jogo manual**

```python
# farm/settings.py
PLAYER_SPEED = 594      # 1,5x
PLAYER_ANIM_FPS = 22    # acompanha a velocidade
```

Nos scripts e no agente prefira `speed` / `--speed`, que acelera tudo sem mudar o jogo.

**Trocar o modelo do agente**

```bash
venv/Scripts/python.exe run_llm.py --model openai/gpt-5.6-luna --days 30 --headless
```

Para deixar fixo, mude `MODEL` em `llm_agent/settings.py`. Modelos de raciocínio aceitam
`REASONING_EFFORT = "low"` para responder mais rápido e mais barato.

**Run longa estável**

```bash
venv/Scripts/python.exe run_llm.py --seed 42 --days 120 --headless
```

Sem janela o Windows não fecha o processo como travado, e o PC não suspende enquanto a run existe.

**Run rápida só para testar**

```bash
venv/Scripts/python.exe run_llm.py --days 3 --no-video --headless --speed 7
```

**Modelo lento ou provedor instável**

```bash
venv/Scripts/python.exe run_llm.py --timeout 600 --attempts 5
```

**Comparar modelos de forma justa**

Mesmo `--seed`, mesmo `--days`, mesmos `settings.py` e mesmos prompts. A velocidade não interfere
no resultado. O `config.json` de cada run guarda os parâmetros do agente e a cópia dos prompts, mas
**não** os valores de `farm/settings.py`: se mudar regras do jogo, anote.

## Cuidados

- **A semente não cobre as regras.** Ela só fixa o sorteio de estoque e promoções. Duas partidas com
  a mesma semente e `settings.py` diferentes não são comparáveis.
- **Mapa acoplado.** Mudar `PLANTABLE_AREAS`, `WALKABLE_AREAS` ou `PLAYER_START_CELL` exige ajustar
  junto:
  - `scripting/session.py`: `SHOP = (21, 12)` e `HOUSE` (que é o `PLAYER_START_CELL`);
  - `llm_agent/grammar.py`: `ZONE_CELLS` (entradas das hortas em (6,8) e (33,8)) e `PLOT_COLUMNS`;
  - os prompts, que citam "49 células" por horta;
  - a arte do fundo, que desenha as hortas, a casa e a loja nesses lugares.
- **Números escritos nos prompts.** Quase tudo vem calculado, mas "30 dias" por estação, "49
  células" por horta e a lista de cultivos da gramática estão escritos no texto dos `.md`.
- **Cultivo novo** precisa das imagens (`Assets/props/<cultivo> 1..4.png`, ícones de semente e do
  vegetal em `Assets/icons`) e da lista de cultivos da gramática nos prompts.
- **`PLAYER_SPEED` muda o teto de `speed`.** O limite dos scripts é uma célula por quadro:
  `Session.max_speed()` = `FPS × (TILE − 1) / PLAYER_SPEED`.
- **`SCREEN_SIZE` precisa manter 2:1**, e `WORLD_SIZE` precisa ser múltiplo de `TILE`: o jogo recusa
  abrir se não for.
