# tests — a suíte do agente LLM

Testes sem rede e sem crédito: o modelo é trocado por um cliente falso, que responde o que cada teste
roteiriza. As partidas são de verdade — o jogo roda, grava vídeo e escreve os CSVs —, então a suíte
pega regressão no agente, no interpretador, nos logs e no vídeo.

```bash
venv/Scripts/python.exe tests/check_llm.py            # ~8 min, numa pasta temporária nova
venv/Scripts/python.exe tests/check_llm.py C:/tmp/t   # ou numa pasta nova ou vazia
venv/Scripts/python.exe tests/check_links.py          # links e âncoras dos .md
```

A suíte nunca apaga nada: uma pasta passada à mão precisa estar vazia. O `logs/` e o `runs_llm/` do
projeto não são tocados — o bloco 16 confere isso.

| Arquivo | O que é |
| --- | --- |
| `check_llm.py` | a suíte: 20 blocos em sequência, cada um imprime `N ok: ...`, e o fim é `TUDO OK` |
| `fake_llm.py` | o cliente falso do OpenRouter (`FakeClient`) e as respostas padrão de estratégia e de dia |
| `run_mata_filho.py` | uma run que trava na chamada do dia 4; o bloco 19 a para à força e confere o vídeo |
| `check_links.py` | confere links relativos e âncoras de todos os `.md`; sai com código 1 se achar algum quebrado |

## Os blocos

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
