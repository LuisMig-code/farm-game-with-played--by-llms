"""Suite do agente LLM: sem rede, sem credito, com um cliente LLM falso.

    venv/Scripts/python.exe tests/check_llm.py            # pasta temporaria nova
    venv/Scripts/python.exe tests/check_llm.py <pasta>    # pasta nova ou vazia

Sao 20 blocos em sequencia (um bloco usa o que os anteriores importaram), cada
um imprime "N ok: ..." e o fim e "TUDO OK". Leva ~8 min: varios blocos rodam
partidas de verdade com video. Um assert que falha para tudo com o traceback.

A pasta de saida recebe as runs, os logs e os videos dos testes; o logs/ e o
runs_llm/ do projeto nao sao tocados. O bloco 19 mata um processo com taskkill e
so roda no Windows.
"""
import csv
import json
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.WARNING)

from fake_llm import FakeClient, padrao_dia, padrao_estrategia
from farm import settings as game_settings
from farm.crops import COIN, FERTILIZER, seed_key
from farm.game import State
from llm_agent import facts, responses, settings, templates
from llm_agent.executor import (CONTEXT, GRAMMAR, OK, PARTIAL, RESOURCE, STAMINA_PARTS, TRUNCATED,
                                Executor)
from llm_agent.grammar import GrammarError, parse
from llm_agent.openrouter import OpenRouterClient
from llm_agent.runner import LLMRun
from scripting import HOUSE, Session, shortest_path

# Pasta de saida: uma temporaria nova, ou a passada na linha de comando, que
# precisa estar vazia -- a suite nunca apaga nada. Caminho curto por causa do
# limite de 260 caracteres do Windows.
if len(sys.argv) > 1:
    OUT = Path(sys.argv[1])
    if OUT.exists() and any(OUT.iterdir()):
        sys.exit(f"{OUT} nao esta vazia: passe uma pasta nova ou vazia (a suite nao apaga nada)")
else:
    OUT = Path(tempfile.mkdtemp(prefix="llmt_"))
print(f"saida da suite: {OUT}", flush=True)
game_settings.LOGS_DIR = OUT / "logs_jogo"
LOGS_REAIS = Path(ROOT) / "logs"


def logs_reais():
    """O que ha no logs/ do projeto (um clone novo pode nem ter a pasta)."""
    return sorted(p.name for p in LOGS_REAIS.iterdir()) if LOGS_REAIS.is_dir() else []


LOGS_REAIS_ANTES = logs_reais()


def rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ler(pasta, rel):
    return (pasta / rel).read_text(encoding="utf-8")


def planos(mapa, estrategia=None):
    def script(kind, day, messages, attempt):
        if kind == "estrategia":
            return estrategia or padrao_estrategia()
        return padrao_dia(mapa.get(day, []))
    return script


def run(script, days, **kw):
    kw.setdefault("video", False)
    kw.setdefault("seed", 42)
    cliente = kw.pop("client", None) or FakeClient(script, timeout=kw.pop("fake_timeout", 5.0))
    kw.setdefault("game_logs_dir", OUT / "logs_ia")
    r = LLMRun(days=days, client=cliente, runs_dir=OUT / "runs", **kw)
    resumo = r.run()
    return r, resumo, OUT / "runs" / resumo["pasta"], cliente


def codigos(execucao):
    return [r.code for r in execucao.results]


# ============================================================ 1. gramática
validas = ["IR loja", "ir canteiro_esquerdo", "COLHER", "COLHER TUDO", "COLHER 3",
           "COLHER LIMITE 3", "PLANTAR trigo", "PLANTAR trigo TUDO", "PLANTAR trigo 5",
           "PLANTAR batata LIMITE 4", "FERTILIZAR", "FERTILIZAR TUDO", "FERTILIZAR 2",
           "FERTILIZAR LIMITE 2", "LIMPAR", "LIMPAR TUDO", "LIMPAR 1", "LIMPAR LIMITE 1",
           "COMPRAR trigo 12", "COMPRAR trigo LIMITE 12", "COMPRAR fertilizante 1",
           "VENDER melancia", "VENDER melancia TUDO", "VENDER trigo 3", "VENDER trigo LIMITE 3",
           "plantar Melancia 12", "colher limite 3"]
for linha in validas:
    parse(linha)
assert parse("COMPRAR trigo 12").item == "semente trigo"
assert parse("COMPRAR fertilizante 2").item == FERTILIZER
assert parse("PLANTAR batata LIMITE 4").limit == 4 and parse("COLHER").all_


def campos(linha):                          # a mesma coisa escrita de dois jeitos
    c = parse(linha)
    return c.verb, c.crop, c.item, c.limit, c.amount, c.all_


for a, b in (("PLANTAR trigo 5", "PLANTAR trigo LIMITE 5"),
             ("PLANTAR trigo", "PLANTAR trigo TUDO"),
             ("COLHER 3", "COLHER LIMITE 3"),
             ("FERTILIZAR 2", "FERTILIZAR LIMITE 2"),
             ("LIMPAR 1", "LIMPAR LIMITE 1"),
             ("VENDER trigo 3", "VENDER trigo LIMITE 3"),
             ("VENDER trigo", "VENDER trigo TUDO"),
             ("COMPRAR trigo 12", "COMPRAR trigo LIMITE 12")):
    assert campos(a) == campos(b), (a, b, campos(a), campos(b))
assert campos("PLANTAR trigo 5") == ("PLANTAR", "trigo", None, 5, None, False), campos("PLANTAR trigo 5")
assert parse("COLHER 3").limit == 3 and parse("VENDER trigo 3").amount == 3
invalidas = ["DORMIR", "MOVER cima", "IR", "IR praia", "COLHER trigo", "COLHER LIMITE", "COLHER 3 4",
             "PLANTAR", "PLANTAR trigo 0", "PLANTAR trigo cinco", "PLANTAR abacaxi TUDO",
             "COMPRAR semente_trigo 2", "COMPRAR trigo 0", "COMPRAR trigo", "COMPRAR trigo TUDO",
             "COMPRAR", "VENDER", "", 42]
for linha in invalidas:
    try:
        parse(linha)
        raise AssertionError(f"aceitou {linha!r}")
    except GrammarError:
        pass
print(f"1 ok: um quantificador só — LIMITE opcional em todo verbo, TUDO (ou nada) no campo, número "
      f"obrigatório no COMPRAR: {len(validas)} aceitos, {len(invalidas)} recusados")

# ============================================================ 2. templates .md
for caminho in (settings.PROMPT_STRATEGY, settings.PROMPT_DAY):
    system, user = templates.load(caminho)
    assert system and user
tmp = OUT / "tpl"
tmp.mkdir(parents=True, exist_ok=True)
teste = tmp / "t.md"
teste.write_text('# SYSTEM\nSou {NOME}.\n\n# USER\nJSON: {"a": 1} e {"chave": "{NOME}"}\n',
                 encoding="utf-8")
p = templates.render(teste, {"NOME": "X"})
assert p.system == "Sou X." and p.user == 'JSON: {"a": 1} e {"chave": "X"}', p.user
teste.write_text("# SYSTEM\nSou {NOVO_CAMPO}.\n# USER\nok\n", encoding="utf-8")
try:
    templates.render(teste, {"NOME": "X"})
    raise AssertionError("placeholder desconhecido passou")
except templates.TemplateError:
    pass
teste.write_text("# USER\nsem system\n", encoding="utf-8")
try:
    templates.load(teste)
    raise AssertionError("arquivo sem SYSTEM passou")
except templates.TemplateError:
    pass
print("2 ok: .md separa SYSTEM/USER, preenche só {MAIUSCULAS}, preserva o JSON e recusa "
      "placeholder desconhecido")

# ================================================================= 3. fatos
assert facts.last_planting_day("trigo", 1, 30) == 23               # 7 dias
assert facts.last_planting_day("melancia", 1, 30, True) == 24      # 9 - 3
assert facts.last_planting_day("cenoura", 85, 121) == 87           # outono +1, virada no 91
assert facts.last_planting_day("cenoura", 85, 121, True) == 88
assert facts.last_planting_day("melancia", 85, 121) is None        # não fecha antes do inverno
assert facts.last_planting_day("trigo", 29, 30) is None
bloco, inviaveis = facts.deadline_block(29, 30)
assert "trigo" in inviaveis and "melancia" in inviaveis and "cenoura" not in inviaveis, inviaveis

