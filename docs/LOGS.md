# Logs por run

Uma **run** é uma partida: começa no dia 1 e termina ao perder, ao reiniciar com `R` ou ao
fechar o jogo. Cada run gera **dois arquivos** em `logs/`, com o mesmo nome e extensões
diferentes:

```
run_<id>_semente<N>_<AAAA-MM-DD_HH-MM-SS>.log   texto, igual ao que sai no console
run_<id>_semente<N>_<AAAA-MM-DD_HH-MM-SS>.csv   uma linha por ação, movimentação inclusa
```

O `<id>` são 8 caracteres hexadecimais sorteados no início da run, o `<N>` é a semente do
cenário (ver [SEMENTE.md](SEMENTE.md)) e o datetime é o momento em que ela começou. Reiniciar
com `R` fecha o par anterior e abre um novo — os arquivos de uma run nunca se misturam.

A semente vai no nome de propósito: é o que permite escolher qual partida repetir sem abrir
arquivo nenhum. Ela também aparece na primeira linha do `.log`, junto do `id`. Duas runs com a
mesma semente são o mesmo cenário, mas partidas diferentes — o `id` é o que as separa.

Implementação em [`farm/run_log.py`](../farm/run_log.py). O arquivo de texto é só um
`FileHandler` pendurado no logger raiz enquanto a run dura; o `main.py` cuida apenas do
console.

## Colunas do CSV

| Coluna | Conteúdo |
| --- | --- |
| `timestamp` | data e hora com milissegundos |
| `segundos` | tempo desde o início da run |
| `dia` | dia do jogo quando a ação aconteceu |
| `acao` | ver tabela abaixo |
| `de_col`, `de_lin` | célula de origem — só no movimento |
| `para_col`, `para_lin` | célula onde a ação aconteceu |
| `item` | cultura, `fertilizante` ou o tipo do menu |
| `quantidade` | quantas unidades entraram ou saíram; na promoção, o desconto |
| `preco` | moedas por unidade — só em `comprar`, `vender` e `promocao` |
| `estamina` | estamina **depois** da ação |

## Ações registradas

| `acao` | Quando |
| --- | --- |
| `inicio` | primeira linha da run |
| `mover` | cada célula concluída (esbarrar não gera linha) |
| `abrir_menu` | menu de semente ou de fertilizante aberto |
| `cancelar_menu` | menu fechado com ESC, sem escolher |
| `plantar` | fim da animação de plantio |
| `fertilizar` | fertilizante usado |
| `colher` | fim da animação de colheita |
| `estragou` | uma planta apodreceu na virada do dia |
| `remover` | planta estragada arrancada da célula |
| `vender` | uma unidade vendida na loja |
| `comprar` | uma unidade comprada na loja |
| `dormir` | dia avançou |
| `promocao` | uma linha por item promovido, a cada sorteio diário |
| `derrota` | estamina chegou a zero |
| `saiu` | jogo fechado |

Cada linha é gravada com `flush` imediato, para o arquivo continuar completo mesmo se a
janela for fechada no meio.

## Exemplo

```csv
timestamp,segundos,dia,acao,de_col,de_lin,para_col,para_lin,item,quantidade,preco,estamina
2026-08-29 17:23:49.288,0.033,1,inicio,,,17,12,,,,150
2026-08-29 17:23:49.288,0.033,1,mover,17,12,17,13,,,,149
2026-08-29 17:23:49.989,0.734,2,plantar,,,6,8,batata,1,,131
2026-08-29 17:23:50.682,1.427,5,colher,,,6,8,batata,1,,130
2026-08-29 17:23:51.100,1.845,5,vender,,,21,12,batata,1,6,130
2026-08-29 17:23:51.900,2.645,6,promocao,,,,,semente batata,3,1,150
2026-08-29 17:23:52.026,2.771,6,derrota,,,6,7,,,,0
```

Como cada célula andada vira uma linha com a estamina do momento, dá para reconstruir o
trajeto inteiro da partida a partir do CSV.

## Histórico de células estragadas

Fora dos arquivos por run existe um **acumulado entre partidas**, em
`logs/celulas_estragadas.csv`, com uma linha por planta que apodreceu:
`timestamp, run_id, dia, col, lin, cultura`. Ele **não** é apagado no `R` nem ao fechar o jogo —
o `run_id` é o que separa uma partida da outra. Nada disso aparece na tela para o jogador; o
registro existe para uma mecânica futura de solo gasto.

## Reconstruindo estado a partir do CSV

O caixa diário da loja também sai daqui, sem precisar de coluna própria: dentro de um mesmo
`dia`, o saldo é `200 + soma(preco das linhas comprar) − soma(preco das linhas vender)`.
