"""
O grupo dos amigos da Shopee Vídeo: um grupo do Telegram em que os amigos do Rafael pedem um vídeo pronto para postar
na Shopee Vídeo deles, como os do modo assistente (um vídeo da Fonte dos Vídeos do painel, editado como os do
assistente, com o título, os produtos e o comentário). O Rafael manda /amigos no grupo, e o bot fixa a mensagem com o
botão Quero um vídeo 🎬. Cada toque é um pedido, numa fila, atendido um de cada vez, na ordem; o vídeo vai no grupo, em
resposta à mensagem do pedido. Só pede quem o Rafael liberou: quem toca sem estar liberado recebe o aviso no grupo, e
o Rafael recebe o nome no privado, com o Liberar ✅. O Rafael sempre pode pedir: o vídeo dele é preparado como o
Enviar 1 Agora 📤 e vai ao privado, com o Postei ✅, e ao grupo (P281 1). A mensagem do pedido diz em quanto tempo o
vídeo fica pronto (minutos_estimados). Nenhum vídeo vai a duas pessoas, e o produto que o amigo já
recebeu não volta para ele (assistente_shopee_video.preparar_para_o_amigo). O robô e o assistente do Rafael não mudam.

O bot_mestre inclui o router, chama configurar_dependencias e passa o /amigos (comando_amigos) antes do tratamento
das mensagens soltas nos grupos, que fica com todas elas. O painel_shopee_video mostra o botão Grupo dos Amigos 👥;
nele, o Liberar Amigos ✅ mostra o nome de cada um que tocou e ainda não foi liberado. Depois do 1º /amigos, o comando
fica no menu do grupo, visível só para o Rafael.
Escolhas do Rafael (21 e 22/11/2026, P271 2 a P281 1): DECISOES.md, Shopee Vídeo.
"""
import asyncio
import html
import logging
import math
import time
import uuid
from datetime import datetime, timedelta

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (BotCommand, BotCommandScopeChatMember, InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton)

import assistente_shopee_video as assistente
import db
import links_grupos
import painel_shopee_video as painel
import registro_processos
from fuso import fuso_horario
from teclados import montar_teclado
from utils import mencao_do_usuario

logger = logging.getLogger("ShopeeVideo")

router = Router()
bot_instance = None
ADMIN_ID = None

CHAVE = "grupo_dos_amigos"
CALLBACK_QUERO = "amigos:quero"
CALLBACK_LIBERAR = "amigos:liberar:"
BOTAO_QUERO = "Quero um vídeo 🎬"
BOTAO_LIGAR = "Ligar o Grupo ▶️"
BOTAO_DESLIGAR = "Desligar o Grupo ⏸️"
BOTAO_TIRAR = "Tirar Amigo ➖"
BOTAO_LIBERAR = "Liberar ✅"
# O botão do painel leva, entre parênteses, quantos esperam a liberação (P279 1).
BOTAO_LIBERAR_AMIGOS = "Liberar Amigos ✅"
BOTAO_VOLTAR_AMIGOS = "Voltar ao Grupo dos Amigos 🔙"
DESCRICAO_DO_COMANDO = "Pôr o botão Quero um vídeo 🎬 no grupo"
PROCESSO_DO_PEDIDO = "grupo dos amigos: pedido"
PROCESSO_DO_PAINEL = "grupo dos amigos: painel"
# Quem toca sem estar liberado: o aviso no privado do Rafael sai no máximo uma vez neste tempo, por pessoa (os toques
# seguintes só respondem no próprio botão).
ESPERA_DO_AVISO = 6 * 3600
# A estimativa da mensagem do pedido (pedido do Rafael, 22/11): a mediana do preparo dos últimos PREPAROS_GUARDADOS
# pedidos feitos, vezes a posição na fila; sem nenhum feito ainda, PREPARO_PADRAO segundos por pedido.
PREPARO_PADRAO = 180
PREPAROS_GUARDADOS = 10

TEXTO_DO_BOTAO = (
    "🎬 <b>Vídeos para a Shopee Vídeo</b>\n"
    f"Toque em <b>{BOTAO_QUERO}</b> e eu preparo um vídeo pronto para você postar na sua Shopee Vídeo: o vídeo, o "
    "título, o produto e o comentário. Ele chega aqui no grupo, em resposta ao seu pedido, com os passos. Cada toque é "
    "um vídeo, e os pedidos são feitos um de cada vez, na ordem.")
