# Semente do cenário

O jogo sorteia pouca coisa — só o **estoque** e a **promoção** de cada dia na loja. Todo o resto
(crescimento, validade, estação, preço, saturação) já é função do dia. A semente faz esse sorteio
virar função do dia também: **com a mesma semente, o dia 30 é sempre o mesmo dia 30**, em qualquer
partida futura.

Isso é o que torna duas partidas comparáveis. Sem a semente não dá para repetir uma corrida boa,
nem para medir duas estratégias no mesmo cenário.

## Como definir

Três formas, nesta ordem de prioridade:

| Ordem | Onde | Exemplo |
| --- | --- | --- |
| 1º | linha de comando | `python main.py --seed 42` |
| 2º | variável de ambiente | `FARM_SEED=42` |
| 3º | `farm/settings.py` | `SEED = 2026` |

Se nenhuma delas der um número (`SEED = None` e nada no ambiente), o jogo **sorteia uma semente na
largada** e grava o número. Você joga às cegas e, se a partida for interessante, repete depois — o
número está no nome do arquivo de log.

## O que a semente cobre

| Cobre | Não cobre |
| --- | --- |
| O estoque diário de cada item | O que o jogador decide fazer |
| Quantos e quais itens entram em promoção | O `id` e os horários da run |
| O tamanho de cada desconto | `logs/celulas_estragadas.csv`, que acumula entre partidas |

A semente fixa o **cenário**, não o resultado. Duas partidas com a semente 42 encontram a mesma
loja todo dia; o que cada uma faz com isso é problema do jogador.

## Repetindo uma partida

O número está no nome dos arquivos em `logs/`:

```
run_b4b10dc9_semente20260905_2026-09-05_15-33-01.csv
                    ^^^^^^^^
```

Basta rodar com ele:

```bash
python main.py --seed 20260905
```

Reiniciar com `R` **também** repete o cenário: a semente é resolvida uma vez, quando o jogo abre, e
vale para todas as partidas daquela janela — inclusive quando ela foi sorteada. Cada `R` continua
gerando um par de arquivos novo, com um `id` diferente.

## Como funciona

Em [`farm/rng.py`](../farm/rng.py), duas funções:

- `resolve_seed(explicit)` — aplica a ordem de prioridade da tabela acima e sorteia se nada definir
  um número.
- `stream(seed, name, day)` — devolve o `random.Random` de um sistema num dia, a partir da chave
  `"{seed}:{name}:{day}"`.

A chave é uma **string** por dois motivos: uma tupla levantaria `TypeError` desde o Python 3.11, e
a string passa por `sha512` em vez de `hash()`, então o resultado é o mesmo entre processos, com ou
sem `PYTHONHASHSEED`.

O `name` separa os fluxos por sistema (hoje só existe `mercado`). É o que permite acrescentar um
sorteio novo ao jogo — clima, evento — sem deslocar o cenário das partidas antigas.

O `Market` refaz o `self.rng` no começo de cada dia, em `_roll_day`, antes de sortear estoque e
promoção. Recomeçar o fluxo todo dia é o que faz um dia não depender de por quais dias a partida
passou antes: pular direto para o dia 30 dá exatamente o mesmo resultado que caminhar até ele.
