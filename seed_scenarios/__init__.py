"""O cenario da loja de cada semente, simulado sem abrir o jogo.

    from seed_scenarios.simulator import simulate, summarize
    cenario = simulate(42, 121)             # estoque e promocao de cada dia
    summarize(cenario)["promocoes"]         # itens em promocao somados nos 121 dias

Ou pela linha de comando: `simulate_seed.py --seed 42` para uma semente e
`simulate_range.py --from 1 --to 1000` para um intervalo, em paralelo. Ver
docs/CENARIOS.md.
"""
