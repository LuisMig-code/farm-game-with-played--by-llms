# Jogando por script

O pacote `scripting/` deixa o jogo ser jogado por código, com a partida gravada em vídeo. Foi feito
pensando em agentes de IA: o script anda, planta, negocia e dorme, lê o estado da partida em JSON ou
em texto pronto para prompt, e no fim sobra um MP4 para assistir ao que o agente fez.

Nada em `farm/` foi modificado. A camada monta um `Game` normal e o dirige de fora.

## Começo rápido

```python
from scripting import Session, HOUSE, SHOP

with Session(seed=42, record="logs/partida.mp4") as s:
    s.walk_to((6, 8))
    s.plant("batata")
    s.walk_to(HOUSE).sleep_until(day=4)
    s.walk_to((6, 8)).harvest()
    s.walk_to(SHOP).sell("batata")
    print(s.observe().as_text())
```

Dois exemplos prontos, em [`examples/`](../examples):

```bash
venv/Scripts/python.exe examples/scripted_run.py --seed 7
venv/Scripts/python.exe examples/random_agent.py --seed 7 --days 20
```

O primeiro é o roteiro fixo acima. O segundo é o esqueleto de um agente: um laço que lê o estado,
escolhe uma ação e trata a recusa. Trocar a função `decide()` por uma chamada de LLM — passando
`s.observe().as_text()` no prompt — é o passo seguinte.

## A `Session`

`Session(seed=None, record=None, fps=60)`. A `seed` é a mesma de
[SEMENTE.md](SEMENTE.md): mesma semente, mesmo estoque e mesma promoção em cada dia. `record` é o
caminho do MP4; sem ele, nada é gravado.

| Grupo | Métodos |
| --- | --- |
| Movimento | `walk_to(cell)`, `step(direction)` |
| Campo | `plant(crop)`, `harvest()`, `fertilize()`, `clear()` |
| Casa e loja | `sleep()`, `sleep_until(day)`, `sell(crop, n=1)`, `buy(item, n=1)`, `leave_shop()` |
| Estado | `observe()`, `day`, `cell`, `stamina`, `coins`, `over`, `stats`, `count(item)` |
| Baixo nível | `press(key)`, `tick(frames, direction)`, `breathe(seconds)`, `game` |

Todo método de ação **bloqueia até a ação terminar de verdade**: plantar e colher só têm efeito
quando a animação de 0,5 s acaba, e dormir tem 0,6 s de transição. Quando a chamada retorna, o
inventário e o campo já mudaram.

Os métodos de ação devolvem a própria sessão, então dá para encadear: `s.walk_to(HOUSE).sleep()`.

`walk_to` acha o menor caminho com uma busca em largura sobre as 136 células andáveis, que formam um
único componente conexo. Cada passo custa 1 de estamina — a distância é o custo.

## Erros

Todos herdam de `ScriptingError`, então dá para capturar só a base.

| Erro | Quando |
| --- | --- |
| `Blocked` | O jogo recusou a ação. A mensagem traz o motivo que o próprio jogo escreveu |
| `NoRoute` | Não existe caminho andável até a célula |
| `GameOver` | A estamina chegou a zero |
| `Aborted` | A janela foi fechada, ou o jogo travou num estado que não avança |
| `RecorderUnavailable` | Falta o `imageio-ffmpeg` para gravar |

Recusa é informação, não acidente. Um agente pode tentar uma ação e usar a mensagem para decidir
outra:

```python
try:
    s.plant("melancia")
except Blocked as erro:
    print(erro)   # nao ha semente de melancia no inventario
```

## Por que tudo passa pelo menu

O jogo tem um atalho interno, `Game._start_action`, que executa a ação direto. Ele **não revalida
nada**: com zero sementes, plantar por ali funciona assim mesmo, porque o retorno de
`Inventory.take` é descartado. Todas as travas de regra — sem saldo, esgotado, inventário cheio, já
fertilizada, limite de 3 por dia, estação sem plantio — vivem no campo `enabled` das opções de menu.

Por isso a `Session` **abre o menu, procura a opção, confere o `enabled` e só então confirma**, como
um humano faria. Se a opção estiver desabilitada, ela levanta `Blocked` com o rótulo do jogo em vez
de forçar. Um agente não deve conseguir trapacear sem querer — nem quando o bug está do lado do
jogo.

