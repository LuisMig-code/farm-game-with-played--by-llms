# Regras do jogo

O objetivo é cultivar sem ficar sem energia. Andar, plantar e colher gastam estamina; só dormir em
casa recupera. Chegar a zero encerra a partida.

Este arquivo tem o que vale para a partida inteira. O resto está separado por assunto:

| Documento | Assunto |
| --- | --- |
| [CULTIVO.md](CULTIVO.md) | plantar, crescer, fertilizar, validade e colher |
| [COMERCIO.md](COMERCIO.md) | preços, promoção, estoque, caixa da loja e oferta/demanda |
| [ESTACOES.md](ESTACOES.md) | o ciclo do ano e o que cada estação muda |
| [CONTROLS.md](CONTROLS.md) | teclas e o que o Espaço faz em cada célula |
| [LOGS.md](LOGS.md) | os arquivos que cada partida grava |
| [SEMENTE.md](SEMENTE.md) | a `SEED` que faz duas partidas terem o mesmo cenário |

O objetivo é cultivar sem ficar sem energia. Andar, plantar e colher gastam estamina; só
dormir em casa recupera. Chegar a zero encerra a partida.

## Estamina

| Ação | Custo |
| --- | --- |
| Andar uma célula | 1 |
| Plantar | 2 |
| Colher | 1 |
| Remover planta estragada | 2 |
| Usar fertilizante | 2 |

- O jogador começa cada dia com **160** de estamina (`STAMINA_MAX`).
- A célula só é cobrada quando o passo **termina**: esbarrar numa parede não custa nada.
- Plantar e colher são cobrados no fim da animação, junto com o efeito.
- **Chegar a 0 é derrota.** A partida congela e mostra o resumo da run.

Como o mapa é largo, o custo de ida e volta é o que limita o dia: da casa (17,12) até a
horta esquerda são ~17 células de ida, e o mesmo de volta.

## Dias e o dormir

- O jogo começa no **dia 1**. O dia atual aparece sempre no canto esquerdo do painel.
- Espaço na célula da casa (17,12) faz o jogador dormir: o dia avança em 1 e a estamina
  volta ao máximo. Uma tela curta anuncia o novo dia.
- Dormir é a **única** forma de passar o tempo — as plantas só crescem entre um dia e outro.
- Fora da casa o Espaço não dorme.

## Inventário

Mostrado na faixa inferior, com os 12 itens sempre visíveis (os zerados ficam esmaecidos):

- Sementes: batata, cenoura, beterraba, trigo, melancia
- Vegetais: batata, cenoura, beterraba, trigo, melancia
- Fertilizante e moeda

No começo da partida: **1 semente de cada tipo**, **2 fertilizantes**, 0 vegetais, 0 moedas.

O jogador carrega no máximo **20 sementes de cada tipo** e **9 fertilizantes**. Vegetais colhidos
e moedas não têm teto. Cada slot do painel mostra o teto embaixo do ícone (`max: 20`, `max: 9`);
vegetais e moedas não têm essa linha. Chegando no limite, a contagem e o `max:` ficam **dourados**
e a linha no menu da loja vira `você já carrega 20, o máximo`, desabilitada.

## Derrota

Ao zerar a estamina a tela escurece e mostra:

- o dia alcançado,
- quantas sementes de cada tipo foram plantadas,
- quantos vegetais de cada tipo foram colhidos,
- o que foi vendido e o que foi comprado, por tipo,
- as moedas ao final.

`R` começa uma partida nova do dia 1 (inventário inicial, campo vazio, jogador em casa) e
`ESC` sai do jogo.

## Registro das partidas

Cada run grava um `.log` de texto e um `.csv` com todas as ações, movimentação inclusa, em
`logs/`, mais um histórico de células estragadas que atravessa as partidas. Detalhes e colunas em
[LOGS.md](LOGS.md).

## Ainda não implementado

- **Estações e o resto do jogo**: as quatro estações já mudam cultivo e mercado; o que ainda não
  existe é efeito sobre estamina, custos ou zonas do mapa.
