"""
Painel da Shopee Vídeo: roteador do bot_mestre (Outros Canais → Shopee Vídeo 🎬).

Dois robôs, cada um com o seu botão de pausar e retomar:
- o modo assistente prepara cada postagem (vídeo, título pela IA, produtos e
  comentário) e manda no privado do Rafael, que posta pelo próprio celular
  (assistente_shopee_video.py);
- o robô automático prepara rascunhos sozinho no celular guardado e posta os que o
  Rafael aprova aqui, um por um, em "Rascunhos do Robô 📝" (robo_shopee_video.py).
Os dois puxam da mesma Fonte dos Vídeos, e o vídeo que um usou o outro não pega.

Este painel guarda o que o Rafael controla, na chave "shopee_video" das configurações:
- assistente: pausa, quantos vídeos por dia (faixa sorteada a cada dia) e a janela de
  horário dos envios;
- robô automático (chaves robo_*): pausa, quantos rascunhos por dia (faixa) e o Horário
  do Robô, em que ele toca no celular e posta;
- de onde vêm os vídeos (Autorais, Viral, Canal Afiliados ou Grupo Público).
Também liga os dois no agendador: o assistente vê a cada 5 min se chegou a hora, e o
robô roda uma rodada a cada 15 min, num processo à parte. "Enviar 1 Agora 📤" manda uma
postagem do assistente na hora, mesmo pausado; "Testar Caminho 🧭" roda o treino do robô
na hora. O botão "Celular do Robô 📱" liga o servidor ao celular guardado do Rafael
(celular_robo.py): o código de pareamento chega só aqui, no privado. Lá, o "Passo a
Passo 📖" ensina a deixar o celular pronto de novo depois de um reset, e o "Ver Tela do
Celular 🖥️" manda no privado um link de 30 min para o Rafael ver e tocar na tela do
celular de longe (tela_android.py).
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import asyncio
import logging
import os
import re
import sys
from datetime import datetime
from html import escape as html_escape

from aiogram import Router, Bot, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import FSInputFile, KeyboardButton
from teclados import (montar_teclado, teclado_com_cancelar, teclado_cancelar,
                      teclado_aprovar_cancelar, teclado_janela_dia_todo)

import android_virtual as av
import assistente_shopee_video as assistente
import celular_robo
import db
import robo_shopee_video as robo
from fuso import fuso_horario
from motor_filas import sortear_teto_do_dia

logger = logging.getLogger("ShopeeVideo")

router = Router()
bot_instance = None
scheduler_instance = None
ADMIN_ID = None

CHAVE_CONFIG = "shopee_video"
# Os dois começam pausados: só trabalham quando o Rafael retomar no painel.
PADRAO = {"pausado": True, "limite_min": 5, "limite_max": 10, "inicio": 13, "fim": 22,
          "fonte": assistente.FONTE_PADRAO, **robo.PADRAO}
MAXIMO_POR_DIA = 50
ROBO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "robo_shopee_video.py")


def configurar_dependencias(bot: Bot, scheduler, admin_id):
    global bot_instance, scheduler_instance, ADMIN_ID
    bot_instance, scheduler_instance, ADMIN_ID = bot, scheduler, admin_id
    scheduler.add_job(verificar_envio, "interval", minutes=5, id="shopee_video_assistente",
                      replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(verificar_robo, "interval", minutes=15, id="shopee_video_robo",
                      replace_existing=True, max_instances=1, coalesce=True)


# Um envio de cada vez: o agendador e o botão Enviar 1 Agora pegariam o mesmo vídeo.
_envio = asyncio.Lock()


async def enviar_um(fonte):
    """Prepara e manda uma postagem (vídeo da fonte) no privado. Devolve o que aconteceu, numa frase."""
    async with _envio:
        try:
            return await assistente.preparar_e_enviar(bot_instance, ADMIN_ID, fonte=fonte)
        except Exception as e:
            logger.error(f"❌ [Shopee Vídeo] Erro ao preparar a postagem: {type(e).__name__}: {e}")
            return f"deu erro ao preparar ({type(e).__name__})"


async def verificar_envio():
    """Volta do agendador: manda um vídeo se um horário do plano de hoje já passou."""
    config = ler_config()
    if _envio.locked() or not assistente.decidir_envio(config):
        return
    logger.info(f"🎬 [Shopee Vídeo] {await enviar_um(config['fonte'])}.")


# Uma rodada do robô de cada vez: o agendador e o Testar Caminho tocariam juntos no celular.
_rodada = asyncio.Lock()


async def rodar_robo(*argumentos):
    """
    Uma rodada do robô automático num processo à parte: ele passa minutos tocando no
    celular, e a IA dele não pode dividir a conexão com a do bot. O resultado vai para
    o log; o que importa ao Rafael o próprio robô manda no privado.
    """
    async with _rodada:
        processo = await asyncio.create_subprocess_exec(sys.executable, ROBO, *argumentos,
                                                        cwd=os.path.dirname(ROBO))
        try:
            await asyncio.wait_for(processo.wait(), robo.MAXIMO_DA_RODADA)
        except asyncio.TimeoutError:
            processo.kill()
            logger.warning("⚠️ [Robô Shopee Vídeo] A rodada passou de 30 min e foi interrompida.")


async def verificar_robo():
    """Volta do agendador: uma rodada do robô, se ele está ativo e dentro do Horário do Robô."""
    config = ler_config()
    if _rodada.locked():
        return
    if config["robo_pausado"]:
        # Os horários de rascunho que passam pausado são pulados, como no assistente.
        robo.consumir_horarios(config)
        return
    if robo.no_horario(config):
        await rodar_robo("--rodada")


def _admin(message):
    return message.from_user is not None and message.from_user.id == ADMIN_ID


class ShopeeVideoFluxo(StatesGroup):
    menu = State()
    aguardando_faixa = State()
    aguardando_confirmacao_faixa = State()
    aguardando_janela = State()
    aguardando_confirmacao_janela = State()
    aguardando_confirmacao_pausa = State()
    aguardando_fonte = State()
    aguardando_faixa_robo = State()
    aguardando_confirmacao_faixa_robo = State()
    aguardando_janela_robo = State()
    aguardando_confirmacao_janela_robo = State()
    aguardando_confirmacao_pausa_robo = State()
    rascunho = State()
    aguardando_confirmacao_recusa = State()
    celular = State()
    aguardando_escolha_celular = State()
    aguardando_pareamento = State()
    aguardando_porta = State()


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


def rascunhos_hoje(config, agora=None):
    return robo.quantos_hoje(config, (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d"))


# --- Painel ---

BOTAO_CELULAR = "Celular do Robô 📱"
BOTAO_PAREAR = "Parear Celular 🔗"
BOTAO_RECONECTAR = "Reconectar Celular 🔄"
BOTAO_VOLTAR = "Voltar à Shopee Vídeo 🔙"
BOTAO_PASSO_A_PASSO = "Passo a Passo 📖"
BOTAO_TELA = "Ver Tela do Celular 🖥️"

BOTAO_RASCUNHOS = "Rascunhos do Robô 📝"
BOTAO_FAIXA_ROBO = "Rascunhos por Dia 📦"
BOTAO_HORARIO_ROBO = "Horário do Robô 🕗"
BOTAO_TREINO = "Testar Caminho 🧭"
BOTAO_APROVAR = "Aprovar Rascunho ✅"
BOTAO_RECUSAR = "Recusar Rascunho ❌"
BOTAO_PROXIMO = "Próximo Rascunho ⏭️"
# Os botões de pausar e retomar de cada robô trocam conforme o estado (pausado mostra
# Retomar). Os antigos "Pausar Robô"/"Retomar Robô" ainda podem estar no teclado do
# Rafael e valem para o assistente.
PAUSA_ASSISTENTE = ["Pausar Assistente ⏸️", "Retomar Assistente ▶️", "Pausar Robô ⏸️", "Retomar Robô ▶️"]
PAUSA_ROBO = ["Pausar Postagem ⏸️", "Retomar Postagem ▶️"]


def teclado_painel(config):
    pausa = "Retomar Assistente ▶️" if config["pausado"] else "Pausar Assistente ⏸️"
    pausa_robo = "Retomar Postagem ▶️" if config["robo_pausado"] else "Pausar Postagem ⏸️"
    return montar_teclado([
        [KeyboardButton(text="Vídeos por Dia 📦"), KeyboardButton(text="Horário de Postagem ⏰")],
        [KeyboardButton(text=pausa), KeyboardButton(text="Enviar 1 Agora 📤")],
        [KeyboardButton(text="Fonte dos Vídeos 🎞️")],
        [KeyboardButton(text=BOTAO_RASCUNHOS)],
        [KeyboardButton(text=pausa_robo), KeyboardButton(text=BOTAO_TREINO)],
        [KeyboardButton(text=BOTAO_FAIXA_ROBO), KeyboardButton(text=BOTAO_HORARIO_ROBO)],
        [KeyboardButton(text=BOTAO_CELULAR)],
        [KeyboardButton(text="Voltar aos Canais 🔙")],
    ])


def _linha_treino():
    estado = robo.ler_estado()
    if not estado.get("treino_em"):
        return "ainda não rodou"
    resultado = estado.get("treino_resultado") or "rodando"
    quando = _data_curta(estado["treino_em"])
    return f"✅ caminho OK em {quando}" if resultado == "ok" else f"⚠️ {html_escape(resultado)} em {quando}"


def texto_painel(config, agora=None):
    status = "⏸️ <b>Pausado</b>" if config["pausado"] else "▶️ <b>Ativo</b>"
    status_robo = "⏸️ <b>Pausado</b>" if config["robo_pausado"] else "▶️ <b>Ativo</b>"
    piso, topo = config["limite_min"], config["limite_max"]
    hoje = f" (sorteado a cada dia; hoje: <b>{videos_hoje(config, agora)}</b>)" if topo > piso else ""
    piso_robo, topo_robo = config["robo_limite_min"], config["robo_limite_max"]
    hoje_robo = f" (hoje: <b>{rascunhos_hoje(config, agora)}</b>)" if topo_robo > piso_robo else ""
    return (
        "🎬 <b>Shopee Vídeo</b>\n"
        f"🎞️ Fonte dos vídeos: <b>{assistente.FONTES.get(config['fonte'], config['fonte'])}</b>\n\n"
        "📲 <b>Modo assistente</b>: prepara as postagens (vídeo, título, produtos e comentário) e "
        "manda aqui no seu privado, para você postar pelo seu celular.\n"
        f"Status: {status}\n"
        f"📦 Vídeos por dia: <b>{rotulo_faixa(piso, topo)}</b>{hoje}\n"
        f"⏰ Horário dos envios: <b>{rotulo_janela(config['inicio'], config['fim'])}</b>\n"
        f"📤 Mandados hoje: <b>{assistente.enviados_hoje(agora)}</b>\n\n"
        "🤖 <b>Robô automático</b>: prepara rascunhos sozinho no celular guardado e posta os que "
        "você aprovar em Rascunhos do Robô 📝.\n"
        f"Status: {status_robo}\n"
        f"📦 Rascunhos por dia: <b>{rotulo_faixa(piso_robo, topo_robo)}</b>{hoje_robo}\n"
        f"🕗 Horário do robô: <b>{rotulo_janela(config['robo_inicio'], config['robo_fim'])}</b>\n"
        f"📝 Esperando a sua aprovação: <b>{len(robo.esperando_aprovacao())}</b> | "
        f"✅ Aprovados na fila: <b>{len(robo.listar('aprovado'))}</b>\n"
        f"🧭 Treino: {_linha_treino()}\n\n"
        "<i>Enviar 1 Agora 📤 manda uma postagem do assistente na hora, mesmo pausado. "
        "Testar Caminho 🧭 confere agora se as telas do app continuam como o robô conhece.</i>"
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
        parse_mode="HTML", reply_markup=teclado_janela_dia_todo)
    await state.set_state(ShopeeVideoFluxo.aguardando_janela)



# --- Pausa ---

@router.message(F.text.in_(PAUSA_ASSISTENTE), StateFilter("*"))
async def pedir_pausa(message: types.Message, state: FSMContext):
    if not _admin(message): return
    pausar = message.text.startswith("Pausar")
    await state.update_data(pausar=pausar)
    pergunta = ("⚠️ <b>Pausar</b> o modo assistente? Ele para de mandar postagens até você retomar."
                if pausar else
                "▶️ <b>Retomar</b> o modo assistente? Ele volta a mandar as postagens aqui no seu "
                "privado, dentro do horário e da quantidade do painel.")
    botao = "Confirmar Pausa ✅" if pausar else "Confirmar Retomada ✅"
    teclado = teclado_com_cancelar(botao)
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
    await message.answer("⏳ Preparando a postagem: a IA assiste ao vídeo e escreve o texto (1 a 2 min; até 4 se ela precisar refazer o título).")
    resultado = await enviar_um(ler_config()["fonte"])
    if resultado != "postagem mandada no seu privado":
        await message.answer(f"⚠️ Não mandei: {resultado}.")


# --- Fonte dos vídeos ---

# O que muda em cada fonte, para o Rafael escolher sabendo.
EXPLICACAO_FONTES = (
    "🎞️ <b>De onde o robô puxa os vídeos?</b>\n\n"
    "• <b>Autorais 🎥</b>: feitos para afiliados repostarem (recomendado).\n"
    "• <b>Viral (Espião) 🕵️</b>: vídeos de outros criadores; a Shopee não recomenda conteúdo "
    "copiado (diretriz 7.2.1), e a IA pula os com marca d'água de outra plataforma.\n"
    "• <b>Canal Afiliados 📺</b>: os vídeos da fila do seu canal principal.\n"
    "• <b>Grupo Público 📬</b>: os vídeos enviados pelos membros.\n\n"
    "<i>Vale para os próximos envios, inclusive o Enviar 1 Agora.</i>"
)


def teclado_fontes():
    nomes = list(assistente.FONTES.values())
    linhas = [[KeyboardButton(text=nome) for nome in nomes[i:i + 2]] for i in range(0, len(nomes), 2)]
    return montar_teclado(linhas + [[KeyboardButton(text="Cancelar ❌")]])


@router.message(F.text == "Fonte dos Vídeos 🎞️", StateFilter("*"))
async def pedir_fonte(message: types.Message, state: FSMContext):
    if not _admin(message): return
    atual = assistente.FONTES.get(ler_config()["fonte"], "")
    await message.answer(f"{EXPLICACAO_FONTES}\n\nHoje: <b>{atual}</b>.", parse_mode="HTML",
                         reply_markup=teclado_fontes())
    await state.set_state(ShopeeVideoFluxo.aguardando_fonte)


# --- Robô automático ---

@router.message(F.text.in_(PAUSA_ROBO), StateFilter("*"))
async def pedir_pausa_robo(message: types.Message, state: FSMContext):
    if not _admin(message): return
    pausar = message.text.startswith("Pausar")
    pergunta = ("⚠️ <b>Pausar</b> o robô automático? Ele para de preparar rascunhos e de postar os "
                "aprovados até você retomar. Os rascunhos ficam guardados."
                if pausar else
                "▶️ <b>Retomar</b> o robô automático? Ele volta a preparar rascunhos e a postar os que você "
                "aprovar, dentro do Horário do Robô e da quantidade do painel.")
    botao = "Confirmar Pausa ✅" if pausar else "Confirmar Retomada ✅"
    await message.answer(pergunta, parse_mode="HTML", reply_markup=teclado_com_cancelar(botao))
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_pausa_robo)


@router.message(F.text == BOTAO_FAIXA_ROBO, StateFilter("*"))
async def pedir_faixa_robo(message: types.Message, state: FSMContext):
    if not _admin(message): return
    config = ler_config()
    await message.answer(
        "Quantos rascunhos novos o robô prepara por dia?\n\n"
        "• Faixa: <code>1-3</code>: cada dia sorteia um número entre 1 e 3\n"
        "• Fixo: <code>2</code>: sempre 2 por dia\n\n"
        f"<i>Hoje está em {rotulo_faixa(config['robo_limite_min'], config['robo_limite_max'])}. "
        f"Máximo de {robo.MAXIMO_POR_DIA} por dia. A faixa existe para a quantidade não ser sempre igual, "
        "que é o que denuncia robô.</i>",
        parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(ShopeeVideoFluxo.aguardando_faixa_robo)


@router.message(F.text == BOTAO_HORARIO_ROBO, StateFilter("*"))
async def pedir_janela_robo(message: types.Message, state: FSMContext):
    if not _admin(message): return
    config = ler_config()
    await message.answer(
        "Em que horário o robô pode tocar no celular? Os rascunhos e as postagens aprovadas se "
        "espalham dentro dessa faixa, em minutos sorteados.\n\n"
        "Envie <code>início-fim</code> (ex.: <code>9-21</code>) ou toque em Dia Todo.\n"
        f"<i>Hoje está {rotulo_janela(config['robo_inicio'], config['robo_fim'])}. Fora dele, se a Shopee "
        "pedir a verificação, ninguém resolve até você acordar.</i>",
        parse_mode="HTML", reply_markup=teclado_janela_dia_todo)
    await state.set_state(ShopeeVideoFluxo.aguardando_janela_robo)


@router.message(F.text == BOTAO_TREINO, StateFilter("*"))
async def treino_handler(message: types.Message, state: FSMContext):
    """
    O treino na hora: o robô percorre o caminho do app sem salvar nem postar e diz se
    alguma tela mudou. Roda mesmo pausado ou fora do Horário do Robô.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    if not _admin(message): return
    if _rodada.locked():
        await message.answer("⏳ O robô está no meio de uma rodada no celular. Tente de novo em alguns minutos.")
        return
    logger.info("🧭 Shopee Vídeo: Testar Caminho.")
    await message.answer("🧭 Treino começando: o robô percorre o caminho no celular sem salvar nem postar. "
                         "O resultado chega aqui em uns 5 min.")
    asyncio.create_task(rodar_robo("--treino"))


