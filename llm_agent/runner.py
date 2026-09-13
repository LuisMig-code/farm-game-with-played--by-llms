"""Uma run completa, no laco do Projeto Fazenda.

    chamada inicial (1x): regras + prazo + custos -> analise, regras_de_bolso, estrategia (<=128)
    cada dia:  estrategia + estado calculado + prazo + feedback de ontem + diario + conhecimento
               -> leitura_do_dia, conhecimento (reescrito, <=15), plano
               -> interpretador executa em ordem, descarta o invalido, reserva a volta, dorme
               -> feedback classificado para amanha

Total: N + 1 chamadas para N dias. Nunca se pede reenvio de plano: comando
invalido e descartado e vira feedback. So se repete chamada cuja resposta chegou
mas nao serve como JSON (ou 429/5xx). Timeout nao repete: o jogador dorme.
"""

import faulthandler
import logging
import os
import shutil
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from farm import rng as farm_rng
from farm import seasons, settings as game_settings
from llm_agent import facts, feedback, responses, settings, templates
from llm_agent.executor import (CONTEXT, GRAMMAR, OK, PARTIAL, RESOURCE, TRUNCATED, DayExecution,
                                Executor)
from llm_agent.openrouter import OK as HTTP_OK
from llm_agent.openrouter import TIMEOUT, OpenRouterClient, load_api_key
from llm_agent.parsing import ParseError, extract_json
from llm_agent.run_logs import RunFolder, call_timing, publish_game_logs, slug
from scripting import Aborted, Session

logger = logging.getLogger(__name__)

LLM_OK, LLM_TIMEOUT, LLM_API_ERROR, LLM_BAD_JSON = "ok", "timeout", "erro_api", "json_invalido"


@dataclass
class Outcome:
    status: str
    parsed: dict | None = None       # a resposta aprovada
    candidate: dict | None = None    # o ultimo JSON lido, mesmo reprovado
    problem: str | None = None       # por que o ultimo JSON foi reprovado