SEM_VIDEO = "😕 {mencao}, agora não tenho vídeo novo para você. Toque de novo mais tarde."
NAO_SAIU = "😕 {mencao}, não consegui preparar o seu vídeo agora. Toque de novo mais tarde."


class AmigosFluxo(StatesGroup):
    menu = State()
    tirando = State()
    liberando = State()


def configurar_dependencias(bot, scheduler, admin_id):
    global bot_instance, ADMIN_ID
    bot_instance, ADMIN_ID = bot, admin_id
    # A fila fica no banco: depois de um reinício (deploy), o pedido que esperava é atendido na volta seguinte.
    scheduler.add_job(atender_a_fila, "interval", minutes=1, id="shopee_video_amigos",
                      replace_existing=True, max_instances=1, coalesce=True)
    # O /amigos no menu do grupo que já existia antes dele ir para o menu, sem esperar outro /amigos.
    scheduler.add_job(conferir_o_comando_no_menu, "date", id="shopee_video_amigos_menu", replace_existing=True,
                      run_date=datetime.now(fuso_horario) + timedelta(seconds=30), misfire_grace_time=None)


# --- A trava do bot_mestre ---
# A trava do bot_mestre (BloqueioAdminMiddleware) só deixa o Rafael usar o bot no privado: num grupo, ela barra até as
# mensagens dele e os toques de quem não é ele. Por ela passam só o /amigos do Rafael e o toque de qualquer pessoa no
# Quero um vídeo 🎬; o grupo certo e quem foi liberado, o comando_amigos e o quero_um_video conferem.
COMANDO = "/amigos"


def via_verde(texto, clique, do_admin):
    """O que a trava do bot_mestre deixa passar num grupo: o /amigos do Rafael e o toque no Quero um vídeo 🎬."""
    texto = (texto or "").strip()
    if clique:
        return texto == CALLBACK_QUERO
    comando = texto.split(maxsplit=1)[0].split("@", 1)[0].casefold() if texto else ""
    return bool(do_admin) and comando == COMANDO


# --- Dados (chave grupo_dos_amigos) ---
# grupo e titulo: o grupo do /amigos; ligado: o grupo atende os pedidos; botao: a mensagem fixada com o botão;
# liberados: {id do Telegram: {"nome"}} de quem pode pedir; fila: os pedidos, o mais velho primeiro; avisados:
# {id: {"quando", "nome"}} do último aviso no privado do Rafael de quem tocou sem estar liberado (o Liberar ✅ pega o
# nome dali; quem está ali espera no Liberar Amigos ✅ do painel até ser liberado); preparos: os segundos de preparo
# dos últimos pedidos feitos, para a estimativa (minutos_estimados).

def _padrao():
    return {"grupo": None, "titulo": "", "ligado": False, "botao": None, "liberados": {}, "fila": [], "avisados": {},
            "preparos": []}


def ler():
    return {**_padrao(), **(db.ler_config(CHAVE, {}) or {})}


def _alterar(alterar):
    """Lê, muda e grava a chave numa transação só (db.atualizar_config); devolve o retorno de alterar."""
    def com_padrao(dados):
        for chave, valor in _padrao().items():
            dados.setdefault(chave, valor)
        return alterar(dados)
    return db.atualizar_config(CHAVE, com_padrao, {})


def nome_do_usuario(usuario):
    """O nome de quem tocou, para o painel e o privado do Rafael: o nome e o @, quando tem."""
    nome = " ".join(p for p in (getattr(usuario, "first_name", None), getattr(usuario, "last_name", None)) if p)
    arroba = getattr(usuario, "username", None)
    return (nome or "Sem nome") + (f" (@{arroba})" if arroba else "")


def liberar(ident):
    """Libera quem pode pedir, com o nome do aviso dele; devolve (se é novo, o nome)."""
    def alterar(dados):
        chave = str(ident)
        novo = chave not in dados["liberados"]
        if novo:
            aviso = dados["avisados"].pop(chave, None) or {}
            dados["liberados"][chave] = {"nome": aviso.get("nome") or chave}
        return novo, dados["liberados"][chave]["nome"]
    return _alterar(alterar) or (False, str(ident))


