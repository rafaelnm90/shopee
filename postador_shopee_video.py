#!/usr/bin/env python3
"""
Robô da Shopee Vídeo: opera o app da Shopee no Android virtual (android_virtual.py)
como uma pessoa, tocando na tela, para postar os vídeos dos Autorais com os
produtos vinculados. A Shopee Vídeo só aceita postagem pelo app.

Por enquanto ele só explora: faz os passos pedidos e descreve cada tela (botões,
campos e onde ficam), para ensinar o caminho da postagem que o Rafael mostrou
no tutorial. Roda à mão pelo workflow android.yml (ação explorar) ou no servidor:

    python3 postador_shopee_video.py --explorar "abrir; tocar:Eu; tocar:Criadores"

Passos, separados por ponto e vírgula:
    abrir            abre o app da Shopee (fechar: fecha)
    tocar:TEXTO      toca no botão com esse texto ou descrição (tocar:@id pelo id)
    xy:X,Y           toca nesse ponto da tela
    voltar, inicio   as teclas do Android
    rolar:baixo      arrasta a tela (rolar:cima)
    esperar:N        espera N segundos
    escrever:TEXTO   escreve no campo que está com o cursor
    link             abre no app o produto (ou o vídeo) do Autoral mais novo
    video            põe na galeria o vídeo do Autoral mais novo
    tela             só descreve a tela

Nunca toca em "Postar": a exploração termina, no máximo, em Rascunhos.

Imprime a forma da tela, não o conteúdo, porque o log do Actions é público e a
tela mostra a conta do Rafael: palavra que não é de botão vira "…" e número
vira "#". Também nunca imprime os links.
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import asyncio
import os
import re
import sys
import time
import xml.etree.ElementTree as ET

import android_virtual as av
import db
from api_shopee import link_para_converter, tipo_de_link

PACOTE = av.PACOTE_SHOPEE
GALERIA = "/sdcard/DCIM/Camera"
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
    ganhos comissões relatório upload duet costurar adesivos clipes
""".split())
NUMERO = re.compile(r"[\d.,%R$()+x×/:#-]*\d[\d.,%R$()+x×/:#-]*")
PONTUACAO = ".,:;!?()[]{}\"'«»“”‘’-–—/|+*·•"


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
    """Elementos visíveis da tela que interessam: com texto, descrição, id ou que aceitam toque."""
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError:
        return []
    achados = []
    for no in raiz.iter("node"):
        caixa = _limites(no)
        if not caixa or no.get("visible-to-user", "true") != "true":
            continue
        texto, descricao = no.get("text", ""), no.get("content-desc", "")
        ident = no.get("resource-id", "").split(":id/")[-1]
        clicavel = no.get("clickable") == "true"
        if texto or descricao or ident or clicavel:
            achados.append({"texto": texto, "descricao": descricao, "id": ident, "clicavel": clicavel,
                            "classe": no.get("class", "").rsplit(".", 1)[-1], "caixa": caixa,
                            "marcado": no.get("checked") == "true"})
    return achados


def descrever(xml):
    """Linhas da tela para o log: centro, tipo, id, texto e descrição mascarados."""
    linhas = []
    for el in elementos(xml)[:MAXIMO_LINHAS]:
        x1, y1, x2, y2 = el["caixa"]
        partes = [f"({(x1 + x2) // 2},{(y1 + y2) // 2})", el["classe"] or "?"]
        if el["id"]:
            partes.append(f"id={el['id']}")
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


def eh_botao_de_postar(alvo):
    return _normal(alvo) == "postar"


def ultimo_autoral():
    """(arquivo do vídeo, link da Shopee) do Autoral mais novo que ainda tem o vídeo; (None, None) sem nenhum."""
    try:
        with db.conexao() as con:
            linhas = con.execute("SELECT caminho_arquivo, legenda FROM fila_autorais "
                                 "ORDER BY data_captura DESC").fetchall()
    except Exception:
        return None, None
    for caminho, legenda in linhas:
        if not caminho:
            continue
        # Caminho relativo à pasta do projeto, de onde os robôs rodam (archive/...).
        arquivo = os.path.abspath(caminho)
        link = re.search(r"https?://[^\s<>\"]*shopee[^\s<>\"]*", legenda or "")
        if os.path.exists(arquivo) and link:
            return arquivo, link.group(0)
    return None, None