class LLMRun:
    def __init__(self, *, seed: int | None = None, days: int = settings.DAYS,
                 model: str = settings.MODEL, mode: str = settings.MODE,
                 knowledge_path: Path | None = None, video: bool = settings.VIDEO,
                 realtime: bool = settings.REALTIME, speed: float = settings.GAME_SPEED,
                 api_timeout: float = settings.API_TIMEOUT_SECONDS,
                 max_attempts: int = settings.API_MAX_ATTEMPTS,
                 retry_wait: float = settings.API_RETRY_WAIT_SECONDS,
                 runs_dir: Path = settings.RUNS_DIR,
                 game_logs_dir: Path = settings.GAME_LOGS_DIR, client=None,
                 prompt_strategy: Path = settings.PROMPT_STRATEGY,
                 prompt_day: Path = settings.PROMPT_DAY):
        if mode not in settings.MODES:
            raise ValueError(f"modo invalido '{mode}' (validos: {', '.join(settings.MODES)})")
        if days < 1:
            raise ValueError("a run precisa de pelo menos 1 dia")
        if not 0 < speed <= Session.max_speed():
            raise ValueError(f"velocidade invalida {speed} (entre 0 e {Session.max_speed():.2f})")

        self.seed = farm_rng.resolve_seed(seed)
        self.days, self.model, self.mode = days, model, mode
        self.video, self.realtime, self.speed = video, realtime, speed
        self.api_timeout, self.max_attempts, self.retry_wait = api_timeout, max_attempts, retry_wait
        self.runs_dir = Path(runs_dir)
        self.game_logs_dir = Path(game_logs_dir)
        self.game_logs_published: list[Path] = []
        self.prompt_strategy, self.prompt_day = Path(prompt_strategy), Path(prompt_day)
        self.knowledge_path = Path(knowledge_path) if knowledge_path else None
        self.knowledge_base = (self.knowledge_path.read_text(encoding="utf-8")
                               if self.knowledge_path else None)
        self.client = client or OpenRouterClient(
            model=model, api_key=load_api_key(), timeout=api_timeout, seed=self.seed)

        self.session: Session | None = None
        self.folder: RunFolder | None = None
        self.strategy = ""
        self.knowledge: list[str] = []
        self.diary: list[str] = []
        self.last_sold: dict[str, int] = {}
        self.plot_zones_used: set[str] = set()
        self.totals = Counter()
        self._day_calls = Counter()
        self._day_timings: list[dict] = []

    # --------------------------------------------------------------- execucao

    def run(self) -> dict:
        # Os dois templates sao conferidos antes de abrir o jogo: placeholder
        # errado no .md falha aqui, e nao no meio da run.
        for caminho in (self.prompt_strategy, self.prompt_day):
            templates.load(caminho)

        self.folder = RunFolder(self.runs_dir, model=self.model, mode=self.mode, seed=self.seed)
        # Atribuicao em runtime, antes de criar o Game: os logs nativos do jogo
        # vao para dentro da pasta da run. O arquivo de settings nao muda.
        game_settings.LOGS_DIR = self.folder.game_logs
        logger.info("run %s | modelo %s | modo %s | semente %s | %d dias",
                    self.folder.name, self.model, self.mode, self.seed, self.days)

        interrompida, dia_final = None, 0
        try:
            self.session = Session(seed=self.seed, realtime=self.realtime, speed=self.speed,
                                   record=self.folder.video if self.video else None)
            self.executor = Executor(self.session)
            self._write_config()
            self._strategy()

            feedback_ontem = "Hoje é o primeiro dia: ainda não há feedback."
            for dia in range(game_settings.FIRST_DAY, self.days + 1):
                feedback_ontem = self._day(dia, feedback_ontem)
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
        self._day_calls, self._day_timings = Counter(), []
        valores = facts.strategy_values(self.session.game, self.days, self.knowledge_base)
        prompt = templates.render(self.prompt_strategy, valores)
        self.folder.prompt_text("estrategia/prompt.txt", prompt)

        out = self._call(prompt.messages(), 0, "estrategia", "estrategia/resposta",
                         responses.STRATEGY_KEYS, responses.strategy_problem)
        cortada = False
        dados = out.parsed
        if dados is None and out.candidate and isinstance(out.candidate.get("estrategia"), str):
            # Esgotou as tentativas so por tamanho: usa a ultima, cortada no teto.
            dados, cortada = out.candidate, True
        if dados is not None:
            texto = " ".join(str(dados.get("estrategia") or "").split())
            self.strategy = texto[:settings.STRATEGY_MAX_CHARS]
            cortada = cortada or len(texto) > settings.STRATEGY_MAX_CHARS

        logger.info("estrategia: %s%s | %r", out.status, " (cortada)" if cortada else "",
                    self.strategy)
        self.folder.json("estrategia/chamadas.json", self._timing_summary())
        self.folder.json("estrategia/estrategia.json", {
            "status_llm": out.status,
            "estrategia": self.strategy,
            "estrategia_cortada": cortada,
            "caracteres": len(self.strategy),
            "analise": (dados or {}).get("analise"),
            "regras_de_bolso": (dados or {}).get("regras_de_bolso"),
            "problema_na_ultima_resposta": out.problem,
            "base_de_conhecimento": str(self.knowledge_path) if self.knowledge_path else None,
        })

    # -------------------------------------------------------------------- dia

    def _day(self, dia: int, feedback_ontem: str) -> str:
        s, game = self.session, self.session.game
        assert s.day == dia, (s.day, dia)
        rel = self.folder.day_dir(dia).relative_to(self.folder.root)
        self._day_calls, self._day_timings = Counter(), []

        moedas_inicio, estamina_inicio = s.coins, s.stamina
        podres_antes = Counter(game.stats.spoiled)
        memoria = self.mode == "principal"

        valores = facts.day_values(
            game, horizon=self.days, strategy=self.strategy, feedback=feedback_ontem,
            diary=self.diary[-settings.DIARY_DAYS:], knowledge=self.knowledge if memoria else [],
            memory=memoria, last_sold=self.last_sold)
        prompt = templates.render(self.prompt_day, valores)
        self.folder.prompt_text(rel / "prompt.txt", prompt)
        self.folder.json(rel / "estado.json", facts.state_snapshot(game, self.days))

        out = self._call(prompt.messages(), dia, "dia", rel / "resposta",
                         responses.DAY_KEYS, responses.day_problem)
        leitura, plano, conhecimento = "", [], responses.Knowledge(lines=list(self.knowledge))
        anterior = list(self.knowledge)

        if out.status == LLM_OK:
            leitura = str(out.parsed.get("leitura_do_dia") or "")
            plano = out.parsed.get("plano")
            conhecimento = responses.curate(out.parsed.get("conhecimento"))
            inicio_jogo = time.monotonic()
            execucao = self.executor.run(plano)
            # Reescrito tambem no modo sem memoria: la ele so nao volta no prompt,
            # e formato e custo das respostas ficam iguais nos dois modos.
            self.knowledge = conhecimento.lines
        else:
            inicio_jogo = time.monotonic()
            execucao = DayExecution(stamina_start=estamina_inicio)
            logger.warning("dia %d sem plano (%s): o jogador dorme", dia, out.status)

        self.executor.go_home(execucao)
        if dia < self.days:
            s.sleep()
        segundos_execucao = time.monotonic() - inicio_jogo
        apodreceram = Counter(game.stats.spoiled) - podres_antes
        self.plot_zones_used |= execucao.plot_zones_visited
        for r in execucao.results:
            if r.verb == "VENDER" and r.effective:
                self.last_sold[r.crop] = dia

        aviso = self._warning(out.status)
        texto_feedback = feedback.day_feedback(
            dia, execucao, status_llm=out.status, aviso=aviso, moedas_inicio=moedas_inicio,
            moedas_fim=s.coins, apodreceram=apodreceram, knowledge_cut=conhecimento.cut)
        self.diary.append(feedback.diary_line(
            dia, execucao, status_llm=out.status, moedas_inicio=moedas_inicio,
            moedas_fim=s.coins, leitura=leitura))

        self._save_day(dia, rel, out, leitura, plano, conhecimento, anterior, execucao,
                       texto_feedback, moedas_inicio, apodreceram, segundos_execucao, aviso)
        logger.info("dia %d fim | %s | moedas %d -> %d | %s | stamina na cama %d | LLM %.0fs em "
                    "%d chamada(s), jogo %.0fs", dia, out.status, moedas_inicio, s.coins,
                    _code_summary(execucao), execucao.stamina_at_bed, self._day_calls["segundos"],
                    self._day_calls["chamadas"], segundos_execucao)
        return texto_feedback

    def _warning(self, status: str) -> str | None:
        if status == LLM_TIMEOUT:
            return (f"A sua resposta não chegou a tempo (limite de {self.api_timeout:.0f} s, ou o "
                    "provedor desistiu antes). O jogador dormiu sem agir.")
        if status != LLM_OK:
            return f"A sua resposta não pôde ser usada ({status}). O jogador dormiu sem agir."
        return None

    def _save_day(self, dia, rel, out, leitura, plano, conhecimento, anterior, execucao,
                  texto_feedback, moedas_inicio, apodreceram, segundos_execucao, aviso) -> None:
        f, s = self.folder, self.session
        if out.parsed is not None:
            f.json(rel / "resposta.json", out.parsed)
        f.text(rel / "feedback.txt", texto_feedback + "\n")
        f.text(rel / "conhecimento.md", _knowledge_md(dia, self.knowledge, conhecimento, anterior))
        f.json(rel / "chamadas.json", {**self._timing_summary(),
                                       "segundos_execucao_jogo": round(segundos_execucao, 1)})
        f.json(rel / "relatorio.json", {
            "dia": dia, "status_llm": out.status, "dia_perdido": out.status != LLM_OK,
            "aviso": aviso, "leitura_do_dia": leitura,
            "plano": plano if isinstance(plano, list) else plano,
            "comandos": [r.as_dict() for r in execucao.results],
            "truncado": execucao.truncated, "truncado_em": execucao.truncated_at,
            "estamina": {"inicio": execucao.stamina_start, "na_cama": execucao.stamina_at_bed,
                         "gasta": execucao.stamina_start - execucao.stamina_at_bed,
                         **{p: execucao.stamina_parts[p] for p in feedback.STAMINA_PARTS}},
            "passos_de_volta_para_a_cama": execucao.steps_home,
            "moedas": {"inicio": moedas_inicio, "fim": s.coins},
            "apodreceram_na_virada": dict(apodreceram),
            "canteiros_visitados": sorted(execucao.plot_zones_visited),
            "conhecimento": {"linhas": len(conhecimento.lines),
                             "novas": conhecimento.new_since(anterior),
                             "removidas": conhecimento.removed_since(anterior),
                             "cortadas": conhecimento.cut},
        })

        for r in execucao.results:
            f.commands.row([dia, r.index, r.raw, r.code, r.detail, r.requested, r.effective,
                            r.steps, r.coins, r.stamina_before, r.stamina_after])
            if r.code == GRAMMAR:
                f.grammar_errors.row([dia, r.index, r.raw, r.detail])

        vendas = [r for r in execucao.results if r.verb == "VENDER" and r.effective]
        partes, c, t = execucao.stamina_parts, self._day_calls, self.totals
        for code in (GRAMMAR, CONTEXT, RESOURCE):
            t[code] += execucao.count(code)
        t["dias_perdidos"] += out.status != LLM_OK
        t["dias_timeout"] += out.status == LLM_TIMEOUT
        t["dias_truncados"] += execucao.truncated
        f.days.row([
            dia, seasons.season_at(dia).key, out.status, int(out.status != LLM_OK), moedas_inicio,
            s.coins, len(execucao.results), execucao.count(OK), execucao.count(PARTIAL),
            execucao.count(GRAMMAR), execucao.count(CONTEXT), execucao.count(RESOURCE),
            execucao.count(TRUNCATED), int(execucao.truncated),
            execucao.stamina_start - execucao.stamina_at_bed,
            *(partes[p] for p in feedback.STAMINA_PARTS), execucao.stamina_at_bed,
            "+".join(sorted(execucao.plot_zones_visited)), sum(r.effective for r in vendas),
            sum(r.below_base for r in vendas), sum(apodreceram.values()),
            len(s.game.field.plots), len(conhecimento.lines), conhecimento.new_since(anterior),
            conhecimento.removed_since(anterior), conhecimento.cut, c["chamadas"],
            f"{c['segundos']:.1f}", f"{c['maior_chamada']:.1f}", f"{segundos_execucao:.1f}",
            c["tokens_in"], c["tokens_out"], f"{c['custo']:.6f}",
        ])

    # --------------------------------------------------------------- chamadas

    def _call(self, mensagens, dia, tipo, prefixo, chaves, problema) -> Outcome:
        """Chama o modelo com as tentativas e confere a resposta."""
        ultimo = Outcome(LLM_API_ERROR)
        for tentativa in range(1, self.max_attempts + 1):
            logger.info("dia %d: chamada %s (tentativa %d)", dia, tipo, tentativa)
            comeco, t0 = datetime.now(), time.monotonic()
            # Se a espera passar do prazo, a pilha de todas as threads vai para o
            # travamentos.log: foi assim que se achou o join() travado nas runs reais.
            with open(self.folder.root / "travamentos.log", "a", encoding="utf-8") as trava:
                faulthandler.dump_traceback_later(self.api_timeout + 15, repeat=False, file=trava)
                try:
                    r = self.client.complete(mensagens, wait=self._pump)
                finally:
                    faulthandler.cancel_dump_traceback_later()
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
                return Outcome(LLM_TIMEOUT, candidate=ultimo.candidate)
            if r.status != HTTP_OK:
                logger.warning("dia %d: %s (%s) %s", dia, r.status, r.http_status, r.error[:200])
                if r.retryable and tentativa < self.max_attempts:
                    self._wait(self.retry_wait)
                    continue
                return Outcome(LLM_API_ERROR, candidate=ultimo.candidate)

            try:
                dados = extract_json(r.content or r.reasoning, chaves)
                motivo = problema(dados)
            except ParseError as erro:
                dados, motivo = None, str(erro)
            if motivo is None:
                return Outcome(LLM_OK, parsed=dados)

            ultimo = Outcome(LLM_BAD_JSON, candidate=dados or ultimo.candidate, problem=motivo)
            logger.warning("dia %d: resposta reprovada (%s)", dia, motivo)
            if tentativa < self.max_attempts:
                mensagens = mensagens + [
                    {"role": "assistant", "content": r.content or "(vazio)"},
                    {"role": "user", "content": f"Resposta rejeitada: {motivo}. Responda "
                                                f"SOMENTE com o objeto JSON pedido, com as "
                                                f"chaves {', '.join(chaves)}."}]
        return ultimo

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
        """Atende a janela enquanto o modelo pensa, sem desenhar nem gravar."""
        game = self.session.game
        game._handle_events()
        if not game.running:
            raise Aborted("a janela do jogo foi fechada durante a espera do modelo")

    def _wait(self, segundos: float) -> None:
        fim = time.monotonic() + segundos
        while time.monotonic() < fim:
            self._pump()
            time.sleep(0.05)

    # -------------------------------------------------------------------- fim

    def _write_config(self) -> None:
        # Os templates usados vao junto: editar o .md muda a proxima run, entao a
        # pasta precisa guardar exatamente o que esta rodou.
        (self.folder.root / "prompts").mkdir(exist_ok=True)
        for caminho in (self.prompt_strategy, self.prompt_day):
            shutil.copy2(caminho, self.folder.root / "prompts" / caminho.name)
        self.folder.json("config.json", {
            "pasta": self.folder.name,
            "inicio": self.folder.started.isoformat(timespec="seconds"),
            "modelo": self.model, "modo": self.mode, "seed": self.seed, "dias": self.days,
            "tempo_real": self.realtime, "velocidade": self.speed, "video": self.video,
            "logs_do_jogo_copiados_para": str(self.game_logs_dir),
            "janela": os.environ.get("SDL_VIDEODRIVER") != "dummy",
            "api_timeout_segundos": self.api_timeout, "tentativas_por_chamada": self.max_attempts,
            "temperatura": settings.TEMPERATURE, "reasoning_effort": settings.REASONING_EFFORT,
            "json_forcado": settings.RESPONSE_FORMAT_JSON, "max_tokens": settings.MAX_TOKENS,
            "estrategia_max_caracteres": settings.STRATEGY_MAX_CHARS,
            "conhecimento_max_linhas": settings.KNOWLEDGE_MAX_LINES,
            "diario_dias": settings.DIARY_DAYS, "reserva_de_estamina": settings.STAMINA_RESERVE,
            "prompts": [str(self.prompt_strategy), str(self.prompt_day)],
            "base_de_conhecimento": str(self.knowledge_path) if self.knowledge_path else None,
            "base_de_conhecimento_conteudo": self.knowledge_base,
        })

    def _finish(self, dia_final: int, interrompida: str | None) -> dict:
        moedas = self.session.coins if self.session else 0
        no_chao = len(self.session.game.field.plots) if self.session else 0
        if self.session is not None:
            self.session.close()
            self._publish_game_logs()
        f = self.folder
        trava = f.root / "travamentos.log"
        if trava.exists() and trava.stat().st_size == 0:
            trava.unlink()                     # so fica na pasta se houve travamento
        f.text("conhecimento_final.txt",
               f"# Conhecimento final da run {f.name} (dia {dia_final}, modelo {self.model})\n"
               + "\n".join(self.knowledge) + ("\n" if self.knowledge else ""))

        t = self.totals
        resumo = {
            "pasta": f.name, "inicio": f.started.isoformat(timespec="seconds"),
            "fim": datetime.now().isoformat(timespec="seconds"), "modelo": self.model,
            "modo": self.mode, "seed": self.seed, "dias_jogados": dia_final,
            "horizonte": self.days, "moedas_fim": moedas,
            "dias_perdidos": t["dias_perdidos"], "dias_timeout": t["dias_timeout"],
            "dias_truncados": t["dias_truncados"], "no_chao_no_fim": no_chao,
            "canteiros_usados": "+".join(sorted(self.plot_zones_used)) or "nenhum",
            "erros_gramatica": t[GRAMMAR], "erros_contexto": t[CONTEXT],
            "erros_recurso": t[RESOURCE], "chamadas": t["chamadas"],
            "segundos_llm_total": f"{t['segundos']:.1f}",
            "segundos_por_chamada_media": (f"{t['segundos'] / t['chamadas']:.1f}"
                                           if t["chamadas"] else "0.0"),
            "segundos_maior_chamada": f"{t['maior_chamada']:.1f}",
            "segundos_run": f"{(datetime.now() - f.started).total_seconds():.1f}",
            "tokens_in": t["tokens_in"], "tokens_out": t["tokens_out"],
            "custo_usd": f"{t['custo']:.6f}", "interrompida": interrompida or "",
        }
        f.append_summary(resumo)
        f.text("LEIAME.md", _readme(resumo, self))
        logger.info("run encerrada | dia %d | %d moedas | %s", dia_final, moedas,
                    interrompida or "completa")
        f.close()
        return resumo

    def _publish_game_logs(self) -> None:
        """Copia os logs nativos para a pasta de logs do jogo, com o prefixo da IA.

        Uma falha aqui nao pode derrubar o fim da run: o original segue em jogo/.
        """
        prefixo = settings.GAME_LOGS_PREFIX.format(modelo=slug(self.model))
        try:
            self.game_logs_published = publish_game_logs(self.session.game, self.game_logs_dir,
                                                         prefixo)
        except OSError as erro:
            logger.warning("nao deu para copiar os logs do jogo para %s: %s",
                           self.game_logs_dir, erro)
            return
        logger.info("logs do jogo copiados para %s: %s", self.game_logs_dir,
                    ", ".join(p.name for p in self.game_logs_published))


