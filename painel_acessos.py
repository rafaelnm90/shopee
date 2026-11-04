"""
Acessos do Servidor: roteador do bot_mestre (Opções do Servidor → Acessos do Servidor 🔐).

Mostra, no privado do Rafael, onde entrar em cada serviço por trás dos robôs, no
mesmo formato das Informações de Acesso do Disparador de Notas (link, login para
copiar e senha escondida):
- Tailscale: a rede privada que liga o servidor ao celular de verdade. Entra pelo
  Google, então guarda só qual conta Google; a senha é a do Google e não fica aqui.
- Oracle Cloud: onde o servidor dos robôs roda. Guarda o nome da conta na nuvem,
  o e-mail e a senha.
- Cópia do backup (a que o bot manda todo dia no privado): onde o Rafael guardou a
  senha dela (o link do arquivo ou o lugar), nunca a senha. A legenda de cada cópia
  mostra o mesmo lugar, para achá-la mesmo com o servidor fora do ar.
Os dados são do Rafael e vêm pelo próprio bot (botões Editar) ou, cifrados com a
chave do servidor, pelo Claude (avisar.yml, acao=acesso: `guardar`), na chave
"acessos_servidor" das configurações: o repositório é público, então nada disso
fica no código. A mensagem em que ele manda a senha é apagada da conversa logo
depois de guardada, e nenhum dado vai para o log.
Decisão do Rafael: DECISOES.md, Monitor, deploy e servidor.
"""
import html
import json
import logging
import os
import re
import sys

from aiogram import Router, Bot, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import KeyboardButton
from teclados import montar_teclado

import db

logger = logging.getLogger("Acessos")

router = Router()
bot_instance = None
ADMIN_ID = None

CHAVE_CONFIG = "acessos_servidor"
LINK_TAILSCALE = "https://login.tailscale.com/"
LINK_ORACLE = "https://cloud.oracle.com/"
MANTER = "Manter como Está ⏭️"
EDITAR_BACKUP = "Editar Senha do Backup ✏️"
LIMITE_DO_ONDE = 500
# A senha da cópia (uma chave Fernet: 43 letras e um "=") não fica aqui: só onde ela está.
PARECE_A_SENHA = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{43}=")
# O que cada serviço guarda: os campos dos botões Editar, os únicos que o guardar aceita.
CAMPOS = {"tailscale": ("email",), "oracle": ("conta", "email", "senha"), "backup": ("onde",)}
NOMES = {"tailscale": "a conta do Tailscale", "oracle": "o acesso da Oracle",
         "backup": "onde está a senha da cópia do backup"}
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
    aguardando_backup_onde = State()


# --- Dados ---

def ler_acessos():
    """{"tailscale": {...}, "oracle": {...}, "backup": {...}}, com dicionário vazio no que falta cadastrar."""
    dados = db.ler_config(CHAVE_CONFIG, {}) or {}
    return {servico: dict(dados.get(servico) or {}) for servico in CAMPOS}


def salvar_servico(servico, campos):
    """Grava os campos de um serviço, sem mexer no outro."""
    def alterar(dados):
        dados.setdefault(servico, {}).update(campos)
    db.atualizar_config(CHAVE_CONFIG, alterar)


def onde_esta_a_senha():
    """Onde o Rafael guardou a senha da cópia do backup, ou "" se ainda não disse."""
    return (ler_acessos()["backup"].get("onde") or "").strip()


def texto_do_onde(onde):
    """O lugar no HTML do Telegram: o link fica clicável; um lugar escrito aparece como veio."""
    if re.fullmatch(r"https?://\S+", onde or ""):
        link = html.escape(onde, quote=True)
        return f'<a href="{link}">{link}</a>'
    return html.escape(onde or "")


def parece_email(texto):
    texto = (texto or "").strip()
    usuario, arroba, dominio = texto.partition("@")
    return bool(usuario and arroba and "." in dominio and " " not in texto)


# --- Painel ---

def teclado_painel():
    return montar_teclado([
        [KeyboardButton(text="Editar Tailscale ✏️"), KeyboardButton(text="Editar Oracle ✏️")],
        [KeyboardButton(text=EDITAR_BACKUP)],
        [KeyboardButton(text=VOLTAR)],
    ])


def teclado_pergunta(tem_valor):
    """Cancelar e, quando já há um valor guardado, o botão para mantê-lo."""
    linhas = [[KeyboardButton(text=MANTER)]] if tem_valor else []
    return montar_teclado(linhas + [[KeyboardButton(text="Cancelar ❌")]])


def _copiavel(valor, botao):
    if valor:
        return f"<code>{html.escape(valor)}</code>"
    return f"<i>não cadastrado (toque em {botao})</i>"


def texto_painel(acessos):
    tailscale, oracle = acessos["tailscale"], acessos["oracle"]
    senha = oracle.get("senha")
    senha_oracle = (f"<tg-spoiler>{html.escape(senha)}</tg-spoiler>" if senha
                    else "<i>não cadastrada (toque em Editar Oracle ✏️)</i>")
    onde = (acessos["backup"].get("onde") or "").strip()
    onde_backup = texto_do_onde(onde) if onde else f"<i>não cadastrado (toque em {EDITAR_BACKUP})</i>"
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
        "💾 <b>Cópia do backup (a que chega aqui todo dia):</b>\n"
        f"🔑 <b>Onde está a senha:</b> {onde_backup}\n\n"
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