s = Session(seed=42, realtime=False)
g = s.game
g.field.plant((6, 8), "trigo", day=1)
g.field.plant((6, 7), "cenoura", day=1)
g.field.fertilize((6, 7))
g.field.plant((5, 8), "cenoura", day=1)
g.field.fertilize((5, 8))
g.field.plant((7, 8), "batata", day=1)
g.field.plant((8, 8), "cenoura", day=-10)
g.day = 5
livres, texto = facts.plot_zone(g, "canteiro_esquerdo")
assert livres == 44, livres
assert "2 prontas (fertilizadas), apodrecem em 2 dias" in texto, texto
assert "1 pronta, apodrece em 2 dias" in texto, texto
assert "1 crescendo, pronta em 3 dias" in texto, texto
assert "PODRES (LIMPAR para liberar): cenoura 1" in texto, texto
promo = next((i for i in g.market.promos if i.startswith("semente")), None)
tabela = facts.crop_table(g, g.day)
if promo:
    cultura = promo.split(" ", 1)[1]
    linha = next(l for l in tabela.splitlines() if l.strip().startswith(cultura))
    assert f"{g.market.buy_price(promo):>10}" in linha, (linha, g.market.buy_price(promo))
s.close()
print(f"3 ok: prazo por cultivo (inclusive atravessando o inverno), canteiros com concordância, "
      f"tabela com o preço do dia{' (promo ' + promo + ')' if promo else ''}")

# ================================================= 4. códigos do interpretador
s = Session(seed=42, realtime=False)
g = s.game
ex = Executor(s)


def dia_de(plano, coins=None):
    if coins is not None:
        g.inventory._counts[COIN] = coins
    g.player.restore()                 # cada "dia" do teste comeca com a estamina cheia
    d = ex.run(plano)
    ex.go_home(d)
    return d


d = dia_de(["IR loja", "VOAR para longe", "IR cama"])
assert codigos(d) == [OK, GRAMMAR, OK], codigos(d)
assert d.results[0].detail == "6 passos", d.results[0].detail
assert "não existe" in d.results[1].detail

d = dia_de(["COLHER", "IR canteiro_esquerdo", "VENDER trigo TUDO", "COMPRAR trigo 1"])
assert codigos(d) == [CONTEXT, OK, CONTEXT, CONTEXT], codigos(d)
assert "exige estar num canteiro; você estava em cama" in d.results[0].detail

d = dia_de(["IR loja", "COMPRAR trigo 1", "VENDER trigo TUDO", "IR canteiro_esquerdo", "COLHER",
            "LIMPAR", "FERTILIZAR"], coins=0)
assert codigos(d) == [OK, RESOURCE, RESOURCE, OK, RESOURCE, RESOURCE, RESOURCE], codigos(d)
assert "não comprou nenhuma" in d.results[1].detail and "0 unidades de trigo" in d.results[2].detail
assert "nada pronto para colher" in d.results[4].detail

d = dia_de(["IR canteiro_esquerdo", "PLANTAR trigo TUDO", "PLANTAR trigo LIMITE 2"])
assert codigos(d) == [OK, OK, RESOURCE], (codigos(d), [r.detail for r in d.results])
assert d.results[1].detail == "1 de 49 células livres", d.results[1].detail
assert d.results[2].detail == "0 sementes de trigo"

g.inventory._counts[seed_key("batata")] = 5                 # PLANTAR <cultivo> <n> = LIMITE <n>
d = dia_de(["IR canteiro_esquerdo", "PLANTAR batata 2", "PLANTAR batata LIMITE 2", "PLANTAR batata 9"])
assert codigos(d) == [OK, OK, OK, OK], [(r.code, r.detail) for r in d.results]
assert [r.effective for r in d.results[1:]] == [2, 2, 1], [(r.requested, r.effective) for r in d.results]
assert g.inventory.count(seed_key("batata")) == 0

# COLHER: LIMITE e opcional e TUDO vale por ele, igual ao PLANTAR
g.field.plots.clear()
canteiro = [c for c in sorted(g.zones.plantable) if c[0] < 20][:6]
for cell in canteiro:
    g.field.plant(cell, "cenoura", day=g.day)
g.day += facts.grow_days("cenoura", g.day)
d = dia_de(["IR canteiro_esquerdo", "COLHER 2", "COLHER LIMITE 2", "COLHER TUDO"])
assert codigos(d) == [OK, OK, OK, OK], [(r.code, r.detail) for r in d.results]
assert [r.effective for r in d.results[1:]] == [2, 2, 2], [r.effective for r in d.results]
g.day = 5

# o cultivo com mais estoque hoje, para o corte ser pelas moedas e nao pelo estoque
farto = max(("batata", "cenoura", "beterraba", "trigo", "melancia"),
            key=lambda c: g.market.stock_left(seed_key(c)))
assert g.market.stock_left(seed_key(farto)) >= 10, farto
preco = g.market.buy_price(seed_key(farto))
d = dia_de(["IR loja", f"COMPRAR {farto} 10"], coins=preco * 3)
assert codigos(d) == [OK, PARTIAL], [(r.code, r.detail) for r in d.results]
assert d.results[1].effective == 3 and "comprou 3 de 10" in d.results[1].detail, d.results[1].detail
assert "não pagam mais uma" in d.results[1].detail, d.results[1].detail

g.inventory._counts[seed_key("cenoura")] = 5
g.inventory._counts[FERTILIZER] = 9
g.fertilizers_today = 1
d = dia_de(["IR canteiro_esquerdo", "PLANTAR cenoura TUDO", "FERTILIZAR"])
assert codigos(d) == [OK, OK, PARTIAL], [(r.code, r.detail) for r in d.results]
# 2 aplicacoes (1 ja usada hoje); o total de elegiveis inclui o trigo plantado antes no teste
assert d.results[2].effective == 2 and d.results[2].detail.startswith("fertilizou 2 de ")
assert d.results[2].detail.endswith(": limite de 3 fertilizantes por dia já usado"), d.results[2].detail

g.day = 95                                                  # inverno
d = dia_de(["IR canteiro_esquerdo", "PLANTAR cenoura TUDO", "FERTILIZAR"])
assert codigos(d) == [OK, CONTEXT, CONTEXT], codigos(d)
assert "não se planta no inverno" in d.results[1].detail
g.day = 5

d = dia_de(["IR canteiro_direito", "IR loja", "IR canteiro_esquerdo"])
gasto = d.stamina_start - d.stamina_at_bed
assert sum(d.stamina_parts[p] for p in STAMINA_PARTS) == gasto, (dict(d.stamina_parts), gasto)
assert d.plot_zones_visited == {"canteiro_direito", "canteiro_esquerdo"}

d = ex.run("IR loja")                                       # plano que não é lista
assert codigos(d) == [GRAMMAR]
s.close()
print("4 ok: OK, PARCIAL, ERRO_GRAMATICA (linha descartada, o resto roda), ERRO_CONTEXTO "
      "(zona e inverno), ERRO_RECURSO; COLHER 2 = COLHER LIMITE 2 e COLHER TUDO = COLHER no "
      "executor; decomposição da stamina fecha com o gasto")

# ============================================= 5. rede de segurança de stamina
s = Session(seed=42, realtime=False)
ex = Executor(s)
ENTRADA = (6, 8)
ida = ex.home_distance(ENTRADA)
justo = ida + game_settings.STAMINA_PLANT + ida + settings.STAMINA_RESERVE
s.game.player.stamina = justo
d = ex.run(["IR canteiro_esquerdo", "PLANTAR batata LIMITE 1"])
ex.go_home(d)
assert codigos(d) == [OK, OK] and s.stamina == 1 and not s.over, (codigos(d), s.stamina)
s.sleep()
s.game.player.stamina = justo - 1
s.game.field.plots.pop((6, 8), None)
s.game.inventory.add(seed_key("batata"))
d = ex.run(["IR canteiro_esquerdo", "PLANTAR batata LIMITE 1", "IR loja"])
ex.go_home(d)
assert codigos(d) == [OK, TRUNCATED, TRUNCATED], codigos(d)
# ja na entrada do canteiro: plantar 2 + voltar + reserva, e havia 1 a menos
na_entrada = game_settings.STAMINA_PLANT + ida + settings.STAMINA_RESERVE
assert "a próxima exigia" in d.results[1].detail and d.results[1].stamina_needed == na_entrada, d.results[1]
assert d.results[1].stamina_before == na_entrada - 1, d.results[1]
assert d.results[2].detail == "descartado: o plano já tinha sido cortado"
assert d.truncated and s.stamina >= 1 and not s.over
s.close()
s = Session(seed=42, realtime=False)
s.game.player.stamina = 0
s.tick()
assert s.game.state is State.GAME_OVER
s.close()

rng = random.Random(7)
CAMPO = ["COLHER", "LIMPAR", "FERTILIZAR", "PLANTAR cenoura TUDO", "PLANTAR batata TUDO",
         "PLANTAR trigo TUDO"]
