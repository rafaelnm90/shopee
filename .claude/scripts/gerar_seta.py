"""
As setinhas em cascata dos vídeos da Shopee Vídeo (midia/setas_em_cascata.apng): três setinhas
para baixo, uma embaixo da outra, no laranja da Shopee, com um contorno branco e uma sombra leve,
acendendo de cima para baixo, uma volta por segundo, logo acima do cartão do produto que o app
mostra (escolhas do Rafael, 02/11: P127, o laranja com o contorno; P130, as setinhas em cascata no
lugar da seta do arquivo dele: DECISOES.md, Shopee Vídeo). O quadro tem o tamanho do
TAMANHO_DA_SETA do edicao_video.py, com a margem transparente onde cabem o contorno e a sombra, e
a ponta da setinha de baixo na altura do pé da legenda da fala. Ferramenta do Claude, fora dos
robôs: roda só para refazer ou mudar as setinhas.

    python3 .claude/scripts/gerar_seta.py midia
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

LARANJA = (238, 77, 45)          # o LARANJA_DA_SHOPEE do edicao_video.py (o teste confere)
QUADRO = (202, 160)              # o TAMANHO_DA_SETA do edicao_video.py
MARGEM = 10                      # o MARGEM_DA_SETA do edicao_video.py
CONTORNO = 5                     # a grossura do contorno branco, em px do vídeo de 720
SOMBRA = (2, 2)                  # o deslocamento da sombra
BORRAO_DA_SOMBRA = 3
FORCA_DA_SOMBRA = 0.55           # de 0 a 1: a sombra é leve, meio transparente
SETINHA = (80, 36)               # largura e altura de cada setinha, sem o contorno
TRACO = 14                       # a grossura do traço da setinha
PASSO = 36                       # de uma setinha para a de baixo
QUADROS_POR_SEGUNDO = 25
QUADROS_POR_VOLTA = 25           # uma volta da cascata por segundo
APAGADA = 0.25                   # a setinha apagada ainda aparece um pouco
PASSAGEM = 0.08                  # da volta: o tempo em que uma apaga e a de baixo acende


def contorno(alfa, grossura):
    """A máscara engordada `grossura` px para todos os lados, com a borda suave."""
    borrada = alfa.filter(ImageFilter.GaussianBlur(grossura))
    return borrada.point(lambda v: 255 if v > 18 else 0).filter(ImageFilter.GaussianBlur(0.8))


def com_estilo(alfa):
    """A forma (máscara L) no laranja, com o contorno branco e a sombra, em RGBA do mesmo tamanho."""
    saida = Image.new("RGBA", alfa.size, (0, 0, 0, 0))
    if not alfa.getbbox():
        return saida
    borda = contorno(alfa, CONTORNO)
    sombra = borda.filter(ImageFilter.GaussianBlur(BORRAO_DA_SOMBRA)).point(lambda v: int(v * FORCA_DA_SOMBRA))
    preta = Image.new("RGBA", alfa.size, (0, 0, 0, 255))
    preta.putalpha(sombra)
    saida.alpha_composite(preta, SOMBRA)
    branca = Image.new("RGBA", alfa.size, (255, 255, 255, 255))
    branca.putalpha(borda)
    saida.alpha_composite(branca)
    laranja = Image.new("RGBA", alfa.size, LARANJA + (255,))
    laranja.putalpha(alfa)
    saida.alpha_composite(laranja)
    return saida


def setinha():
    """Uma setinha para baixo (o V com as pontas redondas) com o estilo, num quadro com a margem."""
    vezes = 4
    largura, altura = SETINHA[0] * vezes, SETINHA[1] * vezes
    traco = TRACO * vezes
    mascara = Image.new("L", (largura, altura), 0)
    desenho = ImageDraw.Draw(mascara)
    pontos = [(traco // 2, traco // 2), (largura // 2, altura - traco // 2), (largura - traco // 2, traco // 2)]
    desenho.line(pontos, fill=255, width=traco, joint="curve")
    for x, y in pontos:
        desenho.ellipse((x - traco // 2, y - traco // 2, x + traco // 2, y + traco // 2), fill=255)
    forma = Image.new("L", (SETINHA[0] + 2 * MARGEM, SETINHA[1] + 2 * MARGEM), 0)
    forma.paste(mascara.resize(SETINHA, Image.LANCZOS), (MARGEM, MARGEM))
    return com_estilo(forma)


def luz(fase):
    """
    Quanto a setinha acende (de APAGADA a 1) na fase da volta, contada a partir da vez dela: acesa
    no terço dela, com a PASSAGEM para acender e para apagar. Sempre há uma acesa: quando uma
    apaga, a de baixo acende ao mesmo tempo.
    """
    if fase < PASSAGEM:
        quanto = fase / PASSAGEM
    elif fase < 1 / 3:
        quanto = 1.0
    elif fase < 1 / 3 + PASSAGEM:
        quanto = 1 - (fase - 1 / 3) / PASSAGEM
    else:
        quanto = 0.0
    return APAGADA + (1 - APAGADA) * quanto


def quadros():
    """Os quadros de uma volta da cascata: cada setinha acende na sua vez, de cima para baixo."""
    uma = setinha()
    x = (QUADRO[0] - uma.width) // 2
    # A ponta da setinha de baixo na altura do pé da legenda: a margem de baixo fica para a sombra.
    topo = QUADRO[1] - MARGEM - uma.height - 2 * PASSO
    lista = []
    for n in range(QUADROS_POR_VOLTA):
        tela = Image.new("RGBA", QUADRO, (0, 0, 0, 0))
        for i in range(3):
            # A fase em números inteiros (terços de quadro), sem o arredondamento da divisão.
            volta = 3 * QUADROS_POR_VOLTA
            quanto = luz(((3 * n - i * QUADROS_POR_VOLTA) % volta) / volta)
            acesa = uma.copy()
            acesa.putalpha(acesa.getchannel("A").point(lambda v, quanto=quanto: int(v * quanto)))
            tela.alpha_composite(acesa, (x, topo + i * PASSO))
        lista.append(tela)
    return lista


def main(pasta):
    destino = os.path.join(pasta, "setas_em_cascata.apng")
    lista = quadros()
    # Cada quadro inteiro, sem somar com o de antes: disposal 1 (limpa) e blend 0 (substitui).
    lista[0].save(destino, format="PNG", save_all=True, append_images=lista[1:],
                  duration=1000 // QUADROS_POR_SEGUNDO, loop=0, disposal=1, blend=0, optimize=True)
    print(f"{destino}: {len(lista)} quadros, {QUADRO[0]}x{QUADRO[1]}, {os.path.getsize(destino) // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "midia")
