"""Fatos calculados, injetados nos prompts.

Memoria autoescrita compoe erro: se o modelo anotar no dia 4 que beterraba da
prejuizo, acredita nisso para sempre. O antidoto e: tudo que e calculavel, o
codigo calcula e injeta como fato -- lucro por ciclo, pedagio de cada viagem,
celulas livres, prazo por cultivo. O modelo so escreve interpretacao.

Aqui so se le o jogo, nunca se escreve nele.
"""

from collections import Counter, defaultdict
from functools import lru_cache

from farm import seasons, settings as game_settings
from farm.crops import (BUY_PRICES, COIN, CROPS, FERTILIZER, FERTILIZER_PRICE, ITEM_LIMITS,
                        seed_key)
from llm_agent import settings
from llm_agent.grammar import BED, LEFT, PLOT_ZONES, RIGHT, STORE, ZONE_CELLS, plot_zone_of
from scripting import shortest_path

Cell = tuple[int, int]

NAMES = {BED: "cama", STORE: "loja", LEFT: "canteiro_esquerdo", RIGHT: "canteiro_direito"}


# ------------------------------------------------------------------ mapa

@lru_cache(maxsize=None)
def distances(walkable: frozenset) -> dict[tuple[str, str], int]:
    zonas = list(ZONE_CELLS)
    return {(a, b): len(shortest_path(ZONE_CELLS[a], ZONE_CELLS[b], walkable))
            for i, a in enumerate(zonas) for b in zonas[i + 1:]}


def distance_table(walkable: frozenset) -> str:
    d = distances(walkable)
    linhas = []
    for (a, b), passos in d.items():
        ida_volta = f"   (ida e volta {2 * passos})" if a == BED else ""
        linhas.append(f"  {a} -> {b} ".ljust(42, ".") + f" {passos:>2}{ida_volta}")
    return "\n".join(linhas)


def cost_table() -> str:
    g = game_settings
    itens = [("andar 1 célula", g.STAMINA_WALK), ("plantar", g.STAMINA_PLANT),
             ("colher", g.STAMINA_HARVEST), ("fertilizar", g.STAMINA_FERTILIZE),
             ("limpar planta podre", g.STAMINA_CLEAR), ("comprar / vender", 0), ("dormir", 0)]
    return "\n".join(f"  {nome} ".ljust(24, ".") + f" {custo}" for nome, custo in itens)


# -------------------------------------------------------------- cultivos

def grow_days(crop: str, planted_day: int, fertilized: bool = False) -> int:
    c, estacao = CROPS[crop], seasons.season_at(planted_day)
    dias = c.grow_days + estacao.grow_delta
    return max(0, dias - c.fert_grow_cut) if fertilized else dias


def shelf_days(crop: str, planted_day: int, fertilized: bool = False) -> int:
    c, estacao = CROPS[crop], seasons.season_at(planted_day)
    dias = estacao.shelf_days.get(crop, c.shelf_days)
    return dias + c.fert_shelf_bonus if fertilized else dias


def _winter_turn(day: int) -> bool:
    """Neste dia a partida acorda numa estacao sem plantio: tudo no chao apodrece."""
    return day > 1 and not seasons.season_at(day).can_plant and seasons.season_at(day - 1).can_plant


def last_planting_day(crop: str, today: int, horizon: int, fertilized: bool = False) -> int | None:
    """Ultimo dia em que plantar ainda da colheita ate o fim do prazo.

    Considera a estacao do plantio (que congela o prazo), os dias sem plantio e
    a virada para o inverno, que apodrece o que estiver no chao.
    """
    for dia in range(horizon, today - 1, -1):
        if not seasons.season_at(dia).can_plant:
            continue
        pronto = dia + grow_days(crop, dia, fertilized)
        if pronto > horizon:
            continue
        if any(_winter_turn(x) for x in range(dia + 1, pronto + 1)):
            continue
        return dia
    return None


def deadline_block(today: int, horizon: int) -> tuple[str, str]:
    linhas, inviaveis = [], []
    for crop in CROPS:
        normal = last_planting_day(crop, today, horizon)
        fert = last_planting_day(crop, today, horizon, fertilized=True)
        if normal is None and fert is None:
            inviaveis.append(crop)
            continue
        texto = f"plantar até o dia {normal}" if normal is not None else "sem fertilizante, já não dá"
        if fert is not None and fert != normal:
            texto += f" (fertilizada: até o dia {fert})"
        linhas.append(f"  {crop} ".ljust(14, ".") + f" {texto}")
    return ("\n".join(linhas) or "  (nenhum cultivo amadurece mais a tempo)",
            ", ".join(inviaveis) or "nenhum")