LOJA = ["VENDER cenoura TUDO", "VENDER batata TUDO", "COMPRAR cenoura 1"]


def aleatorio(kind, day, messages, attempt):
    if kind == "estrategia":
        return padrao_estrategia("caos")
    plano = []
    for _ in range(rng.randint(7, 12)):
        zona = rng.choice(["canteiro_esquerdo", "canteiro_direito"]) if rng.random() < 0.85 else "loja"
        plano.append(f"IR {zona}")
        plano += rng.sample(CAMPO if zona != "loja" else LOJA, rng.randint(0, 2))
    if rng.random() < 0.3:
        plano.insert(rng.randrange(len(plano)), "DORMIR agora")
    return padrao_dia(plano)


agente, resumo, pasta, _ = run(aleatorio, days=10, seed=99)
truncados = sum(int(l["truncado"]) for l in rows(pasta / "dias.csv"))
assert truncados >= 5, truncados
assert all(int(l["estamina_sobrando"]) >= 1 for l in rows(pasta / "dias.csv"))
jogo = next((pasta / "jogo").glob("run_*.csv"))
assert not any(l["acao"] == "derrota" for l in rows(jogo)) and not agente.session.over
print(f"5 ok: com {justo} o plano fecha e chega com 1; com {justo - 1} vira TRUNCADO_STAMINA; "
      f"10 dias aleatórios com {truncados} truncados e nenhuma derrota")

# ================================ 6. feedback no formato e dia seguinte o recebe
mapa = {1: ["IR loja", "COMPRAR trigo 99", "IR canteiro_esquerdo", "PLANTAR cenoura TUDO",
            "BOBAGEM total", "VENDER cenoura TUDO"]}
agente, resumo, pasta, cliente = run(planos(mapa), days=2)
fb = ler(pasta, "dias/dia_001/feedback.txt")
linhas = fb.splitlines()
assert linhas[0] == "DIA 1 — executado", linhas[0]
assert re.match(r"\[1\] IR loja\s+OK \(6 passos\)$", linhas[1]), linhas[1]
assert re.match(r"\[2\] COMPRAR trigo 99\s+ERRO_RECURSO: não comprou nenhuma", linhas[2]), linhas[2]
assert re.match(r"\[4\] PLANTAR cenoura TUDO\s+OK \(1 de 49 células livres\)$", linhas[4]), linhas[4]
assert re.match(r"\[5\] BOBAGEM total\s+ERRO_GRAMATICA: verbo 'BOBAGEM' não existe", linhas[5]), linhas[5]
assert re.match(r"\[6\] VENDER cenoura TUDO\s+ERRO_CONTEXTO: VENDER exige estar na loja", linhas[6]), linhas[6]
assert re.match(r"\[--\] volta para a cama\s+OK \(17 passos\)$", linhas[7]), linhas[7]
m = re.match(r"stamina: 160 -> (\d+)   \(andando (\d+) \| plantando (\d+) \| colhendo (\d+) \| "
             r"fertilizando (\d+) \| limpando (\d+)\)$", linhas[8])
assert m, linhas[8]
fim, *partes = map(int, m.groups())
assert sum(partes) == 160 - fim, (partes, fim)
dia2 = next(c for c in cliente.calls if c["day"] == 2)["messages"][1]["content"]
assert fb.strip() in dia2, "o feedback de ontem não chegou inteiro no prompt do dia 2"
assert len([c for c in cliente.calls if c["day"] == 1]) == 1, "pediu reenvio do plano com erro"
assert rows(pasta / "erros_gramatica.csv")[0]["comando"] == "BOBAGEM total"
print("6 ok: feedback no formato do Projeto Fazenda, com a decomposição da stamina; chega inteiro "
      "no dia seguinte; plano com erro não gera reenvio")

# ======================================== 7. diário de 5 dias e conhecimento
def memoria(kind, day, messages, attempt):
    if kind == "estrategia":
        return padrao_estrategia()
    conhecimento = [f"lição do dia {day}"] + [f"linha {i}" for i in range(20 if day == 3 else 2)]
    return padrao_dia(["IR loja"], conhecimento=conhecimento, leitura=f"LEITURA_DIA_{day}")


agente, resumo, pasta, cliente = run(memoria, days=8)
p8 = next(c for c in cliente.calls if c["day"] == 8)["messages"][1]["content"]
diario = p8.split("## DIÁRIO", 1)[1].split("## SEU CONHECIMENTO", 1)[0]
assert [f"dia {d} " in diario for d in range(1, 8)] == [False, False, True, True, True, True, True], diario
assert "LEITURA_DIA_7" in diario and "LEITURA_DIA_2" not in diario
conh = p8.split("## SEU CONHECIMENTO ACUMULADO", 1)[1].split("## GRAMÁTICA", 1)[0]
assert "- lição do dia 7" in conh and "lição do dia 6" not in conh, conh

p4 = next(c for c in cliente.calls if c["day"] == 4)["messages"][1]["content"]
assert "3 foram cortadas" not in p4                       # 21 linhas -> 15, cortadas 6
assert "6 foram cortadas" in p4, p4.split("## O QUE ACONTECEU ONTEM", 1)[1][:600]
rel3 = json.loads(ler(pasta, "dias/dia_003/relatorio.json"))
assert rel3["conhecimento"]["linhas"] == 15 and rel3["conhecimento"]["cortadas"] == 6, rel3["conhecimento"]

_, _, pasta_sm, cliente_sm = run(memoria, days=2, mode="sem_memoria")
p2 = next(c for c in cliente_sm.calls if c["day"] == 2)["messages"][1]["content"]
assert "lição do dia 1" not in p2 and "modo sem memória" in p2
print("7 ok: diário com só os últimos 5 dias; conhecimento reescrito inteiro e reinjetado; teto de "
      "15 linhas com corte avisado; sem_memoria não reinjeta")

# ================== 8. estratégia: bullets, teto de caracteres e só ela reinjetada
TETO = settings.STRATEGY_MAX_CHARS
longa = ["X" * (TETO + 12)]
BULLETS = ["Trigo no esquerdo, melancia no direito",
           "Vender no máximo 5 por dia, alternando o cultivo",
           "Guardar 60 moedas de caixa; nunca zerar"]
BLOCO = "\n".join(f"- {linha}" for linha in BULLETS)

assert responses.strategy_text(["a", "b"]) == "- a\n- b"
assert responses.strategy_text("- um\n* dois\n\n") == "- um\n- dois"      # texto tambem serve
assert responses.strategy_text("uma linha só") == "- uma linha só"
assert responses.strategy_text(42) == "" and responses.strategy_text([1, "a"]) == "- a"
tres = "\n".join("- " + letra * 100 for letra in "ABC")                  # 308 caracteres
assert responses.fit(tres, TETO) == "\n".join("- " + letra * 100 for letra in "AB")
assert len(responses.fit("- " + "A" * 400, TETO)) == TETO                # bullet único: corta nele


def estrategia_longa(kind, day, messages, attempt):
    if kind == "estrategia":
        return padrao_estrategia(longa if attempt < 3 else BULLETS)
    return padrao_dia([])


base = OUT / "base.txt"
base.write_text("BASE_MARCADOR trigo rende bem", encoding="utf-8")
agente, resumo, pasta, cliente = run(estrategia_longa, days=2, knowledge_path=base)
est = [c for c in cliente.calls if c["kind"] == "estrategia"]
assert len(est) == 3, len(est)
assert f"{TETO + 14} caracteres, contando" in est[1]["messages"][-1]["content"], est[1]["messages"][-1]["content"]
assert f"o máximo é {TETO}" in est[1]["messages"][-1]["content"]
dados = json.loads(ler(pasta, "estrategia/estrategia.json"))
assert dados["estrategia"] == BLOCO and not dados["estrategia_cortada"], dados
dia1 = next(c for c in cliente.calls if c["day"] == 1)["messages"]
assert BLOCO in dia1[1]["content"], dia1[1]["content"]
assert "REGRA_DE_BOLSO_MARCADOR" not in dia1[1]["content"], "regras_de_bolso vazou para o dia"
assert "BASE_MARCADOR" in est[0]["messages"][1]["content"]
assert all("BASE_MARCADOR" not in m["content"] for c in cliente.calls if c["kind"] == "dia"
           for m in c["messages"])


def sempre_longa(kind, day, messages, attempt):
    return padrao_estrategia(longa) if kind == "estrategia" else padrao_dia([])


