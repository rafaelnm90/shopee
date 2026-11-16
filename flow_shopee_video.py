#!/usr/bin/env python3
"""
Vídeos feitos por IA no Google Flow, no celular do robô da Shopee Vídeo, com a conta Pro do
Rafael. Primeiro o teste que ele escolheu (P229 1, 15/11/2026): 3 vídeos do mesmo produto, um em
cada modelo do Flow, só no privado dele, para ele escolher o modelo. Depois dele, a produção (P232
1, 15/11/2026): 1 vídeo por dia no Omni 1.2 Flash, o mais avançado, que vira um rascunho do robô
(robo_shopee_video escolhe o produto entre os produtos em alta da API de afiliado, P234 1, e chama
producao_no_celular na rodada dele; o rascunho leva a nossa edição, os produtos e o Rótulo de IA
ligado, e o Rafael aprova em Rascunhos do Robô 📝). A IA vê a foto do anúncio e o nome do produto e
escreve o pedido do vídeo (a cena, o movimento da câmera e a luz), sempre com o produto igual ao da
foto; o Flow gera o vídeo a partir da foto.

O caminho no app (mapeado no Motorola em 15/11/2026, sem gerar nada; as telas estão no
roteiro_robo_shopee_video.md): o ícone "Flow" → o projeto do robô na lista ("Shopee Video";
sem ele, o teste para, sem criar outro) →
Criar → Vídeo → + (Adicionar mídia) → Imagens → a foto no seletor do Android ("Item Foto ...")
→ Adicionar → a caixa "O que você quer fazer?" → o modelo (9:16, 720p, x1, 8 s e o modelo, com
o custo em créditos) → Gerar. Depois do Gerar (mapeado no 1º vídeo, 15/11/2026): o vídeo novo
aparece no projeto como "N% Gerando…" e, pronto, com o título que o Flow dá; o teste abre o
mais novo pelo filtro Vídeos, confere no título que ele é do modelo do teste, toca em Mais opções
→ Baixar (na janela da resolução, o 1080p quando ele vem sem custo; sem isso, o tamanho
original) e traz o arquivo do celular para o servidor. Com o celular já solto, a IA confere o
produto do vídeo com a foto do anúncio, e o vídeo vai ao privado do Rafael com o modelo, o
custo, o produto, a cena e a conferência. O vídeo que não fica pronto ou não sai num teste é
baixado e mandado no próximo, sem gerar outro.

As amostras (P236 1, 16/11/2026): vídeos de teste como os da produção (o produto pela lista da
API de afiliado e o Omni 1.2 Flash), um por vez, só no privado do Rafael, para ele ver como os
vídeos de IA estão ficando; não viram rascunho nem post.

Usado pelo workflow video_ia.yml (acao flow, flow-sem-gerar ou amostra). O log do Actions é
público: saem só estados, modelos e números; o produto e o pedido ficam no banco, e o vídeo, no
privado.

    python3 flow_shopee_video.py teste              # o próximo passo do teste (um modelo por vez)
    python3 flow_shopee_video.py teste --sem-gerar  # tudo até o Gerar, sem tocar nele
    python3 flow_shopee_video.py amostra            # a próxima amostra do vídeo de IA (P236 1)
"""
import asyncio
import io
import json
import logging
import os
import re
import sys
import time
import unicodedata
from datetime import datetime

import api_gemini
import api_shopee
import assistente_shopee_video as assistente
import avisar_rafael
import casos_robo
import celular_robo
import db
import postador_shopee_video as ps
import videos
from fuso import fuso_horario

PACOTE = "com.google.android.apps.labs.whisk"
PACOTE_DO_SELETOR = "com.google.android.providers.media.module"
CHAVE = "flow_shopee_video"
PASTA = os.path.join(os.path.expanduser("~"), "shopee_video", "flow")
# Os modelos de vídeo do Flow na conta do Rafael e o custo de cada vídeo de 8 s em 720p,
# lidos no app em 15/11/2026. O teste vai do mais barato ao mais caro (46 créditos, dentro
# dos 50 grátis do dia): o 1º vídeo é o que mostra as telas depois do Gerar.
MODELOS_DO_TESTE = (("Veo 3.1 - Lite", 10), ("Omni 1.1 Flash", 12), ("Omni 1.2 Flash", 24))
# A produção: depois dos 3 vídeos do teste, o Rafael escolheu o mais avançado para 1 vídeo de IA por dia, que vira
# um rascunho do robô, no lugar de um da fonte (P232 1). 24 créditos por vídeo, dentro dos 50 grátis do dia: nunca
# mais de um Gerar por dia. Escolha do Rafael (15/11/2026): DECISOES.md, Shopee Vídeo.
MODELO_DA_PRODUCAO = ("Omni 1.2 Flash", 24)
# A produção que para antes do Gerar (sem gastar crédito) tenta de novo no mesmo dia, até estas vezes.
TENTATIVAS_ANTES_DO_GERAR = 2
# O vídeo pronto que não vira rascunho nestas tentativas (o celular, o app, nada do vídeo) sai, e o robô segue com os
# vídeos da fonte.
TENTATIVAS_DO_RASCUNHO = 6
# Quantos dos próximos vídeos da fonte o teste tenta até a IA achar a foto boa para o vídeo.
PRODUTOS_TENTADOS = 10
ESPERA_DA_TELA = 20
PAUSA_DA_LEITURA = 1.5
# Depois do Gerar, o quadrado do vídeo novo aparece no projeto com "N% Gerando…" e, pronto, vira o
# vídeo com o título que o Flow dá ("…, 1 item"). O Veo 3.1 - Lite ficou pronto em menos de 1 min
# (15/11/2026). O teste espera até ESPERA_DA_GERACAO e guarda a tela a cada INTERVALO_DOS_CASOS; o
# que não fica pronto nesse tempo é baixado no próximo teste. Sem o "Gerando…" logo depois do
# Gerar, o Flow não gerou (a tela fica guardada para o Claude ver o porquê).
ESPERA_DA_GERACAO = 10 * 60
ESPERA_DO_GERANDO = 30
INTERVALO_DOS_CASOS = 60
GERANDO = re.compile(r"\bgerando\b", re.I)
# O "Gerando…" some de uma leitura da tela no meio da geração (15/11/2026, o Omni 1.2 Flash: o
# robô viu "pronto" aos 6 s e abriu o vídeo de antes). Pronto só depois de PRONTO_SEGUIDAS leituras
# seguidas do projeto sem ele.
PRONTO_SEGUIDAS = 3
ITEM_DO_PROJETO = re.compile(r",\s*\d+\s+(?:item|itens|items)\s*$", re.I)
# O vídeo aberto: o player ("Vídeo tocando, 1 de 1") e, no alto, o título com o nome, o modelo e a
# resolução, uma linha cada (mapeado em 15/11/2026).
VIDEO_ABERTO = re.compile(r"^v[íi]deo\b.*\b\d+ de \d+", re.I | re.S)
# O Baixar (Mais opções do vídeo aberto) guarda o arquivo numa destas pastas do celular. A marca é
# um arquivo vazio criado antes do toque: o vídeo baixado é o .mp4 mais novo que ela.
PASTAS_DO_BAIXAR = ("/sdcard/Download", "/sdcard/Movies", "/sdcard/DCIM", "/sdcard/Pictures")
MARCA_DO_BAIXAR = "/sdcard/Download/.flow_antes_do_baixar"
# O 1080p é o vídeo aumentado pelo Flow na hora do Baixar e pode levar uns minutos: o robô espera
# até ESPERA_DO_BAIXAR, mas segue assim que o arquivo para de crescer.
ESPERA_DO_BAIXAR = 5 * 60
# Depois do Baixar do menu, o tempo para a janela da resolução aparecer (sem ela, o download já
# começou) e, na janela, para a escolha ficar marcada.
ESPERA_DA_JANELA_DO_BAIXAR = 8
# Depois do Baixar da janela, o tempo para ela fechar (no 1080p, o Flow pode mostrar nela o andamento antes).
ESPERA_PARA_A_JANELA_FECHAR = 30
# Depois do toque na miniatura de uma versão, o tempo para o título do vídeo aberto mudar.
ESPERA_DA_VERSAO = 6
# O vídeo aberto com o player em "Falha ao carregar o vídeo" (visto em 16/11/2026, logo depois de o
# vídeo ficar pronto): o título com o modelo aparece, mas o vídeo não toca. O robô espera o player
# até ESPERA_DO_PLAYER e, sem ele, fecha o vídeo e o abre de novo depois de PAUSA_ANTES_DE_REABRIR,
# até ABERTURAS_DO_VIDEO vezes; sem carregar, Parada (o vídeo continua gerado: a próxima vez baixa).
FALHA_NO_PLAYER = re.compile(r"falha ao carregar", re.I)
ESPERA_DO_PLAYER = 10
PAUSA_ANTES_DE_REABRIR = 20
ABERTURAS_DO_VIDEO = 3
# A janela "Baixar vídeo" (mapeada em 15/11/2026) vem com o "720p Tamanho original" marcado; o
# "1080p Aumentar a resolução" fica livre no plano Pro e o 4K pede outro plano. O robô baixa no
# 1080p e só quando a linha dele não fala em plano nem em crédito, e a janela não fala em crédito;
# sem isso, no tamanho original. Nunca toca no 4K nem no plano. Pedido do Rafael (P229):
# DECISOES.md, Shopee Vídeo.
CUSTO_OU_PLANO = re.compile(r"cr[ée]dito|assin|plano|premium|ultra", re.I)
CREDITO = re.compile(r"cr[ée]dito", re.I)
# O botão da janela muda com a escolha: "Baixar" no tamanho original e "Aumentar resolução e
# baixar" no 1080p (visto no 1º Baixar no 1080p, 15/11/2026).
BOTAO_DO_BAIXAR = re.compile(r"(?:aumentar (?:a )?resolu[çc][ãa]o e )?baixar")
# Fora dessa janela, outra pergunta de tamanho depois do Baixar (ou uma permissão do Android) para
# o robô: ele não escolhe nada que não foi mapeado.
ESCOLHA_NO_BAIXAR = re.compile(r"1080p|\b4k\b|upscal|aumentar|ampliar|melhorad", re.I)
PACOTES_DE_PERMISSAO = ("com.android.permissioncontroller", "com.google.android.permissioncontroller")
# O projeto do robô no Flow: o Rafael o renomeou para "Shopee Video" (15/11/2026) e pediu que
# todos os vídeos fiquem só nele, para não bagunçar. Sem ele em lugar nenhum da lista (o Rafael
# pode tê-lo apagado), o robô cria outro com esse nome e o usa de padrão, no máximo um por dia.
# Pedido do Rafael (P229): DECISOES.md, Shopee Vídeo.
PROJETO_DO_ROBO = "Shopee Video"
# A lista do início põe o projeto novo no alto e empurra os outros para baixo: o robô rola até o
# fim (até a lista parar de andar, no máximo ROLADAS_DA_LISTA vezes) antes de dar o projeto por sumido,
# esperando cada tela da lista até ESPERA_DA_LISTA s.
ROLADAS_DA_LISTA = 10
ESPERA_DA_LISTA = 8
# O alto do projeto aberto (mapeado em 15/11/2026, entre y 152 e 278): o título, o Voltar e o Mais
# opções; no Renomear, o campo do nome com o ✓ e o ✕ ao lado. O menu do Mais opções tem Renomear,
# Grade, Ver lixeira e Excluir projeto: o robô só toca no Renomear, nunca no Excluir nem na lixeira.
ALTO_DO_PROJETO = 330
PROIBIDO_NO_MENU_DO_PROJETO = re.compile(r"excluir|lixeira", re.I)
CUSTO_NA_TELA = re.compile(r"(\d+)\s+créditos de IA", re.I)
# A tela de termos ou de consentimento: o robô nunca aceita nada pelo Rafael. Também o aviso do
# teclado (o do Google Tradutor, que abriu em 15/11 com um toque fora do lugar): OK e Cancelar
# num diálogo do teclado.
PALAVRAS_DE_TERMOS = ("termos de serviço", "aceitar", "concordo", "política de privacidade")
PACOTE_DO_TECLADO = "com.google.android.inputmethod.latin"
# O jeito de cada vídeo, que a IA escolhe pelo produto e varia de um vídeo para outro (o nome que o
# Rafael vê na legenda). Com fala em português do Brasil, viral, inusitado ou de comédia: pedido do
# Rafael (15/11/2026: "você pode fazer vídeos também com falas (...) Pode ser até vídeos virais também,
# do tipo uma coisa inusitada (...) Uma coisa mais comédia"), sempre dentro das diretrizes da Shopee
# Vídeo (sem humilhar ninguém, sem marca, sem preço, sem promessa falsa): DECISOES.md, Shopee Vídeo.
ESTILOS = {"demonstracao": "demonstração (o produto em uso)", "fala": "pessoa falando do produto",
           "inusitado": "inusitado (viral)", "comedia": "comédia"}
