# examples — scripts prontos

Dois scripts que jogam sozinhos usando a camada [scripting](../scripting). Os dois gravam vídeo por
padrão, então precisam do `requirements-agent.txt` (ou rode com `--no-video`).

| Script | Parâmetros | O que faz |
| --- | --- | --- |
| `scripted_run.py` | `--seed N`, `--no-video` | roteiro fixo: planta, espera crescer, colhe e vende; grava `logs/scripted_run.mp4` |
| `random_agent.py` | `--seed N`, `--days N` (padrão 15), `--no-video` | escolhe ações ao acaso até o dia pedido ou a estamina acabar; grava `logs/random_agent.mp4` |

```bash
venv/Scripts/python.exe examples/scripted_run.py --seed 7
venv/Scripts/python.exe examples/random_agent.py --seed 7 --days 20
```

O `random_agent.py` é o esqueleto de um agente: lê a observação, escolhe uma ação e trata a recusa.
Trocar a função `decide()` por outra política é o ponto de partida para um agente próprio.

Ver [docs/SCRIPTING.md](../docs/SCRIPTING.md).
