"""
As punições da Shopee Vídeo e o texto da apelação de cada uma, para o Rafael copiar e
colar no app (Apelar aqui). Pedido do Rafael: DECISOES.md, Shopee Vídeo.

O caminho:
- o robô (robo_shopee_video.py) lê no Motorola a tela Saúde do Vídeo, uma vez por dia,
  quando acha uma punição nova nas Notificações, quando acha a suspensão da conta e
  pelo botão Gerar Apelação ⚖️; cada punição entra na tabela shopee_video_punicoes, com
  o vídeo (título e data do post) e o texto que a IA escreveu (gerar_texto);
- o bot_mestre (painel_shopee_video, lembrar) manda no privado o aviso de cada punição
  ainda não recorrida e o repete de hora em hora, a qualquer hora, como as perguntas do
  Claude, até o Rafael tocar em Já recorri ou Não vou recorrer; se a Saúde do Vídeo
  mostrar que ela já foi recorrida, para também;
- Relatório Geral 📊 → Saúde da Shopee Vídeo 🩺 mostra as punições (texto_saude).

O texto só diz o que é verdade: punição por propriedade intelectual de vídeo que veio de
outro canal nunca ganha texto dizendo que o vídeo é dele; ganha o texto sem autoria
(texto_sem_autoria: afiliado, o produto vendido na própria Shopee, o pedido de revisão), e
o aviso diz de onde veio o vídeo.
"""
import html
import json
import logging
import re
from datetime import datetime, timedelta

import db
from fuso import fuso_horario

logger = logging.getLogger(__name__)

INTERVALO = timedelta(hours=1)
# O campo "Razão para apelar" do app aceita até 200 caracteres.
TAMANHO_DO_TEXTO = 200
# A Saúde do Vídeo mostra as violações dos últimos 30 dias.
DIAS_DA_SAUDE = 30
# Status da apelação, como o app escreve.
NAO_RECORRIDO = "Não Recorrido"
# O que o Rafael decidiu (ou o app mostrou) sobre cada punição.
PENDENTE, RECORRIDA, NAO_VAI, ENCERRADA = "pendente", "recorrida", "nao_vai", "encerrada"
# O recurso deu certo: a Shopee marca "Bem-sucedido" ou tira a punição da Saúde do Vídeo
# (com isso os pontos baixam, e a suspensão que dependia deles some). Saiu da lista por ter
# mais de 30 dias: fora da janela.
ACEITA, RETIRADA, FORA_DA_JANELA, RECUSADA = "aceita", "retirada", "fora_da_janela", "recusada"
ROTULOS = {PENDENTE: "⏳ não recorrida (lembrando de hora em hora)", RECORRIDA: "✅ recorrida",
           NAO_VAI: "🚫 você escolheu não recorrer", ENCERRADA: "⌛ o prazo do recurso acabou",
           ACEITA: "🎉 recurso aceito", RETIRADA: "🎉 a Shopee tirou a punição (recurso aceito)",
           FORA_DA_JANELA: "📅 saiu dos últimos 30 dias", RECUSADA: "❌ a Shopee não aceitou o recurso"}
# Depois do Já recorri, o robô olha a Saúde do Vídeo de hora em hora até sair o resultado
# (escolha do Rafael em 24/10, P6), por até estes dias: o Já recorri tocado sem o recurso
# enviado não deixa o robô olhando para sempre.
DIAS_ESPERANDO_O_RESULTADO = 7
# A escala dos pontos de penalidade na Saúde do Vídeo (0 a 15, Motorola em 24/10/2026) e,
# como o Rafael explicou (24/10/2026), com quantos a Shopee suspende as postagens: com 5
# não há suspensão, com 6 há; o recurso aceito tira os pontos da punição.
PONTOS_DA_ESCALA = 15
PONTOS_DA_SUSPENSAO = 6
# Fontes que são vídeos do próprio Rafael: só nelas o texto pode dizer que o vídeo é dele.
FONTES_PROPRIAS = ("autorais",)
CALLBACK_RECORRI, CALLBACK_NAO_VAI = "apel_ok:", "apel_nao:"