# --- Rascunhos do robô: aprovar um por um ---

def teclado_rascunho():
    return montar_teclado([[KeyboardButton(text=BOTAO_APROVAR), KeyboardButton(text=BOTAO_RECUSAR)],
                           [KeyboardButton(text=BOTAO_PROXIMO)],
                           [KeyboardButton(text=BOTAO_VOLTAR)]])


def texto_rascunho(rascunho, posicao, total):
    produtos = "\n".join(f"• {html_escape(nome)}" for nome in rascunho["produtos"]) or "• ?"
    aviso = (f"\n⚠️ Da última vez não deu certo: {html_escape(rascunho['motivo'])}\n"
             if rascunho.get("motivo") else "")
    return (f"📝 <b>Rascunho {posicao} de {total}</b> (salvo em {_data_curta(rascunho['criado_em'])})\n\n"
            "📝 <b>Título</b> (o que está na legenda):\n"
            f"<code>{html_escape(rascunho['titulo'] or '')}</code>\n\n"
            f"🛍️ <b>Produto anexado:</b>\n{produtos}\n"
            f"🔗 {html_escape(rascunho['link'] or '')}\n{aviso}\n"
            f"<b>{BOTAO_APROVAR}</b>: o robô posta, um de cada vez, dentro do Horário do Robô.\n"
            f"<b>{BOTAO_RECUSAR}</b>: o robô apaga o rascunho do celular, e o vídeo não volta.")


