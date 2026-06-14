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
import time
import hmac
import hashlib
import aiohttp
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command, StateFilter
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, FSInputFile
import subprocess
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google import genai

# 1. CONSTANTES E TOKENS
API_TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = 1226920464
GRUPO_ID = -1003909405581
LINK_GRUPO = "https://t.me/shopee_video_afiliado"
GEMINI_API_KEY = os.getenv('GEMINI_KEY')
SHOPEE_APP_ID = os.getenv('SHOPEE_APP_ID')
SHOPEE_APP_SECRET = os.getenv('SHOPEE_APP_SECRET')

MODELOS_CASCATA_GEMINI = [
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-pro"
]

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
    aguardando_confirmacao_zerar = State()

class ConfigDivulgacao(StatesGroup):
    menu_principal = State()
    aguardando_alvos = State()
    aguardando_exclusao_alvo = State()
    # Novos estados para a edição unificada (Global vs Individual)
    aguardando_tipo_edicao = State()
    aguardando_selecao_alvo = State()
    aguardando_valores_unificados = State()

class ConfigRotina(StatesGroup):
    menu_principal = State()
    aguardando_novo_horario = State()

class ConfigPausa(StatesGroup):
    menu_principal = State()

class PausaProgramadaFluxo(StatesGroup):
    aguardando_data_retorno = State()
    aguardando_selecao_servicos = State()

class EspiaoFluxo(StatesGroup):
    menu_principal = State()
    aguardando_novo_alvo = State()
    aguardando_remocao_alvo = State()
    aguardando_canal_destino = State()

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
FUSO_STR = "America/Sao_Paulo"
fuso_horario = ZoneInfo(FUSO_STR)
_lock_contador = asyncio.Lock()
scheduler = AsyncIOScheduler(timezone=FUSO_STR)

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

