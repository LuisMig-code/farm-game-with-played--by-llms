# Regras do jogo

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

## Plantar, fertilizar e colher

Espaço é contextual — depende da célula em que o jogador está parado (ele precisa estar
parado no centro de uma célula; apertando durante um passo, nada acontece):

| Célula | O que acontece |
| --- | --- |
| Casa (17,12) | dorme |
| Comércio (21,12) | abre a loja: vender colheita ou comprar |
| Plantável vazia | abre o menu de sementes; sem nenhuma semente, a opção fica desabilitada |
| Plantável com planta ainda pequena | abre o menu com "Usar fertilizante" |
| Plantável com planta crescida | colhe direto, sem menu |
| Plantável com planta estragada | arranca a planta, sem menu e sem receber nada |
| Qualquer outra | nada |

- **Plantar** roda a animação de plantio, consome 1 semente e 2 de estamina, e deixa a
  célula no estágio 1. A cultura é registrada com o dia do plantio.
- **Colher** roda a animação de colheita, dá 1 unidade do vegetal, custa 1 de estamina e
  libera a célula para um novo plantio.
- **Fertilizante** consome 1 unidade e 2 de estamina, e muda o prazo da planta — ver a seção
  abaixo.

## Crescimento

O estágio não é guardado: sai da diferença entre o dia atual e o dia do plantio. Plantando
no dia D:

| Cultura | Dias para crescer | Estágio 1 | Estágio 2 (germinando) | Estágio 3 (colhível) |
| --- | --- | --- | --- | --- |
| Cenoura | 2 | dia D | D+1 | D+2 |
| Batata | 3 | dia D | D+1 a D+2 | D+3 |
| Beterraba | 5 | dia D | D+1 a D+4 | D+5 |
| Trigo | 7 | dia D | D+1 a D+6 | D+7 |
| Melancia | 9 | dia D | D+1 a D+8 | D+9 |

As imagens são `Assets/props/<cultura> 1|2|3.png`, ancoradas pela base da célula. Só o
estágio 3 pode ser colhido; nos outros o Espaço abre o menu de fertilizante.

Abaixo de cada planta há uma **barrinha de crescimento** no rodapé da célula, preenchida na
proporção `dias passados / dias necessários`. Ela fica **âmbar** enquanto a planta cresce e
**verde e cheia** quando está pronta para colher — dá para varrer a horta de longe e ver o
que já dá para colher sem passar célula por célula.

## Derrota

Ao zerar a estamina a tela escurece e mostra:

- o dia alcançado,
- quantas sementes de cada tipo foram plantadas,
- quantos vegetais de cada tipo foram colhidos,
- o que foi vendido e o que foi comprado, por tipo,
- as moedas ao final.

`R` começa uma partida nova do dia 1 (inventário inicial, campo vazio, jogador em casa) e
`ESC` sai do jogo.

## Fertilizante

Usar custa **1 fertilizante e 2 de estamina**, roda a animacao propria de regar (`fertilizing`)
e faz duas coisas de uma vez: encurta o crescimento e estica a validade. Como nas outras acoes, o
efeito so vale quando a animacao termina.

| Cultura | Cresce em | Fertilizada cresce em | Dura | Fertilizada dura |
| --- | --- | --- | --- | --- |
| Cenoura | 2 | −1 → **1** | 3 | +2 → **5** |
| Batata | 3 | −2 → **1** | 3 | +2 → **5** |
| Beterraba | 5 | −2 → **3** | 3 | +4 → **7** |
| Trigo | 7 | −2 → **5** | 4 | +4 → **8** |
| Melancia | 9 | −3 → **6** | 4 | +4 → **8** |

**Crescimento instantâneo**: como o estágio sai da idade da planta, encurtar o prazo pode fazê-la
ficar pronta na hora. Fertilizar uma cenoura de 1 dia leva o prazo para 1 e ela vira estágio 3 no
mesmo instante, sprite e tudo. É o caso do "0 ou menos dias restantes".

Limites:

- **3 fertilizantes por dia**, no total. Chegando lá, a opção fica desabilitada como
  `Limite de 3 por dia`; dormir zera a conta.
- **Um por planta**. Na segunda vez a opção vira `Já fertilizada` e não gasta nada.
- **Só antes de crescer**. Em planta pronta o Espaço colhe, em planta podre ele remove — nos dois
  casos o menu de fertilizante nem abre.

A data de apodrecer **nunca é antecipada**: o saldo entre o corte no crescimento e o bônus de
validade é positivo em todas as culturas, e zero na batata.

## Validade

Depois de crescer, a planta **não fica boa para sempre**. Cada cultura aguenta alguns dias no
estágio 3 e, passado o prazo, apodrece: o sprite vira `props/<cultura> 4.png`, ela deixa de poder
ser colhida e ainda ocupa a célula.

| Cultura | Cresce em | Dura | Apodrece em |
| --- | --- | --- | --- |
| Cenoura | 2 dias | 3 dias | D+5 |
| Batata | 3 dias | 3 dias | D+6 |
| Beterraba | 5 dias | 3 dias | D+8 |
| Trigo | 7 dias | 4 dias | D+11 |
| Melancia | 9 dias | 4 dias | D+13 |

Assim que a planta cresce, aparece uma **segunda barrinha acima dela** mostrando quanto tempo
resta: **verde** com 3 dias ou mais, **âmbar** com 2, **vermelho** no último dia. A barra de
crescimento continua no rodapé da célula.

Planta apodrecida **não mostra barra nenhuma** — as duas somem. Uma barra de crescimento cheia e
verde em cima de uma planta podre passaria a mensagem errada; o sprite escuro já diz o que houve.

