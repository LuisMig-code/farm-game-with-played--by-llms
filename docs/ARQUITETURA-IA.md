# Arquitetura: LLMs jogando o jogo

Sistema para fazer modelos de linguagem jogarem uma run completa via OpenRouter, sem treino,
medindo se o modelo **aprende** ao longo dos dias.

Referências de regras: [GAME_RULES.md](GAME_RULES.md), [CULTIVO.md](CULTIVO.md),
[COMERCIO.md](COMERCIO.md), [ESTACOES.md](ESTACOES.md), [LOGS.md](LOGS.md).

---

## 1. Escopo

| Parâmetro | Valor |
| --- | --- |
| Horizonte | **121 dias** (ano completo + 1 dia de primavera) |
| Score | **moedas ao fim do dia 121** — inventário não conta |
| Derrota | **impossível**: rede de segurança leva o jogador para casa |
| Chamadas por run | **1 + 121** |
| Temperatura | **0** |
| Seeds por configuração | *a definir — recomendação: 5* |
| Modelos | ≥ 5, definidos depois |
| Modos na 1ª leva | `principal` e `sem_memoria` |

O modelo **sabe** que o horizonte é 121 dias e que o score são moedas puras. Isso vai
explícito no prompt de estratégia e no snapshot diário (campo `dias_restantes`), porque
liquidar o celeiro no fim é uma jogada legítima que queremos observar se ele descobre.

---

## 2. Camadas

```
┌─────────────────────────────────────────────┐
│  runner.py        orquestra o experimento    │
│                   (modelos × seeds × modos)  │
├─────────────────────────────────────────────┤
│  agent/           prompts, chamada OpenRouter│
│                   parsing, caderno           │
├─────────────────────────────────────────────┤
│  harness/         snapshot, validador,       │
│                   executor, relatório        │
├─────────────────────────────────────────────┤
│  farm/core        GameState puro (sem pygame)│
├─────────────────────────────────────────────┤
│  farm/render      pygame — opcional          │
└─────────────────────────────────────────────┘
```

Tudo no **mesmo processo**, chamada de função direta. A camada de render é plugável: com ela
desligada roda headless e rápido; ligada, grava a tela do agente jogando.

### 2.1 O que o modo headless exige

Hoje a lógica está acoplada ao pygame. O refactor mínimo:

1. **`GameState` puro** — dia, estamina, inventário, grid de plantas, RNG, contadores de
   saturação, caixa da loja, estoque e promoções do dia. Zero import de pygame.
2. **API de mutação** com retorno estruturado, não booleano:
   `mover_um_passo(dir)`, `plantar(cultura)`, `colher()`, `fertilizar()`, `remover()`,
   `comprar(item, qtd)`, `vender(cultura, qtd)`, `dormir()`.
   Cada uma devolve `{ok, motivo, custo_estamina, delta_inventario, delta_moedas}`.
3. **Sem animação no caminho lógico.** Hoje o efeito só vale quando a animação termina. No
   headless o efeito é imediato; o render, se ligado, roda a animação por cima do estado já
   aplicado. Isso não muda nenhum resultado porque nada acontece *durante* a animação.
4. **`farm/zones.py` exposto** — o executor precisa do grafo das 136 células andáveis para
   calcular rotas.

O jogo visual passa a ser um cliente do `GameState`, não o dono dele.

### 2.2 Seed

Um único inteiro por run determina **tudo** que é sorteado: estoque diário dos 6 itens,
quantos itens entram em promoção, quais e qual desconto. Um `random.Random(seed)` no
`GameState`, nunca o `random` global.

Requisito duro: **duas runs com a mesma seed e o mesmo plano produzem estado idêntico dia a
dia.** Sem isso o controle "mesma seed repetida" não existe. Vale escrever um teste que roda
a mesma seed duas vezes com um plano fixo e compara os CSVs byte a byte.

---

## 3. O loop

