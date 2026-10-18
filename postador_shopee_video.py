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
bot; sem ele, no Android virtual. No celular, só das 8h às 22h de Brasília
(HORARIO_DAS_RODADAS): a verificação da Shopee precisa do Rafael acordado para resolver.

Passos, separados por ponto e vírgula:
    abrir            abre o app da Shopee (fechar: fecha)
    tocar:TEXTO      toca no botão com esse texto ou descrição (tocar:@id pelo id)
    xy:X,Y           toca nesse ponto da tela
    voltar, inicio   as teclas do Android
    rolar:baixo      arrasta a tela (rolar:cima)
    esperar:N        espera N segundos
    escrever:TEXTO   escreve no campo que está com o cursor
    video            põe na galeria o vídeo do teste (video:novo escolhe outro na fonte)
    link             abre no app o produto (ou o vídeo) do vídeo do teste
    titulo           escreve no campo com o cursor o título da IA para o vídeo do teste
    ia               a IA assiste ao vídeo do teste e diz se o produto do link é o do vídeo
    produto          na lista de Adicionar Produto, toca em Adicionar só no produto do vídeo
                     do teste, achado pelo nome, e confere o nome na janela que abre
    conferir         confere na tela final que o produto anexado é o do vídeo (o toque em
                     Rascunhos faz essa conferência antes, sozinho)
    print            manda um print da tela no privado do Rafael (nunca no log)
    tela             só descreve a tela

ia, produto e conferir param a exploração quando o produto não bate, e avisam o Rafael
no privado, com o nome do produto (nunca no log): um produto errado no post rende ponto
de punição na Shopee.

O vídeo do teste sai da "Fonte dos Vídeos 🎞️" do painel da Shopee Vídeo, escolhido
como no modo assistente (o mais novo com arquivo e link ainda não mandado), e fica
guardado (chave CHAVE_TESTE): video, link e titulo usam sempre o mesmo, para o produto
curtido ser o do vídeo do rascunho. Só video:novo troca.

Nunca toca em "Postar" nem nos botões de comprar da página do produto (Compre agora,
carrinho, chat), por texto, id ou ponto: a exploração termina, no máximo, em Rascunhos. Nunca mexe
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
import xml.etree.ElementTree as ET
from datetime import datetime

import android_virtual as av
import api_gemini
import assistente_shopee_video as assistente
import avisar_rafael
import celular_robo
import db
from api_shopee import link_para_converter, tipo_de_link
from fuso import fuso_horario

PACOTE = av.PACOTE_SHOPEE
PACOTE_SISTEMA = "com.android.systemui"
GALERIA = "/sdcard/DCIM/Camera"
CHAVE_PAINEL = "shopee_video"  # a mesma chave do painel_shopee_video
CHAVE_TESTE = "celular_robo_teste"
# Horas de Brasília (início, fim) em que uma rodada no celular pode começar.
# Decisão do Rafael: DECISOES.md, Shopee Vídeo.
HORARIO_DAS_RODADAS = (8, 22)
LEGENDA_PRINT = "🤖 Robô da Shopee Vídeo (teste): a tela antes de salvar o rascunho."
AVISO_SEM_PRODUTO = "🤖 Robô da Shopee Vídeo (teste): nenhum produto foi adicionado ao vídeo."
AVISO_IA = "🤖 Robô da Shopee Vídeo (teste): a IA viu que o produto do link não é o produto do vídeo. Parei aqui."
AVISO_TELA_FINAL = ("🤖 Robô da Shopee Vídeo (teste): na tela final, o produto anexado não é o do vídeo "
                    "(ou há produto a mais ou a menos). Não salvei nem postei; confira o celular.")
PROMPT_PRODUTO_DO_VIDEO = """Você confere um vídeo de afiliado da Shopee antes de ele ir para a Shopee Vídeo.
O link que vai junto com o vídeo leva a este produto: "{nome}".
Assista ao vídeo inteiro e diga se o produto mostrado no vídeo é esse produto (o mesmo produto, \
ou pelo menos o mesmo tipo de produto: vídeo de vestido infantil com link de vestido infantil confere; \
vídeo de vestido com link de fibra de cabelo não confere).
Responda só com um JSON: {{"confere": true ou false, "motivo": "uma frase curta"}}"""
AVISO_JANELA_ERRADA = ("🤖 Robô da Shopee Vídeo (teste): a janela de editar o nome aberta no celular é de outro "
                       "produto, não do produto do vídeo. Parei sem tocar em Feito; confira o celular.")
