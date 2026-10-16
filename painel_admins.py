"""
Administradores: roteador do bot_mestre (Opções do Servidor → Administradores 🛡️).

Mostra, no privado do Rafael, o registro que a conta principal monta todo dia
(registro_admins): cada grupo e canal em que ele é dono ou admin, quem são os
administradores, o que cada um pode fazer, e as últimas mudanças. O aviso no privado
quando algo muda sai do bot_mestre (avisar_mudancas), a cada 15 min, e também as
instruções para ligar a cópia no repositório privado (avisar_registro_privado).
Decisão do Rafael: DECISOES.md, Monitor, deploy e servidor.
"""
import logging

from aiogram import Router, Bot, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton

import db
import links_grupos
import registro_admins
import registro_privado
from teclados import montar_teclado

logger = logging.getLogger("Painel_Admins")

router = Router()
bot_instance = None
ADMIN_ID = None

BOTAO = "Administradores 🛡️"
# Tratado no bot_mestre, junto do botão Opções do Servidor ⚙️, dono daquele teclado.
VOLTAR = "Voltar às Opções do Servidor 🔙"
LIMITE_LINHAS_AVISO = 30


def configurar_dependencias(bot: Bot, admin_id):
    global bot_instance, ADMIN_ID
    bot_instance, ADMIN_ID = bot, admin_id


def teclado_painel():
    return montar_teclado([[KeyboardButton(text=VOLTAR)]])


@router.message(F.text == BOTAO, StateFilter("*"))
async def painel_handler(message: types.Message, state: FSMContext):
    if message.from_user is None or message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    logger.info("🛡️ Consultando o registro de administradores.")
    textos = registro_admins.textos_do_painel(links_grupos.nome_clicavel)
    linha = linha_registro_privado()
    if linha:
        textos[0] += "\n" + linha
    for i, texto in enumerate(textos):
        teclado = teclado_painel() if i == len(textos) - 1 else None
        await message.answer(texto, parse_mode="HTML", reply_markup=teclado, disable_web_page_preview=True)


def linha_registro_privado():
    """Como está a cópia no repositório privado do GitHub; vazio se ainda não tentou."""
    status = registro_privado.situacao()
    situacao = status.get("situacao")
    if situacao == "ok":
        quando = status.get("ultimo_envio") or ""
        quando = f"{quando[8:10]}/{quando[5:7]} às {quando[11:16]}" if len(quando) >= 16 else "?"
        return f"📁 Cópia no GitHub privado: ✅ em dia (último envio em {quando})"
    if situacao == "sem_acesso":
        return "📁 Cópia no GitHub privado: ⏳ esperando o repositório e a chave (instruções no seu privado)"
    if situacao == "erro":
        return "📁 Cópia no GitHub privado: ❌ o último envio falhou; tento de novo a cada 10 min"
    return ""


def texto_da_chave(chave_publica):
    """As instruções para ligar a cópia privada, com a parte pública da chave do servidor."""
    return ("🔐 <b>Registro privado dos administradores no GitHub</b>\n\n"
            "Para o servidor gravar o registro no seu repositório privado:\n\n"
            f"1. Se ainda não criou, crie o repositório <b>{registro_privado.REPOSITORIO.split('/')[1]}</b>, "
            f"marcado como <b>Private</b> e com <b>Add a README file</b>: {registro_privado.LINK_NOVO_REPOSITORIO}\n"
            f"2. Abra {registro_privado.LINK_CADASTRAR_CHAVE}, ponha o título <b>Servidor dos robôs</b>, cole a chave "
            "abaixo e marque <b>Allow write access</b>.\n\n"
            f"<code>{chave_publica}</code>\n\n"
            "<i>É a parte pública da chave: sozinha, não dá acesso a nada. Depois de cadastrada, o servidor envia "
            "o arquivo em até 10 minutos e eu te aviso aqui.</i>")


async def avisar_registro_privado():
    """Uma vez por chave: as instruções com ela (o servidor gera outra se a perdeu). Depois, uma vez: que ligou."""
    try:
        status = registro_privado.situacao()
        if (status.get("situacao") == "sem_acesso" and status.get("chave_publica")
                and status.get("avisado_chave") != status["chave_publica"]):
            await bot_instance.send_message(ADMIN_ID, texto_da_chave(status["chave_publica"]), parse_mode="HTML",
                                            disable_web_page_preview=True)
            db.atualizar_config(registro_privado.CHAVE_STATUS,
                                lambda s: s.update(avisado_chave=status["chave_publica"], avisado_ok=False))
            logger.info("🔐 Instruções do registro privado enviadas ao admin.")
        elif status.get("situacao") == "ok" and not status.get("avisado_ok"):
            await bot_instance.send_message(
                ADMIN_ID, "✅ <b>Registro privado ligado.</b> Os administradores estão no seu repositório privado "
                f"<b>{registro_privado.REPOSITORIO}</b>, e o arquivo se atualiza sozinho quando algo muda.",
                parse_mode="HTML")
            db.atualizar_config(registro_privado.CHAVE_STATUS, lambda s: s.update(avisado_ok=True))
    except Exception as e:
        logger.error(f"❌ [Admins] Falha ao avisar sobre o registro privado: {type(e).__name__}: {e}")


def texto_do_aviso(mudancas):
    """O aviso no privado com as mudanças novas (as primeiras LIMITE_LINHAS_AVISO)."""
    linhas = [registro_admins.linha_mudanca(m, links_grupos.nome_clicavel) for m in mudancas[:LIMITE_LINHAS_AVISO]]
    texto = "🛡️ <b>Administradores: o que mudou</b>\n\n" + "\n".join(linhas)
    if len(mudancas) > LIMITE_LINHAS_AVISO:
        texto += f"\n\n…e mais {len(mudancas) - LIMITE_LINHAS_AVISO}."
    return texto + f"\n\n<i>O registro completo fica em Opções do Servidor ⚙️ → {BOTAO}.</i>"


async def avisar_mudancas():
    """Manda no privado as mudanças que a conferência achou e ainda não foram avisadas."""
    try:
        mudancas = registro_admins.mudancas_nao_avisadas()
        if not mudancas:
            return
        await bot_instance.send_message(ADMIN_ID, texto_do_aviso(mudancas), parse_mode="HTML",
                                        disable_web_page_preview=True)
        registro_admins.marcar_avisadas([m["id"] for m in mudancas])
        logger.info(f"🛡️ Aviso de {len(mudancas)} mudança(s) de administradores enviado ao admin.")
    except Exception as e:
        logger.error(f"❌ [Admins] Falha ao avisar as mudanças: {type(e).__name__}: {e}")
