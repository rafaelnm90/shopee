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
(texto_sem_autoria: afiliado, o produto vendido na própria Shopee), e o aviso diz de onde
veio o vídeo. Nenhum texto pede a revisão: o recurso já é o pedido, e os 200 caracteres vão
para os fatos (sem_pedido_de_revisao).

Os pontos de penalidade também dizem quantos posts por dia o robô e o modo assistente fazem
(a escada da P144 e da P145, faixa_pelos_pontos): de 0 a 3, a faixa do painel; acima, uma
parte dela com um teto, até os pontos baixarem (recurso aceito) ou zerarem, no começo de
cada trimestre (pontos_de_agora).
"""
import html
import json
import logging
import math
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
# Punições sem recurso com o texto na tela Saúde da Shopee Vídeo (cabe na mensagem do Telegram).
PENDENTES_NA_TELA = 5
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
# A tabela oficial (Central de Ajuda do Afiliado, "Acompanhe a Saúde da conta e os indicadores
# de seus vídeos", lida em 03/11/2026): a partir de quantos pontos, quantos dias sem postar
# (None = para sempre). Os pontos zeram no começo de cada trimestre (MESES_DO_TRIMESTRE).
BANIMENTOS = ((15, None), (12, 30), (9, 7), (6, 3))
MESES_DO_TRIMESTRE = (1, 4, 7, 10)
# A escada dos posts por dia pelos pontos (P144 e P145, escolhas do Rafael em 03/11/2026):
# de 0 a 3 pontos, a faixa do painel; acima, (a partir de quantos pontos, a parte da faixa do
# painel, o teto por dia). A parte é sempre da faixa que o Rafael pôs no painel, não do teto do
# degrau anterior: de 4 a 5, a metade; de 6 a 8, a metade da metade. Sem parte, a faixa inteira
# até o teto; teto 0, nenhum post até os pontos zerarem. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
ESCADA_DOS_PONTOS = ((12, None, 0), (9, None, 2), (6, 0.25, 6), (4, 0.5, 8))
NOMES_DAS_PARTES = {0.5: "metade da sua faixa", 0.25: "um quarto da sua faixa"}
# Com estes pontos ou mais, só o produto do vídeo vai ao post: sem os produtos a mais (P145).
PONTOS_SO_O_PRODUTO_DO_VIDEO = 4
# Onde o robô guarda a última leitura da Saúde do Vídeo (saude_pontos e saude_lida_em): a
# CHAVE_ESTADO do robo_shopee_video, lida aqui também pelo modo assistente, que não importa o robô.
CHAVE_DA_SAUDE = "shopee_video_robo"
# Fontes que são vídeos do próprio Rafael: só nelas o texto pode dizer que o vídeo é dele.
FONTES_PROPRIAS = ("autorais",)
CALLBACK_RECORRI, CALLBACK_NAO_VAI = "apel_ok:", "apel_nao:"


def _momento(agora=None):
    return (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d %H:%M:%S")


# --- Os pontos e a escada dos posts por dia ---

def inicio_do_trimestre(agora=None):
    """O começo do trimestre de agora: a Shopee zera os pontos no 1º de janeiro, abril, julho e outubro."""
    agora = agora or datetime.now(fuso_horario)
    mes = max(m for m in MESES_DO_TRIMESTRE if m <= agora.month)
    return agora.replace(month=mes, day=1, hour=0, minute=0, second=0, microsecond=0)


def quando_zeram(agora=None):
    """O dia em que os pontos zeram de novo ("01/01"): o começo do trimestre seguinte."""
    mes = inicio_do_trimestre(agora).month + 3
    return f"01/{(mes - 1) % 12 + 1:02d}"


def pontos_de_agora(estado=None, agora=None):
    """
    Os pontos de penalidade da última leitura da Saúde do Vídeo (estado: o do robô; sem ele, lido
    do banco). Sem leitura, 0; a leitura de antes do começo do trimestre também vale 0, porque
    a Shopee zera os pontos nesse dia.
    """
    estado = (db.ler_config(CHAVE_DA_SAUDE, {}) or {}) if estado is None else estado
    lida = str(estado.get("saude_lida_em") or "")
    try:
        pontos = max(0, int(estado.get("saude_pontos")))
    except (TypeError, ValueError):
        return 0
    if lida[:10] < inicio_do_trimestre(agora).strftime("%Y-%m-%d"):
        return 0
    return pontos


def degrau_dos_pontos(pontos):
    """O degrau da escada para estes pontos, (a partir de, parte da faixa, teto), ou None (a faixa do painel)."""
    for degrau in ESCADA_DOS_PONTOS:
        if pontos >= degrau[0]:
            return degrau
    return None


def faixa_pelos_pontos(piso, topo, pontos):
    """
    A faixa de posts por dia pelos pontos: (piso, topo, teto). Até 3 pontos, a do painel, sem teto
    (None); acima, a parte dela que o degrau diz (arredondada para cima, pelo menos 1), e o que passa
    do teto vira o teto: a faixa vai do mínimo até o teto, e o sorteio do dia corre nela inteira
    (pedido do Rafael, 03/11: "sempre pensando na faixa"). Mínimo acima do teto, só o teto.
    """
    degrau = degrau_dos_pontos(pontos)
    if not degrau:
        return piso, topo, None
    _a_partir, parte, teto = degrau
    if parte:
        piso, topo = (max(1, math.ceil(n * parte)) if n else n for n in (piso, topo))
    if teto:
        piso, topo = (min(n, teto) if n else n for n in (piso, topo))
    return piso, topo, teto


def quantos_pelos_pontos(semente, dia, piso, topo, pontos):
    """Quantos posts o dia faz: o sorteio de sempre, na faixa pelos pontos (já limitada pelo teto)."""
    from motor_filas import sortear_teto_do_dia
    piso, topo, teto = faixa_pelos_pontos(piso, topo, pontos)
    if teto == 0:
        return 0
    return sortear_teto_do_dia(semente, dia, piso, topo)


def rotulo_dos_pontos(pontos, agora=None, piso=None, topo=None):
    """
    A linha dos painéis com o porquê da faixa menor ("" de 0 a 3 pontos): os pontos, o degrau, a
    faixa que fica com a faixa do painel (piso e topo, quando vêm) e quando os pontos zeram.
    """
    degrau = degrau_dos_pontos(pontos)
    if not degrau:
        return ""
    zeram = quando_zeram(agora)
    if degrau[2] == 0:
        return (f"⛔ Pelos pontos de penalidade (<b>{pontos}</b>): nenhum post até os pontos baixarem "
                f"(recurso aceito) ou zerarem em <b>{zeram}</b>")
    parte = f"{NOMES_DAS_PARTES[degrau[1]]}, " if degrau[1] else ""
    fica = ""
    if piso:
        de, ate, _teto = faixa_pelos_pontos(piso, topo, pontos)
        fica = f" (fica <b>{de} a {ate}</b>)" if ate and ate > de else f" (fica <b>{de}</b>)"
    return (f"⚠️ Pelos pontos de penalidade (<b>{pontos}</b>): {parte}até <b>{degrau[2]} por dia</b>{fica}, só "
            f"com o produto do vídeo, até os pontos baixarem (recurso aceito) ou zerarem em <b>{zeram}</b>")


def aviso_acima_do_teto(feitos, teto, pontos, oque="rascunhos"):
    """
    O aviso do Preparar 1 Agora e do Postar Agora quando o dia já chegou ao teto pelos pontos
    (o botão continua valendo: é pedido do Rafael). "" sem teto ou abaixo dele.
    """
    if pontos < PONTOS_SO_O_PRODUTO_DO_VIDEO or feitos < teto:
        return ""
    return (f"\n\n⚠️ Hoje já foram <b>{feitos}</b> {oque}, e o teto pelos pontos de penalidade ({pontos}) é "
            f"<b>{teto}</b> por dia: este passa do teto.")


def nota_dos_pontos(pontos):
    """O que estes pontos querem dizer, pela tabela oficial: a restrição e o próximo degrau."""
    for minimo, dias in BANIMENTOS:
        if pontos >= minimo:
            atual = "banimento para sempre" if dias is None else f"cada alerta novo, {dias} dias sem postar"
            break
    else:
        atual = "nenhuma restrição"
    proximo = next(((m, d) for m, d in sorted(BANIMENTOS) if m > pontos), None)
    if not proximo:
        return atual
    m, d = proximo
    return f"{atual}; com {m}, " + ("banimento para sempre" if d is None else f"{d} dias sem postar")


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

def texto_para_copiar(p):
    """
    O texto do recurso da punição: o guardado (sem a frase que pede a revisão, que os textos de
    antes traziam) ou, na de propriedade intelectual de vídeo de outro canal guardada sem texto,
    o texto sem autoria pelo título (P31).
    """
    if p.get("texto"):
        return sem_pedido_de_revisao(p["texto"])
    if not so_com_autoria_verdadeira(p.get("tipo"), p.get("fonte")):
        return texto_sem_autoria(titulo=p.get("titulo") or "")
    return ""


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
    texto = texto_para_copiar(p)
    if texto:
        linhas += ["", f"👇 Toque no texto para copiar ({len(texto)} de {TAMANHO_DO_TEXTO} caracteres):",
                   f"<code>{html.escape(texto)}</code>"]
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
- Use o espaço para os fatos que mostram que o vídeo cumpre a regra da punição: o que o vídeo mostra, o produto anexado e para que ele serve.
- Não peça a revisão nem a reconsideração e não agradeça: o recurso já é o pedido, e cada caractere vale mais com um fato.
- Se o nome do produto puder ser confundido com outra coisa (ex.: "botijão térmico" com botijão de gás), deixe claro o que o produto é.
- Escreva com a acentuação e a ortografia corretas do português, também no nome do produto, que pode vir sem acento.
- Sem hashtags, emojis, aspas ou link. Devolva só o texto.

Punição: {tipo}
Explicação da Shopee: {explicacao}
Título do vídeo: {titulo}
Produto anexado ao vídeo: {produtos}
O que a IA viu no vídeo antes de postar: {conferencia}
De onde veio o vídeo: {origem}
"""