def pendentes(config):
    """Quem tocou em Quero um vídeo 🎬 e ainda não foi liberado: {id: nome}, na ordem do 1º toque."""
    return {ident: dados.get("nome") or ident for ident, dados in config["avisados"].items()
            if ident not in config["liberados"]}


def tirar(ident):
    """Tira quem podia pedir, com os pedidos dele que esperavam na fila; devolve o nome, ou "" se não estava."""
    def alterar(dados):
        quem = dados["liberados"].pop(str(ident), None)
        dados["fila"] = [p for p in dados["fila"] if str(p["id"]) != str(ident)]
        return (quem or {}).get("nome", "")
    return _alterar(alterar) or ""


def entrar_na_fila(usuario, mensagem=None):
    """O pedido novo no fim da fila; devolve (chave do pedido, posição na fila, contando o que está sendo feito)."""
    pedido = {"chave": uuid.uuid4().hex[:12], "id": usuario.id, "mencao": mencao_do_usuario(usuario),
              "mensagem": mensagem, "pedido_em": datetime.now(fuso_horario).strftime("%Y-%m-%d %H:%M:%S")}

    def alterar(dados):
        dados["fila"].append(pedido)
        return len(dados["fila"])
    return pedido["chave"], _alterar(alterar) or 1


def anotar_mensagem_do_pedido(chave, mensagem):
    """A mensagem "estou preparando" do pedido, a que o vídeo responde."""
    def alterar(dados):
        for pedido in dados["fila"]:
            if pedido["chave"] == chave:
                pedido["mensagem"] = mensagem
    _alterar(alterar)


def sair_da_fila(chave):
    def alterar(dados):
        dados["fila"] = [p for p in dados["fila"] if p["chave"] != chave]
    _alterar(alterar)


def avisar_agora(ident, nome, agora=None):
    """
    Se o aviso de quem tocou sem estar liberado vai agora ao privado do Rafael (uma vez a cada ESPERA_DO_AVISO); o
    nome fica guardado para o Liberar ✅.
    """
    momento = agora if agora is not None else time.time()

    def alterar(dados):
        if momento - float((dados["avisados"].get(str(ident)) or {}).get("quando", 0)) < ESPERA_DO_AVISO:
            return False
        dados["avisados"][str(ident)] = {"quando": momento, "nome": nome}
        return True
    return bool(_alterar(alterar))


def do_rafael(ident):
    """O pedido é do Rafael: ele sempre pode pedir, sem se liberar (P281 1)."""
    return ADMIN_ID is not None and str(ident) == str(ADMIN_ID)


def anotar_preparo(segundos):
    """Os segundos de preparo de um pedido feito, para a estimativa dos próximos (os últimos PREPAROS_GUARDADOS)."""
    def alterar(dados):
        dados["preparos"] = (list(dados.get("preparos") or []) + [round(segundos)])[-PREPAROS_GUARDADOS:]
    _alterar(alterar)


def minutos_estimados(config, posicao):
    """
    Em quantos minutos fica pronto o pedido nesta posição da fila (1: o primeiro): a mediana do preparo dos últimos
    pedidos feitos, vezes a posição, arredondada para cima.
    """
    preparos = sorted(config.get("preparos") or []) or [PREPARO_PADRAO]
    return max(1, math.ceil(preparos[len(preparos) // 2] * max(1, posicao) / 60))


# --- O botão no grupo ---

def teclado_do_grupo():
    botao = InlineKeyboardButton(text=BOTAO_QUERO, callback_data=CALLBACK_QUERO)
    return InlineKeyboardMarkup(inline_keyboard=[[botao]])


def botao_liberar(ident):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=BOTAO_LIBERAR,
                                                                       callback_data=f"{CALLBACK_LIBERAR}{ident}")]])


def _menu_do_rafael(grupo):
    """O menu de comandos do bot (o / do campo de escrever) só do Rafael, só nesse grupo: os outros não veem."""
    return BotCommandScopeChatMember(chat_id=grupo, user_id=ADMIN_ID)


