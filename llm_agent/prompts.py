"""Os textos enviados ao modelo.

O system prompt e o mesmo em todas as chamadas da run (regras + como o executor
funciona), para aproveitar cache de prompt quando o provedor tiver. O que muda de
chamada para chamada vai no user prompt, que tambem diz o formato de resposta.
"""

import json

from farm import settings as game_settings
from llm_agent import settings
from llm_agent.grammar import ZONE_CELLS, reference
from llm_agent.notebook import PREFIXES

STRATEGY_KEYS = ("estrategia", "caderno")
DAY_KEYS = ("raciocinio", "plano", "caderno")


def system_prompt(horizon: int) -> str:
    regras = "\n\n".join(
        f"===== {nome} =====\n{(settings.DOCS_DIR / nome).read_text(encoding='utf-8').strip()}"
        for nome in settings.RULE_DOCS)
    entradas = ", ".join(f"{z} {c}" for z, c in ZONE_CELLS.items())

    return f"""Voce e o agente que joga um jogo de fazenda 2D, um dia de cada vez.

# Objetivo
- A run dura {horizon} dias. O score e a quantidade de MOEDAS ao fim do dia {horizon}.
  Inventario, sementes e plantas no chao NAO contam no score.
- Voce nao controla teclas: a cada dia voce escreve um PLANO numa gramatica propria, e um
  executor o joga de verdade. O jogo real aplica todas as regras abaixo.

# Regras do jogo
As regras completas estao nos documentos a seguir. Ignore o que falar de teclado, janela ou
arquivos de log: quem aperta as teclas e o executor.

{regras}

# Como o seu plano e executado
{reference()}

Execucao:
- O dia comeca sempre na cama, com a estamina cheia ({game_settings.STAMINA_MAX}).
- As acoes rodam NA ORDEM escrita. O executor nao reordena nada: a sequencia de IR e a rota,
  e cada passo de caminhada custa {game_settings.STAMINA_WALK} de estamina.
- Celulas de referencia de cada zona: {entradas}. "IR canteiro_..." leva a celula de entrada.
- Dentro do canteiro o executor vai sempre a celula-alvo mais proxima (empate: menor coluna,
  depois menor linha), age, e repete. Andar entre essas celulas tambem custa estamina.
- Custos por unidade: plantar {game_settings.STAMINA_PLANT}, colher {game_settings.STAMINA_HARVEST},
  fertilizar {game_settings.STAMINA_FERTILIZE}, limpar {game_settings.STAMINA_CLEAR}. Comprar e vender
  nao custam estamina.
- Dormir e implicito: quando o plano termina, o jogador volta para a cama e dorme. Nao existe
  verbo DORMIR.

REDE DE SEGURANCA (impede a derrota):
- Antes de cada trecho de caminhada e de cada acao de campo, o executor confere:
  estamina_atual >= passos_ate_o_alvo + custo_da_acao + passos_do_alvo_ate_a_cama + {settings.STAMINA_RESERVE}
  (o jogo declara derrota com estamina 0 mesmo em cima da cama; por isso a reserva).
- Se a conta nao fecha, a acao para ali (TRUNCADO / SEM_ESTAMINA), todas as seguintes viram
  NAO_EXECUTADO / SEM_ESTAMINA, e o jogador volta para a cama e dorme.
- Voce fica sabendo disso no relatorio do dia seguinte, com a estamina que faltava. Planeje
  o orcamento de estamina do dia incluindo a volta para casa.

Resultado de cada acao, no relatorio:
- EXECUTADO: rodou inteira.  TRUNCADO: rodou em parte (com "efetivo", "pedido" e "motivo").
- NAO_EXECUTADO: nao rodou nada (com "motivo").
- Motivos: SEM_ESTAMINA, SEM_ESTOQUE, SEM_CAIXA_LOJA, SEM_MOEDAS, LIMITE_INVENTARIO,
  SEM_CELULA_LIVRE, SEM_ALVO, SEM_RECURSO, LIMITE_FERTILIZANTE_DIARIO, ZONA_ERRADA, ESTACAO,
  RECUSADO_PELO_JOGO.

Validacao antes de executar: erros de gramatica, de zona (ex.: VENDER fora da loja), de
estacao (plantar ou fertilizar no inverno), de limite de inventario, de recurso (pedir mais
sementes do que tera) e de limite diario voltam para voce corrigir UMA vez. Se o plano
corrigido ainda tiver erro, so o trecho antes do primeiro erro e executado.

# Caderno
O caderno e a sua memoria entre os dias: ate {settings.NOTEBOOK_MAX_LINES} linhas, reescrito
por inteiro a cada resposta (o que voce nao repetir, some). Cada linha comeca com um destes
prefixos: {' '.join(PREFIXES)} e precisa conter um numero ou uma referencia concreta
(cultura, zona, item). Linhas fora disso sao descartadas.
Exemplos:
  [REGRA] Vender 7+ da mesma cultura no mesmo dia derruba 1 moeda por unidade. (dia 14)
  [NUMERO] Cama ate canteiro_esquerdo: 17 passos; ida e volta 34. (dia 3)
  [CALENDARIO] Ultimo dia para plantar melancia antes do inverno: dia 81.
  [ERRO] Dia 22: pedi 4 fertilizantes, o limite e 3 por dia.

Responda sempre com UM objeto JSON valido, sem texto fora dele."""


