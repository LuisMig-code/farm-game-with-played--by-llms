"""Simula varias sementes, em paralelo, pulando as que ja estao no log.

    from seed_scenarios.batch import run_batch
    resultado = run_batch(range(1, 1001), workers=8)

Com mais de um processo o pool sobe interpretadores novos, e no Windows eles
reimportam o script principal: quem chama `run_batch` com `workers` > 1 precisa
estar atras de `if __name__ == "__main__":`.
"""

import os
import platform
import signal
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from seed_scenarios import settings
from seed_scenarios.simulator import rules_fingerprint, simulate, summarize
from seed_scenarios.store import ScenarioStore

WINDOWS_MAX_WORKERS = 61        # o ProcessPoolExecutor do Windows nao aceita mais
POLL_SECONDS = 0.5              # de quanto em quanto o processo principal ve o Ctrl+C
INTERRUPTED = "ctrl+c"


@dataclass
class BatchResult:
    """O que uma execucao fez. As listas so tem sementes que terminaram."""

    execution: str
    rules: str
    days: int
    requested: list[int]
    new: list[int] = field(default_factory=list)
    redone: list[int] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)
    failures: dict[int, str] = field(default_factory=dict)
    # O resumo de cada semente pedida que ficou no log com estes dias e regras.
    rows: dict[int, dict] = field(default_factory=dict)
    workers: int = 1
    seconds: float = 0.0
    interrupted: str = ""
    save_error: str = ""        # resumo.csv ou execucoes.csv que nao deu para gravar
    # Sementes do resumo, fora do pedido, simuladas com outros dias ou regras.
    stale_elsewhere: int = 0

    @property
    def pending(self) -> int:
        """Pedidas que nao chegaram ao fim (so numa execucao interrompida)."""
        return (len(self.requested) - len(self.new) - len(self.redone) - len(self.skipped)
                - len(self.failures))


def run_batch(seeds, *, days: int = settings.DAYS, workers: int | None = 1,
              out_dir: Path = settings.OUT_DIR, force: bool = False, script: str = "run_batch",
              label: str | None = None, progress=None) -> BatchResult:
    """Simula as sementes pedidas e atualiza a pasta de log.

    Pula a semente que ja esta no resumo com os mesmos `days` e as mesmas regras e
    cujo CSV existe, a nao ser com `force`. As outras vao em lotes de CHUNK_SEEDS
    para `workers` processos (None = um por nucleo). `progress(feitas, total)` e
    chamado a cada lote. Um Ctrl+C para no meio e grava o que terminou.
    """
    inicio = datetime.now()
    relogio = time.perf_counter()
    store = ScenarioStore(out_dir)
    pedidas = list(dict.fromkeys(int(semente) for semente in seeds))   # sem repetir
    r = BatchResult(execution=f"{inicio:%Y-%m-%d_%H-%M-%S}_{os.getpid()}",
                    rules=rules_fingerprint(), days=days, requested=pedidas)

    def vale(linha: dict) -> bool:
        return str(linha.get("dias")) == str(days) and str(linha.get("regras")) == r.rules

    resumo = store.load_summary()
    gravados = store.saved_seed_files()
    a_simular, refazer = [], set()
    for semente in pedidas:
        antiga = resumo.get(semente)
        if (antiga is not None and not force and vale(antiga)
                and store.seed_file(semente).name in gravados):
            r.skipped.append(semente)
            continue
        a_simular.append(semente)
        if antiga is not None:
            refazer.add(semente)
    pedido = set(pedidas)
    r.stale_elsewhere = sum(1 for semente, linha in resumo.items()
                            if semente not in pedido and not vale(linha))

    tamanho = settings.CHUNK_SEEDS
    lotes = [a_simular[i:i + tamanho] for i in range(0, len(a_simular), tamanho)]
    r.workers = min(_workers(workers), max(1, len(lotes)))

    def recolhe(resultados) -> None:
        for semente, metricas, ms, quando, erro in resultados:
            if erro:
                r.failures[semente] = erro
                continue
            resumo[semente] = {"semente": semente, "dias": days, "regras": r.rules, **metricas,
                               "execucao": r.execution, "simulado_em": quando, "ms": ms}
            (r.redone if semente in refazer else r.new).append(semente)
        if progress:
            progress(len(r.new) + len(r.redone) + len(r.failures), len(a_simular))

    try:
        if r.workers == 1:
            for lote in lotes:
                recolhe(simulate_chunk(lote, days, str(store.root)))
        else:
            _run_pool(lotes, days, store.root, r.workers, recolhe)
    except KeyboardInterrupt:
        r.interrupted = INTERRUPTED
    except Exception as erro:
        r.interrupted = f"erro: {type(erro).__name__}: {erro}"
        raise
    finally:
        _save(store, r, resumo, inicio, relogio, script, label, vale)
    return r


