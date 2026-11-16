"""
A mãozinha tocando dos vídeos da Shopee Vídeo (midia/mao_tocando.apng), no lugar das setinhas em
cascata (escolha do Rafael, 15/11, P231 1: DECISOES.md, Shopee Vídeo): a mãozinha amarela de
emoji, com o contorno branco e a sombra leve, desce, toca a borda de cima do cartão do produto
que o app mostra (P239 1), aperta e volta, uma volta por segundo, e do toque sai uma onda (branca, com um anel
no vermelho do destaque), inteira, deitada em volta da ponta do dedo (P238 1). Ela é sempre
amarela: a cor do painel não vale para ela. O quadro tem o
tamanho do TAMANHO_DA_SETA do edicao_video.py, com a margem transparente onde cabem o contorno e a
sombra, e a ponta do dedo, no toque, em PONTA (no vídeo, na borda de cima do cartão, pelo
CENTRO_DA_SETA do edicao_video.py). O desenho da
mão é o do emoji da fonte Noto Color Emoji (licença livre), o mesmo do exemplo que o Rafael
escolheu. Ferramenta do Claude, fora dos robôs: roda só para refazer ou mudar a mãozinha.

    python3 .claude/scripts/gerar_mao.py midia
"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTE = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
MAO = "\U0001F447"               # a mão apontando para baixo
QUADRO = (202, 160)              # o TAMANHO_DA_SETA do edicao_video.py
MARGEM = 10                      # o MARGEM_DA_SETA do edicao_video.py
PONTA = (105, 141)               # onde o dedo toca no quadro (no vídeo, x 146 e y 917: na borda do cartão)
ALTURA_DA_MAO = 113              # px do vídeo de 720x1280
DESCIDA = 21                     # quanto a mão desce até tocar
APERTO = 0.94                    # o tamanho da mão apertando
CONTORNO = 5                     # a grossura do contorno branco (a das setinhas)
SOMBRA = (2, 2)
BORRAO_DA_SOMBRA = 3
FORCA_DA_SOMBRA = 0.55
VERMELHO = (214, 24, 38)         # o VERMELHO_DO_DESTAQUE do edicao_video.py, no anel de dentro da onda
QUADROS_POR_SEGUNDO = 25
QUADROS_POR_VOLTA = 25           # uma volta por segundo
TOQUE = (0.4, 0.5)               # da volta: desce até 0,4, fica apertando até 0,5 e volta até o fim
ONDA = (8.0, 31.0)               # o raio da onda no toque e quanto ela cresce até o fim da volta
ACHATAMENTO = 0.30               # a onda é uma elipse deitada (o toque visto de lado), achatada para caber inteira
VEZES = 4                        # a onda é desenhada maior e reduzida, para a borda sair lisa


def contorno(alfa, grossura):
    """A máscara engordada `grossura` px para todos os lados, com a borda suave."""
    borrada = alfa.filter(ImageFilter.GaussianBlur(grossura))
    return borrada.point(lambda v: 255 if v > 18 else 0).filter(ImageFilter.GaussianBlur(0.8))


def mao():
    """A mão do emoji com o contorno branco e a sombra (RGBA) e o ponto da ponta do dedo nela."""
    fonte = ImageFont.truetype(FONTE, 109)
    tela = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(tela).text((10, 10), MAO, font=fonte, embedded_color=True)
    desenho = tela.crop(tela.getbbox())
    # A ponta do dedo: o meio dos pontos mais baixos do desenho.
    alfa = desenho.getchannel("A")
    largura, altura = desenho.size
    baixo = max(y for y in range(altura) for x in range(largura) if alfa.getpixel((x, y)) > 128)
    xs = [x for x in range(largura) if alfa.getpixel((x, baixo)) > 128]
    ponta = ((min(xs) + max(xs)) / 2, baixo)
    escala = ALTURA_DA_MAO / altura
    desenho = desenho.resize((round(largura * escala), ALTURA_DA_MAO), Image.LANCZOS)
    folga = CONTORNO + BORRAO_DA_SOMBRA + 3
    estilo = Image.new("RGBA", (desenho.width + 2 * folga, desenho.height + 2 * folga), (0, 0, 0, 0))
    forma = Image.new("L", estilo.size, 0)
    forma.paste(desenho.getchannel("A"), (folga, folga))
    borda = contorno(forma, CONTORNO)
    sombra = borda.filter(ImageFilter.GaussianBlur(BORRAO_DA_SOMBRA)).point(lambda v: int(v * FORCA_DA_SOMBRA))
    preta = Image.new("RGBA", estilo.size, (0, 0, 0, 255))
    preta.putalpha(sombra)
    estilo.alpha_composite(preta, SOMBRA)
    branca = Image.new("RGBA", estilo.size, (255, 255, 255, 255))
    branca.putalpha(borda)
    estilo.alpha_composite(branca)
    estilo.alpha_composite(desenho, (folga, folga))
    return estilo, (folga + ponta[0] * escala, folga + ponta[1] * escala)


def onda(k):
    """
    A onda do toque na fração k (0 a 1) do caminho dela, no quadro todo (RGBA): o anel inteiro, deitado em volta
    da ponta do dedo, atrás da mão (P238 1: a metade de cima só, com a mão tampando o meio, parecia um círculo
    quebrado). Ele é achatado e cresce só até caber inteiro no quadro; no vídeo, a frente dele passa por baixo
    do cartão do produto, que o app desenha por cima (P239 1).
    """
    grande = Image.new("RGBA", (QUADRO[0] * VEZES, QUADRO[1] * VEZES), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(grande)
    raio = (ONDA[0] + ONDA[1] * k) * VEZES
    x, y = PONTA[0] * VEZES, PONTA[1] * VEZES
    forca = int(230 * (1 - k))
    branca, vermelha = 5 * VEZES, 3 * VEZES
    desenho.ellipse((x - raio, y - raio * ACHATAMENTO, x + raio, y + raio * ACHATAMENTO),
                    outline=(255, 255, 255, forca), width=branca)
    dentro = raio - branca
    if dentro > vermelha:
        desenho.ellipse((x - dentro, y - dentro * ACHATAMENTO, x + dentro, y + dentro * ACHATAMENTO),
                        outline=VERMELHO + (int(forca * 0.8),), width=vermelha)
    return grande.resize(QUADRO, Image.LANCZOS)


def quadros():
    """Os quadros de uma volta: a mão desce, toca (com a onda), aperta e volta."""
    estilo, ponta = mao()
    lista = []
    for n in range(QUADROS_POR_VOLTA):
        t = n / QUADROS_POR_VOLTA
        aperto = 1.0
        if t < TOQUE[0]:
            desce = DESCIDA * math.sin(t / TOQUE[0] * math.pi / 2)
        elif t < TOQUE[1]:
            desce, aperto = DESCIDA, APERTO
        else:
            desce = DESCIDA * math.cos((t - TOQUE[1]) / (1 - TOQUE[1]) * math.pi / 2)
        tela = Image.new("RGBA", QUADRO, (0, 0, 0, 0))
        if t >= TOQUE[0]:
            tela.alpha_composite(onda((t - TOQUE[0]) / (1 - TOQUE[0])))
        img = estilo
        if aperto != 1.0:
            img = estilo.resize((round(estilo.width * aperto), round(estilo.height * aperto)), Image.LANCZOS)
        # A ponta do dedo fica no lugar do toque (apertando, a mão encolhe em volta dela).
        x = round(PONTA[0] - ponta[0] * aperto)
        y = round(PONTA[1] - DESCIDA + desce - ponta[1] * aperto)
        tela.alpha_composite(img, (x, y))
        lista.append(tela)
    return lista


def main(pasta):
    destino = os.path.join(pasta, "mao_tocando.apng")
    lista = quadros()
    # Cada quadro inteiro, sem somar com o de antes: disposal 1 (limpa) e blend 0 (substitui).
    lista[0].save(destino, format="PNG", save_all=True, append_images=lista[1:],
                  duration=1000 // QUADROS_POR_SEGUNDO, loop=0, disposal=1, blend=0, optimize=True)
    print(f"{destino}: {len(lista)} quadros, {QUADRO[0]}x{QUADRO[1]}, {os.path.getsize(destino) // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "midia")
