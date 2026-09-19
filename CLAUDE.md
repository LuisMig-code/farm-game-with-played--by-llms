# CLAUDE.md

Jogo de fazenda 2D em grid (Python 3.14 + pygame-ce) que pode ser jogado por uma pessoa, por um
script ou por um LLM via OpenRouter. O projeto existe para comparar como modelos planejam sob
restrição de energia, prazo, estações e mercado. Visão geral no [README.md](README.md); índice da
documentação em [docs/README.md](docs/README.md).

## Regras fixas

- **`farm/` é o jogo e não se edita.** O que o agente precisa entra por fora:
  - `scripting.Session` dirige o jogo pelos mesmos menus e teclas de quem joga no teclado;
  - configuração trocada em runtime, sem mexer no arquivo (ex.: `game_settings.LOGS_DIR = ...` em
    `llm_agent/runner.py`);
  - método sombreado na instância quando é preciso observar o jogo (`_input_direction` na
    `Session`, `game.run_log.record` em `llm_agent/transactions.py`).
- **Idioma:** documentação, prompts, mensagens ao modelo, commits e PRs em português (PT-BR).
  Comentários e docstrings em português **sem acento**; texto que o modelo ou o usuário leem, com
  acento. Classes e funções em inglês, variáveis locais em português — siga o arquivo ao redor.
- **Commit e PR só quando o usuário pedir.**
- **A chave** (`OPEN_ROUTER_API_KEY`, lida do ambiente ou do `.env`) nunca aparece em log, comando
  ou saída. `.env`, `runs_llm/`, `logs/` e `cenarios/` ficam fora do git.

## Onde fica cada coisa

| Caminho | O que é |
| --- | --- |
| `farm/` | o jogo: regras, mapa, loja, estações, desenho; `farm/settings.py` tem os números das regras |
| `scripting/` | jogar por código (`session.py`) e gravar vídeo (`recorder.py`) |
| `llm_agent/runner.py` | a run: chamada de estratégia, laço dos dias, pasta da run, `_finish` |
| `llm_agent/facts.py` | todo fato calculado que entra nos prompts |
| `llm_agent/grammar.py`, `executor.py` | a linguagem do plano e o interpretador (células, caminho, stamina) |
| `llm_agent/responses.py` | conferência das respostas: estratégia, dia, conhecimento |
| `llm_agent/openrouter.py` | o cliente HTTP: prazo, repetição, erro fatal |
| `llm_agent/run_logs.py`, `transactions.py` | a pasta da run, os CSVs e as transações lidas do jogo |
| `llm_agent/settings.py` | configuração do agente: modelo, tetos, tentativas, velocidade, pastas |
| `seed_scenarios/` | o simulador de cenários: estoque e promoção de cada dia de uma semente, sem abrir o jogo ([docs/CENARIOS.md](docs/CENARIOS.md)) |
| `prompts/` | os dois prompts em `.md`, lidos a cada run |
| `run_llm.py`, `main.py` | rodar um LLM; jogar no teclado |
| `simulate_seed.py`, `simulate_range.py` | o cenário de uma semente; o de um intervalo, em paralelo |
| `tests/` | as suítes sem rede (agente e simulador) e o conferidor de links ([tests/README.md](tests/README.md)) |
| `docs/`, `examples/` | a documentação; dois scripts prontos |
| `runs_llm/`, `logs/`, `cenarios/` | saídas das runs, dos logs do jogo e do simulador (fora do git) |

## Comandos

```bash
venv/Scripts/python.exe main.py --seed 42                     # jogar no teclado
venv/Scripts/python.exe run_llm.py --days 121 --seed 42 --headless --model google/gemini-3.8-flash
venv/Scripts/python.exe simulate_seed.py --seed 42            # cenário da loja de uma semente
venv/Scripts/python.exe simulate_range.py --from 1 --to 1000  # um intervalo, em paralelo
venv/Scripts/python.exe tests/check_llm.py                    # suíte do agente, ~8 min, sem rede
venv/Scripts/python.exe tests/check_scenarios.py              # suíte do simulador, ~20 s
venv/Scripts/python.exe tests/check_links.py                  # links e âncoras dos .md
```

`run_llm.py --help` lista as flags (`--reasoning-effort`, `--speed`, `--no-video`, ...); a tabela
completa, com os valores possíveis, está em [docs/AGENTE_LLM.md](docs/AGENTE_LLM.md). O ambiente é
Windows: `venv/Scripts/python.exe`, e caminhos curtos por causa do limite de 260 caracteres.

## Mexendo no agente

Rode a suíte do agente inteira (`tests/check_llm.py`) depois de mudar `llm_agent/`, `scripting/` ou
`prompts/`, e o `tests/check_links.py` depois de mexer em `.md`. O que costuma quebrar:

- **Fato calculado ganha de nota escrita.** Número de regra (preço, prazo, custo, saturação) sai de
  `farm/settings.py` e de `CROPS`, calculado em `facts.py`; nunca escrito à mão no prompt. Exemplo
  numérico no prompt tem teste que o confere contra o jogo (bloco 18).
- **Placeholder novo** em `prompts/*.md`: preencher em `facts.strategy_values`/`day_values` **e**
  documentar em `prompts/README.md`. Placeholder desconhecido derruba a run antes de abrir o jogo.
- **Gramática:** `grammar.py`, o bloco "GRAMÁTICA DO PLANO" de `prompts/prompt_gaming.md`,
  `docs/GRAMATICA.md` e `docs/AGENTE_LLM.md` mudam juntos. Os `ERRO_GRAMATICA` das runs ficam em
  `erros_gramatica.csv` e costumam ser pedidos de feature.
- **Flag nova no `run_llm.py`:** entra nas três tabelas de flags (`docs/AGENTE_LLM.md`,
  `docs/COMO_JOGAR.md`, `docs/CONFIGURACOES.md`) e no `config.json` da run.
- **Chaves do JSON de resposta** (`estrategia`, `plano`, ...) não se renomeiam: o runner as exige.
- **Vídeo:** `scripting/recorder.py` grava MP4 fragmentado; `-frag_duration` e `-flush_packets 1`
  ficam, senão o vídeo de uma run morta à força volta a não abrir.
- **Velocidade:** `--speed` vai até `Session.max_speed()` (~7,4); acima disso um passo emenda no
  seguinte.
- **Falhas:** dia sem resposta dorme sem repetir; a estratégia repete até 10 vezes e, sem ela, a run
  não começa; 402/401/403 param a run na hora, e o `_finish` salva vídeo, logs e resumo.

## Mexendo no simulador de cenários

Rode `tests/check_scenarios.py` depois de mudar `seed_scenarios/` ou os dois scripts.

- **O sorteio é o do jogo.** O simulador cria o `Market` de `farm/market.py` e faz as mesmas chamadas
  do `Game`: `Market(seed)` na largada e `new_day(dia)` a cada noite. Nunca reimplemente o sorteio.
  O bloco 1 confere dia a dia contra uma partida de verdade.
- **Colunas saem do jogo:** itens de `BUY_PRICES`, estações de `SEASONS`. A coluna `regras` é o
  hash dos arquivos do sorteio em `farm/`; se ela muda, o que está em `cenarios/` é refeito.
- **Pool no Windows:** cada processo reimporta o script principal, então `run_batch` com mais de um
  processo só roda atrás de `if __name__ == "__main__"`. Por isso a suíte testa o paralelo por
  subprocesso e nunca abre o pool dentro dela.

## Rodando experimentos

- Cada run gasta crédito do OpenRouter e leva de ~20 min a ~4 h.
- Comparações usam **semente 42** e 121 dias, salvo pedido diferente. A 42 é uma loja típica: 158
  promoções contra a média de 160 das sementes 0–999, que vão de 128 a 197. Para escolher outros
  cenários, use `simulate_range.py` e `cenarios/resumo.csv`.
- Runs idênticas variam muito (`gpt-5.6-luna`: 904, 1858 e 2546 moedas). Uma run só não prova
  nada; compare também as métricas de mecanismo — saturação, dias parados, fertilizante, estoque.
- Em paralelo, um processo por run (o `LOGS_DIR` do jogo é global), entrando com 30–60 s de
  diferença. Oito ao mesmo tempo já rodaram na máquina de desenvolvimento.
- Modelo novo: confira o id e os `supported_parameters` em `https://openrouter.ai/api/v1/models` e
  acompanhe a estratégia e o dia 1. Modelo que queima os 16.000 tokens raciocinando sem responder
  pede `--reasoning-effort low`.
- Parar: Ctrl+C fecha a run direito; à força, vídeo e CSVs sobram, mas `LEIAME.md` e `resumo.csv`
  não. Pasta de run interrompida só se apaga quando o usuário pede.
- Ler o resultado: `runs_llm/<run>/` (`dias.csv`, `transacoes.csv`, `precos.csv`, `comandos.csv`,
  `chamadas.csv`, `dias/dia_NNN/estado.json`) e `runs_llm/resumo.csv`. Os modelos costumam chegar
  ao dia 90 com o caixa quase zerado: o placar sai da mochila levada para o inverno (dia 91).

## Git

- Cada mudança num branch novo, criado da `origin/main` atualizada (`git fetch` antes). Os PRs são
  mergeados rápido: confira com `gh pr view <n>` antes de reaproveitar um branch.
- Título de commit `Área: resumo` (ex.: `Agente LLM: ...`, `Video: ...`), em ASCII; o corpo diz o
  porquê e como foi verificado. PR em PT-BR, com uma seção de verificação.
- O working tree usa CRLF (`core.autocrlf=true`).
