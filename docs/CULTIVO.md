# Cultivo

Plantar, fertilizar, esperar crescer e colher antes de estragar. As regras aqui são as do ritmo
**padrão**; cada estação do ano altera prazos e bloqueios — ver [ESTACOES.md](ESTACOES.md).

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

## Custos de estamina

| Ação | Custo |
| --- | --- |
| Plantar | 2 |
| Colher | 1 |
| Usar fertilizante | 2 |
| Remover planta estragada | 2 |

Os valores completos, incluindo o custo de andar, estão em [GAME_RULES.md](GAME_RULES.md).
