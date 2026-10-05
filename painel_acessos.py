"""
Acessos do Servidor: roteador do bot_mestre (Opções do Servidor → Acessos do Servidor 🔐).

Mostra, no privado do Rafael, onde entrar em cada serviço por trás dos robôs, no
mesmo formato das Informações de Acesso do Disparador de Notas (link, login para
copiar e senha escondida):
- Tailscale: a rede privada que liga o servidor ao celular de verdade. Entra pelo
  Google, então guarda só qual conta Google; a senha é a do Google e não fica aqui.
- Oracle Cloud: onde o servidor dos robôs roda. Guarda o nome da conta na nuvem,
  o e-mail e a senha.
Os dados são do Rafael e vêm pelo próprio bot (botões Editar), na chave
"acessos_servidor" das configurações: o repositório é público, então nada disso
fica no código. A mensagem em que ele manda a senha é apagada da conversa logo
depois de guardada, e nenhum dado vai para o log.
Decisão do Rafael: DECISOES.md, Monitor, deploy e servidor.
"""
import html
import logging

from aiogram import Router, Bot, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

import db

logger = logging.getLogger("Acessos")

router = Router()
bot_instance = None
ADMIN_ID = None

CHAVE_CONFIG = "acessos_servidor"
LINK_TAILSCALE = "https://login.tailscale.com/"
LINK_ORACLE = "https://cloud.oracle.com/"
MANTER = "Manter como Está ⏭️"
# Tratado no bot_mestre, junto do botão Opções do Servidor ⚙️, dono daquele teclado.
VOLTAR = "Voltar às Opções do Servidor 🔙"


def configurar_dependencias(bot: Bot, admin_id):
    global bot_instance, ADMIN_ID
    bot_instance, ADMIN_ID = bot, admin_id


def _admin(message):
    return message.from_user is not None and message.from_user.id == ADMIN_ID


class AcessosFluxo(StatesGroup):
    menu = State()
    aguardando_tailscale_email = State()
    aguardando_oracle_conta = State()
    aguardando_oracle_email = State()
    aguardando_oracle_senha = State()


# --- Dados ---

def ler_acessos():
    """{"tailscale": {...}, "oracle": {...}}, com dicionário vazio no serviço ainda não cadastrado."""
    dados = db.ler_config(CHAVE_CONFIG, {})
    return {"tailscale": dict(dados.get("tailscale") or {}), "oracle": dict(dados.get("oracle") or {})}


def salvar_servico(servico, campos):
    """Grava os campos de um serviço, sem mexer no outro."""
    def alterar(dados):
        dados.setdefault(servico, {}).update(campos)
    db.atualizar_config(CHAVE_CONFIG, alterar)


def parece_email(texto):
    texto = (texto or "").strip()
    usuario, arroba, dominio = texto.partition("@")
    return bool(usuario and arroba and "." in dominio and " " not in texto)


# --- Painel ---

