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
# ✅ Importação dos nossos novos módulos blindados (Fase 2)
from api_gemini import gerar_texto_gemini, analisar_video_gemini, MODELOS_CASCATA_GEMINI, client_genai
from api_shopee import converter_link_shopee, buscar_ofertas_shopee

import matplotlib.pyplot as plt
import io
import sqlite3
import espelhador
from utils import registrar_erro_json, ler_cache_nomes_grupos, salvar_nome_grupo
EXIBIR_LOGS = True

# 2. CONFIGURAÇÃO DE LOGS 🚀
if EXIBIR_LOGS:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    logger = logging.getLogger(__name__)

# ✅ Cria a pasta temp isolada na inicialização
os.makedirs("temp", exist_ok=True)

def inicializar_banco_sqlite():
    if EXIBIR_LOGS: logger.info("🚀 Preparando a fundação de dados em SQLite...")
    conexao = sqlite3.connect("banco_dados.db")
    cursor = conexao.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fila_postagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_unico TEXT UNIQUE,
            caminho_video TEXT,
            video_id TEXT,
            legenda TEXT,
            data_alvo TEXT,
            status TEXT DEFAULT 'PENDENTE',
            prioridade INTEGER DEFAULT 0,
            data_postagem TEXT,
            horario_postagem TEXT
        )
    ''')
    conexao.commit()
    conexao.close()
    if EXIBIR_LOGS: logger.info("✅ Tabela 'fila_postagens' blindada e pronta para receber operações de leitura/escrita.")

inicializar_banco_sqlite()

# 1. CONSTANTES E TOKENS
API_TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = 1226920464
GRUPO_ID = -1003909405581
LINK_GRUPO = "https://t.me/shopee_video_afiliado"
GRUPO_VIRAL_ID = -1003932482573
LINK_GRUPO_VIRAL = "https://t.me/acervo_viral_shopee"
SHOPEE_APP_ID = os.getenv('SHOPEE_APP_ID')
SHOPEE_APP_SECRET = os.getenv('SHOPEE_APP_SECRET')
# As chaves do Gemini e a cascata foram removidas. Agora são geridas com total segurança pelo api_gemini.py

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
    aguardando_confirmacao_zerar_filas = State()

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
    aguardando_confirmacao_forcar_clones = State() # ✅ NOVO

class AchadinhosFluxo(StatesGroup):
    menu_principal = State()
    aguardando_nome = State()
    aguardando_destino = State()
    aguardando_thread_id = State() # ✅ NOVO: Estado para capturar o Tópico
    aguardando_keywords = State()
    aguardando_remocao = State()
    aguardando_confirmacao_remocao = State()
    aguardando_selecao_edicao = State()
    aguardando_campo_edicao = State()
    aguardando_novo_valor_edicao = State()

class AutoraisFluxo(StatesGroup):
    menu_principal = State()
    aguardando_origem = State()
    aguardando_topico = State() 
    aguardando_destino = State()
    aguardando_dias_retorno = State() # ✅ NOVO
    aguardando_limite_videos = State() # ✅ NOVO

class RelatoriosFluxo(StatesGroup):
    menu_filas = State()

# ✅ NOVO: Máquina de Estados para a configuração do agendamento do Espião
class ConfigRotinaEspiao(StatesGroup):
    aguardando_janela = State()
    aguardando_intervalo_espiao = State()
    aguardando_modo = State()

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
FUSO_STR = "America/Sao_Paulo"
fuso_horario = ZoneInfo(FUSO_STR)
_lock_contador = asyncio.Lock()

# ✅ NOVO: Sistema de travas assíncronas para proteção contra Race Conditions
if EXIBIR_LOGS: logger.info("🚀 Inicializando o gerenciador de travas (Locks) para os arquivos locais...")
_locks_json = {
    "fila_clonagem.json": asyncio.Lock(),
    "pausa_programada.json": asyncio.Lock(),
    "config_rotina.json": asyncio.Lock(),
    "alvos_espiao.json": asyncio.Lock(),
    "banco_pedidos.json": asyncio.Lock()
}
if EXIBIR_LOGS: logger.info("✅ Travas de segurança dos bancos JSON prontas e ativas.")

scheduler = AsyncIOScheduler(timezone=FUSO_STR)

if EXIBIR_LOGS: logger.info("🔄 Acoplando o módulo externo Espelhador ao fluxo principal...")
dp.include_router(espelhador.router)
espelhador.configurar_dependencias(bot, scheduler)
if EXIBIR_LOGS: logger.info("✅ Módulo Espelhador montado com segurança.")

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
        [KeyboardButton(text="🔄 Atualizar Rotinas"), KeyboardButton(text="Zerar Filas e Tarefas 🧹")],
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
        [KeyboardButton(text="Gerador de Achadinhos 🛍️")],
        [KeyboardButton(text="Vídeos Autorais 🎥")],
        [KeyboardButton(text="Voltar ao Início 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

teclado_menu_autorais = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Editar Origem 📥"), KeyboardButton(text="Editar Destino 📤")],
        [KeyboardButton(text="Editar Dias (Retorno) ⏳"), KeyboardButton(text="Editar Limite (Retorno) 📦")],
        [KeyboardButton(text="Voltar aos Canais 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

teclado_menu_achadinhos = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Adicionar Nicho ➕"), KeyboardButton(text="Remover Nicho 🗑️")],
        [KeyboardButton(text="Editar Nicho ✏️"), KeyboardButton(text="Forçar Garimpo 🚀")],
        [KeyboardButton(text="Voltar aos Canais 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

teclado_edicao_nicho = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Editar Nome 📝"), KeyboardButton(text="Editar Destino 🎯")],
        [KeyboardButton(text="Editar Tópico 💬"), KeyboardButton(text="Editar Palavras-chave 🔑")],
        [KeyboardButton(text="Cancelar ❌")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

# 🛠️ Função do novo Menu Inicial Raiz
def obter_teclado_raiz():
    botoes = [
        [KeyboardButton(text="Canal Afiliados 📺"), KeyboardButton(text="Outros Canais 🗂️")],
        [KeyboardButton(text="Relatório Geral 📊")],
        [KeyboardButton(text="Opções do Servidor ⚙️")]
    ]
    return ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)

def obter_teclado_principal():
    botoes = [
        [KeyboardButton(text="Criar Postagem 📝"), KeyboardButton(text="Gerenciar Fila 📋")],
        [KeyboardButton(text="🛠️ Configurações Avançadas")],
        [KeyboardButton(text="Voltar ao Início 🔙")]
    ]
    return ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)

# 🛠️ Novo Sub-Menu do Servidor
def obter_teclado_opcoes_servidor():
    botoes = [
        [KeyboardButton(text="Monitorar Servidor 🖥️"), KeyboardButton(text="Zerar Filas e Tarefas 🧹")],
        [KeyboardButton(text="Voltar ao Início 🔙")]
    ]
    return ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)

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
        [KeyboardButton(text="Forçar Clones 🚀")],
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

teclado_opcoes_espiao = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Definir Canal de Destino 🎯"), KeyboardButton(text="Editar Agendamento 🕒")],
        [KeyboardButton(text="Adicionar Concorrente ➕"), KeyboardButton(text="Remover Concorrente 🗑️")],
        [KeyboardButton(text="Voltar ao Menu Espião 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

# --- SISTEMA DE FILA DE POSTAGENS ASSÍNCRONAS ---
def ler_fila_postagens():
    import os
    # 📦 Módulo de migração silenciosa (Executa apenas na primeira vez)
    if os.path.exists("fila_postagens.json"):
        try:
            if EXIBIR_LOGS: logger.info("📦 Migrando dados antigos do JSON para o banco SQLite...")
            with open("fila_postagens.json", "r") as f:
                dados_antigos = json.load(f)
            
            salvar_fila_postagens(dados_antigos)
            os.rename("fila_postagens.json", "fila_postagens_bkp.json")
            if EXIBIR_LOGS: logger.info("✅ Migração concluída com sucesso! Ficheiro antigo arquivado.")
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro na migração do JSON: {e}")

    try:
        conexao = sqlite3.connect("banco_dados.db")
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()
        
        # Retorna ordenado pela data e depois pela prioridade para manter a ordem visual
        cursor.execute("SELECT * FROM fila_postagens ORDER BY data_alvo ASC, prioridade ASC")
        linhas = cursor.fetchall()
        conexao.close()
        
        fila = []
        for linha in linhas:
            fila.append({
                "id": linha["id_unico"],
                "caminho_video": linha["caminho_video"],
                "video_id": linha["video_id"],
                "legenda": linha["legenda"],
                "data_adicao": linha["data_alvo"],
                "postado": True if linha["status"] == 'CONCLUIDO' else False,
                "horario_postagem": linha["horario_postagem"],
                "data_postagem": linha["data_postagem"],
                "prioridade": linha["prioridade"]
            })
        return {"fila": fila}
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler fila do SQLite: {e}")
        return {"fila": []}

def salvar_fila_postagens(dados):
    # Função adaptador temporária para não quebrar os menus antigos
    try:
        conexao = sqlite3.connect("banco_dados.db")
        cursor = conexao.cursor()
        fila = dados.get("fila", [])
        
        cursor.execute("DELETE FROM fila_postagens")
        for i, item in enumerate(fila):
            status = 'CONCLUIDO' if item.get("postado") else 'PENDENTE'
            cursor.execute('''
                INSERT INTO fila_postagens 
                (id_unico, caminho_video, video_id, legenda, data_alvo, status, prioridade, data_postagem, horario_postagem)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item.get("id"),
                item.get("caminho_video"),
                item.get("video_id"),
                item.get("legenda"),
                item.get("data_adicao"),
                status,
                i + 1,
                item.get("data_postagem"),
                item.get("horario_postagem")
            ))
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao reescrever fila no SQLite: {e}")

# 🧹 O antigo salvar_fila_postagens() foi completamente eliminado nesta fase.
# Todas as gravações agora ocorrem através de queries atómicas (UPDATE/INSERT/DELETE).

def agendar_fila_postagens():
    # ✅ NOVO MOTOR DE FILA (Fase 3): O agendamento em massa foi desativado!
    # A função atua apenas como um "adaptador" para remover lixos antigos da memória.
    if EXIBIR_LOGS: logger.info("🔄 Efeito Dominó desativado. Limpando agendamentos estáticos de postagem...")
    for job in scheduler.get_jobs():
        if job.id.startswith('job_fila_postagem_'):
            job.remove()

async def motor_fila_minuto():
    # 1. Verifica se a loja está aberta (Expediente)
    agora = datetime.now(fuso_horario)
    hoje_str = agora.strftime("%Y-%m-%d")
    
    dados_pausa = ler_pausa_programada()
    if dados_pausa.get("ativa"): return
    
    dados_rotina = ler_config_rotina()
    ultimo_bd = dados_rotina.get("ultimo_bom_dia", "")
    ultimo_bn = dados_rotina.get("ultimo_boa_noite", "")
    
    if ultimo_bd != hoje_str or ultimo_bn == hoje_str:
        return # Fora do expediente
        
    hora_ultimo_bd = dados_rotina.get("hora_ultimo_bom_dia", "")
    if hora_ultimo_bd:
        hora_bd_obj = datetime.strptime(hora_ultimo_bd, "%H:%M").time()
        momento_bd = datetime.combine(agora.date(), hora_bd_obj).replace(tzinfo=fuso_horario)
        if (agora - momento_bd).total_seconds() / 60 < 15:
            return # Respiro matinal (aguarda 15 min do Bom Dia)
            
    try:
        conexao = sqlite3.connect("banco_dados.db")
        cursor = conexao.cursor()
        
        # 2. Inteligência de Espaçamento Orgânico Dinâmico
        cursor.execute("SELECT COUNT(*) FROM fila_postagens WHERE status = 'PENDENTE' AND (data_alvo <= ? OR data_alvo = '2000-01-01')", (hoje_str,))
        qtd_videos = cursor.fetchone()[0]
        
        if qtd_videos == 0:
            conexao.close()
            return
            
        INTERVALO_MINIMO = 15
        job_bn = scheduler.get_job('job_rotina_boa_noite_0')
        if job_bn and getattr(job_bn, 'next_run_time', None):
            limite_fim = job_bn.next_run_time.astimezone(fuso_horario)
        else:
            hora_fim = dados_rotina.get("boa_noite", {}).get("inicio", 21)
            limite_fim = agora.replace(hour=hora_fim, minute=59)
            
        minutos_restantes = (limite_fim - agora).total_seconds() / 60
        if minutos_restantes > 0:
            # Reduz a janela em 10% garantindo que o último caiba com folga antes de fechar a loja
            gap_organico = int((minutos_restantes * 0.9) / qtd_videos)
            INTERVALO_MINIMO = max(15, min(gap_organico, 90))
            
        # 3. Verifica a distância de tempo do último vídeo (O Semáforo)
        cursor.execute("SELECT horario_postagem FROM fila_postagens WHERE data_postagem = ? AND status = 'CONCLUIDO' ORDER BY horario_postagem DESC LIMIT 1", (hoje_str,))
        ultimo_vid = cursor.fetchone()
        if ultimo_vid and ultimo_vid[0]:
            hora_ult_vid = datetime.strptime(ultimo_vid[0], "%H:%M").time()
            dt_ult_vid = datetime.combine(agora.date(), hora_ult_vid).replace(tzinfo=fuso_horario)
            if (agora - dt_ult_vid).total_seconds() / 60 < INTERVALO_MINIMO:
                conexao.close()
                return
                
        # 4. Verifica colisão com rotinas fixas (Abre alas de 15 minutos)
        for job in scheduler.get_jobs():
            if not job.id.startswith('job_fila_postagem_') and getattr(job, 'next_run_time', None):
                diff = abs((agora - job.next_run_time.astimezone(fuso_horario)).total_seconds() / 60)
                if diff < 15:
                    conexao.close()
                    return
                    
        # 5. Semáforo Verde! Puxa a mercadoria com a prioridade mais alta
        cursor.execute("SELECT id_unico FROM fila_postagens WHERE status = 'PENDENTE' AND (data_alvo <= ? OR data_alvo = '2000-01-01') ORDER BY prioridade ASC LIMIT 1", (hoje_str,))
        proximo = cursor.fetchone()
        
        if proximo:
            id_unico = proximo[0]
            cursor.execute("UPDATE fila_postagens SET status = 'PROCESSANDO' WHERE id_unico = ?", (id_unico,))
            conexao.commit()
            conexao.close()
            
            if EXIBIR_LOGS: logger.info(f"🚦 Semáforo Verde (Gap Orgânico: {INTERVALO_MINIMO}m)! O Relógio Central puxou o vídeo {id_unico}.")
            await executar_postagem_fila(id_unico)
        else:
            conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro no Relógio Central: {e}")

async def executar_postagem_fila(item_id):
    if EXIBIR_LOGS: logger.info(f"📤 Iniciando upload físico do vídeo pela nova esteira SQLite...")
    agora = datetime.now(fuso_horario)
    hoje_str = agora.strftime("%Y-%m-%d")
    
    try:
        conexao = sqlite3.connect("banco_dados.db")
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()
        cursor.execute("SELECT * FROM fila_postagens WHERE id_unico = ?", (item_id,))
        item = cursor.fetchone()
        
        if not item:
            conexao.close()
            return
            
        caminho_video = item["caminho_video"]
        video_id = item["video_id"]
        legenda = item["legenda"]
        
        sucesso = False
        falha_irreversivel = False
        novo_file_id = None
        
        if caminho_video and os.path.exists(caminho_video):
            # ✅ SEGUNDA TRAVA DE SEGURANÇA MANTIDA INTACTA
            if caminho_video.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                if EXIBIR_LOGS: logger.warning(f"🚫 [Segurança] Upload cancelado! Ficheiro é uma imagem.")
                try: os.remove(caminho_video)
                except: pass
                falha_irreversivel = True
            else:
                arquivo = FSInputFile(caminho_video)
                msg = await bot.send_video(chat_id=GRUPO_ID, video=arquivo, caption=legenda, parse_mode="HTML")
                novo_file_id = msg.video.file_id
                sucesso = True
                if EXIBIR_LOGS: logger.info("🚀 [Fluxo] Vídeo enviado com sucesso pelo Motor Central.")
                try: os.remove(caminho_video)
                except: pass
        elif video_id:
            await bot.send_video(chat_id=GRUPO_ID, video=video_id, caption=legenda, parse_mode="HTML")
            sucesso = True
        else:
            if EXIBIR_LOGS: logger.error("❌ Falha irreversível: Vídeo expirou ou foi perdido fisicamente.")
            falha_irreversivel = True
            
        if sucesso or falha_irreversivel:
            novo_status = 'CONCLUIDO' if sucesso else 'ERRO'
            cursor.execute("UPDATE fila_postagens SET status = ?, data_postagem = ?, horario_postagem = ? WHERE id_unico = ?", (novo_status, hoje_str, agora.strftime("%H:%M"), item_id))
            
            if sucesso and novo_file_id:
                cursor.execute("UPDATE fila_postagens SET video_id = ?, caminho_video = NULL WHERE caminho_video = ? AND id_unico != ?", (novo_file_id, caminho_video, item_id))
            conexao.commit()
            
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha crítica ao postar vídeo da fila: {e}")
        try:
            conexao = sqlite3.connect("banco_dados.db")
            cursor = conexao.cursor()
            cursor.execute("UPDATE fila_postagens SET status = 'ERRO' WHERE id_unico = ?", (item_id,))
            conexao.commit()
            conexao.close()
        except: pass

# --- GERENCIADOR CENTRAL DE CONFIGURAÇÕES (SQLITE) ---
def ler_config_bd(chave, padrao=None, arquivo_legado=None):
    if padrao is None: padrao = {}
    try:
        conexao = sqlite3.connect("banco_dados.db")
        cursor = conexao.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave,))
        resultado = cursor.fetchone()
        conexao.close()
        
        if resultado:
            return json.loads(resultado[0])
            
        # Auto-migração transparente do JSON antigo para a nova tabela do SQLite
        import os
        if arquivo_legado and os.path.exists(arquivo_legado):
            with open(arquivo_legado, "r", encoding="utf-8") as f:
                dados_antigos = json.load(f)
            salvar_config_bd(chave, dados_antigos)
            os.rename(arquivo_legado, arquivo_legado + ".bkp")
            if EXIBIR_LOGS: logger.info(f"📦 Migração concluída: '{arquivo_legado}' movido para o SQLite com sucesso.")
            return dados_antigos
            
        return padrao
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler configuração '{chave}' do SQLite: {e}")
        return padrao

def salvar_config_bd(chave, dados):
    try:
        conexao = sqlite3.connect("banco_dados.db")
        cursor = conexao.cursor()
        dados_str = json.dumps(dados, ensure_ascii=False)
        cursor.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)", (chave, dados_str))
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao salvar configuração '{chave}' no SQLite: {e}")

