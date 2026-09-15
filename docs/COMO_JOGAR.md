# Como jogar

Guia do jogador: como abrir o jogo, o que fazer num dia, as regras que importam e como rodar as
outras formas de jogar (script e LLM). As regras completas, com todos os detalhes, estão nos
documentos de cada assunto — os links aparecem em cada seção.

- [Abrindo o jogo](#abrindo-o-jogo)
- [Objetivo](#objetivo)
- [Controles](#controles)
- [O mapa](#o-mapa)
- [Um dia de jogo](#um-dia-de-jogo)
- [Estamina](#estamina)
- [Cultivos](#cultivos)
- [Fertilizante](#fertilizante)
- [A loja](#a-loja)
- [Estações](#estações)
- [Derrota e recomeço](#derrota-e-recomeço)
- [Dicas](#dicas)
- [Outras formas de jogar](#outras-formas-de-jogar)

## Abrindo o jogo

Com o ambiente instalado (ver o [README](../README.md#instalação)):

```bash
venv/Scripts/python.exe main.py
```

Em macOS/Linux, `venv/bin/python main.py`.

| Parâmetro | Exemplo | O que faz |
| --- | --- | --- |
| `--seed N` | `main.py --seed 42` | fixa o cenário da loja: mesmo estoque e mesmas promoções em cada dia |

Sem `--seed`, vale a variável de ambiente `FARM_SEED` e, depois, o `SEED` de `farm/settings.py`
(2026 por padrão). Com `SEED = None` e nada definido, o jogo sorteia uma semente e grava o número no
nome do log, para você repetir a partida depois. Ver [SEMENTE.md](SEMENTE.md).

```bash
# PowerShell
$env:FARM_SEED = "42"; venv/Scripts/python.exe main.py
# Git Bash no Windows
FARM_SEED=42 venv/Scripts/python.exe main.py
# macOS, Linux
FARM_SEED=42 venv/bin/python main.py
```

A janela tem 2000x1000. Se não couber no monitor, o SDL reduz sozinho; para uma janela menor de
verdade, veja `SCREEN_SIZE` em [CONFIGURACOES.md](CONFIGURACOES.md#janela-e-mundo).

## Objetivo

Cultivar e acumular moedas **sem deixar a estamina chegar a zero**. Não existe condição de vitória
no jogo livre: a partida segue até a derrota ou até você fechar a janela.

Nas partidas jogadas por um LLM o objetivo é fixo: terminar o último dia (`--days`) com o máximo de
moedas.

## Controles

| Tecla | Ação |
| --- | --- |
| `W A S D` / setas | anda uma célula por vez; com um menu aberto, troca a opção |
| `Espaço` / `Enter` | age na célula em que você está (ver abaixo) |
| `ESC` | com menu: volta um nível ou fecha; sem menu: sai do jogo |
| `G` | liga/desliga o grid e o colorido das zonas |
| `R` | só na tela de derrota: começa uma partida nova |
| Mouse | destaca a célula sob o cursor |

O `Espaço` depende da célula — e só funciona com o personagem parado:

| Onde você está | O que o Espaço faz |
| --- | --- |
| Casa (17,12) | dorme e avança o dia |
| Loja (21,12) | abre o menu: vender colheita / comprar sementes e fertilizante |
| Célula de horta vazia | abre o menu de sementes |
| Planta ainda crescendo | abre o menu de fertilizante |
| Planta pronta (barra verde) | colhe |
| Planta podre | arranca (não rende nada, libera a célula) |

Mais em [CONTROLS.md](CONTROLS.md).

## O mapa

O mapa inteiro fica sempre visível. Só dá para pisar nas zonas marcadas (aperte `G` para vê-las):

| Lugar | Células | Para quê |
| --- | --- | --- |
| Casa | (17,12) | dormir; é onde o jogador começa |
| Loja | (21,12) | vender e comprar |
| Horta esquerda | (3,2) a (9,8) — 49 células | plantar |
| Horta direita | (30,2) a (36,8) — 49 células | plantar |
| Caminho | liga casa, loja e as hortas | andar |

Distâncias em passos (cada passo custa 1 de estamina):

| De → para | Passos |
| --- | --- |
| casa → loja | 6 |
| casa → horta esquerda (entrada) | 17 |
| casa → horta direita (entrada) | 22 |
| loja → horta esquerda | 21 |
| loja → horta direita | 18 |
| horta esquerda → horta direita | 37 |

## Um dia de jogo

1. **Acorde** em casa com 160 de estamina.
2. **Vá à horta** e plante: `Espaço` numa célula vazia, escolha a semente, `Espaço` de novo.
3. **Volte e durma**: as plantas só crescem de um dia para o outro, e só dormindo o dia passa.
4. **Colha** quando a barrinha sob a planta ficar verde e cheia. Uma segunda barrinha, acima da
   planta, mostra quantos dias ela aguenta antes de apodrecer.
5. **Venda na loja** e **compre sementes** com o que ganhou. Negociar não gasta estamina.
6. Repita, cuidando para sempre sobrar estamina para voltar para a cama.

## Estamina

| Ação | Custo |
| --- | --- |
| andar 1 célula | 1 |
| plantar | 2 |
| colher | 1 |
| fertilizar | 2 |
| arrancar planta podre | 2 |
| comprar, vender, dormir | 0 |

- São **160 por dia**, recarregados ao dormir.
- **Chegar a 0 é derrota, mesmo em cima da cama.** Um passeio até a horta direita e de volta já
  custa 44.

Mais em [GAME_RULES.md](GAME_RULES.md).

## Cultivos

Você começa com **1 semente de cada tipo**, **2 fertilizantes** e **0 moedas**.

| Cultivo | Cresce em | Validade depois de pronto | Semente | Venda | Lucro por célula |
| --- | --- | --- | --- | --- | --- |
| Cenoura | 2 dias | 3 dias | 2 | 3 | 1 |
| Batata | 3 dias | 3 dias | 4 | 6 | 2 |
| Beterraba | 5 dias | 3 dias | 6 | 9 | 3 |
| Trigo | 7 dias | 4 dias | 7 | 12 | 5 |
| Melancia | 9 dias | 4 dias | 11 | 18 | 7 |

- Cada colheita rende **1 unidade** e libera a célula. Semente só vem da loja.
- Planta que passa da validade **apodrece**: não rende nada e ocupa a célula até ser arrancada.
- Os valores são os base; promoção, estação e saturação mudam os preços do dia.

Mais em [CULTIVO.md](CULTIVO.md).

## Fertilizante

Numa planta **ainda crescendo**, corta dias do crescimento e aumenta a validade:

| Cultivo | Crescimento | Validade |
| --- | --- | --- |
| Cenoura | −1 dia | +2 |
| Batata | −2 dias | +2 |
| Beterraba | −2 dias | +4 |
| Trigo | −2 dias | +4 |
| Melancia | −3 dias | +4 |

- O corte conta desde o plantio: uma batata de 1 dia fertilizada fica pronta **na hora**.
- **1 por planta**, **no máximo 3 por dia**, custa 2 de estamina.
- **Não funciona no inverno.**
- Custa 21 moedas na loja; você carrega até 9.

## A loja

- **Vender**: o menu negocia 1 unidade por `Espaço`, sem fechar. A loja tem um **caixa de 200
  moedas por dia** (300 no inverno) para pagar colheita; comprar devolve caixa.
- **Comprar**: sementes e fertilizante, com **estoque sorteado todo dia** (beterraba, trigo e
  melancia podem faltar) e **promoção** em até 3 itens.
- **Saturação** (a partir do dia 11): vender 7 ou mais do mesmo cultivo no mesmo dia, ou o mesmo
  cultivo em dois dias seguidos, derruba o preço dele em 1 moeda por unidade, até o preço da
  semente. Cada dia sem vendê-lo recupera 1.
- **Limites do inventário**: 20 sementes de cada tipo e 9 fertilizantes. Vegetais e moedas não têm
  teto.

O quadro de preços aparece no topo da tela, acima da loja. Mais em [COMERCIO.md](COMERCIO.md).

## Estações

Cada estação dura **30 dias**, na ordem Primavera → Verão → Outono → Inverno.

| Estação | Dias | O que muda |
| --- | --- | --- |
| Primavera | 1–30 | nada: ritmo padrão |
| Verão | 31–60 | a colheita estraga rápido (validade de 1 ou 2 dias) |
| Outono | 61–90 | tudo leva +1 dia para crescer |
| Inverno | 91–120 | **não dá para plantar**, fertilizante não funciona, **venda multiplicada** (trigo x2,5, melancia x3, o resto x2) e caixa de 300 |

- **Na virada para o inverno, tudo que está no chão apodrece.** Colha até o dia 90 e guarde a
  colheita na mochila para vender caro no inverno — vegetal na mochila não estraga.
- O prazo de uma planta é o da estação em que ela foi **plantada**, mesmo que a estação vire.

O indicador no topo da tela mostra a estação atual, a próxima e quantos dias faltam. Mais em
[ESTACOES.md](ESTACOES.md).

## Derrota e recomeço

Com a estamina em zero a tela escurece e mostra o resumo da partida: dia alcançado, o que foi
plantado, colhido, vendido e comprado, e as moedas. `R` começa de novo no dia 1 (com a mesma
semente) e `ESC` fecha o jogo.

Cada partida grava em `logs/` um `.log` de texto e um `.csv` com todas as ações — ver
[LOGS.md](LOGS.md).

## Dicas

- **Conte a volta.** Antes de cada ação, some os passos até a cama. A horta esquerda é mais barata
  para ir e voltar (34) que a direita (44).
- **Colha e plante na mesma viagem**: colher libera a célula na hora.
- **Venda antes de comprar**: no começo você não tem moedas.
- **Alterne os cultivos que vende** depois do dia 11 para não saturar os preços.
- **Use os fertilizantes iniciais** em plantas de ciclo curto para girar o dinheiro mais cedo.
- **Prepare o inverno**: nos dias 80–90 encha a mochila de trigo e melancia e venda aos poucos,
  deixando dias sem vender o mesmo cultivo para o preço recuperar.

## Outras formas de jogar

### Por script

A camada `scripting/` joga pelos mesmos menus e regras de um jogador no teclado, e grava a tela em
MP4 (precisa do `requirements-agent.txt`).

```bash
venv/Scripts/python.exe examples/scripted_run.py
venv/Scripts/python.exe examples/random_agent.py --seed 7 --days 20
```

| Script | Parâmetros | O que faz |
| --- | --- | --- |
| `examples/scripted_run.py` | `--seed N`, `--no-video` | roteiro fixo: planta, espera, colhe e vende; grava `logs/scripted_run.mp4` |
| `examples/random_agent.py` | `--seed N`, `--days N` (padrão 15), `--no-video` | ações sorteadas até o dia pedido; grava `logs/random_agent.mp4` |

Para escrever o seu próprio script, veja [SCRIPTING.md](SCRIPTING.md).

### Com um LLM

1. Crie o `.env` na raiz com a sua chave do OpenRouter:

   ```
   OPEN_ROUTER_API_KEY=sua-chave-aqui
   ```

2. Rode uma partida:

   ```bash
   venv/Scripts/python.exe run_llm.py --seed 42 --days 30 --headless
   ```

| Flag | Padrão | O que faz |
| --- | --- | --- |
| `--seed N` | a do jogo | semente do cenário |
| `--days N` | 121 | quantos dias jogar |
| `--model ID` | `openai/gpt-5.6-luna` | qualquer modelo do OpenRouter |
| `--mode` | `principal` | `sem_memoria`: o bloco de conhecimento chega sempre vazio |
| `--knowledge ARQ` | — | `.txt` de aprendizados anteriores, anexado à chamada de estratégia |
| `--timeout S` | 360 | segundos de espera por chamada; estourou, o jogador dorme |
| `--attempts N` | 3 | tentativas quando a resposta chega mas não serve |
| `--speed X` | 2 | velocidade das ações na tela (1 = a do jogo) |
| `--headless` | — | sem janela; o vídeo é gravado igual. O mais estável para runs longas |
| `--no-video` | — | não grava o MP4 |
| `--realtime` | — | roda a 60 fps de verdade em vez de acelerado |
| `--allow-sleep` | — | deixa o Windows suspender por inatividade durante a run |
| `--runs-dir PASTA` | `runs_llm/` | onde criar a pasta da run |

Exemplos:

```bash
# comparar dois modelos no mesmo cenário
venv/Scripts/python.exe run_llm.py --seed 42 --days 60 --headless --model openai/gpt-5.6-luna
venv/Scripts/python.exe run_llm.py --seed 42 --days 60 --headless --model outro/modelo

# reaproveitar o que a run anterior aprendeu
venv/Scripts/python.exe run_llm.py --seed 7 --days 120 --headless --knowledge runs_llm/<pasta>/conhecimento_final.txt
```

Cada run cria uma pasta em `runs_llm/` com prompts, respostas, CSVs, vídeo e um `LEIAME.md` com o
resumo. O funcionamento do agente está em [AGENTE_LLM.md](AGENTE_LLM.md) e a linguagem de comandos
do plano em [GRAMATICA.md](GRAMATICA.md).
