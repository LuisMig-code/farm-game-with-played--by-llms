# Estações do ano

O ano roda em **4 estações de 30 dias cada**, na ordem Primavera → Verão → Outono → Inverno e de
volta. A run começa no dia 1, na primavera.

| Estação | Dias | Fundo |
| --- | --- | --- |
| Primavera | 1-30 | `main-background.png` |
| Verão | 31-60 | `main-background-summer.png` |
| Outono | 61-90 | `main-background-fall.png` |
| Inverno | 91-120 | `main-background-winter.png` |

Depois do dia 120 o ciclo recomeça na primavera. Como tudo é derivado do dia, não há estado
guardado: o dia 121 é primavera pelo mesmo cálculo que faz o dia 1 ser.

**Por enquanto isso é só visual.** Nenhuma mecânica muda com a estação — preços, crescimento,
validade, estamina e mercado funcionam igual o ano inteiro.

## Transição visual

Nos últimos 4 dias da estação o fundo da próxima vai aparecendo por cima, para a virada não ser um
corte seco:

| Dias restantes | Opacidade do novo fundo |
| --- | --- |
| 4 | 20% |
| 3 | 40% |
| 2 | 60% |
| 1 | 80% |

No dia seguinte a estação virou e o fundo novo aparece inteiro. Os quatro fundos são o mesmo mapa
desenhado nas quatro estações, alinhados pixel a pixel, então a mistura não desloca nada.

## Indicador na tela

No topo da tela, à esquerda do quadro de preços, um painel mostra o ícone e o nome da estação
atual em destaque e, menores, o ícone e o nome da próxima com quantos dias faltam para ela.

## O que cada estação muda

| | Primavera | Verão | Outono | Inverno |
| --- | --- | --- | --- | --- |
| Crescimento | padrão | padrão | **+1 dia** | não cresce |
| Validade | padrão | **ver abaixo** | padrão | — |
| Fertilizante | padrão | padrão | padrão | **não funciona** |
| Plantar | sim | sim | sim | **bloqueado** |
| Preço de venda | padrão | padrão | padrão | **multiplicado** |
| Promoção | 40/25/10 | 40/25/10 | 40/25/10 | **50/30/20** |
| Desconto | 50/30/15/5 | 50/30/15/5 | 50/30/15/5 | **30/35/25/10** |
| Caixa da loja | 200 | 200 | 200 | **300** |

### O prazo congela no plantio

A estação usada para calcular crescimento e validade é a do **dia do plantio**, não a do dia atual.
Uma cenoura plantada no verão continua com a validade curta do verão mesmo depois da virada para o
outono, e uma plantada no outono mantém o dia a mais de crescimento.

Sem isso uma planta pronta poderia voltar a não estar pronta na virada, e as barras andariam para
trás. Do jeito que está, o estágio de uma planta nunca regride.

### Verão: a colheita estraga rápido

| Cultura | Validade normal | No verão |
| --- | --- | --- |
| Cenoura | 3 dias | **1 dia** |
| Batata | 3 dias | **1 dia** |
| Beterraba | 3 dias | **2 dias** |
| Trigo | 4 dias | **2 dias** |
| Melancia | 4 dias | **2 dias** |

O crescimento e o fertilizante seguem o padrão.

### Outono: um dia a mais para crescer

Todas as culturas levam **+1 dia** para ficarem prontas. Validade e fertilizante seguem o padrão.

### Inverno: a lavoura fecha, o celeiro paga

- **Não dá para plantar.** O menu de sementes abre com `Nada cresce no inverno`, desabilitado.
- **O fertilizante não funciona.** O menu abre com `Não funciona no inverno`.
- **Na virada para o inverno, tudo que está no chão apodrece na hora** — inclusive o que já estava
  pronto para colher. Quem não colheu até o dia 90 perde a lavoura, e as células ficam ocupadas até
  serem limpas (2 de estamina cada).
- **A venda vale muito mais:**

| Cultura | Preço normal | No inverno |
| --- | --- | --- |
| Cenoura | 3 | ×2 → **6** |
| Batata | 6 | ×2 → **12** |
| Beterraba | 9 | ×2 → **18** |
| Trigo | 12 | ×2,5 → **30** |
| Melancia | 18 | ×3 → **54** |

O multiplicador entra no preço base; a saturação por excesso de venda continua descontando por
cima, com o mesmo piso do preço da semente. No quadro de preços o valor aparece em **verde**, com o
preço normal riscado — verde é bônus, vermelho é perda.

- **A loja sorteia diferente**: promoção em **1 item (50%), 2 (30%) ou 3 (20%)** — todo dia de
  inverno tem promoção — e o desconto pesa **1 moeda (30%), 2 (35%), 3 (25%), 5 (10%)**.
- **O caixa diário sobe para 300 moedas** (em vez de 200). Sem isso, com a melancia a 54, a loja
  esgotaria o dinheiro do dia em menos de quatro vendas — o preço melhor não adiantaria de nada.

O inverno é, na prática, a estação de esvaziar o celeiro pelos melhores preços do ano e comprar
semente barata para a primavera.