async def mostrar_rascunho(message, state, depois_de=None):
    """
    Um rascunho por vez, com o vídeo, o print da tela final, o título e o link do produto:
    o Rafael é o validador, e o print prova que o que ele aprova é o que vai ao ar.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    pendentes = robo.esperando_aprovacao()
    if not pendentes:
        await message.answer("📝 Nenhum rascunho esperando a sua aprovação.")
        await mostrar_painel(message, state)
        return
    seguintes = [r for r in pendentes if depois_de is not None and r["id"] > depois_de]
    rascunho = (seguintes or pendentes)[0]
    posicao = pendentes.index(rascunho) + 1
    await state.set_state(ShopeeVideoFluxo.rascunho)
    await state.update_data(rascunho_id=rascunho["id"])
    if rascunho["arquivo"] and os.path.exists(rascunho["arquivo"]):
        await message.answer_video(FSInputFile(rascunho["arquivo"]), supports_streaming=True,
                                   caption=f"🎬 Rascunho {posicao}: o vídeo.")
    if rascunho["print"] and os.path.exists(rascunho["print"]):
        await message.answer_photo(FSInputFile(rascunho["print"]),
                                   caption=f"📱 Rascunho {posicao}: a tela final no celular, como vai ao ar.")
    await message.answer(texto_rascunho(rascunho, posicao, len(pendentes)), parse_mode="HTML",
                         disable_web_page_preview=True, reply_markup=teclado_rascunho())


@router.message(F.text == BOTAO_RASCUNHOS, StateFilter("*"))
async def rascunhos_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    logger.info("📝 Shopee Vídeo: Rascunhos do Robô.")
    await mostrar_rascunho(message, state)


async def _rascunho_da_vez(message, state):
    """O rascunho que está na tela, se ele ainda espera aprovação; senão mostra o próximo."""
    ident = (await state.get_data()).get("rascunho_id")
    rascunho = robo.pegar(ident) if ident else None
    if not rascunho or rascunho["estado"] != "rascunho":
        await message.answer("Esse rascunho já foi resolvido. Mostro o próximo.")
        await mostrar_rascunho(message, state)
        return None
    return rascunho


@router.message(F.text == BOTAO_APROVAR, StateFilter("*"))
async def aprovar_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    rascunho = await _rascunho_da_vez(message, state)
    if not rascunho:
        return
    quando = robo.aprovar(rascunho["id"])
    logger.info("✅ Shopee Vídeo: rascunho aprovado.")
    await message.answer(f"✅ Aprovado. O robô posta por volta de <b>{_data_curta(quando)}</b> e manda aqui o "
                         "link do post e o comentário.", parse_mode="HTML")
    await mostrar_rascunho(message, state, depois_de=rascunho["id"])


@router.message(F.text == BOTAO_RECUSAR, StateFilter("*"))
async def pedir_recusa(message: types.Message, state: FSMContext):
    if not _admin(message): return
    if not await _rascunho_da_vez(message, state):
        return
    await message.answer("❌ <b>Recusar</b> este rascunho? O robô apaga do celular, e o vídeo não volta.",
                         parse_mode="HTML", reply_markup=teclado_com_cancelar("Confirmar Recusa ✅"))
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_recusa)


@router.message(F.text == BOTAO_PROXIMO, StateFilter("*"))
async def proximo_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await mostrar_rascunho(message, state, depois_de=(await state.get_data()).get("rascunho_id"))


# --- Celular do robô ---
# Plano do celular de verdade (roteiro_robo_shopee_video.md, fase 1c): parear uma vez,
# com o código que só existe enquanto a janela dele está aberta no celular, e
# reconectar quando a porta muda (o celular reiniciou ou a depuração foi desligada).

def teclado_celular():
    return montar_teclado([[KeyboardButton(text=BOTAO_TELA)],
                           [KeyboardButton(text=BOTAO_PAREAR), KeyboardButton(text=BOTAO_RECONECTAR)],
                           [KeyboardButton(text=BOTAO_PASSO_A_PASSO)],
                           [KeyboardButton(text=BOTAO_VOLTAR)]])


# Para o Rafael refazer tudo sozinho depois de resetar o celular, talvez meses depois:
# frases curtas, na ordem, com os nomes das telas como aparecem no Motorola.
PASSO_A_PASSO = (
    "📖 <b>Passo a passo do celular do robô</b>\n"
    "Para quando você resetar o celular guardado (ou trocar de celular). Faça na ordem.\n\n"
    "🔁 <b>Só reiniciou ou desligou a depuração?</b> Não precisa de tudo: ligue a "
    f"<b>Depuração por Wi-Fi</b> (passo 6) e toque em <b>{BOTAO_RECONECTAR}</b>.\n\n"
    "<b>Parte 1: no celular guardado</b>\n"
    "1️⃣ <b>Ligar:</b> configure o celular, entre na sua conta Google e conecte no <b>Wi-Fi de casa</b>. "
    "Deixe no carregador.\n"
    "2️⃣ <b>Apps:</b> na Play Store, instale a <b>Shopee</b> e o <b>Tailscale</b>.\n"
    "3️⃣ <b>Shopee:</b> entre na sua conta pessoal (a de sempre). Se pedir verificação, resolva com a mão. "
    "Depois: Configurações → Apps → Shopee → Bateria → <b>Sem restrições</b>.\n"
    "4️⃣ <b>Tailscale:</b> entre com a mesma conta de antes e ligue (aceite o pedido de VPN). "
    "Depois: Configurações → Rede e Internet → VPN → ⚙️ do Tailscale → ligue <b>VPN sempre ativa</b>.\n"
    "5️⃣ <b>Modo desenvolvedor:</b> Configurações → Sobre o telefone → toque <b>7 vezes</b> em "
    "\"Número da versão\" (ele pede o PIN).\n"
    "6️⃣ <b>Opções do desenvolvedor:</b> ligue <b>Manter ativado</b> e <b>Depuração por Wi-Fi</b> "
    "(toque em Permitir).\n"
    "💡 Não achou uma opção? Use a lupa 🔍 no alto das Configurações e digite o nome dela.\n\n"
    "<b>Parte 2: aqui no bot</b>\n"
    f"7️⃣ Toque em <b>{BOTAO_PAREAR}</b>.\n"
    "8️⃣ No celular: Depuração por Wi-Fi → <b>Parear o dispositivo com um código de pareamento</b>. "
    "Deixe a janela aberta.\n"
    "9️⃣ Mande aqui os números da janela: o <b>código de 6 dígitos</b>, um espaço e a <b>porta</b> "
    "(o número depois dos dois-pontos). Ex.: <code>123456 37123</code>. Eu apago a sua mensagem.\n"
    "🔟 Depois eu peço a <b>porta da conexão</b>: na tela da Depuração por Wi-Fi, em \"Endereço IP e "
    "porta\", é o número depois dos dois-pontos (outro número). Mande só ele.\n"
    "✅ Pronto quando aparecer <b>Celular conectado</b>. Avise o Claude.\n\n"
    "<b>Uma vez só, no navegador</b> (para o celular não sair da rede depois de uns meses): "
    "login.tailscale.com → Machines → o celular → ⋯ → <b>Disable key expiry</b>. Se o celular antigo "
    "ainda aparecer na lista, pode tirar (⋯ → Remove)."
)


def _data_curta(texto):
    return f"{texto[8:10]}/{texto[5:7]} às {texto[11:16]}" if texto and len(texto) >= 16 else "?"


async def texto_celular():
    dados = celular_robo.ler()
    rede = await asyncio.to_thread(celular_robo.celulares_na_rede)
    conectado = await asyncio.to_thread(celular_robo.conectado) if dados.get("porta") else False
    if not rede:
        linha_rede = "❌ nenhum celular (ligue o Tailscale no celular guardado)"
    else:
        linha_rede = ", ".join(f"<b>{html_escape(c['nome'])}</b> {'✅ ligado' if c['online'] else '⚠️ fora do ar'}"
                               for c in rede)
    pareado = f"✅ em {_data_curta(dados['pareado_em'])}" if dados.get("pareado_em") else "⏳ ainda não"
    if conectado:
        conexao = f"✅ conectado ({html_escape(dados.get('modelo') or 'celular')})"
    elif dados.get("porta"):
        conexao = f"⚠️ desconectado: toque em {BOTAO_RECONECTAR}"
    else:
        conexao = "⏳ ainda não"
    return ("📱 <b>Celular do Robô</b>\n"
            "O robô da Shopee Vídeo vai postar pelo seu celular guardado, ligado ao servidor pela "
            "rede privada (Tailscale).\n\n"
            f"🌐 Na rede privada: {linha_rede}\n"
            f"🔗 Pareado: {pareado}\n"
            f"📶 Conexão: {conexao}\n\n"
            f"<i>{BOTAO_TELA} manda aqui um link de 30 min para ver e tocar na tela do celular de "
            "longe. Parear é uma vez só. {BOTAO_RECONECTAR} é para depois que o celular reiniciar ou a "
            "Depuração por Wi-Fi for desligada, porque a porta muda. Resetou o celular? Toque em "
            f"{BOTAO_PASSO_A_PASSO}.</i>")


async def mostrar_celular(message: types.Message, state: FSMContext):
    await state.set_state(ShopeeVideoFluxo.celular)
    await message.answer(await texto_celular(), parse_mode="HTML", reply_markup=teclado_celular())


@router.message(F.text == BOTAO_CELULAR, StateFilter("*"))
async def celular_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    logger.info("📱 Acessando o celular do robô.")
    await mostrar_celular(message, state)


@router.message(F.text == BOTAO_PASSO_A_PASSO, StateFilter("*"))
async def passo_a_passo_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await state.set_state(ShopeeVideoFluxo.celular)
    await message.answer(PASSO_A_PASSO, parse_mode="HTML", reply_markup=teclado_celular())


@router.message(F.text == BOTAO_TELA, StateFilter("*"))
async def abrir_tela_handler(message: types.Message, state: FSMContext):
    """
    A tela do celular no navegador, para o Rafael resolver a verificação ou mexer no app
    de longe. O link vai no privado (pelo avisar_rafael), nunca no log.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    if not _admin(message): return
    await state.set_state(ShopeeVideoFluxo.celular)
    if not await asyncio.to_thread(celular_robo.conectado):
        await message.answer(f"⚠️ O celular está desconectado: toque em {BOTAO_RECONECTAR} primeiro.",
                             reply_markup=teclado_celular())
        return
    await message.answer("⏳ Abrindo a tela do celular (leva até 1 min)...")
    logger.info("🖥️ Abrindo a tela do celular do robô.")
    if await asyncio.to_thread(av.abrir_tela, True):
        await message.answer(
            "✅ O link da tela chegou aqui no privado e vale 30 min. Na página, toque em "
            "<b>Terminei</b> quando acabar: enquanto ela está aberta, o robô não mexe no celular.",
            parse_mode="HTML", reply_markup=teclado_celular())
        return
    motivo = av._ler_estado_tela().removeprefix("erro: ") or "não respondeu a tempo"
    await message.answer(f"❌ A tela não abriu ({html_escape(motivo)}). Tente de novo daqui a pouco.",
                         parse_mode="HTML", reply_markup=teclado_celular())