# Quantas vezes o passo produto rola a lista de Minhas Curtidas atrás do produto do vídeo.
ROLAGENS_DO_PRODUTO = 3
# Nome cortado na lista só vale como o mesmo produto a partir deste tamanho.
TAMANHO_MINIMO_DO_NOME = 15
# Elemento de outro app até este tamanho (px) é coisa flutuante, como a bolinha da Motorola.
LADO_MAXIMO_FLUTUANTE = 400
NOME_NA_GALERIA = "autoral_shopee_video.mp4"
SEGUNDOS_DEPOIS_DO_PASSO = 3
MAXIMO_ESPERA = 60
MAXIMO_LINHAS = 150

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
    verificação verificar segurança arraste arrastar deslize deslizar controle deslizante
    quebra-cabeça peça complete completar tente atualizar erro carregando aguarde rede
    conexão internet ops algo deu errado página encontrada negado bloqueado suspeita
    atividade incomum robô humano captcha verify slide puzzle
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


# Botões que a exploração nunca toca: o que publica o vídeo e os de comprar da página do
# produto (Compre agora, carrinho e chat, embaixo). "Postar vídeo" não entra: só abre a câmera.
# Postar: DECISOES.md, Shopee Vídeo.
TEXTOS_PROIBIDOS = frozenset({"postar", "compre agora", "comprar agora", "adicionar ao carrinho"})
IDS_PROIBIDOS = frozenset({"btn_post", "buttonProductBuyNow", "buttonProductAddCart", "buttonProductChatNow"})
RECUSA = "recusado: a exploração nunca toca em Postar nem nos botões de comprar"


def eh_alvo_proibido(alvo):
    """O alvo de um tocar (texto ou @id) é um dos botões proibidos?"""
    if alvo.startswith("@"):
        return alvo[1:] in IDS_PROIBIDOS
    return _normal(alvo) in TEXTOS_PROIBIDOS


def proibido_no_ponto(xml, x, y):
    """Algum botão proibido cobre esse ponto da tela? Vale para o toque por texto e por xy."""
    for el in elementos(xml):
        x1, y1, x2, y2 = el["caixa"]
        if x1 <= x <= x2 and y1 <= y <= y2 and (
                el["id"] in IDS_PROIBIDOS
                or any(_normal(el[campo]) in TEXTOS_PROIBIDOS for campo in ("texto", "descricao"))):
            return True
    return False


def video_da_fonte():
    """
    {"id", "arquivo", "link", "nome"} do vídeo que o modo assistente mandaria agora,
    da fonte escolhida no painel; None sem nenhum.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    fonte = (db.ler_config(CHAVE_PAINEL, {}) or {}).get("fonte", assistente.FONTE_PADRAO)
    video = assistente.proximo_video(fonte)
    return dict(video, arquivo=os.path.abspath(video["arquivo"])) if video else None


def video_do_teste(novo=False):
    """
    O vídeo do teste no celular: com novo=True (passo video:novo), escolhe na fonte e
    guarda; sem, devolve o guardado, enquanto o arquivo existir. None sem nenhum.
    """
    guardado = db.ler_config(CHAVE_TESTE, {}) or {}
    if not novo and guardado.get("arquivo") and os.path.exists(guardado["arquivo"]):
        return guardado
    video = video_da_fonte()
    if video:
        db.salvar_config(CHAVE_TESTE, video)
    return video


def escrever_titulo(d, video):
    """Escreve o título da IA (prompt do Gem e diretrizes) no campo com o cursor. (ok, o que dizer no log)."""
    textos = asyncio.run(assistente.textos_do_video(video["arquivo"], video.get("nome") or ""))
    if textos and textos["violacao"]:
        return False, "a IA viu violação das diretrizes: título não escrito"
    if not textos or not textos["titulo"]:
        return False, "a IA não devolveu título"
    d.send_keys(textos["titulo"])
    return True, f"título com {len(textos['titulo'])} caracteres"


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


def adicionar_do_produto(xml, nome):
    """
    O botão Adicionar do produto com esse nome na lista de Adicionar Produto; None se
    ele não está na tela. O botão certo é o único Adicionar dentro do menor bloco de
    toque que contém o nome: com mais de um, o bloco é a lista e o robô não adivinha.
    """
    lista = elementos(xml)
    botoes = [el for el in lista if _normal(el["texto"]) == "adicionar"]
    for el in lista:
        if not mesmo_produto(el["texto"], nome):
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
    """Nome do produto do vídeo pela API de afiliado, a partir do link; "" quando o link não diz."""
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
    if not any(mesmo_produto(el["texto"], nome) for el in lista):
        avisar_rafael.mandar_texto(f"{AVISO_JANELA_ERRADA}\n\nO produto do vídeo é: {nome}")
        return False, "a janela de editar o nome é de outro produto: Feito não tocado (aviso no privado)"
    if not ponto:
        return True, "a janela do produto do vídeo já estava aberta; nada tocado"
    return True, f"produto do vídeo achado pelo nome; Adicionar tocado em {ponto}; a janela confere"


def ia_confere_produto(video):
    """
    A IA assiste ao vídeo com o nome do produto do link e diz se é o mesmo produto:
    pega o link errado que vem da fonte antes de qualquer toque. Sem confirmação da IA
    (não confere, não respondeu ou o link não diz o produto), a exploração para.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    nome = nome_do_produto(video)
    if not nome:
        avisar_rafael.mandar_texto(f"{AVISO_IA}\n\nO link do vídeo não diz qual é o produto.")
        return False, "o link não diz o produto do vídeo: a IA não tem o que conferir (aviso no privado)"
    resposta = asyncio.run(api_gemini.analisar_video_gemini(video["arquivo"],
                                                            PROMPT_PRODUTO_DO_VIDEO.format(nome=nome)))
    achado = re.search(r"\{.*\}", resposta or "", re.S)
    try:
        dados = json.loads(achado.group(0)) if achado else None
    except ValueError:
        dados = None
    if not isinstance(dados, dict):
        return False, "a IA não respondeu à conferência: parado"
    if dados.get("confere") is not True:
        avisar_rafael.mandar_texto(f"{AVISO_IA}\n\nProduto do link: {nome}\nO que a IA viu: "
                                   f"{str(dados.get('motivo') or '').strip()}")
        return False, "a IA viu outro produto no vídeo: parado (aviso no privado)"
    return True, "a IA confere: o produto do link é o do vídeo"