def _momento(agora=None):
    return (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d %H:%M:%S")


def _criar_tabela(con):
    con.execute("CREATE TABLE IF NOT EXISTS shopee_video_punicoes ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, chave TEXT UNIQUE, tipo TEXT, data_punicao TEXT, "
                "status_app TEXT, titulo TEXT, postado_em TEXT, rascunho INTEGER, fonte TEXT, texto TEXT, "
                "observacao TEXT, situacao TEXT, criada TEXT, lida_em TEXT, ultimo_aviso TEXT, "
                "avisos INTEGER DEFAULT 0, recorrida_em TEXT, mensagens TEXT)")
    # As colunas que vieram depois entram na tabela que já existe no servidor.
    existentes = {linha[1] for linha in con.execute("PRAGMA table_info(shopee_video_punicoes)")}
    for coluna in ("recorrida_em", "mensagens"):
        if coluna not in existentes:
            con.execute(f"ALTER TABLE shopee_video_punicoes ADD COLUMN {coluna} TEXT")


COLUNAS = ("id", "chave", "tipo", "data_punicao", "status_app", "titulo", "postado_em", "rascunho", "fonte",
           "texto", "observacao", "situacao", "criada", "lida_em", "ultimo_aviso", "avisos", "recorrida_em",
           "mensagens")


def _ler(linhas):
    return [dict(zip(COLUNAS, linha)) for linha in linhas]


def chave(tipo, data_punicao):
    """Uma punição é o tipo e a data dela, como a Saúde do Vídeo mostra."""
    return f"{' '.join(str(tipo).split())}|{' '.join(str(data_punicao).split())}"


def recorrida_no_app(status_app):
    return bool(status_app) and status_app.strip().casefold() != NAO_RECORRIDO.casefold()


def aceita_no_app(status_app):
    """O app marca o recurso aceito como "Bem-sucedido"."""
    return "sucedid" in (status_app or "").casefold() and "mal" not in (status_app or "").casefold()


def recusada_no_app(status_app):
    """O recurso que a Shopee não aceitou (o texto exato do app ainda não foi visto: as formas comuns)."""
    texto = (status_app or "").casefold()
    return any(palavra in texto for palavra in ("malsucedid", "mal-sucedid", "recusad", "rejeitad", "negad",
                                                "reprovad", "falhou", "não aceit"))


def situacao_de(tipo, data_punicao):
    with db.conexao() as con:
        _criar_tabela(con)
        linha = con.execute("SELECT situacao FROM shopee_video_punicoes WHERE chave = ?",
                            (chave(tipo, data_punicao),)).fetchone()
        return linha[0] if linha else None


def conhecida(tipo, data_punicao):
    """A punição já está na tabela? (o robô não precisa abrir o vídeo dela de novo)"""
    with db.conexao() as con:
        _criar_tabela(con)
        return con.execute("SELECT 1 FROM shopee_video_punicoes WHERE chave = ?",
                           (chave(tipo, data_punicao),)).fetchone() is not None


def guardar(tipo, data_punicao, status_app, titulo="", postado_em="", rascunho=None, fonte="", texto="",
            observacao="", pode_apelar=True, agora=None):
    """
    Guarda uma punição nova, ou atualiza o status do app de uma conhecida. A que já foi
    recorrida no app nunca é lembrada; a pendente que o app mostra recorrida para de
    ser lembrada; a que não tem mais o Apelar aqui (prazo acabou) também não é lembrada.
    Devolve o id.
    """
    k = chave(tipo, data_punicao)
    with db.conexao() as con:
        _criar_tabela(con)
        linha = con.execute("SELECT id, situacao FROM shopee_video_punicoes WHERE chave = ?", (k,)).fetchone()
        if linha:
            ident, situacao = linha
            if situacao == PENDENTE and recorrida_no_app(status_app):
                situacao = RECORRIDA
            if aceita_no_app(status_app) and situacao not in (RETIRADA, FORA_DA_JANELA):
                situacao = ACEITA
            elif recusada_no_app(status_app) and situacao in (PENDENTE, RECORRIDA):
                situacao = RECUSADA
            con.execute("UPDATE shopee_video_punicoes SET status_app = ?, situacao = ?, lida_em = ? WHERE id = ?",
                        (status_app, situacao, _momento(agora), ident))
            return ident
        situacao = (ACEITA if aceita_no_app(status_app) else RECUSADA if recusada_no_app(status_app)
                    else RECORRIDA if recorrida_no_app(status_app) else PENDENTE if pode_apelar else ENCERRADA)
        cursor = con.execute(
            "INSERT INTO shopee_video_punicoes (chave, tipo, data_punicao, status_app, titulo, postado_em, rascunho, "
            "fonte, texto, observacao, situacao, criada, lida_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (k, tipo, data_punicao, status_app, titulo, postado_em, rascunho, fonte, texto, observacao, situacao,
             _momento(agora), _momento(agora)))
        return cursor.lastrowid


