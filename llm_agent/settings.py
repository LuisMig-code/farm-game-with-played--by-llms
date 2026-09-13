"""Configuracao dos agentes LLM. Sem logica, apenas valores.

Mora aqui, e nao em `farm/settings.py`, para o jogo continuar intocado. Tudo que
tem flag na linha de comando (`run_llm.py --help`) pode ser sobreposto por ela.
"""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"

# Os prompts sao lidos destes .md em runtime: editar o arquivo muda a proxima run
# sem tocar em Python.
PROMPTS_DIR = ROOT_DIR / "prompts"
PROMPT_STRATEGY = PROMPTS_DIR / "prompt_inicial.md"
PROMPT_DAY = PROMPTS_DIR / "prompt_gaming.md"

# ------------------------------------------------------------------- modelo
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY_ENV = "OPEN_ROUTER_API_KEY"      # lido do ambiente ou do .env
MODEL = "openai/gpt-5.6-luna"
# None = nao envia. O gpt-5.6-luna nao lista `temperature` nos parametros aceitos.
TEMPERATURE: float | None = None
# None = deixa o provedor decidir. Aceita "low", "medium" ou "high" nos modelos
# que listam `reasoning_effort`.
REASONING_EFFORT: str | None = None
# Pede JSON de verdade ao provedor (`response_format`). Modelos que nao aceitam o
# parametro caem no parser, que extrai o objeto do texto de qualquer jeito.
RESPONSE_FORMAT_JSON = True
MAX_TOKENS = 16000
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
MODE = "principal"             # sem_memoria: o conhecimento entra sempre vazio

STRATEGY_MAX_CHARS = 128       # o campo "estrategia", reinjetado todo dia
KNOWLEDGE_MAX_LINES = 15       # o bloco "conhecimento", reescrito inteiro todo dia
DIARY_DAYS = 5                 # janela do diario gerado pelo codigo

# O jogo declara derrota com estamina 0 mesmo em cima da cama, entao o jogador
# precisa CHEGAR em casa com pelo menos isso.
STAMINA_RESERVE = 1

# ------------------------------------------------------------- execucao
REALTIME = False               # False: passo fixo de 1/60s, sem esperar o relogio
# Velocidade das acoes na tela: andar, plantar, colher, fertilizar, limpar e a
# transicao do sono. 1.0 = a do jogo; 2.0 = cada uma na metade do tempo, e o
# video junto. Nao muda regra: estamina, crescimento e precos contam passos e
# dias, nao segundos. Teto: `Session.max_speed()` (~7x a 60 fps).
GAME_SPEED = 2.0
VIDEO = True
RUNS_DIR = ROOT_DIR / "runs_llm"
# Ao fim da run, os logs nativos do jogo tambem vao para a pasta de logs do jogo
# (a mesma de farm/settings.py), com o prefixo IA_<modelo>_ para nao se misturarem
# com os das partidas jogadas por gente. A copia original fica em jogo/, na run.
GAME_LOGS_DIR = ROOT_DIR / "logs"
GAME_LOGS_PREFIX = "IA_{modelo}_"
