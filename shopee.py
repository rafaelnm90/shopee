# 0. CONFIGURAÇÕES INICIAIS
EXIBIR_LOGS = True
import os
from dotenv import load_dotenv
load_dotenv()
import logging
import json
import asyncio
import random
from datetime import datetime, timedelta
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
import matplotlib.pyplot as plt
import io

import espelhador

# 1. CONSTANTES E TOKENS
API_TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = 1226920464
GRUPO_ID = -1003909405581
LINK_GRUPO = "https://t.me/shopee_video_afiliado"
GRUPO_VIRAL_ID = -1003932482573
LINK_GRUPO_VIRAL = "https://t.me/acervo_viral_shopee"
GEMINI_API_KEY = os.getenv('GEMINI_KEY')
SHOPEE_APP_ID = os.getenv('SHOPEE_APP_ID')
SHOPEE_APP_SECRET = os.getenv('SHOPEE_APP_SECRET')

MODELOS_CASCATA_GEMINI = [
    "gemini-3.1-pro-preview",
    "gemini-2.5-pro",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash-lite"
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
    aguardando_decisao_erro = State()
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

class ConfigDivulgacaoViral(StatesGroup):
    menu_principal = State()
    aguardando_alvos = State()
    aguardando_exclusao_alvo = State()
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
    aguardando_confirmacao_pausa = State()
    aguardando_intencao_encerramento = State()
    aguardando_confirmacao_encerramento = State()

class EspiaoFluxo(StatesGroup):
    menu_principal = State()
    aguardando_novo_alvo = State()
    aguardando_confirmacao_alvo = State() # ✅ NOVO
    aguardando_remocao_alvo = State()
    aguardando_confirmacao_remocao = State() # ✅ NOVO
    aguardando_canal_destino = State()
    aguardando_confirmacao_destino = State() # ✅ NOVO

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
FUSO_STR = "America/Sao_Paulo"
fuso_horario = ZoneInfo(FUSO_STR)
_lock_contador = asyncio.Lock()
scheduler = AsyncIOScheduler(timezone=FUSO_STR)

dp.include_router(espelhador.router)
espelhador.configurar_dependencias(bot, scheduler)

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

# 🛠️ Teclado para erro na IA (NOVO)
teclado_erro_ia = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Tentar Novamente 🔄"), KeyboardButton(text="Digitar Manualmente ✍️")],
        [KeyboardButton(text="Cancelar ❌")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

# 🛠️ Teclado de confirmação da análise da inteligência artificial
teclado_confirmacao = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Digitar Nome ✍️")],
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
        [KeyboardButton(text="Voltar 🔙")]
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
def obter_teclado_configuracoes_gerais():
    dados_pausa = ler_pausa_programada()
    texto_botao_pausa = "Retomar Postagens ▶️" if dados_pausa.get("ativa") else "Pausar Postagens 🛑"
    
    botoes = [
        [KeyboardButton(text="Mensagens de Rotina ⏰"), KeyboardButton(text="SPAM em Grupos 📢")],
        [KeyboardButton(text="Editar Número da Postagem 🔢"), KeyboardButton(text=texto_botao_pausa)],
        [KeyboardButton(text="🔄 Atualizar Rotinas")],
        [KeyboardButton(text="Voltar 🔙")]
    ]
    return ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)

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
        [KeyboardButton(text="Espião Afiliados 🕵️"), KeyboardButton(text="Espelhador de Canais 🔄")],
        [KeyboardButton(text="Voltar ao Início 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

# 🛠️ Função do novo Menu Inicial Raiz
def obter_teclado_raiz():
    botoes = [
        [KeyboardButton(text="Canal Afiliados 📺"), KeyboardButton(text="Outros Canais 🗂️")],
        [KeyboardButton(text="Relatório Geral 📊")]
    ]
    return ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)

# 🛠️ Função centralizadora da pasta do Canal Principal
def obter_teclado_principal():
    botoes = [
        [KeyboardButton(text="Criar Postagem 📝")],
        [KeyboardButton(text="Gerenciar Fila 📋")],
        [KeyboardButton(text="Disparar Bom Dia ☀️"), KeyboardButton(text="Disparar Boa Noite 🌙")],
        [KeyboardButton(text="Disparar Incentivo 🔥"), KeyboardButton(text="Disparar Convite do Grupo 🔗")],
        [KeyboardButton(text="Disparar Convite Viral 🚀")],
        [KeyboardButton(text="🛠️ Configurações Avançadas")], 
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
        [KeyboardButton(text="Disparar Convite Afiliados 🚀"), KeyboardButton(text="Disparar Convite do Grupo 🔗\u200b")],
        [KeyboardButton(text="⚙️ Automações (SPAM e Rotina)\u200b")],
        [KeyboardButton(text="Voltar aos Canais 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

teclado_automacoes_espiao = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Rotinas do Espião ⏰"), KeyboardButton(text="SPAM do Espião 📢")],
        [KeyboardButton(text="Voltar ao Menu Espião 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

teclado_opcoes_espiao = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Definir Canal de Destino 🎯")],
        [KeyboardButton(text="Adicionar Concorrente ➕"), KeyboardButton(text="Remover Concorrente 🗑️")],
        [KeyboardButton(text="Voltar ao Menu Espião 🔙")]
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
    
    from datetime import timedelta
    videos_para_hoje = [item for item in fila if (item.get("data_adicao") <= hoje_str or item.get("data_adicao") == "2000-01-01") and not item.get("postado")]
    
    if not videos_para_hoje:
        if EXIBIR_LOGS: logger.info("⏳ Todos os vídeos na fila estão agendados aguardando o dia de amanhã.")
        return
        
    dados_rotina = ler_config_rotina()
    ultimo_bd = dados_rotina.get("ultimo_bom_dia", "")
    ultimo_bn = dados_rotina.get("ultimo_boa_noite", "")
    
    if EXIBIR_LOGS: logger.info("🚀 Construindo miolo útil dinâmico ancorado no Bom Dia e Boa Noite...")
    
    horarios_ocupados = []
    rotinas_virais_lista = ["promo_principal", "link_grupo_viral", "divulgar_gem_viral"]
    
    for job in scheduler.get_jobs():
        proxima_execucao = getattr(job, 'next_run_time', None)
        if proxima_execucao and not job.id.startswith('job_fila_postagem_'):
            # ✅ Isolamento Absoluto: O motor de produtos Afiliado ignora a agenda do mundo Viral
            if not any(rv in job.id for rv in rotinas_virais_lista):
                horarios_ocupados.append(proxima_execucao.astimezone(fuso_horario))
            
    # Fronteira Inicial Dinâmica (Ancorada no Bom Dia)
    job_bd = scheduler.get_job('job_rotina_bom_dia_0')
    if ultimo_bd == hoje_str:
        limite_inicio_hoje = max(agora + timedelta(minutes=2), agora.replace(hour=0, minute=0, second=0, microsecond=0))
    elif job_bd and getattr(job_bd, 'next_run_time', None):
        limite_inicio_hoje = max(agora + timedelta(minutes=2), job_bd.next_run_time.astimezone(fuso_horario) + timedelta(minutes=10))
    else:
        hora_fim_bom_dia = dados_rotina.get("bom_dia", {}).get("fim", 9)
        limite_inicio_hoje = max(agora + timedelta(minutes=2), agora.replace(hour=hora_fim_bom_dia, minute=0, second=0, microsecond=0))
    
    # Fronteira Final Dinâmica (Ancorada no Boa Noite)
    job_bn = scheduler.get_job('job_rotina_boa_noite_0')
    if ultimo_bn == hoje_str:
        limite_fim_hoje = agora
    elif job_bn and getattr(job_bn, 'next_run_time', None):
        limite_fim_hoje = job_bn.next_run_time.astimezone(fuso_horario) - timedelta(minutes=15)
    else:
        hora_inicio_boa_noite = dados_rotina.get("boa_noite", {}).get("inicio", 21)
        hora_limite_final = hora_inicio_boa_noite - 1 if hora_inicio_boa_noite > 0 else 23
        limite_fim_hoje = agora.replace(hour=hora_limite_final, minute=59, second=59, microsecond=0)
    
    if agora >= limite_fim_hoje:
        if EXIBIR_LOGS: logger.warning("⚠️ O expediente de hoje encerrou. Transbordando vídeos retidos para amanhã.")
        amanha_str = (agora + timedelta(days=1)).strftime("%Y-%m-%d")
        for item in videos_para_hoje:
            item["data_adicao"] = amanha_str
        salvar_fila_postagens(fila_data)
        return
        
    inicio_real = limite_inicio_hoje
    minutos_disponiveis = int((limite_fim_hoje - inicio_real).total_seconds() / 60)
    
    qtd_videos = len(videos_para_hoje)
    espacamento_medio = minutos_disponiveis // qtd_videos if qtd_videos > 0 else 15
    
    # ✅ COMPRESSÃO DINÂMICA E TRAVA DE SILÊNCIO: Protege 15 minutos em torno de cada rotina do Afiliado.
    if espacamento_medio < 15:
        espacamento_medio = 15
        
    minuto_atual_busca = inicio_real
    # ✅ CAMPO DE FORÇA: 15 minutos obrigatórios de distância de qualquer rotina
    INTERVALO_MINIMO = 15
    
    houve_transbordo = False
    amanha_str = (agora + timedelta(days=1)).strftime("%Y-%m-%d")
    
    for index, item in enumerate(videos_para_hoje):
        limite_sorteio = minuto_atual_busca + timedelta(minutes=espacamento_medio - 1)
        if limite_sorteio < minuto_atual_busca: limite_sorteio = minuto_atual_busca
        
        max_minutos_offset = int((limite_sorteio - minuto_atual_busca).total_seconds() / 60)
        if max_minutos_offset < 0: max_minutos_offset = 0
        
        sucesso = False
        horario_disparo = None
        
        for tentativa in range(100):
            minutos_offset = random.randint(0, max_minutos_offset)
            horario_candidato = minuto_atual_busca + timedelta(minutes=minutos_offset, seconds=random.randint(0, 59))
            
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
            if EXIBIR_LOGS: logger.warning(f"⚠️ Vídeo {index+1}: Sem lacuna limpa. Forçando encaixe de segurança com 3 min de distância.")
            # ✅ Fallback reduzido para garantir que os vídeos caibam no expediente
            horario_disparo = minuto_atual_busca + timedelta(minutes=3)

        if horario_disparo >= limite_fim_hoje:
            if EXIBIR_LOGS: logger.warning(f"🛑 O vídeo excedeu o horário limite ({horario_disparo.strftime('%H:%M:%S')}). Transbordando para amanhã.")
            item["data_adicao"] = amanha_str
            houve_transbordo = True
            continue
            
        horarios_ocupados.append(horario_disparo)
        
        job_id = f"job_fila_postagem_{item['id']}"
        scheduler.add_job(executar_postagem_fila, 'date', run_date=horario_disparo, args=[item['id']], id=job_id, replace_existing=True)
        if EXIBIR_LOGS: logger.info(f"✅ Fila: Vídeo {index+1}/{qtd_videos} distribuído organicamente para as {horario_disparo.strftime('%H:%M:%S')}")
        
        # ✅ CORREÇÃO MATEMÁTICA: Avança a grade com base no bloco estático, e não no horário sorteado (Fim do Efeito Bola de Neve)
        minuto_atual_busca = minuto_atual_busca + timedelta(minutes=espacamento_medio)
        
    if houve_transbordo:
        salvar_fila_postagens(fila_data)
        if EXIBIR_LOGS: logger.info("✅ Fila atualizada no sistema após o transbordo dos vídeos excedentes.")

async def executar_postagem_fila(item_id):
    if EXIBIR_LOGS: logger.info(f"📤 Iniciando processo de extração de vídeo da fila...")
    
    agora = datetime.now(fuso_horario)
    hoje_str = agora.strftime("%Y-%m-%d")
    
    # 🚀 CORREÇÃO: Trava de segurança absoluta baseada na abertura do expediente
    dados_rotina = ler_config_rotina()
    ultimo_bd = dados_rotina.get("ultimo_bom_dia", "")
    hora_ultimo_bd = dados_rotina.get("hora_ultimo_bom_dia", "")
    ultimo_bn = dados_rotina.get("ultimo_boa_noite", "")
    
    # ✅ NOVA TRAVA MATINAL ABSOLUTA E MARGEM DE RESPIRO
    if ultimo_bd != hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Trava Ativada: O expediente ainda não foi aberto pelo 'Bom Dia'. Retendo vídeo...")
        
        # Inteligência: Espia a agenda para empurrar o vídeo para 15 minutos DEPOIS do Bom Dia
        job_bd = scheduler.get_job('job_rotina_bom_dia_0')
        if job_bd and getattr(job_bd, 'next_run_time', None):
            tempo_bom_dia = job_bd.next_run_time.astimezone(fuso_horario)
            novo_horario = max(agora + timedelta(minutes=15), tempo_bom_dia + timedelta(minutes=15))
        else:
            novo_horario = agora + timedelta(minutes=15)
            
        job_id_reagendado = f"job_fila_postagem_adiado_{int(agora.timestamp())}"
        scheduler.add_job(executar_postagem_fila, 'date', run_date=novo_horario, args=[item_id], id=job_id_reagendado, replace_existing=True)
        return
        
    elif hora_ultimo_bd:
        hora_bd_obj = datetime.strptime(hora_ultimo_bd, "%H:%M").time()
        momento_bd = datetime.combine(agora.date(), hora_bd_obj).replace(tzinfo=fuso_horario)
        minutos_passados = (agora - momento_bd).total_seconds() / 60
        
        if minutos_passados < 10:
            if EXIBIR_LOGS: logger.warning(f"🛑 Trava de Respiro: O 'Bom Dia' saiu há apenas {int(minutos_passados)} min. Empurrando vídeo para respeitar a margem de 10 a 15 min.")
            novo_horario = momento_bd + timedelta(minutes=12)
            if novo_horario <= agora: novo_horario = agora + timedelta(minutes=2)
            job_id_reagendado = f"job_fila_postagem_adiado_{int(agora.timestamp())}"
            scheduler.add_job(executar_postagem_fila, 'date', run_date=novo_horario, args=[item_id], id=job_id_reagendado, replace_existing=True)
            return

    # Trava Noturna Dinâmica: Avalia o horário exato do Boa Noite agendado, e não apenas a hora estática
    job_bn = scheduler.get_job('job_rotina_boa_noite_0')
    
    if ultimo_bn == hoje_str:
        expediente_encerrado = True
    elif job_bn and getattr(job_bn, 'next_run_time', None):
        from datetime import timedelta
        limite_fim_hoje = job_bn.next_run_time.astimezone(fuso_horario) - timedelta(minutes=15)
        expediente_encerrado = agora >= limite_fim_hoje
    else:
        hora_fechamento_videos = dados_rotina.get("boa_noite", {}).get("inicio", 21)
        expediente_encerrado = agora.hour >= hora_fechamento_videos

    if expediente_encerrado:
        if EXIBIR_LOGS: logger.warning(f"🛑 Trava Noturna Ativada: O limite dinâmico do expediente encerrou. Vídeo retido para amanhã.")
        return

    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    if EXIBIR_LOGS: logger.info(f"🔎 Buscando o vídeo exato na fila pelo ID: {item_id}...")
    
    # Leitura estrita com base no ID exato passado pelo agendador
    item = next((x for x in fila if x.get("id") == item_id and not x.get("postado")), None)
    
    if not item:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Vídeo alvo ({item_id}) não encontrado. Acionando busca de segurança (fallback)...")
        item = next((x for x in fila if (x.get("data_adicao") <= hoje_str or x.get("data_adicao") == "2000-01-01") and not x.get("postado")), None)
        
        if not item:
            if EXIBIR_LOGS: logger.warning("❌ Nenhum vídeo elegível encontrado na fila para extração.")
            return
            
    item_id_real = item["id"]
    caminho_video = item.get("caminho_video")
    video_id = item.get("video_id")
    legenda = item.get("legenda")
    
    if EXIBIR_LOGS: logger.info(f"🎯 Extração concluída. Vídeo {item_id_real} capturado do topo da fila atualizada.")
    
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
        # Marca o item como postado em vez de excluí-lo (para manter o histórico visual no painel)
        for x in fila:
            if x["id"] == item_id_real:
                x["postado"] = True
                x["horario_postagem"] = agora.strftime("%H:%M")
                x["data_postagem"] = hoje_str # ✅ NOVO: Registra o dia para a faxina não apagar no restart
                if EXIBIR_LOGS: logger.info(f"🚀 Horário de postagem registrado na fila: {x['horario_postagem']}")
                break
        fila_data["fila"] = fila
        salvar_fila_postagens(fila_data)
        if EXIBIR_LOGS: logger.info(f"✅ Vídeo {item_id_real} marcado como 'Já postado' no histórico da fila.")
        
        # A faxina física real do arquivo foi transferida para a limpeza da madrugada em agendar_tarefas_diarias
        # para permitir que o vídeo fique visível no painel até o final do dia.

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

def recalcular_datas_pos_pausa():
    if EXIBIR_LOGS: logger.info("🔄 Iniciando recálculo de datas da fila pós-pausa...")
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    if not fila:
        if EXIBIR_LOGS: logger.info("⚠️ Fila vazia, nenhum ajuste de data necessário.")
        return
        
    from datetime import datetime, timedelta
    agora = datetime.now(fuso_horario)
    hoje_obj = agora.date()
    
    menor_data_obj = None
    for item in fila:
        d_str = item.get("data_adicao", "")
        if d_str and d_str != "2000-01-01":
            try:
                d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
                if menor_data_obj is None or d_obj < menor_data_obj:
                    menor_data_obj = d_obj
            except ValueError:
                pass
                
    if menor_data_obj and menor_data_obj < hoje_obj:
        offset_dias = (hoje_obj - menor_data_obj).days
        if EXIBIR_LOGS: logger.info(f"⏳ Deslocamento identificado: {offset_dias} dias. Aplicando offset na fila...")
        
        for item in fila:
            d_str = item.get("data_adicao", "")
            if d_str and d_str != "2000-01-01":
                try:
                    d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
                    nova_data = d_obj + timedelta(days=offset_dias)
                    item["data_adicao"] = nova_data.strftime("%Y-%m-%d")
                except ValueError:
                    pass
        
        fila_data["fila"] = fila
        salvar_fila_postagens(fila_data)
        if EXIBIR_LOGS: logger.info("✅ Datas da fila recalculadas e salvas com sucesso.")
    else:
        if EXIBIR_LOGS: logger.info("✅ O primeiro vídeo da fila já está no futuro ou presente. Nenhum offset necessário.")

async def verificar_pausa_diaria():
    if EXIBIR_LOGS: logger.info("⏰ Iniciando verificação diária de pausa programada (envio de aviso)...")
    dados_pausa = ler_pausa_programada()
    if not dados_pausa.get("ativa"):
        return
        
    data_retorno_str = dados_pausa.get("data_retorno")
    if not data_retorno_str:
        return
        
    if EXIBIR_LOGS: logger.info("🛑 Pausa ativa. Enviando aviso diário ao grupo principal...")
    
    # 1. Recupera e apaga o aviso antigo
    id_aviso_imediato = dados_pausa.get("id_aviso_imediato")
    if id_aviso_imediato:
        if EXIBIR_LOGS: logger.info("🧹 Excluindo aviso antigo para dar lugar ao novo aviso diário...")
        await apagar_mensagem_automatica(id_aviso_imediato, GRUPO_ID)

    motivo_salvo = dados_pausa.get("motivo", "organização interna e curadoria de novos conteúdos")
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
    
    # 2. Envia o novo aviso
    msg_enviada = await bot.send_message(GRUPO_ID, texto)
    
    # ✅ CORREÇÃO: Atualiza o ID na memória da pausa em vez de atirar para a lixeira
    dados_pausa["id_aviso_imediato"] = msg_enviada.message_id
    salvar_pausa_programada(dados_pausa)
    
    if EXIBIR_LOGS: logger.info("✅ Aviso diário enviado e salvo na memória com sucesso.")

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
        
        # Apaga a placa de "Fechado"
        id_aviso = dados_pausa.pop("id_aviso_imediato", None)
        if id_aviso:
            await apagar_mensagem_automatica(id_aviso, GRUPO_ID)
            
        # ✅ NOVO: A IA gera o aviso de retorno ao trabalho silenciosamente no background
        prompt_retorno = (
            "Você é um assistente de afiliados. Crie uma mensagem MUITO CURTA E EMPOLGANTE "
            "avisando o grupo que a pausa de manutenção acabou, o canal voltou à ativa e os "
            "vídeos com ofertas voltarão a ser postados normalmente a partir de hoje. "
            "REGRA ABSOLUTA: Seja direto (máximo 150 caracteres), use emojis animados e entregue APENAS o texto pronto."
        )
        texto_retorno = await gerar_mensagem_gemini(prompt_retorno)
        
        # ✅ CORREÇÃO: Salva a mensagem enviada numa variável e joga o ID na lixeira
        msg_retorno = await bot.send_message(GRUPO_ID, texto_retorno)
        registrar_lixeira(msg_retorno.message_id, GRUPO_ID)
        
        if EXIBIR_LOGS: logger.info("✅ Mensagem triunfal de retorno postada no grupo e enviada para a lixeira.")
            
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
        salvar_pausa_programada(dados_pausa)
        recalcular_datas_pos_pausa()
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

def limpar_historico_antigo():
    if os.path.exists("historico_mensagens.json"):
        os.remove("historico_mensagens.json")
        if EXIBIR_LOGS: logger.info("🧹 Histórico de mensagens do userbot reiniciado.")

def registrar_lixeira(msg_id, chat_id=GRUPO_ID):
    dados = ler_lixeira()
    dados["mensagens"].append({"id": msg_id, "chat_id": chat_id})
    salvar_lixeira(dados)
    if EXIBIR_LOGS: logger.info(f"💾 ID {msg_id} (Chat: {chat_id}) salvo na lixeira persistente para exclusão na madrugada (03h00).")

async def varredor_de_lixeira():
    if EXIBIR_LOGS: logger.info("🧹 Iniciando varredura diária da lixeira persistente (03h00)...")
    dados = ler_lixeira()
    mensagens = dados.get("mensagens", [])
    
    for msg in mensagens:
        try:
            # Recupera o ID e o chat correto da mensagem salva
            msg_id = msg.get("id") if isinstance(msg, dict) else msg
            chat_destino = msg.get("chat_id", GRUPO_ID) if isinstance(msg, dict) else GRUPO_ID
            await apagar_mensagem_automatica(msg_id, chat_destino)
        except Exception as e:
            if EXIBIR_LOGS: logger.warning(f"⚠️ Erro ao processar item da lixeira: {e}")
            
    dados["mensagens"] = []
    salvar_lixeira(dados)
    if EXIBIR_LOGS: logger.info("✅ Lixeira persistente esvaziada com sucesso.")

async def apagar_mensagem_automatica(msg_id, chat_id=GRUPO_ID):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        if EXIBIR_LOGS: logger.info(f"🧹 Faxina concluída: Mensagem {msg_id} apagada do chat {chat_id}.")
    except Exception as e:
        if EXIBIR_LOGS: logger.info(f"⚠️ Faxina: A mensagem {msg_id} já havia sido apagada manualmente.")

async def disparar_mensagem(tipo, forcar=False):
    if EXIBIR_LOGS: logger.info(f"🔍 Validando status antes de disparar a rotina '{tipo}' (Forçar: {forcar})...")
    
    dados_rotina = ler_config_rotina()
    is_viral = tipo in ["promo_principal", "link_grupo_viral", "divulgar_gem_viral"]
    
    if is_viral and dados_rotina.get("pausado_viral", False) and not forcar:
        if EXIBIR_LOGS: logger.info(f"🛑 Disparo abortado ({tipo}): As rotinas do VIRAL estão pausadas no sistema.")
        return
    elif not is_viral and dados_rotina.get("pausado", False) and not forcar:
        if EXIBIR_LOGS: logger.info(f"🛑 Disparo abortado ({tipo}): As rotinas do PRINCIPAL estão pausadas no sistema.")
        return

    agora_tz = datetime.now(fuso_horario)
    hoje_str = datetime.now(fuso_horario).strftime("%Y-%m-%d")
    
    # 🚀 LÓGICA DE TRAVA ABSOLUTA E EXPEDIENTE
    if tipo == "bom_dia" and dados_rotina.get("ultimo_bom_dia") == hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Bloqueio Anti-Acidente: O 'Bom Dia' já foi enviado hoje.")
        return
    if tipo == "boa_noite" and dados_rotina.get("ultimo_boa_noite") == hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Bloqueio Anti-Acidente: O 'Boa Noite' já foi enviado hoje.")
        return
        
    # ✅ NOVA TRAVA: Controle absoluto do Expediente e Margem de Respiro
    if tipo not in ["bom_dia", "boa_noite"] and not tipo.startswith("campanha_"):
        if dados_rotina.get("ultimo_bom_dia") != hoje_str:
            if EXIBIR_LOGS: logger.warning(f"🛑 Disparo abortado ({tipo}): O expediente ainda não foi aberto pelo 'Bom Dia'.")
            return
            
        hora_ultimo_bd = dados_rotina.get("hora_ultimo_bom_dia", "")
        if hora_ultimo_bd:
            hora_bd_obj = datetime.strptime(hora_ultimo_bd, "%H:%M").time()
            momento_bd = datetime.combine(agora_tz.date(), hora_bd_obj).replace(tzinfo=fuso_horario)
            minutos_passados = (agora_tz - momento_bd).total_seconds() / 60
            
            if minutos_passados < 10:
                if EXIBIR_LOGS: logger.warning(f"🛑 Disparo ({tipo}) adiado: O 'Bom Dia' saiu há apenas {int(minutos_passados)} min. Reagendando para respeitar a margem de segurança.")
                novo_horario = momento_bd + timedelta(minutes=random.randint(12, 25))
                job_id = f"job_rotina_{tipo}_reagendado_{int(agora_tz.timestamp())}"
                scheduler.add_job(disparar_mensagem, 'date', run_date=novo_horario, args=[tipo], id=job_id, replace_existing=True)
                return
                
        if dados_rotina.get("ultimo_boa_noite") == hoje_str:
            if EXIBIR_LOGS: logger.warning(f"🛑 Disparo abortado ({tipo}): O expediente já foi encerrado pelo 'Boa Noite'.")
            return

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
            "amigos afiliados para o nosso grupo gratuito. "
            "REGRA: Parta do pressuposto de que o leitor JÁ ESTÁ NO GRUPO. O objetivo é encorajá-lo a trazer novas pessoas. "
            "Não adicione nenhum link na sua resposta. Use emojis."
        )
    elif tipo == "link_grupo_viral":
        prompt = (
            f"{contexto_afiliado} Crie um convite curto e empolgante pedindo aos membros que convidem "
            "seus amigos para entrarem neste nosso acervo de vídeos virais. "
            "REGRA ABSOLUTA: Parta do pressuposto de que o leitor JÁ ESTÁ NO GRUPO. "
            "O foco é apenas encorajá-los a trazer novas pessoas para o nosso grupo gratuito. Não adicione nenhum link na sua resposta. Use emojis."
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

    elif tipo in ["divulgar_gem", "divulgar_gem_viral"]:
        prompt = (
            "Você atua como assistente de afiliados. Crie uma mensagem curta (MÁXIMO 200 CARACTERES) "
            "perguntando se a equipe está com dificuldade para criar legendas e hashtags. "
            "Convide-os a usar nosso prompt automatizado. Insinue de forma sutil que utilizar a "
            "versão PRO do Gemini resulta em textos muito melhores. Altere as palavras e a abordagem "
            "toda vez que gerar esse texto, use emojis e entregue apenas a mensagem pronta, sem aspas."
        )

    elif tipo == "promo_viral":
        prompt = (
            "Você é um criador de conteúdo recomendando o canal de um parceiro para a sua comunidade. "
            "Crie uma recomendação MUITO CURTA E NATURAL (MÁXIMO 150 CARACTERES) chamando a galera para conhecer o trabalho desse parceiro. "
            "Explique de forma fluida e humana que o dono de lá tem um grupo gratuito focado em vídeos virais estilo 'copia e cola' diretos das tendências. "
            "REGRA ABSOLUTA: Aja como um humano recomendando o trabalho de outra pessoa. NUNCA use palavras que deem a entender que o grupo é seu (evite 'nosso grupo', 'eu criei', 'estou postando'). "
            "Refira-se ao grupo na terceira pessoa ('o parceiro posta', 'o canal deles'). "
            "Use emojis, varie o texto a cada geração e entregue apenas a mensagem pronta, sem aspas e sem links."
        )
    elif tipo == "promo_principal":
        prompt = (
            "Você é um criador de conteúdo recomendando o canal de um parceiro para a sua comunidade. "
            "Crie uma recomendação MUITO CURTA E NATURAL (MÁXIMO 150 CARACTERES) chamando a galera para conhecer o canal parceiro (Acervo Afiliados). "
            "Explique de forma fluida e humana que o dono de lá libera o acesso a um grupo gratuito com conteúdos premium, editados e selecionados a dedo. "
            "REGRA ABSOLUTA: Aja como um humano recomendando o trabalho de outra pessoa. NUNCA use palavras que deem a entender que o grupo é seu (evite 'nosso grupo', 'estou liberando', 'nós distribuímos'). "
            "Refira-se ao grupo na terceira pessoa ('eles liberam', 'o parceiro solta'). "
            "Use emojis, varie o texto a cada geração e entregue apenas a mensagem pronta, sem aspas e sem links."
        )

    texto = await gerar_mensagem_gemini(prompt)
    
    # Roteamento de chat: Define qual grupo receberá qual mensagem
    chat_destino = GRUPO_VIRAL_ID if tipo in ["promo_principal", "link_grupo_viral", "divulgar_gem_viral"] else GRUPO_ID
    
    if EXIBIR_LOGS: logger.info(f"🚀 Enviando rotina ({tipo}) para o chat {chat_destino}: {texto[:20]}...")
    msg_enviada = await bot.send_message(chat_destino, texto)
    
    registrar_lixeira(msg_enviada.message_id, chat_destino)

    agora_tz = datetime.now(fuso_horario)
    hoje_str = agora_tz.strftime("%Y-%m-%d")
    dados_rot_atualizados = ler_config_rotina()
    
    recalcular_fila = False
    hora_exata_disparo = agora_tz.strftime("%H:%M")
    
    if tipo == "bom_dia":
        dados_rot_atualizados["ultimo_bom_dia"] = hoje_str
        dados_rot_atualizados["hora_ultimo_bom_dia"] = hora_exata_disparo
        # Desativa o recálculo forçado para preservar a grade da madrugada
        recalcular_fila = False 
        if EXIBIR_LOGS: logger.info("🛠️ Correção aplicada: Gatilho de recálculo da fila neutralizado no 'Bom Dia'.")
        if EXIBIR_LOGS: logger.info(f"✅ Bandeira de 'Bom Dia' registada às {hora_exata_disparo}. Fila de vídeos liberada para hoje.")
    elif tipo == "boa_noite":
        dados_rot_atualizados["ultimo_boa_noite"] = hoje_str
        dados_rot_atualizados["hora_ultimo_boa_noite"] = hora_exata_disparo
        # Desativa o recálculo forçado no Boa Noite para manter a integridade da agenda
        recalcular_fila = False 
        if EXIBIR_LOGS: logger.info("🛠️ Correção aplicada: Gatilho de recálculo da fila neutralizado no 'Boa Noite'.")
        if EXIBIR_LOGS: logger.info(f"✅ Bandeira de 'Boa Noite' registada às {hora_exata_disparo}. Fila de vídeos suspensa até amanhã.")
        
    # Registra o disparo no histórico diário para evitar sobrecarga em caso de reinício do servidor
    hoje_historico = agora_tz.strftime("%Y-%m-%d")
    if dados_rot_atualizados.get("historico_diario", {}).get("data") != hoje_historico:
        dados_rot_atualizados["historico_diario"] = {"data": hoje_historico, "contagem": {}}
    
    # ✅ NOVO: Armazena o horário exato em lista em vez de apenas contar os disparos
    historico_tipo = dados_rot_atualizados["historico_diario"]["contagem"].get(tipo, [])
    if isinstance(historico_tipo, int):
        historico_tipo = [] # Proteção de retrocompatibilidade para limpar registros antigos de números
        
    historico_tipo.append(hora_exata_disparo)
    dados_rot_atualizados["historico_diario"]["contagem"][tipo] = historico_tipo
    salvar_config_rotina(dados_rot_atualizados)
    
    if EXIBIR_LOGS: 
        qtd_disparos = len(historico_tipo)
        horarios_str = ", ".join(historico_tipo)
        logger.info(f"📊 Auditoria de Rotina | {tipo.upper()}: {qtd_disparos}º envio diário efetuado. Horários de hoje: [{horarios_str}]")

    # Recalcula a distribuição orgânica dos vídeos se a fronteira do dia sofreu alteração forçada
    if recalcular_fila:
        if EXIBIR_LOGS: logger.info("🔄 Alteração de fronteira detetada. A recalcular toda a fila de postagens em tempo real...")
        agendar_fila_postagens()
    
    if tipo == "link_grupo":
        link_separado = f"👇 <b>Link de Convite:</b>\n{LINK_GRUPO}"
        if EXIBIR_LOGS: logger.info("🔗 Enviando link do grupo em mensagem isolada.")
        msg_link = await bot.send_message(GRUPO_ID, link_separado, parse_mode="HTML")
        registrar_lixeira(msg_link.message_id, GRUPO_ID)
    elif tipo == "link_grupo_viral":
        link_separado = f"👇 <b>Link de Convite:</b>\n{LINK_GRUPO_VIRAL}"
        if EXIBIR_LOGS: logger.info("🔗 Enviando link do grupo viral em mensagem isolada.")
        msg_link = await bot.send_message(GRUPO_VIRAL_ID, link_separado, parse_mode="HTML")
        registrar_lixeira(msg_link.message_id, GRUPO_VIRAL_ID)
    elif tipo in ["divulgar_gem", "divulgar_gem_viral"]:
        link_gem = "👇 <b>Acesse o Prompt Automatizado:</b>\nhttps://gemini.google.com/gem/1HtJMuknyMZ76utOu-i6c_xvc3vmQx7bT?usp=sharing"
        if EXIBIR_LOGS: logger.info("🤖 Enviando link do GEM em mensagem isolada.")
        msg_gem = await bot.send_message(chat_destino, link_gem, parse_mode="HTML")
        registrar_lixeira(msg_gem.message_id, chat_destino)
    elif tipo == "promo_viral":
        link_viral = f"👇 <b>Acesse o Canal Parceiro:</b>\n{LINK_GRUPO_VIRAL}"
        if EXIBIR_LOGS: logger.info("🔗 Enviando link do Acervo Viral.")
        msg_viral = await bot.send_message(GRUPO_ID, link_viral, parse_mode="HTML")
        registrar_lixeira(msg_viral.message_id, GRUPO_ID)
    elif tipo == "promo_principal":
        link_princ = f"👇 <b>Acesse o Canal Parceiro:</b>\n{LINK_GRUPO}"
        if EXIBIR_LOGS: logger.info("🔗 Enviando link do Acervo Afiliados.")
        msg_princ = await bot.send_message(GRUPO_VIRAL_ID, link_princ, parse_mode="HTML")
        registrar_lixeira(msg_princ.message_id, GRUPO_VIRAL_ID)   

def ler_config_rotina():
    if EXIBIR_LOGS: logger.info("📂 Lendo configurações de rotina...")
    try:
        with open("config_rotina.json", "r") as f:
            dados = json.load(f)
            # Adiciona chaves padrão se não existirem (retrocompatibilidade)
            if "link_grupo" not in dados: dados["link_grupo"] = {"inicio": 9, "fim": 21, "frequencia": 3}
            if "divulgar_gem" not in dados: dados["divulgar_gem"] = {"inicio": 8, "fim": 22, "frequencia": 1}
            if "promo_viral" not in dados: dados["promo_viral"] = {"inicio": 10, "fim": 20, "frequencia": 1}
            if "promo_principal" not in dados: dados["promo_principal"] = {"inicio": 10, "fim": 20, "frequencia": 1}
            if "divulgar_gem_viral" not in dados: dados["divulgar_gem_viral"] = {"inicio": 8, "fim": 22, "frequencia": 1}
            if "pausado" not in dados: dados["pausado"] = False
            if "pausado_viral" not in dados: dados["pausado_viral"] = False
            if "historico_diario" not in dados: dados["historico_diario"] = {"data": "", "contagem": {}}
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
            "promo_viral": {"inicio": 10, "fim": 20, "frequencia": 1},
            "promo_principal": {"inicio": 10, "fim": 20, "frequencia": 1},
            "divulgar_gem_viral": {"inicio": 8, "fim": 22, "frequencia": 1},
            "pausado": False,
            "pausado_viral": False,
            "historico_diario": {"data": "", "contagem": {}}
        }

def salvar_config_rotina(dados):
    with open("config_rotina.json", "w") as f:
        json.dump(dados, f, indent=4)

def agendar_tarefas_diarias():
    if EXIBIR_LOGS: logger.info("🔄 Reestruturando a grade: Sorteando horários com inteligência de lacunas (Gap-Filling)...")
    
    agora_faxina = datetime.now(fuso_horario)
    hoje_faxina_str = agora_faxina.strftime("%Y-%m-%d")
    
    # --- Limpeza de Madrugada: Remove vídeos já postados em dias anteriores ---
    fila_data = ler_fila_postagens()
    fila_original = fila_data.get("fila", [])
    fila_limpa = []
    
    for x in fila_original:
        if not x.get("postado"):
            fila_limpa.append(x) # Vídeo pendente, continua na fila
        elif x.get("data_postagem") == hoje_faxina_str:
            fila_limpa.append(x) # Vídeo postado HOJE, mantido para o histórico visual do painel
        else:
            # Vídeo antigo (ou de versão anterior do bot), vai para a lixeira
            caminho_vid = x.get("caminho_video")
            if caminho_vid and os.path.exists(caminho_vid):
                ainda_usado = any(v.get("caminho_video") == caminho_vid and not v.get("postado") for v in fila_original)
                if not ainda_usado:
                    try:
                        os.remove(caminho_vid)
                        if EXIBIR_LOGS: logger.info(f"🧹 Ficheiro {caminho_vid} excluído na limpeza de madrugada.")
                    except:
                        pass
                        
    if len(fila_original) != len(fila_limpa):
        fila_data["fila"] = fila_limpa
        salvar_fila_postagens(fila_data)
        if EXIBIR_LOGS: logger.info(f"🧹 Limpeza da fila: {len(fila_original) - len(fila_limpa)} vídeos de dias anteriores foram eliminados.")
    # -------------------------------------------------------------------------
    
    for job in scheduler.get_jobs():
        if job.id.startswith('job_rotina_') or job.id.startswith('job_campanha_'):
            job.remove()
            if EXIBIR_LOGS: logger.info(f"🧹 Agendamento antigo apagado da memória: {job.id}")

    dados_rotina = ler_config_rotina()
    agora = datetime.now(fuso_horario)
    hoje_str = agora.strftime("%Y-%m-%d")
    
    # 1. ABERTURA E FECHAMENTO RÍGIDOS (Cadeados do Expediente)
    for tipo in ["bom_dia", "boa_noite"]:
        if tipo not in dados_rotina or type(dados_rotina[tipo]) is not dict:
            continue
            
        ultimo_disparo = dados_rotina.get(f"ultimo_{tipo}", "")
        if ultimo_disparo == hoje_str:
            if EXIBIR_LOGS: logger.info(f"⏭️ {tipo.replace('_', ' ').title()} já disparado hoje. Pulando agendamento inicial.")
            continue
            
        config = dados_rotina[tipo]
        inicio = config.get("inicio", 6 if tipo == "bom_dia" else 21)
        fim = config.get("fim", 9 if tipo == "bom_dia" else 23)
        limite_superior = fim - 1 if fim > inicio else fim
        
        min_inicio_busca = inicio * 60
        min_fim_busca = limite_superior * 60 + 59
        
        minuto_absoluto = random.randint(min_inicio_busca, min_fim_busca)
        hora_sorteada = minuto_absoluto // 60
        min_sorteado = minuto_absoluto % 60
        
        horario_candidato = agora.replace(hour=hora_sorteada, minute=min_sorteado, second=0, microsecond=0)
        
        if horario_candidato <= agora:
            horario_candidato = agora + timedelta(minutes=5)
            hora_sorteada, min_sorteado = horario_candidato.hour, horario_candidato.minute
            
        job_id = f"job_rotina_{tipo}_0"
        scheduler.add_job(disparar_mensagem, 'cron', hour=hora_sorteada, minute=min_sorteado, timezone=FUSO_STR, args=[tipo], id=job_id, replace_existing=True)
        if EXIBIR_LOGS: logger.info(f"🔒 Fronteira {tipo.upper()} cravada às {hora_sorteada:02d}:{min_sorteado:02d}.")

    # 2. DISTRIBUIÇÃO DOS VÍDEOS (Espinha Dorsal)
    agendar_fila_postagens()
    
    # 3. MAPEAMENTO DAS LACUNAS DE TEMPO
    eventos_fixos = []
    for job in scheduler.get_jobs():
        if job.id.startswith('job_rotina_bom_dia') or job.id.startswith('job_rotina_boa_noite') or job.id.startswith('job_fila_postagem_'):
            if getattr(job, 'next_run_time', None):
                tempo_evento = job.next_run_time.astimezone(fuso_horario)
                if tempo_evento.date() == agora.date():
                    eventos_fixos.append(tempo_evento)
                    
   # 🚧 TRAVA DA PORTA DE ENTRADA (Abre a Loja no Bom Dia)
    ultimo_bd = dados_rotina.get("ultimo_bom_dia", "")
    job_bd = scheduler.get_job('job_rotina_bom_dia_0')
    
    if ultimo_bd == hoje_str:
        fronteira_inicial = agora
    elif job_bd and getattr(job_bd, 'next_run_time', None):
        fronteira_inicial = job_bd.next_run_time.astimezone(fuso_horario)
    else:
        hora_inicio_bd = dados_rotina.get("bom_dia", {}).get("inicio", 6)
        fronteira_inicial = max(agora, agora.replace(hour=hora_inicio_bd, minute=0, second=0, microsecond=0))
        
    eventos_fixos.append(fronteira_inicial)
    
    # 🚧 TRAVA DA PORTA DE SAÍDA (Cadeado no Boa Noite)
    ultimo_bn = dados_rotina.get("ultimo_boa_noite", "")
    job_bn = scheduler.get_job('job_rotina_boa_noite_0')
    
    if ultimo_bn == hoje_str:
        fronteira_final = agora # A loja já fechou
    elif job_bn and getattr(job_bn, 'next_run_time', None):
        fronteira_final = job_bn.next_run_time.astimezone(fuso_horario)
    else:
        hora_fim_bn = dados_rotina.get("boa_noite", {}).get("fim", 23)
        fronteira_final = agora.replace(hour=max(0, hora_fim_bn - 1), minute=59, second=59, microsecond=0)
        
    eventos_fixos.append(fronteira_final)
    
    eventos_fixos.sort()
    
    def encontrar_maior_lacuna_e_inserir(duracao_minima=15):
        maior_gap = timedelta(0)
        ponto_insercao = None
        idx_insercao = -1
        
        for i in range(len(eventos_fixos) - 1):
            gap = eventos_fixos[i+1] - eventos_fixos[i]
            if gap > maior_gap:
                maior_gap = gap
                ponto_insercao = eventos_fixos[i] + (gap / 2)
                idx_insercao = i + 1
                
        if maior_gap.total_seconds() / 60 >= duracao_minima:
            eventos_fixos.insert(idx_insercao, ponto_insercao)
            return ponto_insercao
        return None

    # 4. PREENCHIMENTO DINÂMICO (Intercalação nas maiores lacunas)
    tipos_restantes = [t for t in dados_rotina.keys() if t not in ["bom_dia", "boa_noite", "pausado", "pausado_viral", "ultimo_bom_dia", "ultimo_boa_noite", "historico_diario"]]
    
    # ✅ NOVO: Separação de Trilhas (Principal vs Viral)
    rotinas_virais_lista = ["promo_principal", "link_grupo_viral", "divulgar_gem_viral"]
    rotinas_principais = [t for t in tipos_restantes if t not in rotinas_virais_lista]
    rotinas_virais = [t for t in tipos_restantes if t in rotinas_virais_lista]
    
    hoje_historico = agora.strftime("%Y-%m-%d")
    historico = dados_rotina.get("historico_diario", {})
    if historico.get("data") != hoje_historico:
        contagem_hoje = {}
    else:
        contagem_hoje = historico.get("contagem", {})
        
    def obter_qtd_disparos(tipo_rotina):
        registro = contagem_hoje.get(tipo_rotina, [])
        return len(registro) if isinstance(registro, list) else registro
    
    # 4.1 AGENDAMENTO DA GRADE PRINCIPAL (Rastreando as lacunas reais)
    grupos_tarefas = {}
    for tipo in rotinas_principais:
        config = dados_rotina[tipo]
        if type(config) is dict:
            frequencia_total = config.get("frequencia", 1)
            disparos_ja_feitos = obter_qtd_disparos(tipo)
            frequencia_restante = frequencia_total - disparos_ja_feitos
            
            if frequencia_restante > 0:
                grupos_tarefas[tipo] = [(tipo, i + disparos_ja_feitos) for i in range(frequencia_restante)]
            elif frequencia_total > 0:
                if EXIBIR_LOGS: logger.info(f"✅ Rotina {tipo.upper()} já atingiu a cota diária ({disparos_ja_feitos}/{frequencia_total}). Ignorando reagendamento.")
                
    tarefas_para_distribuir = []
    chaves_grupos = list(grupos_tarefas.keys())
    while chaves_grupos:
        random.shuffle(chaves_grupos)
        chaves_remover = []
        for chave in chaves_grupos:
            if grupos_tarefas[chave]:
                tarefas_para_distribuir.append(grupos_tarefas[chave].pop(0))
            if not grupos_tarefas[chave]:
                chaves_remover.append(chave)
        for chave in chaves_remover:
            chaves_grupos.remove(chave)
            
    ultimo_tipo_agendado = None
    
    for tipo, indice in tarefas_para_distribuir:
        duracao_min_gap = 20
        if tipo == ultimo_tipo_agendado:
            duracao_min_gap = 60
            if EXIBIR_LOGS: logger.info(f"🛡️ Bloqueio de repetição ativado para {tipo.upper()}. Forçando lacuna mínima de 60 minutos.")
            
        horario_ideal = encontrar_maior_lacuna_e_inserir(duracao_minima=duracao_min_gap)
        
        if horario_ideal:
            job_id = f"job_rotina_{tipo}_{indice}"
            scheduler.add_job(disparar_mensagem, 'date', run_date=horario_ideal, args=[tipo], id=job_id, replace_existing=True)
            ultimo_tipo_agendado = tipo
            if EXIBIR_LOGS: logger.info(f"🧩 Lacuna preenchida: {tipo.upper()} [{indice+1}] encaixado exatamente às {horario_ideal.strftime('%H:%M:%S')}.")
        else:
            if EXIBIR_LOGS: logger.warning(f"⚠️ Grade superlotada! Acionando fallback forçado para {tipo.upper()} [{indice+1}].")
            minutos_offset = random.randint(30, 90) if tipo == ultimo_tipo_agendado else random.randint(15, 60)
            horario_fallback = agora + timedelta(minutes=minutos_offset)
            
            # 🚧 Impede que o desvio fure a porta de entrada (Bom Dia)
            if horario_fallback <= fronteira_inicial:
                horario_fallback = fronteira_inicial + timedelta(minutes=random.randint(15, 45))
                
            # 🚧 Impede que o desvio force a porta de saída (Boa Noite)
            if horario_fallback >= fronteira_final:
                horario_fallback = fronteira_final - timedelta(minutes=random.randint(5, 30))
                if horario_fallback <= agora: horario_fallback = agora + timedelta(minutes=2)
                
            job_id = f"job_rotina_{tipo}_{indice}"
            scheduler.add_job(disparar_mensagem, 'date', run_date=horario_fallback, args=[tipo], id=job_id, replace_existing=True)
            ultimo_tipo_agendado = tipo

    # 4.5. AGENDAMENTO PARALELO PARA O CANAL VIRAL (Sem roubar espaço da grade principal)
    grupos_virais = {}
    for tipo in rotinas_virais:
        config = dados_rotina[tipo]
        if type(config) is dict:
            frequencia_total = config.get("frequencia", 1)
            disparos_ja_feitos = obter_qtd_disparos(tipo)
            frequencia_restante = frequencia_total - disparos_ja_feitos
            
            if frequencia_restante > 0:
                grupos_virais[tipo] = [(tipo, i + disparos_ja_feitos, config) for i in range(frequencia_restante)]
            elif frequencia_total > 0:
                if EXIBIR_LOGS: logger.info(f"✅ Rotina VIRAL {tipo.upper()} já atingiu a cota diária.")
                
    tarefas_virais = []
    chaves_virais = list(grupos_virais.keys())
    while chaves_virais:
        random.shuffle(chaves_virais)
        chaves_remover = []
        for chave in chaves_virais:
            if grupos_virais[chave]:
                tarefas_virais.append(grupos_virais[chave].pop(0))
            if not grupos_virais[chave]:
                chaves_remover.append(chave)
        for chave in chaves_remover:
            chaves_virais.remove(chave)
            
    ultimo_tipo_viral = None
                
    for tipo, indice, config in tarefas_virais:
        inicio = config.get("inicio", 8)
        fim = config.get("fim", 22)
        
        min_inicio_busca = inicio * 60
        min_fim_busca = fim * 60 + 59
        
        minuto_absoluto = random.randint(min_inicio_busca, min_fim_busca)
        hora_sorteada = minuto_absoluto // 60
        min_sorteado = minuto_absoluto % 60
        
        horario_candidato = agora.replace(hour=hora_sorteada, minute=min_sorteado, second=0, microsecond=0)
        
        if tipo == ultimo_tipo_viral:
            horario_candidato += timedelta(minutes=random.randint(60, 120))
            if EXIBIR_LOGS: logger.info(f"🛡️ Bloqueio de repetição ativado para VIRAL {tipo.upper()}. Empurrando agendamento para a frente.")
            
        # 🚧 Impede que qualquer rotina paralela fure a fila do Bom Dia
        if horario_candidato <= fronteira_inicial:
            horario_candidato = fronteira_inicial + timedelta(minutes=random.randint(5, 60))
            
        # 🚧 Impede que qualquer rotina paralela force o cadeado do Boa Noite
        if horario_candidato >= fronteira_final:
            horario_candidato = fronteira_final - timedelta(minutes=random.randint(5, 60))
            
        # Se após os empurrões a hora ficar colada no passado, joga alguns minutos para a frente
        if horario_candidato <= agora:
            horario_candidato = agora + timedelta(minutes=random.randint(2, 10))
            
        # ✅ NOVA TRAVA ANTI-COLISÃO ISOLADA (Evita choque visual apenas dentro do próprio Mundo Viral - margem de 2 min)
        conflito_geral = False
        for job_existente in scheduler.get_jobs():
            if getattr(job_existente, 'next_run_time', None) and any(rv in job_existente.id for rv in rotinas_virais_lista):
                tempo_existente = job_existente.next_run_time.astimezone(fuso_horario)
                if abs((horario_candidato - tempo_existente).total_seconds()) < 120:
                    conflito_geral = True
                    break
                    
        if conflito_geral:
            horario_candidato += timedelta(minutes=random.randint(3, 8))
            
        job_id = f"job_rotina_{tipo}_{indice}"
        scheduler.add_job(disparar_mensagem, 'date', run_date=horario_candidato, args=[tipo], id=job_id, replace_existing=True)
        ultimo_tipo_viral = tipo
        if EXIBIR_LOGS: logger.info(f"🦠 Agendamento VIRAL Paralelo: {tipo.upper()} [{indice+1}] marcado para {horario_candidato.strftime('%H:%M:%S')} (Grade Livre).")

    # 5. AGENDAMENTO DAS CAMPANHAS ESPECIAIS
    for i in range(4):
        data_futura = agora + timedelta(days=i)
        if data_futura.day == data_futura.month:
            if EXIBIR_LOGS: logger.info(f"🎉 Mega Campanha {data_futura.day:02d}.{data_futura.month:02d} rastreada! Faltam {i} dias.")
            tipo_alerta = f"campanha_{i}_{data_futura.day:02d}.{data_futura.month:02d}"
            
            for p in ["manha", "tarde", "noite"]:
                horario_campanha = encontrar_maior_lacuna_e_inserir(duracao_minima=10)
                if not horario_campanha:
                    if p == "manha": horario_campanha = agora.replace(hour=random.randint(8,11), minute=random.randint(0,59))
                    elif p == "tarde": horario_campanha = agora.replace(hour=random.randint(14,17), minute=random.randint(0,59))
                    else: horario_campanha = agora.replace(hour=random.randint(18,21), minute=random.randint(0,59))
                    
                scheduler.add_job(disparar_mensagem, 'date', run_date=horario_campanha, args=[tipo_alerta], id=f'job_campanha_{p}', replace_existing=True)
                if EXIBIR_LOGS: logger.info(f"⏳ Alerta Campanha {p.title()} encaixado às: {horario_campanha.strftime('%H:%M:%S')}")
            break

# --- SISTEMA DE SESSÃO E INATIVIDADE ---
from aiogram import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable
from aiogram.fsm.storage.base import StorageKey

async def resetar_sessao_inatividade(chat_id: int, user_id: int, thread_id: int = None):
    # 1. Recupera o estado de navegação atual do utilizador de forma remota
    state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=user_id, thread_id=thread_id))
    estado_atual = await state.get_state()
    data = await state.get_data()
    
    # Trava de inteligência: Se já estiver na raiz (estado vazio E flag confirmada), a função morre silenciosamente
    if not estado_atual and data.get("painel_atual") == "raiz":
        return
        
    if EXIBIR_LOGS: logger.info(f"⏳ Cronômetro de inatividade zerou (Tarefa pendente: {estado_atual}). Limpando memória FSM e atualizando a interface minimalista.")
    await state.clear()
    await state.update_data(painel_atual="raiz")
    
    # 2. Notifica o encerramento, aguarda renderização e limpa o chat
    try:
        if EXIBIR_LOGS: logger.info("✅ Restaurando o menu principal por inatividade e efetuando limpeza...")
        
        # Passo A: Envia o aviso temporário SEM botões
        msg_aviso = await bot.send_message(chat_id, "⏳ Sessão expirada por inatividade. Limpando tela...")
        await asyncio.sleep(1.5)
        await bot.delete_message(chat_id=chat_id, message_id=msg_aviso.message_id)
        
        # Passo B: Envia a mensagem âncora definitiva COM os botões do menu raiz
        await bot.send_message(chat_id, "🏠 Painel Inicial restaurado.", reply_markup=obter_teclado_raiz())
        
        if EXIBIR_LOGS: logger.info("🧹 Mensagem temporária apagada e botões restaurados com sucesso.")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao atualizar o teclado e limpar chat: {e}")

class InatividadeMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[types.Message, Dict[str, Any]], Awaitable[Any]],
        event: types.Message,
        data: Dict[str, Any]
    ) -> Any:
        # O filtro garante que o cronómetro só é aplicado a si (Administrador)
        if event.from_user and event.from_user.id == ADMIN_ID:
            job_id = f"job_inatividade_{event.from_user.id}"
            
            # 1. Inicia uma nova contagem limpa de 15 minutos
            from datetime import datetime, timedelta
            novo_limite = datetime.now(fuso_horario) + timedelta(minutes=15)
            
            # Captura o thread_id para manter a compatibilidade da chave de memória
            thread_id = getattr(event, 'message_thread_id', None)
            if EXIBIR_LOGS: logger.info(f"⏰ Registrando nova contagem de inatividade. Thread ID: {thread_id}")
            
            # 2. Adiciona ou sobrepõe o cronômetro antigo de forma limpa e unificada
            scheduler.add_job(
                resetar_sessao_inatividade, 
                'date', 
                run_date=novo_limite, 
                args=[event.chat.id, event.from_user.id, thread_id], 
                id=job_id,
                replace_existing=True
            )
            
        return await handler(event, data)

# Acopla o interceptador de inatividade ao núcleo do robô para vigiar todas as mensagens
dp.message.middleware(InatividadeMiddleware())

# 5. HANDLERS DE COMANDO E INTERAÇÃO
@dp.message(Command("start"), StateFilter("*"))
async def comando_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await state.update_data(painel_atual="raiz")
    if EXIBIR_LOGS: logger.info("⌨️ Iniciando o bot no Menu Raiz.")
    await message.answer("🏠 Painel de Controle Inicial. Escolha uma área para gerenciar:", reply_markup=obter_teclado_raiz())

@dp.message(F.text == "Canal Afiliados 📺", StateFilter("*"))
async def menu_canal_principal(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    if EXIBIR_LOGS: logger.info("📂 Acessando a pasta do Canal Afiliados.")
    await message.answer("📺 <b>Menu do Canal Afiliados</b>\nGerencie as postagens e rotinas abaixo:", reply_markup=obter_teclado_principal(), parse_mode="HTML")

async def buscar_dados_financeiros_shopee(dias_retroativos=30):
    if not SHOPEE_APP_ID or not SHOPEE_APP_SECRET:
        if EXIBIR_LOGS: logger.warning("⏳ [API Shopee] Chaves financeiras ausentes no .env.")
        return None
        
    from datetime import timedelta
    agora = datetime.now(fuso_horario)
    inicio = agora - timedelta(days=dias_retroativos)
    
    # 1. Geração correta dos Timestamps UNIX para GraphQL
    start_ts = int(inicio.replace(hour=0, minute=0, second=0).timestamp())
    end_ts = int(agora.replace(hour=23, minute=59, second=59).timestamp())
    
    endpoint = "https://open-api.affiliate.shopee.com.br/graphql"
    
    # 2. Formatação rigorosa da Query (Documentação Oficial Shopee)
    payload = {
        "query": """query getConversionReport($purchaseTimeStart: Int64!, $purchaseTimeEnd: Int64!, $limit: Int!) {
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
            "purchaseTimeStart": str(start_ts),
            "purchaseTimeEnd": str(end_ts),
            "limit": 500
        }
    }
    
    # 3. Compactação JSON exata (A Shopee recusa espaços em branco)
    payload_json = json.dumps(payload, separators=(',', ':'))
    timestamp = int(time.time())
    
    # 4. Assinatura de Segurança HMAC SHA256
    fator_base = f"{SHOPEE_APP_ID}{timestamp}{payload_json}{SHOPEE_APP_SECRET}"
    assinatura = hashlib.sha256(fator_base.encode('utf-8')).hexdigest()
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={SHOPEE_APP_ID}, Timestamp={timestamp}, Signature={assinatura}"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, data=payload_json) as response:
                
                dados_crus = await response.text()
                if EXIBIR_LOGS: logger.info(f"🔍 [API Shopee - Auditoria] {dados_crus}")
                
                if response.status == 200:
                    dados = json.loads(dados_crus)
                    
                    # 5. Validação da devolução de dados e tratamento de erro oficial Shopee
                    erros_shopee = dados.get("errors")
                    if erros_shopee:
                        mensagem_erro = erros_shopee[0].get("message", "Erro Desconhecido")
                        if EXIBIR_LOGS: logger.error(f"❌ A Shopee recusou a consulta: {mensagem_erro}")
                        return []
                        
                    return dados.get("data", {}).get("conversionReport", {}).get("nodes", [])
                else:
                    if EXIBIR_LOGS: logger.error(f"❌ Erro de Conexão {response.status}: {dados_crus}")
                    
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro crítico no motor financeiro: {e}")
    return []

def obter_teclado_relatorios():
    botoes = [
        [KeyboardButton(text="Relatório Financeiro 💰"), KeyboardButton(text="Diagnóstico de IA 🧠")],
        [KeyboardButton(text="Voltar ao Início 🔙")]
    ]
    return ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)

@dp.message(F.text == "Relatório Geral 📊", StateFilter("*"))
async def menu_relatorio_geral(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await message.answer("📊 <b>Central de Relatórios</b>\nEscolha qual métrica deseja analisar:", reply_markup=obter_teclado_relatorios(), parse_mode="HTML")

def ler_historico_financeiro():
    try:
        with open("historico_financeiro.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def salvar_historico_financeiro(dados):
    with open("historico_financeiro.json", "w") as f:
        json.dump(dados, f, indent=4)

@dp.message(F.text == "Relatório Financeiro 💰", StateFilter("*"))
async def gerar_relatorio_financeiro(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    msg_status = await message.answer("💰 Sincronizando API Financeira com a Shopee e processando relatório... Aguarde ⏳")
    if EXIBIR_LOGS: logger.info("🚀 Iniciando extração profunda e atualização estrutural do banco de dados...")
    
    conversoes = await buscar_dados_financeiros_shopee(30)
    
    total_pedidos = len(conversoes) if conversoes else 0
    pagos, pendentes, cancelados = 0, 0, 0
    hoje = datetime.now(fuso_horario)
    
    diario_api = {}
    
    if conversoes:
        for conv in conversoes:
            orders = conv.get("orders", [])
            if not orders: continue

            c_shopee = float(conv.get("shopeeCommissionCapped", "0"))
            c_extra = float(conv.get("sellerCommission", "0"))
            c_total = float(conv.get("totalCommission", "0"))
            dt_obj = datetime.fromtimestamp(conv.get("purchaseTime", 0), tz=fuso_horario)
            dt_db_str = dt_obj.strftime("%Y-%m-%d")
            
            if dt_db_str not in diario_api:
                diario_api[dt_db_str] = {"aprovado": 0.0, "pendente": 0.0, "cancelado": 0.0, "shopee": 0.0, "vendedor": 0.0, "qtd_aprovado": 0, "qtd_pendente": 0, "qtd_cancelado": 0, "clicks": 0}
            
            if EXIBIR_LOGS: logger.info("🧮 Analisando transação e desmembrando carrinho misto...")
            qtd_itens = len(orders)
            c_total_frac = c_total / qtd_itens
            c_shopee_frac = c_shopee / qtd_itens
            c_extra_frac = c_extra / qtd_itens

            for order in orders:
                status = order.get("orderStatus", "").upper()
                if status == "COMPLETED":
                    pagos += 1
                    diario_api[dt_db_str]["aprovado"] += c_total_frac
                    diario_api[dt_db_str]["shopee"] += c_shopee_frac
                    diario_api[dt_db_str]["vendedor"] += c_extra_frac
                    diario_api[dt_db_str]["qtd_aprovado"] += 1
                elif status == "PENDING":
                    pendentes += 1
                    diario_api[dt_db_str]["pendente"] += c_total_frac
                    diario_api[dt_db_str]["qtd_pendente"] += 1
                else:
                    cancelados += 1
                    diario_api[dt_db_str]["cancelado"] += c_total_frac
                    diario_api[dt_db_str]["qtd_cancelado"] += 1
    
    taxa_conversao = (pagos / total_pedidos * 100) if total_pedidos > 0 else 0.0
    
    if EXIBIR_LOGS: logger.info("💾 Atualizando o banco de dados histórico local...")
    historico = ler_historico_financeiro()
    historico_limpo = {}
    
    for k, v in historico.items():
        try:
            if isinstance(v, float) or isinstance(v, int):
                historico_limpo[k] = {"aprovado": float(v), "pendente": 0.0, "cancelado": 0.0, "shopee": 0.0, "vendedor": 0.0, "qtd_aprovado": 0, "qtd_pendente": 0, "qtd_cancelado": 0, "clicks": 0}
            else:
                v.setdefault("qtd_aprovado", 0)
                v.setdefault("qtd_pendente", 0)
                v.setdefault("qtd_cancelado", 0)
                v.setdefault("cancelado", 0.0)
                v.setdefault("clicks", 0)
                historico_limpo[k] = v
        except ValueError:
            pass 
                
    ontem_str = (hoje - timedelta(days=1)).strftime("%Y-%m-%d")
    
    for i in range(30):
        d_str = (hoje - timedelta(days=i)).strftime("%Y-%m-%d")
        v_api = diario_api.get(d_str, {"aprovado": 0.0, "pendente": 0.0, "cancelado": 0.0, "shopee": 0.0, "vendedor": 0.0, "qtd_aprovado": 0, "qtd_pendente": 0, "qtd_cancelado": 0, "clicks": 0})
        v_antigo = historico_limpo.get(d_str, {"clicks": 0, "cancelado": 0.0, "qtd_cancelado": 0})
        
        v_api["clicks"] = v_antigo.get("clicks", 0)
        
        v_total_api = v_api["aprovado"] + v_api["pendente"]
        
        if v_total_api > 0 or v_api["clicks"] > 0 or v_api["cancelado"] > 0:
            historico_limpo[d_str] = v_api
        else:
            if d_str == hoje.strftime("%Y-%m-%d") or d_str == ontem_str:
                pass 
            elif d_str not in historico_limpo:
                historico_limpo[d_str] = {"aprovado": 0.0, "pendente": 0.0, "cancelado": 0.0, "shopee": 0.0, "vendedor": 0.0, "qtd_aprovado": 0, "qtd_pendente": 0, "qtd_cancelado": 0, "clicks": 0}
                
    salvar_historico_financeiro(historico_limpo)
    
    MESES_PT = {
        "01": "Janeiro", "02": "Fevereiro", "03": "Março", "04": "Abril",
        "05": "Maio", "06": "Junho", "07": "Julho", "08": "Agosto",
        "09": "Setembro", "10": "Outubro", "11": "Novembro", "12": "Dezembro"
    }
    MESES_ABREV_PT = {
        "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
        "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
        "09": "Set", "10": "Out", "11": "Nov", "12": "Dez"
    }
        
    mes_atual_str = hoje.strftime("%Y-%m")
    aprovado_mes = sum(v["aprovado"] for k, v in historico_limpo.items() if k.startswith(mes_atual_str))
    pendente_mes = sum(v["pendente"] for k, v in historico_limpo.items() if k.startswith(mes_atual_str))
    shopee_mes = sum(v["shopee"] for k, v in historico_limpo.items() if k.startswith(mes_atual_str))
    vendedor_mes = sum(v["vendedor"] for k, v in historico_limpo.items() if k.startswith(mes_atual_str))
    
    qtd_aprovado_mes = sum(v.get("qtd_aprovado", 0) for k, v in historico_limpo.items() if k.startswith(mes_atual_str))
    qtd_pendente_mes = sum(v.get("qtd_pendente", 0) for k, v in historico_limpo.items() if k.startswith(mes_atual_str))
    clicks_mes = sum(v.get("clicks", 0) for k, v in historico_limpo.items() if k.startswith(mes_atual_str))
    total_mes = aprovado_mes + pendente_mes
    
    # Agrupamento Mensal e Anual
    dados_por_mes = {}
    dados_por_ano = {}
    
    for data_str, dados_dia in historico_limpo.items():
        mes_key = data_str[:7]
        ano_key = data_str[:4]
        
        if mes_key not in dados_por_mes:
            dados_por_mes[mes_key] = {"aprovado": 0.0, "pendente": 0.0, "cancelado": 0.0, "qtd_aprovado": 0, "qtd_pendente": 0, "qtd_cancelado": 0, "clicks": 0}
        if ano_key not in dados_por_ano:
            dados_por_ano[ano_key] = {"aprovado": 0.0, "pendente": 0.0, "cancelado": 0.0, "qtd_aprovado": 0, "qtd_pendente": 0, "qtd_cancelado": 0, "clicks": 0}
            
        for k in ["aprovado", "pendente", "cancelado", "qtd_aprovado", "qtd_pendente", "qtd_cancelado", "clicks"]:
            dados_por_mes[mes_key][k] += dados_dia.get(k, 0)
            dados_por_ano[ano_key][k] += dados_dia.get(k, 0)
    
    def f_br(valor): return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    nome_mes_extenso = MESES_PT.get(hoje.strftime('%m'), "Atual").upper()
    
    texto = (
        f"📅 <b>BALANÇO DO MÊS DE {nome_mes_extenso}</b>\n\n"
        f"• Comissão Aprovada: <b>R$ {f_br(aprovado_mes)}</b> <i>({qtd_aprovado_mes} pedidos)</i>\n"
        f"  └ <i>Shopee: R$ {f_br(shopee_mes)} | Vendedor: R$ {f_br(vendedor_mes)}</i>\n"
        f"• Comissão Pendente: <b>R$ {f_br(pendente_mes)}</b> <i>({qtd_pendente_mes} pedidos)</i>\n"
        f"• Total do Mês: <b>R$ {f_br(total_mes)}</b>\n"
        f"• Clicks do Mês: <b>{clicks_mes}</b>\n\n"
    )
    
    texto += "🗓️ <b>HISTÓRICO MENSAL E CRESCIMENTO</b>\n"
    meses_ordenados_desc = sorted(dados_por_mes.keys(), reverse=True)
    
    for i, mes in enumerate(meses_ordenados_desc):
        dados_m = dados_por_mes[mes]
        total_m = dados_m["aprovado"] + dados_m["pendente"]
        
        try:
            ano_str, mes_str = mes.split('-')
            mes_fmt = f"{MESES_PT.get(mes_str, mes_str)}/{ano_str[2:]}"
        except:
            mes_fmt = mes

        variacao_texto = ""
        if i < len(meses_ordenados_desc) - 1:
            mes_anterior = meses_ordenados_desc[i+1]
            total_ant = dados_por_mes[mes_anterior]["aprovado"] + dados_por_mes[mes_anterior]["pendente"]
            if total_ant > 0:
                variacao = ((total_m - total_ant) / total_ant) * 100
                sinal = "📈 +" if variacao >= 0 else "📉 "
                variacao_texto = f" <b>({sinal}{variacao:.1f}%)</b>"
            elif total_ant == 0 and total_m > 0:
                variacao_texto = " <b>(📈 +100%)</b>"

        if EXIBIR_LOGS: logger.info(f"🧮 Calculando proporções do mês {mes_fmt}...")
        total_pedidos_m = dados_m['qtd_aprovado'] + dados_m['qtd_pendente'] + dados_m.get('qtd_cancelado', 0)
        pct_aprov_m = (dados_m['qtd_aprovado'] / total_pedidos_m * 100) if total_pedidos_m > 0 else 0.0
        pct_pend_m = (dados_m['qtd_pendente'] / total_pedidos_m * 100) if total_pedidos_m > 0 else 0.0
        pct_canc_m = (dados_m.get('qtd_cancelado', 0) / total_pedidos_m * 100) if total_pedidos_m > 0 else 0.0

        texto += f"• <b>{mes_fmt}</b>: R$ {f_br(total_m)}{variacao_texto}\n"
        texto += f"  ├ Conf: R$ {f_br(dados_m['aprovado'])} ({dados_m['qtd_aprovado']} pedidos - {pct_aprov_m:.1f}%)\n"
        texto += f"  ├ Pend: R$ {f_br(dados_m['pendente'])} ({dados_m['qtd_pendente']} pedidos - {pct_pend_m:.1f}%)\n"
        texto += f"  └ Canc: R$ {f_br(dados_m.get('cancelado', 0.0))} ({dados_m.get('qtd_cancelado', 0)} pedidos - {pct_canc_m:.1f}%)\n\n"

    texto += "🗓️ <b>HISTÓRICO ANUAL E CRESCIMENTO</b>\n"
    anos_ordenados_desc = sorted(dados_por_ano.keys(), reverse=True)
    
    for i, ano in enumerate(anos_ordenados_desc):
        dados_a = dados_por_ano[ano]
        total_a = dados_a["aprovado"] + dados_a["pendente"]
        
        variacao_texto = ""
        if i < len(anos_ordenados_desc) - 1:
            ano_anterior = anos_ordenados_desc[i+1]
            total_ant = dados_por_ano[ano_anterior]["aprovado"] + dados_por_ano[ano_anterior]["pendente"]
            if total_ant > 0:
                variacao = ((total_a - total_ant) / total_ant) * 100
                sinal = "📈 +" if variacao >= 0 else "📉 "
                variacao_texto = f" <b>({sinal}{variacao:.1f}%)</b>"
            elif total_ant == 0 and total_a > 0:
                variacao_texto = " <b>(📈 +100%)</b>"

        if EXIBIR_LOGS: logger.info(f"🧮 Calculando proporções do ano {ano}...")
        total_pedidos_a = dados_a['qtd_aprovado'] + dados_a['qtd_pendente'] + dados_a.get('qtd_cancelado', 0)
        pct_aprov_a = (dados_a['qtd_aprovado'] / total_pedidos_a * 100) if total_pedidos_a > 0 else 0.0
        pct_pend_a = (dados_a['qtd_pendente'] / total_pedidos_a * 100) if total_pedidos_a > 0 else 0.0
        pct_canc_a = (dados_a.get('qtd_cancelado', 0) / total_pedidos_a * 100) if total_pedidos_a > 0 else 0.0

        texto += f"• <b>{ano}</b>: R$ {f_br(total_a)}{variacao_texto}\n"
        texto += f"  ├ Conf: R$ {f_br(dados_a['aprovado'])} ({dados_a['qtd_aprovado']} pedidos - {pct_aprov_a:.1f}%)\n"
        texto += f"  ├ Pend: R$ {f_br(dados_a['pendente'])} ({dados_a['qtd_pendente']} pedidos - {pct_pend_a:.1f}%)\n"
        texto += f"  └ Canc: R$ {f_br(dados_a.get('cancelado', 0.0))} ({dados_a.get('qtd_cancelado', 0)} pedidos - {pct_canc_a:.1f}%)\n\n"

    texto += (
        "📊 <b>MÉTRICAS DA VARREDURA (Últimos 30 Dias)</b>\n"
        f"• Taxa de Conversão: <b>{taxa_conversao:.1f}%</b>\n"
        f"• Pedidos Totais: {pagos} Pagos | {pendentes} Pendentes | {cancelados} Cancel.\n\n"
    )

    todos_totais = {}
    for d, vals in historico_limpo.items():
        if d <= hoje.strftime("%Y-%m-%d"):
            v_tot = vals.get("aprovado", 0.0) + vals.get("pendente", 0.0)
            todos_totais[d] = v_tot
            
    if todos_totais:
        melhor_dia_str = max(todos_totais, key=todos_totais.get)
        pior_dia_str = min(todos_totais, key=todos_totais.get)
        media_global = sum(todos_totais.values()) / len(todos_totais)
        
        melhor_dia_br = datetime.strptime(melhor_dia_str, "%Y-%m-%d").strftime("%d/%m/%Y")
        pior_dia_br = datetime.strptime(pior_dia_str, "%Y-%m-%d").strftime("%d/%m/%Y")
        
        texto += "🏆 <b>RECORDES GLOBAIS (Todo o Histórico)</b>\n"
        texto += f"• 🥇 Melhor Dia: {melhor_dia_br} (<b>R$ {f_br(todos_totais[melhor_dia_str])}</b>)\n"
        texto += f"• 📉 Pior Dia: {pior_dia_br} (<b>R$ {f_br(todos_totais[pior_dia_str])}</b>)\n"
        texto += f"• ⚖️ Média Diária: <b>R$ {f_br(media_global)}</b>\n\n"

    texto += "📈 <b>DESEMPENHO DIÁRIO (Últimos 7 Dias)</b>\n"
    dias_exibicao = [(hoje - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, 8)]
    
    for d_str in dias_exibicao:
        d_br = datetime.strptime(d_str, "%Y-%m-%d").strftime("%d/%m")
        dados_dia = historico_limpo.get(d_str, {"aprovado": 0.0, "pendente": 0.0, "cancelado": 0.0, "qtd_aprovado": 0, "qtd_pendente": 0, "qtd_cancelado": 0})
        v_aprov = dados_dia.get("aprovado", 0.0)
        v_pend = dados_dia.get("pendente", 0.0)
        v_canc = dados_dia.get("cancelado", 0.0)
        q_aprov = dados_dia.get("qtd_aprovado", 0)
        q_pend = dados_dia.get("qtd_pendente", 0)
        q_canc = dados_dia.get("qtd_cancelado", 0)
        v_tot = v_aprov + v_pend
        
        if EXIBIR_LOGS: logger.info(f"🧮 Calculando proporções diárias para {d_br}...")
        total_pedidos_d = q_aprov + q_pend + q_canc
        pct_aprov_d = (q_aprov / total_pedidos_d * 100) if total_pedidos_d > 0 else 0.0
        pct_pend_d = (q_pend / total_pedidos_d * 100) if total_pedidos_d > 0 else 0.0
        pct_canc_d = (q_canc / total_pedidos_d * 100) if total_pedidos_d > 0 else 0.0
        
        texto += f"• <b>{d_br}</b>: R$ {f_br(v_tot)}\n"
        texto += f"  ├ Conf: R$ {f_br(v_aprov)} ({q_aprov} pedidos - {pct_aprov_d:.1f}%)\n"
        texto += f"  ├ Pend: R$ {f_br(v_pend)} ({q_pend} pedidos - {pct_pend_d:.1f}%)\n"
        texto += f"  └ Canc: R$ {f_br(v_canc)} ({q_canc} pedidos - {pct_canc_d:.1f}%)\n\n"

    await msg_status.delete()
    await message.answer(texto, parse_mode="HTML")
        
    try:
        if EXIBIR_LOGS: logger.info("📈 Desenhando gráfico visual estático de 12 meses...")
        
        ano_atual_str = str(hoje.year)
        meses_ano_atual = [f"{ano_atual_str}-{str(m).zfill(2)}" for m in range(1, 13)]
        
        labels_grafico = []
        valores_comissao = []
        valores_clicks = []
        valores_pedidos = []
        
        for m in meses_ano_atual:
            mes_numero = m.split('-')[1]
            labels_grafico.append(MESES_ABREV_PT.get(mes_numero, mes_numero))
                
            if m in dados_por_mes:
                valores_comissao.append(dados_por_mes[m]["aprovado"])
                valores_pedidos.append(dados_por_mes[m].get("qtd_aprovado", 0))
                valores_clicks.append(dados_por_mes[m].get("clicks", 0))
            else:
                valores_comissao.append(0.0)
                valores_pedidos.append(0)
                valores_clicks.append(0)

        if EXIBIR_LOGS: logger.info("📈 Estruturando gráfico exclusivamente para comissões aprovadas.")
        fig, ax1 = plt.subplots(figsize=(8, 5), facecolor='#f4f4f9')
        ax1.set_facecolor('#f4f4f9')
        
        bars = ax1.bar(labels_grafico, valores_comissao, color='#ff6600', edgecolor='black', linewidth=0.5, label='Comissão Aprovada (R$)')
        ax1.set_ylabel('Comissão (R$)', fontsize=10, color='#333333')
        ax1.grid(axis='y', linestyle='--', alpha=0.5)
        
        ax2 = ax1.twinx()
        line1, = ax2.plot(labels_grafico, valores_clicks, color='#0066cc', marker='o', linestyle='-', linewidth=2, label='Clicks')
        line2, = ax2.plot(labels_grafico, valores_pedidos, color='#2ca02c', marker='s', linestyle='--', linewidth=2, label='Pedidos Vendidos')
        ax2.set_ylabel('Quantidade (Clicks / Pedidos)', fontsize=10, color='#333333')
        
        plt.title(f'Evolução de Faturamento e Tráfego ({ano_atual_str})', fontsize=12, fontweight='bold', color='#333333')
        
        for bar in bars:
            yval = bar.get_height()
            if yval > 0:
                ax1.text(bar.get_x() + bar.get_width()/2, yval + (max(valores_comissao)*0.02), f'R${yval:.0f}', ha='center', va='bottom', fontsize=8, fontweight='bold', color='#333333')

        lines_1, labels_1 = ax1.get_legend_handles_labels()
        lines_2, labels_2 = ax2.get_legend_handles_labels()
        ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left', fontsize=9)

        ax1.spines['top'].set_visible(False)
        ax2.spines['top'].set_visible(False)

        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        plt.close()
        
        if EXIBIR_LOGS: logger.info("✅ Imagem do gráfico enviada para o Telegram.")
        await message.answer_photo(photo=types.BufferedInputFile(buf.getvalue(), filename="grafico.png"))
        
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha ao processar e enviar a imagem do gráfico: {e}")

@dp.message(F.text == "Diagnóstico de IA 🧠", StateFilter("*"))
async def gerar_relatorio_ia(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    msg_status = await message.answer("🧠 Iniciando teste de diagnóstico dos motores Gemini... Aguarde ⏳")
    if EXIBIR_LOGS: logger.info("🧠 Iniciando teste visual e sequencial da Cascata Gemini...")
    
    texto_modelos = "🧠 <b>STATUS DA CASCATA DE IA (GEMINI)</b>\n\n"
    
    for i, modelo in enumerate(MODELOS_CASCATA_GEMINI, 1):
        try:
            await msg_status.edit_text(f"🧠 <i>Testando motores IA...</i>\n🔎 Verificando motor ({i}/{len(MODELOS_CASCATA_GEMINI)}): <code>{modelo}</code> ⏳", parse_mode="HTML")
            
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=modelo,
                contents="Responda apenas 'ok'"
            )
            if response and response.text:
                texto_modelos += f"• {i}º <code>{modelo}</code>: 🟢 Online\n"
            else:
                texto_modelos += f"• {i}º <code>{modelo}</code>: 🟡 Resposta Vazia\n"
        except Exception as e:
            erro_str = str(e).lower()
            if "429" in erro_str or "quota" in erro_str or "exhausted" in erro_str:
                texto_modelos += f"• {i}º <code>{modelo}</code>: 🟡 Cota Esgotada (Renova aprox. 04h00)\n"
            elif "404" in erro_str or "not found" in erro_str:
                texto_modelos += f"• {i}º <code>{modelo}</code>: 🔴 Descontinuado\n"
            elif "503" in erro_str or "overloaded" in erro_str:
                texto_modelos += f"• {i}º <code>{modelo}</code>: 🔴 Servidor Indisponível\n"
            else:
                erro_curto = str(e).replace('\n', ' ')[:30]
                texto_modelos += f"• {i}º <code>{modelo}</code>: 🔴 Erro ({erro_curto}...)\n"

    await msg_status.delete()
    await message.answer(texto_modelos, parse_mode="HTML")

# ✅ Handlers para Envio Manual de Mensagens via Botões
@dp.message(F.text == "Disparar Bom Dia ☀️")
async def manual_bom_dia(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    dados_rotina = ler_config_rotina()
    hoje_str = datetime.now(fuso_horario).strftime("%Y-%m-%d")
    
    if dados_rotina.get("ultimo_bom_dia") == hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Clique manual rejeitado: Bom Dia já enviado.")
        await message.answer("⚠️ <b>Bloqueio Anti-Acidente:</b> O 'Bom Dia' de hoje já foi enviado ao grupo. Ação cancelada.", parse_mode="HTML")
        return

    await message.answer("Gerando e enviando mensagem de Bom Dia... ⏳")
    if EXIBIR_LOGS: logger.info("🚀 Comando de disparo manual autorizado para Bom Dia.")
    await disparar_mensagem("bom_dia", forcar=True)
    await message.answer("Mensagem de Bom Dia enviada ao grupo com sucesso! ✅")

@dp.message(F.text == "Disparar Boa Noite 🌙")
async def manual_boa_noite(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    dados_rotina = ler_config_rotina()
    hoje_str = datetime.now(fuso_horario).strftime("%Y-%m-%d")
    
    if dados_rotina.get("ultimo_boa_noite") == hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Clique manual rejeitado: Boa Noite já enviado.")
        await message.answer("⚠️ <b>Bloqueio Anti-Acidente:</b> O 'Boa Noite' de hoje já foi enviado ao grupo. Ação cancelada.", parse_mode="HTML")
        return

    await message.answer("Gerando e enviando mensagem de Boa Noite... ⏳")
    if EXIBIR_LOGS: logger.info("🚀 Comando de disparo manual autorizado para Boa Noite.")
    await disparar_mensagem("boa_noite", forcar=True)
    await message.answer("Mensagem de Boa Noite enviada ao grupo com sucesso! ✅")

@dp.message(F.text == "Disparar Incentivo 🔥")
async def manual_incentivo(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    dados_rotina = ler_config_rotina()
    hoje_str = datetime.now(fuso_horario).strftime("%Y-%m-%d")
    
    # Valida se o dia já começou (Bom Dia) e se ainda não terminou (Boa Noite)
    if dados_rotina.get("ultimo_bom_dia") != hoje_str or dados_rotina.get("ultimo_boa_noite") == hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Clique manual rejeitado: Fora do expediente.")
        await message.answer("⚠️ <b>Ação Bloqueada:</b> Você só pode disparar esta mensagem durante o expediente (após o 'Bom Dia' e antes do 'Boa Noite').", parse_mode="HTML")
        return
        
    await message.answer("Gerando e enviando mensagem de Incentivo... ⏳")
    if EXIBIR_LOGS: logger.info("🚀 Comando de disparo manual autorizado para Incentivo.")
    await disparar_mensagem("incentivo", forcar=True)
    await message.answer("Mensagem de Incentivo enviada ao grupo com sucesso! ✅")

@dp.message(F.text == "Disparar Convite do Grupo 🔗")
async def manual_link_grupo(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    dados_rotina = ler_config_rotina()
    hoje_str = datetime.now(fuso_horario).strftime("%Y-%m-%d")
    
    # Valida se o dia já começou (Bom Dia) e se ainda não terminou (Boa Noite)
    if dados_rotina.get("ultimo_bom_dia") != hoje_str or dados_rotina.get("ultimo_boa_noite") == hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Clique manual rejeitado: Fora do expediente.")
        await message.answer("⚠️ <b>Ação Bloqueada:</b> Você só pode disparar esta mensagem durante o expediente (após o 'Bom Dia' e antes do 'Boa Noite').", parse_mode="HTML")
        return
        
    await message.answer("Gerando e enviando divulgação do grupo... ⏳")
    if EXIBIR_LOGS: logger.info("🚀 Comando de disparo manual autorizado para Convite do Grupo.")
    await disparar_mensagem("link_grupo", forcar=True)
    await message.answer("Mensagem de divulgação enviada ao grupo com sucesso! ✅")

@dp.message(F.text == "Disparar Convite Viral 🚀")
async def manual_promo_viral(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    dados_rotina = ler_config_rotina()
    hoje_str = datetime.now(fuso_horario).strftime("%Y-%m-%d")
    
    if dados_rotina.get("ultimo_bom_dia") != hoje_str or dados_rotina.get("ultimo_boa_noite") == hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Clique manual rejeitado: Fora do expediente.")
        await message.answer("⚠️ <b>Ação Bloqueada:</b> Você só pode disparar esta mensagem durante o expediente.", parse_mode="HTML")
        return
        
    await message.answer("Gerando e enviando divulgação do canal parceiro... ⏳")
    if EXIBIR_LOGS: logger.info("🚀 Comando de disparo manual autorizado para Promo Viral.")
    await disparar_mensagem("promo_viral", forcar=True)
    await message.answer("Mensagem de Promo Viral enviada ao grupo com sucesso! ✅")

# Bloco Modificado
@dp.message(F.text == "Disparar Convite Afiliados 🚀")
async def manual_promo_afiliados(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    # ❌ Bloqueio de expediente removido a pedido do administrador
    await message.answer("Gerando e enviando divulgação do canal de afiliados... ⏳")
    if EXIBIR_LOGS: logger.info("🚀 Comando de disparo manual autorizado para Convite Afiliados.")
    await disparar_mensagem("promo_principal", forcar=True)
    await message.answer("Propaganda do canal de afiliados enviada ao canal viral com sucesso! ✅")

@dp.message(F.text == "Disparar Convite do Grupo 🔗\u200b")
async def manual_convite_viral(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    # ❌ Bloqueio de expediente removido a pedido do administrador
    await message.answer("Gerando e enviando convite do canal viral... ⏳")
    if EXIBIR_LOGS: logger.info("🚀 Comando de disparo manual autorizado para Convite do Grupo Viral.")
    await disparar_mensagem("link_grupo_viral", forcar=True)
    await message.answer("Convite de recrutamento enviado ao canal viral com sucesso! ✅")

# ❌ NOVO: Handler Global para Cancelar via Botão (Agora 100% à prova de falhas)
@dp.message(F.text == "Cancelar ❌", StateFilter("*"))
async def cancelar_fluxo_global(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    estado_atual = await state.get_state()
    if EXIBIR_LOGS: logger.info(f"❌ Ação cancelada via botão. Estado anterior: {estado_atual}")

    data = await state.get_data()

    # 🔁 Roteamento Inteligente: Se estiver no Gerenciador de Fila
    if estado_atual and estado_atual.startswith("GerenciarFilaFluxo"):
        await state.clear()
        await message.answer("Ação cancelada.")
        await menu_gerenciar_fila(message, state)
        return
        
    # 🔁 Roteamento Inteligente: Se estiver no Espião (Grupos Vigiados)
    if estado_atual and estado_atual.startswith("EspiaoFluxo"):
        await state.clear()
        await message.answer("Ação cancelada.")
        await menu_grupos_vigiados(message, state)
        return

    # 🔁 Roteamento Inteligente: Se estiver no SPAM Principal
    if estado_atual and estado_atual.startswith("ConfigDivulgacao:"):
        await state.clear()
        await message.answer("Ação cancelada.")
        await gerenciar_divulgacao(message, state)
        return

    # 🔁 Roteamento Inteligente: Se estiver no SPAM Viral
    if estado_atual and estado_atual.startswith("ConfigDivulgacaoViral"):
        await state.clear()
        await message.answer("Ação cancelada.")
        await gerenciar_divulgacao_viral(message, state)
        return
        
    # 🔁 Roteamento Inteligente: Se estiver nas Rotinas
    if estado_atual and estado_atual.startswith("ConfigRotina"):
        tipo_edicao = data.get('tipo_edicao')
        await state.clear()
        if EXIBIR_LOGS: logger.info("🔙 Cancelando edição de rotina e redirecionando ao menu correto.")
        await message.answer("Ação cancelada.")
        if tipo_edicao in ["promo_principal", "link_grupo_viral", "divulgar_gem_viral"]:
            await gerenciar_rotina_espiao(message, state)
        else:
            await gerenciar_rotina(message, state)
        return

    if EXIBIR_LOGS: logger.info("🔍 Verificando pendências de numeração na memória antes de limpar...")
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

@dp.message(Command("postar"), StateFilter("*"))
@dp.message(F.text == "Criar Postagem 📝", StateFilter("*"))
async def iniciar_postagem(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
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
            
        # ✅ NOVO: Exibe o teclado com as três opções claras
        await message.answer(f"⚠️ A IA não conseguiu processar este vídeo.\n**Motivo:** {motivo}\n\nO que você deseja fazer agora?", reply_markup=teclado_erro_ia)
        
        # ✅ Em caso de erro, preservamos o arquivo físico e o número já reservado
        video_path_recuperacao = f"temp_{file_id}.mp4"
        await state.update_data(video_path=video_path_recuperacao, video_id=file_id, links=[], numero_reservado=numero_atual)
        
        # ✅ Redireciona para o novo estado de decisão
        await state.set_state(PostagemFluxo.aguardando_decisao_erro)

@dp.message(PostagemFluxo.aguardando_decisao_erro)
async def processar_erro_ia(message: types.Message, state: FSMContext):
    texto = message.text.strip()
    
    if texto == "Digitar Manualmente ✍️":
        if EXIBIR_LOGS: logger.info("✍️ Usuário optou por digitar manualmente após erro da IA.")
        await message.answer("Sem problemas. Digite manualmente APENAS O NOME DO PRODUTO ou kit:", reply_markup=teclado_cancelar)
        await state.set_state(PostagemFluxo.aguardando_chamada_manual)
        
    elif texto == "Tentar Novamente 🔄":
        if EXIBIR_LOGS: logger.info("🔄 Usuário optou por tentar processar o vídeo na IA novamente.")
        data = await state.get_data()
        video_path = data.get('video_path')
        numero_atual = data.get('numero_reservado')
        
        # Trava de segurança caso o arquivo físico tenha sido corrompido ou apagado
        if not video_path or not os.path.exists(video_path):
            await message.answer("⚠️ O arquivo de vídeo foi perdido no servidor. Por favor, clique em Cancelar e envie o vídeo novamente.", reply_markup=teclado_erro_ia)
            return
            
        msg_status = await message.answer("🔄 Reenviando vídeo para a IA analisar... Aguarde. ⏳", reply_markup=teclado_cancelar)
        
        def analisar_video_retry():
            import time
            if EXIBIR_LOGS: logger.info("📤 Fazendo re-upload do vídeo para o Google Storage...")
            video_gemini = client.files.upload(file=video_path)
            
            while video_gemini.state.name == "PROCESSING":
                time.sleep(2)
                video_gemini = client.files.get(name=video_gemini.name)
                
            if video_gemini.state.name == "FAILED":
                raise Exception("Falha de processamento no servidor do Google.")
                
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
            
        try:
            chamada_gerada = await asyncio.to_thread(analisar_video_retry)
            await msg_status.delete()
            
            await state.update_data(nome_produto=chamada_gerada)
            mensagem_aprovacao = f"{chamada_gerada}\n\n👉 <b>Esta identificação está correta?</b> Escolha uma opção abaixo:"
            await message.answer(mensagem_aprovacao, reply_markup=teclado_confirmacao, parse_mode="HTML")
            await state.set_state(PostagemFluxo.aguardando_confirmacao_nome)
            
        except Exception as e:
            erro_str = str(e)
            if EXIBIR_LOGS: logger.error(f"❌ Erro na tentativa de reprocessamento: {erro_str}")
            await msg_status.delete()
            motivo = "Falha no servidor."
            if "429" in erro_str:
                motivo = "Limite de velocidade da IA atingido. Aguarde 1 minuto."
            else:
                motivo = erro_str[:150] 
                
            await message.answer(f"⚠️ A IA falhou novamente.\n**Motivo:** {motivo}\n\nO que você deseja fazer agora?", reply_markup=teclado_erro_ia)
            
    elif texto != "Cancelar ❌":
        # 🚀 ATALHO: O usuário digitou o nome do produto diretamente na tela de erro
        if EXIBIR_LOGS: logger.info("✍️ Atalho: Usuário digitou o texto direto ignorando os botões de erro.")
        data = await state.get_data()
        numero_atual = data.get('numero_reservado')
        
        nome_formatado = f"Vídeo {numero_atual}\n📦 Item: {texto}"
        await state.update_data(nome_produto=nome_formatado)
        await message.answer(f"Identificação salva como:\n\n{nome_formatado}\n\nOnde você postou/vai postar este vídeo?", reply_markup=teclado_plataforma)
        await state.set_state(PostagemFluxo.aguardando_plataforma)

@dp.message(PostagemFluxo.aguardando_confirmacao_nome)
async def confirmar_nome(message: types.Message, state: FSMContext):
    texto = message.text.strip()
    if texto == "Aprovar ✅":
        if EXIBIR_LOGS: logger.info("✅ Nome aprovado. Avançando para seleção de plataforma.")
        await message.answer("Onde você postou/vai postar este vídeo?", reply_markup=teclado_plataforma)
        await state.set_state(PostagemFluxo.aguardando_plataforma)
    elif texto == "Digitar Nome ✍️":
        if EXIBIR_LOGS: logger.info("✍️ Transição manual solicitada para digitação do nome do produto.")
        await message.answer("Sem problemas. Digite manualmente APENAS O NOME DO PRODUTO:", reply_markup=teclado_cancelar)
        await state.set_state(PostagemFluxo.aguardando_chamada_manual)
    elif texto != "Cancelar ❌":
        # 🚀 ATALHO: O usuário digitou o nome do produto diretamente na tela de confirmação
        if EXIBIR_LOGS: logger.info("✍️ Atalho: Usuário digitou o texto direto sobrepondo a IA.")
        data = await state.get_data()
        numero_atual = data.get('numero_reservado')
        
        nome_formatado = f"Vídeo {numero_atual}\n📦 Item: {texto}"
        await state.update_data(nome_produto=nome_formatado)
        await message.answer(f"Identificação corrigida e salva como:\n\n{nome_formatado}\n\nOnde você postou/vai postar este vídeo?", reply_markup=teclado_plataforma)
        await state.set_state(PostagemFluxo.aguardando_plataforma)

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

    agora = datetime.now(fuso_horario)
    hoje_str = agora.strftime("%Y-%m-%d")
    amanha_str = (agora + timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 🚀 LÓGICA DE INTELIGÊNCIA TEMPORAL E FILA ESTRITA (FIFO)
    dados_rotina = ler_config_rotina()
    
    # 1. Define a data base olhando para a bandeira do Bom Dia
    if dados_rotina.get("ultimo_bom_dia") == hoje_str:
        data_agendamento_base = amanha_str
        if EXIBIR_LOGS: logger.info("⏰ O 'Bom Dia' de hoje já passou. Data base projetada para Amanhã.")
    else:
        data_agendamento_base = "2000-01-01" # Flag interna para 'Imediato/Hoje'
        if EXIBIR_LOGS: logger.info("⏰ O 'Bom Dia' de hoje ainda não passou (Madrugada/Manhã). Data base projetada para Hoje.")
        
    # 2. 🚧 Trava de Ordem Cronológica (Não permite furar a fila)
    fila_data_temp = ler_fila_postagens()
    fila_temp = fila_data_temp.get("fila", [])
    if fila_temp:
        ultima_data_str = fila_temp[-1].get("data_adicao", "2000-01-01")
        
        # Se o último vídeo da fila já foi empurrado para o futuro, o novo vídeo tem que acompanhá-lo.
        if ultima_data_str != "2000-01-01" and ultima_data_str > data_agendamento_base:
            data_agendamento_base = ultima_data_str
            if EXIBIR_LOGS: logger.info(f"🚧 FIFO: O novo vídeo foi empurrado para o fim da fila: {data_agendamento_base}")
    
    def adicionar_a_fila(caminho_vid, vid_id, caption):
        fila_data = ler_fila_postagens()
        
        if EXIBIR_LOGS: logger.info(f"📅 Aplicando blindagem temporal. Data base fixada: {data_agendamento_base}")
            
        item = {
            "id": f"{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}",
            "caminho_video": caminho_vid,
            "video_id": vid_id,
            "legenda": caption,
            "data_adicao": data_agendamento_base
        }
        fila_data.setdefault("fila", []).append(item)
        salvar_fila_postagens(fila_data)

    caminho_final = caminho_processado if caminho_processado and os.path.exists(caminho_processado) else caminho_video_original
    
    if caminho_processado and caminho_video_original and os.path.exists(caminho_video_original):
        os.remove(caminho_video_original)

    if nivel_4_ativado:
        legenda_shopee = montar_legenda(texto_longo, is_rodape=False, plataforma_alvo="Apenas Shopee 🛒")
        if EXIBIR_LOGS: logger.info(f"📦 A agendar vídeo 1/2 (Shopee) na fila invisível para a data: {data_agendamento_base}.")
        adicionar_a_fila(caminho_final, None, legenda_shopee)
        
        legenda_tiktok = montar_legenda(texto_longo, is_rodape=False, plataforma_alvo="Apenas TikTok 🎵")
        if EXIBIR_LOGS: logger.info(f"📦 A agendar vídeo 2/2 (TikTok) na fila invisível para a data: {data_agendamento_base}.")
        adicionar_a_fila(caminho_final, None, legenda_tiktok)
    else:
        if EXIBIR_LOGS: logger.info(f"📦 A agendar vídeo consolidado na fila invisível para a data: {data_agendamento_base}.")
        adicionar_a_fila(caminho_final, video_id_fallback if not caminho_final else None, legenda_final)
        
    if EXIBIR_LOGS: logger.info("💾 Ficheiro físico adormecido. A limpeza ocorrerá automaticamente após o upload escalonado.")
    
    async with _lock_contador:
        proximo_numero = ler_contador()
        
    # ✅ CORREÇÃO: O recálculo só acontece se o vídeo for para HOJE.
    # Vídeos do futuro entram na fila sem afetar os horários já definidos para hoje.
    if data_agendamento_base == "2000-01-01" or data_agendamento_base <= hoje_str:
        if EXIBIR_LOGS: logger.info("🔄 O novo vídeo é para hoje. A recalcular a grelha de publicações em tempo real...")
        agendar_fila_postagens()
        texto_data = "hoje! 🟢"
    else:
        if EXIBIR_LOGS: logger.info(f"⏭️ O novo vídeo é para o futuro ({data_agendamento_base}). A grelha de hoje não será afetada.")
        texto_data = "o futuro! 📅✅"
    
    await message.answer(f"Publicação processada e agendada para {texto_data}\nO sistema distribuirá os vídeos de forma orgânica. O próximo vídeo assumirá o número {proximo_numero}.", reply_markup=obter_teclado_principal())
    await state.clear()

# ✅ Handlers para Gerenciar a Numeração
@dp.message(F.text == "Editar Número da Postagem 🔢", StateFilter("*"))
async def menu_editar_numero(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
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

@dp.message(F.text == "🛠️ Configurações Avançadas", StateFilter("*"))
async def menu_configuracoes(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    if EXIBIR_LOGS: logger.info("⚙️ Acessando Dashboard de Configurações Gerais de Automações.")
    
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
    await message.answer(texto, reply_markup=obter_teclado_configuracoes_gerais(), parse_mode="HTML")

# ✅ NOVO: Botão de Pânico / Reset Mestre (Versão Completa)
@dp.message(F.text == "🔄 Atualizar Rotinas", StateFilter("*"))
async def resetar_expediente(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    if EXIBIR_LOGS: logger.info("🔄 Acionado o Reset Mestre do Expediente...")
    msg_status = await message.answer("🔄 Iniciando o protocolo de Reset Mestre e recalculando a grade. Aguarde...", reply_markup=teclado_cancelar)
    
    # 1. Dá a "pílula de amnésia" no robô (Limpa o histórico e o painel visual)
    dados_rotina = ler_config_rotina()
    dados_rotina["ultimo_bom_dia"] = ""
    dados_rotina["hora_ultimo_bom_dia"] = "" # Limpa do painel visual
    dados_rotina["ultimo_boa_noite"] = ""
    dados_rotina["hora_ultimo_boa_noite"] = "" # Limpa do painel visual
    dados_rotina["historico_diario"] = {"data": "", "contagem": {}}
    salvar_config_rotina(dados_rotina)
    
    # 2. O Resgate dos Vídeos (Puxa de volta os vídeos empurrados para amanhã)
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    for item in fila:
        if not item.get("postado"):
            # Devolve o status "Imediato/Hoje" (código 2000-01-01) para todos os pendentes
            item["data_adicao"] = "2000-01-01"
            
    fila_data["fila"] = fila
    salvar_fila_postagens(fila_data)
    
    # 3. Varre a agenda antiga e recalcula a distribuição
    agendar_tarefas_diarias()
    
    await msg_status.delete()
    
    texto = (
        "🔄 <b>Expediente Resetado com Sucesso!</b>\n\n"
        "O robô esqueceu o falso encerramento e <b>recalculou toda a grade do zero</b>.\n\n"
        "✅ O painel de horários foi zerado.\n"
        "✅ A cota de disparos de rotina foi renovada.\n"
        "✅ <b>Os vídeos empurrados para amanhã foram resgatados e distribuídos no dia de hoje!</b>"
    )
    await message.answer(texto, parse_mode="HTML", reply_markup=obter_teclado_principal())
    await state.clear()

@dp.message(F.text == "Outros Canais 🗂️", StateFilter("*"))
async def menu_outros_canais(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    if EXIBIR_LOGS: logger.info("🗂️ Acessando a gaveta de Outros Canais.")
    await message.answer("Selecione o robô ou módulo secundário que deseja gerir:", reply_markup=teclado_outros_canais)

@dp.message(F.text == "Voltar ao Início 🔙", StateFilter("*"))
async def voltar_inicio(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await state.update_data(painel_atual="raiz")
    await message.answer("🏠 Voltando ao Painel Inicial.", reply_markup=obter_teclado_raiz())

@dp.message(F.text == "Voltar aos Canais 🔙", StateFilter("*"))
async def voltar_outros_canais(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await message.answer("Selecione o robô ou módulo secundário que deseja gerir:", reply_markup=teclado_outros_canais)

@dp.message(F.text == "Voltar ao Menu Espião 🔙", StateFilter("*"))
async def voltar_menu_espiao(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🔙 Retornando ao Menu Principal do Espião...")
    await state.clear()
    # Redireciona a execução diretamente para a função principal para exibir o painel completo
    await menu_espiao_principal(message, state)

@dp.message(F.text == "⚙️ Automações (SPAM e Rotina)\u200b", StateFilter("*"))
async def menu_automacoes_espiao(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    if EXIBIR_LOGS: logger.info("⚙️ Acessando Dashboard de Automações do Espião.")
    
    dados_div = ler_alvos_divulgacao_viral()
    status_spam = "🔴 PAUSADO" if dados_div.get("pausado", False) else "🟢 ATIVO"
    
    dados_rotina = ler_config_rotina()
    status_rotina = "🔴 PAUSADAS" if dados_rotina.get("pausado_viral", False) else "🟢 ATIVAS"
    
    texto = (
        "⚙️ <b>Central de Automações do Espião</b>\n\n"
        "📊 <b>Status Atual das Automações:</b>\n"
        f"📢 SPAM do Viral: {status_spam}\n"
        f"⏰ Rotinas do Viral: {status_rotina}\n\n"
        "Escolha o módulo que deseja configurar abaixo:"
    )
    await message.answer(texto, reply_markup=teclado_automacoes_espiao, parse_mode="HTML")

@dp.message(F.text == "Voltar às Automações 🔙", StateFilter("*"))
async def voltar_para_automacoes_espiao(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🔙 Retornando à Central de Automações do Espião.")
    await state.clear()
    await menu_automacoes_espiao(message, state)

@dp.message(F.text == "Voltar às Configs 🔙", StateFilter("*"))
async def voltar_para_configs_avancadas(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🔙 Retornando à Central de Configurações Avançadas.")
    await state.clear()
    await menu_configuracoes(message, state)

@dp.message(F.text == "Voltar 🔙", StateFilter("*"))
async def voltar_configs(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await message.answer("Painel de Controle atualizado.", reply_markup=obter_teclado_principal())

# --- HANDLERS DO PAINEL DO ESPIÃO 🕵️ ---
@dp.message(F.text == "Espião Afiliados 🕵️")
async def menu_espiao_principal(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    
    if EXIBIR_LOGS: logger.info("🚀 Iniciando consolidação de estatísticas para o painel do Espião...")
    
    # 1. Obter quantidade de vídeos pendentes na fila
    fila_data = ler_fila_clonagem()
    fila = fila_data.get("fila", [])
    videos_pendentes = len([item for item in fila if not item.get("processado")])
    
    # 2. Obter canais monitorizados e destino do ficheiro de configuração (CORRIGIDO)
    dados_espiao = ler_alvos_espiao()
    concorrentes = dados_espiao.get("alvos", [])
    qtd_concorrentes = len(concorrentes)
    canal_destino = dados_espiao.get("canal_destino")
    
    if not canal_destino:
        canal_destino = "Não definido"
    
    # 3. Construir a mensagem unificada do painel
    texto = "🕵️ <b>Painel Principal do Espião</b>\n\n"
    texto += f"📦 <b>Fila de clonagem:</b> {videos_pendentes} vídeos aguardando.\n"
    texto += f"📡 <b>Radar operacional:</b> {qtd_concorrentes} concorrentes vigiados.\n"
    texto += f"🎯 <b>Canal de destino:</b> <code>{canal_destino}</code>\n\n"
    texto += "Escolha uma opção para gerenciar:"
    
    if EXIBIR_LOGS: logger.info("✅ Sucesso: Painel unificado do Espião renderizado com logs operacionais.")
    await message.answer(texto, reply_markup=teclado_menu_espiao, parse_mode="HTML")

@dp.message(F.text == "Grupos Vigiados 📡")
async def menu_grupos_vigiados(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("📡 Acessando a lista de grupos vigiados do Espião...")
    
    # ✅ NOVO: Leitura direta e atualizada do arquivo para pegar o status real do Userbot
    try:
        with open("alvos_espiao.json", "r") as f:
            dados = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        dados = {"alvos": [], "canal_destino": None, "status_alvos": {}}
        
    alvos = dados.get("alvos", [])
    destino = dados.get("canal_destino", "Não definido")
    status_alvos = dados.get("status_alvos", {})
    
    texto = f"📡 <b>Gestão de Grupos Vigiados</b>\n\n"
    texto += f"🎯 <b>Canal de Destino:</b> {destino}\n\n"
    texto += "<b>Na Escuta:</b>\n"
    
    if alvos:
        for i, alvo in enumerate(alvos, 1):
            info = status_alvos.get(alvo, {})
            status_ico = "⏳" # Status pendente enquanto o Userbot não verifica
            detalhe = alvo
            
            if info.get("status") == "ok":
                status_ico = "✅"
                detalhe = f"{info.get('nome')} <code>({alvo})</code>"
            elif info.get("status") == "erro":
                status_ico = "❌"
                detalhe = f"<code>{alvo}</code> - <i>Acesso negado/Link inválido</i>"
                
            texto += f"   {i}. {status_ico} {detalhe}\n"
    else:
        texto += "   <i>Nenhum grupo sendo monitorado no momento.</i>\n"
        
    await message.answer(texto, reply_markup=teclado_opcoes_espiao, parse_mode="HTML")
    await state.set_state(EspiaoFluxo.menu_principal)

@dp.message(EspiaoFluxo.menu_principal, F.text == "Adicionar Concorrente ➕")
async def pedir_alvo_espiao(message: types.Message, state: FSMContext):
    await message.answer("Envie o @username, link ou ID do grupo do concorrente que deseja monitorar:", reply_markup=teclado_cancelar)
    await state.set_state(EspiaoFluxo.aguardando_novo_alvo)

@dp.message(EspiaoFluxo.aguardando_novo_alvo)
async def confirmar_alvo_espiao(message: types.Message, state: FSMContext):
    entrada_bruta = message.text.strip()
    
    # 🧹 O Higienizador rígido foi removido. O bot passará o dado bruto para o 
    # motor Espião auditar e corrigir o ID automaticamente.
    await state.update_data(novo_alvo_formatado=entrada_bruta)
    
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )

    if EXIBIR_LOGS: logger.info("⏳ Aguardando aprovação para auditar o novo alvo do espião...")
    await message.answer(f"Deseja adicionar o alvo abaixo ao radar do Espião?\n<i>(O motor testará os formatos de ID e corrigirá automaticamente se necessário)</i>\n\n<b>{entrada_bruta}</b>", reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(EspiaoFluxo.aguardando_confirmacao_alvo)

@dp.message(EspiaoFluxo.aguardando_confirmacao_alvo)
async def salvar_alvo_espiao(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, clique em Aprovar ou Cancelar.")
        return
        
    data = await state.get_data()
    alvo_formatado = data.get("novo_alvo_formatado").strip()
    dados = ler_alvos_espiao()
    
    # Validação semântica: ignora o '@' e passa para minúsculas para barrar duplicados
    alvo_limpo = alvo_formatado.lstrip('@').lower()
    alvos_existentes_limpos = [str(a).lstrip('@').lower() for a in dados.get("alvos", [])]
    
    if alvo_limpo not in alvos_existentes_limpos:
        dados.setdefault("alvos", []).append(alvo_formatado)
        salvar_alvos_espiao(dados)
        if EXIBIR_LOGS: logger.info(f"✅ Novo alvo do espião adicionado na base de dados: {alvo_formatado}")
        await message.answer(f"✅ Alvo cadastrado com sucesso:\n<b>{alvo_formatado}</b>", parse_mode="HTML")
    else:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Tentativa de duplicar alvo bloqueada. O alvo '{alvo_formatado}' já existe.")
        await message.answer(f"⚠️ O alvo <b>{alvo_formatado}</b> já está na sua lista de monitoramento.", parse_mode="HTML")
        
    await menu_grupos_vigiados(message, state)

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
async def confirmar_remocao_espiao(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas o NÚMERO.", reply_markup=teclado_cancelar)
        return
        
    indice = int(message.text) - 1
    dados = ler_alvos_espiao()
    alvos = dados.get("alvos", [])
    
    if 0 <= indice < len(alvos):
        alvo_selecionado = alvos[indice]
        await state.update_data(indice_remocao=indice)
        
        teclado_confirmacao = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
            resize_keyboard=True,
            is_persistent=True
        )
        
        await message.answer(f"Tem certeza de que deseja parar de monitorar o alvo abaixo?\n\n<b>{alvo_selecionado}</b>", reply_markup=teclado_confirmacao, parse_mode="HTML")
        await state.set_state(EspiaoFluxo.aguardando_confirmacao_remocao)
    else:
        await message.answer("⚠️ Número inválido. Tente novamente:", reply_markup=teclado_cancelar)

@dp.message(EspiaoFluxo.aguardando_confirmacao_remocao)
async def processar_remocao_espiao(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, clique em Aprovar ou Cancelar.")
        return
        
    data = await state.get_data()
    indice = data.get("indice_remocao")
    dados = ler_alvos_espiao()
    alvos = dados.get("alvos", [])
    
    if indice is not None and 0 <= indice < len(alvos):
        removido = dados["alvos"].pop(indice)
        salvar_alvos_espiao(dados)
        if EXIBIR_LOGS: logger.info(f"🗑️ Alvo do espião removido: {removido}")
        await message.answer(f"✅ Alvo '{removido}' removido do radar!")
    else:
        await message.answer("⚠️ Erro de sincronização. Ação cancelada.")
        
    await menu_grupos_vigiados(message, state)

@dp.message(EspiaoFluxo.menu_principal, F.text == "Definir Canal de Destino 🎯")
async def pedir_destino_espiao(message: types.Message, state: FSMContext):
    await message.answer("Envie o @username ou ID do seu Canal onde o bot postará os vídeos clonados (Ex: -100123456789):", reply_markup=teclado_cancelar)
    await state.set_state(EspiaoFluxo.aguardando_canal_destino)

@dp.message(EspiaoFluxo.aguardando_canal_destino)
async def confirmar_destino_espiao(message: types.Message, state: FSMContext):
    destino = message.text.strip()
    await state.update_data(novo_destino=destino)
    
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    
    await message.answer(f"Os vídeos clonados serão enviados automaticamente para o canal:\n\n<b>{destino}</b>\n\nConfirma essa alteração?", reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(EspiaoFluxo.aguardando_confirmacao_destino)

@dp.message(EspiaoFluxo.aguardando_confirmacao_destino)
async def salvar_destino_espiao(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, clique em Aprovar ou Cancelar.")
        return
        
    data = await state.get_data()
    destino = data.get("novo_destino")
    
    dados = ler_alvos_espiao()
    dados["canal_destino"] = destino
    salvar_alvos_espiao(dados)
    
    if EXIBIR_LOGS: logger.info(f"🎯 Canal de destino do espião atualizado para: {destino}")
    await message.answer("✅ Canal de destino configurado com sucesso!")
    
    await menu_grupos_vigiados(message, state)

@dp.message(F.text == "Rotinas do Espião ⏰", StateFilter("*"))
async def gerenciar_rotina_espiao(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    dados = ler_config_rotina()
    
    # Resgata as configurações das três rotinas do canal viral
    config_convite = dados.get("link_grupo_viral", {"inicio": 9, "fim": 21, "frequencia": 2})
    config_gem = dados.get("divulgar_gem_viral", {"inicio": 8, "fim": 22, "frequencia": 1})
    config_promo = dados.get("promo_principal", {"inicio": 10, "fim": 20, "frequencia": 1})
    
    if EXIBIR_LOGS: logger.info("⚙️ Acessando painel de Rotinas do Espião...")
    texto = "⏰ <b>Rotina do Espião (Canal Viral)</b>\n\n"
    
    texto += f"🔹 <b>Convite do Grupo 🔗 (Para o próprio grupo)</b>\n"
    texto += f"   Janela de Sorteio: {config_convite['inicio']}h às {config_convite['fim']}h\n"
    texto += f"   Disparos por Dia: {config_convite['frequencia']}x\n\n"

    texto += f"🔹 <b>Prompt GEM 🤖 (Para o próprio grupo)</b>\n"
    texto += f"   Janela de Sorteio: {config_gem['inicio']}h às {config_gem['fim']}h\n"
    texto += f"   Disparos por Dia: {config_gem['frequencia']}x\n\n"
    
    texto += f"🔹 <b>Convite do Grupo Afiliados 🛍️ (Para o Canal Afiliados)</b>\n"
    texto += f"   Janela de Sorteio: {config_promo['inicio']}h às {config_promo['fim']}h\n"
    texto += f"   Disparos por Dia: {config_promo['frequencia']}x\n\n"
    
    texto += "Selecione o que deseja editar abaixo:"
    
    # ✅ NOVO: Verificação do status e adição do botão de pausa dinâmico
    texto_botao_pausa = "Retomar Rotinas ▶️" if dados.get("pausado_viral") else "Pausar Rotinas ⏸️"
    
    teclado = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Editar Convite do Grupo 🔗"), KeyboardButton(text="Editar Prompt GEM 🤖\u200b")],
            [KeyboardButton(text="Editar Convite Afiliados 🚀"), KeyboardButton(text=texto_botao_pausa)],
            [KeyboardButton(text="Voltar às Automações 🔙")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer(texto, reply_markup=teclado, parse_mode="HTML")
    await state.update_data(menu_origem="espiao") # ✅ Salva a origem para não quebrar a navegação
    await state.set_state(ConfigRotina.menu_principal)

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

@dp.message(ConfigDivulgacaoViral.menu_principal, F.text.in_(["Pausar SPAM ⏸️", "Retomar SPAM ▶️"]))
async def alternar_pausa_spam_viral_interno(message: types.Message, state: FSMContext):
    dados = ler_alvos_divulgacao_viral()
    novo_status = not dados.get("pausado", False)
    dados["pausado"] = novo_status
    salvar_alvos_divulgacao_viral(dados)

    if novo_status:
        if EXIBIR_LOGS: logger.info("⏸️ SPAM Viral PAUSADO internamente.")
        await message.answer("⏸️ <b>SPAM Viral PAUSADO.</b>\nO Userbot não enviará convites para o Viral.", parse_mode="HTML")
    else:
        if EXIBIR_LOGS: logger.info("▶️ SPAM Viral ATIVADO internamente.")
        await message.answer("▶️ <b>SPAM Viral ATIVO.</b>\nO Userbot voltará a operar normalmente para o Viral.", parse_mode="HTML")

    await gerenciar_divulgacao_viral(message, state)

@dp.message(ConfigRotina.menu_principal, F.text.in_(["Pausar Rotinas ⏸️", "Retomar Rotinas ▶️"]))
async def alternar_pausa_rotinas_interno(message: types.Message, state: FSMContext):
    data = await state.get_data()
    origem = data.get("menu_origem")
    dados_rotina = ler_config_rotina()

    if origem == "espiao":
        novo_status = not dados_rotina.get("pausado_viral", False)
        dados_rotina["pausado_viral"] = novo_status
        salvar_config_rotina(dados_rotina)
        
        if novo_status:
            if EXIBIR_LOGS: logger.info("⏸️ Rotinas do VIRAL pausadas internamente.")
            await message.answer("⏸️ <b>Rotinas do Canal Viral PAUSADAS.</b>\nAs mensagens automáticas foram suspensas.", parse_mode="HTML")
        else:
            if EXIBIR_LOGS: logger.info("▶️ Rotinas do VIRAL ativadas internamente.")
            await message.answer("▶️ <b>Rotinas do Canal Viral ATIVAS.</b>\nAs mensagens automáticas voltarão a ser enviadas.", parse_mode="HTML")
        
        await gerenciar_rotina_espiao(message, state)
    else:
        novo_status = not dados_rotina.get("pausado", False)
        dados_rotina["pausado"] = novo_status
        salvar_config_rotina(dados_rotina)
        
        if novo_status:
            if EXIBIR_LOGS: logger.info("⏸️ Rotinas do PRINCIPAL pausadas internamente.")
            await message.answer("⏸️ <b>Mensagens de Rotina PAUSADAS.</b>\nAs mensagens automáticas do grupo foram suspensas.", parse_mode="HTML")
        else:
            if EXIBIR_LOGS: logger.info("▶️ Rotinas do PRINCIPAL ativadas internamente.")
            await message.answer("▶️ <b>Mensagens de Rotina ATIVAS.</b>\nAs mensagens automáticas voltarão a ser enviadas.", parse_mode="HTML")
            
        await gerenciar_rotina(message, state)

# ✅ NOVO: Handler específico para corrigir o "Voltar" na pausa programada
@dp.message(PausaProgramadaFluxo.aguardando_selecao_servicos, F.text == "Voltar 🔙")
@dp.message(PausaProgramadaFluxo.aguardando_data_retorno, F.text == "Voltar 🔙")
@dp.message(PausaProgramadaFluxo.aguardando_intencao_encerramento, F.text == "Voltar 🔙")
async def voltar_pausa_para_inicio(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🔙 Comando Voltar acionado na Pausa Programada.")
    await state.clear()
    await message.answer("Operação cancelada. Voltando ao menu principal.", reply_markup=obter_teclado_principal())

@dp.message(F.text.in_(["Pausar Postagens 🛑", "Retomar Postagens ▶️"]), StateFilter("*"))
async def iniciar_pausa_programada(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    dados_pausa = ler_pausa_programada()
    
    if dados_pausa.get("ativa"):
        data_retorno = dados_pausa.get("data_retorno")
        texto = f"⚠️ <b>Pausa Programada Ativa!</b>\nO robô está em modo de descanso até <b>{data_retorno}</b>.\n\nDeseja cancelar esta pausa e retomar os serviços agora?"
        teclado = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Encerrar Pausa Agora ▶️")], [KeyboardButton(text="Voltar 🔙")]], resize_keyboard=True, is_persistent=True)
        await message.answer(texto, reply_markup=teclado, parse_mode="HTML")
        await state.set_state(PausaProgramadaFluxo.aguardando_intencao_encerramento)
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
        await state.update_data(servicos_selecionados="Nenhum (Apenas Avisos)")
        await message.answer(f"Ambos os serviços já estão pausados manualmente.\nApenas a rotina diária de avisos será agendada até {data_retorno_str}.\nConfirma o agendamento desta pausa?", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Confirmar Pausa ✅"), KeyboardButton(text="Cancelar ❌")]], resize_keyboard=True))
        await state.set_state(PausaProgramadaFluxo.aguardando_confirmacao_pausa)
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
async def processar_selecao_servicos(message: types.Message, state: FSMContext):
    opcoes_validas = ["Pausar Ambos", "Apenas SPAM", "Apenas Rotina", "Pausar SPAM", "Pausar Rotina"]
    if message.text not in opcoes_validas:
        await message.answer("Use um dos botões para escolher.", reply_markup=teclado_cancelar)
        return
        
    await state.update_data(servicos_selecionados=message.text)
    data = await state.get_data()
    data_retorno_str = data["data_retorno_str"]
    
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Confirmar Pausa ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    
    await message.answer(f"Você escolheu: <b>{message.text}</b>\nO robô ficará pausado até <b>{data_retorno_str}</b>.\n\nConfirma o agendamento desta pausa?", reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(PausaProgramadaFluxo.aguardando_confirmacao_pausa)

@dp.message(PausaProgramadaFluxo.aguardando_confirmacao_pausa)
async def confirmar_pausa_programada_final(message: types.Message, state: FSMContext):
    if message.text != "Confirmar Pausa ✅":
        await message.answer("Por favor, clique em Confirmar Pausa ✅ ou Cancelar ❌.")
        return

    data = await state.get_data()
    data_retorno_str = data["data_retorno_str"]
    selecao = data.get("servicos_selecionados", "")
    
    servicos_pausados = []
    if selecao in ["Pausar Ambos", "Apenas SPAM", "Pausar SPAM"]:
        dados_div = ler_alvos_divulgacao()
        dados_div["pausado"] = True
        salvar_alvos_divulgacao(dados_div)
        servicos_pausados.append("spam")
        
    if selecao in ["Pausar Ambos", "Apenas Rotina", "Pausar Rotina"]:
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

    prompt = (
        f"Você é um assistente de afiliados. Crie um aviso imediato MUITO CURTO E DIRETO "
        f"informando que as postagens estão pausadas a partir de agora para {motivo_escolhido}. "
        f"Avise que o retorno será no dia {data_curta}. "
        f"REGRA ABSOLUTA: Use no máximo 2 a 3 linhas e não ultrapasse 150 caracteres. "
        f"Seja direto, não peça desculpas longas e não dê explicações chatas. "
        f"Use emojis e entregue APENAS o texto da mensagem final."
    )
    msg_status = await message.answer("⏳ Configurando a pausa e gerando o aviso no grupo...", reply_markup=teclado_cancelar)
    texto_aviso = await gerar_mensagem_gemini(prompt)
    msg_imediata = await bot.send_message(GRUPO_ID, texto_aviso)
    await msg_status.delete()
    
    dados_pausa = {
        "ativa": True,
        "data_retorno": data_retorno_str,
        "servicos_pausados": servicos_pausados,
        "id_aviso_imediato": msg_imediata.message_id, 
        "motivo": motivo_escolhido 
    }
    salvar_pausa_programada(dados_pausa)
    
    if EXIBIR_LOGS: logger.info(f"🛑 Pausa programada até {data_retorno_str}. Aviso imediato disparado. Serviços: {servicos_pausados}")
    await message.answer(f"🛑 <b>Pausa Configurada com Sucesso!</b>\n\nO aviso já foi enviado ao grupo. A partir de amanhã, o robô atualizará esse aviso todos os dias às 09h00 informando o retorno para o dia {data_retorno_str}.\nNo dia marcado, ele acordará automaticamente.", parse_mode="HTML", reply_markup=obter_teclado_principal())
    await state.clear()

@dp.message(PausaProgramadaFluxo.aguardando_intencao_encerramento)
async def pedir_confirmacao_encerramento(message: types.Message, state: FSMContext):
    if message.text == "Encerrar Pausa Agora ▶️":
        teclado_confirmacao = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Aprovar Encerramento ✅"), KeyboardButton(text="Cancelar ❌")]],
            resize_keyboard=True,
            is_persistent=True
        )
        await message.answer("⚠️ Tem certeza de que deseja <b>encerrar a pausa agora</b>, recalcular a fila e acordar o robô imediatamente?", reply_markup=teclado_confirmacao, parse_mode="HTML")
        await state.set_state(PausaProgramadaFluxo.aguardando_confirmacao_encerramento)
    else:
        await message.answer("Use os botões abaixo para escolher.", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Encerrar Pausa Agora ▶️")], [KeyboardButton(text="Voltar 🔙")]], resize_keyboard=True, is_persistent=True))

@dp.message(PausaProgramadaFluxo.aguardando_confirmacao_encerramento)
async def processar_encerramento_pausa(message: types.Message, state: FSMContext):
    if message.text != "Aprovar Encerramento ✅":
        await message.answer("Por favor, clique em Aprovar Encerramento ✅ ou Cancelar ❌.")
        return

    dados_pausa = ler_pausa_programada()
    servicos = dados_pausa.get("servicos_pausados", [])
    
    # ✅ NOVO: Apaga a mensagem de aviso que ficou pendente no grupo
    id_aviso = dados_pausa.get("id_aviso_imediato")
    if id_aviso:
        await apagar_mensagem_automatica(id_aviso, GRUPO_ID)
        if EXIBIR_LOGS: logger.info("🧹 Aviso de pausa antigo excluído do grupo.")
        
    msg_status = await message.answer("⏳ Gerando mensagem de retorno com a IA...", reply_markup=teclado_cancelar)
    
    # ✅ NOVO: A IA gera o aviso de retorno ao trabalho
    prompt_retorno = (
        "Você é um assistente de afiliados. Crie uma mensagem MUITO CURTA E EMPOLGANTE "
        "avisando o grupo que a pausa de manutenção acabou, o canal voltou à ativa e os "
        "vídeos com ofertas voltarão a ser postados normalmente a partir de agora. "
        "REGRA ABSOLUTA: Seja direto (máximo 150 caracteres), use emojis animados e entregue APENAS o texto pronto."
    )
    texto_retorno = await gerar_mensagem_gemini(prompt_retorno)
    
    # ✅ CORREÇÃO: Salva a mensagem enviada numa variável e joga o ID na lixeira
    msg_retorno = await bot.send_message(GRUPO_ID, texto_retorno)
    registrar_lixeira(msg_retorno.message_id, GRUPO_ID)
    
    await msg_status.delete()
    
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
    dados_pausa.pop("id_aviso_imediato", None)
    salvar_pausa_programada(dados_pausa)
    recalcular_datas_pos_pausa()
    
    await message.answer("▶️ Pausa programada encerrada! O aviso antigo foi apagado e a mensagem de retorno foi postada no grupo. Serviços reativados com sucesso!", reply_markup=obter_teclado_principal())
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
    await message.answer("Alvos adicionados com sucesso!", reply_markup=obter_teclado_configuracoes_gerais())
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
        await message.answer(f"Alvo '{removido}' excluído com sucesso!", reply_markup=obter_teclado_configuracoes_gerais())
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
    
    await message.answer(msg_final, reply_markup=obter_teclado_configuracoes_gerais(), parse_mode="HTML")
    await state.clear()

@dp.message(ConfigDivulgacao.menu_principal, F.text == "Forçar Disparo Agora 🚀")
async def acionar_disparo_imediato(message: types.Message):
    dados = ler_alvos_divulgacao()
    dados["forcar_disparo"] = True
    salvar_alvos_divulgacao(dados)
    if EXIBIR_LOGS: logger.info("🚀 Comando de disparo forçado enviado para o arquivo JSON.")
    await message.answer("🚀 <b>Disparo Imediato Acionado!</b>\nO Userbot detectará o comando e enviará a rajada de convites em até 5 segundos.", parse_mode="HTML", reply_markup=teclado_opcoes_divulgacao)

# --- LÓGICA DE GERENCIAMENTO DE DIVULGAÇÃO (CANAL VIRAL) ---
def ler_alvos_divulgacao_viral():
    try:
        with open("alvos_divulgacao_viral.json", "r") as f:
            dados = json.load(f)
            if "repeticoes_internas" not in dados: dados["repeticoes_internas"] = 6
            if "replicas_mensagem" not in dados: dados["replicas_mensagem"] = 5
            return dados
    except (FileNotFoundError, json.JSONDecodeError):
        return {"alvos": [], "frequencia_por_hora": 0, "pausado": False, "forcar_disparo": False, "repeticoes_internas": 6, "replicas_mensagem": 5}

def salvar_alvos_divulgacao_viral(dados):
    with open("alvos_divulgacao_viral.json", "w") as f:
        json.dump(dados, f, indent=4)

@dp.message(F.text == "SPAM do Espião 📢", StateFilter("*"))
async def gerenciar_divulgacao_viral(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("📢 Acessando o painel de SPAM do Canal Viral...")
    dados = ler_alvos_divulgacao_viral()
    alvos = dados.get("alvos", [])
    freq_g = dados.get("frequencia_por_hora", 0)
    rep_int_g = dados.get("repeticoes_internas", 6)
    rep_msg_g = dados.get("replicas_mensagem", 5)
    status_pausa = "⏸️ Pausado" if dados.get("pausado") else "▶️ Rodando"
    config_alvos = dados.get("config_alvos", {})

    texto = f"📊 <b>Status da Divulgação do Viral</b> [{status_pausa}]\n\n"
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
    teclado_dinamico_spam_viral = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Adicionar Alvo Viral ➕"), KeyboardButton(text="Excluir Alvo Viral 🗑️")],
            [KeyboardButton(text="Editar Configs Viral ⚙️"), KeyboardButton(text="Forçar Disparo Viral 🚀")],
            [KeyboardButton(text=texto_botao_pausa), KeyboardButton(text="Voltar às Automações 🔙")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
        
    await message.answer(texto, parse_mode="HTML", reply_markup=teclado_dinamico_spam_viral)
    await state.set_state(ConfigDivulgacaoViral.menu_principal)

@dp.message(ConfigDivulgacaoViral.menu_principal, F.text == "Adicionar Alvo Viral ➕")
async def pedir_alvo_viral(message: types.Message, state: FSMContext):
    await message.answer("Envie os links ou IDs dos grupos separados por vírgula para o SPAM VIRAL.\nExemplo: <code>https://t.me/grupo_viral, -1009999999</code>", reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(ConfigDivulgacaoViral.aguardando_alvos)

@dp.message(ConfigDivulgacaoViral.aguardando_alvos)
async def salvar_alvo_viral(message: types.Message, state: FSMContext):
    novos_alvos = [alvo.strip() for alvo in message.text.split(",") if alvo.strip()]
    if not novos_alvos:
        await message.answer("Nenhum alvo detectado. Tente novamente:", reply_markup=teclado_cancelar)
        return
        
    dados = ler_alvos_divulgacao_viral()
    dados["alvos"].extend(novos_alvos)
    dados["alvos"] = list(dict.fromkeys(dados["alvos"]))
    salvar_alvos_divulgacao_viral(dados)
    
    if EXIBIR_LOGS: logger.info(f"✅ Novos alvos virais adicionados: {novos_alvos}")
    await message.answer("Alvos do Viral adicionados com sucesso!")
    await gerenciar_divulgacao_viral(message, state)

@dp.message(ConfigDivulgacaoViral.menu_principal, F.text == "Excluir Alvo Viral 🗑️")
async def pedir_exclusao_viral(message: types.Message, state: FSMContext):
    dados = ler_alvos_divulgacao_viral()
    alvos = dados.get("alvos", [])
    if not alvos:
        await message.answer("Não há alvos cadastrados para excluir.")
        await gerenciar_divulgacao_viral(message, state)
        return
        
    texto = "Qual alvo do Viral deseja excluir? Digite o <b>NÚMERO</b> correspondente da lista abaixo:\n\n"
    for i, alvo in enumerate(alvos, 1):
        texto += f"{i}. {alvo}\n"
    await message.answer(texto, reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(ConfigDivulgacaoViral.aguardando_exclusao_alvo)

@dp.message(ConfigDivulgacaoViral.aguardando_exclusao_alvo)
async def processar_exclusao_viral(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas o NÚMERO do alvo.", reply_markup=teclado_cancelar)
        return
        
    indice = int(message.text) - 1
    dados = ler_alvos_divulgacao_viral()
    alvos = dados.get("alvos", [])
    
    if 0 <= indice < len(alvos):
        removido = alvos.pop(indice)
        dados["alvos"] = alvos
        salvar_alvos_divulgacao_viral(dados)
        if EXIBIR_LOGS: logger.info(f"🗑️ Alvo viral removido com sucesso: {removido}")
        await message.answer(f"Alvo Viral '{removido}' excluído com sucesso!")
        await gerenciar_divulgacao_viral(message, state)
    else:
        await message.answer("Número inválido. Tente novamente:", reply_markup=teclado_cancelar)

@dp.message(ConfigDivulgacaoViral.menu_principal, F.text == "Editar Configs Viral ⚙️")
async def iniciar_edicao_spam_viral(message: types.Message, state: FSMContext):
    await message.answer("Deseja editar o Padrão Global ou configurar um Alvo Específico para o Viral?", reply_markup=teclado_tipo_edicao)
    await state.set_state(ConfigDivulgacaoViral.aguardando_tipo_edicao)

@dp.message(ConfigDivulgacaoViral.aguardando_tipo_edicao, F.text.in_(["Global 🌍", "Por Alvo 🎯"]))
async def selecionar_tipo_edicao_viral(message: types.Message, state: FSMContext):
    is_global = message.text == "Global 🌍"
    await state.update_data(edicao_global=is_global)
    
    dados = ler_alvos_divulgacao_viral()
    
    if is_global:
        freq_atual = dados.get("frequencia_por_hora", 0)
        rep_atual = dados.get("repeticoes_internas", 6)
        repl_atual = dados.get("replicas_mensagem", 5)
        
        texto_explicativo = (
            "🌍 <b>Edição do Padrão Global (Viral)</b>\n\n"
            "Envie os três valores juntos separados por vírgula nesta exata ordem:\n\n"
            "<b>1️⃣ Frequência:</b> Disparos por hora efetuados pelo bot.\n"
            "<b>2️⃣ Repetições:</b> Blocos de texto contidos na mensagem longa.\n"
            "<b>3️⃣ Réplicas:</b> Mensagens disparadas seguidas na mesma rajada.\n\n"
            f"<i>Exemplo com a sua configuração atual:</i>\n<code>{freq_atual}, {rep_atual}, {repl_atual}</code>"
        )
        await message.answer(texto_explicativo, reply_markup=teclado_cancelar, parse_mode="HTML")
        await state.set_state(ConfigDivulgacaoViral.aguardando_valores_unificados)
    else:
        alvos = dados.get("alvos", [])
        if not alvos:
            await message.answer("Não há alvos para editar. Adicione um primeiro.")
            await gerenciar_divulgacao_viral(message, state)
            return
        
        texto = "Qual alvo deseja personalizar? Digite o <b>NÚMERO</b> correspondente da lista abaixo:\n\n"
        for i, alvo in enumerate(alvos, 1):
            texto += f"{i}. {alvo}\n"
        await message.answer(texto, reply_markup=teclado_cancelar, parse_mode="HTML")
        await state.set_state(ConfigDivulgacaoViral.aguardando_selecao_alvo)

@dp.message(ConfigDivulgacaoViral.aguardando_selecao_alvo)
async def selecionar_alvo_edicao_viral(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas o NÚMERO.", reply_markup=teclado_cancelar)
        return
    indice = int(message.text) - 1
    dados = ler_alvos_divulgacao_viral()
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
            f"🎯 <b>Edição do Alvo (Viral):</b> {alvo_selecionado}\n\n"
            "Envie os três valores juntos separados por vírgula nesta exata ordem:\n\n"
            "<b>1️⃣ Frequência:</b> Disparos por hora efetuados pelo bot.\n"
            "<b>2️⃣ Repetições:</b> Blocos de texto contidos na mensagem longa.\n"
            "<b>3️⃣ Réplicas:</b> Mensagens disparadas seguidas na mesma rajada.\n\n"
            f"<i>Exemplo com a sua configuração atual:</i>\n<code>{freq_atual}, {rep_atual}, {repl_atual}</code>"
        )
        await message.answer(texto_explicativo, reply_markup=teclado_cancelar, parse_mode="HTML")
        await state.set_state(ConfigDivulgacaoViral.aguardando_valores_unificados)
    else:
        await message.answer("Número inválido. Tente novamente:", reply_markup=teclado_cancelar)

@dp.message(ConfigDivulgacaoViral.aguardando_valores_unificados)
async def salvar_valores_unificados_viral(message: types.Message, state: FSMContext):
    import re
    match = re.match(r"^(\d+)\s*,\s*(\d+)\s*,\s*(\d+)$", message.text.strip())
    
    if not match:
        await message.answer("Formato inválido. Envie os três números isolados por vírgula (Exemplo: 3, 6, 5).", reply_markup=teclado_cancelar)
        return
        
    freq, rep, repl = map(int, match.groups())
    
    data = await state.get_data()
    is_global = data.get("edicao_global")
    alvo = data.get("alvo_em_edicao")
    
    dados = ler_alvos_divulgacao_viral()
    if "config_alvos" not in dados:
        dados["config_alvos"] = {}
        
    if is_global:
        dados["frequencia_por_hora"] = freq
        dados["repeticoes_internas"] = rep
        dados["replicas_mensagem"] = repl
        msg_final = f"✅ <b>Padrão Global (Viral) atualizado!</b>\nFrequência: {freq}x/h | Repetições: {rep}x | Réplicas: {repl}x"
    else:
        if alvo not in dados["config_alvos"]:
            dados["config_alvos"][alvo] = {}
        dados["config_alvos"][alvo]["frequencia"] = freq
        dados["config_alvos"][alvo]["repeticoes"] = rep
        dados["config_alvos"][alvo]["replicas"] = repl
        msg_final = f"✅ <b>Alvo personalizado (Viral) atualizado!</b>\nAlvo: {alvo}\nFrequência: {freq}x/h | Repetições: {rep}x | Réplicas: {repl}x"
        
    salvar_alvos_divulgacao_viral(dados)
    if EXIBIR_LOGS: logger.info(f"⚙️ Configuração Viral salva. Global: {is_global} | Freq: {freq}, Rep: {rep}, Repl: {repl}")
    
    await message.answer(msg_final, parse_mode="HTML")
    await gerenciar_divulgacao_viral(message, state)

@dp.message(ConfigDivulgacaoViral.menu_principal, F.text == "Forçar Disparo Viral 🚀")
async def acionar_disparo_imediato_viral(message: types.Message):
    dados = ler_alvos_divulgacao_viral()
    dados["forcar_disparo"] = True
    salvar_alvos_divulgacao_viral(dados)
    if EXIBIR_LOGS: logger.info("🚀 Comando de disparo forçado enviado para o JSON do Viral.")
    await message.answer("🚀 <b>Disparo Imediato Viral Acionado!</b>\nO Userbot detectará o comando e enviará a rajada de convites.", parse_mode="HTML")

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
        "divulgar_gem": "Prompt GEM 🤖",
        "promo_viral": "Convite do Grupo Viral 🚀"
    }
    
    # Ordem de exibição forçada para organizar o painel
    ordem_exibicao = ["bom_dia", "incentivo", "link_grupo", "divulgar_gem", "promo_viral", "boa_noite"]
    
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
            [KeyboardButton(text="Editar Convite Viral 🚀"), KeyboardButton(text="Editar Boa Noite 🌙")],
            [KeyboardButton(text=texto_botao_pausa), KeyboardButton(text="Voltar às Configs 🔙")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    
    texto += "Selecione o que deseja editar abaixo:"
    await message.answer(texto, reply_markup=teclado_dinamico_rotina, parse_mode="HTML")
    await state.update_data(menu_origem="principal") # ✅ Adicione esta linha exata aqui
    await state.set_state(ConfigRotina.menu_principal)

@dp.message(ConfigRotina.menu_principal, F.text.in_(["Editar Bom Dia ☀️", "Editar Boa Noite 🌙", "Editar Incentivo 🔥", "Editar Convite 🔗", "Editar Prompt GEM 🤖", "Editar Convite Viral 🚀", "Editar Convite Afiliados 🚀", "Editar Convite do Grupo 🔗", "Editar Prompt GEM 🤖\u200b"]))
async def pedir_horario_rotina(message: types.Message, state: FSMContext):
    if EXIBIR_LOGS: logger.info(f"✏️ Iniciando edição da rotina: {message.text}")
    tipo_map = {
        "Editar Bom Dia ☀️": "bom_dia",
        "Editar Boa Noite 🌙": "boa_noite",
        "Editar Incentivo 🔥": "incentivo",
        "Editar Convite 🔗": "link_grupo",
        "Editar Prompt GEM 🤖": "divulgar_gem",
        "Editar Convite Viral 🚀": "promo_viral",
        "Editar Convite Afiliados 🚀": "promo_principal",
        "Editar Convite do Grupo 🔗": "link_grupo_viral",
        "Editar Prompt GEM 🤖\u200b": "divulgar_gem_viral"
    }
    tipo = tipo_map[message.text]
    
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
    await state.update_data(tipo_edicao=tipo)
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
    
    origem = data.get("menu_origem")
    await message.answer("✅ Configuração salva! Os novos horários já foram sorteados e agendados para hoje.")
    
    if origem == "espiao":
        await gerenciar_rotina_espiao(message, state)
    else:
        await gerenciar_rotina(message, state)

# --- SISTEMA DE GERENCIAMENTO DE FILA (INTERATIVO) ---
class GerenciarFilaFluxo(StatesGroup):
    menu_principal = State()
    aguardando_posicao_excluir = State()
    aguardando_confirmacao_exclusao = State()
    aguardando_posicao_editar = State()
    aguardando_nova_legenda = State()
    aguardando_posicao_reordenar = State()
    aguardando_nova_posicao = State()
    aguardando_confirmacao_reordenar = State()
    aguardando_data_posicao = State()
    aguardando_posicao_numeracao = State()
    aguardando_nova_numeracao = State()
    aguardando_posicao_publicar = State()
    aguardando_confirmacao_publicar = State()

teclado_gerenciar_fila = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Publicar Agora 🚀")],
        [KeyboardButton(text="Excluir Vídeo 🗑️")],
        [KeyboardButton(text="Editar Numeração 🔢"), KeyboardButton(text="Mover Posição ↕️")],
        [KeyboardButton(text="Editar Legenda ✏️"), KeyboardButton(text="Voltar 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

@dp.message(F.text == "Gerenciar Fila 📋", StateFilter("*"))
async def menu_gerenciar_fila(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    if EXIBIR_LOGS: logger.info("📋 Acessando o painel de gerenciamento de fila...")
    
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    texto = "📋 <b>Gerenciador de Fila de Postagens</b>\n"
    texto += f"Total de vídeos agendados: <b>{len(fila)}</b>\n\n"
    
    # --- CAPTURA DE BOM DIA / BOA NOITE ---
    from datetime import datetime
    agora = datetime.now(fuso_horario)
    hoje_str = agora.strftime("%Y-%m-%d")
    
    hora_bd, hora_bn = "Não agendado", "Não agendado"
    for job in scheduler.get_jobs():
        if job.id == 'job_rotina_bom_dia_0' and getattr(job, 'next_run_time', None):
            if job.next_run_time.astimezone(fuso_horario).date() == agora.date():
                hora_bd = job.next_run_time.astimezone(fuso_horario).strftime("%H:%M")
        if job.id == 'job_rotina_boa_noite_0' and getattr(job, 'next_run_time', None):
            if job.next_run_time.astimezone(fuso_horario).date() == agora.date():
                hora_bn = job.next_run_time.astimezone(fuso_horario).strftime("%H:%M")
    
    dados_rotina = ler_config_rotina()
    data_dia_br = agora.strftime("%d/%m")
    
    if dados_rotina.get("ultimo_bom_dia") == hoje_str:
        hora_exata_bd = dados_rotina.get("hora_ultimo_bom_dia")
        hora_bd = f"{hora_exata_bd}" if hora_exata_bd else "Indisponível"
        
    if dados_rotina.get("ultimo_boa_noite") == hoje_str:
        hora_exata_bn = dados_rotina.get("hora_ultimo_boa_noite")
        hora_bn = f"{hora_exata_bn}" if hora_exata_bn else "Indisponível"
        
    texto += f"☀️ <b>Bom Dia ({data_dia_br}):</b> {hora_bd}\n"
    texto += "━━━━━━━━━━━━━━━━━━\n"
    
    if fila:
        if EXIBIR_LOGS: logger.info("🔍 Lendo itens da fila para montagem do painel visual enriquecido...")
        import re
        
        dados_pausa = ler_pausa_programada()
        is_pausado = dados_pausa.get("ativa", False)
        
        imprimiu_bn = False
        
        for i, item in enumerate(fila, 1):
            legenda = item.get("legenda", "")
            data_adicao_str = item.get("data_adicao", "")
            is_postado = item.get("postado", False)
            
            # Identifica se o vídeo pertence ao dia de Hoje
            is_hoje = is_postado or data_adicao_str == "2000-01-01" or (data_adicao_str and data_adicao_str <= hoje_str)
            
            # Se for o primeiro vídeo de "Amanhã" (ou além) e ainda não imprimimos a tampa de Boa Noite, imprime agora
            if not is_hoje and not imprimiu_bn:
                texto += "━━━━━━━━━━━━━━━━━━\n"
                texto += f"🌙 <b>Boa Noite ({data_dia_br}):</b> {hora_bn}\n\n"
                imprimiu_bn = True
            
            # Extrai Número do Vídeo e Nome do Item da Legenda HTML
            match_video = re.search(r'(?i)Vídeo\s+\d+', legenda)
            match_item = re.search(r'📦\s*Item:\s*([^\n<]+)', legenda)
            
            nome_video = match_video.group(0).title() if match_video else "Vídeo ?"
            nome_item = match_item.group(1).strip() if match_item else "Sem descrição"
            
            if is_postado:
                horario_envio = item.get("horario_postagem", "Horário indisponível")
                status_previsao_final = f"✅ <b>Postado hoje às {horario_envio}</b>"
            else:
                if data_adicao_str == "2000-01-01":
                    data_br = "Manual (Prioridade)"
                elif data_adicao_str:
                    try:
                        data_br = datetime.strptime(data_adicao_str, "%Y-%m-%d").strftime("%d/%m/%Y")
                    except:
                        data_br = "Data desconhecida"
                else:
                    data_br = "Data desconhecida"
                    
                # Define a Previsão de Postagem base
                if is_pausado:
                    status_previsao = "Pausado 🛑"
                elif data_adicao_str == "2000-01-01" or data_adicao_str <= hoje_str:
                    status_previsao = "Hoje 🟢"
                else:
                    from datetime import timedelta
                    amanha_str = (agora + timedelta(days=1)).strftime("%Y-%m-%d")
                    if data_adicao_str == amanha_str:
                        status_previsao = "Amanhã 🟡"
                    else:
                        status_previsao = "Depois de Amanhã 🔵"

                # Interrogação Silenciosa do Motor para extrair a hora exata
                hora_agendada_str = ""
                job_id_esperado = f"job_fila_postagem_{item.get('id')}"
                job_encontrado = scheduler.get_job(job_id_esperado)
                
                if job_encontrado and getattr(job_encontrado, 'next_run_time', None):
                    hora_exata = job_encontrado.next_run_time.astimezone(fuso_horario).strftime("%H:%M")
                    hora_agendada_str = f" às {hora_exata}"
                    
                status_previsao_final = f"{status_previsao}{hora_agendada_str}"
                
            texto += f"<b>{i}. {nome_video}</b> | 📦 {nome_item[:25]}...\n"
            if is_postado:
                texto += f"   └ Status: {status_previsao_final}\n\n"
            else:
                texto += f"   └ Lote (Data-Alvo): {data_br} | Previsão: {status_previsao_final}\n\n"
                
        # Se terminou de varrer toda a fila e não encontrou vídeos de "Amanhã", a tampa do Boa Noite vai no final
        if not imprimiu_bn:
            texto += "━━━━━━━━━━━━━━━━━━\n"
            texto += f"🌙 <b>Boa Noite ({data_dia_br}):</b> {hora_bn}\n\n"
            
        if EXIBIR_LOGS: logger.info("✅ Painel visual da fila montado com metadados e fronteiras com sucesso.")
    else:
        texto += "\n<i>A sua fila está completamente vazia no momento.</i>\n\n"
        texto += "━━━━━━━━━━━━━━━━━━\n"
        texto += f"🌙 <b>Boa Noite ({data_dia_br}):</b> {hora_bn}\n\n"
        if EXIBIR_LOGS: logger.info("⚠️ Fila vazia detectada ao montar o painel.")

    texto += "O que deseja fazer com a fila?"

    await message.answer(texto, reply_markup=teclado_gerenciar_fila, parse_mode="HTML")
    await state.set_state(GerenciarFilaFluxo.menu_principal)

@dp.message(GerenciarFilaFluxo.menu_principal, F.text == "Voltar 🔙")
async def sair_menu_fila(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Painel de Controle atualizado.", reply_markup=obter_teclado_principal())

async def aplicar_renumeracao_e_salvar(fila, message, state, numero_base=None):
    import re
    if EXIBIR_LOGS: logger.info("🔄 Iniciando auto-correção da numeração da fila...")
    
    if numero_base is not None:
        menor_numero = numero_base
    else:
        menor_numero = float('inf')
        for f_item in fila:
            match = re.search(r'(?i)Vídeo\s+(\d+)', f_item.get("legenda", ""))
            if match:
                num = int(match.group(1))
                if num < menor_numero:
                    menor_numero = num
                
        if menor_numero == float('inf'):
            async with _lock_contador:
                menor_numero = ler_contador()
            
    numero_atual_cascata = menor_numero
    for i in range(len(fila)):
        legenda_antiga = fila[i].get("legenda", "")
        nova_legenda = re.sub(r'(?i)(Vídeo\s+)\d+', rf'\g<1>{numero_atual_cascata}', legenda_antiga, count=1)
        fila[i]["legenda"] = nova_legenda
        numero_atual_cascata += 1
        
    fila_data = ler_fila_postagens()
    fila_data["fila"] = fila
    salvar_fila_postagens(fila_data)
    
    async with _lock_contador:
        salvar_contador(numero_atual_cascata)
    
    if EXIBIR_LOGS: logger.info(f"✅ Auto-correção concluída. Próxima postagem: {numero_atual_cascata}.")
    
    agendar_fila_postagens() 
    
    await message.answer(f"✅ Operação concluída com sucesso!\n🔄 A numeração de toda a fila foi corrigida em cascata e os horários recalculados.")
    await menu_gerenciar_fila(message, state)

# ✅ NOVO: Muralha de Segurança - Trava todas as edições se a fila estiver vazia
@dp.message(GerenciarFilaFluxo.menu_principal, F.text.in_(["Publicar Agora 🚀", "Excluir Vídeo 🗑️", "Editar Numeração 🔢", "Mover Posição ↕️", "Editar Legenda ✏️"]))
async def trava_fila_vazia(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    # Verifica se a fila está vazia ou se só tem vídeos já postados
    videos_pendentes = [item for item in fila if not item.get("postado", False)]
    
    if not videos_pendentes:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Fila: Tentativa de usar '{message.text}' bloqueada (Fila vazia).")
        await message.answer(f"⚠️ <b>Ação Bloqueada:</b> A sua fila de vídeos está vazia no momento.\n\nNão há nenhum vídeo agendado para poder utilizar a função de {message.text.split(' ')[1]}.", parse_mode="HTML")
        await menu_gerenciar_fila(message, state) # Recarrega o menu principal da fila
        return
        
    # 🔁 Roteamento Inteligente (Se tiver vídeos, ele deixa passar para o handler correto)
    if message.text == "Excluir Vídeo 🗑️":
        await pedir_exclusao_fila(message, state)
    elif message.text == "Editar Legenda ✏️":
        await pedir_edicao_fila(message, state)
    elif message.text == "Mover Posição ↕️":
        await pedir_reordenar_fila(message, state)
    elif message.text == "Editar Numeração 🔢":
        await pedir_edicao_numeracao_fila(message, state)
    elif message.text == "Publicar Agora 🚀":
        await pedir_posicao_publicar(message, state)

async def pedir_exclusao_fila(message: types.Message, state: FSMContext):
    await message.answer("Digite o <b>NÚMERO</b> da posição do vídeo que deseja excluir:", reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(GerenciarFilaFluxo.aguardando_posicao_excluir)

@dp.message(GerenciarFilaFluxo.aguardando_posicao_excluir)
async def confirmar_posicao_exclusao_fila(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas números.", reply_markup=teclado_cancelar)
        return
        
    posicao = int(message.text) - 1
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    if 0 <= posicao < len(fila):
        import re
        if fila[posicao].get("postado", False):
            if EXIBIR_LOGS: logger.warning(f"⚠️ Fila: Tentativa de excluir vídeo já postado na posição {posicao+1} bloqueada.")
            await message.answer("⚠️ <b>Ação Bloqueada:</b> Este vídeo já foi postado e serve apenas como histórico. Por favor, escolha outro número ou clique em Cancelar ❌.", parse_mode="HTML")
            return
            
        legenda = fila[posicao].get("legenda", "")
        if legenda:
            legenda_limpa = re.sub(r'<[^>]+>', '', legenda)
            resumo = legenda_limpa.split('\n')[0][:50]
        else:
            resumo = "Vídeo sem descrição"
            
        await state.update_data(posicao_excluir=posicao)
        if EXIBIR_LOGS: logger.info(f"🗑️ Fila: Solicitação de exclusão para posição {posicao+1} iniciada. Aguardando confirmação.")
        
        teclado_confirmacao_exclusao = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Aprovar Exclusão ✅"), KeyboardButton(text="Cancelar ❌")]],
            resize_keyboard=True,
            is_persistent=True
        )
        
        await message.answer(f"Você selecionou o vídeo na posição <b>{posicao+1}</b>:\n📝 <i>{resumo}...</i>\n\nTem certeza de que deseja excluir este vídeo da fila?", reply_markup=teclado_confirmacao_exclusao, parse_mode="HTML")
        await state.set_state(GerenciarFilaFluxo.aguardando_confirmacao_exclusao)
    else:
        await message.answer("Número de posição inválido. Tente novamente:", reply_markup=teclado_cancelar)

@dp.message(GerenciarFilaFluxo.aguardando_confirmacao_exclusao)
async def processar_exclusao_fila(message: types.Message, state: FSMContext):
    if message.text != "Aprovar Exclusão ✅":
        await message.answer("Por favor, utilize os botões abaixo para aprovar ou cancelar a exclusão.")
        return
        
    data = await state.get_data()
    posicao = data.get("posicao_excluir")
    
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    if posicao is not None and 0 <= posicao < len(fila):
        import re
        
        # 🔍 Congela o menor número da fila ANTES de apagar o vídeo
        menor_numero_antes = float('inf')
        for f_item in fila:
            match = re.search(r'(?i)Vídeo\s+(\d+)', f_item.get("legenda", ""))
            if match:
                num = int(match.group(1))
                if num < menor_numero_antes:
                    menor_numero_antes = num
                    
        if menor_numero_antes == float('inf'):
            menor_numero_antes = None

        item_removido = fila.pop(posicao)
        caminho_video = item_removido.get("caminho_video")
        
        if caminho_video and os.path.exists(caminho_video):
            ainda_usado = any(x.get("caminho_video") == caminho_video for x in fila)
            if not ainda_usado:
                os.remove(caminho_video)
                if EXIBIR_LOGS: logger.info("🧹 Fila: Ficheiro físico excluído após remoção manual com confirmação dupla.")
                
        if EXIBIR_LOGS: logger.info(f"🗑️ Fila: Vídeo na posição {posicao+1} removido com sucesso.")
        
        await aplicar_renumeracao_e_salvar(fila, message, state, numero_base=menor_numero_antes)
    else:
        await message.answer("Erro de sincronização. Operação cancelada.")
        await menu_gerenciar_fila(message, state)

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
        if fila[posicao].get("postado", False):
            if EXIBIR_LOGS: logger.warning(f"⚠️ Fila: Tentativa de editar legenda de vídeo já postado na posição {posicao+1} bloqueada.")
            await message.answer("⚠️ <b>Ação Bloqueada:</b> Este vídeo já foi postado e serve apenas como histórico. Por favor, escolha outro número ou clique em Cancelar ❌.", parse_mode="HTML")
            return
            
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
        
        await message.answer("✅ Legenda atualizada com sucesso!")
        await menu_gerenciar_fila(message, state)
    else:
        await message.answer("Erro de sincronização. Operação cancelada.")
        await menu_gerenciar_fila(message, state)

async def pedir_reordenar_fila(message: types.Message, state: FSMContext):
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    # Descobre quantos vídeos realmente faltam postar
    indices_pendentes = [i for i, item in enumerate(fila) if not item.get("postado", False)]
    
    # 🚀 ATALHO INTELIGENTE: Se só existe 1 vídeo, pula as perguntas de posição!
    if len(indices_pendentes) == 1:
        posicao_unica = indices_pendentes[0]
        await state.update_data(posicao_origem=posicao_unica, nova_posicao=posicao_unica)
        
        agora = datetime.now(fuso_horario)
        hoje_str = agora.strftime("%Y-%m-%d")
        
        dados_rotina = ler_config_rotina()
        expediente_encerrado = dados_rotina.get("ultimo_boa_noite") == hoje_str
        
        opcoes = []
        if not expediente_encerrado:
            opcoes.append("Hoje 🟢")
        opcoes.append("Amanhã 🟡")
        
        # Adiciona os próximos 3 dias para dar flexibilidade
        for i in range(2, 5):
            d_futuro = agora + timedelta(days=i)
            opcoes.append(f"{d_futuro.strftime('%d/%m/%Y')} 🔵")
            
        botoes = [[KeyboardButton(text=op)] for op in opcoes[:3]] # Primeira linha com 3 botões
        if len(opcoes) > 3:
            botoes.append([KeyboardButton(text=op) for op in opcoes[3:]]) # Segunda linha com os restantes
        botoes.append([KeyboardButton(text="Cancelar ❌")])
        
        teclado_escolha_data = ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)
        
        if EXIBIR_LOGS: logger.info("↕️ Fila: Atalho acionado (Apenas 1 vídeo na fila). Pulando perguntas de posição.")
        await message.answer("Como há <b>apenas 1 vídeo pendente</b>, não é necessário escolher posições.\n\nPara quando deseja agendar este vídeo?", reply_markup=teclado_escolha_data, parse_mode="HTML")
        await state.set_state(GerenciarFilaFluxo.aguardando_data_posicao)
        return

    # Comportamento normal se houver mais de 1 vídeo
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
        import re
        if fila[posicao_atual].get("postado", False):
            if EXIBIR_LOGS: logger.warning(f"⚠️ Fila: Tentativa de mover vídeo já postado na posição {posicao_atual+1} bloqueada.")
            await message.answer("⚠️ <b>Ação Bloqueada:</b> Este vídeo já foi postado e serve apenas como histórico. Por favor, escolha outro número ou clique em Cancelar ❌.", parse_mode="HTML")
            return
            
        legenda = fila[posicao_atual].get("legenda", "")
        if legenda:
            legenda_limpa = re.sub(r'<[^>]+>', '', legenda)
            resumo = legenda_limpa.split('\n')[0][:50]
        else:
            resumo = "Vídeo sem descrição"
            
        await state.update_data(posicao_origem=posicao_atual)
        if EXIBIR_LOGS: logger.info(f"↕️ Fila: Posição de origem {posicao_atual+1} selecionada para mover.")
        await message.answer(f"O vídeo selecionado na posição <b>{posicao_atual+1}</b> é:\n📝 <i>{resumo}...</i>\n\nPara qual posição deseja enviá-lo? (Ex: 1 para o topo)", reply_markup=teclado_cancelar, parse_mode="HTML")
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
        
        await state.update_data(nova_posicao=nova_posicao)
        
        agora = datetime.now(fuso_horario)
        hoje_str = agora.strftime("%Y-%m-%d")
        amanha_str = (agora + timedelta(days=1)).strftime("%Y-%m-%d")
        
        dados_rotina = ler_config_rotina()
        expediente_encerrado = dados_rotina.get("ultimo_boa_noite") == hoje_str
        
        fila_simulada = fila.copy()
        item_movido = fila_simulada.pop(posicao_origem)
        
        if len(fila_simulada) == 0:
            nova_data_adicao = amanha_str if expediente_encerrado else "2000-01-01"
            await state.update_data(nova_data_adicao=nova_data_adicao)
            await enviar_confirmacao_reordenar(message, state, fila, posicao_origem, nova_posicao)
            return
        
        prev_idx = nova_posicao - 1
        next_idx = nova_posicao
        
        data_min_str = fila_simulada[prev_idx].get("data_adicao", "2000-01-01") if prev_idx >= 0 else "2000-01-01"
        data_max_str = fila_simulada[next_idx].get("data_adicao") if next_idx < len(fila_simulada) else None
        
        if data_min_str == "2000-01-01" or data_min_str < hoje_str:
            data_min_str = hoje_str
            
        data_min_obj = datetime.strptime(data_min_str, "%Y-%m-%d")
        
        if data_max_str is None or data_max_str == "2000-01-01":
            data_max_obj = data_min_obj + timedelta(days=1)
        else:
            data_max_obj = datetime.strptime(data_max_str, "%Y-%m-%d")
            
        if data_max_obj < data_min_obj:
            data_max_obj = data_min_obj
            
        opcoes = []
        d_atual = data_min_obj
        while d_atual <= data_max_obj:
            d_str = d_atual.strftime("%Y-%m-%d")
            if d_str == hoje_str:
                opcoes.append("Hoje 🟢")
            elif d_str == amanha_str:
                opcoes.append("Amanhã 🟡")
            else:
                opcoes.append(f"{d_atual.strftime('%d/%m/%Y')} 🔵")
            d_atual += timedelta(days=1)
            if len(opcoes) >= 3: 
                break

        if expediente_encerrado:
            opcoes = [op for op in opcoes if "Hoje" not in op]
            if not opcoes:
                opcoes = ["Amanhã 🟡"]
                
        if len(opcoes) == 1:
            escolha = opcoes[0]
            if escolha == "Hoje 🟢": nova_data_adicao = "2000-01-01"
            elif escolha == "Amanhã 🟡": nova_data_adicao = amanha_str
            else: nova_data_adicao = (agora + timedelta(days=2)).strftime("%Y-%m-%d")
            
            await state.update_data(nova_data_adicao=nova_data_adicao)
            await enviar_confirmacao_reordenar(message, state, fila, posicao_origem, nova_posicao)
        else:
            botoes = [[KeyboardButton(text=op)] for op in opcoes]
            botoes.append([KeyboardButton(text="Cancelar ❌")])
            teclado_escolha_data = ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)
            await message.answer(f"O vídeo será movido para a posição {nova_posicao+1}.\nPara quando deseja agendar este vídeo nesta nova posição?", reply_markup=teclado_escolha_data)
            await state.set_state(GerenciarFilaFluxo.aguardando_data_posicao)
    else:
        await message.answer("Erro de sincronização. Operação cancelada.")
        await menu_gerenciar_fila(message, state)

@dp.message(GerenciarFilaFluxo.aguardando_data_posicao)
async def processar_data_posicao_fila(message: types.Message, state: FSMContext):
    texto = message.text
    if "Hoje" in texto or "Amanhã" in texto or "🔵" in texto:
        pass
    else:
        await message.answer("Por favor, escolha uma opção válida através dos botões.")
        return

    data = await state.get_data()
    posicao_origem = data.get("posicao_origem")
    nova_posicao = data.get("nova_posicao")
    
    agora = datetime.now(fuso_horario)
    
    if "Hoje" in texto: 
        nova_data_adicao = "2000-01-01"
    elif "Amanhã" in texto: 
        nova_data_adicao = (agora + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        import re
        match = re.search(r'(\d{2}/\d{2}/\d{4})', texto)
        if match:
            nova_data_adicao = datetime.strptime(match.group(1), "%d/%m/%Y").strftime("%Y-%m-%d")
        else:
            nova_data_adicao = (agora + timedelta(days=2)).strftime("%Y-%m-%d")
            
    await state.update_data(nova_data_adicao=nova_data_adicao)
    
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    await enviar_confirmacao_reordenar(message, state, fila, posicao_origem, nova_posicao)

async def enviar_confirmacao_reordenar(message: types.Message, state: FSMContext, fila, posicao_origem, nova_posicao):
    import re
    from datetime import datetime
    legenda = fila[posicao_origem].get("legenda", "")
    if legenda:
        legenda_limpa = re.sub(r'<[^>]+>', '', legenda)
        resumo = legenda_limpa.split('\n')[0][:50]
    else:
        resumo = "Vídeo sem descrição"

    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar Mudança ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    
    data = await state.get_data()
    nova_data_adicao = data.get("nova_data_adicao")
    
    # Formata a data para ficar amigável na mensagem de confirmação
    if nova_data_adicao == "2000-01-01":
        data_amigavel = "Imediato/Hoje"
    else:
        data_amigavel = datetime.strptime(nova_data_adicao, "%Y-%m-%d").strftime("%d/%m/%Y")
    
    texto = f"Você está prestes a alterar o agendamento do vídeo:\n📝 <i>{resumo}...</i>\n\n"
    
    # Só exibe a mudança de posição se ela realmente mudou
    if posicao_origem != nova_posicao:
        texto += f"Da posição <b>{posicao_origem + 1}</b> ➡️ Para a posição <b>{nova_posicao + 1}</b>.\n"
        
    texto += f"🗓️ Nova Data Alvo: <b>{data_amigavel}</b>\n\n"
    texto += "Confirma essa alteração?"
    
    if EXIBIR_LOGS: logger.info(f"↕️ Fila: Coleta finalizada. Pedindo confirmação para confirmar as alterações.")
    await message.answer(texto, reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(GerenciarFilaFluxo.aguardando_confirmacao_reordenar)

@dp.message(GerenciarFilaFluxo.aguardando_confirmacao_reordenar)
async def processar_confirmacao_reordenar(message: types.Message, state: FSMContext):
    if message.text != "Aprovar Mudança ✅":
        await message.answer("Por favor, clique em Aprovar ou Cancelar.")
        return

    data = await state.get_data()
    posicao_origem = data.get("posicao_origem")
    nova_posicao = data.get("nova_posicao")
    nova_data_adicao = data.get("nova_data_adicao")

    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])

    if 0 <= posicao_origem < len(fila):
        fila_simulada = fila.copy()
        item_movido = fila_simulada.pop(posicao_origem)
        item_movido["data_adicao"] = nova_data_adicao
        fila_simulada.insert(nova_posicao, item_movido)
        
        if EXIBIR_LOGS: logger.info(f"↕️ Fila: Confirmação recebida. Vídeo movido com sucesso para a posição {nova_posicao+1}.")
        await aplicar_renumeracao_e_salvar(fila_simulada, message, state)
    else:
        await message.answer("Erro de sincronização. Operação cancelada.")
        await menu_gerenciar_fila(message, state)

async def pedir_edicao_numeracao_fila(message: types.Message, state: FSMContext):
    await message.answer("Digite o <b>NÚMERO</b> da posição do vídeo na fila que deseja alterar a numeração:", reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(GerenciarFilaFluxo.aguardando_posicao_numeracao)

@dp.message(GerenciarFilaFluxo.aguardando_posicao_numeracao)
async def pedir_novo_numero_fila(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas números.", reply_markup=teclado_cancelar)
        return
        
    posicao = int(message.text) - 1
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    if 0 <= posicao < len(fila):
        import re
        if fila[posicao].get("postado", False):
            if EXIBIR_LOGS: logger.warning(f"⚠️ Fila: Tentativa de editar numeração de vídeo já postado na posição {posicao+1} bloqueada.")
            await message.answer("⚠️ <b>Ação Bloqueada:</b> Este vídeo já foi postado e serve apenas como histórico. Por favor, escolha outro número ou clique em Cancelar ❌.", parse_mode="HTML")
            return
            
        legenda = fila[posicao].get("legenda", "")
        if legenda:
            legenda_limpa = re.sub(r'<[^>]+>', '', legenda)
            resumo = legenda_limpa.split('\n')[0][:50]
        else:
            resumo = "Vídeo sem descrição"
            
        await state.update_data(posicao_numeracao=posicao)
        if EXIBIR_LOGS: logger.info(f"🔢 Fila: Posição {posicao+1} selecionada para edição de numeração.")
        await message.answer(f"O vídeo selecionado na posição <b>{posicao+1}</b> é:\n📝 <i>{resumo}...</i>\n\nQual será o <b>NOVO NÚMERO</b> deste vídeo?", reply_markup=teclado_cancelar, parse_mode="HTML")
        await state.set_state(GerenciarFilaFluxo.aguardando_nova_numeracao)
    else:
        await message.answer("Número de posição inválido. Tente novamente:", reply_markup=teclado_cancelar)

@dp.message(GerenciarFilaFluxo.aguardando_nova_numeracao)
async def salvar_nova_numeracao_fila(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas números.", reply_markup=teclado_cancelar)
        return
        
    novo_numero_inicial = int(message.text)
    data = await state.get_data()
    posicao = data.get("posicao_numeracao")
    
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    import re
    
    if 0 <= posicao < len(fila):
        if EXIBIR_LOGS: logger.info(f"🔄 Iniciando renumeração em cascata a partir da posição {posicao+1} com o número {novo_numero_inicial}...")
        
        numero_atual_cascata = novo_numero_inicial
        
        # Percorre a fila apenas a partir do vídeo selecionado para baixo
        for i in range(posicao, len(fila)):
            legenda_antiga = fila[i].get("legenda", "")
            nova_legenda = re.sub(r'(?i)(Vídeo\s+)\d+', rf'\g<1>{numero_atual_cascata}', legenda_antiga, count=1)
            fila[i]["legenda"] = nova_legenda
            if EXIBIR_LOGS: logger.info(f"✏️ Fila: Posição {i+1} atualizada para Vídeo {numero_atual_cascata}.")
            numero_atual_cascata += 1
            
        salvar_fila_postagens(fila_data)
        
        # Sincroniza o contador global para que a próxima postagem assuma o último número +1
        async with _lock_contador:
            salvar_contador(numero_atual_cascata)
        
        if EXIBIR_LOGS: logger.info(f"✅ Renumeração concluída! Contador global ajustado para a próxima postagem virgem: {numero_atual_cascata}.")
        
        await message.answer(f"✅ Numeração atualizada em cascata a partir do vídeo {novo_numero_inicial} com sucesso!")
        await menu_gerenciar_fila(message, state)
    else:
        await message.answer("Erro de sincronização. Operação cancelada.")
        await menu_gerenciar_fila(message, state)

async def pedir_posicao_publicar(message: types.Message, state: FSMContext):
    await message.answer("Digite o <b>NÚMERO</b> da posição do vídeo na fila que deseja publicar imediatamente:", reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(GerenciarFilaFluxo.aguardando_posicao_publicar)

@dp.message(GerenciarFilaFluxo.aguardando_posicao_publicar)
async def preparar_publicacao_imediata(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas números.", reply_markup=teclado_cancelar)
        return
        
    posicao = int(message.text) - 1
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    if 0 <= posicao < len(fila):
        import re
        if fila[posicao].get("postado", False):
            if EXIBIR_LOGS: logger.warning(f"⚠️ Fila: Tentativa de publicar novamente vídeo já postado na posição {posicao+1} bloqueada.")
            await message.answer("⚠️ <b>Ação Bloqueada:</b> Este vídeo já foi postado e serve apenas como histórico. Por favor, escolha outro número ou clique em Cancelar ❌.", parse_mode="HTML")
            return
            
        legenda = fila[posicao].get("legenda", "")
        if legenda:
            legenda_limpa = re.sub(r'<[^>]+>', '', legenda)
            resumo = legenda_limpa.split('\n')[0][:50]
        else:
            resumo = "Vídeo sem descrição"
            
        await state.update_data(posicao_publicar=posicao)
        if EXIBIR_LOGS: logger.info(f"🚀 Fila: Preparando publicação antecipada para a posição {posicao+1}.")
        
        teclado_confirmacao_publicar = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Publicar Vídeo 🚀"), KeyboardButton(text="Cancelar ❌")]],
            resize_keyboard=True,
            is_persistent=True
        )
        
        await message.answer(f"Você selecionou o vídeo na posição <b>{posicao+1}</b>:\n📝 <i>{resumo}...</i>\n\nTem certeza de que deseja publicar este vídeo agora mesmo e recalcular o restante da fila?", reply_markup=teclado_confirmacao_publicar, parse_mode="HTML")
        await state.set_state(GerenciarFilaFluxo.aguardando_confirmacao_publicar)
    else:
        await message.answer("Número de posição inválido. Tente novamente:", reply_markup=teclado_cancelar)

@dp.message(GerenciarFilaFluxo.aguardando_confirmacao_publicar)
async def processar_publicacao_imediata(message: types.Message, state: FSMContext):
    if message.text != "Publicar Vídeo 🚀":
        await message.answer("Por favor, utilize os botões abaixo para aprovar ou cancelar a publicação.")
        return

    data = await state.get_data()
    posicao = data.get("posicao_publicar")

    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    import re
    
    if posicao is not None and 0 <= posicao < len(fila):
        item = fila[posicao]
        
        # 1. Preserva o número original do vídeo (ignora o contador global)
        legenda_disparo = item.get("legenda", "")
        
        if EXIBIR_LOGS: logger.info(f"🚀 Iniciando antecipação do vídeo na posição {posicao+1}. Mantendo a numeração original.")
        
        caminho_video = item.get("caminho_video")
        video_id = item.get("video_id")
        
        msg_status = await message.answer("📤 A preparar ficheiros e a publicar o vídeo agora mesmo... Aguarde.", reply_markup=teclado_cancelar)
        
        sucesso_upload = False
        try:
            # 2. Disparo imediato para o Telegram com a legenda original
            if caminho_video and os.path.exists(caminho_video):
                arquivo = FSInputFile(caminho_video)
                msg = await bot.send_video(chat_id=GRUPO_ID, video=arquivo, caption=legenda_disparo, parse_mode="HTML")
                sucesso_upload = True
                
                novo_file_id = msg.video.file_id
                for x in fila:
                    if x.get("caminho_video") == caminho_video:
                        x["video_id"] = novo_file_id
                        x["caminho_video"] = None
            elif video_id:
                await bot.send_video(chat_id=GRUPO_ID, video=video_id, caption=legenda_disparo, parse_mode="HTML")
                sucesso_upload = True
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Falha no disparo imediato: {e}")
            await msg_status.delete()
            await message.answer(f"Ocorreu um erro técnico ao publicar o vídeo: {e}")
            await menu_gerenciar_fila(message, state)
            return
            
        await msg_status.delete()
            
        if sucesso_upload:
            if EXIBIR_LOGS: logger.info("✅ Vídeo antecipado submetido com sucesso no grupo.")
            
            # 3. Preserva o vídeo no histórico em vez de excluí-lo
            agora_manual = datetime.now(fuso_horario)
            item["postado"] = True
            item["horario_postagem"] = agora_manual.strftime("%H:%M")
            item["data_postagem"] = agora_manual.strftime("%Y-%m-%d") # ✅ NOVO: Registra o dia para a faxina
            if EXIBIR_LOGS: logger.info(f"🚀 Vídeo da posição {posicao+1} marcado como 'postado' às {item['horario_postagem']} no histórico.")
            
            if caminho_video and os.path.exists(caminho_video):
                ainda_usado = any(x.get("caminho_video") == caminho_video and not x.get("postado", False) for x in fila)
                if not ainda_usado:
                    try:
                        os.remove(caminho_video)
                        if EXIBIR_LOGS: logger.info("🧹 Ficheiro físico removido do servidor após o disparo antecipado.")
                    except:
                        pass
            
            fila_data["fila"] = fila
            salvar_fila_postagens(fila_data)
            
            # 4. Recálculo da fragmentação da hora para alocar o buraco (sem corromper os outros números)
            agendar_fila_postagens()
            
            await message.answer("🚀 Publicação realizada com sucesso!\n✅ O vídeo foi marcado como postado no histórico e a grade de horários de hoje foi reajustada.")
            await menu_gerenciar_fila(message, state)
    else:
        await message.answer("Erro de sincronização ou posição inválida. Operação cancelada.")
        await menu_gerenciar_fila(message, state)

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
        
    # ✅ NOVO: Trava de Silêncio do Mundo Viral (Radar de 15 minutos)
    agora_tz = datetime.now(fuso_horario)
    rotinas_virais = ["job_rotina_promo_principal", "job_rotina_link_grupo_viral", "job_rotina_divulgar_gem_viral"]
    conflito_silencio = False
    
    for job in scheduler.get_jobs():
        if any(rv in job.id for rv in rotinas_virais) and getattr(job, 'next_run_time', None):
            tempo_rotina = job.next_run_time.astimezone(fuso_horario)
            if abs((agora_tz - tempo_rotina).total_seconds() / 60) <= 15:
                conflito_silencio = True
                break
                
    if conflito_silencio:
        if EXIBIR_LOGS: logger.info(f"🤫 [Espião] Trava de Silêncio ativada! O motor detectou uma rotina Viral a ±15min. Adormecendo clone {item_id} temporariamente...")
        return # Aborta silenciosamente e tenta novamente na próxima varredura de 1 minuto
        
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
            
        if EXIBIR_LOGS: logger.info("🚀 Preparando prompt com a lista estrita de setores e blindagem semântica...")
            
        prompt = (
            "Assista ao vídeo e identifique qual é o produto demonstrado. "
            "Sua resposta deve conter EXATAMENTE duas linhas.\n"
            "Na primeira linha, escreva APENAS o nome do produto acompanhado de um emoji correspondente no início (Exemplo: 👟 Tênis Casual Feminino).\n"
            "Na segunda linha, inclua as hashtags correspondentes aos setores do produto. IMPORTANTE: Se utilizar mais de uma hashtag, separe-as APENAS com espaços em branco, NUNCA utilize vírgulas.\n"
            "REGRA DE CONTEXTO: Categorize o produto baseando-se estritamente na sua utilidade prática e ambiente de uso. É terminantemente proibido utilizar atalhos semânticos ou associações literais de palavras (exemplo prático: um organizador de sacos plásticos de cozinha pertence a #CasaEDecoracao e NUNCA a #BolsasFemininas, pois não é um acessório de moda).\n"
            "REGRA ABSOLUTA: Você só pode escolher as hashtags desta lista exata, podendo combinar mais de uma se aplicável: "
            "#RoupasFemininas, #SapatosFemininos, #CelularesEDispositivos, #AcessoriosParaVeiculos, #Relogios, "
            "#AlimentosEBebidas, #CasaEDecoracao, #SapatosMasculinos, #EsportesELazer, #BolsasMasculinas, #BolsasFemininas, "
            "#RoupasPlusSize, #ModaInfantil, #Eletrodomesticos, #Motocicletas, #AnimaisDomesticos, #CamerasEDrones, #Beleza, "
            "#AcessoriosDeModa, #BrinquedosEHobbies, #Papelaria, #LivrosERevistas, #RoupasMasculinas, #Automoveis, #MaeEBebe, "
            "#ComputadoresEAcessorios, #Saude, #ViagensEBagagens, #JogosEConsoles, #Audio.\n"
            "É estritamente proibido criar textos de vendas, descrições, inventar novas hashtags, usar gatilhos mentais ou adicionar frases de encerramento."
        )
        
        if EXIBIR_LOGS: logger.info("✅ Prompt blindado e atualizado. Iniciando requisição à IA...")
        
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
        texto_ia = "🛍️ Vídeo do Produto\n#Oferta"
        
    # Fatiar o texto da IA para separar o Nome das Hashtags
    linhas_ia = texto_ia.split('\n')
    nome_produto = linhas_ia[0].strip()
    hashtags = '\n'.join(linhas_ia[1:]).strip() if len(linhas_ia) > 1 else ""
    
    # Montagem da legenda com a nova estética estruturada
    legenda_postagem = f"<b>{nome_produto}</b>\n\n🔗 <b>Link do Produto:</b>\n{link_final}"
    
    # Adiciona as hashtags em itálico no rodapé, caso existam
    if hashtags:
        legenda_postagem += f"\n\n<i>{hashtags}</i>"
    
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

async def sincronizar_financeiro_horario():
    if EXIBIR_LOGS: logger.info("⏰ [Financeiro] Iniciando varredura horária de pendências na API da Shopee...")
    
    historico = ler_historico_financeiro()
    agora = datetime.now(fuso_horario)
    
    ontem_str = (agora - timedelta(days=1)).strftime("%Y-%m-%d")
    anteontem_str = (agora - timedelta(days=2)).strftime("%Y-%m-%d")
    
    precisa_verificar = False
    
    dados_ontem = historico.get(ontem_str)
    dados_anteontem = historico.get(anteontem_str)
    
    if not dados_ontem or (isinstance(dados_ontem, dict) and dados_ontem.get("aprovado", 0.0) + dados_ontem.get("pendente", 0.0) == 0.0):
        precisa_verificar = True
    if not dados_anteontem:
        precisa_verificar = True
        
    if not precisa_verificar:
        if EXIBIR_LOGS: logger.info("✅ [Financeiro] Dados recentes já consolidados. Varredura suspensa.")
        return
        
    if EXIBIR_LOGS: logger.info("🔍 [Financeiro] Valores pendentes detectados. Consultando a API...")
    conversoes = await buscar_dados_financeiros_shopee(3)
    
    if not conversoes:
        return
        
    diario_api = {
        ontem_str: {"aprovado": 0.0, "pendente": 0.0, "cancelado": 0.0, "shopee": 0.0, "vendedor": 0.0, "qtd_aprovado": 0, "qtd_pendente": 0, "qtd_cancelado": 0, "clicks": 0},
        anteontem_str: {"aprovado": 0.0, "pendente": 0.0, "cancelado": 0.0, "shopee": 0.0, "vendedor": 0.0, "qtd_aprovado": 0, "qtd_pendente": 0, "qtd_cancelado": 0, "clicks": 0}
    }
    
    for conv in conversoes:
        orders = conv.get("orders", [])
        if not orders: continue
        
        c_total = float(conv.get("totalCommission", "0"))
        c_shopee = float(conv.get("shopeeCommissionCapped", "0"))
        c_extra = float(conv.get("sellerCommission", "0"))
        dt_obj = datetime.fromtimestamp(conv.get("purchaseTime", 0), tz=fuso_horario)
        dt_db_str = dt_obj.strftime("%Y-%m-%d")
        
        if dt_db_str in diario_api:
            if EXIBIR_LOGS: logger.info("🧮 Sincronizando e desmembrando transação em background...")
            qtd_itens = len(orders)
            c_total_frac = c_total / qtd_itens
            c_shopee_frac = c_shopee / qtd_itens
            c_extra_frac = c_extra / qtd_itens

            for order in orders:
                status = order.get("orderStatus", "").upper()
                if status == "COMPLETED":
                    diario_api[dt_db_str]["aprovado"] += c_total_frac
                    diario_api[dt_db_str]["shopee"] += c_shopee_frac
                    diario_api[dt_db_str]["vendedor"] += c_extra_frac
                    diario_api[dt_db_str]["qtd_aprovado"] += 1
                elif status == "PENDING":
                    diario_api[dt_db_str]["pendente"] += c_total_frac
                    diario_api[dt_db_str]["qtd_pendente"] += 1
                else:
                    diario_api[dt_db_str]["cancelado"] += c_total_frac
                    diario_api[dt_db_str]["qtd_cancelado"] += 1
                
    houve_atualizacao = False
    
    for d_str in [ontem_str, anteontem_str]:
        v_api = diario_api[d_str]
        v_total_api = v_api["aprovado"] + v_api["pendente"]
        
        v_antigo = historico.get(d_str, {"aprovado": 0.0, "pendente": 0.0, "cancelado": 0.0, "shopee": 0.0, "vendedor": 0.0, "qtd_aprovado": 0, "qtd_pendente": 0, "qtd_cancelado": 0, "clicks": 0})
        if isinstance(v_antigo, float): v_antigo = {"aprovado": v_antigo, "pendente": 0.0, "cancelado": 0.0, "shopee": 0.0, "vendedor": 0.0, "qtd_aprovado": 0, "qtd_pendente": 0, "qtd_cancelado": 0, "clicks": 0}
        
        v_total_antigo = v_antigo["aprovado"] + v_antigo["pendente"]
        
        v_api["qtd_aprovado"] = v_antigo.get("qtd_aprovado", 0) if v_api["qtd_aprovado"] == 0 else v_api["qtd_aprovado"]
        v_api["qtd_pendente"] = v_antigo.get("qtd_pendente", 0) if v_api["qtd_pendente"] == 0 else v_api["qtd_pendente"]
        v_api["cancelado"] = v_antigo.get("cancelado", 0.0) if v_api["cancelado"] == 0.0 else v_api["cancelado"]
        v_api["qtd_cancelado"] = v_antigo.get("qtd_cancelado", 0) if v_api["qtd_cancelado"] == 0 else v_api["qtd_cancelado"]
        v_api["clicks"] = v_antigo.get("clicks", 0)
        
        if v_total_api != v_total_antigo or v_api["qtd_cancelado"] != v_antigo.get("qtd_cancelado", 0):
            historico[d_str] = v_api
            houve_atualizacao = True
            if EXIBIR_LOGS: logger.info(f"🔓 [Financeiro] Atualização salva! O dia {d_str} sofreu variação real (Atual: R$ {v_total_api:.2f} | Anterior: R$ {v_total_antigo:.2f}).")
        elif d_str == anteontem_str and not historico.get(d_str):
            historico[d_str] = {"aprovado": 0.0, "pendente": 0.0, "cancelado": 0.0, "shopee": 0.0, "vendedor": 0.0, "qtd_aprovado": 0, "qtd_pendente": 0, "qtd_cancelado": 0, "clicks": 0}
            houve_atualizacao = True
            if EXIBIR_LOGS: logger.info(f"🔒 [Financeiro] Trancamento por Tempo Limite! O dia {d_str} consolidado como R$ 0.00.")
        
    if houve_atualizacao:
        salvar_historico_financeiro(historico)

async def checkup_diario_grupos():
    if EXIBIR_LOGS: logger.info("🚀 Consolidando relatório de saúde diário do sistema...")
    
    relatorio = "📊 <b>Relatório Diário de Saúde dos Robôs</b>\n\n"
    
    # 1. Auditoria passiva do Espião (lendo o status gerado pelo Userbot)
    try:
        with open("alvos_espiao.json", "r", encoding="utf-8") as f:
            dados_espiao = json.load(f)
            
        alvos = dados_espiao.get("alvos", [])
        status_alvos = dados_espiao.get("status_alvos", {})
        
        erros_espiao = 0
        for alvo in alvos:
            info = status_alvos.get(alvo, {})
            if info.get("status") == "erro":
                erros_espiao += 1
                
        relatorio += f"👁️ <b>Espião de Afiliados:</b>\n"
        relatorio += f"✅ Ativos: {len(alvos) - erros_espiao}\n"
        relatorio += f"🔴 Com falhas de acesso: {erros_espiao}\n"
    except FileNotFoundError:
        relatorio += "👁️ <b>Espião de Afiliados:</b> <i>Dados não encontrados.</i>\n"

    relatorio += "\n"
    
    # 2. Auditoria passiva do Espelhador
    try:
        with open("espelhos_config.json", "r", encoding="utf-8") as f:
            dados_espelho = json.load(f)
            
        rotas = dados_espelho.get("rotas", [])
        erros_espelho = [r for r in rotas if r.get("status_verificacao") == "erro"]
        
        relatorio += f"🔄 <b>Espelhador de Canais:</b>\n"
        relatorio += f"✅ Rotas ativas: {len(rotas) - len(erros_espelho)}\n"
        relatorio += f"🔴 Rotas quebradas: {len(erros_espelho)}\n"
    except FileNotFoundError:
        relatorio += "🔄 <b>Espelhador de Canais:</b> <i>Nenhuma rota configurada.</i>\n"
        
    relatorio += "\n<i>*O Userbot testa a conexão constantemente e converte usernames para IDs. Use os painéis para verificar e corrigir as falhas apontadas acima.</i>"
    
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=relatorio, parse_mode="HTML")
        if EXIBIR_LOGS: logger.info("✅ Relatório de saúde diário consolidado e enviado ao administrador com sucesso.")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"⚠️ Erro ao disparar a mensagem do relatório diário: {e}")

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

    # ✅ Novo: Sincronização financeira horária para resgatar dados em atraso da Shopee
    scheduler.add_job(sincronizar_financeiro_horario, 'cron', minute=0, timezone=FUSO_STR)

    # ✅ Novo: Check-up diário de permissões em grupos roda todos os dias às 11:00
    scheduler.add_job(checkup_diario_grupos, 'cron', hour=11, minute=0, timezone=FUSO_STR)
    
    # Roda o agendador imediatamente ao ligar o bot para garantir o dia atual
    agendar_tarefas_diarias()
    
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
