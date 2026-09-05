"""Caminho entre celulas andaveis.

O jogo nao tem pathfinding: o jogador so recebe uma direcao por vez. As 136
celulas andaveis formam um unico componente conexo em 4 direcoes -- duas hortas
ligadas por corredores de uma celula de largura --, entao uma busca em largura
resolve e devolve o menor caminho. A* seria exagero num grafo desse tamanho.
"""

from collections import deque

Cell = tuple[int, int]

STEPS: tuple[Cell, ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))


def shortest_path(start: Cell, target: Cell, walkable) -> list[Cell] | None:
    """Celulas de `start` (exclusive) ate `target` (inclusive), ou None.

    `walkable` e qualquer container com `in` -- na pratica `zones.walkable`,
    que ja e um frozenset publico.
    """
    if start == target:
        return []
    if target not in walkable:
        return None

    came: dict[Cell, Cell | None] = {start: None}
    fila = deque([start])
    while fila:
        cell = fila.popleft()
        if cell == target:
            break
        for dcol, drow in STEPS:
            nxt = (cell[0] + dcol, cell[1] + drow)
            if nxt not in came and nxt in walkable:
                came[nxt] = cell
                fila.append(nxt)

    if target not in came:
        return None

    caminho: list[Cell] = []
    cursor: Cell | None = target
    while cursor is not None:
        caminho.append(cursor)
        cursor = came[cursor]
    caminho.reverse()
    return caminho[1:]          # o primeiro e a celula onde ele ja esta


def directions(path: list[Cell], start: Cell) -> list[Cell]:
    """Converte um caminho em vetores de um passo, para alimentar o jogador."""
    passos = []
    atual = start
    for cell in path:
        passos.append((cell[0] - atual[0], cell[1] - atual[1]))
        atual = cell
    return passos
