# 0. CONFIGURAÇÕES INICIAIS
EXIBIR_LOGS = True
import os
from dotenv import load_dotenv
load_dotenv()
import logging
import asyncio
import random
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, F, StateFilter 
from aiogram import F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google import genai

# 1. CONSTANTES E TOKENS
API_TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = 1226920464
GRUPO_ID = -1003909405581
LINK_GRUPO = "https://t.me/shopee_video_afiliado"
GEMINI_API_KEY = os.getenv('GEMINI_KEY')

# Inicializa o cliente moderno da SDK do Google
client = genai.Client(api_key=GEMINI_API_KEY)

# 2. CONFIGURAÇÃO DE LOGS 🚀
if EXIBIR_LOGS:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    logger = logging.getLogger(__name__)

# 3. MÁQUINA DE ESTADOS (FSM) PARA O FLUXO DE POSTAGEM
class PostagemFluxo(StatesGroup):
    aguardando_nome = State()
    aguardando_video = State()
    aguardando_links = State()

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
fuso_horario = ZoneInfo("America/Sao_Paulo")
scheduler = AsyncIOScheduler(timezone=fuso_horario)

# Teclados auxiliares para o fluxo de postagem 🛠️
teclado_cancelar = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Cancelar ❌")]],
    resize_keyboard=True
)

teclado_finalizar = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Finalizar ✅")],
        [KeyboardButton(text="Cancelar ❌")]
    ],
    resize_keyboard=True
)

# Teclado principal para retornar após o fluxo
def obter_teclado_principal():
    botoes = [
        [KeyboardButton(text="Criar Postagem 📝")],
        [KeyboardButton(text="Enviar mensagem de Bom Dia ☀️"), KeyboardButton(text="Enviar mensagem de Incentivo 🔥")],
        [KeyboardButton(text="Enviar mensagem de Boa Noite 🌙")]
    ]
    return ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)

# 4. FUNÇÕES DE GERAÇÃO COM IA E AGENDAMENTO ⏰
async def gerar_mensagem_gemini(prompt):
    # Lista técnica em ordem de prioridade para garantir a melhor mensagem
    modelos_disponiveis = [
        "gemini-3.1-pro-preview",       # 1. Inteligência superior
        "gemini-2.5-pro",               # 2. Estabilidade e raciocínio
        "gemini-3-flash-preview",       # 3. Equilíbrio e rapidez
        "gemini-2.5-flash",             # 4. Versatilidade (Workhorse)
        "gemini-3.1-flash-lite-preview",# 5. Alta velocidade
        "gemini-2.5-flash-lite"         # 6. Fallback final leve
    ]

    if EXIBIR_LOGS: logger.info("🧠 Iniciando processamento em cascata com a nova SDK...")

    for modelo_nome in modelos_disponiveis:
        try:
            if EXIBIR_LOGS: logger.info(f"⏳ Consultando motor: {modelo_nome}...")
            
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=modelo_nome,
                contents=prompt
            )
            
            if response and response.text:
                if EXIBIR_LOGS: logger.info(f"✅ Sucesso total com o modelo {modelo_nome}!")
                return response.text.strip()
                
        except Exception as e:
            erro_str = str(e)
            if "429" in erro_str:
                if EXIBIR_LOGS: logger.warning(f"⚠️ Limite atingido em {modelo_nome}. Pausando 2s...")
                await asyncio.sleep(2)
            else:
                if EXIBIR_LOGS: logger.warning(f"⚠️ Modelo {modelo_nome} indisponível: {erro_str[:50]}...")
            continue 

    if EXIBIR_LOGS: logger.error("❌ Falha crítica: Nenhum motor da cascata respondeu.")
    return "🚀 Novos materiais disponíveis! Bora postar e converter!"

