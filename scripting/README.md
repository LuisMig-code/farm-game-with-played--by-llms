# scripting — jogar por código

Uma biblioteca para jogar o jogo por script, pelos mesmos menus e regras de quem joga no teclado, com
a partida gravada em MP4. É a base do agente LLM.

```python
from scripting import Session, HOUSE, SHOP

with Session(seed=42, record="logs/partida.mp4", realtime=False, speed=2) as s:
    s.walk_to((6, 8)).plant("batata")
    s.walk_to(HOUSE).sleep_until(day=4)
    s.walk_to((6, 8)).harvest()
    s.walk_to(SHOP).sell("batata")
    print(s.observe().as_text())
```

| Parâmetro de `Session` | Padrão | O que faz |
| --- | --- | --- |
| `seed` | a do jogo | semente do cenário |
| `record` | `None` | caminho do MP4; sem ele nada é gravado (precisa do `requirements-agent.txt`) |
| `fps` | 60 | quadros por segundo da simulação |
| `realtime` | `True` | `False` roda acelerado, sem esperar o relógio |
| `speed` | 1.0 | multiplica a velocidade das ações e do vídeo; teto em `Session.max_speed()` |

| Módulo | O que tem |
| --- | --- |
| `session.py` | a `Session`: andar, plantar, colher, fertilizar, dormir, negociar |
| `observation.py` | o estado da partida em dicionário ou em texto para prompt |
| `recorder.py` | a gravação em MP4 |
| `route.py` | menor caminho entre células |
| `errors.py` | `Blocked`, `NoRoute`, `GameOver`, `Aborted`, `RecorderUnavailable` |

Exemplos prontos em [examples/](../examples). Documentação completa em
[docs/SCRIPTING.md](../docs/SCRIPTING.md).
