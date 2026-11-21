"""
As interações do robô da Shopee Vídeo além de postar: responder os comentários dos
vídeos do Rafael (e curtir o comentário respondido), curtir e comentar vídeos de outros
criadores no feed Live e Vídeo → Para você e comentar no próprio vídeo (depois de cada post
e, 1 vez por dia, num post antigo), curtindo o vídeo e o comentário. Pedidos do Rafael de
24/10/2026 (P9, P10 e P11), de 30/10/2026 (a curtida) e de 04/11/2026 (P148 2):
DECISOES.md, Shopee Vídeo.

Aqui fica o que não toca no celular: a leitura das telas (a lista das Notificações, o
painel de comentários e o player do feed), o texto da IA e as marcas do que já foi
feito. Também as curtidas de cada vídeo do Rafael, contadas nas linhas "curtiu seu vídeo."
das Notificações, e a leitura da folha do compartilhar (Fixar ou Desfixar): o vídeo com 10
curtidas ou mais em 24 h vai para os fixados do Perfil (escolha do Rafael de 20/11/2026, P263 1).
Os toques ficam no robo_shopee_video, que chama estas funções; o checkup conta o
que o robô anotou no registro de processos.

As marcas (tabela shopee_video_interacoes) guardam só um resumo (SHA-1) do comentário
ou do vídeo, nunca o nome nem o texto, por DIAS_DAS_MARCAS dias: com elas o robô nunca
responde o mesmo comentário duas vezes nem comenta o mesmo vídeo de novo.
"""
import hashlib
import logging
import re
from datetime import datetime, timedelta

import db
import postador_shopee_video as ps
from fuso import fuso_horario

logger = logging.getLogger(__name__)

DIAS_DAS_MARCAS = 90
# Um comentário que não deu para responder volta nas rodadas seguintes; na 3ª vez o robô
# desiste, avisa o Rafael (ele responde à mão) e o checkup aponta.
TENTATIVAS_DO_COMENTARIO = 3
# Os vídeos do feed por dia: um limite, não uma meta (o dia com menos é normal), espalhados
# pelo dia, com cada comentário diferente. Escolhas do Rafael (P10, P151 1 e P152): DECISOES.md,
# Shopee Vídeo.
VIDEOS_NO_FEED_POR_DIA = 5
# No feed, o robô prefere os vídeos com até tantos comentários: o dele fica no alto e é
# visto. Escolha do Rafael (P70): DECISOES.md, Shopee Vídeo.
POUCOS_COMENTARIOS = 20
TAMANHO_DA_RESPOSTA = 150
# A resposta do robô lida no painel tem pelo menos tantas letras e números (ou todos, na
# resposta mais curta): o painel corta a longa no fim, mas não a ponto de virar uma palavra.
MINIMO_DA_RESPOSTA = 20
TAMANHO_DO_COMENTARIO = 80
# O comentário do Rafael no próprio vídeo (P148 2): depois de cada post e, POSTS_ANTIGOS_POR_DIA
# vez por dia, num post do robô dos últimos DIAS_DOS_POSTS_ANTIGOS dias que ele não comentou há
# DIAS_ENTRE_COMENTARIOS dias. O de depois do post que não sai na hora (o vídeo ainda em análise)
# volta a cada INTERVALO_DO_PROPRIO, até TENTATIVAS_DO_PROPRIO vezes; depois, o texto vai ao Rafael,
# que comenta à mão. Escolha do Rafael: DECISOES.md, Shopee Vídeo.
TAMANHO_DO_PROPRIO = 100
POSTS_ANTIGOS_POR_DIA = 1
DIAS_DOS_POSTS_ANTIGOS = 30
DIAS_ENTRE_COMENTARIOS = 7
TENTATIVAS_DO_PROPRIO = 3
INTERVALO_DO_PROPRIO = timedelta(minutes=30)
# As marcas do comentário no próprio vídeo, pelo link do post: o de depois do post e o de post antigo.
TIPO_DO_POST, TIPO_DO_ANTIGO = "proprio_post", "post_antigo"
# O post que o link abriu como removido ("Este vídeo foi removido"): não há onde comentar, e a
# escolha do post antigo o deixa de fora. Sem a marca, às 08:22 de 09/11, ele voltaria em toda
# tentativa, todo dia, e o comentário do dia nunca sairia.
TIPO_DO_REMOVIDO = "post_removido"
# O comentário do próprio vídeo que conta como feito: o que apareceu e o enviado sem aparecer
# (pode ter saído; não é repetido).
COMENTADOS_NO_PROPRIO = ("comentado", "não confirmado")
# Os estados de um comentário em que ele não volta mais.
FINAIS = frozenset({"respondido", "já respondido", "pulado", "desistiu", "anterior", "lugar errado"})
# Nem todo vídeo curtido no feed ganha comentário: sem nada específico para dizer sobre ele,
# a IA responde CURTIR, e o robô só curte. Escolha do Rafael (P151 1): DECISOES.md, Shopee Vídeo.
CURTIR = "CURTIR"
SO_CURTIDO = "só curtido"
# Os vídeos do feed que contam nos do dia: o comentado, o enviado sem aparecer na tela (pode
# ter saído; não é comentado de novo) e o só curtido.
FEITOS_NO_FEED = ("comentado", "não confirmado", SO_CURTIDO)

