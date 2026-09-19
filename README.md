# Farm Game com LLMs

Um jogo de fazenda 2D em grid, feito em Python com [pygame-ce](https://pyga.me/), que pode ser
jogado de três jeitos:

- **por você**, no teclado;
- **por um script** Python, com a partida gravada em vídeo;
- **por um modelo de linguagem (LLM)** via [OpenRouter](https://openrouter.ai/), que recebe o estado
  da fazenda todo dia e devolve o plano do dia.

O projeto nasceu para comparar como diferentes LLMs planejam sob restrição de energia, prazo,
estações e mercado — e tudo o que acontece numa partida fica registrado em logs e CSVs.

## O jogo em 30 segundos

- Você acorda em casa com **160 de estamina**. Andar uma célula custa 1, plantar 2, colher 1.
- Planta nas duas hortas, **dorme** para as plantas crescerem, colhe, **vende na loja** e compra
  mais sementes.
- **Estamina zero é derrota** — inclusive em cima da cama. A viagem de volta precisa caber no dia.
- 5 cultivos com prazos e validades diferentes, **4 estações** de 30 dias (no inverno não se
  planta, mas a venda vale até 3x mais) e uma loja com promoção, estoque, caixa diário e saturação
  de preço.

O guia completo está em [docs/COMO_JOGAR.md](docs/COMO_JOGAR.md).

## Requisitos

- **Python 3.14** (a versão usada no desenvolvimento).
- Windows, macOS ou Linux. Os comandos abaixo usam o caminho do Windows; em macOS/Linux troque
  `venv/Scripts/python.exe` por `venv/bin/python`.
- Uma chave do **OpenRouter** — só para os agentes LLM.

## Instalação

```bash
git clone https://github.com/LuisMig-code/farm-game-with-played--by-llms.git
cd farm-game-with-played--by-llms
python -m venv venv
venv/Scripts/python.exe -m pip install -r requirements.txt
```

Para gravar vídeo (scripts e agentes LLM), instale também:

```bash
venv/Scripts/python.exe -m pip install -r requirements-agent.txt
```

| Arquivo | Pacotes | Para quê |
| --- | --- | --- |
| `requirements.txt` | `pygame-ce` | o jogo |
| `requirements-agent.txt` | `imageio-ffmpeg` | gravar MP4 (traz um ffmpeg próprio, nada a instalar à parte) |

## Jogando

### 1. Você joga

```bash
venv/Scripts/python.exe main.py
venv/Scripts/python.exe main.py --seed 42
```

| Tecla | Ação |
| --- | --- |
| `W A S D` / setas | anda; com menu aberto, troca a opção |
| `Espaço` / `Enter` | age na célula: dormir, abrir a loja, plantar, fertilizar, colher, remover |
| `ESC` | volta/fecha o menu; sem menu, sai do jogo |
| `G` | mostra/esconde o grid e as zonas |
| `R` | na tela de derrota, recomeça |

`--seed` fixa o cenário da loja (estoque e promoções de cada dia): a mesma semente dá a mesma loja
em qualquer partida. Ver [docs/SEMENTE.md](docs/SEMENTE.md).

### 2. Um script joga

```bash
venv/Scripts/python.exe examples/scripted_run.py --seed 7
venv/Scripts/python.exe examples/random_agent.py --seed 7 --days 20
```

Ou escreva o seu com a biblioteca `scripting`:

```python
from scripting import Session, HOUSE, SHOP

with Session(seed=42, record="logs/partida.mp4") as s:
    s.walk_to((6, 8)).plant("batata")
    s.walk_to(HOUSE).sleep_until(day=4)
    s.walk_to((6, 8)).harvest()
    s.walk_to(SHOP).sell("batata")
```

Ver [docs/SCRIPTING.md](docs/SCRIPTING.md).

### 3. Um LLM joga

Crie um arquivo `.env` na raiz (ele está no `.gitignore` e nunca é commitado):

```
OPEN_ROUTER_API_KEY=sua-chave-aqui
```

E rode:

```bash
venv/Scripts/python.exe run_llm.py --seed 42 --days 30 --headless
```

| Flag | Padrão | O que faz |
| --- | --- | --- |
| `--seed` | a do jogo | semente do cenário |
| `--days` | 121 | quantos dias jogar |
| `--model` | `openai/gpt-5.6-luna` | qualquer id de modelo do OpenRouter |
| `--mode` | `principal` | `sem_memoria` desliga o bloco de conhecimento |
| `--knowledge` | — | `.txt` com aprendizados de runs anteriores |
| `--timeout` | 360 | segundos de espera por chamada |
| `--speed` | 2 | velocidade das ações na tela (1 = a do jogo) |
| `--headless` | — | sem janela (o vídeo é gravado igual) |
| `--no-video` | — | não grava o MP4 |

A lista completa e o funcionamento do agente estão em [docs/AGENTE_LLM.md](docs/AGENTE_LLM.md).

## Cenários por semente

A semente fixa o estoque e as promoções de cada dia, e dá para ver esse cenário sem jogar. O
simulador usa o próprio `Market` do jogo:

```bash
venv/Scripts/python.exe simulate_seed.py --seed 42              # uma semente, dia a dia
venv/Scripts/python.exe simulate_range.py --from 1 --to 1000    # um intervalo, em paralelo
```

O segundo script pula as sementes que já estão no log. No fim, mostra a média de promoções e as
sementes com menos e com mais, o que ajuda a escolher cenários de teste. Ver
[docs/CENARIOS.md](docs/CENARIOS.md).

## Configurações

Tudo que dá para ajustar mora em arquivos de configuração, sem precisar mexer na lógica:

| Arquivo | O que ajusta |
| --- | --- |
| [`farm/settings.py`](farm/settings.py) | regras e visual do jogo: estamina, inventário inicial, semente, loja, estações, janela |
| [`farm/crops.py`](farm/crops.py) | cultivos: prazos, validade, preços, estoque, fertilizante |
| [`farm/seasons.py`](farm/seasons.py) | o que cada estação muda |
| [`llm_agent/settings.py`](llm_agent/settings.py) | o agente LLM: modelo, timeout, dias, velocidade, pastas |
| [`seed_scenarios/settings.py`](seed_scenarios/settings.py) | o simulador de cenários: pasta, dias, processos |
| [`prompts/`](prompts) | os prompts do LLM, em Markdown, lidos a cada run |
| `.env` | a chave do OpenRouter |

O que cada valor faz, os limites e receitas de ajuste estão em
[docs/CONFIGURACOES.md](docs/CONFIGURACOES.md).

## Onde ficam os resultados

| Pasta | Conteúdo |
| --- | --- |
| `logs/` | partidas no teclado e por script: `run_<id>_semente<N>_<data>.log` e `.csv`, com cada ação. Cópias das runs LLM entram com o prefixo `IA_<modelo>_` |
| `runs_llm/` | uma pasta por run de LLM: prompts, respostas, CSVs por dia, preços, transações, vídeo e um `LEIAME.md` com o resumo |
| `cenarios/` | o simulador de cenários: um CSV por semente com um dia por linha, `resumo.csv` com uma linha por semente e `execucoes.csv` |

Ver [docs/LOGS.md](docs/LOGS.md), a seção "Pastas" de [docs/AGENTE_LLM.md](docs/AGENTE_LLM.md) e
[docs/CENARIOS.md](docs/CENARIOS.md).

## Estrutura do projeto

```
main.py              abre o jogo no teclado
run_llm.py           roda uma partida jogada por um LLM
simulate_seed.py     o cenário da loja de uma semente, sem abrir o jogo
simulate_range.py    o mesmo para um intervalo de sementes, em paralelo
farm/                o jogo (regras, mapa, loja, estações, desenho)
scripting/           a camada que joga por código e grava vídeo
llm_agent/           o agente LLM: prompts, interpretador, logs
seed_scenarios/      o simulador de cenários: simulação, métricas e a pasta cenarios/
prompts/             os dois prompts do agente, em .md
examples/            dois scripts prontos usando a camada de scripting
tests/               as suítes sem rede (agente e simulador) e o conferidor de links
docs/                a documentação
Assets/              imagens do mapa, personagem, plantas e ícones
```

## Documentação

| Documento | Assunto |
| --- | --- |
| [COMO_JOGAR.md](docs/COMO_JOGAR.md) | guia do jogador e como rodar cada modo |
| [CONFIGURACOES.md](docs/CONFIGURACOES.md) | todos os parâmetros e ajustes |
| [GAME_RULES.md](docs/GAME_RULES.md) | estamina, dias, inventário, derrota |
| [CULTIVO.md](docs/CULTIVO.md) | plantar, crescer, fertilizar, validade |
| [COMERCIO.md](docs/COMERCIO.md) | preços, promoção, estoque, caixa, saturação |
| [ESTACOES.md](docs/ESTACOES.md) | o ano e o que cada estação muda |
| [CONTROLS.md](docs/CONTROLS.md) | teclas, mapa, zonas, personagem |
| [SEMENTE.md](docs/SEMENTE.md) | a semente que repete o cenário |
| [CENARIOS.md](docs/CENARIOS.md) | o cenário da loja de cada semente, simulado sem jogar |
| [LOGS.md](docs/LOGS.md) | os arquivos de cada partida |
| [SCRIPTING.md](docs/SCRIPTING.md) | jogar por código |
| [AGENTE_LLM.md](docs/AGENTE_LLM.md) | o agente LLM, flags, pastas das runs |
| [GRAMATICA.md](docs/GRAMATICA.md) | a linguagem de comandos do LLM |
| [ARQUITETURA-IA.md](docs/ARQUITETURA-IA.md) | o desenho anterior do agente (histórico) |