def crop_table(game=None, day: int = game_settings.FIRST_DAY) -> str:
    """Tabela de cultivos. Com `game`, usa os precos de hoje; sem, os precos base."""
    cab = "  cultivo     dias  validade  semente  vende  lucro/ciclo  fertilizada"
    linhas = [cab]
    for key, c in CROPS.items():
        if game is None:
            semente, vende = c.seed_price, c.sell_price
        else:
            semente = game.market.buy_price(seed_key(key))
            vende = game.market.sell_price(key, day)
        g, v = grow_days(key, day), shelf_days(key, day)
        gf, vf = grow_days(key, day, True), shelf_days(key, day, True)
        linhas.append(f"  {key:<11}{g:>4}{v:>9}{semente:>10}{vende:>7}{vende - semente:>11}"
                      f"      {gf} dia(s), validade {vf}")
    return "\n".join(linhas)


def fertilizer_text() -> str:
    g = game_settings
    return (f"Custa {FERTILIZER_PRICE} moedas na loja. Numa planta AINDA CRESCENDO, tira dias do\n"
            "crescimento e aumenta a validade (coluna \"fertilizada\" da tabela). Se o corte zerar\n"
            f"o que falta, a planta fica pronta na hora. Máximo {g.FERTILIZERS_PER_DAY} por dia, 1 por "
            f"planta. Carrega-se no máximo {ITEM_LIMITS[FERTILIZER]}. Custa {g.STAMINA_FERTILIZE} de "
            "stamina aplicar.\nNão funciona em planta já pronta, nem no inverno.")


# -------------------------------------------------------------- estacoes

def season_changes(season) -> list[str]:
    mudancas = []
    if season.grow_delta:
        mudancas.append(f"crescimento {season.grow_delta:+d} dia(s) para o que for plantado nela")
    if season.shelf_days:
        mudancas.append("validade menor: " + ", ".join(f"{c} {d}" for c, d in season.shelf_days.items()))
    if not season.can_plant:
        mudancas.append("NÃO dá para plantar")
        mudancas.append("na virada para ela, TUDO que estiver no chão apodrece na hora")
    if not season.fertilizer_works:
        mudancas.append("fertilizante NÃO funciona")
    if season.sell_multiplier:
        mudancas.append("venda multiplicada: " + ", ".join(
            f"{c} x{m:g}" for c, m in season.sell_multiplier.items()))
    if season.daily_budget:
        mudancas.append(f"caixa da loja {season.daily_budget} moedas por dia")
    return mudancas or ["ritmo padrão"]


def seasons_block(horizon: int) -> str:
    """As estacoes que a partida atravessa, com o intervalo de dias de cada uma."""
    trechos, inicio = [], game_settings.FIRST_DAY
    for dia in range(game_settings.FIRST_DAY + 1, horizon + 2):
        if dia > horizon or seasons.season_at(dia) is not seasons.season_at(inicio):
            estacao = seasons.season_at(inicio)
            trechos.append(f"  {estacao.label} (dias {inicio} a {dia - 1}): "
                           + "; ".join(season_changes(estacao)))
            inicio = dia
    return "\n".join(trechos)


def season_line(day: int) -> str:
    atual, proxima = seasons.season_at(day), seasons.season_after(day)
    faltam = seasons.days_to_next(day)
    return (f"{atual.label} ({'; '.join(season_changes(atual))}). Vira {proxima.label} em "
            f"{faltam} dia(s): {'; '.join(season_changes(proxima))}")


# ------------------------------------------------------------------ loja

def shop_rules() -> str:
    g = game_settings
    precos = "  ".join(f"{k} {c.sell_price}" for k, c in CROPS.items())
    compra = "  ".join(f"{k} {c.seed_price}" for k, c in CROPS.items())
    return "\n".join([
        f"Preço base de venda (1 unidade): {precos}",
        f"Preço base da semente:           {compra}   fertilizante {FERTILIZER_PRICE}",
        "- Promoção sorteada todo dia: alguns itens ficam mais baratos naquele dia.",
        "- Estoque diário limitado por item, sorteado todo dia.",
        f"- Caixa: a loja tem {g.MARKET_DAILY_BUDGET} moedas por dia para pagar colheita (mais no "
        "inverno). Sem caixa, ela não compra. Comprar sementes devolve moedas ao caixa.",
        f"- Saturação (a partir do dia {g.SUPPLY_DEMAND_START_DAY}): vender "
        f"{g.SUPPLY_DEMAND_DAILY_UNITS}+ unidades do mesmo cultivo no mesmo dia, ou o mesmo cultivo "
        f"em dois dias seguidos, derruba o preço em {g.SUPPLY_DEMAND_DROP} moeda por unidade, até o "
        f"piso (preço da semente). Cada dia sem vender o cultivo recupera "
        f"{g.SUPPLY_DEMAND_RECOVERY}.",
        f"- Inventário: no máximo {ITEM_LIMITS[seed_key(next(iter(CROPS)))]} sementes de cada tipo "
        f"e {ITEM_LIMITS[FERTILIZER]} fertilizantes. Vegetais e moedas sem limite.",
    ])


