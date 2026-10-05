"""
Painel da Shopee Vídeo: roteador do bot_mestre (Outros Canais → Shopee Vídeo 🎬).

Modo assistente: o robô prepara cada postagem (vídeo dos Autorais, título pela IA,
produtos e comentário) e manda no privado do Rafael, que posta pelo próprio celular
(assistente_shopee_video.py). Este painel guarda o que o Rafael controla, na chave
"shopee_video" das configurações:
- se o robô está pausado;
- quantos vídeos por dia: uma faixa (ex.: 5 a 10), sorteada a cada dia;
- a janela de horário em que os envios se espalham (ex.: das 13h às 22h).
Também liga o envio no agendador (a cada 5 min vê se chegou a hora) e tem o botão
"Enviar 1 Agora 📤", que manda uma postagem na hora, mesmo pausado.
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import asyncio
import logging
import re
from datetime import datetime

from aiogram import Router, Bot, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

import assistente_shopee_video as assistente
import db
from fuso import fuso_horario
from motor_filas import sortear_teto_do_dia

logger = logging.getLogger("ShopeeVideo")

router = Router()
bot_instance = None
scheduler_instance = None
ADMIN_ID = None

CHAVE_CONFIG = "shopee_video"
# Começa pausado: só manda postagens quando o Rafael retomar no painel.
PADRAO = {"pausado": True, "limite_min": 5, "limite_max": 10, "inicio": 13, "fim": 22}
MAXIMO_POR_DIA = 50


def configurar_dependencias(bot: Bot, scheduler, admin_id):
    global bot_instance, scheduler_instance, ADMIN_ID
    bot_instance, scheduler_instance, ADMIN_ID = bot, scheduler, admin_id
    scheduler.add_job(verificar_envio, "interval", minutes=5, id="shopee_video_assistente",
                      replace_existing=True, max_instances=1, coalesce=True)


# Um envio de cada vez: o agendador e o botão Enviar 1 Agora pegariam o mesmo vídeo.
_envio = asyncio.Lock()


async def enviar_um():
    """Prepara e manda uma postagem no privado. Devolve o que aconteceu, numa frase."""
    async with _envio:
        try:
            return await assistente.preparar_e_enviar(bot_instance, ADMIN_ID)
        except Exception as e:
            logger.error(f"❌ [Shopee Vídeo] Erro ao preparar a postagem: {type(e).__name__}: {e}")
            return f"deu erro ao preparar ({type(e).__name__})"


async def verificar_envio():
    """Volta do agendador: manda um vídeo se um horário do plano de hoje já passou."""
    if _envio.locked() or not assistente.decidir_envio(ler_config()):
        return
    logger.info(f"🎬 [Shopee Vídeo] {await enviar_um()}.")


def _admin(message):
    return message.from_user is not None and message.from_user.id == ADMIN_ID


class ShopeeVideoFluxo(StatesGroup):
    menu = State()
    aguardando_faixa = State()
    aguardando_confirmacao_faixa = State()
    aguardando_janela = State()
    aguardando_confirmacao_janela = State()
    aguardando_confirmacao_pausa = State()


# --- Configuração ---

def ler_config():
    """A configuração do robô, com os valores padrão no que faltar."""
    return {**PADRAO, **db.ler_config(CHAVE_CONFIG, {})}


def alterar_config(**mudancas):
    """Grava só as chaves mudadas, sem apagar o que o motor tiver gravado na mesma chave."""
    def alterar(dados):
        dados.update(mudancas)
    db.atualizar_config(CHAVE_CONFIG, alterar)


def interpretar_faixa(texto):
    """"6" (fixo) ou "5-10" (faixa) → (piso, topo); None se não serve."""
    casou = re.match(r"^(\d{1,3})(?:\s*-\s*(\d{1,3}))?$", (texto or "").strip())
    if not casou:
        return None
    piso = int(casou.group(1))
    topo = int(casou.group(2)) if casou.group(2) else piso
    if piso < 1 or topo < piso or topo > MAXIMO_POR_DIA:
        return None
    return piso, topo


def interpretar_janela(texto):
    """"13-22" ou "Dia Todo" → (inicio, fim) em horas; None se não serve."""
    texto = (texto or "").strip()
    if texto == "Dia Todo (24h) 🕛" or texto.lower() == "dia todo":
        return 0, 24
    casou = re.match(r"^(\d{1,2})\s*-\s*(\d{1,2})$", texto)
    if not casou:
        return None
    inicio, fim = map(int, casou.groups())
    if not 0 <= inicio < fim <= 24:
        return None
    return inicio, fim


def rotulo_faixa(piso, topo):
    return f"{piso} a {topo}" if topo > piso else f"{piso} (fixo)"


def rotulo_janela(inicio, fim):
    return "o dia todo (24h)" if (inicio, fim) == (0, 24) else f"das {inicio}h às {fim}h"


def videos_hoje(config, agora=None):
    """Quantos vídeos o dia de hoje sorteou dentro da faixa (o mesmo número o dia inteiro)."""
    dia = (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d")
    return sortear_teto_do_dia(CHAVE_CONFIG, dia, config["limite_min"], config["limite_max"])


# --- Painel ---

def teclado_painel(config):
    pausa = "Retomar Robô ▶️" if config["pausado"] else "Pausar Robô ⏸️"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Vídeos por Dia 📦"), KeyboardButton(text="Horário de Postagem ⏰")],
            [KeyboardButton(text=pausa), KeyboardButton(text="Enviar 1 Agora 📤")],
            [KeyboardButton(text="Voltar aos Canais 🔙")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


teclado_cancelar = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Cancelar ❌")]], resize_keyboard=True, is_persistent=True)

teclado_janela = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Dia Todo (24h) 🕛")], [KeyboardButton(text="Cancelar ❌")]],
    resize_keyboard=True, is_persistent=True)

teclado_aprovar = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
    resize_keyboard=True, is_persistent=True)


def texto_painel(config, agora=None):
    status = "⏸️ <b>Pausado</b>" if config["pausado"] else "▶️ <b>Ativo</b>"
    piso, topo = config["limite_min"], config["limite_max"]
    hoje = f" (sorteado a cada dia; hoje: <b>{videos_hoje(config, agora)}</b>)" if topo > piso else ""
    return (
        "🎬 <b>Shopee Vídeo</b> (modo assistente)\n"
        "Prepara as postagens dos Autorais (vídeo, título, produtos e comentário) e manda aqui no "
        "seu privado, para você postar pelo seu celular.\n\n"
        f"Status: {status}\n"
        f"📦 Vídeos por dia: <b>{rotulo_faixa(piso, topo)}</b>{hoje}\n"
        f"⏰ Horário dos envios: <b>{rotulo_janela(config['inicio'], config['fim'])}</b>\n"
        f"📤 Mandados hoje: <b>{assistente.enviados_hoje(agora)}</b>\n\n"
        "<i>Enviar 1 Agora 📤 manda uma postagem na hora, mesmo pausado.</i>"
    )


async def mostrar_painel(message: types.Message, state: FSMContext):
    await state.set_state(ShopeeVideoFluxo.menu)
    config = ler_config()
    await message.answer(texto_painel(config), parse_mode="HTML", reply_markup=teclado_painel(config))


# Os botões do painel funcionam em qualquer estado (StateFilter("*")): depois de um
# reinício o estado do FSM some, mas o teclado continua na tela do Rafael.
@router.message(F.text == "Shopee Vídeo 🎬", StateFilter("*"))
async def painel_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    logger.info("🎬 Acessando o painel da Shopee Vídeo.")
    await mostrar_painel(message, state)


# --- Vídeos por dia ---

@router.message(F.text == "Vídeos por Dia 📦", StateFilter("*"))
async def pedir_faixa(message: types.Message, state: FSMContext):
    if not _admin(message): return
    config = ler_config()
    await message.answer(
        "Quantos vídeos por dia?\n\n"
        "• Faixa: <code>5-10</code>: cada dia sorteia um número entre 5 e 10\n"
        "• Fixo: <code>6</code>: sempre 6 por dia\n\n"
        f"<i>Hoje está em {rotulo_faixa(config['limite_min'], config['limite_max'])}. "
        f"Máximo de {MAXIMO_POR_DIA} por dia. A faixa existe para a quantidade não ser sempre igual, "
        "que é o que denuncia robô.</i>",
        parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(ShopeeVideoFluxo.aguardando_faixa)



# --- Horário de postagem ---

@router.message(F.text == "Horário de Postagem ⏰", StateFilter("*"))
async def pedir_janela(message: types.Message, state: FSMContext):
    if not _admin(message): return
    config = ler_config()
    await message.answer(
        "Em que horário as postagens podem chegar? Elas se espalham dentro dessa faixa.\n\n"
        "Envie <code>início-fim</code> (ex.: <code>13-22</code>) ou toque em Dia Todo.\n"
        f"<i>Hoje está {rotulo_janela(config['inicio'], config['fim'])}.</i>",
        parse_mode="HTML", reply_markup=teclado_janela)
    await state.set_state(ShopeeVideoFluxo.aguardando_janela)



# --- Pausa ---

@router.message(F.text.in_(["Pausar Robô ⏸️", "Retomar Robô ▶️"]), StateFilter("*"))
async def pedir_pausa(message: types.Message, state: FSMContext):
    if not _admin(message): return
    pausar = message.text.startswith("Pausar")
    await state.update_data(pausar=pausar)
    pergunta = ("⚠️ <b>Pausar</b> o robô da Shopee Vídeo? Ele para de mandar postagens até você retomar."
                if pausar else
                "▶️ <b>Retomar</b> o robô da Shopee Vídeo? Ele volta a mandar as postagens aqui no seu "
                "privado, dentro do horário e da quantidade do painel.")
    botao = "Confirmar Pausa ✅" if pausar else "Confirmar Retomada ✅"
    teclado = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=botao), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True, is_persistent=True)
    await message.answer(pergunta, parse_mode="HTML", reply_markup=teclado)
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_pausa)



# --- Enviar 1 agora ---

@router.message(F.text == "Enviar 1 Agora 📤", StateFilter("*"))
async def enviar_agora_handler(message: types.Message, state: FSMContext):
    """Manda uma postagem na hora, mesmo pausado (para testar ou para postar mais uma)."""
    if not _admin(message): return
    if _envio.locked():
        await message.answer("⏳ Já estou preparando uma postagem. Ela chega em instantes.")
        return
    logger.info("📤 Shopee Vídeo: Enviar 1 Agora.")
    await message.answer("⏳ Preparando a postagem: a IA assiste ao vídeo e escreve o texto (1 a 2 min).")
    resultado = await enviar_um()
    if resultado != "postagem mandada no seu privado":
        await message.answer(f"⚠️ Não mandei: {resultado}.")


# --- Respostas dentro de cada ajuste ---
# Ficam depois de todos os botões: no aiogram ganha o primeiro handler que casar, e um
# botão do painel tocado no meio de um ajuste tem de abrir o botão, não virar resposta.

@router.message(ShopeeVideoFluxo.aguardando_faixa)
async def confirmar_faixa(message: types.Message, state: FSMContext):
    faixa = interpretar_faixa(message.text)
    if not faixa:
        await message.answer(
            f"⚠️ Envie um número (<code>6</code>) ou uma faixa (<code>5-10</code>), de 1 a {MAXIMO_POR_DIA}.",
            parse_mode="HTML", reply_markup=teclado_cancelar)
        return
    piso, topo = faixa
    await state.update_data(faixa=[piso, topo])
    await message.answer(f"Definir <b>{rotulo_faixa(piso, topo)}</b> vídeos por dia?",
                         parse_mode="HTML", reply_markup=teclado_aprovar)
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_faixa)


@router.message(ShopeeVideoFluxo.aguardando_confirmacao_faixa, F.text == "Aprovar ✅")
async def salvar_faixa(message: types.Message, state: FSMContext):
    piso, topo = (await state.get_data())["faixa"]
    alterar_config(limite_min=piso, limite_max=topo)
    logger.info(f"✅ Shopee Vídeo: {piso} a {topo} vídeos por dia.")
    await message.answer(f"✅ Vídeos por dia: <b>{rotulo_faixa(piso, topo)}</b>.", parse_mode="HTML")
    await mostrar_painel(message, state)


@router.message(ShopeeVideoFluxo.aguardando_janela)
async def confirmar_janela(message: types.Message, state: FSMContext):
    janela = interpretar_janela(message.text)
    if not janela:
        await message.answer(
            "⚠️ Use o formato <code>13-22</code>, com o início menor que o fim (de 0 a 24).",
            parse_mode="HTML", reply_markup=teclado_janela)
        return
    inicio, fim = janela
    await state.update_data(janela=[inicio, fim])
    await message.answer(f"Postar <b>{rotulo_janela(inicio, fim)}</b>?", parse_mode="HTML", reply_markup=teclado_aprovar)
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_janela)


@router.message(ShopeeVideoFluxo.aguardando_confirmacao_janela, F.text == "Aprovar ✅")
async def salvar_janela(message: types.Message, state: FSMContext):
    inicio, fim = (await state.get_data())["janela"]
    alterar_config(inicio=inicio, fim=fim)
    logger.info(f"✅ Shopee Vídeo: janela {inicio}h-{fim}h.")
    await message.answer(f"✅ Horário de postagem: <b>{rotulo_janela(inicio, fim)}</b>.", parse_mode="HTML")
    await mostrar_painel(message, state)


@router.message(ShopeeVideoFluxo.aguardando_confirmacao_pausa,
                F.text.in_(["Confirmar Pausa ✅", "Confirmar Retomada ✅"]))
async def salvar_pausa(message: types.Message, state: FSMContext):
    pausar = message.text == "Confirmar Pausa ✅"
    alterar_config(pausado=pausar)
    logger.info(f"✅ Shopee Vídeo {'pausado' if pausar else 'retomado'}.")
    await message.answer("⏸️ Robô da Shopee Vídeo <b>pausado</b>." if pausar
                         else "▶️ Robô da Shopee Vídeo <b>retomado</b>.", parse_mode="HTML")
    await mostrar_painel(message, state)


@router.message(StateFilter(ShopeeVideoFluxo.aguardando_confirmacao_faixa,
                            ShopeeVideoFluxo.aguardando_confirmacao_janela,
                            ShopeeVideoFluxo.aguardando_confirmacao_pausa))
async def confirmar_com_os_botoes(message: types.Message, state: FSMContext):
    await message.answer("Toque em um dos botões para confirmar ou em Cancelar ❌.")
