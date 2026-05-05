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
from aiogram import Bot, Dispatcher, types, F # ✅ 'F' adicionado ao pacote principal
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter # ✅ 'F' removido daqui para evitar o erro de importação
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

# 2.5 SISTEMA DE NUMERAÇÃO DE VÍDEOS 🔢
def ler_contador():
    try:
        with open("contador.txt", "r") as f:
            return int(f.read().strip())
    except FileNotFoundError:
        return 1 # Se o arquivo não existir, começa do 1

def salvar_contador(numero):
    with open("contador.txt", "w") as f:
        f.write(str(numero))

# 3. MÁQUINA DE ESTADOS (FSM) PARA O FLUXO DE POSTAGEM
class PostagemFluxo(StatesGroup):
    aguardando_video = State()             
    aguardando_confirmacao_nome = State()  
    aguardando_chamada_manual = State()    
    aguardando_links = State()

class ConfigFluxo(StatesGroup):
    aguardando_novo_numero = State() # ✅ Novo estado para você editar o número

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
fuso_horario = ZoneInfo("America/Sao_Paulo")
scheduler = AsyncIOScheduler(timezone=fuso_horario)

# --- NOVOS TECLADOS DE CONTROLE ---
# 🛠️ Teclado básico para etapas de entrada de dados
teclado_cancelar = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Cancelar ❌")]],
    resize_keyboard=True,
    is_persistent=True
)

