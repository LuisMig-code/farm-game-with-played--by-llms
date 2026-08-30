# Controles

| Tecla             | Ação                                                     |
| ----------------- | -------------------------------------------------------- |
| `W A S D` / setas | Move o personagem; com menu aberto, muda a opção          |
| `Espaço` / Enter  | Age na célula: dormir, negociar, plantar, fertilizar, colher ou remover |
| `G`               | Liga/desliga o grid e as zonas                            |
| `ESC`             | Volta um nível no menu da loja; fecha o menu; sem menu, sai do jogo |
| `R`               | Só na tela de derrota: recomeça a partida                 |
| Mouse             | Destaca a célula sob o cursor                             |

O que o Espaço faz em cada célula, e todas as regras de estamina, dias, cultivo, validade e
fertilizante, estão em [GAME_RULES.md](GAME_RULES.md). Cada partida grava um log de texto e um CSV em `logs/`,
descritos em [LOGS.md](LOGS.md).

## Mundo e grid

- Mapa: 2000x1000 px (`Assets/main-background.png`), sempre visivel por inteiro.
- Janela: 2000x1000 px — render 1:1, sem reducao. A `View` continua sendo a ponte
  mundo -> tela, entao voltar a janela para 1000x500 em `settings.py` so muda a escala
  do desenho; a logica do jogo nao muda.
- Flag `SCALED`: se a janela nao couber no monitor, o SDL reduz sozinho e mantem as
  coordenadas logicas.
- Grid: celulas de 50x50 px -> 40 colunas x 20 linhas.
- Linhas mais fortes a cada 5 celulas, para facilitar a contagem.

## Zonas do mapa

Definidas em `settings.py` (`PLANTABLE_AREAS` e `WALKABLE_AREAS`) como pares de cantos
inclusivos, e expandidas em celulas por `farm/zones.py`. A uniao delas e a **unica** area
onde o jogador pode pisar — todo o resto e bloqueado.

| Zona       | Celulas                                  | Cor na tela          |
| ---------- | ---------------------------------------- | -------------------- |
| Plantio    | (3,2)-(9,8) e (30,2)-(36,8)              | verde, 35% opacidade |
| Casa       | (17,12) — inicio do jogo                 | cinza, 35% opacidade |
| Comercio   | (21,12)                                  | cinza, 35% opacidade |
| Caminho    | (6,9)-(6,13), (7,13)-(32,13), (33,9)-(33,13) | cinza, 35% opacidade |

Sao 136 celulas andaveis, 98 delas de plantio. O `G` esconde o colorido junto com as
linhas do grid — as duas camadas ligam e desligam juntas. O colorido e desenhado uma unica vez numa
superficie e so reaproveitado, ja que as areas nao mudam durante o jogo.

## Personagem

- Comeca na celula (17, 12), em frente a porta da casa.
- Anda **de celula em celula**: cada passo vai do centro de uma celula ao centro da
  vizinha e so termina quando chega la — soltar a tecla no meio do caminho nao o deixa
  parado entre duas celulas. Segurando a tecla, os passos emendam sem engasgo.
- Apenas 4 direcoes: na diagonal, a horizontal tem prioridade.
- So entra em celula andavel; ao esbarrar ele vira para o lado tentado mas nao sai do lugar.
- Velocidade: 396 px/s, ou seja ~0,13s por celula (~8 celulas por segundo).
- Animacoes de 4 quadros cada. `run` nas 4 direcoes roda a 15 fps, acompanhando a velocidade;
  `stay` roda a 5 fps, bem mais devagar, porque e respiracao e nao passada.
- Parado, a animacao continua rodando: correr e ficar parado tem relogios separados, entao parar
  nao congela o personagem. Os quadros de `stay` sao todos de frente, entao parado ele sempre
  olha para frente, seja qual for a direcao em que estava correndo.
- `planting`, `harvest` e `fertilizing` tem 4 quadros a 8 fps (~0,5s). Enquanto rodam, o jogador nao anda
  nem aceita outra acao, e o efeito da acao so vale quando a animacao acaba.

## Plantas

Cada planta e desenhada ancorada na base da celula, com uma barrinha de crescimento logo
abaixo dela: ambar enquanto cresce, verde e cheia quando esta pronta. As plantas sao
desenhadas de cima para baixo, entao uma planta alta da linha de baixo passa por cima da
que esta atras.

## Painel inferior

Desenhado por cima das linhas 17-19 do mapa, que sao so grama e nao sao andaveis. Reune o
dia atual, a barra de estamina (vermelha abaixo de 25%), os 12 slots do inventario e as
linhas de informacao que antes ficavam soltas no rodape.