```
chamada 0 ──► estratégia da run  ──► caderno inicial (20 linhas)
                                       │
     ┌─────────────────────────────────┘
     │
     ▼
  dia D ──► snapshot ──► chamada D ──► {plano, caderno}
                              │
                              ▼
                         validação estática
                              │
                    ┌─────────┴─────────┐
                 sem erro            com erro
                    │                   │
                    │            1 correção ──► ainda com erro
                    │                   │              │
                    ▼                   ▼              ▼
                  executor      executor         prefixo válido
                                                  e para
                              │
                              ▼
                     relatório do dia ──► dorme ──► dia D+1
```

Sem revisão de estação e sem preflight de estamina. O orçamento de estamina **não é
pré-validado**: o modelo descobre que errou pelo truncamento no relatório do dia seguinte.
Isso é intencional — o truncamento é o principal sinal de aprendizado.

**Dormir é implícito.** O plano descreve o dia; quando ele termina (ou é truncado), o
executor leva o jogador para casa e dorme. Não existe verbo `DORMIR`.

---

## 4. Gramática

O modelo devolve JSON, mas o plano é uma **lista de strings** em DSL. Assim a validação é
trivial e o log continua legível.

```json
{
  "raciocinio": "texto curto, máx 800 caracteres",
  "plano": [
    "IR loja",
    "VENDER trigo TUDO",
    "COMPRAR semente_trigo 18",
    "IR canteiro_esquerdo",
    "COLHER TUDO",
    "PLANTAR trigo TUDO"
  ],
  "caderno": ["[REGRA] ...", "[NUMERO] ..."]
}
```

### 4.1 Vocabulário

| Categoria | Valores válidos |
| --- | --- |
| Verbos | `IR` `COLHER` `PLANTAR` `FERTILIZAR` `LIMPAR` `COMPRAR` `VENDER` |
| Zonas | `cama` `loja` `canteiro_esquerdo` `canteiro_direito` |
| Cultivos | `cenoura` `batata` `beterraba` `trigo` `melancia` |
| Itens de compra | `semente_cenoura` `semente_batata` `semente_beterraba` `semente_trigo` `semente_melancia` `fertilizante` |
| Quantificadores | `TUDO` · `LIMITE <n>` · `<n>` |

Qualquer token fora dessas listas é `ERRO_GRAMATICA`. Os IDs batem letra por letra com os do
engine.

### 4.2 Assinaturas

| Ação | Zona exigida | Semântica |
| --- | --- | --- |
| `IR <zona>` | — | move até a zona; em canteiro, até a célula de entrada |
| `COLHER <cultivo\|TUDO> [LIMITE n]` | canteiro | colhe estágio 3 do filtro |
| `PLANTAR <cultivo> <TUDO\|LIMITE n\|n>` | canteiro | planta em células vazias |
| `FERTILIZAR <cultivo\|TUDO> [LIMITE n]` | canteiro | plantas não crescidas e não fertilizadas |
| `LIMPAR [LIMITE n]` | canteiro | arranca plantas podres |
| `COMPRAR <item> <n>` | loja | compra n unidades |
| `VENDER <cultivo> <TUDO\|n>` | loja | vende n unidades |

`TUDO` em `PLANTAR` é limitado pelo menor entre células vazias e sementes no inventário.
`TUDO` em `VENDER` é limitado pelo inventário, pelo caixa da loja e pelo piso de preço.

### 4.3 Execução parcial

Uma ação nunca falha em bloco. Ela executa o que couber e o resultado é classificado:

| Status | Quando |
| --- | --- |
| `EXECUTADO` | a ação rodou inteira |
| `TRUNCADO` | rodou em parte — sempre com `motivo` e `quantidade_efetiva` |
| `NAO_EXECUTADO` | não rodou nada — sempre com `motivo` |

