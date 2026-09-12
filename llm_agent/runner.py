"""Uma run completa: estrategia, depois um ciclo por dia.

    dia D: snapshot -> chamada -> validacao -> (1 correcao) -> executor -> cama -> dormir

Timeout de uma chamada nao e repetido: o jogador dorme e o proximo dia recebe o
aviso. Resposta que chegou mas nao serve (JSON invalido, 429, 5xx) e tentada de
novo ate `API_MAX_ATTEMPTS`.
"""

import faulthandler
import logging
import os
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from farm import rng as farm_rng
from farm import seasons, settings as game_settings
from farm.crops import CROPS
from llm_agent import notebook as nb
from llm_agent import prompts, settings, snapshot
from llm_agent.executor import DONE, PARTIAL, SKIPPED, DayExecution, Executor
from llm_agent.openrouter import OK, TIMEOUT, OpenRouterClient, load_api_key
from llm_agent.parsing import ParseError, extract_json
from llm_agent.run_logs import RunFolder, call_timing
from llm_agent.validator import validate
from scripting import Aborted, Session

logger = logging.getLogger(__name__)

LLM_OK, LLM_TIMEOUT, LLM_API_ERROR, LLM_BAD_JSON = "ok", "timeout", "erro_api", "json_invalido"


class LLMRun:
    def __init__(self, *, seed: int | None = None, days: int = settings.DAYS,
                 model: str = settings.MODEL, mode: str = settings.MODE,
                 knowledge_path: Path | None = None, video: bool = settings.VIDEO,
                 realtime: bool = settings.REALTIME,
                 api_timeout: float = settings.API_TIMEOUT_SECONDS,
                 max_attempts: int = settings.API_MAX_ATTEMPTS,
                 retry_wait: float = settings.API_RETRY_WAIT_SECONDS,
                 runs_dir: Path = settings.RUNS_DIR, client=None):
        if mode not in settings.MODES:
            raise ValueError(f"modo invalido '{mode}' (validos: {', '.join(settings.MODES)})")
        if days < 1:
            raise ValueError("a run precisa de pelo menos 1 dia")

        self.seed = farm_rng.resolve_seed(seed)
        self.days, self.model, self.mode = days, model, mode
        self.video, self.realtime = video, realtime
        self.api_timeout, self.max_attempts, self.retry_wait = api_timeout, max_attempts, retry_wait
        self.runs_dir = Path(runs_dir)
        self.knowledge_path = Path(knowledge_path) if knowledge_path else None
        self.knowledge = (self.knowledge_path.read_text(encoding="utf-8")
                          if self.knowledge_path else None)
        self.client = client or OpenRouterClient(
            model=model, api_key=load_api_key(), timeout=api_timeout, seed=self.seed)

        self.session: Session | None = None
        self.folder: RunFolder | None = None
        self.strategy = ""
        self.notebook: list[str] = []
        self.last_sold: dict[str, int] = {}
        self.totals = Counter()
        self._day_calls = Counter()
        self._day_timings: list[dict] = []

    # --------------------------------------------------------------- execucao

    def run(self) -> dict:
        self.folder = RunFolder(self.runs_dir, model=self.model, mode=self.mode, seed=self.seed)
        # Atribuicao em runtime, antes de criar o Game: os logs nativos do jogo
        # vao para dentro da pasta da run. O arquivo de settings nao muda.
        game_settings.LOGS_DIR = self.folder.game_logs
        logger.info("run %s | modelo %s | modo %s | semente %s | %d dias",
                    self.folder.name, self.model, self.mode, self.seed, self.days)

        interrompida = None
        dia_final = 0
        try:
            self.session = Session(seed=self.seed, realtime=self.realtime,
                                   record=self.folder.video if self.video else None)
            self.executor = Executor(self.session)
            self.system = prompts.system_prompt(self.days)
            self._write_config()
            self._strategy()

            relatorio = None
            for dia in range(game_settings.FIRST_DAY, self.days + 1):
                relatorio = self._day(dia, relatorio)
                dia_final = dia
                if self.session.over:
                    interrompida = "game over (nao deveria acontecer com a rede de seguranca)"
                    logger.error(interrompida)
                    break
        except (KeyboardInterrupt, Aborted) as erro:
            interrompida = f"interrompida: {erro or type(erro).__name__}"
            logger.warning("run %s", interrompida)
        finally:
            resumo = self._finish(dia_final, interrompida)
        return resumo

    # ------------------------------------------------------------- estrategia

    def _strategy(self) -> None:
        game = self.session.game
        self._day_calls, self._day_timings = Counter(), []
        snap = snapshot.build(game, horizon=self.days, last_sold=self.last_sold)
        user = prompts.strategy_prompt(snap, self.days, self.knowledge)
        self.folder.text("estrategia/prompt_system.txt", self.system)
        self.folder.text("estrategia/prompt_user.txt", user)

        mensagens = [{"role": "system", "content": self.system},
                     {"role": "user", "content": user}]
        status, parsed, _ = self._call(mensagens, 0, "estrategia", "estrategia/resposta",
                                       prompts.STRATEGY_KEYS)
        check = nb.check(parsed.get("caderno") if parsed else [])
        if parsed:
            self.strategy = str(parsed.get("estrategia") or "").strip()
            self.notebook = check.accepted
        logger.info("estrategia: %s | %d linhas de caderno aceitas, %d rejeitadas",
                    status, len(check.accepted), len(check.rejected))
        self.folder.json("estrategia/chamadas.json", self._timing_summary())
        self.folder.json("estrategia/estrategia.json", {
            "status_llm": status, "estrategia": self.strategy,
            "caderno": check.accepted, "caderno_rejeitado": check.rejected,
            "base_de_conhecimento": str(self.knowledge_path) if self.knowledge_path else None,
        })

    # -------------------------------------------------------------------- dia

    def _day(self, dia: int, ontem: dict | None) -> dict:
        s, game = self.session, self.session.game
        assert s.day == dia, (s.day, dia)
        pasta = self.folder.day_dir(dia)
        rel = pasta.relative_to(self.folder.root)
        self._day_calls, self._day_timings = Counter(), []

        moedas_inicio, estamina_inicio = s.coins, s.stamina
        podres_antes = Counter(game.stats.spoiled)
        memoria = self.mode == "principal"

        snap = snapshot.build(game, horizon=self.days, last_sold=self.last_sold)
        self.folder.json(rel / "snapshot.json", snap)
        user = prompts.day_prompt(snapshot=snap, horizon=self.days, strategy=self.strategy,
                                  notebook=self.notebook if memoria else [],
                                  report=ontem, memory=memoria)
        self.folder.text(rel / "prompt_user.txt", user)
        mensagens = [{"role": "system", "content": self.system},
                     {"role": "user", "content": user}]

        status, parsed, conteudo = self._call(mensagens, dia, "dia", rel / "resposta",
                                              prompts.DAY_KEYS)
        erros, erros_finais, correcao, status_correcao = [], [], False, None
        plano_linhas, raciocinio, so_prefixo = [], "", False
        check = nb.NotebookCheck()
        execucao = DayExecution(stamina_start=estamina_inicio)

        if status == LLM_OK:
            raciocinio = str(parsed.get("raciocinio") or "")
            plano_linhas = parsed.get("plano")
            check = nb.check(parsed.get("caderno"))
            validacao = validate(game, plano_linhas)
            erros = [e.as_dict() for e in validacao.errors]

            if not validacao.ok:
                correcao = True
                pedido = prompts.correction_prompt(erros)
                self.folder.text(rel / "correcao_prompt.txt", pedido)
                logger.info("dia %d: %d erro(s) de validacao, pedindo correcao", dia, len(erros))
                status_correcao, parsed2, _ = self._call(
                    mensagens + [{"role": "assistant", "content": conteudo},
                                 {"role": "user", "content": pedido}],
                    dia, "correcao", rel / "correcao_resposta", prompts.DAY_KEYS)
                if status_correcao == LLM_OK:
                    plano_linhas = parsed2.get("plano")
                    raciocinio = str(parsed2.get("raciocinio") or raciocinio)
                    if "caderno" in parsed2:
                        check = nb.check(parsed2.get("caderno"))
                    validacao = validate(game, plano_linhas)
                erros_finais = [e.as_dict() for e in validacao.errors]

            acoes = validacao.actions if validacao.ok else validacao.valid_prefix
            so_prefixo = not validacao.ok
            inicio_jogo = time.monotonic()
            execucao = self.executor.run(acoes)
            # Reescrito tambem no modo sem memoria: la ele so nao volta no prompt,
            # e assim formato e custo das respostas ficam iguais nos dois modos.
            anterior, self.notebook = self.notebook, check.accepted
            churn = check.churn(anterior)
        else:
            churn = 0
            inicio_jogo = time.monotonic()
            logger.warning("dia %d sem plano (%s): o jogador dorme", dia, status)

        self.executor.go_home(execucao)
        if dia < self.days:
            s.sleep()
        segundos_execucao = time.monotonic() - inicio_jogo
        apodreceram = Counter(game.stats.spoiled) - podres_antes

        for r in execucao.results:
            if r.action.upper().startswith("VENDER") and r.effective:
                self.last_sold[r.action.split()[1].lower()] = dia

        relatorio = self._report(dia, status, status_correcao, raciocinio, plano_linhas, erros,
                                 erros_finais, correcao, so_prefixo, execucao, moedas_inicio,
                                 apodreceram, check)
        self.folder.json(rel / "relatorio.json", relatorio)
        self.folder.json(rel / "plano.json", {"plano": plano_linhas, "raciocinio": raciocinio,
                                               "erros_validacao": erros,
                                               "erros_apos_correcao": erros_finais,
                                               "executado_so_prefixo_valido": so_prefixo})
        self.folder.text(rel / "caderno.md", self._notebook_md(dia, check))
        self.folder.json(rel / "chamadas.json", {**self._timing_summary(),
                                                 "segundos_execucao_jogo": round(segundos_execucao, 1)})
        self._action_rows(dia, execucao)
        self._metrics_row(dia, status, relatorio, execucao, apodreceram, check, churn,
                          moedas_inicio, segundos_execucao)
        logger.info("dia %d fim | %s | moedas %d -> %d | estamina na cama %d | LLM %.0fs em %d "
                    "chamada(s), jogo %.0fs%s", dia, status, moedas_inicio, s.coins,
                    execucao.stamina_at_bed, self._day_calls["segundos"], self._day_calls["chamadas"],
                    segundos_execucao, " | RETORNO FORCADO" if execucao.forced_return else "")
        return relatorio

    # --------------------------------------------------------------- chamadas

    def _call(self, mensagens, dia, tipo, prefixo, chaves):
        """Chama o modelo com as tentativas. Devolve (status, json, conteudo)."""
        for tentativa in range(1, self.max_attempts + 1):
            logger.info("dia %d: chamada %s (tentativa %d)", dia, tipo, tentativa)
            # Se a espera passar do prazo, o faulthandler grava a pilha de todas as
            # threads: nas runs com janela a thread principal ja travou aqui dezenas de
            # segundos, e isso mostra exatamente onde.
            comeco, t0 = datetime.now(), time.monotonic()
            with open(self.folder.root / "travamentos.log", "a", encoding="utf-8") as trava:
                faulthandler.dump_traceback_later(self.api_timeout + 15, repeat=False, file=trava)
                try:
                    r = self.client.complete(mensagens, wait=self._pump)
                finally:
                    faulthandler.cancel_dump_traceback_later()
            # O cliente real ja mede; qualquer outro (ou um futuro) fica medido aqui.
            if r.started_at is None or r.finished_at is None:
                r.started_at, r.finished_at = comeco, datetime.now()
                r.duration = time.monotonic() - t0
            logger.info("dia %d: chamada %s (tentativa %d) -> %s em %.1fs", dia, tipo, tentativa,
                        r.status, r.duration)
            self._day_timings.append(call_timing(tipo, tentativa, r))
            self.folder.call_row(dia, tipo, tentativa, r)
            self.folder.response_text(f"{prefixo}_{tentativa}.txt", r)
            self._count_call(r)

            if r.status == TIMEOUT:
                return LLM_TIMEOUT, None, ""
            if r.status != OK:
                logger.warning("dia %d: %s (%s) %s", dia, r.status, r.http_status, r.error[:200])
                if r.retryable and tentativa < self.max_attempts:
                    self._wait(self.retry_wait)
                    continue
                return LLM_API_ERROR, None, ""
            try:
                return LLM_OK, extract_json(r.content, chaves), r.content
            except ParseError as erro:
                # Alguns modelos de raciocinio escrevem a resposta so no raciocinio.
                try:
                    return LLM_OK, extract_json(r.reasoning, chaves), r.reasoning
                except ParseError:
                    pass
                logger.warning("dia %d: JSON invalido (%s)", dia, erro)
                if tentativa < self.max_attempts:
                    mensagens = mensagens + [
                        {"role": "assistant", "content": r.content or "(vazio)"},
                        {"role": "user", "content": f"A resposta nao trouxe um objeto JSON "
                                                    f"valido com as chaves {', '.join(chaves)} "
                                                    f"({erro}). Responda apenas com o JSON."}]
                    continue
                return LLM_BAD_JSON, None, ""
        return LLM_API_ERROR, None, ""

    def _timing_summary(self) -> dict:
        tempos = [c["segundos"] for c in self._day_timings]
        return {"chamadas": self._day_timings, "total_chamadas": len(tempos),
                "segundos_llm_total": round(sum(tempos), 1),
                "segundos_maior_chamada": max(tempos) if tempos else 0}

    def _count_call(self, r) -> None:
        for alvo in (self.totals, self._day_calls):
            alvo["maior_chamada"] = max(alvo["maior_chamada"], r.duration)
            alvo["chamadas"] += 1
            alvo["segundos"] += r.duration
            alvo["tokens_in"] += r.tokens_in or 0
            alvo["tokens_out"] += r.tokens_out or 0
            alvo["custo"] += r.cost or 0

    def _pump(self) -> None:
        """Atende a janela enquanto o modelo pensa, sem desenhar nem gravar.

        Sem isso o Windows marca a janela como "Nao respondendo" em 5 s, e fechar
        essa caixa mata a run -- foi o que aconteceu na primeira run de 30 dias.
        """
        game = self.session.game
        game._handle_events()
        if not game.running:
            raise Aborted("a janela do jogo foi fechada durante a espera do modelo")

    def _wait(self, segundos: float) -> None:
        fim = time.monotonic() + segundos
        while time.monotonic() < fim:
            self._pump()
            time.sleep(0.05)

    # -------------------------------------------------------------- relatorio

    def _report(self, dia, status, status_correcao, raciocinio, plano, erros, erros_finais,
                correcao, so_prefixo, execucao, moedas_inicio, apodreceram, check) -> dict:
        s = self.session
        relatorio = {
            "dia": dia,
            "status_llm": status,
            "dia_perdido": status != LLM_OK,
        }
        if status == LLM_TIMEOUT:
            relatorio["aviso"] = (f"A sua resposta nao chegou a tempo (timeout: limite de "
                                  f"{self.api_timeout:.0f} s, ou o provedor desistiu antes). "
                                  "O jogador dormiu sem fazer nada nesse dia. Respostas mais "
                                  "curtas e diretas chegam mais rapido.")
        elif status != LLM_OK:
            relatorio["aviso"] = (f"Nao foi possivel usar a sua resposta ({status}). O jogador "
                                  "dormiu sem fazer nada nesse dia.")
        relatorio.update({
            "plano_recebido": plano if isinstance(plano, list) else [],
            "erros_validacao": erros,
            "correcao_usada": correcao,
        })
        if correcao:
            relatorio["status_correcao"] = status_correcao
            relatorio["erros_apos_correcao"] = erros_finais
            relatorio["executado_so_prefixo_valido"] = so_prefixo
        relatorio.update({
            "acoes": [r.as_dict() for r in execucao.results],
            "plano_concluido": status == LLM_OK and not so_prefixo and execucao.completed,
            "retorno_forcado": execucao.forced_return,
        })
        if execucao.forced_return:
            nao_feitas = [r.action for r in execucao.results if r.status != DONE]
            relatorio.update({
                "retorno_forcado_em": execucao.forced_return_at,
                "retorno_forcado_celula": list(execucao.forced_return_cell),
                "acoes_nao_finalizadas_por_estamina": nao_feitas,
            })
        relatorio.update({
            "estamina_inicio": execucao.stamina_start,
            "estamina_gasta": execucao.stamina_start - execucao.stamina_at_bed,
            "estamina_sobrando_ao_dormir": execucao.stamina_at_bed,
            "passos_de_volta_para_a_cama": execucao.steps_home,
            "moedas_inicio": moedas_inicio,
            "moedas_fim": s.coins,
            "apodreceram_na_virada": [{"cultivo": c, "quantidade": n}
                                      for c, n in sorted(apodreceram.items())],
            "caderno_linhas_rejeitadas": check.rejected,
        })
        return relatorio

    def _notebook_md(self, dia: int, check) -> str:
        linhas = [f"# Caderno ao fim do dia {dia}", ""]
        linhas += [f"- {l}" for l in self.notebook] or ["(vazio)"]
        if check.rejected:
            linhas += ["", "## Rejeitadas", ""]
            linhas += [f"- {r['linha']}  _({r['motivo']})_" for r in check.rejected]
        return "\n".join(linhas) + "\n"

    def _action_rows(self, dia: int, execucao) -> None:
        for i, r in enumerate(execucao.results, 1):
            self.folder.actions.row([dia, i, r.action, r.status, r.requested, r.effective,
                                     r.reason or "", r.stamina_before, r.stamina_after,
                                     r.steps, r.coins, (r.detail or "").replace("\n", " ")])

    def _metrics_row(self, dia, status, relatorio, execucao, apodreceram, check, churn,
                     moedas_inicio, segundos_execucao) -> None:
        res = execucao.results
        vendas = [r for r in res if r.action.upper().startswith("VENDER") and r.effective]
        self.totals["retornos_forcados"] += execucao.forced_return
        self.totals["acoes_truncadas"] += sum(r.status == PARTIAL for r in res)
        self.totals["erros_validacao"] += len(relatorio["erros_validacao"])
        self.totals["dias_perdidos"] += status != LLM_OK
        self.totals["dias_timeout"] += status == LLM_TIMEOUT
        c = self._day_calls
        self.folder.metrics.row([
            dia, seasons.season_at(dia).key, status, int(status != LLM_OK), moedas_inicio,
            self.session.coins, len(relatorio["erros_validacao"]), int(relatorio["correcao_usada"]),
            len(res), sum(r.status == DONE for r in res), sum(r.status == PARTIAL for r in res),
            sum(r.status == SKIPPED for r in res), int(relatorio["plano_concluido"]),
            int(execucao.forced_return), relatorio["estamina_gasta"], execucao.stamina_at_bed,
            sum(r.effective for r in vendas), sum(r.below_base for r in vendas),
            len({r.action.split()[1].lower() for r in vendas}), sum(apodreceram.values()),
            len(self.notebook), len(check.rejected), churn, c["chamadas"],
            f"{c['segundos']:.1f}", f"{c['maior_chamada']:.1f}", f"{segundos_execucao:.1f}",
            c["tokens_in"], c["tokens_out"], f"{c['custo']:.6f}",
        ])

    # -------------------------------------------------------------------- fim

    def _write_config(self) -> None:
        self.folder.json("config.json", {
            "pasta": self.folder.name,
            "inicio": self.folder.started.isoformat(timespec="seconds"),
            "modelo": self.model, "modo": self.mode, "seed": self.seed,
            "dias": self.days, "tempo_real": self.realtime, "video": self.video,
            "janela": os.environ.get("SDL_VIDEODRIVER") != "dummy",
            "api_timeout_segundos": self.api_timeout, "tentativas_por_chamada": self.max_attempts,
            "temperatura": settings.TEMPERATURE, "max_tokens": settings.MAX_TOKENS,
            "reserva_de_estamina": settings.STAMINA_RESERVE,
            "caderno_max_linhas": settings.NOTEBOOK_MAX_LINES,
            "documentos_de_regra": list(settings.RULE_DOCS),
            "base_de_conhecimento": str(self.knowledge_path) if self.knowledge_path else None,
            "base_de_conhecimento_conteudo": self.knowledge,
        })

    def _finish(self, dia_final: int, interrompida: str | None) -> dict:
        moedas = self.session.coins if self.session else 0
        if self.session is not None:
            self.session.close()
        f = self.folder
        trava = f.root / "travamentos.log"
        if trava.exists() and trava.stat().st_size == 0:
            trava.unlink()                     # so fica na pasta se houve travamento
        f.text("caderno_final.txt",
               f"# Caderno final da run {f.name} (dia {dia_final}, modelo {self.model})\n"
               + "\n".join(self.notebook) + ("\n" if self.notebook else ""))

        t = self.totals
        resumo = {
            "pasta": f.name, "inicio": f.started.isoformat(timespec="seconds"),
            "fim": datetime.now().isoformat(timespec="seconds"), "modelo": self.model,
            "modo": self.mode, "seed": self.seed, "dias_jogados": dia_final,
            "horizonte": self.days, "moedas_fim": moedas,
            "dias_perdidos": t["dias_perdidos"], "dias_timeout": t["dias_timeout"],
            "retornos_forcados": t["retornos_forcados"], "acoes_truncadas": t["acoes_truncadas"],
            "erros_validacao": t["erros_validacao"], "chamadas": t["chamadas"],
            "segundos_llm_total": f"{t['segundos']:.1f}",
            "segundos_por_chamada_media": (f"{t['segundos'] / t['chamadas']:.1f}"
                                           if t["chamadas"] else "0.0"),
            "segundos_maior_chamada": f"{t['maior_chamada']:.1f}",
            "segundos_run": f"{(datetime.now() - f.started).total_seconds():.1f}",
            "tokens_in": t["tokens_in"],
            "tokens_out": t["tokens_out"], "custo_usd": f"{t['custo']:.6f}",
            "interrompida": interrompida or "",
        }
        f.append_summary(resumo)
        f.text("LEIAME.md", _readme(resumo, self))
        logger.info("run encerrada | dia %d | %d moedas | %s", dia_final, moedas,
                    interrompida or "completa")
        f.close()
        return resumo