# --- SISTEMA DE PAUSA PROGRAMADA ---
def ler_pausa_programada():
    padrao = {"ativa": False, "data_retorno": None, "servicos_pausados": []}
    return ler_config_bd("pausa_programada", padrao, arquivo_legado="pausa_programada.json")

def salvar_pausa_programada(dados):
    salvar_config_bd("pausa_programada", dados)

def recalcular_datas_pos_pausa():
    if EXIBIR_LOGS: logger.info("🔄 Iniciando recálculo de datas no SQLite pós-pausa...")
    try:
        conexao = sqlite3.connect("banco_dados.db")
        cursor = conexao.cursor()
        
        cursor.execute("SELECT MIN(data_alvo) FROM fila_postagens WHERE status = 'PENDENTE' AND data_alvo != '2000-01-01'")
        resultado = cursor.fetchone()
        menor_data_str = resultado[0] if resultado else None
        
        if not menor_data_str:
            conexao.close()
            if EXIBIR_LOGS: logger.info("⚠️ Fila vazia ou sem datas futuras, nenhum ajuste necessário.")
            return
            
        from datetime import datetime, timedelta
        agora = datetime.now(fuso_horario)
        hoje_obj = agora.date()
        menor_data_obj = datetime.strptime(menor_data_str, "%Y-%m-%d").date()
        
        if menor_data_obj < hoje_obj:
            offset_dias = (hoje_obj - menor_data_obj).days
            if EXIBIR_LOGS: logger.info(f"⏳ Deslocamento: {offset_dias} dias. Aplicando offset no banco...")
            
            cursor.execute("SELECT id_unico, data_alvo FROM fila_postagens WHERE status = 'PENDENTE' AND data_alvo != '2000-01-01'")
            itens = cursor.fetchall()
            
            for id_unico, d_str in itens:
                d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
                nova_data = d_obj + timedelta(days=offset_dias)
                cursor.execute("UPDATE fila_postagens SET data_alvo = ? WHERE id_unico = ?", (nova_data.strftime("%Y-%m-%d"), id_unico))
                
            conexao.commit()
            if EXIBIR_LOGS: logger.info("✅ Datas recalculadas no SQLite com sucesso.")
        else:
            if EXIBIR_LOGS: logger.info("✅ O primeiro vídeo da fila já está no futuro ou presente. Nenhum offset necessário.")
            
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao recalcular datas pós-pausa: {e}")

async def verificar_pausa_diaria():
    if EXIBIR_LOGS: logger.info("⏰ Iniciando verificação diária de pausa programada (envio de aviso)...")
    dados_pausa = ler_pausa_programada()
    if not dados_pausa.get("ativa"):
        return
        
    data_retorno_str = dados_pausa.get("data_retorno")
    if not data_retorno_str:
        return
        
    if EXIBIR_LOGS: logger.info("🛑 Pausa ativa. Enviando aviso diário ao grupo principal...")
    
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
    
    msg_enviada = await bot.send_message(GRUPO_ID, texto)
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
        try:
            data_retorno = datetime.strptime(data_retorno_str, "%d/%m/%Y").date()
            hoje = hoje.date()
        except ValueError:
            return
    
    if hoje >= data_retorno:
        if EXIBIR_LOGS: logger.info("⏰ Data e hora de retorno atingidas! Reativando serviços pausados...")
        
        id_aviso = dados_pausa.pop("id_aviso_imediato", None)
        if id_aviso:
            await apagar_mensagem_automatica(id_aviso, GRUPO_ID)
            
        prompt_retorno = (
            "Você é um assistente de afiliados. Crie uma mensagem MUITO CURTA E EMPOLGANTE "
            "avisando o grupo que a pausa de manutenção acabou, o canal voltou à ativa e os "
            "vídeos com ofertas voltarão a ser postados normalmente a partir de hoje. "
            "REGRA ABSOLUTA: Seja direto (máximo 150 caracteres), use emojis animados e entregue APENAS o texto pronto."
        )
        texto_retorno = await gerar_mensagem_gemini(prompt_retorno)
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
    texto = await gerar_texto_gemini(prompt, EXIBIR_LOGS)
    if texto:
        return texto
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

# --- SISTEMA DE LIXEIRA PERSISTENTE (MIGRADO PARA SQLITE) ---
def limpar_historico_antigo():
    if os.path.exists("historico_mensagens.json"):
        os.remove("historico_mensagens.json")
        if EXIBIR_LOGS: logger.info("🧹 Histórico de mensagens do userbot reiniciado.")

def registrar_lixeira(msg_id, chat_id=GRUPO_ID):
    try:
        conexao = sqlite3.connect("banco_dados.db")
        cursor = conexao.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO lixeira_mensagens (msg_id, chat_id, data_inclusao) VALUES (?, ?, ?)", (msg_id, str(chat_id), agora))
        conexao.commit()
        conexao.close()
        if EXIBIR_LOGS: logger.info(f"💾 ID {msg_id} (Chat: {chat_id}) salvo na lixeira persistente (SQLite) para exclusão na madrugada.")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao registrar lixeira no banco: {e}")