def pegar(ident):
    with db.conexao() as con:
        _criar_tabela(con)
        return next(iter(_ler(con.execute(f"SELECT {', '.join(COLUNAS)} FROM shopee_video_punicoes WHERE id = ?",
                                          (ident,)).fetchall())), None)


def todas():
    """Da mais nova para a mais velha (pela ordem em que o robô achou)."""
    with db.conexao() as con:
        _criar_tabela(con)
        return _ler(con.execute(f"SELECT {', '.join(COLUNAS)} FROM shopee_video_punicoes ORDER BY id DESC").fetchall())


def marcar(ident, situacao, agora=None):
    """
    O Rafael tocou em Já recorri ou Não vou recorrer: o lembrete para. False se já não
    estava pendente. Já recorri guarda a hora: o robô passa a esperar o resultado.
    """
    with db.conexao() as con:
        _criar_tabela(con)
        cursor = con.execute("UPDATE shopee_video_punicoes SET situacao = ?, recorrida_em = ? WHERE id = ? AND "
                             "situacao = ?", (situacao, _momento(agora) if situacao == RECORRIDA else None, ident,
                                              PENDENTE))
        return cursor.rowcount > 0


def esperando_resultado(agora=None):
    """
    As punições que o Rafael recorreu (Já recorri) há menos de DIAS_ESPERANDO_O_RESULTADO
    dias e ainda sem resultado: o robô olha a Saúde do Vídeo de hora em hora por elas.
    """
    corte = _momento((agora or datetime.now(fuso_horario)) - timedelta(days=DIAS_ESPERANDO_O_RESULTADO))
    return [p for p in todas() if p["situacao"] == RECORRIDA and (p["recorrida_em"] or "") >= corte]


def _data(data_punicao):
    try:
        return datetime.strptime(" ".join(str(data_punicao).split()), "%d/%m/%Y %H:%M:%S").replace(tzinfo=fuso_horario)
    except ValueError:
        return None


def retirar_ausentes(vistas, agora=None):
    """
    Depois de uma leitura completa da Saúde do Vídeo: a punição guardada que não está
    mais na lista saiu. Com menos de 30 dias, a Shopee a tirou (recurso aceito); com mais,
    saiu da janela. Devolve as que o Rafael esperava (pendentes ou recorridas) e que a
    Shopee tirou, para o aviso.
    """
    agora = agora or datetime.now(fuso_horario)
    retiradas = []
    for p in todas():
        if p["chave"] in vistas or p["situacao"] in (RETIRADA, FORA_DA_JANELA):
            continue
        data = _data(p["data_punicao"])
        recente = data is None or agora - data < timedelta(days=DIAS_DA_SAUDE - 1)
        nova = RETIRADA if recente else FORA_DA_JANELA
        with db.conexao() as con:
            con.execute("UPDATE shopee_video_punicoes SET situacao = ?, lida_em = ? WHERE id = ?",
                        (nova, _momento(agora), p["id"]))
        if recente and p["situacao"] in (PENDENTE, RECORRIDA):
            retiradas.append(p)
    return retiradas


