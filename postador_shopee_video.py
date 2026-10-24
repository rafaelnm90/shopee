#!/usr/bin/env python3
"""
Robô da Shopee Vídeo: opera o app da Shopee no Android virtual (android_virtual.py)
como uma pessoa, tocando na tela, para postar os vídeos dos Autorais com os
produtos vinculados. A Shopee Vídeo só aceita postagem pelo app.

Por enquanto ele só explora: faz os passos pedidos e descreve cada tela (botões,
campos e onde ficam), para ensinar o caminho da postagem que o Rafael mostrou
no tutorial. Roda à mão pelo workflow android.yml (ação explorar) ou no servidor:

    python3 postador_shopee_video.py --explorar "abrir; tocar:Eu; tocar:Criadores"
    python3 postador_shopee_video.py --explorar --celular "tela"   # no celular guardado

Com --celular, explora no celular de verdade do Rafael (celular_robo.py), pareado pelo
bot; sem ele, no Android virtual. No celular, só dentro do Horário do Robô 🕗 do painel
(padrão: das 8h às 22h de Brasília): a verificação da Shopee precisa do Rafael acordado
para resolver. Com o robô automático (robo_shopee_video.py) tocando no celular, nem começa.

Passos, separados por ponto e vírgula:
    abrir            abre o app da Shopee (fechar: fecha)
    tocar:TEXTO      toca no botão com esse texto ou descrição (tocar:@id pelo id)
    xy:X,Y           toca nesse ponto da tela
    voltar, inicio   as teclas do Android
    rolar:baixo      arrasta a tela (rolar:cima)
    esperar:N        espera N segundos
    escrever:TEXTO   escreve no campo que está com o cursor
    video            põe na galeria o vídeo do teste (video:novo escolhe outro na fonte;
                     video:link-de-video, um cujo link abre um vídeo, o Ver Produtos)
    link             abre no app o produto (ou o vídeo) do vídeo do teste
    curtir           na página que o link abriu, toca no nome do produto (abre a página
                     completa) e curte; já curtido, segue sem tocar no coração
    titulo           escreve no campo com o cursor o título da IA para o vídeo do teste
    comentario       manda no privado do Rafael o comentário da IA (o da mesma resposta do
                     titulo), numa mensagem só dele, depois do lembrete de curtir e comentar
    ia               a IA assiste ao vídeo do teste duas vezes e diz se o produto do link é o
                     do vídeo; segue só se as duas confirmarem
    produto          na lista de Adicionar Produto, toca em Adicionar só no produto do vídeo
                     do teste, achado pelo nome, e confere o nome na janela que abre
    conferir         confere na tela final que o produto anexado é o do vídeo (o toque em
                     Rascunhos faz essa conferência antes, sozinho)
    postar           toca em Postar na tela final, com o produto conferido de novo na hora
    print            manda um print da tela no privado do Rafael (nunca no log); print:postar
                     avisa que é a tela antes de postar
    legenda          compara a legenda da tela final com o título do passo titulo (só
                     tamanhos e códigos de caractere no log, nunca o texto), lida de três
                     jeitos: pela cópia do campo, pela acessibilidade e pelo retrato da tela;
                     legenda:TEXTO compara com o texto dado
    colar:TEXTO      troca o texto do campo com o cursor pelo texto, colando (Ctrl+V)
    copiado          diz se o que está copiado no celular é um link da Shopee e o tamanho
                     dele (o link nunca vai para o log): é como o robô pega o link do post
    tela             só descreve a tela

ia, produto e conferir param a exploração quando o produto não bate, e avisam o Rafael
no privado, com o nome do produto (nunca no log): um produto errado no post rende ponto
de punição na Shopee.

O vídeo do teste sai da "Fonte dos Vídeos 🎞️" do painel da Shopee Vídeo, escolhido
como no modo assistente (o mais novo com arquivo e link ainda não mandado), e fica
guardado (chave CHAVE_TESTE): video, link e titulo usam sempre o mesmo, para o produto
curtido ser o do vídeo do rascunho. Só video:novo troca.

Nunca toca nos botões de comprar da página do produto (Compre agora, carrinho, chat), por
texto, id ou ponto. Em "Postar", só pelo passo postar: tocar e xy recusam, e o Claude só
dispara o postar depois do OK do Rafael no print da tela final. Nunca mexe
na Verificação (CAPTCHA) da Shopee: se ela aparece, antes ou depois de um passo, a
exploração para ali, e quem resolve é o Rafael, com a mão no celular ou pela tela do
celular, cujo link vai no privado dele (tela_android.py). Enquanto essa tela está
aberta, o explorar no celular nem começa.

Imprime a forma da tela, não o conteúdo, porque o log do Actions é público e a
tela mostra a conta do Rafael: palavra que não é de botão vira "…" e número
vira "#". Também nunca imprime os links.
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import asyncio
import json
import logging
import os
import re
import sys
import tempfile
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime

import android_virtual as av
import api_gemini
import assistente_shopee_video as assistente
import avisar_rafael
import celular_robo
import db
import legendas
import registro_processos
import links_shopee
from api_shopee import eh_video, link_para_converter, tipo_de_link
from fuso import fuso_horario

PACOTE = av.PACOTE_SHOPEE
PACOTE_SISTEMA = "com.android.systemui"
GALERIA = "/sdcard/DCIM/Camera"
CHAVE_PAINEL = "shopee_video"  # a mesma chave do painel_shopee_video
CHAVE_TESTE = "celular_robo_teste"
# Horas de Brasília (início, fim) em que uma rodada no celular pode começar, enquanto o
# Rafael não muda o Horário do Robô 🕗 no painel (chaves robo_inicio e robo_fim).
# Decisão do Rafael: DECISOES.md, Shopee Vídeo.
HORARIO_DAS_RODADAS = (8, 22)
LEGENDA_PRINT = "🤖 Robô da Shopee Vídeo: a tela antes de salvar o rascunho."
LEGENDA_PRINT_POSTAR = ("🤖 Robô da Shopee Vídeo: a tela antes de postar. Confira o vídeo, o título "
                        "e o produto: só posto com o seu OK.")
AVISO_SEM_PRODUTO = "🤖 Robô da Shopee Vídeo: nenhum produto foi adicionado ao vídeo."
AVISO_COMENTARIO = ("💬 Robô da Shopee Vídeo: o comentário deste vídeo vem na próxima mensagem. Depois de "
                    "postar, curta o vídeo e comente com aquele texto (toque nele, copie e cole).")
AVISO_IA = "🤖 Robô da Shopee Vídeo: a IA viu que o produto do link não é o produto do vídeo. Parei aqui."
AVISO_TELA_FINAL = ("🤖 Robô da Shopee Vídeo: na tela final, o produto anexado não é o do vídeo "
                    "(ou há produto a mais ou a menos). Não salvei nem postei; confira o celular.")
PROMPT_PRODUTO_DO_VIDEO = """Você confere um vídeo de afiliado da Shopee antes de ele ir para a Shopee Vídeo.
O link que vai junto com o vídeo leva a este produto: "{nome}".
Assista ao vídeo inteiro e diga se o produto mostrado no vídeo é esse produto (o mesmo produto, \
ou pelo menos o mesmo tipo de produto: vídeo de vestido infantil com link de vestido infantil confere; \
vídeo de vestido com link de fibra de cabelo não confere).
Responda só com um JSON: {{"confere": true ou false, "motivo": "uma frase curta"}}"""
AVISO_JANELA_ERRADA = ("🤖 Robô da Shopee Vídeo: a janela de editar o nome aberta no celular é de outro "
                       "produto, não do produto do vídeo. Parei sem tocar em Feito; confira o celular.")
# Quantas vezes o passo produto rola a lista de Minhas Curtidas atrás do produto do vídeo.
ROLAGENS_DO_PRODUTO = 3
# Quantas vezes o passo curtir rola a página completa do produto atrás do coração.
ROLAGENS_DO_CORACAO = 2
# Quantas vezes a IA confere o produto do link com o vídeo: ela já recusou um vídeo que
# tinha aceitado antes, então só segue com todas as respostas confirmando.
VEZES_DA_IA = 2
SEGUNDOS_DA_PAGINA = 8
# Nome cortado na lista só vale como o mesmo produto a partir deste tamanho.
TAMANHO_MINIMO_DO_NOME = 15
# Elemento de outro app até este tamanho (px) é coisa flutuante, como a bolinha da Motorola.
LADO_MAXIMO_FLUTUANTE = 400
NOME_NA_GALERIA = "autoral_shopee_video.mp4"
SEGUNDOS_DEPOIS_DO_PASSO = 3
MAXIMO_ESPERA = 60
MAXIMO_LINHAS = 150
# Quantos vídeos da fonte, ainda não usados, o video:link-de-video olha (cada um segue o
# link pela rede).
CANDIDATOS_DE_VIDEO = 60
# Teclas do Android para selecionar tudo, copiar e colar no campo em foco (Ctrl+A, C, V).
CTRL = 0x1000
TECLA_A, TECLA_C, TECLA_V = 29, 31, 50

# Palavras que aparecem nos botões e menus do app. Só elas saem no log como estão;
# o resto (nome da conta, nome de produto, comentário) vira "…".
PALAVRAS_DA_TELA = frozenset("""
    a o as os e ou de da do das dos em no na nos nas ao à com sem por para até um uma
    eu início inicio oficiais live lives vídeo vídeos video videos notificações para você
    criadores criador afiliados afiliado perfil shopee shopeevi postar próximo próxima
    adicionar adicionado produto produtos minha minhas meu meus loja todos todas curtidas
    curtir curtido favoritos rascunho rascunhos ver mais menos selecionar selecione capa
    hashtag legenda galeria biblioteca álbum álbuns recentes recente permitir cancelar ok
    fechar pular agora não sim relevância destaque preço pesquisar pesquisa buscar taxa
    comissão comprar cupom salvar dispositivo rótulo conteúdo gerado ia compartilhar
    automaticamente reutilização permitir efeitos efeito filtros filtro música texto
    captions figurinha figurinhas cortar voltar concluir confirmar continuar enviar seguir
    seguindo seguidores comentário comentários comentar vitrine amostras link conversão
    indique amigo central ajuda vivo editar gerenciar evento centro câmera camera gravar
    carregar fotos foto mencionados oferta melhor frete grátis entrar sair conta
    configurações acesso acessar arquivos mídia permissão durante uso app apenas desta vez
    sempre nunca atualizar atualização depois tarde entendi anterior aplicar pronto feito
    publicar publicado sucesso falhou tentar novamente salvo salva duração segundos
    minutos máximo mínimo escolha toque aqui novo nova criar categoria categorias também
    pode gostar opções detalhes sobre pedido pedidos pagar avaliar compras carteira
    histórico serviços financeiros atividades visto recentemente suporte moedas cupons
    ganhos comissões relatório upload duet costurar adesivos clipes tudo caminho envio
    postagem postagens publicação publicações modelo modelos ir lojas tela telas
    post next done cancel save draft drafts gallery album photos videos add product products
    excluir excluído excluídos apagar apagado deletar remover descartar copiar copiado
    fixado fixados fixar desafixar alterações deseja certeza perder perdido perdidas isso
    este esta esse essa será serão editado edição editando manter selecionado
    selecionados item itens tem mil parado parada erro achei consegui ficou título titulo lista
    nenhum nenhuma celular desconectado pausado horário rodada aprovado recusado pulado
    preparando mostrou mudou marcou apareceu abriu
    share like liked comment comments more button icon options copy delete pin pinned
    verificação verificar segurança arraste arrastar deslize deslizar controle deslizante
    quebra-cabeça peça complete completar tente atualizar erro carregando aguarde rede
    conexão internet ops algo deu errado página encontrada negado bloqueado suspeita
    atividade incomum robô humano captcha verify slide puzzle
    está estão disponível disponíveis indisponível removido removida foi foram existe
    encontrado encontrados vinculado vinculados vinculou ainda há possui sendo
    exibido exibidos ocultado privado expirou expirado
    saúde violação violações violou infração infrações penalidade penalidades pontos punição
    punições irrelevante contrafeito propriedade intelectual direitos autorais diretrizes
    comunidade política políticas regras aviso avisos status apelação apelações apelar
    apelada apelado recorrido recorrida recurso recursos razão motivo bem-sucedido
    malsucedido rejeitado rejeitada aprovada análise revisão pendente decisão retorno
    aprender postado postada últimos dias banida banido temporariamente suspensão suspensa
    período reincidência identificado identificada correspondente apresentado evidências
    orientamos gerou ação seu sua deixe-nos saber poderá desempenho data
