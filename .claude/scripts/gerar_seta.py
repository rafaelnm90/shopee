"""
A seta laranja dos vídeos da Shopee Vídeo (midia/seta_laranja.apng), feita a partir da seta do
Rafael (midia/seta_da_shopee.apng, a do LumaFusion dele, sem o fundo): a mesma seta, quadro a
quadro e no mesmo tempo (a entrada e o pulso), no laranja da Shopee, com um contorno branco e
uma sombra leve, para destacar no fundo claro e no escuro (escolha do Rafael, 02/11, P127:
DECISOES.md, Shopee Vídeo). O quadro ganha MARGEM px transparentes de cada lado, onde cabem o
contorno e a sombra. Ferramenta do Claude, fora dos robôs: roda só para refazer ou mudar a seta.

    python3 .claude/scripts/gerar_seta.py midia
"""
import os
import sys

from PIL import Image, ImageFilter, ImageSequence

LARANJA = (238, 77, 45)          # o LARANJA_DA_SHOPEE do edicao_video.py (o teste confere)
MARGEM = 10                      # o MARGEM_DA_SETA do edicao_video.py
CONTORNO = 5                     # a grossura do contorno branco, em px do vídeo de 720
SOMBRA = (2, 2)                  # o deslocamento da sombra
BORRAO_DA_SOMBRA = 3
FORCA_DA_SOMBRA = 0.55           # de 0 a 1: a sombra é leve, meio transparente


def contorno(alfa, grossura):
    """A máscara da seta engordada `grossura` px para todos os lados, com a borda suave."""
    borrada = alfa.filter(ImageFilter.GaussianBlur(grossura))
    return borrada.point(lambda v: 255 if v > 18 else 0).filter(ImageFilter.GaussianBlur(0.8))


def quadro_laranja(quadro):
    """Um quadro da seta (RGBA) no laranja, com o contorno branco e a sombra, na margem transparente."""
    largura, altura = quadro.size
    tamanho = (largura + 2 * MARGEM, altura + 2 * MARGEM)
    alfa = Image.new("L", tamanho, 0)
    alfa.paste(quadro.getchannel("A"), (MARGEM, MARGEM))
    saida = Image.new("RGBA", tamanho, (0, 0, 0, 0))
    if not alfa.getbbox():
        return saida
    borda = contorno(alfa, CONTORNO)
    sombra = borda.filter(ImageFilter.GaussianBlur(BORRAO_DA_SOMBRA)).point(lambda v: int(v * FORCA_DA_SOMBRA))
    preta = Image.new("RGBA", tamanho, (0, 0, 0, 255))
    preta.putalpha(sombra)
    saida.alpha_composite(preta, SOMBRA)
    branca = Image.new("RGBA", tamanho, (255, 255, 255, 255))
    branca.putalpha(borda)
    saida.alpha_composite(branca)
    laranja = Image.new("RGBA", tamanho, LARANJA + (255,))
    laranja.putalpha(alfa)
    saida.alpha_composite(laranja)
    return saida


def main(pasta):
    origem = os.path.join(pasta, "seta_da_shopee.apng")
    destino = os.path.join(pasta, "seta_laranja.apng")
    with Image.open(origem) as seta:
        duracao = seta.info.get("duration", 40)
        quadros = [quadro_laranja(q.convert("RGBA")) for q in ImageSequence.Iterator(seta)]
    # Cada quadro inteiro, sem somar com o de antes: disposal 1 (limpa) e blend 0 (substitui).
    quadros[0].save(destino, format="PNG", save_all=True, append_images=quadros[1:], duration=duracao,
                    loop=0, disposal=1, blend=0, optimize=True)
    print(f"{destino}: {len(quadros)} quadros, {quadros[0].size[0]}x{quadros[0].size[1]}, "
          f"{os.path.getsize(destino) // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "midia")