async def disparar_mensagem(tipo):
    # ✅ Contexto atualizado: Foco em suporte ao Afiliado (Shopee Vídeo)
    contexto_afiliado = (
        "Você é um assistente especializado em suporte para afiliados da Shopee. "
        "Seu objetivo é motivar parceiros a postarem vídeos no Shopee Vídeo para ganharem comissão. "
        "Entregue APENAS o texto da mensagem final, sem introduções, sem aspas e sem oferecer opções."
    )

    if tipo == "bom_dia":
        prompt = (
            f"{contexto_afiliado} Crie uma mensagem de bom dia motivadora para o grupo de afiliados. "
            "Diga que os vídeos de hoje estão prontos para download e postagem. Use emojis."
        )
    elif tipo == "boa_noite":
        prompt = (
            f"{contexto_afiliado} Crie uma mensagem de boa noite para afiliados. "
            "Sugira que organizem os links para as postagens de amanhã. Use emojis."
        )
    elif tipo == "incentivo":
        prompt = (
            f"{contexto_afiliado} Crie um texto curto e impactante sobre persistência no tráfego orgânico. "
            "Lembre que um vídeo viral pode gerar comissão por semanas. Use emojis."
        )
    elif tipo == "link_grupo":
        prompt = (
            f"{contexto_afiliado} Convide parceiros a trazerem outros afiliados para o grupo para acessarem "
            f"materiais exclusivos. Link: {LINK_GRUPO}. Use emojis."
        )

    texto = await gerar_mensagem_gemini(prompt)
    if EXIBIR_LOGS: logger.info(f"🚀 Enviando mensagem ({tipo}): {texto[:20]}...")
    await bot.send_message(GRUPO_ID, texto)

def agendar_tarefas_diarias():
    if EXIBIR_LOGS: logger.info("🔄 Sorteando horários das postagens de hoje...")
    
    minuto_manha = random.randint(0, 59)
    hora_incentivo = random.randint(8, 21)
    minuto_incentivo = random.randint(0, 59)
    minuto_noite = random.randint(0, 59)
    
    scheduler.add_job(disparar_mensagem, 'cron', hour=7, minute=minuto_manha, args=["bom_dia"], id='job_manha', replace_existing=True)
    scheduler.add_job(disparar_mensagem, 'cron', hour=hora_incentivo, minute=minuto_incentivo, args=["incentivo"], id='job_incentivo', replace_existing=True)
    scheduler.add_job(disparar_mensagem, 'cron', hour=22, minute=minuto_noite, args=["boa_noite"], id='job_noite', replace_existing=True)
    scheduler.add_job(disparar_mensagem, 'cron', hour=random.randint(8, 21), minute=random.randint(0, 59), args=["link_grupo"], id='job_link', replace_existing=True)
    
    if EXIBIR_LOGS:
        logger.info(f"📅 Bom dia: 07:{minuto_manha:02d}")
        logger.info(f"📅 Incentivo: {hora_incentivo:02d}:{minuto_incentivo:02d}")
        logger.info(f"📅 Boa noite: 22:{minuto_noite:02d}")