agente, _, pasta, _ = run(sempre_longa, days=1)
dados = json.loads(ler(pasta, "estrategia/estrategia.json"))
assert dados["estrategia_cortada"] and len(dados["estrategia"]) == TETO, dados
print(f"8 ok: estratégia em bullets (lista ou texto) vira um bloco \"- \" por linha; acima de {TETO} "
      "caracteres, com hífens e quebras, é rejeitada e pedida de novo; esgotadas as tentativas usa a "
      "última cortada em bullets inteiros; só \"estrategia\" é reinjetada; base de conhecimento só "
      "na chamada inicial")

# ======================================= 9. timeout, 504, JSON inválido, 429
def instavel(kind, day, messages, attempt):
    if kind == "estrategia":
        return padrao_estrategia()
    if day == 1:
        return ("http", 429) if attempt == 1 else ("não sei JSON" if attempt == 2 else padrao_dia(["IR loja"]))
    if day == 2:
        return ("sleep", 3.0)
    if day == 3:
        return {"leitura_do_dia": "x", "conhecimento": [], "plano": "IR loja"}   # plano não é lista
    return padrao_dia([])


agente, resumo, pasta, cliente = run(instavel, days=4, fake_timeout=1.0, api_timeout=1.0, retry_wait=0.1)
ch = rows(pasta / "chamadas.csv")
assert [c["status"] for c in ch if c["dia"] == "1"] == ["erro_http", "ok", "ok"], ch
d2 = [c for c in ch if c["dia"] == "2"]
assert len(d2) == 1 and d2[0]["status"] == "timeout", d2
fb2 = ler(pasta, "dias/dia_002/feedback.txt")
assert fb2.startswith("DIA 2 — sem plano") and "não chegou a tempo" in fb2, fb2
assert agente.session.day == 4
d3 = [c for c in ch if c["dia"] == "3"]
assert len(d3) == settings.API_MAX_ATTEMPTS, d3
assert json.loads(ler(pasta, "dias/dia_003/relatorio.json"))["status_llm"] == "json_invalido"
print("9 ok: 429 e JSON inválido repetidos; timeout não repete e o jogador dorme; plano que não é "
      "lista esgota as tentativas e vira dia perdido")

# ============================================== 10. corpo da requisição
cli = OpenRouterClient(model="openai/gpt-5.6-luna", api_key="k", timeout=10)
corpo = cli.body([{"role": "user", "content": "oi"}])
assert "temperature" not in corpo, corpo
assert corpo["response_format"] == {"type": "json_object"}
assert corpo["model"] == settings.MODEL == "openai/gpt-5.6-luna"
cli = OpenRouterClient(model="x", api_key="k", timeout=10, temperature=0.2, reasoning_effort="low",
                       json_output=False)
corpo = cli.body([{"role": "user", "content": "oi"}])
assert corpo["temperature"] == 0.2 and corpo["reasoning"] == {"effort": "low"} and "response_format" not in corpo
agente = LLMRun(days=1, model="deepseek/deepseek-v4.1-flash", reasoning_effort="low",
                runs_dir=OUT / "esforco")                          # cliente real: sem chamar a rede
assert agente.client.body([])["reasoning"] == {"effort": "low"}
assert "reasoning" not in LLMRun(days=1, runs_dir=OUT / "esforco").client.body([])
try:
    LLMRun(days=1, reasoning_effort="max", runs_dir=OUT / "esforco")
    raise AssertionError("aceitou reasoning effort 'max'")
except ValueError:
    pass
for nivel, sufixo, leiame in (("medium", "_gpt-5.6-luna_reasoning-medium_principal_seed42",
                               "| Reasoning effort | medium |"),
                              (None, "_gpt-5.6-luna_principal_seed42",
                               "| Reasoning effort | padrao do provedor |")):
    _, _, pasta, _ = run(planos({}), days=1, reasoning_effort=nivel)
    assert pasta.name.endswith(sufixo), pasta.name
    assert json.loads(ler(pasta, "config.json"))["reasoning_effort"] == nivel
    assert leiame in ler(pasta, "LEIAME.md")
print("10 ok: modelo padrão gpt-5.6-luna; JSON pedido via response_format; temperature só se configurada; "
      "--reasoning-effort chega ao corpo, ao config.json, ao LEIAME e ao nome da pasta")

# ======================================== 11. pastas, CSVs e tempos batendo
mapa = {1: ["IR canteiro_esquerdo", "PLANTAR cenoura TUDO", "PLANTAR batata TUDO"],
        3: ["IR canteiro_esquerdo", "COLHER", "IR loja", "VENDER cenoura TUDO", "PULAR"]}
agente, resumo, pasta, _ = run(planos(mapa), days=3, video=True)
esperados = ["LEIAME.md", "config.json", "agente.log", "chamadas.csv", "comandos.csv", "dias.csv",
             "erros_gramatica.csv", "precos.csv", "transacoes.csv", "conhecimento_final.txt", "video.mp4",
             "prompts/prompt_inicial.md", "prompts/prompt_gaming.md", "estrategia/prompt.txt",
             "estrategia/resposta_1.txt", "estrategia/estrategia.json", "estrategia/chamadas.json"]
for dia in (1, 2, 3):
    esperados += [f"dias/dia_{dia:03d}/{n}" for n in ("prompt.txt", "estado.json", "resposta_1.txt",
                  "resposta.json", "feedback.txt", "relatorio.json", "conhecimento.md", "chamadas.json")]
faltando = [e for e in esperados if not (pasta / e).is_file()]
assert not faltando, faltando
assert not (pasta / "travamentos.log").exists()
comandos = rows(pasta / "comandos.csv")
total = sum(len(json.loads(ler(pasta, f"dias/dia_{d:03d}/relatorio.json"))["comandos"]) for d in (1, 2, 3))
assert len(comandos) == total, (len(comandos), total)
dias = rows(pasta / "dias.csv")
assert int(dias[-1]["moedas_fim"]) == resumo["moedas_fim"] == agente.session.coins > 0
assert rows(pasta / "erros_gramatica.csv")[0]["comando"] == "PULAR"
assert int(resumo["erros_gramatica"]) == 1 and resumo["canteiros_usados"] == "canteiro_esquerdo"
chamadas = rows(pasta / "chamadas.csv")
for dia in (1, 2, 3):
    no_csv = sum(float(c["segundos"]) for c in chamadas if c["dia"] == str(dia))
    assert abs(float(dias[dia - 1]["segundos_llm"]) - no_csv) < 0.2
leiame = ler(pasta, "LEIAME.md")
for pedaco in ("Moedas no fim", "## Estrategia", "Dias truncados", "Plantas no chao no fim", "Custo"):
    assert pedaco in leiame, pedaco
assert leiame.split("## Estrategia", 1)[1].strip().startswith("- "), leiame
assert "OPEN_ROUTER" not in ler(pasta, "agente.log")
ignorado = subprocess.run(["git", "check-ignore", ".env", "runs_llm/x"], cwd=ROOT,
                          capture_output=True, text=True).stdout.split()
assert ignorado == [".env", "runs_llm/x"], ignorado
print(f"11 ok: {len(esperados)} arquivos, templates copiados, comandos.csv = relatórios, moedas e "
      f"tempos batem, ERRO_GRAMATICA guardado, .env ignorado")

# ================================================= 12. determinismo
def sem_tempo(path):
    out = []
    for l in rows(path):
        for coluna in ("segundos_llm", "segundos_maior_chamada", "segundos_execucao"):
            l.pop(coluna, None)
        out.append(l)
    return out


mapa = {1: ["IR loja", "COMPRAR cenoura 2", "IR canteiro_direito", "PLANTAR cenoura TUDO",
            "PLANTAR batata TUDO"],
        3: ["IR canteiro_direito", "COLHER", "IR loja", "VENDER cenoura TUDO"]}
_, r1, p1, _ = run(planos(mapa), days=3, seed=5)
_, r2, p2, _ = run(planos(mapa), days=3, seed=5)
assert (p1 / "comandos.csv").read_bytes() == (p2 / "comandos.csv").read_bytes()
assert sem_tempo(p1 / "dias.csv") == sem_tempo(p2 / "dias.csv")
assert ler(p1, "dias/dia_002/prompt.txt") == ler(p2, "dias/dia_002/prompt.txt")
print("12 ok: mesma semente e mesmo roteiro -> comandos.csv idêntico, mesmos dias e mesmo prompt")

# ============================================ 13. velocidade e loja em lote
from farm.crops import CROPS, ITEM_LIMITS
from farm.spoil_record import CSV_HEADER as SPOILED_HEADER
from scripting import SHOP

MENUS = ("abrir_menu", "cancelar_menu")