async def por_o_comando_no_menu(grupo, grupo_de_antes=None):
    """
    O /amigos no menu do grupo, visível só para o Rafael (P279 1); o do grupo de antes, quando o /amigos foi mandado
    em outro grupo, sai. O bot só sabe qual é o grupo depois do 1º /amigos. Devolve se o menu ficou certo.
    """
    try:
        if grupo_de_antes and grupo_de_antes != grupo:
            await bot_instance.delete_my_commands(scope=_menu_do_rafael(grupo_de_antes))
        await bot_instance.set_my_commands([BotCommand(command=COMANDO.lstrip("/"), description=DESCRICAO_DO_COMANDO)],
                                           scope=_menu_do_rafael(grupo))
    except Exception as e:
        logger.warning(f"⚠️ [Grupo dos Amigos] O /amigos não foi para o menu do grupo: {type(e).__name__}")
        registro_processos.registrar("shopee_video", PROCESSO_DO_PAINEL, "comando no menu", "não foi", ok=False)
        return False
    registro_processos.registrar("shopee_video", PROCESSO_DO_PAINEL, "comando no menu", "posto", ok=True)
    return True


async def conferir_o_comando_no_menu():
    """Na subida do bot: o grupo guardado tem o /amigos no menu do Rafael."""
    grupo = ler()["grupo"]
    if grupo:
        await por_o_comando_no_menu(grupo)


async def comando_amigos(message: types.Message):
    """
    O /amigos do Rafael num grupo: guarda o grupo, liga o grupo dos amigos e fixa a mensagem com o botão (mandado de
    novo, troca o botão: o de antes sai). O bot precisa ser administrador do grupo, com a permissão de fixar mensagens.
    """
    if message.from_user is None or message.from_user.id != ADMIN_ID:
        return
    grupo, antes = message.chat.id, ler()
    try:
        enviada = await bot_instance.send_message(grupo, TEXTO_DO_BOTAO, parse_mode="HTML",
                                                  reply_markup=teclado_do_grupo())
    except Exception as e:
        logger.warning(f"⚠️ [Grupo dos Amigos] O botão não saiu no grupo: {type(e).__name__}")
        registro_processos.registrar("shopee_video", PROCESSO_DO_PAINEL, "botão no grupo", "não saiu", ok=False)
        await bot_instance.send_message(ADMIN_ID, "⚠️ <b>Não consegui mandar o botão no grupo.</b> Confira se o bot "
                                                  "é administrador dele, com a permissão de mandar mensagens, e mande "
                                                  "/amigos lá de novo.", parse_mode="HTML")
        return

    def alterar(dados):
        dados.update(grupo=grupo, titulo=message.chat.title or "", ligado=True, botao=enviada.message_id)
    _alterar(alterar)
    if antes["botao"] and antes["grupo"]:
        try:
            await bot_instance.delete_message(antes["grupo"], antes["botao"])
        except Exception:
            pass    # o botão de antes já tinha saído, ou o bot não pode apagar: fica sem efeito (callback_do_grupo)
    try:
        await bot_instance.pin_chat_message(grupo, enviada.message_id, disable_notification=True)
        fixado = True
    except Exception as e:
        logger.warning(f"⚠️ [Grupo dos Amigos] O botão não foi fixado: {type(e).__name__}")
        fixado = False
    registro_processos.registrar("shopee_video", PROCESSO_DO_PAINEL, "botão no grupo",
                                 "fixado" if fixado else "sem fixar", ok=fixado)
    no_menu = await por_o_comando_no_menu(grupo, antes["grupo"])
    aviso = ("✅ <b>Grupo dos Amigos ligado neste grupo.</b> O botão está fixado; quando um amigo tocar nele, chega "
             f"aqui o nome dele com o {BOTAO_LIBERAR}, e ele espera em {BOTAO_LIBERAR_AMIGOS}, no painel." if fixado
             else "⚠️ <b>Grupo dos Amigos ligado neste grupo, mas o botão não foi fixado.</b> Nas configurações do "
                  "grupo, dê ao bot a permissão de fixar mensagens e mande /amigos lá de novo.")
    if no_menu:
        aviso += "\n📋 O /amigos ficou no menu do grupo (o / ao lado de onde se escreve), visível só para você."
    try:
        await bot_instance.send_message(ADMIN_ID, aviso, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"⚠️ [Grupo dos Amigos] O aviso do /amigos não chegou ao privado: {type(e).__name__}")


