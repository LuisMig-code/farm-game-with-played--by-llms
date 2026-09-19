"""Suite do simulador de cenarios: o simulador contra o jogo, os CSVs e o log.

    venv/Scripts/python.exe tests/check_scenarios.py            # pasta temporaria nova
    venv/Scripts/python.exe tests/check_scenarios.py <pasta>    # pasta nova ou vazia

Sao 7 blocos em sequencia, cada um imprime "N ok: ..." e o fim e "TUDO OK". Leva
menos de um minuto, sem rede: o bloco 1 dorme os 121 dias de uma partida de
verdade. Um assert que falha para tudo com o traceback.

O pool de processos nunca abre dentro deste script: no Windows cada processo
novo reimportaria este arquivo e rodaria a suite de novo. O paralelo e testado
pela linha de comando (bloco 6) e pelo tests/run_interrompe.py (bloco 7). A
suite nunca apaga nada, e o cenarios/ do projeto nao e tocado -- o bloco 6 confere.
"""
import csv
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from farm import settings as game_settings  # noqa: E402
from farm.crops import BUY_PRICES, STOCK_RANGES  # noqa: E402
from farm.seasons import SEASONS, promo_item_chances, season_at  # noqa: E402
from scripting import Session  # noqa: E402
from seed_scenarios import settings  # noqa: E402
from seed_scenarios.batch import INTERRUPTED, run_batch  # noqa: E402
from seed_scenarios.simulator import (COLUMN, DAY_HEADER, ITEMS, METRICS_HEADER,  # noqa: E402
                                      RULE_FILES, rules_fingerprint, simulate, summarize)
from seed_scenarios.store import EXECUTIONS_HEADER, SUMMARY_HEADER, ScenarioStore  # noqa: E402

# Pasta de saida: uma temporaria nova, ou a passada na linha de comando, que
# precisa estar vazia -- a suite nunca apaga nada.
if len(sys.argv) > 1:
    OUT = Path(sys.argv[1])
    if OUT.exists() and any(OUT.iterdir()):
        sys.exit(f"{OUT} nao esta vazia: passe uma pasta nova ou vazia (a suite nao apaga nada)")
else:
    OUT = Path(tempfile.mkdtemp(prefix="cent_"))
print(f"saida da suite: {OUT}", flush=True)
game_settings.LOGS_DIR = OUT / "logs_jogo"          # as partidas do bloco 1 gravam aqui
CENARIOS_REAIS = ROOT / "cenarios"


def cenarios_reais():
    """O que ha no cenarios/ do projeto (pode nem existir): nome, tamanho e mtime."""
    if not CENARIOS_REAIS.is_dir():
        return []
    return sorted((str(p.relative_to(CENARIOS_REAIS)), p.stat().st_size, p.stat().st_mtime_ns)
                  for p in CENARIOS_REAIS.rglob("*"))


CENARIOS_REAIS_ANTES = cenarios_reais()
REGRAS = rules_fingerprint()


def rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def header(path):
    with open(path, newline="", encoding="utf-8") as f:
        return tuple(next(csv.reader(f)))


def roda(*args, env=None):
    """Um dos scripts da raiz (ou de tests/) num processo novo, como o usuario roda."""
    return subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, capture_output=True,
                          text=True, timeout=600, env=env)


# ================== 1. o simulador bate com o jogo, dia a dia
inicio = time.monotonic()
for semente, dias in ((42, 121), (7, 10), (2026, 10)):
    cenario = simulate(semente, dias)
    assert [dia.day for dia in cenario] == list(range(game_settings.FIRST_DAY,
                                                      game_settings.FIRST_DAY + dias))
    with Session(seed=semente, realtime=False, speed=Session.max_speed()) as s:
        for dia in cenario:
            assert s.day == dia.day, (semente, s.day, dia.day)
            assert s.game.market.promos == dia.promos, (semente, dia.day)
            loja = s.observe().market["buy"]
            for item in ITEMS:
                assert loja[item]["stock"] == dia.stock[item], (semente, dia.day, item)
                assert loja[item]["price"] == dia.prices[item], (semente, dia.day, item)
                assert loja[item]["promo"] == (item in dia.promos), (semente, dia.day, item)
                assert loja[item]["full_price"] - loja[item]["price"] == dia.promos.get(item, 0)
            if dia is not cenario[-1]:
                s.sleep()