def contar_quadros(sessao):
    """Embrulha o _tick da sessao; devolve uma funcao que mede os quadros de um trecho."""
    total, original = [0], sessao._tick

    def tick(direction=(0, 0)):
        total[0] += 1
        return original(direction)

    sessao._tick = tick

    def medir(acao):
        antes = total[0]
        acao()
        return total[0] - antes
    return medir


def linhas_do_jogo(path, sem_menus=False):
    return [(l["dia"], l["acao"], l["de_col"], l["de_lin"], l["para_col"], l["para_lin"], l["item"],
             l["quantidade"], l["preco"], l["estamina"])
            for l in rows(path) if not (sem_menus and l["acao"] in MENUS)]


def roteiro(speed, lote, video):
    s = Session(seed=42, realtime=False, speed=speed, record=video)
    g, medir, q = s.game, contar_quadros(s), {}
    g.inventory.add(seed_key("cenoura"), 5)
    passos = len(shortest_path(s.cell, (6, 8), g.zones.walkable))
    q["andar (por passo)"] = medir(lambda: s.walk_to((6, 8))) / passos
    q["plantar"] = medir(lambda: s.plant("batata"))
    q["fertilizar"] = medir(s.fertilize)
    s.walk_to((6, 7)).plant("cenoura")
    g.field.plant((7, 8), "trigo", day=-20)                     # podre: alvo do limpar
    s.walk_to((7, 8))
    q["limpar"] = medir(s.clear)
    s.walk_to(HOUSE)
    q["dormir"] = medir(s.sleep)
    s.walk_to((6, 8))
    q["colher"] = medir(s.harvest)
    g.inventory.add("batata", 9)
    g.inventory.add(COIN, 60)
    s.walk_to(SHOP)
    farto = max(CROPS, key=lambda c: g.market.stock_left(seed_key(c)))
    n = min(5, g.market.stock_left(seed_key(farto)))
    assert n >= 2, (farto, n)
    if lote:
        q["vender 8"] = medir(lambda: s.sell("batata", 8))
        q[f"comprar {n}"] = medir(lambda: s.buy(seed_key(farto), n))
    else:                                     # como o executor fazia: abre e fecha a cada unidade
        q["vender 8"] = medir(lambda: [s.sell("batata", 1) for _ in range(8)])
        q[f"comprar {n}"] = medir(lambda: [s.buy(seed_key(farto), 1) for _ in range(n)])
    s.walk_to(HOUSE).sleep()
    estado = {"dia": g.day, "estamina": s.stamina, "moedas": s.coins,
              "inventario": dict(g.inventory._counts),
              "campo": {c: (p.crop, p.planted_day, p.fertilized, p.spoiled)
                        for c, p in g.field.plots.items()},
              "loja": (dict(g.market.stock), g.market.budget_left(g.day), dict(g.market.saturation))}
    quadros_video = s.recorder.frames if s.recorder else None
    s.close()
    return q, estado, quadros_video, g.run_log.csv_path


antes_q, antes_e, antes_v, antes_csv = roteiro(1.0, lote=False, video=OUT / "vel_antes.mp4")
lote_q, lote_e, _, lote_csv = roteiro(1.0, lote=True, video=None)
depois_q, depois_e, depois_v, depois_csv = roteiro(settings.GAME_SPEED, lote=True,
                                                  video=OUT / "vel_depois.mp4")
assert antes_e == lote_e == depois_e, (antes_e, lote_e, depois_e)
assert linhas_do_jogo(lote_csv) == linhas_do_jogo(depois_csv), "a velocidade mudou alguma ação"
assert linhas_do_jogo(antes_csv, sem_menus=True) == linhas_do_jogo(lote_csv, sem_menus=True), \
    "a loja em lote mudou alguma compra ou venda"
razoes = {acao: antes_q[acao] / depois_q[acao] for acao in antes_q}
assert all(r >= 1.6 for r in razoes.values()), (razoes, antes_q, depois_q)
assert antes_v / depois_v >= 1.6, (antes_v, depois_v)

for ruim in (0, -1, Session.max_speed() + 0.01):
    try:
        Session(seed=42, realtime=False, speed=ruim)
        raise AssertionError(f"aceitou speed={ruim}")
    except ValueError:
        pass
try:
    LLMRun(days=1, speed=Session.max_speed() + 1, client=FakeClient(planos({})), runs_dir=OUT / "runs")
    raise AssertionError("LLMRun aceitou velocidade acima do teto")
except ValueError:
    pass

s = Session(seed=42, realtime=False, speed=Session.max_speed())      # no teto: 1 célula por quadro
caminho = shortest_path(s.cell, (36, 2), s.game.zones.walkable)
s.walk_to((36, 2))
assert s.cell == (36, 2) and s.stamina == game_settings.STAMINA_MAX - len(caminho), (s.cell, s.stamina)
s.close()
movers = [l for l in rows(s.game.run_log.csv_path) if l["acao"] == "mover"]
assert len(movers) == len(caminho), (len(movers), len(caminho))

mapa = {1: ["IR loja", "COMPRAR cenoura 2", "IR canteiro_direito", "PLANTAR cenoura TUDO",
            "PLANTAR batata TUDO"],
        3: ["IR canteiro_direito", "COLHER", "IR loja", "VENDER cenoura TUDO", "VENDER batata 1"]}
_, _, lento, _ = run(planos(mapa), days=3, seed=5, speed=1.0)
_, _, rapido, _ = run(planos(mapa), days=3, seed=5, speed=settings.GAME_SPEED)
assert (lento / "comandos.csv").read_bytes() == (rapido / "comandos.csv").read_bytes()
assert sem_tempo(lento / "dias.csv") == sem_tempo(rapido / "dias.csv")
assert json.loads(ler(rapido, "config.json"))["velocidade"] == settings.GAME_SPEED
assert f"| Velocidade das acoes | {settings.GAME_SPEED:g}x |" in ler(rapido, "LEIAME.md")
print("13 ok: velocidade " + f"{settings.GAME_SPEED:g}x com a loja em lote -> "
      + ", ".join(f"{a} {r:.2f}x" for a, r in razoes.items())
      + f"; vídeo {antes_v} -> {depois_v} quadros; mesmo estado e mesmas ações; teto sem passo emendado")

# ======================================================= 14. próxima estação
def ns(dia, horizonte=121):
    return facts.next_season_text(dia, horizonte)


t = ns(25)
assert t.startswith("Verão, a partir do dia 31 — daqui a 6 dias. Restrições e mudanças:"), t
assert "validade menor para o que for plantado nela: cenoura 1" in t, t
assert "mantém o crescimento e a validade da estação em que foi plantado" in t, t
t = ns(85)
assert t.startswith("Inverno, a partir do dia 91 — daqui a 6 dias."), t
for pedaco in ("  - NÃO dá para plantar", "TUDO que estiver no chão apodrece: colha até o dia 90",
               "fertilizante NÃO funciona", "trigo x2.5", "caixa da loja 300 moedas por dia"):
    assert pedaco in t, (pedaco, t)
assert t.index("NÃO dá para plantar") < t.index("apodrece") < t.index("fertilizante NÃO"), t
t = ns(90)
assert "a partir de AMANHÃ (dia 91)" in t and "colha HOJE" in t, t
t = ns(25, 30)
assert "depois do fim da partida (dia 30)" in t and "Restrições" not in t, t
t = ns(100)
assert t.startswith("Primavera, a partir do dia 121 — daqui a 21 dias."), t
assert "volta a dar para plantar" in t and "fertilizante volta a funcionar" in t, t
t = ns(55)
assert "crescimento +1 dia para" in t and "validade volta ao normal" in t, t
assert facts.current_season_text(85).startswith("Outono (dia 25 de 30) — crescimento +1 dia"), \
    facts.current_season_text(85)
bloco = facts.seasons_block(121)
assert "Inverno (dias 91 a 120): NÃO dá para plantar; na virada para ela, TUDO" in bloco, bloco
assert "Primavera (dia 121)" in bloco, bloco
from farm import seasons as farm_seasons

for dia in range(1, 121):                                  # o dia do texto é o da virada no jogo
    inicio = dia + farm_seasons.days_to_next(dia)
    assert farm_seasons.season_at(inicio) is not farm_seasons.season_at(dia)
    assert farm_seasons.season_at(inicio - 1) is farm_seasons.season_at(dia)
    assert f"dia {inicio}" in ns(dia), (dia, ns(dia))

s = Session(seed=42, realtime=False)                       # as frases conferidas contra o jogo
g = s.game
g.day = 90
g.field.plant((6, 8), "cenoura", 88)
s.sleep()
assert g.day == 91 and g.field.is_spoiled((6, 8), 91), "a virada do inverno não apodreceu"
g.day = 30
g.field.plant((6, 7), "trigo", 30)
s.sleep()
assert g.field.timing(g.field.at((6, 7))) == (7, 4), g.field.timing(g.field.at((6, 7)))
g.day = 85
valores = facts.day_values(g, horizon=121, strategy="x", feedback="x", diary=[], knowledge=[],
                           memory=True, last_sold={})
