"""A DSL do plano diario: vocabulario fechado e parser de um comando.

    IR <cama|loja|canteiro_esquerdo|canteiro_direito>
    COLHER [LIMITE <n>]
    PLANTAR <cultivo> <TUDO|LIMITE <n>>
    FERTILIZAR [LIMITE <n>]
    LIMPAR [LIMITE <n>]
    COMPRAR <cultivo|fertilizante> <n>
    VENDER <cultivo> <TUDO|<n>>

O LLM decide, o interpretador conta: cultivo, quantidade comprada, canteiro e
ordem das paradas sao julgamento do modelo; celula, caminho e estamina ficam com
o codigo. Por isso nao ha MOVER, DORMIR nem coordenada.

Palavras-chave e ids sao aceitos em maiusculas ou minusculas. Qualquer token
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
PLOT_COLUMNS = {LEFT: range(3, 10), RIGHT: range(30, 37)}   # linhas 2..8 nos dois

CROP_IDS = tuple(CROPS)
FERTILIZER_ID = "fertilizante"
ALL, LIMIT = "TUDO", "LIMITE"

FIELD_VERBS = ("COLHER", "PLANTAR", "FERTILIZAR", "LIMPAR")
SHOP_VERBS = ("COMPRAR", "VENDER")


class GrammarError(ValueError):
    pass


@dataclass(frozen=True)
class Command:
    """Um comando ja entendido.

    `limit` = LIMITE n (teto); `amount` = n exato (COMPRAR, VENDER n);
    `all_` = TUDO, ou ausencia de LIMITE em COLHER/FERTILIZAR/LIMPAR.
    """
    raw: str
    verb: str
    zone: str | None = None
    crop: str | None = None
    item: str | None = None          # chave do jogo: "semente trigo" ou "fertilizante"
    amount: int | None = None
    limit: int | None = None
    all_: bool = False

    def cap(self, disponivel: int) -> int:
        """Quantas unidades o comando pede, dado o que da para fazer agora."""
        if self.amount is not None:
            return self.amount
        if self.limit is not None:
            return min(self.limit, disponivel)
        return disponivel


def parse(line) -> Command:
    if not isinstance(line, str):
        raise GrammarError(f"o comando precisa ser texto, veio {type(line).__name__}")
    raw = " ".join(line.split())
    tokens = raw.split(" ") if raw else []
    if not tokens:
        raise GrammarError("comando vazio")

    verb, args = tokens[0].upper(), tokens[1:]
    if verb not in VERBS:
        raise GrammarError(f"verbo '{tokens[0]}' não existe (válidos: {' '.join(VERBS)})")

    if verb == "IR":
        _arity(args, 1, "IR <zona>")
        zona = args[0].lower()
        if zona not in ZONE_CELLS:
            raise GrammarError(f"zona '{args[0]}' não existe (válidas: {' '.join(ZONE_CELLS)})")
        return Command(raw, verb, zone=zona)

    if verb in ("COLHER", "FERTILIZAR", "LIMPAR"):
        forma = f"{verb} [LIMITE <n>]"
        if not args:
            return Command(raw, verb, all_=True)
        return Command(raw, verb, limit=_limit(args, forma))

    if verb == "PLANTAR":
        forma = "PLANTAR <cultivo> <TUDO|LIMITE <n>>"
        if len(args) not in (2, 3):
            raise GrammarError(f"formato errado: {forma}")
        crop = _crop(args[0])
        if len(args) == 2:
            if args[1].upper() != ALL:
                raise GrammarError(f"esperava TUDO ou LIMITE <n> depois do cultivo: {forma}")
            return Command(raw, verb, crop=crop, all_=True)
        return Command(raw, verb, crop=crop, limit=_limit(args[1:], forma))

    if verb == "COMPRAR":
        forma = "COMPRAR <cultivo|fertilizante> <n>"
        _arity(args, 2, forma)
        alvo = args[0].lower()
        if alvo == FERTILIZER_ID:
            return Command(raw, verb, item=FERTILIZER, amount=_positive(args[1], forma))
        crop = _crop(args[0])
        return Command(raw, verb, crop=crop, item=seed_key(crop), amount=_positive(args[1], forma))

    forma = "VENDER <cultivo> <TUDO|<n>>"
    _arity(args, 2, forma)
    crop = _crop(args[0])
    if args[1].upper() == ALL:
        return Command(raw, verb, crop=crop, all_=True)
    return Command(raw, verb, crop=crop, amount=_positive(args[1], forma))


# --------------------------------------------------------------- auxiliares

def _arity(args, n, forma) -> None:
    if len(args) != n:
        raise GrammarError(f"formato errado: {forma}")


def _crop(token: str) -> str:
    cultura = token.lower()
    if cultura not in CROPS:
        raise GrammarError(f"cultivo '{token}' não existe (válidos: {' '.join(CROP_IDS)})")
    return cultura


def _positive(token: str, forma: str) -> int:
    if not token.isdigit() or int(token) < 1:
        raise GrammarError(f"quantidade '{token}' inválida: {forma}")
    return int(token)


def _limit(args: list[str], forma: str) -> int:
    if len(args) != 2 or args[0].upper() != LIMIT:
        raise GrammarError(f"formato errado: {forma}")
    return _positive(args[1], forma)


def plot_zone_of(cell: Cell) -> str | None:
    """Em qual canteiro fica uma celula plantavel, se em algum."""
    for zona, colunas in PLOT_COLUMNS.items():
        if cell[0] in colunas and 2 <= cell[1] <= 8:
            return zona
    return None
