"""A pasta de uma run e tudo que ela grava.

    runs_llm/
      resumo.csv
      <AAAA-MM-DD_HH-MM-SS>_<modelo>_<modo>_seed<N>/
        LEIAME.md  config.json  agente.log
        chamadas.csv  comandos.csv  dias.csv  erros_gramatica.csv
        estrategia/   dias/dia_001/ ...   jogo/   video.mp4
        conhecimento_final.txt
    logs/                                  a pasta de logs do jogo
      IA_<modelo>_run_<id>_semente<N>_<data>.log / .csv   copia do que esta em jogo/
      IA_<modelo>_celulas_estragadas.csv                 acumulado por modelo

O nome da pasta ordena cronologicamente e diz modelo, modo e semente. Todo CSV e
gravado com flush por linha: uma run interrompida no meio continua legivel.
"""

import csv
import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

CALLS_HEADER = ("dia", "tipo", "tentativa", "status", "inicio", "fim", "segundos",
                "http_status", "finish_reason", "provedor", "tokens_in", "tokens_out",
                "tokens_raciocinio", "custo_usd", "erro")
COMMANDS_HEADER = ("dia", "ordem", "comando", "codigo", "detalhe", "pedido", "efetivo",
                   "passos", "moedas", "estamina_antes", "estamina_depois")
DAYS_HEADER = (
    "dia", "estacao", "status_llm", "dia_perdido", "moedas_inicio", "moedas_fim",
    "comandos", "ok", "parcial", "erro_gramatica", "erro_contexto", "erro_recurso",
    "truncado_stamina", "truncado", "estamina_gasta", "andando", "plantando", "colhendo",
    "fertilizando", "limpando", "estamina_sobrando", "canteiros_visitados", "vendidas",
    "vendidas_abaixo_do_base", "apodrecidas", "plantas_no_chao", "conhecimento_linhas",
    "conhecimento_novas", "conhecimento_removidas", "conhecimento_cortadas", "chamadas",
    "segundos_llm", "segundos_maior_chamada", "segundos_execucao", "tokens_in",
    "tokens_out", "custo_usd",
)
GRAMMAR_HEADER = ("dia", "ordem", "comando", "erro")
SUMMARY_HEADER = ("pasta", "inicio", "fim", "modelo", "modo", "seed", "dias_jogados",
                  "horizonte", "moedas_fim", "dias_perdidos", "dias_timeout", "dias_truncados",
                  "no_chao_no_fim", "canteiros_usados", "erros_gramatica", "erros_contexto",
                  "erros_recurso", "chamadas", "segundos_llm_total", "segundos_por_chamada_media",
                  "segundos_maior_chamada", "segundos_run", "tokens_in", "tokens_out",
                  "custo_usd", "interrompida")

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def slug(texto: str) -> str:
    """Pedaco seguro para nome de pasta: 'openai/gpt-5.6-luna' -> 'gpt-5.6-luna'."""
    base = texto.split("/")[-1]
    return re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-") or "modelo"


def _hora(momento: datetime | None) -> str:
    return momento.isoformat(sep=" ", timespec="seconds") if momento else ""


def publish_game_logs(game, dest: Path, prefix: str) -> list[Path]:
    """Copia os logs nativos da partida para a pasta de logs do jogo, com prefixo.

    Na run eles continuam em jogo/, com o nome que o jogo deu. Em `dest` o prefixo
    separa a partida jogada por IA das jogadas por gente. O historico de celulas
    estragadas, que o jogo acumula entre partidas, aqui e acumulado por modelo.
    Chame depois de fechar a sessao, para as ultimas linhas ja estarem gravadas.
    """
    dest.mkdir(parents=True, exist_ok=True)
    publicados = []
    for origem in (game.run_log.text_path, game.run_log.csv_path):
        if origem.is_file():
            publicados.append(Path(shutil.copy2(origem, dest / f"{prefix}{origem.name}")))

    estragadas = game.spoiled_cells.path
    if estragadas.is_file():
        with estragadas.open(newline="", encoding="utf-8") as f:
            cabecalho, *linhas = list(csv.reader(f)) or [[]]
        if linhas:
            acumulado = dest / f"{prefix}{estragadas.name}"
            novo = not acumulado.exists()
            with acumulado.open("a", newline="", encoding="utf-8") as f:
                escritor = csv.writer(f)
                if novo:
                    escritor.writerow(cabecalho)
                escritor.writerows(linhas)
            publicados.append(acumulado)
    return publicados


def call_timing(kind: str, attempt: int, result) -> dict:
    """O tempo de uma chamada, no formato dos chamadas.json."""
    return {"tipo": kind, "tentativa": attempt, "status": result.status,
            "inicio": _hora(result.started_at), "fim": _hora(result.finished_at),
            "segundos": round(result.duration, 1)}


