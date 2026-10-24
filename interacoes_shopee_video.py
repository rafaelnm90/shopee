"""
As interações do robô da Shopee Vídeo além de postar: responder os comentários dos
vídeos do Rafael e curtir e comentar vídeos de outros criadores no feed Live e Vídeo →
Para você. Pedidos do Rafael de 24/10/2026 (P9, P10 e P11): DECISOES.md, Shopee Vídeo.

Aqui fica o que não toca no celular: a leitura das telas (a lista das Notificações, o
painel de comentários e o player do feed), o texto da IA e as marcas do que já foi
feito. Os toques ficam no robo_shopee_video, que chama estas funções; o checkup conta o
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
# Escolha do Rafael (P10): 3 comentários por dia no feed, cada um diferente.
COMENTARIOS_NO_FEED_POR_DIA = 3
TAMANHO_DA_RESPOSTA = 150
TAMANHO_DO_COMENTARIO = 80
# Os estados de um comentário em que ele não volta mais.
FINAIS = frozenset({"respondido", "já respondido", "pulado", "desistiu", "anterior", "lugar errado"})

# O aviso de comentário nas Notificações: "Fulana comentou no seu vídeo: "Amei!"".
COMENTOU = re.compile(r"^(?P<nome>.+?)\s+comentou no seu v[ií]deo\s*:?\s*(?P<texto>.*)$", re.S | re.I)
ASPAS = "\"“”'‘’"
# A hora de cada linha das Notificações ("Hoje 10:15", "24-10 14:32").
HORA_DA_LINHA = re.compile(r"^(?:\S+\s+)?\d{1,2}:\d{2}$")
# O que acompanha cada comentário no painel e não é o nome nem o texto.
EM_VOLTA_DO_COMENTARIO = (
    re.compile(r"^criador$"), re.compile(r"^responder$"), re.compile(r"^curtido pelo criador"),
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


def terminado(marca_):
    """O comentário já teve um fim (respondido, pulado, desistido...)? Esses não voltam."""
    return resultado_de(marca_, "comentario") in FINAIS


def quantos_desde(tipo, resultado, desde):
    """Quantas marcas do tipo ficaram com o resultado desde o momento ("AAAA-MM-DD HH:MM:SS")."""
    with db.conexao() as con:
        _criar_tabela(con)
        return con.execute("SELECT COUNT(*) FROM shopee_video_interacoes WHERE tipo = ? AND resultado = ? "
                           "AND momento >= ?", (tipo, resultado, desde)).fetchone()[0]


# --- As Notificações ---

def linhas_das_notificacoes(xml, filtro):
    """
    Os textos das linhas da lista (filtro Lives, Vídeos e ...), de cima para baixo: só o
    aviso de cada linha, sem a hora. O que fica atrás da fileira de filtros (a lista rolada
    por baixo dela) e a linha cortada pela barra de baixo ficam de fora.
    """
    elementos = ps.elementos(xml)
    chips = [el for el in elementos if ps._normal(el["texto"]).startswith(ps._normal(filtro))]
    if not chips:
        return []
    topo = max(el["caixa"][3] for el in chips)
    barra = [el["caixa"][1] for el in elementos if el["id"] in ("sp_bottom_navigation_container", "shadow_view")]
    fundo = min(barra) if barra else 10 ** 6
    linhas = [el for el in elementos
              if el["texto"].strip() and el["caixa"][1] >= topo and el["caixa"][3] <= fundo
              and not HORA_DA_LINHA.match(el["texto"].strip())]
    linhas.sort(key=lambda el: (el["caixa"][1], el["caixa"][0]))
    return [{"texto": el["texto"], "ponto": ps._centro(el)} for el in linhas]


def comentario_da_notificacao(texto):
    """(nome, comentário) de um aviso "Fulana comentou no seu vídeo: ..."; None nos outros avisos."""
    achado = COMENTOU.match(" ".join((texto or "").split()))
    if not achado:
        return None
    return achado["nome"].strip(), achado["texto"].strip().strip(ASPAS).strip()


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
    "responder" e "ver_respostas" (os pontos de tocar, ou None), "y"}. Cada comentário
    começa na foto (x pequeno, com "comment" na descrição) e vai até a foto seguinte.
    Lista vazia se o painel não está aberto.
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
        comentarios.append({
            "nome": textos[0] if textos else "", "texto": " ".join(textos[1:2]),
            "resposta": ps._centro(foto)[0] >= 130,
            "criador": any(ps._normal(el["texto"]) == "criador" for el in dentro),
            "responder": responder, "ver_respostas": ver, "y": ps._centro(foto)[1],
        })
    return comentarios


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


def onde_ficou(comentarios, i, resposta):
    """
    Onde a resposta do robô apareceu: "embaixo" (do comentário i, como devia), "outro
    lugar" (embaixo de outro comentário ou solta na lista) ou None (não apareceu).
    """
    if i is not None and any(c["criador"] and parecidos(c["texto"], resposta)
                             for c in respostas_embaixo(comentarios, i)):
        return "embaixo"
    if any(parecidos(c["texto"], resposta) for c in comentarios):
        return "outro lugar"
    return None


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
    criador e a legenda ficam embaixo, à esquerda, com "video" no começo da descrição.
    """
    elementos = ps.elementos(xml)
    if eh_live(xml) or not any(el["id"].startswith("rn_vod_player_view") for el in elementos):
        return None
    direita = sorted((el for el in elementos if el["clicavel"] and ps._centro(el)[0] > 900),
                     key=lambda el: el["caixa"][1])
    compartilhar = next((i for i, el in enumerate(direita) if "share" in el["descricao"].casefold()), None)
    if compartilhar is None or compartilhar < 2:
        return None
    coracao, balao = direita[compartilhar - 2], direita[compartilhar - 1]
    caixas = sorted((el for el in elementos if ps._normal(el["descricao"]).startswith("video ")
                     and ps._centro(el)[0] < 700), key=lambda el: el["caixa"][1])
    textos = []
    for caixa in caixas:
        texto = next((el["texto"] for el in elementos if el["texto"].strip()
                      and ps._dentro(ps._centro(el), caixa["caixa"])), "")
        if texto and texto not in textos:
            textos.append(texto)
    if not textos:
        return None
    return {"autor": textos[0], "legenda": " ".join(textos[1:2]), "coracao": ps._centro(coracao),
            "coracao_desc": coracao["descricao"], "balao": ps._centro(balao)}