def _duracao(segundos) -> str:
    total = int(float(segundos))
    horas, resto = divmod(total, 3600)
    minutos, segs = divmod(resto, 60)
    return f"{horas}h{minutos:02d}m{segs:02d}s" if horas else f"{minutos}m{segs:02d}s"


def _readme(r: dict, run: "LLMRun") -> str:
    video = "video.mp4" if run.video else "(sem video nesta run)"
    return f"""# Run {r['pasta']}

| | |
| --- | --- |
| Modelo | `{r['modelo']}` |
| Modo | {r['modo']} |
| Semente | {r['seed']} |
| Dias jogados | {r['dias_jogados']} de {r['horizonte']} |
| **Moedas no fim** | **{r['moedas_fim']}** |
| Dias perdidos (sem plano) | {r['dias_perdidos']} (timeout: {r['dias_timeout']}) |
| Retornos forcados por estamina | {r['retornos_forcados']} |
| Acoes truncadas | {r['acoes_truncadas']} |
| Erros de validacao | {r['erros_validacao']} |
| Chamadas ao modelo | {r['chamadas']} |
| Tempo esperando o modelo | {_duracao(r['segundos_llm_total'])} (media {r['segundos_por_chamada_media']} s por chamada, maior {r['segundos_maior_chamada']} s) |
| Duracao total da run | {_duracao(r['segundos_run'])} |
| Tokens (entrada / saida) | {r['tokens_in']} / {r['tokens_out']} |
| Inicio / fim | {r['inicio']} / {r['fim']} |
| Situacao | {r['interrompida'] or 'completa'} |

## Arquivos

| Caminho | Conteudo |
| --- | --- |
| `config.json` | tudo que definiu a run, inclusive a base de conhecimento |
| `agente.log` | log de texto completo |
| `estrategia/` | prompt de sistema, prompt da estrategia, resposta bruta e a estrategia extraida |
| `dias/dia_NNN/` | snapshot, prompt, respostas brutas (com raciocinio), plano, relatorio, caderno e `chamadas.json` (tempo de cada chamada e da execucao do jogo) |
| `chamadas.csv` | uma linha por chamada ao modelo: inicio, fim, segundos, status, tokens |
| `acoes.csv` | uma linha por acao executada |
| `metricas.csv` | uma linha por dia |
| `jogo/` | os logs nativos do jogo (CSV e texto) |
| `{video}` | a tela do jogo, em tempo de jogo |
| `caderno_final.txt` | o caderno do ultimo dia, pronto para `--knowledge` numa proxima run |

O prompt de sistema e o mesmo em todas as chamadas: esta so em `estrategia/prompt_system.txt`.
"""