print(f"1 ok: o simulador bate com o jogo dia a dia: estoque, preco e promocao de cada item "
      f"(semente 42 nos 121 dias, 7 e 2026 em 10) [{time.monotonic() - inicio:.0f} s]", flush=True)


# ================== 2. o CSV do dia: formato e invariantes
store2 = ScenarioStore(OUT / "b2")
arquivo = store2.write_days(42, simulate(42, 121))
assert arquivo == store2.seed_file(42) and arquivo.name == "semente_42.csv"
assert header(arquivo) == DAY_HEADER
linhas = rows(arquivo)
assert [int(l["dia"]) for l in linhas] == list(range(1, 122))
com_promocao = 0
for l in linhas:
    dia = int(l["dia"])
    assert l["semente"] == "42" and l["estacao"] == season_at(dia).key
    listados = {}
    if l["itens_em_promocao"]:
        for parte in l["itens_em_promocao"].split("; "):
            item, desconto = parte.rsplit(" -", 1)
            listados[item] = int(desconto)
    assert list(listados) == [item for item in ITEMS if item in listados]   # na ordem da loja
    for item in ITEMS:
        c = COLUMN[item]
        estoque, desconto, compra = (int(l[f"estoque_{c}"]), int(l[f"desconto_{c}"]),
                                     int(l[f"compra_{c}"]))
        minimo, maximo = STOCK_RANGES[item]
        assert minimo <= estoque <= maximo, (dia, item, estoque)
        assert compra == BUY_PRICES[item] - desconto >= game_settings.MIN_PRICE, (dia, item)
        if item in listados:
            assert estoque > 0 and listados[item] == desconto > 0, (dia, item)
        else:
            assert desconto == 0, (dia, item)
    assert int(l["promocoes"]) == len(listados) <= max(q for q, _ in promo_item_chances(dia))
    assert int(l["desconto_total"]) == sum(listados.values())
    com_promocao += bool(listados)
assert 0 < com_promocao < 121
print("2 ok: CSV do dia com o cabecalho certo, dias 1 a 121, estacao do jogo, estoque na faixa, "
      "promocao so com estoque e compra = preco cheio - desconto", flush=True)


# ================== 3. o resumo bate com a recontagem do CSV do dia
store3 = ScenarioStore(OUT / "b3")
r = run_batch([42, 7, 2026, 42], days=121, workers=1, out_dir=store3.root, script="teste")
assert r.requested == [42, 7, 2026], "semente repetida entra uma vez so"
assert sorted(r.new) == [7, 42, 2026] and not r.redone and not r.skipped and not r.failures
assert header(store3.summary_path) == SUMMARY_HEADER
assert header(store3.executions_path) == EXECUTIONS_HEADER
resumo = store3.load_summary()
assert list(resumo) == [7, 42, 2026], "resumo ordenado pela semente"
for semente in (42, 7, 2026):
    linhas, m = rows(store3.seed_file(semente)), resumo[semente]
    assert (m["dias"], m["regras"], m["execucao"]) == ("121", REGRAS, r.execution)
    assert m["simulado_em"] and float(m["ms"]) > 0
    promos = [int(l["promocoes"]) for l in linhas]
    assert int(m["promocoes"]) == sum(promos)
    assert int(m["dias_com_promocao"]) == sum(1 for p in promos if p)
    assert int(m["max_promocoes_dia"]) == max(promos)
    assert float(m["media_promocoes_dia"]) == round(sum(promos) / 121, 3)
    assert int(m["desconto_total"]) == sum(int(l["desconto_total"]) for l in linhas)
    for estacao in SEASONS:
        assert int(m[f"promocoes_{estacao.key}"]) == sum(
            int(l["promocoes"]) for l in linhas if l["estacao"] == estacao.key)
    for item in ITEMS:
        c = COLUMN[item]
        estoques = [int(l[f"estoque_{c}"]) for l in linhas]
        assert int(m[f"promocoes_{c}"]) == sum(1 for l in linhas if int(l[f"desconto_{c}"]))
        assert float(m[f"estoque_medio_{c}"]) == round(sum(estoques) / len(estoques), 2)
        assert int(m[f"dias_sem_estoque_{c}"]) == estoques.count(0)
    assert sum(int(m[f"promocoes_{e.key}"]) for e in SEASONS) == int(m["promocoes"])
    assert sum(int(m[f"promocoes_{COLUMN[i]}"]) for i in ITEMS) == int(m["promocoes"])
    assert {k: str(v) for k, v in summarize(simulate(semente, 121)).items()} == \
        {k: m[k] for k in METRICS_HEADER}
