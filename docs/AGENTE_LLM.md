# LLMs jogando a fazenda

Um modelo de linguagem joga uma run inteira pelo OpenRouter. Antes do dia 1 ele lê as regras e
escreve uma estratégia geral; a cada dia recebe o estado da fazenda, a estratégia, o caderno que
ele mesmo vem anotando e o relatório do dia anterior, e devolve as ações do dia numa gramática que
o executor joga de verdade — com a tela gravada em vídeo.

O desenho vem da [ARQUITETURA-IA.md](ARQUITETURA-IA.md). A gramática, o executor e a rede de
segurança estão em [GRAMATICA.md](GRAMATICA.md).

## Rodando

```bash
venv/Scripts/python.exe -m pip install -r requirements-agent.txt
venv/Scripts/python.exe run_llm.py --seed 42
```

A chave vem de `OPEN_ROUTER_API_KEY`, no ambiente ou no `.env` da raiz — que está no `.gitignore`.
A chave nunca é gravada: os logs guardam o corpo das mensagens, nunca os cabeçalhos.

| Flag | Padrão | O que faz |
| --- | --- | --- |
| `--seed` | a do jogo | semente do cenário ([SEMENTE.md](SEMENTE.md)) |
| `--days` | 121 | quantos dias jogar |
| `--model` | `nvidia/nemotron-3.5-lightning:free` | id do modelo no OpenRouter |
| `--mode` | `principal` | `sem_memoria` manda o caderno sempre vazio |
| `--knowledge` | — | `.txt` de base de conhecimento, anexado à chamada de estratégia |
| `--timeout` | 360 | segundos de espera por chamada |
| `--attempts` | 3 | tentativas quando a resposta chega mas não serve |
| `--no-video` | — | não grava o MP4 |
| `--realtime` | — | roda a 60 fps de verdade em vez de acelerado |
| `--headless` | — | sem janela; o vídeo é gravado igual. **O mais estável para runs longas** |
| `--allow-sleep` | — | deixa o Windows suspender por inatividade durante a run |
| `--runs-dir` | `runs_llm/` | onde criar a pasta da run |

Todos os padrões moram em [`llm_agent/settings.py`](../llm_agent/settings.py) — separado de
`farm/settings.py` para o jogo continuar intocado.

## O ciclo

```
chamada 0: regras + snapshot do dia 1 (+ base de conhecimento) -> estrategia + caderno
    |
    v
dia D: snapshot + estrategia + caderno + relatorio de ontem -> raciocinio + plano + caderno
         -> validacao -> (1 correcao) -> executor -> volta para a cama -> dorme -> dia D+1
```

O system prompt é o mesmo em todas as chamadas da run: regras, gramática, rede de segurança e o
objetivo — **moedas ao fim do último dia**; inventário não conta. O que muda vai no prompt do
usuário.

**Base de conhecimento.** O `.txt` de `--knowledge` entra só na chamada de estratégia. O que o
modelo aproveitar dele precisa ir para a estratégia ou o caderno, que são o que ele vê nos dias
seguintes. Toda run termina gravando `caderno_final.txt`, que serve de base para a próxima.

## Timeout e falhas

| Situação | O que acontece |
| --- | --- |
| Chamada sem resposta em `--timeout` segundos | **não repete**: o jogador dorme, o dia fica `timeout` e o modelo é avisado no dia seguinte |
| Provedor desiste por tempo (HTTP 504/408) | igual ao timeout: **não repete** |
| JSON inválido, HTTP 429 ou 5xx | tenta de novo, até `--attempts` |
| Tentativas esgotadas | dia perdido (`json_invalido` ou `erro_api`): o jogador dorme sem agir |
| Chamada de estratégia perdida | a run segue sem estratégia, e o prompt diário diz isso |
| Plano com erro de validação | uma chamada de correção; se ainda falhar, executa só o trecho antes do erro |

Enquanto espera o modelo, o jogo fica parado e o gravador pausado, para o vídeo não encher de
quadros parados; a janela continua sendo atendida, para o Windows não a marcar como
"Não respondendo". Fechar a janela interrompe a run.

### A espera que passava do prazo

Nas primeiras runs reais, respostas foram registradas aos 295, 314, 372, 396, 466 e 508 s com prazo
de 240–360 s, e numa run com janela o Windows chegou a fechar o processo (`Application Hang`, dia
13). A causa foi achada pelo `travamentos.log` de uma run `--headless`:

- a thread principal estava parada em `thread.join(0.05)` — um `join` que deveria voltar em 50 ms
  ficou preso até a thread de rede terminar;
- a thread de rede ainda lia a resposta **chunked** do OpenRouter por SSL, ou seja, o modelo de fato
  não tinha respondido — os `timeout` registrados estavam certos, só chegavam tarde.

