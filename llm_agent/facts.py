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


def fertilizer_text(game=None, horizon: int | None = None) -> str:
    """Como o fertilizante funciona e o que o limita. Com `game`, soma os numeros de hoje."""
    g = game_settings
    efeitos = []
    for key, c in CROPS.items():
        corte = f"-{c.fert_grow_cut} {'dia' if c.fert_grow_cut == 1 else 'dias'} para crescer"
        efeitos.append(f"      {key} ".ljust(18, ".") + f" {corte}, +{c.fert_shelf_bonus} de validade")
    sem_efeito = [s.label for s in seasons.SEASONS if not s.fertilizer_works]
    linhas = [
        "Como funciona:",
        "  - Só age em planta AINDA CRESCENDO: nem pronta, nem podre.",
        "  - Tira dias do crescimento e dá mais validade depois de pronta:",
        *efeitos,
        "    (a coluna \"fertilizada\" da tabela de cultivos já mostra o resultado)",
        "  - O corte conta desde o plantio: se a planta já tem a idade do prazo novo,",
        "    fica pronta na hora.",
        "  - FERTILIZAR não escolhe cultivo: age nas plantas elegíveis mais próximas",
        "    de você, no canteiro em que você está.",
        "",
        "Restrições:",
        "  - 1 por planta: planta já fertilizada não recebe outro.",
        f"  - No máximo {g.FERTILIZERS_PER_DAY} por dia; o contador zera ao dormir.",
        *([f"  - NÃO funciona no {', '.join(sem_efeito)}."] if sem_efeito else []),
        f"  - Aplicar custa {g.STAMINA_FERTILIZE} de stamina, fora o deslocamento.",
        f"  - Carrega-se no máximo {ITEM_LIMITS[FERTILIZER]}. Preço base {FERTILIZER_PRICE} moedas; "
        "a loja sorteia o estoque todo dia.",
    ]
    if game is not None:
        linhas += ["", "Hoje:", *_fertilizer_today(game, horizon or game.day)]
    return "\n".join(linhas)


def _fertilizer_today(game, horizon: int) -> list[str]:
    day, loja = game.day, game.market
    restantes = max(0, game_settings.FERTILIZERS_PER_DAY - game.fertilizers_today)
    linhas = [f"  - Você tem {game.inventory.count(FERTILIZER)}; o limite de hoje ainda permite "
              f"usar {restantes}."]
    estoque = loja.stock_left(FERTILIZER)
    if estoque:
        promo = f" PROMO (base {FERTILIZER_PRICE})" if loja.is_promo(FERTILIZER) else ""
        linhas.append(f"  - Na loja: {loja.buy_price(FERTILIZER)} moedas{promo}, estoque {estoque}.")
    else:
        linhas.append("  - Na loja: esgotado hoje.")

    funciona = seasons.season_at(day).fertilizer_works
    virada = next((d for d in range(day + 1, horizon + 1)
                   if seasons.season_at(d).fertilizer_works != funciona), None)
    if funciona:
        lucros = {k: loja.sell_price(k, day) - loja.buy_price(seed_key(k)) for k in CROPS}
        melhor = max(lucros, key=lucros.get)
        linhas.append(f"  - Para comparar: o maior lucro/ciclo de uma célula hoje é {lucros[melhor]} "
                      f"moedas ({melhor}).")
        linhas.append(f"  - Funciona hoje. Para de funcionar no dia {virada}, com o "
                      f"{seasons.season_at(virada).label}." if virada
                      else "  - Funciona hoje e até o fim da partida.")
    else:
        estacao = seasons.season_at(day).label
        linhas.append(f"  - NÃO funciona hoje ({estacao}). Volta a funcionar no dia {virada}."
                      if virada else f"  - NÃO funciona hoje ({estacao}) nem até o fim da partida.")
    return linhas


# -------------------------------------------------------------- estacoes

def season_changes(season, rot_note: str | None = None) -> list[str]:
    """As regras da estacao que fogem do padrao.

    `rot_note` entra logo depois de "NAO da para plantar": quem chama sabe se e
    para falar da virada em geral ou com o dia marcado.
    """
    mudancas = []
    if season.grow_delta:
        dias = "dia" if abs(season.grow_delta) == 1 else "dias"
        mudancas.append(f"crescimento {season.grow_delta:+d} {dias} para o que for plantado nela")
    if season.shelf_days:
        mudancas.append("validade menor para o que for plantado nela: "
                        + ", ".join(f"{c} {d}" for c, d in season.shelf_days.items()))
    if not season.can_plant:
        mudancas.append("NÃO dá para plantar")
        if rot_note:
            mudancas.append(rot_note)
    if not season.fertilizer_works:
        mudancas.append("fertilizante NÃO funciona")
    if season.sell_multiplier:
        mudancas.append("venda multiplicada: " + ", ".join(
            f"{c} x{m:g}" for c, m in season.sell_multiplier.items()))
    if season.daily_budget:
        mudancas.append(f"caixa da loja {season.daily_budget} moedas por dia")
    return mudancas or ["sem restrições: crescimento, validade, preços e caixa base"]


