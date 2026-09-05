"""Grava a partida em MP4, direto dos quadros que o jogo desenha.

A tela do jogo e 2000x1000 a 60 fps -- gravar isso cru seriam 360 MB/s. Aqui os
quadros sao reduzidos e amostrados: o padrao (1000x500 a 30 fps) custa ~3 ms por
quadro gravado, folgado dentro dos 16,6 ms de orcamento de um quadro a 60 fps.

O encoder e o ffmpeg estatico do `imageio-ffmpeg`, alimentado com bytes RGB
crus. Nao passa por numpy nem por PIL, que nao existem no venv do projeto.
"""

import logging
from pathlib import Path

import pygame

from scripting.errors import RecorderUnavailable

logger = logging.getLogger(__name__)

SIZE = (1000, 500)
FPS = 30
INSTALL = "venv/Scripts/python.exe -m pip install imageio-ffmpeg"


class Recorder:
    """Recebe quadros do laco e escreve um MP4. Use com `close()` no fim."""

    def __init__(self, path: str | Path, size: tuple[int, int] = SIZE, fps: int = FPS):
        self.path = Path(path)
        self.size = size
        self.fps = fps
        self.frames = 0
        self._elapsed = 0.0        # tempo desde o ultimo quadro gravado
        self._writer = self._open()

    def _open(self):
        try:
            import imageio_ffmpeg
        except ImportError as erro:      # noqa: F841 -- a causa vai na mensagem
            raise RecorderUnavailable(
                f"gravar em MP4 precisa do imageio-ffmpeg. Instale com:\n    {INSTALL}"
            ) from erro

        self.path.parent.mkdir(parents=True, exist_ok=True)
        writer = imageio_ffmpeg.write_frames(
            str(self.path), self.size, fps=self.fps,
            # O padrao arredonda a resolucao para multiplos de 16; queremos o
            # tamanho pedido exatamente como esta.
            macro_block_size=1,
        )
        writer.send(None)                # inicializa o gerador
        logger.info("gravando %s (%dx%d a %d fps)", self.path.name, *self.size, self.fps)
        return writer

    # ------------------------------------------------------------------ uso

    def capture(self, surface: pygame.Surface, dt: float) -> None:
        """Grava um quadro se ja passou tempo suficiente desde o ultimo.

        O laco roda a 60 fps e o video a 30, entao a maioria das chamadas so
        acumula tempo e volta.
        """
        if self._writer is None:
            return
        self._elapsed += dt
        intervalo = 1.0 / self.fps
        if self._elapsed < intervalo:
            return
        # Nao zera: guarda a sobra, senao o video atrasa em relacao ao jogo.
        self._elapsed -= intervalo
        self.write(surface)

    def write(self, surface: pygame.Surface) -> None:
        """Grava um quadro agora, sem olhar o relogio."""
        if self._writer is None:
            return
        if surface.get_size() != self.size:
            surface = pygame.transform.smoothscale(surface, self.size)
        self._writer.send(pygame.image.tobytes(surface, "RGB"))
        self.frames += 1

    def close(self) -> None:
        if self._writer is None:
            return
        self._writer.close()
        self._writer = None
        segundos = self.frames / self.fps
        logger.info("video fechado: %s | %d quadros (%.1fs)",
                    self.path.name, self.frames, segundos)