def _code_summary(execucao: DayExecution) -> str:
    contagem = Counter(r.code for r in execucao.results)
    return ", ".join(f"{n} {c}" for c, n in contagem.items()) or "sem comandos"


def _knowledge_md(dia: int, atual: list[str], conhecimento, anterior: list[str]) -> str:
    linhas = [f"# Conhecimento ao fim do dia {dia}", ""]
    linhas += [f"- {l}" for l in atual] or ["(vazio)"]
    novas = [l for l in atual if l not in anterior]
    saiu = [l for l in anterior if l not in atual]
    if novas:
        linhas += ["", "## Novas hoje", ""] + [f"- {l}" for l in novas]
    if saiu:
        linhas += ["", "## Removidas hoje", ""] + [f"- {l}" for l in saiu]
    if conhecimento.cut:
        linhas += ["", f"_{conhecimento.cut} linha(s) acima do teto foram cortadas._"]
    return "\n".join(linhas) + "\n"


def _duracao(segundos) -> str:
    total = int(float(segundos))
    horas, resto = divmod(total, 3600)
    minutos, segs = divmod(resto, 60)
    return f"{horas}h{minutos:02d}m{segs:02d}s" if horas else f"{minutos}m{segs:02d}s"


def _readme(r: dict, run: "LLMRun") -> str:
    video = "video.mp4" if run.video else "(sem video nesta run)"
    publicados = "".join(f"| `{p.parent.name}/{p.name}` | copia dos logs do jogo, na pasta de logs "
                         f"do jogo |\n" for p in run.game_logs_published)
    return f"""# Run {r['pasta']}

| | |
| --- | --- |
| Modelo | `{r['modelo']}` |
| Modo | {r['modo']} |
| Semente | {r['seed']} |
| Velocidade das acoes | {run.speed:g}x |
| Dias jogados | {r['dias_jogados']} de {r['horizonte']} |
| **Moedas no fim** | **{r['moedas_fim']}** |
| Estrategia | `{run.strategy or '(nenhuma)'}` |
| Dias perdidos (sem plano) | {r['dias_perdidos']} (timeout: {r['dias_timeout']}) |
| Dias truncados pela stamina | {r['dias_truncados']} |
| Plantas no chao no fim | {r['no_chao_no_fim']} |
| Canteiros usados | {r['canteiros_usados']} |
| Erros (gramatica / contexto / recurso) | {r['erros_gramatica']} / {r['erros_contexto']} / {r['erros_recurso']} |
| Chamadas ao modelo | {r['chamadas']} |
| Tempo esperando o modelo | {_duracao(r['segundos_llm_total'])} (media {r['segundos_por_chamada_media']} s por chamada, maior {r['segundos_maior_chamada']} s) |
| Duracao total da run | {_duracao(r['segundos_run'])} |
| Tokens (entrada / saida) | {r['tokens_in']} / {r['tokens_out']} |
| Custo | US$ {r['custo_usd']} |
| Inicio / fim | {r['inicio']} / {r['fim']} |
| Situacao | {r['interrompida'] or 'completa'} |

## Arquivos

| Caminho | Conteudo |
| --- | --- |
| `config.json` | tudo que definiu a run, inclusive a base de conhecimento |
| `prompts/` | os templates .md exatamente como estavam nesta run |
| `agente.log` | log de texto completo |
| `estrategia/` | prompt renderizado, respostas brutas, `estrategia.json` (analise, regras de bolso, estrategia) |
| `dias/dia_NNN/` | `prompt.txt`, `estado.json`, respostas brutas (com raciocinio), `resposta.json`, `feedback.txt`, `relatorio.json`, `conhecimento.md`, `chamadas.json` |
| `chamadas.csv` | uma linha por chamada: inicio, fim, segundos, status, tokens |
| `comandos.csv` | uma linha por comando do plano, com o codigo do resultado |
| `dias.csv` | uma linha por dia |
| `erros_gramatica.csv` | todo comando fora da gramatica: sao pedidos de feature |
| `jogo/` | os logs nativos do jogo (CSV e texto) |
{publicados}| `{video}` | a tela do jogo, na velocidade da run |
| `conhecimento_final.txt` | o bloco de conhecimento do ultimo dia, pronto para `--knowledge` |
"""
