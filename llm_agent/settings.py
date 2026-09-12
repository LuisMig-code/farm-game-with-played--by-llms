"""Configuracao dos agentes LLM. Sem logica, apenas valores.

Mora aqui, e nao em `farm/settings.py`, para o jogo continuar intocado. Tudo que
tem flag na linha de comando (`run_llm.py --help`) pode ser sobreposto por ela.
"""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT_DIR / "docs"
ENV_FILE = ROOT_DIR / ".env"

# ------------------------------------------------------------------- modelo
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY_ENV = "OPEN_ROUTER_API_KEY"      # lido do ambiente ou do .env
MODEL = "nvidia/nemotron-3.5-lightning:free"
TEMPERATURE = 0
# Modelos de raciocinio gastam tokens pensando antes de responder: um teto baixo
# corta a resposta no meio do JSON.
MAX_TOKENS = 20000
INCLUDE_REASONING = True                 # grava o raciocinio junto da resposta

# -------------------------------------------------------------- chamadas
# Prazo de UMA chamada. Sem resposta nesse tempo, o jogador dorme e o dia fica
# marcado como timeout -- sem nova tentativa. O OpenRouter as vezes desiste sozinho
# por volta de 300s (HTTP 504), o que tambem conta como timeout.
API_TIMEOUT_SECONDS = 360     # 6 min
# Tentativas quando a resposta CHEGOU mas nao serve (JSON invalido, 429, 5xx).
API_MAX_ATTEMPTS = 3
API_RETRY_WAIT_SECONDS = 5

# ------------------------------------------------------------------ run
DAYS = 121                     # ano completo + 1 dia de primavera
MODES = ("principal", "sem_memoria")
MODE = "principal"             # sem_memoria: o caderno entra sempre vazio
NOTEBOOK_MAX_LINES = 20
REASONING_MAX_CHARS = 800      # o raciocinio do dia e cortado nesse tamanho

# O jogo declara derrota com estamina 0 mesmo em cima da cama, entao o jogador
# precisa CHEGAR em casa com pelo menos isso.
STAMINA_RESERVE = 1

# Documentos de regra enviados ao modelo, na ordem.
RULE_DOCS = ("GAME_RULES.md", "CULTIVO.md", "COMERCIO.md", "ESTACOES.md")

# ------------------------------------------------------------- execucao
REALTIME = False               # False: passo fixo de 1/60s, video em tempo de jogo
VIDEO = True
RUNS_DIR = ROOT_DIR / "runs_llm"
