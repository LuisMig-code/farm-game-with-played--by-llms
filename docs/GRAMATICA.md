# Gramática do plano diário

Especificação da DSL que o LLM emite e que o interpretador (`llm_agent/executor.py`) traduz em ações
do jogo. Segue a lógica do Projeto Fazenda, estendida com o que este jogo tem a mais:
fertilizante, apodrecimento e compra de fertilizante.

O princípio que organiza tudo: **o LLM decide, o interpretador conta.** Escolha de cultivo,
quantidade comprada, qual canteiro e ordem das paradas são julgamento — ficam com o modelo.
Caminho, contagem de células, controle de stamina e sobrevivência são aritmética — ficam com o
código.

---

## 1. Forma dos comandos

```
<comando> ::= IR <zona>
            | COLHER [<quantidade>]
            | PLANTAR <cultivo> [<quantidade>]
            | FERTILIZAR [<quantidade>]
            | LIMPAR [<quantidade>]
            | COMPRAR (<cultivo> | fertilizante) (<n> | LIMITE <n>)
            | VENDER <cultivo> [<quantidade>]

<quantidade> ::= TUDO | <n> | LIMITE <n>
```

Um comando por elemento do array `plano`. Sem prosa, sem numeração, sem coordenada.

**Uma regra só para a quantidade**, em todos os verbos: a palavra `LIMITE` é **opcional**
(`COLHER 3` é o mesmo que `COLHER LIMITE 3`) e `TUDO` — ou nenhuma quantidade — quer dizer "o que
der". A única exceção é `COMPRAR`, que **exige** o número: um comando não zera o caixa da run sem
dizer quanto. Cada grafia produz exatamente o mesmo comando, então `COLHER 3` e `COLHER LIMITE 3`
também têm o mesmo código de retorno.

| Categoria | Valores válidos |
| --- | --- |
| Verbos | `IR` `COLHER` `PLANTAR` `FERTILIZAR` `LIMPAR` `COMPRAR` `VENDER` |
| Zonas | `cama` `loja` `canteiro_esquerdo` `canteiro_direito` |
| Cultivos | `cenoura` `batata` `beterraba` `trigo` `melancia` |
| Quantificadores | `TUDO` · `<n>` · `LIMITE <n>` (a palavra `LIMITE` é opcional; ausente = `TUDO`, menos em `COMPRAR`) |

Maiúsculas e minúsculas são aceitas. Qualquer outro token é `ERRO_GRAMATICA`.

```json
["IR loja", "VENDER trigo TUDO", "COMPRAR trigo 12",
 "IR canteiro_esquerdo", "COLHER", "PLANTAR trigo TUDO"]
```

## 2. O que não está na gramática (e por quê)

- **`MOVER`** — deslocamento é o gargalo do jogo, mas resolvê-lo é BFS, não estratégia. `IR <zona>`
  anda pelo menor caminho; dentro do canteiro o interpretador vai sozinho à célula mais próxima.
- **`DORMIR`** — sempre implícito ao fim do plano.
- **Coordenada** — o modelo erraria, e não precisa: o código sabe quais células estão livres,
  prontas ou podres.
- **Filtro por cultivo em `COLHER`** — colhe tudo que está pronto no canteiro; `LIMITE` cobre o caso
  de dividir a stamina.

## 3. Semântica

- **Execução em ordem**, do topo para baixo. O que estiver no fim pode não acontecer.
- **Todo comando tolera execução parcial**: faz o que der e segue.
- **`COMPRAR <cultivo> n` compra sementes** daquele cultivo. `COMPRAR fertilizante n` compra
  fertilizante. Comprar e vender custam 0 de stamina e exigem estar na `loja`.
- **`COLHER`**, sem quantidade ou com `TUDO`, colhe todas as plantas prontas (e não podres) do
  canteiro. A célula fica livre na hora: plantar logo depois, na mesma viagem, é o uso esperado.
- **`PLANTAR <cultivo> TUDO`** planta enquanto houver semente e célula livre.
- **Um número é um teto**, não uma cota: `PLANTAR trigo 5` (ou `LIMITE 5`) planta **até** 5,
  parando antes se acabar a semente, a célula livre ou a stamina. Em `COMPRAR` e `VENDER` o número
  é a quantidade pedida, e comprar ou vender menos vira `PARCIAL` no feedback.