Motivos de truncamento: `SEM_ESTAMINA`, `SEM_ESTOQUE`, `SEM_CAIXA_LOJA`,
`LIMITE_INVENTARIO`, `SEM_CELULA_LIVRE`, `SEM_ALVO`, `LIMITE_FERTILIZANTE_DIARIO`.

`VENDER melancia TUDO` no inverno com 12 melancias e caixa de 300: vende 5 (5 × 54 = 270),
para em `SEM_CAIXA_LOJA` e o relatório mostra `TRUNCADO 5/12`. É exatamente o tipo de lição
que queremos ver virar linha de caderno.

---

## 5. Executor

### 5.1 Ordem literal

O executor **não reordena nada**. A sequência de `IR` dada pelo modelo é a rota, e um plano
que faz loja → canteiro → loja → canteiro paga os 21 passos de cada trecho. Ordenar bem é
parte da habilidade medida.

### 5.2 Rotas entre zonas

BFS sobre as 136 células andáveis. Distâncias fixas, entregues ao modelo no snapshot:

| De → Para | Passos |
| --- | --- |
| cama ↔ loja | 6 |
| cama ↔ canteiro_esquerdo | 17 |
| cama ↔ canteiro_direito | 22 |
| loja ↔ canteiro_esquerdo | 21 |
| loja ↔ canteiro_direito | 18 |
| canteiro_esquerdo ↔ canteiro_direito | 37 |

Célula de entrada: `(6,8)` no canteiro esquerdo, `(33,8)` no direito. O custo **dentro** do
canteiro é adicional e depende de quantas células a ação toca.

### 5.3 Rota dentro do canteiro

O canteiro tem 49 células. Percorrer todas custa 48 passos, então a rota interna importa
tanto quanto a externa.

**Regra: guloso pelo mais próximo.** A partir da posição atual, vai à célula-alvo mais
próxima ainda não visitada, executa, repete. Empate resolvido por menor `col`, depois menor
`lin`. Só células-alvo entram na rota — `COLHER melancia` não passeia por onde tem trigo.

A regra é determinística e vai documentada no prompt, porque ela muda o cálculo de custo
do modelo.

Ordem de escolha de alvo por verbo:

- `PLANTAR` — célula vazia mais próxima.
- `COLHER` / `LIMPAR` — alvo mais próximo.
- `FERTILIZAR` — planta elegível mais próxima. *(ver decisão em aberto #3)*

### 5.4 Rede de segurança

O jogador nunca perde. **Antes** de cada ação atômica (um passo, um plantio, uma colheita), o
executor verifica:

```
estamina_atual >= custo(acao) + distancia(celula_apos_acao, cama)
```

Se não passa, o plano é abortado ali, o executor caminha até a cama e dorme. A ação em curso
vira `TRUNCADO / SEM_ESTAMINA` e todas as seguintes viram `NAO_EXECUTADO / SEM_ESTAMINA`.

O relatório do dia informa quantas ações foram perdidas e quanta estamina sobrou ao chegar em
casa. Estamina desperdiçada é uma das métricas principais.

---

## 6. Validação

Roda antes do executor, sobre o plano inteiro, simulando inventário e regras **sem** simular
estamina.

| Código | Exemplo |
| --- | --- |
| `ERRO_GRAMATICA` | token desconhecido, aridade errada |
| `ERRO_ZONA` | `VENDER` sem estar na loja |
| `ERRO_ESTACAO` | `PLANTAR` no inverno, `FERTILIZAR` no inverno |
| `ERRO_LIMITE_INVENTARIO` | `COMPRAR semente_trigo 22` com teto de 20 |
| `ERRO_RECURSO` | `PLANTAR trigo 5` com 2 sementes |
| `ERRO_LIMITE_DIARIO` | 4º fertilizante do dia |

Erro → devolve a lista de erros ao modelo → **1 correção**. Se o plano corrigido ainda tiver
erro, executa o **prefixo válido** até o primeiro erro e para.

`ERRO_RECURSO` é fronteiriço: se o plano compra sementes antes de plantar, a simulação
precisa contar a compra. Por isso a validação é sequencial, não linha a linha isolada.

A **contagem de erros por dia é métrica de primeira classe** — provavelmente mais limpa que
lucro, que sobe sozinho com o tempo.

---

## 7. Snapshot diário

O que o modelo vê no início do dia D. Estado observável completo — sem névoa de guerra.

```json
{
  "dia": 47,
  "dias_restantes": 74,
  "estacao": "verao",
  "dias_ate_proxima_estacao": 14,
  "proxima_estacao": "outono",
  "proxima_estacao_muda": ["crescimento +1 dia"],
  "estamina": 160,

  "inventario": {
    "moedas": 412,
    "sementes": {"trigo": 6, "melancia": 0, "...": 0},
    "vegetais": {"trigo": 14, "...": 0},
    "fertilizante": 3
  },

  "loja": {
    "caixa": 200,
    "precos_venda": {
      "trigo": {"base": 12, "atual": 9, "piso": 7, "motivo": "saturacao"}
    },
    "precos_compra": {
      "semente_trigo": {"base": 7, "atual": 5, "promocao": true, "estoque": 12},
      "fertilizante": {"base": 21, "atual": 21, "promocao": false, "estoque": 0}
    }
  },

  "mercado": {
    "vendido_ontem": ["trigo"],
    "dias_sem_vender": {"melancia": 3, "cenoura": 12}
  },

  "canteiro_esquerdo": {
    "celulas_totais": 49,
    "vazias": 12,
    "podres": 3,
    "por_cultivo": {
      "trigo": {"total": 20, "colhivel": 8, "crescendo": 12}
    },
    "prontas_hoje": 8,
    "apodrecem_em_1_dia": 5,
    "apodrecem_em_2_dias": 3
  },

  "canteiro_direito": { "...": "idem" },

  "distancias": { "cama-loja": 6, "...": 0 },

  "relatorio_ontem": { "...": 0 },
  "caderno": ["..."]
}
```

**Agregado, não célula a célula.** Como a gramática opera por zona, a tabela de 98 células
seria ruído caro. O que o modelo precisa decidir é *quanto* colher e *quando* plantar, e isso
sai dos agregados. O campo `apodrecem_em_1_dia` é o que evita perder colheita.

`dias_ate_proxima_estacao` e `proxima_estacao_muda` ficam no snapshot, não no caderno — são
fato do dia, não aprendizado. Na virada para o inverno, `proxima_estacao_muda` traz o aviso
completo: nada cresce, fertilizante não funciona, **tudo que está no chão apodrece na hora**,
e os preços de venda sobem.

---

## 8. Caderno

Máximo **20 linhas**, reescrito por inteiro a cada dia. Substituição total, não operações de
edição — mais tokens, muito menos bug, e o diff diário fica limpo.

| Tipo | Para quê | Exemplo |
| --- | --- | --- |
| `[REGRA]` | mecânica descoberta | `[REGRA] Vender 7+ da mesma cultura no mesmo dia derruba 1 moeda por unidade. (dia 14)` |
| `[NUMERO]` | custo ou distância medida | `[NUMERO] Cama até canteiro esquerdo: 17 passos. Ida e volta 34. (dia 3)` |
| `[CALENDARIO]` | prazo com dia fixo | `[CALENDARIO] Último dia para plantar melancia antes do inverno: dia 81.` |
| `[ERRO]` | erro cometido e correção | `[ERRO] Dia 22: pedi 4 fertilizantes, o limite é 3 por dia.` |

**Validação do caderno:** linha sem prefixo válido é rejeitada; linha sem nenhum número ou
referência concreta é rejeitada. Linhas rejeitadas são descartadas e o caderno segue com as
válidas — não gera erro nem consome a rodada de correção. A contagem de linhas rejeitadas
por dia é métrica: mede quanto o modelo tende à platitude.

Cada versão do caderno é salva. O diff entre o dia 20 e o dia 100 é o artefato mais
interessante do experimento.

No modo `sem_memoria` o caderno é sempre vazio na entrada, mas o modelo continua sendo
solicitado a escrevê-lo — assim o custo de tokens e o formato da resposta ficam idênticos, e
a única variável é o que ele recebe.

---

## 9. Relatório do dia

Gerado pelo código, factual. É isso que o modelo lê no dia seguinte, junto com o caderno.

```json
{
  "dia": 46,
  "acoes": [
    {"acao": "IR loja", "status": "EXECUTADO", "custo": 6},
    {"acao": "VENDER melancia TUDO", "status": "TRUNCADO",
     "efetivo": 5, "pedido": 12, "motivo": "SEM_CAIXA_LOJA",
     "moedas_ganhas": 270, "preco_unitario": 54},
    {"acao": "IR canteiro_esquerdo", "status": "EXECUTADO", "custo": 21},
    {"acao": "COLHER TUDO", "status": "TRUNCADO",
     "efetivo": 22, "pedido": 31, "motivo": "SEM_ESTAMINA"},
    {"acao": "PLANTAR trigo TUDO", "status": "NAO_EXECUTADO",
     "motivo": "SEM_ESTAMINA"}
  ],
  "erros_validacao": [],
  "correcao_usada": false,
  "estamina_gasta": 160,
  "estamina_sobrando_ao_dormir": 0,
  "retorno_forcado": true,
  "retorno_forcado_em": "canteiro_esquerdo",
  "moedas_inicio": 142,
  "moedas_fim": 412,
  "apodreceram_na_virada": [{"cultivo": "trigo", "quantidade": 4}]
}
```

`retorno_forcado: true` é o sinal mais importante do relatório. Se ele aparece dia após dia e
o caderno nunca ganha uma linha `[NUMERO]` sobre orçamento de estamina, o modelo não está
aprendendo.

---

## 10. Chamadas

**Chamada 0 — estratégia.** Recebe as regras completas (os 6 `.md`), o horizonte de 121 dias,
a função objetivo, a gramática e o snapshot do dia 1. Devolve `{raciocinio, caderno}` — sem
plano.

**Chamadas 1..121 — dia.** System prompt **estático** com regras + gramática (prompt caching
obrigatório: são 121 chamadas por run). User prompt com snapshot + relatório de ontem +
caderno.

Falha de API ou JSON inválido: **3 tentativas**. Esgotadas, o dia vira "o agente dormiu sem
fazer nada" — plano vazio, caderno preservado, relatório marcado com `dia_perdido: true`.
Dias perdidos entram na análise: uma run com 8 dias perdidos não é comparável a uma com 0.

---

## 11. Artefatos

```
experimentos/
  <modelo>/<modo>/seed_<n>/
    estrategia.json
    dias/dia_001.json ... dia_121.json      snapshot + resposta + relatório
    caderno/dia_001.md ... dia_121.md
    run.csv                                 o CSV nativo do jogo
    metricas.csv                            uma linha por dia
    video.mp4                               opcional
  resumo.csv                                uma linha por run
```

`metricas.csv`, uma linha por dia:

| Coluna | O que mede |
| --- | --- |
| `moedas_fim` | curva de lucro |
| `erros_validacao` | **aprendizado de regras** |
| `correcao_usada` | idem |
| `acoes_truncadas` | **aprendizado de orçamento** |
| `retorno_forcado` | idem |
| `estamina_desperdicada` | eficiência |
| `unidades_vendidas_abaixo_do_base` | aprendeu saturação? |
| `culturas_distintas_vendidas` | aprendeu o rodízio? |
| `plantas_apodrecidas` | aprendeu validade? |
| `linhas_caderno_rejeitadas` | qualidade da memória |
| `caderno_churn` | linhas trocadas vs. dia anterior |
| `tokens_in`, `tokens_out`, `custo_usd` | conta |