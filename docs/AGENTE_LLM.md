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
| `--speed` | 2 | velocidade das ações na tela: andar, plantar, colher, fertilizar, limpar, dormir. 1 = a do jogo |
| `--allow-sleep` | — | deixa o Windows suspender por inatividade durante a run |
| `--runs-dir` | `runs_llm/` | onde criar a pasta da run |

Os padrões moram em [`llm_agent/settings.py`](../llm_agent/settings.py), separado de
`farm/settings.py` para o jogo continuar intocado. Lá também ficam `TEMPERATURE` (não enviada por
padrão: o `gpt-5.6-luna` não lista o parâmetro), `REASONING_EFFORT` e `RESPONSE_FORMAT_JSON`, que
pede JSON de verdade ao provedor.

## Velocidade

`GAME_SPEED` (padrão 2, ou `--speed`) multiplica o tempo de jogo de cada quadro: passo, animação de
plantar/colher/fertilizar/limpar e a transição do sono levam metade dos quadros, e o vídeo fica com
metade da duração. **Nenhuma regra muda** — estamina, crescimento e preços contam passos e dias,
não segundos; uma run a 1 e outra a 2 produzem `comandos.csv` idênticos. A loja também ficou mais
curta: cada `COMPRAR`/`VENDER` abre o menu uma vez para o lote inteiro, em vez de uma vez por
unidade.

| Ação (quadros a 60 fps) | Velocidade 1, loja unidade por unidade | Velocidade 2, loja em lote |
| --- | --- | --- |
| passo | 8 | 4 |
| plantar / fertilizar | 32 | 17 |
| colher / limpar | 31 | 16 |
| dormir | 36 | 18 |
| vender 8 unidades | 40 | 12 |
| comprar ou vender 1 unidade | 5 | 5 |

A última linha é a exceção: navegar no menu é uma tecla por quadro, e a velocidade não mexe nisso.
O teto é `Session.max_speed()` (~7,4 a 60 fps): acima dele o jogador andaria uma célula inteira num
quadro e o passo emendaria no seguinte. Ver [SCRIPTING.md](SCRIPTING.md).

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

Dois blocos do prompt diário existem para o modelo não ser pego de surpresa:

- **Próxima estação**, em "ONDE VOCÊ ESTÁ": qual é, em que dia começa, quantos dias faltam e o que
  ela restringe — no inverno, o dia limite para colher antes de tudo apodrecer; nas outras viradas,
  o lembrete de que o que já está no chão mantém as regras da estação em que foi plantado.
- **Fertilizante**, logo depois do prazo: o efeito por cultivo, as restrições (1 por planta, 3 por
  dia, não funciona no inverno, stamina, limite de 9) e os números de hoje (quantos tem, quantos
  ainda pode usar, preço e estoque na loja, e em que dia para ou volta a funcionar).

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
    precos.csv               uma linha por dia: preço de compra de cada item e de venda de cada cultivo
    transacoes.csv           uma linha por compra ou venda que o jogador fez no jogo
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
    video.mp4                a tela do jogo, na velocidade da run
    conhecimento_final.txt   pronto para --knowledge numa próxima run

logs/                                               a pasta de logs do jogo
  IA_gpt-5.6-luna_run_<id>_semente42_<data>.log     cópia do .log de jogo/, ao fim da run
  IA_gpt-5.6-luna_run_<id>_semente42_<data>.csv     cópia do .csv de jogo/
  IA_gpt-5.6-luna_celulas_estragadas.csv            células estragadas, acumuladas por modelo
```

Os logs nativos também vão para `logs/`, junto dos das partidas jogadas por gente, e o prefixo
`IA_<modelo>_` separa uns dos outros. A cópia acontece ao fim da run (inclusive se ela for
interrompida), porque o jogo só solta os arquivos quando a sessão fecha; os originais continuam em
`jogo/`. O histórico de células estragadas, que o jogo acumula entre partidas em
`logs/celulas_estragadas.csv`, aqui é acumulado por modelo — as partidas da IA não entram no
histórico das humanas. O destino é `GAME_LOGS_DIR`, e o prefixo, `GAME_LOGS_PREFIX`.

**A economia da run** fica em dois CSVs:

- `precos.csv` — uma linha por dia com os preços do **começo do dia**, os mesmos do prompt:
  `compra_semente_<cultivo>` e `compra_fertilizante` (já com promoção) e `venda_<cultivo>` (já com
  a estação e a saturação). Durante o dia a venda ainda pode cair com a saturação; o preço de cada
  unidade vendida está em `transacoes.csv`.
- `transacoes.csv` — `dia, tipo, item, quantidade, preco_min, preco_max, total_moedas,
  moedas_depois`. Sai do **registro do próprio jogo**, não do plano: só entra o que o jogador de
  fato comprou ou vendeu. Unidades seguidas da mesma operação e do mesmo item são uma transação;
  qualquer outra ação registrada pelo jogo a fecha — andar, plantar, dormir, negociar outro item,
  sair da loja. Vender 5 batatas, sair e voltar para vender 17 dá duas linhas; comprar sementes de
  3 cultivos dá três. Nas compras, `item` é o cultivo da semente (ou `fertilizante`).

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