execucao = rows(store3.executions_path)
assert len(execucao) == 1 and execucao[0]["sementes"] == "7,42,2026"
assert (execucao[0]["script"], execucao[0]["novas"], execucao[0]["processos"]) == ("teste", "3", "1")
print("3 ok: resumo = recontagem do CSV do dia (total, estacoes, itens, estoque), ordenado pela "
      "semente; execucoes.csv com a execucao", flush=True)


# ================== 4. pula o que ja esta no log, refaz o que mudou
out4 = OUT / "b4"
store4 = ScenarioStore(out4)
lote = range(1, 21)


def contagem(resultado):
    return len(resultado.new), len(resultado.redone), len(resultado.skipped)


assert contagem(run_batch(lote, days=30, workers=1, out_dir=out4)) == (20, 0, 0)
mtimes = {s: store4.seed_file(s).stat().st_mtime_ns for s in lote}
resumo_mtime = store4.summary_path.stat().st_mtime_ns
time.sleep(0.05)
r = run_batch(lote, days=30, workers=1, out_dir=out4)
assert contagem(r) == (0, 0, 20) and len(r.rows) == 20
assert {s: store4.seed_file(s).stat().st_mtime_ns for s in lote} == mtimes, "pulada nao e regravada"
assert store4.summary_path.stat().st_mtime_ns == resumo_mtime, "nada mudou: resumo intocado"
store4.seed_file(5).unlink()                                    # CSV sumiu
r = run_batch(lote, days=30, workers=1, out_dir=out4)
assert contagem(r) == (0, 1, 19) and r.redone == [5] and store4.seed_file(5).is_file()
linhas4 = store4.load_summary()
linhas4[7]["regras"] = "000000000000"                           # regras de outra versao do jogo
store4.save_summary(linhas4)
r = run_batch(lote, days=30, workers=1, out_dir=out4)
assert contagem(r) == (0, 1, 19) and r.redone == [7]
assert contagem(run_batch(lote, days=31, workers=1, out_dir=out4)) == (0, 20, 0)   # outros dias
r = run_batch(range(15, 26), days=31, workers=1, out_dir=out4)
assert contagem(r) == (5, 0, 6) and r.new == [21, 22, 23, 24, 25]
r = run_batch([30], days=30, workers=1, out_dir=out4)
assert contagem(r) == (1, 0, 0) and r.stale_elsewhere == 25, "1..25 ficaram com 31 dias"
assert contagem(run_batch([30], days=30, workers=1, out_dir=out4, force=True)) == (0, 1, 0)
execucoes = rows(store4.executions_path)
assert [(e["novas"], e["refeitas"], e["puladas"]) for e in execucoes] == [
    ("20", "0", "0"), ("0", "0", "20"), ("0", "1", "19"), ("0", "1", "19"), ("0", "20", "0"),
    ("5", "0", "6"), ("1", "0", "0"), ("0", "1", "0")]
assert {e["regras"] for e in execucoes} == {REGRAS}
assert [e["dias"] for e in execucoes] == ["30"] * 4 + ["31"] * 2 + ["30"] * 2
resumo4 = store4.load_summary()
assert sorted(resumo4) == list(range(1, 26)) + [30]
assert all(resumo4[s]["regras"] == REGRAS for s in resumo4)
assert not list(out4.rglob("*.tmp")), "sobrou arquivo temporario"
print("4 ok: segunda execucao pula tudo sem regravar; CSV apagado, regras diferentes, outros dias "
      "e force refazem; contagens no execucoes.csv", flush=True)