def seasons_block(horizon: int) -> str:
    """As estacoes que a partida atravessa, com o intervalo de dias de cada uma."""
    trechos, inicio = [], game_settings.FIRST_DAY
    for dia in range(game_settings.FIRST_DAY + 1, horizon + 2):
        if dia > horizon or seasons.season_at(dia) is not seasons.season_at(inicio):
            estacao = seasons.season_at(inicio)
            regras = season_changes(
                estacao, "na virada para ela, TUDO que estiver no chão apodrece na hora")
            dias = f"dia {inicio}" if inicio == dia - 1 else f"dias {inicio} a {dia - 1}"
            trechos.append(f"  {estacao.label} ({dias}): " + "; ".join(regras))
            inicio = dia
    return "\n".join(trechos)


def current_season_text(day: int) -> str:
    estacao = seasons.season_at(day)
    dia_nela = game_settings.SEASON_DAYS - seasons.days_to_next(day) + 1
    return (f"{estacao.label} (dia {dia_nela} de {game_settings.SEASON_DAYS}) — "
            + "; ".join(season_changes(estacao)))


def next_season_text(day: int, horizon: int) -> str:
    """A proxima estacao: quando comeca, quanto falta e o que ela restringe."""
    atual, proxima = seasons.season_at(day), seasons.season_after(day)
    faltam = seasons.days_to_next(day)
    inicio = day + faltam
    if inicio > horizon:
        return (f"{proxima.label}, só no dia {inicio} — depois do fim da partida (dia {horizon}), "
                "não afeta esta partida.")

    quando = (f"a partir de AMANHÃ (dia {inicio})" if faltam == 1
              else f"a partir do dia {inicio} — daqui a {faltam} dias")
    apodrece = None
    if atual.can_plant and not proxima.can_plant:
        prazo = "HOJE" if faltam == 1 else f"até o dia {inicio - 1}"
        apodrece = f"na virada para o dia {inicio}, TUDO que estiver no chão apodrece: colha {prazo}"
    regras = season_changes(proxima, apodrece)
    if proxima.can_plant:
        if not atual.can_plant:
            regras.append("volta a dar para plantar")
        if atual.grow_delta and not proxima.grow_delta:
            regras.append("crescimento volta ao normal para o que for plantado nela")
        if atual.shelf_days and not proxima.shelf_days:
            regras.append("validade volta ao normal para o que for plantado nela")
        if (atual.grow_delta, atual.shelf_days) != (proxima.grow_delta, proxima.shelf_days):
            # Field.timing congela o prazo no plantio: a virada nao mexe no que ja esta no chao.
            regras.append("o que já estiver no chão na virada mantém o crescimento e a validade "
                          "da estação em que foi plantado")
    if proxima.fertilizer_works and not atual.fertilizer_works:
        regras.append("fertilizante volta a funcionar")
    return (f"{proxima.label}, {quando}. Restrições e mudanças:\n"
            + "\n".join(f"  - {r}" for r in regras))


# ------------------------------------------------------------------ loja

def _dump_example(crop: str, units: int) -> tuple[int, int]:
    """(quanto rende, quanto renderia sem saturacao) despejar `units` num dia so.

    Repete a conta de `Market.register_sale`: a unidade que dispara o gatilho
    ainda sai pelo preco cheio, e a queda comeca na seguinte.
    """
    base, piso = CROPS[crop].sell_price, CROPS[crop].seed_price
    total = queda = 0
    for vendidas in range(1, units + 1):
        total += max(piso, base - queda)
        if vendidas >= game_settings.SUPPLY_DEMAND_DAILY_UNITS:
            queda += game_settings.SUPPLY_DEMAND_DROP
    return total, base * units


def _streak_example(crop: str, per_day: int, days: int) -> list[list[int]]:
    """O preco de cada unidade vendendo `per_day` por dia, `days` dias seguidos.

    Mesma conta do dump, com o outro gatilho: a partir do segundo dia o "vendeu
    ontem e hoje" ja derruba desde a primeira unidade do dia.
    """
    base, piso = CROPS[crop].sell_price, CROPS[crop].seed_price
    queda, ontem, dias = 0, False, []
    for _ in range(days):
        precos = []
        for vendidas in range(1, per_day + 1):
            precos.append(max(piso, base - queda))
            if ontem or vendidas >= game_settings.SUPPLY_DEMAND_DAILY_UNITS:
                queda += game_settings.SUPPLY_DEMAND_DROP
        dias.append(precos)
        ontem = True
    return dias