# 🛠️ Teclado de confirmação da análise da inteligência artificial
teclado_confirmacao = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Tentar Novamente 🔄")],
        [KeyboardButton(text="Cancelar ❌")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

# 🛠️ Teclado para a fase de coleta de links e encerramento
teclado_finalizar = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Finalizar ✅")],
        [KeyboardButton(text="Cancelar ❌")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

# 🛠️ Função centralizadora do menu principal
def obter_teclado_principal():
    botoes = [
        [KeyboardButton(text="Criar Postagem 📝")],
        [KeyboardButton(text="Enviar mensagem de Bom Dia ☀️"), KeyboardButton(text="Enviar mensagem de Incentivo 🔥")],
        [KeyboardButton(text="Enviar mensagem de Boa Noite 🌙"), KeyboardButton(text="Divulgar Grupo 📢")],
        # ✅ Novos botões para controle da numeração
        [KeyboardButton(text="Zerar Contador 🔄"), KeyboardButton(text="Editar Número ✏️")]
    ]
    return ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)
# ----------------------------------

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
        # ✅ Prompt isolado para focar 100% no convite e ignorar a regra de postagem
        prompt = (
            f"{contexto_afiliado} IMPORTANTE: Nesta mensagem específica, não peça para o usuário postar vídeos. "
            "Foque EXCLUSIVAMENTE em criar um texto persuasivo pedindo aos membros que convidem amigos afiliados. "
            "Use um tom de parceria do tipo: 'Conhece alguém que é afiliado e está sem tempo de buscar vídeos? "
            "Mande nosso link para ele! Aqui entregamos tudo pronto e 100% de graça.' "
            f"Finalize chamando para a ação com o link: {LINK_GRUPO}. Use emojis."
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
    if EXIBIR_LOGS: logger.info("🎬 Iniciando postagem com IA Copywriter.")
    await message.answer("Excelente! Envie o vídeo do produto e eu criarei a legenda de vendas para você.", reply_markup=teclado_cancelar)
    await state.set_state(PostagemFluxo.aguardando_video)

@dp.message(PostagemFluxo.aguardando_video)
async def receber_video(message: types.Message, state: FSMContext):
    if not message.video:
        await message.answer("Por favor, envie um arquivo de vídeo.", reply_markup=teclado_cancelar)
        return

    msg_status = await message.answer("📥 Baixando e analisando o vídeo com a IA... Aguarde. ⏳", reply_markup=teclado_cancelar)
    file_id = message.video.file_id
    
    try:
        # 1. Download do vídeo para o servidor Ubuntu
        file_info = await bot.get_file(file_id)
        video_path = f"temp_{file_id}.mp4"
        await bot.download_file(file_info.file_path, destination=video_path)

        # 2. Upload para a API do Gemini processar a Copy
        def analisar_video():
            import time # ✅ Biblioteca necessária para criar a pausa de verificação
            if EXIBIR_LOGS: logger.info("📤 Fazendo upload do vídeo para o Google Storage...")
            video_gemini = client.files.upload(file=video_path)
            
            # OBRIGATÓRIO: Loop que aguarda a API processar o vídeo
            if EXIBIR_LOGS: logger.info("⏳ Aguardando processamento do vídeo pelo Google...")
            while video_gemini.state.name == "PROCESSING":
                time.sleep(2)
                video_gemini = client.files.get(name=video_gemini.name)
                
            if video_gemini.state.name == "FAILED":
                raise Exception("Falha de processamento no servidor do Google.")

            if EXIBIR_LOGS: logger.info("✅ Vídeo pronto! Gerando a copy persuasiva...")
            
            # ✅ Lê o número atual para informar a IA
            numero_atual = ler_contador()
            
            prompt_ia = (
                f"Você é um copywriter da Shopee. Assista ao vídeo e crie uma legenda de vendas. "
                f"IMPORTANTE: Inicie OBRIGATORIAMENTE o texto com 'Vídeo {numero_atual} - [Nome do Produto]'. "
                f"Destaque os benefícios e use emojis. Não peça links e não use aspas."
            )
            
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[video_gemini, prompt_ia]
            )
            return response.text.strip()

        # Executa a IA de forma assíncrona para não travar o bot
        chamada_gerada = await asyncio.to_thread(analisar_video)
        
        # 3. Limpeza do servidor
        if os.path.exists(video_path): os.remove(video_path)
        
        await state.update_data(video_id=file_id, nome_produto=chamada_gerada, links=[])
        await msg_status.delete()
        
        # Exibe a arte gerada para sua aprovação
        await message.answer(f"**Texto Criado:**\n\n{chamada_gerada}\n\nFicou bom?", reply_markup=teclado_confirmacao, parse_mode="Markdown")
        await state.set_state(PostagemFluxo.aguardando_confirmacao_nome)

    except Exception as e:
        if os.path.exists(f"temp_{file_id}.mp4"): os.remove(f"temp_{file_id}.mp4")
        if EXIBIR_LOGS: logger.error(f"❌ Erro na IA: {e}")
        await msg_status.delete()
        await message.answer("A IA falhou ao ler o vídeo. Digite manualmente o texto da postagem:", reply_markup=teclado_cancelar)
        await state.update_data(video_id=file_id, links=[])
        await state.set_state(PostagemFluxo.aguardando_chamada_manual)

@dp.message(PostagemFluxo.aguardando_confirmacao_nome)
async def confirmar_nome(message: types.Message, state: FSMContext):
    if message.text == "Aprovar ✅":
        await message.answer("Show! Agora mande os links um por um e clique em 'Finalizar'.", reply_markup=teclado_finalizar)
        await state.set_state(PostagemFluxo.aguardando_links)
    elif message.text == "Tentar Novamente 🔄":
        await message.answer("Sem problemas. Digite como você quer que fique a legenda:", reply_markup=teclado_cancelar)
        await state.set_state(PostagemFluxo.aguardando_chamada_manual)

@dp.message(PostagemFluxo.aguardando_chamada_manual)
async def receber_chamada_manual(message: types.Message, state: FSMContext):
    await state.update_data(nome_produto=message.text)
    await message.answer("Legenda salva! Agora envie os links e clique em 'Finalizar'.", reply_markup=teclado_finalizar)
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
    
    numero_atual = ler_contador()
    
    # Mensagem 1: Apresentação do Produto
    texto_intro = f"**Vídeo {numero_atual}**\n" \
                  f"📦 Item: {nome}"
    await bot.send_message(GRUPO_ID, texto_intro, parse_mode="Markdown")
    
    # Mensagem 2: Vídeo do Produto
    await bot.send_video(GRUPO_ID, video)
    
    # Mensagem 3: Lista de Links Limpa
    texto_links = "🔗 **Links da Shopee:**\n\n"
    for i, link in enumerate(links, 1):
        texto_links += f"👉 {i}º Link: {link}\n"
        
    await bot.send_message(GRUPO_ID, texto_links, parse_mode="Markdown")
    
    # ✅ Incrementa o contador para o próximo vídeo
    salvar_contador(numero_atual + 1)
    if EXIBIR_LOGS: logger.info(f"🔢 Contador atualizado de {numero_atual} para {numero_atual + 1}.")
    
    await message.answer(f"Postagem enviada com sucesso! ✅\nO próximo vídeo será o número {numero_atual + 1}.", reply_markup=obter_teclado_principal())
    await state.clear()

# ✅ Handlers para Gerenciar a Numeração
@dp.message(F.text == "Zerar Contador 🔄")
async def zerar_numero(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    salvar_contador(1)
    if EXIBIR_LOGS: logger.info("🔢 Contador zerado pelo administrador.")
    await message.answer("Contador zerado! O próximo post será o 'Vídeo 1'.", reply_markup=obter_teclado_principal())

@dp.message(F.text == "Editar Número ✏️")
async def pedir_novo_numero(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    numero_atual = ler_contador()
    await message.answer(f"O próximo vídeo será o {numero_atual}.\n\nDigite o novo número que deseja usar (apenas números):", reply_markup=teclado_cancelar)
    await state.set_state(ConfigFluxo.aguardando_novo_numero)

@dp.message(ConfigFluxo.aguardando_novo_numero)
async def salvar_novo_numero(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        novo_numero = int(message.text)
        salvar_contador(novo_numero)
        if EXIBIR_LOGS: logger.info(f"🔢 Contador editado manualmente para: {novo_numero}.")
        await message.answer(f"Sucesso! O próximo post será o 'Vídeo {novo_numero}'.", reply_markup=obter_teclado_principal())
        await state.clear()
    else:
        await message.answer("Por favor, digite apenas números. Exemplo: 50", reply_markup=teclado_cancelar)

async def main():
    # Agendador mestre que roda todo dia às 00:01
    scheduler.add_job(agendar_tarefas_diarias, 'cron', hour=0, minute=1)
    
    # Roda o agendador imediatamente ao ligar o bot para garantir o dia atual
    agendar_tarefas_diarias() 
    
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