@router.message(F.text == BOTAO_VOLTAR, StateFilter("*"))
async def voltar_ao_painel(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await mostrar_painel(message, state)


async def _seguir_com_celular(message, state, celular, acao):
    """Com o celular escolhido, pede o código (parear) ou a porta (reconectar)."""
    await state.update_data(celular_ip=celular["ip"], celular_nome=celular["nome"])
    nome = html_escape(celular["nome"])
    if acao == "parear":
        await message.answer(
            f"🔗 <b>Parear o celular</b> ({nome})\n\n"
            "No celular guardado:\n"
            "1. Opções do desenvolvedor → <b>Depuração por Wi-Fi</b>.\n"
            "2. Toque em <b>Parear dispositivo com código de pareamento</b>.\n"
            "3. Mande aqui o <b>código de 6 dígitos</b> e a <b>porta</b> (o número depois dos dois-pontos "
            "em \"Endereço IP e porta\"), assim: <code>123456 37123</code>.\n\n"
            "<i>Deixe a janela do código aberta até eu responder. Apago a sua mensagem logo depois de "
            "usar o código.</i>",
            parse_mode="HTML", reply_markup=teclado_cancelar)
        await state.set_state(ShopeeVideoFluxo.aguardando_pareamento)
    else:
        await message.answer(
            f"🔄 <b>Conectar ao celular</b> ({nome})\n\n"
            "No celular guardado, abra Opções do desenvolvedor → <b>Depuração por Wi-Fi</b> (ligada). "
            "No alto aparece <b>Endereço IP e porta</b>: mande aqui só a <b>porta</b>, o número depois "
            "dos dois-pontos (ex.: <code>41235</code>).",
            parse_mode="HTML", reply_markup=teclado_cancelar)
        await state.set_state(ShopeeVideoFluxo.aguardando_porta)


async def _escolher_celular(message, state, acao):
    """Acha o celular ligado na rede privada; com mais de um, pergunta qual."""
    online = [c for c in await asyncio.to_thread(celular_robo.celulares_na_rede) if c["online"]]
    if not online:
        await message.answer(
            "⚠️ Não achei nenhum celular ligado na rede privada. No celular guardado, confira se o "
            "<b>Tailscale</b> está ligado e se ele está no Wi-Fi.", parse_mode="HTML", reply_markup=teclado_celular())
        return
    salvo = next((c for c in online if c["ip"] == celular_robo.ler().get("ip")), None)
    if salvo or len(online) == 1:
        await _seguir_com_celular(message, state, salvo or online[0], acao)
        return
    await state.update_data(acao_celular=acao, celulares=online)
    await message.answer("Qual destes é o celular guardado?", reply_markup=montar_teclado(
        [[KeyboardButton(text=c["nome"])] for c in online] + [[KeyboardButton(text="Cancelar ❌")]]))
    await state.set_state(ShopeeVideoFluxo.aguardando_escolha_celular)


@router.message(F.text == BOTAO_PAREAR, StateFilter("*"))
async def pedir_pareamento(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await _escolher_celular(message, state, "parear")


@router.message(F.text == BOTAO_RECONECTAR, StateFilter("*"))
async def pedir_reconexao(message: types.Message, state: FSMContext):
    if not _admin(message): return
    if not celular_robo.ler().get("pareado_em"):
        await message.answer(f"⚠️ O celular ainda não foi pareado: toque em {BOTAO_PAREAR} primeiro.",
                             reply_markup=teclado_celular())
        return
    await _escolher_celular(message, state, "reconectar")


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
                         parse_mode="HTML", reply_markup=teclado_aprovar_cancelar)
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
            parse_mode="HTML", reply_markup=teclado_janela_dia_todo)
        return
    inicio, fim = janela
    await state.update_data(janela=[inicio, fim])
    await message.answer(f"Postar <b>{rotulo_janela(inicio, fim)}</b>?", parse_mode="HTML", reply_markup=teclado_aprovar_cancelar)
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
    await message.answer("⏸️ Modo assistente <b>pausado</b>." if pausar
                         else "▶️ Modo assistente <b>retomado</b>.", parse_mode="HTML")
    await mostrar_painel(message, state)


