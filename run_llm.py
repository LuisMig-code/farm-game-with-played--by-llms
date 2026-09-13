"""Roda uma run de um LLM jogando a fazenda via OpenRouter.

    venv/Scripts/python.exe run_llm.py --seed 42
    venv/Scripts/python.exe run_llm.py --seed 42 --days 5 --knowledge base.txt

Os padroes vem de llm_agent/settings.py; cada flag abaixo sobrepoe um deles.
A chave e lida de OPEN_ROUTER_API_KEY (ambiente ou .env).
"""

import argparse
import logging
import sys
from pathlib import Path

from llm_agent import settings


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LLM jogando a fazenda via OpenRouter")
    p.add_argument("--seed", type=int, default=None,
                   help="semente do cenario (padrao: a do jogo, farm/settings.py)")
    p.add_argument("--days", type=int, default=settings.DAYS,
                   help=f"quantos dias jogar (padrao {settings.DAYS})")
    p.add_argument("--model", default=settings.MODEL, help=f"id no OpenRouter (padrao {settings.MODEL})")
    p.add_argument("--mode", choices=settings.MODES, default=settings.MODE,
                   help="principal, ou sem_memoria (o conhecimento chega sempre vazio)")
    p.add_argument("--knowledge", type=Path, default=None,
                   help="txt com base de conhecimento previa, anexada a chamada de estrategia")
    p.add_argument("--timeout", type=float, default=settings.API_TIMEOUT_SECONDS,
                   help=f"segundos de espera por chamada (padrao {settings.API_TIMEOUT_SECONDS})")
    p.add_argument("--attempts", type=int, default=settings.API_MAX_ATTEMPTS,
                   help="tentativas quando a resposta chega mas nao serve")
    p.add_argument("--no-video", action="store_true", help="nao gravar o MP4")
    p.add_argument("--realtime", action="store_true",
                   help="roda a 60 fps de verdade em vez de acelerado")
    p.add_argument("--speed", type=float, default=settings.GAME_SPEED,
                   help="velocidade das acoes na tela (andar, plantar, colher, dormir): 1 = a do "
                        f"jogo (padrao {settings.GAME_SPEED:g})")
    p.add_argument("--headless", action="store_true",
                   help="sem janela (o video e gravado igual); o mais estavel para runs longas")
    p.add_argument("--allow-sleep", action="store_true",
                   help="deixa o Windows suspender por inatividade durante a run")
    p.add_argument("--runs-dir", type=Path, default=settings.RUNS_DIR,
                   help=f"onde criar a pasta da run (padrao {settings.RUNS_DIR.name}/)")
    return p.parse_args(argv)


def keep_awake() -> bool:
    """Impede o Windows de suspender por inatividade enquanto a run durar.

    Uma run de dezenas de dias leva horas sem ninguem mexer no PC; se ele entrar
    em espera, o processo congela e as chamadas estouram o prazo. O pedido vale so
    para este processo e acaba sozinho quando ele termina -- nenhuma configuracao
    do sistema e alterada. Tampa fechada ou "Suspender" manual ainda suspendem.
    """
    if sys.platform != "win32":
        return False
    import ctypes
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    return bool(ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED))


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.knowledge and not args.knowledge.is_file():
        print(f"base de conhecimento nao encontrada: {args.knowledge}", file=sys.stderr)
        return 2

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    if args.headless:
        # Antes de importar o pygame: o driver nulo troca a janela por uma superficie.
        import os
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    if not args.allow_sleep and keep_awake():
        logging.getLogger(__name__).info("o PC nao vai suspender por inatividade durante a run")

    from llm_agent.runner import LLMRun       # importa pygame so depois dos argumentos
    resumo = LLMRun(seed=args.seed, days=args.days, model=args.model, mode=args.mode,
                    knowledge_path=args.knowledge, video=not args.no_video,
                    realtime=args.realtime, speed=args.speed, api_timeout=args.timeout,
                    max_attempts=args.attempts, runs_dir=args.runs_dir).run()

    print()
    print(f"run: {args.runs_dir / resumo['pasta']}")
    print(f"moedas no fim: {resumo['moedas_fim']} | dias jogados: {resumo['dias_jogados']} | "
          f"dias perdidos: {resumo['dias_perdidos']} | dias truncados: {resumo['dias_truncados']} | "
          f"custo US$ {resumo['custo_usd']}")
    return 1 if resumo["interrompida"] else 0


if __name__ == "__main__":
    sys.exit(main())
