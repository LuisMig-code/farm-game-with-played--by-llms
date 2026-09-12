"""Cliente do OpenRouter: uma chamada de chat com prazo e sem dependencia nova.

A requisicao roda numa thread; quem chama espera com um relogio proprio e, se
quiser, um gancho (`wait`) chamado periodicamente. Estourado o prazo, a thread e
abandonada (daemon) e o resultado vira `timeout`.

A chave nunca e gravada em lugar nenhum: o que vai para os logs e o corpo da
mensagem, nunca os cabecalhos.
"""

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from llm_agent import settings

logger = logging.getLogger(__name__)

OK, TIMEOUT, HTTP_ERROR, NETWORK_ERROR = "ok", "timeout", "erro_http", "erro_rede"
RETRYABLE_HTTP = {409, 425, 429, 500, 502, 503}   # 408/504 sao timeout: nao repetem


@dataclass
class CallResult:
    status: str
    duration: float
    content: str = ""
    reasoning: str = ""
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost: float | None = None
    http_status: int | None = None
    finish_reason: str | None = None
    provider: str | None = None
    reasoning_tokens: int | None = None
    error: str = ""
    # Relogio de parede da chamada inteira, do envio ate a decisao (resposta ou prazo).
    started_at: datetime | None = None
    finished_at: datetime | None = None
    raw: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def retryable(self) -> bool:
        """Vale tentar de novo? Timeout nunca: a regra e dormir e seguir."""
        if self.status == NETWORK_ERROR:
            return True
        return self.status == HTTP_ERROR and self.http_status in RETRYABLE_HTTP


def _provider_timeout(codigo: int | None, corpo: str) -> bool:
    """O provedor desistiu por tempo (o OpenRouter corta em ~300s com 504).

    Conta como timeout, e nao como erro para repetir: e o mesmo "nao chegou
    resposta" da regra, so que declarado do outro lado.
    """
    if codigo in (408, 504):
        return True
    try:
        dados = json.loads(corpo)
    except (json.JSONDecodeError, TypeError):
        return False
    dados = dados.get("error", dados) if isinstance(dados, dict) else {}
    meta = dados.get("metadata") if isinstance(dados, dict) else None
    return isinstance(meta, dict) and meta.get("error_type") == "timeout"


class MissingApiKey(RuntimeError):
    pass


def load_api_key(env_file: Path = settings.ENV_FILE,
                 var: str = settings.API_KEY_ENV) -> str:
    """Ambiente primeiro, depois o .env. So KEY=valor; aspas sao removidas."""
    valor = os.environ.get(var, "").strip()
    if not valor and env_file.is_file():
        for linha in env_file.read_text(encoding="utf-8-sig").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            nome, _, resto = linha.partition("=")
            if nome.strip() == var:
                valor = resto.strip().strip('"').strip("'")
                break
    if not valor:
        raise MissingApiKey(f"defina {var} no ambiente ou em {env_file.name}")
    return valor