user = templates.render(settings.PROMPT_DAY, valores).user
onde = user.split("## ONDE VOCÊ ESTÁ", 1)[1].split("## OS CANTEIROS", 1)[0]
assert "Estação atual: Outono (dia 25 de 30)" in onde and "Próxima estação: Inverno, a partir do dia 91" in onde, onde
assert "colha até o dia 90" in onde, onde
s.close()
print("14 ok: próxima estação em ONDE VOCÊ ESTÁ: dia da virada igual ao do jogo em 120 dias, dias "
      "que faltam, AMANHÃ, depois do fim da partida, restrições do inverno e volta da primavera")

# ========================================================= 15. fertilizante
s = Session(seed=42, realtime=False)
g = s.game
texto = facts.fertilizer_text(g, 121)
for key, c in CROPS.items():
    linha = next(l for l in texto.splitlines() if l.strip().startswith(key + " "))
    dias = "dia" if c.fert_grow_cut == 1 else "dias"
    assert f"-{c.fert_grow_cut} {dias} para crescer, +{c.fert_shelf_bonus} de validade" in linha, linha
for pedaco in ("Só age em planta AINDA CRESCENDO", "1 por planta",
               f"No máximo {game_settings.FERTILIZERS_PER_DAY} por dia; o contador zera ao dormir",
               "NÃO funciona no Inverno", f"custa {game_settings.STAMINA_FERTILIZE} de stamina",
               f"no máximo {ITEM_LIMITS[FERTILIZER]}", "Preço base 21 moedas",
               "FERTILIZAR não escolhe cultivo",
               f"Você tem {g.inventory.count(FERTILIZER)}; o limite de hoje ainda permite usar 3",
               "Funciona hoje. Para de funcionar no dia 91, com o Inverno."):
    assert pedaco in texto, (pedaco, texto)
estoque = g.market.stock_left(FERTILIZER)
assert (f"Na loja: {g.market.buy_price(FERTILIZER)} moedas" in texto and f"estoque {estoque}." in texto
        if estoque else "esgotado hoje" in texto), texto
lucros = {k: g.market.sell_price(k, 1) - g.market.buy_price(seed_key(k)) for k in CROPS}
assert f"lucro/ciclo de uma célula hoje é {max(lucros.values())} moedas" in texto, texto
g.fertilizers_today = 2
assert "ainda permite usar 1." in facts.fertilizer_text(g, 121)
g.day = 100
inverno = facts.fertilizer_text(g, 121)
assert "NÃO funciona hoje (Inverno). Volta a funcionar no dia 121." in inverno, inverno
assert "lucro/ciclo" not in inverno
assert "NÃO funciona hoje (Inverno) nem até o fim da partida." in facts.fertilizer_text(g, 110)
g.day = 1
g.field.plant((6, 8), "trigo", 1)                           # "fica pronta na hora"
g.day = 6
assert not g.field.is_grown((6, 8), 6)
g.field.fertilize((6, 8))
assert g.field.is_grown((6, 8), 6), "o corte não deixou a planta pronta na hora"
g.day = 1
dia1 = templates.render(settings.PROMPT_DAY, facts.day_values(
    g, horizon=121, strategy="x", feedback="x", diary=[], knowledge=[], memory=True, last_sold={})).user
secao = dia1.split("## FERTILIZANTE", 1)[1].split("## O QUE ACONTECEU ONTEM", 1)[0]
assert dia1.index("## O PRAZO") < dia1.index("## FERTILIZANTE") and "Hoje:" in secao, secao
inicial = templates.render(settings.PROMPT_STRATEGY, facts.strategy_values(g, 121, None)).user
fert_inicial = inicial.split("## FERTILIZANTE", 1)[1].split("## AS ESTAÇÕES", 1)[0]
assert "Como funciona:" in fert_inicial and "Restrições:" in fert_inicial and "Hoje:" not in fert_inicial
s.close()
print("15 ok: fertilizante no prompt diário (depois do prazo): cortes e bônus de CROPS, limites, "
      "inverno, preço/estoque/usos de hoje; parte fixa também no prompt inicial")

# ================================================= 16. logs do jogo em logs/
def estraga(kind, day, messages, attempt):                  # cenoura do dia 1 apodrece no dia 6
    if kind == "estrategia":
        return padrao_estrategia()
    return padrao_dia(["IR canteiro_esquerdo", "PLANTAR cenoura TUDO"] if day == 1 else [])


logs_ia = OUT / "logs_16"
shutil.rmtree(logs_ia, ignore_errors=True)
ids, esperados = [], {"IA_gpt-5.6-luna_celulas_estragadas.csv"}
for _ in range(2):
    agente, resumo, pasta, _ = run(estraga, days=6, game_logs_dir=logs_ia)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_gpt-5\.6-luna_principal_seed42(_\d+)?",
                        pasta.name), pasta.name
    run_log = agente.session.game.run_log
    ids.append(run_log.run_id)
    for original in (run_log.text_path, run_log.csv_path):
        assert original.parent == pasta / "jogo" and original.is_file(), original
        copia = logs_ia / f"IA_gpt-5.6-luna_{original.name}"
        esperados.add(copia.name)
        assert copia.read_bytes() == original.read_bytes(), copia
        assert f"`logs_16/IA_gpt-5.6-luna_{original.name}`" in ler(pasta, "LEIAME.md")
    assert (pasta / "jogo" / "celulas_estragadas.csv").is_file()
    assert "logs do jogo copiados para" in ler(pasta, "agente.log")
acumulado = logs_ia / "IA_gpt-5.6-luna_celulas_estragadas.csv"
with open(acumulado, newline="", encoding="utf-8") as f:
    linhas = list(csv.reader(f))
assert tuple(linhas[0]) == SPOILED_HEADER and SPOILED_HEADER not in map(tuple, linhas[1:]), linhas
por_run = Counter(l[1] for l in linhas[1:])
assert por_run[ids[0]] >= 1 and por_run[ids[1]] == por_run[ids[0]], (por_run, ids)
assert {p.name for p in logs_ia.iterdir()} == esperados, (sorted(p.name for p in logs_ia.iterdir()),
                                                        sorted(esperados))
assert logs_reais() == LOGS_REAIS_ANTES, "a suíte mexeu no logs/ real"
print(f"16 ok: logs do jogo copiados para logs/ com IA_gpt-5.6-luna_ (iguais aos de jogo/), estragadas "
      f"acumuladas por modelo ({dict(por_run)}), pasta da run no padrão de sempre, logs/ real intocado")

# ================================================= 17. preços e transações
from farm.crops import BUY_PRICES
from llm_agent.run_logs import PRICES_HEADER, TRANSACTIONS_HEADER
from llm_agent.transactions import TransactionLog
from scripting import Blocked


def resumo_t(ts):
    return [(t.kind, t.item, t.quantity) for t in ts]


s = Session(seed=42, realtime=False, speed=settings.GAME_SPEED)
g = s.game
fechadas = []
TransactionLog(g, fechadas.append)
g.inventory.add("batata", 30)
g.inventory.add("cenoura", 2)
g.inventory.add(COIN, 100)
s.walk_to(SHOP)
s.sell("batata", 5)
s.walk_to(HOUSE).walk_to(SHOP)                               # outra ação no meio
s.sell("batata", 17)
assert resumo_t(fechadas) == [("venda", "batata", 5), ("venda", "batata", 17)], resumo_t(fechadas)
fechadas.clear()
with s.trading("vender") as escolher:                        # uma visita só, itens alternados
    for valor in ("batata", "batata", "cenoura", "batata"):
        escolher(valor)
assert resumo_t(fechadas) == [("venda", "batata", 2), ("venda", "cenoura", 1),
                              ("venda", "batata", 1)], resumo_t(fechadas)
fechadas.clear()
s.sell("batata", 2)
s.sell("batata", 2)                                          # saiu da loja entre as duas
assert resumo_t(fechadas) == [("venda", "batata", 2), ("venda", "batata", 2)], resumo_t(fechadas)
assert all(t.day == 1 and t.price_min == t.price_max == 6 and t.total == 6 * t.quantity for t in fechadas)

fechadas.clear()
farto = max(CROPS, key=lambda c: g.market.stock_left(seed_key(c)))
preco = g.market.buy_price(seed_key(farto))
s.buy(seed_key(farto), 3)
preco_f = g.market.buy_price(FERTILIZER)
s.buy(FERTILIZER, 1)
compra, fert = fechadas
assert (compra.kind, compra.item, compra.quantity, compra.price_min, compra.price_max, compra.total) == \
    ("compra", farto, 3, preco, preco, 3 * preco), compra
