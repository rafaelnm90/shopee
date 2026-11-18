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
    python3 video_ia.py produtos  # o que a API de afiliado devolve para o produto do vídeo de IA (P234 1)
"""
import asyncio
import json
import logging
import os
import re
import statistics
import sys
import time

import aiohttp
from google.genai import types

import api_gemini
import api_shopee
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


# O que os modelos de vídeo aceitam (o Veo gera por "predictLongRunning"); os de texto e
# imagem ficam de fora.
ACOES_DE_VIDEO = ("predictLongRunning", "generateVideos")


def modelos_de_video():
    """Os modelos de vídeo que a chave do .env enxerga (o nome "veo" ou a ação de gerar vídeo), só os nomes."""
    return sorted(m.name.split("/")[-1] for m in api_gemini.client_genai.models.list()
                  if m.name.split("/")[-1].startswith("veo")
                  or any(acao in (m.supported_actions or []) for acao in ACOES_DE_VIDEO))


def acoes_da_chave():
    """{ação: quantos modelos} de tudo o que a chave enxerga: mostra se ela é de uso pago (vídeo, imagem) ou só texto."""
    contagem = {}
    for modelo in api_gemini.client_genai.models.list():
        for acao in modelo.supported_actions or []:
            contagem[acao] = contagem.get(acao, 0) + 1
    return contagem


def escolher_modelo(nomes):
    """O mais novo e mais barato da lista: Veo 3 antes do 2 e dos outros; Lite, depois Fast, depois o resto."""
    for geracao in ("veo-3", "veo-2", ""):
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


# --- A sonda da API de afiliado: de onde tirar o produto do vídeo de IA (P234 1) ---
# O Rafael escolheu (15/11, P234 1) que o produto do vídeo de IA do dia venha da API de afiliado (os produtos em
# alta, de nota alta, que pagam o mínimo por venda), sem depender do Viral. A sonda mostra o que a API devolve
# com a chave dele em cada jeito de pedir a lista: sem palavra de busca (os em alta, os de maior comissão, os mais
# vendidos, a 2ª página, 100 por página) e com a 1ª palavra-chave dos primeiros nichos dos Achadinhos. Só
# contagens e rótulos fixos: nenhum nome, link, palavra de busca ou preço de produto vai ao log, que é público.
CAMPOS_DA_SONDA = "itemId productName priceMin commissionRate ratingStar sales imageUrl productLink"
PAGINA_DA_SONDA = " pageInfo { page limit hasNextPage }"
# (o rótulo fixo da lista, os argumentos do productOfferV2, o que pedir além dos produtos)
LISTAS_DA_SONDA = (
    ("em alta (listType 2)", "listType: 2, limit: 50", ""),
    ("em alta, 2ª página", "listType: 2, limit: 50, page: 2", ""),
    ("em alta, por mais vendidos", "listType: 2, sortType: 2, limit: 50", ""),
    ("maior comissão (listType 1)", "listType: 1, limit: 50", ""),
    ("todos, por mais vendidos", "sortType: 2, limit: 50", ""),
    ("todos, por maior comissão", "sortType: 5, limit: 50", ""),
    ("em alta, 100 por página", "listType: 2, limit: 100", ""),
    ("em alta, com a página informada", "listType: 2, limit: 50", PAGINA_DA_SONDA),
)
NICHOS_NA_SONDA = 3
NOTA_DA_SONDA = 4.5
TENTATIVAS_DA_SONDA = 4
PRODUTO_NO_LINK = re.compile(r"/product/\d+/\d+")
FAIXAS_DE_PRECO = ((50, "até R$ 50"), (200, "de R$ 50 a R$ 200"), (float("inf"), "acima de R$ 200"))
FAIXAS_POR_VENDA = ((5, "de R$ 2 a R$ 5"), (15, "de R$ 5 a R$ 15"), (float("inf"), "acima de R$ 15"))


def erro_da_api(erros):
    """O erro que a API devolveu, para o log público: o código e a mensagem dela sem números nem sequências longas."""
    primeiro = erros[0] if isinstance(erros, list) and erros and isinstance(erros[0], dict) else {}
    mensagem = re.sub(r"[0-9A-Fa-f]{16,}|\d+", "#", " ".join(str(primeiro.get("message") or "").split()))[:120]
    return f"{api_shopee.rotulo_do_codigo(api_shopee._codigo_do_erro(erros))}: {mensagem or 'sem mensagem'}"


async def pedir_lista(argumentos, extra=""):
    """
    (produtos, erro, tem próxima página) do productOfferV2 com esses argumentos; erro é "" quando a API
    respondeu. O erro de sistema da Shopee tenta de novo, como na busca de ofertas.
    """
    consulta = f"query {{ productOfferV2({argumentos}) {{ nodes {{ {CAMPOS_DA_SONDA} }}{extra} }} }}"
    for tentativa in range(1, TENTATIVAS_DA_SONDA + 1):
        # A assinatura leva a hora: cada tentativa assina de novo.
        headers, corpo = api_shopee.gerar_headers_e_payload({"query": consulta})
        try:
            async with aiohttp.ClientSession() as sessao:
                async with sessao.post(assistente.URL_API, headers=headers, data=corpo) as resposta:
                    estado = resposta.status
                    dados = await resposta.json(content_type=None)
        except Exception as e:
            return [], f"sem resposta ({type(e).__name__})", None
        erros = (dados or {}).get("errors")
        if (erros and api_shopee._codigo_do_erro(erros) == api_shopee.CODIGO_DO_ERRO_DE_SISTEMA
                and tentativa < TENTATIVAS_DA_SONDA):
            await asyncio.sleep(api_shopee.ESPERA_NO_ERRO_DE_SISTEMA * tentativa)
            continue
        if erros:
            return [], erro_da_api(erros), None
        if estado != 200:
            return [], f"status {estado}", None
        lista = ((dados or {}).get("data") or {}).get("productOfferV2") or {}
        return lista.get("nodes") or [], "", (lista.get("pageInfo") or {}).get("hasNextPage")
    return [], "sem resposta", None


def contagens_da_lista(produtos, ja_postados, valor_por_venda, minimo):
    """
    As linhas de uma lista da sonda, só com números e rótulos fixos: quantos têm a nota, quantos pagam o
    mínimo por venda, quantos passam nas duas coisas (e, desses, quantos ainda não foram postados), a foto, o
    link de produto, as medianas das vendas e da nota e as faixas do preço e do que pagam por venda.
    """
    precos = {rotulo: 0 for _, rotulo in FAIXAS_DE_PRECO}
    por_venda = {rotulo: 0 for _, rotulo in FAIXAS_POR_VENDA}
    notas, vendas = [], []
    com_nota = pagam = as_duas = novos = com_foto = com_link = 0
    for produto in produtos:
        preco = assistente._numero(produto.get("priceMin"))
        valor = valor_por_venda(preco, assistente._numero(produto.get("commissionRate")) * 100)
        nota = assistente._numero(produto.get("ratingStar"))
        notas.append(nota)
        vendas.append(int(assistente._numero(produto.get("sales"))))
        com_nota += nota >= NOTA_DA_SONDA
        pagam += valor >= minimo
        com_foto += bool(produto.get("imageUrl"))
        com_link += bool(PRODUTO_NO_LINK.search(produto.get("productLink") or ""))
        precos[next(rotulo for teto, rotulo in FAIXAS_DE_PRECO if preco <= teto)] += 1
        if nota >= NOTA_DA_SONDA and valor >= minimo:
            as_duas += 1
            novos += str(produto.get("itemId") or "") not in ja_postados
            por_venda[next(rotulo for teto, rotulo in FAIXAS_POR_VENDA if valor <= teto)] += 1
    nota_do_meio = f"{statistics.median(notas):.1f}".replace(".", ",") if notas else "-"
    return [
        f"   nota {str(NOTA_DA_SONDA).replace('.', ',')} ou mais: {com_nota} | pagam o mínimo por venda: {pagam} | "
        f"as duas coisas: {as_duas} (ainda não postados: {novos})",
        f"   com a foto: {com_foto} | com o link do produto: {com_link} | vendas (mediana): "
        f"{int(statistics.median(vendas)) if vendas else '-'} | nota (mediana): {nota_do_meio}",
        "   preço: " + " | ".join(f"{rotulo}: {n}" for rotulo, n in precos.items()),
        "   por venda, entre os das duas coisas: " + " | ".join(f"{rotulo}: {n}" for rotulo, n in por_venda.items()),
    ]


def palavras_dos_nichos():
    """(quantos nichos, quantas palavras-chave, a 1ª palavra dos primeiros NICHOS_NA_SONDA nichos) dos Achadinhos."""
    nichos = (db.ler_config("achadinhos_config", {}) or {}).get("nichos") or []
    palavras = [[str(p).strip() for p in (nicho.get("keywords") or []) if str(p).strip()] for nicho in nichos]
    return len(nichos), sum(len(p) for p in palavras), [p[0] for p in palavras if p][:NICHOS_NA_SONDA]


def sondar_produtos():
    """A sonda inteira: cada lista sem palavra de busca e a busca de uma palavra de cada nicho, em contagens."""
    # Só aqui: as outras ações não precisam do robô.
    import robo_shopee_video as robo
    ja_postados = robo.produtos_ja_postados()
    primeira = None
    for rotulo, argumentos, extra in LISTAS_DA_SONDA:
        produtos, erro, proxima = asyncio.run(pedir_lista(argumentos, extra))
        if erro:
            print(f"== {rotulo}: a API recusou ({erro})")
            continue
        itens = {str(p.get("itemId") or "") for p in produtos}
        pagina = "" if proxima is None else f" | tem próxima página: {'sim' if proxima else 'não'}"
        print(f"== {rotulo}: {len(produtos)} produto(s), {len(itens)} diferente(s){pagina}")
        for linha in contagens_da_lista(produtos, ja_postados, robo.valor_por_venda, robo.MINIMO_POR_VENDA):
            print(linha)
        if primeira is None:
            primeira = itens
        else:
            print(f"   em comum com a 1ª lista: {len(itens & primeira)}")
    nichos, palavras, primeiras = palavras_dos_nichos()
    print(f"== Nichos dos Achadinhos: {nichos} nicho(s), {palavras} palavra(s)-chave")
    for posicao, palavra in enumerate(primeiras, 1):
        argumentos = f"keyword: {json.dumps(palavra, ensure_ascii=False)}, sortType: 2, limit: 50"
        produtos, erro, _ = asyncio.run(pedir_lista(argumentos))
        if erro:
            print(f"== nicho nº {posicao}, 1ª palavra, por mais vendidos: a API recusou ({erro})")
            continue
        print(f"== nicho nº {posicao}, 1ª palavra, por mais vendidos: {len(produtos)} produto(s)")
        for linha in contagens_da_lista(produtos, ja_postados, robo.valor_por_venda, robo.MINIMO_POR_VENDA):
            print(linha)
    print(f"== A escolha do robô agora: {escolha_do_robo(robo, ja_postados)}")
    return 0


def escolha_do_robo(robo, ja_postados):
    """
    O que a escolha do produto do vídeo de IA acharia agora (P234 1 e P252 1), sem a IA e sem mudar nada: de que
    lista viriam os produtos, as contagens da peneira do robô (com os que já tiveram vídeo ou a foto recusada de fora)
    e, dos novos, quantos passam em cada corte do 2º nível e nos três, pelos links do Espião já seguidos (os outros
    ficam sem seguir aqui, e a conta diz quantos).
    """
    try:
        ofertas, origem = robo.ofertas_para_o_video_de_ia()
    except api_shopee.BuscaNegada as e:
        return f"a API negou a lista ({e})"
    bons, contagem = robo.candidatos_do_video_de_ia(
        ofertas, ja_postados, robo.flow.itens_gerados() + robo.flow.fotos_recusadas())
    canais, sem_seguir = asyncio.run(robo.tendencia.canais_do_espiao(seguir=False))
    filtros = robo.filtros_do_video_de_ia()
    _ordem, no_segundo = robo.pelos_dois_niveis(bons, canais, filtros)
    vendidos = sum(1 for bom in bons if bom["vendas"] >= filtros["video_ia_vendidos_minimos"])
    preco = sum(1 for bom in bons if bom["preco"] >= filtros["video_ia_preco_minimo"])
    poucos = sum(1 for bom in bons if canais.get(bom["item"], 0) <= filtros["video_ia_canais_maximos"])
    return (f"{origem}: {contagem['lista']} da lista; {contagem['nota']} com a nota; {contagem['minimo']} pagam o "
            f"mínimo; {contagem['novos']} novos; dos novos, {vendidos} com os vendidos, {preco} com o preço e {poucos} "
            f"com os canais do Espião; {no_segundo} no 2º nível ({sem_seguir} link(s) do Espião sem seguir)")


def main(argumentos):
    if argumentos == ["modelos"]:
        nomes = modelos_de_video()
        print(f"Modelos de vídeo na chave: {len(nomes)}")
        for nome in nomes:
            print(f"   {nome}")
        print("Ações de todos os modelos da chave: "
              + ", ".join(f"{acao} {n}" for acao, n in sorted(acoes_da_chave().items())))
        print(f"Para o teste: {escolher_modelo(nomes) or 'nenhum'}")
        return 0
    if argumentos == ["testar"]:
        # Os módulos logam nomes e links; aqui o log é público, e o resultado sai pelos prints.
        logging.disable(logging.CRITICAL)
        try:
            return testar()
        finally:
            logging.disable(logging.NOTSET)
    if argumentos == ["produtos"]:
        logging.disable(logging.CRITICAL)
        try:
            return sondar_produtos()
        finally:
            logging.disable(logging.NOTSET)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