@router.message(ShopeeVideoFluxo.aguardando_fonte, F.text.in_(list(assistente.FONTES.values())))
async def salvar_fonte(message: types.Message, state: FSMContext):
    fonte = next(chave for chave, nome in assistente.FONTES.items() if nome == message.text)
    alterar_config(fonte=fonte)
    logger.info(f"✅ Shopee Vídeo: vídeos de {fonte}.")
    await message.answer(f"✅ Fonte dos vídeos: <b>{message.text}</b>.", parse_mode="HTML")
    await mostrar_painel(message, state)


@router.message(ShopeeVideoFluxo.aguardando_faixa_robo)
async def confirmar_faixa_robo(message: types.Message, state: FSMContext):
    faixa = interpretar_faixa(message.text)
    if not faixa or faixa[1] > robo.MAXIMO_POR_DIA:
        await message.answer(
            f"⚠️ Envie um número (<code>2</code>) ou uma faixa (<code>1-3</code>), de 1 a {robo.MAXIMO_POR_DIA}.",
            parse_mode="HTML", reply_markup=teclado_cancelar)
        return
    piso, topo = faixa
    await state.update_data(faixa=[piso, topo])
    await message.answer(f"Definir <b>{rotulo_faixa(piso, topo)}</b> rascunhos por dia?",
                         parse_mode="HTML", reply_markup=teclado_aprovar_cancelar)
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_faixa_robo)