assert (fert.kind, fert.item, fert.quantity, fert.total) == ("compra", "fertilizante", 1, preco_f), fert
assert fert.coins_after == s.coins and compra.coins_after == s.coins + preco_f, (compra, fert, s.coins)
g.inventory._counts[COIN] = 0
try:
    s.buy(seed_key(farto), 1)
    raise AssertionError("comprou sem moedas")
except Blocked as erro:                                      # o jogo recusou pelo menu
    assert "recusou" in str(erro), erro
assert len(fechadas) == 2, "tentativa recusada virou transação"
s.close()

s = Session(seed=42, realtime=False, speed=settings.GAME_SPEED)   # saturação: preço cai no meio
g = s.game
fechadas = []
TransactionLog(g, fechadas.append)
g.day = 20
g.inventory.add("batata", 10)
antes = s.coins
s.walk_to(SHOP).sell("batata", 10)
(venda,) = fechadas
assert venda.quantity == 10 and venda.price_min < venda.price_max == 6, venda
assert venda.total == s.coins - antes == venda.coins_after - antes, (venda, s.coins, antes)
s.close()

mapa = {1: ["IR canteiro_esquerdo", "PLANTAR batata TUDO", "PLANTAR cenoura TUDO", "FERTILIZAR"],
        2: ["IR canteiro_esquerdo", "COLHER", "IR loja", "VENDER batata TUDO", "VENDER cenoura 1",
            "COMPRAR cenoura 2", "COMPRAR batata 1", "IR canteiro_esquerdo", "PLANTAR cenoura TUDO",
            "PLANTAR batata TUDO"],
        3: ["IR loja", "VENDER cenoura TUDO", "COMPRAR fertilizante 1"],
        4: ["IR canteiro_esquerdo", "COLHER", "IR loja", "VENDER cenoura TUDO", "VENDER batata TUDO",
            "VENDER batata 1"]}
agente, resumo, pasta, _ = run(planos(mapa), days=5)
with open(pasta / "precos.csv", newline="", encoding="utf-8") as f:
    assert tuple(next(csv.reader(f))) == PRICES_HEADER
precos = rows(pasta / "precos.csv")
assert [int(p["dia"]) for p in precos] == [1, 2, 3, 4, 5], precos
for p in precos:
    estado = json.loads(ler(pasta, f"dias/dia_{int(p['dia']):03d}/estado.json"))
    assert p["estacao"] == estado["estacao"]
    for item in BUY_PRICES:
        assert int(p[f"compra_{item.replace(' ', '_')}"]) == estado["precos_compra"][item], (p, item)
    for crop in CROPS:
        assert int(p[f"venda_{crop}"]) == estado["precos_venda"][crop], (p, crop)

with open(pasta / "transacoes.csv", newline="", encoding="utf-8") as f:
    assert tuple(next(csv.reader(f))) == TRANSACTIONS_HEADER
transacoes = rows(pasta / "transacoes.csv")
assert transacoes and all(int(t["quantidade"]) > 0 for t in transacoes), transacoes
for d in rows(pasta / "dias.csv"):                           # só a loja mexe nas moedas
    do_dia = [t for t in transacoes if t["dia"] == d["dia"]]
    saldo = sum(int(t["total_moedas"]) * (1 if t["tipo"] == "venda" else -1) for t in do_dia)
    assert saldo == int(d["moedas_fim"]) - int(d["moedas_inicio"]), (d["dia"], saldo, d)
loja = [c for c in rows(pasta / "comandos.csv")
        if c["comando"].startswith(("VENDER", "COMPRAR")) and int(c["efetivo"] or 0) > 0]
assert len(transacoes) == len(loja), (len(transacoes), len(loja))   # cada ordem foi uma visita à loja
jogo = next((pasta / "jogo").glob("run_*.csv"))
unidades, somadas = Counter(), Counter()
for linha in rows(jogo):                                     # o log nativo: uma linha por unidade
    tipo = {"vender": "venda", "comprar": "compra"}.get(linha["acao"])
    if tipo:
        unidades[(linha["dia"], tipo, linha["item"].removeprefix("semente "))] += int(linha["quantidade"])
for t in transacoes:
    somadas[(t["dia"], t["tipo"], t["item"])] += int(t["quantidade"])
assert somadas == unidades, (somadas, unidades)
# depois da última transação ninguém mexe nas moedas
assert int(transacoes[-1]["moedas_depois"]) == resumo["moedas_fim"], (transacoes[-1], resumo["moedas_fim"])
leiame = ler(pasta, "LEIAME.md")
assert "`precos.csv`" in leiame and "`transacoes.csv`" in leiame
print(f"17 ok: transações do jogo (5 e 17 batatas = 2 linhas; itens alternados = 3; loja fechada "
      f"separa; compra de semente e fertilizante; saturação com preço mín < máx); precos.csv = "
      f"estado.json em {len(precos)} dias; {len(transacoes)} transações fecham com as moedas do dia e "
      f"com o log nativo")

# ===================================== 18. saturação: fatos, exemplos e prompts
from farm.market import Market

texto = facts.saturation_text()
for pedaco in (f"a partir do dia {game_settings.SUPPLY_DEMAND_START_DAY}",
               f"vender {game_settings.SUPPLY_DEMAND_DAILY_UNITS} ou mais unidades",
               "ontem E hoje", "até o piso", "alternar cultivos",
               f"devolve {game_settings.SUPPLY_DEMAND_RECOVERY} moeda ao preço"):
    assert pedaco in texto, (pedaco, texto)

m = Market(7)                                  # despejo: o exemplo do prompt x o jogo
precos = []
for _ in range(20):
    precos.append(m.sell_price("melancia", 30))
    m.register_sale("melancia", 30)
assert facts._dump_example("melancia", 20) == (sum(precos), CROPS["melancia"].sell_price * 20)
assert precos[:7] == [CROPS["melancia"].sell_price] * 7 and precos[-1] == CROPS["melancia"].seed_price
assert f"rende {sum(precos)} moedas" in texto, texto

m = Market(7)                                  # repetição: 3 trigos por dia, 3 dias
real = []
for dia in range(20, 23):
    real.append([])
    for _ in range(3):
        real[-1].append(m.sell_price("trigo", dia))
        m.register_sale("trigo", dia)
    m.new_day(dia + 1)
assert facts._streak_example("trigo", 3, 3) == real, (facts._streak_example("trigo", 3, 3), real)
assert " | ".join(" ".join(str(p) for p in dia) for dia in real) in texto, texto
antes = m.sell_price("trigo", 23)              # e um dia parado devolve 1
m.new_day(24)
assert m.sell_price("trigo", 24) == antes + game_settings.SUPPLY_DEMAND_RECOVERY == 8

s = Session(seed=42, realtime=False)
g = s.game
inicial = templates.render(settings.PROMPT_STRATEGY, facts.strategy_values(g, 121, None)).user
assert inicial.index("## A LOJA") < inicial.index("## O MERCADO É DINÂMICO") \
    < inicial.index("## FORMATO DA RESPOSTA"), "a saturação saiu de lugar"
assert texto in inicial and "Saturação: insistir no mesmo cultivo" in inicial
assert '"uso_de_moedas"' in inicial and "um deles PRECISA ser sobre as moedas" in inicial
assert f"MÁXIMO {settings.STRATEGY_MAX_CHARS} CARACTERES" in inicial
assert inicial.count("bullets") >= 2, "a estratégia ainda não é pedida em bullets"

dia = templates.render(settings.PROMPT_DAY, facts.day_values(
    g, horizon=121, strategy=BLOCO, feedback="x", diary=[], knowledge=[], memory=True,
    last_sold={"trigo": 0})).user
loja = dia.split("## A LOJA HOJE", 1)[1].split("## CUSTOS", 1)[0]
assert f"{game_settings.SUPPLY_DEMAND_DAILY_UNITS}+ do mesmo cultivo hoje" in loja, loja
assert "vendido ontem: trigo" in loja and "piso, que é o preço da semente" in loja, loja
gramatica = dia.split("## GRAMÁTICA DO PLANO", 1)[1].split("## FORMATO DA RESPOSTA", 1)[0]
for forma in ("COLHER [TUDO|<n>|LIMITE <n>]", "FERTILIZAR [TUDO|<n>|LIMITE <n>]",
              "LIMPAR [TUDO|<n>|LIMITE <n>]", "PLANTAR <cenoura|batata|beterraba|trigo|melancia> "
              "[TUDO|<n>|LIMITE <n>]", "VENDER <cenoura|batata|beterraba|trigo|melancia> "
              "[TUDO|<n>|LIMITE <n>]", "a palavra LIMITE é opcional"):
    assert forma in gramatica, forma
