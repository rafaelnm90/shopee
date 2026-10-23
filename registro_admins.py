"""
Registro dos administradores dos grupos e canais do Rafael: quem é admin, com que
permissões e em quais grupos. A conta principal (divulgacao_canal) confere uma vez por
dia, de madrugada, todos os grupos e canais em que é dona ou administradora, e grava a
foto atual e o que mudou desde a anterior. O bot_mestre mostra o registro (painel_admins:
Opções do Servidor → Administradores 🛡️) e avisa no privado quando algo muda.

Nomes e @ de pessoas ficam só no banco e no privado do Rafael: nada vai para o git
(repositório público) nem para o log. Decisão do Rafael: DECISOES.md, Monitor, deploy e servidor.
"""
import asyncio
import html
import json
import logging
from datetime import datetime, timedelta

import db
import registro_processos

logger = logging.getLogger("Registro_Admins")

CHAVE_RESUMO = "registro_admins"
HORA_CONFERENCIA = (4, 20)          # depois do backup das 03:40
IDADE_PARA_CONFERIR_AO_SUBIR = timedelta(hours=20)

# As permissões de admin do Telegram, na ordem e com os nomes da tela do app.
PERMISSOES = (
    ("change_info", "alterar dados"),
    ("post_messages", "postar mensagens"),
    ("edit_messages", "editar mensagens de outros"),
    ("delete_messages", "apagar mensagens de outros"),
    ("ban_users", "banir usuários"),
    ("invite_users", "convidar via link"),
    ("pin_messages", "fixar mensagens"),
    ("manage_topics", "gerenciar tópicos"),
    ("manage_call", "transmissões ao vivo"),
    ("post_stories", "postar stories"),
    ("edit_stories", "editar stories de outros"),
    ("delete_stories", "apagar stories de outros"),
    ("add_admins", "adicionar admins"),
    ("anonymous", "anônimo"),
)
NOME_PERMISSAO = dict(PERMISSOES)


