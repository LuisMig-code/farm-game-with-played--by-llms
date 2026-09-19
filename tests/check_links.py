"""Confere links relativos e âncoras nos .md do projeto (slug no estilo do GitHub).

    venv/Scripts/python.exe tests/check_links.py

Sai com codigo 1 se achar link ou ancora quebrados.
"""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)


def slugs(path: Path) -> set[str]:
    texto = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
    return {re.sub(r"[^\w\- ]", "", h.strip().lower()).replace(" ", "-") for h in HEADING.findall(texto)}


arquivos = [p for p in ROOT.rglob("*.md")
            if not any(parte in {"venv", "runs_llm", "logs", ".git"} for parte in p.parts)]
erros = 0
for md in arquivos:
    texto = re.sub(r"```.*?```", "", md.read_text(encoding="utf-8"), flags=re.S)
    for alvo in LINK.findall(texto):
        if alvo.startswith(("http://", "https://", "mailto:")):
            continue
        caminho, _, ancora = alvo.partition("#")
        destino = (md.parent / caminho).resolve() if caminho else md
        if not destino.exists():
            print(f"{md.relative_to(ROOT)}: link quebrado -> {alvo}")
            erros += 1
            continue
        if ancora and destino.is_file() and ancora not in slugs(destino):
            print(f"{md.relative_to(ROOT)}: âncora inexistente -> {alvo}")
            erros += 1
print(f"{len(arquivos)} arquivos .md conferidos, {erros} problema(s)")
sys.exit(1 if erros else 0)
