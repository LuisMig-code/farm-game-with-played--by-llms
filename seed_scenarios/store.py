"""A pasta de log do simulador e tudo que ela grava.

    cenarios/
      resumo.csv                  uma linha por semente: metricas e como foi simulada
      execucoes.csv               uma linha por execucao dos scripts
      sementes/semente_<N>.csv    o cenario da semente, uma linha por dia

So o processo principal escreve o resumo e as execucoes; cada processo do pool
escreve os CSVs das suas sementes. Arquivo reescrito passa por um temporario e
`os.replace`: uma execucao morta no meio nunca deixa um CSV pela metade que
pareca pronto.
"""

import csv
import os
import time
from pathlib import Path

from seed_scenarios.simulator import DAY_HEADER, METRICS_HEADER

SUMMARY_HEADER = ("semente", "dias", "regras", *METRICS_HEADER, "execucao", "simulado_em", "ms")
EXECUTIONS_HEADER = ("execucao", "script", "inicio", "fim", "segundos", "sementes", "dias",
                     "processos", "pedidas", "novas", "refeitas", "puladas", "falhas", "regras",
                     "python", "interrompida")

# O Windows recusa substituir um arquivo aberto em outro programa (o resumo.csv no
# Excel, um antivirus olhando o CSV recem-criado): tenta de novo antes de desistir.
REPLACE_ATTEMPTS = 3
REPLACE_WAIT_SECONDS = 1.0


class ScenarioStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.seeds_dir = self.root / "sementes"
        self.summary_path = self.root / "resumo.csv"
        self.executions_path = self.root / "execucoes.csv"

    def seed_file(self, seed: int) -> Path:
        return self.seeds_dir / f"semente_{seed}.csv"

    def saved_seed_files(self) -> set[str]:
        """Os nomes dos CSVs de semente que existem: uma listagem, nao um stat por semente."""
        if not self.seeds_dir.is_dir():
            return set()
        with os.scandir(self.seeds_dir) as entradas:
            return {entrada.name for entrada in entradas}

    # ------------------------------------------------------------- sementes

    def write_days(self, seed: int, cenario) -> Path:
        """Grava o CSV do cenario da semente, substituindo o anterior."""
        self.seeds_dir.mkdir(parents=True, exist_ok=True)
        destino = self.seed_file(seed)
        _write_atomic(destino, DAY_HEADER, (dia.row(seed) for dia in cenario))
        return destino

    # --------------------------------------------------------------- resumo

    def load_summary(self) -> dict[int, dict[str, str]]:
        """As linhas do resumo.csv por semente (valores em texto, como no arquivo)."""
        if not self.summary_path.is_file():
            return {}
        with self.summary_path.open(newline="", encoding="utf-8") as f:
            linhas = {}
            for linha in csv.DictReader(f):
                try:
                    linhas[int(linha["semente"])] = linha
                except (KeyError, TypeError, ValueError):
                    continue                     # linha quebrada: a semente e simulada de novo
            return linhas

    def save_summary(self, linhas: dict[int, dict]) -> None:
        """Reescreve o resumo inteiro, uma linha por semente, na ordem das sementes.

        Sempre com o cabecalho atual: uma coluna nova fica vazia nas linhas antigas,
        que de todo jeito tem outras `regras` e serao simuladas de novo.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        _write_atomic(self.summary_path, SUMMARY_HEADER,
                      ([linha.get(coluna, "") for coluna in SUMMARY_HEADER]
                       for _, linha in sorted(linhas.items())))

    # ------------------------------------------------------------- execucoes

    def append_execution(self, linha: dict) -> None:
        """Acrescenta a execucao ao execucoes.csv (colunas novas reescrevem o cabecalho)."""
        self.root.mkdir(parents=True, exist_ok=True)
        antigas = None
        if self.executions_path.is_file():
            with self.executions_path.open(newline="", encoding="utf-8") as f:
                leitor = csv.DictReader(f)
                if tuple(leitor.fieldnames or ()) != EXECUTIONS_HEADER:
                    antigas = list(leitor)
        if antigas is not None:
            _write_atomic(self.executions_path, EXECUTIONS_HEADER,
                          ([velha.get(coluna, "") for coluna in EXECUTIONS_HEADER]
                           for velha in antigas))
        novo = not self.executions_path.exists()
        with self.executions_path.open("a", newline="", encoding="utf-8") as f:
            escritor = csv.writer(f)
            if novo:
                escritor.writerow(EXECUTIONS_HEADER)
            escritor.writerow([linha.get(coluna, "") for coluna in EXECUTIONS_HEADER])


def _write_atomic(destino: Path, header, linhas) -> None:
    """Escreve num temporario ao lado e troca de uma vez pelo destino."""
    temporario = destino.with_name(f".{destino.name}.{os.getpid()}.tmp")
    try:
        with temporario.open("w", newline="", encoding="utf-8") as f:
            escritor = csv.writer(f)
            escritor.writerow(header)
            escritor.writerows(linhas)
        for tentativa in range(1, REPLACE_ATTEMPTS + 1):
            try:
                os.replace(temporario, destino)
                break
            except PermissionError:
                if tentativa == REPLACE_ATTEMPTS:
                    raise
                time.sleep(REPLACE_WAIT_SECONDS)
    finally:
        if temporario.exists():             # so sobra se a troca falhou
            temporario.unlink()