def campo_de_comentar(xml):
    """O "add a comment" do painel de comentários (fechado, sem o teclado), ou None."""
    el = next((el for el in ps.elementos(xml) if "add a comment" in el["descricao"].casefold()), None)
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


async def _pedir(prompt, limite, tentativas=2):
    """O texto da IA; "" quando ela diz PULAR; None quando ela não respondeu."""
    import api_gemini
    for _ in range(tentativas):
        resposta = await api_gemini.gerar_texto_gemini(prompt)
        if not resposta:
            continue
        if resposta.strip().strip(".!").upper() == "PULAR":
            return ""
        texto = texto_simples(resposta, limite)
        if len(texto) >= 2:
            return texto
    return None


async def gerar_resposta(comentario, produto="", legenda="", anteriores=()):
    """A resposta a um comentário do vídeo do Rafael (P9: feita pela IA, diferente para cada pessoa)."""
    prompt = PROMPT_RESPOSTA.format(produto=produto or "—", legenda=legenda or "—", comentario=comentario or "—",
                                    anteriores="; ".join(anteriores) or "nenhuma", limite=TAMANHO_DA_RESPOSTA)
    return await _pedir(prompt, TAMANHO_DA_RESPOSTA)


async def gerar_comentario(legenda="", anteriores=()):
    """O comentário num vídeo do feed (P10: curto e diferente a cada vez)."""
    prompt = PROMPT_COMENTARIO.format(legenda=legenda or "—", anteriores="; ".join(anteriores) or "nenhum",
                                      limite=TAMANHO_DO_COMENTARIO)
    return await _pedir(prompt, TAMANHO_DO_COMENTARIO)