ESTILO_PADRAO = "demonstracao"
# Quantos estilos dos últimos vídeos a IA recebe, para variar (o Rafael pediu vídeos variados, "para não
# ficar um padrão, para ser mais orgânico", 15/11/2026).
ESTILOS_LEMBRADOS = 4
PEDIDO_DA_IA = (
    "Você é diretor de vídeos curtos de produto para a Shopee Vídeo, no Brasil. A imagem é a foto "
    "oficial do anúncio do produto \"{nome}\". O Google Flow vai gerar um vídeo de 8 segundos, em pé "
    "(9:16) e com som, a partir dessa foto. Responda só com um JSON, sem nada antes ou depois:\n"
    '{{"serve": true ou false, "motivo": "...", "estilo": "...", "prompt": "...", "cena": "..."}}\n'
    "- serve: false quando a foto não mostra o produto inteiro e com clareza (colagem de várias "
    "fotos, tabela de medidas, mais texto que produto, só a embalagem fechada) ou quando o produto "
    "é proibido nas diretrizes da Shopee Vídeo{bebida}; motivo: o porquê, em poucas palavras.\n"
    "- estilo: o jeito do vídeo que mais combina com este produto e prende quem está rolando o feed, um "
    "destes: \"demonstracao\" (o produto em uso no dia a dia), \"fala\" (uma pessoa comum mostra o "
    "produto e fala dele, como um cliente contando a experiência), \"inusitado\" (uma situação curiosa "
    "ou surpreendente com o produto, de vídeo viral) ou \"comedia\" (uma cena engraçada do dia a dia com "
    "o produto; por exemplo, a bicicleta ergométrica com alguém começando a pedalar com toda a "
    "determinação e o cachorro assistindo).{evitar}\n"
    "- prompt: em inglês, até 90 palavras, o pedido do vídeo no estilo escolhido: o mesmo produto da "
    "foto, idêntico (mesma forma, cor, material, tamanho, quantidade e detalhes; nada acrescentado, "
    "tirado ou trocado) e bem à vista, numa cena real do Brasil, com luz natural, fotorrealista, com um "
    "movimento de câmera simples. Com fala, a fala vai em português do Brasil, entre aspas, curta (até "
    "15 palavras, para caber nos 8 segundos), natural, sem marca, sem preço e sem prometer o que o "
    "produto não faz. O humor é da situação, nunca de zombar do corpo, da aparência ou de um grupo de "
    "ninguém (as diretrizes punem humilhação e ódio), e nada perigoso, nojento ou com criança. Sem "
    "texto na tela, sem legenda, sem logotipo novo e sem outros produtos.\n"
    "- cena: uma frase em português que descreve a cena (com a fala, se tiver), para o Rafael."
)
# Bebida alcoólica fica de lado enquanto as diretrizes a deixam em espera (P111): o vídeo nem é gerado, para não
# gastar o crédito de um vídeo que o rascunho deixaria de lado.
TRECHO_DA_BEBIDA = ", ou é bebida alcoólica (em espera nas diretrizes)"
# A conferência do vídeo pronto, que vai com ele no privado do Rafael: o produto é o da foto?
PEDIDO_DA_CONFERENCIA = (
    "Este vídeo foi feito por IA a partir da foto do anúncio que vai junto (a imagem). Compare o "
    "produto do vídeo com o da foto: forma, cor, material, detalhes e o que vem junto. Veja também o "
    "que denuncia a IA no vídeo: mãos ou pés estranhos, objetos que se deformam ou mudam de um quadro "
    "para outro, letras sem sentido e, se o vídeo tem fala, a fala que não está em português do Brasil, "
    "que sai cortada ou que não acompanha a boca de quem fala. Responda só com um JSON, sem nada antes "
    "ou depois:\n"
    '{"mesmo_produto": true ou false, "diferencas": "o que muda no produto, em até 200 letras; vazio '
    'se nada", "defeitos": "o que parece falso ou estranho no vídeo, em até 200 letras; vazio se nada"}'
)
ROTULOS_DA_CONFERENCIA = {True: "mesmo produto", False: "produto diferente", None: "sem resposta"}


class Parada(Exception):
    """O teste parou num passo: a mensagem é um texto fixo do código (vai para o log público)."""


def agora():
    return datetime.now(fuso_horario).strftime("%Y-%m-%d %H:%M:%S")


def nome_do_estilo(estilo):
    """A chave do estilo (ESTILOS) pelo que a IA escreveu, com ou sem acento; o ESTILO_PADRAO quando não é nenhum."""
    sem_acento = unicodedata.normalize("NFKD", str(estilo or "")).encode("ascii", "ignore").decode().lower()
    return next((chave for chave in ESTILOS if chave in sem_acento), ESTILO_PADRAO)


def estilos_recentes():
    """Os estilos dos últimos vídeos de IA (o mais novo por último), para a IA variar."""
    return list((db.ler_config(CHAVE, {}) or {}).get("estilos") or [])[-ESTILOS_LEMBRADOS:]


def evitar_os_recentes(recentes):
    """O trecho do pedido à IA que pede outro estilo que não os dos últimos vídeos; "" sem vídeo antes."""
    if not recentes:
        return ""
    return (" Os últimos vídeos foram " + ", ".join(f'"{e}"' for e in recentes) + ": prefira outro estilo, "
            "se ele também combinar com este produto, para os vídeos não ficarem num padrão só.")


def ler_resposta(texto):
    """
    {"serve", "motivo", "estilo", "prompt", "cena"} da resposta da IA; None quando ela não veio num
    JSON ou disse que serve sem escrever o pedido.
    """
    achado = re.search(r"\{.*\}", texto or "", re.S)
    if not achado:
        return None
    try:
        dados = json.loads(achado.group(0))
    except ValueError:
        return None
    if not isinstance(dados, dict):
        return None
    serve = dados.get("serve") is True
    prompt = " ".join(str(dados.get("prompt") or "").split())
    if serve and not prompt:
        return None
    return {"serve": serve, "motivo": " ".join(str(dados.get("motivo") or "").split())[:200],
            "estilo": nome_do_estilo(dados.get("estilo")), "prompt": prompt[:1000],
            "cena": " ".join(str(dados.get("cena") or "").split())[:300]}


def jpeg_sem_metadados(dados):
    """
    A foto regravada em JPEG, sem os dados de câmera (EXIF): no seletor de fotos do Android, a
    mais nova é a 1ª pela hora em que entrou na galeria, e não por uma data antiga da foto.
    None quando os bytes não são uma imagem.
    """
    from PIL import Image
    try:
        with Image.open(io.BytesIO(dados)) as imagem:
            saida = io.BytesIO()
            imagem.convert("RGB").save(saida, "JPEG", quality=95)
            return saida.getvalue()
    except Exception:
        return None


def pedido_para_o_anuncio(link, nome, foto, evitar=""):
    """
    O pedido do vídeo para o anúncio já em mãos (o link, o nome e os bytes da foto do anúncio): a foto sem os
    dados de câmera e o que a IA escreveu, num estilo diferente dos últimos vídeos quando combina (evitar, o
    trecho de evitar_os_recentes). (o pedido, serve): o pedido é {"link", "nome", "foto" (bytes), "estilo",
    "prompt", "cena"} quando a IA acha a foto boa para o vídeo; serve é False quando ela disse que a foto não
    serve e None quando não deu para saber (a foto não é uma imagem, ou a IA não respondeu).
    """
    foto = jpeg_sem_metadados(foto) if foto and nome else None
    if not foto:
        return None, None
    resposta = ler_resposta(asyncio.run(api_gemini.gerar_texto_gemini(
        PEDIDO_DA_IA.format(nome=nome, evitar=evitar, bebida=TRECHO_DA_BEBIDA if assistente.BEBIDA_EM_ESPERA else ""),
        imagens=[(foto, "image/jpeg")])))
    if not resposta:
        return None, None
    if not resposta["serve"]:
        return None, False
    return {"link": link, "nome": nome, "foto": foto, "estilo": resposta["estilo"], "prompt": resposta["prompt"],
            "cena": resposta["cena"]}, True


def pedido_para_o_produto(link, evitar=""):
    """
    O pedido do vídeo para o produto do link (pedido_para_o_anuncio, com a foto e o nome que a API de afiliado
    dá para o link); None quando o anúncio não traz a foto e o nome ou a IA não acha a foto boa para o vídeo.
    """
    anuncio = ps.anuncio_do_produto({"link": link})
    return pedido_para_o_anuncio(link, anuncio.get("nome"), anuncio.get("foto"), evitar)[0]


def escolher_o_produto():
    """
    O produto do teste: o 1º dos próximos vídeos da fonte do painel com a foto do anúncio que a
    IA acha boa para o vídeo, com o pedido dela (pedido_para_o_produto). O pedido_para_o_produto
    com "tentados"; None sem nenhum.
    """
    fonte = (db.ler_config(ps.CHAVE_PAINEL, {}) or {}).get("fonte", assistente.FONTE_PADRAO)
    evitar = evitar_os_recentes(estilos_recentes())
    tentados = 0
    for _, _, link, _ in assistente.candidatos_nao_usados(fonte)[:PRODUTOS_TENTADOS]:
        if not link:
            continue
        tentados += 1
        pedido = pedido_para_o_produto(link, evitar)
        if pedido:
            return dict(pedido, tentados=tentados)
    return None


def teste_guardado():
    """O teste de agora (o produto, o pedido e os vídeos já gerados), do banco; {} sem nenhum."""
    teste = (db.ler_config(CHAVE, {}) or {}).get("teste") or {}
    return teste if teste.get("foto") and os.path.exists(teste["foto"]) else {}