# 🛠️ Teclado de sub-menu para edição da numeração
teclado_opcoes_numero = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Editar Número ✏️"), KeyboardButton(text="Zerar Contador 🔄")],
        [KeyboardButton(text="Voltar ao Início 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

# 🛠️ Teclado de confirmação de segurança para evitar zerar acidentalmente
teclado_confirmar_zerar = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

# --- NOVOS TECLADOS DE CONFIGURAÇÃO ---
teclado_configuracoes_gerais = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Mensagens de Rotina ⏰"), KeyboardButton(text="SPAM em Grupos 📢")],
        [KeyboardButton(text="Voltar ao Início 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

teclado_opcoes_divulgacao = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Adicionar Alvo ➕"), KeyboardButton(text="Excluir Alvo 🗑️")],
        [KeyboardButton(text="Editar Configurações ⚙️"), KeyboardButton(text="Forçar Disparo Agora 🚀")],
        [KeyboardButton(text="Pausar SPAM ⏸️"), KeyboardButton(text="Voltar às Configs 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

teclado_tipo_edicao = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Global 🌍"), KeyboardButton(text="Por Alvo 🎯")],
        [KeyboardButton(text="Cancelar ❌")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

teclado_opcoes_rotina = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Editar Bom Dia ☀️"), KeyboardButton(text="Editar Incentivo 🔥")],
        [KeyboardButton(text="Editar Convite 🔗"), KeyboardButton(text="Editar Prompt GEM 🤖")],
        [KeyboardButton(text="Editar Boa Noite 🌙"), KeyboardButton(text="Pausar Rotinas ⏸️")],
        [KeyboardButton(text="Voltar às Configs 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

teclado_outros_canais = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Espião Afiliados 🕵️")],
        [KeyboardButton(text="Voltar ao Início 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

# 🛠️ Função do novo Menu Inicial Raiz
def obter_teclado_raiz():
    botoes = [
        [KeyboardButton(text="Canal Principal 📺"), KeyboardButton(text="Outros Canais 🗂️")],
        [KeyboardButton(text="Relatório Geral 📊")]
    ]
    return ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)

# 🛠️ Função centralizadora da pasta do Canal Principal
def obter_teclado_principal():
    botoes = [
        [KeyboardButton(text="Criar Postagem 📝"), KeyboardButton(text="Gerenciar Fila 📋")],
        [KeyboardButton(text="Editar Número da Postagem 🔢"), KeyboardButton(text="Pausar Postagens 🛑")],
        [KeyboardButton(text="Disparar Bom Dia ☀️"), KeyboardButton(text="Disparar Incentivo 🔥")],
        [KeyboardButton(text="Disparar Boa Noite 🌙"), KeyboardButton(text="Disparar Convite 📢")],
        [KeyboardButton(text="Configurações Gerais ⚙️")], 
        [KeyboardButton(text="Voltar ao Início 🔙")]
    ]
    return ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)

# --- SISTEMA DO ESPIÃO (CONFIGURAÇÕES) ---
def ler_alvos_espiao():
    try:
        with open("alvos_espiao.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"alvos": [], "canal_destino": None}

def salvar_alvos_espiao(dados):
    with open("alvos_espiao.json", "w") as f:
        json.dump(dados, f, indent=4)

teclado_menu_espiao = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Grupos Vigiados 📡")],
        [KeyboardButton(text="Voltar aos Canais 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

teclado_opcoes_espiao = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Adicionar Concorrente ➕"), KeyboardButton(text="Remover Concorrente 🗑️")],
        [KeyboardButton(text="Definir Canal de Destino 🎯"), KeyboardButton(text="Voltar ao Menu Espião 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

# --- SISTEMA DE FILA DE POSTAGENS ASSÍNCRONAS ---
def ler_fila_postagens():
    try:
        with open("fila_postagens.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"fila": []}

def salvar_fila_postagens(dados):
    with open("fila_postagens.json", "w") as f:
        json.dump(dados, f, indent=4)

def agendar_fila_postagens():
    if EXIBIR_LOGS: logger.info("🔄 Calculando distribuição orgânica de vídeos da fila...")
    for job in scheduler.get_jobs():
        if job.id.startswith('job_fila_postagem_'):
            job.remove()
            
    dados_pausa = ler_pausa_programada()
    if dados_pausa.get("ativa"):
        if EXIBIR_LOGS: logger.info("🛑 Fila de postagens represada: A pausa programada está ativa.")
        return
        
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    if not fila:
        return
        
    agora = datetime.now(fuso_horario)
    hoje_str = agora.strftime("%Y-%m-%d")
    
    # Só posta vídeos que foram inseridos antes de hoje (agendados pro dia seguinte) ou represados
    from datetime import timedelta
    videos_para_hoje = [item for item in fila if item.get("data_adicao") < hoje_str]
    
    if not videos_para_hoje:
        if EXIBIR_LOGS: logger.info("⏳ Todos os vídeos na fila estão agendados aguardando o dia de amanhã.")
        return
        
    dados_rotina = ler_config_rotina()
    config_bom_dia = dados_rotina.get("bom_dia", {"inicio": 6, "fim": 9})
    config_boa_noite = dados_rotina.get("boa_noite", {"inicio": 21, "fim": 23})
        
    # Padrões baseados na configuração, caso os horários ainda não estejam no agendador
    hora_inicio = config_bom_dia.get("inicio", 6)
    min_inicio = 0
    hora_fim = config_boa_noite.get("inicio", 21)
    min_fim = 0
    
    if EXIBIR_LOGS: logger.info("🚀 A iniciar o processamento do radar de ocupação de horários da fila...")
    
    # Extrai a hora exata do "Bom Dia" e "Boa Noite" já sorteados para HOJE, e constrói o radar
    horarios_ocupados = []
    for job in scheduler.get_jobs():
        proxima_execucao = getattr(job, 'next_run_time', None)
        
        if proxima_execucao and not job.id.startswith('job_fila_postagem_'):
            horarios_ocupados.append(proxima_execucao.astimezone(fuso_horario))
            if EXIBIR_LOGS: logger.info(f"🔎 Radar validou com segurança o horário do job '{job.id}'.")
            
        if job.id.startswith('job_rotina_bom_dia_') and proxima_execucao:
            hora_inicio = proxima_execucao.astimezone(fuso_horario).hour
            min_inicio = proxima_execucao.astimezone(fuso_horario).minute
        elif job.id.startswith('job_rotina_boa_noite_') and proxima_execucao:
            hora_fim = proxima_execucao.astimezone(fuso_horario).hour
            min_fim = proxima_execucao.astimezone(fuso_horario).minute
            
    limite_inicio_hoje = agora.replace(hour=hora_inicio, minute=min_inicio, second=0, microsecond=0) + timedelta(minutes=5)
    limite_fim_hoje = agora.replace(hour=hora_fim, minute=min_fim, second=0, microsecond=0) - timedelta(minutes=5)
    
    if agora >= limite_fim_hoje:
        if EXIBIR_LOGS: logger.warning("⚠️ Janela de postagem de hoje já encerrou. Fila aguardará até amanhã.")
        return
        
    inicio_real = max(agora + timedelta(minutes=5), limite_inicio_hoje)
    minutos_disponiveis = int((limite_fim_hoje - inicio_real).total_seconds() / 60)
    
    if minutos_disponiveis < 5:
        if EXIBIR_LOGS: logger.warning("⚠️ Tempo insuficiente para espaçar os vídeos hoje.")
        return
        
    qtd_videos = len(videos_para_hoje)
    espacamento_medio = minutos_disponiveis // qtd_videos
    minuto_atual_busca = inicio_real
    INTERVALO_MINIMO = 15 # Distância de segurança (minutos) entre o vídeo e qualquer outra mensagem
    
    for index, item in enumerate(videos_para_hoje):
        limite_sorteio = minuto_atual_busca + timedelta(minutes=espacamento_medio - 1)
        if limite_sorteio < minuto_atual_busca: limite_sorteio = minuto_atual_busca
        
        max_minutos_offset = int((limite_sorteio - minuto_atual_busca).total_seconds() / 60)
        sucesso = False
        horario_disparo = None
        
        for tentativa in range(100):
            minutos_offset = random.randint(0, max_minutos_offset)
            horario_candidato = minuto_atual_busca + timedelta(minutes=minutos_offset, seconds=random.randint(0, 59))
            
            if horario_candidato > limite_fim_hoje:
                horario_candidato = limite_fim_hoje
                
            colisao = False
            for ocupado in horarios_ocupados:
                if abs((horario_candidato - ocupado).total_seconds() / 60) < INTERVALO_MINIMO:
                    colisao = True
                    break
                    
            if not colisao:
                horario_disparo = horario_candidato
                sucesso = True
                break
                
        if not sucesso:
            if EXIBIR_LOGS: logger.warning(f"⚠️ Vídeo {index+1}: Sem lacuna limpa. Forçando encaixe de segurança.")
            meio_offset = max_minutos_offset // 2
            horario_disparo = minuto_atual_busca + timedelta(minutes=meio_offset)
            if horario_disparo > limite_fim_hoje: horario_disparo = limite_fim_hoje

        # Alimenta o radar para que os próximos vídeos se afastem deste
        horarios_ocupados.append(horario_disparo)
        
        job_id = f"job_fila_postagem_{item['id']}"
        scheduler.add_job(executar_postagem_fila, 'date', run_date=horario_disparo, args=[item['id']], id=job_id, replace_existing=True)
        if EXIBIR_LOGS: logger.info(f"✅ Fila de Amanhã/Retorno: Vídeo {index+1}/{qtd_videos} distribuído organicamente para as {horario_disparo.strftime('%H:%M:%S')}")
        
        minuto_atual_busca += timedelta(minutes=espacamento_medio)

async def executar_postagem_fila(item_id):
    if EXIBIR_LOGS: logger.info(f"📤 Disparando postagem assíncrona programada...")
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    item = next((x for x in fila if x["id"] == item_id), None)
    if not item:
        return
        
    caminho_video = item.get("caminho_video")
    video_id = item.get("video_id")
    legenda = item.get("legenda")
    
    try:
        if caminho_video and os.path.exists(caminho_video):
            arquivo = FSInputFile(caminho_video)
            msg = await bot.send_video(chat_id=GRUPO_ID, video=arquivo, caption=legenda, parse_mode="HTML")
            
            # Atualiza todos os itens que usam esse mesmo arquivo de Nível 4 com o novo ID para evitar uploads duplicados
            novo_file_id = msg.video.file_id
            for x in fila:
                if x.get("caminho_video") == caminho_video and x["id"] != item_id:
                    x["video_id"] = novo_file_id
                    x["caminho_video"] = None
        elif video_id:
            await bot.send_video(chat_id=GRUPO_ID, video=video_id, caption=legenda, parse_mode="HTML")
        else:
            if EXIBIR_LOGS: logger.error(f"❌ Falha: Vídeo expirou ou foi perdido fisicamente da máquina.")
            
        if EXIBIR_LOGS: logger.info("✅ Postagem distribuída com sucesso!")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha ao postar vídeo da fila: {e}")
    finally:
        # Exclui o item da fila após tentativa
        fila = [x for x in fila if x["id"] != item_id]
        fila_data["fila"] = fila
        salvar_fila_postagens(fila_data)
        
        # Faxina responsável: só exclui o vídeo físico se nenhum outro item da fila precisar dele
        if caminho_video and os.path.exists(caminho_video):
            ainda_usado = any(x.get("caminho_video") == caminho_video for x in fila)
            if not ainda_usado:
                os.remove(caminho_video)
                if EXIBIR_LOGS: logger.info("🧹 Faxina: Arquivo fonte excluído permanentemente após esvaziar da fila.")

# --- SISTEMA DE PAUSA PROGRAMADA ---
def ler_pausa_programada():
    try:
        with open("pausa_programada.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"ativa": False, "data_retorno": None, "servicos_pausados": []}

def salvar_pausa_programada(dados):
    with open("pausa_programada.json", "w") as f:
        json.dump(dados, f, indent=4)

async def verificar_pausa_diaria():
    if EXIBIR_LOGS: logger.info("⏰ Iniciando verificação diária de pausa programada (envio de aviso)...")
    dados_pausa = ler_pausa_programada()
    if not dados_pausa.get("ativa"):
        return
        
    data_retorno_str = dados_pausa.get("data_retorno")
    if not data_retorno_str:
        return
        
    if EXIBIR_LOGS: logger.info("🛑 Pausa ativa. Enviando aviso diário ao grupo...")
    
    id_aviso_imediato = dados_pausa.pop("id_aviso_imediato", None)
    if id_aviso_imediato:
        if EXIBIR_LOGS: logger.info("🧹 Excluindo aviso de ativação imediata para dar lugar ao aviso diário...")
        await apagar_mensagem_automatica(id_aviso_imediato)
        salvar_pausa_programada(dados_pausa)

    motivo_salvo = dados_pausa.get("motivo", "organização interna e curadoria de novos conteúdos")

    # Extrai apenas o dia e o mês (DD/MM) da string original
    data_curta = data_retorno_str.split(" ")[0][:5]

    prompt = (
        f"Você é um assistente de afiliados. Crie um aviso MUITO CURTO E DIRETO informando "
        f"que as postagens continuam pausadas para {motivo_salvo}. "
        f"Avise que retornaremos no dia {data_curta}. "
        f"REGRA ABSOLUTA: Use no máximo 2 a 3 linhas e não ultrapasse 150 caracteres. "
        f"Seja direto, não peça desculpas e evite longas explicações. "
        f"Use emojis e entregue APENAS o texto da mensagem final."
    )
    texto = await gerar_mensagem_gemini(prompt)
    msg_enviada = await bot.send_message(GRUPO_ID, texto)
    registrar_lixeira(msg_enviada.message_id)
    if EXIBIR_LOGS: logger.info("✅ Aviso diário enviado com sucesso.")

async def verificar_retorno_pausa_minuto():
    dados_pausa = ler_pausa_programada()
    if not dados_pausa.get("ativa"):
        return
        
    from datetime import datetime
    hoje = datetime.now(fuso_horario)
    data_retorno_str = dados_pausa.get("data_retorno")
    
    if not data_retorno_str:
        return
        
    try:
        data_retorno = datetime.strptime(data_retorno_str, "%d/%m/%Y %H:%M").replace(tzinfo=fuso_horario)
    except ValueError:
        # Fallback de segurança caso haja uma data configurada previamente no formato antigo
        try:
            data_retorno = datetime.strptime(data_retorno_str, "%d/%m/%Y").date()
            hoje = hoje.date()
        except ValueError:
            return
    
    if hoje >= data_retorno:
        if EXIBIR_LOGS: logger.info("⏰ Data e hora de retorno atingidas! Reativando serviços pausados...")
        servicos = dados_pausa.get("servicos_pausados", [])
        
        if "spam" in servicos:
            dados_div = ler_alvos_divulgacao()
            dados_div["pausado"] = False
            salvar_alvos_divulgacao(dados_div)
            if EXIBIR_LOGS: logger.info("✅ SPAM reativado.")
        if "rotina" in servicos:
            dados_rotina = ler_config_rotina()
            dados_rotina["pausado"] = False
            salvar_config_rotina(dados_rotina)
            if EXIBIR_LOGS: logger.info("✅ Mensagens de rotina reativadas.")
        
        dados_pausa["ativa"] = False
        dados_pausa["servicos_pausados"] = []
        dados_pausa.pop("id_aviso_imediato", None)
        salvar_pausa_programada(dados_pausa)
        agendar_fila_postagens()
        if EXIBIR_LOGS: logger.info("✅ Serviços reativados e pausa programada encerrada com sucesso.")
# ----------------------------------

# 4. FUNÇÕES DE GERAÇÃO COM IA E AGENDAMENTO ⏰
async def gerar_mensagem_gemini(prompt):

    if EXIBIR_LOGS: logger.info("🧠 Iniciando processamento em cascata com a nova SDK...")

    for modelo_nome in MODELOS_CASCATA_GEMINI:
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

# --- SISTEMA DE LIXEIRA PERSISTENTE ---
def ler_lixeira():
    try:
        with open("lixeira_mensagens.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"mensagens": []}

def salvar_lixeira(dados):
    with open("lixeira_mensagens.json", "w") as f:
        json.dump(dados, f, indent=4)

# ✅ Função de limpeza extra para o arquivo de histórico
def limpar_historico_antigo():
    if os.path.exists("historico_mensagens.json"):
        os.remove("historico_mensagens.json")
        if EXIBIR_LOGS: logger.info("🧹 Histórico de mensagens do userbot reiniciado.")

def registrar_lixeira(msg_id):
    dados = ler_lixeira()
    # ✅ Agora salvamos apenas o ID da mensagem, sem calcular tempo de expiração
    dados["mensagens"].append({"id": msg_id})
    salvar_lixeira(dados)
    if EXIBIR_LOGS: logger.info(f"💾 ID {msg_id} salvo na lixeira persistente para exclusão na próxima madrugada (03h00).")

async def varredor_de_lixeira():
    if EXIBIR_LOGS: logger.info("🧹 Iniciando varredura diária da lixeira persistente (03h00)...")
    dados = ler_lixeira()
    mensagens = dados.get("mensagens", [])
    
    for msg in mensagens:
        try:
            # Compatibilidade mantida caso existam mensagens salvas no formato antigo
            msg_id = msg["id"] if isinstance(msg, dict) else msg
            await apagar_mensagem_automatica(msg_id)
        except Exception as e:
            if EXIBIR_LOGS: logger.warning(f"⚠️ Erro ao processar item da lixeira: {e}")
            
    # Esvazia a lixeira completamente de uma só vez após o loop de limpeza
    dados["mensagens"] = []
    salvar_lixeira(dados)
    if EXIBIR_LOGS: logger.info("✅ Lixeira persistente esvaziada com sucesso.")

async def apagar_mensagem_automatica(msg_id):
    try:
        await bot.delete_message(chat_id=GRUPO_ID, message_id=msg_id)
        if EXIBIR_LOGS: logger.info(f"🧹 Faxina concluída: Mensagem automática {msg_id} apagada da lixeira.")
    except Exception as e:
        if EXIBIR_LOGS: logger.info(f"⚠️ Faxina: A mensagem {msg_id} já havia sido apagada manualmente ou não foi encontrada.")

async def disparar_mensagem(tipo, forcar=False):
    if EXIBIR_LOGS: logger.info(f"🔍 Validando status antes de disparar a rotina '{tipo}' (Forçar: {forcar})...")
    
    # ✅ NOVO: Trava lógica que substitui o bloqueio global do scheduler
    dados_rotina = ler_config_rotina()
    if dados_rotina.get("pausado", False) and not forcar:
        if EXIBIR_LOGS: logger.info(f"🛑 Disparo abortado ({tipo}): As rotinas estão pausadas no sistema.")
        return

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
        partes = tipo.split("_")
        dias_restantes = int(partes[1])
        data_dupla = partes[2] if len(partes) > 2 else ""
        
        if EXIBIR_LOGS: logger.info(f"📅 Extração concluída: Data dupla {data_dupla} (Faltam {dias_restantes} dias).")

        if dias_restantes == 0:
            aviso = f"É HOJE o evento de data dupla {data_dupla}! Disparem seus links nas redes!"
        elif dias_restantes == 1:
            aviso = f"É AMANHÃ o evento de data dupla {data_dupla}! Preparem todos os materiais!"
        else:
            aviso = f"Faltam {dias_restantes} dias para o evento de data dupla {data_dupla}. Antecipem a organização!"
        
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
    
    registrar_lixeira(msg_enviada.message_id)
    
    # ✅ Disparo condicional: Envia o link separado apenas na divulgação e no GEM
    if tipo == "link_grupo":
        link_separado = f"👇 <b>Link de Convite:</b>\n{LINK_GRUPO}"
        if EXIBIR_LOGS: logger.info("🔗 Enviando link do grupo em mensagem isolada.")
        msg_link = await bot.send_message(GRUPO_ID, link_separado, parse_mode="HTML")
        registrar_lixeira(msg_link.message_id)
    elif tipo == "divulgar_gem":
        link_gem = "👇 <b>Acesse o Prompt Automatizado:</b>\nhttps://gemini.google.com/gem/1HtJMuknyMZ76utOu-i6c_xvc3vmQx7bT?usp=sharing"
        if EXIBIR_LOGS: logger.info("🤖 Enviando link do GEM em mensagem isolada.")
        msg_gem = await bot.send_message(GRUPO_ID, link_gem, parse_mode="HTML")
        registrar_lixeira(msg_gem.message_id)

def ler_config_rotina():
    if EXIBIR_LOGS: logger.info("📂 Lendo configurações de rotina...")
    try:
        with open("config_rotina.json", "r") as f:
            dados = json.load(f)
            # Adiciona chaves padrão se não existirem (retrocompatibilidade)
            if "link_grupo" not in dados:
                dados["link_grupo"] = {"inicio": 9, "fim": 21, "frequencia": 3}
            if "divulgar_gem" not in dados:
                dados["divulgar_gem"] = {"inicio": 8, "fim": 22, "frequencia": 1}
            # ✅ Nova chave para gerenciar o status de pausa via JSON
            if "pausado" not in dados:
                dados["pausado"] = False
            return dados
    except (FileNotFoundError, json.JSONDecodeError):
        # Configuração padrão de segurança se o arquivo não existir
        if EXIBIR_LOGS: logger.warning("⚠️ Arquivo config_rotina.json não encontrado. Criando padrão inicial.")
        return {
            "bom_dia": {"inicio": 6, "fim": 9, "frequencia": 1},
            "incentivo": {"inicio": 10, "fim": 20, "frequencia": 2},
            "boa_noite": {"inicio": 21, "fim": 23, "frequencia": 1},
            "link_grupo": {"inicio": 9, "fim": 21, "frequencia": 3},
            "divulgar_gem": {"inicio": 8, "fim": 22, "frequencia": 1},
            "pausado": False
        }

def salvar_config_rotina(dados):
    with open("config_rotina.json", "w") as f:
        json.dump(dados, f, indent=4)

def agendar_tarefas_diarias():
    if EXIBIR_LOGS: logger.info("🔄 Sorteando horários de rotina com inteligência anti-spam...")
    
    # Limpa os jobs antigos de rotina e de campanhas para evitar duplicatas ao forçar re-sorteio
    for job in scheduler.get_jobs():
        if job.id.startswith('job_rotina_') or job.id.startswith('job_campanha_'):
            job.remove()
            if EXIBIR_LOGS: logger.info(f"🧹 Registro de agendamento antigo apagado da memória: {job.id}")

    dados_rotina = ler_config_rotina()
    horarios_ocupados = [] 
    INTERVALO_MINIMO = 30 # Distância mínima em minutos entre qualquer mensagem
    
    # Executa o sorteio dinâmico e inteligente
    for tipo, config in dados_rotina.items():
        if tipo == "pausado":
            if EXIBIR_LOGS: logger.info("⏭️ Pulando a chave de controle do sistema ('pausado')...")
            continue
            
        freq = config.get("frequencia", 1)
        inicio = config.get("inicio", 6)
        fim = config.get("fim", 22)
        
        limite_superior = fim - 1 if fim > inicio else fim
        if EXIBIR_LOGS: logger.info(f"🧮 Configurando {tipo}: {freq}x entre {inicio}h e {limite_superior}h59.")
        
        # Calcula o espaçamento ideal para distribuir mensagens do mesmo tipo
        minutos_disponiveis = (limite_superior * 60 + 59) - (inicio * 60)
        espacamento_ideal = minutos_disponiveis // freq if freq > 1 else 0
        
        for i in range(freq):
            sucesso = False
            
            # Subdivide a janela total em sub-blocos para cada disparo
            min_inicio_busca = (inicio * 60) + (i * espacamento_ideal)
            if freq > 1:
                min_fim_busca = min((inicio * 60) + ((i + 1) * espacamento_ideal), (limite_superior * 60 + 59))
            else:
                min_fim_busca = (limite_superior * 60 + 59)
                
            for tentativa in range(100):
                minuto_absoluto = random.randint(min_inicio_busca, min_fim_busca)
                
                # Validação global rigorosa contra sobreposição (30 minutos)
                colisao = False
                for ocupado in horarios_ocupados:
                    if abs(minuto_absoluto - ocupado) < INTERVALO_MINIMO:
                        colisao = True
                        break
                
                if not colisao:
                    horarios_ocupados.append(minuto_absoluto)
                    hora_sorteada = minuto_absoluto // 60
                    min_sorteado = minuto_absoluto % 60
                    
                    job_id = f"job_rotina_{tipo}_{i}"
                    scheduler.add_job(disparar_mensagem, 'cron', hour=hora_sorteada, minute=min_sorteado, timezone=FUSO_STR, args=[tipo], id=job_id, replace_existing=True)
                    if EXIBIR_LOGS: logger.info(f"✅ {tipo.upper()} [{i+1}/{freq}]: Agendado para {hora_sorteada:02d}:{min_sorteado:02d} (Tentativas: {tentativa+1})")
                    sucesso = True
                    break
                    
            if not sucesso:
                # O motor aplica o fallback restrito caso a janela esteja muito congestionada
                if EXIBIR_LOGS: logger.warning(f"⚠️ {tipo.upper()} [{i+1}/{freq}]: Limite de tentativas excedido. Aplicando fallback forçado na lacuna.")
                minuto_absoluto_fallback = random.randint(min_inicio_busca, min_fim_busca)
                hora_sorteada = minuto_absoluto_fallback // 60
                min_sorteado = minuto_absoluto_fallback % 60
                
                job_id = f"job_rotina_{tipo}_{i}"
                scheduler.add_job(disparar_mensagem, 'cron', hour=hora_sorteada, minute=min_sorteado, timezone=FUSO_STR, args=[tipo], id=job_id, replace_existing=True)
                if EXIBIR_LOGS: logger.info(f"📅 {tipo.upper()} [{i+1}/{freq}]: Agendamento fallback para {hora_sorteada:02d}:{min_sorteado:02d}")

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
            
            tipo_alerta = f"campanha_{i}_{data_futura.day:02d}.{data_futura.month:02d}"
            
            if EXIBIR_LOGS: logger.info(f"🏷️ Tag de alerta formatada com sucesso: {tipo_alerta}")
            
            scheduler.add_job(disparar_mensagem, 'cron', hour=hora_c_manha, minute=min_c_manha, timezone=FUSO_STR, args=[tipo_alerta], id='job_campanha_manha', replace_existing=True)
            scheduler.add_job(disparar_mensagem, 'cron', hour=hora_c_tarde, minute=min_c_tarde, timezone=FUSO_STR, args=[tipo_alerta], id='job_campanha_tarde', replace_existing=True)
            scheduler.add_job(disparar_mensagem, 'cron', hour=hora_c_noite, minute=min_c_noite, timezone=FUSO_STR, args=[tipo_alerta], id='job_campanha_noite', replace_existing=True)
            
            if EXIBIR_LOGS:
                logger.info(f"⏳ Alerta Campanha Manhã: {hora_c_manha:02d}:{min_c_manha:02d}")
                logger.info(f"⏳ Alerta Campanha Tarde: {hora_c_tarde:02d}:{min_c_tarde:02d}")
                logger.info(f"⏳ Alerta Campanha Noite: {hora_c_noite:02d}:{min_c_noite:02d}")
            break

    # Agora sim, com as rotinas já sorteadas, chamamos a fila de postagens para se basear nelas
    agendar_fila_postagens()

# 5. HANDLERS DE COMANDO E INTERAÇÃO
@dp.message(Command("start"))
async def comando_start(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("⌨️ Iniciando o bot no Menu Raiz.")
    await message.answer("🏠 Painel de Controle Inicial. Escolha uma área para gerenciar:", reply_markup=obter_teclado_raiz())

@dp.message(F.text == "Canal Principal 📺")
async def menu_canal_principal(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("📂 Acessando a pasta do Canal Principal.")
    await message.answer("📺 <b>Menu do Canal Principal</b>\nGerencie as postagens e rotinas abaixo:", reply_markup=obter_teclado_principal(), parse_mode="HTML")

async def buscar_dados_financeiros_shopee(dias_retroativos=30):
    if not SHOPEE_APP_ID or not SHOPEE_APP_SECRET:
        return None
        
    from datetime import timedelta
    agora = datetime.now(fuso_horario)
    inicio = agora - timedelta(days=dias_retroativos)
    
    start_ts = int(inicio.replace(hour=0, minute=0, second=0).timestamp())
    end_ts = int(agora.replace(hour=23, minute=59, second=59).timestamp())
    
    endpoint = "https://open-api.affiliate.shopee.com.br/graphql"
    
    payload = {
        "query": """query getConversionReport($purchaseTimeStart: Int!, $purchaseTimeEnd: Int!, $limit: Int!) {
            conversionReport(purchaseTimeStart: $purchaseTimeStart, purchaseTimeEnd: $purchaseTimeEnd, limit: $limit) {
                nodes {
                    purchaseTime
                    shopeeCommissionCapped
                    sellerCommission
                    totalCommission
                    orders {
                        orderStatus
                    }
                }
            }
        }""",
        "variables": {
            "purchaseTimeStart": start_ts,
            "purchaseTimeEnd": end_ts,
            "limit": 500
        }
    }
    
    payload_json = json.dumps(payload, separators=(',', ':'))
    timestamp = int(time.time())
    fator_base = f"{SHOPEE_APP_ID}{timestamp}{payload_json}{SHOPEE_APP_SECRET}"
    assinatura = hashlib.sha256(fator_base.encode('utf-8')).hexdigest()
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={SHOPEE_APP_ID}, Timestamp={timestamp}, Signature={assinatura}"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, data=payload_json) as response:
                
                # ✅ NOVA AUDITORIA: Captura a resposta exata enviada pela Shopee em formato de texto
                dados_crus = await response.text()
                if EXIBIR_LOGS: logger.info(f"🔍 [API Shopee - Relatório] Resposta crua do servidor: {dados_crus}")
                
                if response.status == 200:
                    dados = json.loads(dados_crus)
                    return dados.get("data", {}).get("conversionReport", {}).get("nodes", [])
                else:
                    if EXIBIR_LOGS: logger.error(f"❌ Erro HTTP {response.status}: {dados_crus}")
                    
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro na consulta financeira à API Shopee: {e}")
    return []

@dp.message(F.text == "Relatório Geral 📊")
async def gerar_relatorio_completo(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    msg_status = await message.answer("📊 Extraindo métricas do servidor e sincronizando API Financeira... Aguarde ⏳")
    if EXIBIR_LOGS: logger.info("🚀 Iniciando auditoria completa do sistema e finanças...")
    
    # 1. Auditoria de Saúde do Sistema
    numero_atual = ler_contador()
    fila_princ = len(ler_fila_postagens().get("fila", []))
    fila_espiao = len(ler_fila_clonagem().get("fila", []))
    radar = len(ler_alvos_espiao().get("alvos", []))
    
    dados_pausa = ler_pausa_programada()
    dados_div = ler_alvos_divulgacao()
    dados_rotina = ler_config_rotina()
    
    if dados_pausa.get("ativa"):
        status_sis = f"🔴 PAUSADO até {dados_pausa.get('data_retorno')}"
    else:
        spam_ok = not dados_div.get("pausado", False)
        rotina_ok = not dados_rotina.get("pausado", False)
        if spam_ok and rotina_ok:
            status_sis = "🟢 ATIVO (Rotina e SPAM rodando)"
        elif spam_ok or rotina_ok:
            status_sis = "🟡 PARCIAL (Algum serviço pausado)"
        else:
            status_sis = "🔴 PARADO (Serviços suspensos manualmente)"
            
    # 2. Extração Financeira
    from datetime import timedelta
    conversoes = await buscar_dados_financeiros_shopee(30)
    
    total_pedidos = len(conversoes) if conversoes else 0
    pagos, pendentes, cancelados = 0, 0, 0
    comissao_shopee, comissao_extra, faturamento_total = 0.0, 0.0, 0.0
    
    hoje = datetime.now(fuso_horario)
    diario = { (hoje - timedelta(days=i)).strftime("%d/%m"): 0.0 for i in range(7) }
    
    if conversoes:
        for conv in conversoes:
            orders = conv.get("orders", [])
            status = orders[0].get("orderStatus", "") if orders else ""
            
            if status == "COMPLETED": pagos += 1
            elif status == "CANCELLED": cancelados += 1
            else: pendentes += 1
            
            c_shopee = float(conv.get("shopeeCommissionCapped", "0"))
            c_extra = float(conv.get("sellerCommission", "0"))
            c_total = float(conv.get("totalCommission", "0"))
            
            comissao_shopee += c_shopee
            comissao_extra += c_extra
            faturamento_total += c_total
            
            dt_compra = datetime.fromtimestamp(conv.get("purchaseTime", 0), tz=fuso_horario).strftime("%d/%m")
            if dt_compra in diario:
                diario[dt_compra] += c_total
                
    # Função para converter formato de moeda para o padrão brasileiro
    def f_br(valor): return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    texto = (
        "📊 <b>RELATÓRIO GERAL DA OPERAÇÃO</b>\n\n"
        "⚙️ <b>SAÚDE DO SISTEMA</b>\n"
        f"• Próximo Vídeo: <b>{numero_atual}</b>\n"
        f"• Fila Principal: <b>{fila_princ} agendados</b>\n"
        f"• Fila do Espião: <b>{fila_espiao} aguardando</b>\n"
        f"• Radar Espião: <b>{radar} vigiados</b>\n"
        f"• Status: <b>{status_sis}</b>\n\n"
        "💰 <b>BALANÇO FINANCEIRO (Últimos 30 Dias)</b>\n"
        f"• Total de Pedidos: <b>{total_pedidos}</b>\n"
        f"• Conversão: {pagos} Pagos | {pendentes} Pendentes | {cancelados} Cancelados\n"
        f"• Comissão Shopee: R$ {f_br(comissao_shopee)}\n"
        f"• Comissão Extra (AMS): R$ {f_br(comissao_extra)}\n"
        f"• Faturamento Bruto: <b>R$ {f_br(faturamento_total)}</b>\n\n"
        "📈 <b>DESEMPENHO DIÁRIO (Últimos 7 Dias)</b>\n"
    )
    
    for i in range(7):
        dt_chave = (hoje - timedelta(days=i)).strftime("%d/%m")
        valor = diario.get(dt_chave, 0.0)
        marc = " (Hoje)" if i == 0 else ""
        texto += f"• {dt_chave}{marc}: R$ {f_br(valor)}\n"
        
    await msg_status.delete()
    await message.answer(texto, parse_mode="HTML")
    if EXIBIR_LOGS: logger.info("✅ Relatório gerado e exibido com sucesso!")

# ✅ Handlers para Envio Manual de Mensagens via Botões
@dp.message(F.text == "Disparar Bom Dia ☀️")
async def manual_bom_dia(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Gerando e enviando mensagem de Bom Dia... ⏳")
    if EXIBIR_LOGS: logger.info("🚀 Comando de disparo manual autorizado para Bom Dia.")
    await disparar_mensagem("bom_dia", forcar=True)
    await message.answer("Mensagem de Bom Dia enviada ao grupo com sucesso! ✅")

@dp.message(F.text == "Disparar Boa Noite 🌙")
async def manual_boa_noite(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Gerando e enviando mensagem de Boa Noite... ⏳")
    if EXIBIR_LOGS: logger.info("🚀 Comando de disparo manual autorizado para Boa Noite.")
    await disparar_mensagem("boa_noite", forcar=True)
    await message.answer("Mensagem de Boa Noite enviada ao grupo com sucesso! ✅")

@dp.message(F.text == "Disparar Incentivo 🔥")
async def manual_incentivo(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Gerando e enviando mensagem de Incentivo... ⏳")
    if EXIBIR_LOGS: logger.info("🚀 Comando de disparo manual autorizado para Incentivo.")
    await disparar_mensagem("incentivo", forcar=True)
    await message.answer("Mensagem de Incentivo enviada ao grupo com sucesso! ✅")

@dp.message(F.text == "Disparar Convite 📢")
async def manual_link_grupo(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Gerando e enviando divulgação do grupo... ⏳")
    if EXIBIR_LOGS: logger.info("🚀 Comando de disparo manual autorizado para Convite do Grupo.")
    await disparar_mensagem("link_grupo", forcar=True)
    await message.answer("Mensagem de divulgação enviada ao grupo com sucesso! ✅")

# ❌ NOVO: Handler Global para Cancelar via Botão (Agora 100% à prova de falhas)
@dp.message(F.text == "Cancelar ❌", StateFilter("*"))
async def cancelar_fluxo_global(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("❌ Ação cancelada ou resetada via botão.")

    if EXIBIR_LOGS: logger.info("🔍 Verificando pendências de numeração na memória antes de limpar...")
    data = await state.get_data()
    numero_reservado = data.get('numero_reservado')

    if numero_reservado:
        if EXIBIR_LOGS: logger.info(f"⏪ Revertendo numeração: devolvendo o número {numero_reservado} ao contador...")
        async with _lock_contador:
            salvar_contador(numero_reservado)
        if EXIBIR_LOGS: logger.info(f"✅ Sucesso! O contador foi restaurado para {numero_reservado}.")

    # 🧹 Limpeza de arquivos de vídeo que ficaram órfãos
    caminho_video = data.get('video_path')
    if caminho_video and os.path.exists(caminho_video):
        os.remove(caminho_video)
        if EXIBIR_LOGS: logger.info("🧹 Vídeo temporário excluído do servidor devido ao cancelamento.")

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
        # ✨ Proteção contra concorrência: Reserva o número instantaneamente
        async with _lock_contador:
            numero_atual = ler_contador()
            salvar_contador(numero_atual + 1)
            if EXIBIR_LOGS: logger.info(f"🔒 Concorrência blindada: Número {numero_atual} reservado. Próximo será {numero_atual + 1}.")

        # 1. Download do vídeo para o servidor Ubuntu
        file_info = await bot.get_file(file_id)
        video_path = f"temp_{file_id}.mp4"
        await bot.download_file(file_info.file_path, destination=video_path)

        # 2. Upload para a API do Gemini processar a Copy
        def analisar_video():
            import time
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
            
            # ✅ O número utilizado já foi travado e reservado acima
            
            # ✅ Prompt ajustado para remover a repetição do nome no título
            
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
        if EXIBIR_LOGS: logger.info("💾 Mantendo o vídeo no servidor para re-upload posterior com data atualizada.")
        
        # ✅ Salva o texto da IA e o caminho do vídeo físico na memória
        await state.update_data(video_path=video_path, video_id=file_id, nome_produto=chamada_gerada, links=[], numero_reservado=numero_atual)
        await msg_status.delete()
        
        # ✅ Junta o texto da IA com uma pergunta orientativa apenas para exibição ao administrador
        mensagem_aprovacao = f"{chamada_gerada}\n\n👉 <b>Esta identificação está correta?</b> Escolha uma opção abaixo:"
        
        await message.answer(mensagem_aprovacao, reply_markup=teclado_confirmacao, parse_mode="HTML")
        await state.set_state(PostagemFluxo.aguardando_confirmacao_nome)

    except Exception as e:
        erro_str = str(e)
        if EXIBIR_LOGS: logger.error(f"❌ Erro na IA ou Download: {erro_str}")
        if EXIBIR_LOGS: logger.info("💾 Mantendo o vídeo original no servidor apesar do erro na IA.")
        await msg_status.delete()
        
        # ✅ Analisa o erro e traduz para o utilizador
        motivo = "Falha no servidor."
        if "file is too big" in erro_str.lower():
            motivo = "O vídeo ultrapassa o limite de 20MB do Telegram para Bots."
        elif "429" in erro_str:
            motivo = "Limite de velocidade da IA atingido. Aguarde 1 minuto."
        else:
            motivo = erro_str[:150] 
            
        await message.answer(f"⚠️ A IA não conseguiu processar este vídeo.\n**Motivo:** {motivo}\n\nDigite manualmente APENAS O NOME DO PRODUTO ou clique em Cancelar:", reply_markup=teclado_cancelar)
        
        # ✅ Em caso de erro, preservamos o arquivo físico e o número já reservado
        video_path_recuperacao = f"temp_{file_id}.mp4"
        await state.update_data(video_path=video_path_recuperacao, video_id=file_id, links=[], numero_reservado=numero_atual)
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
    data = await state.get_data()
    numero_atual = data.get('numero_reservado')
    
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
    video_id_fallback = data.get('video_id')
    caminho_video_original = data.get('video_path')
    plataforma = data['plataforma_escolhida']
    link_vid_shopee = data.get('link_video_shopee', "")
    link_vid_tiktok = data.get('link_video_tiktok', "")
    links_shopee = data.get('links_shopee', [])
    links_tiktok = data.get('links_tiktok', [])
    
    if EXIBIR_LOGS: logger.info("📤 Iniciando montagem inteligente da legenda (3 níveis).")
    # ✅ A leitura e o incremento do contador foram movidos para a primeira etapa do fluxo
    
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

    # ✅ Renova a data do arquivo sem recompressão
    caminho_processado = None
    if caminho_video_original and os.path.exists(caminho_video_original):
        subprocess.run(["touch", caminho_video_original])
        if EXIBIR_LOGS: logger.info("📅 Data do arquivo renovada sem recompressão.")

    hoje_str = datetime.now(fuso_horario).strftime("%Y-%m-%d")
    
    def adicionar_a_fila(caminho_vid, vid_id, caption):
        fila_data = ler_fila_postagens()
        item = {
            "id": f"{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}",
            "caminho_video": caminho_vid,
            "video_id": vid_id,
            "legenda": caption,
            "data_adicao": hoje_str
        }
        fila_data.setdefault("fila", []).append(item)
        salvar_fila_postagens(fila_data)

    caminho_final = caminho_processado if caminho_processado and os.path.exists(caminho_processado) else caminho_video_original
    
    if caminho_processado and caminho_video_original and os.path.exists(caminho_video_original):
        os.remove(caminho_video_original)

    if nivel_4_ativado:
        legenda_shopee = montar_legenda(texto_longo, is_rodape=False, plataforma_alvo="Apenas Shopee 🛒")
        if EXIBIR_LOGS: logger.info("📦 Agendando vídeo 1/2 (Shopee) na fila invisível para amanhã.")
        adicionar_a_fila(caminho_final, None, legenda_shopee)
        
        legenda_tiktok = montar_legenda(texto_longo, is_rodape=False, plataforma_alvo="Apenas TikTok 🎵")
        if EXIBIR_LOGS: logger.info("📦 Agendando vídeo 2/2 (TikTok) na fila invisível para amanhã.")
        adicionar_a_fila(caminho_final, None, legenda_tiktok)
    else:
        if EXIBIR_LOGS: logger.info("📦 Agendando vídeo consolidado na fila invisível para amanhã.")
        adicionar_a_fila(caminho_final, video_id_fallback if not caminho_final else None, legenda_final)
        
    if EXIBIR_LOGS: logger.info("💾 Arquivo físico adormecido. A limpeza ocorrerá automaticamente após o upload escalonado amanhã.")
    
    async with _lock_contador:
        proximo_numero = ler_contador()
        
    agendar_fila_postagens()
    
    await message.answer(f"Postagem processada e agendada para amanhã! 📅✅\nO sistema distribuirá os vídeos de forma invisível ao longo do dia. O próximo vídeo assumirá o número {proximo_numero}.", reply_markup=obter_teclado_principal())
    await state.clear()

# ✅ Handlers para Gerenciar a Numeração
@dp.message(F.text == "Editar Número da Postagem 🔢")
async def menu_editar_numero(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    numero_atual = ler_contador()
    await message.answer(f"O próximo vídeo será o <b>{numero_atual}</b>.\nEscolha uma ação abaixo:", reply_markup=teclado_opcoes_numero, parse_mode="HTML")

@dp.message(F.text == "Zerar Contador 🔄")
async def confirmar_zerar_numero(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    numero_atual = ler_contador()
    if EXIBIR_LOGS: logger.info("⚠️ Solicitando confirmação de segurança para zerar contador.")
    texto_confirmacao = (
        f"⚠️ <b>Atenção!</b>\n\n"
        f"O vídeo atual está no número <b>{numero_atual}</b> e iremos zerar para o vídeo número <b>1</b>.\n"
        f"Você aprova essa ação?"
    )
    await message.answer(texto_confirmacao, reply_markup=teclado_confirmar_zerar, parse_mode="HTML")
    await state.set_state(ConfigFluxo.aguardando_confirmacao_zerar)

@dp.message(ConfigFluxo.aguardando_confirmacao_zerar)
async def processar_zerar_numero(message: types.Message, state: FSMContext):
    if message.text == "Aprovar ✅":
        salvar_contador(1)
        if EXIBIR_LOGS: logger.info("🔢 Contador zerado pelo administrador após confirmação.")
        await message.answer("Contador zerado com sucesso! O próximo post será o 'Vídeo 1'.", reply_markup=obter_teclado_principal())
        await state.clear()
    else:
        await message.answer("Por favor, clique em Aprovar ✅ ou Cancelar ❌.", reply_markup=teclado_confirmar_zerar)

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

@dp.message(F.text == "Configurações Gerais ⚙️")
async def menu_configuracoes(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("⚙️ Acessando Dashboard de Configurações Gerais.")
    
    dados_div = ler_alvos_divulgacao()
    status_spam = "🔴 PAUSADO" if dados_div.get("pausado", False) else "🟢 ATIVO"
    
    dados_rotina = ler_config_rotina()
    status_rotina = "🔴 PAUSADAS" if dados_rotina.get("pausado", False) else "🟢 ATIVAS"
    
    texto = (
        "⚙️ <b>Central de Configurações Gerais</b>\n\n"
        "📊 <b>Status Atual das Automações:</b>\n"
        f"📢 SPAM em Grupos: {status_spam}\n"
        f"⏰ Mensagens de Rotina: {status_rotina}\n\n"
        "Escolha o módulo que deseja configurar abaixo:"
    )
    await message.answer(texto, reply_markup=teclado_configuracoes_gerais, parse_mode="HTML")

@dp.message(F.text == "Outros Canais 🗂️")
async def menu_outros_canais(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🗂️ Acessando a gaveta de Outros Canais.")
    await message.answer("Selecione o robô ou módulo secundário que deseja gerir:", reply_markup=teclado_outros_canais)

@dp.message(F.text == "Voltar ao Início 🔙")
async def voltar_inicio(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await message.answer("🏠 Voltando ao Painel Inicial.", reply_markup=obter_teclado_raiz())

@dp.message(F.text == "Voltar aos Canais 🔙")
async def voltar_outros_canais(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await message.answer("Selecione o robô ou módulo secundário que deseja gerir:", reply_markup=teclado_outros_canais)

@dp.message(F.text == "Voltar às Configs 🔙")
async def voltar_para_configuracoes(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🔙 Retornando à Central de Configurações Gerais.")
    await state.clear()
    await menu_configuracoes(message)

@dp.message(F.text == "Voltar ao Menu Espião 🔙")
async def voltar_menu_espiao(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await message.answer("🕵️ <b>Painel Principal do Espião</b>\nO que deseja acessar?", reply_markup=teclado_menu_espiao, parse_mode="HTML")

# --- HANDLERS DO PAINEL DO ESPIÃO 🕵️ ---
@dp.message(F.text == "Espião Afiliados 🕵️")
async def menu_espiao_principal(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🕵️ Acessando a página inicial do módulo Espião...")
    await message.answer("🕵️ <b>Painel Principal do Espião</b>\nO que deseja acessar?", reply_markup=teclado_menu_espiao, parse_mode="HTML")

@dp.message(F.text == "Grupos Vigiados 📡")
async def menu_grupos_vigiados(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("📡 Acessando a lista de grupos vigiados do Espião...")
    dados = ler_alvos_espiao()
    alvos = dados.get("alvos", [])
    destino = dados.get("canal_destino", "Não definido")
    
    texto = f"📡 <b>Gestão de Grupos Vigiados</b>\n\n"
    texto += f"🎯 <b>Canal de Destino:</b> {destino}\n\n"
    texto += "<b>Na Escuta:</b>\n"
    if alvos:
        for i, alvo in enumerate(alvos, 1):
            texto += f"   {i}. {alvo}\n"
    else:
        texto += "   <i>Nenhum grupo sendo monitorado no momento.</i>\n"
        
    await message.answer(texto, reply_markup=teclado_opcoes_espiao, parse_mode="HTML")
    await state.set_state(EspiaoFluxo.menu_principal)

@dp.message(EspiaoFluxo.menu_principal, F.text == "Adicionar Concorrente ➕")
async def pedir_alvo_espiao(message: types.Message, state: FSMContext):
    await message.answer("Envie o @username, link ou ID do grupo do concorrente que deseja monitorar:", reply_markup=teclado_cancelar)
    await state.set_state(EspiaoFluxo.aguardando_novo_alvo)

@dp.message(EspiaoFluxo.aguardando_novo_alvo)
async def salvar_alvo_espiao(message: types.Message, state: FSMContext):
    novo_alvo = message.text.strip()
    dados = ler_alvos_espiao()
    if novo_alvo not in dados["alvos"]:
        dados["alvos"].append(novo_alvo)
        salvar_alvos_espiao(dados)
        if EXIBIR_LOGS: logger.info(f"✅ Novo alvo do espião adicionado: {novo_alvo}")
        await message.answer(f"Alvo '{novo_alvo}' adicionado ao radar!", reply_markup=obter_teclado_principal())
    else:
        await message.answer("Este alvo já está na lista.", reply_markup=obter_teclado_principal())
    await state.clear()

@dp.message(EspiaoFluxo.menu_principal, F.text == "Remover Concorrente 🗑️")
async def pedir_remocao_espiao(message: types.Message, state: FSMContext):
    dados = ler_alvos_espiao()
    alvos = dados.get("alvos", [])
    if not alvos:
        await message.answer("Não há concorrentes para remover.", reply_markup=teclado_opcoes_espiao)
        return
    
    texto = "Qual alvo deseja excluir? Digite o <b>NÚMERO</b> correspondente:\n\n"
    for i, alvo in enumerate(alvos, 1):
        texto += f"{i}. {alvo}\n"
    await message.answer(texto, reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(EspiaoFluxo.aguardando_remocao_alvo)

@dp.message(EspiaoFluxo.aguardando_remocao_alvo)
async def processar_remocao_espiao(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas o NÚMERO.", reply_markup=teclado_cancelar)
        return
    indice = int(message.text) - 1
    dados = ler_alvos_espiao()
    if 0 <= indice < len(dados.get("alvos", [])):
        removido = dados["alvos"].pop(indice)
        salvar_alvos_espiao(dados)
        if EXIBIR_LOGS: logger.info(f"🗑️ Alvo do espião removido: {removido}")
        await message.answer(f"Alvo '{removido}' removido do radar!", reply_markup=obter_teclado_principal())
    else:
        await message.answer("Número inválido. Ação cancelada.", reply_markup=obter_teclado_principal())
    await state.clear()

@dp.message(EspiaoFluxo.menu_principal, F.text == "Definir Canal de Destino 🎯")
async def pedir_destino_espiao(message: types.Message, state: FSMContext):
    await message.answer("Envie o @username ou ID do seu Canal onde o bot postará os vídeos clonados (Ex: -100123456789):", reply_markup=teclado_cancelar)
    await state.set_state(EspiaoFluxo.aguardando_canal_destino)

@dp.message(EspiaoFluxo.aguardando_canal_destino)
async def salvar_destino_espiao(message: types.Message, state: FSMContext):
    destino = message.text.strip()
    dados = ler_alvos_espiao()
    dados["canal_destino"] = destino
    salvar_alvos_espiao(dados)
    if EXIBIR_LOGS: logger.info(f"🎯 Canal de destino do espião atualizado para: {destino}")
    await message.answer("Canal de destino configurado com sucesso!", reply_markup=obter_teclado_principal())
    await state.clear()

# ✅ NOVOS INTERRUPTORES INTERNOS DE PAUSA
@dp.message(ConfigDivulgacao.menu_principal, F.text.in_(["Pausar SPAM ⏸️", "Retomar SPAM ▶️"]))
async def alternar_pausa_spam_interno(message: types.Message, state: FSMContext):
    dados = ler_alvos_divulgacao()
    novo_status = not dados.get("pausado", False)
    dados["pausado"] = novo_status
    salvar_alvos_divulgacao(dados)

    if novo_status:
        if EXIBIR_LOGS: logger.info("⏸️ SPAM em grupos PAUSADO internamente.")
        await message.answer("⏸️ <b>SPAM em Grupos PAUSADO.</b>\nO Userbot não enviará mais convites.", parse_mode="HTML")
    else:
        if EXIBIR_LOGS: logger.info("▶️ SPAM em grupos ATIVADO internamente.")
        await message.answer("▶️ <b>SPAM em Grupos ATIVO.</b>\nO Userbot voltará a operar normalmente.", parse_mode="HTML")

    await gerenciar_divulgacao(message, state)

@dp.message(ConfigRotina.menu_principal, F.text.in_(["Pausar Rotinas ⏸️", "Retomar Rotinas ▶️"]))
async def alternar_pausa_rotinas_interno(message: types.Message, state: FSMContext):
    dados_rotina = ler_config_rotina()
    novo_status = not dados_rotina.get("pausado", False)
    dados_rotina["pausado"] = novo_status
    salvar_config_rotina(dados_rotina)

    if novo_status:
        if EXIBIR_LOGS: logger.info("⏸️ Mensagens de Rotina PAUSADAS internamente.")
        await message.answer("⏸️ <b>Mensagens de Rotina PAUSADAS.</b>\nAs mensagens automáticas do grupo foram suspensas.", parse_mode="HTML")
    else:
        if EXIBIR_LOGS: logger.info("▶️ Mensagens de Rotina ATIVADAS internamente.")
        await message.answer("▶️ <b>Mensagens de Rotina ATIVAS.</b>\nAs mensagens automáticas voltarão a ser enviadas.", parse_mode="HTML")

    await gerenciar_rotina(message, state)

# ✅ NOVO: Handler específico para corrigir o "Voltar" na pausa programada
@dp.message(PausaProgramadaFluxo.aguardando_selecao_servicos, F.text == "Voltar 🔙")
@dp.message(PausaProgramadaFluxo.aguardando_data_retorno, F.text == "Voltar 🔙")
async def voltar_pausa_para_inicio(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🔙 Comando Voltar acionado na Pausa Programada.")
    await state.clear()
    await message.answer("Operação cancelada. Voltando ao menu principal.", reply_markup=obter_teclado_principal())

@dp.message(F.text == "Pausar Postagens 🛑")
async def iniciar_pausa_programada(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    dados_pausa = ler_pausa_programada()
    
    if dados_pausa.get("ativa"):
        data_retorno = dados_pausa.get("data_retorno")
        texto = f"⚠️ <b>Pausa Programada Ativa!</b>\nO robô está em modo de descanso até <b>{data_retorno}</b>.\n\nDeseja cancelar esta pausa e retomar os serviços agora?"
        teclado = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Encerrar Pausa Agora ▶️")], [KeyboardButton(text="Voltar 🔙")]], resize_keyboard=True, is_persistent=True)
        await message.answer(texto, reply_markup=teclado, parse_mode="HTML")
        await state.set_state(PausaProgramadaFluxo.aguardando_selecao_servicos)
        return
        
    await message.answer("📅 <b>Configurar Pausa Programada</b>\n\nDigite a data e a hora exatas do seu <b>retorno</b> no formato DD/MM HH:MM (Exemplo: 29/05 15:00).\nO robô voltará a funcionar automaticamente neste momento exato.", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(PausaProgramadaFluxo.aguardando_data_retorno)

@dp.message(PausaProgramadaFluxo.aguardando_data_retorno)
async def processar_data_retorno(message: types.Message, state: FSMContext):
    import re
    from datetime import datetime
    
    match = re.match(r"^(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{1,2})$", message.text.strip())
    if not match:
        await message.answer("Formato inválido. Use DD/MM HH:MM, como por exemplo: 29/05 15:00.", reply_markup=teclado_cancelar)
        return
        
    dia, mes, hora, minuto = map(int, match.groups())
    hoje = datetime.now(fuso_horario)
    ano_atual = hoje.year
    
    try:
        data_retorno = datetime(year=ano_atual, month=mes, day=dia, hour=hora, minute=minuto, tzinfo=fuso_horario)
        if data_retorno <= hoje:
            if data_retorno.month < hoje.month:
                data_retorno = datetime(year=ano_atual + 1, month=mes, day=dia, hour=hora, minute=minuto, tzinfo=fuso_horario)
            else:
                await message.answer("A data e hora de retorno devem estar no futuro. Tente novamente:", reply_markup=teclado_cancelar)
                return
    except ValueError:
        await message.answer("Data ou hora inexistente. Tente novamente:", reply_markup=teclado_cancelar)
        return

    data_retorno_str = data_retorno.strftime("%d/%m/%Y %H:%M")
    await state.update_data(data_retorno_str=data_retorno_str)
    
    if EXIBIR_LOGS: logger.info("🔍 Mapeando serviços ativos para a tela de pausa programada...")
    dados_div = ler_alvos_divulgacao()
    spam_ativo = not dados_div.get("pausado", False)
    
    dados_rotina = ler_config_rotina()
    rotina_ativa = not dados_rotina.get("pausado", False)
    
    if not spam_ativo and not rotina_ativa:
        await message.answer(f"Ambos os serviços já estão pausados manualmente.\nApenas a rotina diária de avisos será agendada até {data_retorno_str}.\nConfirma?", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Confirmar Pausa ✅"), KeyboardButton(text="Cancelar ❌")]], resize_keyboard=True))
    else:
        opcoes = []
        if spam_ativo and rotina_ativa:
            opcoes = ["Pausar Ambos", "Apenas SPAM", "Apenas Rotina"]
        elif spam_ativo:
            opcoes = ["Pausar SPAM"]
        elif rotina_ativa:
            opcoes = ["Pausar Rotina"]
            
        botoes = [[KeyboardButton(text=op)] for op in opcoes]
        botoes.append([KeyboardButton(text="Cancelar ❌")])
        
        texto = f"Data e hora de retorno: <b>{data_retorno_str}</b>.\nQuais serviços você deseja pausar automaticamente agora?"
        await message.answer(texto, parse_mode="HTML", reply_markup=ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True))
        
    await state.set_state(PausaProgramadaFluxo.aguardando_selecao_servicos)

@dp.message(PausaProgramadaFluxo.aguardando_selecao_servicos)
async def confirmar_pausa_programada(message: types.Message, state: FSMContext):
    if EXIBIR_LOGS: logger.info("⚙️ Processando a seleção da pausa programada...")
    if message.text == "Encerrar Pausa Agora ▶️":
        dados_pausa = ler_pausa_programada()
        servicos = dados_pausa.get("servicos_pausados", [])
        
        if "spam" in servicos:
            dados_div = ler_alvos_divulgacao()
            dados_div["pausado"] = False
            salvar_alvos_divulgacao(dados_div)
            if EXIBIR_LOGS: logger.info("✅ SPAM reativado após encerramento forçado.")
        if "rotina" in servicos:
            dados_rotina = ler_config_rotina()
            dados_rotina["pausado"] = False
            salvar_config_rotina(dados_rotina)
            if EXIBIR_LOGS: logger.info("✅ Mensagens de rotina reativadas após encerramento forçado.")
                
        dados_pausa["ativa"] = False
        dados_pausa["servicos_pausados"] = []
        salvar_pausa_programada(dados_pausa)
        await message.answer("▶️ Pausa programada encerrada e serviços reativados com sucesso!", reply_markup=obter_teclado_principal())
        await state.clear()
        return

    opcoes_validas = ["Pausar Ambos", "Apenas SPAM", "Apenas Rotina", "Pausar SPAM", "Pausar Rotina", "Confirmar Pausa ✅"]
    if message.text not in opcoes_validas:
        await message.answer("Use um dos botões para escolher.", reply_markup=teclado_cancelar)
        return
        
    data = await state.get_data()
    data_retorno_str = data["data_retorno_str"]
    servicos_pausados = []
    
    if message.text in ["Pausar Ambos", "Apenas SPAM", "Pausar SPAM"]:
        dados_div = ler_alvos_divulgacao()
        dados_div["pausado"] = True
        salvar_alvos_divulgacao(dados_div)
        servicos_pausados.append("spam")
        
    if message.text in ["Pausar Ambos", "Apenas Rotina", "Pausar Rotina"]:
        dados_rotina = ler_config_rotina()
        dados_rotina["pausado"] = True
        salvar_config_rotina(dados_rotina)
        servicos_pausados.append("rotina")
        
    # Sorteio de um motivo dinâmico para a pausa
    motivos_pausa = [
        "manutenção preventiva nos servidores para garantir estabilidade",
        "curadoria minuciosa e validação de um novo lote gigante de vídeos premium de alta conversão",
        "atualização rigorosa no nosso sistema de proteção contra punições e bloqueios nas redes",
        "reestruturação interna e organização do acervo para entregar materiais ainda melhores"
    ]
    import random
    motivo_escolhido = random.choice(motivos_pausa)
    if EXIBIR_LOGS: logger.info(f"🎲 Motivo de pausa sorteado: {motivo_escolhido}")

    # Extrai apenas o dia e o mês (DD/MM) da string original
    data_curta = data_retorno_str.split(" ")[0][:5]

    # ✅ NOVO: Geração e envio do aviso exato no momento do acionamento
    prompt = (
        f"Você é um assistente de afiliados. Crie um aviso imediato MUITO CURTO E DIRETO "
        f"informando que as postagens estão pausadas a partir de agora para {motivo_escolhido}. "
        f"Avise que o retorno será no dia {data_curta}. "
        f"REGRA ABSOLUTA: Use no máximo 2 a 3 linhas e não ultrapasse 150 caracteres. "
        f"Seja direto, não peça desculpas longas e não dê explicações chatas. "
        f"Use emojis e entregue APENAS o texto da mensagem final."
    )
    texto_aviso = await gerar_mensagem_gemini(prompt)
    msg_imediata = await bot.send_message(GRUPO_ID, texto_aviso)
    
    dados_pausa = {
        "ativa": True,
        "data_retorno": data_retorno_str,
        "servicos_pausados": servicos_pausados,
        "id_aviso_imediato": msg_imediata.message_id, # Salva o ID para exclusão na rotina das 9h
        "motivo": motivo_escolhido # ✅ NOVO: Salva o motivo para manter a coerência diária
    }
    salvar_pausa_programada(dados_pausa)
    
    if EXIBIR_LOGS: logger.info(f"🛑 Pausa programada até {data_retorno_str}. Aviso imediato disparado. Serviços: {servicos_pausados}")
    await message.answer(f"🛑 <b>Pausa Configurada com Sucesso!</b>\n\nO aviso já foi enviado ao grupo. A partir de amanhã, o robô atualizará esse aviso todos os dias às 09h00 informando o retorno para o dia {data_retorno_str}.\nNo dia marcado, ele acordará automaticamente.", parse_mode="HTML", reply_markup=obter_teclado_principal())
    await state.clear()

# --- LÓGICA DE GERENCIAMENTO DE DIVULGAÇÃO ---
def ler_alvos_divulgacao():
    try:
        with open("alvos_divulgacao.json", "r") as f:
            dados = json.load(f)
            # ✅ Garante que as novas chaves existam mesmo em arquivos antigos
            if "repeticoes_internas" not in dados: dados["repeticoes_internas"] = 6
            if "replicas_mensagem" not in dados: dados["replicas_mensagem"] = 5
            return dados
    except (FileNotFoundError, json.JSONDecodeError):
        return {"alvos": [], "frequencia_por_hora": 0, "pausado": False, "forcar_disparo": False, "repeticoes_internas": 6, "replicas_mensagem": 5}

def salvar_alvos_divulgacao(dados):
    with open("alvos_divulgacao.json", "w") as f:
        json.dump(dados, f, indent=4)

@dp.message(F.text == "SPAM em Grupos 📢")
async def gerenciar_divulgacao(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    dados = ler_alvos_divulgacao()
    alvos = dados.get("alvos", [])
    freq_g = dados.get("frequencia_por_hora", 0)
    rep_int_g = dados.get("repeticoes_internas", 6)
    rep_msg_g = dados.get("replicas_mensagem", 5)
    status_pausa = "⏸️ Pausado" if dados.get("pausado") else "▶️ Rodando"
    config_alvos = dados.get("config_alvos", {})

    texto = f"📊 <b>Status da Divulgação</b> [{status_pausa}]\n\n"
    texto += f"🌍 <b>Padrão Global:</b>\n"
    texto += f"Frequência: {freq_g} msgs/hora\nRepetições no Texto: {rep_int_g}x\nRéplicas por Disparo: {rep_msg_g}x\n\n"
    texto += "🎯 <b>Alvos Ativos:</b>\n"
    
    if alvos:
        for i, alvo in enumerate(alvos, 1):
            conf = config_alvos.get(alvo, {})
            f_a = conf.get("frequencia", freq_g)
            ri_a = conf.get("repeticoes", rep_int_g)
            rm_a = conf.get("replicas", rep_msg_g)
            
            marcador = " (Personalizado)" if conf else ""
            texto += f"{i}. {alvo}{marcador}\n"
            texto += f"   └ Freq: {f_a}/h | Rep: {ri_a}x | Rép: {rm_a}x\n"
    else:
        texto += "Nenhum alvo cadastrado no momento.\n"
        
    texto_botao_pausa = "Retomar SPAM ▶️" if dados.get("pausado") else "Pausar SPAM ⏸️"
    teclado_dinamico_spam = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Adicionar Alvo ➕"), KeyboardButton(text="Excluir Alvo 🗑️")],
            [KeyboardButton(text="Editar Configurações ⚙️"), KeyboardButton(text="Forçar Disparo Agora 🚀")],
            [KeyboardButton(text=texto_botao_pausa), KeyboardButton(text="Voltar às Configs 🔙")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
        
    await message.answer(texto, parse_mode="HTML", reply_markup=teclado_dinamico_spam)
    await state.set_state(ConfigDivulgacao.menu_principal)

@dp.message(ConfigDivulgacao.menu_principal, F.text == "Adicionar Alvo ➕")
async def pedir_alvo(message: types.Message, state: FSMContext):
    await message.answer("Envie os links ou IDs dos grupos separados por vírgula.\nExemplo: <code>https://t.me/grupo1, -1009999999</code>", reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(ConfigDivulgacao.aguardando_alvos)

@dp.message(ConfigDivulgacao.aguardando_alvos)
async def salvar_alvo(message: types.Message, state: FSMContext):
    novos_alvos = [alvo.strip() for alvo in message.text.split(",") if alvo.strip()]
    if not novos_alvos:
        await message.answer("Nenhum alvo detectado. Tente novamente:", reply_markup=teclado_cancelar)
        return
        
    dados = ler_alvos_divulgacao()
    dados["alvos"].extend(novos_alvos)
    dados["alvos"] = list(dict.fromkeys(dados["alvos"]))
    salvar_alvos_divulgacao(dados)
    
    if EXIBIR_LOGS: logger.info(f"✅ Novos alvos adicionados: {novos_alvos}")
    await message.answer("Alvos adicionados com sucesso!", reply_markup=teclado_configuracoes_gerais)
    await state.clear()

@dp.message(ConfigDivulgacao.menu_principal, F.text == "Excluir Alvo 🗑️")
async def pedir_exclusao(message: types.Message, state: FSMContext):
    dados = ler_alvos_divulgacao()
    alvos = dados.get("alvos", [])
    if not alvos:
        await message.answer("Não há alvos cadastrados para excluir.", reply_markup=teclado_opcoes_divulgacao)
        return
        
    texto = "Qual alvo deseja excluir? Digite o <b>NÚMERO</b> correspondente da lista abaixo:\n\n"
    for i, alvo in enumerate(alvos, 1):
        texto += f"{i}. {alvo}\n"
    await message.answer(texto, reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(ConfigDivulgacao.aguardando_exclusao_alvo)

@dp.message(ConfigDivulgacao.aguardando_exclusao_alvo)
async def processar_exclusao(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas o NÚMERO do alvo.", reply_markup=teclado_cancelar)
        return
        
    indice = int(message.text) - 1
    dados = ler_alvos_divulgacao()
    alvos = dados.get("alvos", [])
    
    if 0 <= indice < len(alvos):
        removido = alvos.pop(indice)
        dados["alvos"] = alvos
        salvar_alvos_divulgacao(dados)
        if EXIBIR_LOGS: logger.info(f"🗑️ Alvo removido com sucesso: {removido}")
        await message.answer(f"Alvo '{removido}' excluído com sucesso!", reply_markup=teclado_configuracoes_gerais)
        await state.clear()
    else:
        await message.answer("Número inválido. Tente novamente:", reply_markup=teclado_cancelar)

@dp.message(ConfigDivulgacao.menu_principal, F.text == "Editar Configurações ⚙️")
async def iniciar_edicao_spam(message: types.Message, state: FSMContext):
    await message.answer("Deseja editar o Padrão Global ou configurar um Alvo Específico?", reply_markup=teclado_tipo_edicao)
    await state.set_state(ConfigDivulgacao.aguardando_tipo_edicao)

@dp.message(ConfigDivulgacao.aguardando_tipo_edicao, F.text.in_(["Global 🌍", "Por Alvo 🎯"]))
async def selecionar_tipo_edicao(message: types.Message, state: FSMContext):
    is_global = message.text == "Global 🌍"
    await state.update_data(edicao_global=is_global)
    
    dados = ler_alvos_divulgacao()
    
    if is_global:
        freq_atual = dados.get("frequencia_por_hora", 0)
        rep_atual = dados.get("repeticoes_internas", 6)
        repl_atual = dados.get("replicas_mensagem", 5)
        
        texto_explicativo = (
            "🌍 <b>Edição do Padrão Global</b>\n\n"
            "Envie os três valores juntos separados por vírgula nesta exata ordem:\n\n"
            "<b>1️⃣ Frequência:</b> Disparos por hora efetuados pelo bot.\n"
            "<b>2️⃣ Repetições:</b> Blocos de texto contidos na mensagem longa.\n"
            "<b>3️⃣ Réplicas:</b> Mensagens disparadas seguidas na mesma rajada.\n\n"
            f"<i>Exemplo com a sua configuração atual:</i>\n<code>{freq_atual}, {rep_atual}, {repl_atual}</code>"
        )
        await message.answer(texto_explicativo, reply_markup=teclado_cancelar, parse_mode="HTML")
        await state.set_state(ConfigDivulgacao.aguardando_valores_unificados)
    else:
        alvos = dados.get("alvos", [])
        if not alvos:
            await message.answer("Não há alvos para editar. Adicione um primeiro.", reply_markup=teclado_opcoes_divulgacao)
            await state.set_state(ConfigDivulgacao.menu_principal)
            return
        
        texto = "Qual alvo deseja personalizar? Digite o <b>NÚMERO</b> correspondente da lista abaixo:\n\n"
        for i, alvo in enumerate(alvos, 1):
            texto += f"{i}. {alvo}\n"
        await message.answer(texto, reply_markup=teclado_cancelar, parse_mode="HTML")
        await state.set_state(ConfigDivulgacao.aguardando_selecao_alvo)

@dp.message(ConfigDivulgacao.aguardando_selecao_alvo)
async def selecionar_alvo_edicao(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas o NÚMERO.", reply_markup=teclado_cancelar)
        return
    indice = int(message.text) - 1
    dados = ler_alvos_divulgacao()
    alvos = dados.get("alvos", [])
    
    if 0 <= indice < len(alvos):
        alvo_selecionado = alvos[indice]
        await state.update_data(alvo_em_edicao=alvo_selecionado)
        
        config_alvos = dados.get("config_alvos", {})
        conf_alvo = config_alvos.get(alvo_selecionado, {})
        
        freq_atual = conf_alvo.get("frequencia", dados.get("frequencia_por_hora", 0))
        rep_atual = conf_alvo.get("repeticoes", dados.get("repeticoes_internas", 6))
        repl_atual = conf_alvo.get("replicas", dados.get("replicas_mensagem", 5))
        
        texto_explicativo = (
            f"🎯 <b>Edição do Alvo:</b> {alvo_selecionado}\n\n"
            "Envie os três valores juntos separados por vírgula nesta exata ordem:\n\n"
            "<b>1️⃣ Frequência:</b> Disparos por hora efetuados pelo bot.\n"
            "<b>2️⃣ Repetições:</b> Blocos de texto contidos na mensagem longa.\n"
            "<b>3️⃣ Réplicas:</b> Mensagens disparadas seguidas na mesma rajada.\n\n"
            f"<i>Exemplo com a sua configuração atual:</i>\n<code>{freq_atual}, {rep_atual}, {repl_atual}</code>"
        )
        await message.answer(texto_explicativo, reply_markup=teclado_cancelar, parse_mode="HTML")
        await state.set_state(ConfigDivulgacao.aguardando_valores_unificados)
    else:
        await message.answer("Número inválido. Tente novamente:", reply_markup=teclado_cancelar)

@dp.message(ConfigDivulgacao.aguardando_valores_unificados)
async def salvar_valores_unificados(message: types.Message, state: FSMContext):
    import re
    match = re.match(r"^(\d+)\s*,\s*(\d+)\s*,\s*(\d+)$", message.text.strip())
    
    if not match:
        await message.answer("Formato inválido. Envie os três números isolados por vírgula (Exemplo: 3, 6, 5).", reply_markup=teclado_cancelar)
        return
        
    freq, rep, repl = map(int, match.groups())
    
    data = await state.get_data()
    is_global = data.get("edicao_global")
    alvo = data.get("alvo_em_edicao")
    
    dados = ler_alvos_divulgacao()
    if "config_alvos" not in dados:
        dados["config_alvos"] = {}
        
    if is_global:
        dados["frequencia_por_hora"] = freq
        dados["repeticoes_internas"] = rep
        dados["replicas_mensagem"] = repl
        msg_final = f"✅ <b>Padrão Global atualizado!</b>\nFrequência: {freq}x/h | Repetições: {rep}x | Réplicas: {repl}x"
    else:
        if alvo not in dados["config_alvos"]:
            dados["config_alvos"][alvo] = {}
        dados["config_alvos"][alvo]["frequencia"] = freq
        dados["config_alvos"][alvo]["repeticoes"] = rep
        dados["config_alvos"][alvo]["replicas"] = repl
        msg_final = f"✅ <b>Alvo personalizado atualizado!</b>\nAlvo: {alvo}\nFrequência: {freq}x/h | Repetições: {rep}x | Réplicas: {repl}x"
        
    salvar_alvos_divulgacao(dados)
    if EXIBIR_LOGS: logger.info(f"⚙️ Configuração salva numa única passagem. Global: {is_global} | Freq: {freq}, Rep: {rep}, Repl: {repl}")
    
    await message.answer(msg_final, reply_markup=teclado_configuracoes_gerais, parse_mode="HTML")
    await state.clear()

@dp.message(ConfigDivulgacao.menu_principal, F.text == "Forçar Disparo Agora 🚀")
async def acionar_disparo_imediato(message: types.Message):
    dados = ler_alvos_divulgacao()
    dados["forcar_disparo"] = True
    salvar_alvos_divulgacao(dados)
    if EXIBIR_LOGS: logger.info("🚀 Comando de disparo forçado enviado para o arquivo JSON.")
    await message.answer("🚀 <b>Disparo Imediato Acionado!</b>\nO Userbot detectará o comando e enviará a rajada de convites em até 5 segundos.", parse_mode="HTML", reply_markup=teclado_opcoes_divulgacao)

# --- LÓGICA DE MENSAGENS DE ROTINA ---
@dp.message(F.text == "Mensagens de Rotina ⏰")
async def gerenciar_rotina(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    dados = ler_config_rotina()
    texto = "⏰ <b>Configuração de Janelas e Frequência</b>\n\n"
    
    nomes_amigaveis = {
        "bom_dia": "Bom Dia ☀️",
        "boa_noite": "Boa Noite 🌙",
        "incentivo": "Incentivo 🔥",
        "link_grupo": "Convite do Grupo 🔗",
        "divulgar_gem": "Prompt GEM 🤖"
    }
    
    # Ordem de exibição forçada para organizar o painel
    ordem_exibicao = ["bom_dia", "incentivo", "link_grupo", "divulgar_gem", "boa_noite"]
    
    for tipo in ordem_exibicao:
        if tipo in dados:
            config = dados[tipo]
            nome_exibicao = nomes_amigaveis.get(tipo, tipo.replace("_", " ").title())
            texto += f"🔹 <b>{nome_exibicao}</b>\n"
            texto += f"   Janela de Sorteio: {config['inicio']}h às {config['fim']}h\n"
            texto += f"   Disparos por Dia: {config['frequencia']}x\n\n"
        
    texto_botao_pausa = "Retomar Rotinas ▶️" if dados.get("pausado") else "Pausar Rotinas ⏸️"
    teclado_dinamico_rotina = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Editar Bom Dia ☀️"), KeyboardButton(text="Editar Incentivo 🔥")],
            [KeyboardButton(text="Editar Convite 🔗"), KeyboardButton(text="Editar Prompt GEM 🤖")],
            [KeyboardButton(text="Editar Boa Noite 🌙"), KeyboardButton(text=texto_botao_pausa)],
            [KeyboardButton(text="Voltar às Configs 🔙")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
        
    texto += "Selecione o que deseja editar abaixo:"
    await message.answer(texto, reply_markup=teclado_dinamico_rotina, parse_mode="HTML")
    await state.set_state(ConfigRotina.menu_principal)

@dp.message(ConfigRotina.menu_principal, F.text.in_(["Editar Bom Dia ☀️", "Editar Boa Noite 🌙", "Editar Incentivo 🔥", "Editar Convite 🔗", "Editar Prompt GEM 🤖"]))
async def pedir_horario_rotina(message: types.Message, state: FSMContext):
    tipo_map = {
        "Editar Bom Dia ☀️": "bom_dia",
        "Editar Boa Noite 🌙": "boa_noite",
        "Editar Incentivo 🔥": "incentivo",
        "Editar Convite 🔗": "link_grupo",
        "Editar Prompt GEM 🤖": "divulgar_gem"
    }
    tipo = tipo_map[message.text]
    await state.update_data(tipo_edicao=tipo)
    
    # ✅ Lê as configurações atuais para criar os exemplos dinâmicos
    dados_atuais = ler_config_rotina()
    config_atual = dados_atuais.get(tipo, {"inicio": 6, "fim": 9, "frequencia": 1})
    inicio_ex = config_atual["inicio"]
    fim_ex = config_atual["fim"]
    freq_ex = config_atual["frequencia"]
    
    if tipo in ["bom_dia", "boa_noite"]:
        await message.answer(
            f"Vamos configurar a janela de sorteio para <b>{message.text}</b>.\n"
            "Atenção: A quantidade de envios para esta rotina é fixada em 1x ao dia.\n\n"
            "Envie os dados no seguinte formato: <code>HoraInicio-HoraFim</code>\n\n"
            f"Exemplo atualizado com a sua configuração:\n<code>{inicio_ex}-{fim_ex}</code>",
            reply_markup=teclado_cancelar,
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"Vamos configurar a janela de sorteio e a quantidade de envios para <b>{message.text}</b>.\n\n"
            "Envie os dados no seguinte formato: <code>HoraInicio-HoraFim, Quantidade</code>\n\n"
            f"Exemplo atualizado com a sua configuração:\n<code>{inicio_ex}-{fim_ex}, {freq_ex}</code>",
            reply_markup=teclado_cancelar,
            parse_mode="HTML"
        )
    await state.set_state(ConfigRotina.aguardando_novo_horario)

@dp.message(ConfigRotina.aguardando_novo_horario)
async def salvar_horario_rotina(message: types.Message, state: FSMContext):
    import re
    data = await state.get_data()
    tipo = data['tipo_edicao']
    
    if tipo in ["bom_dia", "boa_noite"]:
        # ✅ Validação exclusiva para rotinas de disparo único
        match = re.match(r"^(\d{1,2})-(\d{1,2})$", message.text.strip())
        if not match:
            await message.answer("Formato inválido! Use o formato exato como no exemplo: 6-9", reply_markup=teclado_cancelar)
            return
        
        inicio, fim = map(int, match.groups())
        freq = 1
    else:
        # ✅ Validação completa para a rotina de incentivo
        match = re.match(r"^(\d{1,2})-(\d{1,2}),\s*(\d+)$", message.text.strip())
        if not match:
            await message.answer("Formato inválido! Use o formato exato como no exemplo: 10-20, 3", reply_markup=teclado_cancelar)
            return
            
        inicio, fim, freq = map(int, match.groups())
    
    if inicio >= fim or inicio < 0 or fim > 23 or freq < 1:
        await message.answer("Valores inválidos! A hora de início deve ser menor que a do fim (entre 0 e 23) e a quantidade mínima é 1.", reply_markup=teclado_cancelar)
        return
        
    dados = ler_config_rotina()
    dados[tipo] = {"inicio": inicio, "fim": fim, "frequencia": freq}
    salvar_config_rotina(dados)
    
    if EXIBIR_LOGS: logger.info(f"✅ Configuração de {tipo} atualizada: {inicio}h até {fim}h, {freq}x ao dia.")
    
    # Força o re-sorteio imediato para aplicar as novas regras hoje mesmo
    agendar_tarefas_diarias()
    
    await message.answer("✅ Configuração salva! Os novos horários já foram sorteados e agendados para hoje.", reply_markup=teclado_configuracoes_gerais)
    await state.clear()

# --- SISTEMA DE GERENCIAMENTO DE FILA (INTERATIVO) ---
class GerenciarFilaFluxo(StatesGroup):
    menu_principal = State()
    aguardando_posicao_excluir = State()
    aguardando_posicao_editar = State()
    aguardando_nova_legenda = State()
    aguardando_posicao_reordenar = State()
    aguardando_nova_posicao = State()
    aguardando_posicao_numeracao = State()
    aguardando_nova_numeracao = State()
    aguardando_posicao_publicar = State()

teclado_gerenciar_fila = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Publicar Agora 🚀"), KeyboardButton(text="Excluir Vídeo 🗑️")],
        [KeyboardButton(text="Editar Legenda ✏️"), KeyboardButton(text="Editar Numeração 🔢")],
        [KeyboardButton(text="Mover Posição ↕️"), KeyboardButton(text="Voltar ao Início 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

@dp.message(F.text == "Gerenciar Fila 📋")
async def menu_gerenciar_fila(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("📋 Acessando painel de gestão da fila...")
    
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    if not fila:
        await message.answer("A fila de postagens está vazia neste momento.", reply_markup=obter_teclado_principal())
        return
        
    texto = "📋 <b>Fila de Postagens Agendadas</b>\n\n"
    for i, item in enumerate(fila, 1):
        legenda = item.get("legenda", "")
        primeira_linha = legenda.split('\n')[0].replace('<b>', '').replace('</b>', '')[:40]
        if not primeira_linha: primeira_linha = f"Vídeo {i}"
        
        data_add = item.get("data_adicao", "Desconhecida")
        texto += f"<b>{i}.</b> {primeira_linha}...\n📅 <i>Adicionado em: {data_add}</i>\n\n"
        
    texto += "O que deseja fazer com a fila?"
    await message.answer(texto, reply_markup=teclado_gerenciar_fila, parse_mode="HTML")
    await state.set_state(GerenciarFilaFluxo.menu_principal)

@dp.message(GerenciarFilaFluxo.menu_principal, F.text == "Voltar ao Início 🔙")
async def sair_menu_fila(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Painel de Controle atualizado.", reply_markup=obter_teclado_principal())

@dp.message(GerenciarFilaFluxo.menu_principal, F.text == "Excluir Vídeo 🗑️")
async def pedir_exclusao_fila(message: types.Message, state: FSMContext):
    await message.answer("Digite o <b>NÚMERO</b> da posição do vídeo que deseja excluir:", reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(GerenciarFilaFluxo.aguardando_posicao_excluir)

@dp.message(GerenciarFilaFluxo.aguardando_posicao_excluir)
async def processar_exclusao_fila(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas números.", reply_markup=teclado_cancelar)
        return
        
    posicao = int(message.text) - 1
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    if 0 <= posicao < len(fila):
        item_removido = fila.pop(posicao)
        caminho_video = item_removido.get("caminho_video")
        
        if caminho_video and os.path.exists(caminho_video):
            ainda_usado = any(x.get("caminho_video") == caminho_video for x in fila)
            if not ainda_usado:
                os.remove(caminho_video)
                if EXIBIR_LOGS: logger.info("🧹 Fila: Ficheiro físico excluído após remoção manual.")
                
        fila_data["fila"] = fila
        salvar_fila_postagens(fila_data)
        
        if EXIBIR_LOGS: logger.info(f"🗑️ Fila: Vídeo na posição {posicao+1} removido com sucesso.")
        agendar_fila_postagens() 
        
        await message.answer("✅ Vídeo excluído com sucesso e horários recalculados!", reply_markup=obter_teclado_principal())
        await state.clear()
    else:
        await message.answer("Número de posição inválido. Tente novamente:", reply_markup=teclado_cancelar)

@dp.message(GerenciarFilaFluxo.menu_principal, F.text == "Editar Legenda ✏️")
async def pedir_edicao_fila(message: types.Message, state: FSMContext):
    await message.answer("Digite o <b>NÚMERO</b> da posição do vídeo que deseja editar:", reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(GerenciarFilaFluxo.aguardando_posicao_editar)

@dp.message(GerenciarFilaFluxo.aguardando_posicao_editar)
async def processar_posicao_editar_fila(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas números.", reply_markup=teclado_cancelar)
        return
        
    posicao = int(message.text) - 1
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    if 0 <= posicao < len(fila):
        await state.update_data(posicao_edicao=posicao)
        legenda_atual = fila[posicao].get("legenda", "")
        
        await message.answer(f"Aqui está a legenda atual para copiar e editar:\n\n<code>{legenda_atual}</code>\n\nEnvie agora a <b>NOVA LEGENDA COMPLETA</b>:", parse_mode="HTML", reply_markup=teclado_cancelar)
        await state.set_state(GerenciarFilaFluxo.aguardando_nova_legenda)
    else:
        await message.answer("Número de posição inválido. Tente novamente:", reply_markup=teclado_cancelar)

@dp.message(GerenciarFilaFluxo.aguardando_nova_legenda)
async def salvar_nova_legenda_fila(message: types.Message, state: FSMContext):
    data = await state.get_data()
    posicao = data.get("posicao_edicao")
    nova_legenda = message.html_text 
    
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    if 0 <= posicao < len(fila):
        fila[posicao]["legenda"] = nova_legenda
        salvar_fila_postagens(fila_data)
        if EXIBIR_LOGS: logger.info(f"✏️ Fila: Legenda do vídeo na posição {posicao+1} atualizada.")
        
        await message.answer("✅ Legenda atualizada com sucesso!", reply_markup=obter_teclado_principal())
        await state.clear()
    else:
        await message.answer("Erro de sincronização. Operação cancelada.", reply_markup=obter_teclado_principal())
        await state.clear()

@dp.message(GerenciarFilaFluxo.menu_principal, F.text == "Mover Posição ↕️")
async def pedir_reordenar_fila(message: types.Message, state: FSMContext):
    await message.answer("Digite o <b>NÚMERO</b> da posição atual do vídeo que deseja mover:", reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(GerenciarFilaFluxo.aguardando_posicao_reordenar)

@dp.message(GerenciarFilaFluxo.aguardando_posicao_reordenar)
async def pedir_nova_posicao_fila(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas números.", reply_markup=teclado_cancelar)
        return
        
    posicao_atual = int(message.text) - 1
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    if 0 <= posicao_atual < len(fila):
        await state.update_data(posicao_origem=posicao_atual)
        await message.answer(f"O vídeo está na posição {posicao_atual+1}. Para qual posição deseja enviá-lo? (Ex: 1 para o topo)", reply_markup=teclado_cancelar)
        await state.set_state(GerenciarFilaFluxo.aguardando_nova_posicao)
    else:
        await message.answer("Número de posição inválido. Tente novamente:", reply_markup=teclado_cancelar)

@dp.message(GerenciarFilaFluxo.aguardando_nova_posicao)
async def salvar_nova_posicao_fila(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas números.", reply_markup=teclado_cancelar)
        return
        
    nova_posicao = int(message.text) - 1
    data = await state.get_data()
    posicao_origem = data.get("posicao_origem")
    
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    if 0 <= posicao_origem < len(fila):
        if nova_posicao < 0: nova_posicao = 0
        if nova_posicao >= len(fila): nova_posicao = len(fila) - 1
        
        item = fila.pop(posicao_origem)
        fila.insert(nova_posicao, item)
        
        import re
        
        # 1. Identificação do Ponto de Partida (menor número da fila)
        menor_numero = float('inf')
        for f_item in fila:
            match = re.search(r'(?i)Vídeo\s+(\d+)', f_item.get("legenda", ""))
            if match:
                num = int(match.group(1))
                if num < menor_numero:
                    menor_numero = num
                    
        # Fallback de segurança caso a fila perca a formatação
        if menor_numero == float('inf'):
            async with _lock_contador:
                menor_numero = ler_contador()
                
        if EXIBIR_LOGS: logger.info(f"🔄 Iniciando auto-correção da numeração da fila a partir do Vídeo {menor_numero}...")
        
        # 2. Renumeração Dinâmica de cima para baixo
        numero_atual_cascata = menor_numero
        for i in range(len(fila)):
            legenda_antiga = fila[i].get("legenda", "")
            # Atualiza apenas a primeira ocorrência do padrão para evitar mexer no resto da cópia
            nova_legenda = re.sub(r'(?i)(Vídeo\s+)\d+', rf'\g<1>{numero_atual_cascata}', legenda_antiga, count=1)
            fila[i]["legenda"] = nova_legenda
            numero_atual_cascata += 1
            
        fila_data["fila"] = fila
        salvar_fila_postagens(fila_data)
        
        # 3. Sincronização do Contador Global
        async with _lock_contador:
            salvar_contador(numero_atual_cascata)
        
        if EXIBIR_LOGS: logger.info(f"↕️ Fila: Vídeo movido da posição {posicao_origem+1} para {nova_posicao+1}.")
        if EXIBIR_LOGS: logger.info(f"✅ Auto-correção concluída. Contador global atualizado para a próxima postagem: {numero_atual_cascata}.")
        
        agendar_fila_postagens() 
        
        await message.answer(f"✅ Vídeo movido para a posição {nova_posicao+1}!\n🔄 A numeração de toda a fila foi corrigida em cascata e os horários recalculados com sucesso.", reply_markup=obter_teclado_principal())
        await state.clear()
    else:
        await message.answer("Erro de sincronização. Operação cancelada.", reply_markup=obter_teclado_principal())
        await state.clear()

@dp.message(GerenciarFilaFluxo.menu_principal, F.text == "Publicar Agora 🚀")
async def pedir_posicao_publicar(message: types.Message, state: FSMContext):
    await message.answer("Digite o <b>NÚMERO</b> da posição do vídeo na fila que deseja publicar imediatamente:", reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(GerenciarFilaFluxo.aguardando_posicao_publicar)

@dp.message(GerenciarFilaFluxo.aguardando_posicao_publicar)
async def processar_publicacao_imediata(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas números.", reply_markup=teclado_cancelar)
        return
        
    posicao = int(message.text) - 1
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    import re
    
    if 0 <= posicao < len(fila):
        item = fila.pop(posicao)
        
        # 1. Extrai o número correto (o que deveria ser o próximo a nível global)
        async with _lock_contador:
            numero_disparo = ler_contador()
            
        if EXIBIR_LOGS: logger.info(f"🚀 Iniciando antecipação do vídeo na posição {posicao+1}. Novo número atribuído: {numero_disparo}.")
        
        # 2. Atualiza estritamente a legenda do vídeo selecionado para publicação
        legenda_disparo = item.get("legenda", "")
        nova_legenda_disparo = re.sub(r'(?i)(Vídeo\s+)\d+', rf'\g<1>{numero_disparo}', legenda_disparo, count=1)
        
        caminho_video = item.get("caminho_video")
        video_id = item.get("video_id")
        
        msg_status = await message.answer("📤 A preparar ficheiros e a publicar o vídeo agora mesmo... Aguarde.", reply_markup=teclado_cancelar)
        
        sucesso_upload = False
        try:
            # 3. Disparo imediato para o Telegram
            if caminho_video and os.path.exists(caminho_video):
                arquivo = FSInputFile(caminho_video)
                msg = await bot.send_video(chat_id=GRUPO_ID, video=arquivo, caption=nova_legenda_disparo, parse_mode="HTML")
                sucesso_upload = True
                
                novo_file_id = msg.video.file_id
                for x in fila:
                    if x.get("caminho_video") == caminho_video:
                        x["video_id"] = novo_file_id
                        x["caminho_video"] = None
            elif video_id:
                await bot.send_video(chat_id=GRUPO_ID, video=video_id, caption=nova_legenda_disparo, parse_mode="HTML")
                sucesso_upload = True
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Falha no disparo imediato: {e}")
            await msg_status.delete()
            await message.answer(f"Ocorreu um erro técnico ao publicar o vídeo: {e}", reply_markup=obter_teclado_principal())
            await state.clear()
            return
            
        await msg_status.delete()
            
        if sucesso_upload:
            if EXIBIR_LOGS: logger.info("✅ Vídeo antecipado submetido com sucesso no grupo.")
            
            if caminho_video and os.path.exists(caminho_video):
                ainda_usado = any(x.get("caminho_video") == caminho_video for x in fila)
                if not ainda_usado:
                    os.remove(caminho_video)
                    if EXIBIR_LOGS: logger.info("🧹 Ficheiro físico removido do servidor após o disparo antecipado.")
            
            # 4. Numeração em cascata da fila restante
            numero_atual_cascata = numero_disparo + 1
            if fila:
                if EXIBIR_LOGS: logger.info(f"🔄 A iniciar renumeração da fila restante em cascata a partir de {numero_atual_cascata}...")
                for i in range(len(fila)):
                    legenda_antiga = fila[i].get("legenda", "")
                    nova_legenda = re.sub(r'(?i)(Vídeo\s+)\d+', rf'\g<1>{numero_atual_cascata}', legenda_antiga, count=1)
                    fila[i]["legenda"] = nova_legenda
                    numero_atual_cascata += 1
                    
            fila_data["fila"] = fila
            salvar_fila_postagens(fila_data)
            
            # 5. Gravação final e blindagem de concorrência
            async with _lock_contador:
                salvar_contador(numero_atual_cascata)
                
            if EXIBIR_LOGS: logger.info(f"✅ Sistema sincronizado. O contador aguarda a próxima postagem no número: {numero_atual_cascata}.")
            
            # 6. Recálculo da fragmentação da hora para alocar o buraco deixado pela exclusão
            agendar_fila_postagens()
            
            await message.answer(f"🚀 Publicação realizada com sucesso!\n🔄 A fila foi renumerada e os horários restantes de hoje foram recalculados para absorver o novo espaçamento.", reply_markup=obter_teclado_principal())
            await state.clear()
    else:
        await message.answer("Erro de sincronização ou posição inválida. Operação cancelada.", reply_markup=obter_teclado_principal())
        await state.clear()

# --- MOTOR DE PROCESSAMENTO DO ESPIÃO ---
def ler_fila_clonagem():
    try:
        with open("fila_clonagem.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"fila": []}

def salvar_fila_clonagem(dados):
    with open("fila_clonagem.json", "w") as f:
        json.dump(dados, f, indent=4)

async def converter_link_shopee(link_original):
    if not SHOPEE_APP_ID or not SHOPEE_APP_SECRET:
        if EXIBIR_LOGS: logger.warning("⏳ [API Shopee] Chaves ausentes no .env. Ignorando conversão e mantendo o link original.")
        return link_original

    link_processar = link_original
    
    if "shp.ee" in link_original or "shope.ee" in link_original or "s.shopee.com.br" in link_original:
        if EXIBIR_LOGS: logger.info(f"🔍 Detectado link encurtado. A iniciar a expansão do URL: {link_original}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(link_original, allow_redirects=True) as resp:
                    link_processar = str(resp.url)
                    if EXIBIR_LOGS: logger.info(f"✅ Expansão concluída. URL longo obtido: {link_processar}")
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro ao tentar expandir o link: {e}. Será mantido o original.")

    if EXIBIR_LOGS: logger.info(f"🔗 [API Shopee] A iniciar criptografia para o link: {link_processar}")

    timestamp = int(time.time())
    endpoint = "https://open-api.affiliate.shopee.com.br/graphql"

    # A query foi condensada em uma linha para evitar erros de leitura (espaços invisíveis) da Shopee
    payload = {
        "query": "mutation generateShortLink($originUrl: String!) { generateShortLink(input: {originUrl: $originUrl}) { shortLink } }",
        "variables": {
            "originUrl": link_processar
        }
    }
    
    payload_json = json.dumps(payload, separators=(',', ':'))

    # A API de Afiliados exige concatenação simples com a senha no final, e não HMAC
    fator_base = f"{SHOPEE_APP_ID}{timestamp}{payload_json}{SHOPEE_APP_SECRET}"
    assinatura = hashlib.sha256(fator_base.encode('utf-8')).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={SHOPEE_APP_ID}, Timestamp={timestamp}, Signature={assinatura}"
    }

    if EXIBIR_LOGS: logger.info("📤 [API Shopee] Enviando requisição assinada para os servidores...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, data=payload_json) as response:
                resposta_dados = await response.json()

                if response.status == 200 and "data" in resposta_dados and resposta_dados["data"].get("generateShortLink"):
                    novo_link = resposta_dados["data"]["generateShortLink"]["shortLink"]
                    if EXIBIR_LOGS: logger.info(f"✅ [API Shopee] Link convertido com sucesso: {novo_link}")
                    return novo_link
                else:
                    if EXIBIR_LOGS: logger.error(f"❌ [API Shopee] Falha na conversão. Resposta: {resposta_dados}")
                    return link_original

    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [API Shopee] Erro de comunicação com o servidor: {e}")
        return link_original

async def processar_fila_espiao():
    dados_espiao = ler_alvos_espiao()
    canal_destino = dados_espiao.get("canal_destino")
    
    if not canal_destino:
        return # Aborta o processo silenciosamente se o destino não foi configurado no painel
        
    fila_data = ler_fila_clonagem()
    
    # ✅ NOVA LÓGICA: Verificação do relógio orgânico de pausas
    agora = datetime.now()
    proximo_proc_str = fila_data.get("proximo_processamento")
    
    if proximo_proc_str:
        try:
            proximo_proc = datetime.strptime(proximo_proc_str, "%Y-%m-%d %H:%M:%S")
            if agora < proximo_proc:
                return # O relógio de pausa ainda não expirou, aborta a execução silenciosamente
        except ValueError:
            pass # Se houver um erro de leitura na data antiga, prossegue
            
    fila = fila_data.get("fila", [])
    
    # Busca o primeiro vídeo da fila que ainda não foi publicado
    item_pendente = next((item for item in fila if not item.get("processado")), None)
    if not item_pendente:
        return
        
    caminho_video = item_pendente["caminho_video"]
    link_original = item_pendente["link_original"]
    item_id = item_pendente["id"]
    
    # ✅ NOVO: Verificação de validade temporal da postagem (6 horas)
    data_captura_str = item_pendente.get("data_captura")
    if data_captura_str:
        try:
            data_captura = datetime.strptime(data_captura_str, "%Y-%m-%d %H:%M:%S")
            horas_na_fila = (agora - data_captura).total_seconds() / 3600
            
            if horas_na_fila > 6:
                if EXIBIR_LOGS: logger.warning(f"⏳ Clone {item_id} expirou (esperou {horas_na_fila:.1f}h). Ficheiro descartado para priorizar ofertas recentes.")
                
                # Executa a faxina física e remove o item obsoleto
                fila_data["fila"] = [item for item in fila if item["id"] != item_id]
                salvar_fila_clonagem(fila_data)
                
                try:
                    if os.path.exists(caminho_video): os.remove(caminho_video)
                except:
                    pass
                return # Aborta o processamento para que o próximo ciclo pegue um vídeo novo
        except ValueError:
            pass # Continua normalmente caso o formato da data seja antigo
            
    if not os.path.exists(caminho_video):
        if EXIBIR_LOGS: logger.warning(f"⚠️ Ficheiro {caminho_video} não encontrado. Marcando clone {item_id} como falho.")
        item_pendente["processado"] = True
        salvar_fila_clonagem(fila_data)
        return
        
    if EXIBIR_LOGS: logger.info(f"🕵️ Iniciando processamento automático do clone: {item_id}")
    
    # 1. Passagem do link pela Shopee
    link_final = await converter_link_shopee(link_original)
    
    # 2. Análise do vídeo pela IA para reescrita autoral
    def gerar_copy_clone():
        import time
        video_gemini = client.files.upload(file=caminho_video)
        
        while video_gemini.state.name == "PROCESSING":
            time.sleep(2)
            video_gemini = client.files.get(name=video_gemini.name)
            
        if video_gemini.state.name == "FAILED":
            raise Exception("Falha de processamento no servidor do Google.")
            
        prompt = (
            "Assista ao vídeo e identifique qual é o produto demonstrado. "
            "A sua resposta deve conter APENAS o nome do produto acompanhado de um emoji correspondente no início. "
            "É estritamente proibido criar textos de vendas, descrições, gatilhos mentais ou frases de encerramento. "
            "Exemplo de saída esperada: 👟 Tênis Casual Feminino"
        )
        
        for modelo_nome in MODELOS_CASCATA_GEMINI:
            try:
                if EXIBIR_LOGS: logger.info(f"⏳ [Espião] Consultando motor: {modelo_nome}...")
                response = client.models.generate_content(
                    model=modelo_nome,
                    contents=[video_gemini, prompt]
                )
                if response and response.text:
                    if EXIBIR_LOGS: logger.info(f"✅ [Espião] Sucesso com o modelo {modelo_nome}!")
                    return response.text.strip()
            except Exception as erro_modelo:
                if "429" in str(erro_modelo):
                    if EXIBIR_LOGS: logger.warning(f"⚠️ [Espião] Limite atingido em {modelo_nome}. Tentando o próximo...")
                    continue
                else:
                    if EXIBIR_LOGS: logger.warning(f"⚠️ [Espião] Erro no modelo {modelo_nome}: {erro_modelo}")
                    continue
                    
        raise Exception("Todos os modelos da cascata falharam por limite de cota ou erro.")
        
    try:
        if EXIBIR_LOGS: logger.info("🧠 Solicitando à IA a criação de uma nova Copy para o vídeo clonado...")
        texto_ia = await asyncio.to_thread(gerar_copy_clone)
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro na IA ao processar clone: {e}")
        texto_ia = "🛍️ <b>Vídeo do Produto</b>"
        
    legenda_postagem = f"{texto_ia}\n\n🔗 <b>Link do Produto:</b>\n{link_final}"
    
    # 3. Disparo isolado no Canal Paralelo
    try:
        arquivo = FSInputFile(caminho_video)
        await bot.send_video(chat_id=canal_destino, video=arquivo, caption=legenda_postagem, parse_mode="HTML")
        if EXIBIR_LOGS: logger.info(f"✅ Clone {item_id} publicado com sucesso no canal {canal_destino}!")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha ao postar clone no Telegram: {e}")
        
    # 4. Encerramento, Faxina e Agendamento Orgânico
    fila_data["fila"] = [item for item in fila if item["id"] != item_id]
    
    # ✅ Sorteia um intervalo aleatório entre 3 e 7 minutos para adormecer o motor
    minutos_espera = random.randint(3, 7)
    from datetime import timedelta
    proximo_horario = datetime.now() + timedelta(minutes=minutos_espera)
    fila_data["proximo_processamento"] = proximo_horario.strftime("%Y-%m-%d %H:%M:%S")
    
    salvar_fila_clonagem(fila_data)
    if EXIBIR_LOGS: logger.info(f"⏳ Pausa orgânica ativada. O próximo vídeo da fila só será postado após as {proximo_horario.strftime('%H:%M:%S')} (Pausa de {minutos_espera} min).")
    
    try:
        os.remove(caminho_video)
        if EXIBIR_LOGS: logger.info("🧹 Ficheiro de vídeo do clone removido do disco.")
    except:
        pass

async def main():
    # Agendador mestre que roda todo dia às 00:01
    scheduler.add_job(agendar_tarefas_diarias, 'cron', hour=0, minute=1, timezone=FUSO_STR)
    
    # ✅ Agendador da lixeira persistente (roda todos os dias pontualmente às 03:00)
    scheduler.add_job(varredor_de_lixeira, 'cron', hour=3, minute=0, timezone=FUSO_STR)
    
    # ✅ Novo: Despertador e aviso da Pausa Programada (roda às 09:00)
    scheduler.add_job(verificar_pausa_diaria, 'cron', hour=9, minute=0, timezone=FUSO_STR)
    
    # ✅ Novo: Verificador de retorno da Pausa Programada (roda a cada 1 minuto)
    if EXIBIR_LOGS: logger.info("🚀 Iniciando monitoramento de retomada de pausa minuto a minuto...")
    scheduler.add_job(verificar_retorno_pausa_minuto, 'interval', minutes=1, timezone=FUSO_STR)
    
    # ✅ Verificador do Espião: O motor verifica a fila a cada 1 minuto (a cadência aleatória é gerida internamente)
    scheduler.add_job(processar_fila_espiao, 'interval', minutes=1, timezone=FUSO_STR)
    
    # Roda o agendador imediatamente ao ligar o bot para garantir o dia atual
    agendar_tarefas_diarias()
    
    # Roda a faxina imediatamente ao ligar para limpar pendências de quedas
    asyncio.create_task(varredor_de_lixeira())
    
    scheduler.start()
    if EXIBIR_LOGS: logger.info("🔍 Verificando status de pausa programada na inicialização...")
    dados_pausa = ler_pausa_programada()
    if dados_pausa.get("ativa") and "rotina" in dados_pausa.get("servicos_pausados", []):
        dados_rotina = ler_config_rotina()
        dados_rotina["pausado"] = True
        salvar_config_rotina(dados_rotina)
        if EXIBIR_LOGS: logger.info("⏸️ Rotinas estavam em pausa programada. Marcado como pausado no JSON com sucesso.")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