def inicializar_tabelas():
    with db.conexao() as conexao:
        conexao.execute("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
        conexao.execute(
            "CREATE TABLE IF NOT EXISTS admins_grupos ("
            "chat_id TEXT, chat_nome TEXT, tipo TEXT, user_id INTEGER, nome TEXT, usuario TEXT, "
            "bot INTEGER, papel TEXT, titulo TEXT, permissoes TEXT, promovido_por INTEGER, "
            "PRIMARY KEY (chat_id, user_id))")
        conexao.execute(
            "CREATE TABLE IF NOT EXISTS admins_mudancas ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, quando TEXT, chat_id TEXT, chat_nome TEXT, "
            "nome TEXT, mudanca TEXT, avisado INTEGER DEFAULT 0)")


# --- Coleta (conta principal, no divulgacao_canal) ---

def _nome_da_pessoa(usuario):
    if getattr(usuario, "deleted", False):
        return "Conta apagada"
    nome = " ".join(p for p in (getattr(usuario, "first_name", None), getattr(usuario, "last_name", None)) if p)
    return nome or "Sem nome"


def _admin_do_participante(usuario):
    """O admin como dicionário, ou None se o participante não é admin nem dono."""
    participante = getattr(usuario, "participant", None)
    tipo = type(participante).__name__
    if tipo in ("ChannelParticipantCreator", "ChatParticipantCreator"):
        papel = "dono"
    elif tipo in ("ChannelParticipantAdmin", "ChatParticipantAdmin"):
        papel = "admin"
    else:
        return None
    direitos = getattr(participante, "admin_rights", None)
    # Grupo básico não tem permissões separadas: o admin pode tudo o que admin pode.
    permissoes = ([chave for chave, _ in PERMISSOES if getattr(direitos, chave, False)]
                  if direitos is not None else [chave for chave, _ in PERMISSOES if chave != "anonymous"])
    return {
        "user_id": usuario.id, "nome": _nome_da_pessoa(usuario),
        "usuario": getattr(usuario, "username", None) or "", "bot": bool(getattr(usuario, "bot", False)),
        "papel": papel, "titulo": getattr(participante, "rank", None) or "",
        "permissoes": permissoes, "promovido_por": getattr(participante, "promoted_by", None),
    }


async def coletar(client):
    """Os grupos e canais em que a conta é dona ou admin, cada um com os seus admins."""
    from telethon.tl.types import ChannelParticipantsAdmins
    grupos = []
    async for dialogo in client.iter_dialogs():
        if not (dialogo.is_group or dialogo.is_channel):
            continue
        entidade = dialogo.entity
        if getattr(entidade, "left", False) or getattr(entidade, "deactivated", False):
            continue
        if not (getattr(entidade, "creator", False) or getattr(entidade, "admin_rights", None)):
            continue
        admins = []
        try:
            async for usuario in client.iter_participants(entidade, filter=ChannelParticipantsAdmins):
                admin = _admin_do_participante(usuario)
                if admin:
                    admins.append(admin)
        except Exception as e:
            logger.warning(f"⚠️ [Admins] Não consegui ler os admins de um grupo: {type(e).__name__}.")
            continue
        grupos.append({"chat_id": str(dialogo.id), "nome": getattr(entidade, "title", "") or str(dialogo.id),
                       "tipo": "canal" if getattr(entidade, "broadcast", False) else "grupo", "admins": admins})
    return grupos


# --- Foto atual e mudanças ---

def _foto_atual():
    with db.conexao(linhas_por_nome=True) as conexao:
        linhas = conexao.execute("SELECT * FROM admins_grupos").fetchall()
    grupos = {}
    for linha in linhas:
        grupo = grupos.setdefault(linha["chat_id"], {"chat_id": linha["chat_id"], "nome": linha["chat_nome"],
                                                     "tipo": linha["tipo"], "admins": []})
        grupo["admins"].append({
            "user_id": linha["user_id"], "nome": linha["nome"], "usuario": linha["usuario"], "bot": bool(linha["bot"]),
            "papel": linha["papel"], "titulo": linha["titulo"], "permissoes": json.loads(linha["permissoes"] or "[]"),
            "promovido_por": linha["promovido_por"]})
    return grupos


def _lista(chaves):
    return ", ".join(NOME_PERMISSAO.get(c, c) for c in chaves)


def comparar(antes, depois):
    """[(chat_id, chat_nome, nome, mudança)] entre duas fotos {chat_id: grupo}."""
    mudancas = []
    for chat_id, grupo in depois.items():
        anterior = antes.get(chat_id)
        if anterior is None:
            mudancas.append((chat_id, grupo["nome"], "", f"entrou no registro com {len(grupo['admins'])} admin(s)"))
            continue
        velhos = {a["user_id"]: a for a in anterior["admins"]}
        novos = {a["user_id"]: a for a in grupo["admins"]}
        for user_id, admin in novos.items():
            velho = velhos.get(user_id)
            if velho is None:
                mudancas.append((chat_id, grupo["nome"], admin["nome"], f"virou {admin['papel']}"))
                continue
            if velho["papel"] != admin["papel"]:
                mudancas.append((chat_id, grupo["nome"], admin["nome"], f"passou de {velho['papel']} a {admin['papel']}"))
            ganhou = [c for c in admin["permissoes"] if c not in velho["permissoes"]]
            perdeu = [c for c in velho["permissoes"] if c not in admin["permissoes"]]
            if ganhou or perdeu:
                partes = ([f"ganhou: {_lista(ganhou)}"] if ganhou else []) + ([f"perdeu: {_lista(perdeu)}"] if perdeu else [])
                mudancas.append((chat_id, grupo["nome"], admin["nome"], "permissões mudaram (" + "; ".join(partes) + ")"))
        for user_id, velho in velhos.items():
            if user_id not in novos:
                mudancas.append((chat_id, grupo["nome"], velho["nome"], "deixou de ser admin"))
    for chat_id, anterior in antes.items():
        if chat_id not in depois:
            mudancas.append((chat_id, anterior["nome"], "",
                             "saiu do registro (a sua conta deixou de ser dona ou admin, ou saiu dele)"))
    return mudancas


def gravar(grupos, agora=None):
    """Troca a foto pela nova e registra o que mudou. Na primeira vez, só a foto. Devolve as mudanças."""
    agora = agora or datetime.now()
    inicializar_tabelas()
    antes = _foto_atual()
    depois = {g["chat_id"]: g for g in grupos}
    mudancas = comparar(antes, depois) if antes else []
    quando = agora.strftime("%Y-%m-%d %H:%M:%S")
    with db.conexao() as conexao:
        conexao.execute("DELETE FROM admins_grupos")
        for grupo in grupos:
            for a in grupo["admins"]:
                conexao.execute(
                    "INSERT OR REPLACE INTO admins_grupos (chat_id, chat_nome, tipo, user_id, nome, usuario, bot, "
                    "papel, titulo, permissoes, promovido_por) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (grupo["chat_id"], grupo["nome"], grupo["tipo"], a["user_id"], a["nome"], a["usuario"],
                     int(a["bot"]), a["papel"], a["titulo"], json.dumps(a["permissoes"]), a["promovido_por"]))
        conexao.executemany(
            "INSERT INTO admins_mudancas (quando, chat_id, chat_nome, nome, mudanca) VALUES (?, ?, ?, ?, ?)",
            [(quando, chat_id, chat_nome, nome, mudanca) for chat_id, chat_nome, nome, mudanca in mudancas])
    db.salvar_config(CHAVE_RESUMO, {"ultima": quando, "grupos": len(grupos),
                                    "admins": sum(len(g["admins"]) for g in grupos)})
    return mudancas


@registro_processos.anotar("divulgacao", "registro dos administradores")
async def conferir(client):
    """Coleta e grava. O log leva só números: nomes de pessoas não vão para o log."""
    try:
        grupos = await coletar(client)
        mudancas = gravar(grupos)
        logger.info(f"🛡️ [Admins] {len(grupos)} grupo(s) e canal(is) conferidos; {len(mudancas)} mudança(s).")
    except Exception as e:
        logger.error(f"❌ [Admins] Conferência falhou: {type(e).__name__}: {e}")


