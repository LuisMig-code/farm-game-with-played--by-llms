"""Um arquivo de texto e um CSV para cada run.

Uma run e uma partida: comeca no dia 1 e termina ao perder, ao reiniciar com R
ou ao sair do jogo. Cada uma gera dois arquivos em logs/, nomeados com o id da
run e a data/hora de inicio:

    run_<id>_<AAAA-MM-DD_HH-MM-SS>.log   texto, o mesmo do console
    run_<id>_<AAAA-MM-DD_HH-MM-SS>.csv   uma linha por acao, movimentacao inclusa
"""

import csv
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

CSV_HEADER = (
    "timestamp", "segundos", "dia", "acao",
    "de_col", "de_lin", "para_col", "para_lin",
    "item", "quantidade", "preco", "estamina",
)

Cell = tuple[int, int]


class RunLog:
    def __init__(self, logs_dir: Path):
        self.run_id = uuid.uuid4().hex[:8]
        self.started_at = datetime.now()
        self._clock = time.perf_counter()
        self._closed = False

        logs_dir.mkdir(exist_ok=True)
        stem = f"run_{self.run_id}_{self.started_at:%Y-%m-%d_%H-%M-%S}"
        self.text_path = logs_dir / f"{stem}.log"
        self.csv_path = logs_dir / f"{stem}.csv"

        # O texto sai pelo logging normal: basta pendurar um handler proprio
        # da run na raiz, e tirar no fim.
        self._handler = logging.FileHandler(self.text_path, encoding="utf-8")
        self._handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root = logging.getLogger()
        root.addHandler(self._handler)
        if not root.isEnabledFor(logging.INFO):
            # Sem isso o arquivo da run sairia vazio caso o logging nao tenha
            # sido configurado antes (main.py configura, testes nem sempre).
            root.setLevel(logging.INFO)

        self._file = self.csv_path.open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(CSV_HEADER)
        self._file.flush()

        logger.info("run %s iniciada | %s | %s", self.run_id,
                    self.text_path.name, self.csv_path.name)

    def record(self, action: str, *, day: int, stamina: int,
               origin: Cell | None = None, cell: Cell | None = None,
               item: str = "", amount: object = "", price: object = "") -> None:
        """Uma linha no CSV. `origin` so e usado no movimento."""
        if self._closed:
            return
        self._writer.writerow([
            datetime.now().isoformat(sep=" ", timespec="milliseconds"),
            f"{time.perf_counter() - self._clock:.3f}",
            day, action,
            *(origin if origin else ("", "")),
            *(cell if cell else ("", "")),
            item, amount, price, stamina,
        ])
        # Flush a cada linha: a run pode acabar com a janela sendo fechada.
        self._file.flush()

    def close(self, reason: str = "fim") -> None:
        if self._closed:
            return
        logger.info("run %s encerrada (%s)", self.run_id, reason)
        self._closed = True
        logging.getLogger().removeHandler(self._handler)
        self._handler.close()
        self._file.close()