def vencidas(agora=None):
    """As pendentes que ainda não foram avisadas ou cujo último aviso tem 1 h ou mais."""
    limite = _momento((agora or datetime.now(fuso_horario)) - INTERVALO)
    return [p for p in todas()[::-1]
            if p["situacao"] == PENDENTE and (not p["ultimo_aviso"] or p["ultimo_aviso"] <= limite)]


def marcar_aviso(ident, agora=None, mensagem=None):
    """O aviso saiu; mensagem: o id dele no privado, para apagar quando o Rafael decidir."""
    with db.conexao() as con:
        _criar_tabela(con)
        linha = con.execute("SELECT mensagens FROM shopee_video_punicoes WHERE id = ?", (ident,)).fetchone()
        mensagens = json.loads((linha[0] if linha else None) or "[]")
        if type(mensagem) is int:
            mensagens.append(mensagem)
        con.execute("UPDATE shopee_video_punicoes SET ultimo_aviso = ?, avisos = COALESCE(avisos, 0) + 1, "
                    "mensagens = ? WHERE id = ?", (_momento(agora), json.dumps(mensagens), ident))


def mensagens_de(ident):
    """Os ids, no privado, do aviso e dos lembretes da punição."""
    p = pegar(ident)
    return json.loads((p or {}).get("mensagens") or "[]")


def guardar_mensagens(ident, mensagens):
    with db.conexao() as con:
        _criar_tabela(con)
        con.execute("UPDATE shopee_video_punicoes SET mensagens = ? WHERE id = ?", (json.dumps(mensagens), ident))


# --- O aviso no privado ---

def montar_aviso(p):
    """O aviso em HTML: a punição, o vídeo, o texto para copiar com um toque e onde colar."""
    avisos = p.get("avisos") or 0
    topo = ("⚖️ <b>A Shopee puniu um vídeo seu: dá para recorrer</b>" if not avisos
            else f"🔔 <b>Lembrete {avisos + 1}: a punição da Shopee Vídeo ainda espera o recurso</b>")
    linhas = [topo, "", f"🚫 <b>Punição:</b> {html.escape(p['tipo'])} ({html.escape(p['data_punicao'])})"]
    if p["titulo"]:
        linhas.append(f"🎬 <b>Vídeo:</b> {html.escape(p['titulo'][:150])}")
    if p["postado_em"]:
        linhas.append(f"📅 <b>Postado em:</b> {html.escape(p['postado_em'])}")
    if p["observacao"]:
        linhas += ["", f"ℹ️ {html.escape(p['observacao'])}"]
    if p["texto"]:
        linhas += ["", f"👇 Toque no texto para copiar ({len(p['texto'])} de {TAMANHO_DO_TEXTO} caracteres):",
                   f"<code>{html.escape(p['texto'])}</code>"]
    linhas += ["", "📲 No app: Notificações (ou Eu → Criadores &amp; Afiliados → Saúde do Vídeo) → o vídeo → "
                   "<b>Apelar aqui</b> → cole em Razão para apelar → <b>Enviar</b>. Não apague o vídeo enquanto o "
                   "recurso estiver em análise.",
               "", "Lembro de hora em hora até você tocar num dos botões abaixo."]
    return "\n".join(linhas)


def botoes(p):
    """Os botões do aviso: qualquer um dos dois para o lembrete."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Já recorri", callback_data=f"{CALLBACK_RECORRI}{p['id']}"),
        InlineKeyboardButton(text="🚫 Não vou recorrer", callback_data=f"{CALLBACK_NAO_VAI}{p['id']}")]])


async def lembrar(enviar, agora=None):
    """
    Manda o aviso de cada punição pendente nunca avisada, e de novo a cada hora.
    enviar(texto, p) é a função do bot (async, devolve o id da mensagem, que fica guardado
    para apagar depois, ou True se saiu). Um aviso que não sai fica para a próxima volta.
    Devolve quantos saíram.
    """
    enviados = 0
    for p in vencidas(agora):
        try:
            mensagem = await enviar(montar_aviso(p), p)
            if mensagem:
                marcar_aviso(p["id"], agora, mensagem)
                enviados += 1
        except Exception as e:
            logger.warning(f"⚠️ [Apelação Shopee Vídeo] Aviso da punição {p['id']} não saiu: {type(e).__name__}")
    return enviados


# --- O texto da apelação ---

PROMPT = """Você escreve o texto de um recurso (apelação) para a Shopee Vídeo, em português do Brasil.
O criador vai copiar e colar o texto no campo "Razão para apelar", que aceita no máximo {limite} caracteres.