@router.message(ShopeeVideoFluxo.aguardando_confirmacao_faixa_robo, F.text == "Aprovar ✅")
async def salvar_faixa_robo(message: types.Message, state: FSMContext):
    piso, topo = (await state.get_data())["faixa"]
    alterar_config(robo_limite_min=piso, robo_limite_max=topo)
    logger.info(f"✅ Shopee Vídeo: robô com {piso} a {topo} rascunhos por dia.")
    await message.answer(f"✅ Rascunhos por dia: <b>{rotulo_faixa(piso, topo)}</b>.", parse_mode="HTML")
    await mostrar_painel(message, state)


@router.message(ShopeeVideoFluxo.aguardando_janela_robo)
async def confirmar_janela_robo(message: types.Message, state: FSMContext):
    janela = interpretar_janela(message.text)
    if not janela:
        await message.answer(
            "⚠️ Use o formato <code>9-21</code>, com o início menor que o fim (de 0 a 24).",
            parse_mode="HTML", reply_markup=teclado_janela_dia_todo)
        return
    inicio, fim = janela
    await state.update_data(janela=[inicio, fim])
    await message.answer(f"Robô trabalhando <b>{rotulo_janela(inicio, fim)}</b>?", parse_mode="HTML",
                         reply_markup=teclado_aprovar_cancelar)
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_janela_robo)


