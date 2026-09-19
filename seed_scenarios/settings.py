"""Configuracao do simulador de cenarios. Sem logica, apenas valores.

Mora aqui, e nao em `farm/settings.py`, para o jogo continuar intocado. Tudo que
tem flag em `simulate_seed.py` e `simulate_range.py` pode ser sobreposto por ela.
"""

from pathlib import Path

from llm_agent.settings import DAYS as AGENT_DAYS

ROOT_DIR = Path(__file__).resolve().parent.parent

# Pasta de log propria, fora do git: resumo.csv, execucoes.csv e sementes/ (--out).
OUT_DIR = ROOT_DIR / "cenarios"

# O mesmo horizonte das runs do agente: mudou la, muda aqui (--days).
DAYS = AGENT_DAYS

# Processos do simulate_range.py. None = um por nucleo da maquina (--workers).
WORKERS: int | None = None
# Sementes por tarefa mandada a um processo. Uma semente custa poucos
# milissegundos: lote pequeno gasta mais conversando com o processo do que simulando.
CHUNK_SEEDS = 50
# Teto de sementes por execucao do simulate_range.py. Cada semente grava ~12 KB,
# e um --to digitado errado nao pode encher o disco.
MAX_SEEDS = 100_000
