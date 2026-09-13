# LLMs jogando a fazenda

Um modelo de linguagem joga uma partida inteira pelo OpenRouter, na lógica do Projeto Fazenda:
**o LLM decide, o interpretador conta.** O modelo emite intenções de alto nível uma vez por dia; o
interpretador expande essas intenções em ações do jogo, resolve caminho e stamina, e devolve um
relatório do que deu certo e do que não deu.

A gramática, os códigos de retorno e o formato do feedback estão em [GRAMATICA.md](GRAMATICA.md).

## Rodando

```bash
venv/Scripts/python.exe -m pip install -r requirements-agent.txt
venv/Scripts/python.exe run_llm.py --seed 42 --days 30 --headless
```

A chave vem de `OPEN_ROUTER_API_KEY`, no ambiente ou no `.env` da raiz — que está no `.gitignore`.
A chave nunca é gravada.

| Flag | Padrão | O que faz |
| --- | --- | --- |
| `--seed` | a do jogo | semente do cenário ([SEMENTE.md](SEMENTE.md)) |
| `--days` | 121 | quantos dias jogar |
| `--model` | `openai/gpt-5.6-luna` | id do modelo no OpenRouter |
| `--mode` | `principal` | `sem_memoria` manda o conhecimento sempre vazio |
| `--knowledge` | — | `.txt` de base de conhecimento, anexado à chamada inicial |
| `--timeout` | 360 | segundos de espera por chamada |
| `--attempts` | 3 | tentativas quando a resposta chega mas não serve |
| `--headless` | — | sem janela; o vídeo é gravado igual. O mais estável para runs longas |
| `--no-video` | — | não grava o MP4 |
| `--realtime` | — | roda a 60 fps de verdade em vez de acelerado |
| `--allow-sleep` | — | deixa o Windows suspender por inatividade durante a run |
| `--runs-dir` | `runs_llm/` | onde criar a pasta da run |

Os padrões moram em [`llm_agent/settings.py`](../llm_agent/settings.py), separado de
`farm/settings.py` para o jogo continuar intocado. Lá também ficam `TEMPERATURE` (não enviada por
padrão: o `gpt-5.6-luna` não lista o parâmetro), `REASONING_EFFORT` e `RESPONSE_FORMAT_JSON`, que
pede JSON de verdade ao provedor.

## Os prompts são arquivos

Os dois prompts moram em [`prompts/`](../prompts) e são **lidos em runtime**: editar o `.md` muda a
próxima partida sem tocar em Python.

| Arquivo | Chamada |
| --- | --- |
| `prompts/prompt_inicial.md` | a única chamada de abertura, antes do dia 1 |
| `prompts/prompt_gaming.md` | a chamada de cada dia |

Cada arquivo tem as seções `# SYSTEM` e `# USER`. Os `{PLACEHOLDERS}` em maiúsculas são preenchidos
pelo código com fatos calculados; as chaves do JSON de exemplo ficam intactas. Um placeholder que o
código não conhece faz a run falhar **antes** de abrir o jogo — erro de digitação no `.md` aparece
na hora. Cada run guarda uma cópia dos templates que usou, em `prompts/` dentro da pasta dela.

## O laço

```
      ┌─ CHAMADA INICIAL (uma vez, antes do dia 1) ────────────┐
      │  regras + custos + cultivos + estações + loja           │
      │  (+ base de conhecimento)  ->  analise, regras_de_bolso │
      │  "estrategia": máx. 128 caracteres, é a âncora          │
      └─────────────────────────────────────────────────────────┘
                              │
                              v
      ┌─ POR DIA ───────────────────────────────────────────────┐
      │  código monta:  estratégia (128 caracteres)              │
      │                 estado do jogo e loja (calculados)       │
      │                 prazo por cultivo (calculado)            │
      │                 feedback de ontem                        │
      │                 diário (últimos 5 dias)                  │
      │                 conhecimento (devolvido ontem)           │
      │                              │                           │
      │  LLM devolve:   leitura_do_dia                           │
      │                 conhecimento  (reescrito, máx 15 linhas) │
      │                 plano         (comandos da DSL)          │
      │                              │                           │
      │  interpretador: executa em ordem, descarta o inválido,   │
      │                 reserva a volta, dorme                   │
      │                              │                           │
      │  feedback classificado  ──> volta ao topo                │
      └──────────────────────────────────────────────────────────┘
```

Total: **N + 1 chamadas** para uma partida de N dias.

## Decisões de desenho

**O modelo não emite ação primitiva nem coordenada.** `PLANTAR trigo TUDO`, não uma lista de
passos. Um dia inteiro cabe em ~6 comandos.

**Quantidade fica onde é decisão, some onde é contabilidade.** `COMPRAR trigo 12` — o número é a
decisão econômica. `PLANTAR trigo TUDO` — quantas sementes × células × stamina, o código conta.

**O agente não pode morrer.** A única derrota é aritmética pura; o interpretador confere a volta
antes de cada ação e, sem folga, corta o resto do plano. O corte vira feedback
(`TRUNCADO_STAMINA`), não game over.

**Nunca se pede reenvio de plano.** Comando inválido é descartado, o resto executa e o erro volta
amanhã. Só se repete uma chamada cuja resposta **chegou mas não é usável** — JSON que não parseia,
estratégia acima de 128 caracteres, HTTP 429/5xx.

**Memória: três objetos com regras diferentes.**

| Objeto | Quem gera | Como envelhece |
| --- | --- | --- |
| estado do jogo | código | não envelhece: é sempre o presente |
| diário | código | janela dos últimos 5 dias |
| conhecimento | LLM | curadoria, não janela: reescrito inteiro, teto de 15 linhas |