def teclado_painel():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Editar Tailscale ✏️"), KeyboardButton(text="Editar Oracle ✏️")],
            [KeyboardButton(text=VOLTAR)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


teclado_cancelar = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Cancelar ❌")]], resize_keyboard=True, is_persistent=True)


def teclado_pergunta(tem_valor):
    """Cancelar e, quando já há um valor guardado, o botão para mantê-lo."""
    linhas = [[KeyboardButton(text=MANTER)]] if tem_valor else []
    return ReplyKeyboardMarkup(keyboard=linhas + [[KeyboardButton(text="Cancelar ❌")]],
                               resize_keyboard=True, is_persistent=True)


def _copiavel(valor, botao):
    if valor:
        return f"<code>{html.escape(valor)}</code>"
    return f"<i>não cadastrado (toque em {botao})</i>"


def texto_painel(acessos):
    tailscale, oracle = acessos["tailscale"], acessos["oracle"]
    senha = oracle.get("senha")
    senha_oracle = (f"<tg-spoiler>{html.escape(senha)}</tg-spoiler>" if senha
                    else "<i>não cadastrada (toque em Editar Oracle ✏️)</i>")
    return (
        "🔐 <b>Acessos do Servidor (Privado)</b>\n\n"
        "🌐 <b>Tailscale (rede privada do celular):</b>\n"
        f"🔗 <b>Link:</b> {LINK_TAILSCALE}\n"
        "🔓 <b>Entrar:</b> pelo Google (botão <i>Sign in with Google</i>)\n"
        f"👤 <b>Conta Google:</b> {_copiavel(tailscale.get('email'), 'Editar Tailscale ✏️')}\n"
        "🔑 <b>Senha:</b> a da sua conta Google\n\n"
        "☁️ <b>Oracle Cloud (servidor dos robôs):</b>\n"
        f"🔗 <b>Link:</b> {LINK_ORACLE}\n"
        f"🏢 <b>Nome da conta na nuvem:</b> {_copiavel(oracle.get('conta'), 'Editar Oracle ✏️')}\n"
        f"👤 <b>Login:</b> {_copiavel(oracle.get('email'), 'Editar Oracle ✏️')}\n"
        f"🔑 <b>Senha:</b> {senha_oracle}\n\n"
        "<i>(Toque na senha para revelá-la ou nos logins para copiar)</i>"
    )


async def mostrar_painel(message: types.Message, state: FSMContext):
    await state.clear()                       # tira a senha digitada dos dados do fluxo
    await state.set_state(AcessosFluxo.menu)
    await message.answer(texto_painel(ler_acessos()), parse_mode="HTML", reply_markup=teclado_painel())


# Os botões funcionam em qualquer estado (StateFilter("*")): depois de um reinício o
# estado do FSM some, mas o teclado continua na tela do Rafael.
@router.message(F.text == "Acessos do Servidor 🔐", StateFilter("*"))
async def painel_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    logger.info("🔐 Consultando os acessos do servidor.")
    await mostrar_painel(message, state)


@router.message(F.text == "Editar Tailscale ✏️", StateFilter("*"))
async def pedir_tailscale(message: types.Message, state: FSMContext):
    if not _admin(message): return
    atual = ler_acessos()["tailscale"].get("email")
    await state.clear()
    await message.answer(
        "🌐 Qual é a <b>conta Google</b> com que você entra no Tailscale? Envie o e-mail.\n\n"
        "<i>A senha é a do Google e não fica guardada aqui: quem visse o bot teria a sua "
        "conta Google inteira.</i>",
        parse_mode="HTML", reply_markup=teclado_pergunta(bool(atual)))
    await state.set_state(AcessosFluxo.aguardando_tailscale_email)


@router.message(F.text == "Editar Oracle ✏️", StateFilter("*"))
async def pedir_oracle_conta(message: types.Message, state: FSMContext):
    if not _admin(message): return
    atual = ler_acessos()["oracle"].get("conta")
    await state.clear()
    await message.answer(
        "☁️ <b>Oracle (1 de 3):</b> qual é o <b>nome da conta na nuvem</b> "
        "(<i>Cloud Account Name</i>)?\n\n"
        "<i>É o primeiro campo da tela de entrada da Oracle e vem no e-mail de boas-vindas dela. "
        "Nada é gravado antes da última pergunta: Cancelar ❌ não muda nada.</i>",
        parse_mode="HTML", reply_markup=teclado_pergunta(bool(atual)))
    await state.set_state(AcessosFluxo.aguardando_oracle_conta)


# --- Respostas dentro de cada edição ---
# Ficam depois de todos os botões: no aiogram ganha o primeiro handler que casar, e um
# botão tocado no meio de uma edição tem de abrir o botão, não virar resposta.

@router.message(AcessosFluxo.aguardando_tailscale_email)
async def salvar_tailscale(message: types.Message, state: FSMContext):
    if not _admin(message): return
    if message.text != MANTER:
        if not parece_email(message.text):
            await message.answer("⚠️ Envie o e-mail da conta Google (ex.: <code>nome@gmail.com</code>).",
                                 parse_mode="HTML")
            return
        salvar_servico("tailscale", {"email": message.text.strip()})
        logger.info("✅ Acessos: conta do Tailscale atualizada.")
        await message.answer("✅ Conta do Tailscale guardada.")
    await mostrar_painel(message, state)


@router.message(AcessosFluxo.aguardando_oracle_conta)
async def receber_oracle_conta(message: types.Message, state: FSMContext):
    if not _admin(message): return
    texto = (message.text or "").strip()
    if not texto:
        await message.answer("⚠️ Envie o nome da conta na nuvem em texto.")
        return
    if texto != MANTER:
        await state.update_data(conta=texto)
    atual = ler_acessos()["oracle"].get("email")
    await message.answer("☁️ <b>Oracle (2 de 3):</b> qual é o <b>e-mail</b> (login) da conta?",
                         parse_mode="HTML", reply_markup=teclado_pergunta(bool(atual)))
    await state.set_state(AcessosFluxo.aguardando_oracle_email)


@router.message(AcessosFluxo.aguardando_oracle_email)
async def receber_oracle_email(message: types.Message, state: FSMContext):
    if not _admin(message): return
    if message.text != MANTER:
        if not parece_email(message.text):
            await message.answer("⚠️ Envie o e-mail de login da Oracle (ex.: <code>nome@gmail.com</code>).",
                                 parse_mode="HTML")
            return
        await state.update_data(email=message.text.strip())
    atual = ler_acessos()["oracle"].get("senha")
    await message.answer(
        "☁️ <b>Oracle (3 de 3):</b> qual é a <b>senha</b>?\n\n"
        "<i>Assim que eu guardar, apago a sua mensagem com a senha desta conversa. "
        "Ela aparece só aqui, escondida, no Acessos do Servidor 🔐.</i>",
        parse_mode="HTML", reply_markup=teclado_pergunta(bool(atual)))
    await state.set_state(AcessosFluxo.aguardando_oracle_senha)


@router.message(AcessosFluxo.aguardando_oracle_senha)
async def salvar_oracle(message: types.Message, state: FSMContext):
    if not _admin(message): return
    texto = message.text or ""
    if not texto.strip():
        await message.answer("⚠️ Envie a senha em texto.")
        return
    campos = {chave: valor for chave, valor in (await state.get_data()).items() if chave in ("conta", "email")}
    if texto != MANTER:
        campos["senha"] = texto
        try:
            await message.delete()
            apagada = "Apaguei a sua mensagem com a senha."
        except Exception as e:
            logger.warning(f"⚠️ Acessos: não consegui apagar a mensagem da senha ({type(e).__name__}).")
            apagada = "⚠️ Não consegui apagar a sua mensagem com a senha: apague-a você, por favor."
    else:
        apagada = ""
    if campos:
        salvar_servico("oracle", campos)
    logger.info("✅ Acessos: dados da Oracle atualizados.")
    await message.answer(f"✅ Acesso da Oracle guardado. {apagada}".strip())
    await mostrar_painel(message, state)