def conferir_tela_final(d, video):
    """
    Na tela final, antes de Rascunhos (e, no robô pronto, de Postar): o único produto
    anexado tem de ser o do vídeo. Diferente, a mais ou nenhum: não segue e avisa.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    nome = nome_do_produto(video)
    anexados = [el["texto"] for el in elementos(d.dump_hierarchy()) if el["id"] == "tv_product_title"]
    if nome and len(anexados) == 1 and mesmo_produto(anexados[0], nome):
        return True, "tela final confere: o produto anexado é o do vídeo"
    avisar_rafael.mandar_texto(f"{AVISO_TELA_FINAL}\n\nProduto do vídeo: {nome or 'o link não diz'}")
    return False, (f"tela final com {len(anexados)} produto(s) anexado(s) que não confere(m) com o do vídeo: "
                   "nada salvo (aviso no privado)")


def toca_em_rascunhos(xml, x, y):
    """O ponto cai no botão Rascunhos da tela final (tv_drafts_box)?"""
    return any(el["id"] == "tv_drafts_box" and _dentro((x, y), el["caixa"]) for el in elementos(xml))


def rolar(d, para_cima=False):
    """Arrasta a tela no meio, de baixo para cima (o conteúdo desce) ou o contrário."""
    largura, altura = d.window_size()
    de, ate = (0.3, 0.75) if para_cima else (0.75, 0.3)
    d.swipe(largura // 2, int(altura * de), largura // 2, int(altura * ate), 0.4)


def mandar_print(d):
    """Print da tela no privado do Rafael. O arquivo sai do servidor logo depois."""
    descritor, caminho = tempfile.mkstemp(suffix=".png")
    os.close(descritor)
    try:
        d.screenshot(caminho)
        return avisar_rafael.mandar_foto(caminho, LEGENDA_PRINT)
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


def por_na_galeria(d, arquivo):
    """Copia o vídeo para a câmera do Android e avisa a galeria. True se ele apareceu nela."""
    destino = f"{GALERIA}/{NOME_NA_GALERIA}"
    d.shell(["mkdir", "-p", GALERIA])
    d.push(arquivo, destino)
    d.shell(["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", "file://" + destino])
    time.sleep(3)
    lista = d.shell(["content", "query", "--uri", "content://media/external/video/media",
                     "--projection", "_display_name"])
    return NOME_NA_GALERIA in getattr(lista, "output", "")


def separar_passos(texto):
    """Lista de (nome, argumento). Passo desconhecido vira ValueError antes de tocar em qualquer coisa."""
    conhecidos = {"abrir", "fechar", "tocar", "xy", "voltar", "inicio", "rolar", "esperar", "escrever",
                  "link", "video", "titulo", "ia", "produto", "conferir", "print", "tela"}
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
        d.send_keys(argumento)
        return True, "escrito"
    if nome in ("link", "video", "titulo", "ia", "produto", "conferir"):
        video = video_do_teste(novo=nome == "video" and argumento == "novo")
        if not video:
            return False, "nenhum vídeo da fonte do painel com arquivo e link"
        if nome == "link":
            return True, f"aberto: {abrir_link(d, video['link'])}"
        if nome == "titulo":
            return escrever_titulo(d, video)
        if nome == "ia":
            return ia_confere_produto(video)
        if nome == "produto":
            return adicionar_produto(d, video)
        if nome == "conferir":
            return conferir_tela_final(d, video)
        return ((True, "vídeo na galeria") if por_na_galeria(d, video["arquivo"])
                else (False, "o vídeo não apareceu na galeria"))
    if nome == "print":
        return (True, "print mandado no privado") if mandar_print(d) else (False, "o Telegram recusou o print")
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


def no_horario_das_rodadas():
    inicio, fim = HORARIO_DAS_RODADAS
    return inicio <= datetime.now(fuso_horario).hour < fim


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
            inicio, fim = HORARIO_DAS_RODADAS
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
