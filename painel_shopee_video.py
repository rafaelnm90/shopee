"""
Painel da Shopee Vídeo: roteador do bot_mestre (Outros Canais → Shopee Vídeo 🎬).

O robô da Shopee Vídeo posta os vídeos dos Autorais, com o produto vinculado, pelo
app da Shopee num Android virtual no servidor (android_virtual.py). Este painel
guarda o que o Rafael controla, na chave "shopee_video" das configurações:
- se o robô está pausado;
- quantos vídeos por dia: uma faixa (ex.: 5 a 10), sorteada a cada dia;
- a janela de horário em que os vídeos se espalham (ex.: das 13h às 22h).
O motor que posta lê essa mesma chave. O painel também reúne o acesso ao Android:
o botão da tela no navegador (handler no bot_mestre) e o tutorial da instalação.
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import logging
import re
from datetime import datetime

from aiogram import Router, Bot, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

import db
from fuso import fuso_horario
from motor_filas import sortear_teto_do_dia

logger = logging.getLogger("ShopeeVideo")

router = Router()
bot_instance = None
scheduler_instance = None
ADMIN_ID = None

CHAVE_CONFIG = "shopee_video"
# Começa pausado: o robô posta na conta principal do Rafael e só liga quando ele mandar.
PADRAO = {"pausado": True, "limite_min": 5, "limite_max": 10, "inicio": 13, "fim": 22}
MAXIMO_POR_DIA = 50


def configurar_dependencias(bot: Bot, scheduler, admin_id):
    global bot_instance, scheduler_instance, ADMIN_ID
    bot_instance, scheduler_instance, ADMIN_ID = bot, scheduler, admin_id


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
            [KeyboardButton(text=pausa)],
            [KeyboardButton(text="Tela do Android 📱"), KeyboardButton(text="Tutorial do Android 📖")],
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
        "🎬 <b>Shopee Vídeo</b>\n"
        "Posta os vídeos dos Autorais, com o produto vinculado, pelo app da Shopee no Android virtual.\n\n"
        f"Status: {status}\n"
        f"📦 Vídeos por dia: <b>{rotulo_faixa(piso, topo)}</b>{hoje}\n"
        f"⏰ Horário de postagem: <b>{rotulo_janela(config['inicio'], config['fim'])}</b>\n\n"
        "🚧 <i>Robô em construção: ainda não posta. O que você ajustar aqui já vale quando ele começar.</i>"
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
        "Em que horário os vídeos podem ser postados? Eles se espalham dentro dessa faixa.\n\n"
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
    pergunta = ("⚠️ <b>Pausar</b> o robô da Shopee Vídeo? Ele para de postar até você retomar."
                if pausar else
                "▶️ <b>Retomar</b> o robô da Shopee Vídeo? Ele volta a postar na sua conta, "
                "dentro do horário e da quantidade do painel.")
    botao = "Confirmar Pausa ✅" if pausar else "Confirmar Retomada ✅"
    teclado = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=botao), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True, is_persistent=True)
    await message.answer(pergunta, parse_mode="HTML", reply_markup=teclado)
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_pausa)



# --- Tutorial ---

# Passo a passo para instalar a Shopee no Android virtual, para quando o Rafael
# precisar de novo (reset de fábrica, atualização da Shopee, login que caiu) e
# ninguém lembrar como foi. Cada parte cabe numa mensagem do Telegram (4096 caracteres).
TUTORIAL_ANDROID = (
    "📖 <b>Tutorial do Android da Shopee Vídeo (1/4)</b>\n\n"
    "O robô da Shopee Vídeo usa um celular Android virtual, que roda dentro do servidor. "
    "Nele ficam o app da Shopee Brasil e o login da sua conta.\n\n"
    "<b>Quando usar este passo a passo:</b>\n"
    "• na primeira vez, ou depois de um \"Resetar de fábrica\";\n"
    "• quando a Shopee pedir atualização;\n"
    "• quando o login da Shopee cair.\n\n"
    "<b>Por que o app vem do seu celular:</b> a Play Store e os sites de APK recusam o servidor. "
    "Então você instala a Shopee no seu celular, faz uma cópia dela com o app SAI e envia a cópia "
    "para o Android virtual.\n\n"
    "São duas etapas: <b>2/4</b> no seu celular e <b>3/4</b> no Android virtual. "
    "A <b>4/4</b> traz os problemas mais comuns.",

    "📱 <b>2/4: no seu celular, copiar a Shopee com o SAI</b>\n\n"
    "1. Na Play Store, instale ou atualize a <b>Shopee</b>. Abra uma vez e confira que está em português, "
    "com preços em R$.\n"
    "2. Instale o <b>SAI (Split APKs Installer)</b>:\n"
    "https://play.google.com/store/apps/details?id=com.mtv.sai\n"
    "3. Abra o SAI e toque na aba <b>Backup</b>, embaixo.\n"
    "4. Na primeira vez, ele pede a pasta dos backups. O Android não deixa usar a pasta principal nem a "
    "Download, então: toque em <b>CRIAR NOVA PASTA</b>, dê o nome <b>Backups</b>, toque em OK, entre nela "
    "e toque em <b>USAR ESTA PASTA</b> → <b>Permitir</b>.\n"
    "5. Na lista de apps, toque em <b>Shopee</b> → <b>Backup</b>. O SAI pode pedir a assinatura PRO "
    "para fazer o backup (em 04/10/2026 foi preciso assinar).\n"
    "6. Espere terminar: aparece um arquivo terminado em <b>.apks</b> (uns 120 MB) na pasta Backups. "
    "Guarde esse arquivo: ele serve de novo se precisar.\n"
    "7. Se assinou o PRO, cancele depois para não ser cobrado de novo: Play Store → foto do perfil → "
    "<b>Pagamentos e assinaturas</b> → <b>Assinaturas</b> → SAI → <b>Cancelar assinatura</b>.\n\n"
    "⚠️ Não use o \"Compartilhar\" do SAI: ele manda só uma parte da Shopee, e o Android recusa.",

    "🤖 <b>3/4: no Android virtual, instalar e entrar</b>\n\n"
    "1. Aqui no bot: <b>Outros Canais 🗂️</b> → <b>Shopee Vídeo 🎬</b> → <b>Tela do Android 📱</b>. "
    "O link chega aqui em até 1 min. Abra no navegador do celular. A tela fica aberta 30 min.\n"
    "2. Na página, toque em <b>Escolher arquivo</b> → pasta <b>Backups</b> → o arquivo .apks da Shopee "
    "→ <b>📦 Enviar app</b>.\n"
    "3. Deixe a página aberta. Aparece \"Enviando... %\" (pode levar alguns minutos), depois "
    "\"Instalando no Android...\" e, no fim, \"✅ app da Shopee: instalado\".\n"
    "4. Na imagem do Android, toque em <b>● Início</b>, abra a <b>Shopee</b> e entre com a sua conta principal:\n"
    "• para escrever (e-mail, senha, código), toque no campo dentro da imagem, escreva em "
    "<b>Texto para digitar</b> e toque em <b>Digitar</b>;\n"
    "• no quebra-cabeça de segurança, arraste o dedo sobre a imagem.\n"
    "5. Quando terminar, toque em <b>✅ Terminei</b>. O link para de funcionar, e ninguém mais mexe no Android por ele.",

    "🛠️ <b>4/4: problemas comuns</b>\n\n"
    "• <b>A imagem não aparece</b> (\"⏳ Esperando a imagem do Android\"): se o Android acabou de "
    "reiniciar ou resetar, espere de 1 a 4 min. Se não voltar, toque em Tela do Android 📱 de novo.\n"
    "• <b>\"Error 1033\" ao abrir o link:</b> a tela já fechou (Terminei, 30 min ou uma tela nova no lugar). "
    "Peça outra em Tela do Android 📱.\n"
    "• <b>\"❌ o Android recusou o app\":</b> a mensagem diz o motivo. O mais comum é arquivo antigo ou da "
    "Shopee de outro país: refaça a parte 2/4 com a Shopee Brasil atualizada.\n"
    "• <b>Arquivo .apkm</b> (do APKMirror) não serve: só .apks, .xapk ou .apk.\n"
    "• <b>A Shopee pediu atualização:</b> atualize no celular, faça um backup novo no SAI e envie o arquivo "
    "novo. O login continua, porque a instalação vai por cima.\n"
    "• <b>A tela fechou no meio:</b> o bot pode ter reiniciado numa atualização. Toque em Tela do Android 📱 de novo.\n\n"
    "<b>Botões da página:</b>\n"
    "• <b>🧹 Fechar apps:</b> fecha todos os apps e limpa a lista de recentes.\n"
    "• <b>🔄 Reiniciar Android:</b> religa o Android. Os apps e o login continuam (volta em 1 a 2 min).\n"
    "• <b>🗑️ Resetar de fábrica:</b> apaga TUDO, inclusive a Shopee e o login. Depois é preciso refazer "
    "a parte 3/4. Use só se o Android estiver muito travado.",
)


@router.message(F.text == "Tutorial do Android 📖", StateFilter("*"))
async def tutorial_android_handler(message: types.Message, state: FSMContext):
    """Manda o passo a passo da instalação da Shopee no Android virtual, em partes."""
    if not _admin(message): return
    logger.info("📖 Mostrando o tutorial do Android.")
    for parte in TUTORIAL_ANDROID:
        await message.answer(parte, parse_mode="HTML", disable_web_page_preview=True)


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