# ================== 5. regras: a impressao digital dos arquivos do sorteio
assert [p.parent for p in RULE_FILES] == [ROOT / "farm"] * len(RULE_FILES)
assert all(p.is_file() for p in RULE_FILES) and len(REGRAS) == 12
copias = {}
for nome, fim in (("lf", b"\n"), ("crlf", b"\r\n")):
    pasta = OUT / "b5" / nome
    pasta.mkdir(parents=True)
    for original in RULE_FILES:
        texto = original.read_bytes().replace(b"\r\n", b"\n")
        (pasta / original.name).write_bytes(texto.replace(b"\n", fim))
    copias[nome] = [pasta / p.name for p in RULE_FILES]
assert rules_fingerprint(copias["lf"]) == rules_fingerprint(copias["crlf"]) == REGRAS
settings_copia = OUT / "b5" / "lf" / "settings.py"
texto = settings_copia.read_bytes()
assert texto.count(b"MIN_PRICE = 1 ") == 1
settings_copia.write_bytes(texto.replace(b"MIN_PRICE = 1 ", b"MIN_PRICE = 2 "))
assert rules_fingerprint(copias["lf"]) != REGRAS, "numero da loja mudou: regras mudam"
market_copia = OUT / "b5" / "crlf" / "market.py"
market_copia.write_bytes(market_copia.read_bytes() + b"# comentario novo\r\n")
assert rules_fingerprint(copias["crlf"]) != REGRAS, "codigo do sorteio mudou: regras mudam"
print("5 ok: regras iguais com CRLF ou LF; mudam com um numero da loja ou com o codigo do sorteio",
      flush=True)


# ================== 6. a linha de comando
c1 = OUT / "c1"
p = roda("simulate_seed.py", "--seed", 42, "--out", c1)
assert p.returncode == 0, p.stderr
assert p.stdout.startswith(f"semente 42 | 121 dias | regras {REGRAS}"), p.stdout
assert "pygame" not in p.stdout and "promocoes:" in p.stdout, p.stdout
assert str(ScenarioStore(c1).seed_file(42)) in p.stdout
assert ScenarioStore(c1).seed_file(42).read_bytes() == store2.seed_file(42).read_bytes()
p = roda("simulate_seed.py", "--seed", 42, "--out", c1)                 # sempre simula de novo
assert p.returncode == 0, p.stderr
p = roda("simulate_seed.py", "--days", 15, "--out", c1, env={**os.environ, "FARM_SEED": "7"})
assert p.returncode == 0 and p.stdout.startswith("semente 7 | 15 dias"), p.stdout
execucoes = rows(c1 / "execucoes.csv")
assert [(e["script"], e["sementes"], e["novas"], e["refeitas"]) for e in execucoes] == [
    ("simulate_seed", "42", "1", "0"), ("simulate_seed", "42", "0", "1"),
    ("simulate_seed", "7", "1", "0")]

for nome, processos in (("c2", 1), ("c3", 4)):
    p = roda("simulate_range.py", "--from", 1, "--to", 300, "--workers", processos,
             "--out", OUT / nome)
    assert p.returncode == 0, p.stderr
    assert f"300 sementes em" in p.stdout and f"{processos} processo(s)" in p.stdout, p.stdout
    assert "300 novas, 0 refeitas, 0 puladas" in p.stdout and "media:" in p.stdout, p.stdout
for semente in range(1, 301):
    assert ((OUT / "c2" / "sementes" / f"semente_{semente}.csv").read_bytes()
            == (OUT / "c3" / "sementes" / f"semente_{semente}.csv").read_bytes()), semente
