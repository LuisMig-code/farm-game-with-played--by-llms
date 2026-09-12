"""O retrato do inicio do dia que o modelo recebe.

Agregado por canteiro, nao celula a celula: a gramatica opera por zona, entao o
que o modelo precisa decidir e *quanto* colher e *quando* plantar. Tudo sai de
metodo publico do jogo, ou do rastreio de vendas que o runner mantem.
"""

from functools import lru_cache

from farm import seasons, settings as game_settings
from farm.crops import BUY_PRICES, COIN, CROPS, FERTILIZER, ITEM_LIMITS, seed_key
from llm_agent import settings
from llm_agent.grammar import BUY_ITEMS, PLOT_ZONES, ZONE_CELLS, plot_zone_of
from scripting import shortest_path

Cell = tuple[int, int]


@lru_cache(maxsize=None)
def zone_distances(walkable: frozenset) -> dict[str, int]:
    """Passos entre cada par de zonas, pelo menor caminho andavel."""
    nomes = list(ZONE_CELLS)
    tabela = {}
    for i, a in enumerate(nomes):
        for b in nomes[i + 1:]:
            tabela[f"{a}-{b}"] = len(shortest_path(ZONE_CELLS[a], ZONE_CELLS[b], walkable))
    return tabela


def season_changes(season) -> list[str]:
    """O que uma estacao muda em relacao ao ritmo padrao, em frases curtas."""
    mudancas = []
    if season.grow_delta:
        mudancas.append(f"crescimento {season.grow_delta:+d} dia(s) para o que for plantado nela")
    if season.shelf_days:
        prazos = ", ".join(f"{c} {d}" for c, d in season.shelf_days.items())
        mudancas.append(f"validade depois de pronta (dias): {prazos}")
    if not season.can_plant:
        mudancas.append("NAO da para plantar")
        mudancas.append("na virada para ela, TUDO que estiver no chao apodrece na hora "
                        "(inclusive o que ja esta pronto)")
    if not season.fertilizer_works:
        mudancas.append("fertilizante NAO funciona")
    if season.sell_multiplier:
        fatores = ", ".join(f"{c} x{m:g}" for c, m in season.sell_multiplier.items())
        mudancas.append(f"precos de venda multiplicados: {fatores}")
    if season.daily_budget:
        mudancas.append(f"caixa da loja {season.daily_budget} moedas por dia")
    if season.promo_item_chances:
        mudancas.append("promocoes mais frequentes na loja")
    return mudancas or ["ritmo padrao (nada muda)"]


def build(game, *, horizon: int, last_sold: dict[str, int]) -> dict:
    day = game.day
    atual, proxima = seasons.season_at(day), seasons.season_after(day)
    inv, loja = game.inventory, game.market

    return {
        "dia": day,
        "dias_restantes": horizon - day,
        "ultimo_dia": horizon,
        "estacao": atual.key,
        "estacao_muda": season_changes(atual),
        "dias_ate_proxima_estacao": seasons.days_to_next(day),
        "proxima_estacao": proxima.key,
        "proxima_estacao_muda": season_changes(proxima),
        "estamina": game.player.stamina,
        "estamina_maxima": game.player.max_stamina,
        "fertilizantes_restantes_hoje": max(
            0, game_settings.FERTILIZERS_PER_DAY - game.fertilizers_today),

        "inventario": {
            "moedas": inv.count(COIN),
            "sementes": {k: inv.count(seed_key(k)) for k in CROPS},
            "vegetais": {k: inv.count(k) for k in CROPS},
            "fertilizante": inv.count(FERTILIZER),
            "limites": {"sementes_por_tipo": ITEM_LIMITS[seed_key(next(iter(CROPS)))],
                        "fertilizante": ITEM_LIMITS[FERTILIZER]},
        },

        "loja": {
            "caixa": loja.budget_left(day),
            "caixa_do_dia": loja.daily_budget(day),
            "precos_venda": {k: _sell_price(loja, k, day) for k in CROPS},
            "precos_compra": {
                item_id: {"base": BUY_PRICES[item], "atual": loja.buy_price(item),
                          "promocao": loja.is_promo(item), "estoque": loja.stock_left(item)}
                for item_id, item in BUY_ITEMS.items()
            },
        },

        "mercado": {
            # Do rastreio do runner, e nao do Market: o jogo so conta vendas
            # depois que a oferta/demanda liga (dia 11).
            "vendido_ontem": sorted(k for k, d in last_sold.items() if d == day - 1),
            "dias_sem_vender": {k: (day - last_sold[k]) if k in last_sold else None
                                for k in CROPS},
            "saturacao_ativa_a_partir_do_dia": game_settings.SUPPLY_DEMAND_START_DAY,
        },

        **{zona: _plot_zone(game, zona) for zona in PLOT_ZONES},

        "distancias": zone_distances(game.zones.walkable),
        "reserva_de_estamina_ao_chegar_na_cama": settings.STAMINA_RESERVE,
    }


def _sell_price(loja, crop: str, day: int) -> dict:
    base = loja.base_price(crop, day)
    atual = loja.sell_price(crop, day)
    info = {"base": base, "atual": atual, "piso": CROPS[crop].seed_price}
    if atual < base:
        info["motivo"] = "saturacao"
    return info


def _plot_zone(game, zona: str) -> dict:
    campo, day = game.field, game.day
    celulas = [c for c in game.zones.plantable if plot_zone_of(c) == zona]

    por_cultivo: dict[str, dict[str, int]] = {}
    resumo = {"celulas_totais": len(celulas), "vazias": 0, "podres": 0,
              "prontas_hoje": 0, "prontas_amanha": 0,
              "apodrecem_em_1_dia": 0, "apodrecem_em_2_dias": 0}

    for cell in celulas:
        plot = campo.at(cell)
        if plot is None:
            resumo["vazias"] += 1
            continue
        linha = por_cultivo.setdefault(plot.crop, {
            "total": 0, "colhivel": 0, "crescendo": 0, "podres": 0, "fertilizadas": 0})
        linha["total"] += 1
        linha["fertilizadas"] += plot.fertilized

        if campo.is_spoiled(cell, day):
            resumo["podres"] += 1
            linha["podres"] += 1
        elif campo.is_grown(cell, day):
            linha["colhivel"] += 1
            resumo["prontas_hoje"] += 1
            restantes = campo.days_left(cell, day)
            if restantes == 1:
                resumo["apodrecem_em_1_dia"] += 1
            elif restantes == 2:
                resumo["apodrecem_em_2_dias"] += 1
        else:
            linha["crescendo"] += 1
            crescer, _ = campo.timing(plot)
            if crescer - campo.age(cell, day) == 1:
                resumo["prontas_amanha"] += 1

    resumo["por_cultivo"] = por_cultivo
    return resumo
