"""
Atalho para abrir no Telegram um grupo ou canal citado nos painéis: o nome vira link.
Os painéis do bot_mestre e do Espelhador mostram (nome_clicavel); os userbots
(motor_userbot, divulgacao_canal e espelhador_videos_autorais) guardam, ao ler as
conversas da conta, o que o Telegram diz de cada grupo (tabela links_grupos).

O link, do melhor para o pior:
- o @ do grupo (o alvo já é @, ou o Telegram contou o @ de um grupo salvo pelo
  número): t.me/<usuário>, abre para qualquer um;
- o link de convite de um grupo comum em que a conta é admin;
- supergrupo ou canal privado (-100...): t.me/c/<número>/<última mensagem>, abre para
  quem é membro (o Telegram não tem link de grupo privado sem uma mensagem);
- grupo comum (número sem -100) sem convite: sem link. O Telegram não dá @ a esse tipo
  de grupo.
Com tópico ("-100...:5" ou "-100..._5"), o link abre o tópico.
Decisão do Rafael: DECISOES.md, Código e manutenção.
"""
import html
import logging
import os
import re
import time
from datetime import datetime

import db

logger = logging.getLogger("Links_Grupos")

_USUARIO = re.compile(r"^(?:https?://)?(?:t\.me/|@)([A-Za-z][A-Za-z0-9_]{3,})(?:[/?].*)?$")
_NUMERO = re.compile(r"^(-?\d+)(?:[:_](\d+))?$")


def _garantir_tabela(con):
    con.execute("CREATE TABLE IF NOT EXISTS links_grupos (chat_id TEXT PRIMARY KEY, usuario TEXT, "
                "convite TEXT, ultima_msg INTEGER, atualizado TEXT)")


def ler_todos():
    """{chat_id: {"usuario", "convite", "ultima_msg"}} de todos os grupos guardados."""
    try:
        with db.conexao() as con:
            _garantir_tabela(con)
            linhas = con.execute("SELECT chat_id, usuario, convite, ultima_msg FROM links_grupos").fetchall()
    except Exception as e:
        logger.warning(f"⚠️ [Links] Não consegui ler os links dos grupos: {type(e).__name__}")
        return {}
    return {chat_id: {"usuario": usuario, "convite": convite, "ultima_msg": ultima}
            for chat_id, usuario, convite, ultima in linhas}


def guardar(chat_id, usuario, convite=None):
    """
    Guarda o que o Telegram disse de um grupo: o @ (None = sem @) e, se veio, o link de
    convite. Usado quando o bot ou o auditor dos userbots confere um grupo.
    """
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with db.conexao() as con:
            _garantir_tabela(con)
            con.execute("INSERT INTO links_grupos (chat_id, usuario, convite, atualizado) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(chat_id) DO UPDATE SET usuario = excluded.usuario, "
                        "convite = COALESCE(excluded.convite, links_grupos.convite), "
                        "atualizado = excluded.atualizado",
                        (str(chat_id), usuario or None, convite or None, agora))
    except Exception as e:
        logger.warning(f"⚠️ [Links] Não consegui guardar o link de um grupo: {type(e).__name__}")


def guardar_entidade(entidade):
    """O guardar() de um grupo ou canal do Telethon (o auditor dos userbots)."""
    if entidade is None or not getattr(entidade, "title", None):
        return
    try:
        guardar(_chat_id(entidade), _usuario_da_entidade(entidade))
    except Exception as e:
        logger.warning(f"⚠️ [Links] Não consegui guardar o link de um grupo: {type(e).__name__}")


# Os painéis montam listas de dezenas de grupos: a tabela é lida no máximo a cada 30 s
# (de novo também se o banco for outro, como nos testes, que usam um banco por teste).
_recentes = {"lido_em": 0.0, "banco": None, "dados": {}}


def _guardados_recentes():
    agora = time.monotonic()
    banco = os.path.abspath(db.ARQUIVO_BANCO)
    if agora - _recentes["lido_em"] > 30 or _recentes["banco"] != banco:
        _recentes["dados"] = ler_todos()
        _recentes["lido_em"] = agora
        _recentes["banco"] = banco
    return _recentes["dados"]


def link(alvo, guardados=None):
    """
    O link que abre o grupo ou canal alvo (como os painéis o guardam: "@canal",
    "-100123", "-100123:5", "-5232187113"), ou None se o Telegram não tiver um.
    guardados é o ler_todos(); sem ele, usa a leitura dos últimos 30 s.
    """
    texto = str(alvo or "").strip()
    if re.match(r"^(?:https?://)?t\.me/(?:\+|joinchat/)", texto):
        return texto if texto.startswith("http") else f"https://{texto}"
    usuario = _USUARIO.match(texto)
    if usuario:
        return f"https://t.me/{usuario.group(1)}"
    numero = _NUMERO.match(texto)
    if not numero:
        return None
    chat_id, topico = numero.group(1), numero.group(2)
    if guardados is None:
        guardados = _guardados_recentes()
    info = guardados.get(chat_id) or {}
    privado = chat_id.startswith("-100")
    if info.get("usuario"):
        return f"https://t.me/{info['usuario']}" + (f"/{topico}" if topico else "")
    if privado and topico:
        return f"https://t.me/c/{chat_id[4:]}/{topico}"
    if info.get("convite"):
        return info["convite"]
    if privado and info.get("ultima_msg"):
        return f"https://t.me/c/{chat_id[4:]}/{info['ultima_msg']}"
    return None