def guardar(**campos):
    """Grava os campos na chave do Flow (o projeto do robô e o teste)."""
    db.atualizar_config(CHAVE, lambda dados: dados.update(campos))


def marcar_video(modelo, **campos):
    """Anota no teste guardado o vídeo do modelo (o estado: gerando, baixado ou enviado; o custo; o arquivo)."""
    def alterar(dados):
        dados.setdefault("teste", {}).setdefault("videos", {}).setdefault(modelo, {}).update(campos)
    db.atualizar_config(CHAVE, alterar)


def proximo_modelo(teste):
    """(nome, custo) do próximo modelo do teste, do mais barato ao mais caro; None com os 3 gerados."""
    gerados = (teste or {}).get("videos") or {}
    return next(((nome, custo) for nome, custo in MODELOS_DO_TESTE if nome not in gerados), None)


def video_pendente(teste):
    """O modelo cujo vídeo já foi gerado e ainda não chegou ao Rafael (gerando ou baixado); None sem ele."""
    return next((nome for nome, video in ((teste or {}).get("videos") or {}).items()
                 if video.get("estado") in ("gerando", "baixado")), None)


def numero_do_modelo(modelo):
    """A posição do modelo no teste (1 a 3); 0 fora dele."""
    return next((numero for numero, (nome, _) in enumerate(MODELOS_DO_TESTE, 1) if nome == modelo), 0)


# --- As telas do Flow -----------------------------------------------------------------------

def _tela(d):
    try:
        return d.dump_hierarchy()
    except Exception:
        return ""


def esperar(d, condicao, espera=ESPERA_DA_TELA):
    """A tela (o xml) assim que a condição vale nela, esperando até `espera` s; "" se não veio."""
    fim = time.monotonic() + espera
    while True:
        xml = _tela(d)
        if xml and condicao(xml):
            return xml
        if time.monotonic() >= fim:
            return ""
        time.sleep(PAUSA_DA_LEITURA)


def tem_termos(xml):
    """A tela pede para aceitar termos ou dar consentimento (ou o teclado abriu um aviso)? O robô para."""
    for el in ps.elementos(xml):
        if any(palavra in f"{el['texto']} {el['descricao']}".casefold() for palavra in PALAVRAS_DE_TERMOS):
            return True
        if el["pacote"] == PACOTE_DO_TECLADO and el["texto"] in ("OK", "Cancelar"):
            return True
    return False


def ponto_parado(d, achar_ponto, passo, espera=ESPERA_DA_TELA):
    """
    O ponto (achar_ponto(xml)) quando ele para de se mexer: duas leituras seguidas no mesmo lugar.
    O pedido do Flow sobe com o teclado, e o toque no meio da subida cai em outro lugar (em 15/11,
    no Traduzir do teclado). Parada na tela de termos; None sem o ponto.
    """
    fim, anterior = time.monotonic() + espera, None
    while True:
        xml = _tela(d)
        if xml and tem_termos(xml):
            raise Parada(f"{passo}: tela de termos ou aviso do teclado; o robô nunca aceita pelo Rafael")
        ponto = achar_ponto(xml) if xml else None
        if ponto and ponto == anterior:
            return ponto
        anterior = ponto
        if time.monotonic() >= fim:
            return None
        time.sleep(PAUSA_DA_LEITURA)


def tocar(d, alvo, passo, espera=ESPERA_DA_TELA):
    """Toca no elemento (texto, descrição ou @id, como no ps.achar) quando ele aparece parado; Parada sem ele."""
    ponto = ponto_parado(d, lambda xml: ps.achar(xml, alvo), passo, espera)
    if not ponto:
        raise Parada(f"{passo}: não achei o botão na tela")
    d.click(*ponto)


def centro_da_caixa(xml):
    """O centro da caixa do pedido; None sem ela."""
    campo = next((el for el in ps.elementos(xml) if el["pacote"] == PACOTE and el["classe"] == "EditText"), None)
    if not campo:
        return None
    x1, y1, x2, y2 = campo["caixa"]
    return (x1 + x2) // 2, (y1 + y2) // 2


def projeto_na_lista(xml, nome=PROJETO_DO_ROBO):
    """
    O centro do projeto com esse nome na lista do início; None sem ele. O Flow descreve cada um como
    "O título do projeto é Shopee Video, 1 vídeo, 4 imagens" (lido em 15/11/2026): vale o nome
    inteiro, logo depois do "é" (ou no começo), e não um pedaço dele ("Shopee Video 2" não serve).
    """
    for el in ps.elementos(xml):
        if el["pacote"] != PACOTE:
            continue
        for valor in (el["descricao"], el["texto"]):
            if re.search(rf"(?:^|\bé\s+){re.escape(nome)}\s*(?:$|[,\n])", (valor or "").strip(), re.I):
                x1, y1, x2, y2 = el["caixa"]
                return (x1 + x2) // 2, (y1 + y2) // 2
    return None


def modelo_no_pedido(xml):
    """O modelo que está marcado no pedido (o botão "Omni 1.2 Flash\\nx1"); "" sem ele."""
    for el in ps.elementos(xml):
        achado = re.fullmatch(r"(.+?)\s*\n\s*x\d", el["descricao"] or "")
        if el["pacote"] == PACOTE and achado:
            return " ".join(achado.group(1).split())
    return ""


def custo_na_tela(xml):
    """Quantos créditos a geração vai usar, como o app diz ("24 créditos de IA"); None sem o aviso."""
    for el in ps.elementos(xml):
        achado = CUSTO_NA_TELA.search(f"{el['descricao']} {el['texto']}")
        if achado:
            return int(achado.group(1))
    return None


def texto_do_pedido(xml):
    """O que está escrito na caixa do pedido ("" vazia)."""
    for el in ps.elementos(xml):
        if el["pacote"] == PACOTE and el["classe"] == "EditText":
            return el["texto"]
    return ""


def fotos_no_pedido(xml):
    """
    Quantas miniaturas de foto o pedido tem: as imagens tocáveis do app, sem descrição, logo acima do
    + (Adicionar mídia). Com as opções do modelo abertas, a caixa do pedido ocupa a tela toda e a
    miniatura fica dentro dela (visto no ensaio de 15/11); o + fica abaixo da miniatura nos dois jeitos.
    """
    elementos = ps.elementos(xml)
    mais = next((el["caixa"] for el in elementos
                 if el["pacote"] == PACOTE and el["descricao"] == "Adicionar mídia"), None)
    if not mais:
        return 0
    return sum(1 for el in elementos
               if el["pacote"] == PACOTE and el["classe"] == "ImageView" and el["clicavel"] and not el["descricao"]
               and 60 <= el["caixa"][2] - el["caixa"][0] <= 300 and mais[1] - 900 <= el["caixa"][3] <= mais[1])


def foto_no_pedido(xml):
    """A miniatura da foto do produto já está no pedido?"""
    return fotos_no_pedido(xml) > 0


def pronto_para_gerar(xml, prompt, modelo, custo):
    """"" quando o pedido está como o teste quer (foto, texto, modelo e custo); senão, o que falta (texto fixo)."""
    if fotos_no_pedido(xml) != 1:
        return "o pedido não tem uma foto só"
    if " ".join(texto_do_pedido(xml).split())[:40] != " ".join(prompt.split())[:40]:
        return "o texto do pedido não entrou"
    if modelo_no_pedido(xml) != modelo:
        return "o modelo marcado não é o do teste"
    if custo_na_tela(xml) != custo:
        return "o custo na tela não é o esperado"
    return ""


def projetos_na_tela(xml):
    """As descrições dos projetos que a lista do início mostra agora (para saber se ela ainda anda)."""
    return tuple(el["descricao"] for el in ps.elementos(xml)
                 if el["pacote"] == PACOTE and (el["descricao"] or "").startswith("O título do projeto"))


def achar_o_projeto(d):
    """
    O centro do projeto do robô na lista do início, rolando até o fim dela; None quando ele não está
    em lugar nenhum da lista (a lista parou de andar sem ele).
    """
    vistos = None
    for _ in range(ROLADAS_DA_LISTA + 1):
        ponto = ponto_parado(d, projeto_na_lista, "projeto do robô", ESPERA_DA_LISTA)
        if ponto:
            return ponto
        na_tela = projetos_na_tela(_tela(d))
        if na_tela == vistos:
            return None
        vistos = na_tela
        ps.rolar(d)
        time.sleep(1)
    return None


def botao_do_alto(xml, descricao):
    """O centro do botão do alto do projeto com essa descrição (o Mais opções do projeto, não o de um vídeo); None sem ele."""
    for el in ps.elementos(xml):
        if (el["pacote"] == PACOTE and el["clicavel"] and el["descricao"] == descricao
                and el["caixa"][3] <= ALTO_DO_PROJETO):
            x1, y1, x2, y2 = el["caixa"]
            return (x1 + x2) // 2, (y1 + y2) // 2
    return None


def titulo_do_projeto(xml):
    """O nome do projeto aberto, no alto da tela; "" fora de um projeto."""
    for el in ps.elementos(xml):
        x1, y1, x2, y2 = el["caixa"]
        if (el["pacote"] == PACOTE and el["classe"] == "View" and not el["clicavel"] and el["descricao"]
                and y2 <= ALTO_DO_PROJETO and x2 - x1 >= 900):
            return el["descricao"]
    return ""


def campo_do_nome(xml):
    """O campo do nome do Renomear, no alto do projeto (o elemento); None sem ele."""
    return next((el for el in ps.elementos(xml) if el["pacote"] == PACOTE and el["classe"] == "EditText"
                 and el["caixa"][3] <= ALTO_DO_PROJETO), None)


