# llm_agent — um LLM jogando a fazenda

Um modelo de linguagem joga uma partida inteira via OpenRouter: uma chamada de estratégia antes do
dia 1 e uma chamada por dia, que devolve o plano do dia numa linguagem de comandos. O interpretador
executa o plano no jogo, protege a estamina e devolve um relatório no dia seguinte.

```bash
venv/Scripts/python.exe run_llm.py --seed 42 --days 30 --headless
```

A chave vai no `.env` da raiz: `OPEN_ROUTER_API_KEY=sua-chave-aqui`.

| Módulo | O que tem |
| --- | --- |
| `settings.py` | **a configuração do agente**: modelo, timeout, dias, velocidade, pastas |
| `runner.py` | a run: estratégia, laço dos dias, logs e resumo final |
| `executor.py` | o interpretador do plano e a rede de segurança de estamina |
| `grammar.py` | a linguagem de comandos (`IR`, `PLANTAR`, `COLHER`, `VENDER`...) |
| `facts.py` | os números calculados que entram no prompt |
| `feedback.py` | o relatório de ontem e o diário |
| `responses.py` | validação da resposta e do bloco de conhecimento |
| `templates.py` | leitura dos prompts `.md` de [prompts/](../prompts) |
| `openrouter.py` | cliente HTTP, timeout e novas tentativas |
| `parsing.py` | extrai o JSON da resposta |
| `run_logs.py` | a pasta da run e todos os CSVs |
| `transactions.py` | as compras e vendas que o jogador de fato fez |

Cada run vira uma pasta em `runs_llm/` com prompts, respostas, `dias.csv`, `comandos.csv`,
`precos.csv`, `transacoes.csv`, vídeo e um `LEIAME.md` com o resumo.

| Documento | Assunto |
| --- | --- |
| [docs/AGENTE_LLM.md](../docs/AGENTE_LLM.md) | como o agente funciona, flags e pastas |
| [docs/GRAMATICA.md](../docs/GRAMATICA.md) | os comandos do plano e os códigos de retorno |
| [docs/CONFIGURACOES.md](../docs/CONFIGURACOES.md) | todos os parâmetros |
