"""
IA: roteador do bot_mestre (Opções do Servidor → IA 🤖).

Junta num lugar os atalhos para as IAs que cuidam dos robôs. Por enquanto, o Claude IA 🧠:
manda no privado do Rafael o link da conversa com o Claude em que os robôs são feitos e
mantidos; tocando no link, ele abre a conversa. A conversa é sempre a mesma (as rotinas de
retomada e de checkup chamam esta); se um dia mudar, trocar o LINK_CLAUDE. O link não é
segredo: só abre na conta do Rafael, e já aparece em cada commit do repositório.
Pedido do Rafael (vídeo de 25/10/2026): DECISOES.md, Trabalho com o Claude.
"""
import logging

from aiogram import Router, Bot, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton

from teclados import montar_teclado

logger = logging.getLogger("Painel_IA")

router = Router()
bot_instance = None
ADMIN_ID = None

BOTAO = "IA 🤖"
BOTAO_CLAUDE = "Claude IA 🧠"
# Tratado no bot_mestre, junto do botão Opções do Servidor ⚙️, dono daquele teclado.
VOLTAR = "Voltar às Opções do Servidor 🔙"
LINK_CLAUDE = "https://claude.ai/code/session_017ZsGvBU2Gu3wGbbbAJpT8c"


def configurar_dependencias(bot: Bot, admin_id):
    global bot_instance, ADMIN_ID
    bot_instance, ADMIN_ID = bot, admin_id


def teclado_painel():
    return montar_teclado([[KeyboardButton(text=BOTAO_CLAUDE)], [KeyboardButton(text=VOLTAR)]])


def _do_admin(message):
    return message.from_user is not None and message.from_user.id == ADMIN_ID


@router.message(F.text == BOTAO, StateFilter("*"))
async def painel_handler(message: types.Message, state: FSMContext):
    if not _do_admin(message):
        return
    await state.clear()
    logger.info("🤖 Abrindo o painel de IA.")
    await message.answer(
        "🤖 <b>IA</b>\n"
        "Atalhos para as IAs que cuidam dos robôs.\n\n"
        "<b>O que cada botão faz</b>\n"
        f"🧠 <b>{BOTAO_CLAUDE}</b>: manda o link da nossa conversa com o Claude, onde os robôs são feitos e "
        "consertados; toque no link e a conversa abre.\n"
        f"🔙 <b>{VOLTAR}</b>: volta ao menu anterior.",
        parse_mode="HTML", reply_markup=teclado_painel())


@router.message(F.text == BOTAO_CLAUDE, StateFilter("*"))
async def claude_handler(message: types.Message, state: FSMContext):
    if not _do_admin(message):
        return
    await state.clear()
    logger.info("🧠 Mandando o link da conversa com o Claude.")
    await message.answer(
        "🧠 <b>Claude IA</b>\n"
        "Toque no link para abrir a nossa conversa:\n"
        f"{LINK_CLAUDE}",
        parse_mode="HTML", reply_markup=teclado_painel(), disable_web_page_preview=True)