async def varredor_de_lixeira():
    if EXIBIR_LOGS: logger.info("🧹 Iniciando varredura diária da lixeira persistente (03h00)...")
    try:
        conexao = sqlite3.connect("banco_dados.db")
        cursor = conexao.cursor()
        cursor.execute("SELECT id, msg_id, chat_id FROM lixeira_mensagens")
        mensagens = cursor.fetchall()
        
        ids_apagados = []
        for linha in mensagens:
            id_banco, msg_id, chat_id = linha
            try:
                await apagar_mensagem_automatica(msg_id, chat_id)
                ids_apagados.append(id_banco)
            except Exception as e:
                if EXIBIR_LOGS: logger.warning(f"⚠️ Erro ao processar item da lixeira: {e}")
                ids_apagados.append(id_banco) # Remove do banco mesmo com falha para não travar
        
        for id_banco in ids_apagados:
            cursor.execute("DELETE FROM lixeira_mensagens WHERE id = ?", (id_banco,))
            
        conexao.commit()
        conexao.close()
        if EXIBIR_LOGS: logger.info("✅ Lixeira persistente (SQLite) esvaziada com sucesso.")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro na varredura da lixeira: {e}")

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
    padrao = {
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
    
    dados = ler_config_bd("config_rotina", padrao, arquivo_legado="config_rotina.json")
    
    # Injeta chaves padrão que possam estar faltando em arquivos de versões antigas
    houve_alteracao = False
    for chave, valor in padrao.items():
        if chave not in dados:
            dados[chave] = valor
            houve_alteracao = True
            
    if houve_alteracao:
        salvar_config_bd("config_rotina", dados)
        
    return dados

def salvar_config_rotina(dados):
    salvar_config_bd("config_rotina", dados)

def agendar_tarefas_diarias():
    if EXIBIR_LOGS: logger.info("🔄 Sorteando horários fixos de rotina (Bom Dia, Boa Noite, Campanhas)...")
    
    agora_faxina = datetime.now(fuso_horario)
    hoje_faxina_str = agora_faxina.strftime("%Y-%m-%d")
    
    # --- Limpeza de Madrugada no SQLite: Remove físicos e registros de dias anteriores ---
    try:
        conexao = sqlite3.connect("banco_dados.db")
        cursor = conexao.cursor()
        
        # Puxa os ficheiros associados a vídeos antigos para deletá-los
        cursor.execute("SELECT caminho_video FROM fila_postagens WHERE status IN ('CONCLUIDO', 'ERRO') AND data_postagem != ?", (hoje_faxina_str,))
        para_apagar = cursor.fetchall()
        
        for item in para_apagar:
            cam = item[0]
            if cam and os.path.exists(cam):
                # Confirma que não há outro pendente usando o mesmo ficheiro físico
                cursor.execute("SELECT COUNT(*) FROM fila_postagens WHERE caminho_video = ? AND status = 'PENDENTE'", (cam,))
                em_uso = cursor.fetchone()[0]
                if em_uso == 0:
                    try: os.remove(cam)
                    except: pass
                
        cursor.execute("DELETE FROM fila_postagens WHERE status IN ('CONCLUIDO', 'ERRO') AND data_postagem != ?", (hoje_faxina_str,))
        apagados = cursor.rowcount
        conexao.commit()
        conexao.close()
        
        if EXIBIR_LOGS and apagados > 0: logger.info(f"🧹 Limpeza da madrugada: {apagados} registos antigos eliminados do SQLite.")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro na faxina da madrugada (SQLite): {e}")
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
            
            # Interliga a Campanha ao JSON para não repetir avisos já dados hoje
            disparos_ja_feitos = obter_qtd_disparos(tipo_alerta)
            turnos = ["manha", "tarde", "noite"]
            
            # Corta os turnos que já foram processados
            turnos_pendentes = turnos[disparos_ja_feitos:]
            
            for p in turnos_pendentes:
                horario_campanha = encontrar_maior_lacuna_e_inserir(duracao_minima=10)
                if not horario_campanha:
                    if p == "manha": horario_campanha = agora.replace(hour=random.randint(8,11), minute=random.randint(0,59))
                    elif p == "tarde": horario_campanha = agora.replace(hour=random.randint(14,17), minute=random.randint(0,59))
                    else: horario_campanha = agora.replace(hour=random.randint(18,21), minute=random.randint(0,59))
                    
                # Trava contra viagem no tempo (Impede disparos imediatos em rajada)
                if horario_campanha <= agora:
                    horario_campanha = agora + timedelta(minutes=random.randint(3, 10))
                    
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

# ----------------------------------
# NOVO MÓDULO: VÍDEOS AUTORAIS 🎥
# ----------------------------------
def ler_autorais_config():
    padrao = {"origem": -1003673555953, "origem_topico": None, "destino": "@videos_autorais", "dias_retorno": 15, "limite_videos": 5}
    return ler_config_bd("autorais_config", padrao, arquivo_legado="autorais_config.json")

def salvar_autorais_config(dados):
    salvar_config_bd("autorais_config", dados)

@dp.message(F.text == "Vídeos Autorais 🎥", StateFilter("*"))
async def painel_autorais(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    
    if EXIBIR_LOGS: logger.info("🎥 Acessando painel visual do Bot Vídeos Autorais...")
    config = ler_autorais_config()
    
    origem = config.get("origem", "Não definida")
    topico = config.get("origem_topico", "0 (Todos)")
    destino = config.get("destino", "Não definido")
    dias_retorno = config.get("dias_retorno", 15)
    limite_videos = config.get("limite_videos", 5)
    
    cache_nomes = ler_cache_nomes_grupos()

    # --- Lógica Avançada Visual da Origem ---
    nome_origem = str(origem)
    icone_origem = "⏳"
    
    if str(origem) != "Não definida":
        # 1. Procura primeiro no Cache Local
        if str(origem) in cache_nomes:
            nome_origem = f"{cache_nomes[str(origem)]} (<code>{origem}</code>)"
            icone_origem = "✅"
        else:
            # 2. Tenta perguntar à API do Telegram
            try:
                chat_obj = await bot.get_chat(origem)
                nome = chat_obj.title or chat_obj.full_name
                nome_origem = f"{nome} (<code>{origem}</code>)"
                salvar_nome_grupo(str(origem), nome)
                icone_origem = "✅"
            except Exception:
                # 3. Tenta procurar na Base de Dados do Espião
                nome_encontrado_no_espiao = False
                try:
                    with open("alvos_espiao.json", "r", encoding="utf-8") as f:
                        dados_espiao = json.load(f)
                        status_alvos = dados_espiao.get("status_alvos", {})
                        
                        for alvo_id, dados_alvo in status_alvos.items():
                            if str(dados_alvo.get("id")) == str(origem) or str(dados_alvo.get("id")).replace("-100", "") == str(origem).replace("-100", ""):
                                nome = dados_alvo.get("nome", "Desconhecido")
                                nome_origem = f"{nome} (<code>{origem}</code>)"
                                salvar_nome_grupo(str(origem), nome) # Guarda para a próxima vez
                                icone_origem = "✅"
                                nome_encontrado_no_espiao = True
                                break
                except Exception:
                    pass

                if not nome_encontrado_no_espiao:
                    nome_origem = f"<code>{origem}</code> - <i>Aguardando leitura do Userbot...</i>"
                    icone_origem = "⏳"
                
    # --- Lógica Visual do Destino ---
    nome_destino = str(destino)
    icone_destino = "⏳"
    if str(destino) != "Não definido":
        if str(destino) in cache_nomes:
            nome_destino = f"{cache_nomes[str(destino)]} (<code>{destino}</code>)"
            icone_destino = "✅"
        else:
            try:
                chat_obj = await bot.get_chat(destino)
                nome = chat_obj.title or chat_obj.full_name
                nome_destino = f"{nome} (<code>{destino}</code>)"
                salvar_nome_grupo(str(destino), nome)
                icone_destino = "✅"
            except Exception:
                nome_destino = f"<code>{destino}</code> - <i>Acesso Negado</i>"
                icone_destino = "❌"
    
    texto = (
        "🎥 <b>Painel do Bot Vídeos Autorais</b>\n\n"
        f"{icone_origem} <b>Origem atual:</b> {nome_origem}\n"
        f"📂 <b>Tópico (Subcanal):</b> <code>{topico}</code>\n\n"
        f"{icone_destino} <b>Destino atual:</b> {nome_destino}\n\n"
        f"♻️ <b>Regras de Retorno (Re-postagem):</b>\n"
        f"⏳ Oculto por: <b>{dias_retorno} dias</b>\n"
        f"📦 Cota Diária: <b>{limite_videos} vídeos/dia</b>\n\n"
        "O robô Espelhador Isolado fará a escuta e o envio em tempo real baseando-se estritamente nestes valores.\n\n"
        "Escolha o que deseja alterar:"
    )
    await message.answer(texto, parse_mode="HTML", reply_markup=teclado_menu_autorais)
    await state.set_state(AutoraisFluxo.menu_principal)

@dp.message(AutoraisFluxo.menu_principal, F.text == "Editar Origem 📥")
async def pedir_origem_autorais(message: types.Message, state: FSMContext):
    if EXIBIR_LOGS: logger.info("📥 Solicitando nova origem para vídeos autorais...")
    await message.answer("Envie o <b>ID Numérico</b> ou <b>@username</b> do grupo de ORIGEM de onde o bot vai puxar os vídeos (Ex: -100123456789):", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AutoraisFluxo.aguardando_origem)

@dp.message(AutoraisFluxo.aguardando_origem)
async def pedir_topico_autorais(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await cancelar_fluxo_global(message, state)
        return
        
    novo_valor = message.text.strip()
    msg_status = await message.answer("⏳ <b>Validando grupo de origem...</b>", parse_mode="HTML")
    
    id_real = novo_valor
    nome_chat = novo_valor
    sucesso = False
    
    variacoes = [novo_valor]
    if novo_valor.lstrip('-').isdigit():
        so_num = novo_valor.replace("-100", "").replace("-", "")
        variacoes = [novo_valor, f"-100{so_num}", f"-{so_num}", so_num]
    elif "t.me/c/" in novo_valor:
        so_num = novo_valor.split("t.me/c/")[1].split("/")[0]
        variacoes = [f"-100{so_num}"]
    elif "t.me/" in novo_valor:
        username = novo_valor.split("t.me/")[1].split("/")[0]
        variacoes = [f"@{username}"]
        
    for var in variacoes:
        try:
            chat_obj = await bot.get_chat(var)
            nome_chat = chat_obj.title or chat_obj.full_name or var
            id_real = chat_obj.id
            sucesso = True
            break
        except Exception:
            continue
    
    if sucesso:
        await msg_status.delete()
        await message.answer(f"✅ Origem validada e encontrada: <b>{nome_chat}</b>", parse_mode="HTML")
        salvar_nome_grupo(str(id_real), nome_chat)
    else:
        await msg_status.delete()
        await message.answer("⚠️ <b>Aviso de Permissão:</b> O Bot Principal não tem permissão para enxergar este grupo. O ID será salvo, pois a Conta Secundária é quem fará a extração física.", parse_mode="HTML")
        if novo_valor.lstrip('-').isdigit():
            so_num = novo_valor.replace("-100", "").replace("-", "")
            id_real = int(f"-100{so_num}")
            
    await state.update_data(nova_origem=id_real)
    
    await message.answer("Agora, digite o <b>NÚMERO DO TÓPICO (Subcanal)</b> que ele deve monitorar.\n\n<i>Dica: Se os vídeos caem no chat 'Geral', digite <b>1</b>. Se for um canal sem tópicos, digite <b>0</b> para ler tudo.</i>", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AutoraisFluxo.aguardando_topico)

@dp.message(AutoraisFluxo.aguardando_topico)
async def salvar_origem_autorais(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await cancelar_fluxo_global(message, state)
        return
        
    if not message.text.isdigit():
        await message.answer("⚠️ Formato inválido! Envie apenas o número do tópico (Ex: 1 ou 0).", reply_markup=teclado_cancelar)
        return
        
    topico = int(message.text)
    topico_final = topico if topico > 0 else None
    
    data = await state.get_data()
    nova_origem = data.get("nova_origem")
    
    config = ler_autorais_config()
    config["origem"] = nova_origem
    config["origem_topico"] = topico_final
    salvar_autorais_config(config)
    
    if EXIBIR_LOGS: logger.info(f"✅ Origem dos vídeos autorais salva: {nova_origem} | Tópico: {topico_final}")
    await message.answer(f"✅ <b>Origem e Tópico salvos com sucesso!</b>", parse_mode="HTML")
    await painel_autorais(message, state)

@dp.message(AutoraisFluxo.menu_principal, F.text == "Editar Destino 📤")
async def pedir_destino_autorais(message: types.Message, state: FSMContext):
    if EXIBIR_LOGS: logger.info("📤 Solicitando novo destino para vídeos autorais...")
    await message.answer("Envie o <b>ID Numérico</b> ou <b>@username</b> do canal de DESTINO para onde o bot vai enviar os vídeos convertidos (Ex: @meu_canal):", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AutoraisFluxo.aguardando_destino)

@dp.message(AutoraisFluxo.aguardando_destino)
async def salvar_destino_autorais(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await cancelar_fluxo_global(message, state)
        return
        
    novo_valor = message.text.strip()
    msg_status = await message.answer("⏳ <b>Validando canal de destino...</b>", parse_mode="HTML")
    
    id_real = novo_valor
    nome_chat = novo_valor
    sucesso = False
    
    variacoes = [novo_valor]
    if novo_valor.lstrip('-').isdigit():
        so_num = novo_valor.replace("-100", "").replace("-", "")
        variacoes = [novo_valor, f"-100{so_num}", f"-{so_num}", so_num]
    elif "t.me/c/" in novo_valor:
        so_num = novo_valor.split("t.me/c/")[1].split("/")[0]
        variacoes = [f"-100{so_num}"]
    elif "t.me/" in novo_valor:
        username = novo_valor.split("t.me/")[1].split("/")[0]
        variacoes = [f"@{username}"]
        
    for var in variacoes:
        try:
            chat_obj = await bot.get_chat(var)
            nome_chat = chat_obj.title or chat_obj.full_name or var
            id_real = chat_obj.id
            sucesso = True
            break
        except Exception:
            continue

    if sucesso:
        await msg_status.delete()
        await message.answer(f"✅ Destino validado: <b>{nome_chat}</b>", parse_mode="HTML")
        salvar_nome_grupo(str(id_real), nome_chat)
    else:
        await msg_status.delete()
        await message.answer("⚠️ <b>Aviso:</b> O bot não conseguiu encontrar este destino (verifique se ele é administrador do canal). O ID será salvo mesmo assim.", parse_mode="HTML")
        if novo_valor.lstrip('-').isdigit():
            so_num = novo_valor.replace("-100", "").replace("-", "")
            id_real = int(f"-100{so_num}")
            
    config = ler_autorais_config()
    config["destino"] = id_real
    salvar_autorais_config(config)
    
    if EXIBIR_LOGS: logger.info(f"✅ Destino dos vídeos autorais atualizado para: {id_real}")
    await message.answer(f"✅ <b>Destino atualizado com sucesso!</b>\nOs vídeos convertidos serão enviados instantaneamente para: <code>{id_real}</code>", parse_mode="HTML")
    await painel_autorais(message, state)

@dp.message(AutoraisFluxo.menu_principal, F.text == "Editar Dias (Retorno) ⏳")
async def pedir_dias_autorais(message: types.Message, state: FSMContext):
    await message.answer("Por quantos <b>dias</b> o vídeo deve ficar arquivado e oculto até retornar para o grupo de origem? (Ex: 15)", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AutoraisFluxo.aguardando_dias_retorno)

@dp.message(AutoraisFluxo.aguardando_dias_retorno)
async def salvar_dias_autorais(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await cancelar_fluxo_global(message, state)
        return
        
    if not message.text.isdigit():
        await message.answer("⚠️ Envie apenas números inteiros.", reply_markup=teclado_cancelar)
        return
        
    novo_valor = int(message.text)
    config = ler_autorais_config()
    config["dias_retorno"] = novo_valor
    salvar_autorais_config(config)
    
    await message.answer(f"✅ <b>Tempo de Retorno Atualizado!</b>\nOs vídeos interceptados ficarão arquivados por {novo_valor} dias antes de serem postados novamente.", parse_mode="HTML")
    await painel_autorais(message, state)

@dp.message(AutoraisFluxo.menu_principal, F.text == "Editar Limite (Retorno) 📦")
async def pedir_limite_autorais(message: types.Message, state: FSMContext):
    await message.answer("Qual será o <b>limite máximo</b> de vídeos arquivados salvos por dia? (Ex: 5)", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AutoraisFluxo.aguardando_limite_videos)

@dp.message(AutoraisFluxo.aguardando_limite_videos)
async def salvar_limite_autorais(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await cancelar_fluxo_global(message, state)
        return
        
    if not message.text.isdigit():
        await message.answer("⚠️ Envie apenas números inteiros.", reply_markup=teclado_cancelar)
        return
        
    novo_valor = int(message.text)
    config = ler_autorais_config()
    config["limite_videos"] = novo_valor
    salvar_autorais_config(config)
    
    await message.answer(f"✅ <b>Cota de Retorno Atualizada!</b>\nO robô arquivará no máximo {novo_valor} vídeos de retorno por dia.", parse_mode="HTML")
    await painel_autorais(message, state)

# ----------------------------------
# NOVO MÓDULO: GERADOR AUTÔNOMO DE ACHADINHOS 🛍️
# ----------------------------------
def ler_achadinhos_config():
    return ler_config_bd("achadinhos_config", {"nichos": []}, arquivo_legado="achadinhos_config.json")

def salvar_achadinhos_config(dados):
    salvar_config_bd("achadinhos_config", dados)

def ler_achadinhos_enviados():
    return ler_config_bd("achadinhos_enviados", [], arquivo_legado="achadinhos_enviados.json")

def salvar_achadinhos_enviados(lista):
    if len(lista) > 500:
        lista = lista[-500:]
    salvar_config_bd("achadinhos_enviados", lista)

async def gerar_copy_achadinho_ia(nome_produto, preco_original, desconto, nota_loja):
    if EXIBIR_LOGS: logger.info(f"🧠 [Achadinhos] Estruturando estratégia de Copywriting para o produto...")
    
    prompt = (
        f"Você é um copywriter especialista em e-commerce alimentando um canal de achadinhos. "
        f"Crie um texto de venda MUITO CURTO para este produto: '{nome_produto}'. "
        f"A loja possui uma excelente avaliação de ⭐ {nota_loja}/5 estrelas. "
        f"O preço original era R$ {preco_original} e agora a loja aplicou {desconto} de desconto. "
        f"REGRA ABSOLUTA: Comece com uma frase extremamente chamativa focada em resolver um problema ou gerar desejo. "
        f"Apresente a queda de preço focando na urgência de levar agora. "
        f"Não ultrapasse 4 linhas. Não use palavras complexas, seja direto e use emojis atraentes. "
        f"Finalize o texto estritamente com: '🔗 Confira a oferta no link abaixo: 👇'\n\n"
        f"REGRA ABSOLUTA DE INTEGRIDADE NUMÉRICA:\n"
        f"Você está estritamente proibido de calcular, deduzir, arredondar ou inventar qualquer valor financeiro. O preço fornecido nos dados brutos é um fato imutável e intocável. Utilize EXATAMENTE os números informados na sua redação. Se o valor final com desconto não estiver matematicamente explícito na entrada de dados, não tente adivinhá-lo sob nenhuma circunstância. Concentre a persuasão do texto exclusivamente nos benefícios físicos do produto e no gatilho de escassez, preservando a integridade absoluta da etiqueta de preço."
    )
    
    texto_gerado = await gerar_texto_gemini(prompt, EXIBIR_LOGS)
    if texto_gerado:
        return texto_gerado
        
    return f"🔥 Achadinho Imperdível!\n📦 {nome_produto}\nDe R$ {preco_original} com {desconto} de desconto!\n\n🔗 Confira a oferta no link abaixo: 👇"

async def processar_garimpo_automatico():
    if EXIBIR_LOGS: logger.info("🕵️‍♂️ [Achadinhos] Iniciando operação de garimpo varrendo todos os nichos mapeados...")
    config = ler_achadinhos_config()
    nichos = config.get("nichos", [])
    
    if not nichos:
        if EXIBIR_LOGS: logger.warning("⚠️ [Achadinhos] O radar está vazio. Adicione nichos ao arquivo achadinhos_config.json.")
        return
        
    enviados = ler_achadinhos_enviados()
    
    for nicho in nichos:
        nome_nicho = nicho.get("nome")
        destino = nicho.get("destino")
        thread_id_nicho = nicho.get("thread_id", "0")
        keywords = nicho.get("keywords", [])
        
        if not keywords or not destino:
            continue
            
        keyword_sorteada = random.choice(keywords)
        if EXIBIR_LOGS: logger.info(f"🔎 [Achadinhos] Rastreando o setor '{nome_nicho}' buscando por: '{keyword_sorteada}'.")
        
        # Aumentamos a "pesca" para 40 produtos virais para ter uma amostra rica
        ofertas = await buscar_ofertas_shopee(keyword_sorteada, limite=40)
        
        # 🧠 Curadoria: O robô organiza a lista internamente do maior desconto para o menor
        ofertas.sort(key=lambda x: int(x.get("priceDiscountRate") or 0), reverse=True)
        
        item_escolhido = None
        for oferta in ofertas:
            item_id = str(oferta.get("itemId"))
            taxa_desconto = int(oferta.get("priceDiscountRate") or 0)
            
            # 🛡️ Trava de Qualidade: Só aprova se for inédito E o desconto for de no mínimo 15%
            if item_id not in enviados and taxa_desconto >= 15:
                item_escolhido = oferta
                break
                
        if not item_escolhido:
            if EXIBIR_LOGS: logger.info(f"⏭️ [Achadinhos] Nenhum produto inédito com desconto matador (>= 15%) encontrado para '{keyword_sorteada}'. Poupando a vitrine.")
            continue
            
        item_id = str(item_escolhido.get("itemId"))
        nome = item_escolhido.get("productName", "Produto Exclusivo")
        preco = item_escolhido.get("price", "Consultar na Loja")
        
        taxa_desconto = item_escolhido.get("priceDiscountRate")
        desconto = f"{taxa_desconto}%" if taxa_desconto else "Promoção Especial"
        
        nota_loja = item_escolhido.get("ratingStar", "4.8")
        
        img_url = item_escolhido.get("imageUrl")
        link_original = item_escolhido.get("productLink")
        
        texto_ia = await gerar_copy_achadinho_ia(nome, preco, desconto, nota_loja)
        link_curto = await converter_link_shopee(link_original, nome_nicho, EXIBIR_LOGS)
        legenda_final = f"{texto_ia}\n{link_curto}"
        
        try:
            temp_img = f"temp/temp_achado_{item_id}.jpg"
            async with aiohttp.ClientSession() as session:
                async with session.get(img_url) as resp:
                    if resp.status == 200:
                        with open(temp_img, "wb") as f:
                            f.write(await resp.read())
                            
            if os.path.exists(temp_img):
                arquivo_img = FSInputFile(temp_img)
                
                # 🚀 Roteamento Inteligente: Define se o disparo vai para o chat raiz ou para a gaveta do tópico
                thread_param = None
                if thread_id_nicho and str(thread_id_nicho) != "0":
                    thread_param = int(thread_id_nicho)
                    
                await bot.send_photo(chat_id=destino, photo=arquivo_img, caption=legenda_final, parse_mode="HTML", message_thread_id=thread_param)
                
                enviados.append(item_id)
                salvar_achadinhos_enviados(enviados)
                
                os.remove(temp_img)
                if EXIBIR_LOGS: logger.info(f"✅ [Achadinhos] Operação concluída. Oferta fresca entregue ao canal {destino}!")
                
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ [Achadinhos] Falha estrutural ao tratar mídia física do produto: {e}")
            
        # 🛡️ Trava de Segurança para Escala (Previne banimento do Telegram e limite do Gemini)
        tempo_espera = random.randint(15, 35)
        if EXIBIR_LOGS: logger.info(f"⏳ Diluição de Tráfego: Aguardando {tempo_espera}s antes de processar o próximo nicho...")
        await asyncio.sleep(tempo_espera)

# ----------------------------------

# 5. HANDLERS DE COMANDO E INTERAÇÃO
@dp.message(Command("start"), StateFilter("*"))
async def comando_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await state.update_data(painel_atual="raiz")
    if EXIBIR_LOGS: logger.info("⌨️ Iniciando o bot no Menu Raiz.")
    await message.answer("🏠 Painel de Controle Inicial. Escolha uma área para gerenciar:", reply_markup=obter_teclado_raiz())

@dp.message(F.text == "Opções do Servidor ⚙️", StateFilter("*"))
async def menu_opcoes_servidor_handler(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    if EXIBIR_LOGS: logger.info("⚙️ Acessando o painel de Opções do Servidor.")
    await message.answer("⚙️ <b>Opções do Servidor</b>\nEscolha uma ferramenta de manutenção global:", reply_markup=obter_teclado_opcoes_servidor(), parse_mode="HTML")

# BLOCO ESPECIFICAMENTE INSERIDO
@dp.message(F.text == "Monitorar Servidor 🖥️", StateFilter("*"))
async def monitorar_servidor_oracle(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    if EXIBIR_LOGS: logger.info("🖥️ Iniciando auditoria assíncrona de saúde do servidor (Disco e Memória)...")
    msg_status = await message.answer("🖥️ Lendo sensores da máquina Oracle... ⏳")
    
    try:
        # Coleta as métricas de forma não bloqueante
        comando_disco = await asyncio.create_subprocess_exec("df", "-h", "/", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout_disco, _ = await comando_disco.communicate()
        linhas_disco = stdout_disco.decode().strip().split('\n')
        
        comando_ram = await asyncio.create_subprocess_exec("free", "-m", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout_ram, _ = await comando_ram.communicate()
        linhas_ram = stdout_ram.decode().strip().split('\n')
        
        import re
        pct_disco = 0
        if len(linhas_disco) > 1:
            match = re.search(r'(\d+)%', linhas_disco[1])
            if match: pct_disco = int(match.group(1))
            
        pct_ram = 0
        if len(linhas_ram) > 1:
            partes_ram = linhas_ram[1].split()
            if len(partes_ram) >= 3:
                total_ram = int(partes_ram[1])
                usada_ram = int(partes_ram[2])
                pct_ram = int((usada_ram / total_ram) * 100) if total_ram > 0 else 0

        icone_disco = "🟢" if pct_disco < 75 else "🟡" if pct_disco < 90 else "🔴"
        icone_ram = "🟢" if pct_ram < 75 else "🟡" if pct_ram < 90 else "🔴"
        
        texto = (
            "🖥️ <b>Monitoramento do Servidor Oracle</b>\n\n"
            f"{icone_disco} <b>Armazenamento (Disco /):</b>\n"
            f"<code>{linhas_disco[0]}\n{linhas_disco[1] if len(linhas_disco) > 1 else 'Indisponível'}</code>\n\n"
            f"{icone_ram} <b>Memória RAM (MB):</b>\n"
            f"<code>{linhas_ram[0]}\n{linhas_ram[1] if len(linhas_ram) > 1 else 'Indisponível'}</code>\n\n"
            "<i>Legenda: 🟢 Saudável | 🟡 Atenção | 🔴 Risco Crítico</i>"
        )
        
        if EXIBIR_LOGS: logger.info(f"✅ Auditoria concluída em background. Disco: {pct_disco}% | RAM: {pct_ram}%")
        await msg_status.edit_text(texto, parse_mode="HTML")
        
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha ao tentar coletar métricas no terminal do Linux: {e}")
        await msg_status.edit_text(f"❌ <b>Erro interno ao ler sensores:</b>\n<code>{e}</code>", parse_mode="HTML")

@dp.message(F.text == "Canal Afiliados 📺", StateFilter("*"))
async def menu_canal_principal(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    if EXIBIR_LOGS: logger.info("📂 Acessando a pasta do Canal Afiliados.")
    await message.answer("📺 <b>Menu do Canal Afiliados</b>\nGerencie as postagens e rotinas abaixo:", reply_markup=obter_teclado_principal(), parse_mode="HTML")

# NOVO: Funções de Gestão do Banco de Pedidos Individuais
def ler_banco_pedidos():
    try:
        with open("banco_pedidos.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def salvar_banco_pedidos(dados):
    with open("banco_pedidos.json", "w") as f:
        json.dump(dados, f, indent=4)

async def buscar_dados_financeiros_shopee(dias_retroativos=30):
    if not SHOPEE_APP_ID or not SHOPEE_APP_SECRET:
        if EXIBIR_LOGS: logger.warning("⏳ [API Shopee] Chaves financeiras ausentes no .env.")
        return None
        
    from datetime import timedelta
    agora = datetime.now(fuso_horario)
    inicio = agora - timedelta(days=dias_retroativos)
    
    start_ts = int(inicio.replace(hour=0, minute=0, second=0).timestamp())
    end_ts = int(agora.replace(hour=23, minute=59, second=59).timestamp())
    
    endpoint = "https://open-api.affiliate.shopee.com.br/graphql"
    
    payload = {
        "query": """query getConversionReport($purchaseTimeStart: Int64!, $purchaseTimeEnd: Int64!, $limit: Int!) {
            conversionReport(purchaseTimeStart: $purchaseTimeStart, purchaseTimeEnd: $purchaseTimeEnd, limit: $limit) {
                nodes {
                    purchaseTime
                    shopeeCommissionCapped
                    sellerCommission
                    totalCommission
                    orders {
                        orderId
                        orderStatus
                    }
                }
            }
        }""",
        "variables": {
            "purchaseTimeStart": str(start_ts),
            "purchaseTimeEnd": str(end_ts),
            "limit": 5000
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
                dados_crus = await response.text()
                if response.status == 200:
                    dados = json.loads(dados_crus)
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

def processar_e_salvar_pedidos_api(conversoes):
    pedidos_db = ler_banco_pedidos()
    historico = ler_historico_financeiro()
    
    historico_limpo = {}
    for k, v in historico.items():
        if isinstance(v, float) or isinstance(v, int):
            historico_limpo[k] = {"aprovado": float(v), "pendente": 0.0, "cancelado": 0.0, "shopee": 0.0, "vendedor": 0.0, "qtd_aprovado": 0, "qtd_pendente": 0, "qtd_cancelado": 0, "clicks": 0}
        else:
            v.setdefault("qtd_aprovado", 0)
            v.setdefault("qtd_pendente", 0)
            v.setdefault("qtd_cancelado", 0)
            v.setdefault("cancelado", 0.0)
            v.setdefault("clicks", 0)
            historico_limpo[k] = v

    if not conversoes:
        return historico_limpo

    houve_atualizacao = False
    import random
    
    for conv in conversoes:
        orders = conv.get("orders", [])
        if not orders: continue
        
        c_total = float(conv.get("totalCommission", "0"))
        c_shopee = float(conv.get("shopeeCommissionCapped", "0"))
        c_extra = float(conv.get("sellerCommission", "0"))
        
        from datetime import timezone
        dt_obj_utc = datetime.fromtimestamp(conv.get("purchaseTime", 0), tz=timezone.utc)
        dt_obj = dt_obj_utc.astimezone(fuso_horario)
        if EXIBIR_LOGS: logger.info("✅ Fuso horário corrigido de UTC para America/Sao_Paulo com sucesso.")
        
        dt_db_str = dt_obj.strftime("%Y-%m-%d")
        
        qtd_itens = len(orders)
        c_total_frac = c_total / qtd_itens
        c_shopee_frac = c_shopee / qtd_itens
        c_extra_frac = c_extra / qtd_itens

        for order in orders:
            order_sn = order.get("orderId")
            if not order_sn: 
                order_sn = f"{conv.get('purchaseTime')}_{random.randint(1000,9999)}"
                
            novo_status = order.get("orderStatus", "").upper()
            
            if order_sn in pedidos_db:
                estado_anterior = pedidos_db[order_sn]["status"]
                if estado_anterior != novo_status:
                    pedidos_db[order_sn]["status"] = novo_status
                    houve_atualizacao = True
                    
                if c_total_frac > 0:
                    if pedidos_db[order_sn]["comissao_total"] != c_total_frac:
                        pedidos_db[order_sn]["comissao_total"] = c_total_frac
                        pedidos_db[order_sn]["comissao_shopee"] = c_shopee_frac
                        pedidos_db[order_sn]["comissao_vendedor"] = c_extra_frac
                        houve_atualizacao = True
            else:
                pedidos_db[order_sn] = {
                    "data": dt_db_str,
                    "status": novo_status,
                    "comissao_total": c_total_frac,
                    "comissao_shopee": c_shopee_frac,
                    "comissao_vendedor": c_extra_frac
                }
                houve_atualizacao = True
                    
    if houve_atualizacao:
        salvar_banco_pedidos(pedidos_db)
        if EXIBIR_LOGS: logger.info("💾 Banco de Pedidos Individuais consolidado e blindado!")
        
    dias_no_banco = set(p["data"] for p in pedidos_db.values())
    
    for d_str in dias_no_banco:
        if d_str not in historico_limpo:
            historico_limpo[d_str] = {"aprovado": 0.0, "pendente": 0.0, "cancelado": 0.0, "shopee": 0.0, "vendedor": 0.0, "qtd_aprovado": 0, "qtd_pendente": 0, "qtd_cancelado": 0, "clicks": 0}
        else:
            historico_limpo[d_str]["aprovado"] = 0.0
            historico_limpo[d_str]["pendente"] = 0.0
            historico_limpo[d_str]["cancelado"] = 0.0
            historico_limpo[d_str]["qtd_aprovado"] = 0
            historico_limpo[d_str]["qtd_pendente"] = 0
            historico_limpo[d_str]["qtd_cancelado"] = 0
            historico_limpo[d_str]["shopee"] = 0.0
            historico_limpo[d_str]["vendedor"] = 0.0
            
    for sn, p in pedidos_db.items():
        d_str = p["data"]
        st = p["status"]
        if st == "COMPLETED":
            historico_limpo[d_str]["aprovado"] += p["comissao_total"]
            historico_limpo[d_str]["shopee"] += p.get("comissao_shopee", 0.0)
            historico_limpo[d_str]["vendedor"] += p.get("comissao_vendedor", 0.0)
            historico_limpo[d_str]["qtd_aprovado"] += 1
        elif st == "PENDING":
            historico_limpo[d_str]["pendente"] += p["comissao_total"]
            historico_limpo[d_str]["qtd_pendente"] += 1
        else:
            historico_limpo[d_str]["cancelado"] += p["comissao_total"]
            historico_limpo[d_str]["qtd_cancelado"] += 1
            
    salvar_historico_financeiro(historico_limpo)
    return historico_limpo

def obter_teclado_relatorios():
    botoes = [
        [KeyboardButton(text="Relatório Financeiro 💰"), KeyboardButton(text="Diagnóstico de IA 🧠")],
        [KeyboardButton(text="Relatórios de Filas 📋"), KeyboardButton(text="Logs de Erros ⚠️")],
        [KeyboardButton(text="Voltar ao Início 🔙")]
    ]
    return ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)

def obter_teclado_relatorios_filas():
    botoes = [
        [KeyboardButton(text="Fila do Espião 🕵️"), KeyboardButton(text="Fila do Espelhador 🔄")],
        [KeyboardButton(text="Voltar aos Relatórios 🔙")]
    ]
    return ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)

@dp.message(F.text == "Relatórios de Filas 📋", StateFilter("*"))
async def menu_relatorios_filas(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🚀 Acessando o submenu de Relatórios de Filas...")
    
    await state.clear()
    await message.answer("📋 <b>Central de Filas</b>\nEscolha qual fila ou radar deseja analisar:", reply_markup=obter_teclado_relatorios_filas(), parse_mode="HTML")
    await state.set_state(RelatoriosFluxo.menu_filas)
    if EXIBIR_LOGS: logger.info("✅ Menu de Relatórios de Filas exibido com sucesso!")

@dp.message(F.text == "Voltar aos Relatórios 🔙", StateFilter("*"))
async def voltar_relatorios_geral(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🔙 Retornando ao menu principal de relatórios...")
    await state.clear()
    await menu_relatorio_geral(message, state)

@dp.message(RelatoriosFluxo.menu_filas, F.text.in_(["Fila do Espelhador 🔄", "Fila do Espião 🕵️"]))
async def relatorio_filas_unificado(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    tipo_fila = "Espelhador" if "Espelhador" in message.text else "Espião"
    if EXIBIR_LOGS: logger.info(f"📊 Iniciando compilação do relatório unificado (Sem limites) para a fila do {tipo_fila}...")
    
    arquivo_fila = "fila_espelhador.json" if tipo_fila == "Espelhador" else "fila_clonagem.json"
    try:
        with open(arquivo_fila, "r", encoding="utf-8") as f:
            fila_data = json.load(f)
            fila = fila_data.get("fila", [])
    except (FileNotFoundError, json.JSONDecodeError):
        fila_data = {"fila": []}
        fila = []

    # --- Obter a defasagem temporal real configurada (Precisamos disso cedo para o Espião) ---
    atraso_dias = 0
    dados_espiao = {}
    if tipo_fila == "Espelhador":
        try:
            with open("espelhos_config.json", "r", encoding="utf-8") as f:
                 dados_espelho = json.load(f)
                 atraso_dias = dados_espelho.get("config_global", {}).get("intervalo_dias", 0)
        except: pass
    elif tipo_fila == "Espião":
        try:
            with open("alvos_espiao.json", "r", encoding="utf-8") as f:
                dados_espiao = json.load(f)
                atraso_dias = dados_espiao.get("intervalo_dias", 1)
        except: pass
        
    # Lógica de filtragem corrigida (Pente Fino ATIVO)
    pendentes = []
    agora = datetime.now(fuso_horario)
    agora_str = agora.strftime("%Y-%m-%d %H:%M:%S")
    
    if tipo_fila == "Espião":
        fila_limpa = []
        houve_alteracao = False
        limite_horas = (atraso_dias * 24) + 24 # Expiração fluida (Ex: D+1 expira em 48h)
        
        hoje_str = agora.strftime("%Y-%m-%d")
        
        for item in fila:
            # ✅ CORREÇÃO: Mantém no visual os que foram postados HOJE. Deleta os antigos.
            if item.get("processado", False):
                if item.get("data_postagem") == hoje_str:
                    if EXIBIR_LOGS: logger.info(f"👁️ Pente Fino (Relatório): Mantendo o vídeo postado hoje ({item.get('id')}) no visual da fila.")
                    fila_limpa.append(item)
                else:
                    houve_alteracao = True
                continue
                
            data_cap_str = item.get("data_captura", "")
            if data_cap_str:
                try:
                    data_captura = datetime.strptime(data_cap_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario)
                    horas_na_fila = (agora - data_captura).total_seconds() / 3600
                    
                    # Elimina os vídeos fantasmas que ficaram presos no estado "Atrasado"
                    if horas_na_fila > limite_horas:
                        if EXIBIR_LOGS: logger.info(f"🧹 Pente Fino (Relatório): Removendo clone expirado ({horas_na_fila:.1f}h).")
                        houve_alteracao = True
                        caminho_video = item.get("caminho_video")
                        if caminho_video and os.path.exists(caminho_video):
                            try: os.remove(caminho_video)
                            except: pass
                        continue # Pula este item, ele não vai para a fila limpa
                except ValueError:
                    pass
            
            fila_limpa.append(item)
            
        # Se encontrou lixo, salva o JSON limpo imediatamente
        if houve_alteracao:
            fila_data["fila"] = fila_limpa
            salvar_fila_clonagem(fila_data)
            
        pendentes = fila_limpa
        
    elif tipo_fila == "Espelhador":
        for item in fila:
            if not item.get("processado", False):
                data_pub = item.get("data_publicacao", "")
                if not data_pub or data_pub > agora_str:
                    pendentes.append(item)
    
    if not pendentes:
        await message.answer(f"📭 A fila do {tipo_fila} está vazia no momento.", parse_mode="HTML")
        if EXIBIR_LOGS: logger.info(f"✅ Relatório do {tipo_fila} gerado (Fila vazia).")
        return
        
    cache_nomes = ler_cache_nomes_grupos()
    rotas_agrupadas = {}
    
    if tipo_fila == "Espelhador":
        import espelhador
        dados_rotas = espelhador.ler_espelhos()
        mapa_rotas = {r["nome"]: r for r in dados_rotas.get("rotas", [])}
        
        for item in pendentes:
            nome_rota = item.get("nome_rota", "Rota Desconhecida")
            if nome_rota not in rotas_agrupadas: rotas_agrupadas[nome_rota] = []
            rotas_agrupadas[nome_rota].append(item)
            
    else: 
        mapa_rotas = {
            "Radar Global": {
                "inicio": dados_espiao.get("inicio", 10),
                "fim": dados_espiao.get("fim", 22),
                "status_canais": dados_espiao.get("status_alvos", {})
            }
        }
        
        # ✅ ORDENAÇÃO INTELIGENTE DO ESPIÃO
        # Grupo 0 (Topo): Postados hoje, ordenados pela hora de postagem
        # Grupo 1 (Fundo): Pendentes, ordenados pela data e hora de captura
        def chave_ordenacao(item):
            if item.get("processado", False):
                return (0, item.get("horario_postagem", "00:00"))
            return (1, item.get("data_captura", "2099-01-01 00:00:00"))
            
        pendentes.sort(key=chave_ordenacao)
        rotas_agrupadas["Radar Global"] = pendentes
         
    titulo_atraso = f" (D+{atraso_dias})"

    mensagens_para_enviar = []
    texto_atual = f"📊 <b>Relatório da Fila do {tipo_fila}{titulo_atraso}</b>\n\n"

    for nome_rota, itens in rotas_agrupadas.items():
        rota_info = mapa_rotas.get(nome_rota, {})
        inicio = rota_info.get("inicio", 10)
        fim = rota_info.get("fim", 22)
        status_canais = rota_info.get("status_canais") or rota_info.get("status_alvos") or {}
        
        info_sorteio = ""
        if tipo_fila == "Espião":
            qtd_aguardando = len([i for i in itens if not i.get("processado")])
            proximo_proc = fila_data.get("proximo_processamento")
            if proximo_proc and proximo_proc != "2000-01-01 00:00:00":
                try:
                    hora_sorteio = datetime.strptime(proximo_proc, "%Y-%m-%d %H:%M:%S").strftime("%H:%M")
                    info_sorteio = f"🎲 <b>Próximo Sorteio:</b> Previsto para {hora_sorteio}\n"
                except: pass
            cabecalho_rota = f"📡 <b>Rota: {nome_rota}</b> ({qtd_aguardando} vídeos na urna)\n🕒 <b>Janela:</b> {inicio}h às {fim}h\n{info_sorteio}"
        else:
            texto_postagem = "Imediata (D+0)" if atraso_dias == 0 else f"D+{atraso_dias}, entre {inicio}h e {fim}h"
            cabecalho_rota = f"📡 <b>Rota: {nome_rota}</b> ({len(itens)} vídeos aguardando)\n🕒 <b>Postagem:</b> {texto_postagem}\n"
        
        if len(texto_atual) + len(cabecalho_rota) > 3800:
            mensagens_para_enviar.append(texto_atual)
            texto_atual = f"📊 <b>Relatório da Fila do {tipo_fila} (Continuação)</b>\n\n"
            
        texto_atual += cabecalho_rota
        
        for i, v in enumerate(itens, 1):
            data_cap = v.get("data_captura", "Data não registrada")
            
            origem_bruta = str(v.get("chat_origem", v.get("origem", v.get("grupo_id", v.get("canal_id", "Desconhecida")))))
            link_original = v.get("link_original", "")
            msg_id = v.get("mensagem_id") or v.get("msg_id") or v.get("message_id")
            
            # --- 1. RESGATE ESTRUTURAL DE ORIGEM ---
            if origem_bruta in ["Desconhecida", "Origem desconhecida", "Origem não mapeada", "None", ""]:
                if link_original and "t.me/c/" in link_original:
                    try: origem_bruta = "-100" + link_original.split("t.me/c/")[1].split("/")[0]
                    except: pass
                elif link_original and "t.me/" in link_original:
                    try: origem_bruta = "@" + link_original.split("t.me/")[1].split("/")[0]
                    except: pass

            # --- 2. CONSTRUÇÃO PRIORITÁRIA DO LINK DO TELEGRAM ---
            # Ignora o link da Shopee gravado e força a rota para a mensagem original no Telegram
            link_telegram = ""
            if msg_id and origem_bruta not in ["Desconhecida", "Origem desconhecida", "Origem não mapeada", "None", ""]:
                if origem_bruta.lstrip("-").isdigit():
                    chat_id_limpo = origem_bruta.replace("-100", "").replace("-", "")
                    link_telegram = f"https://t.me/c/{chat_id_limpo}/{msg_id}"
                elif origem_bruta.startswith("@"):
                    username = origem_bruta.replace("@", "")
                    link_telegram = f"https://t.me/{username}/{msg_id}"
            
            # --- 3. ETIQUETA INTELIGENTE PARA O LINK ---
            link_final_exibicao = link_telegram if link_telegram else link_original
            
            if link_final_exibicao:
                if "t.me" in link_final_exibicao:
                    texto_link = "Ver Post no Telegram"
                elif "shopee" in link_final_exibicao or "shp.ee" in link_final_exibicao:
                    texto_link = "Ver Produto na Shopee"
                else:
                    texto_link = "Ver Link"
                link_display = f"<a href='{link_final_exibicao}'>{texto_link}</a>"
            else:
                link_display = "<i>Sem link direto</i>"
                
            # --- 4. RESOLUÇÃO DE NOMES COM CACHE E BUSCA PROFUNDA ---
            if origem_bruta in ["Desconhecida", "Origem desconhecida", "Origem não mapeada", "None", ""]:
                display_origem = "<code>Pendente de rastreio</code>"
            else:
                nome_origem = origem_bruta
                nome_gravado_no_item = v.get("nome_origem")
                
                if nome_gravado_no_item and str(nome_gravado_no_item) != origem_bruta:
                    nome_origem = str(nome_gravado_no_item)
                    if origem_bruta not in cache_nomes:
                        cache_nomes[origem_bruta] = nome_origem
                        salvar_nome_grupo(origem_bruta, nome_origem)
                elif origem_bruta in cache_nomes:
                    nome_origem = cache_nomes[origem_bruta]
                else:
                    nome_encontrado = None
                    base_dados = locals().get("dados_rotas", {}) if tipo_fila == "Espelhador" else locals().get("dados_espiao", {})
                    status_alvos = base_dados.get("status_alvos", {})
                    
                    for alvo_key, dados_alvo in status_alvos.items():
                        if isinstance(dados_alvo, dict):
                            id_alvo = str(dados_alvo.get("id", ""))
                            if id_alvo and (id_alvo == origem_bruta or id_alvo.replace("-100", "") == origem_bruta.replace("-100", "")):
                                nome_encontrado = dados_alvo.get("nome")
                                break
                                
                    if not nome_encontrado and tipo_fila == "Espelhador":
                        def busca_recursiva(dados, alvo_id):
                            if isinstance(dados, dict):
                                str_id = str(dados.get("id", dados.get("chat_id", "")))
                                if str_id and (str_id == alvo_id or str_id.replace("-100", "") == alvo_id.replace("-100", "")):
                                    return dados.get("nome")
                                for val in dados.values():
                                    res = busca_recursiva(val, alvo_id)
                                    if res: return res
                            elif isinstance(dados, list):
                                for item_lista in dados:
                                    res = busca_recursiva(item_lista, alvo_id)
                                    if res: return res
                            return None
                        nome_encontrado = busca_recursiva(base_dados, origem_bruta)

                    if nome_encontrado:
                        nome_origem = nome_encontrado
                    
                    if (nome_origem == origem_bruta or not nome_origem) and origem_bruta.lstrip("-").isdigit():
                        so_numeros = origem_bruta.replace("-100", "").replace("-", "")
                        variacoes = [origem_bruta, f"-100{so_numeros}", f"-{so_numeros}", so_numeros]
                        variacoes_unicas = list(dict.fromkeys(variacoes))
                        
                        for var in variacoes_unicas:
                            try:
                                chat_obj = await bot.get_chat(var)
                                nome_origem = chat_obj.title or chat_obj.full_name or var
                                origem_bruta = var 
                                break 
                            except Exception:
                                continue
                            finally:
                                await asyncio.sleep(0.3)
                    
                    cache_nomes[origem_bruta] = nome_origem
                    if nome_origem != origem_bruta:
                        salvar_nome_grupo(origem_bruta, nome_origem)
                
                display_origem = f"{nome_origem[:25]}" if nome_origem != origem_bruta else f"{origem_bruta}"
                
            # --- 5. CÁLCULO DINÂMICO DE DATAS ---
            status_dia = "⚪ Indefinido"
            data_cap_formatada = "Desconhecida"
            data_alvo = None
            
            if data_cap != "Data não registrada":
                try:
                    formato = "%Y-%m-%d %H:%M:%S" if len(data_cap) > 10 else "%Y-%m-%d"
                    data_obj = datetime.strptime(data_cap, formato)
                    data_cap_formatada = data_obj.strftime("%d/%m às %H:%M")
                    
                    data_alvo = data_obj + timedelta(days=atraso_dias)
                    hoje_obj = agora.date()
                    
                    if tipo_fila == "Espelhador":
                        horario_disparo_str = v.get("horario_disparo", "")
                        if horario_disparo_str:
                            hd_obj = datetime.strptime(horario_disparo_str, "%Y-%m-%d %H:%M:%S")
                            if hd_obj.date() == hoje_obj:
                                status_dia = "🔴 Atrasado" if agora > hd_obj else "🟢 Hoje"
                            elif hd_obj.date() > hoje_obj:
                                status_dia = "🟡 Amanhã" if hd_obj.date() == hoje_obj + timedelta(days=1) else f"🔵 D+{abs((hd_obj.date() - hoje_obj).days)}"
                            else:
                                status_dia = "🔴 Atrasado"
                        else:
                            # ✅ CORREÇÃO: Aplica a tag correta baseada no D+0, D+1 ou D+2
                            if atraso_dias == 0:
                                status_dia = "🟢 Na Fila (D+0)" if data_obj.date() == hoje_obj else "🔴 Retido/Falha"
                            elif atraso_dias == 1:
                                status_dia = "🟡 Represa (D+1)" if data_obj.date() == hoje_obj else "🔴 Retido/Falha"
                            else:
                                status_dia = f"🔵 Represa (D+{atraso_dias})" if data_obj.date() == hoje_obj else "🔴 Retido/Falha"
                    else:
                        if data_alvo.date() == hoje_obj:
                            # ✅ INTELIGÊNCIA: Se já passou da hora limite, a janela fechou
                            if agora.hour >= fim:
                                status_dia = "🔴 Atrasado (Janela Fechada)"
                            else:
                                status_dia = "🟢 Hoje"
                        elif data_alvo.date() == hoje_obj + timedelta(days=1):
                            status_dia = "🟡 Amanhã"
                        elif data_alvo.date() < hoje_obj:
                            status_dia = "🔴 Atrasado"
                        else:
                            status_dia = f"🔵 D+{abs((data_alvo.date() - hoje_obj).days)}"
                except Exception:
                    pass

            # --- 6. CÁLCULO DE PREVISÃO EXATA E COMPACTA ---
            if tipo_fila == "Espelhador":
                data_pub = v.get("horario_disparo", "")
                if data_pub:
                    try:
                        dp_obj = datetime.strptime(data_pub, "%Y-%m-%d %H:%M:%S")
                        previsao_texto = dp_obj.strftime("%d/%m às %H:%M")
                    except:
                        previsao_texto = "Pendente na esteira"
                else:
                    # ✅ CORREÇÃO: Altera o texto se for processamento no mesmo dia
                    previsao_texto = "Processamento Imediato" if atraso_dias == 0 else "Aguardando virada do dia"
            else: # Lógica para o Espião
                is_postado = v.get("processado", False)
                horario_postagem = v.get("horario_postagem", "")
                
                if is_postado:
                    status_dia = "✅ Postado"
                    previsao_texto = f"Hoje às {horario_postagem}"
                else:
                    if "Fechada" in status_dia:
                        previsao_texto = f"Amanhã {inicio}h-{fim}h"
                        status_dia = "🔴 Atrasado" # Limpa a tag para o layout
                    elif "Atrasado" in status_dia:
                        if agora.hour >= fim:
                            previsao_texto = f"Amanhã {inicio}h-{fim}h"
                        else:
                            previsao_texto = "Imediato"
                    else:
                        previsao_texto = f"Sorteio {inicio}h-{fim}h"

           # --- 7. NOVO LAYOUT VISUAL EM 3 LINHAS ---
            linha_video = (
                f"<b>{i}.</b> {status_dia} | 📡 {display_origem}\n"
                f"   └ 📥 Cap: {data_cap_formatada} ➡️ 📤 Prev: {previsao_texto}\n"
                f"   └ 🔗 {link_display}\n"
            )
            
            if len(texto_atual) + len(linha_video) > 3800:
                mensagens_para_enviar.append(texto_atual)
                texto_atual = f"📊 <b>Relatório da Fila do {tipo_fila} (Continuação)</b>\n\n📡 <b>Rota: {nome_rota} (Cont.)</b>\n"
                
            texto_atual += linha_video
            
        texto_atual += "\n"

    mensagens_para_enviar.append(texto_atual)

    for msg in mensagens_para_enviar:
        await message.answer(msg, parse_mode="HTML", disable_web_page_preview=True)
        
    if EXIBIR_LOGS: logger.info(f"✅ Relatório unificado do {tipo_fila} entregue com sucesso!")

@dp.message(Command("nomeargrupo"), StateFilter("*"))
async def nomear_grupo_manual(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return

    partes = message.text.split(maxsplit=2)
    if len(partes) < 3:
        await message.answer(
            "⚠️ <b>Uso:</b> <code>/nomeargrupo ID_ou_@username Nome do Grupo</code>\n\n"
            "Use quando o bot não conseguir puxar o nome sozinho (ex: quando o bot não é membro do canal, só o Espião é).\n"
            "Exemplo: <code>/nomeargrupo -1001234567890 Achadinhos da Maria</code>",
            parse_mode="HTML"
        )
        return

    comando = partes[0]
    chat_id_bruto = partes[1]
    nome = partes[2].strip()

    chat_id_limpo = chat_id_bruto.strip()
    if chat_id_limpo.replace('-', '').isdigit():
        numeros = chat_id_limpo.replace('-', '')
        if numeros.startswith("100") and len(numeros) > 10:
            numeros = numeros[3:]
        chat_id_limpo = f"-100{numeros}"

    # Salva no cache geral do bot
    salvar_nome_grupo(chat_id_limpo, nome)
    
    # Atualiza também o cache de vídeos autorais se for a origem ou destino atual
    config_autorais = ler_autorais_config()
    
    origem_atual = str(config_autorais.get("origem", ""))
    destino_atual = str(config_autorais.get("destino", ""))
    
    # Verifica variações do ID (-100, sem -100)
    id_variacoes = [chat_id_limpo, chat_id_limpo.replace("-100", "-"), chat_id_limpo.replace("-100", "")]
    
    if any(var == origem_atual for var in id_variacoes) or any(var == destino_atual for var in id_variacoes):
         await message.answer(f"✅ Pronto! <code>{chat_id_limpo}</code> vai aparecer como <b>{nome}</b> nos painéis e relatórios.", parse_mode="HTML")
    else:
         await message.answer(f"✅ Nome registado! <code>{chat_id_limpo}</code> foi associado a <b>{nome}</b>.", parse_mode="HTML")

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
    if EXIBIR_LOGS: logger.info("🚀 Acionando extração de dados e recálculo dinâmico pelo Rastreio Individual...")
    
    conversoes = await buscar_dados_financeiros_shopee(30)
    historico_limpo = processar_e_salvar_pedidos_api(conversoes)
    
    from datetime import timedelta
    hoje = datetime.now(fuso_horario)
    data_corte = (hoje - timedelta(days=30)).strftime("%Y-%m-%d")
    
    pagos, pendentes, cancelados = 0, 0, 0
    for k, v in historico_limpo.items():
        if k >= data_corte:
            pagos += v.get("qtd_aprovado", 0)
            pendentes += v.get("qtd_pendente", 0)
            cancelados += v.get("qtd_cancelado", 0)
            
    total_pedidos = pagos + pendentes + cancelados
    taxa_conversao = (pagos / total_pedidos * 100) if total_pedidos > 0 else 0.0
    
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
    qtd_cancelado_mes = sum(v.get("qtd_cancelado", 0) for k, v in historico_limpo.items() if k.startswith(mes_atual_str))
    cancelado_mes = sum(v.get("cancelado", 0.0) for k, v in historico_limpo.items() if k.startswith(mes_atual_str))
    clicks_mes = sum(v.get("clicks", 0) for k, v in historico_limpo.items() if k.startswith(mes_atual_str))
    total_mes = aprovado_mes + pendente_mes + cancelado_mes
    
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
    )
    
    # ✅ NOVA MÉTRICA: Estimativa de Faturamento (CORRIGIDA CONTRA ATRASOS DA API)
    import calendar
    dias_no_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    dia_atual = hoje.day
    
    # 1. Inteligência para ignorar o atraso da API da Shopee
    dias_sincronizados = 0
    for i in range(1, dia_atual + 1):
        d_str = f"{hoje.year}-{hoje.month:02d}-{i:02d}"
        dados_d = historico_limpo.get(d_str, {})
        # Se o dia teve alguma movimentação (venda ou cancelamento), ele conta como dia útil sincronizado
        if dados_d.get("aprovado", 0) + dados_d.get("pendente", 0) + dados_d.get("cancelado", 0) > 0:
            dias_sincronizados = i
            
    faturamento_valido_mes = aprovado_mes + pendente_mes
    estimativa_mensal = 0.0
    
    if dias_sincronizados > 0 and faturamento_valido_mes > 0:
        if EXIBIR_LOGS: logger.info(f"🧮 Calculando projeção mensal sobre faturamento válido de R$ {faturamento_valido_mes:.2f} (excluindo cancelados)...")
        media_diaria = faturamento_valido_mes / dias_sincronizados
        estimativa_mensal = media_diaria * dias_no_mes
        texto += f"🚀 <b>PROJEÇÃO MENSAL ESTIMADA: R$ {f_br(estimativa_mensal)}</b>\n"
        
        from datetime import timedelta
        ontem = hoje - timedelta(days=1)
        ontem_faturamento_str = ontem.strftime("%Y-%m-%d")
        
        dados_ontem = historico_limpo.get(ontem_faturamento_str, {})
        faturamento_ontem = dados_ontem.get("aprovado", 0.0) + dados_ontem.get("pendente", 0.0)
        
        if media_diaria > 0:
            variacao_ontem = ((faturamento_ontem - media_diaria) / media_diaria) * 100
            sinal_ontem = "📈 +" if variacao_ontem >= 0 else "📉 "
            texto_var = f"{sinal_ontem}{variacao_ontem:.1f}%"
        elif media_diaria == 0 and faturamento_ontem > 0:
            texto_var = "📈 +100.0%"
        else:
            texto_var = "0.0%"
            
        texto += f"⚖️ <b>Média Diária: R$ {f_br(media_diaria)}</b> <i>(Ontem: R$ {f_br(faturamento_ontem)} | {texto_var})</i>\n\n"
        if EXIBIR_LOGS: logger.info(f"📊 Desempenho de ontem calculado: R$ {faturamento_ontem:.2f} face à média de R$ {media_diaria:.2f} ({texto_var})")
        
    else:
        texto += f"🚀 <b>PROJEÇÃO MENSAL ESTIMADA: Calculando...</b>\n\n"
    
    texto += "🗓️ <b>HISTÓRICO MENSAL E CRESCIMENTO</b>\n"
    meses_ordenados_desc = sorted(dados_por_mes.keys(), reverse=True)
    
    for i, mes in enumerate(meses_ordenados_desc):
        dados_m = dados_por_mes[mes]
        total_m = dados_m["aprovado"] + dados_m["pendente"] + dados_m.get("cancelado", 0.0)
        
        try:
            ano_str, mes_str = mes.split('-')
            mes_fmt = f"{MESES_PT.get(mes_str, mes_str)}/{ano_str[2:]}"
        except:
            mes_fmt = mes

        variacao_texto = ""
        if i < len(meses_ordenados_desc) - 1:
            mes_anterior = meses_ordenados_desc[i+1]
            total_ant = dados_por_mes[mes_anterior]["aprovado"] + dados_por_mes[mes_anterior]["pendente"] + dados_por_mes[mes_anterior].get("cancelado", 0.0)
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
        total_a = dados_a["aprovado"] + dados_a["pendente"] + dados_a.get("cancelado", 0.0)
        
        variacao_texto = ""
        if i < len(anos_ordenados_desc) - 1:
            ano_anterior = anos_ordenados_desc[i+1]
            total_ant = dados_por_ano[ano_anterior]["aprovado"] + dados_por_ano[ano_anterior]["pendente"] + dados_por_ano[ano_anterior].get("cancelado", 0.0)
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
            v_tot = vals.get("aprovado", 0.0) + vals.get("pendente", 0.0) + vals.get("cancelado", 0.0)
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
        v_tot = v_aprov + v_pend + v_canc
        
        if EXIBIR_LOGS: logger.info(f"🧮 Calculando proporções diárias para {d_br}...")
        total_pedidos_d = q_aprov + q_pend + q_canc
        pct_aprov_d = (q_aprov / total_pedidos_d * 100) if total_pedidos_d > 0 else 0.0
        pct_pend_d = (q_pend / total_pedidos_d * 100) if total_pedidos_d > 0 else 0.0
        pct_canc_d = (q_canc / total_pedidos_d * 100) if total_pedidos_d > 0 else 0.0
        
        variacao_texto = ""
        d_obj = datetime.strptime(d_str, "%Y-%m-%d")
        d_ant_str = (d_obj - timedelta(days=1)).strftime("%Y-%m-%d")
        
        dados_ant = historico_limpo.get(d_ant_str, {})
        v_tot_ant = dados_ant.get("aprovado", 0.0) + dados_ant.get("pendente", 0.0) + dados_ant.get("cancelado", 0.0)
        
        if v_tot_ant > 0:
            variacao = ((v_tot - v_tot_ant) / v_tot_ant) * 100
            sinal = "📈 +" if variacao >= 0 else "📉 "
            variacao_texto = f" <b>({sinal}{variacao:.1f}%)</b>"
        elif v_tot_ant == 0 and v_tot > 0:
            variacao_texto = " <b>(📈 +100%)</b>"
        
        texto += f"• <b>{d_br}</b>: R$ {f_br(v_tot)}{variacao_texto}\n"
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
        valores_pedidos = []
        valores_estimativa = []
        
        mes_atual_grafico = hoje.strftime("%Y-%m")
        
        for m in meses_ano_atual:
            mes_numero = m.split('-')[1]
            labels_grafico.append(MESES_ABREV_PT.get(mes_numero, mes_numero))
                
            v_aprov = dados_por_mes.get(m, {}).get("aprovado", 0.0)
            v_pend = dados_por_mes.get(m, {}).get("pendente", 0.0)
            v_valido = v_aprov + v_pend
            
            valores_comissao.append(v_valido)
            
            q_aprov = dados_por_mes.get(m, {}).get("qtd_aprovado", 0)
            q_pend = dados_por_mes.get(m, {}).get("qtd_pendente", 0)
            valores_pedidos.append(q_aprov + q_pend)
            
            if m == mes_atual_grafico:
                valores_estimativa.append(estimativa_mensal)
            elif m < mes_atual_grafico:
                valores_estimativa.append(v_valido)
            else:
                valores_estimativa.append(float('nan'))

        if EXIBIR_LOGS: logger.info("📈 Estruturando gráfico...")
        fig, ax1 = plt.subplots(figsize=(8, 5), facecolor='#f4f4f9')
        ax1.set_facecolor('#f4f4f9')
        
        bars = ax1.bar(labels_grafico, valores_comissao, color='#ff6600', edgecolor='black', linewidth=0.5, label='Comissão Atual (R$)')
        line_est, = ax1.plot(labels_grafico, valores_estimativa, color='#0066cc', marker='^', linestyle=':', linewidth=2, label='Projeção / Fechamento')
        
        ax1.set_ylabel('Comissão (R$)', fontsize=10, color='#333333')
        ax1.grid(axis='y', linestyle='--', alpha=0.5)
        
        ax2 = ax1.twinx()
        line_ped, = ax2.plot(labels_grafico, valores_pedidos, color='#2ca02c', marker='s', linestyle='--', linewidth=2, label='Pedidos Gerados')
        ax2.set_ylabel('Quantidade de Pedidos', fontsize=10, color='#333333')
        
        plt.title(f'Evolução de Faturamento e Vendas ({ano_atual_str})', fontsize=12, fontweight='bold', color='#333333')
        
        offset_y = max([v for v in valores_comissao + valores_estimativa if v == v]) * 0.02 if any(v == v for v in valores_comissao + valores_estimativa) else 0

        for bar in bars:
            yval = bar.get_height()
            if yval > 0:
                ax1.text(bar.get_x() + bar.get_width()/2, yval + offset_y, f'R${yval:.0f}', ha='center', va='bottom', fontsize=8, fontweight='bold', color='#333333')

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
                client_genai.models.generate_content,
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

@dp.message(F.text == "Logs de Erros ⚠️", StateFilter("*"))
async def gerar_relatorio_logs(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    msg_status = await message.answer("⚠️ A extrair o histórico de falhas do banco de dados... Aguarde ⏳")
    if EXIBIR_LOGS: logger.info("🚀 A iniciar a auditoria da tabela erros_logs...")
    
    try:
        conexao = sqlite3.connect("banco_dados.db")
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()
        
        # Puxa os últimos 5 erros ordenados do mais recente para o mais antigo
        cursor.execute("SELECT * FROM erros_logs ORDER BY id DESC LIMIT 5")
        erros_db = cursor.fetchall()
        
        cursor.execute("SELECT COUNT(*) FROM erros_logs")
        total_erros = cursor.fetchone()[0]
        conexao.close()
        
        if total_erros == 0:
            if EXIBIR_LOGS: logger.info("✅ A tabela de logs está vazia. Sistema limpo.")
            await msg_status.edit_text("✅ <b>Sistema Limpo!</b>\nNão existe nenhum registo de erros no banco de dados. A automação está a funcionar perfeitamente.", parse_mode="HTML")
            return
            
        if EXIBIR_LOGS: logger.info(f"📊 Leitura concluída. Foram encontrados {total_erros} registos no total.")
        
        texto = f"⚠️ <b>Relatório de Erros Recentes</b> (Últimos {len(erros_db)} de {total_erros})\n\n"
        for i, erro in enumerate(erros_db, 1):
            data_hora = erro["timestamp"]
            origem = erro["origem"]
            detalhe = str(erro["erro"])[:200]
            
            texto += f"<b>{i}. ⏱️ {data_hora}</b>\n"
            texto += f"📍 <i>Origem:</i> {origem}\n"
            texto += f"❌ <i>Falha:</i> <code>{detalhe}</code>\n\n"
            
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        teclado_limpar = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Limpar Histórico de Erros 🧹", callback_data="limpar_logs")]]
        )
        
        await msg_status.edit_text(texto, parse_mode="HTML", reply_markup=teclado_limpar)
        
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha crítica ao processar a leitura dos logs no SQLite: {e}")
        await msg_status.edit_text(f"❌ <b>Erro interno ao processar os logs:</b>\n<code>{e}</code>", parse_mode="HTML")

# ✅ NOVO: Handler (Callback) para limpar o histórico do banco de dados
from aiogram.types import CallbackQuery

@dp.callback_query(F.data == "limpar_logs")
async def limpar_historico_erros(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    
    if EXIBIR_LOGS: logger.info("🧹 Pedido de exclusão do histórico de erros recebido via botão interativo.")
    
    try:
        conexao = sqlite3.connect("banco_dados.db")
        cursor = conexao.cursor()
        cursor.execute("DELETE FROM erros_logs")
        conexao.commit()
        conexao.close()
        
        # Cria o arquivo de trava na raiz do projeto para silenciar erros temporariamente
        with open("trava_manutencao.txt", "w") as f:
            f.write("ativo")
            
        if EXIBIR_LOGS: logger.info("✅ Tabela erros_logs limpa e trava_manutencao.txt ativada.")
        await callback.message.edit_text("✅ <b>Histórico Limpo e Trava Ativada!</b>\nOs erros antigos foram apagados do banco de dados. O abafador de ruído está ativo enquanto você faz as correções no código.", parse_mode="HTML")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro de permissão/sistema ao tentar limpar a tabela de logs: {e}")
        await callback.answer(f"Erro ao apagar: {e}", show_alert=True)
        
    await callback.answer()

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

    # 🔁 Roteamento Inteligente: Se estiver na confirmação de Zerar Filas Globais
    if estado_atual == "ConfigFluxo:aguardando_confirmacao_zerar_filas":
        await state.clear()
        await message.answer("Ação cancelada. O sistema não foi limpo.", reply_markup=obter_teclado_opcoes_servidor())
        return

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
        
    # 🔁 Roteamento Inteligente: Se estiver no Gerador de Achadinhos
    if estado_atual and estado_atual.startswith("AchadinhosFluxo"):
        await state.clear()
        await message.answer("Ação cancelada.")
        await painel_achadinhos(message, state)
        return

    # 🔁 Roteamento Inteligente: Se estiver em Vídeos Autorais
    if estado_atual and estado_atual.startswith("AutoraisFluxo"):
        await state.clear()
        await message.answer("Ação cancelada.")
        await painel_autorais(message, state)
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

    if EXIBIR_LOGS: logger.info("🔍 Limpeza de memória solicitada. Avaliando necessidade de rollback no contador global...")
    
    # ✅ SISTEMA DE ROLLBACK: Devolve o número reservado ao cancelar a criação da postagem
    numero_reservado = data.get('numero_reservado')
    if estado_atual and estado_atual.startswith("PostagemFluxo") and numero_reservado is not None:
        async with _lock_contador:
            contador_atual = ler_contador()
            # Só executa o rollback se o contador não tiver avançado por outro processo simultâneo
            if contador_atual == numero_reservado + 1:
                salvar_contador(numero_reservado)
                if EXIBIR_LOGS: logger.info(f"⏪ Rollback executado: Número {numero_reservado} foi devolvido ao contador global com sucesso.")
            else:
                if EXIBIR_LOGS: logger.warning(f"⚠️ Rollback abortado: O contador já avançou para {contador_atual} e não pode ser revertido com segurança.")

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
        video_path = f"temp/temp_{file_id}.mp4"
        await bot.download_file(file_info.file_path, destination=video_path)

        # 2. Processa a Copy pela API Central do Gemini
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
        
        chamada_gerada = await analisar_video_gemini(video_path, prompt_ia, EXIBIR_LOGS)
        if not chamada_gerada:
            raise Exception("Falha total na análise do vídeo pela IA.")
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
        video_path_recuperacao = f"temp/temp_{file_id}.mp4"
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
            chamada_gerada = await analisar_video_gemini(video_path, prompt_ia, EXIBIR_LOGS)
            if not chamada_gerada:
                raise Exception("Falha total na análise de re-processamento.")
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
        if EXIBIR_LOGS: logger.info(f"📅 Inserindo no Banco SQLite de forma concorrente. Data alvo: {data_agendamento_base}")
        id_unico = f"{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}"
        
        try:
            conexao = sqlite3.connect("banco_dados.db")
            cursor = conexao.cursor()
            
            # Descobre a próxima prioridade para este dia
            cursor.execute("SELECT MAX(prioridade) FROM fila_postagens WHERE data_alvo = ?", (data_agendamento_base,))
            resultado = cursor.fetchone()[0]
            proxima_prioridade = (resultado if resultado else 0) + 1
            
            cursor.execute('''
                INSERT INTO fila_postagens (id_unico, caminho_video, video_id, legenda, data_alvo, prioridade)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (id_unico, caminho_vid, vid_id, caption, data_agendamento_base, proxima_prioridade))
            
            conexao.commit()
            conexao.close()
            if EXIBIR_LOGS: logger.info(f"✅ Vídeo blindado no SQLite com prioridade {proxima_prioridade}.")
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro grave ao inserir vídeo direto no banco: {e}")

    caminho_final = caminho_processado if caminho_processado and os.path.exists(caminho_processado) else caminho_video_original
    
    if caminho_processado and caminho_video_original and os.path.exists(caminho_video_original):
        os.remove(caminho_video_original)

    if EXIBIR_LOGS: logger.info("🚀 Aplicando blindagem: Assegurando persistência do video_id para o fallback de segurança...")

    if nivel_4_ativado:
        legenda_shopee = montar_legenda(texto_longo, is_rodape=False, plataforma_alvo="Apenas Shopee 🛒")
        if EXIBIR_LOGS: logger.info(f"📦 A agendar vídeo 1/2 (Shopee) na fila invisível para a data: {data_agendamento_base}.")
        adicionar_a_fila(caminho_final, video_id_fallback, legenda_shopee)
        
        legenda_tiktok = montar_legenda(texto_longo, is_rodape=False, plataforma_alvo="Apenas TikTok 🎵")
        if EXIBIR_LOGS: logger.info(f"📦 A agendar vídeo 2/2 (TikTok) na fila invisível para a data: {data_agendamento_base}.")
        adicionar_a_fila(caminho_final, video_id_fallback, legenda_tiktok)
    else:
        if EXIBIR_LOGS: logger.info(f"📦 A agendar vídeo consolidado na fila invisível para a data: {data_agendamento_base}.")
        adicionar_a_fila(caminho_final, video_id_fallback, legenda_final)
        
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

@dp.message(F.text == "Zerar Filas e Tarefas 🧹", StateFilter("*"))
async def confirmar_zerar_filas_tarefas(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("⚠️ Solicitando seleção do tipo de limpeza de filas.")
    
    teclado_opcoes_limpeza = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Limpar Tudo (Geral) 💥")],
            [KeyboardButton(text="Limpar Fila Principal 🛒"), KeyboardButton(text="Limpar Fila do Espião 🕵️")],
            [KeyboardButton(text="Limpar Fila Espelhador 🔄"), KeyboardButton(text="Cancelar ❌")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    
    texto = (
        "🧹 <b>CENTRAL DE LIMPEZA DO SERVIDOR</b>\n\n"
        "Escolha qual fila você deseja esvaziar. As suas configurações do robô (textos, horários, alvos) <b>nunca</b> são apagadas.\n\n"
        "👉 <b>Fila Principal:</b> Apaga vídeos agendados no SQLite.\n"
        "👉 <b>Fila Espião:</b> Apaga clones retidos no radar.\n"
        "👉 <b>Fila Espelhador:</b> Apaga a repassagem de vídeos entre canais.\n"
        "👉 <b>Geral:</b> Faz a faxina absoluta em todas as opções acima."
    )
    await message.answer(texto, reply_markup=teclado_opcoes_limpeza, parse_mode="HTML")
    await state.set_state(ConfigFluxo.aguardando_confirmacao_zerar_filas)

@dp.message(ConfigFluxo.aguardando_confirmacao_zerar_filas)
async def processar_zerar_filas_tarefas(message: types.Message, state: FSMContext):
    opcoes_validas = [
        "Limpar Tudo (Geral) 💥", "Limpar Fila Principal 🛒", 
        "Limpar Fila do Espião 🕵️", "Limpar Fila Espelhador 🔄"
    ]

    if message.text == "Cancelar ❌":
        await cancelar_fluxo_global(message, state)
        return
        
    if message.text not in opcoes_validas:
        await message.answer("Por favor, utilize os botões abaixo para escolher a limpeza.")
        return
        
    msg_status = await message.answer(f"🧹 <b>Executando: {message.text}...</b> Isso pode levar alguns segundos. ⏳", reply_markup=teclado_cancelar, parse_mode="HTML")
    if EXIBIR_LOGS: logger.info(f"🚀 Iniciando protocolo de limpeza modular: {message.text}")
    
    # Flags de execução baseadas na escolha do usuário
    limpar_tudo = message.text == "Limpar Tudo (Geral) 💥"
    limpar_principal = message.text == "Limpar Fila Principal 🛒" or limpar_tudo
    limpar_espiao = message.text == "Limpar Fila do Espião 🕵️" or limpar_tudo
    limpar_espelhador = message.text == "Limpar Fila Espelhador 🔄" or limpar_tudo

    relatorio = {
        "db": 0,
        "espiao": 0,
        "espelhador": 0,
        "jobs": 0,
        "arquivos": 0,
        "espaco_mb": 0.0
    }

    def apagar_arquivo(caminho):
        if caminho and os.path.exists(caminho):
            try:
                tamanho = os.path.getsize(caminho) / (1024 * 1024) # Converte bytes para MB
                os.remove(caminho)
                relatorio["arquivos"] += 1
                relatorio["espaco_mb"] += tamanho
            except: pass

    # 1. Limpar Fila Principal (SQLite)
    if limpar_principal:
        try:
            conexao = sqlite3.connect("banco_dados.db")
            cursor = conexao.cursor()
            cursor.execute("SELECT caminho_video FROM fila_postagens WHERE status = 'PENDENTE'")
            for (caminho_video,) in cursor.fetchall():
                apagar_arquivo(caminho_video)
            
            cursor.execute("DELETE FROM fila_postagens WHERE status = 'PENDENTE'")
            relatorio["db"] = cursor.rowcount
            conexao.commit()
            conexao.close()
            
            # Removemos os jobs pendentes APENAS se estivermos a limpar a fila principal
            for job in scheduler.get_jobs():
                if job.id.startswith('job_fila_postagem_'):
                    job.remove()
                    relatorio["jobs"] += 1
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro ao limpar Fila Principal: {e}")
            
    # 2. Limpar Fila do Espião
    if limpar_espiao:
        try:
            fila_clonagem = ler_fila_clonagem()
            mantidos_espiao = []
            for item in fila_clonagem.get("fila", []):
                if item.get("processado"):
                    mantidos_espiao.append(item)
                else:
                    apagar_arquivo(item.get("caminho_video"))
                    relatorio["espiao"] += 1
            fila_clonagem["fila"] = mantidos_espiao
            salvar_fila_clonagem(fila_clonagem)
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro ao limpar Fila do Espião: {e}")
            
    # 3. Limpar Fila do Espelhador
    if limpar_espelhador:
        try:
            with open("fila_espelhador.json", "r", encoding="utf-8") as f:
                fila_espelhador = json.load(f)
            mantidos_espelhador = []
            for item in fila_espelhador.get("fila", []):
                if item.get("processado"):
                    mantidos_espelhador.append(item)
                else:
                    apagar_arquivo(item.get("caminho_video"))
                    relatorio["espelhador"] += 1
            fila_espelhador["fila"] = mantidos_espelhador
            with open("fila_espelhador.json", "w", encoding="utf-8") as f:
                json.dump(fila_espelhador, f, indent=4)
        except FileNotFoundError:
            pass
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro ao limpar Fila do Espelhador: {e}")

    # 4. Faxina Cega na Pasta Temp (Sempre roda para matar arquivos soltos)
    try:
        if os.path.exists("temp"):
            for filename in os.listdir("temp"):
                caminho_completo = os.path.join("temp", filename)
                if os.path.isfile(caminho_completo):
                    apagar_arquivo(caminho_completo)
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao esvaziar pasta temp: {e}")

    await msg_status.delete()
    
    texto_final = (
        "✨ <b>Operação Concluída!</b>\n\n"
        "Relatório de eliminação:\n"
        f"🗑️ <b>{relatorio['db']}</b> registros do Banco Principal\n"
        f"🗑️ <b>{relatorio['espiao']}</b> clones do Espião\n"
        f"🗑️ <b>{relatorio['espelhador']}</b> itens do Espelhador\n"
        f"⏱️ <b>{relatorio['jobs']}</b> agendamentos cancelados\n"
        f"🧹 <b>{relatorio['arquivos']}</b> ficheiros físicos apagados\n"
        f"💾 <b>{relatorio['espaco_mb']:.2f} MB</b> liberados no servidor!\n\n"
        "O seu ambiente de trabalho está atualizado."
    )
    
    if EXIBIR_LOGS: logger.info(f"✅ Faxina concluída ({message.text}). {relatorio['espaco_mb']:.2f} MB liberados.")
    await message.answer(texto_final, parse_mode="HTML", reply_markup=obter_teclado_opcoes_servidor())
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

@dp.message(F.text == "Gerador de Achadinhos 🛍️", StateFilter("*"))
async def painel_achadinhos(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    
    config = ler_achadinhos_config()
    nichos = config.get("nichos", [])
    
    texto = "🛍️ <b>Painel do Gerador de Achadinhos</b>\n\n"
    texto += f"O motor autônomo está configurado para inspecionar <b>{len(nichos)} nicho(s) de mercado</b> em ciclo.\n"
    
    if not nichos:
        texto += "\n<i>Nenhum nicho configurado. Clique em 'Adicionar Nicho ➕' para começar.</i>"
    else:
        for i, nicho in enumerate(nichos, 1):
            texto += f"\n🎯 <b>{i}. {nicho.get('nome')}</b>\n"
            texto += f"   └ Canal Alvo: <code>{nicho.get('destino')}</code>\n"
            texto += f"   └ Termos Rastreados: {', '.join(nicho.get('keywords', []))}\n"
            
    await message.answer(texto, parse_mode="HTML", reply_markup=teclado_menu_achadinhos)
    await state.set_state(AchadinhosFluxo.menu_principal)

@dp.message(F.text == "Forçar Garimpo 🚀", StateFilter("*"))
async def forcar_garimpo_achadinhos(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🚀 <b>Motor Acionado!</b> O garimpo extrairá as melhores ofertas nos nichos mapeados de forma silenciosa no servidor. Em instantes elas cairão nos canais.", parse_mode="HTML")
    asyncio.create_task(processar_garimpo_automatico())

# --- FLUXO: ADICIONAR NICHO ---
@dp.message(AchadinhosFluxo.menu_principal, F.text == "Adicionar Nicho ➕")
async def pedir_nome_nicho(message: types.Message, state: FSMContext):
    await message.answer("Vamos configurar um novo robô de garimpo!\n\nQual será o <b>Nome deste nicho</b>? (Ex: Achadinhos Tech, Moda Feminina)", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AchadinhosFluxo.aguardando_nome)

@dp.message(AchadinhosFluxo.aguardando_nome)
async def pedir_destino_nicho(message: types.Message, state: FSMContext):
    nome_nicho = message.text.strip()
    await state.update_data(novo_nome_nicho=nome_nicho)
    if EXIBIR_LOGS: logger.info(f"🛍️ Criando novo nicho: {nome_nicho}")
    await message.answer(f"Nome salvo: <b>{nome_nicho}</b>\n\nAgora, envie o <b>ID Numérico</b> do canal no Telegram onde o robô irá postar estas ofertas (Ex: -100123456789):", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AchadinhosFluxo.aguardando_destino)

@dp.message(AchadinhosFluxo.aguardando_destino)
async def pedir_thread_nicho(message: types.Message, state: FSMContext):
    destino_nicho = message.text.strip()
    await state.update_data(novo_destino_nicho=destino_nicho)
    await message.answer(f"Grupo salvo: <code>{destino_nicho}</code>\n\nAgora, informe o <b>ID do Tópico (Thread)</b> específico para este nicho.\n<i>(Se não houver tópicos ou for um canal normal, digite apenas <b>0</b>)</i>:", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AchadinhosFluxo.aguardando_thread_id)

@dp.message(AchadinhosFluxo.aguardando_thread_id)
async def pedir_keywords_nicho(message: types.Message, state: FSMContext):
    thread_id = message.text.strip()
    await state.update_data(novo_thread_id=thread_id)
    await message.answer(f"Tópico salvo: <code>{thread_id}</code>\n\nPor fim, digite as <b>Palavras-chave</b> que o motor usará para rastrear produtos na Shopee. Separe-as por vírgula.\nExemplo: <code>smartwatch, fone bluetooth, gamer</code>", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AchadinhosFluxo.aguardando_keywords)

@dp.message(AchadinhosFluxo.aguardando_keywords)
async def salvar_novo_nicho(message: types.Message, state: FSMContext):
    keywords_raw = message.text.strip()
    keywords_lista = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    
    if not keywords_lista:
        await message.answer("Nenhuma palavra-chave detectada. Tente novamente separando por vírgulas:", reply_markup=teclado_cancelar)
        return

    data = await state.get_data()
    nome = data.get("novo_nome_nicho")
    destino = data.get("novo_destino_nicho")
    thread_id = data.get("novo_thread_id", "0")
    
    config = ler_achadinhos_config()
    novo_nicho = {
        "nome": nome,
        "destino": destino,
        "thread_id": thread_id,
        "keywords": keywords_lista
    }
    
    config.setdefault("nichos", []).append(novo_nicho)
    salvar_achadinhos_config(config)
        
    if EXIBIR_LOGS: logger.info(f"✅ Nicho '{nome}' adicionado com sucesso e ativo no radar!")
    await message.answer(f"✅ Nicho <b>{nome}</b> criado e ativado com sucesso!", parse_mode="HTML")
    await painel_achadinhos(message, state)

# --- FLUXO: REMOVER NICHO ---
@dp.message(AchadinhosFluxo.menu_principal, F.text == "Remover Nicho 🗑️")
async def pedir_remocao_nicho(message: types.Message, state: FSMContext):
    config = ler_achadinhos_config()
    nichos = config.get("nichos", [])
    
    if not nichos:
        await message.answer("Não há nichos configurados para remover.")
        return
        
    texto = "Qual nicho deseja excluir? Digite o <b>NÚMERO</b> correspondente:\n\n"
    for i, nicho in enumerate(nichos, 1):
        texto += f"<b>{i}.</b> {nicho.get('nome')} (Canal: {nicho.get('destino')})\n"
        
    await message.answer(texto, parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AchadinhosFluxo.aguardando_remocao)

@dp.message(AchadinhosFluxo.aguardando_remocao)
async def confirmar_remocao_nicho(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas o número do nicho.")
        return
        
    indice = int(message.text) - 1
    config = ler_achadinhos_config()
    nichos = config.get("nichos", [])
    
    if 0 <= indice < len(nichos):
        nicho_selecionado = nichos[indice]
        await state.update_data(indice_nicho_remocao=indice)
        
        teclado_confirmacao = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Confirmar Exclusão ✅"), KeyboardButton(text="Cancelar ❌")]], resize_keyboard=True, is_persistent=True)
        await message.answer(f"Tem certeza que deseja apagar permanentemente o nicho <b>{nicho_selecionado.get('nome')}</b> do motor?", parse_mode="HTML", reply_markup=teclado_confirmacao)
        await state.set_state(AchadinhosFluxo.aguardando_confirmacao_remocao)
    else:
        await message.answer("Número inválido. Tente novamente:")

@dp.message(AchadinhosFluxo.aguardando_confirmacao_remocao)
async def processar_remocao_nicho(message: types.Message, state: FSMContext):
    if message.text != "Confirmar Exclusão ✅":
        await message.answer("Use os botões para confirmar ou cancelar.")
        return
        
    data = await state.get_data()
    indice = data.get("indice_nicho_remocao")
    
    config = ler_achadinhos_config()
    if indice is not None and 0 <= indice < len(config.get("nichos", [])):
        removido = config["nichos"].pop(indice)
        salvar_achadinhos_config(config)
        if EXIBIR_LOGS: logger.info(f"🗑️ Nicho '{removido.get('nome')}' excluído.")
        await message.answer(f"✅ Nicho '{removido.get('nome')}' removido com sucesso!")
    
    await painel_achadinhos(message, state)

# --- FLUXO: EDITAR NICHO ---
@dp.message(AchadinhosFluxo.menu_principal, F.text == "Editar Nicho ✏️")
async def pedir_edicao_nicho(message: types.Message, state: FSMContext):
    config = ler_achadinhos_config()
    nichos = config.get("nichos", [])
    
    if not nichos:
        await message.answer("Não há nichos configurados para editar.")
        return
        
    texto = "Qual nicho deseja editar? Digite o <b>NÚMERO</b> correspondente:\n\n"
    for i, nicho in enumerate(nichos, 1):
        texto += f"<b>{i}.</b> {nicho.get('nome')}\n"
        
    await message.answer(texto, parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AchadinhosFluxo.aguardando_selecao_edicao)

@dp.message(AchadinhosFluxo.aguardando_selecao_edicao)
async def selecionar_campo_edicao(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas o número.")
        return
        
    indice = int(message.text) - 1
    config = ler_achadinhos_config()
    nichos = config.get("nichos", [])
    
    if 0 <= indice < len(nichos):
        nicho = nichos[indice]
        await state.update_data(indice_nicho_edicao=indice)
        
        texto = f"🎯 Editando: <b>{nicho.get('nome')}</b>\nO que você deseja alterar?"
        await message.answer(texto, parse_mode="HTML", reply_markup=teclado_edicao_nicho)
        await state.set_state(AchadinhosFluxo.aguardando_campo_edicao)
    else:
        await message.answer("Número inválido. Tente novamente:")

@dp.message(AchadinhosFluxo.aguardando_campo_edicao)
async def pedir_novo_valor_edicao(message: types.Message, state: FSMContext):
    opcoes = {
        "Editar Nome 📝": ("nome", "Digite o novo <b>Nome</b> para este nicho:"),
        "Editar Destino 🎯": ("destino", "Digite o novo <b>ID do Canal/Grupo</b> de destino:"),
        "Editar Tópico 💬": ("thread_id", "Digite o novo <b>ID do Tópico (Thread)</b> (ou 0 para geral):"),
        "Editar Palavras-chave 🔑": ("keywords", "Digite a nova lista de <b>Palavras-chave</b> separadas por vírgula:")
    }
    
    selecao = opcoes.get(message.text)
    if not selecao:
        await message.answer("Use os botões abaixo para escolher o que editar.")
        return
        
    campo, pergunta = selecao
    await state.update_data(campo_edicao=campo)
    await message.answer(pergunta, parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AchadinhosFluxo.aguardando_novo_valor_edicao)

@dp.message(AchadinhosFluxo.aguardando_novo_valor_edicao)
async def salvar_edicao_nicho(message: types.Message, state: FSMContext):
    data = await state.get_data()
    indice = data.get("indice_nicho_edicao")
    campo = data.get("campo_edicao")
    novo_valor = message.text.strip()
    
    config = ler_achadinhos_config()
    nichos = config.get("nichos", [])
    
    if 0 <= indice < len(nichos):
        if campo == "keywords":
            novo_valor = [k.strip() for k in novo_valor.split(",") if k.strip()]
            
        nichos[indice][campo] = novo_valor
        salvar_achadinhos_config(config)
            
        if EXIBIR_LOGS: logger.info(f"✏️ Nicho {indice+1} atualizado. Campo '{campo}' alterado.")
        await message.answer("✅ Nicho atualizado com sucesso!")
    
    await painel_achadinhos(message, state)

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

    # ✅ NOVO: Resgate das configurações de tempo e distribuição do Espião
    inicio_e = dados_espiao.get("inicio", 10)
    fim_e = dados_espiao.get("fim", 22)
    modo_e = dados_espiao.get("modo", "aleatorio").title()
    intervalo_e = dados_espiao.get("intervalo_dias", 1)
    
    # 3. Construir a mensagem unificada do painel
    texto = "🕵️ <b>Painel Principal do Espião</b>\n\n"
    texto += f"📦 <b>Fila de clonagem:</b> {videos_pendentes} vídeos aguardando.\n"
    texto += f"📡 <b>Radar operacional:</b> {qtd_concorrentes} concorrentes vigiados.\n"
    texto += f"🎯 <b>Canal de destino:</b> <code>{canal_destino}</code>\n"
    texto += f"🕒 <b>Janela de Postagem:</b> {inicio_e}h às {fim_e}h\n"
    texto += f"📅 <b>Atraso (Defasagem):</b> D+{intervalo_e} (Modo: {modo_e})\n\n"
    texto += "Escolha uma opção para gerenciar:"
    
    if EXIBIR_LOGS: logger.info("✅ Sucesso: Painel unificado do Espião renderizado com logs operacionais.")
    await message.answer(texto, reply_markup=teclado_menu_espiao, parse_mode="HTML")

@dp.message(F.text == "Forçar Clones 🚀", StateFilter("*"))
async def iniciar_esvaziar_clones(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    fila_data = ler_fila_clonagem()
    fila = fila_data.get("fila", [])
    qtd_pendentes = len([i for i in fila if not i.get("processado")])
    
    if qtd_pendentes == 0:
        await message.answer("A fila de clonagem já está vazia no momento.", reply_markup=teclado_menu_espiao)
        return
        
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    
    await message.answer(f"🚀 Tem certeza que deseja forçar o processamento de <b>{qtd_pendentes} vídeos</b> da fila do Espião imediatamente?", reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(EspiaoFluxo.aguardando_confirmacao_forcar_clones)

@dp.message(EspiaoFluxo.aguardando_confirmacao_forcar_clones)
async def processar_esvaziar_clones(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Operação cancelada.", reply_markup=teclado_menu_espiao)
        await menu_espiao_principal(message, state)
        return

    if EXIBIR_LOGS: logger.info("🚀 Iniciando processo de forçar clones para o Espião...")
    
    await message.answer("✅ <b>Clonagens Forçadas!</b>\nOs vídeos pendentes na fila do Espião serão analisados pela IA e postados em instantes. Você receberá um aviso quando o processo terminar.", parse_mode="HTML", reply_markup=teclado_menu_espiao)
    await state.clear()
    
    # Chama o processo de forma assíncrona para não travar a interface do Telegram
    asyncio.create_task(esvaziar_fila_espiao_background(message.chat.id))

async def esvaziar_fila_espiao_background(chat_id):
    if EXIBIR_LOGS: logger.info("🚀 [Espião] Iniciando rajada forçada em background...")
    while True:
        try:
            dados = ler_fila_clonagem()
            pendentes = [i for i in dados.get("fila", []) if not i.get("processado")]
            if not pendentes:
                if EXIBIR_LOGS: logger.info("✅ [Espião] Fila de clonagem esvaziada com sucesso!")
                await bot.send_message(chat_id, "✅ <b>Concluído!</b>\nTodos os vídeos retidos na fila do Espião foram analisados pela IA e publicados com sucesso no seu canal.", parse_mode="HTML")
                break
            
            dados["proximo_processamento"] = "2000-01-01 00:00:00"
            agora = datetime.now(fuso_horario)
            ontem_str = (agora - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            for item in dados.get("fila", []):
                if not item.get("processado"):
                    item["data_captura"] = ontem_str
                    
            salvar_fila_clonagem(dados)
            
            # ✅ O PARÂMETRO 'forcar=True' ORDENA AO BOT IGNORAR A JANELA DE TEMPO
            await processar_fila_espiao(forcar=True)
            await asyncio.sleep(5) 
            
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro durante esvaziamento forçado: {e}")
            await bot.send_message(chat_id, "⚠️ Ocorreu um erro durante o processamento em background. A rajada pode ter sido interrompida.")
            break

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
    status_destino = dados.get("status_destino", {})
    
    texto = f"📡 <b>Gestão de Grupos Vigiados</b>\n\n"
    
    if destino != "Não definido":
        nome_dest = status_destino.get("nome", str(destino))
        icone_dest = "❌" if status_destino.get("status") == "erro" else "✅" if status_destino.get("status") == "ok" else "⏳"
        display_destino = f"{icone_dest} {nome_dest} (<code>{destino}</code>)" if nome_dest != str(destino) else f"{icone_dest} <code>{destino}</code>"
    else:
        display_destino = "<i>Não definido</i>"
        
    texto += f"🎯 <b>Canal de Destino:</b> {display_destino}\n\n"
    texto += "<b>Na Escuta:</b>\n"
    
    if alvos:
        cache_nomes_vigiados = ler_cache_nomes_grupos()  # 🚀 Fallback para grupos ainda não auditados pelo Userbot
        for i, alvo in enumerate(alvos, 1):
            info = status_alvos.get(alvo, {})
            status_ico = "⏳" # Status pendente enquanto o Userbot não verifica
            nome_cache = cache_nomes_vigiados.get(str(alvo))
            detalhe = f"{nome_cache} <code>({alvo})</code>" if nome_cache else alvo
            
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

@dp.message(F.text == "Editar Agendamento 🕒", StateFilter("*"))
async def iniciar_config_tempo_espiao(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    if EXIBIR_LOGS: logger.info("🚀 Iniciando configuração da janela de horário do Espião.")
    
    dados = ler_alvos_espiao()
    inicio = dados.get("inicio", 10)
    fim = dados.get("fim", 22)
    
    await message.answer(
        f"Defina a <b>Janela de Horário</b> útil em que o Espião pode postar os vídeos D+1 no canal.\n\n"
        f"Envie no formato <code>Inicio-Fim</code> (Exemplo: <code>10-22</code>):\n"
        f"<i>Janela atual: {inicio}h às {fim}h</i>", 
        reply_markup=teclado_cancelar, 
        parse_mode="HTML"
    )
    await state.set_state(ConfigRotinaEspiao.aguardando_janela)

@dp.message(ConfigRotinaEspiao.aguardando_janela)
async def receber_janela_espiao(message: types.Message, state: FSMContext):
    match = re.match(r"^(\d{1,2})-(\d{1,2})$", message.text.strip())
    if not match:
        await message.answer("Formato inválido! Use o formato exato como no exemplo: 10-22", reply_markup=teclado_cancelar)
        return
        
    inicio, fim = map(int, match.groups())
    if inicio >= fim or inicio < 0 or fim > 23:
        await message.answer("Valores inválidos! A hora de início deve ser menor que a do fim.", reply_markup=teclado_cancelar)
        return

    await state.update_data(espiao_inicio=inicio, fmt_espiao_fim=fim)
    
    teclado_dias = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Mesmo Dia (D+0) 🟢")],
            [KeyboardButton(text="Dia Seguinte (D+1) 🟡")],
            [KeyboardButton(text="Dois Dias (D+2) 🔵")],
            [KeyboardButton(text="Cancelar ❌")]
        ], resize_keyboard=True, is_persistent=True
    )
    await message.answer("Excelente! Agora escolha a defasagem temporal das postagens extraídas do Espião:", reply_markup=teclado_dias)
    await state.set_state(ConfigRotinaEspiao.aguardando_intervalo_espiao)

@dp.message(ConfigRotinaEspiao.aguardando_intervalo_espiao)
async def receber_intervalo_espiao(message: types.Message, state: FSMContext):
    mapa_dias = {"Mesmo Dia (D+0) 🟢": 0, "Dia Seguinte (D+1) 🟡": 1, "Dois Dias (D+2) 🔵": 2}
    
    if message.text not in mapa_dias:
        await message.answer("Por favor, use os botões na tela para escolher o intervalo.", reply_markup=teclado_cancelar)
        return
        
    intervalo = mapa_dias[message.text]
    await state.update_data(intervalo_dias_espiao=intervalo)
    
    teclado_modo = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Aleatório 🔀"), KeyboardButton(text="Ordem de Chegada ⬇️")],
            [KeyboardButton(text="Cancelar ❌")]
        ], resize_keyboard=True, is_persistent=True
    )
    await message.answer("Como deseja distribuir os clones retidos dentro da janela estipulada?", reply_markup=teclado_modo)
    await state.set_state(ConfigRotinaEspiao.aguardando_modo)

@dp.message(ConfigRotinaEspiao.aguardando_modo)
async def salvar_config_tempo_espiao(message: types.Message, state: FSMContext):
    if message.text not in ["Aleatório 🔀", "Ordem de Chegada ⬇️"]:
        await message.answer("Por favor, use os botões de seleção para definir o modo.", reply_markup=teclado_cancelar)
        return
        
    modo = "aleatorio" if message.text == "Aleatório 🔀" else "ordem"
    data = await state.get_data()
    inicio = data.get("espiao_inicio")
    fim = data.get("fmt_espiao_fim")
    intervalo = data.get("intervalo_dias_espiao", 1)
    
    dados = ler_alvos_espiao()
    dados["inicio"] = inicio
    dados["fim"] = fim
    dados["intervalo_dias"] = intervalo
    dados["modo"] = modo
    salvar_alvos_espiao(dados)
    
    if EXIBIR_LOGS: logger.info(f"✅ Configuração do Espião salva: Janela {inicio}h-{fim}h | D+{intervalo} | Modo: {modo}")
    await message.answer(f"✅ <b>Configurações do Espião Salvas!</b>\nJanela: {inicio}h às {fim}h\nAtraso: D+{intervalo}\nDistribuição: {message.text}", parse_mode="HTML")
    await state.clear()
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
    padrao = {"alvos": [], "frequencia_por_hora": 0, "pausado": False, "forcar_disparo": False, "repeticoes_internas": 6, "replicas_mensagem": 5}
    dados = ler_config_bd("alvos_divulgacao", padrao, arquivo_legado="alvos_divulgacao.json")
    
    houve_alteracao = False
    if "repeticoes_internas" not in dados: 
        dados["repeticoes_internas"] = 6
        houve_alteracao = True
    if "replicas_mensagem" not in dados: 
        dados["replicas_mensagem"] = 5
        houve_alteracao = True
        
    if houve_alteracao:
        salvar_config_bd("alvos_divulgacao", dados)
        
    return dados

def salvar_alvos_divulgacao(dados):
    salvar_config_bd("alvos_divulgacao", dados)

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
    padrao = {"alvos": [], "frequencia_por_hora": 0, "pausado": False, "forcar_disparo": False, "repeticoes_internas": 6, "replicas_mensagem": 5}
    dados = ler_config_bd("alvos_divulgacao_viral", padrao, arquivo_legado="alvos_divulgacao_viral.json")
    
    houve_alteracao = False
    if "repeticoes_internas" not in dados: 
        dados["repeticoes_internas"] = 6
        houve_alteracao = True
    if "replicas_mensagem" not in dados: 
        dados["replicas_mensagem"] = 5
        houve_alteracao = True
        
    if houve_alteracao:
        salvar_config_bd("alvos_divulgacao_viral", dados)
        
    return dados

def salvar_alvos_divulgacao_viral(dados):
    salvar_config_bd("alvos_divulgacao_viral", dados)

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
            
            if EXIBIR_LOGS: logger.info(f"⚙️ Tratando segurança de string para a legenda do item {i}...")
            legenda_segura = str(legenda) if legenda is not None else ""
            
            if is_postado:
                horario_envio = item.get("horario_postagem", "Horário indisponível")
                if "[ERRO: VÍDEO PERDIDO]" in legenda_segura:
                    status_previsao_final = f"❌ <b>FALHA: Vídeo perdido às {horario_envio}</b>"
                else:
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

async def aplicar_renumeracao_e_salvar(fila_ids_ordenada, message, state, numero_base=None):
    import re
    if EXIBIR_LOGS: logger.info("🔄 Reorganizando prioridades e numeração no SQLite...")
    
    try:
        conexao = sqlite3.connect("banco_dados.db")
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()

        if numero_base is not None:
            menor_numero = numero_base
        else:
            menor_numero = float('inf')
            for id_item in fila_ids_ordenada:
                cursor.execute("SELECT legenda FROM fila_postagens WHERE id_unico = ?", (id_item,))
                resultado = cursor.fetchone()
                if resultado:
                    match = re.search(r'(?i)Vídeo\s+(\d+)', resultado["legenda"])
                    if match:
                        num = int(match.group(1))
                        if num < menor_numero:
                            menor_numero = num
            if menor_numero == float('inf'):
                async with _lock_contador:
                    menor_numero = ler_contador()

        numero_atual_cascata = menor_numero

        for i, id_item in enumerate(fila_ids_ordenada):
            cursor.execute("SELECT legenda FROM fila_postagens WHERE id_unico = ?", (id_item,))
            resultado = cursor.fetchone()
            if resultado:
                legenda_antiga = resultado["legenda"]
                nova_legenda = re.sub(r'(?i)(Vídeo\s+)\d+', rf'\g<1>{numero_atual_cascata}', legenda_antiga, count=1)
                nova_prioridade = i + 1

                cursor.execute("UPDATE fila_postagens SET legenda = ?, prioridade = ? WHERE id_unico = ?", (nova_legenda, nova_prioridade, id_item))
                numero_atual_cascata += 1

        conexao.commit()
        conexao.close()

        async with _lock_contador:
            contador_real = ler_contador()
            if numero_atual_cascata > contador_real:
                salvar_contador(numero_atual_cascata)
                if EXIBIR_LOGS: logger.info(f"✅ Auto-correção do banco concluída. Novo contador global: {numero_atual_cascata}.")

        await message.answer("✅ Operação concluída com sucesso!\n🔄 A fila foi sincronizada de forma segura no Banco de Dados.")
        await menu_gerenciar_fila(message, state)
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao organizar SQLite: {e}")
        await message.answer(f"❌ Erro interno ao salvar no banco: {e}")

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
        
        menor_numero_antes = float('inf')
        for f_item in fila:
            match = re.search(r'(?i)Vídeo\s+(\d+)', f_item.get("legenda", ""))
            if match:
                num = int(match.group(1))
                if num < menor_numero_antes:
                    menor_numero_antes = num
        if menor_numero_antes == float('inf'): menor_numero_antes = None

        item_removido = fila.pop(posicao)
        id_remover = item_removido.get("id")
        caminho_video = item_removido.get("caminho_video")
        
        try:
            conexao = sqlite3.connect("banco_dados.db")
            cursor = conexao.cursor()
            cursor.execute("DELETE FROM fila_postagens WHERE id_unico = ?", (id_remover,))
            conexao.commit()
            conexao.close()
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro ao apagar do banco: {e}")

        if caminho_video and os.path.exists(caminho_video):
            ainda_usado = any(x.get("caminho_video") == caminho_video for x in fila)
            if not ainda_usado:
                try: os.remove(caminho_video)
                except: pass
                
        if EXIBIR_LOGS: logger.info(f"🗑️ Vídeo {id_remover} apagado do banco.")
        
        fila_ids = [item["id"] for item in fila]
        await aplicar_renumeracao_e_salvar(fila_ids, message, state, numero_base=menor_numero_antes)
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
        id_item = fila[posicao]["id"]
        try:
            conexao = sqlite3.connect("banco_dados.db")
            cursor = conexao.cursor()
            cursor.execute("UPDATE fila_postagens SET legenda = ? WHERE id_unico = ?", (nova_legenda, id_item))
            conexao.commit()
            conexao.close()
            if EXIBIR_LOGS: logger.info(f"✏️ Fila: Legenda do vídeo {id_item} atualizada no SQLite.")
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro ao editar legenda: {e}")
            
        await message.answer("✅ Legenda atualizada com sucesso direto no banco de dados!")
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
        
        id_movido = item_movido.get("id")
        try:
            conexao = sqlite3.connect("banco_dados.db")
            cursor = conexao.cursor()
            cursor.execute("UPDATE fila_postagens SET data_alvo = ? WHERE id_unico = ?", (nova_data_adicao, id_movido))
            conexao.commit()
            conexao.close()
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro ao mudar data_alvo no DB: {e}")
            
        fila_simulada.insert(nova_posicao, item_movido)
        
        if EXIBIR_LOGS: logger.info(f"↕️ Fila: Confirmação recebida. Vídeo reordenado via SQLite.")
        
        fila_ids = [item["id"] for item in fila_simulada]
        await aplicar_renumeracao_e_salvar(fila_ids, message, state)
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
        if EXIBIR_LOGS: logger.info(f"🔄 Iniciando renumeração via SQLite a partir da posição {posicao+1}...")
        
        # Pega a lista de IDs a partir da posição selecionada
        fila_ids_alvo = [item["id"] for item in fila[posicao:]]
        await aplicar_renumeracao_e_salvar(fila_ids_alvo, message, state, numero_base=novo_numero_inicial)
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

# 🚀 CORREÇÃO: Vinculação do handler ao estado correto da FSM para processar o clique
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
            # 2. Disparo imediato para o Telegram
            if caminho_video and os.path.exists(caminho_video):
                # ✅ SEGUNDA TRAVA DE SEGURANÇA: Inspeção da extensão física
                if caminho_video.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                    if EXIBIR_LOGS: logger.warning("🚫 [Segurança] Disparo imediato abortado! O ficheiro é uma imagem.")
                    raise Exception("O ficheiro físico validado é uma imagem e não um vídeo.")
                    
                arquivo = FSInputFile(caminho_video)
                msg = await bot.send_video(chat_id=GRUPO_ID, video=arquivo, caption=legenda_disparo, parse_mode="HTML")
                novo_file_id = msg.video.file_id
                sucesso_upload = True
                try: os.remove(caminho_video)
                except: pass
            elif video_id:
                await bot.send_video(chat_id=GRUPO_ID, video=video_id, caption=legenda_disparo, parse_mode="HTML")
                sucesso_upload = True
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Falha no disparo imediato: {e}")
            if caminho_video and os.path.exists(caminho_video):
                try: os.rename(caminho_video, caminho_video + ".pendente")
                except: pass
            await msg_status.delete()
            await message.answer(f"Ocorreu um erro técnico ao publicar o vídeo: {e}")
            await menu_gerenciar_fila(message, state)
            return
            
        await msg_status.delete()
            
        if sucesso_upload:
            if EXIBIR_LOGS: logger.info("✅ Vídeo manual submetido. Atualizando SQLite...")
            
            agora_manual = datetime.now(fuso_horario)
            id_unico = item["id"]
            
            try:
                conexao = sqlite3.connect("banco_dados.db")
                cursor = conexao.cursor()
                cursor.execute("UPDATE fila_postagens SET status = 'CONCLUIDO', data_postagem = ?, horario_postagem = ? WHERE id_unico = ?", 
                               (agora_manual.strftime("%Y-%m-%d"), agora_manual.strftime("%H:%M"), id_unico))
                               
                if novo_file_id:
                    cursor.execute("UPDATE fila_postagens SET video_id = ?, caminho_video = NULL WHERE caminho_video = ? AND id_unico != ?", 
                                   (novo_file_id, caminho_video, id_unico))
                conexao.commit()
                conexao.close()
            except Exception as e:
                if EXIBIR_LOGS: logger.error(f"❌ Erro ao atualizar status manual no DB: {e}")
            
            if caminho_video and os.path.exists(caminho_video):
                ainda_usado = any(x.get("caminho_video") == caminho_video and not x.get("postado", False) for x in fila)
                if not ainda_usado:
                    try: os.remove(caminho_video)
                    except: pass
            
            await message.answer("🚀 Publicação realizada com sucesso!\n✅ O vídeo foi marcado como concluído direto no banco de dados.")
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

# A função converter_link_shopee foi deletada daqui.

async def processar_fila_espiao(forcar=False):
    dados_espiao = ler_alvos_espiao()
    canal_destino = dados_espiao.get("canal_destino")
    
    if not canal_destino:
        return 
        
    fila_data = ler_fila_clonagem()
    intervalo_dias = dados_espiao.get("intervalo_dias", 1)
    
    # ✅ RESGATE DA JANELA DE HORÁRIO
    inicio_janela = dados_espiao.get("inicio", 10)
    fim_janela = dados_espiao.get("fim", 22)
    
    agora = datetime.now(fuso_horario)
    hoje_str = agora.strftime("%Y-%m-%d")

    # 🛑 TRAVA DE EXPEDIENTE: Se não for um disparo forçado e estiver fora da hora, o bot dorme
    if not forcar and (agora.hour < inicio_janela or agora.hour >= fim_janela):
        return
        
    proximo_proc_str = fila_data.get("proximo_processamento")
    if proximo_proc_str:
        try:
            proximo_proc = datetime.strptime(proximo_proc_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario)
            if agora < proximo_proc:
                return
        except ValueError:
            pass
            
    fila = fila_data.get("fila", [])
    
    itens_elegiveis = []
    for item in fila:
        if not item.get("processado"):
            data_cap_str = item.get("data_captura", "")
            if data_cap_str:
                try:
                    data_captura_obj = datetime.strptime(data_cap_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario)
                    data_alvo_obj = data_captura_obj + timedelta(days=intervalo_dias)
                    dia_alvo = data_alvo_obj.strftime("%Y-%m-%d")
                    if dia_alvo <= hoje_str:
                        itens_elegiveis.append(item)
                except ValueError:
                    dia_cap = data_cap_str.split(" ")[0]
                    data_cap_obj = datetime.strptime(dia_cap, "%Y-%m-%d").replace(tzinfo=fuso_horario)
                    data_alvo_obj = data_cap_obj + timedelta(days=intervalo_dias)
                    dia_alvo = data_alvo_obj.strftime("%Y-%m-%d")
                    if dia_alvo <= hoje_str:
                        itens_elegiveis.append(item)

    if not itens_elegiveis:
        return

    item_pendente = random.choice(itens_elegiveis)
    if EXIBIR_LOGS: logger.info(f"🪞 [Espião] Sorteio aleatório ativo. Vídeo selecionado: {item_pendente['id']}")

    caminho_video = item_pendente["caminho_video"]
    link_original = item_pendente["link_original"]
    item_id = item_pendente["id"]
    
    data_captura_str = item_pendente.get("data_captura")
    if data_captura_str:
        try:
            data_captura = datetime.strptime(data_captura_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario)
            horas_na_fila = (agora - data_captura).total_seconds() / 3600
            limite_horas = (intervalo_dias * 24) + 24 
            if horas_na_fila > limite_horas:
                if EXIBIR_LOGS: logger.warning(f"⏳ Clone {item_id} expirou ({horas_na_fila:.1f}h). Descartando.")
                fila_data["fila"] = [item for item in fila if item["id"] != item_id]
                salvar_fila_clonagem(fila_data)
                try:
                    if os.path.exists(caminho_video): os.remove(caminho_video)
                except: pass
                return
        except ValueError:
            pass

    rotinas_virais = ["job_rotina_promo_principal", "job_rotina_link_grupo_viral", "job_rotina_divulgar_gem_viral"]
    conflito_silencio = False
    for job in scheduler.get_jobs():
        if any(rv in job.id for rv in rotinas_virais) and getattr(job, 'next_run_time', None):
            tempo_rotina = job.next_run_time.astimezone(fuso_horario)
            if abs((agora - tempo_rotina).total_seconds() / 60) <= 15:
                conflito_silencio = True
                break
                
    if conflito_silencio:
        if EXIBIR_LOGS: logger.info(f"🤫 [Espião] Trava de Silêncio ativa. Adormecendo clone {item_id}...")
        return
            
    if not os.path.exists(caminho_video):
        item_pendente["processado"] = True
        salvar_fila_clonagem(fila_data)
        return
        
    if EXIBIR_LOGS: logger.info(f"🕵️ Processando clone: {item_id}")
    
    link_final = await converter_link_shopee(link_original)
    
    try:
        prompt_espiao = (
            "Assista ao vídeo e identifique qual é o produto demonstrado. "
            "Sua resposta deve conter EXATAMENTE duas linhas.\n"
            "Na primeira linha, escreva APENAS o nome do produto acompanhado de um emoji correspondente no final (Exemplo: Tênis Casual Feminino 👟).\n"
            "Na segunda linha, inclua as hashtags correspondentes aos setores do produto. IMPORTANTE: Se utilizar mais de uma hashtag, separe-as APENAS com espaços em branco, NUNCA utilize vírgulas.\n"
            "REGRA DE CONTEXTO: Categorize o produto baseando-se estritamente na sua utilidade prática e ambiente de uso. É terminantemente proibido utilizar atalhos semânticos ou associações literais de palavras.\n"
            "REGRA ABSOLUTA: Você só pode escolher as hashtags desta lista exata, podendo combinar mais de uma se aplicável: "
            "#RoupasFemininas, #SapatosFemininos, #CelularesEDispositivos, #AcessoriosParaVeiculos, #Relogios, "
            "#AlimentosEBebidas, #CasaEDecoracao, #SapatosMasculinos, #EsportesELazer, #BolsasMasculinas, #BolsasFemininas, "
            "#RoupasPlusSize, #ModaInfantil, #Eletrodomesticos, #Motocicletas, #AnimaisDomesticos, #CamerasEDrones, #Beleza, "
            "#AcessoriosDeModa, #BrinquedosEHobbies, #Papelaria, #LivrosERevistas, #RoupasMasculinas, #Automoveis, #MaeEBebe, "
            "#ComputadoresEAcessorios, #Saude, #ViagensEBagagens, #JogosEConsoles, #Audio.\n"
            "É estritamente proibido criar textos de vendas, descrições, inventar novas hashtags, usar gatilhos mentais ou adicionar frases de encerramento."
        )
        texto_ia = await analisar_video_gemini(caminho_video, prompt_espiao, EXIBIR_LOGS)
        if not texto_ia:
            raise Exception("O módulo central da IA não retornou dados válidos.")
    except Exception as e:
        registrar_erro_json(f"processar_fila_espiao IA: {e}", origem="espiao.py")
        texto_ia = "Vídeo do Produto 🛍️\n#Oferta"
        
    linhas_ia = texto_ia.split('\n')
    nome_produto = linhas_ia[0].strip()
    hashtags = '\n'.join(linhas_ia[1:]).strip() if len(linhas_ia) > 1 else ""
    
    legenda_postagem = f"<b>{nome_produto}</b>\n\n🔗 <b>Link do Produto:</b>\n{link_final}"
    if hashtags:
        legenda_postagem += f"\n\n<i>{hashtags}</i>"
    
    try:
        if EXIBIR_LOGS: logger.info("🚀 Iniciando disparo do vídeo para o canal destino...")
        # ✅ SEGUNDA TRAVA DE SEGURANÇA: Inspeção física para o Espião
        if caminho_video.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
            if EXIBIR_LOGS: logger.warning(f"🚫 [Segurança] Disparo do Espião abortado! O ficheiro {caminho_video} é uma imagem.")
            raise Exception("O ficheiro retido é uma imagem.")
            
        arquivo = FSInputFile(caminho_video)
        await bot.send_video(chat_id=canal_destino, video=arquivo, caption=legenda_postagem, parse_mode="HTML")
        if EXIBIR_LOGS: logger.info(f"✅ Clone {item_id} publicado com sucesso!")
        try: os.remove(caminho_video)
        except: pass
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha ao postar clone: {e}")
        try: os.rename(caminho_video, caminho_video + ".pendente")
        except: pass
        
    # ✅ CORREÇÃO: Em vez de apagar, marca como processado para manter no relatório até ao fim do dia
    for item in fila:
        if item["id"] == item_id:
            item["processado"] = True
            item["data_postagem"] = agora.strftime("%Y-%m-%d")
            item["horario_postagem"] = agora.strftime("%H:%M")
            if EXIBIR_LOGS: logger.info(f"💾 [Espião] Vídeo {item_id} marcado como 'Postado' às {item['horario_postagem']} na memória da fila.")
            break
    fila_data["fila"] = fila
    
    # ✅ MOTOR DE ESPAÇAMENTO DINÂMICO (Baseado estritamente na Janela)
    if forcar:
        minutos_espera = 0
        proximo_horario = agora
    else:
        fim_da_janela = agora.replace(hour=max(0, fim_janela - 1), minute=59, second=59, microsecond=0)
        minutos_restantes = int((fim_da_janela - agora).total_seconds() / 60)
        if minutos_restantes < 1:
            minutos_restantes = 1
            
        base_intervalo = minutos_restantes // len(itens_elegiveis) if len(itens_elegiveis) > 0 else 1
        minutos_espera = base_intervalo + random.randint(-5, 5)
        if minutos_espera < 2:
            minutos_espera = 2  
            
        proximo_horario = agora + timedelta(minutes=minutos_espera)
        
    # ✅ FAXINA AUTOMÁTICA: Remove os vídeos postados em dias anteriores para o JSON não inchar
    hoje_faxina = agora.strftime("%Y-%m-%d")
    fila_data["fila"] = [i for i in fila_data["fila"] if not i.get("processado") or i.get("data_postagem") == hoje_faxina]
    
    fila_data["proximo_processamento"] = proximo_horario.strftime("%Y-%m-%d %H:%M:%S")
    salvar_fila_clonagem(fila_data)
    
    try: os.remove(caminho_video)
    except: pass

async def sincronizar_financeiro_horario():
    if EXIBIR_LOGS: logger.info("⏰ [Financeiro] Iniciando sincronização em background com a API Shopee...")
    
    conversoes = await buscar_dados_financeiros_shopee(3)
    if conversoes:
        processar_e_salvar_pedidos_api(conversoes)
        if EXIBIR_LOGS: logger.info("✅ [Financeiro] Varredura horária concluída. Banco de Pedidos atualizado.")

async def varredura_retroativa_pendentes():
    if EXIBIR_LOGS: logger.info("🌙 [Pente Fino] Iniciando varredura de madrugada para caçar pedidos pendentes antigos...")
    
    pedidos_db = ler_banco_pedidos()
    if not pedidos_db:
        return
        
    agora = datetime.now(fuso_horario)
    data_mais_antiga = agora
    tem_pendentes = False
    
    for order_sn, dados in pedidos_db.items():
        if dados.get("status") == "PENDING":
            tem_pendentes = True
            try:
                data_pedido = datetime.strptime(dados["data"], "%Y-%m-%d").replace(tzinfo=fuso_horario)
                if data_pedido < data_mais_antiga:
                    data_mais_antiga = data_pedido
            except ValueError:
                pass
                
    if not tem_pendentes:
        if EXIBIR_LOGS: logger.info("✅ [Pente Fino] Nenhum pedido pendente no banco de dados. Varredura suspensa.")
        return
        
    dias_retroativos = (agora - data_mais_antiga).days + 1
    if dias_retroativos > 60: dias_retroativos = 60
    if dias_retroativos < 5: dias_retroativos = 5
    
    if EXIBIR_LOGS: logger.info(f"🔍 [Pente Fino] Pendentes antigos detetados! A requisitar relatório dos últimos {dias_retroativos} dias à Shopee...")
    
    conversoes = await buscar_dados_financeiros_shopee(dias_retroativos)
    if conversoes:
        processar_e_salvar_pedidos_api(conversoes)
        if EXIBIR_LOGS: logger.info("✅ [Pente Fino] Varredura profunda concluída! Pendentes antigos consolidados (Confirmados ou Cancelados).")

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

# =========================================================
# COLE O CALLBACK AQUI, ANTES DO MAIN()
# =========================================================
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@dp.callback_query(F.data == 'forcar_clones_espiao')
async def forcar_clones_fila(callback: types.CallbackQuery):
    if EXIBIR_LOGS:
        logger.info("🚀 Iniciando processo de forçar disparo dos clones...")
        
    try:
        with open('fila_clonagem.json', 'r', encoding='utf-8') as f:
            fila = json.load(f).get("fila", [])
            
        quantidade = len([i for i in fila if not i.get("processado")])
        
        if quantidade == 0:
            if EXIBIR_LOGS: logger.info("⚠️ A fila de clonagem já está vazia.")
            await callback.answer("A fila de clonagem já está vazia!", show_alert=True)
            return
            
        if EXIBIR_LOGS: logger.info(f"📂 {quantidade} vídeos encontrados na fila. Solicitando confirmação...")
            
        markup_confirmacao = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Aprovar ✅", callback_data="executar_forcar_clones"),
                    InlineKeyboardButton(text="Cancelar ❌", callback_data="cancelar_operacao")
                ]
            ]
        )
        
        await callback.message.edit_text(f"Você tem {quantidade} vídeos retidos na fila de clonagem.\nDeseja forçar o processamento imediato de todos?", reply_markup=markup_confirmacao)
        
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler fila de clonagem: {e}")
        await callback.answer("Erro ao acessar a fila de clonagem.", show_alert=True)

# =========================================================
# O MAIN() E O INICIADOR FICAM SEMPRE NO FINAL ABSOLUTO
# =========================================================
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
    
    # ✅ NOVO: Pente fino de madrugada (roda todos os dias às 02:00) para resgatar pendentes de meses anteriores
    scheduler.add_job(varredura_retroativa_pendentes, 'cron', hour=2, minute=0, timezone=FUSO_STR)

    # ✅ Novo: Check-up diário de permissões em grupos roda todos os dias às 11:00
    scheduler.add_job(checkup_diario_grupos, 'cron', hour=11, minute=0, timezone=FUSO_STR)

    # ✅ Novo: Motor Autônomo de Garimpo de Achadinhos (Gatilho de 2 em 2 horas)
    scheduler.add_job(processar_garimpo_automatico, 'interval', hours=2, timezone=FUSO_STR)
    
    # ✅ NOVO MOTOR DE FILA (Fase 3): O Relógio Central bate a cada 1 minuto
    scheduler.add_job(motor_fila_minuto, 'interval', minutes=1, timezone=FUSO_STR)
    
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