@router.callback_query(F.data == CALLBACK_QUERO)
async def quero_um_video(callback: types.CallbackQuery):
    """Toque em Quero um vídeo 🎬: o liberado entra na fila; quem não foi liberado é avisado, e o Rafael também."""
    config, usuario = ler(), callback.from_user
    if callback.message is None or callback.message.chat.id != config["grupo"]:
        await callback.answer("Este botão não vale mais.", show_alert=True)
        return
    if not config["ligado"]:
        await callback.answer("Os pedidos estão pausados agora. Tente mais tarde.", show_alert=True)
        return
    grupo, mencao, nome = config["grupo"], mencao_do_usuario(usuario), nome_do_usuario(usuario)
    if not do_rafael(usuario.id) and str(usuario.id) not in config["liberados"]:
        if not avisar_agora(usuario.id, nome):
            await callback.answer("Você ainda não foi liberado para pedir vídeos. O administrador já foi avisado.",
                                  show_alert=True)
            return
        await callback.answer()
        registro_processos.registrar("shopee_video", PROCESSO_DO_PEDIDO, "não liberado", "avisado no privado",
                                     ok=None)
        try:
            await bot_instance.send_message(grupo, f"⛔ {mencao}, você ainda não foi liberado para pedir vídeos. Já "
                                                   "avisei o administrador.", parse_mode="HTML")
            await bot_instance.send_message(
                ADMIN_ID, f"👥 <b>Grupo dos Amigos:</b> {mencao} ({html.escape(nome)}) tocou em {BOTAO_QUERO}, mas "
                          f"ainda não foi liberado. Toque em {BOTAO_LIBERAR} para ele poder pedir vídeos.",
                parse_mode="HTML", reply_markup=botao_liberar(usuario.id))
        except Exception as e:
            logger.warning(f"⚠️ [Grupo dos Amigos] O aviso de quem não foi liberado não saiu: {type(e).__name__}")
        return
    chave, posicao = entrar_na_fila(usuario)
    await callback.answer()
    registro_processos.registrar("shopee_video", PROCESSO_DO_PEDIDO, "na fila", ok=True)
    try:
        minutos = minutos_estimados(ler(), posicao)
        enviada = await bot_instance.send_message(grupo, f"⏳ {mencao}, estou preparando o seu vídeo ({posicao}º da "
                                                         f"fila). Fica pronto em cerca de {minutos} min. Ele chega "
                                                         "aqui, em resposta a esta mensagem.", parse_mode="HTML")
        anotar_mensagem_do_pedido(chave, enviada.message_id)
    except Exception as e:
        logger.warning(f"⚠️ [Grupo dos Amigos] O aviso do pedido não saiu: {type(e).__name__}")
    _atender_logo()


@router.callback_query(F.data.startswith(CALLBACK_LIBERAR))
async def liberar_amigo(callback: types.CallbackQuery):
    """O Liberar ✅ do aviso no privado do Rafael: quem tocou no botão do grupo passa a poder pedir."""
    if callback.from_user is None or callback.from_user.id != ADMIN_ID:
        return
    ident = callback.data[len(CALLBACK_LIBERAR):]
    if not ident.lstrip("-").isdigit():
        await callback.answer()
        return
    novo, nome = liberar(int(ident))
    registro_processos.registrar("shopee_video", PROCESSO_DO_PAINEL, "liberado" if novo else "já liberado", ok=True)
    await callback.answer("Liberado: já pode pedir vídeos no grupo." if novo else "Já estava liberado.")
    try:
        await callback.message.edit_text(f"✅ <b>Liberado:</b> {html.escape(nome)} já pode pedir vídeos no grupo dos "
                                         f"amigos. Para tirar, use {painel.BOTAO_GRUPO_DOS_AMIGOS} no painel da "
                                         "Shopee Vídeo.", parse_mode="HTML")
    except Exception:
        pass


# --- A fila ---

_atendendo = asyncio.Lock()
_tarefas = set()


def _atender_logo():
    """O pedido novo começa a ser feito na hora, sem esperar a volta do agendador."""
    tarefa = asyncio.create_task(atender_a_fila())
    _tarefas.add(tarefa)
    tarefa.add_done_callback(_tarefas.discard)