# 5. HANDLERS DE COMANDO E INTERAÇÃO
@dp.message(Command("start"))
async def comando_start(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("⌨️ Atualizando menu principal.")
    await message.answer("Painel de Controle atualizado. Escolha uma ação abaixo:", reply_markup=obter_teclado_principal())

# ❌ NOVO: Handler Global para Cancelar via Botão
@dp.message(F.text == "Cancelar ❌", StateFilter(PostagemFluxo))
async def cancelar_fluxo_global(message: types.Message, state: FSMContext):
    if EXIBIR_LOGS: logger.info("❌ Fluxo de postagem cancelado via botão.")
    await state.clear()
    await message.answer("Postagem cancelada. Voltando ao menu...", reply_markup=obter_teclado_principal())

@dp.message(Command("postar"))
@dp.message(F.text == "Criar Postagem 📝")
async def iniciar_postagem(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🎬 Iniciando novo fluxo de postagem.")
    await message.answer("Certo! Qual o nome do produto?", reply_markup=teclado_cancelar)
    await state.set_state(PostagemFluxo.aguardando_nome)

@dp.message(PostagemFluxo.aguardando_nome)
async def receber_nome(message: types.Message, state: FSMContext):
    await state.update_data(nome_produto=message.text)
    await message.answer("Perfeito. Agora, anexe o vídeo do produto.", reply_markup=teclado_cancelar)
    await state.set_state(PostagemFluxo.aguardando_video)

@dp.message(PostagemFluxo.aguardando_video)
async def receber_video(message: types.Message, state: FSMContext):
    if not message.video:
        await message.answer("Por favor, envie um arquivo de vídeo ou clique em Cancelar.", reply_markup=teclado_cancelar)
        return
    
    await state.update_data(video_id=message.video.file_id, links=[])
    await message.answer("Vídeo recebido! Agora envie os links um por um.\n\nUse o botão Finalizar quando terminar.", reply_markup=teclado_finalizar)
    await state.set_state(PostagemFluxo.aguardando_links)

@dp.message(PostagemFluxo.aguardando_links)
async def receber_links(message: types.Message, state: FSMContext):
    # ✅ Captura tanto o botão quanto o comando antigo para redundância
    if message.text in ["Finalizar ✅", "/finalizar"]:
        await finalizar_postagem(message, state)
        return

    data = await state.get_data()
    links = data.get('links', [])
    links.append(message.text)
    
    if len(links) >= 8:
        await state.update_data(links=links)
        await finalizar_postagem(message, state)
    else:
        await state.update_data(links=links)
        await message.answer(f"Link {len(links)} registrado. Envie o próximo link ou clique em Finalizar.", reply_markup=teclado_finalizar)

async def finalizar_postagem(message: types.Message, state: FSMContext):
    data = await state.get_data()
    nome = data['nome_produto']
    video = data['video_id']
    links = data['links']
    
    if EXIBIR_LOGS: logger.info("📤 Publicando postagem no grupo.")
    
    # Mensagem 1: Apresentação
    texto_intro = f"✨ Confira este achadinho: {nome}!\n\nVeja os detalhes no vídeo abaixo e aproveite as ofertas."
    await bot.send_message(GRUPO_ID, texto_intro)
    
    # Mensagem 2: Vídeo
    await bot.send_video(GRUPO_ID, video)
    
    # Mensagem 3: Lista de Links
    texto_links = "🛒 **Links do Produto:**\n\n"
    for i, link in enumerate(links, 1):
        texto_links += f"{i}° Vídeo\n{link}\n\n"
    
    await bot.send_message(GRUPO_ID, texto_links, parse_mode="Markdown")
    await message.answer("Postagem enviada com sucesso! ✅", reply_markup=obter_teclado_principal())
    await state.clear()

@dp.message(F.text == "Enviar mensagem de Bom Dia ☀️")
async def gatilho_bom_dia(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("☀️ Disparo manual: Bom Dia.")
    await disparar_mensagem("bom_dia")
    await message.answer("Mensagem de Bom Dia enviada! 🚀")

@dp.message(F.text == "Enviar mensagem de Incentivo 🔥")
async def gatilho_incentivo(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🔥 Disparo manual: Incentivo.")
    await disparar_mensagem("incentivo")
    await message.answer("Mensagem de Incentivo enviada! 🚀")

@dp.message(F.text == "Enviar mensagem de Boa Noite 🌙")
async def gatilho_boa_noite(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🌙 Disparo manual: Boa Noite.")
    await disparar_mensagem("boa_noite")
    await message.answer("Mensagem de Boa Noite enviada! 🚀")

async def main():
    # Agendador mestre que roda todo dia às 00:01
    scheduler.add_job(agendar_tarefas_diarias, 'cron', hour=0, minute=1)
    
    # Roda o agendador imediatamente ao ligar o bot para garantir o dia atual
    agendar_tarefas_diarias() 
    
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