def abrir_link(d, link):
    """Abre no app da Shopee o produto (ou o vídeo) do link. Devolve o tipo de página, para o log."""
    destino = asyncio.run(link_para_converter(link))
    d.shell(["am", "start", "-a", "android.intent.action.VIEW", "-d", destino, "-p", PACOTE])
    return tipo_de_link(destino)


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
                  "link", "video", "tela"}
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
        if eh_botao_de_postar(argumento):
            return False, "recusado: a exploração nunca toca em Postar"
        ponto = achar(d.dump_hierarchy(), argumento)
        if not ponto:
            return False, "não achei na tela"
        d.click(*ponto)
        return True, f"tocado em {ponto}"
    if nome == "xy":
        x, y = (int(n) for n in argumento.split(","))
        d.click(x, y)
        return True, f"tocado em ({x},{y})"
    if nome in ("voltar", "inicio"):
        d.press("back" if nome == "voltar" else "home")
        return True, "tecla apertada"
    if nome == "rolar":
        largura, altura = d.window_size()
        de, ate = (0.75, 0.3) if argumento != "cima" else (0.3, 0.75)
        d.swipe(largura // 2, int(altura * de), largura // 2, int(altura * ate), 0.4)
        return True, "rolado"
    if nome == "esperar":
        time.sleep(min(float(argumento or 1), MAXIMO_ESPERA))
        return True, "esperado"
    if nome == "escrever":
        d.send_keys(argumento)
        return True, "escrito"
    if nome in ("link", "video"):
        arquivo, link = ultimo_autoral()
        if not arquivo:
            return False, "nenhum vídeo dos Autorais com arquivo e link"
        if nome == "link":
            return True, f"aberto: {abrir_link(d, link)}"
        return (True, "vídeo na galeria") if por_na_galeria(d, arquivo) else (False, "o vídeo não apareceu na galeria")
    return True, "só a tela"


def conectar():
    """O Android pelo uiautomator2, que lê a tela mesmo com vídeo tocando (o uiautomator do adb trava)."""
    import uiautomator2
    av.android_ligado()
    return uiautomator2.connect(av.ENDERECO_ADB)


def explorar(texto, d=None):
    """Faz os passos e descreve a tela depois de cada um. Para no primeiro que falhar."""
    print("== Explorando o app da Shopee")
    try:
        passos = separar_passos(texto)
    except ValueError as e:
        print(f"passos: {e}")
        return False
    if not passos:
        passos = [("tela", "")]
    if d is None:
        if not av.android_ligado():
            print("android: desligado; rode o preparar antes")
            return False
        d = conectar()
    for numero, (nome, argumento) in enumerate(passos, 1):
        try:
            ok, resultado = fazer_passo(d, nome, argumento)
        except Exception as e:
            ok, resultado = False, f"erro: {type(e).__name__}"
        print(f"\n== passo {numero}: {nome}{':' + argumento if argumento else ''} → {resultado}")
        if nome != "esperar":
            time.sleep(SEGUNDOS_DEPOIS_DO_PASSO)
        try:
            atual = d.app_current()
            print(f"app: {atual.get('package', '?')} | tela: {atual.get('activity', '?').rsplit('.', 1)[-1]}")
            print("\n".join(descrever(d.dump_hierarchy())) or "  (tela sem elementos)")
        except Exception as e:
            print(f"tela: não deu para ler ({type(e).__name__})")
        if not ok:
            return False
    return True


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--explorar":
        sys.exit(0 if explorar(" ".join(sys.argv[2:])) else 1)
    print(__doc__)