Para liberar a célula é preciso ir até lá e apertar Espaço: a remoção custa **2 de estamina**,
não rende nada e usa a mesma animação da colheita. Depois disso dá para plantar de novo.

## Comércio

Espaço na célula (21,12) abre a loja. **Negociar não custa estamina** — só o caminho até lá.
O menu tem dois níveis: "Vender colheita" / "Comprar sementes e fertilizante", e dentro de cada
um o Espaço negocia **1 unidade por vez** sem fechar o menu, então dá para repetir. ESC volta um
nível; ESC de novo fecha.

Os preços ficam sempre visíveis num quadro alinhado ao grid, nas linhas livres acima do prédio
da loja (colunas 19-26, linhas 0-4). Quando um preço está diferente do base, o base aparece
riscado em cima e o atual embaixo — dourado para promoção, vermelho para mercado saturado.

| Cultura | A loja paga | A semente custa |
| --- | --- | --- |
| Cenoura | 3 | 2 |
| Batata | 6 | 4 |
| Beterraba | 9 | 6 |
| Trigo | 12 | 7 |
| Melancia | 18 | 11 |

O fertilizante custa **21** e não é vendável.

### Promoção do dia

Todo dia, ao dormir (e no começo da run, para o dia 1), a loja sorteia promoções **apenas nos
itens de compra** — as 5 sementes e o fertilizante. São três sorteios encadeados:

1. **Quantos itens**, em casos mutuamente exclusivos: **1 item com 40%**, **2 itens com 25%**,
   **3 itens com 10%** e **nenhum com 25%** — promoção em três de cada quatro dias.
2. **Quais itens**, sorteados **só entre os que têm estoque naquele dia** — não se anuncia
   desconto em semente que a loja não tem. Entre os disponíveis a escolha é uniforme, sem peso
   nenhum, e eles saem distintos.
3. **O desconto**, sorteado **uma vez para cada item** e não uma vez para o dia: com dois itens em
   promoção, um pode sair com 1 moeda de desconto e o outro com 3. Aqui, e só aqui, existe peso:
   1 moeda (50%), 2 (30%), 3 (15%), 5 (5%).

Item com preço abaixo de 3 — só a semente de cenoura, que custa 2 — recebe sempre o menor
desconto. E o desconto nunca leva o preço abaixo de 1: **nada sai de graça**.

### Estoque do dia

A loja não tem oferta infinita: todo dia ela sorteia quanto tem de cada item, uniformemente
dentro da faixa abaixo. O estoque baixa a cada compra e **não acumula** — dormir sorteia tudo de
novo, sobrando ou não.

| Item | Estoque do dia |
| --- | --- |
| Semente de cenoura | 1 a 30 |
| Semente de batata | 1 a 35 |
| Semente de beterraba | 0 a 25 |
| Semente de trigo | 0 a 25 |
| Semente de melancia | 0 a 15 |
| Fertilizante | 1 a 6 |

Beterraba, trigo e melancia podem simplesmente **não estar à venda** num dia. O número aparece no
menu de compra (`Semente de Batata   4 moedas   12 no estoque`), e item zerado vira
`esgotado hoje`, desabilitado. O quadro de preços continua só com preços — os seis números de
estoque não caberiam nas células sem virar sopa.

### Caixa diário da loja

A loja tem **200 moedas por dia** para pagar por colheita. Cada venda desconta o preço pago desse
caixa, e quando o que sobra não cobre um item, a linha dele no menu fica desabilitada com
`(sem saldo)` — não dá para liquidar a colheita inteira de uma vez.

**Comprar devolve caixa ao mercado**: cada moeda gasta na loja levanta o teto do dia na mesma
medida. Gastar 21 numa saca de fertilizante leva o caixa de 200 para 221, e isso funciona mesmo
depois de ele ter zerado — comprar reabre espaço para vender.

O caixa **não acumula**: ao dormir ele volta a 200 exatos, por mais que o jogador tenha comprado
no dia anterior. O quadro de preços mostra o valor corrente logo abaixo do título
(`caixa 143/200`), em vermelho quando não cobre nem o item mais barato do dia.

### Oferta e demanda

São **duas condições somadas** para o preço de uma cultura começar a cair:

1. Estar no **dia 11 ou depois** — antes disso nada é sequer contado, para dar tempo de acumular
   patrimônio. Ninguém leva uma conta acumulada de uma vez quando o sistema liga.
2. Ter vendido aquela cultura **ontem e também hoje**. A quantidade não importa: **1 unidade em
   cada um dos dois dias já basta**. O que o mercado pune é a repetição, não o volume.

Como nada é contado antes do dia 11, o dia 11 nunca tem um "ontem" válido — na prática a primeira
queda possível é no **dia 12**. A partir do gatilho, cada unidade vendida derruba 1 moeda, até o
piso do **preço da própria semente**: vender continua empatando com o custo, mas para de dar lucro.

Cada dia **sem vender** aquela cultura devolve 1 moeda ao preço, até voltar ao valor original, e
um único dia parado já quebra a sequência — o "ontem" zera e é preciso começar de novo. Vender dia
sim, dia não nunca derruba nada. Na prática, isso força um rodízio: alternar culturas mantém os
preços cheios, insistir na mesma derruba 1 moeda por unidade sem recuperação nenhuma.

## Registro das partidas

Cada run grava um `.log` de texto e um `.csv` com todas as ações, movimentação inclusa, em
`logs/`. Detalhes e colunas em [LOGS.md](LOGS.md).

## Ainda não implementado

- **Estações**: os ícones `icon verao/outono/inverno.png` existem, mas não há sistema por trás.
