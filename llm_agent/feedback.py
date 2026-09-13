"""O que o modelo le sobre ontem: o feedback classificado e o diario.

Feedback classificado, nao binario: cada codigo pede uma correcao diferente, e
"nao executado" num balde so nao diz ao modelo o que corrigir.

    DIA 12 -- executado
    [1] IR loja                    OK (6 passos)
    [2] VENDER trigo TUDO          OK (18 un -> 216 moedas)
    [3] COMPRAR trigo 22           PARCIAL: comprou 6 de 22 (42 moedas): ...
    [--] volta para a cama         OK (25 passos)
    stamina: 160 -> 3   (andando 79 | plantando 12 | colhendo 7 | fertilizando 0 | limpando 0)

A ultima linha e a que expoe o gargalo: o deslocamento come mais que o trabalho.
"""

from collections import Counter

from llm_agent.executor import CODES, OK, STAMINA_PARTS, DayExecution

WIDTH = 32


def day_feedback(dia: int, execucao: DayExecution, *, status_llm: str, aviso: str | None,
                 moedas_inicio: int, moedas_fim: int, apodreceram: Counter,
                 knowledge_cut: int = 0) -> str:
    if status_llm != "ok":
        cabecalho = f"DIA {dia} — sem plano"
        corpo = [aviso or "A sua resposta não pôde ser usada. O jogador dormiu sem agir."]
    else:
        cabecalho = f"DIA {dia} — executado" + (", cortado pela stamina" if execucao.truncated else "")
        corpo = [_line(f"[{r.index}] {r.raw}", r.code, r.detail) for r in execucao.results]
        if not execucao.results:
            corpo.append("(plano vazio)")
        corpo.append(_line("[--] volta para a cama", OK, f"{execucao.steps_home} passos"))

    partes = execucao.stamina_parts
    corpo.append(f"stamina: {execucao.stamina_start} -> {execucao.stamina_at_bed}   ("
                 + " | ".join(f"{p} {partes[p]}" for p in STAMINA_PARTS) + ")")
    corpo.append(f"moedas: {moedas_inicio} -> {moedas_fim}")
    if apodreceram:
        corpo.append("apodreceram na virada da noite: "
                     + ", ".join(f"{c} {n}" for c, n in sorted(apodreceram.items())))
    if knowledge_cut:
        corpo.append(f"conhecimento: vieram linhas demais; {knowledge_cut} foram cortadas (as últimas)")
    return "\n".join([cabecalho, *corpo])


def _line(esquerda: str, code: str, detail: str) -> str:
    esquerda = esquerda if len(esquerda) >= WIDTH else esquerda.ljust(WIDTH)
    if code == OK:
        return f"{esquerda} OK ({detail})" if detail else f"{esquerda} OK"
    return f"{esquerda} {code}: {detail}"


def diary_line(dia: int, execucao: DayExecution, *, status_llm: str, moedas_inicio: int,
               moedas_fim: int, leitura: str) -> str:
    """Uma linha por dia: o que aconteceu, sem opiniao."""
    if status_llm != "ok":
        return f"dia {dia} | {status_llm}: sem plano, dormiu | moedas {moedas_inicio} -> {moedas_fim}"
    codigos = Counter(r.code for r in execucao.results)
    resumo = ", ".join(f"{codigos[c]} {c}" for c in CODES if codigos[c]) or "plano vazio"
    feitos = Counter()
    for r in execucao.results:
        if r.effective and r.verb in ("VENDER", "COMPRAR", "PLANTAR", "COLHER", "FERTILIZAR", "LIMPAR"):
            chave = r.verb.lower() + (f" {r.crop}" if r.crop and r.verb != "COLHER" else "")
            feitos[chave] += r.effective
    acoes = ", ".join(f"{k} {n}" for k, n in feitos.items()) or "nada"
    texto = " ".join(leitura.split())
    if len(texto) > 160:
        texto = texto[:157] + "..."
    return (f"dia {dia} | moedas {moedas_inicio} -> {moedas_fim} | {resumo} | "
            f"stamina gasta {execucao.stamina_start - execucao.stamina_at_bed} | {acoes} | "
            f"leitura: {texto or '-'}")