@router.message(F.text == EDITAR_BACKUP, StateFilter("*"))
async def pedir_backup(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await state.clear()
    await message.answer(
        "💾 Onde está guardada a <b>senha da cópia do backup</b>? Envie o link (ex.: o do arquivo no "
        "Google Drive) ou escreva o lugar.\n\n"
        "<i>Guardo só onde ela está, nunca a senha. O lugar aparece aqui e na legenda de cada cópia, "
        "para você achar a senha mesmo com o servidor fora do ar.</i>",
        parse_mode="HTML", reply_markup=teclado_pergunta(bool(onde_esta_a_senha())))
    await state.set_state(AcessosFluxo.aguardando_backup_onde)


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


@router.message(AcessosFluxo.aguardando_backup_onde)
async def salvar_backup(message: types.Message, state: FSMContext):
    if not _admin(message): return
    texto = (message.text or "").strip()
    if texto != MANTER:
        if PARECE_A_SENHA.search(texto):
            # A senha no banco, junto da cópia, abriria a cópia para quem visse o bot.
            try:
                await message.delete()
                apagada = "Apaguei a sua mensagem."
            except Exception as e:
                logger.warning(f"⚠️ Acessos: não consegui apagar a mensagem com a senha ({type(e).__name__}).")
                apagada = "Apague a sua mensagem, por favor."
            await message.answer(f"⚠️ Isso parece a própria senha, e ela não fica no bot. {apagada} "
                                 "Envie só onde ela está (o link do arquivo ou o lugar).")
            return
        if not texto or len(texto) > LIMITE_DO_ONDE:
            await message.answer(f"⚠️ Envie o link ou o lugar em texto (até {LIMITE_DO_ONDE} caracteres).")
            return
        salvar_servico("backup", {"onde": texto})
        logger.info("✅ Acessos: onde está a senha da cópia do backup atualizado.")
        await message.answer("✅ Guardei onde está a senha da cópia do backup.")
    await mostrar_painel(message, state)


# --- Linha de comando (avisar.yml, acao=acesso; o cifrar roda no ambiente do Claude) ---

class Recusado(Exception):
    """O que veio cifrado não é um acesso que o painel guarda (a mensagem é fixa, sem o dado)."""


def cifrar(dados, valor_chave):
    from cryptography.fernet import Fernet
    return Fernet(valor_chave).encrypt(json.dumps(dados, ensure_ascii=False).encode()).decode()


def guardar_cifrado(texto_cifrado, valor_chave):
    """
    No servidor: abre o que o Claude mandou cifrado com a chave do servidor (ex.:
    {"backup": {"onde": "..."}}, só os CAMPOS dos botões Editar) e guarda como o botão
    guardaria. Confere tudo antes de gravar e devolve só os nomes dos serviços.
    """
    from cryptography.fernet import Fernet
    dados = json.loads(Fernet(valor_chave).decrypt(texto_cifrado.strip().encode()).decode())
    if not isinstance(dados, dict) or not dados:
        raise Recusado("nada para guardar")
    for servico, campos in dados.items():
        if servico not in CAMPOS or not isinstance(campos, dict) or not campos:
            raise Recusado("serviço desconhecido")
        for campo, valor in campos.items():
            if campo not in CAMPOS[servico] or not isinstance(valor, str) or not valor.strip():
                raise Recusado("campo desconhecido ou vazio")
        if servico == "backup" and (len(campos["onde"].strip()) > LIMITE_DO_ONDE
                                    or PARECE_A_SENHA.search(campos["onde"])):
            raise Recusado("o lugar da senha do backup não vale")
    for servico, campos in dados.items():
        salvar_servico(servico, {campo: valor.strip() for campo, valor in campos.items()})
    return list(dados)


def texto_da_confirmacao(servicos):
    """O aviso no privado do Rafael: o que foi guardado e onde ver, sem o dado."""
    return (f"🔐 Guardei {' e '.join(NOMES[s] for s in servicos)} no "
            "<b>Opções do Servidor ⚙️ → Acessos do Servidor 🔐</b>.")


def main(argumentos):
    if len(argumentos) != 2 or argumentos[0] not in ("cifrar", "guardar"):
        print("uso: painel_acessos.py cifrar ARQUIVO.json | guardar TEXTO_CIFRADO")
        return 2
    acao, valor = argumentos
    import registro_privado
    try:
        if acao == "cifrar":
            chave = os.getenv(registro_privado.VARIAVEL_CHAVE, "").strip()
            if not chave:
                print(f"❌ {registro_privado.VARIAVEL_CHAVE} ausente no ambiente")
                return 1
            with open(valor, encoding="utf-8") as arquivo:
                print(cifrar(json.load(arquivo), chave))
            return 0
        servicos = guardar_cifrado(valor, registro_privado.chave())
        import avisar_rafael
        avisado = avisar_rafael.mandar_texto(texto_da_confirmacao(servicos), html=True)
        print(f"✅ Guardado no Acessos do Servidor: {', '.join(servicos)}"
              + ("" if avisado else " (o aviso no privado não saiu)"))
        return 0
    except Recusado as e:
        print(f"❌ Recusado: {e}")
        return 1
    except Exception as e:
        # Só o tipo: a mensagem de erro pode trazer o dado.
        print(f"❌ Falhou: {type(e).__name__}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