- **`COLHER TUDO`, `LIMPAR TUDO` e `PLANTAR <cultivo> <n>`** foram, nessa ordem, os erros de
  gramática mais comuns das runs: a linguagem passou a aceitar as três formas em vez de recusá-las.
- **`FERTILIZAR`** age em plantas ainda crescendo e não fertilizadas, até o limite de 3 por dia.
- **`LIMPAR`** arranca plantas podres: não rende nada, só libera a célula.
- Dentro do canteiro, **o alvo é sempre a célula mais próxima** (empate: menor coluna, depois menor
  linha).

## 4. Rede de segurança de stamina

Antes de cada trecho de caminhada e de cada ação de campo:

```
stamina >= passos_até_o_alvo + custo_da_ação + passos_do_alvo_até_a_cama + 1
```

O `+ 1` existe porque o jogo declara derrota com stamina 0 **mesmo em cima da cama**. Quando a conta
não fecha, o comando vira `TRUNCADO_STAMINA`, todos os seguintes também, e o jogador volta e dorme.
`IR` confere a ida inteira antes de sair, para não andar meio caminho só para voltar.

## 5. Códigos de retorno

Nunca se pede reenvio ao modelo: **comando inválido é descartado, o resto executa, e o erro volta
no feedback de amanhã.** Reenviar esconde o erro; reportar ensina.

| Código | Significado | O que sinaliza |
| --- | --- | --- |
| `OK` | executado por completo | — |
| `PARCIAL` | executado em parte | contabilidade otimista (moedas, estoque, caixa, limite diário) |
| `ERRO_GRAMATICA` | token fora do vocabulário | falta expressividade ou exemplo no prompt |
| `ERRO_CONTEXTO` | verbo certo, lugar ou época errados | perdeu a noção de onde está (ou plantou no inverno) |
| `ERRO_RECURSO` | falta semente, moeda, item ou alvo | erro de conta |
| `TRUNCADO_STAMINA` | cortado pela rede de segurança | erro de priorização |

| Verbo | Contexto exigido | Falha por recurso |
| --- | --- | --- |
| `IR` | qualquer | — |
| `COLHER` | canteiro | nada pronto |
| `PLANTAR` | canteiro, fora do inverno | sem semente / sem célula livre |
| `FERTILIZAR` | canteiro, fora do inverno | sem fertilizante / sem planta elegível / limite do dia |
| `LIMPAR` | canteiro | nenhuma planta podre |
| `COMPRAR` | loja | moedas, estoque da loja, limite do inventário |
| `VENDER` | loja | não tem o vegetal / caixa da loja acabou |

Todo `ERRO_GRAMATICA` é guardado em `erros_gramatica.csv` na pasta da run: quando o modelo insiste
em escrever algo que não existe, geralmente faltou expressividade na gramática.

## 6. Feedback do dia anterior

É o texto que o modelo recebe na chamada seguinte, gerado por `llm_agent/feedback.py`:

```
DIA 12 — executado
[1] IR loja                      OK (6 passos)
[2] VENDER trigo TUDO            OK (18 un -> 216 moedas)
[3] COMPRAR trigo 22             PARCIAL: comprou 6 de 22 (42 moedas): o estoque da loja acabou
[4] IR canteiro_esquerdo         OK (21 passos)
[5] COLHER                       OK (7 células)
[6] PLANTAR trigo TUDO           OK (6 de 7 células livres)
[7] PLANTAR beterraba LIMITE 5   ERRO_RECURSO: 0 sementes de beterraba
[--] volta para a cama           OK (17 passos)
stamina: 160 -> 107   (andando 44 | plantando 12 | colhendo 7 | fertilizando 0 | limpando 0)
moedas: 27 -> 201
```

A linha de stamina é a que expõe o gargalo: o deslocamento come mais que o trabalho. Quando algo
apodrece na virada da noite, ou o bloco de conhecimento passa do teto, o feedback também diz.
