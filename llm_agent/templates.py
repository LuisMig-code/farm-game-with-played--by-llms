"""Prompts em .md, lidos em runtime.

Cada arquivo tem duas secoes, `# SYSTEM` e `# USER`, e placeholders em
`{MAIUSCULAS}`. So esses sao substituidos: as chaves do JSON de exemplo que o
prompt mostra ao modelo ficam intactas. Um placeholder que o codigo nao conhece
levanta erro -- erro de digitacao no .md aparece na hora, e nao como texto cru
mandado ao modelo.
"""

import re
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDER = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
SECTION = re.compile(r"^#\s+(SYSTEM|USER)\s*$", re.MULTILINE)


class TemplateError(ValueError):
    pass


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str

    def messages(self) -> list[dict[str, str]]:
        return [{"role": "system", "content": self.system},
                {"role": "user", "content": self.user}]


def load(path: Path) -> tuple[str, str]:
    """As secoes SYSTEM e USER do arquivo, ainda com os placeholders."""
    texto = Path(path).read_text(encoding="utf-8")
    partes = SECTION.split(texto)
    # split com grupo: [antes, "SYSTEM", corpo, "USER", corpo]
    secoes = {partes[i]: partes[i + 1].strip() for i in range(1, len(partes) - 1, 2)}
    faltam = {"SYSTEM", "USER"} - secoes.keys()
    if faltam:
        raise TemplateError(f"{Path(path).name} sem a(s) secao(oes) {', '.join(sorted(faltam))}")
    return secoes["SYSTEM"], secoes["USER"]


def placeholders(path: Path) -> set[str]:
    system, user = load(path)
    return set(PLACEHOLDER.findall(system)) | set(PLACEHOLDER.findall(user))


def render(path: Path, values: dict[str, object]) -> Prompt:
    system, user = load(path)
    return Prompt(_fill(system, values, path), _fill(user, values, path))


def _fill(texto: str, values: dict[str, object], path: Path) -> str:
    def troca(m: re.Match) -> str:
        nome = m.group(1)
        if nome not in values:
            raise TemplateError(f"{Path(path).name}: placeholder {{{nome}}} sem valor no codigo")
        return str(values[nome])
    return PLACEHOLDER.sub(troca, texto)
