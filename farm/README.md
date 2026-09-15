# farm — o jogo

O jogo de fazenda em si, em pygame-ce. Abre com `main.py` na raiz:

```bash
venv/Scripts/python.exe main.py --seed 42
```

| Módulo | O que tem |
| --- | --- |
| `settings.py` | **todas as constantes do jogo**: estamina, loja, estações, janela, cores |
| `crops.py` | catálogo dos cultivos, fertilizante e limites do inventário |
| `seasons.py` | as quatro estações e o que cada uma muda |
| `game.py` | loop principal, máquina de estados, menus e ações |
| `player.py` | movimento célula a célula, animações e estamina |
| `field.py` | o que está plantado, crescimento, validade e apodrecimento |
| `market.py` | preços, promoção, estoque, caixa e saturação |
| `inventory.py` | inventário e estatísticas da partida |
| `menu.py`, `hud.py` | menus, painel, quadro de preços e telas |
| `grid.py`, `zones.py`, `view.py` | grid, zonas andáveis e a conversão mundo → tela |
| `rng.py` | a semente e os sorteios por dia |
| `run_log.py`, `spoil_record.py` | os logs de cada partida em `logs/` |
| `assets.py` | carregamento das imagens de `Assets/` |

Os ajustes mais comuns ficam em `settings.py`, `crops.py` e `seasons.py` — ver
[docs/CONFIGURACOES.md](../docs/CONFIGURACOES.md). As regras estão em
[docs/COMO_JOGAR.md](../docs/COMO_JOGAR.md).

As camadas `scripting/` e `llm_agent/` usam o jogo sem modificá-lo.
