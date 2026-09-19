"""Simula o cenario da loja de uma semente: estoque e promocao de cada dia.

    venv/Scripts/python.exe simulate_seed.py --seed 42
    venv/Scripts/python.exe simulate_seed.py --seed 42 --days 30

Grava cenarios/sementes/semente_<N>.csv, com um dia por linha, atualiza a linha
da semente em cenarios/resumo.csv e registra a execucao em cenarios/execucoes.csv.
Nao abre o jogo: usa o mesmo `Market` que ele usa. Ver docs/CENARIOS.md.
"""

import argparse
import os
import sys
from pathlib import Path

# O pygame, importado pelo jogo, imprime um aviso ao carregar; aqui ele so polui.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from seed_scenarios import settings  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cenario da loja de uma semente, dia a dia")
    p.add_argument("--seed", type=int, default=None,
                   help="semente (padrao: FARM_SEED, depois SEED de farm/settings.py, como no main.py)")
    p.add_argument("--days", type=int, default=settings.DAYS,
                   help=f"quantos dias simular, a partir do dia 1 (padrao {settings.DAYS})")
    p.add_argument("--out", type=Path, default=settings.OUT_DIR,
                   help=f"pasta de log (padrao {settings.OUT_DIR.name}/)")
    args = p.parse_args(argv)
    if args.days < 1:
        p.error("--days precisa ser pelo menos 1")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    from farm.crops import crop_of_seed
    from farm.rng import resolve_seed
    from farm.seasons import SEASONS
    from seed_scenarios.batch import run_batch
    from seed_scenarios.simulator import COLUMN, ITEMS
    from seed_scenarios.store import ScenarioStore

    semente = resolve_seed(args.seed)
    r = run_batch([semente], days=args.days, workers=1, out_dir=args.out, force=True,
                  script="simulate_seed")
    if r.interrupted:
        print("interrompido antes de gravar a semente")
        return 130
    if semente in r.failures:
        print(f"semente {semente}: nao deu para gravar o CSV ({r.failures[semente]})", file=sys.stderr)
        return 1

    m = r.rows[semente]
    print(f"semente {semente} | {args.days} dias | regras {r.rules}")
    print(f"promocoes: {m['promocoes']} em {m['dias_com_promocao']} dias "
          f"(media {_num(m['media_promocoes_dia'])} por dia, ate {m['max_promocoes_dia']} num dia), "
          f"{m['desconto_total']} moedas de desconto somadas")
    print("  por estacao: " + " | ".join(f"{e.key} {m[f'promocoes_{e.key}']}" for e in SEASONS))
    print("  por item:    " + " | ".join(f"{crop_of_seed(i)} {m[f'promocoes_{COLUMN[i]}']}"
                                         for i in ITEMS))
    faltas = [f"{crop_of_seed(i)} {m[f'dias_sem_estoque_{COLUMN[i]}']}" for i in ITEMS
              if m[f"dias_sem_estoque_{COLUMN[i]}"]]
    print("dias sem estoque: " + (" | ".join(faltas) if faltas else "nenhum"))
    print(f"cenario dia a dia: {ScenarioStore(args.out).seed_file(semente)}")
    if r.save_error:
        print(f"ATENCAO: nao deu para gravar {r.save_error} (arquivo aberto em outro programa?)",
              file=sys.stderr)
        return 1
    return 0


def _num(valor) -> str:
    return f"{float(valor):.2f}".replace(".", ",")


if __name__ == "__main__":
    sys.exit(main())