async def atender_a_fila():
    """
    Volta do agendador e de cada pedido novo: atende os pedidos da fila, um de cada vez, na ordem. O pedido sai da
    fila depois de feito (o que um reinício corta no meio é feito de novo na volta). Com o grupo desligado, a fila
    espera.
    """
    if _atendendo.locked():
        return
    async with _atendendo:
        while True:
            config = ler()
            if not config["ligado"] or not config["grupo"] or not config["fila"]:
                return
            pedido = config["fila"][0]
            try:
                if str(pedido["id"]) in config["liberados"] or do_rafael(pedido["id"]):
                    await _atender(config, pedido)
            except Exception as e:
                logger.error(f"❌ [Grupo dos Amigos] Erro ao atender o pedido: {type(e).__name__}")
            sair_da_fila(pedido["chave"])


async def _atender(config, pedido):
    """
    Prepara e manda o vídeo do pedido. Um envio de cada vez com o assistente do Rafael (o mesmo cadeado do painel):
    os dois pegariam o mesmo vídeo da fonte. O pedido do Rafael é como o Enviar 1 Agora 📤 (as regras do assistente
    dele): o vídeo vai ao privado, com o Postei ✅, e o mesmo vídeo ao grupo, em resposta ao pedido (P281 1).
    """
    amigo = {"id": pedido["id"], "mencao": pedido["mencao"], "grupo": config["grupo"],
             "responder_a": pedido.get("mensagem")}
    comeco = time.monotonic()
    async with painel._envio:
        try:
            config_do_painel = painel.ler_config()
            if do_rafael(pedido["id"]):
                resultado = await assistente.preparar_e_enviar(bot_instance, ADMIN_ID, fonte=config_do_painel["fonte"],
                                                               cobrindo=painel.cobrindo_o_robo(config_do_painel),
                                                               no_grupo=amigo)
            else:
                resultado = await assistente.preparar_para_o_amigo(bot_instance, ADMIN_ID, amigo,
                                                                   fonte=config_do_painel["fonte"])
        except Exception as e:
            logger.error(f"❌ [Grupo dos Amigos] Erro ao preparar o vídeo: {type(e).__name__}")
            resultado = ""
    if resultado in (assistente.MANDADO_AO_AMIGO, assistente.MANDADO_NO_PRIVADO):
        anotar_preparo(time.monotonic() - comeco)
        logger.info("👥 [Grupo dos Amigos] Vídeo mandado no grupo.")
        return
    sem_video = resultado == assistente.SEM_VIDEO_PARA_O_AMIGO or resultado.startswith(assistente.SEM_VIDEO_NO_ENVIO)
    texto = SEM_VIDEO if sem_video else NAO_SAIU
    try:
        await bot_instance.send_message(config["grupo"], texto.format(mencao=pedido["mencao"]), parse_mode="HTML",
                                        reply_parameters=assistente._em_resposta_a(pedido.get("mensagem")))
    except Exception as e:
        logger.warning(f"⚠️ [Grupo dos Amigos] A resposta do pedido não saiu: {type(e).__name__}")


# --- O painel (Shopee Vídeo 🎬 → Grupo dos Amigos 👥) ---

def _admin(message):
    return message.from_user is not None and message.from_user.id == ADMIN_ID


