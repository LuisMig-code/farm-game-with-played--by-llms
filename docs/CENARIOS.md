# Cenários por semente

O simulador mostra o que a loja vai ter em cada dia de uma semente, sem abrir o jogo: quais itens
entram em promoção, com quanto de desconto, e o estoque de cada item. Serve para escolher sementes
de teste — a com mais promoções, a com menos, uma perto da média — e para saber de antemão o que uma
run vai encontrar.

```bash
venv/Scripts/python.exe simulate_seed.py --seed 42              # uma semente, dia a dia
venv/Scripts/python.exe simulate_range.py --from 1 --to 1000    # um intervalo, em paralelo
```

- [Por que dá para simular](#por-que-dá-para-simular)
- [Uma semente](#uma-semente)
- [Um intervalo, em paralelo](#um-intervalo-em-paralelo)
- [A pasta cenarios/](#a-pasta-cenarios)
- [Quando uma semente é simulada de novo](#quando-uma-semente-é-simulada-de-novo)
- [Velocidade e espaço](#velocidade-e-espaço)
- [Por dentro](#por-dentro)

## Por que dá para simular

O jogo sorteia pouca coisa: só o estoque e a promoção de cada dia. Os dois dependem só da semente e
do dia ([SEMENTE.md](SEMENTE.md)), e nada que o jogador faz muda esse sorteio. O dia 30 da semente
42 é o mesmo em qualquer partida, e dá para calculá-lo sem jogar os 29 anteriores.

O simulador não reescreve regra nenhuma. Ele cria o mesmo `Market` do jogo
([`farm/market.py`](../farm/market.py)) e faz as mesmas chamadas: `Market(seed)` na largada e
`new_day(dia)` a cada noite. Se a loja mudar, o simulador acompanha sem precisar de ajuste. O
`tests/check_scenarios.py` compara, dia a dia, o simulador com uma partida de verdade. As colunas
`compra_*` saem iguais ao `precos.csv` das runs do agente com a mesma semente: foi conferido nas 18
runs guardadas, das sementes 42 e 2026, num total de 2.205 dias.

O cenário é a loja **no começo de cada dia**:

- entram o estoque de cada item, quais itens estão em promoção, o desconto de cada um, o preço de
  compra e a estação;
- ficam de fora as compras do jogador, que baixam o estoque, e a saturação, que depende do que ele
  vende;
- também não entram o preço de venda e o caixa da loja: eles dependem só do dia, não da semente
  (ver [ESTACOES.md](ESTACOES.md) e [COMERCIO.md](COMERCIO.md)).

## Uma semente

```bash
venv/Scripts/python.exe simulate_seed.py --seed 42
```

```
semente 42 | 121 dias | regras 3fd85bdbaa83
promocoes: 158 em 101 dias (media 1,31 por dia, ate 3 num dia), 278 moedas de desconto somadas
  por estacao: primavera 30 | verao 36 | outono 39 | inverno 53
  por item:    batata 26 | cenoura 27 | beterraba 29 | trigo 29 | melancia 20 | fertilizante 27
dias sem estoque: beterraba 3 | trigo 4 | melancia 15
cenario dia a dia: ...\cenarios\sementes\semente_42.csv
```

| Flag | Padrão | O que faz |
| --- | --- | --- |
| `--seed N` | `FARM_SEED`, depois `SEED` de `farm/settings.py` | a semente, na mesma ordem de prioridade do `main.py` |
| `--days N` | 121, o `DAYS` do agente | quantos dias simular, a partir do dia 1 |
| `--out PASTA` | `cenarios/` | a pasta de log |

O script simula sempre, mesmo que a semente já esteja no log: o pedido é explícito e custa
milissegundos. Ele grava o CSV da semente, atualiza a linha dela no `resumo.csv` e acrescenta a
execução ao `execucoes.csv`.

## Um intervalo, em paralelo

```bash
venv/Scripts/python.exe simulate_range.py --from 0 --to 999
```

```
sementes 0 a 999 | 121 dias
  100/1000 simuladas
  ...
  1000/1000 simuladas
1000 sementes em 1,5 s, 16 processo(s), regras 3fd85bdbaa83: 1000 novas, 0 refeitas, 0 puladas (ja estavam no log)
promocoes em 121 dias, nas 1000 sementes do intervalo no log:
  media: 160,3 por semente (1,32 por dia)
  menos: semente 714 (128) | semente 334 (131) | semente 354 (131)
  mais:  semente 517 (197) | semente 273 (191) | semente 359 (189)
resumo: ...\cenarios\resumo.csv
dia a dia: ...\cenarios\sementes\semente_<N>.csv
```

| Flag | Padrão | O que faz |
| --- | --- | --- |
| `--from A` | obrigatório | a primeira semente |
| `--to B` | obrigatório | a última semente, inclusive |
| `--days N` | 121 | quantos dias simular |
| `--workers N` | um por núcleo | quantos processos |
| `--out PASTA` | `cenarios/` | a pasta de log |

- Uma semente que já está no log, com os mesmos dias e as mesmas regras, é pulada (ver
  [abaixo](#quando-uma-semente-é-simulada-de-novo)). As outras são repartidas em lotes de 50 entre
  os processos.
- A média e as sementes com menos e com mais promoções valem para o intervalo pedido inteiro: as
  simuladas agora e as que já estavam no log.
- Um intervalo tem no máximo 100 mil sementes (`MAX_SEEDS`). Para mais, divida em partes.
- Ctrl+C para no meio sem perder o que terminou:
  - o resumo é gravado com as sementes prontas;
  - a execução fica marcada como `interrompida`;
  - rodar o mesmo comando de novo completa o resto.
- Código de saída:
  - `0`: tudo gravado;
  - `1`: uma semente ou o resumo não pôde ser gravado (arquivo aberto no Excel, por exemplo);
  - `2`: argumento inválido;
  - `130`: Ctrl+C.

## A pasta `cenarios/`

```
cenarios/                      fora do git, como runs_llm/ e logs/
  resumo.csv                   uma linha por semente: as métricas e como foi simulada
  execucoes.csv                uma linha por execução dos dois scripts
  sementes/semente_<N>.csv     o cenário da semente, uma linha por dia
```

Nas colunas abaixo, `<item>` é cada item da loja, na ordem do quadro de preços: `semente_batata`,
`semente_cenoura`, `semente_beterraba`, `semente_trigo`, `semente_melancia` e `fertilizante`. Os
itens e as estações vêm de `BUY_PRICES` e `SEASONS`: um item novo no jogo vira coluna sozinho.

### `sementes/semente_<N>.csv`

Uma linha por dia.

| Coluna | Conteúdo |
| --- | --- |
| `semente`, `dia`, `estacao` | a semente, o dia e a estação (`primavera`, `verao`, `outono`, `inverno`) |
| `promocoes` | quantos itens estão em promoção no dia |
| `itens_em_promocao` | quais, com o desconto, na ordem da loja: `semente trigo -1; semente melancia -1` |
| `desconto_total` | a soma dos descontos do dia, em moedas |
| `estoque_<item>` | o estoque no começo do dia, antes de qualquer compra |
| `desconto_<item>` | o desconto do item; `0` é sem promoção |
| `compra_<item>` | o preço de compra do dia, já com o desconto; é o mesmo do `precos.csv` de uma run |

```
semente,dia,estacao,promocoes,itens_em_promocao,desconto_total,estoque_semente_batata,...
42,1,primavera,1,semente cenoura -1,1,22,...
42,6,primavera,2,semente trigo -1; semente melancia -1,2,8,...
```

### `resumo.csv`

Uma linha por semente, na ordem das sementes: abra no Excel e ordene pela coluna que quiser. Só
compare linhas com os mesmos `dias` e as mesmas `regras`.

| Coluna | Conteúdo |
| --- | --- |
| `semente`, `dias`, `regras` | a semente, quantos dias foram simulados e a [impressão digital das regras](#quando-uma-semente-é-simulada-de-novo) |
| `promocoes` | itens em promoção somados no horizonte: um dia com 2 itens conta 2 |
| `dias_com_promocao` | dias com pelo menos um item em promoção |
| `media_promocoes_dia` | `promocoes / dias` |
| `max_promocoes_dia` | o maior número de itens em promoção num mesmo dia |
| `desconto_total` | todas as moedas de desconto somadas |
| `promocoes_<estacao>` | as promoções de cada estação; no inverno não se planta, então semente em promoção lá vale pouco |
| `promocoes_<item>` | em quantos dias o item esteve em promoção |
| `estoque_medio_<item>` | o estoque médio do item no começo do dia |
| `dias_sem_estoque_<item>` | dias em que o item não estava à venda; com as faixas de hoje, só beterraba, trigo e melancia zeram ([COMERCIO.md](COMERCIO.md#estoque-do-dia)) |
| `execucao`, `simulado_em`, `ms` | a execução que gravou a linha (a chave do `execucoes.csv`), quando e em quantos milissegundos |

### `execucoes.csv`

Uma linha por execução de qualquer um dos dois scripts.

| Coluna | Conteúdo |
| --- | --- |
| `execucao` | o id, `AAAA-MM-DD_HH-MM-SS_<pid>` |
| `script` | `simulate_seed` ou `simulate_range` |
| `inicio`, `fim`, `segundos` | quando rodou e quanto tempo levou |
| `sementes`, `dias` | o pedido (`42` ou `1..1000`) e o horizonte |
| `processos` | os processos usados: 1 quando não havia nada a simular ou só um lote |
| `pedidas`, `novas`, `refeitas`, `puladas`, `falhas` | o que aconteceu com as sementes pedidas |
| `regras`, `python` | as regras do jogo e a versão do Python |
| `interrompida` | `ctrl+c`, o erro que parou a execução, ou vazio |

## Quando uma semente é simulada de novo

O `simulate_range.py` pula a semente quando as três condições valem:

1. ela tem linha no `resumo.csv` com os mesmos `dias`;
2. essa linha tem as mesmas `regras`;
3. o `sementes/semente_<N>.csv` dela existe.

Nos outros casos a semente é simulada de novo, e a linha e o arquivo dela são substituídos; na
contagem, ela aparece como `refeitas`. O cenário é determinístico e custa milissegundos, então
refazer nunca perde nada.

As `regras` são uma impressão digital, 12 caracteres do sha256, dos arquivos que decidem o sorteio:
`farm/market.py`, `rng.py`, `crops.py`, `seasons.py` e `settings.py`. Se mudar uma faixa de estoque,
uma tabela de promoção ou o código do sorteio, o valor muda e as sementes salvas deixam de valer:
[a semente não cobre as regras](CONFIGURACOES.md#cuidados). As quebras de linha são normalizadas, e
o valor é o mesmo com CRLF ou LF.

Quando o resumo tem sementes de fora do intervalo pedido simuladas com outros dias ou regras, o
`simulate_range.py` avisa numa linha. Elas são refeitas quando entrarem num intervalo pedido.

## Velocidade e espaço

Medido na máquina de desenvolvimento, com 16 núcleos e Windows:

| Sementes | Processos | Tempo |
| --- | --- | --- |
| 1.000 | 1 | 3,9 s |
| 1.000 | 16 | 1,5 s |
| 10.000 | 4 | 11,8 s |
| 10.000 | 8 | 9,0 s |
| 10.000 | 16 | 9,7 s |
| 1.000 já no log | — | 0,1 s |

Simular custa ~2 ms por semente, e o resto do tempo vai para gravar o CSV. A partir de ~8
processos, o disco vira o gargalo. Cada semente ocupa ~11 KB: mil sementes dão ~13 MB, e dez mil
~120 MB.

## Por dentro

| Arquivo | O que tem |
| --- | --- |
| [`seed_scenarios/simulator.py`](../seed_scenarios/simulator.py) | `simulate`, `summarize`, `rules_fingerprint` e os cabeçalhos dos CSVs |
| [`seed_scenarios/store.py`](../seed_scenarios/store.py) | a pasta de log: gravação atômica, `resumo.csv` e `execucoes.csv` |
| [`seed_scenarios/batch.py`](../seed_scenarios/batch.py) | `run_batch`: o que pular, os lotes, o pool e o Ctrl+C |
| [`seed_scenarios/settings.py`](../seed_scenarios/settings.py) | a pasta, os dias, os processos, o tamanho do lote e o teto de sementes |

- **Escrita.** Só o processo principal escreve o `resumo.csv` e o `execucoes.csv`; cada processo do
  pool grava os CSVs das suas sementes.
- **Arquivo pela metade.** Todo arquivo reescrito passa por um temporário e é trocado de uma vez
  (`os.replace`). Assim, uma execução morta à força não deixa um CSV pela metade que pareça pronto.
  Um `.tmp` que sobrar depois disso pode ser apagado.
- **Windows e o pool.** Cada processo do pool reimporta o script principal. Quem chama `run_batch`
  com mais de um processo precisa estar atrás de `if __name__ == "__main__":`. Os processos do pool
  ignoram o Ctrl+C; quem para a execução é o principal.
- **Excel.** Com o `resumo.csv` aberto no Excel, o Windows não deixa gravar. O script tenta 3
  vezes, avisa e sai com `1`. Os CSVs das sementes ficam, e a próxima execução completa o resumo.

Pelo código:

```python
from seed_scenarios.simulator import simulate, summarize

cenario = simulate(42, 121)        # um Day por dia: day, season, stock, promos, prices
cenario[5].promos                  # {'semente trigo': 1, 'semente melancia': 1}
summarize(cenario)["promocoes"]    # 158
```

Os testes estão em `tests/check_scenarios.py`, que roda em ~20 s (ver
[tests/README.md](../tests/README.md)).
