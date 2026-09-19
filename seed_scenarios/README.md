# seed_scenarios — o cenário da loja de cada semente

Simula, sem abrir o jogo, o estoque e as promoções de cada dia de uma semente, usando o próprio
`Market` do jogo. Serve para escolher sementes de teste: a com mais promoções, a com menos, uma
perto da média.

```bash
venv/Scripts/python.exe simulate_seed.py --seed 42              # uma semente, dia a dia
venv/Scripts/python.exe simulate_range.py --from 1 --to 1000    # um intervalo, em paralelo
```

| Módulo | O que tem |
| --- | --- |
| `settings.py` | **a configuração**: pasta de log, dias, processos, tamanho do lote, teto de sementes |
| `simulator.py` | a simulação (`simulate`), as métricas (`summarize`) e a impressão digital das regras |
| `store.py` | a pasta `cenarios/`: o CSV de cada semente, o `resumo.csv` e o `execucoes.csv` |
| `batch.py` | várias sementes em paralelo, pulando as que já estão no log |

Tudo vai para `cenarios/`, que fica fora do git:
- `sementes/semente_<N>.csv`, com um dia por linha;
- `resumo.csv`, com uma linha por semente;
- `execucoes.csv`, com uma linha por execução.

| Documento | Assunto |
| --- | --- |
| [docs/CENARIOS.md](../docs/CENARIOS.md) | os dois scripts, as colunas e quando uma semente é refeita |
| [docs/SEMENTE.md](../docs/SEMENTE.md) | por que a semente fixa o cenário |