def shop_today(game, last_sold: dict[str, int]) -> str:
    loja, day = game.market, game.day
    vende = []
    for key in CROPS:
        preco, base = loja.sell_price(key, day), loja.base_price(key, day)
        vende.append(f"{key} {preco}" + (f" (saturado, base {base})" if preco < base else ""))
    compra = []
    for key in (*CROPS, "fertilizante"):
        item = FERTILIZER if key == "fertilizante" else seed_key(key)
        preco, estoque = loja.buy_price(item), loja.stock_left(item)
        promo = f" PROMO (base {BUY_PRICES[item]})" if loja.is_promo(item) else ""
        compra.append(f"{key} {preco}{promo} [estoque {estoque}]")
    ontem = sorted(k for k, d in last_sold.items() if d == day - 1)
    saturacao = ("ativa" if loja.supply_demand_active(day)
                 else f"desligada até o dia {game_settings.SUPPLY_DEMAND_START_DAY}")
    return "\n".join([
        f"  caixa da loja hoje: {loja.budget_left(day)} moedas",
        "  vende (1 un):  " + " | ".join(vende),
        "  compra:        " + " | ".join(compra[:3]),
        "                 " + " | ".join(compra[3:]),
        f"  saturação: {saturacao} | vendido ontem: {', '.join(ontem) or 'nada'}",
    ])


# --------------------------------------------------------------- canteiros

def plot_zone(game, zona: str) -> tuple[int, str]:
    """(celulas livres, texto das plantacoes) de um canteiro."""
    campo, day = game.field, game.day
    celulas = [c for c in game.zones.plantable if plot_zone_of(c) == zona]
    livres = sum(campo.at(c) is None for c in celulas)
    # cultura -> (estado, dias, fertilizada) -> quantidade
    grupos: dict[str, Counter] = defaultdict(Counter)
    podres = Counter()
    for cell in celulas:
        plot = campo.at(cell)
        if plot is None:
            continue
        if campo.is_spoiled(cell, day):
            podres[plot.crop] += 1
        elif campo.is_grown(cell, day):
            grupos[plot.crop][("pronta", campo.days_left(cell, day), plot.fertilized)] += 1
        else:
            falta = campo.timing(plot)[0] - campo.age(cell, day)
            grupos[plot.crop][("crescendo", falta, plot.fertilized)] += 1

    linhas = []
    for crop, estados in grupos.items():
        partes = [_plot_group(n, *chave) for chave, n in
                  sorted(estados.items(), key=lambda x: (x[0][0] != "pronta", x[0][1]))]
        linhas.append(f"  {crop} x{sum(estados.values())}: " + " | ".join(partes))
    if podres:
        linhas.append("  PODRES (LIMPAR para liberar): "
                      + ", ".join(f"{c} {n}" for c, n in podres.items()))
    return livres, "\n".join(linhas) or "  (vazio)"


def _plot_group(n: int, estado: str, dias: int, fertilizada: bool) -> str:
    plural = n > 1
    quando = "amanhã" if dias == 1 else f"em {dias} dias"
    fert = f" ({'fertilizadas' if plural else 'fertilizada'})" if fertilizada else ""
    if estado == "pronta":
        return (f"{n} {'prontas' if plural else 'pronta'}{fert}, "
                f"{'apodrecem' if plural else 'apodrece'} {quando}")
    return f"{n} crescendo{fert}, {'prontas' if plural else 'pronta'} {quando}"


# ------------------------------------------------------------- inventario

def inventory_lines(game) -> tuple[str, str, str]:
    inv = game.inventory
    colheita = " | ".join(f"{k} {inv.count(k)}" for k in CROPS if inv.count(k)) or "nenhuma"
    teto = ITEM_LIMITS[seed_key(next(iter(CROPS)))]
    sementes = " | ".join(f"{k} {inv.count(seed_key(k))}" for k in CROPS
                          if inv.count(seed_key(k))) or "nenhuma"
    sementes += f"   (máximo {teto} de cada)"
    restantes = max(0, game_settings.FERTILIZERS_PER_DAY - game.fertilizers_today)
    fert = (f"{inv.count(FERTILIZER)} (máximo {ITEM_LIMITS[FERTILIZER]}; "
            f"pode usar {restantes} hoje)")
    return colheita, sementes, fert


# ---------------------------------------------------------- valores prontos

