"""
Faxina do tópico do Baixador ("Downloader Videos", no Grupo Público): deixa um
painel só, o mais recente, e tira as mensagens "fixou uma mensagem". Os vídeos
entregues aos usuários ficam para sempre (decisão do Rafael: DECISOES.md, Baixador).

O painel desce para o fim do tópico e é fixado pelo downloader_bot a cada vez; o
anterior deveria sumir. Quem apaga aqui é a conta principal (userbot), porque o
Telegram só deixa um bot apagar mensagem com menos de 48 h e os painéis antigos
passam disso. Roda dentro do divulgacao_canal, o serviço que usa a sessão da conta
principal: a cada 10 min olha as últimas mensagens do tópico e, ao subir e uma vez
por dia, o tópico inteiro.

Também guarda o grupo e o tópico do Baixador, que o downloader_bot importa daqui.
"""
import asyncio
import logging
import os
import time

import db

GRUPO_DOWNLOADER = -1003892378604      # Grupo Público para Afiliados
TOPICO_DOWNLOADER = 1054               # tópico "Downloader Videos"
TITULO_PAINEL = "BAIXADOR DE VÍDEOS"   # primeira linha do TEXTO_PAINEL_DOWNLOADER
LOTE = 100                             # o Telegram apaga até 100 mensagens por chamada
RECENTES = 300                         # quantas mensagens a volta de 10 min olha
INTERVALO_S = 600
INTERVALO_COMPLETA_S = 86400

logger = logging.getLogger(__name__)


def ids_dos_bots():
    """IDs do bot do Baixador e do bot_mestre (o número antes do ':' no token)."""
    ids = set()
    for nome in ("TELEGRAM_TOKEN_DOWNLOADER", "TELEGRAM_TOKEN"):
        token = os.getenv(nome, "")
        if token.split(":", 1)[0].isdigit():
            ids.add(int(token.split(":", 1)[0]))
    return ids


def painel_atual():
    """ID do painel que o downloader_bot registrou por último."""
    try:
        with db.conexao() as conexao:
            linha = conexao.execute("SELECT valor FROM painel_downloader WHERE chave = 'msg_id'").fetchone()
        return int(linha[0]) if linha and str(linha[0]).isdigit() else None
    except Exception:
        return None


def eh_aviso_de_fixacao(msg):
    """Mensagem de serviço "fulano fixou uma mensagem"."""
    return type(getattr(msg, "action", None)).__name__ == "MessageActionPinMessage"


def eh_painel(msg, bots):
    """Painel do Baixador mandado por um dos bots. Mensagem de pessoa nunca conta."""
    de_bot = msg.sender_id in bots or getattr(getattr(msg, "sender", None), "bot", False)
    return de_bot and TITULO_PAINEL in (getattr(msg, "message", None) or "")


async def limpar_topico(client, limite=None, bots=None):
    """
    Apaga os painéis antigos e os avisos de fixação do tópico. Fica o painel
    registrado e também o mais novo de todos, caso o registro ainda não tenha
    sido atualizado. Devolve (apagadas, motivo_da_falha ou None).
    """
    bots = ids_dos_bots() if bots is None else bots
    paineis, avisos = [], []
    async for msg in client.iter_messages(GRUPO_DOWNLOADER, reply_to=TOPICO_DOWNLOADER, limit=limite):
        if msg.id == TOPICO_DOWNLOADER:
            continue
        if eh_aviso_de_fixacao(msg):
            avisos.append(msg.id)
        elif eh_painel(msg, bots):
            paineis.append(msg.id)

    manter = {painel_atual(), max(paineis, default=None)}
    apagar = sorted(avisos + [i for i in paineis if i not in manter])

    apagadas = 0
    for i in range(0, len(apagar), LOTE):
        lote = apagar[i:i + LOTE]
        try:
            await client.delete_messages(GRUPO_DOWNLOADER, lote)
            apagadas += len(lote)
        except Exception as e:
            # Sem direito de apagar (a conta não é admin) ou limite do Telegram:
            # para aqui e tenta de novo na próxima volta.
            return apagadas, f"{type(e).__name__}: {e}"
        await asyncio.sleep(1)
    return apagadas, None


async def faxina_loop(client):
    """A cada 10 min, as últimas mensagens; ao subir e uma vez por dia, o tópico inteiro."""
    await asyncio.sleep(120)   # deixa a sessão terminar de subir
    ultima_completa = None
    while True:
        completa = ultima_completa is None or time.monotonic() - ultima_completa >= INTERVALO_COMPLETA_S
        try:
            apagadas, falha = await limpar_topico(client, limite=None if completa else RECENTES)
            if completa:
                ultima_completa = time.monotonic()
            if apagadas:
                logger.info(f"🧹 [Baixador] {apagadas} painel(is) antigo(s) e aviso(s) de fixação apagado(s).")
            if falha:
                logger.error(f"❌ [Baixador] Faxina do tópico parou: {falha}")
                from utils import registrar_erro_json
                registrar_erro_json(f"faxina_topico_baixador: {falha}", origem="faxina_baixador.py")
        except Exception as e:
            logger.error(f"❌ [Baixador] Erro na faxina do tópico ({type(e).__name__}): {e}")
        await asyncio.sleep(INTERVALO_S)