Uma lição do dia 3 sobrevive ao dia 25 porque o modelo a recopiou. O teto é o que força a
curadoria; linhas acima dele são cortadas e o corte é avisado no feedback.

**Fato calculado ganha de nota escrita.** Tudo que é calculável vem calculado: prazo por cultivo
(com as estações, inclusive a virada do inverno que apodrece o que está no chão), lucro/ciclo com os
preços do dia, pedágio de cada viagem, células livres, estado de cada plantio, a decomposição da
stamina de ontem. O prompt diz que, quando um número contradiz o conhecimento, o número ganha.

**A ordem do output importa.** `leitura_do_dia` → `conhecimento` → `plano`: o plano sai condicionado
à reflexão recém-escrita.

## Timeout e falhas

| Situação | O que acontece |
| --- | --- |
| Sem resposta em `--timeout` segundos | **não repete**: o jogador dorme e o feedback do dia seguinte diz |
| Provedor desiste por tempo (HTTP 504/408) | igual ao timeout |
| JSON inválido, 429, 5xx | tenta de novo, até `--attempts` |
| Estratégia acima de 128 caracteres | rejeitada e pedida de novo; esgotadas as tentativas, usa a última cortada no teto |
| Tentativas esgotadas num dia | dia perdido: o jogador dorme sem agir |

Enquanto espera o modelo, o jogo fica parado e o gravador pausado. Se a espera passar do prazo, a
pilha de todas as threads vai para `travamentos.log`, dentro da pasta da run (o arquivo só existe
se isso acontecer). Numa run antiga esse dump mostrou um `thread.join()` preso enquanto a resposta
chunked chegava; a espera hoje usa `Event` + `sleep` e ainda confere o prazo na resposta.

A run pede ao Windows para não suspender por inatividade enquanto existir (`--allow-sleep`
desliga). Para runs longas, `--headless` evita a janela, que o Windows poderia fechar como travada.

## Pastas

```
runs_llm/
  resumo.csv                                        uma linha por run
  2026-09-13_09-44-09_gpt-5.6-luna_principal_seed42/
    LEIAME.md                resumo: moedas, estratégia, dias truncados, no chão no fim, custo, tempo
    config.json              tudo que definiu a run, inclusive a base de conhecimento
    prompts/                 os templates .md exatamente como estavam nesta run
    agente.log               log de texto completo
    chamadas.csv             uma linha por chamada: início, fim, segundos, status, tokens, custo
    comandos.csv             uma linha por comando do plano, com o código do resultado
    dias.csv                 uma linha por dia
    erros_gramatica.csv      todo comando fora da gramática: pedidos de feature
    estrategia/
      prompt.txt             o prompt renderizado (system + user)
      resposta_1.txt         resposta bruta + raciocínio
      estrategia.json        analise, regras_de_bolso, estrategia (e se foi cortada)
      chamadas.json
    dias/dia_001/
      prompt.txt             o prompt que o modelo recebeu
      estado.json            o estado do jogo em JSON
      resposta_1.txt         resposta bruta (resposta_2, _3 se houve nova tentativa)
      resposta.json          leitura_do_dia, conhecimento e plano aprovados
      feedback.txt           o feedback exatamente como vai para o dia seguinte
      relatorio.json         comandos, códigos, stamina decomposta, moedas, apodrecimento
      conhecimento.md        o bloco ao fim do dia, com linhas novas e removidas
      chamadas.json          tempo de cada chamada e da execução do jogo
    jogo/                    os logs nativos do jogo (CSV e texto)
    video.mp4
    conhecimento_final.txt   pronto para --knowledge numa próxima run
```

`dias.csv`, uma linha por dia: moedas, contagem de cada código, se truncou, stamina gasta e
decomposta (andando, plantando, colhendo, fertilizando, limpando), canteiros visitados, vendas,
apodrecidas, plantas no chão, evolução do conhecimento (linhas, novas, removidas, cortadas),
chamadas, tempo do modelo, tempo do jogo, tokens e custo.

**A evolução do bloco de conhecimento ao longo da partida é provavelmente o resultado mais
interessante** — mais que o placar. `dias/dia_NNN/conhecimento.md` mostra o que entrou e o que saiu
a cada dia.

## Diferenças para o Projeto Fazenda

A lógica é a mesma; o jogo daqui tem mais regras, e isso pede extensões:

| Projeto Fazenda | Aqui | Por quê |
| --- | --- | --- |
| 4 cultivos, colheita de 2–3 unidades | 5 cultivos, 1 unidade por colheita | regras deste jogo |
| sem apodrecimento | validade + `LIMPAR [LIMITE n]` | planta pronta apodrece |
| sem fertilizante | `FERTILIZAR [LIMITE n]`, `COMPRAR fertilizante n` | regras deste jogo |
| sem estações | prazo por cultivo considera estação e virada do inverno | regras deste jogo |
| loja sem limites | promoção, estoque, caixa e saturação no prompt e no feedback | regras deste jogo |
| folga de 2 na volta | conta exata com o custo da ação + reserva de 1 | o custo da ação já entra na conta |
| logs em xlsx | CSV + texto por dia | pedido para este projeto |
| — | `--knowledge` na chamada inicial | pedido para este projeto |

A [ARQUITETURA-IA.md](ARQUITETURA-IA.md) descreve o desenho anterior deste projeto (validação
com uma chamada de correção, caderno com prefixos); ele foi substituído por este.