def strategy_values(game, horizon: int, knowledge: str | None) -> dict:
    inv = game.inventory
    iniciais = ", ".join(f"{inv.count(seed_key(k))} semente de {k}" for k in CROPS)
    base = ""
    if knowledge and knowledge.strip():
        base = ("## BASE DE CONHECIMENTO DE PARTIDAS ANTERIORES\n\n"
                "Anotações de partidas passadas. Use o que for útil e confira contra as regras "
                "acima: se contradisser um número, o NÚMERO ganha.\n\n" + knowledge.strip())
    return {
        "DIAS": horizon,
        "MOEDAS_INICIAIS": inv.count(COIN),
        "SEMENTES_INICIAIS": iniciais,
        "FERTILIZANTES_INICIAIS": inv.count(FERTILIZER),
        "STAMINA_MAX": game.player.max_stamina,
        "TABELA_CUSTOS": cost_table(),
        "TABELA_DISTANCIAS": distance_table(game.zones.walkable),
        "TABELA_CULTIVOS": crop_table(),
        "FERTILIZANTE": fertilizer_text(),
        "ESTACOES": seasons_block(horizon),
        "REGRAS_LOJA": shop_rules(),
        "BASE_DE_CONHECIMENTO": base,
        "ESTRATEGIA_MAX": settings.STRATEGY_MAX_CHARS,
    }


def day_values(game, *, horizon: int, strategy: str, feedback: str, diary: list[str],
               knowledge: list[str], memory: bool, last_sold: dict[str, int]) -> dict:
    day = game.day
    colheita, sementes, fert = inventory_lines(game)
    livres_esq, plantios_esq = plot_zone(game, LEFT)
    livres_dir, plantios_dir = plot_zone(game, RIGHT)
    prazo, inviaveis = deadline_block(day, horizon)
    if not memory:
        conhecimento = ("(modo sem memória: o conhecimento chega sempre vazio. Escreva o seu "
                        "mesmo assim.)")
    elif knowledge:
        conhecimento = "\n".join(f"- {linha}" for linha in knowledge)
    else:
        conhecimento = "(vazio: escreva o seu)"
    return {
        "DIAS": horizon, "DIA": day, "DIAS_RESTANTES": horizon - day,
        "ESTRATEGIA": strategy or "(sem estratégia: a chamada inicial não retornou)",
        "ESTACAO": season_line(day),
        "STAMINA": game.player.stamina,
        "MOEDAS": game.inventory.count(COIN),
        "COLHEITA": colheita, "SEMENTES": sementes, "FERTILIZANTES": fert,
        "LIVRES_ESQ": livres_esq, "PLANTIOS_ESQ": plantios_esq,
        "LIVRES_DIR": livres_dir, "PLANTIOS_DIR": plantios_dir,
        "LOJA": shop_today(game, last_sold),
        "CUSTOS": distance_table(game.zones.walkable) + "\n\n" + cost_table(),
        "PRAZO_POR_CULTIVO": prazo, "CULTIVOS_INVIAVEIS": inviaveis,
        "TABELA_CULTIVOS": ("Com os preços de hoje e plantando hoje:\n\n" + crop_table(game, day)),
        "FEEDBACK_ONTEM": feedback,
        "DIARIO_DIAS": settings.DIARY_DAYS,
        "DIARIO": "\n".join(diary) or "(ainda vazio)",
        "CONHECIMENTO": conhecimento,
        "CONHECIMENTO_MAX": settings.KNOWLEDGE_MAX_LINES,
    }


def state_snapshot(game, horizon: int) -> dict:
    """O estado do dia em JSON, so para os logs (o modelo recebe o texto)."""
    campo, day, inv = game.field, game.day, game.inventory
    plantas = []
    for cell, plot in sorted(campo.plots.items()):
        plantas.append({
            "celula": list(cell), "canteiro": plot_zone_of(cell), "cultivo": plot.crop,
            "fertilizada": plot.fertilized,
            "estado": ("podre" if campo.is_spoiled(cell, day)
                       else "pronta" if campo.is_grown(cell, day) else "crescendo"),
            "idade": campo.age(cell, day),
        })
    return {
        "dia": day, "dias_restantes": horizon - day, "estacao": seasons.season_at(day).key,
        "estamina": game.player.stamina, "moedas": inv.count(COIN),
        "colheita": {k: inv.count(k) for k in CROPS},
        "sementes": {k: inv.count(seed_key(k)) for k in CROPS},
        "fertilizante": inv.count(FERTILIZER),
        "caixa_loja": game.market.budget_left(day),
        "precos_venda": {k: game.market.sell_price(k, day) for k in CROPS},
        "precos_compra": {item: game.market.buy_price(item) for item in BUY_PRICES},
        "estoque_loja": {item: game.market.stock_left(item) for item in BUY_PRICES},
        "promocoes": dict(game.market.promos),
        "ultimo_dia_de_plantio": {k: last_planting_day(k, day, horizon) for k in CROPS},
        "plantas": plantas,
    }