Regras:
- No máximo {limite} caracteres, contando espaços. Uma ou duas frases, educadas e diretas.
- Só fatos que estão abaixo. Nunca invente nada (marca, autorização, que o vídeo é original) que não esteja aqui.
- Diga por que o vídeo cumpre a regra da punição e termine pedindo a revisão.
- Se o nome do produto puder ser confundido com outra coisa (ex.: "botijão térmico" com botijão de gás), deixe claro o que o produto é.
- Sem hashtags, emojis, aspas ou link. Devolva só o texto.

Punição: {tipo}
Explicação da Shopee: {explicacao}
Título do vídeo: {titulo}
Produto anexado ao vídeo: {produtos}
O que a IA viu no vídeo antes de postar: {conferencia}
De onde veio o vídeo: {origem}
"""


def _encurtar(texto, limite=TAMANHO_DO_TEXTO):
    """Corta no fim da última frase que cabe; sem frase inteira, no último espaço."""
    texto = " ".join(str(texto or "").replace('"', "").split())
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    fim = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "))
    if fim >= limite // 2:
        return corte[:fim + 1]
    return corte[:corte.rfind(" ")].rstrip(",;:") + "."


def so_com_autoria_verdadeira(tipo, fonte):
    """
    Punição por propriedade intelectual (ou direitos autorais) de vídeo que não é do
    Rafael: o texto diria que o vídeo é dele, o que não é verdade.
    """
    texto = (tipo or "").casefold()
    autoral = "propriedade intelectual" in texto or "direito" in texto
    return not autoral or (fonte or "") in FONTES_PROPRIAS


# O recurso da punição por propriedade intelectual de vídeo que veio de outro canal: só o que
# é verdade, sem dizer que o vídeo é do Rafael nem que é original. Escolha do Rafael (P31):
# DECISOES.md, Shopee Vídeo.
TEXTO_SEM_AUTORIA = ("Sou afiliado da Shopee. Este vídeo divulga {produto}, vendido na própria Shopee e anexado "
                     "ao vídeo. Peço a revisão da remoção.")


def texto_sem_autoria(produtos=(), titulo=""):
    """
    O texto sem autoria, com até TAMANHO_DO_TEXTO caracteres: o nome do produto anexado (ou o
    título do vídeo sem as hashtags), cortado numa palavra se não couber.
    """
    nome = " ".join(str((produtos or [""])[0] or "").split()) or " ".join(
        palavra for palavra in str(titulo or "").split() if not palavra.startswith("#"))
    if not nome:
        return TEXTO_SEM_AUTORIA.format(produto="o produto do vídeo")
    cabe = TAMANHO_DO_TEXTO - len(TEXTO_SEM_AUTORIA.format(produto="o produto "))
    if len(nome) > cabe:
        nome = nome[:cabe].rsplit(" ", 1)[0].rstrip(",;:-")
    return TEXTO_SEM_AUTORIA.format(produto=f"o produto {nome}")


async def gerar_texto(tipo, explicacao="", titulo="", produtos=(), conferencia="", fonte="", tentativas=2):
    """
    O texto do recurso, com até 200 caracteres, ou ("", observação) quando não cabe
    texto verdadeiro. Devolve (texto, observacao).
    """
    if not so_com_autoria_verdadeira(tipo, fonte):
        return texto_sem_autoria(produtos, titulo), (
            "O vídeo veio de outro canal (não é dos Autorais): o texto não diz que ele é seu, só que você é "
            "afiliado e divulga o produto vendido na própria Shopee. Nesse caso a Shopee costuma manter a remoção.")
    import api_gemini
    origem = {"autorais": "gravado pelo próprio criador (Autorais)"}.get(fonte, f"de outro canal ({fonte})"
                                                                           if fonte else "não se sabe")
    prompt = PROMPT.format(limite=TAMANHO_DO_TEXTO, tipo=tipo, explicacao=explicacao or "—", titulo=titulo or "—",
                           produtos=", ".join(produtos) or "—", conferencia=conferencia or "—", origem=origem)
    melhor = ""
    for _ in range(tentativas):
        resposta = await api_gemini.gerar_texto_gemini(prompt)
        texto = " ".join(str(resposta or "").replace('"', "").split())
        if texto and len(texto) <= TAMANHO_DO_TEXTO:
            return texto, ""
        melhor = melhor or texto
    if melhor:
        return _encurtar(melhor), ""
    return "", "A IA não respondeu agora: toque em Gerar Apelação ⚖️ (Relatório Geral 📊 → Saúde da Shopee Vídeo 🩺) para tentar de novo."


# --- A tela Saúde da Shopee Vídeo ---

def texto_saude(config, estado_robo=None, agora=None):
    """
    Relatório Geral 📊 → Saúde da Shopee Vídeo 🩺: a suspensão, os pontos de penalidade
    e as punições dos últimos 30 dias, como o robô leu no Motorola (estado_robo).
    """
    import robo_shopee_video as robo
    agora = agora or datetime.now(fuso_horario)
    estado_robo = estado_robo or {}
    linhas = ["🩺 <b>Saúde da Shopee Vídeo</b>", ""]
    if robo.suspensa(config, agora):
        linhas.append(f"⛔ Conta suspensa pela Shopee até <b>{robo.quando_acaba(robo.suspenso_ate(config))}</b>.")
    else:
        linhas.append("✅ Conta sem suspensão.")
    pontos = estado_robo.get("saude_pontos")
    if pontos is not None:
        if pontos >= PONTOS_DA_SUSPENSAO:
            nota = f"com {PONTOS_DA_SUSPENSAO} ou mais, a Shopee suspende as postagens; recurso aceito tira pontos"
        elif pontos == PONTOS_DA_SUSPENSAO - 1:
            nota = f"a 1 ponto da suspensão, que vem com {PONTOS_DA_SUSPENSAO}"
        else:
            nota = f"a suspensão vem com {PONTOS_DA_SUSPENSAO}"
        linhas.append(f"⚠️ Pontos de penalidade: <b>{pontos}</b> ({nota})")
    lida = estado_robo.get("saude_lida_em") or ""
    try:
        lida = datetime.strptime(lida, "%Y-%m-%d %H:%M:%S").strftime("%d/%m às %H:%M")
    except ValueError:
        lida = "ainda não olhou"
    linhas.append(f"🔎 Última olhada na Saúde do Vídeo do Motorola: <b>{lida}</b>")
    corte = _momento(agora - timedelta(days=DIAS_DA_SAUDE))
    recentes = [p for p in todas() if (p["criada"] or "") >= corte]
    linhas += ["", f"<b>Punições dos últimos {DIAS_DA_SAUDE} dias: {len(recentes)}</b>"]
    for p in recentes[:15]:
        titulo = f"\n   🎬 {html.escape(p['titulo'][:80])}" if p["titulo"] else ""
        linhas.append(f"• {html.escape(p['tipo'])} ({html.escape(p['data_punicao'])}): "
                      f"{ROTULOS.get(p['situacao'], p['situacao'])}{titulo}")
    linhas += ["", "<b>O que o botão faz</b>",
               "⚖️ <b>Gerar Apelação</b>: o robô olha agora a Saúde do Vídeo no Motorola e manda aqui o texto "
               "pronto de cada punição ainda não recorrida, com os botões Já recorri e Não vou recorrer. Ele "
               "também olha sozinho uma vez por dia."]
    return "\n".join(linhas)


def ler_explicacao(texto):
    """A explicação da Shopee, sem espaços repetidos e sem o "Apelar aqui." do fim."""
    return re.sub(r"\s*Apelar aqui\.?\s*$", "", " ".join(str(texto or "").split()))