assert BLOCO in dia, "a estratégia em bullets não chegou ao prompt diário"
s.close()
print("18 ok: saturação no prompt inicial com os dois gatilhos, o piso e os exemplos conferidos "
      "contra o Market; regra curta na loja do dia; gramática nova e estratégia em bullets no "
      "prompt diário")

# ======================================== 19. vídeo de uma run parada no meio
import imageio_ffmpeg
from scripting import recorder as recorder_mod

assert "+empty_moov+default_base_moof" in recorder_mod.FRAGMENTED
assert "-flush_packets" in recorder_mod.FRAGMENTED and "-frag_duration" in recorder_mod.FRAGMENTED
if sys.platform == "win32":                                  # usa taskkill
    FILHO = str(Path(__file__).with_name("run_mata_filho.py"))     # run falsa que trava no dia 4


    def para_run(modo):
        """Roda o agente num processo à parte e para durante a chamada do dia 4."""
        p = subprocess.Popen([sys.executable, FILHO, str(OUT / f"parada_{modo}"), modo],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        for linha in p.stdout:
            if linha.startswith("TRAVOU"):
                _, gravados, pasta = linha.split(" ", 2)
                break
        else:
            raise AssertionError(f"a run ({modo}) não chegou ao dia 4")
        if modo == "mata":
            time.sleep(3)                                            # o modelo "pensando"
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        p.wait(timeout=120)
        pasta = Path(pasta.strip())
        quadros, _ = imageio_ffmpeg.count_frames_and_secs(str(pasta / "video.mp4"))
        return int(gravados), quadros, pasta


    gravados, abre, pasta = para_run("mata")                        # Gerenciador de Tarefas, taskkill /F
    assert gravados - 5 * 30 <= abre < gravados, (gravados, abre)   # só o fim, que estava no encoder
    assert not (pasta / "LEIAME.md").exists(), "morta à força não escreve o LEIAME"
    gravados_c, abre_c, pasta_c = para_run("ctrlc")                 # Ctrl+C: a run fecha normalmente
    assert abre_c == gravados_c, (gravados_c, abre_c)
    assert "interrompida" in ler(pasta_c, "LEIAME.md")
    busca = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-ss", "10", "-i",
                            str(pasta_c / "video.mp4"), "-frames:v", "1", "-f", "null", "-"],
                           capture_output=True, text=True)
    assert busca.returncode == 0 and not busca.stderr.strip(), busca.stderr
    print(f"19 ok: run morta à força no meio da chamada do dia 4 deixa o vídeo abrindo com {abre} de "
          f"{gravados} quadros (perdeu {(gravados - abre) / 30:.1f}s); com Ctrl+C sai inteiro "
          f"({abre_c} de {gravados_c}) e com LEIAME; o MP4 fragmentado aceita busca no meio")
else:
    print("19 pulado: mata o processo com taskkill, so no Windows")

# ================== 20. erro fatal para a run; a chamada inicial insiste pela estratégia
from llm_agent.openrouter import AUTH_ERROR, HTTP_ERROR, NO_CREDITS, CallResult, fatal_status

assert fatal_status(402, "") == NO_CREDITS and fatal_status(401, "") == AUTH_ERROR
assert fatal_status(403, "") == AUTH_ERROR and fatal_status(429, "rate limit") is None
assert fatal_status(400, '{"error": "Insufficient credits for this request"}') == NO_CREDITS
assert fatal_status(504, "gateway timeout") is None                  # continua sendo timeout
assert CallResult(NO_CREDITS, 1).fatal and not CallResult(NO_CREDITS, 1).retryable
assert CallResult(AUTH_ERROR, 1).fatal
assert not CallResult(HTTP_ERROR, 1, http_status=429).fatal and CallResult(HTTP_ERROR, 1, http_status=429).retryable

SEM_SALDO = '{"error":{"code":402,"message":"requires more credits, or fewer max_tokens"}}'


def acaba_credito(kind, day, messages, attempt):
    if kind == "estrategia":
        return padrao_estrategia(["- plantar cenoura e vender"])
    if day >= 3:
        return ("http", 402, SEM_SALDO)
    return padrao_dia(["IR canteiro_esquerdo", "PLANTAR cenoura TUDO"])


agente, resumo, pasta, cliente = run(acaba_credito, days=8, video=True, retry_wait=0.1)
assert resumo["interrompida"].startswith("sem creditos"), resumo["interrompida"]
assert "402" in resumo["interrompida"] and resumo["dias_jogados"] == 2, resumo
assert len([c for c in cliente.calls if c["day"] == 3]) == 1, "repetiu a chamada sem créditos"
assert [int(d["dia"]) for d in rows(pasta / "dias.csv")] == [1, 2]
assert "sem creditos" in ler(pasta, "LEIAME.md")
assert agente.game_logs_published, "os logs do jogo não foram publicados"
assert any(l["pasta"] == pasta.name for l in rows(OUT / "runs" / "resumo.csv"))
quadros, _ = imageio_ffmpeg.count_frames_and_secs(str(pasta / "video.mp4"))
assert quadros > 0, "o vídeo não fechou"


def chave_ruim(kind, day, messages, attempt):
    return ("http", 401, "No auth credentials found")


agente, resumo, pasta, cliente = run(chave_ruim, days=5, video=True, retry_wait=0.1)
assert resumo["interrompida"].startswith("chave recusada"), resumo["interrompida"]
assert resumo["dias_jogados"] == 0 and not rows(pasta / "dias.csv"), resumo
assert len(cliente.calls) == 1, "repetiu com a chave recusada"
assert (pasta / "video.mp4").is_file()          # parou antes de jogar: video existe, sem quadros


def teimosa(kind, day, messages, attempt):                 # só a 8ª tentativa presta
    if kind != "estrategia":
        return padrao_dia([])
    if attempt <= 2:
        return ("sleep", 3.0)                              # timeout: antes, matava a estratégia
    if attempt <= 4:
        return "isto não é JSON"
    if attempt == 5:
        return ("http", 500, "erro do provedor")
    if attempt <= 7:
        return padrao_estrategia(["X" * 400])              # acima do teto
    return padrao_estrategia(["- trigo no esquerdo", "- guardar 50 moedas de caixa"])


agente, resumo, pasta, _ = run(teimosa, days=1, fake_timeout=1.0, api_timeout=1.0, retry_wait=0.05)
dados = json.loads(ler(pasta, "estrategia/estrategia.json"))
assert dados["estrategia"] == "- trigo no esquerdo\n- guardar 50 moedas de caixa", dados
assert not dados["estrategia_cortada"] and not resumo["interrompida"], (dados, resumo)
assert len([c for c in rows(pasta / "chamadas.csv") if c["dia"] == "0"]) == 8
assert resumo["dias_jogados"] == 1


def nunca_responde(kind, day, messages, attempt):
    return ("sleep", 3.0) if kind == "estrategia" else padrao_dia([])


agente, resumo, pasta, cliente = run(nunca_responde, days=5, video=True, fake_timeout=0.5,
                                     api_timeout=0.5, retry_wait=0.05)
assert resumo["interrompida"].startswith("sem estrategia"), resumo["interrompida"]
assert resumo["dias_jogados"] == 0 and not rows(pasta / "dias.csv"), resumo
assert len(cliente.calls) == settings.STRATEGY_MAX_ATTEMPTS, len(cliente.calls)
assert "sem estrategia" in ler(pasta, "LEIAME.md")
assert (pasta / "video.mp4").is_file()


def so_longa(kind, day, messages, attempt):                # nunca cabe no teto: usa cortada
    return padrao_estrategia(["Y" * 400]) if kind == "estrategia" else padrao_dia([])


agente, resumo, pasta, _ = run(so_longa, days=1, retry_wait=0.05)
dados = json.loads(ler(pasta, "estrategia/estrategia.json"))
assert dados["estrategia_cortada"] and len(dados["estrategia"]) == settings.STRATEGY_MAX_CHARS
assert not resumo["interrompida"] and resumo["dias_jogados"] == 1, resumo
print(f"20 ok: 402 e 401/403 param a run na hora e ainda salvam vídeo, logs, LEIAME e resumo.csv; a "
      f"chamada inicial repete até {settings.STRATEGY_MAX_ATTEMPTS} (timeout inclusive) e sai com "
      f"estratégia; sem nenhuma, a run não começa; só longa demais, joga cortada")

print("\nTUDO OK")