## Observação

`s.observe()` devolve um `Observation` com duas saídas do mesmo conteúdo:

- **`as_dict()`** — serializável em JSON: dia, estação e dias para a próxima, estamina, célula,
  inventário com limites, todas as plantas (`cell`, `crop`, `stage`, dias para crescer e para
  estragar, fertilizada), o mercado (preço de compra e venda, estoque, promoções, caixa restante) e
  `actions`, a lista do que é legal fazer na célula atual.
- **`as_text()`** — o mesmo em texto curto em português, pronto para entrar num prompt.

```
Dia 4 | Primavera (muda em 27 dia(s)): ritmo padrão o mês inteiro
Estamina 118/160 | 9 moeda(s) | jogador em (21, 12) (comercio) | fertilizantes hoje: 3 de 3

Inventario: Semente de Beterraba x1/20, Semente de Trigo x1/20, Fertilizante x2/9

Plantacao: nada plantado

Loja (caixa 191/200):
  vender Batata: 6
  comprar Semente de Batata: 3 (estoque 18) [promocao, era 4]
  ...

Acoes possiveis aqui: walk_to, sell, buy
```

Nada aqui recalcula regra: tudo sai de método público do jogo, para a observação nunca discordar da
partida.

## Gravação

A tela é 2000x1000 a 60 fps — gravar isso cru seriam 360 MB/s. O `Recorder` reduz cada quadro para
**1000x500** e grava a **30 fps**, o que custa ~3 ms por quadro, folgado dentro dos 16,6 ms de
orçamento. Uma partida de 4 dias sai com ~500 KB.

```python
Session(seed=42, record="logs/partida.mp4")        # padrao 1000x500 a 30 fps
```

O encoder é o ffmpeg estático que vem no `imageio-ffmpeg`, alimentado com bytes RGB crus — sem
numpy e sem Pillow, que não existem no venv do projeto. É a única dependência nova, e mora em
[`requirements-agent.txt`](../requirements-agent.txt) para não mexer no `requirements.txt` do jogo:

```bash
venv/Scripts/python.exe -m pip install -r requirements-agent.txt
```

Sem ela, `Session(record=...)` levanta `RecorderUnavailable` com o comando; sem `record`, a sessão
roda normalmente.

## Ritmo e a janela

A sessão roda em **tempo real, com a janela aberta**, a 60 fps. Duas consequências:

**Enquanto o agente pensa, o jogo para.** O laço só roda dentro das chamadas da `Session`, então uma
chamada de LLM de 5 segundos deixa a janela congelada naquele quadro. Isso é correto — o jogo não
deve avançar enquanto ninguém decide —, mas o Windows pode marcar a janela como "não respondendo"
numa espera longa. `s.breathe(segundos)` roda quadros sem agir, para quem quiser manter a janela
viva.

**O passo de simulação é limitado a 50 ms.** Sem essa trava, o tempo acumulado durante a pausa
entraria de uma vez no quadro seguinte e o jogador atravessaria meia dezena de células de um salto.

Para rodar sem janela — em teste ou em lote — basta o driver nulo do SDL antes de importar o
pygame, o mesmo que as suítes do projeto usam:

```python
import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
```

## Como funciona por dentro

`Game.run()` é bloqueante e é o único dono do tempo, então `Session._tick()` refaz o corpo dele por
fora: `_handle_events()`, `_update(dt)`, `_draw()`, `flip()` e um quadro para o gravador. `close()`
faz o que o `finally` de `run()` faria — registra `saiu` e fecha o log da run.

O movimento é o único ponto que exige um truque. `Game._on_key` trata Espaço, ESC e G, mas **não
trata WASD**: a direção vem de `Game._input_direction()`, que lê o teclado físico. Como é um
`staticmethod`, um atributo de instância tem prioridade, e a sessão injeta a direção assim:

```python
game._input_direction = lambda: pygame.Vector2(dx, dy)
```

A partir daí `_update(dt)` move o jogador com todas as regras intactas: estamina, bloqueio de
célula, log de passo e checagem de derrota. É o mesmo padrão que as suítes de teste do projeto já
usavam.

Cada partida por script continua gravando seus arquivos em `logs/` como qualquer outra — ver
[LOGS.md](LOGS.md).