def saturation_text() -> str:
    """O mercado dinamico: como o preco de venda cai por insistencia e como volta.

    Os dois exemplos sao calculados aqui, com a conta de `farm/market.py`; a
    suite compara os numeros com um `Market` de verdade.
    """
    g = game_settings
    despejo, unidades = "melancia", 20
    total, cheio = _dump_example(despejo, unidades)
    base, piso = CROPS[despejo].sell_price, CROPS[despejo].seed_price
    seguido, por_dia, dias = "trigo", 3, 3
    sequencia = " | ".join(" ".join(str(preco) for preco in dia)
                           for dia in _streak_example(seguido, por_dia, dias))
    return "\n".join([
        f"Vale a partir do dia {g.SUPPLY_DEMAND_START_DAY}: antes disso nada é contado. A queda "
        "é por cultivo — saturar",
        "melancia não mexe no trigo.",
        "",
        "Dois gatilhos, qualquer um deles basta:",
        f"  - Volume: vender {g.SUPPLY_DEMAND_DAILY_UNITS} ou mais unidades do mesmo cultivo no "
        "MESMO dia.",
        "  - Repetição: vender o mesmo cultivo ontem E hoje, em qualquer quantidade — 1 unidade",
        "    em cada um dos dois dias já basta.",
        "",
        f"Disparado o gatilho, cada unidade seguinte vale {g.SUPPLY_DEMAND_DROP} moeda a menos, "
        "até o piso: o preço",
        "da semente daquele cultivo, onde vender empata com o custo e para de dar lucro. A conta",
        "não é retroativa, e o desconto entra em cima do preço já multiplicado pela estação.",
        "",
        f"Cada dia SEM vender aquele cultivo devolve {g.SUPPLY_DEMAND_RECOVERY} moeda ao preço, "
        "até o valor cheio; um",
        "único dia parado também quebra a sequência da repetição.",
        "",
        "Com os preços base:",
        f"  - despejar {unidades} {despejo}s num dia só rende {total} moedas, e não {cheio}: as "
        f"{g.SUPPLY_DEMAND_DAILY_UNITS} primeiras",
        f"    saem a {base}, depois {base - 1}, {base - 2}, {base - 3}... até o piso de {piso}.",
        f"  - {por_dia} {seguido}s por dia, {dias} dias seguidos: {sequencia} — e no "
        f"{dias + 1}º dia já",
        "    começa no piso.",
        "  - alternar cultivos, ou pular um dia, mantém o preço cheio.",
    ])


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
        "- Saturação: insistir no mesmo cultivo derruba o preço de venda — a seção seguinte, "
        "O MERCADO É DINÂMICO, tem a regra inteira.",
        f"- Inventário: no máximo {ITEM_LIMITS[seed_key(next(iter(CROPS)))]} sementes de cada tipo "
        f"e {ITEM_LIMITS[FERTILIZER]} fertilizantes. Vegetais e moedas sem limite.",
    ])


def shop_today(game, last_sold: dict[str, int]) -> str:
    g, loja, day = game_settings, game.market, game.day
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
                 else f"desligada até o dia {g.SUPPLY_DEMAND_START_DAY}")
    return "\n".join([
        f"  caixa da loja hoje: {loja.budget_left(day)} moedas",
        "  vende (1 un):  " + " | ".join(vende),
        "  compra:        " + " | ".join(compra[:3]),
        "                 " + " | ".join(compra[3:]),
        f"  saturação: {saturacao} | vendido ontem: {', '.join(ontem) or 'nada'}",
        f"    ({g.SUPPLY_DEMAND_DAILY_UNITS}+ do mesmo cultivo hoje, ou o mesmo cultivo ontem e hoje, "
        f"derrubam {g.SUPPLY_DEMAND_DROP} moeda por",
        f"     unidade até o piso, que é o preço da semente; cada dia sem vender devolve "
        f"{g.SUPPLY_DEMAND_RECOVERY})",
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
        "SATURACAO": saturation_text(),
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
        "ESTACAO": current_season_text(day),
        "PROXIMA_ESTACAO": next_season_text(day, horizon),
        "FERTILIZANTE": fertilizer_text(game, horizon),
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
        "proxima_estacao": seasons.season_after(day).key,
        "dias_ate_proxima_estacao": seasons.days_to_next(day),
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
