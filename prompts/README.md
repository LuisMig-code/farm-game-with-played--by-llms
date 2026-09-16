# Prompts do agente LLM

Os dois prompts que o agente manda ao modelo, em Markdown. São **lidos a cada run**: editar um
arquivo muda a próxima partida, sem tocar em Python.

| Arquivo | Quando é usado | O modelo devolve |
| --- | --- | --- |
| `prompt_inicial.md` | uma vez, antes do dia 1 | `analise` (prazo, cultivos, canteiros, abertura, uso das moedas, fechamento), `regras_de_bolso`, `estrategia` em bullets |
| `prompt_gaming.md` | todo dia | `leitura_do_dia`, `conhecimento`, `plano` |

## Formato

- Duas seções obrigatórias: `# SYSTEM` e `# USER`.
- `{PLACEHOLDERS}` em maiúsculas são trocados por valores calculados do jogo.
- Um placeholder que o código não conhece faz a run **falhar antes de abrir o jogo**.
- Chaves de JSON (`{"plano": ...}`) não são placeholders e passam intactas.
- Cada run guarda a cópia dos templates usados em `runs_llm/<run>/prompts/`.

**Não renomeie as chaves do JSON de resposta** (`estrategia`, `plano` etc.): o código confere que elas
existem e rejeita a resposta se faltarem.

## Placeholders

### `prompt_inicial.md`

| Placeholder | Conteúdo |
| --- | --- |
| `{DIAS}` | dias da partida |
| `{MOEDAS_INICIAIS}`, `{SEMENTES_INICIAIS}`, `{FERTILIZANTES_INICIAIS}` | o inventário inicial |
| `{STAMINA_MAX}` | estamina por dia |
| `{TABELA_CUSTOS}` | custo de cada ação |
| `{TABELA_DISTANCIAS}` | passos entre cama, loja e as hortas |
| `{TABELA_CULTIVOS}` | prazo, validade, preços e lucro de cada cultivo |
| `{FERTILIZANTE}` | como o fertilizante funciona e suas restrições |
| `{ESTACOES}` | as estações que a partida atravessa, com os dias de cada uma |
| `{REGRAS_LOJA}` | preços base, promoção, estoque, caixa, limites |
| `{SATURACAO}` | o mercado dinâmico: gatilhos, piso, recuperação e dois exemplos |
| `{BASE_DE_CONHECIMENTO}` | o `--knowledge`, ou vazio |
| `{ESTRATEGIA_MAX}` | tamanho máximo da estratégia |

### `prompt_gaming.md`

| Placeholder | Conteúdo |
| --- | --- |
| `{DIA}`, `{DIAS}`, `{DIAS_RESTANTES}` | onde a partida está |
| `{ESTRATEGIA}` | a estratégia da chamada inicial |
| `{ESTACAO}`, `{PROXIMA_ESTACAO}` | estação atual e a próxima, com dias e restrições |
| `{STAMINA}`, `{MOEDAS}` | estamina e moedas |
| `{COLHEITA}`, `{SEMENTES}`, `{FERTILIZANTES}` | o inventário |
| `{LIVRES_ESQ}`, `{PLANTIOS_ESQ}`, `{LIVRES_DIR}`, `{PLANTIOS_DIR}` | células livres e plantações de cada horta |
| `{LOJA}` | caixa, preços, promoções, estoque e saturação de hoje, com a regra curta da saturação |
| `{CUSTOS}` | distâncias e custo de cada ação |
| `{PRAZO_POR_CULTIVO}`, `{CULTIVOS_INVIAVEIS}` | até que dia ainda dá para plantar cada cultivo |
| `{TABELA_CULTIVOS}` | a tabela de cultivos com os preços de hoje |
| `{FERTILIZANTE}` | regras do fertilizante e os números de hoje |
| `{FEEDBACK_ONTEM}` | o relatório do dia anterior, comando a comando |
| `{DIARIO}`, `{DIARIO_DIAS}` | o resumo dos últimos dias |
| `{CONHECIMENTO}`, `{CONHECIMENTO_MAX}` | o bloco de conhecimento que o modelo escreveu |

Os placeholders de um arquivo não existem no outro: cada chamada tem o seu conjunto.

Alguns números estão escritos direto no texto e **não** se ajustam sozinhos se as regras mudarem:
"30 dias" por estação, "49 células" por horta e a lista de cultivos da gramática.

Mais em [docs/AGENTE_LLM.md](../docs/AGENTE_LLM.md) e [docs/GRAMATICA.md](../docs/GRAMATICA.md).