# A frase que pede a revisão (ou agradece) só gasta os 200 caracteres do campo: quem recorre já
# está pedindo a revisão. Pedido do Rafael (03/11): DECISOES.md, Shopee Vídeo.
PEDIDO_DE_REVISAO = re.compile(r"(revis[aã]o|revisar|revisem|reconsider|reavalia|rean[aá]lise|solicit|\bpe[çc]o\b|"
                               r"\bpedimos\b|\baguardo\b|\bgostaria\b|agrade[çc]o|obrigad[oa])", re.IGNORECASE)


def sem_pedido_de_revisao(texto):
    """
    O texto sem as frases que pedem a revisão da punição ou agradecem. Sem nenhuma frase de
    fato, o texto volta como veio (melhor um texto que nenhum).
    """
    frases = [f for f in re.split(r"(?<=[.!?])\s+", " ".join(str(texto or "").split())) if f]
    fatos = [f for f in frases if not PEDIDO_DE_REVISAO.search(f)]
    return " ".join(fatos) if fatos else " ".join(frases)


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
TEXTO_SEM_AUTORIA = "Sou afiliado da Shopee. Este vídeo divulga {produto}, vendido na própria Shopee e anexado ao vídeo."


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
    # A resposta que pede a revisão vai de novo à IA; na última, sai só a frase do pedido.
    respostas = []
    for _ in range(tentativas):
        resposta = await api_gemini.gerar_texto_gemini(prompt)
        texto = " ".join(str(resposta or "").replace('"', "").split())
        if texto and len(texto) <= TAMANHO_DO_TEXTO and not PEDIDO_DE_REVISAO.search(texto):
            return texto, ""
        if texto:
            respostas.append(sem_pedido_de_revisao(texto))
    for texto in respostas:
        if len(texto) <= TAMANHO_DO_TEXTO:
            return texto, ""
    if respostas:
        return _encurtar(respostas[0]), ""
    return "", "A IA não respondeu agora: toque em Gerar Apelação ⚖️ (Relatório Geral 📊 → Saúde da Shopee Vídeo 🩺) para tentar de novo."