Com janela, essa trava também deixava a janela sem ser atendida, e daí o "Não respondendo". A espera
não usa mais `join`: a thread de rede sinaliza um `Event` ao terminar e o laço só dorme 50 ms entre as
checagens. A reprodução local (HTTP e HTTPS, com resposta chunked a conta-gotas) não trava nem com o
código antigo, então a condição exata depende da conexão real.

Proteções que ficam:

- O prazo é conferido também na resposta: uma que chegue depois do limite vira `timeout`.
- Se a espera passar do prazo, a pilha de todas as threads vai para `travamentos.log`, na pasta da
  run. O arquivo só existe se isso acontecer.
- `--headless` roda sem janela e grava o vídeo igual. Para runs longas sem ninguém olhando continua
  sendo a opção mais segura: sem janela, não há o que o Windows marcar como "Não respondendo".

### Latência medida do modelo padrão

Com o prompt real (~8,7 mil tokens de entrada: regras + estado do dia), o
`nvidia/nemotron-3.5-lightning:free` levou **de 2 a 7 minutos** por chamada nos testes, e numa delas
parou de raciocinar sem escrever resposta nenhuma (`finish_reason=stop`, conteúdo igual ao
raciocínio) — o que conta como JSON inválido e é tentado de novo.

| Chamada | Tempo | Resultado |
| --- | --- | --- |
| estratégia | > 240 s | timeout |
| dia 1 | 295 s | sem resposta, só raciocínio |
| dia 1, repetida | 121 s | sem resposta, só raciocínio |
| dia 1, `reasoning.effort=low` | 435 s | JSON válido — o parâmetro não encurtou, raciocinou mais |

Esses testes foram feitos com prazo de 240 s; o padrão passou a 360 s (6 min) por causa deles.
O OpenRouter também pode desistir sozinho, devolvendo `504 "A Timeout Occurred"` por volta dos
300 s — aconteceu 5 vezes em 2 dias da primeira run de 30 dias, mas não é regra: a estratégia da run
seguinte chegou com 337 s. O 504 conta como timeout e não é repetido.
Ainda assim, espere alguns dias marcados `timeout`. Para mudar o prazo, use `--timeout` ou
`API_TIMEOUT_SECONDS`.
`chamadas.csv` registra `finish_reason`, provedor e tokens de raciocínio de cada chamada, para
acompanhar isso run a run.

**PC acordado.** Uma run longa passa horas sem ninguém mexer no computador. Por padrão o
`run_llm.py` pede ao Windows que não suspenda por inatividade enquanto o processo existir
(`SetThreadExecutionState`); o pedido acaba sozinho com a run e não muda nenhuma configuração. Tampa
fechada ou "Suspender" manual continuam suspendendo — e aí o processo congela e as chamadas estouram
o prazo.

## Ritmo e vídeo

Por padrão a simulação é **acelerada**: cada quadro simula exatamente 1/60 s sem esperar o relógio,
com a janela aberta. O vídeo continua em **tempo de jogo**, porque o gravador amostra pelo tempo
simulado — dá para assistir normalmente, mas a run termina bem antes. Nada no jogo depende do
relógio de parede, então os resultados são os mesmos do tempo real.

## Pastas

```
runs_llm/
  resumo.csv                                              uma linha por run
  2026-09-12_15-48-59_nemotron-3.5-lightning-free_principal_seed42/
    LEIAME.md            resumo legivel da run
    config.json          tudo que definiu a run, inclusive a base de conhecimento
    agente.log           log de texto completo
    chamadas.csv         uma linha por chamada: inicio, fim, segundos, status, tokens
    acoes.csv            uma linha por acao executada
    metricas.csv         uma linha por dia
    estrategia/
      prompt_system.txt  o system prompt (o mesmo em todas as chamadas)
      prompt_user.txt
      resposta_1.txt     resposta bruta + raciocinio do modelo
      estrategia.json
    dias/dia_001/
      snapshot.json      o estado que o modelo recebeu
      prompt_user.txt
      resposta_1.txt     (resposta_2, _3 se houve nova tentativa)
      correcao_prompt.txt, correcao_resposta_1.txt   (se houve correcao)
      plano.json         plano, raciocinio e erros de validacao
      relatorio.json     o que aconteceu -- e o que o modelo le no dia seguinte
      caderno.md         o caderno ao fim do dia, com as linhas rejeitadas
      chamadas.json      tempo de cada chamada do dia e da execucao do jogo
    jogo/                os logs nativos do jogo (CSV e texto)
    video.mp4
    caderno_final.txt    pronto para --knowledge numa proxima run
```

O nome da pasta ordena cronologicamente e diz modelo, modo e semente. Todo CSV é gravado com flush
por linha: uma run interrompida no meio continua legível.

No Windows, caminhos passam de 260 caracteres com facilidade se `--runs-dir` for muito fundo — o
log nativo do jogo já tem ~50 no nome. A run avisa no log quando estiver perto do limite.

