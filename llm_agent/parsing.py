"""Extrai o objeto JSON da resposta do modelo.

O modelo configurado nao aceita `response_format`, entao o JSON pode vir puro,
dentro de uma cerca ```json, ou cercado de texto. Tenta nessa ordem e, entre os
objetos encontrados, fica com o que tem as chaves esperadas.
"""

import json
import re

CERCA = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class ParseError(ValueError):
    pass


def extract_json(text: str, expected: tuple[str, ...] = ()) -> dict:
    """Devolve o dicionario da resposta ou levanta `ParseError`."""
    if not text or not text.strip():
        raise ParseError("resposta vazia")

    candidatos: list[dict] = []
    for trecho in (text.strip(), *CERCA.findall(text), *_objetos_balanceados(text)):
        try:
            valor = json.loads(trecho)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(valor, dict):
            candidatos.append(valor)

    if not candidatos:
        raise ParseError("nenhum objeto JSON válido na resposta")

    if expected:
        completos = [c for c in candidatos if all(k in c for k in expected)]
        if completos:
            return completos[-1]          # o ultimo costuma ser a resposta final
        faltam = [k for k in expected if all(k not in c for c in candidatos)]
        raise ParseError(f"JSON sem as chaves obrigatórias: {', '.join(faltam)}")
    return candidatos[-1]


def _objetos_balanceados(text: str) -> list[str]:
    """Todos os trechos {...} de nivel mais externo, respeitando strings."""
    trechos, profundidade, inicio = [], 0, None
    em_string = escapado = False
    for i, ch in enumerate(text):
        if em_string:
            if escapado:
                escapado = False
            elif ch == "\\":
                escapado = True
            elif ch == '"':
                em_string = False
            continue
        if ch == '"':
            em_string = True
        elif ch == "{":
            if profundidade == 0:
                inicio = i
            profundidade += 1
        elif ch == "}" and profundidade:
            profundidade -= 1
            if profundidade == 0 and inicio is not None:
                trechos.append(text[inicio:i + 1])
                inicio = None
    return trechos