# --- A tela Saúde da Shopee Vídeo ---

# --- Quais posts levam punição (P146 2) ---
# Cada punição que o robô lê na Saúde do Vídeo fica ligada ao post dele que a levou (coluna
# rascunho, pelo rascunho_do_post do robô); aqui ela é cruzada com o que o post tinha, para o
# Rafael decidir com números o que desligar. Só conta: nada muda no robô. Pedido do Rafael
# (P146 2): DECISOES.md, Shopee Vídeo.

def _lista(valor):
    """A coluna em JSON do rascunho como lista (vazia quando não há)."""
    try:
        lido = json.loads(valor) if valor else []
    except (TypeError, ValueError):
        return []
    return lido if isinstance(lido, list) else []


CARACTERISTICAS_DO_POST = ("produtos a mais", "troca de loja", "outra foto de capa", "outra cor",
                           "chamada na capa", "rótulo de IA", "Ver Produtos")


def _tem(nome, r):
    """
    O post (rascunho postado) tem a característica? None = o rascunho não anotou (a troca de
    loja é anotada desde 03/11 nos de link de produto e desde 05/11 nos de Ver Produtos): fica fora
    da conta dessa linha.
    """
    if nome == "produtos a mais":
        return any(isinstance(i, dict) and i.get("a_mais") for i in _lista(r["itens"]))
    if nome == "troca de loja":
        return {"1": True, "0": False}.get(r["trocado"])
    if nome == "outra foto de capa":
        return bool(_lista(r["outras_capas"]))
    if nome == "outra cor":
        return bool(_lista(r["outra_cor"]))
    if nome == "chamada na capa":
        return r["chamada"] == "1"
    if nome == "rótulo de IA":
        return bool(r["rotulo_ia"])
    return bool(_lista(r["links_dos_produtos"]))  # Ver Produtos
