"""Cliente falso do OpenRouter para testar o agente sem rede (lógica Projeto Fazenda)."""
import json
import re
import time

from llm_agent.openrouter import HTTP_ERROR, OK, TIMEOUT, CallResult, fatal_status

DIA = re.compile(r"Dia (\d+) de \d+")


class FakeClient:
    """Responde a partir de `script(kind, day, messages, attempt)`.

    - dict vira JSON; str vai cru (serve para JSON inválido);
    - ("sleep", segundos[, resposta]) simula demora (para testar timeout);
    - ("http", codigo[, corpo]) simula erro HTTP.
    """

    def __init__(self, script, timeout=5.0):
        self.script = script
        self.timeout = timeout
        self.calls = []

    def complete(self, messages, wait=None):
        user = messages[1]["content"]
        if "## A PARTIDA" in user:
            kind, day = "estrategia", 0
        else:
            kind, day = "dia", int(DIA.search(user).group(1))
        attempt = sum(1 for c in self.calls if c["kind"] == kind and c["day"] == day) + 1
        self.calls.append({"kind": kind, "day": day, "attempt": attempt, "messages": messages})
        resposta = self.script(kind, day, messages, attempt)

        inicio = time.monotonic()
        if isinstance(resposta, tuple) and resposta[0] == "sleep":
            while time.monotonic() - inicio < resposta[1]:
                if time.monotonic() - inicio >= self.timeout:
                    return CallResult(TIMEOUT, time.monotonic() - inicio, error="fake timeout")
                if wait:
                    wait()
                time.sleep(0.02)
            resposta = resposta[2] if len(resposta) > 2 else padrao_dia([])
        if isinstance(resposta, tuple) and resposta[0] == "http":
            corpo = resposta[2] if len(resposta) > 2 else "fake http"
            # Mesma classificacao do cliente real: 402/401/403 sao fatais.
            classe = fatal_status(resposta[1], corpo) or HTTP_ERROR
            return CallResult(classe, 0.01, http_status=resposta[1], error=corpo)
        conteudo = json.dumps(resposta, ensure_ascii=False) if isinstance(resposta, dict) else resposta
        return CallResult(OK, time.monotonic() - inicio, content=conteudo,
                          reasoning="(raciocínio falso)", tokens_in=100, tokens_out=50, cost=0.0001,
                          http_status=200)


def padrao_estrategia(texto="Trigo no esquerdo; vender todo dia."):
    return {"analise": {"prazo": "x", "cultivos": "x", "canteiros": "x", "abertura": "x",
                        "fechamento": "x"},
            "regras_de_bolso": ["REGRA_DE_BOLSO_MARCADOR vender antes de comprar"],
            "estrategia": texto}


def padrao_dia(plano, conhecimento=None, leitura="leitura falsa"):
    return {"leitura_do_dia": leitura,
            "conhecimento": conhecimento if conhecimento is not None else ["cama-loja custa 6 passos"],
            "plano": plano}
