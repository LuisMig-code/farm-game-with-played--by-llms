# Comércio

Tudo que acontece na célula (21,12): vender colheita, comprar semente e fertilizante, e os
sistemas que impedem a mesma jogada de funcionar para sempre.

No **inverno** os preços de venda são multiplicados e os sorteios da loja usam tabelas próprias —
ver [ESTACOES.md](ESTACOES.md).

## Como funciona a loja

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

A loja tem **200 moedas por dia** para pagar por colheita — **300 no inverno**, onde os preços são multiplicados (ver [ESTACOES.md](ESTACOES.md)). Cada venda desconta o preço pago desse
caixa, e quando o que sobra não cobre um item, a linha dele no menu fica desabilitada com
`(sem saldo)` — não dá para liquidar a colheita inteira de uma vez.

**Comprar devolve caixa ao mercado**: cada moeda gasta na loja levanta o teto do dia na mesma
medida. Gastar 21 numa saca de fertilizante leva o caixa de 200 para 221, e isso funciona mesmo
depois de ele ter zerado — comprar reabre espaço para vender.

O caixa **não acumula**: ao dormir ele volta a 200 exatos, por mais que o jogador tenha comprado
no dia anterior. O quadro de preços mostra o valor corrente logo abaixo do título
(`caixa 143/200`), em vermelho quando não cobre nem o item mais barato do dia.

### Oferta e demanda

Para o preço de uma cultura começar a cair é preciso estar no **dia 11 ou depois** — antes disso
nada é sequer contado, para dar tempo de acumular patrimônio — **e** disparar um destes dois
gatilhos, qualquer um deles:

1. **Repetição**: ter vendido aquela cultura **ontem e também hoje**. A quantidade não importa,
   1 unidade em cada um dos dois dias já basta.
2. **Volume**: ter vendido **7 ou mais unidades** dela **hoje**, mesmo sem ter vendido ontem. Sem
   isso dava para chegar na loja com 40 melancias, despejar tudo num dia só e não sofrer nada.

A contagem começa **quando o gatilho dispara**, não retroativamente: num despejo isolado as 6
primeiras saem pelo preço cheio e a **7ª** é a primeira a derrubar 1 moeda. Dali em diante cada
unidade derruba mais 1, até o piso do **preço da própria semente**: vender continua empatando com o
custo, mas para de dar lucro.

Pelo gatilho da repetição, como nada é contado antes do dia 11, o dia 11 nunca tem um "ontem"
válido e a primeira queda por repetição só pode acontecer no **dia 12**. Pelo gatilho de volume ela
pode acontecer já no dia 11.

Cada dia **sem vender** aquela cultura devolve 1 moeda ao preço, até voltar ao valor original, e
um único dia parado já quebra a sequência — o "ontem" zera e é preciso começar de novo. Vender dia
sim, dia não nunca derruba nada. Na prática, isso força um rodízio: alternar culturas mantém os
preços cheios, insistir na mesma derruba 1 moeda por unidade sem recuperação nenhuma.

## Limite do inventário

O jogador carrega no máximo **20 sementes de cada tipo** e **9 fertilizantes**. Vegetais colhidos e
moedas não têm teto. Cada slot do painel mostra o teto embaixo do ícone (`max: 20`, `max: 9`);
chegando no limite, a contagem e o `max:` ficam dourados e a linha no menu da loja vira
`você já carrega 20, o máximo`, desabilitada.
