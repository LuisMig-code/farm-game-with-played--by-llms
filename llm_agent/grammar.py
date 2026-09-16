"""A DSL do plano diario: vocabulario fechado e parser de um comando.

    IR <cama|loja|canteiro_esquerdo|canteiro_direito>
    COLHER [TUDO|<n>|LIMITE <n>]
    PLANTAR <cultivo> [TUDO|<n>|LIMITE <n>]
    FERTILIZAR [TUDO|<n>|LIMITE <n>]
    LIMPAR [TUDO|<n>|LIMITE <n>]
    COMPRAR <cultivo|fertilizante> <n>
    VENDER <cultivo> [TUDO|<n>|LIMITE <n>]

Um quantificador so, sempre no fim: a palavra LIMITE e opcional em todo lugar, e
TUDO -- ou nada -- quer dizer "o que der". A unica excecao e COMPRAR, que exige o
numero: um comando nao pode zerar o caixa da run sem dizer quanto.

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
QUANT = "[TUDO|<n>|LIMITE <n>]"

FIELD_VERBS = ("COLHER", "PLANTAR", "FERTILIZAR", "LIMPAR")
SHOP_VERBS = ("COMPRAR", "VENDER")


class GrammarError(ValueError):
    pass


@dataclass(frozen=True)
class Command:
    """Um comando ja entendido.

    `limit` = teto nos verbos de campo (LIMITE n ou n solto); `amount` = a
    quantidade pedida (COMPRAR, VENDER); `all_` = TUDO ou quantificador ausente.
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
        return Command(raw, verb, **_quant(args, f"{verb} {QUANT}"))

    if verb == "PLANTAR":
        forma = f"PLANTAR <cultivo> {QUANT}"
        crop = _crop(_first(args, forma))
        return Command(raw, verb, crop=crop, **_quant(args[1:], forma))

    if verb == "COMPRAR":
        forma = "COMPRAR <cultivo|fertilizante> <n>"
        alvo = _first(args, forma)
        quanto = _quant(args[1:], forma, exact=True, required=True)
        if alvo.lower() == FERTILIZER_ID:
            return Command(raw, verb, item=FERTILIZER, **quanto)
        crop = _crop(alvo)
        return Command(raw, verb, crop=crop, item=seed_key(crop), **quanto)

    forma = f"VENDER <cultivo> {QUANT}"
    crop = _crop(_first(args, forma))
    return Command(raw, verb, crop=crop, **_quant(args[1:], forma, exact=True))


# --------------------------------------------------------------- auxiliares

def _arity(args, n, forma) -> None:
    if len(args) != n:
        raise GrammarError(f"formato errado: {forma}")


def _first(args: list[str], forma: str) -> str:
    if not args:
        raise GrammarError(f"formato errado: {forma}")
    return args[0]


def _crop(token: str) -> str:
    cultura = token.lower()
    if cultura not in CROPS:
        raise GrammarError(f"cultivo '{token}' não existe (válidos: {' '.join(CROP_IDS)})")
    return cultura


def _positive(token: str, forma: str) -> int:
    if not token.isdigit() or int(token) < 1:
        raise GrammarError(f"quantidade '{token}' inválida: {forma}")
    return int(token)


def _quant(args: list[str], forma: str, *, exact: bool = False,
           required: bool = False) -> dict:
    """O quantificador do fim do comando, ja nos campos do Command.

    A palavra LIMITE e opcional: `COLHER 3` e `COLHER LIMITE 3` sao o mesmo
    comando, e sem quantificador -- ou com TUDO -- vale o que der. `exact`
    devolve `amount` (quantidade pedida) no lugar de `limit` (teto); `required`
    recusa TUDO e a ausencia, que e o caso do COMPRAR.
    """
    if args and args[0].upper() == LIMIT:
        args = args[1:]
        if not args:
            raise GrammarError(f"LIMITE sem número depois: {forma}")
    if not args:
        if required:
            raise GrammarError(f"falta a quantidade: {forma}")
        return {"all_": True}
    if len(args) > 1:
        raise GrammarError(f"sobrou texto depois da quantidade: {forma}")
    if args[0].upper() == ALL:
        if required:
            raise GrammarError(f"COMPRAR exige o número de unidades, não aceita TUDO: {forma}")
        return {"all_": True}
    n = _positive(args[0], forma)
    return {"amount": n} if exact else {"limit": n}


def plot_zone_of(cell: Cell) -> str | None:
    """Em qual canteiro fica uma celula plantavel, se em algum."""
    for zona, colunas in PLOT_COLUMNS.items():
        if cell[0] in colunas and 2 <= cell[1] <= 8:
            return zona
    return None