def arroba(alvo, guardados=None):
    """
    O @ público do grupo ou canal alvo ("@canal"), ou None se ele não tem @ (privado,
    convite ou número que o Telegram nunca contou com @). Usado no crédito do parceiro.
    """
    texto = str(alvo or "").strip()
    if re.match(r"^(?:https?://)?t\.me/(?:\+|joinchat/)", texto):
        return None
    usuario = _USUARIO.match(texto)
    if usuario:
        return f"@{usuario.group(1)}"
    numero = _NUMERO.match(texto)
    if not numero:
        return None
    if guardados is None:
        guardados = _guardados_recentes()
    chat_id = numero.group(1)
    # A origem pode estar cadastrada sem o -100 que o Telegram usa nos canais.
    for chave in (chat_id, f"-100{chat_id}" if not chat_id.startswith("-") else None):
        if chave and (guardados.get(chave) or {}).get("usuario"):
            return f"@{guardados[chave]['usuario']}"
    return None


def nome_clicavel(nome, alvo, guardados=None):
    """O nome (já escapado para o HTML do Telegram) como link para o grupo, se houver link."""
    texto = html.escape(str(nome))
    endereco = link(alvo, guardados)
    if not endereco:
        return texto
    return f'<a href="{html.escape(endereco, quote=True)}">{texto}</a>'


def _usuario_da_entidade(entidade):
    usuario = getattr(entidade, "username", None)
    if usuario:
        return usuario
    for u in getattr(entidade, "usernames", None) or []:
        if getattr(u, "active", False) and getattr(u, "username", None):
            return u.username
    return None


def _chat_id(entidade):
    from telethon import utils as telethon_utils
    return str(telethon_utils.get_peer_id(entidade))


def guardar_dialogos(dialogos):
    """
    Guarda, de cada grupo ou canal das conversas da conta (client.get_dialogs()), o @ e
    a última mensagem. Conversa com pessoa fica de fora. Devolve quantos guardou.
    """
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linhas = []
    for dialogo in dialogos or []:
        entidade = getattr(dialogo, "entity", None)
        if entidade is None or not getattr(entidade, "title", None):
            continue
        try:
            chat_id = _chat_id(entidade)
        except Exception:
            continue
        ultima = getattr(getattr(dialogo, "message", None), "id", None)
        linhas.append((chat_id, _usuario_da_entidade(entidade), ultima, agora))
    if not linhas:
        return 0
    try:
        with db.conexao() as con:
            _garantir_tabela(con)
            # O @ vem sempre do Telegram (sem @ = None); a última mensagem só troca se veio.
            con.executemany(
                "INSERT INTO links_grupos (chat_id, usuario, ultima_msg, atualizado) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(chat_id) DO UPDATE SET usuario = excluded.usuario, "
                "ultima_msg = COALESCE(excluded.ultima_msg, links_grupos.ultima_msg), "
                "atualizado = excluded.atualizado", linhas)
    except Exception as e:
        logger.warning(f"⚠️ [Links] Não consegui guardar os links dos grupos: {type(e).__name__}")
        return 0
    return len(linhas)


async def guardar_convites(client, dialogos):
    """
    Grupo comum não tem @ nem t.me/c: o atalho é o link de convite, que o Telegram só
    mostra a quem é admin. Lê o convite que já existe (não cria outro) dos grupos comuns
    em que a conta é dona ou admin e que ainda não têm convite guardado.
    """
    from telethon.tl.functions.messages import GetFullChatRequest
    from telethon.tl.types import Chat

    guardados = ler_todos()
    guardou = 0
    for dialogo in dialogos or []:
        entidade = getattr(dialogo, "entity", None)
        if not isinstance(entidade, Chat):
            continue
        if not (getattr(entidade, "creator", False) or getattr(entidade, "admin_rights", None)):
            continue
        chat_id = _chat_id(entidade)
        if (guardados.get(chat_id) or {}).get("convite"):
            continue
        try:
            completo = await client(GetFullChatRequest(chat_id=entidade.id))
            convite = getattr(getattr(completo.full_chat, "exported_invite", None), "link", None)
        except Exception as e:
            logger.warning(f"⚠️ [Links] Não consegui ler o convite de um grupo: {type(e).__name__}")
            break
        if convite:
            try:
                with db.conexao() as con:
                    _garantir_tabela(con)
                    con.execute("INSERT INTO links_grupos (chat_id, convite, atualizado) VALUES (?, ?, ?) "
                                "ON CONFLICT(chat_id) DO UPDATE SET convite = excluded.convite, "
                                "atualizado = excluded.atualizado",
                                (chat_id, convite, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                guardou += 1
            except Exception as e:
                logger.warning(f"⚠️ [Links] Não consegui guardar o convite: {type(e).__name__}")
    return guardou


async def atualizar_pela_conta(client, rotulo):
    """
    Lê as conversas da conta e guarda os links: o que os userbots chamam ao ligar.
    Devolve os diálogos, para quem também precisava deles (carregar o cache de IDs).
    """
    dialogos = await client.get_dialogs()
    try:
        total = guardar_dialogos(dialogos)
        convites = await guardar_convites(client, dialogos)
        logger.info(f"🔗 [{rotulo}] Links dos grupos guardados: {total} conversa(s), {convites} convite(s) novo(s).")
    except Exception as e:
        logger.warning(f"⚠️ [{rotulo}] Não consegui guardar os links dos grupos: {type(e).__name__}")
    return dialogos