def botoes_do_nome(xml):
    """
    Os botões sem nome ao lado do campo do Renomear, da esquerda para a direita: o ✓ e o ✕ (vistos
    em 15/11/2026). Lista de centros; vazia sem o campo.
    """
    campo = campo_do_nome(xml)
    if not campo:
        return []
    _, cima, _, baixo = campo["caixa"]
    botoes = sorted(el["caixa"] for el in ps.elementos(xml)
                    if el["pacote"] == PACOTE and el["classe"] == "Button" and el["clicavel"]
                    and not el["descricao"] and not el["texto"] and cima <= (el["caixa"][1] + el["caixa"][3]) // 2 <= baixo)
    return [((x1 + x2) // 2, (y1 + y2) // 2) for x1, y1, x2, y2 in botoes]


def criar_o_projeto(d):
    """
    Cria o projeto do robô quando ele sumiu da lista e o usa de padrão (pedido do Rafael, 15/11/2026).
    Caminho mapeado em 15/11: o Novo cria um projeto vazio com o nome do dia e já o abre; o Mais
    opções do alto abre o menu do projeto; o Renomear põe o nome num campo no alto, com o ✓ e o ✕
    ao lado. O robô escreve PROJETO_DO_ROBO, toca no ✓ e confere o título. No máximo um projeto por
    dia: o criado que não ficou com o nome não vira outro no mesmo dia. Parada no que falhar.
    """
    criado_em = (db.ler_config(CHAVE, {}) or {}).get("projeto_criado_em") or ""
    if criado_em[:10] == agora()[:10]:
        raise Parada(f"abrir o Flow: o projeto {PROJETO_DO_ROBO} não está na lista, e o robô já criou um "
                     "projeto hoje; não cria outro no mesmo dia")
    tocar(d, "Novo", "criar o projeto")
    guardar(projeto_criado_em=agora())
    ponto = ponto_parado(d, lambda x: ps.achar(x, "Criar") and botao_do_alto(x, "Mais opções"), "projeto novo")
    if not ponto:
        raise Parada("criar o projeto: o projeto novo não abriu")
    d.click(*ponto)
    menu = esperar(d, lambda x: ps.achar(x, "Renomear"))
    if not menu:
        raise Parada("criar o projeto: o Renomear não apareceu no menu do projeto")
    toque_x, toque_y = ps.achar(menu, "Renomear")
    if any(PROIBIDO_NO_MENU_DO_PROJETO.search(f"{el['texto']} {el['descricao']}")
           and el["caixa"][0] <= toque_x <= el["caixa"][2] and el["caixa"][1] <= toque_y <= el["caixa"][3]
           for el in ps.elementos(menu)):
        raise Parada("criar o projeto: o toque do Renomear cairia no Excluir ou na lixeira; o robô não toca")
    d.click(toque_x, toque_y)
    if not esperar(d, lambda x: campo_do_nome(x) is not None):
        raise Parada("renomear o projeto: o campo do nome não apareceu")
    ps.escrever(d, PROJETO_DO_ROBO)
    xml = esperar(d, lambda x: (campo_do_nome(x) or {}).get("texto") == PROJETO_DO_ROBO, 10)
    if not xml:
        raise Parada("renomear o projeto: o nome não entrou no campo")
    botoes = botoes_do_nome(xml)
    if len(botoes) != 2:
        raise Parada("renomear o projeto: o ✓ e o ✕ não estão ao lado do campo como no mapeamento")
    d.click(*botoes[0])
    # O Criar, que o teclado pode tapar logo depois do ✓, o pedido espera do jeito de sempre.
    if not esperar(d, lambda x: titulo_do_projeto(x) == PROJETO_DO_ROBO):
        raise Parada(f"renomear o projeto: o título não ficou {PROJETO_DO_ROBO}")


def abrir_o_projeto(d):
    """
    Abre o Flow do zero e entra no projeto do robô (PROJETO_DO_ROBO), conferindo o título no alto.
    Sem ele em lugar nenhum da lista, cria um com esse nome (criar_o_projeto). True quando criou.
    """
    d.app_start(PACOTE, stop=True, wait=True)
    xml = esperar(d, lambda x: ps.achar(x, "Novo") or tem_termos(x), 30)
    if not xml or tem_termos(xml):
        raise Parada("abrir o Flow: o início não apareceu" if not xml else
                     "abrir o Flow: tela de termos; o robô nunca aceita pelo Rafael")
    ponto = achar_o_projeto(d)
    if not ponto:
        # A lista rolada esconde o Novo, que fica no alto do início: o Flow abre de novo, do alto.
        d.app_start(PACOTE, stop=True, wait=True)
        if not esperar(d, lambda x: ps.achar(x, "Novo"), 30):
            raise Parada("criar o projeto: o início do Flow não voltou")
        criar_o_projeto(d)
        return True
    d.click(*ponto)
    if not esperar(d, lambda x: ps.achar(x, "Criar") and titulo_do_projeto(x) == PROJETO_DO_ROBO):
        raise Parada(f"abrir o projeto: o Criar ou o título {PROJETO_DO_ROBO} não apareceu")
    return False


def montar_o_pedido(d, prompt, modelo, custo):
    """Criar → Vídeo → a foto → o texto → o modelo; devolve a tela pronta para o Gerar (Parada no que falhar)."""
    tocar(d, "Criar", "criar")
    tocar(d, "Vídeo", "modo vídeo")
    # O pedido guardado de antes (foto ou texto) não é apagado às cegas: o teste para, e
    # nunca gera com duas fotos ou com o texto de outro pedido.
    xml = esperar(d, lambda x: any(el["classe"] == "EditText" for el in ps.elementos(x)))
    if not xml:
        raise Parada("pedido: a caixa do pedido não apareceu")
    if fotos_no_pedido(xml) or texto_do_pedido(xml).strip():
        raise Parada("pedido: já tinha foto ou texto de antes")
    tocar(d, "Adicionar mídia", "adicionar mídia")
    tocar(d, "Imagens", "imagens")
    if not esperar(d, lambda x: PACOTE_DO_SELETOR in x and ps.achar(x, "Item Foto")):
        raise Parada("seletor de fotos: a foto do produto não apareceu")
    tocar(d, "Item Foto", "escolher a foto")
    tocar(d, "@button_add", "adicionar a foto")
    if not esperar(d, foto_no_pedido, 30):
        raise Parada("foto no pedido: a miniatura não apareceu")
    ponto = ponto_parado(d, centro_da_caixa, "texto do pedido")
    if not ponto:
        raise Parada("texto do pedido: a caixa não apareceu")
    d.click(*ponto)
    time.sleep(1)
    ps.escrever(d, prompt)
    if not esperar(d, lambda x: " ".join(texto_do_pedido(x).split())[:40] == " ".join(prompt.split())[:40], 10):
        raise Parada("texto do pedido: o texto não entrou na caixa")
    xml = _tela(d)
    atual = modelo_no_pedido(xml)
    if not atual:
        raise Parada("modelo: o botão do modelo não apareceu")
    tocar(d, f"{atual} x", "abrir o modelo")
    # O Flow abre no último modelo usado, e as opções mudam com o modelo: primeiro o modelo, depois
    # as opções dele. O Veo 3.1 - Lite não tem a escolha da resolução (visto em 15/11/2026); o custo
    # conferido antes do Gerar pega a resolução errada nos modelos que a têm.
    if atual != modelo:
        tocar(d, atual, "lista de modelos")
        tocar(d, modelo, "escolher o modelo")
        if not esperar(d, lambda x: modelo_no_pedido(x) == modelo):
            raise Parada("modelo: o escolhido não ficou marcado")
    xml = _tela(d)
    for opcao in ("9:16", "720p", "x1"):
        if opcao == "720p" and not (ps.achar(xml, "720p") or ps.achar(xml, "360p")):
            continue
        tocar(d, opcao, f"opção {opcao}")
    return esperar(d, lambda x: custo_na_tela(x) is not None) or _tela(d)


def gerando(xml):
    """Há vídeo sendo gerado no projeto (o quadrado "N% Gerando…")?"""
    return any(el["pacote"] == PACOTE and GERANDO.search(f"{el['texto']} {el['descricao']}")
               for el in ps.elementos(xml))


def esperar_o_video(d, ja_gerado=False, guardar_telas=True):
    """
    Espera o vídeo novo ficar pronto no projeto, guardando a tela a cada INTERVALO_DOS_CASOS
    (casos_robo; guardar_telas=False na produção do dia, para as telas da espera não tirarem do
    servidor os casos das falhas, que ficam no máximo 30). Logo depois do Gerar, o "Gerando…" tem de
    aparecer em ESPERA_DO_GERANDO s (Parada sem ele: o Flow não gerou). ja_gerado=True (gerado numa
    vez anterior): pronto se ele não aparece. Os segundos até ficar pronto; None se não ficou em
    ESPERA_DA_GERACAO.
    """
    inicio, proximo_caso, visto, seguidas = time.monotonic(), 0.0, ja_gerado, 0
    while True:
        passado = time.monotonic() - inicio
        if guardar_telas and passado >= proximo_caso:
            casos_robo.guardar(d, "flow", "tela", f"esperando o vídeo, aos {int(passado)} s", passo="flow gerar")
            proximo_caso += INTERVALO_DOS_CASOS
        xml = _tela(d)
        if xml and tem_termos(xml):
            raise Parada("gerar: tela de termos ou de consentimento; o robô nunca aceita pelo Rafael")
        if xml and gerando(xml):
            visto, seguidas = True, 0
        elif xml and visto and ps.achar(xml, "Criar"):
            seguidas += 1
            if seguidas >= PRONTO_SEGUIDAS:
                return int(passado)
        else:
            seguidas = 0
            if not visto and passado >= ESPERA_DO_GERANDO:
                raise Parada("gerar: o Flow não mostrou o vídeo sendo gerado")
        if passado >= ESPERA_DA_GERACAO:
            return None
        time.sleep(PAUSA_DA_LEITURA)


def quadro_mais_novo(xml):
    """O centro do quadro mais novo do projeto (o 1º da grade: o mais alto e, empatado, o da esquerda); None sem quadro."""
    quadros = [el for el in ps.elementos(xml)
               if el["pacote"] == PACOTE and el["clicavel"] and ITEM_DO_PROJETO.search(el["descricao"] or "")]
    if not quadros:
        return None
    x1, y1, x2, y2 = min(quadros, key=lambda el: (el["caixa"][1], el["caixa"][0]))["caixa"]
    return (x1 + x2) // 2, (y1 + y2) // 2


def titulo_do_video(xml):
    """As linhas do título do vídeo aberto (o nome, o modelo e a resolução); None fora do vídeo aberto."""
    elementos = [el for el in ps.elementos(xml) if el["pacote"] == PACOTE]
    if not any(VIDEO_ABERTO.search(el["descricao"] or "") for el in elementos):
        return None
    for el in elementos:
        linhas = [" ".join(linha.split()) for linha in (el["descricao"] or "").split("\n")]
        if len(linhas) >= 2 and not el["clicavel"] and el["caixa"][1] < 400:
            return linhas
    return []


def versoes_do_video(xml):
    """
    Os centros das miniaturas das versões do vídeo aberto: a coluna à direita do player, quando o
    vídeo tem mais de uma (o Estender guarda a versão nova junto da original, "1 de 2"). [] sem elas.
    """
    pontos = []
    for el in ps.elementos(xml):
        x1, y1, x2, y2 = el["caixa"]
        if (el["pacote"] == PACOTE and el["classe"] == "ImageView" and el["clicavel"] and not el["descricao"]
                and x1 > 800 and 30 <= x2 - x1 <= 120 and 30 <= y2 - y1 <= 120):
            pontos.append(((x1 + x2) // 2, (y1 + y2) // 2))
    return pontos


def video_sem_carregar(xml):
    """O vídeo aberto com o player em "Falha ao carregar o vídeo"?"""
    return any(el["pacote"] == PACOTE and FALHA_NO_PLAYER.search(f"{el['texto']} {el['descricao']}")
               for el in ps.elementos(xml))


def abrir_o_video_novo(d, modelo):
    """
    No projeto: Vídeos → o mais novo. O título dele tem de ter o modelo do teste: com mais de uma
    versão (o Estender que o Rafael fez no vídeo do teste em 15/11 ficou junto do original), o robô
    passa pelas miniaturas das versões até o título dizer o modelo. Nunca baixa nem manda um vídeo
    de outro modelo (Parada). O player que não carrega é fechado e aberto de novo (ABERTURAS_DO_VIDEO).
    """
    tocar(d, "Vídeos", "filtro dos vídeos")
    for abertura in range(1, ABERTURAS_DO_VIDEO + 1):
        ponto = ponto_parado(d, quadro_mais_novo, "vídeo novo")
        if not ponto:
            raise Parada("baixar: o vídeo novo não apareceu no projeto")
        d.click(*ponto)
        xml = esperar(d, lambda x: titulo_do_video(x) is not None or video_sem_carregar(x))
        if not xml:
            raise Parada("baixar: o vídeo não abriu")
        if titulo_do_video(xml) is not None or esperar(d, lambda x: titulo_do_video(x) is not None, ESPERA_DO_PLAYER):
            break
        if abertura == ABERTURAS_DO_VIDEO:
            raise Parada(f"baixar: o Flow não carregou o vídeo ({ABERTURAS_DO_VIDEO} vezes)")
        print("Flow: o vídeo não carregou no player; fechado para abrir de novo")
        tocar(d, "Fechar", "fechar o vídeo que não carregou")
        time.sleep(PAUSA_ANTES_DE_REABRIR)
    # O título com o modelo e a coluna das versões aparecem um pouco depois do player (visto em
    # 15/11: lido cedo demais, o vídeo parecia não ter versões); a versão estendida tem só o nome
    # no título, sem o modelo.
    xml = esperar(d, lambda x: modelo in (titulo_do_video(x) or []) or bool(versoes_do_video(x)), ESPERA_DA_VERSAO)
    if xml and modelo in (titulo_do_video(xml) or []):
        return
    for versao in versoes_do_video(xml or _tela(d)):
        d.click(*versao)
        if esperar(d, lambda x: modelo in (titulo_do_video(x) or []), ESPERA_DA_VERSAO):
            return
    raise Parada("baixar: o vídeo mais novo não é do modelo do teste")


def arquivos_novos(d):
    """Os vídeos (.mp4) que apareceram no celular depois da marca do Baixar: [(caminho, bytes)], o mais novo primeiro."""
    comando = ["find", *PASTAS_DO_BAIXAR, "-type", "f", "-name", "*.mp4", "-newer", MARCA_DO_BAIXAR,
               "-exec", "stat", "-c", "%Y %s %n", "{}", "+"]
    try:
        saida = d.shell(comando).output or ""
    except Exception:
        return []
    achados = []
    for linha in saida.splitlines():
        partes = linha.strip().split(" ", 2)
        # O arquivo com ponto na frente (o ".pending-…" do Android) ainda está sendo gravado.
        if len(partes) == 3 and partes[0].isdigit() and partes[1].isdigit() \
                and not os.path.basename(partes[2]).startswith("."):
            achados.append((int(partes[0]), int(partes[1]), partes[2]))
    return [(caminho, tamanho) for _, tamanho, caminho in sorted(achados, reverse=True)]


def pede_escolha(xml):
    """Depois da janela da resolução, o Flow pergunta outra coisa do tamanho ou o Android pede uma permissão? O robô não escolhe."""
    for el in ps.elementos(xml):
        if el["pacote"] in PACOTES_DE_PERMISSAO:
            return True
        if el["pacote"] == PACOTE and el["clicavel"] and ESCOLHA_NO_BAIXAR.search(f"{el['texto']} {el['descricao']}"):
            return True
    return False


def _centro(el):
    x1, y1, x2, y2 = el["caixa"]
    return (x1 + x2) // 2, (y1 + y2) // 2


def janela_do_baixar(xml):
    """
    A janela "Baixar vídeo": {"original", "1080p", "baixar"}; None sem ela. "original" e "1080p" são
    {"centro" (o botão redondo da linha), "marcada"}; o "1080p" é None quando falta, quando a linha
    dele fala em plano ou crédito ou quando a janela fala em crédito. "baixar" é o centro do botão
    que confirma a janela ("Baixar" ou, com o 1080p marcado, "Aumentar resolução e baixar"); None
    sem ele.
    """
    elementos = [el for el in ps.elementos(xml) if el["pacote"] == PACOTE]

    def texto(el):
        return " ".join(f"{el['texto']} {el['descricao']}".split()).casefold()

    def linha(achou):
        el = next((el for el in elementos if achou(texto(el))), None)
        if not el:
            return None
        x1, y1, x2, y2 = el["caixa"]
        na_linha = [outro for outro in elementos if x1 <= outro["caixa"][0] and outro["caixa"][2] <= x2
                    and y1 <= outro["caixa"][1] and outro["caixa"][3] <= y2]
        redondo = next((outro for outro in na_linha if outro["classe"] == "RadioButton"), None)
        if not redondo:
            return None
        return {"centro": _centro(redondo), "marcada": redondo["marcado"],
                "texto": " ".join(texto(outro) for outro in na_linha)}

    original = linha(lambda t: "tamanho original" in t)
    if not original:
        return None
    maior = linha(lambda t: t.startswith("1080p"))
    if maior and (CUSTO_OU_PLANO.search(maior["texto"]) or any(CREDITO.search(texto(el)) for el in elementos)):
        maior = None
    botao = next((el for el in elementos if el["classe"] == "Button" and BOTAO_DO_BAIXAR.fullmatch(texto(el))), None)
    return {"original": original, "1080p": maior, "baixar": _centro(botao) if botao else None}


def escolher_a_resolucao(d, xml):
    """
    Na janela do Baixar: marca o 1080p quando ele está livre (sem plano nem crédito na tela), confere
    que ficou marcado e toca no Baixar da janela; sem o 1080p livre, baixa no tamanho original, que
    vem marcado. A resolução escolhida ("1080p" ou "720p"). Nunca toca no 4K nem no plano. Pedido do
    Rafael (P229): DECISOES.md, Shopee Vídeo.
    """
    janela = janela_do_baixar(xml)
    if janela["1080p"] and not janela["1080p"]["marcada"]:
        d.click(*janela["1080p"]["centro"])
        xml = esperar(d, lambda x: bool(((janela_do_baixar(x) or {}).get("1080p") or {}).get("marcada")),
                      ESPERA_DA_JANELA_DO_BAIXAR)
        if not xml:
            raise Parada("baixar: o 1080p não ficou marcado; o robô não baixa sem conferir a resolução")
        janela = janela_do_baixar(xml)
    if janela["1080p"] and janela["1080p"]["marcada"]:
        escolhida = "1080p"
    elif janela["original"]["marcada"]:
        escolhida = "720p"
    else:
        raise Parada("baixar: nem o 1080p nem o tamanho original estão marcados; o robô não escolhe outra resolução")
    if not janela["baixar"]:
        raise Parada("baixar: a janela da resolução não tem o botão Baixar")
    d.click(*janela["baixar"])
    if not esperar(d, lambda x: janela_do_baixar(x) is None, ESPERA_PARA_A_JANELA_FECHAR):
        raise Parada("baixar: a janela da resolução não fechou depois do Baixar")
    return escolhida


def baixar(d):
    """
    No vídeo aberto: Mais opções → Baixar → (na janela da resolução, o 1080p quando ele vem sem
    custo; sem isso, o tamanho original) Baixar. (O caminho do arquivo no celular, quando ele para de
    crescer; a resolução escolhida, "" quando o Flow baixou sem perguntar.)
    """
    d.shell(["touch", MARCA_DO_BAIXAR])
    # A hora do arquivo baixado tem de passar a da marca.
    time.sleep(1.1)
    tocar(d, "Mais opções", "mais opções do vídeo")
    tocar(d, "Baixar", "baixar")
    janela = esperar(d, lambda x: janela_do_baixar(x) is not None, ESPERA_DA_JANELA_DO_BAIXAR)
    resolucao = escolher_a_resolucao(d, janela) if janela else ""
    fim, anterior = time.monotonic() + ESPERA_DO_BAIXAR, None
    while True:
        xml = _tela(d)
        if xml and (tem_termos(xml) or pede_escolha(xml)):
            raise Parada("baixar: o Flow pediu uma escolha (tamanho ou permissão); o robô não escolhe pelo Rafael")
        novos = arquivos_novos(d)
        if novos and novos[0][1] > 0 and novos[0] == anterior:
            return novos[0][0], resolucao
        anterior = novos[0] if novos else None
        if time.monotonic() >= fim:
            raise Parada("baixar: o arquivo do vídeo não apareceu no celular")
        time.sleep(2)


def puxar(d, remoto, local):
    """Traz o vídeo do celular para o servidor e tira do celular o arquivo e a marca do Baixar."""
    os.makedirs(os.path.dirname(local), exist_ok=True)
    try:
        d.pull(remoto, local)
    except Exception as e:
        raise Parada(f"baixar: o vídeo não veio do celular para o servidor ({type(e).__name__})")
    d.shell(["rm", "-f", remoto, MARCA_DO_BAIXAR])
    d.shell(["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", "file://" + remoto])
    if not os.path.exists(local) or not os.path.getsize(local):
        raise Parada("baixar: o vídeo não veio do celular para o servidor")


def ler_conferencia(texto):
    """{"mesmo": True, False ou None, "diferencas", "defeitos"} da resposta da IA (None: não deu para ler)."""
    achado = re.search(r"\{.*\}", texto or "", re.S)
    try:
        dados = json.loads(achado.group(0)) if achado else None
    except ValueError:
        dados = None
    if not isinstance(dados, dict):
        return {"mesmo": None, "diferencas": "", "defeitos": ""}
    mesmo = dados.get("mesmo_produto")
    return {"mesmo": mesmo if isinstance(mesmo, bool) else None,
            "diferencas": " ".join(str(dados.get("diferencas") or "").split())[:200],
            "defeitos": " ".join(str(dados.get("defeitos") or "").split())[:200]}


def conferir_o_video(caminho, foto):
    """A conferência da IA: o produto do vídeo é o mesmo da foto do anúncio? (ler_conferencia)"""
    try:
        with open(foto, "rb") as arquivo:
            imagem = arquivo.read()
        texto = asyncio.run(api_gemini.analisar_video_gemini(caminho, PEDIDO_DA_CONFERENCIA,
                                                             imagens=[(imagem, "image/jpeg")]))
    except Exception:
        texto = None
    return ler_conferencia(texto)


def legenda_do_video(teste, modelo, custo, conferencia):
    """O texto que vai com o vídeo no privado do Rafael (até 1000 letras): o modelo, o custo, o produto, a cena e a conferência."""
    numero = numero_do_modelo(modelo)
    if conferencia["mesmo"] is True:
        conferido = "o produto é o mesmo da foto do anúncio"
    elif conferencia["mesmo"] is False:
        conferido = f"o produto muda: {conferencia['diferencas'] or 'sem detalhes'}"
    else:
        conferido = "não deu para conferir"
    linhas = [f"🎬 Teste do Flow (P229 1): vídeo {numero} de {len(MODELOS_DO_TESTE)}",
              f"🤖 Modelo: {modelo} ({custo} créditos de IA)",
              f"📦 Produto: {teste.get('nome', '')}",
              f"🎥 Cena: {teste.get('cena', '')}",
              f"🎭 Estilo: {ESTILOS.get(teste.get('estilo'), ESTILOS[ESTILO_PADRAO])}",
              f"🔎 A IA conferiu: {conferido}"]
    video = (teste.get("videos") or {}).get(modelo) or {}
    resolucao = {"1080p": "1080p (aumentada pelo Flow no Baixar)", "720p": "720p (o tamanho original)"}.get(
        video.get("resolucao"))
    if resolucao:
        linhas.append(f"📐 Resolução: {resolucao}" + (f", {video['tamanho']}" if video.get("tamanho") else ""))
    if conferencia["defeitos"]:
        linhas.append(f"⚠️ O que parece IA: {conferencia['defeitos']}")
    linhas.append("Nada foi postado: o vídeo é só para você comparar os modelos.")
    if numero == len(MODELOS_DO_TESTE):
        linhas.append("Este é o último dos 3: o Claude vai perguntar qual modelo usar.")
    return "\n".join(linhas)[:1000]


def link_do_anuncio(link):
    """O endereço do anúncio para o Rafael abrir (https://shopee.com.br/product/<loja>/<item>); o link da fonte quando não dá para achar."""
    try:
        return api_shopee.produto_do_link(asyncio.run(api_shopee.link_para_converter(link))) or link
    except Exception:
        return link


def legenda_do_anuncio(teste, modelo):
    """O texto da foto do anúncio que vai logo depois do vídeo: para comparar, com o link do anúncio."""
    return (f"🖼️ Foto do anúncio, para comparar com o vídeo {numero_do_modelo(modelo)} de "
            f"{len(MODELOS_DO_TESTE)} do teste do Flow\n🔗 Anúncio: {link_do_anuncio(teste.get('link', ''))}")[:1000]


def mandar_ao_rafael(teste, modelo, custo, local):
    """
    Confere o vídeo pela IA e manda no privado do Rafael (sem o celular), e logo depois a foto do
    anúncio com o link dele, para ele comparar (pedido dele, 15/11: DECISOES.md, Shopee Vídeo).
    0 mandado, 1 não.
    """
    conferencia = conferir_o_video(local, teste["foto"])
    print(f"Flow: conferência da IA: {ROTULOS_DA_CONFERENCIA[conferencia['mesmo']]}")
    try:
        ok = avisar_rafael.mandar_video(local, legenda_do_video(teste, modelo, custo, conferencia))
    except Exception as e:
        print(f"Flow: o envio ao privado falhou ({type(e).__name__}); o próximo teste manda de novo")
        return 1
    if not ok:
        print("Flow: o Telegram não aceitou o vídeo; o próximo teste manda de novo")
        return 1
    marcar_video(modelo, estado="enviado", enviado_em=agora(), mesmo_produto=conferencia["mesmo"])
    print("Flow: vídeo mandado no privado do Rafael")
    try:
        foto = avisar_rafael.mandar_foto(teste["foto"], legenda_do_anuncio(teste, modelo))
    except Exception:
        foto = False
    print("Flow: foto e link do anúncio mandados" if foto else "Flow: a foto do anúncio não foi ao privado")
    return 0


def mandar_o_baixado(modelo, custo):
    """Manda o vídeo do modelo que já está no servidor (estado baixado). 0 mandado, 1 não."""
    teste = teste_guardado()
    video = (teste.get("videos") or {}).get(modelo) or {}
    if video.get("estado") != "baixado" or not os.path.exists(video.get("arquivo") or ""):
        print("Flow: o vídeo baixado não está no servidor")
        return 1
    return mandar_ao_rafael(teste, modelo, custo, video["arquivo"])


def foto_na_galeria(d, foto):
    """Põe a foto do produto na galeria do celular, com nome novo; o nome do arquivo ("" se não apareceu)."""
    with open(foto, "rb") as arquivo:
        return ps.por_foto_na_galeria(d, arquivo.read(), nome=f"flow_{int(time.time())}")


def tirar_da_galeria(d, nome):
    """Tira a foto do produto da galeria e avisa a galeria."""
    if not nome:
        return
    caminho = f"{ps.GALERIA}/{nome}"
    d.shell(["rm", "-f", caminho])
    d.shell(["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", "file://" + caminho])


def no_flow(d, pedido, modelo, custo, local, marcar, sem_gerar=False, so_baixar=False, guardar_telas=True):
    """
    O caminho no Flow, com a trava do celular na mão e a tela já conferida: a foto do pedido na
    galeria, o projeto do robô, o pedido (a foto, o texto e o modelo) conferido na tela, o Gerar e,
    com o vídeo pronto, o Baixar até o arquivo chegar ao servidor em local. marcar(**campos) guarda o
    andamento: "gerando" logo depois do Gerar (com o custo e a hora) e "baixado" com o arquivo no
    servidor. so_baixar=True: o vídeo já foi gerado e só falta baixar. Devolve True (o pedido pronto,
    com sem_gerar, ou o vídeo baixado) ou False (o vídeo não ficou pronto a tempo: a próxima vez
    baixa); Parada com o passo que parou. A foto sai da galeria no fim, dê certo ou não.
    guardar_telas: a tela da espera do vídeo vai aos casos de minuto em minuto (esperar_o_video).
    """
    nome_na_galeria = ""
    if not so_baixar:
        nome_na_galeria = foto_na_galeria(d, pedido["foto"])
        if not nome_na_galeria:
            raise Parada("celular: a foto do produto não apareceu na galeria; nada foi tocado no Flow")
    try:
        if abrir_o_projeto(d):
            print(f"Flow: o projeto {PROJETO_DO_ROBO} não estava na lista; criado com esse nome e aberto")
        else:
            print("Flow: aberto no projeto do robô")
        if not so_baixar:
            xml = montar_o_pedido(d, pedido["prompt"], modelo, custo)
            falta = pronto_para_gerar(xml, pedido["prompt"], modelo, custo)
            if falta:
                raise Parada(f"antes do Gerar: {falta}")
            print(f"Flow: pedido pronto (foto, texto, {modelo}, {custo} créditos)")
            if sem_gerar:
                casos_robo.guardar(d, "flow", "tela", "pedido pronto, sem gerar", passo="flow sem gerar")
                print("Flow: sem gerar; a tela do pedido pronto foi guardada")
                return True
            tocar(d, "Gerar", "gerar")
            marcar(custo=custo, gerado_em=agora(), estado="gerando")
            print(f"Flow: Gerar tocado ({modelo}, {custo} créditos)")
        pronto = esperar_o_video(d, ja_gerado=so_baixar, guardar_telas=guardar_telas)
        if pronto is None:
            print(f"Flow: o vídeo não ficou pronto em {ESPERA_DA_GERACAO // 60} min; a próxima vez baixa")
            return False
        print(f"Flow: vídeo pronto ({pronto} s esperando)")
        abrir_o_video_novo(d, modelo)
        print("Flow: vídeo aberto (o modelo conferido no título)")
        remoto, resolucao = baixar(d)
        puxar(d, remoto, local)
        largura, altura = asyncio.run(videos.dimensoes(local, timeout=30))
        marcar(estado="baixado", arquivo=local, resolucao=resolucao,
               tamanho=f"{largura}x{altura}" if largura and altura else "")
        print(f"Flow: vídeo baixado ({resolucao or 'sem a janela da resolução'}, "
              f"{os.path.getsize(local) / 1e6:.1f} MB, {videos.duracao(local):.0f} s)")
        return True
    finally:
        tirar_da_galeria(d, nome_na_galeria)


def no_celular(teste, modelo, custo, sem_gerar, so_baixar=False):
    """
    O teste no celular, com a trava na mão: a tela, a foto, o Flow, o Gerar e, com o vídeo pronto,
    o Baixar até o arquivo chegar ao servidor (estado baixado). so_baixar=True: o vídeo do modelo foi
    gerado num teste anterior e só falta baixar. 0 deu certo, 1 parou.
    """
    if celular_robo.tela_acesa() is False:
        ps.conectar(celular=True).screen_on()
        time.sleep(2)
    if celular_robo.tela_acesa() is False or celular_robo.tela_de_bloqueio():
        print("celular: a tela está apagada ou na tela de bloqueio; nada foi tocado")
        return 1
    d = ps.conectar(celular=True)
    local = os.path.join(PASTA, f"video_{numero_do_modelo(modelo)}.mp4")
    try:
        feito = no_flow(d, teste, modelo, custo, local, lambda **campos: marcar_video(modelo, **campos),
                        sem_gerar=sem_gerar, so_baixar=so_baixar)
    except Parada as e:
        casos_robo.guardar(d, "flow", "parou", str(e), passo="flow")
        print(f"Flow: parou: {e}")
        return 1
    return 0 if feito else 1


# --- A produção: 1 vídeo de IA por dia, que vira rascunho do robô (P232 1) ---
# O andamento do vídeo do dia fica na chave do Flow, em "producao": a data, o estado, o nome que o vídeo de IA tem
# entre os vídeos do robô ("id_video"), o produto ("link", "nome", "item", "valor") e de onde ele veio ("origem": a
# lista da API de afiliado, P234 1), o pedido da IA ("estilo", "prompt", "cena"), a foto e o vídeo no servidor e a
# conferência da IA. Os estados: "parou" (antes do Gerar, sem gastar crédito) e "sem foto" (a IA não achou boa
# nenhuma das fotos desta vez, e há outros produtos para olhar), que tentam de novo no dia, até
# TENTATIVAS_ANTES_DO_GERAR; "sem produto" (nenhum produto da lista serve hoje), "gerando" (o Gerar foi tocado e
# falta o vídeo chegar ao servidor), "baixado" (falta a conferência), "pronto" (espera o rascunho), "descartado" (a
# IA viu outro produto no vídeo, ou o Flow não o entregou), "usado" (virou rascunho) e "desistiu" (não virou
# rascunho em TENTATIVAS_DO_RASCUNHO). O robô escolhe o produto pelas regras dele e chama a produção na rodada
# dele, com a trava do celular na mão. Escolhas do Rafael (15/11/2026, P232 1 e P234 1): DECISOES.md.
ESTADOS_PENDENTES = ("gerando", "baixado")
ESTADOS_DO_DIA_ACABADO = ("sem produto", "pronto", "descartado", "usado", "desistiu")
# A escolha do produto pela lista da API de afiliado (P234 1) vai sempre do que paga mais para o que paga menos:
# sem uma memória, o produto que não deu certo num dia seria o 1º de novo no dia seguinte. Ficam de fora o produto
# que já teve um vídeo gerado (itens_gerados: virou rascunho, foi recusado ou descartado) e o de foto que a IA não
# achou boa para o vídeo (fotos_recusadas). Só os números dos produtos, os ITENS_LEMBRADOS mais novos de cada lista.
ITENS_LEMBRADOS = 600


def producao():
    """O andamento do vídeo de IA do dia ({} sem nenhum)."""
    return dict((db.ler_config(CHAVE, {}) or {}).get("producao") or {})


def guardar_producao(**campos):
    """Grava os campos no andamento do vídeo do dia."""
    db.atualizar_config(CHAVE, lambda dados: dados.setdefault("producao", {}).update(campos))


def _o_do_robo_acabou(atual):
    """
    O andamento do vídeo do dia do robô fechou o dia dele? Gerado, num estado que acaba o dia ou sem mais tentativas
    antes do Gerar. O "sem produto" sem a lista de onde veio é o da escolha antiga, pelos vídeos da fonte, que a
    P234 1 trocou pela lista da API de afiliado: não fecha o dia.
    """
    estado = atual.get("estado")
    if estado == "sem produto" and not atual.get("origem"):
        return False
    return bool(estado in ESTADOS_DO_DIA_ACABADO or atual.get("gerado_em")
                or atual.get("tentativas_de_gerar", 0) >= TENTATIVAS_ANTES_DO_GERAR)


def o_do_robo_saiu(dia, atual=None):
    """
    O vídeo de IA do dia do robô (P232 1) já saiu no dia (ou desistiu)? O andamento do Preparar 1 Agora ⚡ (do_botao,
    P243) guarda a resposta do andamento que veio antes dele (do_robo_fechado).
    """
    atual = producao() if atual is None else atual
    if atual.get("data") != dia:
        return False
    if atual.get("do_botao"):
        return bool(atual.get("do_robo_fechado"))
    return _o_do_robo_acabou(atual)


def gerados_no_dia(dia, atual=None):
    """
    Quantos Gerar o Flow teve no dia, o do robô e os do Preparar 1 Agora ⚡ (P243): o número passa de um andamento ao
    seguinte do mesmo dia. O andamento gerado conta pelo menos 1 (o de antes desta conta não a tem).
    """
    atual = producao() if atual is None else atual
    if atual.get("data") != dia:
        return 0
    return max(int(atual.get("gerados_no_dia") or 0), 1 if atual.get("gerado_em") else 0)


def recomecar_producao(dia, **campos):
    """
    Um andamento novo para o vídeo do dia, no lugar do de antes (os arquivos de antes saem do servidor). Do de antes,
    no mesmo dia, ficam quantos Gerar o dia já teve e, no do Preparar 1 Agora ⚡ (do_botao), se o vídeo do dia do
    robô já tinha saído.
    """
    anterior = producao()
    for nome in os.listdir(PASTA) if os.path.isdir(PASTA) else []:
        if nome.startswith("producao_"):
            try:
                os.remove(os.path.join(PASTA, nome))
            except OSError:
                pass
    novo = dict(campos, data=dia, gerados_no_dia=gerados_no_dia(dia, anterior))
    if novo.get("do_botao"):
        novo["do_robo_fechado"] = o_do_robo_saiu(dia, anterior)
    db.atualizar_config(CHAVE, lambda dados: dados.update(producao=novo))


def itens_gerados():
    """Os produtos que já tiveram um vídeo de IA gerado (os números deles): não ganham outro."""
    return [str(item) for item in (db.ler_config(CHAVE, {}) or {}).get("itens_gerados") or []]


def fotos_recusadas():
    """Os produtos cuja foto do anúncio a IA não achou boa para o vídeo (os números deles): não voltam à IA."""
    return [str(item) for item in (db.ler_config(CHAVE, {}) or {}).get("fotos_recusadas") or []]


def _lembrar(lista, item):
    """Põe o produto no fim da lista da chave do Flow (itens_gerados ou fotos_recusadas), sem repetir."""
    if not item:
        return

    def alterar(dados):
        dados[lista] = ([i for i in dados.get(lista) or [] if str(i) != str(item)] + [str(item)])[-ITENS_LEMBRADOS:]
    db.atualizar_config(CHAVE, alterar)


def lembrar_item_gerado(item):
    """O produto teve um vídeo gerado no Flow (o crédito foi gasto): fica de fora das próximas escolhas."""
    _lembrar("itens_gerados", item)


def lembrar_foto_recusada(item):
    """A IA disse que a foto do anúncio do produto não serve para o vídeo: ele fica fora das próximas escolhas."""
    _lembrar("fotos_recusadas", item)


def comecar_producao(dia, escolhido, tentativas_de_gerar, do_botao=False):
    """
    Guarda o pedido do vídeo do dia (escolhido: o pedido_para_o_anuncio com o nome do vídeo de IA entre os
    vídeos do robô, "id", o produto, "item" e "valor", e de onde ele veio, "origem"), no estado "escolhido", e o
    estilo na lista dos últimos (estilos_recentes). A foto vai a um arquivo ao lado dos vídeos; o banco fica com o
    caminho. do_botao: o vídeo pedido no De IA ✨ do Preparar 1 Agora ⚡ (P243). Devolve o andamento novo.
    """
    recomecar_producao(dia, estado="escolhido", tentativas_de_gerar=tentativas_de_gerar,
                       **({"do_botao": True} if do_botao else {}))
    os.makedirs(PASTA, exist_ok=True)
    foto = os.path.join(PASTA, f"producao_{dia}.jpg")
    with open(foto, "wb") as arquivo:
        arquivo.write(escolhido["foto"])
    modelo, custo = MODELO_DA_PRODUCAO
    guardar_producao(id_video=escolhido["id"], link=escolhido["link"], nome=escolhido["nome"],
                     item=escolhido.get("item", ""), valor=escolhido.get("valor"), origem=escolhido.get("origem", ""),
                     foto=foto, estilo=escolhido["estilo"], prompt=escolhido["prompt"], cena=escolhido["cena"],
                     modelo=modelo, custo=custo, escolhido_em=agora())
    guardar(estilos=(estilos_recentes() + [escolhido["estilo"]])[-ESTILOS_LEMBRADOS:])
    return producao()


def producao_no_celular(d, atual):
    """
    O vídeo do dia no Flow, na rodada do robô (a trava e a tela já conferidas por ele): o Gerar no
    MODELO_DA_PRODUCAO e o Baixar, ou só o Baixar do que já foi gerado ("gerando"). True com o vídeo
    no servidor ("baixado"), False quando ele não ficou pronto a tempo (a próxima rodada baixa);
    Parada com o passo que parou, com o caso guardado.
    """
    local = os.path.join(PASTA, f"producao_{atual['data']}.mp4")
    try:
        # Sem as telas da espera nos casos: todo dia, elas tirariam do servidor os casos das falhas.
        return no_flow(d, atual, atual["modelo"], atual["custo"], local, _marcar_a_producao,
                       so_baixar=atual.get("estado") == "gerando", guardar_telas=False)
    except Parada as e:
        casos_robo.guardar(d, "video de IA", "parou", str(e), passo="flow")
        raise


def _marcar_a_producao(**campos):
    """
    Guarda o andamento do vídeo do dia; no toque do Gerar ("gerado_em"), o produto entra nos que já tiveram um
    vídeo gerado (itens_gerados), na mesma hora: a rodada que cai logo depois não deixa o produto voltar à escolha.
    O Gerar conta também entre os do dia (gerados_no_dia, P243).
    """
    if campos.get("gerado_em"):
        atual = producao()
        campos["gerados_no_dia"] = gerados_no_dia(atual.get("data"), atual) + (0 if atual.get("gerado_em") else 1)
    guardar_producao(**campos)
    if campos.get("gerado_em"):
        lembrar_item_gerado(producao().get("item"))


def conferir_a_producao():
    """
    A conferência da IA do vídeo do dia com a foto do anúncio (conferir_o_video): "pronto" ou, com outro
    produto no vídeo, "descartado" (nunca vira rascunho). Devolve o estado novo.
    """
    atual = producao()
    conferencia = conferir_o_video(atual["arquivo"], atual["foto"])
    estado = "descartado" if conferencia["mesmo"] is False else "pronto"
    guardar_producao(estado=estado, conferencia=conferencia, conferido_em=agora())
    return estado


def video_pronto():
    """O andamento do vídeo do dia que espera o rascunho, com o arquivo no servidor; None sem ele."""
    atual = producao()
    if atual.get("estado") == "pronto" and os.path.exists(atual.get("arquivo") or ""):
        return atual
    return None


def legenda_da_producao(atual):
    """As linhas do vídeo de IA no aviso e no texto do rascunho: o modelo, o custo, o estilo, a cena e a conferência."""
    conferencia = atual.get("conferencia") or {}
    if conferencia.get("mesmo") is True:
        conferido = "o produto é o mesmo da foto do anúncio"
    elif conferencia.get("mesmo") is False:
        conferido = f"o produto muda: {conferencia.get('diferencas') or 'sem detalhes'}"
    else:
        conferido = "não deu para conferir"
    linhas = [f"🤖 Feito por IA no Google Flow: {atual.get('modelo', '')} ({atual.get('custo', 0)} créditos de IA)",
              f"🎭 Estilo: {ESTILOS.get(atual.get('estilo'), ESTILOS[ESTILO_PADRAO])}",
              f"🎥 Cena: {atual.get('cena', '')}",
              f"🔎 A IA conferiu: {conferido}"]
    if conferencia.get("defeitos"):
        linhas.append(f"⚠️ O que parece IA: {conferencia['defeitos']}")
    return "\n".join(linhas)


# --- As amostras: vídeos de teste da produção, só no privado do Rafael (P236 1) ---
# Pedido do Rafael (16/11, P236 1): ver como os vídeos de IA estão ficando sem esperar o do dia. Cada amostra é um
# vídeo como o da produção (o produto pela lista da API de afiliado, P234 1, o pedido da IA num estilo que varia e o
# MODELO_DA_PRODUCAO), que vai só ao privado dele, com a foto e o link do anúncio e a conferência da IA, como o teste
# da P229 1. Não vira rascunho nem post e não muda o vídeo de IA do dia: o produto da amostra fica fora só das
# amostras seguintes (amostras_feitas) e continua podendo ser o do vídeo do dia. Roda a qualquer hora, porque ele
# pediu (como o Preparar 1 Agora ⚡). Uma amostra por vez (cada video_ia.yml amostra faz a próxima); a que ficou
# gerando ou baixada vai ao privado antes de outra ser gerada. Escolha do Rafael (16/11/2026, P236 1): DECISOES.md.


def amostra_guardada():
    """A amostra de agora (o produto, o pedido e o vídeo), do banco; {} sem nenhuma."""
    atual = (db.ler_config(CHAVE, {}) or {}).get("amostra") or {}
    return atual if atual.get("foto") and os.path.exists(atual["foto"]) else {}


def marcar_amostra(**campos):
    """Grava os campos na amostra de agora (o estado: gerando, baixado ou enviado; o custo; o arquivo)."""
    db.atualizar_config(CHAVE, lambda dados: dados.setdefault("amostra", {}).update(campos))


def amostras_feitas():
    """Os produtos que já tiveram uma amostra mandada ao Rafael (os números deles): ficam fora das próximas."""
    return [str(item) for item in (db.ler_config(CHAVE, {}) or {}).get("amostras_feitas") or []]


def legenda_da_amostra(atual, conferencia):
    """O texto que vai com a amostra no privado do Rafael (até 1000 letras)."""
    if conferencia["mesmo"] is True:
        conferido = "o produto é o mesmo da foto do anúncio"
    elif conferencia["mesmo"] is False:
        conferido = f"o produto muda: {conferencia['diferencas'] or 'sem detalhes'}"
    else:
        conferido = "não deu para conferir"
    linhas = [f"🎬 Amostra do vídeo de IA nº {atual.get('numero', 1)} (teste da P236 1)",
              f"🤖 Modelo: {atual.get('modelo', '')} ({atual.get('custo', 0)} créditos de IA)",
              f"📦 Produto: {atual.get('nome', '')}",
              f"💰 Paga {assistente._reais(atual.get('valor') or 0)} por venda (o que paga mais entre "
              f"{atual.get('origem') or 'a lista da Shopee'}, ainda não postado)",
              f"🎥 Cena: {atual.get('cena', '')}",
              f"🎭 Estilo: {ESTILOS.get(atual.get('estilo'), ESTILOS[ESTILO_PADRAO])}",
              f"🔎 A IA conferiu: {conferido}"]
    resolucao = {"1080p": "1080p (aumentada pelo Flow no Baixar)", "720p": "720p (o tamanho original)"}.get(
        atual.get("resolucao"))
    if resolucao:
        linhas.append(f"📐 Resolução: {resolucao}" + (f", {atual['tamanho']}" if atual.get("tamanho") else ""))
    if conferencia["defeitos"]:
        linhas.append(f"⚠️ O que parece IA: {conferencia['defeitos']}")
    linhas.append("Nada foi postado: é só para você ver como os vídeos de IA estão ficando. O vídeo de IA do dia sai "
                  "normalmente e vira rascunho.")
    return "\n".join(linhas)[:1000]


def mandar_a_amostra():
    """
    Confere a amostra baixada pela IA e manda no privado do Rafael (sem o celular), e logo depois a foto do anúncio
    com o link dele. O produto entra nas amostras feitas. 0 mandada, 1 não.
    """
    atual = amostra_guardada()
    if atual.get("estado") != "baixado" or not os.path.exists(atual.get("arquivo") or ""):
        print("Amostra: o vídeo baixado não está no servidor")
        return 1
    conferencia = conferir_o_video(atual["arquivo"], atual["foto"])
    print(f"Amostra: conferência da IA: {ROTULOS_DA_CONFERENCIA[conferencia['mesmo']]}")
    try:
        ok = avisar_rafael.mandar_video(atual["arquivo"], legenda_da_amostra(atual, conferencia))
    except Exception as e:
        print(f"Amostra: o envio ao privado falhou ({type(e).__name__}); a próxima amostra manda de novo")
        return 1
    if not ok:
        print("Amostra: o Telegram não aceitou o vídeo; a próxima amostra manda de novo")
        return 1
    marcar_amostra(estado="enviado", enviado_em=agora(), mesmo_produto=conferencia["mesmo"])

    def anotar(dados):
        dados["amostras_feitas"] = ([i for i in dados.get("amostras_feitas") or [] if str(i) != str(atual["item"])]
                                    + [str(atual["item"])])[-ITENS_LEMBRADOS:]
    db.atualizar_config(CHAVE, anotar)
    print(f"Amostra nº {atual.get('numero', 1)}: vídeo mandado no privado do Rafael")
    try:
        foto = avisar_rafael.mandar_foto(atual["foto"], (
            f"🖼️ Foto do anúncio, para comparar com a amostra nº {atual.get('numero', 1)}\n"
            f"🔗 Anúncio: {link_do_anuncio(atual.get('link', ''))}")[:1000])
    except Exception:
        foto = False
    print("Amostra: foto e link do anúncio mandados" if foto else "Amostra: a foto do anúncio não foi ao privado")
    return 0


def amostra(sem_gerar=False):
    """
    A próxima amostra do vídeo de IA (P236 1): escolhe o produto como a produção, gera no MODELO_DA_PRODUCAO, baixa
    e manda no privado do Rafael. A que já foi gerada só é baixada e mandada (nunca dois Gerar para a mesma amostra).
    sem_gerar: tudo até o Gerar, sem tocar nele. 0 deu certo, 1 parou. Só rótulos fixos e números no log.
    """
    atual = amostra_guardada()
    if atual.get("estado") == "baixado" and os.path.exists(atual.get("arquivo") or ""):
        print(f"Amostra nº {atual.get('numero', 1)}: já baixada; falta mandar")
        return mandar_a_amostra()
    so_baixar = atual.get("estado") == "gerando"
    if so_baixar:
        print(f"Amostra nº {atual.get('numero', 1)}: já gerada; falta baixar e mandar")
    else:
        # Só aqui: o robô importa este módulo, e a escolha é a dele (P234 1).
        import robo_shopee_video as robo
        try:
            escolhido, origem, _restam = robo.escolher_para_o_video_de_ia(fora=amostras_feitas(), amostra=True)
        except api_shopee.BuscaNegada as e:
            print(f"Amostra: a API da Shopee negou a lista de produtos ({e}); nada foi tocado")
            return 1
        if not escolhido:
            print("Amostra: nenhum produto da lista serviu agora (a foto ou o link curto); nada foi tocado")
            return 1
        os.makedirs(PASTA, exist_ok=True)
        foto = os.path.join(PASTA, "amostra.jpg")
        with open(foto, "wb") as arquivo:
            arquivo.write(escolhido["foto"])
        modelo, custo = MODELO_DA_PRODUCAO
        atual = {chave: escolhido.get(chave) for chave in ("link", "nome", "item", "valor", "origem", "estilo",
                                                            "prompt", "cena")}
        atual.update(foto=foto, modelo=modelo, custo=custo, estado="escolhido", criado_em=agora(),
                     numero=len(amostras_feitas()) + 1)
        guardar(amostra=atual, estilos=(estilos_recentes() + [escolhido["estilo"]])[-ESTILOS_LEMBRADOS:])
        print(f"Amostra nº {atual['numero']}: produto escolhido (o {escolhido.get('posicao')}º de {origem}); "
              f"estilo {escolhido['estilo']}; pedido da IA com {len(escolhido['prompt'].split())} palavras")
    if not celular_robo.conectado():
        print("celular: desconectado; conecte pelo bot (Shopee Vídeo 🎬 → Celular do Robô 📱)")
        return 1
    tentativas = ps.ESPERA_DO_CELULAR // ps.PAUSA_DA_ESPERA + 1
    for tentativa in range(tentativas):
        with celular_robo.trava() as livre:
            if livre:
                codigo = _amostra_no_celular(atual, sem_gerar, so_baixar)
                break
        if tentativa == 0:
            print(f"celular: o robô automático está tocando no celular; esperando ele soltar "
                  f"(até {ps.ESPERA_DO_CELULAR // 60} min)")
        if tentativa < tentativas - 1:
            time.sleep(ps.PAUSA_DA_ESPERA)
    else:
        print("celular: o robô automático continua tocando no celular; nada foi tocado")
        return 1
    # A conferência da IA e o envio ao privado vêm com o celular já solto para o robô automático.
    if codigo == 0 and not sem_gerar:
        return mandar_a_amostra()
    return codigo


def _amostra_no_celular(atual, sem_gerar, so_baixar):
    """A amostra no celular, com a trava na mão: a tela, a foto, o Flow, o Gerar e o Baixar. 0 deu certo, 1 parou."""
    if celular_robo.tela_acesa() is False:
        ps.conectar(celular=True).screen_on()
        time.sleep(2)
    if celular_robo.tela_acesa() is False or celular_robo.tela_de_bloqueio():
        print("celular: a tela está apagada ou na tela de bloqueio; nada foi tocado")
        return 1
    d = ps.conectar(celular=True)
    try:
        feito = no_flow(d, atual, atual["modelo"], atual["custo"], os.path.join(PASTA, "amostra.mp4"),
                        marcar_amostra, sem_gerar=sem_gerar, so_baixar=so_baixar, guardar_telas=False)
    except Parada as e:
        casos_robo.guardar(d, "flow", "parou", str(e), passo="flow")
        print(f"Amostra: parou: {e}")
        return 1
    return 0 if feito else 1


def teste(sem_gerar=False):
    """O próximo vídeo do teste (um modelo por vez); com sem_gerar, tudo até o Gerar, sem tocar nele."""
    teste_de_agora = teste_guardado()
    if not teste_de_agora:
        escolhido = escolher_o_produto()
        if not escolhido:
            print(f"Nenhum dos próximos {PRODUTOS_TENTADOS} vídeos da fonte tem uma foto boa para o vídeo: "
                  "o teste não roda.")
            return 1
        os.makedirs(PASTA, exist_ok=True)
        caminho = os.path.join(PASTA, "foto_do_teste.jpg")
        with open(caminho, "wb") as arquivo:
            arquivo.write(escolhido["foto"])
        teste_de_agora = {"link": escolhido["link"], "nome": escolhido["nome"], "foto": caminho,
                          "estilo": escolhido["estilo"], "prompt": escolhido["prompt"], "cena": escolhido["cena"],
                          "criado_em": agora(), "videos": {}}
        # O estilo entra na lista dos últimos, para o próximo vídeo variar (pedido do Rafael, 15/11).
        guardar(teste=teste_de_agora, estilos=(estilos_recentes() + [escolhido["estilo"]])[-ESTILOS_LEMBRADOS:])
        print(f"Produto do teste: escolhido (o {escolhido['tentados']}º dos próximos vídeos da fonte); "
              f"estilo {escolhido['estilo']}; pedido da IA com {len(escolhido['prompt'].split())} palavras")
    # O vídeo já gerado vai ao Rafael antes de outro ser gerado: o baixado só falta mandar (sem o
    # celular); o que ficou gerando é baixado agora.
    pendente = None if sem_gerar else video_pendente(teste_de_agora)
    if pendente:
        modelo = pendente
        custo = ((teste_de_agora.get("videos") or {}).get(modelo) or {}).get("custo", 0)
        if os.path.exists(((teste_de_agora.get("videos") or {}).get(modelo) or {}).get("arquivo") or ""):
            print(f"Vídeo do teste: {modelo} já baixado; falta mandar")
            return mandar_o_baixado(modelo, custo)
        print(f"Vídeo do teste: {modelo} já gerado; falta baixar e mandar")
    else:
        proximo = proximo_modelo(teste_de_agora)
        if not proximo:
            print("Os 3 vídeos do teste já foram gerados.")
            return 0
        modelo, custo = proximo
        print(f"Vídeo do teste: {modelo} ({custo} créditos)")
    if not celular_robo.conectado():
        print("celular: desconectado; conecte pelo bot (Shopee Vídeo 🎬 → Celular do Robô 📱)")
        return 1
    if not ps.no_horario_das_rodadas():
        inicio, fim = ps.horario_das_rodadas()
        print(f"celular: fora do horário das rodadas ({inicio}h às {fim}h de Brasília); nada foi tocado")
        return 1
    tentativas = ps.ESPERA_DO_CELULAR // ps.PAUSA_DA_ESPERA + 1
    for tentativa in range(tentativas):
        with celular_robo.trava() as livre:
            if livre:
                codigo = no_celular(teste_de_agora, modelo, custo, sem_gerar, so_baixar=bool(pendente))
                break
        if tentativa == 0:
            print(f"celular: o robô automático está tocando no celular; esperando ele soltar "
                  f"(até {ps.ESPERA_DO_CELULAR // 60} min)")
        if tentativa < tentativas - 1:
            time.sleep(ps.PAUSA_DA_ESPERA)
    else:
        print("celular: o robô automático continua tocando no celular; nada foi tocado")
        return 1
    # A conferência da IA e o envio ao privado vêm com o celular já solto para o robô automático.
    if codigo == 0 and not sem_gerar:
        return mandar_o_baixado(modelo, custo)
    return codigo


def main(argumentos):
    if argumentos and argumentos[0] in ("teste", "amostra") and set(argumentos[1:]) <= {"--sem-gerar"}:
        # Os módulos logam nomes e links; aqui o log é público, e o resultado sai pelos prints.
        logging.disable(logging.CRITICAL)
        try:
            return (teste if argumentos[0] == "teste" else amostra)(sem_gerar="--sem-gerar" in argumentos)
        except Exception as e:
            # Só o tipo: a mensagem de um erro inesperado pode trazer o nome do arquivo do vídeo.
            print(f"Flow: erro inesperado ({type(e).__name__})")
            return 1
        finally:
            logging.disable(logging.NOTSET)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