# O aviso de comentário nas Notificações: "Fulana comentou no seu vídeo: "Amei!"".
COMENTOU = re.compile(r"^(?P<nome>.+?)\s+comentou no seu v[ií]deo\s*:?\s*(?P<texto>.*)$", re.S | re.I)
# As curtidas dos vídeos nas Notificações (P263 1): a linha da curtida no vídeo (a no comentário é "Your
# comment gets a like."), a largura mínima do bloco de toque da linha (de lado a lado da tela), o tamanho
# mínimo da capa pequena (no Motorola, 105 px) e as horas escritas embaixo do aviso.
CURTIU = re.compile(r"\bcurtiu seu v[ií]deo\b", re.I)
LARGURA_DA_LINHA = 900
TAMANHO_MINIMO_DA_CAPA = 60
HORA_DE_HOJE = re.compile(r"^(?:hoje\s+)?(\d{1,2}):(\d{2})$")
HORA_DE_ONTEM = re.compile(r"^ontem\s+(\d{1,2}):(\d{2})$")
DIA_E_HORA = re.compile(r"^(\d{1,2})[-/](\d{1,2})(?:[-/](\d{4}))?\s+(\d{1,2}):(\d{2})$")
HA_POUCO = re.compile(r"^h[aá]\s+(\d+)\s*(min|minutos?|h|horas?)$")
# As curtidas contam nas últimas HORAS_DAS_CURTIDAS horas e ficam guardadas DIAS_DAS_CURTIDAS dias.
HORAS_DAS_CURTIDAS = 24
DIAS_DAS_CURTIDAS = 3
# Os botões da folha do compartilhar do próprio vídeo, ao lado do Copiar link (Motorola, 20/11/2026).
FIXAR, DESFIXAR = "Fixar", "Desfixar"
ASPAS = "\"“”'‘’"
# A hora de cada linha das Notificações ("Hoje 10:15", "24-10 14:32").
HORA_DA_LINHA = re.compile(r"^(?:\S+\s+)?\d{1,2}:\d{2}$")
# A hora fica logo embaixo do aviso, alinhada com ele (no Motorola, uns 15 px abaixo).
ESPACO_DA_HORA = 90
# O coração de cada comentário do painel (desc "button comment like", na ponta direita da
# linha) e o "Curtido pelo criador" que aparece embaixo do comentário curtido pelo Rafael.
CORACAO_DO_COMENTARIO = "comment like"
# O número de curtidas escrito dentro do coração do comentário ("1", "12", "1,2 mil"). No
# comentário do próprio Rafael, a curtida não muda a descrição do coração nem traz o "Curtido pelo
# criador": só esse número aparece (casos do comentário no próprio post, 06/11).
NUMERO_DE_CURTIDAS = re.compile(r"^([\d.,]+)( ?mil)?$")
CURTIDO_PELO_CRIADOR = re.compile(r"^curtido pel[oa] criador")
# O que acompanha cada comentário no painel e não é o nome nem o texto.
EM_VOLTA_DO_COMENTARIO = (
    re.compile(r"^criador$"), re.compile(r"^responder$"), CURTIDO_PELO_CRIADOR,
    re.compile(r"^há \d+"), re.compile(r"^\d{1,2} de \w+"), re.compile(r"^\d{1,2}[-/]\d{1,2}([-/]\d{2,4})?$"),
    re.compile(r"^[\d.,]+( ?mil)?$"), re.compile(r"^(ver|ocultar) (\d+ )?respostas?"), re.compile(r"^ver tradução"),
)
VER_RESPOSTAS = re.compile(r"^ver (\d+ )?(mais )?respostas?", re.I)
# O título do painel: "3 Comentários" (sem número quando o vídeo ainda não tem nenhum).
CABECALHO = re.compile(r"^([\d.,]+( mil)?\s+)?coment[aá]rios?$")


def _agora(agora=None):
    return agora or datetime.now(fuso_horario)


def _momento(agora=None):
    return _agora(agora).strftime("%Y-%m-%d %H:%M:%S")


def marca(*partes):
    """O resumo que identifica um comentário ou vídeo sem guardar o texto."""
    texto = " | ".join(ps._normal(p) for p in partes)
    return hashlib.sha1(texto.encode()).hexdigest()[:16]


# --- As marcas do que já foi feito ---

def _criar_tabela(con):
    con.execute("CREATE TABLE IF NOT EXISTS shopee_video_interacoes ("
                "marca TEXT, tipo TEXT, resultado TEXT, tentativas INTEGER DEFAULT 0, momento TEXT, "
                "PRIMARY KEY (marca, tipo))")


def guardar(marca_, tipo, resultado, agora=None):
    """Guarda o resultado de um comentário (tipo "comentario") ou vídeo do feed ("video_feed")."""
    with db.conexao() as con:
        _criar_tabela(con)
        con.execute("INSERT INTO shopee_video_interacoes (marca, tipo, resultado, tentativas, momento) "
                    "VALUES (?, ?, ?, 0, ?) ON CONFLICT (marca, tipo) DO UPDATE SET resultado = excluded.resultado, "
                    "momento = excluded.momento", (marca_, tipo, resultado, _momento(agora)))
        corte = (_agora(agora) - timedelta(days=DIAS_DAS_MARCAS)).strftime("%Y-%m-%d %H:%M:%S")
        con.execute("DELETE FROM shopee_video_interacoes WHERE momento < ?", (corte,))


def guardar_falha(marca_, tipo, agora=None):
    """Conta mais uma tentativa que não deu certo e devolve quantas já foram."""
    with db.conexao() as con:
        _criar_tabela(con)
        con.execute("INSERT INTO shopee_video_interacoes (marca, tipo, resultado, tentativas, momento) "
                    "VALUES (?, ?, 'falhou', 1, ?) ON CONFLICT (marca, tipo) DO UPDATE SET "
                    "tentativas = tentativas + 1, momento = excluded.momento", (marca_, tipo, _momento(agora)))
        return con.execute("SELECT tentativas FROM shopee_video_interacoes WHERE marca = ? AND tipo = ?",
                           (marca_, tipo)).fetchone()[0]


def resultado_de(marca_, tipo):
    """O último resultado guardado para a marca, ou None."""
    with db.conexao() as con:
        _criar_tabela(con)
        linha = con.execute("SELECT resultado FROM shopee_video_interacoes WHERE marca = ? AND tipo = ?",
                            (marca_, tipo)).fetchone()
    return linha[0] if linha else None


def situacao(marca_, tipo):
    """{"resultado", "tentativas", "momento"} da marca, ou None se ela não foi guardada."""
    with db.conexao() as con:
        _criar_tabela(con)
        linha = con.execute("SELECT resultado, tentativas, momento FROM shopee_video_interacoes "
                            "WHERE marca = ? AND tipo = ?", (marca_, tipo)).fetchone()
    return dict(zip(("resultado", "tentativas", "momento"), linha)) if linha else None


def terminado(marca_):
    """O comentário já teve um fim (respondido, pulado, desistido...)? Esses não voltam."""
    return resultado_de(marca_, "comentario") in FINAIS


def quantos_desde(tipo, resultados, desde):
    """Quantas marcas do tipo ficaram com um dos resultados desde o momento ("AAAA-MM-DD HH:MM:SS")."""
    resultados = (resultados,) if isinstance(resultados, str) else tuple(resultados)
    with db.conexao() as con:
        _criar_tabela(con)
        return con.execute(f"SELECT COUNT(*) FROM shopee_video_interacoes WHERE tipo = ? AND resultado IN "
                           f"({','.join('?' * len(resultados))}) AND momento >= ?",
                           (tipo, *resultados, desde)).fetchone()[0]