def texto_do_painel(config, agora=None):
    if not config["grupo"]:
        status = "⚠️ <b>Sem grupo</b> (mande /amigos no grupo dos amigos)"
    elif config["ligado"]:
        status = "▶️ <b>Ligado</b>"
    else:
        status = "⏸️ <b>Desligado</b> (o botão do grupo avisa que os pedidos estão pausados, e a fila espera)"
    grupo = (links_grupos.nome_clicavel(config["titulo"] or "o grupo", config["grupo"]) if config["grupo"]
             else "nenhum")
    hoje, total = assistente.enviados_aos_amigos(agora)
    nomes = [html.escape(dados.get("nome") or ident) for ident, dados in config["liberados"].items()]
    liberados = "\n".join(f"{n}. {nome}" for n, nome in enumerate(nomes, 1)) or "ninguém ainda"
    return (
        f"👥 <b>{painel.BOTAO_GRUPO_DOS_AMIGOS}</b>\n"
        f"Os amigos que você libera pedem, no grupo, um vídeo pronto para postar na Shopee Vídeo deles: cada toque em "
        f"{BOTAO_QUERO} é um pedido, e eu faço um de cada vez, na ordem, com um vídeo da sua Fonte dos Vídeos, editado "
        "como os do assistente. Nenhum vídeo vai a duas pessoas (nem a você), e o produto que um amigo já recebeu não "
        "volta para ele. O seu robô e o assistente continuam como estão. Você também pode pedir pelo botão, sem se "
        "liberar: o seu vídeo é preparado como o Enviar 1 Agora 📤 e vai ao seu privado, com o Postei ✅, e ao "
        "grupo. A mensagem de cada pedido diz em quanto tempo o vídeo fica pronto.\n\n"
        f"Status: {status}\n"
        f"💬 Grupo: {grupo}\n"
        f"⏳ Pedidos na fila: <b>{len(config['fila'])}</b>\n"
        f"📤 Vídeos mandados no grupo: hoje <b>{hoje}</b>, no total <b>{total}</b>\n"
        f"🙋 Esperando a liberação: <b>{len(pendentes(config))}</b>\n"
        f"✅ Liberados ({len(nomes)}):\n{liberados}\n\n"
        "<b>O que cada botão faz</b>\n"
        f"▶️ <b>{BOTAO_LIGAR}</b> / ⏸️ <b>{BOTAO_DESLIGAR}</b>: volta a atender ou pausa os pedidos do grupo.\n"
        f"✅ <b>{BOTAO_LIBERAR_AMIGOS}</b>: um botão com o nome de cada um que tocou em {BOTAO_QUERO} e ainda não "
        "foi liberado; o toque no nome libera, e ele sai da lista. O aviso de cada um no privado, com o "
        f"{BOTAO_LIBERAR}, continua.\n"
        f"➖ <b>{BOTAO_TIRAR}</b>: escolha quem não pode mais pedir (os pedidos dele na fila saem).\n"
        f"🔙 <b>{painel.BOTAO_VOLTAR}</b>: volta à tela da Shopee Vídeo.\n\n"
        "Para pôr o botão no grupo: mande /amigos lá (o bot precisa ser administrador, com a permissão de fixar "
        "mensagens). Depois do 1º, o /amigos fica no menu do grupo (o / ao lado de onde se escreve), visível só para "
        "você."
    )


def rotulo_liberar(config):
    """O botão do painel, com quantos esperam a liberação."""
    esperando = len(pendentes(config))
    return f"{BOTAO_LIBERAR_AMIGOS} ({esperando})" if esperando else BOTAO_LIBERAR_AMIGOS


def teclado_do_painel(config):
    liga = BOTAO_DESLIGAR if config["ligado"] else BOTAO_LIGAR
    return montar_teclado([
        [KeyboardButton(text=liga), KeyboardButton(text=rotulo_liberar(config))],
        [KeyboardButton(text=BOTAO_TIRAR), KeyboardButton(text=painel.BOTAO_VOLTAR)],
    ])


async def mostrar_painel(message: types.Message, state: FSMContext):
    await state.set_state(AmigosFluxo.menu)
    config = ler()
    await message.answer(texto_do_painel(config), parse_mode="HTML", reply_markup=teclado_do_painel(config),
                         disable_web_page_preview=True)


@router.message(F.text == painel.BOTAO_GRUPO_DOS_AMIGOS, StateFilter("*"))
async def grupo_dos_amigos_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await mostrar_painel(message, state)


@router.message(F.text.in_([BOTAO_LIGAR, BOTAO_DESLIGAR]), StateFilter("*"))
async def ligar_ou_desligar(message: types.Message, state: FSMContext):
    if not _admin(message): return
    ligado = message.text == BOTAO_LIGAR
    if ligado and not ler()["grupo"]:
        await message.answer("⚠️ Ainda não há grupo: mande /amigos no grupo dos amigos (o bot precisa ser "
                             "administrador dele).")
        await mostrar_painel(message, state)
        return

    def alterar(dados):
        dados["ligado"] = ligado
    _alterar(alterar)
    registro_processos.registrar("shopee_video", PROCESSO_DO_PAINEL, "ligado" if ligado else "desligado", ok=True)
    await message.answer("▶️ Grupo dos Amigos <b>ligado</b>: os pedidos voltam a ser atendidos." if ligado else
                         "⏸️ Grupo dos Amigos <b>desligado</b>: o botão do grupo avisa que os pedidos estão pausados, "
                         "e a fila espera você ligar de novo.", parse_mode="HTML")
    if ligado:
        _atender_logo()
    await mostrar_painel(message, state)


