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
    print            manda um print da tela no privado do Rafael (nunca no log)
    tela             só descreve a tela

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
import logging
import os
import re
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import android_virtual as av
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
                            "marcado": no.get("checked") == "true"})
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
                  "link", "video", "titulo", "print", "tela"}
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
        d.click(x, y)
        return True, f"tocado em {ponto}"
    if nome == "xy":
        x, y = (int(n) for n in argumento.split(","))
        if proibido_no_ponto(d.dump_hierarchy(), x, y):
            return False, RECUSA
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
    if nome in ("link", "video", "titulo"):
        video = video_do_teste(novo=nome == "video" and argumento == "novo")
        if not video:
            return False, "nenhum vídeo da fonte do painel com arquivo e link"
        if nome == "link":
            return True, f"aberto: {abrir_link(d, video['link'])}"
        if nome == "titulo":
            return escrever_titulo(d, video)
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
