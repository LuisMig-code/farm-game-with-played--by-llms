"""A DSL do plano diario: vocabulario e parser de uma linha.

    IR <zona>
    COLHER <cultivo|TUDO> [LIMITE n]
    PLANTAR <cultivo> <TUDO|LIMITE n|n>
    FERTILIZAR <cultivo|TUDO> [LIMITE n]
    LIMPAR [LIMITE n]
    COMPRAR <item> <n>
    VENDER <cultivo> <TUDO|n>

Palavras-chave e ids sao aceitos em maiusculas ou minusculas: o que medimos e se
o modelo entende as regras, nao se acerta a caixa das letras. Qualquer token
fora do vocabulario e ERRO_GRAMATICA.
"""

from dataclasses import dataclass

from farm.crops import CROPS, FERTILIZER, seed_key
from scripting import HOUSE, SHOP

Cell = tuple[int, int]

VERBS = ("IR", "COLHER", "PLANTAR", "FERTILIZAR", "LIMPAR", "COMPRAR", "VENDER")

BED, STORE, LEFT, RIGHT = "cama", "loja", "canteiro_esquerdo", "canteiro_direito"
# Onde cada zona "e": para canteiro, a celula de entrada colada no caminho.
ZONE_CELLS: dict[str, Cell] = {BED: HOUSE, STORE: SHOP, LEFT: (6, 8), RIGHT: (33, 8)}
PLOT_ZONES = (LEFT, RIGHT)
# Colunas de cada canteiro (as linhas sao 2..8 nos dois).
PLOT_COLUMNS = {LEFT: range(3, 10), RIGHT: range(30, 37)}

CROP_IDS = tuple(CROPS)
BUY_ITEMS: dict[str, str] = {
    **{f"semente_{k}": seed_key(k) for k in CROPS},
    "fertilizante": FERTILIZER,
}

ALL, LIMIT = "TUDO", "LIMITE"

# Custo de estamina de cada acao de campo, por unidade.
FIELD_VERBS = ("COLHER", "PLANTAR", "FERTILIZAR", "LIMPAR")
SHOP_VERBS = ("COMPRAR", "VENDER")


class GrammarError(ValueError):
    pass


@dataclass(frozen=True)
class Action:
    """Uma linha do plano ja entendida.

    Quantidade: `all_` = TUDO; `limit` = LIMITE n (TUDO com teto); `amount` = n
    exato. Em COLHER/FERTILIZAR `crop=None` significa todas as culturas.
    """
    raw: str
    verb: str
    zone: str | None = None
    crop: str | None = None
    item: str | None = None          # chave do jogo, ex. "semente trigo"
    item_id: str | None = None       # id da DSL, ex. "semente_trigo"
    amount: int | None = None
    limit: int | None = None
    all_: bool = False

    def cap(self, disponivel: int) -> int:
        """Quantas unidades a acao pede, dado o que esta disponivel agora."""
        if self.amount is not None:
            return self.amount
        if self.limit is not None:
            return min(self.limit, disponivel)
        return disponivel


def parse_line(line: str) -> Action:
    if not isinstance(line, str):
        raise GrammarError(f"a linha do plano precisa ser texto, veio {type(line).__name__}")
    raw = " ".join(line.split())
    tokens = raw.split(" ") if raw else []
    if not tokens:
        raise GrammarError("linha vazia")

    verb = tokens[0].upper()
    args = tokens[1:]
    if verb not in VERBS:
        raise GrammarError(f"verbo desconhecido '{tokens[0]}' (validos: {' '.join(VERBS)})")

    if verb == "IR":
        _arity(verb, args, 1, "IR <zona>")
        return Action(raw, verb, zone=_zone(args[0]))

    if verb in ("COLHER", "FERTILIZAR"):
        forma = f"{verb} <cultivo|TUDO> [LIMITE n]"
        if len(args) not in (1, 3):
            raise GrammarError(f"aridade errada: {forma}")
        crop = None if args[0].upper() == ALL else _crop(args[0])
        limit = _limit(args[1:], forma) if len(args) == 3 else None
        return Action(raw, verb, crop=crop, limit=limit, all_=limit is None)

    if verb == "PLANTAR":
        forma = "PLANTAR <cultivo> <TUDO|LIMITE n|n>"
        if len(args) not in (2, 3):
            raise GrammarError(f"aridade errada: {forma}")
        crop = _crop(args[0])
        return _quantified(raw, verb, args[1:], forma, crop=crop)

    if verb == "LIMPAR":
        forma = "LIMPAR [LIMITE n]"
        if len(args) not in (0, 2):
            raise GrammarError(f"aridade errada: {forma}")
        limit = _limit(args, forma) if args else None
        return Action(raw, verb, limit=limit, all_=limit is None)

    if verb == "COMPRAR":
        forma = "COMPRAR <item> <n>"
        _arity(verb, args, 2, forma)
        item_id = args[0].lower()
        if item_id not in BUY_ITEMS:
            raise GrammarError(f"item de compra desconhecido '{args[0]}' "
                               f"(validos: {' '.join(BUY_ITEMS)})")
        return Action(raw, verb, item=BUY_ITEMS[item_id], item_id=item_id,
                      amount=_positive(args[1], forma))

    # VENDER
    forma = "VENDER <cultivo> <TUDO|n>"
    _arity(verb, args, 2, forma)
    crop = _crop(args[0])
    if args[1].upper() == ALL:
        return Action(raw, verb, crop=crop, all_=True)
    return Action(raw, verb, crop=crop, amount=_positive(args[1], forma))