sequencial, paralelo = ScenarioStore(OUT / "c2").load_summary(), ScenarioStore(OUT / "c3").load_summary()
metricas = [k for k in SUMMARY_HEADER if k not in ("execucao", "simulado_em", "ms")]
assert list(sequencial) == list(paralelo) == list(range(1, 301))
assert all({k: sequencial[s][k] for k in metricas} == {k: paralelo[s][k] for k in metricas}
           for s in sequencial)
p = roda("simulate_range.py", "--from", 1, "--to", 300, "--workers", 4, "--out", OUT / "c3")
assert p.returncode == 0 and "0 novas, 0 refeitas, 300 puladas" in p.stdout, p.stdout
assert rows(OUT / "c3" / "execucoes.csv")[-1]["processos"] == "1", "nada a simular: sem pool"

for argumentos in (("--from", 10, "--to", 5), ("--from", 1, "--to", settings.MAX_SEEDS + 1),
                   ("--from", 1, "--to", 5, "--days", 0), ("--from", 1, "--to", 5, "--workers", 0),
                   ("--from", 1)):
    p = roda("simulate_range.py", *argumentos, "--out", OUT / "c4")
    assert p.returncode == 2, (argumentos, p.returncode, p.stderr)
p = roda("simulate_seed.py", "--seed", 1, "--days", 0, "--out", OUT / "c4")
assert p.returncode == 2, p.stderr
assert not (OUT / "c4").exists(), "argumento invalido nao grava nada"
assert cenarios_reais() == CENARIOS_REAIS_ANTES, "a suite mexeu no cenarios/ do projeto"
print("6 ok: simulate_seed.py (sempre simula; FARM_SEED sem --seed); simulate_range.py com 4 "
      "processos = com 1, byte a byte; 2a execucao pula tudo; argumento invalido sai com 2; "
      "cenarios/ do projeto intocado", flush=True)


# ================== 7. Ctrl+C no meio grava o que terminou
out7 = OUT / "b7"


def para_depois_do_primeiro_lote(feitas, total):
    if feitas >= settings.CHUNK_SEEDS:
        raise KeyboardInterrupt


r = run_batch(range(1, 201), days=20, workers=1, out_dir=out7, progress=para_depois_do_primeiro_lote)
assert r.interrupted == INTERRUPTED and len(r.new) == settings.CHUNK_SEEDS
assert r.pending == 200 - settings.CHUNK_SEEDS
assert sorted(ScenarioStore(out7).load_summary()) == list(range(1, settings.CHUNK_SEEDS + 1))
assert rows(out7 / "execucoes.csv")[-1]["interrompida"] == INTERRUPTED
r = run_batch(range(1, 201), days=20, workers=1, out_dir=out7)
assert contagem(r) == (200 - settings.CHUNK_SEEDS, 0, settings.CHUNK_SEEDS) and not r.interrupted

out7p = OUT / "b7p"                                  # agora com o pool aberto, num processo novo
p = roda(Path("tests") / "run_interrompe.py", out7p, 4)
assert p.returncode == 0, p.stderr
_, motivo, processos, novas, pendentes = p.stdout.split()
assert (motivo, processos, novas) == (INTERRUPTED, "4", str(settings.CHUNK_SEEDS)), p.stdout
assert int(pendentes) == 2000 - settings.CHUNK_SEEDS
assert len(ScenarioStore(out7p).load_summary()) == settings.CHUNK_SEEDS
execucao = rows(out7p / "execucoes.csv")[-1]
assert (execucao["interrompida"], execucao["processos"]) == (INTERRUPTED, "4")
p = roda("simulate_range.py", "--from", 1, "--to", 2000, "--days", 20, "--workers", 4,
         "--out", out7p)
assert p.returncode == 0, p.stderr
assert f"{2000 - settings.CHUNK_SEEDS} novas, 0 refeitas, {settings.CHUNK_SEEDS} puladas" in p.stdout
assert len(ScenarioStore(out7p).load_summary()) == 2000
assert not list(out7p.rglob("*.tmp"))
print("7 ok: Ctrl+C (sem e com o pool) grava o que terminou e marca a execucao; a proxima "
      "execucao completa o resto", flush=True)

print("\nTUDO OK")
