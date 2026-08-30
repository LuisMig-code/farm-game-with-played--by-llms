"""Historico das celulas onde uma planta apodreceu, acumulado entre partidas.

Ao contrario dos arquivos de run, este sobrevive ao `R` e a fechar o jogo: e um
CSV unico que so cresce. Nada disso e desenhado -- o jogador nao ve a lista nem
a contagem; o registro existe para uma mecanica futura de solo gasto.
"""

import csv
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

CSV_HEADER = ("timestamp", "run_id", "dia", "col", "lin", "cultura")

Cell = tuple[int, int]


class SpoiledCells:
    def __init__(self, path: Path):
        self.path = path
        self.cells: Counter[Cell] = Counter()
        path.parent.mkdir(exist_ok=True)

        novo = not path.is_file()
        if not novo:
            self._load()
        with path.open("a", newline="", encoding="utf-8") as f:
            if novo:
                csv.writer(f).writerow(CSV_HEADER)
        logger.info("historico de celulas estragadas: %s (%d registros)",
                    path.name, sum(self.cells.values()))

    def _load(self) -> None:
        """Le o que ja existe para `cells` ficar disponivel para consulta."""
        with self.path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    self.cells[(int(row["col"]), int(row["lin"]))] += 1
                except (KeyError, TypeError, ValueError):
                    continue   # linha estranha nao derruba o jogo

    def record(self, cell: Cell, crop: str, day: int, run_id: str) -> None:
        self.cells[cell] += 1
        with self.path.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                datetime.now().isoformat(sep=" ", timespec="seconds"),
                run_id, day, cell[0], cell[1], crop,
            ])