""".split())
NUMERO = re.compile(r"[\d.,%R$()+x×/:#-]*\d[\d.,%R$()+x×/:#-]*")
PONTUACAO = ".,:;!?()[]{}\"'«»“”‘’-–—/|+*·•"
# Id que é nome de código (buttonActionBarBack, tv_drafts_box) vai para o log; o resto
# vira "…": o app também usa como id o endereço da imagem do produto, e o log é público.
ID_DE_CODIGO = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def mascarar(texto):
    """Forma do texto: palavras de botão e símbolos soltos (&, emoji) ficam, números viram # e o resto vira …"""
    partes = []
    for palavra in (texto or "").split():
        if palavra.strip(PONTUACAO).casefold() in PALAVRAS_DA_TELA or not any(c.isalnum() for c in palavra):
            partes.append(palavra)
        elif NUMERO.fullmatch(palavra):
            partes.append(re.sub(r"\d+", "#", palavra))
        elif not partes or partes[-1] != "…":
            partes.append("…")
    return " ".join(partes)


def _limites(no):
    """(x1, y1, x2, y2) do elemento; None se ele não tem tamanho."""
    achado = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", no.get("bounds", ""))
    if not achado:
        return None
    x1, y1, x2, y2 = map(int, achado.groups())
    return (x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None


def elementos(xml):
    """
    Elementos visíveis da tela que interessam: com texto, descrição, id ou que aceitam
    toque. As barras do Android (relógio, bateria, voltar) ficam de fora: só enchem o log.
    """
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError:
        return []
    achados = []
    for no in raiz.iter("node"):
        caixa = _limites(no)
        if not caixa or no.get("visible-to-user", "true") != "true" or no.get("package") == PACOTE_SISTEMA:
            continue
        texto, descricao = no.get("text", ""), no.get("content-desc", "")
        ident = no.get("resource-id", "").split(":id/")[-1]
        clicavel = no.get("clickable") == "true"
        if texto or descricao or ident or clicavel:
            achados.append({"texto": texto, "descricao": descricao, "id": ident, "clicavel": clicavel,
                            "classe": no.get("class", "").rsplit(".", 1)[-1], "caixa": caixa,
                            "marcado": no.get("checked") == "true", "pacote": no.get("package", "")})
    return achados


def descrever(xml):
    """Linhas da tela para o log: centro, tipo, id, texto e descrição mascarados."""
    linhas = []
    for el in elementos(xml)[:MAXIMO_LINHAS]:
        x1, y1, x2, y2 = el["caixa"]
        partes = [f"({(x1 + x2) // 2},{(y1 + y2) // 2})", el["classe"] or "?"]
        if el["id"]:
            partes.append(f"id={el['id'] if ID_DE_CODIGO.fullmatch(el['id']) else '…'}")
        if el["texto"]:
            partes.append(f'"{mascarar(el["texto"])}"')
        if el["descricao"]:
            partes.append(f'desc="{mascarar(el["descricao"])}"')
        if el["clicavel"]:
            partes.append("[toque]")
        if el["marcado"]:
            partes.append("[ligado]")
        linhas.append("  " + " ".join(partes))
    sobra = len(elementos(xml)) - MAXIMO_LINHAS
    if sobra > 0:
        linhas.append(f"  (+{sobra} elementos)")
    return linhas


def _normal(texto):
    return " ".join((texto or "").split()).casefold()


def achar(xml, alvo):
    """
    Centro do elemento com esse texto ou descrição: primeiro igual, depois começando
    assim, depois contendo. "@id" procura pelo id. None se não achou.
    """
    lista = elementos(xml)
    if alvo.startswith("@"):
        candidatos = [el for el in lista if el["id"] == alvo[1:]]
    else:
        procurado = _normal(alvo)
        candidatos = []
        for criterio in (str.__eq__, str.startswith, str.__contains__):
            candidatos = [el for el in lista
                          if any(criterio(_normal(el[campo]), procurado) for campo in ("texto", "descricao")
                                 if el[campo])]
            if candidatos:
                break
    if not candidatos:
        return None
    x1, y1, x2, y2 = candidatos[0]["caixa"]
    return (x1 + x2) // 2, (y1 + y2) // 2


def eh_verificacao(xml):
    """A Shopee está pedindo a Verificação (CAPTCHA) nesta tela?"""
    return any("captcha" in f"{el['id']} {el['texto']}".casefold() or _normal(el["texto"]) == "verificação"
               for el in elementos(xml))


AVISO_VERIFICACAO = "\n== verificação na tela: parado; o Rafael resolve com a mão no celular"


# Botões que tocar e xy nunca tocam: o que publica o vídeo (só o passo postar chega nele) e
# os de comprar (Compre agora, carrinho e chat na página do produto; "Comprar com cupom"
# no player de um vídeo, visto no Motorola em 23/10/2026): todo texto que começa com
# "comprar" ou "compre". "Postar vídeo" não entra: só abre a câmera. Postar: DECISOES.md,
# Shopee Vídeo.
TEXTOS_PROIBIDOS = frozenset({"postar", "compre agora", "comprar agora", "adicionar ao carrinho"})
COMECOS_PROIBIDOS = ("comprar", "compre")
IDS_PROIBIDOS = frozenset({"btn_post", "buttonProductBuyNow", "buttonProductAddCart", "buttonProductChatNow"})
RECUSA = "recusado: a exploração nunca toca em Postar nem nos botões de comprar"


def texto_proibido(texto):
    """O texto é de um botão que o robô nunca toca (Postar ou de comprar)?"""
    normal = _normal(texto)
    return normal in TEXTOS_PROIBIDOS or any(normal == c or normal.startswith(c + " ") for c in COMECOS_PROIBIDOS)


def eh_alvo_proibido(alvo):
    """O alvo de um tocar (texto ou @id) é um dos botões proibidos?"""
    if alvo.startswith("@"):
        return alvo[1:] in IDS_PROIBIDOS
    return texto_proibido(alvo)


def proibido_no_ponto(xml, x, y):
    """Algum botão proibido cobre esse ponto da tela? Vale para o toque por texto e por xy."""
    for el in elementos(xml):
        x1, y1, x2, y2 = el["caixa"]
        if x1 <= x <= x2 and y1 <= y <= y2 and (
                el["id"] in IDS_PROIBIDOS or any(texto_proibido(el[campo]) for campo in ("texto", "descricao"))):
            return True
    return False


def video_da_fonte(de_video=False):
    """
    {"id", "arquivo", "link", "nome"} do vídeo que o modo assistente mandaria agora,
    da fonte escolhida no painel; None sem nenhum. Com de_video=True, o mais novo cujo
    link abre um vídeo (Ver Produtos), fora o vídeo do teste de agora, para mapear esse
    caminho no celular.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    fonte = (db.ler_config(CHAVE_PAINEL, {}) or {}).get("fonte", assistente.FONTE_PADRAO)
    if not de_video:
        video = assistente.proximo_video(fonte)
        return dict(video, arquivo=os.path.abspath(video["arquivo"])) if video else None
    anterior = (db.ler_config(CHAVE_TESTE, {}) or {}).get("id")
    for id_unico, arquivo, link, legenda in assistente.candidatos_nao_usados(fonte)[:CANDIDATOS_DE_VIDEO]:
        # O de agora fica de fora: video:link-de-video de novo passa para o seguinte.
        if id_unico == anterior or not (link and arquivo and os.path.exists(arquivo)):
            continue
        if eh_video(asyncio.run(link_para_converter(link))):
            return {"id": id_unico, "arquivo": os.path.abspath(arquivo), "link": link,
                    "nome": legendas.nome_da_legenda(legenda)}
    return None


def video_do_teste(novo=False, de_video=False):
    """
    O vídeo do teste no celular: com novo=True (passo video:novo), escolhe na fonte e
    guarda; sem, devolve o guardado, enquanto o arquivo existir. None sem nenhum.
    de_video=True (passo video:link-de-video) escolhe um cujo link abre um vídeo.
    """
    guardado = db.ler_config(CHAVE_TESTE, {}) or {}
    if not novo and guardado.get("arquivo") and os.path.exists(guardado["arquivo"]):
        return guardado
    video = video_da_fonte(de_video)
    if video:
        db.salvar_config(CHAVE_TESTE, video)
    return video


def escrever(d, texto):
    """
    Escreve no campo com o cursor pela acessibilidade do Android (o set_text do campo em
    foco): o texto entra inteiro, com os emojis, no lugar do que havia no campo. Sem campo
    em foco, cai no send_keys.
    """
    campo = d(focused=True)
    if campo.exists:
        campo.set_text(texto)
    else:
        d.send_keys(texto)


def escrever_titulo(d, video):
    """Escreve o título da IA (prompt do Gem e diretrizes) no campo com o cursor. (ok, o que dizer no log)."""
    textos = asyncio.run(assistente.textos_do_video(video["arquivo"], video.get("nome") or ""))
    if textos and textos["violacao"]:
        return False, "a IA viu violação das diretrizes: título não escrito"
    if not textos or not textos["titulo"]:
        return False, "a IA não devolveu título"
    escrever(d, textos["titulo"])
    # O título fica guardado para a aprovação do rascunho mostrar o texto que está na
    # legenda, e o comentário (da mesma resposta da IA) para o passo comentario.
    db.salvar_config(CHAVE_TESTE, dict(video, titulo=textos["titulo"], comentario=textos.get("comentario") or ""))
    return True, f"título com {len(textos['titulo'])} caracteres"


def mandar_comentario(video):
    """
    Manda no privado do Rafael o lembrete de curtir e comentar à mão depois de postar
    (curtir e comentar nunca são automáticos, diretriz 9.1.1) e, numa mensagem só dele,
    o comentário da IA: emendado no lembrete, ficava difícil de copiar. O texto não vai
    para o log.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    comentario = (video.get("comentario") or "").strip()
    if not comentario:
        return False, "nenhum comentário guardado: o passo titulo vem antes"
    if not (avisar_rafael.mandar_texto(AVISO_COMENTARIO) and avisar_rafael.mandar_texto(comentario)):
        return False, "o Telegram recusou o comentário"
    return True, f"comentário com {len(comentario)} caracteres mandado no privado"


def _centro(el):
    x1, y1, x2, y2 = el["caixa"]
    return (x1 + x2) // 2, (y1 + y2) // 2


def _dentro(ponto, caixa):
    x1, y1, x2, y2 = caixa
    return x1 <= ponto[0] <= x2 and y1 <= ponto[1] <= y2


def mesmo_produto(texto, nome):
    """
    O texto da tela é o nome desse produto? Igual, ou um começa com o outro, porque a
    lista pode cortar o nome com reticências; o pedaço cortado precisa ser grande o
    bastante para não confundir dois produtos parecidos.
    """
    a, b = (_normal(t).rstrip(".… ") for t in (texto, nome))
    if not a or not b:
        return False
    curto, longo = sorted((a, b), key=len)
    return a == b or (len(curto) >= TAMANHO_MINIMO_DO_NOME and longo.startswith(curto))


def nome_na_pagina(texto, nome):
    """
    O texto da tela é o nome desse produto? O app pode pôr um pedaço curto antes do nome
    (o selo "Oficial", um número), na página do produto e nas listas: vale o nome
    começando numa das primeiras palavras, com a mesma régua de mesmo_produto. Usado em
    todo lugar em que o robô confere o nome na tela (página, Minhas Curtidas, janela de
    editar e tela final), para os quatro aceitarem o mesmo nome.
    """
    palavras = (texto or "").split()
    return any(mesmo_produto(" ".join(palavras[i:]), nome) for i in range(min(len(palavras), 4)))


def parecido_na_tela(xml, nome):
    """
    Quando o nome não é achado: o quanto o texto mais parecido da tela lembra o nome do
    produto, em números (o nome não sai daqui): (% das palavras do nome que estão nele,
    quantas palavras vêm antes do nome nele, ou -1 se o nome não começa em nenhuma).
    Diz se o produto estava na lista com outro nome ou se não estava.
    """
    # Palavras de 3 letras ou mais: "de", "a" e "e" estão em quase todo nome.
    alvo = {p for p in _normal(nome).split() if len(p) >= 3}
    melhor = (0, -1)
    for el in elementos(xml):
        texto = _normal(el["texto"]).rstrip(".… ")
        if len(texto) < TAMANHO_MINIMO_DO_NOME or not alvo:
            continue
        palavras = texto.split()
        comum = len(alvo & set(palavras)) * 100 // len(alvo)
        antes = next((i for i in range(len(palavras)) if mesmo_produto(" ".join(palavras[i:]), nome)), -1)
        melhor = max(melhor, (comum, antes))
    return melhor


def adicionar_do_produto(xml, nome):
    """
    O botão Adicionar do produto com esse nome na lista de Adicionar Produto; None se
    ele não está na tela. O botão certo é o único Adicionar dentro do menor bloco de
    toque que contém o nome: com mais de um, o bloco é a lista e o robô não adivinha.
    """
    lista = elementos(xml)
    botoes = [el for el in lista if _normal(el["texto"]) == "adicionar"]
    for el in lista:
        if not nome_na_pagina(el["texto"], nome):
            continue
        blocos = sorted((b for b in lista if b["clicavel"] and _dentro(_centro(el), b["caixa"])),
                        key=lambda b: (b["caixa"][2] - b["caixa"][0]) * (b["caixa"][3] - b["caixa"][1]))
        for bloco in blocos:
            dentro = [bt for bt in botoes if _dentro(_centro(bt), bloco["caixa"])]
            if len(dentro) == 1:
                return dentro[0]
            if dentro:
                break
    return None


def ponto_livre(botao, xml):
    """
    Ponto do botão que nenhum outro app cobre: a bolinha de dicas da Motorola fica em
    cima do Adicionar do 1º produto e pega o toque. O centro ou, coberto, as pontas;
    None se o botão todo está coberto. Só conta o que flutua (pequeno), não uma tela inteira.
    """
    x1, y1, x2, y2 = botao["caixa"]
    meio = (y1 + y2) // 2
    cobertas = [el["caixa"] for el in elementos(xml)
                if el["pacote"] and el["pacote"] != botao["pacote"]
                and el["caixa"][2] - el["caixa"][0] <= LADO_MAXIMO_FLUTUANTE
                and el["caixa"][3] - el["caixa"][1] <= LADO_MAXIMO_FLUTUANTE]
    for x in ((x1 + x2) // 2, x1 + (x2 - x1) // 5, x2 - (x2 - x1) // 5):
        if not any(_dentro((x, meio), caixa) for caixa in cobertas):
            return x, meio
    return None


def nome_do_produto(video):
    """
    Nome do produto do vídeo pela API de afiliado, a partir do link; "" quando o link não
    diz. Num link de vídeo (Ver Produtos), o nome vem da página do produto no celular e fica
    em video["produto"].
    """
    if (video or {}).get("produto"):
        return video["produto"]
    if not (video or {}).get("link"):
        return ""
    produtos, _ = asyncio.run(assistente.produtos_do_link(video["link"]))
    return produtos[0]["nome"] if produtos else ""


def adicionar_produto(d, video):
    """
    Toca em Adicionar só no produto do vídeo, achado pelo nome, rolando a lista se
    preciso, e confere o nome de novo na janela "Editar nome do produto" que abre.
    Pela posição, um toque desviado adiciona outro produto: a bolinha de dicas da
    Motorola fica em cima do Adicionar do 1º, e o toque que a fecha pode cair na lista.
    Sem achar ou com outro produto na janela, não segue (o Feito fica sem tocar) e avisa
    o Rafael no privado; o nome não vai para o log.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    nome = nome_do_produto(video)
    if not nome:
        avisar_rafael.mandar_texto(f"{AVISO_SEM_PRODUTO}\n\nO link do vídeo não diz qual é o produto.")
        return False, "o link não diz o produto do vídeo: nada adicionado (aviso no privado)"
    if janela_de_editar_aberta(elementos(d.dump_hierarchy())):
        # Um toque de antes (como o que fecha a bolinha da Motorola) já abriu um produto.
        return conferir_janela(d, nome, None)
    for rolagem in range(ROLAGENS_DO_PRODUTO + 1):
        tela = d.dump_hierarchy()
        botao = adicionar_do_produto(tela, nome)
        if botao:
            ponto = ponto_livre(botao, tela)
            if not ponto:
                return False, "o Adicionar do produto está coberto por outro app: nada tocado"
            x, y = ponto
            if proibido_no_ponto(tela, x, y):
                return False, RECUSA
            d.click(x, y)
            return conferir_janela(d, nome, ponto)
        if rolagem < ROLAGENS_DO_PRODUTO:
            rolar(d)
            time.sleep(SEGUNDOS_DEPOIS_DO_PASSO)
    # Para a próxima vez dar para saber a causa: o produto estava com outro nome ou não estava.
    comum, antes = parecido_na_tela(tela, nome)
    registro_processos.registrar("shopee_video", "anexar o produto", "nome não achado em Minhas Curtidas",
                                 f"o mais parecido tem {comum}% das palavras"
                                 + (f" e o nome começa depois de {antes} palavra(s)" if antes > 0 else ""), ok=False)
    avisar_rafael.mandar_texto(f"{AVISO_SEM_PRODUTO}\n\nO produto do vídeo não está em Minhas Curtidas: {nome}")
    return False, "o produto do vídeo não está na lista: nada adicionado (aviso no privado)"


def janela_de_editar_aberta(lista):
    """A janela "Editar nome do produto" (a do Feito) está na tela?"""
    return any(_normal(el["texto"]) == "feito" for el in lista)


def conferir_janela(d, nome, ponto):
    """
    A janela "Editar nome do produto" mostra o produto do vídeo? Depois do Adicionar
    (ponto = onde tocou) ou quando ela já estava aberta no começo do passo (ponto None).
    """
    if ponto:
        time.sleep(SEGUNDOS_DEPOIS_DO_PASSO)
    lista = elementos(d.dump_hierarchy())
    if not janela_de_editar_aberta(lista):
        return False, f"Adicionar tocado em {ponto}, mas a janela de editar o nome não abriu"
    if not any(nome_na_pagina(el["texto"], nome) for el in lista):
        avisar_rafael.mandar_texto(f"{AVISO_JANELA_ERRADA}\n\nO produto do vídeo é: {nome}")
        return False, "a janela de editar o nome é de outro produto: Feito não tocado (aviso no privado)"
    if not ponto:
        return True, "a janela do produto do vídeo já estava aberta; nada tocado"
    return True, f"produto do vídeo achado pelo nome; Adicionar tocado em {ponto}; a janela confere"


def ia_confere_produto(video, vistos=None, avisar=True):
    """
    A IA assiste ao vídeo com o nome do produto do link e diz se é o mesmo produto:
    pega o link errado que vem da fonte antes de qualquer toque. Confere VEZES_DA_IA
    vezes, porque já recusou um vídeo que tinha aceitado antes. Sem confirmação em todas
    (não confere, não respondeu ou o link não diz o produto), a exploração para.
    vistos (lista): recebe o que a IA disse em cada vez, para o Rafael ver no rascunho.
    avisar=False: o produto recusado não vira aviso no privado (nos produtos do Ver
    Produtos, o recusado só fica de fora). Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    nome = nome_do_produto(video)
    if not nome:
        avisar_rafael.mandar_texto(f"{AVISO_IA}\n\nO link do vídeo não diz qual é o produto.")
        return False, "o link não diz o produto do vídeo: a IA não tem o que conferir (aviso no privado)"
    for vez in range(1, VEZES_DA_IA + 1):
        resposta = asyncio.run(api_gemini.analisar_video_gemini(video["arquivo"],
                                                                PROMPT_PRODUTO_DO_VIDEO.format(nome=nome)))
        achado = re.search(r"\{.*\}", resposta or "", re.S)
        try:
            dados = json.loads(achado.group(0)) if achado else None
        except ValueError:
            dados = None
        if not isinstance(dados, dict):
            return False, f"a IA não respondeu à conferência ({vez}ª vez): parado"
        if dados.get("confere") is not True:
            if avisar:
                avisar_rafael.mandar_texto(f"{AVISO_IA}\n\nProduto do link: {nome}\nO que a IA viu: "
                                           f"{str(dados.get('motivo') or '').strip()}")
            return False, f"a IA viu outro produto no vídeo ({vez}ª vez): parado (aviso no privado)"
        if vistos is not None:
            vistos.append(str(dados.get("motivo") or "").strip())
    return True, f"a IA confere {VEZES_DA_IA} vezes: o produto do link é o do vídeo"


def tem_coracao(lista):
    """O coração da página completa do produto está na tela (curtido ou não)?"""
    return any(el["id"] in ("buttonItemLike", "buttonItemLiked") for el in lista)


def abrir_pagina_completa(d, video):
    """
    A página completa do produto do vídeo, a que tem o coração. O link abre uma página
    curta (foto, preço, nome com a seta ">" e Compre Agora), sem o coração: o robô toca no
    nome do produto, achado pelo nome da API, e rola se o coração ficar mais embaixo.
    Devolve (ok, o que dizer no log, a tela).
    """
    tela = d.dump_hierarchy()
    if tem_coracao(elementos(tela)):
        return True, "a página completa do produto já estava aberta", tela
    nome = nome_do_produto(video)
    if not nome:
        return False, "o link não diz o produto do vídeo: não sei em que nome tocar", tela
    alvo = next((el for el in elementos(tela) if nome_na_pagina(el["texto"], nome)), None)
    if not alvo:
        return False, "o nome do produto do vídeo não está na página: nada tocado", tela
    x, y = _centro(alvo)
    if proibido_no_ponto(tela, x, y):
        return False, RECUSA, tela
    d.click(x, y)
    time.sleep(SEGUNDOS_DA_PAGINA)
    for rolagem in range(ROLAGENS_DO_CORACAO + 1):
        tela = d.dump_hierarchy()
        if tem_coracao(elementos(tela)):
            return True, "nome tocado: a página completa do produto abriu", tela
        if rolagem < ROLAGENS_DO_CORACAO:
            rolar(d)
            time.sleep(SEGUNDOS_DEPOIS_DO_PASSO)
    return False, "o coração não está na página do produto: nada curtido", tela


def curtir(d, video):
    """
    Curte o produto do vídeo na página completa dele (abrir_pagina_completa). Já curtido
    (buttonItemLiked), segue sem tocar: o toque descurtiria. Sem achar o nome ou o
    coração, para sem curtir nada.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    ok, resultado, tela = abrir_pagina_completa(d, video)
    if not ok:
        return False, resultado
    return curtir_na_pagina(d, tela)


def curtir_na_pagina(d, tela):
    """
    Curte o produto da página que está aberta, com o coração já na tela: já curtido
    (buttonItemLiked), segue sem tocar, porque o toque descurtiria.
    """
    lista = elementos(tela)
    if not tem_coracao(lista):
        return False, "o coração não está na página do produto: nada curtido"
    if any(el["id"] == "buttonItemLiked" for el in lista):
        return True, "o produto já estava curtido: segui sem tocar no coração"
    coracao = next(el for el in lista if el["id"] == "buttonItemLike")
    d.click(*_centro(coracao))
    time.sleep(SEGUNDOS_DEPOIS_DO_PASSO)
    if not any(el["id"] == "buttonItemLiked" for el in elementos(d.dump_hierarchy())):
        return False, "toquei no coração, mas o produto não ficou curtido"
    return True, "produto curtido"


def nomes_dos_produtos(video):
    """
    Os produtos que vão no post: os do Ver Produtos que a IA confirmou (video["produtos"])
    ou o do link.
    """
    if (video or {}).get("produtos"):
        return list(video["produtos"])
    nome = nome_do_produto(video)
    return [nome] if nome else []


ROTULO_DE_IA = "Rótulo de conteúdo gerado por IA"


def chave_do_rotulo_de_ia(lista):
    """
    A chave do Rótulo de conteúdo gerado por IA na tela final: na mesma linha do nome, à
    direita (a frase que explica fica embaixo do nome, e as chaves de Salvar no dispositivo
    e de Compartilhar ficam nas linhas de cima e de baixo). None sem a linha na tela.
    """
    nome = next((el for el in lista if _normal(el["texto"]).startswith(_normal(ROTULO_DE_IA))), None)
    if not nome:
        return None
    _x0, topo, _x1, base = nome["caixa"]
    direita = 0.7 * max(el["caixa"][2] for el in lista)
    candidatas = [el for el in lista if el is not nome and (el["clicavel"] or "switch" in el["classe"].lower())
                  and _centro(el)[0] >= direita and topo - 40 <= _centro(el)[1] <= base + 120]
    centro = (topo + base) / 2
    # A chave de verdade é a de classe Switch; sem ela, o que aceita toque mais perto do nome.
    return min(candidatas, key=lambda el: ("switch" not in el["classe"].lower(), abs(_centro(el)[1] - centro)),
               default=None)


def ajustar_rotulo_de_ia(d, ligado):
    """
    Deixa o Rótulo de conteúdo gerado por IA como a IA decidiu: ligado só no vídeo
    claramente feito por IA; senão, desligado, como o app abre. Toca na chave e confere que
    ela mudou. Sem achar a chave: para se era para ligar (não vai sem o rótulo); se era para
    ficar desligado, segue como o app abre. Escolha do Rafael: DECISOES.md, Shopee Vídeo.
    """
    estado = "ligado" if ligado else "desligado"
    tela = d.dump_hierarchy()
    chave = chave_do_rotulo_de_ia(elementos(tela))
    if not chave:
        if ligado:
            return False, "o Rótulo de IA não está na tela final: nada salvo"
        return True, "o Rótulo de IA não está na tela: fica como o app abre (desligado)"
    if chave["marcado"] == ligado:
        return True, f"Rótulo de IA já {estado}"
    x, y = _centro(chave)
    if proibido_no_ponto(tela, x, y):
        return False, RECUSA
    d.click(x, y)
    time.sleep(SEGUNDOS_DEPOIS_DO_PASSO)
    depois = chave_do_rotulo_de_ia(elementos(d.dump_hierarchy()))
    if not depois or depois["marcado"] != ligado:
        return False, f"toquei no Rótulo de IA, mas ele não ficou {estado}"
    return True, f"Rótulo de IA {estado}"


def conferir_tela_final(d, video):
    """
    Na tela final, antes de Rascunhos (e, no robô pronto, de Postar): os produtos anexados
    têm de ser os do vídeo, um para um (o do link, ou os do Ver Produtos que a IA
    confirmou). Diferente, a mais, a menos ou nenhum: não segue e avisa.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    nomes = nomes_dos_produtos(video)
    anexados = [el["texto"] for el in elementos(d.dump_hierarchy()) if el["id"] == "tv_product_title"]
    sobrando = list(anexados)
    for nome in nomes:
        par = next((anexado for anexado in sobrando if nome_na_pagina(anexado, nome)), None)
        if par is None:
            break
        sobrando.remove(par)
    else:
        if nomes and not sobrando:
            return True, (f"tela final confere: os {len(nomes)} produtos anexados são os do vídeo" if len(nomes) > 1
                          else "tela final confere: o produto anexado é o do vídeo")
    avisar_rafael.mandar_texto(f"{AVISO_TELA_FINAL}\n\nProduto(s) do vídeo: {'; '.join(nomes) or 'o link não diz'}")
    return False, (f"tela final com {len(anexados)} produto(s) anexado(s) que não confere(m) com o(s) "
                   f"{len(nomes)} do vídeo: nada salvo (aviso no privado)")


# --- Link de vídeo: o Ver Produtos (mapeado no Motorola em 23/10/2026) ---
# O link abre o player do vídeo (Live e Vídeo) com "Ver Produtos (N)"; o toque abre, por
# cima, a lista com os produtos que o criador vinculou ao vídeo e, depois de "Ver Mais" e
# "Você Também Pode Gostar", recomendações da Shopee, que não são do vídeo. O toque no nome
# de um produto abre a página dele (HalfPdpActivity), com o coração e o nome no id
# labelProductPageProductName. Vídeo apagado: "Este vídeo foi removido".
FIM_DOS_VINCULADOS = ("ver mais", "você também pode gostar")


def video_removido(xml):
    """O link abriu o aviso de vídeo removido?"""
    return any(_normal(el["texto"]).startswith("este vídeo foi removido") for el in elementos(xml))


def _texto_de_nome(texto):
    """Texto que pode ser o nome do produto num cartão (não preço, desconto, nota nem botão)."""
    normal = _normal(texto)
    return bool(normal) and not (normal.startswith("r$") or normal[0].isdigit() or normal[0] in "-+#"
                                 or texto_proibido(normal) or normal == "apenas vídeo")


def produtos_vinculados(xml):
    """
    Onde tocar para abrir cada produto que o criador vinculou ao vídeo, na lista do Ver
    Produtos, de cima para baixo: o nome (o texto mais longo) de cada cartão abaixo do
    título e acima de "Ver Mais" e de "Você Também Pode Gostar". Ponto sobre um botão de
    comprar fica de fora.
    """
    lista = elementos(xml)
    topo = max((el["caixa"][3] for el in lista if _normal(el["texto"]).startswith("ver produtos")), default=0)
    fim = min((el["caixa"][1] for el in lista if _normal(el["texto"]).startswith(FIM_DOS_VINCULADOS)), default=10 ** 6)
    cartoes = sorted((el for el in lista if el["clicavel"] and el["caixa"][1] >= topo and el["caixa"][3] <= fim
                      and el["caixa"][2] - el["caixa"][0] >= 800 and 150 <= el["caixa"][3] - el["caixa"][1] <= 500),
                     key=lambda el: el["caixa"][1])
    pontos = []
    for cartao in cartoes:
        nomes = [el for el in lista if el["texto"] and _texto_de_nome(el["texto"]) and el is not cartao
                 and _dentro(_centro(el), cartao["caixa"])]
        if not nomes:
            continue
        x, y = _centro(max(nomes, key=lambda el: len(el["texto"])))
        if not proibido_no_ponto(xml, x, y):
            pontos.append((x, y))
    return pontos


def nome_na_pagina_do_produto(xml):
    """O nome do produto na página dele (labelProductPageProductName); "" sem ele."""
    return next((el["texto"].strip() for el in elementos(xml) if el["id"] == "labelProductPageProductName"), "")


def toca_em_rascunhos(xml, x, y):
    """O ponto cai no botão Rascunhos da tela final (tv_drafts_box)?"""
    return any(el["id"] == "tv_drafts_box" and _dentro((x, y), el["caixa"]) for el in elementos(xml))


def postar(d, video):
    """
    Toca em Postar uma vez, só na tela final e com o produto conferido de novo na hora.
    É o único caminho até esse botão: tocar e xy recusam. O Claude só dispara este passo
    depois do OK do Rafael no print da tela final (print:postar).
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    botoes = [el for el in elementos(d.dump_hierarchy()) if el["id"] == "btn_post"]
    if len(botoes) != 1:
        return False, "Postar não está na tela: nada postado"
    ok, resultado = conferir_tela_final(d, video)
    if not ok:
        return False, resultado
    d.click(*_centro(botoes[0]))
    return True, "Postar tocado, com a tela final conferida"


def rolar(d, para_cima=False):
    """Arrasta a tela no meio, de baixo para cima (o conteúdo desce) ou o contrário."""
    largura, altura = d.window_size()
    de, ate = (0.3, 0.75) if para_cima else (0.75, 0.3)
    d.swipe(largura // 2, int(altura * de), largura // 2, int(altura * ate), 0.4)


def mandar_print(d, legenda=LEGENDA_PRINT):
    """Print da tela no privado do Rafael. O arquivo sai do servidor logo depois."""
    descritor, caminho = tempfile.mkstemp(suffix=".png")
    os.close(descritor)
    try:
        d.screenshot(caminho)
        return avisar_rafael.mandar_foto(caminho, legenda)
    finally:
        if os.path.exists(caminho):
            os.remove(caminho)


def abrir_link(d, link):
    """
    Abre no app da Shopee o link do vídeo como veio, como o Rafael abre o link que o modo
    assistente manda: o app segue o link curto sozinho até o produto. Pelo endereço final
    do produto (/product/loja/item), o app fica preso no esqueleto da página, carregando.
    Devolve o tipo de página a que o link leva, para o log.
    """
    d.shell(["am", "start", "-a", "android.intent.action.VIEW", "-d", link, "-p", PACOTE])
    return tipo_de_link(asyncio.run(link_para_converter(link)))


def por_na_galeria(d, arquivo, nome=NOME_NA_GALERIA):
    """Copia o vídeo para a câmera do Android e avisa a galeria. True se ele apareceu nela."""
    destino = f"{GALERIA}/{nome}"
    d.shell(["mkdir", "-p", GALERIA])
    d.push(arquivo, destino)
    d.shell(["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", "file://" + destino])
    time.sleep(3)
    lista = d.shell(["content", "query", "--uri", "content://media/external/video/media",
                     "--projection", "_display_name"])
    return nome in getattr(lista, "output", "")


def texto_copiado(d):
    """O que está copiado no celular; "" se nada ou se o Android não deixou ler."""
    try:
        return (d.clipboard or "").strip()
    except Exception:
        return ""


def legenda_na_tela(xml):
    """O texto do campo da legenda (@et_caption) no retrato da tela; "" sem ele."""
    return next((el["texto"] for el in elementos(xml) if el["id"] == "et_caption"), "")


def legenda_lida(d):
    """
    O texto do campo da legenda pela acessibilidade do Android (get_text do uiautomator2;
    sem o campo, o retrato da tela). Essa leitura devolve cada emoji de fora do plano
    básico (💡, 👗) como ".." (no Motorola, em 23/10/2026, até a bio e as legendas postadas
    à mão vieram assim): serve para achar o campo, não para conferir esses emojis.
    """
    campo = d(resourceId=f"{PACOTE}:id/et_caption")
    if campo.exists:
        return campo.get_text() or ""
    return legenda_na_tela(d.dump_hierarchy())


def legenda_copiada(d):
    """
    O texto do campo da legenda em foco pela área de transferência: Ctrl+A e Ctrl+C no
    campo e lê o copiado, que vem como o app guardou, com os emojis. A área é limpa antes,
    para um copiado antigo nunca passar pelo texto do campo. "" quando o campo não está
    em foco, o app não copiou ou o Android não deixou ler.

    Só com a edição da legenda aberta (depois de tocar no campo): na tela final, o Ctrl+A
    abre a edição do texto e tira o Postar e o Rascunhos da tela (Motorola, 23/10/2026).
    """
    try:
        d.set_clipboard("")
        d.press(TECLA_A, CTRL)
        d.press(TECLA_C, CTRL)
    except Exception:
        return ""
    time.sleep(1)
    return texto_copiado(d)


def legenda_do_campo(d):
    """A legenda do campo pela cópia (com os emojis); sem a cópia, pela acessibilidade. Só na edição da legenda."""
    return legenda_copiada(d) or legenda_lida(d)


def como_o_android_le(texto):
    """O texto como a leitura pela acessibilidade o devolve: cada emoji de fora do plano básico vira ".."."""
    return "".join(".." if ord(c) > 0xFFFF else c for c in texto or "")


def colar(d, texto):
    """Troca o texto do campo em foco pelo texto, pela área de transferência (Ctrl+A e Ctrl+V), como quem cola."""
    d.set_clipboard(texto)
    d.press(TECLA_A, CTRL)
    d.press(TECLA_V, CTRL)


def _o_que_conta(texto):
    """
    O texto da legenda sem o que o app pode mudar sem mudar o título: espaços e quebras
    de linha, caracteres invisíveis (largura zero) e o seletor de variação dos emojis.
    """
    texto = unicodedata.normalize("NFC", texto or "")
    return "".join(c for c in texto if not c.isspace() and unicodedata.category(c) not in ("Cf", "Mn", "Cc"))


def mesma_legenda(na_tela, titulo):
    """A legenda da tela é o título guardado? O campo pode cortar o fim."""
    a, b = _o_que_conta(na_tela), _o_que_conta(titulo)
    return bool(a and b) and (a == b or (len(a) >= 25 and b.startswith(a.rstrip(".…"))))


def comparar_legenda(na_tela, titulo):
    """
    Onde a legenda da tela e o título diferem, só com tamanhos e códigos de caractere: o
    log do explorar é público e nunca leva o texto.
    """
    if mesma_legenda(na_tela, titulo):
        return f"a legenda é o título ({len(na_tela)} caracteres na tela, {len(titulo)} no título)"
    a, b = na_tela or "", titulo or ""
    i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    def codigo(texto):
        return f"U+{ord(texto[i]):04X}" if i < len(texto) else "fim"
    return (f"a legenda NÃO é o título: {len(a)} caracteres na tela, {len(b)} no título; a 1ª diferença "
            f"está no caractere {i + 1} (na tela {codigo(a)}, no título {codigo(b)})")


def link_copiado(d):
    """O link da Shopee que está copiado no celular (Copiar link do post); "" sem ele."""
    return links_shopee.primeiro_link(texto_copiado(d), links_shopee.PADRAO_LINK_QUALQUER) or ""


def separar_passos(texto):
    """Lista de (nome, argumento). Passo desconhecido vira ValueError antes de tocar em qualquer coisa."""
    conhecidos = {"abrir", "fechar", "tocar", "xy", "voltar", "inicio", "rolar", "esperar", "escrever",
                  "link", "video", "titulo", "comentario", "ia", "curtir", "produto", "conferir", "postar",
                  "print", "copiado", "legenda", "colar", "tela"}
    passos = []
    for pedaco in (texto or "").split(";"):
        pedaco = pedaco.strip()
        if not pedaco:
            continue
        nome, _, argumento = pedaco.partition(":")
        nome = nome.strip().lower()
        if nome not in conhecidos:
            raise ValueError(f"passo desconhecido: {nome}")
        passos.append((nome, argumento.strip()))
    return passos


def fazer_passo(d, nome, argumento):
    """Faz um passo. Devolve (deu certo, o que dizer no log)."""
    if nome == "abrir":
        d.app_start(PACOTE, wait=True)
        return True, "app aberto"
    if nome == "fechar":
        d.app_stop(PACOTE)
        return True, "app fechado"
    if nome == "tocar":
        if eh_alvo_proibido(argumento):
            return False, RECUSA
        tela = d.dump_hierarchy()
        ponto = achar(tela, argumento)
        if not ponto:
            return False, "não achei na tela"
        x, y = ponto
        if proibido_no_ponto(tela, x, y):
            return False, RECUSA
        if toca_em_rascunhos(tela, x, y):
            ok, resultado = conferir_tela_final(d, db.ler_config(CHAVE_TESTE, {}))
            if not ok:
                return False, resultado
        d.click(x, y)
        return True, f"tocado em {ponto}"
    if nome == "xy":
        x, y = (int(n) for n in argumento.split(","))
        tela = d.dump_hierarchy()
        if proibido_no_ponto(tela, x, y):
            return False, RECUSA
        if toca_em_rascunhos(tela, x, y):
            ok, resultado = conferir_tela_final(d, db.ler_config(CHAVE_TESTE, {}))
            if not ok:
                return False, resultado
        d.click(x, y)
        return True, f"tocado em ({x},{y})"
    if nome in ("voltar", "inicio"):
        d.press("back" if nome == "voltar" else "home")
        return True, "tecla apertada"
    if nome == "rolar":
        rolar(d, para_cima=argumento == "cima")
        return True, "rolado"
    if nome == "esperar":
        time.sleep(min(float(argumento or 1), MAXIMO_ESPERA))
        return True, "esperado"
    if nome == "escrever":
        escrever(d, argumento)
        return True, "escrito"
    if nome in ("link", "video", "titulo", "comentario", "ia", "curtir", "produto", "conferir", "postar"):
        escolher = nome == "video" and argumento in ("novo", "link-de-video")
        video = video_do_teste(novo=escolher, de_video=escolher and argumento == "link-de-video")
        if not video:
            return False, "nenhum vídeo da fonte do painel com arquivo e link"
        if nome == "link":
            return True, f"aberto: {abrir_link(d, video['link'])}"
        if nome == "titulo":
            return escrever_titulo(d, video)
        if nome == "comentario":
            return mandar_comentario(video)
        if nome == "ia":
            return ia_confere_produto(video)
        if nome == "curtir":
            return curtir(d, video)
        if nome == "produto":
            return adicionar_produto(d, video)
        if nome == "conferir":
            return conferir_tela_final(d, video)
        if nome == "postar":
            return postar(d, video)
        return ((True, "vídeo na galeria") if por_na_galeria(d, video["arquivo"])
                else (False, "o vídeo não apareceu na galeria"))
    if nome == "legenda":
        # Sem argumento, compara com o título guardado pelo passo titulo; com ele, com o texto dado.
        titulo = argumento or (db.ler_config(CHAVE_TESTE, {}) or {}).get("titulo") or ""
        tela = d.dump_hierarchy()
        contador = next((el["texto"] for el in elementos(tela) if el["id"] == "tv_content_num"), "")
        emojis = sum(ord(c) > 0xFFFF for c in titulo)
        return True, (f"pela cópia: {comparar_legenda(legenda_copiada(d), titulo)} | pela acessibilidade: "
                      f"{comparar_legenda(legenda_lida(d), titulo)} | pelo retrato da tela: "
                      f"{comparar_legenda(legenda_na_tela(tela), titulo)}") + (
            f"; contador do app: {contador}" if re.fullmatch(r"[\d/ ]+", contador or "") else "") + (
            f"; {emojis} emoji(s) de fora do plano básico no título")
    if nome == "colar":
        colar(d, argumento)
        return True, "colado"
    if nome == "copiado":
        texto, link = texto_copiado(d), link_copiado(d)
        if link:
            return True, f"link da Shopee copiado ({len(link)} caracteres, num texto de {len(texto)})"
        return False, ("nada copiado, ou o Android não deixou ler" if not texto
                       else f"o copiado ({len(texto)} caracteres) não tem link da Shopee")
    if nome == "print":
        legenda = LEGENDA_PRINT_POSTAR if argumento == "postar" else LEGENDA_PRINT
        return ((True, "print mandado no privado") if mandar_print(d, legenda)
                else (False, "o Telegram recusou o print"))
    return True, "só a tela"


def conectar(celular=False):
    """
    O Android pelo uiautomator2, que lê a tela mesmo com vídeo tocando (o uiautomator do
    adb trava): o celular guardado (celular=True) ou o Android virtual.
    """
    import uiautomator2
    if celular:
        return uiautomator2.connect(celular_robo.endereco())
    av.android_ligado()
    return uiautomator2.connect(av.ENDERECO_ADB)


def horario_das_rodadas():
    """(início, fim) das rodadas no celular, em horas de Brasília: o Horário do Robô 🕗 do painel."""
    config = db.ler_config(CHAVE_PAINEL, {}) or {}
    return (config.get("robo_inicio", HORARIO_DAS_RODADAS[0]), config.get("robo_fim", HORARIO_DAS_RODADAS[1]))


def no_horario_das_rodadas(agora=None):
    inicio, fim = horario_das_rodadas()
    return inicio <= (agora or datetime.now(fuso_horario)).hour < fim


def explorar(texto, d=None, celular=False):
    """
    Faz os passos e descreve a tela depois de cada um. Para no primeiro que falhar
    e na Verificação da Shopee. True se todos deram certo, False se um falhou ou a
    verificação apareceu e None se nem começou (passo desconhecido ou Android desligado).

    O log do Actions é público: nele só entram as linhas do próprio explorar (a forma
    da tela, estados e números). O log dos módulos que ele usa fica calado, porque a
    IA registra os endereços que chama, com o código da sessão de envio do vídeo.
    """
    logging.disable(logging.CRITICAL)
    try:
        if celular and d is None:
            with celular_robo.trava() as livre:
                if not livre:
                    print("celular: o robô automático está tocando no celular agora; nada foi tocado")
                    return None
                return _explorar(texto, d, celular)
        return _explorar(texto, d, celular)
    finally:
        logging.disable(logging.NOTSET)


def _explorar(texto, d, celular):
    print("== Explorando o app da Shopee")
    try:
        passos = separar_passos(texto)
    except ValueError as e:
        print(f"passos: {e}")
        return None
    if not passos:
        passos = [("tela", "")]
    if d is None:
        if celular and not celular_robo.conectado():
            print("celular: desconectado; conecte pelo bot (Shopee Vídeo 🎬 → Celular do Robô 📱)")
            return None
        if celular and not no_horario_das_rodadas():
            inicio, fim = horario_das_rodadas()
            print(f"celular: fora do horário das rodadas ({inicio}h às {fim}h de Brasília); nada foi tocado")
            return None
        if celular and av.tela_aberta():
            # O Rafael pode estar mexendo no celular pela tela: o robô não toca junto.
            print("celular: a tela do celular está aberta no privado do Rafael; nada foi tocado")
            return None
        if not celular and not av.android_ligado():
            print("android: desligado; rode o preparar antes")
            return None
        d = conectar(celular)
    if eh_verificacao(_tela(d)):
        return parar_na_verificacao(celular)
    for numero, (nome, argumento) in enumerate(passos, 1):
        try:
            ok, resultado = fazer_passo(d, nome, argumento)
        except Exception as e:
            ok, resultado = False, f"erro: {type(e).__name__}"
        print(f"\n== passo {numero}: {nome}{':' + argumento if argumento else ''} → {resultado}")
        if nome != "esperar":
            time.sleep(SEGUNDOS_DEPOIS_DO_PASSO)
        tela = ""
        try:
            atual = d.app_current()
            print(f"app: {atual.get('package', '?')} | tela: {atual.get('activity', '?').rsplit('.', 1)[-1]}")
            tela = d.dump_hierarchy()
            print("\n".join(descrever(tela)) or "  (tela sem elementos)")
        except Exception as e:
            print(f"tela: não deu para ler ({type(e).__name__})")
        if eh_verificacao(tela):
            return parar_na_verificacao(celular)
        if not ok:
            return False
    return True


def parar_na_verificacao(celular):
    """
    Para a exploração na verificação. No celular, manda no privado do Rafael o link da
    tela do celular, para ele resolver de onde estiver. Devolve False (a rodada parou).
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    print(AVISO_VERIFICACAO)
    if celular:
        av.abrir_tela(celular=True, verificacao=True)
    return False


def _tela(d):
    """A tela de agora; vazia se não deu para ler (o primeiro passo mostra o erro)."""
    try:
        return d.dump_hierarchy()
    except Exception:
        return ""


def codigo_de_saida(resultado):
    """
    Botão que não está na tela é resposta da exploração, não erro: o workflow só fica
    vermelho (e o GitHub manda e-mail ao Rafael) quando a exploração nem começou.
    """
    return 1 if resultado is None else 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--explorar":
        no_celular = sys.argv[2:3] == ["--celular"]
        passos = " ".join(sys.argv[3:] if no_celular else sys.argv[2:])
        sys.exit(codigo_de_saida(explorar(passos, celular=no_celular)))
    print(__doc__)
