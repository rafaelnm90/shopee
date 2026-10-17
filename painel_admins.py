"""
Administradores: roteador do bot_mestre (Opções do Servidor → Administradores 🛡️).

Mostra, no privado do Rafael, o registro que a conta principal monta todo dia
(registro_admins): cada grupo e canal em que ele é dono ou admin, quem são os
administradores, o que cada um pode fazer, e as últimas mudanças. O aviso no privado
quando algo muda sai do bot_mestre (avisar_mudancas), a cada 15 min, e também a chave
da cópia cifrada no repositório, uma vez por chave (avisar_registro_privado).
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
    """Quando saiu a última cópia cifrada no repositório (ramo registro-admins)."""
    quando = registro_privado.situacao().get("ultima_copia") or ""
    if len(quando) < 16:
        return f"🔐 Cópia cifrada no GitHub: a primeira sai às {registro_privado.HORARIO_COPIA}"
    return (f"🔐 Cópia cifrada no GitHub: última em {quando[8:10]}/{quando[5:7]} às {quando[11:16]} "
            f"(todo dia às {registro_privado.HORARIO_COPIA})")


def texto_da_chave(valor):
    """As instruções para o Claude abrir a cópia cifrada, com a chave do servidor."""
    return ("🔐 <b>Registro dos administradores: chave da cópia cifrada</b>\n\n"
            "Todo dia o registro vai para o repositório dos robôs (ramo "
            f"<b>{registro_privado.RAMO}</b>) embaralhado: sem esta chave, é só um monte de letras. "
            "Quem abre é o Claude, com a chave nas configurações do ambiente dele.\n\n"
            "Faça uma vez só, no app ou no site do Claude:\n"
            "1. Na conversa com o Claude, toque no nome do ambiente, no alto, e depois em <b>Editar</b>.\n"
            "2. Em <b>Variáveis de ambiente</b>, acrescente esta linha e salve:\n\n"
            f"<code>{registro_privado.VARIAVEL_CHAVE}={valor}</code>\n\n"
            "<i>Não mande esta chave no chat do Claude nem para ninguém. Depois de salvar, pode apagar "
            "esta mensagem. Vale a partir da próxima vez que o ambiente do Claude iniciar.</i>")


async def avisar_registro_privado():
    """Manda a chave da cópia cifrada ao Rafael, uma vez por chave (o servidor gera outra se a perder)."""
    try:
        valor = registro_privado.chave()
        marca = registro_privado.id_da_chave(valor)
        if registro_privado.situacao().get("avisado_chave") == marca:
            return
        await bot_instance.send_message(ADMIN_ID, texto_da_chave(valor.decode("ascii")), parse_mode="HTML")
        db.atualizar_config(registro_privado.CHAVE_STATUS, lambda s: s.update(avisado_chave=marca))
        logger.info("🔐 Chave da cópia cifrada do registro enviada ao admin.")
    except Exception as e:
        logger.error(f"❌ [Admins] Falha ao mandar a chave da cópia cifrada: {type(e).__name__}")


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
