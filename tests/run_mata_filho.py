"""Uma run do agente com cliente falso que trava na chamada do dia 4, como um LLM lento.

Usado pelo bloco 19 da suite: o processo e parado a forca (ou com Ctrl+C) no
meio da espera, e a suite confere o video.mp4 que sobrou.

    python run_mata_filho.py <pasta_de_saida> <mata|ctrlc>
"""
import os
import sys
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
RAIZ = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
OUT = Path(sys.argv[1])
modo = sys.argv[2]                                   # "mata" (espera eterna) ou "ctrlc"
from farm import settings as game_settings
game_settings.LOGS_DIR = OUT / "logs_jogo"
from fake_llm import FakeClient, padrao_dia, padrao_estrategia
from llm_agent.runner import LLMRun

PLANO = ["IR canteiro_esquerdo", "PLANTAR cenoura TUDO", "IR loja", "IR canteiro_direito", "IR cama"]
agente = None


def roteiro(kind, day, messages, attempt):
    if kind == "estrategia":
        return padrao_estrategia(["- plantar e andar"])
    if day == 4:
        print("TRAVOU", agente.session.recorder.frames, agente.folder.root, flush=True)
        if modo == "ctrlc":
            raise KeyboardInterrupt                  # o Ctrl+C chega durante a espera
        return ("sleep", 3600, padrao_dia([]))
    return padrao_dia(PLANO)


agente = LLMRun(days=8, client=FakeClient(roteiro, timeout=3600), runs_dir=OUT / "runs", seed=42,
                video=True, game_logs_dir=OUT / "logs_ia")
agente.run()
print("TERMINOU", flush=True)