def _save(store, r: BatchResult, resumo, inicio, relogio, script, label, vale) -> None:
    """Grava o resumo e a execucao, inclusive depois de um Ctrl+C."""
    erros = []
    if r.new or r.redone:                   # nada mudou: o resumo nem e reaberto
        try:
            store.save_summary(resumo)
        except OSError as erro:
            erros.append(f"resumo.csv: {erro}")
    r.seconds = round(time.perf_counter() - relogio, 2)
    try:
        store.append_execution({
            "execucao": r.execution, "script": script, "inicio": _hora(inicio),
            "fim": _hora(datetime.now()), "segundos": r.seconds,
            "sementes": label or describe(r.requested), "dias": r.days, "processos": r.workers,
            "pedidas": len(r.requested), "novas": len(r.new), "refeitas": len(r.redone),
            "puladas": len(r.skipped), "falhas": len(r.failures), "regras": r.rules,
            "python": platform.python_version(), "interrompida": r.interrupted,
        })
    except OSError as erro:
        erros.append(f"execucoes.csv: {erro}")
    r.save_error = " | ".join(erros)
    r.rows = {semente: resumo[semente] for semente in r.requested
              if semente in resumo and semente not in r.failures and vale(resumo[semente])}


def _run_pool(lotes, days: int, raiz: Path, processos: int, recolhe) -> None:
    pool = ProcessPoolExecutor(max_workers=processos, initializer=_ignore_sigint)
    try:
        pendentes = {pool.submit(simulate_chunk, lote, days, str(raiz)) for lote in lotes}
        while pendentes:
            # Com prazo: no Windows uma espera sem prazo nao deixa o Ctrl+C chegar.
            prontos, pendentes = wait(pendentes, timeout=POLL_SECONDS, return_when=FIRST_COMPLETED)
            for futuro in prontos:
                recolhe(futuro.result())
    finally:
        # No Ctrl+C os lotes que nem comecaram sao descartados. Os que ja rodam
        # terminam (sao curtos): o CSV fica, mas a semente nao entra no resumo e e
        # refeita na proxima execucao.
        pool.shutdown(wait=True, cancel_futures=True)


def simulate_chunk(seeds: list[int], days: int, out_dir: str) -> list[tuple]:
    """Um lote, dentro de um processo do pool: simula, grava o CSV e devolve as metricas.

    Devolve (semente, metricas, ms, simulado_em, erro) por semente. Um erro de
    gravacao fica so naquela semente, sem derrubar o lote.
    """
    store = ScenarioStore(Path(out_dir))
    feitas = []
    for semente in seeds:
        comeco = time.perf_counter()
        try:
            cenario = simulate(semente, days)
            store.write_days(semente, cenario)
        except OSError as erro:
            feitas.append((semente, None, 0.0, "", f"{type(erro).__name__}: {erro}"))
            continue
        ms = round((time.perf_counter() - comeco) * 1000, 2)
        feitas.append((semente, summarize(cenario), ms, _hora(datetime.now()), ""))
    return feitas


def promo_ranking(rows: dict[int, dict], n: int = 3):
    """As `n` sementes com menos e com mais promocoes entre `rows`, e a media.

    Devolve (menos, mais, media), com menos e mais como listas de (promocoes,
    semente). Empate vai para a semente menor.
    """
    pares = sorted((int(linha["promocoes"]), semente) for semente, linha in rows.items())
    if not pares:
        return [], [], None
    mais = sorted(pares, key=lambda par: (-par[0], par[1]))[:n]
    return pares[:n], mais, sum(promocoes for promocoes, _ in pares) / len(pares)


def describe(seeds: list[int]) -> str:
    """'42', '1..1000' para um intervalo sem buracos, ou a lista."""
    if len(seeds) == 1:
        return str(seeds[0])
    ordenadas = sorted(seeds)
    if ordenadas and ordenadas[-1] - ordenadas[0] == len(ordenadas) - 1:
        return f"{ordenadas[0]}..{ordenadas[-1]}"
    return ",".join(map(str, ordenadas))


def _workers(pedido: int | None) -> int:
    processos = pedido or os.cpu_count() or 1
    if sys.platform == "win32":
        processos = min(processos, WINDOWS_MAX_WORKERS)
    return max(1, processos)


def _ignore_sigint() -> None:
    """Nos processos do pool: o Ctrl+C e do processo principal, que cancela o resto."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def _hora(momento: datetime) -> str:
    return momento.isoformat(sep=" ", timespec="seconds")