class OpenRouterClient:
    def __init__(self, *, model: str, api_key: str, timeout: float,
                 temperature: float = settings.TEMPERATURE,
                 max_tokens: int = settings.MAX_TOKENS, seed: int | None = None,
                 include_reasoning: bool = settings.INCLUDE_REASONING,
                 url: str = settings.OPENROUTER_URL):
        self.model = model
        self._api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.seed = seed
        self.include_reasoning = include_reasoning
        self.url = url

    def body(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        corpo: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "usage": {"include": True},
        }
        if self.seed is not None:
            corpo["seed"] = self.seed
        if self.include_reasoning:
            corpo["include_reasoning"] = True
        return corpo

    def complete(self, messages: list[dict[str, str]],
                 wait: Callable[[], None] | None = None) -> CallResult:
        """Faz a chamada e espera no maximo `timeout` segundos."""
        caixa: dict[str, CallResult] = {}
        comeco = datetime.now()
        inicio = time.monotonic()

        pronto = threading.Event()

        def trabalho() -> None:
            try:
                caixa["r"] = self._request(messages, inicio)
            finally:
                pronto.set()

        threading.Thread(target=trabalho, daemon=True, name="openrouter").start()
        # Sem Thread.join(): na run real de 30 dias, um join(0.05) ficou preso ate a
        # thread terminar (466 s, dump em travamentos.log) enquanto ela lia a resposta
        # chunked do OpenRouter. sleep + Event nao dependem do handle da thread.
        while not pronto.is_set():
            if time.monotonic() - inicio >= self.timeout:
                break
            if wait is not None:
                wait()
            time.sleep(0.05)

        # O prazo e conferido tambem na resposta: se a thread principal ficou
        # presa (dentro do gancho, ou com o processo congelado), uma resposta
        # atrasada nao pode passar como ok.
        decorrido = time.monotonic() - inicio
        resultado = caixa.get("r")
        if resultado is None or resultado.duration > self.timeout:
            atraso = (f"; a resposta so chegou em {resultado.duration:.0f}s"
                      if resultado is not None else "")
            logger.warning("chamada sem resposta em %.0fs: timeout%s", self.timeout, atraso)
            resultado = CallResult(TIMEOUT, decorrido,
                                   error=f"sem resposta em {self.timeout:.0f}s{atraso}")
        # A duracao registrada e o tempo que a run de fato esperou por esta chamada.
        resultado.duration = decorrido
        resultado.started_at, resultado.finished_at = comeco, datetime.now()
        return resultado

    # ---------------------------------------------------------------- http

    def _request(self, messages, inicio: float) -> CallResult:
        dados = json.dumps(self.body(messages)).encode("utf-8")
        req = urllib.request.Request(self.url, data=dados, method="POST", headers={
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Title": "farm-game-with-llms",
        })
        try:
            # Um pouco acima do prazo: quem decide o timeout e o laco de espera,
            # isto so garante que a thread abandonada acaba morrendo.
            with urllib.request.urlopen(req, timeout=self.timeout + 15) as resp:
                bruto = resp.read().decode("utf-8")
                status = resp.status
        except urllib.error.HTTPError as erro:
            corpo = erro.read().decode("utf-8", errors="replace")
            classe = TIMEOUT if _provider_timeout(erro.code, corpo) else HTTP_ERROR
            return CallResult(classe, time.monotonic() - inicio, http_status=erro.code,
                              error=corpo[:2000])
        except (urllib.error.URLError, TimeoutError, OSError) as erro:
            return CallResult(NETWORK_ERROR, time.monotonic() - inicio, error=str(erro))

        duracao = time.monotonic() - inicio
        try:
            resposta = json.loads(bruto)
        except json.JSONDecodeError:
            return CallResult(HTTP_ERROR, duracao, http_status=status,
                              error=f"corpo nao e JSON: {bruto[:500]}")

        # O OpenRouter as vezes responde 200 com um erro do provedor dentro.
        if "error" in resposta and not resposta.get("choices"):
            erro = resposta["error"]
            codigo = erro.get("code") if isinstance(erro, dict) else None
            codigo = codigo if isinstance(codigo, int) else 502
            texto = json.dumps(erro, ensure_ascii=False)
            classe = TIMEOUT if _provider_timeout(codigo, texto) else HTTP_ERROR
            return CallResult(classe, duracao, http_status=codigo, error=texto[:2000], raw=resposta)

        escolha = (resposta.get("choices") or [{}])[0]
        mensagem = escolha.get("message") or {}
        uso = resposta.get("usage") or {}
        detalhes = uso.get("completion_tokens_details") or {}
        return CallResult(
            OK, duracao,
            content=mensagem.get("content") or "",
            reasoning=mensagem.get("reasoning") or "",
            tokens_in=uso.get("prompt_tokens"),
            tokens_out=uso.get("completion_tokens"),
            cost=uso.get("cost"),
            http_status=status,
            finish_reason=escolha.get("native_finish_reason") or escolha.get("finish_reason"),
            provider=resposta.get("provider"),
            reasoning_tokens=detalhes.get("reasoning_tokens"),
            raw=resposta,
        )
