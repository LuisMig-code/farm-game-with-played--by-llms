# Gramática do plano diário

O modelo não aperta teclas: a cada dia ele devolve um **plano**, uma lista de linhas nesta
gramática, e o executor joga o plano no jogo de verdade. Implementação em
[`llm_agent/grammar.py`](../llm_agent/grammar.py); o texto que vai no prompt é gerado das mesmas
constantes, então os dois nunca discordam.

## Resposta do modelo

```json
{
  "raciocinio": "texto curto, até 800 caracteres",
  "plano": ["IR loja", "VENDER trigo TUDO", "IR canteiro_esquerdo", "COLHER TUDO"],
  "caderno": ["[REGRA] ...", "[NUMERO] ..."]
}
```

A chamada de estratégia, antes do dia 1, devolve `{"estrategia": "...", "caderno": [...]}`.

O modelo configurado não aceita JSON forçado, então o parser procura o objeto no texto: puro,
dentro de uma cerca ` ```json `, ou cercado de texto — e, se a resposta vier vazia, também no
raciocínio.

## Vocabulário

| Categoria | Valores |
| --- | --- |
| Verbos | `IR` `COLHER` `PLANTAR` `FERTILIZAR` `LIMPAR` `COMPRAR` `VENDER` |
| Zonas | `cama` `loja` `canteiro_esquerdo` `canteiro_direito` |
| Cultivos | `cenoura` `batata` `beterraba` `trigo` `melancia` |
| Itens de compra | `semente_cenoura` `semente_batata` `semente_beterraba` `semente_trigo` `semente_melancia` `fertilizante` |
| Quantificadores | `TUDO` · `LIMITE <n>` · `<n>` |

Maiúsculas e minúsculas são aceitas: o que se mede é se o modelo entende as regras, não a caixa
das letras. Qualquer outro token é `ERRO_GRAMATICA`.

## Assinaturas

| Ação | Onde | O que faz |
| --- | --- | --- |
| `IR <zona>` | — | anda até a zona; em canteiro, até a célula de entrada |
| `COLHER <cultivo\|TUDO> [LIMITE n]` | canteiro | colhe plantas prontas e não estragadas |
| `PLANTAR <cultivo> <TUDO\|LIMITE n\|n>` | canteiro | planta em células vazias |
| `FERTILIZAR <cultivo\|TUDO> [LIMITE n]` | canteiro | plantas crescendo, ainda não fertilizadas |
| `LIMPAR [LIMITE n]` | canteiro | arranca plantas estragadas |
| `COMPRAR <item> <n>` | loja | compra n unidades |
| `VENDER <cultivo> <TUDO\|n>` | loja | vende unidades da colheita |

**Quantificadores.** `TUDO` é tudo o que for possível agora; `LIMITE n` é `TUDO` com teto n; `n` é
exatamente n — e, por ser exato, a validação confere se o recurso existe.

`PLANTAR ... TUDO` já nasce limitado pelo menor entre células vazias e sementes no inventário.
`VENDER ... TUDO` vende o inventário inteiro enquanto a loja tiver caixa.

## Zonas e distâncias

| Zona | Célula |
| --- | --- |
| `cama` | (17,12) |
| `loja` | (21,12) |
| `canteiro_esquerdo` | entrada (6,8); canteiro de colunas 3–9 e linhas 2–8 |
| `canteiro_direito` | entrada (33,8); canteiro de colunas 30–36 e linhas 2–8 |

| De ↔ Para | Passos |
| --- | --- |
| cama ↔ loja | 6 |
| cama ↔ canteiro_esquerdo | 17 |
| cama ↔ canteiro_direito | 22 |
| loja ↔ canteiro_esquerdo | 21 |
| loja ↔ canteiro_direito | 18 |
| canteiro_esquerdo ↔ canteiro_direito | 37 |

As distâncias saem do BFS sobre as células andáveis e vão no snapshot de todo dia.

## Execução

- **Ordem literal.** O executor não reordena nada: a sequência de `IR` é a rota.
- **Guloso dentro do canteiro.** Vai à célula-alvo mais próxima (empate: menor coluna, depois menor
  linha), age e repete. Só células-alvo entram na rota, e andar entre elas custa estamina.
- **Dormir é implícito.** Terminado o plano, o jogador volta para a cama e dorme. Não existe verbo
  `DORMIR`.
- Tudo passa pelos menus do jogo, pela camada `scripting/` — o executor não consegue trapacear.

### Rede de segurança

Antes de cada trecho de caminhada e de cada ação de campo:

```
estamina >= passos_até_o_alvo + custo_da_ação + passos_do_alvo_até_a_cama + 1
```

O `+ 1` não é folga: o jogo declara derrota com estamina 0 **mesmo em cima da cama**, antes de dar
para dormir. Chegar em casa com zero é game over.

Se a conta não fecha, a ação para ali com `TRUNCADO`/`NAO_EXECUTADO` e motivo `SEM_ESTAMINA` —
com a estamina que era necessária e a que havia —, todas as seguintes viram `NAO_EXECUTADO` /
`SEM_ESTAMINA`, e o jogador volta e dorme. O relatório registra `retorno_forcado`, onde aconteceu e
quais ações ficaram por fazer; o modelo lê isso no dia seguinte.

`IR` confere a ida inteira antes de sair, para não andar meio caminho só para voltar.

## Resultado de cada ação

| Status | Quando |
| --- | --- |
| `EXECUTADO` | rodou inteira |
| `TRUNCADO` | rodou em parte — com `pedido`, `efetivo` e `motivo` |
| `NAO_EXECUTADO` | não rodou nada — com `motivo` |

| Motivo | Quando |
| --- | --- |
| `SEM_ESTAMINA` | a rede de segurança barrou |
| `SEM_ESTOQUE` | a loja não tem mais o item hoje |
| `SEM_CAIXA_LOJA` | a loja não tem caixa para pagar a próxima unidade |
| `SEM_MOEDAS` | faltou moeda para comprar |
| `LIMITE_INVENTARIO` | o jogador já carrega o teto do item |
| `SEM_CELULA_LIVRE` | não há célula vazia para plantar |
| `SEM_ALVO` | nenhuma planta atende ao filtro |
| `SEM_RECURSO` | acabou a semente, o fertilizante ou o vegetal a vender |
| `LIMITE_FERTILIZANTE_DIARIO` | já foram usados os 3 fertilizantes do dia |
| `ZONA_ERRADA` | ação de campo fora do canteiro, ou de loja fora da loja |
| `ESTACAO` | plantar ou fertilizar no inverno |
| `RECUSADO_PELO_JOGO` | o menu do jogo recusou por um motivo não previsto acima |

`SEM_MOEDAS`, `SEM_RECURSO`, `ZONA_ERRADA`, `ESTACAO` e `RECUSADO_PELO_JOGO` não estavam na
[ARQUITETURA-IA.md](ARQUITETURA-IA.md): apareceram na implementação.

## Validação

Antes de executar, o plano inteiro é simulado em sequência — uma compra no começo conta para o
plantio adiante —, sem estamina e sem moedas, que só a execução conhece.

| Código | Exemplo |
| --- | --- |
| `ERRO_GRAMATICA` | token desconhecido, aridade errada, plano que não é lista |
| `ERRO_ZONA` | `VENDER` sem ter ido à loja |
| `ERRO_ESTACAO` | `PLANTAR` ou `FERTILIZAR` no inverno |
| `ERRO_LIMITE_INVENTARIO` | `COMPRAR semente_trigo 20` com 1 no inventário (teto 20) |
| `ERRO_RECURSO` | `PLANTAR trigo 5` com 2 sementes; `VENDER trigo 3` com 1 |
| `ERRO_LIMITE_DIARIO` | `FERTILIZAR` com os 3 do dia já usados |

Com erro, a lista volta ao modelo para **uma** correção. Se o plano corrigido ainda tiver erro — ou
a correção não voltar —, só as ações antes do primeiro erro são executadas.