@router.message(ShopeeVideoFluxo.aguardando_confirmacao_janela_robo, F.text == "Aprovar ✅")
async def salvar_janela_robo(message: types.Message, state: FSMContext):
    inicio, fim = (await state.get_data())["janela"]
    alterar_config(robo_inicio=inicio, robo_fim=fim)
    logger.info(f"✅ Shopee Vídeo: Horário do Robô {inicio}h-{fim}h.")
    await message.answer(f"✅ Horário do robô: <b>{rotulo_janela(inicio, fim)}</b>.", parse_mode="HTML")
    await mostrar_painel(message, state)


@router.message(ShopeeVideoFluxo.aguardando_confirmacao_pausa_robo,
                F.text.in_(["Confirmar Pausa ✅", "Confirmar Retomada ✅"]))
async def salvar_pausa_robo(message: types.Message, state: FSMContext):
    pausar = message.text == "Confirmar Pausa ✅"
    alterar_config(robo_pausado=pausar)
    logger.info(f"✅ Robô automático da Shopee Vídeo {'pausado' if pausar else 'retomado'}.")
    await message.answer("⏸️ Robô automático <b>pausado</b>." if pausar
                         else "▶️ Robô automático <b>retomado</b>.", parse_mode="HTML")
    await mostrar_painel(message, state)