async def conferir_se_atrasado(client, espera_s=90):
    """Ao subir: confere já se a última conferência tem mais de 20 h (ou nunca houve)."""
    await asyncio.sleep(espera_s)
    inicializar_tabelas()
    ultima = (db.ler_config(CHAVE_RESUMO, {}) or {}).get("ultima")
    try:
        atrasada = not ultima or datetime.now() - datetime.strptime(ultima, "%Y-%m-%d %H:%M:%S") > IDADE_PARA_CONFERIR_AO_SUBIR
    except ValueError:
        atrasada = True
    if atrasada:
        await conferir(client)


# --- Leitura (bot_mestre) ---

def mudancas_nao_avisadas():
    inicializar_tabelas()
    with db.conexao(linhas_por_nome=True) as conexao:
        return [dict(l) for l in conexao.execute("SELECT * FROM admins_mudancas WHERE avisado = 0 ORDER BY id")]


def marcar_avisadas(ids):
    with db.conexao() as conexao:
        conexao.executemany("UPDATE admins_mudancas SET avisado = 1 WHERE id = ?", [(i,) for i in ids])


def ultimas_mudancas(quantas=10):
    inicializar_tabelas()
    with db.conexao(linhas_por_nome=True) as conexao:
        return [dict(l) for l in conexao.execute(
            "SELECT * FROM admins_mudancas ORDER BY id DESC LIMIT ?", (quantas,))]


def linha_mudanca(m, nome_do_grupo=None):
    """Uma mudança em HTML: grupo, pessoa e o que mudou."""
    grupo = nome_do_grupo(m["chat_nome"], m["chat_id"]) if nome_do_grupo else html.escape(m["chat_nome"] or "")
    quem = f"<b>{html.escape(m['nome'])}</b> " if m.get("nome") else ""
    return f"• {grupo}: {quem}{html.escape(m['mudanca'])}"


def linha_admin(admin, nomes_por_id):
    """Uma linha do painel: quem é, o papel e o que pode."""
    icone = "👑" if admin["papel"] == "dono" else ("🤖" if admin["bot"] else "👤")
    quem = html.escape(admin["nome"]) + (f" (@{html.escape(admin['usuario'])})" if admin["usuario"] else "")
    if admin["papel"] == "dono":
        pode = "dono, pode tudo"
    elif not admin["permissoes"]:
        pode = "nenhuma permissão"
    else:
        pode = _lista(admin["permissoes"])
    extra = f" · título \"{html.escape(admin['titulo'])}\"" if admin.get("titulo") else ""
    if admin.get("promovido_por") and admin["promovido_por"] in nomes_por_id:
        extra += f" · promovido por {html.escape(nomes_por_id[admin['promovido_por']])}"
    return f"{icone} {quem}: {pode}{extra}"


def textos_do_painel(nome_do_grupo=None, limite=3800):
    """As mensagens do painel: o resumo, um bloco por grupo e as últimas mudanças, cada mensagem até o limite."""
    inicializar_tabelas()
    resumo = db.ler_config(CHAVE_RESUMO, {}) or {}
    if not resumo.get("ultima"):
        return ["🛡️ <b>Administradores</b>\n\nA primeira conferência ainda não rodou. Ela roda sozinha "
                "pouco depois de o robô de divulgação ligar e, depois, todo dia às 04:20."]
    quando = datetime.strptime(resumo["ultima"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m às %H:%M")
    cabecalho = (f"🛡️ <b>Administradores</b>\nConferido em {quando}: {resumo.get('grupos', 0)} grupo(s) e canal(is) "
                 f"em que você é dono ou admin, {resumo.get('admins', 0)} administradores no total.")
    blocos = []
    for grupo in sorted(_foto_atual().values(), key=lambda g: (g["tipo"], g["nome"].lower())):
        nomes = {a["user_id"]: a["nome"] for a in grupo["admins"]}
        titulo = nome_do_grupo(grupo["nome"], grupo["chat_id"]) if nome_do_grupo else html.escape(grupo["nome"])
        icone = "📢" if grupo["tipo"] == "canal" else "👥"
        ordem = sorted(grupo["admins"], key=lambda a: (a["papel"] != "dono", a["bot"], a["nome"].lower()))
        blocos.append(f"{icone} <b>{titulo}</b>\n" + "\n".join(linha_admin(a, nomes) for a in ordem))
    mudancas = ultimas_mudancas()
    if mudancas:
        blocos.append("🕓 <b>Últimas mudanças</b>\n" + "\n".join(
            f"<code>{m['quando'][8:10]}/{m['quando'][5:7]}</code> " + linha_mudanca(m, nome_do_grupo)[2:]
            for m in mudancas))
    mensagens, atual = [], cabecalho
    for bloco in blocos:
        if len(atual) + len(bloco) + 2 > limite:
            mensagens.append(atual)
            atual = bloco
        else:
            atual += "\n\n" + bloco
    mensagens.append(atual)
    return mensagens