class _Csv:
    def __init__(self, path: Path, header):
        self.path = path
        novo = not path.exists()
        self._file = path.open("a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        if novo:
            self._writer.writerow(header)
            self._file.flush()

    def row(self, values) -> None:
        self._writer.writerow(values)
        self._file.flush()

    def close(self) -> None:
        self._file.close()


class RunFolder:
    def __init__(self, runs_dir: Path, *, model: str, mode: str, seed: int,
                 started: datetime | None = None):
        self.started = started or datetime.now()
        self.name = f"{self.started:%Y-%m-%d_%H-%M-%S}_{slug(model)}_{mode}_seed{seed}"
        self.root = runs_dir / self.name
        sufixo = 2                                 # duas runs no mesmo segundo
        while self.root.exists():
            self.root = runs_dir / f"{self.name}_{sufixo}"
            sufixo += 1
        self.name = self.root.name
        self.runs_dir = runs_dir

        # O Windows limita caminhos a 260 caracteres, e o log nativo do jogo
        # (run_<id>_semente<N>_<data>.log, ~50) mora em jogo/ dentro da run.
        mais_longo = len(str(self.root.resolve())) + len("/jogo/") + 60
        if mais_longo > 255:
            logging.getLogger(__name__).warning(
                "caminho da run perto do limite de 260 caracteres do Windows (%d): "
                "use um --runs-dir mais curto se aparecer FileNotFoundError", mais_longo)

        for sub in ("estrategia", "dias", "jogo"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

        self.calls = _Csv(self.root / "chamadas.csv", CALLS_HEADER)
        self.commands = _Csv(self.root / "comandos.csv", COMMANDS_HEADER)
        self.days = _Csv(self.root / "dias.csv", DAYS_HEADER)
        self.grammar_errors = _Csv(self.root / "erros_gramatica.csv", GRAMMAR_HEADER)

        self._handler = logging.FileHandler(self.root / "agente.log", encoding="utf-8")
        self._handler.setFormatter(logging.Formatter(LOG_FORMAT))
        raiz = logging.getLogger()
        raiz.addHandler(self._handler)
        if not raiz.isEnabledFor(logging.INFO):
            raiz.setLevel(logging.INFO)

    # ------------------------------------------------------------- caminhos

    @property
    def game_logs(self) -> Path:
        return self.root / "jogo"

    @property
    def video(self) -> Path:
        return self.root / "video.mp4"

    def day_dir(self, day: int) -> Path:
        pasta = self.root / "dias" / f"dia_{day:03d}"
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    # --------------------------------------------------------------- escrita

    def text(self, relative: str | Path, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def json(self, relative: str | Path, data) -> Path:
        return self.text(relative, json.dumps(data, ensure_ascii=False, indent=2))

    def prompt_text(self, relative: str | Path, prompt) -> Path:
        return self.text(relative, f"===== SYSTEM =====\n{prompt.system}\n\n"
                                   f"===== USER =====\n{prompt.user}\n")

    def response_text(self, relative: str | Path, result) -> Path:
        """A resposta bruta, com raciocinio e metadados -- nunca a chave."""
        partes = [
            f"status: {result.status}",
            f"inicio: {_hora(result.started_at)} | fim: {_hora(result.finished_at)} | "
            f"segundos: {result.duration:.1f}",
            f"http_status: {result.http_status} | finish_reason: {result.finish_reason} | "
            f"provedor: {result.provider}",
            f"tokens_in: {result.tokens_in} | tokens_out: {result.tokens_out} | "
            f"tokens_raciocinio: {result.reasoning_tokens} | custo_usd: {result.cost}",
        ]
        if result.error:
            partes += ["", "===== ERRO =====", result.error]
        if result.reasoning:
            partes += ["", "===== RACIOCINIO DO MODELO =====", result.reasoning]
        partes += ["", "===== RESPOSTA =====", result.content or "(vazia)"]
        return self.text(relative, "\n".join(partes) + "\n")

    def call_row(self, day, kind, attempt, result) -> None:
        self.calls.row([day, kind, attempt, result.status, _hora(result.started_at),
                        _hora(result.finished_at), f"{result.duration:.1f}", result.http_status,
                        result.finish_reason, result.provider, result.tokens_in,
                        result.tokens_out, result.reasoning_tokens, result.cost,
                        (result.error or "")[:300].replace("\n", " ")])

    def append_summary(self, row: dict) -> None:
        caminho = self.runs_dir / "resumo.csv"
        if caminho.exists():
            with caminho.open(newline="", encoding="utf-8") as f:
                leitor = csv.DictReader(f)
                antigas = list(leitor)
                cabecalho = tuple(leitor.fieldnames or ())
            if cabecalho != SUMMARY_HEADER:
                # Colunas mudaram entre versoes: reescreve com o cabecalho atual, sem
                # perder as runs antigas (colunas novas ficam vazias nelas).
                with caminho.open("w", newline="", encoding="utf-8") as f:
                    escritor = csv.DictWriter(f, fieldnames=SUMMARY_HEADER, extrasaction="ignore")
                    escritor.writeheader()
                    escritor.writerows(antigas)
        resumo = _Csv(caminho, SUMMARY_HEADER)
        resumo.row([row.get(k, "") for k in SUMMARY_HEADER])
        resumo.close()

    def close(self) -> None:
        for arquivo in (self.calls, self.commands, self.days, self.grammar_errors):
            arquivo.close()
        logging.getLogger().removeHandler(self._handler)
        self._handler.close()