_COLUNAS_DO_POST = ("id", "postado_em", "fonte", "itens", "trocado", "outras_capas", "outra_cor", "chamada",
                    "rotulo_ia", "links_dos_produtos")


def punicoes_por_tipo_de_post():
    """
    Os posts do robô e quais levaram punição, por característica e por fonte:
    {"posts", "punidos", "fora_do_robo", "desde", "caracteristicas": [(nome, com, com_punidos,
    sem, sem_punidos)], "fontes": [(fonte, posts, punidos)], "tipos": [(tipo, quantas)]}.
    fora_do_robo: as punições de vídeo que não é post do robô (ou que o robô não achou).
    """
    with db.conexao(linhas_por_nome=True) as con:
        _criar_tabela(con)
        punicoes = con.execute("SELECT tipo, rascunho, titulo, postado_em FROM shopee_video_punicoes").fetchall()
        tem_rascunhos = con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                                    "AND name = 'shopee_video_rascunhos'").fetchone()
        existentes = {linha[1] for linha in con.execute("PRAGMA table_info(shopee_video_rascunhos)")} \
            if tem_rascunhos else set()
        colunas = [c if c in existentes else f"NULL AS {c}" for c in _COLUNAS_DO_POST]
        posts = con.execute(f"SELECT {', '.join(colunas)} FROM shopee_video_rascunhos WHERE estado = 'postado' "
                            "ORDER BY postado_em").fetchall() if tem_rascunhos else []
    ids = {r["id"] for r in posts}
    punidos = {p["rascunho"] for p in punicoes if p["rascunho"] in ids}
    caracteristicas = []
    for nome in CARACTERISTICAS_DO_POST:
        contas = {True: [0, 0], False: [0, 0]}
        for r in posts:
            valor = _tem(nome, r)
            if valor is None:
                continue
            contas[bool(valor)][0] += 1
            contas[bool(valor)][1] += r["id"] in punidos
        caracteristicas.append((nome, *contas[True], *contas[False]))
    fontes = {}
    for r in posts:
        conta = fontes.setdefault(r["fonte"] or "?", [0, 0])
        conta[0] += 1
        conta[1] += r["id"] in punidos
    tipos = {}
    for p in punicoes:
        tipos[p["tipo"] or "?"] = tipos.get(p["tipo"] or "?", 0) + 1
    # Sem post do robô ligado: a punição que o robô achou já recorrida no app, ou já conhecida,
    # fica guardada sem ele abrir a tela do vídeo (sem título nem hora do post); as outras ele leu
    # e o vídeo não casou com nenhum post dele (outro vídeo da conta, como os do modo assistente).
    fora = [p for p in punicoes if p["rascunho"] not in ids]
    return {"posts": len(posts), "punidos": len(punidos), "fora_do_robo": len(fora),
            "fora_sem_a_tela": sum(1 for p in fora if not (p["titulo"] or p["postado_em"])),
            "desde": (posts[0]["postado_em"] or "")[:10] if posts else "",
            "caracteristicas": caracteristicas, "fontes": sorted((f, *c) for f, c in fontes.items()),
            "tipos": sorted(tipos.items(), key=lambda par: (-par[1], par[0]))}