## Métricas

`metricas.csv`, uma linha por dia:

| Coluna | O que mede |
| --- | --- |
| `moedas_fim` | curva de lucro |
| `status_llm`, `dia_perdido` | se o modelo respondeu (`ok`, `timeout`, `json_invalido`, `erro_api`) |
| `erros_validacao`, `correcao_usada` | aprendizado de regras |
| `acoes_truncadas`, `retorno_forcado`, `plano_concluido` | aprendizado de orçamento de estamina |
| `estamina_gasta`, `estamina_desperdicada` | eficiência — desperdiçada é a que sobrou ao deitar |
| `unidades_vendidas_abaixo_do_base` | aprendeu a saturação? |
| `culturas_distintas_vendidas` | aprendeu o rodízio? |
| `plantas_apodrecidas` | aprendeu a validade? |
| `linhas_caderno_rejeitadas`, `caderno_churn` | qualidade da memória |
| `chamadas`, `segundos_llm`, `segundos_maior_chamada` | quanto tempo o dia esperou o modelo |
| `segundos_execucao` | quanto tempo o jogo levou para executar o plano, voltar e dormir |
| `tokens_in`, `tokens_out`, `custo_usd` | a conta |

### Tempo das chamadas

Toda chamada ao modelo registra **início, fim e duração** — inclusive as que deram timeout, que
contam o tempo que a run de fato esperou:

| Onde | O quê |
| --- | --- |
| `chamadas.csv` | uma linha por chamada: `inicio`, `fim`, `segundos` |
| `dias/dia_NNN/chamadas.json`, `estrategia/chamadas.json` | as chamadas daquele dia, o total e a maior |
| `dias/dia_NNN/resposta_N.txt` | início, fim e duração no cabeçalho da resposta bruta |
| `agente.log` | uma linha ao terminar cada chamada, com status e segundos |
| `metricas.csv` | `segundos_llm`, `segundos_maior_chamada` e `segundos_execucao` por dia |
| `LEIAME.md`, `resumo.csv` | total esperando o modelo, média por chamada, maior chamada e duração da run |

## Caderno

Até 20 linhas, reescrito por inteiro a cada resposta. Cada linha começa com `[REGRA]`, `[NUMERO]`,
`[CALENDARIO]` ou `[ERRO]` e precisa ter um número ou uma referência concreta (cultura, zona, item,
verbo). O resto é descartado sem gastar a correção, e contado em `linhas_caderno_rejeitadas`.

No modo `sem_memoria` o caderno chega sempre vazio, mas o modelo continua escrevendo — assim o
formato e o custo das respostas ficam iguais, e a única variável é o que ele recebe.

## Diferenças em relação à ARQUITETURA-IA.md

| Documento | Implementação | Por quê |
| --- | --- | --- |
| Refactor em `farm/core` puro + `farm/render` | o jogo real, dirigido pela `Session` | o jogo não podia ser alterado; a `Session` espera cada animação, então o resultado é o mesmo |
| Rede: `estamina >= custo + distancia` | `estamina >= custo + distancia + 1` | o jogo declara derrota com 0 mesmo em cima da cama |
| 3 tentativas por falha de API | timeout não repete; só erro com resposta repete | pedido: sem resposta no prazo, dorme e segue |
| Base de conhecimento | `--knowledge`, só na estratégia | pedido |
| Motivos de truncamento | mais `SEM_MOEDAS`, `SEM_RECURSO`, `ZONA_ERRADA`, `ESTACAO`, `RECUSADO_PELO_JOGO` | casos que o documento não cobria |
| Orquestrador modelos × seeds × modos | uma run por comando, `resumo.csv` acumulando | o laço entre runs é um `for` no shell |
| `IR` checado passo a passo | checa a ida inteira antes de sair, e passo a passo | não andar meio caminho só para voltar |

## Módulos

| Arquivo | Papel |
| --- | --- |
| `run_llm.py` | linha de comando |
| `llm_agent/runner.py` | a run: estratégia, ciclo dos dias, relatório, métricas |
| `llm_agent/openrouter.py` | cliente HTTP com prazo (stdlib, sem dependência nova) |
| `llm_agent/prompts.py` | system, estratégia, dia e correção |
| `llm_agent/parsing.py` | extrai o JSON da resposta |
| `llm_agent/grammar.py` | vocabulário e parser da DSL |
| `llm_agent/validator.py` | validação estática sequencial |
| `llm_agent/snapshot.py` | estado agregado por canteiro |
| `llm_agent/executor.py` | executa o plano com a rede de segurança |
| `llm_agent/notebook.py` | validação do caderno |
| `llm_agent/run_logs.py` | pasta da run e arquivos |
| `llm_agent/settings.py` | configuração |