def strategy_prompt(snapshot: dict, horizon: int, knowledge: str | None) -> str:
    base = ""
    if knowledge:
        base = f"""
## Base de conhecimento previa
Anotacoes de runs anteriores. Use o que for util; confira contra as regras.

{knowledge.strip()}
"""
    return f"""# Antes do dia 1: estrategia da run

Voce vai jogar {horizon} dias. Leia as regras e o estado inicial e escreva uma estrategia geral
para a run inteira: o que plantar em cada estacao, como usar a estamina, quando vender, como
se preparar para o inverno e como terminar o dia {horizon} com o maximo de moedas.
Essa estrategia sera mostrada a voce todos os dias.
{base}
## Estado do dia 1
```json
{json.dumps(snapshot, ensure_ascii=False, indent=2)}
```

## Formato da resposta
Um unico objeto JSON:
{{
  "estrategia": "texto com a estrategia geral da run",
  "caderno": ["[NUMERO] Cama ate canteiro_esquerdo: 17 passos.",
              "[CALENDARIO] Inverno comeca no dia 91: nada pode ficar no chao na virada."]
}}
As linhas do caderno acima sao exemplos de formato: escreva as suas, com fatos reais."""


def day_prompt(*, snapshot: dict, horizon: int, strategy: str, notebook: list[str],
               report: dict | None, memory: bool) -> str:
    dia = snapshot["dia"]
    if not memory:
        caderno = "(modo sem memoria: o caderno chega sempre vazio, mas escreva-o mesmo assim)"
    elif notebook:
        caderno = "\n".join(f"- {linha}" for linha in notebook)
    else:
        caderno = "(vazio)"

    if report is None:
        ontem = "Hoje e o primeiro dia: nao ha relatorio anterior."
    else:
        ontem = f"```json\n{json.dumps(report, ensure_ascii=False, indent=2)}\n```"

    return f"""# Dia {dia} de {horizon} (depois de hoje faltam {horizon - dia} dia(s))

## Estrategia geral da run
{strategy.strip() if strategy else "(sem estrategia: a chamada de estrategia nao retornou)"}

## Caderno
{caderno}

## O que aconteceu ontem
{ontem}

## Estado de hoje (inicio do dia, na cama)
```json
{json.dumps(snapshot, ensure_ascii=False, indent=2)}
```

## Formato da resposta
Um unico objeto JSON:
{{
  "raciocinio": "texto curto, ate {settings.REASONING_MAX_CHARS} caracteres",
  "plano": ["IR loja", "VENDER trigo TUDO", "IR canteiro_esquerdo", "COLHER TUDO"],
  "caderno": ["[REGRA] Cenoura fertilizada fica pronta em 1 dia.",
              "[NUMERO] Plantar custa 2 de estamina por semente, fora a caminhada."]
}}
O plano e o caderno acima sao exemplos de formato: escreva os seus, com base no estado de hoje."""


def correction_prompt(errors: list[dict]) -> str:
    linhas = "\n".join(f"- linha {e['indice'] + 1} \"{e['linha']}\": {e['codigo']} -- {e['mensagem']}"
                       for e in errors)
    return f"""O plano tem erros de validacao:
{linhas}

Devolva o objeto JSON completo corrigido, no mesmo formato (raciocinio, plano, caderno).
Esta e a unica chance de correcao: se ainda houver erro, so o trecho antes do primeiro erro
sera executado."""