def _parte(punidos, posts):
    return f"{punidos} de {posts} ({round(punidos * 100 / posts)}%)" if posts else "nenhum post"


def linhas_das_punicoes_por_post(medicao):
    """As linhas da Saúde da Shopee Vídeo com a medição (só as características que algum post teve)."""
    if not medicao["posts"]:
        return []
    desde = medicao["desde"]
    linhas = ["", f"<b>Quais posts levaram punição</b> ({medicao['posts']} posts do robô desde "
                  f"{desde[8:10]}/{desde[5:7]}; {medicao['punidos']} punidos)"]
    for nome, com, com_punidos, sem, sem_punidos in medicao["caracteristicas"]:
        if com:
            nota = " (anotada desde 03/11)" if nome == "troca de loja" else ""
            linhas.append(f"• Com {nome}: {_parte(com_punidos, com)} · sem: {_parte(sem_punidos, sem)}{nota}")
    if medicao["fontes"]:
        linhas.append("• Por fonte: " + " · ".join(f"{html.escape(fonte)} {_parte(punidos, posts)}"
                                                   for fonte, posts, punidos in medicao["fontes"]))
    if medicao["fora_do_robo"]:
        sem_a_tela = medicao.get("fora_sem_a_tela", 0)
        linhas.append(f"• Punições sem post do robô ligado: {medicao['fora_do_robo']} (de {sem_a_tela}, o robô não leu "
                      "a tela do vídeo, porque já estavam recorridas ou são de antes da leitura; as outras são de "
                      "vídeos que não são posts do robô)")
    linhas.append("<i>Só mostra os números; desligar alguma coisa continua com você.</i>")
    return linhas


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
        linhas.append(f"⚠️ Pontos de penalidade: <b>{pontos}</b> ({nota_dos_pontos(pontos)}; zeram em "
                      f"{quando_zeram(agora)}; recurso aceito tira pontos)")
        escada = rotulo_dos_pontos(pontos_de_agora(estado_robo, agora), agora)
        if escada:
            linhas.append(escada)
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
    # O texto de cada punição ainda sem recurso, também aqui, para copiar a qualquer hora (pedido
    # do Rafael, 25/10: "onde que eu posso ver?").
    pendentes = [p for p in recentes if p["situacao"] == PENDENTE][:PENDENTES_NA_TELA]
    if pendentes:
        linhas += ["", "<b>Para recorrer</b> (toque no texto para copiar):"]
        for p in pendentes:
            texto = texto_para_copiar(p)
            linhas.append(f"🎬 {html.escape((p['titulo'] or p['tipo'])[:80])}")
            linhas.append(f"<code>{html.escape(texto)}</code>" if texto else
                          "   sem texto ainda: toque em Gerar Apelação ⚖️")
        linhas.append("📲 No app: Notificações (ou Eu → Criadores &amp; Afiliados → Saúde do Vídeo) → o vídeo → "
                      "<b>Apelar aqui</b> → cole em Razão para apelar → <b>Enviar</b>. Depois toque em "
                      "<b>✅ Já recorri</b> no aviso do privado, para os lembretes pararem.")
    linhas += linhas_das_punicoes_por_post(punicoes_por_tipo_de_post())
    linhas += ["", "<b>O que o botão faz</b>",
               "⚖️ <b>Gerar Apelação</b>: o robô olha agora a Saúde do Vídeo no Motorola e manda aqui o texto "
               "pronto de cada punição ainda não recorrida, com os botões Já recorri e Não vou recorrer. Ele "
               "também olha sozinho uma vez por dia."]
    return "\n".join(linhas)


def ler_explicacao(texto):
    """A explicação da Shopee, sem espaços repetidos e sem o "Apelar aqui." do fim."""
    return re.sub(r"\s*Apelar aqui\.?\s*$", "", " ".join(str(texto or "").split()))