# --- O comentário no próprio vídeo (P148 2) ---

def marca_do_post(link):
    """A marca do post do robô, pelo link dele."""
    return marca(link or "")


def ultimo_comentario(link):
    """Quando o robô comentou no post por último (o de depois do post ou o de post antigo), ou ""."""
    momentos = [s["momento"] for s in (situacao(marca_do_post(link), tipo) for tipo in (TIPO_DO_POST, TIPO_DO_ANTIGO))
                if s and s["resultado"] in COMENTADOS_NO_PROPRIO]
    return max(momentos, default="")


def antigos_hoje(agora=None):
    """Quantos posts antigos o robô já comentou hoje (a meta é POSTS_ANTIGOS_POR_DIA)."""
    return quantos_desde(TIPO_DO_ANTIGO, COMENTADOS_NO_PROPRIO, _agora(agora).strftime("%Y-%m-%d 00:00:00"))


def escolher_post_antigo(postados, agora=None):
    """
    O post do robô que ganha o comentário do dia, entre os postados nos últimos
    DIAS_DOS_POSTS_ANTIGOS dias, com o link e não removido (TIPO_DO_REMOVIDO), que o robô não
    comenta há DIAS_ENTRE_COMENTARIOS dias (contando o de depois do post): primeiro o que nunca
    ganhou comentário do robô, depois o comentado há mais tempo; no empate, o mais novo. None
    sem nenhum.
    """
    agora = _agora(agora)
    desde = (agora - timedelta(days=DIAS_DOS_POSTS_ANTIGOS)).strftime("%Y-%m-%d %H:%M:%S")
    corte = (agora - timedelta(days=DIAS_ENTRE_COMENTARIOS)).strftime("%Y-%m-%d %H:%M:%S")
    candidatos = []
    for post in postados:
        if not post.get("link_post") or (post.get("postado_em") or "") < desde:
            continue
        if resultado_de(marca_do_post(post["link_post"]), TIPO_DO_REMOVIDO):
            continue
        ultimo = ultimo_comentario(post["link_post"])
        if ultimo and ultimo > corte:
            continue
        candidatos.append((ultimo, post))
    if not candidatos:
        return None
    nunca = [post for ultimo, post in candidatos if not ultimo]
    if nunca:
        return max(nunca, key=lambda post: post.get("postado_em") or "")
    return min(candidatos, key=lambda par: par[0])[1]


# --- As Notificações ---

def linhas_das_notificacoes(xml, filtro):
    """
    As linhas da lista (filtro Lives, Vídeos e ...), de cima para baixo: o aviso de cada linha, com
    a hora escrita embaixo dele ("hora"). O que fica atrás da fileira de filtros (a lista rolada por
    baixo dela) e a linha cortada pela barra de baixo (o aviso, ou a hora dele) ficam de fora.
    """
    elementos = ps.elementos(xml)
    faixa = _faixa_da_lista(elementos, filtro)
    if not faixa:
        return []
    topo, fundo = faixa
    na_lista = [el for el in elementos if el["texto"].strip() and el["caixa"][1] >= topo and el["caixa"][3] <= fundo]
    horas = [el for el in na_lista if HORA_DA_LINHA.match(el["texto"].strip())]
    linhas = []
    for el in sorted((el for el in na_lista if not HORA_DA_LINHA.match(el["texto"].strip())),
                     key=lambda el: (el["caixa"][1], el["caixa"][0])):
        x1, _y1, _x2, y2 = el["caixa"]
        hora = next((h["texto"].strip() for h in horas
                     if abs(h["caixa"][0] - x1) <= 40 and y2 - 5 <= h["caixa"][1] <= y2 + ESPACO_DA_HORA), "")
        if not hora and y2 > fundo - ESPACO_DA_HORA:
            # A hora ficou embaixo da barra: a linha vem inteira na próxima rolada.
            continue
        linhas.append({"texto": el["texto"], "hora": hora, "ponto": ps._centro(el)})
    return linhas


def chave_da_linha(texto, hora, agora=None):
    """
    A marca de uma linha das Notificações com a hora dela (o topo da leitura e cada curtida): o mesmo aviso
    em outra hora, como a mesma pessoa curtindo outro vídeo, é outra linha. Com a hora certa quando o app a
    escreve (momento_da_hora: o "18:38" de hoje e o "Ontem 18:38" de amanhã dão a mesma chave); a de "há 5
    min", que muda a cada leitura, e o que não diz a hora, como estão escritos.
    """
    escrita = " ".join((hora or "").split())
    quando = None if HA_POUCO.match(escrita.casefold()) else momento_da_hora(escrita, agora)
    return marca(texto, quando.strftime("%Y-%m-%d %H:%M") if quando else escrita)


def comentario_da_notificacao(texto):
    """(nome, comentário) de um aviso "Fulana comentou no seu vídeo: ..."; None nos outros avisos."""
    achado = COMENTOU.match(" ".join((texto or "").split()))
    if not achado:
        return None
    return achado["nome"].strip(), achado["texto"].strip().strip(ASPAS).strip()


# --- As curtidas dos vídeos nas Notificações (P263 1) ---
# Escolha do Rafael (20/11/2026, P263 1): o vídeo dele com 10 curtidas ou mais em 24 h vai para os
# fixados do Perfil. Cada curtida é uma linha "Fulana curtiu seu vídeo." com a hora embaixo e a capa
# pequena do vídeo à direita; quando quem curtiu não tem foto, a capa vai à esquerda e a direita fica
# vazia (Motorola, 20/11/2026). As linhas do mesmo vídeo se juntam pela marca dessa capa
# (visualizacoes_shopee_video.marca_da_miniatura). Aqui ficam só a marca da linha (SHA-1 do aviso e da
# hora), a marca da capa e a hora da curtida, por DIAS_DAS_CURTIDAS dias: nunca o nome nem a imagem.

def _nos_da_tela(xml):
    """
    Todos os nós da tela com caixa, até as imagens sem texto (que ps.elementos deixa de fora):
    {"texto", "classe", "caixa", "clicavel"}.
    """
    import xml.etree.ElementTree as ET
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError:
        return []
    nos = []
    for no in raiz.iter("node"):
        caixa = ps._limites(no)
        if caixa and no.get("visible-to-user", "true") == "true" and no.get("package") != ps.PACOTE_SISTEMA:
            nos.append({"texto": no.get("text", ""), "classe": no.get("class", "").rsplit(".", 1)[-1], "caixa": caixa,
                        "clicavel": no.get("clickable") == "true"})
    return nos


