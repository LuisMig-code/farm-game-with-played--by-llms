"""Simula os cenarios de um intervalo de sementes, em paralelo.

    venv/Scripts/python.exe simulate_range.py --from 1 --to 1000
    venv/Scripts/python.exe simulate_range.py --from 1 --to 1000 --workers 8 --days 121

Pula a semente que ja esta no log com os mesmos dias e as mesmas regras do jogo;
as outras sao simuladas por varios processos. No fim mostra, para o intervalo
pedido, a media de promocoes e as sementes com menos e com mais. Ver
docs/CENARIOS.md.
"""

import argparse
import os
import sys
from pathlib import Path

# O pygame, importado pelo jogo, imprime um aviso ao carregar -- uma vez por processo.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from seed_scenarios import settings  # noqa: E402

RANKING_SIZE = 3            # quantas sementes mostrar com menos e com mais promocoes
PROGRESS_MIN_SEEDS = 1000   # abaixo disso termina rapido demais para valer o progresso


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cenarios de um intervalo de sementes, em paralelo")
    p.add_argument("--from", dest="first", type=int, required=True, help="primeira semente")
    p.add_argument("--to", dest="last", type=int, required=True, help="ultima semente (inclusive)")
    p.add_argument("--days", type=int, default=settings.DAYS,
                   help=f"quantos dias simular, a partir do dia 1 (padrao {settings.DAYS})")
    p.add_argument("--workers", type=int, default=settings.WORKERS,
                   help=f"processos (padrao: um por nucleo, {os.cpu_count()} nesta maquina)")
    p.add_argument("--out", type=Path, default=settings.OUT_DIR,
                   help=f"pasta de log (padrao {settings.OUT_DIR.name}/)")
    args = p.parse_args(argv)
    if args.first > args.last:
        p.error("--from maior que --to")
    quantas = args.last - args.first + 1
    if quantas > settings.MAX_SEEDS:
        p.error(f"{quantas} sementes passam do teto de {settings.MAX_SEEDS} por execucao "
                "(MAX_SEEDS em seed_scenarios/settings.py): divida o intervalo")
    if args.days < 1:
        p.error("--days precisa ser pelo menos 1")
    if args.workers is not None and args.workers < 1:
        p.error("--workers precisa ser pelo menos 1")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    from seed_scenarios.batch import INTERRUPTED, promo_ranking, run_batch
    from seed_scenarios.store import ScenarioStore

    print(f"sementes {args.first} a {args.last} | {args.days} dias", flush=True)
    decimos = [0]

    def progresso(feitas: int, total: int) -> None:
        if total >= PROGRESS_MIN_SEEDS and feitas * 10 // total > decimos[0]:
            decimos[0] = feitas * 10 // total
            print(f"  {feitas}/{total} simuladas", flush=True)

    r = run_batch(range(args.first, args.last + 1), days=args.days, workers=args.workers,
                  out_dir=args.out, script="simulate_range", label=f"{args.first}..{args.last}",
                  progress=progresso)

    if r.interrupted == INTERRUPTED:
        print(f"interrompido com Ctrl+C: {r.pending} sementes nao chegaram a ser gravadas")
    linha = (f"{len(r.requested)} sementes em {_num(r.seconds, 1)} s, {r.workers} processo(s), "
             f"regras {r.rules}: {len(r.new)} novas, {len(r.redone)} refeitas, "
             f"{len(r.skipped)} puladas (ja estavam no log)")
    if r.failures:
        linha += f", {len(r.failures)} falhas"
    print(linha)
    for semente, erro in list(r.failures.items())[:5]:
        print(f"  falhou a semente {semente}: {erro}", file=sys.stderr)
    if r.stale_elsewhere:
        print(f"aviso: o resumo tem {r.stale_elsewhere} semente(s) fora do intervalo simuladas com "
              "outros dias ou regras; elas sao refeitas quando entrarem num intervalo pedido")

    menos, mais, media = promo_ranking(r.rows, RANKING_SIZE)
    if media is not None:
        print(f"promocoes em {args.days} dias, nas {len(r.rows)} sementes do intervalo no log:")
        print(f"  media: {_num(media, 1)} por semente ({_num(media / args.days, 2)} por dia)")
        print("  menos: " + " | ".join(f"semente {s} ({p})" for p, s in menos))
        print("  mais:  " + " | ".join(f"semente {s} ({p})" for p, s in mais))

    store = ScenarioStore(args.out)
    print(f"resumo: {store.summary_path}")
    print(f"dia a dia: {store.seeds_dir / 'semente_<N>.csv'}")
    if r.save_error:
        print(f"ATENCAO: nao deu para gravar {r.save_error} (arquivo aberto em outro programa?)",
              file=sys.stderr)
        return 1
    if r.interrupted:
        return 130
    return 1 if r.failures else 0


def _num(valor: float, casas: int) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


if __name__ == "__main__":
    sys.exit(main())