# --------------------------------------------------------------- auxiliares

def _arity(verb, args, n, forma) -> None:
    if len(args) != n:
        raise GrammarError(f"aridade errada: {forma}")


def _zone(token: str) -> str:
    zona = token.lower()
    if zona not in ZONE_CELLS:
        raise GrammarError(f"zona desconhecida '{token}' (validas: {' '.join(ZONE_CELLS)})")
    return zona


def _crop(token: str) -> str:
    cultura = token.lower()
    if cultura not in CROPS:
        raise GrammarError(f"cultivo desconhecido '{token}' (validos: {' '.join(CROP_IDS)})")
    return cultura


def _positive(token: str, forma: str) -> int:
    if not token.isdigit() or int(token) < 1:
        raise GrammarError(f"quantidade invalida '{token}': {forma}")
    return int(token)


def _limit(args: list[str], forma: str) -> int:
    if len(args) != 2 or args[0].upper() != LIMIT:
        raise GrammarError(f"esperava 'LIMITE n': {forma}")
    return _positive(args[1], forma)


def _quantified(raw, verb, args, forma, **campos) -> Action:
    if len(args) == 1 and args[0].upper() == ALL:
        return Action(raw, verb, all_=True, **campos)
    if len(args) == 1:
        return Action(raw, verb, amount=_positive(args[0], forma), **campos)
    return Action(raw, verb, limit=_limit(args, forma), **campos)


def plot_zone_of(cell: Cell) -> str | None:
    """Em qual canteiro fica uma celula plantavel, se em algum."""
    for zona, colunas in PLOT_COLUMNS.items():
        if cell[0] in colunas and 2 <= cell[1] <= 8:
            return zona
    return None


def reference() -> str:
    """Texto da gramatica para o prompt, gerado das mesmas constantes do parser."""
    return "\n".join([
        "Verbos e assinaturas (uma acao por linha do plano):",
        "  IR <zona>                              move ate a zona",
        "  COLHER <cultivo|TUDO> [LIMITE n]       colhe plantas prontas (nao estragadas)",
        "  PLANTAR <cultivo> <TUDO|LIMITE n|n>    planta em celulas vazias",
        "  FERTILIZAR <cultivo|TUDO> [LIMITE n]   plantas crescendo e ainda nao fertilizadas",
        "  LIMPAR [LIMITE n]                      arranca plantas estragadas",
        "  COMPRAR <item> <n>                     compra n unidades",
        "  VENDER <cultivo> <TUDO|n>              vende unidades da colheita",
        "",
        f"Zonas: {' '.join(ZONE_CELLS)}",
        f"Cultivos: {' '.join(CROP_IDS)}",
        f"Itens de compra: {' '.join(BUY_ITEMS)}",
        "Quantificadores: TUDO = tudo o que for possivel; LIMITE n = tudo, com teto n; "
        "n = exatamente n.",
        "",
        "COLHER, PLANTAR, FERTILIZAR e LIMPAR exigem estar num canteiro (use IR antes).",
        "COMPRAR e VENDER exigem estar na loja.",
    ])