def _faixa_da_lista(elementos, filtro):
    """(topo, fundo) da lista das Notificações: abaixo dos filtros e acima da barra de baixo; None sem os filtros."""
    chips = [el for el in elementos if ps._normal(el["texto"]).startswith(ps._normal(filtro))]
    if not chips:
        return None
    topo = max(el["caixa"][3] for el in chips)
    barra = [el["caixa"][1] for el in elementos if el["id"] in ("sp_bottom_navigation_container", "shadow_view")]
    return topo, min(barra) if barra else 10 ** 6


def curtidas_das_notificacoes(xml, filtro):
    """
    As linhas de curtida de vídeo ("... curtiu seu vídeo.") inteiras na tela, de cima para baixo:
    [{"texto", "hora", "ponto", "miniatura"}]: o aviso, a hora como está escrita embaixo dele, o centro
    do aviso (o toque abre o vídeo) e a caixa da capa pequena do vídeo (a imagem da direita; sem ela, a da
    esquerda). A curtida no comentário ("Your comment gets a like.") e a linha cortada ficam de fora.
    """
    faixa = _faixa_da_lista(ps.elementos(xml), filtro)
    if not faixa:
        return []
    topo, fundo = faixa
    nos = _nos_da_tela(xml)
    linhas = []
    for aviso in nos:
        if not CURTIU.search(" ".join(aviso["texto"].split())):
            continue
        x, y = ps._centro(aviso)
        # A linha é o bloco de toque de lado a lado da tela em volta do aviso.
        blocos = [no for no in nos if no["clicavel"] and no["caixa"][2] - no["caixa"][0] >= LARGURA_DA_LINHA
                  and ps._dentro((x, y), no["caixa"])]
        if not blocos:
            continue
        linha = min(blocos, key=lambda no: (no["caixa"][3] - no["caixa"][1]))["caixa"]
        if linha[1] < topo or linha[3] > fundo:
            continue
        dentro = [no for no in nos if no is not aviso and ps._dentro(ps._centro(no), linha)]
        hora = next((no["texto"].strip() for no in dentro
                     if no["texto"].strip() and no["caixa"][1] >= aviso["caixa"][3] - 5), "")
        imagens = [no for no in dentro if no["classe"] == "ImageView" and _quadrada(no["caixa"])]
        largura = linha[2] - linha[0]
        direita = [no for no in imagens if ps._centro(no)[0] > linha[0] + largura * 3 // 4]
        esquerda = [no for no in imagens if ps._centro(no)[0] < linha[0] + largura // 4]
        lado = direita or esquerda
        if lado:
            capa = max(lado, key=lambda no: (no["caixa"][2] - no["caixa"][0]) * (no["caixa"][3] - no["caixa"][1]))
            linhas.append({"texto": aviso["texto"], "hora": hora, "ponto": (x, y), "miniatura": capa["caixa"]})
    linhas.sort(key=lambda linha: linha["ponto"][1])
    return linhas


def _quadrada(caixa):
    """A imagem tem o jeito da capa pequena da linha (quase quadrada e não minúscula), e não de um ícone?"""
    largura, altura = caixa[2] - caixa[0], caixa[3] - caixa[1]
    return min(largura, altura) >= TAMANHO_MINIMO_DA_CAPA and 0.6 <= largura / max(altura, 1) <= 1.6


def momento_da_hora(hora, agora=None):
    """
    Quando foi a curtida, pela hora da linha: "18:38" ou "Hoje 18:38" (hoje), "Ontem 18:38", "20-11 18:38"
    (dia-mês, como as datas do app) ou "há 5 min"/"há 2 h". None no que não diz a hora (só a data, outro jeito).
    """
    texto = " ".join((hora or "").split()).casefold()
    base = _agora(agora)
    achado = HORA_DE_HOJE.match(texto) or HORA_DE_ONTEM.match(texto)
    if achado:
        horas, minutos = int(achado[1]), int(achado[2])
        if horas > 23 or minutos > 59:
            return None
        quando = base.replace(hour=horas, minute=minutos, second=0, microsecond=0)
        if texto.startswith("ontem"):
            quando -= timedelta(days=1)
        return quando - timedelta(days=1) if quando > base + timedelta(minutes=5) else quando
    achado = DIA_E_HORA.match(texto)
    if achado:
        dia, mes, ano, horas, minutos = (int(achado[i]) if achado[i] else None for i in range(1, 6))
        try:
            quando = base.replace(year=ano or base.year, month=mes, day=dia, hour=horas, minute=minutos,
                                  second=0, microsecond=0)
        except ValueError:
            return None
        return quando.replace(year=quando.year - 1) if not ano and quando > base + timedelta(days=1) else quando
    achado = HA_POUCO.match(texto)
    if achado:
        unidade = timedelta(hours=1) if achado[2].startswith("h") else timedelta(minutes=1)
        return base - int(achado[1]) * unidade
    return None


def _criar_tabela_das_curtidas(con):
    con.execute("CREATE TABLE IF NOT EXISTS shopee_video_curtidas (marca TEXT PRIMARY KEY, video TEXT, momento TEXT, "
                "lida_em TEXT)")


def guardar_curtidas(curtidas, agora=None):
    """
    Guarda as curtidas lidas: [{"texto", "chave", "video", "momento"}], chave o que diz quando a curtida foi
    (a hora certa, ou o que estava escrito) e momento o datetime dela. A mesma linha lida de novo não conta
    duas vezes (a marca do aviso e da chave). As de mais de DIAS_DAS_CURTIDAS dias saem. Devolve quantas novas.
    """
    novas = 0
    with db.conexao() as con:
        _criar_tabela_das_curtidas(con)
        for curtida in curtidas:
            if not curtida.get("video") or not curtida.get("momento"):
                continue
            cursor = con.execute("INSERT OR IGNORE INTO shopee_video_curtidas (marca, video, momento, lida_em) "
                                 "VALUES (?, ?, ?, ?)",
                                 (marca("curtida", curtida["texto"], curtida["chave"]), curtida["video"],
                                  curtida["momento"].strftime("%Y-%m-%d %H:%M:%S"), _momento(agora)))
            novas += cursor.rowcount
        corte = (_agora(agora) - timedelta(days=DIAS_DAS_CURTIDAS)).strftime("%Y-%m-%d %H:%M:%S")
        con.execute("DELETE FROM shopee_video_curtidas WHERE momento < ?", (corte,))
    return novas


def videos_mais_curtidos(agora=None, horas=HORAS_DAS_CURTIDAS):
    """
    As curtidas das últimas `horas` horas juntadas por vídeo (marcas de capa parecidas, até
    visualizacoes.MARCA_PARECIDA): [{"video", "curtidas"}], o mais curtido primeiro (no empate, o da curtida
    mais nova); "video" é a marca da capa na curtida mais nova dele.
    """
    import visualizacoes_shopee_video as visualizacoes
    desde = (_agora(agora) - timedelta(hours=horas)).strftime("%Y-%m-%d %H:%M:%S")
    with db.conexao() as con:
        _criar_tabela_das_curtidas(con)
        linhas = con.execute("SELECT video, momento FROM shopee_video_curtidas WHERE momento >= ? "
                             "ORDER BY momento DESC", (desde,)).fetchall()
    grupos = []
    for video, momento in linhas:
        grupo = next((g for g in grupos if visualizacoes.diferenca(g["video"], video) <= visualizacoes.MARCA_PARECIDA),
                     None)
        if grupo:
            grupo["curtidas"] += 1
        else:
            grupos.append({"video": video, "curtidas": 1, "ultima": momento})
    grupos.sort(key=lambda g: (g["curtidas"], g["ultima"]), reverse=True)
    return [{"video": g["video"], "curtidas": g["curtidas"]} for g in grupos]


def curtidas_do_video(xml):
    """As curtidas do vídeo aberto no player: o número no coração da coluna da direita (ou logo embaixo), ou None."""
    elementos = ps.elementos(xml)
    coracao = next((el for el in elementos if el["clicavel"] and ps._centro(el)[0] > 900
                    and coracao_curtido(el["descricao"]) is not None), None)
    if not coracao:
        return None
    x1, y1, x2, y2 = coracao["caixa"]
    for el in elementos:
        x, y = ps._centro(el)
        if el["texto"].strip() and x1 - 30 <= x <= x2 + 30 and y1 <= y <= y2 + 60:
            numero = contagem(el["texto"])
            if numero is not None:
                return numero
    return None


def texto_exato(xml, texto):
    """
    O centro do elemento com exatamente esse texto, ou None. Sem o "começa com" e o "contém" do ps.achar:
    o toque no Fixar nunca cai no Desfixar.
    """
    alvo = ps._normal(texto)
    el = next((el for el in ps.elementos(xml) if ps._normal(el["texto"]) == alvo), None)
    return ps._centro(el) if el else None


def estado_do_fixar(xml):
    """Na folha do compartilhar do próprio vídeo: "desfixar" (está fixado), "fixar" (não está) ou None (sem os dois)."""
    if texto_exato(xml, DESFIXAR):
        return "desfixar"
    if texto_exato(xml, FIXAR):
        return "fixar"
    return None


def limite_de_fixados(xml):
    """O app disse que não dá para fixar mais ("Você só pode fixar até 3 vídeos")?"""
    return any("pode fixar" in ps._normal(el["texto"]) for el in ps.elementos(xml))


# --- O painel de comentários ---

def _chave(texto):
    """O texto só com letras e números, sem caixa: compara o mesmo comentário lido em telas diferentes."""
    return "".join(c for c in (texto or "").casefold() if c.isalnum())


def parecidos(a, b):
    """
    O mesmo texto, mesmo cortado no fim (a lista corta o comentário longo com "... mais")
    ou com os emojis lidos como "..": iguais, ou um começa o outro com pelo menos 4 letras.
    """
    a, b = _chave(a), _chave(b)
    if a.endswith("mais") and len(a) > 8:
        a = a[:-4]
    if b.endswith("mais") and len(b) > 8:
        b = b[:-4]
    if not a or not b:
        return a == b
    curto, longo = sorted((a, b), key=len)
    return curto == longo or (len(curto) >= 4 and longo.startswith(curto))


def _do_comentario(texto):
    """O texto é o nome ou o comentário (e não a data, o Responder, o selo Criador...)?"""
    normal = ps._normal(texto)
    return bool(normal) and not any(regra.match(normal) for regra in EM_VOLTA_DO_COMENTARIO)


def _cabecalho(elementos):
    """O "# Comentários" no alto do painel, ou None se o painel não está aberto."""
    return next((el for el in elementos if CABECALHO.match(ps._normal(el["texto"]))), None)


def _limite_de_baixo(elementos):
    """Onde a lista acaba: a fileira de emojis rápidos ou o campo de escrever, o que vier antes."""
    emojis = {}
    for el in elementos:
        if el["texto"].strip() == "..":
            emojis.setdefault(ps._centro(el)[1], []).append(el)
    fileiras = [min(el["caixa"][1] for el in grupo) for grupo in emojis.values() if len(grupo) >= 5]
    campos = [el["caixa"][1] for el in elementos
              if el["classe"] == "EditText" or "add a comment" in el["descricao"].casefold()]
    return min(fileiras + campos, default=10 ** 6)


def comentarios_do_painel(xml):
    """
    Os comentários do painel aberto, de cima para baixo: {"nome", "texto", "resposta" (a
    linha recuada, resposta a um comentário), "criador" (o selo Criador: é do dono do vídeo),
    "responder", "ver_respostas" e "curtir" (os pontos de tocar, ou None; "curtir" é o
    coração da linha), "curtido" (o "Curtido pelo criador" embaixo dele), "coracao_desc" (a
    descrição do coração, que muda quando ele é curtido), "curtidas" (o número escrito dentro do
    coração, 0 sem número), "y"}. Cada
    comentário começa na foto (x pequeno, com "comment" na descrição) e vai até a foto
    seguinte. Lista vazia se o painel não está aberto.
    """
    elementos = ps.elementos(xml)
    cabecalho = _cabecalho(elementos)
    if not cabecalho:
        return []
    alto, baixo = cabecalho["caixa"][3], _limite_de_baixo(elementos)
    fotos = sorted((el for el in elementos
                    if "comment" in el["descricao"].casefold() and "like" not in el["descricao"].casefold()
                    and ps._centro(el)[0] < 260 and alto <= ps._centro(el)[1] < baixo),
                   key=lambda el: el["caixa"][1])
    comentarios = []
    for i, foto in enumerate(fotos):
        comeco = foto["caixa"][1] - 20
        fim = fotos[i + 1]["caixa"][1] - 20 if i + 1 < len(fotos) else baixo
        dentro = sorted((el for el in elementos if comeco <= ps._centro(el)[1] < fim and el["texto"].strip()),
                        key=lambda el: (el["caixa"][1], el["caixa"][0]))
        textos = [el["texto"] for el in dentro if _do_comentario(el["texto"])]
        responder = next((ps._centro(el) for el in dentro if ps._normal(el["texto"]) == "responder"), None)
        ver = next((ps._centro(el) for el in dentro if VER_RESPOSTAS.match(ps._normal(el["texto"]))), None)
        coracao = next((el for el in elementos if CORACAO_DO_COMENTARIO in el["descricao"].casefold()
                        and comeco <= ps._centro(el)[1] < fim), None)
        numero = next((el for el in elementos if NUMERO_DE_CURTIDAS.match(ps._normal(el["texto"]))
                       and ps._dentro(ps._centro(el), coracao["caixa"])), None) if coracao else None
        comentarios.append({
            "nome": textos[0] if textos else "", "texto": " ".join(textos[1:2]),
            "resposta": ps._centro(foto)[0] >= 130,
            "criador": any(ps._normal(el["texto"]) == "criador" for el in dentro),
            "responder": responder, "ver_respostas": ver, "curtir": ps._centro(coracao) if coracao else None,
            "curtido": any(CURTIDO_PELO_CRIADOR.match(ps._normal(el["texto"])) for el in dentro),
            "coracao_desc": coracao["descricao"] if coracao else "",
            "curtidas": numero_de_curtidas(numero["texto"]) if numero else 0,
            "y": ps._centro(foto)[1],
        })
    return comentarios


def numero_de_curtidas(texto):
    """O número de curtidas escrito no coração ("1", "1.234", "1,2 mil"); 0 sem número."""
    achado = NUMERO_DE_CURTIDAS.match(ps._normal(texto))
    if not achado:
        return 0
    valor = achado.group(1)
    try:
        if achado.group(2):
            return int(float(valor.replace(".", "").replace(",", ".")) * 1000)
        return int(valor.replace(".", "").replace(",", ""))
    except ValueError:
        return 0


def alvo_no_painel(comentarios, nome, texto):
    """A posição do comentário da pessoa (não as respostas) na lista do painel, ou None."""
    for i, c in enumerate(comentarios):
        if not c["resposta"] and ps._normal(c["nome"]) == ps._normal(nome) and parecidos(c["texto"], texto):
            return i
    return None


def respostas_embaixo(comentarios, i):
    """As respostas que aparecem embaixo do comentário i, até o próximo comentário."""
    respostas = []
    for c in comentarios[i + 1:]:
        if not c["resposta"]:
            break
        respostas.append(c)
    return respostas


def do_criador_embaixo(comentarios, i):
    """Quantas respostas do dono do vídeo já estão embaixo do comentário i."""
    return sum(1 for c in respostas_embaixo(comentarios, i) if c["criador"])


def _e_a_resposta(texto, resposta):
    """
    O texto lido na tela é a resposta do robô, mesmo cortada no fim? Um comentário curto
    que só começa igual a ela (o "Lindo" da pessoa e o "Lindo demais! ..." do robô) não é.
    """
    return parecidos(texto, resposta) and len(_chave(texto)) >= min(len(_chave(resposta)), MINIMO_DA_RESPOSTA)


def _de_cima(comentarios, j):
    """O comentário de cima da linha j (ela mesma, se não é resposta), ou None se ele não está na tela."""
    return next((k for k in range(j, -1, -1) if not comentarios[k]["resposta"]), None)


def onde_ficou(comentarios, i, resposta):
    """
    Onde a resposta do robô apareceu: "embaixo" (do comentário i, como devia), "outro
    lugar" (embaixo de outro comentário que está na tela, ou solta na lista) ou None (não
    apareceu, ou só sem o comentário de cima dela na tela: não dá para dizer onde ficou).
    """
    if i is not None and any(_e_a_resposta(c["texto"], resposta) for c in respostas_embaixo(comentarios, i)):
        return "embaixo"
    if any(_e_a_resposta(c["texto"], resposta) and _de_cima(comentarios, j) not in (None, i)
           for j, c in enumerate(comentarios)):
        return "outro lugar"
    return None


def como_ficou(comentarios, i, resposta):
    """
    O que o painel mostra da resposta do robô, em rótulos fixos (sem nome nem texto), para
    o registro: o comentário da pessoa na tela ou não, onde a resposta aparece e se tem o
    selo Criador.
    """
    if not comentarios:
        return "painel sem comentários na tela"
    comentario = "comentário na tela" if i is not None else "comentário fora da tela"
    j = next((j for j, c in enumerate(comentarios) if _e_a_resposta(c["texto"], resposta)), None)
    if j is None:
        return f"{comentario}, resposta não vista"
    dono = _de_cima(comentarios, j)
    lugar = ("resposta solta na lista" if dono == j else "resposta sem o comentário de cima na tela" if dono is None
             else "resposta embaixo dele" if dono == i else "resposta embaixo de outro comentário")
    return f"{comentario}, {lugar}, {'com' if comentarios[j]['criador'] else 'sem'} o selo Criador"


def produto_do_painel(xml):
    """O nome do produto no cartão do alto do painel (acima do "# Comentários"), ou ""."""
    elementos = ps.elementos(xml)
    cabecalho = _cabecalho(elementos)
    if not cabecalho:
        return ""
    textos = sorted((el for el in elementos if el["caixa"][3] <= cabecalho["caixa"][1]
                     and sum(c.isalpha() for c in el["texto"]) >= 8 and "cupom" not in el["texto"].casefold()),
                    key=lambda el: el["caixa"][1])
    return textos[0]["texto"] if textos else ""


def campo_de_escrever(xml):
    """O campo com o teclado (EditText) do painel, ou None."""
    return next((el for el in ps.elementos(xml) if el["classe"] == "EditText"), None)


def botao_de_enviar(xml, campo):
    """O botão de enviar: à direita do campo, na mesma altura. None se não está lá."""
    _, y = ps._centro(campo)
    candidatos = [el for el in ps.elementos(xml)
                  if el is not campo and el["caixa"][0] >= campo["caixa"][2] - 20 and abs(ps._centro(el)[1] - y) < 60]
    return ps._centro(min(candidatos, key=lambda el: el["caixa"][0])) if candidatos else None


def teclado_aberto(xml):
    """O teclado do celular está na tela (as teclas têm ids key_pos_...)?"""
    return any(el["id"].startswith("key_pos_") or el["id"] == "keyboard_holder" for el in ps.elementos(xml))


# --- O feed Live e Vídeo ---

def eh_live(xml):
    """A tela do feed é uma live (ids live_..., espectadores, Diga alguma coisa)?"""
    return any(el["id"].startswith("live_") or el["id"] in ("tv_audience_viewer_num", "tv_send_message")
               for el in ps.elementos(xml))


def coracao_curtido(descricao):
    """
    O coração do player está curtido? True, False ou None (a descrição não diz). A
    descrição do coração começa com "like" no vídeo ainda não curtido (Motorola, 24/10/2026).
    """
    normal = ps._normal(descricao)
    if normal.startswith(("unlike", "liked")) or " liked" in normal:
        return True
    if normal.startswith("like"):
        return False
    return None


def video_do_feed(xml):
    """
    O vídeo na tela do feed: {"autor", "legenda", "coracao", "coracao_desc", "balao"}, ou
    None (live, outra tela). A coluna da direita, de cima para baixo: foto do criador,
    coração, balão de comentários, compartilhar ("share" na descrição) e mais; o nome do
    criador ("video caption user") e a legenda ("video caption ...") ficam embaixo, à esquerda.
    """
    return ler_o_feed(xml)[0]


def ler_o_feed(xml):
    """
    (vídeo, motivo): o vídeo de video_do_feed, ou None e o motivo fixo de não ser um vídeo
    para comentar. O motivo vai para o registro, e o checkup mostra onde o robô se perdeu.
    """
    elementos = ps.elementos(xml)
    if eh_live(xml):
        return None, "live"
    if not any(el["id"].startswith("rn_vod_player_view") for el in elementos):
        return None, "tela sem o player de vídeo"
    direita = sorted((el for el in elementos if el["clicavel"] and ps._centro(el)[0] > 900),
                     key=lambda el: el["caixa"][1])
    compartilhar = next((i for i, el in enumerate(direita) if "share" in el["descricao"].casefold()), None)
    if compartilhar is None:
        return None, "sem o compartilhar na coluna da direita"
    if compartilhar < 2:
        return None, "coluna da direita sem o coração e o balão"
    coracao, balao = direita[compartilhar - 2], direita[compartilhar - 1]
    # Embaixo, à esquerda: "video caption user" (o nome do criador) e "video caption ..." (a legenda).
    caixas = sorted((el for el in elementos if ps._normal(el["descricao"]).startswith("video caption")
                     and ps._centro(el)[0] < 700), key=lambda el: el["caixa"][1])

    def texto_em(caixa):
        return next((el["texto"] for el in elementos if el["texto"].strip()
                     and ps._dentro(ps._centro(el), caixa["caixa"])), "")

    autor = next((texto_em(c) for c in caixas if ps._normal(c["descricao"]) == "video caption user"), "")
    if not autor:
        return None, "sem o nome do criador"
    legenda = next((t for t in (texto_em(c) for c in caixas if ps._normal(c["descricao"]) != "video caption user")
                    if t and t != autor), "")
    return {"autor": autor, "legenda": legenda, "coracao": ps._centro(coracao),
            "coracao_desc": coracao["descricao"], "balao": ps._centro(balao),
            "comentarios": numero_embaixo(elementos, balao)}, ""


def numero_embaixo(elementos, botao):
    """O número escrito logo embaixo de um botão da coluna da direita (no balão, os comentários), ou None."""
    x1, _y1, x2, y2 = botao["caixa"]
    for el in elementos:
        x, y = ps._centro(el)
        if el["texto"].strip() and x1 - 30 <= x <= x2 + 30 and y2 - 5 <= y <= y2 + 60:
            return contagem(el["texto"])
    return None


def contagem(texto):
    """O número do app: "3" → 3, "1.234" → 1234, "1,2 mil" → 1200, "2K" → 2000; None se não é um número."""
    numero, multiplo = ps._normal(texto).replace(" ", "").rstrip("+"), 1
    for sufixo, valor in (("mil", 1000), ("mi", 1000000), ("k", 1000), ("m", 1000000)):
        if numero.endswith(sufixo):
            numero, multiplo = numero[:-len(sufixo)].replace(",", "."), valor
            break
    else:
        numero = numero.replace(".", "").replace(",", "")
    try:
        return int(float(numero) * multiplo)
    except ValueError:
        return None


def campo_de_comentar(xml):
    """O "add a comment" do painel de comentários (fechado, sem o teclado), ou None."""
    el = next((el for el in ps.elementos(xml) if "add a comment" in el["descricao"].casefold()), None)
    return ps._centro(el) if el else None


def painel_aberto(xml):
    """O painel de comentários está aberto (o "# Comentários" no alto dele)?"""
    return _cabecalho(ps.elementos(xml)) is not None


def compartilhar_do_video(xml):
    """
    O compartilhar da coluna da direita do player de vídeo ("share" na descrição; o "Compartilhar" escrito embaixo
    dele), com o painel de comentários fechado: o caminho do Copiar link do vídeo aberto. None sem ele.
    """
    elementos = ps.elementos(xml)
    if _cabecalho(elementos) or not any(el["id"].startswith("rn_vod_player_view") for el in elementos):
        return None
    el = next((el for el in elementos if el["clicavel"] and ps._centro(el)[0] > 900
               and "share" in el["descricao"].casefold()), None)
    return ps._centro(el) if el else None


# --- O texto da IA ---

PROMPT_RESPOSTA = """Você é o criador de um vídeo de achadinhos na Shopee Vídeo e vai responder um comentário que alguém deixou no seu vídeo.

Produto do vídeo: {produto}
Legenda do vídeo: {legenda}
Comentário: {comentario}
Respostas que você já deu hoje (não repita nenhuma): {anteriores}

Escreva UMA resposta curta, em português do Brasil, com no máximo {limite} caracteres:
- simpática, natural e a favor do vídeo e do produto, puxando para a compra e para compartilhar (exemplo do tom: "Pronta para arrasar! Gostou? Compartilha com aquela amiga que vai amar");
- responda ao que a pessoa disse; numa dúvida, diga só o que dá para saber pelo produto e pela legenda e convide a ver os detalhes no produto do vídeo; numa reclamação, responda com educação e sem prometer nada;
- sem o nome da pessoa, sem nome de marca, sem link, sem preço, sem desconto ou promessa que o produto e a legenda não mostram, sem pedir dados e sem chamar para fora da Shopee;
- com palavras que não mostram o gênero de quem responde (ex.: "Valeu!" em vez de "Obrigado" ou "Obrigada");
- no máximo 1 emoji, sem hashtags e sem aspas.
Se o comentário for ofensivo, golpe, propaganda de outra loja ou conteúdo adulto, escreva só: PULAR"""

PROMPT_COMENTARIO = """Você vai comentar, como um comprador animado, um vídeo de achadinhos de outro criador na Shopee Vídeo.

Legenda do vídeo: {legenda}
Comentários que você já fez (não repita nem escreva parecido): {anteriores}

Escreva UM comentário curto, em português do Brasil, com no máximo {limite} caracteres: natural, positivo e sobre o que a legenda mostra (o produto, o resultado, a ideia), como uma pessoa de verdade escreveria. Sem link, sem nome de marca, sem convite para o seu perfil, sem pedir nada, sem hashtags, no máximo 1 emoji e sem aspas.
Se a legenda tiver conteúdo adulto, político, ofensivo, de aposta ou de golpe, escreva só: PULAR"""

# Com a tela do vídeo anexa, o comentário fala do que aparece nele. Escolha do Rafael (P70).
SOBRE_A_IMAGEM = """

A imagem anexa é a tela do vídeo agora: comente o que aparece nela (o produto, o resultado, a ideia), junto com a legenda, sem falar dos botões nem dos textos do aplicativo. Se a imagem mostrar conteúdo adulto, político, ofensivo, de aposta ou de golpe, escreva só: PULAR"""

# O pedido do comentário continua o mesmo; só ganha a saída de só curtir (P151 1).
SO_CURTIR = f"""

Se o vídeo não for para PULAR, mas não houver nada específico para comentar sobre o que ele mostra (o produto, o resultado ou a ideia), escreva só: {CURTIR}"""


PROMPT_PROPRIO = """Você é o criador de um vídeo de achadinhos na Shopee Vídeo e vai deixar um comentário no seu próprio vídeo, para chamar quem assiste a comprar.

Produto do vídeo: {produto}
Título do vídeo: {titulo}
Comentários que já estão no vídeo ou que você já escreveu (não repita nem escreva parecido com nenhum): {anteriores}

Escreva UM comentário curto, em português do Brasil, com no máximo {limite} caracteres:
- natural e animado, chamando para comprar o produto do vídeo (exemplo do tom: "Esse aqui vale muito a pena! Ele está nos produtos do vídeo");
- só o que o título e o produto mostram: sem preço, desconto, frete ou estoque que eles não dizem, sem promessa de resultado e sem exagero ("garantido", "milagre", "cura");
- sem nome de marca, sem link, sem chamar para fora da Shopee e sem pedir curtida, seguidor ou compartilhamento;
- com palavras que não mostram o gênero de quem escreve;
- sem hashtags, no máximo 1 emoji e sem aspas."""


def texto_simples(texto, limite):
    """
    O texto da IA pronto para o campo: sem aspas, sem quebra de linha e sem emoji de fora
    do plano básico (o 😍 e o 👗 a leitura da tela devolve como "..", e o robô não
    conseguiria conferir o que escreveu), cortado no limite numa palavra inteira.
    """
    texto = "".join(c for c in str(texto or "") if ord(c) <= 0xFFFF and c not in ASPAS)
    texto = " ".join(texto.split())
    if len(texto) > limite:
        texto = texto[:limite].rsplit(" ", 1)[0].rstrip(",;:-")
    return texto


async def _pedir(prompt, limite, tentativas=2, imagens=None, curtir=False):
    """
    O texto da IA (com as imagens [(bytes, tipo)], se vierem); "" quando ela diz PULAR; CURTIR
    quando ela diz CURTIR (com curtir, no vídeo do feed sem nada específico para comentar);
    None quando ela não respondeu.
    """
    import api_gemini
    for _ in range(tentativas):
        resposta = await (api_gemini.gerar_texto_gemini(prompt, imagens=imagens) if imagens
                          else api_gemini.gerar_texto_gemini(prompt))
        if not resposta:
            continue
        if resposta.strip().strip(".!").upper() == "PULAR":
            return ""
        # Só a palavra, com ou sem pontuação ou emoji em volta: nunca vira o texto do comentário.
        if curtir and re.sub(r"[^A-Za-z]", "", resposta).upper() == CURTIR:
            return CURTIR
        texto = texto_simples(resposta, limite)
        if len(texto) >= 2:
            return texto
    return None


async def gerar_resposta(comentario, produto="", legenda="", anteriores=()):
    """A resposta a um comentário do vídeo do Rafael (P9: feita pela IA, diferente para cada pessoa)."""
    prompt = PROMPT_RESPOSTA.format(produto=produto or "—", legenda=legenda or "—", comentario=comentario or "—",
                                    anteriores="; ".join(anteriores) or "nenhuma", limite=TAMANHO_DA_RESPOSTA)
    return await _pedir(prompt, TAMANHO_DA_RESPOSTA)


async def gerar_comentario(legenda="", anteriores=(), imagem=None):
    """
    O comentário num vídeo do feed (P10: curto e diferente a cada vez). Com a imagem (JPEG da
    tela do vídeo), sobre o que aparece nele (P70). CURTIR quando a IA não vê nada específico
    para dizer: o robô só curte (P151 1).
    """
    prompt = (PROMPT_COMENTARIO.format(legenda=legenda or "—", anteriores="; ".join(anteriores) or "nenhum",
                                       limite=TAMANHO_DO_COMENTARIO) + (SOBRE_A_IMAGEM if imagem else "") + SO_CURTIR)
    return await _pedir(prompt, TAMANHO_DO_COMENTARIO, imagens=[(imagem, "image/jpeg")] if imagem else None,
                        curtir=True)


async def gerar_proprio(produto="", titulo="", anteriores=()):
    """
    O comentário do Rafael no próprio vídeo (P148 2): curto, sem hashtag, chamando para comprar,
    diferente dos que já estão no vídeo e dos últimos que o robô escreveu. Volta para a IA
    uma vez quando o texto sai igual a um deles; None se ela não escreveu um novo.
    """
    prompt = PROMPT_PROPRIO.format(produto=produto or "—", titulo=titulo or "—",
                                   anteriores="; ".join(anteriores) or "nenhum", limite=TAMANHO_DO_PROPRIO)
    for _ in range(2):
        texto = await _pedir(prompt, TAMANHO_DO_PROPRIO)
        if texto and not any(parecidos(texto, anterior) for anterior in anteriores):
            return texto
    return None
