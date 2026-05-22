# 0. CONFIGURAÇÕES INICIAIS
EXIBIR_LOGS = True
import os
from dotenv import load_dotenv
load_dotenv()
import logging
import json
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
    # ✅ Novos estados para o fluxo aprimorado
    aguardando_plataforma = State()
    aguardando_link_video_shopee = State()
    aguardando_link_video_tiktok = State()
    # ✅ Estados separados para coletar os links corretos de cada plataforma
    aguardando_links_shopee = State()
    aguardando_links_tiktok = State()

class ConfigFluxo(StatesGroup):
    aguardando_novo_numero = State()

class ConfigDivulgacao(StatesGroup):
    aguardando_alvos = State()
    aguardando_frequencia = State()

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
fuso_horario = ZoneInfo("America/Sao_Paulo")
scheduler = AsyncIOScheduler(timezone=fuso_horario)

# --- NOVOS TECLADOS DE CONTROLE ---
# 🛠️ Teclado para seleção da plataforma
teclado_plataforma = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Ambos 🛒🎵")],
        [KeyboardButton(text="Apenas Shopee 🛒"), KeyboardButton(text="Apenas TikTok 🎵")],
        [KeyboardButton(text="Cancelar ❌")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

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
        [KeyboardButton(text="Zerar Contador 🔄"), KeyboardButton(text="Editar Número ✏️")],
        [KeyboardButton(text="Configurar Divulgação 🎯")]
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

async def apagar_mensagem_automatica(msg_id):
    try:
        await bot.delete_message(chat_id=GRUPO_ID, message_id=msg_id)
        if EXIBIR_LOGS: logger.info(f"🧹 Faxina concluída: Mensagem automática {msg_id} apagada após 24h.")
    except Exception as e:
        if EXIBIR_LOGS: logger.info(f"⚠️ Faxina: A mensagem {msg_id} já havia sido apagada manualmente ou não foi encontrada.")

async def disparar_mensagem(tipo):
    # ✅ Contexto atualizado com limitação estrita de caracteres
    contexto_afiliado = (
        "Você é um assistente de suporte para afiliados da Shopee. "
        "REGRA ABSOLUTA: Sua resposta deve ser extremamente curta e direta, "
        "contendo NO MÁXIMO 200 CARACTERES no total. "
        "Entregue APENAS o texto da mensagem, sem introduções e sem aspas."
    )

    if tipo == "bom_dia":
        prompt = (
            f"{contexto_afiliado} Crie uma mensagem de bom dia motivadora. "
            "Diga que os vídeos de hoje estão prontos para postagem. Use emojis."
        )
    elif tipo == "boa_noite":
        prompt = (
            f"{contexto_afiliado} Crie uma mensagem de boa noite. "
            "Sugira que organizem os links para amanhã. Use emojis."
        )
    elif tipo == "incentivo":
        prompt = (
            f"{contexto_afiliado} Crie uma frase de impacto sobre persistência no tráfego orgânico. Use emojis."
        )
    elif tipo == "link_grupo":
        prompt = (
            f"{contexto_afiliado} Não peça para postar vídeos. Crie um convite rápido e chamativo pedindo aos membros que convidem "
            "amigos afiliados para o nosso grupo gratuito. Não adicione nenhum link na sua resposta. Use emojis."
        )

    elif tipo.startswith("campanha_"):
        dias_restantes = int(tipo.split("_")[1])
        if dias_restantes == 0:
            aviso = "É HOJE o evento de data dupla! Disparem seus links nas redes!"
        elif dias_restantes == 1:
            aviso = "É AMANHÃ o evento de data dupla! Preparem todos os materiais!"
        else:
            aviso = f"Faltam {dias_restantes} dias para o evento de data dupla. Antecipem a organização!"
        
        prompt = (
            f"Você atua como assistente de afiliados. Crie um alerta baseado no seguinte status: '{aviso}'. "
            f"REGRA ABSOLUTA: Sua resposta final deve conter NO MÁXIMO 100 CARACTERES. "
            f"Transmita urgência, use emojis e entregue estritamente o texto pronto, sem aspas."
        )

    elif tipo == "divulgar_gem":
        prompt = (
            "Você atua como assistente de afiliados. Crie uma mensagem curta (MÁXIMO 200 CARACTERES) "
            "perguntando se a equipe está com dificuldade para criar legendas e hashtags. "
            "Convide-os a usar nosso prompt automatizado. Insinue de forma sutil que utilizar a "
            "versão PRO do Gemini resulta em textos muito melhores. Altere as palavras e a abordagem "
            "toda vez que gerar esse texto, use emojis e entregue apenas a mensagem pronta, sem aspas."
        )

    texto = await gerar_mensagem_gemini(prompt)
    if EXIBIR_LOGS: logger.info(f"🚀 Enviando mensagem principal ({tipo}): {texto[:20]}...")
    msg_enviada = await bot.send_message(GRUPO_ID, texto)
    
    from datetime import timedelta
    data_exclusao = datetime.now(fuso_horario) + timedelta(hours=24)
    scheduler.add_job(apagar_mensagem_automatica, 'date', run_date=data_exclusao, args=[msg_enviada.message_id])
    
    # ✅ Disparo condicional: Envia o link separado apenas na divulgação e no GEM
    if tipo == "link_grupo":
        link_separado = f"👇 <b>Link de Convite:</b>\n{LINK_GRUPO}"
        if EXIBIR_LOGS: logger.info("🔗 Enviando link do grupo em mensagem isolada.")
        msg_link = await bot.send_message(GRUPO_ID, link_separado, parse_mode="HTML")
        scheduler.add_job(apagar_mensagem_automatica, 'date', run_date=data_exclusao, args=[msg_link.message_id])
    elif tipo == "divulgar_gem":
        link_gem = "👇 <b>Acesse o Prompt Automatizado:</b>\nhttps://gemini.google.com/gem/1HtJMuknyMZ76utOu-i6c_xvc3vmQx7bT?usp=sharing"
        if EXIBIR_LOGS: logger.info("🤖 Enviando link do GEM em mensagem isolada.")
        msg_gem = await bot.send_message(GRUPO_ID, link_gem, parse_mode="HTML")
        scheduler.add_job(apagar_mensagem_automatica, 'date', run_date=data_exclusao, args=[msg_gem.message_id])

def agendar_tarefas_diarias():
    if EXIBIR_LOGS: logger.info("🔄 Sorteando horários das postagens de hoje...")
    
    minuto_manha = random.randint(0, 59)
    hora_incentivo = random.randint(8, 21)
    minuto_incentivo = random.randint(0, 59)
    minuto_noite = random.randint(0, 59)
    
    # ✅ Sorteio dos 3 turnos de divulgação
    hora_link_manha = random.randint(9, 12)
    minuto_link_manha = random.randint(0, 59)
    
    hora_link_tarde = random.randint(14, 17)
    minuto_link_tarde = random.randint(0, 59)
    
    hora_link_noite = random.randint(18, 21)
    minuto_link_noite = random.randint(0, 59)
    
    scheduler.add_job(disparar_mensagem, 'cron', hour=7, minute=minuto_manha, args=["bom_dia"], id='job_manha', replace_existing=True)
    scheduler.add_job(disparar_mensagem, 'cron', hour=hora_incentivo, minute=minuto_incentivo, args=["incentivo"], id='job_incentivo', replace_existing=True)
    scheduler.add_job(disparar_mensagem, 'cron', hour=22, minute=minuto_noite, args=["boa_noite"], id='job_noite', replace_existing=True)
    
    # ✅ Agendamento dos 3 disparos de convite
    scheduler.add_job(disparar_mensagem, 'cron', hour=hora_link_manha, minute=minuto_link_manha, args=["link_grupo"], id='job_link_manha', replace_existing=True)
    scheduler.add_job(disparar_mensagem, 'cron', hour=hora_link_tarde, minute=minuto_link_tarde, args=["link_grupo"], id='job_link_tarde', replace_existing=True)
    scheduler.add_job(disparar_mensagem, 'cron', hour=hora_link_noite, minute=minuto_link_noite, args=["link_grupo"], id='job_link_noite', replace_existing=True)

    # ✅ Agendamento do disparo diário do GEM (Sorteio restrito entre 08h e 22h)
    hora_gem = random.randint(8, 22)
    minuto_gem = random.randint(0, 59)
    scheduler.add_job(disparar_mensagem, 'cron', hour=hora_gem, minute=minuto_gem, args=["divulgar_gem"], id='job_divulgar_gem', replace_existing=True)

    from datetime import datetime, timedelta
    hoje_alvo = datetime.now(fuso_horario)
    
    for i in range(4):
        data_futura = hoje_alvo + timedelta(days=i)
        if data_futura.day == data_futura.month:
            if EXIBIR_LOGS: logger.info(f"🎉 Mega Campanha {data_futura.day:02d}.{data_futura.month:02d} rastreada! Faltam {i} dias.")
            
            hora_c_manha = random.randint(8, 11)
            min_c_manha = random.randint(0, 59)
            
            hora_c_tarde = random.randint(14, 17)
            min_c_tarde = random.randint(0, 59)
            
            hora_c_noite = random.randint(18, 21)
            min_c_noite = random.randint(0, 59)
            
            tipo_alerta = f"campanha_{i}"
            
            scheduler.add_job(disparar_mensagem, 'cron', hour=hora_c_manha, minute=min_c_manha, args=[tipo_alerta], id='job_campanha_manha', replace_existing=True)
            scheduler.add_job(disparar_mensagem, 'cron', hour=hora_c_tarde, minute=min_c_tarde, args=[tipo_alerta], id='job_campanha_tarde', replace_existing=True)
            scheduler.add_job(disparar_mensagem, 'cron', hour=hora_c_noite, minute=min_c_noite, args=[tipo_alerta], id='job_campanha_noite', replace_existing=True)
            
            if EXIBIR_LOGS:
                logger.info(f"⏳ Alerta Campanha Manhã: {hora_c_manha:02d}:{min_c_manha:02d}")
                logger.info(f"⏳ Alerta Campanha Tarde: {hora_c_tarde:02d}:{min_c_tarde:02d}")
                logger.info(f"⏳ Alerta Campanha Noite: {hora_c_noite:02d}:{min_c_noite:02d}")
            break
    
    if EXIBIR_LOGS:
        logger.info(f"📅 Bom dia: 07:{minuto_manha:02d}")
        logger.info(f"📅 Incentivo: {hora_incentivo:02d}:{minuto_incentivo:02d}")
        logger.info(f"📅 Boa noite: 22:{minuto_noite:02d}")
        logger.info(f"📢 Divulgação Manhã: {hora_link_manha:02d}:{minuto_link_manha:02d}")
        logger.info(f"📢 Divulgação Tarde: {hora_link_tarde:02d}:{minuto_link_tarde:02d}")
        logger.info(f"📢 Divulgação Noite: {hora_link_noite:02d}:{minuto_link_noite:02d}")
        logger.info(f"🤖 Divulgação GEM: {hora_gem:02d}:{minuto_gem:02d}")

# 5. HANDLERS DE COMANDO E INTERAÇÃO
@dp.message(Command("start"))
async def comando_start(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("⌨️ Atualizando menu principal.")
    await message.answer("Painel de Controle atualizado. Escolha uma ação abaixo:", reply_markup=obter_teclado_principal())

# ✅ Handlers para Envio Manual de Mensagens via Botões
@dp.message(F.text == "Enviar mensagem de Bom Dia ☀️")
async def manual_bom_dia(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Gerando e enviando mensagem de Bom Dia... ⏳")
    await disparar_mensagem("bom_dia")
    await message.answer("Mensagem de Bom Dia enviada ao grupo com sucesso! ✅")

@dp.message(F.text == "Enviar mensagem de Boa Noite 🌙")
async def manual_boa_noite(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Gerando e enviando mensagem de Boa Noite... ⏳")
    await disparar_mensagem("boa_noite")
    await message.answer("Mensagem de Boa Noite enviada ao grupo com sucesso! ✅")

@dp.message(F.text == "Enviar mensagem de Incentivo 🔥")
async def manual_incentivo(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Gerando e enviando mensagem de Incentivo... ⏳")
    await disparar_mensagem("incentivo")
    await message.answer("Mensagem de Incentivo enviada ao grupo com sucesso! ✅")

@dp.message(F.text == "Divulgar Grupo 📢")
async def manual_link_grupo(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Gerando e enviando divulgação do grupo... ⏳")
    await disparar_mensagem("link_grupo")
    await message.answer("Mensagem de divulgação enviada ao grupo com sucesso! ✅")

# ❌ NOVO: Handler Global para Cancelar via Botão (Agora 100% à prova de falhas)
@dp.message(F.text == "Cancelar ❌")
async def cancelar_fluxo_global(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("❌ Ação cancelada ou resetada via botão.")
    await state.clear()
    await message.answer("Ação cancelada e memória limpa. Voltando ao menu...", reply_markup=obter_teclado_principal())

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
            
            # ✅ Prompt ajustado para remover a repetição do nome no título
            prompt_ia = (
                f"Assista ao vídeo INTEIRO para identificar o produto ou kit principal. "
                f"Sua resposta deve conter EXATAMENTE duas linhas. "
                f"Na primeira linha, escreva estritamente: 'Vídeo {numero_atual}'. "
                f"Na segunda linha, escreva '📦 Item: ' seguido do nome do produto ou kit identificado. "
                f"Exemplo de saída esperada:\n"
                f"Vídeo {numero_atual}\n"
                f"📦 Item: Kit Dove Reconstrução\n"
                f"Não adicione nenhuma outra palavra, ponto final extra ou descrição."
            )
            
            # ✅ Mini-cascata para o vídeo: Se o modelo 3-flash esgotar a cota, tenta o 2.5-flash
            try:
                response = client.models.generate_content(
                    model="gemini-3-flash-preview",
                    contents=[video_gemini, prompt_ia]
                )
            except Exception as erro_modelo:
                if "429" in str(erro_modelo):
                    if EXIBIR_LOGS: logger.warning("⚠️ Limite do 3-flash atingido. Usando 2.5-flash como fallback...")
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[video_gemini, prompt_ia]
                    )
                else:
                    raise erro_modelo

            return response.text.strip()

        # Executa a IA de forma assíncrona para não travar o bot
        chamada_gerada = await asyncio.to_thread(analisar_video)
        
        # 3. Limpeza do servidor
        if os.path.exists(video_path): os.remove(video_path)
        
        # ✅ Salva APENAS o texto limpo da IA na memória para a postagem final
        await state.update_data(video_id=file_id, nome_produto=chamada_gerada, links=[])
        await msg_status.delete()
        
        # ✅ Junta o texto da IA com uma pergunta orientativa apenas para exibição ao administrador
        mensagem_aprovacao = f"{chamada_gerada}\n\n👉 <b>Esta identificação está correta?</b> Escolha uma opção abaixo:"
        
        await message.answer(mensagem_aprovacao, reply_markup=teclado_confirmacao, parse_mode="HTML")
        await state.set_state(PostagemFluxo.aguardando_confirmacao_nome)

    except Exception as e:
        erro_str = str(e)
        if os.path.exists(f"temp_{file_id}.mp4"): os.remove(f"temp_{file_id}.mp4")
        if EXIBIR_LOGS: logger.error(f"❌ Erro na IA ou Download: {erro_str}")
        await msg_status.delete()
        
        # ✅ Analisa o erro e traduz para o usuário
        motivo = "Falha no servidor."
        if "file is too big" in erro_str.lower():
            motivo = "O vídeo ultrapassa o limite de 20MB do Telegram para Bots."
        elif "429" in erro_str:
            motivo = "Limite de velocidade da IA atingido. Aguarde 1 minuto."
        else:
            motivo = erro_str[:150] # Exibe o começo do erro técnico
            
        await message.answer(f"⚠️ A IA não conseguiu processar este vídeo.\n**Motivo:** {motivo}\n\nDigite manualmente APENAS O NOME DO PRODUTO ou clique em Cancelar:", reply_markup=teclado_cancelar)
        
        await state.update_data(video_id=file_id, links=[])
        await state.set_state(PostagemFluxo.aguardando_chamada_manual)

@dp.message(PostagemFluxo.aguardando_confirmacao_nome)
async def confirmar_nome(message: types.Message, state: FSMContext):
    if message.text == "Aprovar ✅":
        # ✅ Fluxo modificado: em vez de pedir os links de produto, pede a plataforma primeiro
        await message.answer("Onde você postou/vai postar este vídeo?", reply_markup=teclado_plataforma)
        await state.set_state(PostagemFluxo.aguardando_plataforma)
    elif message.text == "Tentar Novamente 🔄":
        await message.answer("Sem problemas. Digite manualmente APENAS O NOME DO PRODUTO:", reply_markup=teclado_cancelar)
        await state.set_state(PostagemFluxo.aguardando_chamada_manual)

@dp.message(PostagemFluxo.aguardando_chamada_manual)
async def receber_chamada_manual(message: types.Message, state: FSMContext):
    numero_atual = ler_contador()
    nome_formatado = f"Vídeo {numero_atual}\n📦 Item: {message.text.strip()}"
    
    if EXIBIR_LOGS: logger.info(f"✍️ Identificação manual formatada automaticamente: Vídeo {numero_atual}.")
    
    await state.update_data(nome_produto=nome_formatado)
    await message.answer(f"Identificação salva como:\n\n{nome_formatado}\n\nOnde você postou/vai postar este vídeo?", reply_markup=teclado_plataforma)
    await state.set_state(PostagemFluxo.aguardando_plataforma)

@dp.message(PostagemFluxo.aguardando_plataforma)
async def receber_plataforma(message: types.Message, state: FSMContext):
    plataforma = message.text
    if plataforma not in ["Ambos 🛒🎵", "Apenas Shopee 🛒", "Apenas TikTok 🎵"]:
        await message.answer("Por favor, use os botões para escolher a plataforma.")
        return
        
    await state.update_data(plataforma_escolhida=plataforma, links_shopee=[], links_tiktok=[])
    
    if plataforma in ["Ambos 🛒🎵", "Apenas Shopee 🛒"]:
        if EXIBIR_LOGS: logger.info("🔀 Direcionando para fluxo de vídeo da Shopee.")
        await message.answer("Certo! Agora envie o <b>Link do Vídeo</b> que você postou na <b>SHOPEE</b>.", reply_markup=teclado_cancelar, parse_mode="HTML")
        await state.set_state(PostagemFluxo.aguardando_link_video_shopee)
    else:
        if EXIBIR_LOGS: logger.info("🔀 Direcionando para fluxo de vídeo do TikTok.")
        await message.answer("Certo! Agora envie o <b>Link do Vídeo</b> que você postou no <b>TIKTOK</b>.", reply_markup=teclado_cancelar, parse_mode="HTML")
        await state.set_state(PostagemFluxo.aguardando_link_video_tiktok)

@dp.message(PostagemFluxo.aguardando_link_video_shopee)
async def receber_link_video_shopee(message: types.Message, state: FSMContext):
    if EXIBIR_LOGS: logger.info("📥 Recebido link do vídeo da Shopee.")
    await state.update_data(link_video_shopee=message.text)
    await message.answer("Link do vídeo da Shopee salvo! 🛒\n\nAgora, envie os links dos <b>produtos da SHOPEE</b> um por um. Clique em 'Finalizar' quando terminar.", reply_markup=teclado_finalizar, parse_mode="HTML")
    await state.set_state(PostagemFluxo.aguardando_links_shopee)

@dp.message(PostagemFluxo.aguardando_link_video_tiktok)
async def receber_link_video_tiktok(message: types.Message, state: FSMContext):
    if EXIBIR_LOGS: logger.info("📥 Recebido link do vídeo do TikTok.")
    await state.update_data(link_video_tiktok=message.text)
    await message.answer("Link do vídeo do TikTok salvo! 🎵\n\nAgora, envie os links dos <b>produtos do TIKTOK</b> um por um. Clique em 'Finalizar' quando acabar.", reply_markup=teclado_finalizar, parse_mode="HTML")
    await state.set_state(PostagemFluxo.aguardando_links_tiktok)

@dp.message(PostagemFluxo.aguardando_links_shopee)
async def receber_links_shopee(message: types.Message, state: FSMContext):
    data = await state.get_data()
    links = data.get('links_shopee', [])
    
    if message.text in ["Finalizar ✅", "/finalizar"]:
        plataforma = data['plataforma_escolhida']
        if plataforma == "Ambos 🛒🎵":
            if EXIBIR_LOGS: logger.info("🔀 Transição manual: Produtos Shopee concluídos.")
            await message.answer("Links da Shopee salvos! 🛒\n\nAgora, envie o <b>Link do Vídeo</b> que você postou no <b>TIKTOK</b>.", reply_markup=teclado_cancelar, parse_mode="HTML")
            await state.set_state(PostagemFluxo.aguardando_link_video_tiktok)
        else:
            if EXIBIR_LOGS: logger.info("✅ Fluxo Shopee concluído manualmente.")
            await finalizar_postagem(message, state)
        return

    links.append(message.text)
    await state.update_data(links_shopee=links)
    
    if len(links) >= 6:
        if EXIBIR_LOGS: logger.info("✅ 🎯 Limite máximo de links da Shopee alcançado.")
        await message.answer("Link Shopee 6/6 registrado.\nLimite atingido, avançando para a próxima etapa...", parse_mode="HTML")
        
        plataforma = data['plataforma_escolhida']
        if plataforma == "Ambos 🛒🎵":
            if EXIBIR_LOGS: logger.info("🔀 Transição automática: solicitando vídeo do TikTok.")
            await message.answer("Links da Shopee salvos! 🛒\n\nAgora, envie o <b>Link do Vídeo</b> que você postou no <b>TIKTOK</b>.", reply_markup=teclado_cancelar, parse_mode="HTML")
            await state.set_state(PostagemFluxo.aguardando_link_video_tiktok)
        else:
            if EXIBIR_LOGS: logger.info("✅ Fluxo Shopee concluído por limite automático.")
            await finalizar_postagem(message, state)
    else:
        if EXIBIR_LOGS: logger.info(f"🔗 Link Shopee {len(links)}/6 validado.")
        await message.answer(f"Link Shopee {len(links)}/6 registrado. Envie o próximo ou clique em Finalizar.", reply_markup=teclado_finalizar)

@dp.message(PostagemFluxo.aguardando_links_tiktok)
async def receber_links_tiktok(message: types.Message, state: FSMContext):
    data = await state.get_data()
    links = data.get('links_tiktok', [])

    if message.text in ["Finalizar ✅", "/finalizar"]:
         if EXIBIR_LOGS: logger.info("✅ Fluxo TikTok concluído manualmente.")
         await finalizar_postagem(message, state)
         return

    links.append(message.text)
    await state.update_data(links_tiktok=links)
    
    if len(links) >= 6:
         if EXIBIR_LOGS: logger.info("✅ 🎯 Limite máximo de links do TikTok alcançado.")
         await message.answer("Link TikTok 6/6 registrado.\nLimite atingido, finalizando a postagem...", parse_mode="HTML")
         await finalizar_postagem(message, state)
    else:
         if EXIBIR_LOGS: logger.info(f"🔗 Link TikTok {len(links)}/6 validado.")
         await message.answer(f"Link TikTok {len(links)}/6 registrado. Envie o próximo ou clique em Finalizar.", reply_markup=teclado_finalizar)

async def finalizar_postagem(message: types.Message, state: FSMContext):
    data = await state.get_data()
    nome = data['nome_produto']
    video = data['video_id']
    plataforma = data['plataforma_escolhida']
    link_vid_shopee = data.get('link_video_shopee', "")
    link_vid_tiktok = data.get('link_video_tiktok', "")
    links_shopee = data.get('links_shopee', [])
    links_tiktok = data.get('links_tiktok', [])
    
    if EXIBIR_LOGS: logger.info("📤 Iniciando montagem inteligente da legenda (3 níveis).")
    numero_atual = ler_contador()
    
    # Substitui a quebra de linha por espaço e formata o título
    titulo_limpo = nome.replace('\n', ' | ')
    linha_divisoria = "━━━━━━━━━━━━━━━"
    cabecalho = f"<b>{titulo_limpo}</b>\n\n{linha_divisoria}\n\n"
    
    texto_longo = "<i>(💡 O nosso grupo é 100% gratuito. Para nos ajudar a continuar trazendo conteúdos, por favor, clique no link do vídeo acima, assista, curta, comente e siga o perfil! Isso nos ajuda muito!)</i>\n\n"
    texto_curto = "<i>(💡 Grupo 100% gratuito. Curta e comente nos vídeos para ajudar!)</i>\n\n"
    texto_rodape = "\n<i>(💡 Grupo 100% gratuito. Curta e comente nos vídeos para ajudar!)</i>"

    def montar_legenda(mensagem_apoio, is_rodape=False, plataforma_alvo=None):
        plat_atual = plataforma_alvo if plataforma_alvo else plataforma
        legenda_temp = cabecalho
        
        if plat_atual in ["Ambos 🛒🎵", "Apenas Shopee 🛒"]:
            legenda_temp += f"🔶 <b>SHOPEE VÍDEO</b> 🔶\n\n"
            legenda_temp += f"🎬 Link do Vídeo:\n{link_vid_shopee}\n"
            if not is_rodape:
                legenda_temp += mensagem_apoio
            if links_shopee:
                legenda_temp += "🔗 Links dos Produtos:\n"
                for i, link in enumerate(links_shopee, 1):
                    legenda_temp += f"👉 {i}º: {link}\n"
            if plat_atual == "Ambos 🛒🎵":
                legenda_temp += f"\n{linha_divisoria}\n\n"
            else:
                legenda_temp += "\n"
                
        if plat_atual in ["Ambos 🛒🎵", "Apenas TikTok 🎵"]:
            legenda_temp += f"⬛ <b>TIKTOK</b> ⬛\n\n"
            legenda_temp += f"🎬 Link do Vídeo:\n{link_vid_tiktok}\n"
            if not is_rodape:
                legenda_temp += mensagem_apoio
            if links_tiktok:
                legenda_temp += "🔗 Links dos Produtos:\n"
                for i, link in enumerate(links_tiktok, 1):
                    legenda_temp += f"👉 {i}º: {link}\n"
            legenda_temp += "\n"
        
        if is_rodape:
            legenda_temp += mensagem_apoio
            
        return legenda_temp

    # Nível 1: Tenta o texto longo duplo
    legenda_final = montar_legenda(texto_longo, is_rodape=False)
    if EXIBIR_LOGS: logger.info(f"📏 Avaliando Nível 1: {len(legenda_final)} caracteres.")
    
    nivel_4_ativado = False

    if len(legenda_final) > 1024:
        if EXIBIR_LOGS: logger.warning("⚠️ Limite excedido no Nível 1. Ativando Nível 2 (texto curto duplo).")
        legenda_final = montar_legenda(texto_curto, is_rodape=False)
        if EXIBIR_LOGS: logger.info(f"📏 Avaliando Nível 2: {len(legenda_final)} caracteres.")
        
        if len(legenda_final) > 1024:
            if EXIBIR_LOGS: logger.warning("⚠️ Limite excedido no Nível 2. Ativando Nível 3 (rodapé simples).")
            legenda_final = montar_legenda(texto_rodape, is_rodape=True)
            if EXIBIR_LOGS: logger.info(f"📏 Avaliando Nível 3: {len(legenda_final)} caracteres.")
            
            if len(legenda_final) > 1024 and plataforma == "Ambos 🛒🎵":
                if EXIBIR_LOGS: logger.warning("🚨 Limite crítico excedido no Nível 3. Ativando Nível 4 (Divisão de Postagem).")
                nivel_4_ativado = True

    if nivel_4_ativado:
        # Envia a publicação fracionada em duas mensagens
        legenda_shopee = montar_legenda(texto_longo, is_rodape=False, plataforma_alvo="Apenas Shopee 🛒")
        if EXIBIR_LOGS: logger.info("🎥 Disparando vídeo 1/2 (Exclusivo Shopee).")
        await bot.send_video(chat_id=GRUPO_ID, video=video, caption=legenda_shopee, parse_mode="HTML")
        
        legenda_tiktok = montar_legenda(texto_longo, is_rodape=False, plataforma_alvo="Apenas TikTok 🎵")
        if EXIBIR_LOGS: logger.info("🎥 Disparando vídeo 2/2 (Exclusivo TikTok).")
        await bot.send_video(chat_id=GRUPO_ID, video=video, caption=legenda_tiktok, parse_mode="HTML")
    else:
        # Envia o vídeo com a legenda consolidada e validada
        if EXIBIR_LOGS: logger.info("🎥 Disparando vídeo com a legenda encapsulada.")
        await bot.send_video(chat_id=GRUPO_ID, video=video, caption=legenda_final, parse_mode="HTML")
    
    # Incrementa o contador para o próximo vídeo
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

@dp.message(F.text == "Configurar Divulgação 🎯")
async def iniciar_config_divulgacao(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("⚙️ Iniciando configuração de alvos de divulgação.")
    await message.answer(
        "Vamos configurar os grupos de destino.\n"
        "Envie os links ou IDs dos grupos separados por vírgula.\n\n"
        "Exemplo de resposta: <code>https://t.me/grupo1, -1009999999, @grupo3</code>",
        reply_markup=teclado_cancelar,
        parse_mode="HTML"
    )
    await state.set_state(ConfigDivulgacao.aguardando_alvos)

@dp.message(ConfigDivulgacao.aguardando_alvos)
async def receber_alvos(message: types.Message, state: FSMContext):
    alvos = [alvo.strip() for alvo in message.text.split(",") if alvo.strip()]
    if not alvos:
        await message.answer("Nenhum alvo detectado. Tente novamente separando por vírgula:", reply_markup=teclado_cancelar)
        return
    await state.update_data(alvos=alvos)
    if EXIBIR_LOGS: logger.info(f"✅ Alvos registrados: {alvos}")
    await message.answer(
        "Alvos salvos com sucesso!\n"
        "Agora, digite quantas mensagens por hora devem ser enviadas em cada grupo.\n\n"
        "Exemplo de resposta: <code>3</code>",
        reply_markup=teclado_cancelar,
        parse_mode="HTML"
    )
    await state.set_state(ConfigDivulgacao.aguardando_frequencia)

@dp.message(ConfigDivulgacao.aguardando_frequencia)
async def receber_frequencia(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Envie apenas números. Exemplo: 3", reply_markup=teclado_cancelar)
        return
    
    frequencia = int(message.text)
    data = await state.get_data()
    alvos = data.get("alvos", [])
    
    config = {
        "alvos": alvos,
        "frequencia_por_hora": frequencia
    }
    
    with open("alvos_divulgacao.json", "w") as f:
        json.dump(config, f, indent=4)
        
    if EXIBIR_LOGS: logger.info(f"💾 Configuração salva no JSON: {frequencia} msgs/hora para {len(alvos)} alvos.")
    
    await message.answer(
        f"Tudo pronto! 🚀\nO arquivo foi atualizado. O sistema de divulgação fará {frequencia} envios por hora nos alvos informados.",
        reply_markup=obter_teclado_principal()
    )
    await state.clear()

async def main():
    # Agendador mestre que roda todo dia às 00:01
    scheduler.add_job(agendar_tarefas_diarias, 'cron', hour=0, minute=1)
    
    # Roda o agendador imediatamente ao ligar o bot para garantir o dia atual
    agendar_tarefas_diarias() 
    
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
