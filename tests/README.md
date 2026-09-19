# tests — as suítes sem rede

Duas suítes, sem rede e sem crédito:

- **`check_llm.py`**, a do agente LLM. O modelo é trocado por um cliente falso, que responde o que
  cada teste roteiriza. As partidas são de verdade — o jogo roda, grava vídeo e escreve os CSVs —,
  então a suíte pega regressão no agente, no interpretador, nos logs e no vídeo.
- **`check_scenarios.py`**, a do [simulador de cenários](../docs/CENARIOS.md). Compara o simulador
  com uma partida de verdade, dia a dia, e confere:
  - os CSVs;
  - o que é pulado e o que é refeito;
  - o paralelo;
  - o Ctrl+C.

```bash
venv/Scripts/python.exe tests/check_llm.py            # ~8 min, numa pasta temporária nova
venv/Scripts/python.exe tests/check_llm.py C:/tmp/t   # ou numa pasta nova ou vazia
venv/Scripts/python.exe tests/check_scenarios.py      # ~20 s, também numa pasta temporária nova
venv/Scripts/python.exe tests/check_links.py          # links e âncoras dos .md
```

As suítes nunca apagam nada: uma pasta passada à mão precisa estar vazia. Elas também não tocam no
`logs/`, no `runs_llm/` e no `cenarios/` do projeto. O bloco 16 do `check_llm.py` e o bloco 6 do
`check_scenarios.py` conferem isso.

| Arquivo | O que é |
| --- | --- |
| `check_llm.py` | a suíte do agente: 20 blocos em sequência, cada um imprime `N ok: ...`, e o fim é `TUDO OK` |
| `fake_llm.py` | o cliente falso do OpenRouter (`FakeClient`) e as respostas padrão de estratégia e de dia |
| `run_mata_filho.py` | uma run que trava na chamada do dia 4; o bloco 19 a para à força e confere o vídeo |
| `check_scenarios.py` | a suíte do simulador de cenários: 7 blocos, no mesmo formato |
| `run_interrompe.py` | um `simulate_range` que leva um Ctrl+C depois do primeiro lote, com o pool aberto (bloco 7) |
| `check_links.py` | confere links relativos e âncoras de todos os `.md`; sai com código 1 se achar algum quebrado |

## Os blocos do `check_llm.py`

| Bloco | O que cobre |
| --- | --- |
| 1 | gramática: formas aceitas e recusadas, equivalências do quantificador |
| 2 | templates `.md`: `# SYSTEM`/`# USER`, placeholders, placeholder desconhecido |
| 3 | fatos calculados: prazo por cultivo, canteiros, tabela com o preço do dia |
| 4 | códigos do interpretador: OK, PARCIAL, erros de gramática, contexto e recurso |
| 5 | rede de segurança da stamina |
| 6 | feedback do dia anterior |
| 7 | diário dos últimos dias e bloco de conhecimento |
| 8 | estratégia em bullets e teto de caracteres |
| 9 | timeout, 504, JSON inválido e 429 |
| 10 | corpo da requisição e `--reasoning-effort` |
| 11 | arquivos da pasta da run e tempos batendo |
| 12 | determinismo: mesma semente e mesmo roteiro, mesmo resultado |
| 13 | velocidade das ações e loja em lote |
| 14 | próxima estação no prompt |
| 15 | fertilizante no prompt |
| 16 | logs do jogo publicados em `logs/`, com prefixo por modelo |
| 17 | `precos.csv` e `transacoes.csv` |
| 18 | saturação no prompt, com os exemplos conferidos contra o `Market` |
| 19 | vídeo de uma run parada no meio (só no Windows: usa `taskkill`) |
| 20 | erro fatal da API para a run; a chamada inicial insiste pela estratégia |

Os blocos dependem do que os anteriores importaram, então a suíte roda inteira. Um bloco novo entra
no fim, antes do `print("\nTUDO OK")`.

## Os blocos do `check_scenarios.py`

| Bloco | O que cobre |
| --- | --- |
| 1 | o simulador contra uma partida de verdade: estoque, preço e promoção de cada item, dia a dia (semente 42 nos 121 dias, 7 e 2026 em 10) |
| 2 | o CSV do dia: cabeçalho, dias, estação, estoque na faixa, promoção só com estoque, compra = preço cheio − desconto |
| 3 | o `resumo.csv` bate com a recontagem do CSV do dia |
| 4 | pula o que já está no log; refaz com CSV apagado, `regras` diferentes, outros dias ou `force` |
| 5 | `regras`: iguais com CRLF ou LF; mudam com um número da loja ou com o código do sorteio |
| 6 | a linha de comando: os dois scripts, 4 processos iguais a 1 byte a byte, argumento inválido, `cenarios/` intocado |
| 7 | Ctrl+C sem e com o pool: grava o que terminou, e a próxima execução completa o resto |

O pool de processos nunca abre dentro do `check_scenarios.py`: no Windows, cada processo novo
reimportaria a suíte e a rodaria de novo. Por isso o paralelo é testado por subprocesso.
