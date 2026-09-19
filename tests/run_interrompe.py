"""Um simulate_range que leva um Ctrl+C logo depois do primeiro lote, com o pool aberto.

Usado pelo bloco 7 da suite de cenarios. O Ctrl+C e levantado dentro do
processo principal, pelo callback de progresso, que e por onde um Ctrl+C de
verdade chega: os processos do pool o ignoram.

    python run_interrompe.py <pasta_de_saida> <processos>
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from seed_scenarios.batch import run_batch  # noqa: E402


def para_no_primeiro_lote(feitas, total):
    if feitas:
        raise KeyboardInterrupt


if __name__ == "__main__":
    r = run_batch(range(1, 2001), days=20, workers=int(sys.argv[2]), out_dir=Path(sys.argv[1]),
                  script="run_interrompe", progress=para_no_primeiro_lote)
    print("INTERROMPIDA", r.interrupted, r.workers, len(r.new), r.pending, flush=True)