def teclado_tirar(config):
    nomes = [dados.get("nome") or ident for ident, dados in config["liberados"].items()]
    linhas = [[KeyboardButton(text=f"{n}. {nome}"[:60])] for n, nome in enumerate(nomes, 1)]
    return montar_teclado(linhas + [[KeyboardButton(text="Cancelar ❌")]])


@router.message(F.text == BOTAO_TIRAR, StateFilter("*"))
async def pedir_quem_tirar(message: types.Message, state: FSMContext):
    if not _admin(message): return
    config = ler()
    if not config["liberados"]:
        await message.answer("Ninguém está liberado ainda.")
        await mostrar_painel(message, state)
        return
    await state.set_state(AmigosFluxo.tirando)
    await message.answer("➖ Quem não pode mais pedir vídeos? Toque no nome.", reply_markup=teclado_tirar(config))


@router.message(AmigosFluxo.tirando)
async def tirar_amigo(message: types.Message, state: FSMContext):
    if not _admin(message): return
    config = ler()
    numero = (message.text or "").split(".", 1)[0].strip()
    idents = list(config["liberados"])
    if not numero.isdigit() or not 1 <= int(numero) <= len(idents):
        await message.answer("Toque num dos nomes ou em Cancelar ❌.", reply_markup=teclado_tirar(config))
        return
    nome = tirar(idents[int(numero) - 1])
    registro_processos.registrar("shopee_video", PROCESSO_DO_PAINEL, "tirado", ok=True)
    await message.answer(f"➖ {html.escape(nome)} não pode mais pedir vídeos (os pedidos dele na fila saíram).",
                         parse_mode="HTML")
    await mostrar_painel(message, state)


# --- Liberar Amigos ✅ (P279 1) ---

def _botoes_dos_pendentes(config):
    """{texto do botão: id} de quem espera a liberação, numerados (dois nomes iguais ficam em botões diferentes)."""
    return {f"{n}. {nome}"[:60]: ident for n, (ident, nome) in enumerate(pendentes(config).items(), 1)}


def teclado_liberar(config):
    linhas = [[KeyboardButton(text=texto)] for texto in _botoes_dos_pendentes(config)]
    return montar_teclado(linhas + [[KeyboardButton(text=BOTAO_VOLTAR_AMIGOS)]])


@router.message(F.text.startswith(BOTAO_LIBERAR_AMIGOS), StateFilter("*"))
async def pedir_quem_liberar(message: types.Message, state: FSMContext):
    if not _admin(message): return
    config = ler()
    if not pendentes(config):
        await message.answer(f"Ninguém esperando a liberação agora. Quando alguém tocar em {BOTAO_QUERO} sem estar "
                             "liberado, o nome aparece aqui.")
        await mostrar_painel(message, state)
        return
    await state.set_state(AmigosFluxo.liberando)
    await message.answer("✅ Quem pode pedir vídeos? Toque no nome: ele é liberado e sai da lista.",
                         reply_markup=teclado_liberar(config))


@router.message(F.text == BOTAO_VOLTAR_AMIGOS, StateFilter("*"))
async def voltar_ao_grupo_dos_amigos(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await mostrar_painel(message, state)


@router.message(AmigosFluxo.liberando)
async def liberar_da_lista(message: types.Message, state: FSMContext):
    """O toque num nome do Liberar Amigos ✅: libera, e a lista volta sem ele (vazia, volta ao painel)."""
    if not _admin(message): return
    config = ler()
    ident = _botoes_dos_pendentes(config).get(message.text or "")
    if ident is None:
        await message.answer(f"Toque num dos nomes ou em {BOTAO_VOLTAR_AMIGOS}.", reply_markup=teclado_liberar(config))
        return
    novo, nome = liberar(ident)
    registro_processos.registrar("shopee_video", PROCESSO_DO_PAINEL, "liberado" if novo else "já liberado",
                                 "pelo painel", ok=True)
    await message.answer(f"✅ <b>Liberado:</b> {html.escape(nome)} já pode pedir vídeos no grupo.", parse_mode="HTML")
    config = ler()
    if pendentes(config):
        await message.answer("Quem mais? Toque no nome.", reply_markup=teclado_liberar(config))
        return
    await message.answer("Ninguém mais esperando a liberação.")
    await mostrar_painel(message, state)