@router.message(ShopeeVideoFluxo.aguardando_confirmacao_recusa, F.text == "Confirmar Recusa ✅")
async def salvar_recusa(message: types.Message, state: FSMContext):
    ident = (await state.get_data()).get("rascunho_id")
    rascunho = robo.pegar(ident) if ident else None
    if rascunho and rascunho["estado"] == "rascunho":
        robo.recusar(ident)
        logger.info("❌ Shopee Vídeo: rascunho recusado.")
        await message.answer("❌ Recusado. O robô apaga o rascunho do celular na próxima rodada.")
    await mostrar_rascunho(message, state, depois_de=ident)


@router.message(StateFilter(ShopeeVideoFluxo.aguardando_confirmacao_faixa,
                            ShopeeVideoFluxo.aguardando_confirmacao_janela,
                            ShopeeVideoFluxo.aguardando_confirmacao_pausa,
                            ShopeeVideoFluxo.aguardando_fonte,
                            ShopeeVideoFluxo.aguardando_confirmacao_faixa_robo,
                            ShopeeVideoFluxo.aguardando_confirmacao_janela_robo,
                            ShopeeVideoFluxo.aguardando_confirmacao_pausa_robo,
                            ShopeeVideoFluxo.aguardando_confirmacao_recusa))
async def confirmar_com_os_botoes(message: types.Message, state: FSMContext):
    await message.answer("Toque em um dos botões para confirmar ou em Cancelar ❌.")


@router.message(ShopeeVideoFluxo.aguardando_escolha_celular)
async def receber_escolha_celular(message: types.Message, state: FSMContext):
    dados = await state.get_data()
    celular = next((c for c in dados.get("celulares", []) if c["nome"] == message.text), None)
    if not celular:
        await message.answer("Toque no nome do celular guardado ou em Cancelar ❌.")
        return
    await _seguir_com_celular(message, state, celular, dados.get("acao_celular", "parear"))


@router.message(ShopeeVideoFluxo.aguardando_pareamento)
async def receber_pareamento(message: types.Message, state: FSMContext):
    lido = celular_robo.interpretar_pareamento(message.text)
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"⚠️ Celular do robô: não consegui apagar a mensagem do código ({type(e).__name__}).")
    if not lido:
        await message.answer("⚠️ Mande o código de 6 dígitos e a porta, separados por espaço "
                             "(ex.: <code>123456 37123</code>).", parse_mode="HTML", reply_markup=teclado_cancelar)
        return
    codigo, porta = lido
    dados = await state.get_data()
    await message.answer("⏳ Pareando com o celular…")
    ok, motivo = await asyncio.to_thread(celular_robo.parear, dados["celular_ip"], porta, codigo)
    if not ok:
        logger.warning(f"⚠️ Celular do robô: pareamento falhou ({motivo}).")
        await message.answer(f"⚠️ Não pareou: {motivo}. Toque em {BOTAO_PAREAR} para tentar de novo, com um "
                             "código novo.", reply_markup=teclado_celular())
        await state.set_state(ShopeeVideoFluxo.celular)
        return
    logger.info("✅ Celular do robô: pareado.")
    await message.answer(
        "✅ <b>Pareado!</b> Agora feche a janela do código. No alto da tela Depuração por Wi-Fi aparece "
        "<b>Endereço IP e porta</b>: mande aqui só a <b>porta</b>, o número depois dos dois-pontos "
        "(ex.: <code>41235</code>).", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(ShopeeVideoFluxo.aguardando_porta)


@router.message(ShopeeVideoFluxo.aguardando_porta)
async def receber_porta(message: types.Message, state: FSMContext):
    porta = celular_robo.interpretar_porta(message.text)
    if not porta:
        await message.answer("⚠️ Mande só a porta, o número depois dos dois-pontos (ex.: <code>41235</code>).",
                             parse_mode="HTML", reply_markup=teclado_cancelar)
        return
    dados = await state.get_data()
    await message.answer("⏳ Conectando ao celular…")
    ok, resultado = await asyncio.to_thread(celular_robo.conectar, dados["celular_ip"], porta)
    if not ok:
        logger.warning(f"⚠️ Celular do robô: conexão falhou ({resultado}).")
        await message.answer(f"⚠️ Não conectou: {resultado}. Confira a porta e mande de novo.",
                             reply_markup=teclado_cancelar)
        return
    logger.info("✅ Celular do robô: conectado.")
    await message.answer(f"✅ <b>Celular conectado:</b> {html_escape(resultado)}.", parse_mode="HTML")
    await mostrar_celular(message, state)
