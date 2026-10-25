#!/usr/bin/env python3
"""
Vídeo feito por IA a partir da foto do anúncio do produto, para a Shopee Vídeo ter
conteúdo do próprio Rafael em vez de vídeo copiado de outro canal. Por enquanto é só o
teste que ele pediu (25/10, P34): um vídeo de uns 8 s, que chega só no privado dele;
nada é postado. A Shopee aceita vídeo de IA quando o produto aparece igual ao anúncio
(cor, tamanho, material e formato) e com o rótulo de IA.

Usado pelo workflow video_ia.yml (só à mão). O log do Actions é público: saem só nomes de
modelo, estados e números; o nome do produto, a foto e o vídeo vão só no privado.

    python3 video_ia.py modelos   # os modelos de vídeo que a chave do Google enxerga
    python3 video_ia.py testar    # 1 vídeo de teste do próximo produto da fonte, no privado
"""
import asyncio
import logging
import os
import sys
import time

from google.genai import types

import api_gemini
import assistente_shopee_video as assistente
import avisar_rafael
import db
import postador_shopee_video as ps
import videos

PASTA = os.path.join(os.path.expanduser("~"), "shopee_video", "video_ia")
# O mais barato primeiro: o teste é para ver se serve, não a melhor qualidade.
PREFERENCIA = ("lite", "fast", "")
# Quantos produtos da fonte o teste tenta até achar um com a foto do anúncio.
PRODUTOS_TENTADOS = 10
# O Google gera em uns minutos; depois disso o teste desiste.
ESPERA_MAXIMA = 600
INTERVALO_DA_CONSULTA = 10
# Em inglês, como o gerador entende melhor. O produto igual ao anúncio é a regra da
# Shopee para vídeo de IA; pessoas, texto e logo novos ficam de fora.
PROMPT = (
    "Vertical 9:16 product showcase video of the exact product shown in the reference image. "
    "Keep the product identical to the image: same shape, color, material, size, packaging and printed text. "
    "Smooth, slow camera movement around the product on a clean, well-lit tabletop with soft natural light. "
    "Realistic, high quality, no people, no faces, no added text, no added logos, no other products, "
    "no exaggerated effects."
)


def modelos_de_video():
    """Os modelos de vídeo (Veo) que a chave do .env enxerga, só os nomes."""
    nomes = (m.name.split("/")[-1] for m in api_gemini.client_genai.models.list())
    return sorted(n for n in nomes if n.startswith("veo"))


def escolher_modelo(nomes):
    """O mais novo e mais barato da lista: Veo 3 antes do 2; Lite, depois Fast, depois o resto."""
    for geracao in ("veo-3", "veo-2"):
        da_geracao = sorted((n for n in nomes if n.startswith(geracao)), reverse=True)
        for tipo in PREFERENCIA:
            escolhido = next((n for n in da_geracao if tipo in n), None)
            if escolhido:
                return escolhido
    return None


def produto_para_teste():
    """(nome, foto em bytes) do primeiro dos próximos vídeos da fonte que tem a foto do anúncio; None sem nenhum."""
    fonte = (db.ler_config("shopee_video", {}) or {}).get("fonte", assistente.FONTE_PADRAO)
    for _, _, link, _ in assistente.candidatos_nao_usados(fonte)[:PRODUTOS_TENTADOS]:
        if not link:
            continue
        nome = ps.nome_do_produto({"link": link})
        foto = ps.foto_do_produto({"link": link}) if nome else None
        if foto:
            return nome, foto
    return None


def gerar(modelo, foto, destino):
    """
    Gera o vídeo pela foto e grava em destino. Devolve "" quando deu certo, ou o motivo
    fixo de não ter dado (sem nada do produto: o motivo vai para o log público).
    """
    operacao = api_gemini.client_genai.models.generate_videos(
        model=modelo,
        source=types.GenerateVideosSource(prompt=PROMPT, image=types.Image(image_bytes=foto, mime_type="image/jpeg")),
        config=types.GenerateVideosConfig(aspect_ratio="9:16", number_of_videos=1))
    inicio = time.monotonic()
    while not operacao.done:
        if time.monotonic() - inicio > ESPERA_MAXIMA:
            return f"o Google não terminou em {ESPERA_MAXIMA // 60} min"
        time.sleep(INTERVALO_DA_CONSULTA)
        operacao = api_gemini.client_genai.operations.get(operacao)
    if operacao.error:
        return f"o Google recusou (código {(operacao.error or {}).get('code', '?')})"
    resposta = operacao.response or operacao.result
    gerados = (resposta.generated_videos or []) if resposta else []
    if not gerados:
        filtrados = getattr(resposta, "rai_media_filtered_count", 0) if resposta else 0
        return f"nenhum vídeo veio ({filtrados or 0} barrado(s) pelo filtro do Google)"
    api_gemini.client_genai.files.download(file=gerados[0].video)
    gerados[0].video.save(destino)
    return ""


def testar():
    nomes = modelos_de_video()
    modelo = escolher_modelo(nomes)
    print(f"Modelos de vídeo na chave: {len(nomes)}; para o teste: {modelo or 'nenhum'}")
    if not modelo:
        print("A chave não enxerga nenhum modelo de vídeo: o teste não roda.")
        return 1
    produto = produto_para_teste()
    if not produto:
        print(f"Nenhum dos próximos {PRODUTOS_TENTADOS} vídeos da fonte tem a foto do anúncio: o teste não roda.")
        return 1
    nome, foto = produto
    os.makedirs(PASTA, exist_ok=True)
    destino = os.path.join(PASTA, "teste.mp4")
    inicio = time.monotonic()
    motivo = gerar(modelo, foto, destino)
    if motivo:
        print(f"Não gerou: {motivo}")
        return 1
    largura, altura = asyncio.run(videos.dimensoes(destino))
    print(f"Gerado em {time.monotonic() - inicio:.0f} s: {largura}x{altura}, {os.path.getsize(destino) // 1024} KB")
    legenda = (f"🎬 Teste de vídeo feito por IA (P34), a partir da foto do anúncio de: {nome}\n"
               f"Modelo: {modelo}. Não foi postado: me diga se o produto ficou igual ao anúncio e se você postaria.")
    enviado = avisar_rafael.mandar_video(destino, legenda)
    print(f"Mandado no privado do Rafael: {'sim' if enviado else 'não (grande demais ou o Telegram recusou)'}")
    return 0 if enviado else 1


def main(argumentos):
    if argumentos == ["modelos"]:
        nomes = modelos_de_video()
        print(f"Modelos de vídeo na chave: {len(nomes)}")
        for nome in nomes:
            print(f"   {nome}")
        print(f"Para o teste: {escolher_modelo(nomes) or 'nenhum'}")
        return 0
    if argumentos == ["testar"]:
        # Os módulos logam nomes e links; aqui o log é público, e o resultado sai pelos prints.
        logging.disable(logging.CRITICAL)
        try:
            return testar()
        finally:
            logging.disable(logging.NOTSET)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
