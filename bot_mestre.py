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
from aiogram import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
import subprocess
from apscheduler.schedulers.asyncio import AsyncIOScheduler
# ✅ Importação dos nossos novos módulos blindados (Fase 2)
from api_gemini import gerar_texto_gemini, analisar_video_gemini, MODELOS_CASCATA_GEMINI, client_genai
from api_shopee import converter_link_shopee, buscar_ofertas_shopee
from motor_filas import calcular_horarios_distribuicao # ⚙️ Novo Motor Centralizado

import matplotlib.pyplot as plt
import io
import sqlite3
import painel_espelhos
import painel_notas
from utils import registrar_erro_json, ler_cache_nomes_grupos, salvar_nome_grupo, validar_e_formatar_alvo
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
    
    # 1. Tabela da Fila de Vídeos Central
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
    
    # 2. Tabela de Configurações (Guarda o status do Bom Dia/Boa Noite)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    ''')
    
    # 3. Tabela da Lixeira Persistente (Guarda os IDs para apagar às 03h00)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lixeira_mensagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_id INTEGER,
            chat_id TEXT,
            data_inclusao TEXT
        )
    ''')
    
    # 4. Tabela de Logs de Erros
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS erros_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            origem TEXT,
            erro TEXT
        )
    ''')
    
    # 5. Tabela de Despesas Operacionais (Centro Financeiro)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS financeiro_despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            valor REAL,
            data_registro TEXT
        )
    ''')
    
    # 🚀 Migração invisível 1: Adiciona a coluna 'tipo' se ela não existir
    try:
        cursor.execute("ALTER TABLE financeiro_despesas ADD COLUMN tipo TEXT DEFAULT 'mensal'")
        if EXIBIR_LOGS: logger.info("📦 Banco de dados atualizado: Coluna 'tipo' adicionada à tabela de despesas.")
    except sqlite3.OperationalError:
        pass

    # 🚀 Migração invisível 2: Colunas do Robô Repostador no Público
    try:
        cursor.execute("ALTER TABLE fila_autorais ADD COLUMN repostado_publico INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE fila_autorais ADD COLUMN data_repost_publico TEXT")
        if EXIBIR_LOGS: logger.info("📦 Banco de dados atualizado: Colunas de Repostagem Pública adicionadas à fila_autorais.")
    except sqlite3.OperationalError:
        pass

    # 🚀 Migração invisível 4: Data-alvo própria da fila do Grupo Público
    try:
        cursor.execute("ALTER TABLE fila_autorais ADD COLUMN data_alvo_publico TEXT")
        cursor.execute("ALTER TABLE fila_autorais ADD COLUMN status_publico TEXT")
        if EXIBIR_LOGS: logger.info("📦 Banco de dados atualizado: Colunas 'data_alvo_publico' e 'status_publico' adicionadas à fila_autorais.")
    except sqlite3.OperationalError:
        pass

    # 🚀 Migração invisível 5: garante a coluna de status mesmo em bancos que já tinham a data-alvo
    try:
        cursor.execute("ALTER TABLE fila_autorais ADD COLUMN status_publico TEXT")
        if EXIBIR_LOGS: logger.info("📦 Banco de dados atualizado: Coluna 'status_publico' adicionada à fila_autorais.")
    except sqlite3.OperationalError:
        pass
        
    # 🚀 Migração invisível 3: Atualiza a tabela de Logs para suportar o Utils Avançado
    try:
        cursor.execute("ALTER TABLE erros_logs ADD COLUMN rastro_codigo TEXT")
        cursor.execute("ALTER TABLE erros_logs ADD COLUMN contexto TEXT")
        if EXIBIR_LOGS: logger.info("📦 Banco de dados atualizado: Colunas 'rastro_codigo' e 'contexto' adicionadas à tabela erros_logs.")
    except sqlite3.OperationalError:
        pass
    
    # 6. Tabela de Histórico de Saques (Centro Financeiro)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS financeiro_saques (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            valor REAL,
            data_registro TEXT
        )
    ''')
    
    conexao.commit()
    conexao.close()
    if EXIBIR_LOGS: logger.info("✅ Estrutura SQLite blindada e pronta para receber operações de leitura/escrita.")

inicializar_banco_sqlite()

# 1. CONSTANTES E TOKENS
API_TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = 1226920464
GRUPO_ID = -1003909405581
LINK_GRUPO = "https://t.me/shopee_video_afiliado"
GRUPO_VIRAL_ID = -1003932482573
LINK_GRUPO_VIRAL = "https://t.me/acervo_viral_shopee"
LINK_GRUPO_PUBLICO = "https://t.me/GrupoPublicoAfiliados"
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
    aguardando_selecao_limpeza = State() # ✅ NOVO: Passo 1 (Escolher o que limpar)
    aguardando_acao_limpeza = State()    # ✅ NOVO: Passo 2 (Confirmar a limpeza)
    aguardando_confirmacao_reiniciar = State()

class ConfigDivulgacao(StatesGroup):
    menu_principal = State()
    aguardando_alvos = State()
    aguardando_exclusao_alvo = State()
    aguardando_tipo_edicao = State()
    aguardando_selecao_alvo = State()
    aguardando_valores_unificados = State()
    aguardando_confirmacao_pausa = State() # ✅ NOVO

class ConfigDivulgacaoViral(StatesGroup):
    menu_principal = State()
    aguardando_alvos = State()
    aguardando_exclusao_alvo = State()
    aguardando_tipo_edicao = State()
    aguardando_selecao_alvo = State()
    aguardando_valores_unificados = State()
    aguardando_confirmacao_pausa = State() # ✅ NOVO

class ConfigRotina(StatesGroup):
    menu_principal = State()
    aguardando_novo_horario = State()
    aguardando_confirmacao_pausa = State() # ✅ NOVO: Estado para confirmar a pausa
    aguardando_confirmacao_disparo = State() # ✅ NOVO: Confirmação dos disparos manuais do Público
    aguardando_alvos_rotina = State() # ✅ NOVO: Seleção dos tópicos que recebem as rotinas
    aguardando_confirmacao_alvos_rotina = State() # ✅ NOVO: Confirmação dos alvos de postagem

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
    aguardando_confirmacao_alvo = State()
    aguardando_remocao_alvo = State()
    aguardando_confirmacao_remocao = State()
    aguardando_canal_destino = State()
    aguardando_confirmacao_destino = State()
    aguardando_confirmacao_forcar_clones = State()
    aguardando_acao_blacklist = State()
    aguardando_blacklist_add = State()
    aguardando_blacklist_remove = State()
    aguardando_confirmacao_blacklist_conflito = State()
    aguardando_acao_analise = State()

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

class SubmissaoAdminFluxo(StatesGroup):
    menu_principal = State()
    aguardando_confirmacao_toggle = State()
    
    # Estados para Regras de Repostagem
    aguardando_repost_dias = State()
    aguardando_repost_limite = State()
    aguardando_confirmacao_repost_dias = State()
    aguardando_confirmacao_repost_limite = State()
    aguardando_confirmacao_pausa_repost = State()
    aguardando_repost_origem = State()
    aguardando_repost_destino = State() # ✅ NOVO ESTADO AQUI
    
    # ✅ NOVOS ESTADOS: Edição Modular do Grupo e Tópicos
    aguardando_selecao_edicao_grupo = State()
    aguardando_novo_valor_grupo = State()
    aguardando_confirmacao_grupo = State()

class SubmissaoUsuarioInterativa(StatesGroup):
    aguardando_video = State()
    aguardando_shopee = State()
    aguardando_tiktok = State()

def ler_submissao_config():
    return ler_config_bd("submissao_config", padrao={
        "ativo": False, 
        "grupo_id": None, 
        "topico_envio": None, 
        "topico_destino": None,
        "repost_origem": None, # ✅ NOVO: Chave para a origem
        "repost_dias": 15,
        "repost_limite": 6,
        "repost_pausado": False,
        "repost_data_atual": "",
        "repost_qtd_hoje": 0,
        "repost_ultimo_horario": ""
    })

def salvar_submissao_config(dados):
    salvar_config_bd("submissao_config", dados)

class AutoraisFluxo(StatesGroup):
    menu_principal = State()
    aguardando_origem = State()
    aguardando_topico = State() 
    aguardando_confirmacao_origem = State() # ✅ NOVO: Etapa de confirmação
    aguardando_destino = State()
    aguardando_confirmacao_destino = State() # ✅ NOVO: Etapa de confirmação
    aguardando_dias_retorno = State()
    aguardando_confirmacao_dias_retorno = State() # ✅ NOVO: Etapa de confirmação
    aguardando_limite_videos = State()
    aguardando_confirmacao_limite_videos = State() # ✅ NOVO: Etapa de confirmação
    aguardando_janela_autorais = State()           # 🕐 NOVO: Janela de horário do retorno
    aguardando_confirmacao_janela_autorais = State()
    aguardando_confirmacao_pausa_repost = State()
    aguardando_confirmacao_pausa_robo = State()

class RelatoriosFluxo(StatesGroup):
    menu_filas = State()
    aguardando_rota_espelhador = State() # ✅ NOVO: Estado para selecionar qual rota visualizar

class ConfigRotinaEspiao(StatesGroup):
    aguardando_janela = State()
    aguardando_confirmacao_janela = State() # ✅ NOVO
    aguardando_intervalo_espiao = State()
    aguardando_modo = State()
    aguardando_confirmacao_tempo = State() # ✅ NOVO

# --- MÁQUINA DE ESTADOS DO CENTRO FINANCEIRO ---
class FinanceiroFluxo(StatesGroup):
    menu_principal = State()
    aguardando_nome_despesa = State()
    aguardando_valor_despesa = State()
    aguardando_tipo_despesa = State()
    aguardando_exclusao_despesa = State()
    aguardando_valor_imposto = State()
    aguardando_saldo_shopee = State()

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
dp.include_router(painel_espelhos.router)
painel_espelhos.configurar_dependencias(bot, scheduler)
if EXIBIR_LOGS: logger.info("✅ Módulo Espelhador montado com segurança.")

if EXIBIR_LOGS: logger.info("🔄 Acoplando o módulo de Disparo de Notas ao fluxo principal...")
dp.include_router(painel_notas.router)
painel_notas.configurar_dependencias(bot, scheduler)
if EXIBIR_LOGS: logger.info("✅ Módulo de Notas montado com segurança.")

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

def obter_teclado_outros_canais():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Espião Afiliados 🕵️"), KeyboardButton(text="Espelhador de Canais 🔄")],
            [KeyboardButton(text="Vídeos Autorais 🎥"), KeyboardButton(text="Grupo Público 📬")],
            [KeyboardButton(text="Gerador de Achadinhos 🛍️")],
            [KeyboardButton(text="Voltar ao Início 🔙")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

teclado_outros_canais = obter_teclado_outros_canais()

## --- NOVO MENU: CENTRO FINANCEIRO ---
def obter_teclado_centro_financeiro():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Extrato Rápido 📜"), KeyboardButton(text="Relatório Financeiro 💰")],
            [KeyboardButton(text="Gestão de Custos 📉"), KeyboardButton(text="Provisão de Impostos 🏛️")],
            [KeyboardButton(text="Definir Saldo (App) 💰"), KeyboardButton(text="Fluxo de Caixa 🏦")],
            [KeyboardButton(text="Disparador de Notas 🧾")],
            [KeyboardButton(text="Voltar ao Início 🔙")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

@dp.message(F.text == "Centro Financeiro 💸", StateFilter("*"))
async def menu_centro_financeiro(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    if EXIBIR_LOGS: logger.info("💸 Acessando a gaveta do Centro Financeiro.")
    await message.answer("💸 <b>Centro Financeiro</b>\nSelecione a ferramenta de gestão desejada:", reply_markup=obter_teclado_centro_financeiro(), parse_mode="HTML")
    await state.set_state(FinanceiroFluxo.menu_principal)

# ==========================================
# MÓDULO: CENTRO FINANCEIRO (FASE 2)
# ==========================================

def obter_teclado_gestao_custos():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Adicionar Custo ➕"), KeyboardButton(text="Remover Custo 🗑️")],
            [KeyboardButton(text="Voltar ao Centro Financeiro 🔙")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

@dp.message(F.text == "Voltar ao Centro Financeiro 🔙", StateFilter("*"))
async def voltar_centro_financeiro(message: types.Message, state: FSMContext):
    # Essa função agora é um "ímã" global. De qualquer lugar do bot, 
    # se esse botão for clicado, ele te puxa direto para o painel financeiro.
    await menu_centro_financeiro(message, state)

# --- 1. PROVISÃO DE IMPOSTOS ---
@dp.message(FinanceiroFluxo.menu_principal, F.text == "Provisão de Impostos 🏛️")
async def menu_impostos(message: types.Message, state: FSMContext):
    taxa_atual = ler_config_bd("imposto_taxa", 6.0)
    texto = (
        f"🏛️ <b>Provisão de Impostos (Simples Nacional)</b>\n\n"
        f"A sua alíquota atual configurada é: <b>{taxa_atual}%</b>\n\n"
        f"O robô usa essa porcentagem para descontar virtualmente do seu faturamento bruto aprovado, ajudando a calcular o Lucro Líquido Real.\n\n"
        f"Envie o novo valor percentual (Exemplo: <code>6.5</code> ou <code>10</code>) ou clique em Cancelar:"
    )
    await message.answer(texto, reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(FinanceiroFluxo.aguardando_valor_imposto)

@dp.message(FinanceiroFluxo.aguardando_valor_imposto)
async def salvar_imposto(message: types.Message, state: FSMContext):
    # 🛡️ Trava de Cancelamento
    if message.text == "Cancelar ❌":
        await state.clear()
        await message.answer("Ação cancelada.")
        await menu_centro_financeiro(message, state)
        return
        
    texto = message.text.strip().replace(",", ".")
    try:
        nova_taxa = float(texto)
        salvar_config_bd("imposto_taxa", nova_taxa)
        if EXIBIR_LOGS: logger.info(f"🏛️ Alíquota de imposto atualizada no banco para {nova_taxa}%.")
        await message.answer(f"✅ <b>Alíquota atualizada!</b>\nNovo imposto configurado para <b>{nova_taxa}%</b>.", parse_mode="HTML")
        await menu_centro_financeiro(message, state)
    except ValueError:
        await message.answer("⚠️ Valor inválido. Digite apenas números e ponto (Ex: 6.5):", reply_markup=teclado_cancelar)

# --- 2. GESTÃO DE CUSTOS ---
@dp.message(FinanceiroFluxo.menu_principal, F.text == "Gestão de Custos 📉")
async def listar_custos(message: types.Message, state: FSMContext):
    conexao = sqlite3.connect("banco_dados.db")
    cursor = conexao.cursor()
    
    agora_str = datetime.now(fuso_horario).strftime("%Y-%m")
    
    # Busca apenas os fixos mensais e os pontuais deste exato mês
    cursor.execute("SELECT id, nome, valor, tipo FROM financeiro_despesas WHERE tipo = 'mensal' OR (tipo = 'pontual' AND data_registro LIKE ?)", (f"{agora_str}%",))
    despesas = cursor.fetchall()
    conexao.close()
    
    texto = "📉 <b>Gestão de Custos Operacionais</b>\n\n"
    total_custos = 0.0
    
    if despesas:
        for i, (id_db, nome, valor, tipo) in enumerate(despesas, 1):
            valor_br = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            etiqueta = "🔁 Fixo" if tipo == "mensal" else "🎯 Pontual"
            texto += f"<b>{i}.</b> {nome} <i>({etiqueta})</i>: R$ {valor_br}\n"
            total_custos += valor
            
        total_br = f"{total_custos:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        texto += f"\n💰 <b>Custo Total Deduzido no Mês:</b> R$ {total_br}"
        
        # Salva o mapa de IDs na memória para a função de exclusão
        mapa_exclusao = {str(i): id_db for i, (id_db, nome, valor, tipo) in enumerate(despesas, 1)}
        await state.update_data(mapa_custos=mapa_exclusao)
    else:
        texto += "<i>Nenhuma despesa ativa cadastrada para este mês. Todo o faturamento será considerado lucro bruto.</i>"
        
    await message.answer(texto, reply_markup=obter_teclado_gestao_custos(), parse_mode="HTML")
    await state.set_state(FinanceiroFluxo.menu_principal)

@dp.message(FinanceiroFluxo.menu_principal, F.text == "Adicionar Custo ➕")
async def pedir_nome_custo(message: types.Message, state: FSMContext):
    await message.answer("Digite o <b>NOME</b> da despesa (Ex: Servidor Oracle, Domínio, Anúncio Extra):", reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(FinanceiroFluxo.aguardando_nome_despesa)

@dp.message(FinanceiroFluxo.aguardando_nome_despesa)
async def pedir_valor_custo(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await state.clear()
        await message.answer("Ação cancelada.")
        await menu_centro_financeiro(message, state)
        return
        
    nome_custo = message.text.strip()
    await state.update_data(nome_despesa=nome_custo)
    await message.answer(f"Custo: <b>{nome_custo}</b>\n\nDigite o <b>VALOR</b> dessa despesa (Exemplo: <code>50.00</code> ou <code>120,50</code>):", reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(FinanceiroFluxo.aguardando_valor_despesa)

@dp.message(FinanceiroFluxo.aguardando_valor_despesa)
async def pedir_tipo_custo(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await state.clear()
        await message.answer("Ação cancelada.")
        await listar_custos(message, state)
        return
        
    texto_valor = message.text.strip().replace("R$", "").replace(" ", "").replace(",", ".")
    try:
        valor = float(texto_valor)
        await state.update_data(valor_despesa=valor)
        
        teclado_tipo_custo = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Mensal Fixo 🔁"), KeyboardButton(text="Pontual (Só este mês) 🎯")],
                [KeyboardButton(text="Cancelar ❌")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        
        await message.answer("Excelente! Como deseja classificar esta despesa?\n\n<b>Mensal Fixo:</b> Será cobrada todos os meses.\n<b>Pontual:</b> Será deduzida apenas no caixa deste mês.", reply_markup=teclado_tipo_custo, parse_mode="HTML")
        await state.set_state(FinanceiroFluxo.aguardando_tipo_despesa)
        
    except ValueError:
        await message.answer("⚠️ Valor numérico inválido. Digite apenas números (Ex: 50.00):", reply_markup=teclado_cancelar)

@dp.message(FinanceiroFluxo.aguardando_tipo_despesa)
async def salvar_tipo_custo(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await state.clear()
        await message.answer("Ação cancelada.")
        await listar_custos(message, state)
        return
        
    if message.text not in ["Mensal Fixo 🔁", "Pontual (Só este mês) 🎯"]:
        await message.answer("Por favor, utilize os botões em tela para escolher o tipo de despesa.")
        return
        
    tipo_escolhido = "mensal" if "Mensal" in message.text else "pontual"
    
    data = await state.get_data()
    nome = data.get("nome_despesa")
    valor = data.get("valor_despesa")
    data_hoje = datetime.now(fuso_horario).strftime("%Y-%m-%d")
    
    conexao = sqlite3.connect("banco_dados.db")
    cursor = conexao.cursor()
    cursor.execute("INSERT INTO financeiro_despesas (nome, valor, data_registro, tipo) VALUES (?, ?, ?, ?)", (nome, valor, data_hoje, tipo_escolhido))
    conexao.commit()
    conexao.close()
    
    if EXIBIR_LOGS: logger.info(f"📉 Nova despesa adicionada: {nome} - R$ {valor} ({tipo_escolhido})")
    
    valor_br = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    etiqueta = "fixa mensal" if tipo_escolhido == "mensal" else "pontual"
    await message.answer(f"✅ Despesa <b>{nome}</b> (R$ {valor_br}) cadastrada como {etiqueta} no seu fluxo de caixa!", parse_mode="HTML")
    
    await listar_custos(message, state)

@dp.message(FinanceiroFluxo.menu_principal, F.text == "Remover Custo 🗑️")
async def pedir_remocao_custo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    mapa_custos = data.get("mapa_custos", {})
    
    if not mapa_custos:
        await message.answer("Não há custos cadastrados para remover nesta visualização.", reply_markup=obter_teclado_gestao_custos())
        return
        
    await message.answer("Digite o <b>NÚMERO</b> do custo que deseja excluir da lista:", reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(FinanceiroFluxo.aguardando_exclusao_despesa)

@dp.message(FinanceiroFluxo.aguardando_exclusao_despesa)
async def processar_remocao_custo(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await state.clear()
        await message.answer("Ação cancelada.")
        await listar_custos(message, state)
        return
        
    numero_digitado = message.text.strip()
    data = await state.get_data()
    mapa_custos = data.get("mapa_custos", {})
    
    if numero_digitado in mapa_custos:
        id_db = mapa_custos[numero_digitado]
        conexao = sqlite3.connect("banco_dados.db")
        cursor = conexao.cursor()
        cursor.execute("DELETE FROM financeiro_despesas WHERE id = ?", (id_db,))
        conexao.commit()
        conexao.close()
        
        if EXIBIR_LOGS: logger.info(f"🗑️ Despesa excluída do banco de dados (ID {id_db}).")
        await message.answer("✅ Custo removido com sucesso!")
        await listar_custos(message, state)
    else:
        await message.answer("⚠️ Número não encontrado na lista. Digite um número válido ou clique em Cancelar:", reply_markup=teclado_cancelar)

# --- 3. FLUXO DE CAIXA (PLANILHA EXTERNA) 🏦 ---
@dp.message(FinanceiroFluxo.menu_principal, F.text == "Fluxo de Caixa 🏦")
async def abrir_fluxo_caixa_planilha(message: types.Message, state: FSMContext):
    if EXIBIR_LOGS: logger.info("🏦 Usuário solicitou acesso ao Fluxo de Caixa externo.")
    texto = (
        "🏦 <b>Seu Fluxo de Caixa</b>\n\n"
        "O controle detalhado de saídas, recebimentos reais e caixa livre agora é feito diretamente na sua planilha oficial do Google Planilhas para maior precisão.\n\n"
        "Acesse o seu controle financeiro clicando no link abaixo:\n"
        "👉 <a href='https://docs.google.com/spreadsheets/d/1zKtT_Zl5XLDrG9cQgzhoThyXzw56UyG_0vxOcUZjlZM/edit?usp=sharing'>Abrir Planilha de Fluxo de Caixa</a>"
    )
    await message.answer(texto, parse_mode="HTML", disable_web_page_preview=True)


# --- 5. DEFINIR SALDO BASE (LIVRO CAIXA AUTOMÁTICO) ---
@dp.message(FinanceiroFluxo.menu_principal, F.text == "Definir Saldo (App) 💰")
async def pedir_saldo_shopee(message: types.Message, state: FSMContext):
    saldo_atual = float(ler_config_bd("saldo_caixa_shopee", 0.0))
    valor_br = f"{saldo_atual:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    texto = (
        f"💰 <b>Definir Saldo Inicial</b>\n\n"
        f"O saldo atual gravado no robô é: <b>R$ {valor_br}</b>\n\n"
        f"Digite o valor exato que aparece no seu saldo 'A Receber' do App da Shopee.\n"
        f"A partir de agora, o robô vai somar automaticamente qualquer venda que mudar para 'Confirmado' dentro deste valor.\n\n"
        f"Digite o valor (Exemplo: <code>746.29</code>):"
    )
    await message.answer(texto, reply_markup=teclado_cancelar, parse_mode="HTML")
    await state.set_state(FinanceiroFluxo.aguardando_saldo_shopee)

@dp.message(FinanceiroFluxo.aguardando_saldo_shopee)
async def salvar_saldo_shopee(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await state.clear()
        await message.answer("Ação cancelada.")
        await menu_centro_financeiro(message, state)
        return
        
    texto_valor = message.text.strip().replace("R$", "").replace(" ", "").replace(",", ".")
    try:
        valor = float(texto_valor)
        msg_status = await message.answer("🔄 Sincronizando e fotografando o passado para evitar duplicações... Aguarde ⏳", reply_markup=teclado_cancelar)
        
        # Puxa 90 dias (limite físico máximo da API) e salva o status atual SEM mexer no saldo
        conversoes = await buscar_dados_financeiros_shopee(90)
        if conversoes:
            processar_e_salvar_pedidos_api(conversoes, ignorar_ledger=True)
            
        # Agora define o saldo base limpo
        salvar_config_bd("saldo_caixa_shopee", valor)
        if EXIBIR_LOGS: logger.info(f"💰 Saldo Base definido cirurgicamente para R$ {valor}.")
        
        await msg_status.delete()
        valor_br = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        await message.answer(f"✅ <b>Saldo Atualizado!</b>\nO robô assumiu <b>R$ {valor_br}</b> como base.\nA partir de amanhã, as novas confirmações serão somadas automaticamente aqui.", parse_mode="HTML")
        await menu_centro_financeiro(message, state)
    except ValueError:
        await message.answer("⚠️ Valor inválido. Digite apenas números e ponto (Ex: 746.29):", reply_markup=teclado_cancelar)

# --- 6. EXTRATO RÁPIDO (HISTÓRICO) 📜 ---
@dp.message(FinanceiroFluxo.menu_principal, F.text == "Extrato Rápido 📜")
async def gerar_extrato_rapido(message: types.Message, state: FSMContext):
    msg_status = await message.answer("📜 Compilando seu histórico financeiro... Aguarde ⏳")
    
    historico_limpo = ler_historico_financeiro()
    taxa_imposto = ler_config_bd("imposto_taxa", 6.0)
    
    # 🟢 O cérebro do DRE clonado para o mês atual
    saldo_caixa_atual = float(ler_config_bd("saldo_caixa_shopee", 0.0))
    hoje_str = datetime.now(fuso_horario).strftime("%Y-%m")
    
    conexao = sqlite3.connect("banco_dados.db")
    cursor = conexao.cursor()
    
    # Pega todos os custos para separar por mês
    cursor.execute("SELECT valor, tipo, data_registro FROM financeiro_despesas")
    despesas = cursor.fetchall()
    conexao.close()
    
    custos_fixos_mensais = sum(d[0] for d in despesas if d[1] == "mensal")
    custos_pontuais = {} # Dicionário para agrupar custos pontuais por mês "YYYY-MM"
    for d in despesas:
        if d[1] == "pontual" and d[2]:
            mes_gasto = d[2][:7] # Extrai YYYY-MM
            custos_pontuais[mes_gasto] = custos_pontuais.get(mes_gasto, 0.0) + d[0]
            
    # Agrupa o faturamento por mês (Para o histórico passado)
    faturamento_mensal = {}
    for data_str, dados_dia in historico_limpo.items():
        mes_key = data_str[:7]
        faturamento_mensal[mes_key] = faturamento_mensal.get(mes_key, 0.0) + dados_dia.get("aprovado", 0.0)
        
    # Garante que o mês atual apareça no extrato mesmo se a API ainda não leu nada novo hoje
    if hoje_str not in faturamento_mensal and saldo_caixa_atual > 0:
        faturamento_mensal[hoje_str] = 0.0
        
    if not faturamento_mensal:
        await msg_status.edit_text("<i>Nenhum histórico financeiro encontrado ainda.</i>", parse_mode="HTML")
        return
        
    # Ordena os meses do mais recente para o mais antigo (Mostra os últimos 6 meses)
    meses_ordenados = sorted(faturamento_mensal.keys(), reverse=True)[:6]
    
    def f_br(valor): return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    texto = "📜 <b>Extrato Rápido (Últimos 6 Meses)</b>\n\n"
    
    for mes in meses_ordenados:
        # 🟢 A MÁGICA DA SINCRONIZAÇÃO: Se for o mês atual, usa o saldo cravado do DRE!
        if mes == hoje_str:
            faturamento = saldo_caixa_atual
        else:
            faturamento = faturamento_mensal[mes]
            
        imposto = faturamento * (taxa_imposto / 100)
        custo_pontual_mes = custos_pontuais.get(mes, 0.0)
        custo_total_mes = custos_fixos_mensais + custo_pontual_mes
        
        lucro = faturamento - imposto - custo_total_mes
        
        # Formatação visual amigável do mês
        ano_str, mes_str = mes.split('-')
        meses_pt = {"01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr", "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago", "09": "Set", "10": "Out", "11": "Nov", "12": "Dez"}
        nome_mes = f"{meses_pt.get(mes_str, mes_str)}/{ano_str}"
        
        icone_lucro = "✅" if lucro >= 0 else "🛑"
        
        texto += f"📅 <b>{nome_mes}</b>\n"
        texto += f"   💰 Confirmado: R$ {f_br(faturamento)}\n"
        texto += f"   🏛️ Provisão Imposto: - R$ {f_br(imposto)}\n"
        texto += f"   📉 Custos Totais: - R$ {f_br(custo_total_mes)}\n"
        texto += f"   {icone_lucro} <b>LUCRO LIVRE DO MÊS: R$ {f_br(lucro)}</b>\n\n"
        
    texto += "<i>*O mês atual está sincronizado em tempo real com o seu Caixa da Shopee.</i>\n"
    texto += "<i>*Os custos incluem suas despesas fixas + despesas pontuais do respectivo mês.</i>"
    
    await msg_status.edit_text(texto, parse_mode="HTML")

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
        [KeyboardButton(text="Centro Financeiro 💸")],
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
        [KeyboardButton(text="Reiniciar Robôs 🔄")], # ✅ NOVO BOTÃO AQUI
        [KeyboardButton(text="Voltar ao Início 🔙")]
    ]
    return ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)

# --- SISTEMA DO ESPIÃO (CONFIGURAÇÕES) ---
def ler_alvos_espiao():
    padrao = {"alvos": [], "canal_destino": None, "status_alvos": {}}
    return ler_config_bd("alvos_espiao", padrao, arquivo_legado="alvos_espiao.json")

def salvar_alvos_espiao(dados):
    salvar_config_bd("alvos_espiao", dados)

teclado_menu_espiao = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Grupos Vigiados 📡")],
        [KeyboardButton(text="Forçar Postagens 🚀")],
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
        [KeyboardButton(text="Definir Destino 🎯")],
        [KeyboardButton(text="Adicionar Grupo ➕"), KeyboardButton(text="Remover Grupo 🗑️")],
        [KeyboardButton(text="Editar Janela 🕒"), KeyboardButton(text="Editar Atraso ⏳")],
        [KeyboardButton(text="Analisar Canais Vigiados 🔎")],
        [KeyboardButton(text="Voltar ao Menu Espião 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

@dp.message(EspiaoFluxo.menu_principal, F.text == "Analisar Canais Vigiados 🔎")
async def menu_analise_canais_espiao(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    teclado_analise = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Listar Todos 📜"), KeyboardButton(text="❌ Erros")],
            [KeyboardButton(text="⚠️ Duplicados")],
            [KeyboardButton(text="Voltar às Opções 🔙")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer("🔎 <b>Análise de Canais Vigiados</b>\nEscolha a ferramenta que deseja utilizar:", reply_markup=teclado_analise, parse_mode="HTML")
    await state.set_state(EspiaoFluxo.aguardando_acao_analise)

@dp.message(EspiaoFluxo.aguardando_acao_analise, F.text == "❌ Erros")
async def listar_erros_espiao(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    dados = ler_alvos_espiao()
    alvos = dados.get("alvos", [])
    if not alvos:
        await message.answer("Não há grupos sendo monitorados.")
        return
        
    cache_nomes = ler_cache_nomes_grupos()
    status_alvos = dados.get("status_alvos", {})
    canais_com_erro = []
    texto = "❌ <b>Canais com Erro de Acesso (Espião)</b>\n\n"
    
    for i, alvo in enumerate(alvos, 1):
        info = status_alvos.get(str(alvo), {})
        if info.get("status") == "erro":
            nome = info.get("nome") or cache_nomes.get(str(alvo), str(alvo))
            canais_com_erro.append(str(alvo))
            texto += f"<b>{i}.</b> ❌ {nome} (<code>{alvo}</code>)\n"
            
    if not canais_com_erro:
        await message.answer("✅ <b>Tudo limpo!</b>\nNão há nenhum canal com erro de acesso no Espião.", parse_mode="HTML")
        return
        
    teclado_remover_erros = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Remover Todos com Erro 🗑️", callback_data="remover_erros_espiao")]]
    )
    await message.answer(texto, parse_mode="HTML", reply_markup=teclado_remover_erros)

@dp.callback_query(F.data == "remover_erros_espiao")
async def remover_erros_espiao_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    dados = ler_alvos_espiao()
    alvos_atuais = dados.get("alvos", [])
    status_alvos = dados.get("status_alvos", {})
    
    alvos_limpos = []
    removidos = 0
    for alvo in alvos_atuais:
        info = status_alvos.get(str(alvo), {})
        if info.get("status") == "erro": removidos += 1
        else: alvos_limpos.append(alvo)
            
    if removidos > 0:
        dados["alvos"] = alvos_limpos
        salvar_alvos_espiao(dados)
        await callback.message.edit_text(f"✅ <b>Limpeza Concluída!</b>\n{removidos} canal(is) com erro foram removidos da escuta.", parse_mode="HTML")
    else:
        await callback.message.edit_text("Nenhum canal com erro foi encontrado para remover.")
    await callback.answer()

@dp.message(F.text == "Voltar às Opções 🔙", StateFilter("*"))
async def voltar_opcoes_espiao(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await menu_grupos_vigiados(message, state)

# 🛠️ Novo Teclado para Janela do Espião
teclado_janela_espiao = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Dia Todo (24h) 🕛")],
        [KeyboardButton(text="Cancelar ❌")]
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
    if EXIBIR_LOGS: logger.info("🔄 Recalculando e agendando fila de postagens de forma DINÂMICA (Variação 50%)...")
    # 1. Limpa agendamentos antigos para evitar duplicidade
    for job in scheduler.get_jobs():
        if job.id.startswith('job_fila_postagem_'):
            job.remove()

    # 2. Busca vídeos pendentes para hoje no SQLite
    agora = datetime.now(fuso_horario)
    hoje_str = agora.strftime("%Y-%m-%d")
    
    try:
        conexao = sqlite3.connect("banco_dados.db")
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()
        cursor.execute("SELECT id_unico FROM fila_postagens WHERE status = 'PENDENTE' AND (data_alvo <= ? OR data_alvo = '2000-01-01') ORDER BY prioridade ASC", (hoje_str,))
        pendentes_hoje = cursor.fetchall()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler fila no agendador: {e}")
        return

    if not pendentes_hoje:
        return

    dados_rotina = ler_config_rotina()
    
    # 3. Determina as fronteiras de expediente (Bom Dia e Boa Noite)
    job_bd = scheduler.get_job('job_rotina_bom_dia_0')
    if job_bd and getattr(job_bd, 'next_run_time', None):
        limite_inicio = job_bd.next_run_time.astimezone(fuso_horario)
    else:
        hora_inicio = dados_rotina.get("bom_dia", {}).get("inicio", 6)
        limite_inicio = agora.replace(hour=hora_inicio, minute=0, second=0, microsecond=0)

    job_bn = scheduler.get_job('job_rotina_boa_noite_0')
    if job_bn and getattr(job_bn, 'next_run_time', None):
        limite_fim = job_bn.next_run_time.astimezone(fuso_horario)
    else:
        hora_fim = dados_rotina.get("boa_noite", {}).get("inicio", 21)
        limite_fim = agora.replace(hour=hora_fim, minute=59, second=59, microsecond=0)

    # 4. Cálculo Dinâmico de Tempo Restante com Variação de 50%
    import random
    from datetime import timedelta
    
    # Cria uma margem para o vídeo não sair imediatamente colado ao "agora" ou ao "Bom dia"
    margem_seguranca = timedelta(minutes=random.randint(15, 30))
    inicio_real = max(agora + margem_seguranca, limite_inicio + margem_seguranca)

    # Se já estivermos além do expediente, cancela o agendamento por hoje
    if inicio_real >= limite_fim:
        if EXIBIR_LOGS: logger.warning("⚠️ O expediente de postagens encerrou por hoje. Vídeos aguardarão na fila para amanhã.")
        return

    minutos_disponiveis = (limite_fim - inicio_real).total_seconds() / 60
    qtd_pendentes = len(pendentes_hoje)
    
    # Divide o tempo restante em "blocos" iguais para cada vídeo pendente
    espacamento_bloco = minutos_disponiveis / qtd_pendentes
    tempo_acumulado = inicio_real

    for item in pendentes_hoje:
        id_unico = item["id_unico"]
        job_id = f"job_fila_postagem_{id_unico}"
        
        # Descobre o meio exato do bloco de tempo deste vídeo
        meio_do_bloco = tempo_acumulado + timedelta(minutes=(espacamento_bloco / 2))
        
        # ✅ A SUA LÓGICA DE 50%: 
        # Se o bloco tem 5 horas, a metade é 2h30. 50% dessa metade é 1h15.
        # O vídeo vai flutuar dinamicamente entre -1h15 e +1h15 a partir do meio!
        variacao_max = int((espacamento_bloco / 2) * 0.50)
        
        # Trava mínima para não dar erro se o bloco for minúsculo (ex: só sobrou 5 minutos do dia)
        variacao_max = max(2, variacao_max) 
        
        # Sorteia a variação dentro do limiar de 50%
        variacao = random.randint(-variacao_max, variacao_max)
        
        horario_final = meio_do_bloco + timedelta(minutes=variacao)

        # Travas finais de segurança
        if horario_final >= limite_fim:
            horario_final = limite_fim - timedelta(minutes=random.randint(2, 8))
        if horario_final <= agora:
            horario_final = agora + timedelta(minutes=random.randint(5, 15))

        scheduler.add_job(
            executar_postagem_fila, 
            'date', 
            run_date=horario_final, 
            args=[id_unico], 
            id=job_id, 
            replace_existing=True
        )
        if EXIBIR_LOGS: logger.info(f"⏳ Postagem {id_unico[:8]} agendada dinamicamente para {horario_final.strftime('%H:%M:%S')}")
        
        # Avança a linha do tempo para o início do bloco do próximo vídeo
        tempo_acumulado += timedelta(minutes=espacamento_bloco)

async def motor_fila_minuto():
    # ✅ NOVO FISCAL HÍBRIDO (Watchdog): Apenas vigia a memória e auto-cura a grade
    agora = datetime.now(fuso_horario)
    hoje_str = agora.strftime("%Y-%m-%d")
    
    dados_pausa = ler_pausa_programada()
    if dados_pausa.get("ativa"): return
    
    dados_rotina = ler_config_rotina()
    ultimo_bd = dados_rotina.get("ultimo_bom_dia", "")
    ultimo_bn = dados_rotina.get("ultimo_boa_noite", "")
    
    if ultimo_bd != hoje_str or ultimo_bn == hoje_str:
        return # Fora do expediente
        
    try:
        conexao = sqlite3.connect("banco_dados.db")
        cursor = conexao.cursor()
        cursor.execute("SELECT COUNT(*) FROM fila_postagens WHERE status = 'PENDENTE' AND (data_alvo <= ? OR data_alvo = '2000-01-01')", (hoje_str,))
        qtd_db = cursor.fetchone()[0]
        conexao.close()
        
        if qtd_db > 0:
            # Verifica quantos vídeos estão realmente na memória do agendador
            qtd_jobs = sum(1 for job in scheduler.get_jobs() if job.id.startswith('job_fila_postagem_'))
            
            # Se o banco tem vídeo, mas a memória está vazia, o sistema falhou (reboot, crash, etc)
            if qtd_jobs == 0:
                if EXIBIR_LOGS: logger.warning("⚠️ O Fiscal detectou vídeos perdidos sem agendamento! Forçando auto-cura da grade...")
                agendar_fila_postagens()
                
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro no Fiscal da Fila: {e}")

async def executar_postagem_fila(item_id):
    if EXIBIR_LOGS: logger.info(f"📤 Iniciando processamento do vídeo {item_id}...")
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
            
        # 🛡️ TRAVA ABSOLUTA ANTI-DUPLICIDADE: Se o vídeo não for mais 'PENDENTE', aborta imediatamente.
        # Isso impede que o Fiscal (Watchdog) ou qualquer atraso de rede gere postagens duplas.
        if item["status"] != 'PENDENTE':
            if EXIBIR_LOGS: logger.warning(f"🛑 Bloqueio ativado: O vídeo já foi processado anteriormente (Status: {item['status']}). Postagem duplicada evitada.")
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
    
    # 🎯 MAPEAMENTO DE DESTINOS
    rotinas_virais = ["promo_principal", "link_grupo_viral", "divulgar_gem_viral", "promo_publico_viral"]
    rotinas_publico = ["link_grupo_publico", "promo_principal_publico", "promo_viral_publico"]
    
    is_viral = tipo in rotinas_virais
    is_publico = tipo in rotinas_publico
    
    chat_destino = GRUPO_ID
    if is_viral:
        chat_destino = GRUPO_VIRAL_ID
    elif is_publico:
        config_sub = ler_submissao_config()
        chat_destino = config_sub.get("grupo_id")
        if not chat_destino or chat_destino == "Não definido":
            if EXIBIR_LOGS: logger.warning(f"🛑 Disparo abortado ({tipo}): Grupo Público ainda não configurado.")
            return

    # 🚀 PAUSAS ABSOLUTAS (Bloqueia sem exceção para forçar)
    if is_viral and dados_rotina.get("pausado_viral", False):
        if EXIBIR_LOGS: logger.info(f"🛑 Disparo abortado ({tipo}): Rotinas do VIRAL estão pausadas.")
        return
    if is_publico and dados_rotina.get("pausado_publico", False):
        if EXIBIR_LOGS: logger.info(f"🛑 Disparo abortado ({tipo}): Rotinas do PÚBLICO estão pausadas.")
        return
    if not is_viral and not is_publico and dados_rotina.get("pausado", False):
        if EXIBIR_LOGS: logger.warning(f"🛑 Disparo abortado ({tipo}): Rotinas do PRINCIPAL estão pausadas.")
        return

    agora_tz = datetime.now(fuso_horario)
    hoje_str = agora_tz.strftime("%Y-%m-%d")
    
    # 🚀 LÓGICA DE TRAVA ABSOLUTA E EXPEDIENTE
    if tipo == "bom_dia" and dados_rotina.get("ultimo_bom_dia") == hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Bloqueio Anti-Acidente: O 'Bom Dia' já foi enviado hoje.")
        return
    if tipo == "boa_noite" and dados_rotina.get("ultimo_boa_noite") == hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Bloqueio Anti-Acidente: O 'Boa Noite' já foi enviado hoje.")
        return
        
    if tipo not in ["bom_dia", "boa_noite"] and not tipo.startswith("campanha_"):
        if not forcar:
            if not is_viral and not is_publico and dados_rotina.get("ultimo_bom_dia") != hoje_str:
                if EXIBIR_LOGS: logger.warning(f"🛑 Disparo abortado ({tipo}): Expediente principal fechado.")
                return
                
            if not is_viral and not is_publico:
                hora_ultimo_bd = dados_rotina.get("hora_ultimo_bom_dia", "")
                if hora_ultimo_bd:
                    hora_bd_obj = datetime.strptime(hora_ultimo_bd, "%H:%M").time()
                    momento_bd = datetime.combine(agora_tz.date(), hora_bd_obj).replace(tzinfo=fuso_horario)
                    minutos_passados = (agora_tz - momento_bd).total_seconds() / 60
                    
                    if minutos_passados < 10:
                        novo_horario = momento_bd + timedelta(minutes=random.randint(12, 25))
                        job_id = f"job_rotina_{tipo}_reagendado_{int(agora_tz.timestamp())}"
                        scheduler.add_job(disparar_mensagem, 'date', run_date=novo_horario, args=[tipo], id=job_id, replace_existing=True)
                        return
                        
            if not is_viral and not is_publico and dados_rotina.get("ultimo_boa_noite") == hoje_str:
                return

    hora_exata_disparo = agora_tz.strftime("%H:%M")
    
    if tipo == "bom_dia":
        dados_rotina["ultimo_bom_dia"] = hoje_str
        dados_rotina["hora_ultimo_bom_dia"] = hora_exata_disparo
    elif tipo == "boa_noite":
        dados_rotina["ultimo_boa_noite"] = hoje_str
        dados_rotina["hora_ultimo_boa_noite"] = hora_exata_disparo
        
    if dados_rotina.get("historico_diario", {}).get("data") != hoje_str:
        dados_rotina["historico_diario"] = {"data": hoje_str, "contagem": {}}
    
    historico_tipo = dados_rotina["historico_diario"]["contagem"].get(tipo, [])
    if isinstance(historico_tipo, int):
        historico_tipo = [] 
        
    historico_tipo.append(hora_exata_disparo)
    dados_rotina["historico_diario"]["contagem"][tipo] = historico_tipo
    salvar_config_rotina(dados_rotina)

    contexto_afiliado = (
        "Você é um assistente de suporte para afiliados da Shopee. "
        "REGRA ABSOLUTA: Sua resposta deve ser curta, direta, "
        "contendo NO MÁXIMO 200 CARACTERES no total. "
        "Entregue APENAS o texto da mensagem, sem introduções e sem aspas."
    )

    # 🧠 PROMPTS DA INTELIGÊNCIA ARTIFICIAL
    if tipo == "bom_dia":
        prompt = f"{contexto_afiliado} Crie uma mensagem de bom dia motivadora avisando que os vídeos de hoje estão prontos. Use emojis."
    elif tipo == "boa_noite":
        prompt = f"{contexto_afiliado} Crie uma mensagem de boa noite. Sugira organizar os links para amanhã. Use emojis."
    elif tipo == "incentivo":
        prompt = f"{contexto_afiliado} Crie uma frase de impacto sobre persistência no tráfego orgânico. Use emojis."
    elif tipo == "link_grupo":
        prompt = f"{contexto_afiliado} Crie um convite pedindo aos membros para chamarem amigos para nosso grupo. Não use links. Use emojis."
    elif tipo == "link_grupo_viral":
        prompt = f"{contexto_afiliado} Peça aos membros para convidarem amigos para o acervo de virais. Não use links. Use emojis."
    elif tipo.startswith("campanha_"):
        partes = tipo.split("_")
        dias_restantes = int(partes[1])
        data_dupla = partes[2] if len(partes) > 2 else ""
        if dias_restantes == 0: aviso = f"É HOJE o evento de data dupla {data_dupla}!"
        elif dias_restantes == 1: aviso = f"É AMANHÃ o evento de data dupla {data_dupla}!"
        else: aviso = f"Faltam {dias_restantes} dias para o evento de data dupla {data_dupla}."
        prompt = f"{contexto_afiliado} Crie um alerta baseado nisto: '{aviso}'. Transmita urgência. Máximo 100 caracteres."
    elif tipo in ["divulgar_gem", "divulgar_gem_viral"]:
        prompt = "Você atua como assistente. Convide a equipe a usar nosso prompt automatizado de legendas no Gemini PRO. Vá direto ao assunto, sem saudações. Use emojis. Máximo 150 caracteres."
    elif tipo == "promo_viral":
        prompt = "Recomende o canal de um parceiro (fale na terceira pessoa). Diga que ele tem um Acervo Viral incrível estilo copia-e-cola. Seja natural. Máximo 150 caracteres. Sem links."
    elif tipo == "promo_principal":
        prompt = "Recomende um canal parceiro VIP (Acervo Afiliados). Diga que eles liberam conteúdos premium e editados a dedo. Seja humano. Máximo 150 caracteres. Sem links."
    
    ## ✅ NOVOS PROMPTS DA EXPANSÃO DO PÚBLICO
    elif tipo in ["promo_publico", "promo_publico_viral"]:
        prompt = "Recomende nosso Grupo Público. Explique que é um espaço aberto onde todos os afiliados podem postar seus vídeos com links para divulgação. Destaque que é uma comunidade de ajuda mútua, garantindo que sempre tenham vídeos disponíveis para todos usarem. Seja empolgante, máximo 200 caracteres, use emojis, sem links."
    elif tipo == "link_grupo_publico":
        prompt = "Atue como administrador do grupo público. Peça aos membros para convidarem mais amigos para a nossa comunidade aberta. Lembre-os que aqui todos os afiliados se ajudam postando vídeos e links, garantindo material infinito para todos divulgarem. Seja direto, máximo 200 caracteres, use emojis, sem links."
    elif tipo == "promo_principal_publico":
        prompt = "Atue como moderador do grupo público. Recomende a galera a entrar no nosso Canal VIP Oficial (Acervo Afiliados), onde postamos vídeos premium mastigados. Máximo 150 caracteres, use emojis, sem links."
    elif tipo == "promo_viral_publico":
        prompt = "Atue como moderador do grupo público. Recomende nosso Acervo de Vídeos Virais para a galera copiar e colar as tendências do momento. Máximo 150 caracteres, use emojis, sem links."

    texto = await gerar_mensagem_gemini(prompt)
    
    if EXIBIR_LOGS: logger.info(f"🚀 Preparando rotina ({tipo}) para o chat {chat_destino}.")
    
    # ✅ NOVO: Lógica de Multi-Tópicos (Multi-Threading)
    destinos = []
    if is_publico:
        config_sub = ler_submissao_config()
        topicos_rotina = config_sub.get("topicos_rotina", [])
        if topicos_rotina:
            # Transforma os IDs em inteiros e inclui os tópicos de escuta/vitrine se necessário
            for t in topicos_rotina:
                try: destinos.append(int(t))
                except: pass
        else:
            destinos.append(None)
    else:
        destinos.append(None)

    # ✅ Segurança: se a lista ficou vazia (ex: todos os IDs inválidos),
    # cai para o Geral em vez de não enviar nada.
    if not destinos:
        destinos.append(None)

    for thread_id in destinos:
        try:
            # ✅ CORREÇÃO: Converte o ID rigorosamente para número inteiro.
            # O tópico 1 é o "Geral" do fórum e a Bot API do Telegram REJEITA
            # message_thread_id=1 ("message thread not found"). Para postar no
            # Geral é obrigatório OMITIR o parâmetro, ou seja, enviar None.
            thread_param = int(thread_id) if thread_id is not None else None
            if thread_param == 1:
                thread_param = None
            
            if EXIBIR_LOGS: logger.info(f"📤 Disparando {tipo} para Thread: {thread_param if thread_param else 'Geral'}")
            msg_enviada = await bot.send_message(chat_destino, texto, message_thread_id=thread_param)
            registrar_lixeira(msg_enviada.message_id, chat_destino)
            
            await asyncio.sleep(1) # Pausa de respiro para anexos
            
            # 🔗 ANEXADORES DE LINKS ISOLADOS
            if tipo == "link_grupo":
                msg_link = await bot.send_message(chat_destino, f"👇 <b>Link de Convite:</b>\n{LINK_GRUPO}", parse_mode="HTML", message_thread_id=thread_param)
                registrar_lixeira(msg_link.message_id, chat_destino)
            elif tipo == "link_grupo_viral":
                msg_link = await bot.send_message(chat_destino, f"👇 <b>Link de Convite:</b>\n{LINK_GRUPO_VIRAL}", parse_mode="HTML", message_thread_id=thread_param)
                registrar_lixeira(msg_link.message_id, chat_destino)
            elif tipo in ["divulgar_gem", "divulgar_gem_viral"]:
                msg_gem = await bot.send_message(chat_destino, "👇 <b>Acesse o Prompt Automatizado:</b>\nhttps://gemini.google.com/gem/1HtJMuknyMZ76utOu-i6c_xvc3vmQx7bT?usp=sharing", parse_mode="HTML", message_thread_id=thread_param)
                registrar_lixeira(msg_gem.message_id, chat_destino)
            elif tipo == "promo_viral" or tipo == "promo_viral_publico":
                msg_viral = await bot.send_message(chat_destino, f"👇 <b>Acesse o Acervo Viral:</b>\n{LINK_GRUPO_VIRAL}", parse_mode="HTML", message_thread_id=thread_param)
                registrar_lixeira(msg_viral.message_id, chat_destino)
            elif tipo == "promo_principal" or tipo == "promo_principal_publico":
                msg_princ = await bot.send_message(chat_destino, f"👇 <b>Acesse o Acervo Afiliados:</b>\n{LINK_GRUPO}", parse_mode="HTML", message_thread_id=thread_param)
                registrar_lixeira(msg_princ.message_id, chat_destino)
            elif tipo in ["promo_publico", "promo_publico_viral", "link_grupo_publico"]:
                msg_pub = await bot.send_message(chat_destino, f"🔥 <b>Venha participar do nosso Grupo de Ofertas:</b>\n{LINK_GRUPO_PUBLICO}", parse_mode="HTML", message_thread_id=thread_param) 
                registrar_lixeira(msg_pub.message_id, chat_destino)
                
        except Exception as e:
            if "message thread not found" in str(e).lower() or "wrong_id" in str(e).lower():
                if EXIBIR_LOGS: logger.error(f"❌ O tópico {thread_id} não existe mais no grupo ou o ID '{thread_id}' é inválido.")
            else:
                if EXIBIR_LOGS: logger.error(f"❌ Erro ao enviar rotina {tipo} para thread {thread_id}: {e}")
            
        await asyncio.sleep(4) # ✅ CORREÇÃO: Pausa LONGA (4 seg) para não tomar punição de flood do Telegram entre um tópico e outro!

def ler_config_rotina():
    if EXIBIR_LOGS: logger.info("🚀 Iniciando leitura e validação das configurações de rotina...")
    padrao = {
        # Rotinas do Canal Principal
        "bom_dia": {"inicio": 6, "fim": 9, "frequencia": 1},
        "incentivo": {"inicio": 10, "fim": 20, "frequencia": 2},
        "boa_noite": {"inicio": 21, "fim": 23, "frequencia": 1},
        "link_grupo": {"inicio": 9, "fim": 21, "frequencia": 3},
        "divulgar_gem": {"inicio": 8, "fim": 22, "frequencia": 1},
        "promo_viral": {"inicio": 10, "fim": 20, "frequencia": 1},
        "promo_publico": {"inicio": 10, "fim": 20, "frequencia": 1},

        # Rotinas do Canal Viral
        "promo_principal": {"inicio": 10, "fim": 20, "frequencia": 1},
        "divulgar_gem_viral": {"inicio": 8, "fim": 22, "frequencia": 1},
        "link_grupo_viral": {"inicio": 9, "fim": 21, "frequencia": 2},
        "promo_publico_viral": {"inicio": 10, "fim": 20, "frequencia": 1},

        # Rotinas do Grupo Público
        "link_grupo_publico": {"inicio": 9, "fim": 21, "frequencia": 2},
        "promo_principal_publico": {"inicio": 10, "fim": 20, "frequencia": 1},
        "promo_viral_publico": {"inicio": 10, "fim": 20, "frequencia": 1},

        "pausado": False,
        "pausado_viral": False,
        "pausado_publico": False,
        "historico_diario": {"data": "", "contagem": {}}
    }
    
    dados = ler_config_bd("config_rotina", padrao, arquivo_legado="config_rotina.json")
    
    houve_alteracao = False
    for chave, valor in padrao.items():
        if chave not in dados:
            dados[chave] = valor
            houve_alteracao = True
            
    if houve_alteracao:
        salvar_config_bd("config_rotina", dados)
        if EXIBIR_LOGS: logger.info("✅ Sucesso: Novas chaves de rotina injetadas e salvas no banco.")
        
    return dados

def salvar_config_rotina(dados):
    salvar_config_bd("config_rotina", dados)

def agendar_tarefas_diarias(escopo="todos"):
    if EXIBIR_LOGS: logger.info(f"🔄 Sorteando horários de rotina (Escopo: {escopo.upper()})...")
    
    agora_faxina = datetime.now(fuso_horario)
    hoje_faxina_str = agora_faxina.strftime("%Y-%m-%d")
    
    if escopo == "todos":
        # --- Limpeza de Madrugada no SQLite ---
        try:
            conexao = sqlite3.connect("banco_dados.db")
            cursor = conexao.cursor()
            cursor.execute("SELECT caminho_video FROM fila_postagens WHERE status IN ('CONCLUIDO', 'ERRO') AND data_postagem != ?", (hoje_faxina_str,))
            para_apagar = cursor.fetchall()
            for item in para_apagar:
                cam = item[0]
                if cam and os.path.exists(cam):
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
    
    rotinas_virais_lista = ["promo_principal", "link_grupo_viral", "divulgar_gem_viral"]

    # Remove os jobs antigos respeitando estritamente o ESCOPO solicitado
    for job in scheduler.get_jobs():
        if job.id.startswith('job_rotina_') or job.id.startswith('job_campanha_'):
            is_viral = any(rv in job.id for rv in rotinas_virais_lista)
            if escopo == "principal" and is_viral:
                continue # Pula os virais, não apaga
            if escopo == "viral" and not is_viral:
                continue # Pula os principais, não apaga
                
            job.remove()
            if EXIBIR_LOGS: logger.info(f"🧹 Agendamento antigo apagado da memória: {job.id}")

    dados_rotina = ler_config_rotina()
    agora = datetime.now(fuso_horario)
    hoje_str = agora.strftime("%Y-%m-%d")
    
    # 1. ABERTURA E FECHAMENTO RÍGIDOS (Apenas se o escopo permitir)
    if escopo in ["todos", "principal"]:
        for tipo in ["bom_dia", "boa_noite"]:
            if tipo not in dados_rotina or type(dados_rotina[tipo]) is not dict: continue
            ultimo_disparo = dados_rotina.get(f"ultimo_{tipo}", "")
            if ultimo_disparo == hoje_str: continue
            
            config = dados_rotina[tipo]
            inicio = config.get("inicio", 6 if tipo == "bom_dia" else 21)
            fim = config.get("fim", 9 if tipo == "bom_dia" else 23)
            limite_superior = fim - 1 if fim > inicio else fim
            
            minuto_absoluto = random.randint(inicio * 60, limite_superior * 60 + 59)
            hora_sorteada, min_sorteado = divmod(minuto_absoluto, 60)
            horario_candidato = agora.replace(hour=hora_sorteada, minute=min_sorteado, second=0, microsecond=0)
            
            if horario_candidato <= agora:
                horario_candidato = agora + timedelta(minutes=5)
                hora_sorteada, min_sorteado = horario_candidato.hour, horario_candidato.minute
                
            scheduler.add_job(disparar_mensagem, 'cron', hour=hora_sorteada, minute=min_sorteado, timezone=FUSO_STR, args=[tipo], id=f"job_rotina_{tipo}_0", replace_existing=True)

        # 2. DISTRIBUIÇÃO DOS VÍDEOS (Fila do Canal Principal)
        agendar_fila_postagens()
    
    # 3. MAPEAMENTO DAS LACUNAS (Sempre roda para achar as fronteiras de limite)
    eventos_fixos = []
    for job in scheduler.get_jobs():
        if job.id.startswith('job_rotina_bom_dia') or job.id.startswith('job_rotina_boa_noite') or job.id.startswith('job_fila_postagem_'):
            if getattr(job, 'next_run_time', None):
                tempo_evento = job.next_run_time.astimezone(fuso_horario)
                if tempo_evento.date() == agora.date():
                    eventos_fixos.append(tempo_evento)
                    
    ultimo_bd = dados_rotina.get("ultimo_bom_dia", "")
    job_bd = scheduler.get_job('job_rotina_bom_dia_0')
    if ultimo_bd == hoje_str: fronteira_inicial = agora
    elif job_bd and getattr(job_bd, 'next_run_time', None): fronteira_inicial = job_bd.next_run_time.astimezone(fuso_horario)
    else: fronteira_inicial = max(agora, agora.replace(hour=dados_rotina.get("bom_dia", {}).get("inicio", 6), minute=0, second=0, microsecond=0))
    eventos_fixos.append(fronteira_inicial)
    
    ultimo_bn = dados_rotina.get("ultimo_boa_noite", "")
    job_bn = scheduler.get_job('job_rotina_boa_noite_0')
    if ultimo_bn == hoje_str: fronteira_final = agora
    elif job_bn and getattr(job_bn, 'next_run_time', None): fronteira_final = job_bn.next_run_time.astimezone(fuso_horario)
    else: fronteira_final = agora.replace(hour=max(0, dados_rotina.get("boa_noite", {}).get("fim", 23) - 1), minute=59, second=59, microsecond=0)
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

    # PREPARAÇÃO DINÂMICA
    tipos_restantes = [t for t in dados_rotina.keys() if t not in ["bom_dia", "boa_noite", "pausado", "pausado_viral", "ultimo_bom_dia", "ultimo_boa_noite", "historico_diario"]]
    rotinas_principais = [t for t in tipos_restantes if t not in rotinas_virais_lista]
    rotinas_virais = [t for t in tipos_restantes if t in rotinas_virais_lista]
    
    hoje_historico = agora.strftime("%Y-%m-%d")
    historico = dados_rotina.get("historico_diario", {})
    contagem_hoje = historico.get("contagem", {}) if historico.get("data") == hoje_historico else {}
    def obter_qtd_disparos(tipo_rotina):
        registro = contagem_hoje.get(tipo_rotina, [])
        return len(registro) if isinstance(registro, list) else registro

    if escopo in ["todos", "principal"]:
        # 4.1 AGENDAMENTO DA GRADE PRINCIPAL
        grupos_tarefas = {}
        for tipo in rotinas_principais:
            config = dados_rotina[tipo]
            if type(config) is dict:
                frequencia_total = config.get("frequencia", 1)
                disparos_ja_feitos = obter_qtd_disparos(tipo)
                frequencia_restante = frequencia_total - disparos_ja_feitos
                if frequencia_restante > 0:
                    grupos_tarefas[tipo] = [(tipo, i + disparos_ja_feitos) for i in range(frequencia_restante)]
                    
        tarefas_para_distribuir = []
        chaves_grupos = list(grupos_tarefas.keys())
        while chaves_grupos:
            random.shuffle(chaves_grupos)
            chaves_remover = []
            for chave in chaves_grupos:
                if grupos_tarefas[chave]: tarefas_para_distribuir.append(grupos_tarefas[chave].pop(0))
                if not grupos_tarefas[chave]: chaves_remover.append(chave)
            for chave in chaves_remover: chaves_grupos.remove(chave)
                
        ultimo_tipo_agendado = None
        for tipo, indice in tarefas_para_distribuir:
            duracao_min_gap = 60 if tipo == ultimo_tipo_agendado else 20
            horario_ideal = encontrar_maior_lacuna_e_inserir(duracao_minima=duracao_min_gap)
            if horario_ideal:
                scheduler.add_job(disparar_mensagem, 'date', run_date=horario_ideal, args=[tipo], id=f"job_rotina_{tipo}_{indice}", replace_existing=True)
                ultimo_tipo_agendado = tipo
            else:
                minutos_offset = random.randint(30, 90) if tipo == ultimo_tipo_agendado else random.randint(15, 60)
                horario_fallback = agora + timedelta(minutes=minutos_offset)
                if horario_fallback <= fronteira_inicial: horario_fallback = fronteira_inicial + timedelta(minutes=random.randint(15, 45))
                if horario_fallback >= fronteira_final:
                    horario_fallback = fronteira_final - timedelta(minutes=random.randint(5, 30))
                    if horario_fallback <= agora: horario_fallback = agora + timedelta(minutes=2)
                scheduler.add_job(disparar_mensagem, 'date', run_date=horario_fallback, args=[tipo], id=f"job_rotina_{tipo}_{indice}", replace_existing=True)
                ultimo_tipo_agendado = tipo

        # 5. AGENDAMENTO DAS CAMPANHAS ESPECIAIS
        for i in range(4):
            data_futura = agora + timedelta(days=i)
            if data_futura.day == data_futura.month:
                tipo_alerta = f"campanha_{i}_{data_futura.day:02d}.{data_futura.month:02d}"
                turnos_pendentes = ["manha", "tarde", "noite"][obter_qtd_disparos(tipo_alerta):]
                for p in turnos_pendentes:
                    horario_campanha = encontrar_maior_lacuna_e_inserir(duracao_minima=10)
                    if not horario_campanha:
                        if p == "manha": horario_campanha = agora.replace(hour=random.randint(8,11), minute=random.randint(0,59))
                        elif p == "tarde": horario_campanha = agora.replace(hour=random.randint(14,17), minute=random.randint(0,59))
                        else: horario_campanha = agora.replace(hour=random.randint(18,21), minute=random.randint(0,59))
                    if horario_campanha <= agora: horario_campanha = agora + timedelta(minutes=random.randint(3, 10))
                    scheduler.add_job(disparar_mensagem, 'date', run_date=horario_campanha, args=[tipo_alerta], id=f'job_campanha_{p}', replace_existing=True)
                break

    if escopo in ["todos", "viral"]:
        # 4.5. AGENDAMENTO PARALELO PARA O CANAL VIRAL
        grupos_virais = {}
        for tipo in rotinas_virais:
            config = dados_rotina[tipo]
            if type(config) is dict:
                frequencia_total = config.get("frequencia", 1)
                disparos_ja_feitos = obter_qtd_disparos(tipo)
                frequencia_restante = frequencia_total - disparos_ja_feitos
                if frequencia_restante > 0:
                    grupos_virais[tipo] = [(tipo, i + disparos_ja_feitos, config) for i in range(frequencia_restante)]
                    
        tarefas_virais = []
        chaves_virais = list(grupos_virais.keys())
        while chaves_virais:
            random.shuffle(chaves_virais)
            chaves_remover = []
            for chave in chaves_virais:
                if grupos_virais[chave]: tarefas_virais.append(grupos_virais[chave].pop(0))
                if not grupos_virais[chave]: chaves_remover.append(chave)
            for chave in chaves_remover: chaves_virais.remove(chave)
                
        ultimo_tipo_viral = None
        for tipo, indice, config in tarefas_virais:
            minuto_absoluto = random.randint(config.get("inicio", 8) * 60, config.get("fim", 22) * 60 + 59)
            hora_sorteada, min_sorteado = divmod(minuto_absoluto, 60)
            horario_candidato = agora.replace(hour=hora_sorteada, minute=min_sorteado, second=0, microsecond=0)
            
            if tipo == ultimo_tipo_viral: horario_candidato += timedelta(minutes=random.randint(60, 120))
            if horario_candidato <= fronteira_inicial: horario_candidato = fronteira_inicial + timedelta(minutes=random.randint(5, 60))
            if horario_candidato >= fronteira_final: horario_candidato = fronteira_final - timedelta(minutes=random.randint(5, 60))
            if horario_candidato <= agora: horario_candidato = agora + timedelta(minutes=random.randint(2, 10))
                
            conflito_geral = False
            for job_existente in scheduler.get_jobs():
                if getattr(job_existente, 'next_run_time', None) and any(rv in job_existente.id for rv in rotinas_virais_lista):
                    if abs((horario_candidato - job_existente.next_run_time.astimezone(fuso_horario)).total_seconds()) < 120:
                        conflito_geral = True
                        break
            if conflito_geral: horario_candidato += timedelta(minutes=random.randint(3, 8))
                
            scheduler.add_job(disparar_mensagem, 'date', run_date=horario_candidato, args=[tipo], id=f"job_rotina_{tipo}_{indice}", replace_existing=True)
            ultimo_tipo_viral = tipo

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

class BloqueioAdminMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any]
    ) -> Any:
        usuario = getattr(event, "from_user", None)
        
        # Identifica se é uma mensagem de texto ou um clique num botão (CallbackQuery)
        is_callback = hasattr(event, "data")
        mensagem_base = event.message if is_callback else event
        
        chat = getattr(mensagem_base, "chat", None)
        texto = getattr(event, "text", getattr(event, "data", ""))
        
        # 1. VIA VERDE: Verifica se a mensagem está no grupo e tópico de submissão
        is_submissao = False
        if chat:
            try:
                config_sub = ler_submissao_config()
                if config_sub and config_sub.get("ativo"):
                    grupo_alvo = config_sub.get("grupo_id")
                    topico_alvo = config_sub.get("topico_envio")
                    
                    thread_id = getattr(mensagem_base, "message_thread_id", None)
                    
                    # Valida se está exatamente no grupo e no tópico configurado
                    if str(chat.id) == str(grupo_alvo) and str(thread_id) == str(topico_alvo):
                        is_submissao = True
                        if is_callback and EXIBIR_LOGS: logger.info("🟢 [Via Verde] Clique de botão autorizado no painel de submissão.")
            except Exception:
                pass

        # 2. Bloqueia quem não for ADMIN, EXCETO se estiver na Via Verde
        if usuario and getattr(usuario, "id", None) != ADMIN_ID:
            if not is_submissao:
                return 
                
        # 3. Bloqueia o próprio ADMIN se usar o bot em grupo (evita expor botões)
        if usuario and getattr(usuario, "id", None) == ADMIN_ID:
            if chat and chat.type != "private" and texto != "/limpar_teclado" and not is_submissao:
                if getattr(event, "text", None) and EXIBIR_LOGS: logger.warning("🛡️ [Segurança Global] Comando bloqueado no grupo para evitar exposição visual.")
                return 

        return await handler(event, data)

# Acopla os interceptadores de segurança e inatividade ao núcleo do robô para vigiar todas as mensagens
dp.message.middleware(BloqueioAdminMiddleware())
dp.callback_query.middleware(BloqueioAdminMiddleware())
dp.message.middleware(InatividadeMiddleware())

# ==========================================
# PAINEL DO GRUPO PÚBLICO & MOTOR REPOSTADOR
# ==========================================

@dp.message(F.text == "Grupo Público 📬", StateFilter("*"))
async def painel_submissoes(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    
    if EXIBIR_LOGS: logger.info("👥 Acessando Painel do Grupo Público e Repostador.")
    config = ler_submissao_config()
    status = "🟢 ATIVADO" if config.get("ativo") else "🔴 DESATIVADO"
    texto_botao_moderador = "Desativar Robô Moderador 🛑" if config.get("ativo") else "Ativar Robô Moderador ⚙️"
    
    grupo_id = config.get("grupo_id")
    topico_escuta = config.get("topico_envio")
    topico_vitrine = config.get("topico_destino")

    cache_nomes = ler_cache_nomes_grupos()

    # Extrai o ID do grupo para montar as chaves compostas dos tópicos
    grupo_id_str = str(grupo_id) if grupo_id else ""

    # --- 1. Tópico de Escuta ---
    topico_escuta_str = str(topico_escuta) if topico_escuta else ""
    chave_escuta = f"{grupo_id_str}_{topico_escuta_str}"
    
    nome_escuta = (cache_nomes.get(chave_escuta)
                   or config.get("nome_topico_envio")
                   or "Tópico de Escuta")
    icone_escuta = "✅" if chave_escuta in cache_nomes else "⏳"
    
    if not topico_escuta_str:
        display_escuta = "    ❌ <i>Não definido</i>"
    else:
        display_escuta = f"    {icone_escuta} {nome_escuta} (<code>{chave_escuta}</code>)"

# --- 2. Tópico de Postagem (Postando) ---
    topico_vitrine_str = str(topico_vitrine) if topico_vitrine else ""
    chave_vitrine = f"{grupo_id_str}_{topico_vitrine_str}"
    
    nome_vitrine = (cache_nomes.get(chave_vitrine)
                    or config.get("nome_topico_destino")
                    or "Tópico de Postagem")
    icone_vitrine = "✅" if chave_vitrine in cache_nomes else "⏳"
    
    if not topico_vitrine_str:
        display_vitrine = "    ❌ <i>Não definido</i>"
    else:
        display_vitrine = f"    {icone_vitrine} {nome_vitrine} (<code>{chave_vitrine}</code>)"

    # --- 3. Tópicos de Rotina ---
    topicos_rotina = config.get("topicos_rotina", [])
    nomes_rotinas_salvos = config.get("nomes_topicos_rotina", {})

    def resolver_nome_topico(numero_topico):
        t_str = str(numero_topico)
        for chave in (f"{grupo_id_str}_{t_str}", f"{grupo_id_str}:{t_str}"):
            if cache_nomes.get(chave):
                return cache_nomes[chave], "✅"

        nome = nomes_rotinas_salvos.get(t_str)
        if nome:
            return nome, "✅"

        if topico_vitrine_str and t_str == topico_vitrine_str:
            return nome_vitrine, icone_vitrine
        if topico_escuta_str and t_str == topico_escuta_str:
            return nome_escuta, icone_escuta

        if t_str == "1":
            return "Geral", "✅"

        return f"Tópico {t_str}", "⏳"

    if topicos_rotina:
        lista_exibicao = []
        for t in topicos_rotina:
            id_completo_topico = f"{grupo_id_str}_{t}"
            nome_t, icone_t = resolver_nome_topico(t)
            lista_exibicao.append(f"    {icone_t} {nome_t} (<code>{id_completo_topico}</code>)")
        display_rotinas = "\n" + "\n".join(lista_exibicao)
    else:
        display_rotinas = "\n    ✅ <i>Chat Geral (Padrão)</i>"

    # --- INFORMAÇÕES DO ROBÔ REPOSTADOR ---
    repost_status = "🔴 PAUSADO" if config.get("repost_pausado") else "🟢 ATIVADO"
    dias = config.get("repost_dias", 15)
    limite = config.get("repost_limite", 6)
    
    # Origem do Repostador
    repost_origem = config.get("repost_origem")
    if repost_origem:
        repost_origem_base = str(repost_origem).split(":")[0].strip()
        nome_repost_origem = cache_nomes.get(repost_origem_base, str(repost_origem_base))
        icone_rep_orig = "✅" if repost_origem_base in cache_nomes else "⏳"
        display_repost_origem = f"    {icone_rep_orig} {nome_repost_origem} (<code>{str(repost_origem).replace(':', '_')}</code>)"
    else:
        config_aut = ler_config_bd("autorais_config", {})
        dest_aut = config_aut.get("destino", "Não definido")
        dest_aut_base = str(dest_aut).split(":")[0].strip()
        nome_aut = cache_nomes.get(dest_aut_base, str(dest_aut_base))
        icone_rep_orig = "✅" if dest_aut_base in cache_nomes else "⏳"
        display_repost_origem = f"    {icone_rep_orig} {nome_aut} (<code>{str(dest_aut).replace(':', '_')}</code>) [Padrão]"

    # Destino do Repostador (Flexível)
    repost_destino = config.get("repost_destino")
    if repost_destino:
        repost_dest_base = str(repost_destino).split(":")[0].strip()
        nome_repost_dest = cache_nomes.get(repost_dest_base, str(repost_dest_base))
        icone_rep_dest = "✅" if repost_dest_base in cache_nomes else "⏳"
        display_repost_destino = f"\n    {icone_rep_dest} {nome_repost_dest} (<code>{str(repost_destino).replace(':', '_')}</code>)"
    else:
        display_repost_destino = f"\n{display_vitrine} [Padrão]"

    # --- STATUS DAS ROTINAS DO PÚBLICO ---
    dados_rotina = ler_config_rotina()
    status_rotinas = "🔴 PAUSADAS" if dados_rotina.get("pausado_publico") else "🟢 ATIVAS"

    texto = (
        "📬 <b>PAINEL DO GRUPO PÚBLICO</b>\n"
        "<i>Os três robôs que atuam no seu Supergrupo.</i>\n\n"

        f"⚙️ <b>ROBÔ MODERADOR</b>  ·  {status}\n"
        "<blockquote>"
        f"📥 <b>Escuta</b>\n{display_escuta}\n"
        f"📤 <b>Publica</b>\n{display_vitrine}"
        "</blockquote>\n"

        f"♻️ <b>ROBÔ REPOSTADOR</b>  ·  {repost_status}\n"
        "<blockquote>"
        f"📥 <b>Escuta</b>\n{display_repost_origem}\n"
        f"📤 <b>Publica</b>{display_repost_destino}\n"
        f"⏳ Oculto por <b>{dias} dias</b>  ·  📦 <b>{limite} vídeos/dia</b>"
        "</blockquote>\n"

        f"⏰ <b>ROTINAS DO GRUPO</b>  ·  {status_rotinas}\n"
        "<blockquote>"
        f"📢 <b>Publicando nos alvos</b>{display_rotinas}"
        "</blockquote>\n"

        "Escolha a ação desejada:"
    )
    
    teclado_pub = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Configurações do Robô Moderador ⚙️")],
            [KeyboardButton(text="Configurações do Robô Repostador ♻️")],
            [KeyboardButton(text="Configurações do Robô de Rotina do Grupo Público ⏰")],
            [KeyboardButton(text="Voltar aos Canais 🔙")]
        ], resize_keyboard=True, is_persistent=True
    )
    await message.answer(texto, reply_markup=teclado_pub, parse_mode="HTML")
    await state.set_state(SubmissaoAdminFluxo.menu_principal)

@dp.message(F.text == "Voltar ao Painel Público 🔙", StateFilter("*"))
async def voltar_painel_publico_repost(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await painel_submissoes(message, state)

@dp.message(SubmissaoAdminFluxo.menu_principal, F.text == "Configurações do Robô Moderador ⚙️")
async def submenu_robo_moderador(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("⚙️ Acessando submenu de Configurações do Robô Moderador...")

    config = ler_submissao_config()
    status = "🟢 ATIVADO" if config.get("ativo") else "🔴 PAUSADO"
    texto_botao_moderador = "Pausar Robô Moderador ⏸️" if config.get("ativo") else "Retomar Robô Moderador ▶️"

    teclado_mod = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Definir Tópicos de Moderação 💬")],
            [KeyboardButton(text=texto_botao_moderador)],
            [KeyboardButton(text="Voltar ao Painel Público 🔙")]
        ], resize_keyboard=True, is_persistent=True
    )

    texto = (
        "⚙️ <b>Configurações do Robô Moderador</b>\n\n"
        f"📊 <b>Status Atual:</b> {status}\n\n"
        "Aqui você liga ou desliga a moderação automática de vídeos e define "
        "os Tópicos que o robô deve escutar e usar para publicar.\n\n"
        "Escolha a ação desejada:"
    )

    await message.answer(texto, reply_markup=teclado_mod, parse_mode="HTML")
    await state.set_state(SubmissaoAdminFluxo.menu_principal)

@dp.message(SubmissaoAdminFluxo.menu_principal, F.text == "Configurações do Robô Repostador ♻️")
async def submenu_regras_repost_publico(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("♻️ Acessando submenu do Robô Repostador do Grupo Público...")

    config = ler_submissao_config()
    status = "🔴 PAUSADO" if config.get("repost_pausado") else "🟢 ATIVADO"
    texto_repostagem = "Retomar Repostagem ▶️" if config.get("repost_pausado") else "Pausar Repostagem ⏸️"

    teclado = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Editar Escutando (Público) 📥"), KeyboardButton(text="Editar Postando (Público) 📤")],
            [KeyboardButton(text="Editar Dias (Público) ⏳"), KeyboardButton(text="Editar Limite (Público) 📦")],
            [KeyboardButton(text=texto_repostagem)],
            [KeyboardButton(text="Voltar ao Painel Público 🔙")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

    texto = (
        "♻️ <b>Configurações do Robô Repostador</b>\n\n"
        f"📊 <b>Status Atual:</b> {status}\n"
        f"⏳ Oculto por: <b>{config.get('repost_dias', 15)} dias</b>\n"
        f"📦 Cota Diária: <b>{config.get('repost_limite', 6)} vídeos/dia</b>\n\n"
        "Aqui você define de onde os vídeos são puxados, para onde vão, as regras de tempo "
        "e o cota diária — além de pausar ou retomar o robô.\n\n"
        "Escolha a ação desejada:"
    )
    await message.answer(texto, reply_markup=teclado, parse_mode="HTML")
    await state.set_state(SubmissaoAdminFluxo.menu_principal)

# ✅ NOVO: Handlers para Editar o Destino do Repost Público
@dp.message(F.text == "Editar Postando (Público) 📤", StateFilter("*"))
async def pedir_destino_repost_publico(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer(
        "Envie o <b>ID Numérico, @username ou Link do Telegram Web</b> do canal/tópico de DESTINO para onde o robô vai enviar as repostagens:\n"
        "<i>(Se você não definir, ele continuará postando no Tópico de Postagem por padrão)</i>",
        parse_mode="HTML", 
        reply_markup=teclado_cancelar
    )
    await state.set_state(SubmissaoAdminFluxo.aguardando_repost_destino)

@dp.message(SubmissaoAdminFluxo.aguardando_repost_destino)
async def salvar_destino_repost_publico(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await message.answer("Operação cancelada.")
        await submenu_regras_repost_publico(message, state)
        return
        
    novo_valor = message.text.strip()
    msg_status = await message.answer("⏳ <b>Validando canal de destino...</b>", parse_mode="HTML")
    
    sucesso, id_final, nome_chat = await validar_e_formatar_alvo(bot, novo_valor)
    await msg_status.delete()

    if sucesso:
        await message.answer(f"✅ Destino validado e encontrado: <b>{nome_chat}</b>", parse_mode="HTML")
        salvar_nome_grupo(str(id_final).split(":")[0], nome_chat)
    else:
        import re
        id_final = novo_valor
        if "t.me/c/" in novo_valor:
            so_num = re.search(r't\.me/c/(\d+)', novo_valor)
            if so_num: id_final = f"-100{so_num.group(1)}"
        elif "web.telegram.org" in novo_valor:
             so_num = re.search(r'-(\d+)', novo_valor)
             if so_num: id_final = f"-100{so_num.group(1)}"
        await message.answer("⚠️ <b>Aviso:</b> O bot não conseguiu encontrar este canal na base de dados. O ID será salvo mesmo assim.", parse_mode="HTML")

    config = ler_submissao_config()
    config["repost_destino"] = id_final
    salvar_submissao_config(config)
    
    await message.answer(f"✅ <b>Destino do Repost atualizado com sucesso!</b>\nOs vídeos serão postados em: <code>{id_final}</code>", parse_mode="HTML")
    await submenu_regras_repost_publico(message, state)

# ✅ NOVO: Handlers para Editar a Origem do Repost Público
@dp.message(F.text == "Editar Escutando (Público) 📥", StateFilter("*"))
async def pedir_origem_repost_publico(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer(
        "Envie o <b>ID Numérico, @username ou Link do Telegram Web</b> do canal de ORIGEM de onde o robô vai puxar os vídeos para postar no Grupo Público:\n"
        "<i>(Se você não definir, ele continuará pegando do destino dos Vídeos Autorais)</i>", 
        parse_mode="HTML", 
        reply_markup=teclado_cancelar
    )
    await state.set_state(SubmissaoAdminFluxo.aguardando_repost_origem)

@dp.message(SubmissaoAdminFluxo.aguardando_repost_origem)
async def salvar_origem_repost_publico(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await message.answer("Operação cancelada.")
        await submenu_regras_repost_publico(message, state)
        return
        
    novo_valor = message.text.strip()
    msg_status = await message.answer("⏳ <b>Validando canal de origem...</b>", parse_mode="HTML")
    
    sucesso, id_final, nome_chat = await validar_e_formatar_alvo(bot, novo_valor)
    await msg_status.delete()

    if sucesso:
        await message.answer(f"✅ Origem validada e encontrada: <b>{nome_chat}</b>", parse_mode="HTML")
        salvar_nome_grupo(str(id_final), nome_chat)
    else:
        import re
        id_final = novo_valor
        if "t.me/c/" in novo_valor:
            so_num = re.search(r't\.me/c/(\d+)', novo_valor)
            if so_num: id_final = f"-100{so_num.group(1)}"
        elif "web.telegram.org" in novo_valor:
             so_num = re.search(r'-(\d+)', novo_valor)
             if so_num: id_final = f"-100{so_num.group(1)}"
        await message.answer("⚠️ <b>Aviso:</b> O bot não conseguiu encontrar este canal na base de dados. O ID será salvo mesmo assim.", parse_mode="HTML")

    config = ler_submissao_config()
    config["repost_origem"] = id_final
    salvar_submissao_config(config)
    
    await message.answer(f"✅ <b>Origem do Repost atualizada com sucesso!</b>\nOs vídeos serão puxados de: <code>{id_final}</code>", parse_mode="HTML")
    await submenu_regras_repost_publico(message, state)

@dp.message(SubmissaoAdminFluxo.menu_principal, F.text == "Status do Robô ⏸️")
async def submenu_status_robo_publico(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("⏸️ Acessando submenu de Status do Robô do Grupo Público...")
    config = ler_submissao_config()
    texto_repostagem = "Retomar Repostagem ▶️" if config.get("repost_pausado") else "Pausar Repostagem ⏸️"

    teclado_submenu_pausa = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texto_repostagem)],
            [KeyboardButton(text="Voltar ao Painel Público 🔙")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer("⏸️ <b>Controle de Pausa do Repostador</b>\nSelecione a ação:", reply_markup=teclado_submenu_pausa, parse_mode="HTML")
    await state.set_state(SubmissaoAdminFluxo.menu_principal)

@dp.message(SubmissaoAdminFluxo.menu_principal, F.text.in_(["Pausar Repostagem ⏸️", "Retomar Repostagem ▶️"]))
async def pedir_confirmacao_repostagem_publico(message: types.Message, state: FSMContext):
    acao = "pausar" if "Pausar" in message.text else "retomar"
    await state.update_data(acao_repost_pub=acao)

    texto_botao = "Confirmar Pausa ✅" if acao == "pausar" else "Confirmar Retomada ✅"
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texto_botao), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )

    texto = f"⚠️ Tem certeza de que deseja <b>{'PAUSAR' if acao == 'pausar' else 'RETOMAR'}</b> a repostagem automática para o Grupo Público?"
    await message.answer(texto, reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(SubmissaoAdminFluxo.aguardando_confirmacao_pausa_repost)

@dp.message(SubmissaoAdminFluxo.aguardando_confirmacao_pausa_repost)
async def processar_pausa_repostagem_publico(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await message.answer("Ação cancelada.")
        await submenu_regras_repost_publico(message, state) 
        return
    if "Confirmar" not in message.text:
        await message.answer("Por favor, clique no botão para confirmar ou cancelar.")
        return

    config = ler_submissao_config()
    data = await state.get_data()
    acao = data.get("acao_repost_pub")
    
    config["repost_pausado"] = (acao == "pausar")
    salvar_submissao_config(config)

    status = "PAUSADA 🔴" if config["repost_pausado"] else "RETOMADA 🟢"
    if EXIBIR_LOGS: logger.info(f"⚙️ Status da repostagem pública alterado para: {status}")
    await message.answer(f"✅ A repostagem automática para o Público foi <b>{status}</b>.", parse_mode="HTML")
    await submenu_regras_repost_publico(message, state)

@dp.message(F.text == "Editar Dias (Público) ⏳", StateFilter("*"))
async def pedir_dias_repost_publico(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Por quantos <b>dias</b> o vídeo deve ficar arquivado antes de ir para o Grupo Público? (Ex: 15)", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(SubmissaoAdminFluxo.aguardando_repost_dias)

@dp.message(SubmissaoAdminFluxo.aguardando_repost_dias)
async def confirmar_dias_repost_publico(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await message.answer("Operação cancelada.")
        await submenu_regras_repost_publico(message, state)
        return
    if not message.text.isdigit():
        await message.answer("⚠️ Envie apenas números inteiros.", reply_markup=teclado_cancelar)
        return
    novo_valor = int(message.text)
    await state.update_data(novo_valor_dias_pub=novo_valor)
    
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer(f"Tem certeza que deseja configurar o atraso para <b>{novo_valor} dias</b>?", parse_mode="HTML", reply_markup=teclado_confirmacao)
    await state.set_state(SubmissaoAdminFluxo.aguardando_confirmacao_repost_dias)

@dp.message(SubmissaoAdminFluxo.aguardando_confirmacao_repost_dias)
async def processar_dias_repost_publico(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await message.answer("Operação cancelada.")
        await submenu_regras_repost_publico(message, state)
        return
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, clique em Aprovar ou Cancelar.")
        return

    data = await state.get_data()
    novo_valor = data.get("novo_valor_dias_pub")
    
    config = ler_submissao_config()
    config["repost_dias"] = novo_valor
    salvar_submissao_config(config)
    
    if EXIBIR_LOGS: logger.info(f"✅ Dias de atraso do repost público atualizados para: {novo_valor}")
    await message.answer(f"✅ <b>Tempo de Atraso Atualizado!</b>\nOs vídeos irão para o Grupo Público após {novo_valor} dias da captura original.", parse_mode="HTML")
    await submenu_regras_repost_publico(message, state)

@dp.message(F.text == "Editar Limite (Público) 📦", StateFilter("*"))
async def pedir_limite_repost_publico(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Qual será o <b>limite máximo</b> de vídeos repostados por dia no Grupo Público? (Ex: 6)", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(SubmissaoAdminFluxo.aguardando_repost_limite)

@dp.message(SubmissaoAdminFluxo.aguardando_repost_limite)
async def confirmar_limite_repost_publico(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await message.answer("Operação cancelada.")
        await submenu_regras_repost_publico(message, state)
        return
    if not message.text.isdigit():
        await message.answer("⚠️ Envie apenas números inteiros.", reply_markup=teclado_cancelar)
        return
        
    novo_valor = int(message.text)
    await state.update_data(novo_valor_limite_pub=novo_valor)
    
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer(f"Tem certeza que deseja definir a cota diária para <b>{novo_valor} vídeos</b>?", parse_mode="HTML", reply_markup=teclado_confirmacao)
    await state.set_state(SubmissaoAdminFluxo.aguardando_confirmacao_repost_limite)

@dp.message(SubmissaoAdminFluxo.aguardando_confirmacao_repost_limite)
async def processar_limite_repost_publico(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await message.answer("Operação cancelada.")
        await submenu_regras_repost_publico(message, state)
        return
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, clique em Aprovar ou Cancelar.")
        return

    data = await state.get_data()
    novo_valor = data.get("novo_valor_limite_pub")
    
    config = ler_submissao_config()
    config["repost_limite"] = novo_valor
    salvar_submissao_config(config)
    
    if EXIBIR_LOGS: logger.info(f"✅ Limite diário do repost público atualizado para: {novo_valor}")
    await message.answer(f"✅ <b>Cota Diária Atualizada!</b>\nO robô enviará no máximo {novo_valor} vídeos por dia ao Grupo Público.", parse_mode="HTML")
    await submenu_regras_repost_publico(message, state)

async def motor_repost_publico_step():
    try:
        config = ler_submissao_config()
        if not config.get("ativo") or config.get("repost_pausado", False):
            return
            
        # ✅ Puxa a flexibilidade de roteamento
        grupo_id_base = config.get("grupo_id")
        topico_destino_base = config.get("topico_destino")
        repost_destino = config.get("repost_destino")
        
        if repost_destino:
            if ":" in str(repost_destino):
                grupo_id = str(repost_destino).split(":")[0]
                topico_destino = int(str(repost_destino).split(":")[1])
            else:
                grupo_id = str(repost_destino)
                topico_destino = None
        else:
            grupo_id = grupo_id_base
            topico_destino = topico_destino_base
            
        if not grupo_id:
            return

        limite_diario = config.get("repost_limite", 6)
        dias_atraso = config.get("repost_dias", 15)
        
        agora = datetime.now(fuso_horario)
        hoje_str = agora.strftime("%Y-%m-%d")
        
        # 🔄 Virada do dia: reseta o banco de dados interno
        if config.get("repost_data_atual") != hoje_str:
            config["repost_data_atual"] = hoje_str
            config["repost_qtd_hoje"] = 0
            salvar_submissao_config(config)
            
        qtd_hoje = config.get("repost_qtd_hoje", 0)
        
        # Expediente Fixo: 10h às 20h
        if agora.hour < 10 or agora.hour >= 20:
            return
            
        if qtd_hoje >= limite_diario:
            return
            
        minutos_expediente = 600
        espacamento = minutos_expediente / limite_diario if limite_diario > 0 else 600
        
        hora_ultimo = config.get("repost_ultimo_horario")
        if hora_ultimo:
            try:
                ultimo_obj = datetime.strptime(hora_ultimo, "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario)
                minutos_passados = (agora - ultimo_obj).total_seconds() / 60
                if minutos_passados < espacamento:
                    return # Catraca de espaçamento ativa
            except: pass
        
        data_corte_str = (agora - timedelta(days=dias_atraso)).strftime("%Y-%m-%d %H:%M:%S")
        
        conexao = sqlite3.connect("banco_dados.db")
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()
        
        # ✅ A fila é construída pelo sorteio do espelhador, na tabela fila_publico.
        # Aqui só publicamos o que já venceu a data-alvo sorteada.
        cursor.execute('''
            SELECT * FROM fila_publico
            WHERE processado = 0
            AND data_alvo IS NOT NULL
            AND data_alvo != ''
            AND data_alvo <= ?
            ORDER BY data_alvo ASC, id_unico ASC LIMIT 1
        ''', (hoje_str,))
        
        video_alvo = cursor.fetchone()
        
        if video_alvo:
            if EXIBIR_LOGS: logger.info("🚀 [Motor Público] Vídeo elegível detetado. A iniciar a transferência de repostagem...")
            file_id = video_alvo["msg_id_destino"]
            id_unico = video_alvo["id_unico"]
            legenda_original = video_alvo["legenda"]
            
            # ✅ NOVO: Tenta usar a origem personalizada. Se não tiver, usa a dos Autorais.
            canal_autorais = config.get("repost_origem")
            if not canal_autorais:
                config_aut = ler_config_bd("autorais_config", {})
                canal_autorais = config_aut.get("destino")
            
            if file_id and canal_autorais:
                import re
                import random
                
                match_link = re.search(r'(?:https?://)?(?:s\.shopee\.com\.br|shope\.ee|br\.shp\.ee|shp\.ee)/[^\s<]+', legenda_original, re.IGNORECASE)
                link_shopee = match_link.group(0) if match_link else "https://shopee.com.br"
                
                match_item = re.search(r'📦\s*Item:\s*([^\n<]+)', legenda_original)
                nome_produto = match_item.group(1).strip() if match_item else "Produto Exclusivo"

                nomes_fakes = ["Rafael", "Membro VIP", "Shopee Afiliado", "Dicas da Comunidade", "Ofertas Top", "Guia de Ofertas"]
                user_mention = random.choice(nomes_fakes)

                legenda_final = (
                    f"👤 Dica enviada por: {user_mention}\n\n"
                    f"<b>{nome_produto}</b>\n\n"
                    f"🔗 <b>Link do Produto:</b>\n{link_shopee}\n\n"
                    f"<i>#Recomendado #Shopee</i>"
                )
                
                try:
                    await bot.copy_message(
                        chat_id=grupo_id,
                        from_chat_id=canal_autorais,
                        message_id=int(file_id),
                        caption=legenda_final,
                        parse_mode="HTML",
                        message_thread_id=int(topico_destino)
                    )
                    if EXIBIR_LOGS: logger.info(f"✅ [Motor Público] Vídeo '{nome_produto}' encaminhado para o Tópico de Postagem do Público com sucesso!")
                    
                    cursor.execute("UPDATE fila_publico SET processado = 1, data_postagem = ?, horario_disparo = ? WHERE id_unico = ?", (agora.strftime("%Y-%m-%d %H:%M:%S"), agora.strftime("%Y-%m-%d %H:%M:%S"), id_unico))
                    conexao.commit()
                    
                    config["repost_qtd_hoje"] = qtd_hoje + 1
                    config["repost_ultimo_horario"] = agora.strftime("%Y-%m-%d %H:%M:%S")
                    salvar_submissao_config(config)
                    
                except Exception as e:
                    if EXIBIR_LOGS: logger.error(f"❌ [Motor Público] Falha ao tentar executar copy_message: {e}")
        
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [Motor Público] Erro estrutural crítico: {e}")

# Inicia o motor autônomo agendado no APScheduler a cada 2 minutos
scheduler.add_job(motor_repost_publico_step, 'interval', minutes=2, id='motor_repost_publico_loop', replace_existing=True)

# ----------------------------------
# NOVO MÓDULO: VÍDEOS AUTORAIS 🎥
# ----------------------------------
def ler_autorais_config():
    padrao = {
        "origem": -1003673555953, 
        "origem_topico": None, 
        "destino": "@videos_autorais", 
        "dias_retorno": 15, 
        "limite_videos": 5,
        "inicio": 10,   # 🕐 Janela de postagem: hora de abertura
        "fim": 20,      # 🕐 Janela de postagem: hora de fechamento
        "pausar_repostagem": False,
        "pausar_robo_completo": False
    }
    return ler_config_bd("autorais_config", padrao, arquivo_legado="autorais_config.json")

def salvar_autorais_config(dados):
    salvar_config_bd("autorais_config", dados)

teclado_menu_autorais = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Editar Origem 📥"), KeyboardButton(text="Editar Destino 📤")],
        [KeyboardButton(text="Regras de Repostagem ♻️"), KeyboardButton(text="Status do Robô ⏸️")],
        [KeyboardButton(text="Voltar aos Canais 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

teclado_submenu_retorno = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Editar Dias ⏳"), KeyboardButton(text="Editar Limite 📦")],
        [KeyboardButton(text="Janela de Horário ⏰")],
        [KeyboardButton(text="Voltar ao Menu Autorais 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

def calcular_dias_restantes_autorais():
    """Busca o vídeo mais antigo na fila de autorais e calcula quantos dias faltam para ele ser postado."""
    try:
        conexao = sqlite3.connect("banco_dados.db")
        cursor = conexao.cursor()
        # Busca a data mais próxima que está agendada
        cursor.execute("SELECT MIN(data_alvo) FROM fila_autorais")
        resultado = cursor.fetchone()
        conexao.close()

        if resultado and resultado[0]:
            data_alvo_str = resultado[0]
            
            # Compara a data do banco com o dia de hoje
            hoje = datetime.now(fuso_horario).date()
            data_alvo = datetime.strptime(data_alvo_str, "%Y-%m-%d").date()

            dias_restantes = (data_alvo - hoje).days
            
            # Só retorna a contagem se ainda faltarem dias (> 0)
            if dias_restantes > 0:
                return dias_restantes
        return None
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao calcular dias para repostagem: {e}")
        return None

@dp.message(F.text == "Vídeos Autorais 🎥", StateFilter("*"))
async def painel_autorais(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    
    if EXIBIR_LOGS: logger.info("🎥 Acessando painel visual do Bot Vídeos Autorais...")
    config = ler_autorais_config()
    
    origem = config.get("origem", "Não definida")
    topico = config.get("origem_topico")

    # ✅ CORREÇÃO: o ID pode ter chegado no formato composto "-100123:1".
    # Separamos aqui para o painel não imprimir ":1:1" e para o cache achar o nome.
    if isinstance(origem, str) and ":" in origem:
        _partes_origem = origem.split(":")
        origem = _partes_origem[0].strip()
        if len(_partes_origem) > 1 and _partes_origem[1].strip().isdigit() and not topico:
            topico = int(_partes_origem[1].strip())

    topico_str = f"_{topico}" if topico else ""
    destino = config.get("destino", "Não definido")
    destino_topico_str = ""
    if isinstance(destino, str) and ":" in destino:
        _partes_destino = destino.split(":")
        destino = _partes_destino[0].strip()
        if len(_partes_destino) > 1 and _partes_destino[1].strip().isdigit():
            destino_topico_str = f"_{_partes_destino[1].strip()}"
    dias_retorno = config.get("dias_retorno", 15)
    limite_videos = config.get("limite_videos", 5)
    janela_inicio = config.get("inicio", 10)
    janela_fim = config.get("fim", 20)
    
    # Verifica os status de pausa
    pausar_repost = config.get("pausar_repostagem", False)
    pausar_robo = config.get("pausar_robo_completo", False)
    
    status_robo = "🔴 Pausado" if pausar_robo else "🟢 Ativo"
    status_repost = "🔴 Pausada" if pausar_repost else "🟢 Ativa"
    
    # ✅ LÓGICA DA CONTAGEM REGRESSIVA
    texto_contagem = ""
    # A contagem só aparece se a repostagem NÃO estiver pausada
    if not pausar_repost:
        dias_restantes = calcular_dias_restantes_autorais()
        if dias_restantes:
            texto_contagem = f"⏳ <i>Faltam {dias_restantes} dias para iniciar a repostagem.</i>\n"

    cache_nomes = ler_cache_nomes_grupos()

    # --- Lógica Avançada Visual da Origem ---
    nome_origem = str(origem)
    icone_origem = "⏳"
    
    if str(origem) != "Não definida":
        if str(origem) in cache_nomes:
            nome_origem = f"{cache_nomes[str(origem)]} (<code>{origem}{topico_str}</code>)"
            icone_origem = "✅"
        else:
            try:
                chat_obj = await bot.get_chat(origem)
                nome = chat_obj.title or chat_obj.full_name
                nome_origem = f"{nome} (<code>{origem}{topico_str}</code>)"
                salvar_nome_grupo(str(origem), nome)
                icone_origem = "✅"
            except Exception:
                nome_encontrado_no_espiao = False
                try:
                    dados_espiao = ler_alvos_espiao()
                    status_alvos = dados_espiao.get("status_alvos", {})
                    for alvo_id, dados_alvo in status_alvos.items():
                            if str(dados_alvo.get("id")) == str(origem) or str(dados_alvo.get("id")).replace("-100", "") == str(origem).replace("-100", ""):
                                nome = dados_alvo.get("nome", "Desconhecido")
                                nome_origem = f"{nome} (<code>{origem}{topico_str}</code>)"
                                salvar_nome_grupo(str(origem), nome)
                                icone_origem = "✅"
                                nome_encontrado_no_espiao = True
                                break
                except Exception: pass

                if not nome_encontrado_no_espiao:
                    nome_origem = f"<code>{origem}{topico_str}</code> - <i>Aguardando leitura do Userbot...</i>"
                    icone_origem = "⏳"
                
    # --- Lógica Visual do Destino ---
    nome_destino = str(destino)
    icone_destino = "⏳"
    if str(destino) != "Não definido":
        if str(destino) in cache_nomes:
            nome_destino = f"{cache_nomes[str(destino)]} (<code>{destino}{destino_topico_str}</code>)"
            icone_destino = "✅"
        else:
            try:
                chat_obj = await bot.get_chat(destino)
                nome = chat_obj.title or chat_obj.full_name
                nome_destino = f"{nome} (<code>{destino}{destino_topico_str}</code>)"
                salvar_nome_grupo(str(destino), nome)
                icone_destino = "✅"
            except Exception:
                nome_destino = f"<code>{destino}{destino_topico_str}</code> - <i>Acesso Negado</i>"
                icone_destino = "❌"
    
    # --- MONTAGEM DO TEXTO ---
    texto = (
        "🎥 <b>Painel do Bot Vídeos Autorais</b>\n\n"
        f"<b>- Status Geral:</b>\n"
        f"    🤖 Robô Completo: <b>{status_robo}</b>\n"
        f"    ♻️ Repostagem: <b>{status_repost}</b>\n\n"
        f"<b>- Origem atual:</b>\n"
        f"    {icone_origem} {nome_origem}\n\n"
        f"<b>- Destino atual:</b>\n"
        f"    {icone_destino} {nome_destino}\n\n"
        f"♻️ <b>Regras de Repostagem:</b>\n"
        f"⏳ Oculto por: <b>{dias_retorno} dias</b>\n"
        f"📦 Cota Diária: <b>{limite_videos} vídeos/dia</b>\n"
        f"⏰ Janela de Postagem: <b>{janela_inicio}h às {janela_fim}h</b>\n"
        f"{texto_contagem}\n"
        "O robô Espelhador Isolado fará a escuta e o envio em tempo real baseando-se estritamente nestes valores.\n\n"
        "Escolha o que deseja alterar:"
    )
    await message.answer(texto, parse_mode="HTML", reply_markup=teclado_menu_autorais)
    await state.set_state(AutoraisFluxo.menu_principal)

# ----------------------------------------------------
# SUBSTITUA OS HANDLERS DOS SUBMENUS POR ESTES:
# ----------------------------------------------------

@dp.message(AutoraisFluxo.menu_principal, F.text == "Regras de Repostagem ♻️")
async def submenu_regras_retorno(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("♻️ <b>Regras de Repostagem</b>\nEscolha o que deseja editar:", reply_markup=teclado_submenu_retorno, parse_mode="HTML")
    # ✅ CORREÇÃO: reancora o estado no menu principal dos Autorais.
    # Sem isto, quando chamada de dentro do cancelar_fluxo_global (que dá
    # state.clear()) ou após Aprovar/Cancelar, o estado fica None e os botões
    # "Editar Dias ⏳" / "Editar Limite 📦" param de responder.
    await state.set_state(AutoraisFluxo.menu_principal)

@dp.message(AutoraisFluxo.menu_principal, F.text == "Status do Robô ⏸️")
async def submenu_status_robo(message: types.Message, state: FSMContext):
    config = ler_autorais_config()
    texto_repostagem = "Retomar Repostagem ▶️" if config.get("pausar_repostagem") else "Pausar Repostagem ⏸️"
    texto_robo = "Retomar Robô Completo ▶️" if config.get("pausar_robo_completo") else "Pausar Robô Completo ⏸️"

    teclado_submenu_pausa = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texto_repostagem)],
            [KeyboardButton(text=texto_robo)],
            [KeyboardButton(text="Voltar ao Menu Autorais 🔙")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer("⏸️ <b>Controle de Pausa</b>\nSelecione o serviço que deseja pausar ou retomar:", reply_markup=teclado_submenu_pausa, parse_mode="HTML")
    # ✅ IMPORTANTE: Volta o estado para o menu principal dos autorais para que os botões funcionem corretamente
    await state.set_state(AutoraisFluxo.menu_principal)

# --- LÓGICA DE CONFIRMAÇÃO DE PAUSA DA REPOSTAGEM ---
@dp.message(AutoraisFluxo.menu_principal, F.text.in_(["Pausar Repostagem ⏸️", "Retomar Repostagem ▶️"]))
async def pedir_confirmacao_repostagem(message: types.Message, state: FSMContext):
    acao = "pausar" if "Pausar" in message.text else "retomar"
    await state.update_data(acao_repost=acao)

    texto_botao = "Confirmar Pausa ✅" if acao == "pausar" else "Confirmar Retomada ✅"
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texto_botao), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )

    texto = f"⚠️ Tem certeza de que deseja <b>{'PAUSAR' if acao == 'pausar' else 'RETOMAR'}</b> a repostagem automática de vídeos antigos?"
    await message.answer(texto, reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(AutoraisFluxo.aguardando_confirmacao_pausa_repost)

@dp.message(AutoraisFluxo.aguardando_confirmacao_pausa_repost)
async def processar_pausa_repostagem(message: types.Message, state: FSMContext):
    # ✅ Lógica para o botão Cancelar
    if message.text == "Cancelar ❌":
        await message.answer("Ação cancelada.")
        await submenu_status_robo(message, state) 
        return

    # ✅ Lógica para quando ele não apertar nem Cancelar e nem Confirmar
    if "Confirmar" not in message.text:
        await message.answer("Por favor, clique no botão para confirmar ou cancelar.")
        return

    config = ler_autorais_config()
    data = await state.get_data()
    acao = data.get("acao_repost")
    
    # Se a ação for "pausar", ele salva como True, senão salva como False
    config["pausar_repostagem"] = (acao == "pausar")
    salvar_autorais_config(config)

    status = "PAUSADA 🔴" if config["pausar_repostagem"] else "RETOMADA 🟢"
    await message.answer(f"✅ A repostagem automática de vídeos antigos foi <b>{status}</b>.", parse_mode="HTML")
    await submenu_status_robo(message, state)

# --- LÓGICA DE CONFIRMAÇÃO DE PAUSA DO ROBÔ COMPLETO ---
@dp.message(AutoraisFluxo.menu_principal, F.text.in_(["Pausar Robô Completo ⏸️", "Retomar Robô Completo ▶️"]))
async def pedir_confirmacao_robo(message: types.Message, state: FSMContext):
    acao = "pausar" if "Pausar" in message.text else "retomar"
    await state.update_data(acao_robo=acao)

    texto_botao = "Confirmar Pausa ✅" if acao == "pausar" else "Confirmar Retomada ✅"
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texto_botao), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )

    texto = f"⚠️ Tem certeza de que deseja <b>{'PAUSAR' if acao == 'pausar' else 'RETOMAR'}</b> o funcionamento geral do robô Espelhador Isolado?"
    await message.answer(texto, reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(AutoraisFluxo.aguardando_confirmacao_pausa_robo)

@dp.message(AutoraisFluxo.aguardando_confirmacao_pausa_robo)
async def processar_pausa_robo(message: types.Message, state: FSMContext):
    # ✅ Lógica para o botão Cancelar
    if message.text == "Cancelar ❌":
        await message.answer("Ação cancelada.")
        await submenu_status_robo(message, state) 
        return

    # ✅ Lógica para quando ele não apertar nem Cancelar e nem Confirmar
    if "Confirmar" not in message.text:
        await message.answer("Por favor, clique no botão para confirmar ou cancelar.")
        return

    config = ler_autorais_config()
    data = await state.get_data()
    acao = data.get("acao_robo")

    # Se a ação for "pausar", ele salva como True, senão salva como False
    config["pausar_robo_completo"] = (acao == "pausar")
    salvar_autorais_config(config)

    status = "PAUSADO 🔴" if config["pausar_robo_completo"] else "RETOMADO 🟢"
    await message.answer(f"✅ O funcionamento geral do robô Espelhador Isolado foi <b>{status}</b>.", parse_mode="HTML")
    await submenu_status_robo(message, state)

# ----------------------------------------------------
# REGRAS DE ORIGEM E DESTINO
# ----------------------------------------------------
@dp.message(F.text == "Voltar ao Menu Autorais 🔙", StateFilter("*"))
async def voltar_menu_autorais(message: types.Message, state: FSMContext):
    await painel_autorais(message, state)

@dp.message(AutoraisFluxo.menu_principal, F.text == "Editar Origem 📥")
async def pedir_origem_autorais(message: types.Message, state: FSMContext):
    if EXIBIR_LOGS: logger.info("📥 Solicitando nova origem para vídeos autorais...")
    await message.answer("Envie o <b>ID Numérico, @username ou Link do Telegram Web</b> do grupo de ORIGEM de onde o bot vai puxar os vídeos (Ex: -100123456789 ou https://web.telegram.org/a/#-100...):", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AutoraisFluxo.aguardando_origem)

@dp.message(AutoraisFluxo.aguardando_origem)
async def pedir_topico_autorais(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await cancelar_fluxo_global(message, state)
        return
        
    novo_valor = message.text.strip()
    msg_status = await message.answer("⏳ <b>Validando grupo de origem...</b>", parse_mode="HTML")
    
    sucesso, id_final, nome_chat = await validar_e_formatar_alvo(bot, novo_valor)
    
    await msg_status.delete()

    if sucesso:
        # ✅ Se o bot não enxerga o grupo, a função devolve o próprio ID no lugar
        # do nome. Nesse caso buscamos o nome real que o Userbot já cacheou.
        id_base_exibicao = str(id_final).split(":")[0].strip()
        if str(nome_chat).strip() == id_base_exibicao:
            cache_nomes = ler_cache_nomes_grupos()
            nome_chat = cache_nomes.get(id_base_exibicao, nome_chat)
        await message.answer(f"✅ Origem validada e encontrada: <b>{nome_chat}</b>", parse_mode="HTML")
        salvar_nome_grupo(id_base_exibicao, nome_chat)
    else:
        import re
        id_final = novo_valor
        if "t.me/c/" in novo_valor:
            so_num = re.search(r't\.me/c/(\d+)', novo_valor)
            if so_num: id_final = f"-100{so_num.group(1)}"
        elif "web.telegram.org" in novo_valor:
             so_num = re.search(r'-(\d+)', novo_valor)
             if so_num: id_final = f"-100{so_num.group(1)}"
             
        await message.answer("⚠️ <b>Aviso de Permissão:</b> O Bot Principal não tem permissão para enxergar este grupo. O ID será salvo, pois a Conta Secundária é quem fará a extração física.", parse_mode="HTML")

    # ✅ NOVO: o link já pode trazer o tópico embutido ("-100123:1" vindo do "_1").
    # Se veio, não faz sentido perguntar de novo - pulamos direto para a confirmação.
    partes_id = str(id_final).split(":")
    origem_base = partes_id[0].strip()
    topico_detectado = int(partes_id[1].strip()) if len(partes_id) > 1 and partes_id[1].strip().isdigit() else None
    
    await state.update_data(nova_origem=origem_base, nome_origem_validado=nome_chat)
    
    if topico_detectado is not None:
        await message.answer(
            f"🔎 <b>Tópico detectado automaticamente pelo link:</b> <code>{topico_detectado}</code>\n"
            "<i>Não precisa digitar nada.</i>",
            parse_mode="HTML"
        )
        await confirmar_origem_autorais(message, state, origem_base, topico_detectado, nome_chat)
        return
    
    await message.answer("Agora, digite o <b>NÚMERO DO TÓPICO (Subcanal)</b> que ele deve monitorar.\n\n<i>Dica: Se os vídeos caem no chat 'Geral', digite <b>1</b>. Se for um canal sem tópicos, digite <b>0</b> para ler tudo.</i>", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AutoraisFluxo.aguardando_topico)

async def confirmar_origem_autorais(message, state, nova_origem, topico_final, nome_novo=None):
    """Monta a tela de aprovação da ORIGEM. Usada tanto pelo caminho automático
    (tópico vindo do link) quanto pelo manual (tópico digitado)."""
    await state.update_data(origem_pendente=nova_origem, topico_pendente=topico_final)
    
    config = ler_autorais_config()
    origem_antiga = str(config.get("origem", "Não definida")).split(":")[0].strip()
    topico_antigo = config.get("origem_topico")
    
    nome_novo = nome_novo or nova_origem
    sufixo_novo = f"_{topico_final}" if topico_final else ""
    sufixo_antigo = f"_{topico_antigo}" if topico_antigo else ""
    texto_topico_novo = f"Tópico {topico_final}" if topico_final else "Todos os tópicos"
    texto_topico_antigo = f"Tópico {topico_antigo}" if topico_antigo else "Todos os tópicos"
    
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    
    texto = (
        "⚠️ <b>Confirme a alteração da ORIGEM</b>\n\n"
        f"<b>De:</b> <code>{origem_antiga}{sufixo_antigo}</code> ({texto_topico_antigo})\n"
        f"<b>Para:</b> {nome_novo}\n"
        f"<code>{nova_origem}{sufixo_novo}</code> ({texto_topico_novo})\n\n"
        "O robô passará a escutar exclusivamente este grupo/tópico. Deseja aprovar?"
    )
    await message.answer(texto, parse_mode="HTML", reply_markup=teclado_confirmacao)
    await state.set_state(AutoraisFluxo.aguardando_confirmacao_origem)

@dp.message(AutoraisFluxo.aguardando_topico)
async def salvar_origem_autorais(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await cancelar_fluxo_global(message, state)
        return
    
    entrada_topico = message.text.strip()
    
    # ✅ Tolerante: se colarem o link ou "ID_1" de novo, extraímos só o tópico
    if not entrada_topico.isdigit():
        import re
        achado = re.search(r'[_:/](\d+)\s*$', entrada_topico)
        if achado:
            entrada_topico = achado.group(1)
        else:
            await message.answer("⚠️ Formato inválido! Envie apenas o número do tópico (Ex: 1 ou 0).", reply_markup=teclado_cancelar)
            return
        
    topico = int(entrada_topico)
    topico_final = topico if topico > 0 else None
    
    data = await state.get_data()
    nova_origem = str(data.get("nova_origem")).split(":")[0].strip()
    
    await confirmar_origem_autorais(message, state, nova_origem, topico_final, data.get("nome_origem_validado"))

@dp.message(AutoraisFluxo.aguardando_confirmacao_origem)
async def processar_origem_autorais(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await message.answer("❌ Operação cancelada. A origem <b>não</b> foi alterada.", parse_mode="HTML")
        await painel_autorais(message, state)
        return
        
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, clique em Aprovar ✅ ou Cancelar ❌.")
        return
    
    data = await state.get_data()
    nova_origem = data.get("origem_pendente")
    topico_final = data.get("topico_pendente")
    
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
    await message.answer("Envie o <b>ID Numérico, @username ou Link do Telegram Web</b> do canal de DESTINO para onde o bot vai enviar os vídeos convertidos (Ex: @meu_canal ou https://web.telegram.org/...):", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AutoraisFluxo.aguardando_destino)

@dp.message(AutoraisFluxo.aguardando_destino)
async def salvar_destino_autorais(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await cancelar_fluxo_global(message, state)
        return
        
    novo_valor = message.text.strip()
    msg_status = await message.answer("⏳ <b>Validando canal de destino...</b>", parse_mode="HTML")
    
    sucesso, id_final, nome_chat = await validar_e_formatar_alvo(bot, novo_valor)

    await msg_status.delete()

    if sucesso:
        # ✅ Mesmo tratamento da origem: usa o nome real do cache se a função
        # tiver devolvido o próprio ID (Modo Trust).
        id_base_exibicao = str(id_final).split(":")[0].strip()
        if str(nome_chat).strip() == id_base_exibicao:
            cache_nomes = ler_cache_nomes_grupos()
            nome_chat = cache_nomes.get(id_base_exibicao, nome_chat)
        await message.answer(f"✅ Destino validado: <b>{nome_chat}</b>", parse_mode="HTML")
        salvar_nome_grupo(id_base_exibicao, nome_chat)
    else:
        import re
        id_final = novo_valor
        if "t.me/c/" in novo_valor:
            so_num = re.search(r't\.me/c/(\d+)', novo_valor)
            if so_num: id_final = f"-100{so_num.group(1)}"
        elif "web.telegram.org" in novo_valor:
             so_num = re.search(r'-(\d+)', novo_valor)
             if so_num: id_final = f"-100{so_num.group(1)}"
             
        await message.answer("⚠️ <b>Aviso:</b> O bot não conseguiu encontrar este destino (verifique se ele é administrador do canal). O ID será salvo mesmo assim.", parse_mode="HTML")

    config = ler_autorais_config()
    destino_antigo = config.get("destino", "Não definido")
    
    # ✅ NOVO: guarda o valor e pede aprovação antes de gravar
    await state.update_data(destino_pendente=id_final, nome_destino_validado=nome_chat)
    
    nome_novo = nome_chat or id_final
    # ✅ Exibição no mesmo formato do link do Telegram Web ("-100123_1")
    id_final_exibicao = str(id_final).replace(":", "_")
    destino_antigo_exibicao = str(destino_antigo).replace(":", "_")
    origem_atual = str(config.get("origem", "")).split(":")[0].strip()
    
    aviso_loop = ""
    if origem_atual and str(id_final).split(":")[0].strip() == origem_atual:
        aviso_loop = (
            "\n\n🚨 <b>ATENÇÃO:</b> este destino é o <b>mesmo grupo da origem</b>. "
            "Isso cria um <b>loop infinito</b> (o robô reposta o que ele mesmo publicou). "
            "Só aprove se souber o que está fazendo."
        )
    
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    
    texto = (
        "⚠️ <b>Confirme a alteração do DESTINO</b>\n\n"
        f"<b>De:</b> <code>{destino_antigo_exibicao}</code>\n"
        f"<b>Para:</b> {nome_novo}\n"
        f"<code>{id_final_exibicao}</code>\n\n"
        "Todos os vídeos convertidos passarão a ser publicados aqui. Deseja aprovar?"
        f"{aviso_loop}"
    )
    await message.answer(texto, parse_mode="HTML", reply_markup=teclado_confirmacao)
    await state.set_state(AutoraisFluxo.aguardando_confirmacao_destino)

@dp.message(AutoraisFluxo.aguardando_confirmacao_destino)
async def processar_destino_autorais(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await message.answer("❌ Operação cancelada. O destino <b>não</b> foi alterado.", parse_mode="HTML")
        await painel_autorais(message, state)
        return
        
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, clique em Aprovar ✅ ou Cancelar ❌.")
        return
    
    data = await state.get_data()
    id_final = data.get("destino_pendente")
    
    config = ler_autorais_config()
    config["destino"] = id_final
    salvar_autorais_config(config)
    
    if EXIBIR_LOGS: logger.info(f"✅ Destino dos vídeos autorais atualizado para: {id_final}")
    await message.answer(f"✅ <b>Destino atualizado com sucesso!</b>\nOs vídeos convertidos serão enviados instantaneamente para: <code>{str(id_final).replace(':', '_')}</code>", parse_mode="HTML")
    await painel_autorais(message, state)

# ----------------------------------------------------
# LÓGICA DE CONFIRMAÇÃO PARA EDIÇÃO DE DIAS E LIMITES
# ----------------------------------------------------
@dp.message(AutoraisFluxo.menu_principal, F.text == "Editar Dias ⏳")
async def pedir_dias_autorais(message: types.Message, state: FSMContext):
    await message.answer("Por quantos <b>dias</b> o vídeo deve ficar arquivado e oculto até retornar para o grupo de origem? (Ex: 15)", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AutoraisFluxo.aguardando_dias_retorno)

@dp.message(AutoraisFluxo.aguardando_dias_retorno)
async def confirmar_dias_autorais(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await cancelar_fluxo_global(message, state)
        return
        
    if not message.text.isdigit():
        await message.answer("⚠️ Envie apenas números inteiros.", reply_markup=teclado_cancelar)
        return
        
    novo_valor = int(message.text)
    await state.update_data(novo_valor_dias=novo_valor)
    
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer(f"Tem certeza que deseja configurar o retorno para <b>{novo_valor} dias</b>?", parse_mode="HTML", reply_markup=teclado_confirmacao)
    await state.set_state(AutoraisFluxo.aguardando_confirmacao_dias_retorno)

@dp.message(AutoraisFluxo.aguardando_confirmacao_dias_retorno)
async def processar_dias_autorais(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await message.answer("Operação cancelada.")
        await submenu_regras_retorno(message, state)
        return
        
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, clique em Aprovar ou Cancelar.")
        return

    data = await state.get_data()
    novo_valor = data.get("novo_valor_dias")
    
    config = ler_autorais_config()
    config["dias_retorno"] = novo_valor
    salvar_autorais_config(config)
    
    await message.answer(f"✅ <b>Tempo de Retorno Atualizado!</b>\nOs vídeos interceptados ficarão arquivados por {novo_valor} dias antes de serem postados novamente.", parse_mode="HTML")
    await submenu_regras_retorno(message, state)

@dp.message(AutoraisFluxo.menu_principal, F.text == "Editar Limite 📦")
async def pedir_limite_autorais(message: types.Message, state: FSMContext):
    await message.answer("Qual será o <b>limite máximo</b> de vídeos arquivados salvos por dia? (Ex: 5)", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(AutoraisFluxo.aguardando_limite_videos)

@dp.message(AutoraisFluxo.aguardando_limite_videos)
async def confirmar_limite_autorais(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await cancelar_fluxo_global(message, state)
        return
        
    if not message.text.isdigit():
        await message.answer("⚠️ Envie apenas números inteiros.", reply_markup=teclado_cancelar)
        return
        
    novo_valor = int(message.text)
    await state.update_data(novo_valor_limite=novo_valor)
    
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer(f"Tem certeza que deseja definir o limite de vídeos diários para <b>{novo_valor}</b>?", parse_mode="HTML", reply_markup=teclado_confirmacao)
    await state.set_state(AutoraisFluxo.aguardando_confirmacao_limite_videos)

@dp.message(AutoraisFluxo.aguardando_confirmacao_limite_videos)
async def processar_limite_autorais(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await message.answer("Operação cancelada.")
        await submenu_regras_retorno(message, state)
        return
        
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, clique em Aprovar ou Cancelar.")
        return

    data = await state.get_data()
    novo_valor = data.get("novo_valor_limite")
    
    config = ler_autorais_config()
    config["limite_videos"] = novo_valor
    salvar_autorais_config(config)
    
    await message.answer(f"✅ <b>Cota de Retorno Atualizada!</b>\nO robô arquivará no máximo {novo_valor} vídeos de retorno por dia.", parse_mode="HTML")
    await submenu_regras_retorno(message, state)

# ----------------------------------------------------
# 🕐 JANELA DE HORÁRIO DOS VÍDEOS AUTORAIS
# ----------------------------------------------------
teclado_janela_autorais = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Dia Todo (24h) 🕛")],
        [KeyboardButton(text="Cancelar ❌")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

@dp.message(AutoraisFluxo.menu_principal, F.text == "Janela de Horário ⏰")
async def pedir_janela_autorais(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return

    config = ler_autorais_config()
    inicio = config.get("inicio", 10)
    fim = config.get("fim", 20)

    await message.answer(
        f"Defina a <b>Janela de Horário</b> em que os vídeos de retorno podem ser postados.\n\n"
        f"Envie no formato <code>Inicio-Fim</code> (Exemplo: <code>8-22</code>) ou clique no botão para rodar 24h.\n"
        f"<i>Janela atual: {inicio}h às {fim}h</i>",
        parse_mode="HTML",
        reply_markup=teclado_janela_autorais
    )
    await state.set_state(AutoraisFluxo.aguardando_janela_autorais)

@dp.message(AutoraisFluxo.aguardando_janela_autorais)
async def confirmar_janela_autorais(message: types.Message, state: FSMContext):
    import re

    if message.text == "Cancelar ❌":
        await cancelar_fluxo_global(message, state)
        return

    texto = message.text.strip()

    if texto == "Dia Todo (24h) 🕛" or texto.lower() == "dia todo":
        inicio, fim = 0, 24
    else:
        match = re.match(r"^(\d{1,2})\s*-\s*(\d{1,2})$", texto)
        if not match:
            await message.answer("⚠️ Formato inválido! Use exatamente como no exemplo: <code>8-22</code>.", parse_mode="HTML", reply_markup=teclado_janela_autorais)
            return
        inicio, fim = map(int, match.groups())
        if inicio >= fim or inicio < 0 or fim > 24:
            await message.answer("⚠️ Valores inválidos! A hora de início precisa ser menor que a do fim (0 a 24).", reply_markup=teclado_janela_autorais)
            return

    limite = ler_autorais_config().get("limite_videos", 5)
    minutos_janela = (fim - inicio) * 60
    espaco = int(minutos_janela / limite) if limite else 0

    await state.update_data(janela_inicio=inicio, janela_fim=fim)

    texto_exibicao = "24 horas por dia" if inicio == 0 and fim == 24 else f"entre {inicio}h e {fim}h"
    teclado_conf = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer(
        f"Confirmar a janela de postagem <b>{texto_exibicao}</b>?\n\n"
        f"<i>Com {limite} vídeos/dia, dará cerca de {espaco} minutos entre um vídeo e outro.</i>",
        parse_mode="HTML",
        reply_markup=teclado_conf
    )
    await state.set_state(AutoraisFluxo.aguardando_confirmacao_janela_autorais)

@dp.message(AutoraisFluxo.aguardando_confirmacao_janela_autorais)
async def processar_janela_autorais(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await message.answer("Operação cancelada. A janela <b>não</b> foi alterada.", parse_mode="HTML")
        await submenu_regras_retorno(message, state)
        return

    if message.text != "Aprovar ✅":
        await message.answer("Por favor, clique em Aprovar ✅ ou Cancelar ❌.")
        return

    data = await state.get_data()
    inicio = data.get("janela_inicio")
    fim = data.get("janela_fim")

    config = ler_autorais_config()
    config["inicio"] = inicio
    config["fim"] = fim
    salvar_autorais_config(config)

    if EXIBIR_LOGS: logger.info(f"✅ Janela de postagem dos Autorais atualizada para {inicio}h-{fim}h.")

    texto_exibicao = "24 horas por dia" if inicio == 0 and fim == 24 else f"entre as {inicio}h e as {fim}h"
    await message.answer(
        f"✅ <b>Janela de Postagem Salva!</b>\n"
        f"Os vídeos de retorno serão distribuídos {texto_exibicao}.\n\n"
        f"<i>Vale a partir do próximo agendamento. Vídeos que já têm horário cravado mantêm o horário antigo.</i>",
        parse_mode="HTML"
    )
    await submenu_regras_retorno(message, state)

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

@dp.message(Command("limpar_teclado"), StateFilter("*"))
async def limpar_teclado_grupo(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    msg = await message.answer("🧹 Limpando painel de botões preso no grupo...", reply_markup=types.ReplyKeyboardRemove())
    await asyncio.sleep(2)
    try:
        await msg.delete()
        await message.delete()
    except: pass

@dp.message(Command("start"), F.chat.type == "private", StateFilter("*"))
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

@dp.message(F.text == "Monitorar Servidor 🖥️", StateFilter("*"))
async def monitorar_servidor_oracle(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    if EXIBIR_LOGS: logger.info("🖥️ Iniciando auditoria assíncrona de saúde do servidor (Disco e Memória)...")
    msg_status = await message.answer("🖥️ Lendo sensores da máquina Oracle... ⏳")
    
    try:
        # --- 1. COLETA E CÁLCULO DO DISCO ---
        comando_disco = await asyncio.create_subprocess_exec("df", "-h", "/", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout_disco, _ = await comando_disco.communicate()
        # Pega a última linha (que contém os dados da raiz /)
        linha_disco = stdout_disco.decode().strip().split('\n')[-1].split()
        
        # Formatações amigáveis (ex: de "45G" para "45 GB")
        total_disco = linha_disco[1].replace("G", " GB")
        usado_disco = linha_disco[2].replace("G", " GB")
        livre_disco = linha_disco[3].replace("G", " GB")
        pct_disco_str = linha_disco[4]
        pct_disco = int(pct_disco_str.replace('%', ''))
        
        # --- 2. COLETA E CÁLCULO DA RAM ---
        comando_ram = await asyncio.create_subprocess_exec("free", "-m", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout_ram, _ = await comando_ram.communicate()
        linha_ram = stdout_ram.decode().strip().split('\n')[1].split()
        
        total_ram_mb = int(linha_ram[1])
        usado_ram_mb = int(linha_ram[2])
        # Pega a coluna 'available' (mais precisa no Linux moderno)
        disp_ram_mb = int(linha_ram[6]) if len(linha_ram) > 6 else int(linha_ram[3])
        
        # Conversão de MB para GB com 1 casa decimal
        total_ram_gb = round(total_ram_mb / 1024, 1)
        usado_ram_gb = round(usado_ram_mb / 1024, 1)
        disp_ram_gb = round(disp_ram_mb / 1024, 1)
        
        pct_ram = int((usado_ram_mb / total_ram_mb) * 100) if total_ram_mb > 0 else 0
        
        # --- 3. DEFINIÇÃO DE STATUS E ÍCONES ---
        icone_disco = "🟢" if pct_disco < 75 else "🟡" if pct_disco < 90 else "🔴"
        status_disco_txt = "Excelente" if pct_disco < 75 else "Atenção" if pct_disco < 90 else "Crítico"
        
        icone_ram = "🟢" if pct_ram < 75 else "🟡" if pct_ram < 90 else "🔴"
        status_ram_txt = "Excelente" if pct_ram < 75 else "Atenção" if pct_ram < 90 else "Crítico"
        
        # Analisa o status macro para o texto introdutório
        if pct_disco < 75 and pct_ram < 75:
            status_geral = "<b>excelente saúde</b> (🟢 Saudável em todos os aspectos primários)"
            texto_risco = "Não há nenhum gargalo de recursos ou risco iminente de queda por esgotamento de hardware."
        elif pct_disco < 90 and pct_ram < 90:
            status_geral = "<b>estado de atenção</b> (🟡 Requer monitoramento)"
            texto_risco = "Os recursos estão sendo bastante utilizados. É recomendável acompanhar o consumo."
        else:
            status_geral = "<b>risco crítico</b> (🔴 Esgotamento iminente)"
            texto_risco = "Atenção! Há um gargalo severo de recursos. Recomenda-se realizar limpeza ou upgrade de hardware imediatamente."

        # --- 4. CONSTRUÇÃO DA TABELA VISUAL ALINHADA (<pre>) ---
        # A tag <pre> alinha os espaços como no bloco de notas
        tabela = (
            f"<pre>\n"
            f"Recurso | Total | Uso | Livre | Status\n"
            f"----------------------------------------\n"
            f"Disco   | {linha_disco[1]:<5} | {pct_disco_str:<3} | {linha_disco[3]:<5} | {icone_disco} {status_disco_txt}\n"
            f"RAM     | {total_ram_gb:<4}G | {pct_ram:<2}% | {disp_ram_gb:<4}G | {icone_ram} {status_ram_txt}\n"
            f"</pre>"
        )

        # --- 5. MONTAGEM DA MENSAGEM FINAL ---
        texto = (
            f"Seu servidor está em um estado de {status_geral}. {texto_risco}\n"
            f"Abaixo está o diagnóstico detalhado dos recursos analisados:\n\n"
            
            f"💻 <b>Diagnóstico dos Recursos</b>\n\n"
            
            f"🔹 <b>Disco (/dev/sda1):</b> {icone_disco} <b>{pct_disco}% de Uso</b>\n"
            f"Com apenas {usado_disco} ocupados de um total de {total_disco}, você possui {livre_disco} livres. O espaço em disco está bastante confortável para logs, banco de dados ou atualizações de sistema.\n\n"
            
            f"🔹 <b>Memória RAM:</b> {icone_ram} <b>~{pct_ram}% de Uso Real</b>\n"
            f"O sistema está utilizando apenas {usado_ram_gb} GB de um total de {total_ram_gb} GB disponíveis ({total_ram_mb} MB). Você tem aproximadamente {disp_ram_gb} GB livres/disponíveis (<code>available</code>), o que garante uma margem extremamente ampla para rodar novas aplicações, containers ou processos pesados.\n\n"
            
            f"📊 <b>Resumo do Status</b>\n"
            f"{tabela}\n"
            
            f"<blockquote><b>Observação técnica:</b> A utilização da instância Oracle Cloud Free Tier (4 vCPUs Ampere + 24 GB RAM) está super dimensionada para a carga de trabalho atual, garantindo altíssima estabilidade.</blockquote>"
        )
        
        if EXIBIR_LOGS: logger.info(f"✅ Auditoria concluída em background. Disco: {pct_disco}% | RAM: {pct_ram}%")
        await msg_status.edit_text(texto, parse_mode="HTML")
        
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha ao tentar coletar métricas no terminal do Linux: {e}")
        await msg_status.edit_text(f"❌ <b>Erro interno ao ler sensores:</b>\n<code>{e}</code>", parse_mode="HTML")

@dp.message(F.text == "Reiniciar Robôs 🔄", StateFilter("*"))
async def confirmar_reiniciar_robos(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("⚠️ Solicitando confirmação para reiniciar os serviços do servidor.")
    
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar Reinício ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    
    texto = (
        "⚠️ <b>ATENÇÃO!</b>\n\n"
        "Você está prestes a reiniciar <b>TODOS</b> os robôs simultaneamente no servidor Linux:\n\n"
        "🔹 Motor Espião (Userbot)\n"
        "🔹 Espelhador (Vídeos Autorais)\n"
        "🔹 Divulgação de Canais (Spam)\n"
        "🔹 Bot Mestre (Painel Principal)\n\n"
        "<i>Isso causará uma breve interrupção. O painel ficará mudo por alguns segundos até que o sistema inteiro acorde e se reconecte ao Telegram.</i>\n\n"
        "Confirma o reinício de todos os sistemas?"
    )
    await message.answer(texto, reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(ConfigFluxo.aguardando_confirmacao_reiniciar)

@dp.message(ConfigFluxo.aguardando_confirmacao_reiniciar)
async def processar_reiniciar_robos(message: types.Message, state: FSMContext):
    if message.text != "Aprovar Reinício ✅":
        await message.answer("Por favor, clique em Aprovar Reinício ✅ ou Cancelar ❌.")
        return

    await state.clear()
    
    # 1. Envia a mensagem de status SEM o teclado embutido
    msg_status = await message.answer("🔄 <b>Reiniciando os serviços no servidor Linux...</b>\n<i>Aguarde...</i>", parse_mode="HTML")
    
    if EXIBIR_LOGS: logger.info("🔄 Comando de reinício global acionado pelo administrador.")
    
    # Baseado na sua pasta services_linux do Github
    servicos_background = [
        "motor_userbot_bot.service",
        "espelhador_videos_autorais_bot.service",
        "divulgacao_canal_bot.service"
    ]

    import subprocess
    # 2. Reinicia os serviços secundários em background
    for servico in servicos_background:
        try:
            subprocess.Popen(["sudo", "systemctl", "restart", servico])
            if EXIBIR_LOGS: logger.info(f"✅ Disparado reinício para: {servico}")
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro ao reiniciar {servico}: {e}")
            
    # Dá tempo para as threads do Linux processarem os outros robôs
    await asyncio.sleep(2)

    # 3. Apaga a mensagem temporária e envia a nova mensagem de Sucesso COM o teclado
    await msg_status.delete()
    await message.answer("✅ <b>Sistemas Secundários Reiniciados!</b>\n🔄 Reiniciando o Bot Principal agora. O Painel voltará online em 5 segundos!", parse_mode="HTML", reply_markup=obter_teclado_opcoes_servidor())
    
    # 4. Reinicia a si mesmo (Este comando vai forçar a interrupção imediata do bot mestre)
    try:
        if EXIBIR_LOGS: logger.info("🔄 Reiniciando o próprio serviço (bot_mestre_bot.service). O script será interrompido agora!")
        subprocess.Popen(["sudo", "systemctl", "restart", "bot_mestre_bot.service"])
    except Exception:
        pass

@dp.message(F.text == "Canal Afiliados 📺", StateFilter("*"))
async def menu_canal_principal(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    if EXIBIR_LOGS: logger.info("📂 Acessando a pasta do Canal Afiliados.")
    await message.answer("📺 <b>Menu do Canal Afiliados</b>\nGerencie as postagens e rotinas abaixo:", reply_markup=obter_teclado_principal(), parse_mode="HTML")

# NOVO: Funções de Gestão do Banco de Pedidos Individuais
def ler_banco_pedidos():
    return ler_config_bd("banco_pedidos", padrao={}, arquivo_legado="banco_pedidos.json")

def salvar_banco_pedidos(dados):
    salvar_config_bd("banco_pedidos", dados)

async def buscar_dados_financeiros_shopee(dias_retroativos=30):
    if not SHOPEE_APP_ID or not SHOPEE_APP_SECRET:
        if EXIBIR_LOGS: logger.warning("⏳ [API Shopee] Chaves financeiras ausentes no .env.")
        return None
        
    from datetime import timedelta
    agora = datetime.now(fuso_horario)
    conversoes_totais = []
    
    # ✅ A API da Shopee barra requisições > 31 dias.
    # O robô agora "fatia" buscas longas em janelas de 30 dias automaticamente!
    for i in range(0, dias_retroativos, 30):
        dias_para_puxar = min(30, dias_retroativos - i)
        
        fim_chunk = agora - timedelta(days=i)
        inicio_chunk = fim_chunk - timedelta(days=dias_para_puxar)
        
        start_ts = int(inicio_chunk.replace(hour=0, minute=0, second=0).timestamp())
        end_ts = int(fim_chunk.replace(hour=23, minute=59, second=59).timestamp())
        
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
                            if EXIBIR_LOGS: logger.error(f"❌ A Shopee recusou a fatia {i} a {i+dias_para_puxar} dias: {mensagem_erro}")
                        else:
                            nodes = dados.get("data", {}).get("conversionReport", {}).get("nodes", [])
                            if nodes:
                                conversoes_totais.extend(nodes)
                                if EXIBIR_LOGS: logger.info(f"✅ Fatiamento financeiro ({i} a {i+dias_para_puxar} dias atrás): {len(nodes)} pedidos extraídos.")
                    else:
                        if EXIBIR_LOGS: logger.error(f"❌ Erro de Conexão HTTP {response.status}: {dados_crus}")
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro crítico no motor financeiro: {e}")
            
        await asyncio.sleep(1) # Pequena pausa anti-ban da Shopee entre os blocos
        
    return conversoes_totais

def processar_e_salvar_pedidos_api(conversoes, ignorar_ledger=False):
    pedidos_db = ler_banco_pedidos()
    historico = ler_historico_financeiro()
    
    # 🟢 O Robô carrega a sua conta bancária virtual
    saldo_caixa = float(ler_config_bd("saldo_caixa_shopee", 0.0))
    houve_atualizacao = False
    from datetime import timezone
    import random
    
    if conversoes:
        for conv in conversoes:
            orders = conv.get("orders", [])
            if not orders: continue
            
            c_total = float(conv.get("totalCommission", "0"))
            c_shopee = float(conv.get("shopeeCommissionCapped", "0"))
            c_extra = float(conv.get("sellerCommission", "0"))
            
            dt_obj_utc = datetime.fromtimestamp(conv.get("purchaseTime", 0), tz=timezone.utc)
            dt_obj = dt_obj_utc.astimezone(fuso_horario)
            dt_db_str = dt_obj.strftime("%Y-%m-%d")
            
            qtd_itens = len(orders)
            c_total_frac = c_total / qtd_itens
            c_shopee_frac = c_shopee / qtd_itens
            c_extra_frac = c_extra / qtd_itens

            for idx_order, order in enumerate(orders):
                order_sn = order.get("orderId")
                if not order_sn: 
                    order_sn = f"shopee_vid_{conv.get('purchaseTime')}_{idx_order}"
                    
                novo_status = order.get("orderStatus", "").upper()
                
                if order_sn in pedidos_db:
                    estado_anterior = pedidos_db[order_sn]["status"]
                    if estado_anterior != novo_status:
                        pedidos_db[order_sn]["status"] = novo_status
                        houve_atualizacao = True
                        
                        # 🟢 A MÁGICA: Se o pedido MUDOU para Confirmado agora, ele soma no seu Saldo!
                        if not ignorar_ledger:
                            if estado_anterior != "COMPLETED" and novo_status == "COMPLETED":
                                saldo_caixa += c_total_frac
                                if EXIBIR_LOGS: logger.info(f"💰 Transição detectada! Pedido confirmado: + R${c_total_frac:.2f}")
                            elif estado_anterior == "COMPLETED" and novo_status != "COMPLETED":
                                saldo_caixa -= c_total_frac # Estorno de segurança
                                
                    # Atualiza comissões caso o valor tenha sido ajustado pela Shopee
                    if c_total_frac > 0 and pedidos_db[order_sn].get("comissao_total", 0) != c_total_frac:
                        if not ignorar_ledger and novo_status == "COMPLETED":
                            diferenca = c_total_frac - pedidos_db[order_sn]["comissao_total"]
                            saldo_caixa += diferenca
                        
                        pedidos_db[order_sn]["comissao_total"] = c_total_frac
                        pedidos_db[order_sn]["comissao_shopee"] = c_shopee_frac
                        pedidos_db[order_sn]["comissao_vendedor"] = c_extra_frac
                        houve_atualizacao = True
                else:
                    # É um Pedido Novo Inédito
                    pedidos_db[order_sn] = {
                        "data": dt_db_str,
                        "status": novo_status,
                        "comissao_total": c_total_frac,
                        "comissao_shopee": c_shopee_frac,
                        "comissao_vendedor": c_extra_frac
                    }
                    houve_atualizacao = True
                    # Se ele já nasceu confirmado na API, soma no Saldo
                    if not ignorar_ledger and novo_status == "COMPLETED":
                        saldo_caixa += c_total_frac
                        if EXIBIR_LOGS: logger.info(f"💰 Novo pedido já nasceu confirmado! + R${c_total_frac:.2f}")
                    
    if houve_atualizacao:
        salvar_banco_pedidos(pedidos_db)
        if not ignorar_ledger:
            salvar_config_bd("saldo_caixa_shopee", saldo_caixa) # Salva a conta bancária
            
    # Reconstrói a visão de desempenho do DRE (Fica intacta para o gráfico)
    historico_limpo = {}
    for sn, p in pedidos_db.items():
        d_str = p["data"]
        st = p["status"]
        
        if d_str not in historico_limpo:
            historico_limpo[d_str] = {"aprovado": 0.0, "pendente": 0.0, "cancelado": 0.0, "shopee": 0.0, "vendedor": 0.0, "qtd_aprovado": 0, "qtd_pendente": 0, "qtd_cancelado": 0, "clicks": 0}
            
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
        [KeyboardButton(text="Fila de Autorais 🎥"), KeyboardButton(text="Fila do Grupo Público 📬")],
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

# ✅ NOVO: Fila dedicada do Grupo Público (espelha o layout da Fila de Autorais)
@dp.message(RelatoriosFluxo.menu_filas, F.text == "Fila do Grupo Público 📬")
async def relatorio_fila_publico(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("📬 Compilando o relatório da Fila do Grupo Público...")

    config = ler_submissao_config()
    dias_atraso = config.get("repost_dias", 15)
    limite = config.get("repost_limite", 6)
    is_pausado = config.get("repost_pausado", False) or not config.get("ativo", False)

    agora = datetime.now(fuso_horario)
    hoje_str = agora.strftime("%Y-%m-%d")

    # Origem real de onde os vídeos são puxados para o Público
    canal_origem = config.get("repost_origem")
    if not canal_origem:
        config_aut = ler_config_bd("autorais_config", {})
        canal_origem = config_aut.get("destino", "")
    origem_base = str(canal_origem).split(":")[0].strip()

    cache_nomes = ler_cache_nomes_grupos()
    display_origem = cache_nomes.get(origem_base, origem_base or "Origem não definida")

    try:
        conexao = sqlite3.connect("banco_dados.db")
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()
        cursor.execute("""
            SELECT * FROM fila_publico
            WHERE processado = 0 OR data_postagem LIKE ?
            ORDER BY data_alvo ASC
        """, (f"{hoje_str}%",))
        linhas = cursor.fetchall()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler a fila do Grupo Público: {e}")
        await message.answer(f"❌ Erro interno ao ler o banco de dados: {e}")
        return

    if not linhas:
        await message.answer(
            "📭 <b>A fila do Grupo Público está vazia no momento.</b>\n\n"
            "<i>Ela é preenchida pelo sorteio no momento da captura. Assim que um vídeo novo "
            "for sorteado, ele aparece aqui com a data prevista.</i>",
            parse_mode="HTML"
        )
        return

    itens = []
    for linha in linhas:
        data_post = linha["data_postagem"] or ""
        data_alvo = linha["data_alvo"] or ""
        itens.append({
            "id": str(linha["id_unico"]),
            "msg_id_destino": linha["msg_id_destino"],
            "legenda": linha["legenda"],
            "data_captura": linha["data_captura"],
            "processado": bool(linha["processado"]),
            # ✅ Se o motor já cravou o horário exato, usa ele; senão mostra só a data
            "data_publicacao": (linha["horario_disparo"] or data_alvo),
            "data_postagem": data_post.split(" ")[0] if data_post else "",
            "horario_postagem": data_post.split(" ")[1][:5] if " " in data_post else "",
            "is_pausado": is_pausado
        })

    # Postados hoje aparecem primeiro; depois os agendados por data-alvo
    itens.sort(key=lambda x: (0 if x["processado"] else 1, x.get("data_publicacao") or ""))
    qtd_pendentes = len([i for i in itens if not i["processado"]])

    from motor_filas import gerar_layout_item_padrao

    status_txt = "🔴 PAUSADO" if is_pausado else "🟢 ATIVO"
    texto_atual = f"📊 <b>Relatório da Fila Grupo Público (D+{dias_atraso})</b>\n\n"
    texto_atual += f"📡 <b>Rota: Repostagem Pública</b> ({qtd_pendentes} vídeos agendados)\n"
    texto_atual += f"🕒 <b>Postagem:</b> D+{dias_atraso}, entre 10h e 20h\n"
    texto_atual += f"📦 <b>Cota Diária:</b> {limite} vídeos/dia  ·  ⚙️ {status_txt}\n"

    mensagens_para_enviar = []

    for i, v in enumerate(itens, 1):
        link_origem = ""
        msg_id = v.get("msg_id_destino")
        if msg_id and origem_base:
            if origem_base.lstrip("-").isdigit():
                id_limpo = origem_base.replace("-100", "").replace("-", "")
                link_origem = f"https://t.me/c/{id_limpo}/{msg_id}"
            elif origem_base.startswith("@"):
                link_origem = f"https://t.me/{origem_base.replace('@', '')}/{msg_id}"

        linha_video = gerar_layout_item_padrao(
            index=i,
            item=v,
            tipo_fila="Público",
            atraso_dias=dias_atraso,
            agora=agora,
            fuso_horario=fuso_horario,
            display_origem=display_origem,
            link_origem=link_origem,
            link_destino=None
        )

        if len(texto_atual) + len(linha_video) > 3800:
            mensagens_para_enviar.append(texto_atual)
            texto_atual = "📡 <b>Rota: Repostagem Pública (Continuação)</b>\n\n"

        texto_atual += linha_video

    if texto_atual.strip():
        mensagens_para_enviar.append(texto_atual)

    for msg in mensagens_para_enviar:
        await message.answer(msg, parse_mode="HTML", disable_web_page_preview=True)

    if EXIBIR_LOGS: logger.info(f"✅ Relatório da Fila do Grupo Público entregue ({len(itens)} itens).")

@dp.message(RelatoriosFluxo.menu_filas, F.text.in_(["Fila do Espelhador 🔄", "Fila do Espião 🕵️", "Fila de Autorais 🎥"]))
@dp.message(RelatoriosFluxo.aguardando_rota_espelhador)
async def relatorio_filas_unificado(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    estado_atual = await state.get_state()
    rota_selecionada = None
    
    # 1. TRATAMENTO DO NOVO MENU DE MÚLTIPLAS ROTAS (ESPELHADOR)
    if estado_atual == RelatoriosFluxo.aguardando_rota_espelhador:
        if message.text == "Voltar aos Relatórios 🔙":
            if EXIBIR_LOGS: logger.info("🔙 Cancelando seleção de rota e retornando.")
            await state.clear()
            await menu_relatorios_filas(message, state)
            return
            
        tipo_fila = "Espelhador"
        rota_selecionada = message.text
        if EXIBIR_LOGS: logger.info(f"📊 Rota específica selecionada para exibição: {rota_selecionada}")
    else:
        if "Espelhador" in message.text:
            tipo_fila = "Espelhador"
        elif "Autorais" in message.text:
            tipo_fila = "Autorais"
        else:
            tipo_fila = "Espião"
        
        # Se for o Espelhador e existirem múltiplas rotas, cria a interrupção visual
        if tipo_fila == "Espelhador":
            import painel_espelhos
            dados_rotas = painel_espelhos.ler_espelhos()
            rotas = dados_rotas.get("rotas", [])
            
            if len(rotas) > 1:
                if EXIBIR_LOGS: logger.info("🔄 Múltiplas rotas detectadas no Espelhador. Exibindo menu de seleção...")
                botoes = []
                
                # Primeiro botão isolado no topo
                botoes.append([KeyboardButton(text="Todos os Espelhos 🌐")])
                
                # Um botão para cada espelho
                for r in rotas:
                    botoes.append([KeyboardButton(text=r['nome'])])
                    
                # Botão de voltar no final
                botoes.append([KeyboardButton(text="Voltar aos Relatórios 🔙")])
                
                teclado = ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)
                await message.answer("🔄 <b>Múltiplas rotas detectadas!</b>\nQual fila do Espelhador deseja analisar?", reply_markup=teclado, parse_mode="HTML")
                await state.set_state(RelatoriosFluxo.aguardando_rota_espelhador)
                return

    if EXIBIR_LOGS: logger.info(f"📊 Iniciando compilação do relatório unificado (Sem limites) para a fila do {tipo_fila}...")
    
    if tipo_fila == "Espião":
        fila_data = ler_fila_clonagem()
        fila = fila_data.get("fila", [])
    elif tipo_fila == "Autorais":
        try:
            conexao = sqlite3.connect("banco_dados.db")
            conexao.row_factory = sqlite3.Row
            cursor = conexao.cursor()
            cursor.execute("SELECT * FROM fila_autorais ORDER BY data_alvo ASC, horario_disparo ASC")
            linhas = cursor.fetchall()
            conexao.close()
            
            fila = []
            for linha in linhas:
                fila.append({
                    "id": str(linha["id_unico"]),
                    "msg_id_destino": linha["msg_id_destino"],
                    "legenda": linha["legenda"],
                    "caminho_video": linha["caminho_arquivo"],
                    "data_captura": linha["data_captura"],
                    "data_alvo": linha["data_alvo"],
                    "horario_disparo": linha["horario_disparo"],
                    "processado": bool(linha["processado"])
                })
        except Exception as e:
            fila = []
            if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler fila_autorais: {e}")
    else:
        try:
            with open("fila_espelhador.json", "r", encoding="utf-8") as f:
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
    elif tipo_fila == "Autorais":
        config_aut = ler_autorais_config()
        atraso_dias = config_aut.get("dias_retorno", 15)
    elif tipo_fila == "Espião":
        try:
            if EXIBIR_LOGS: logger.info("🔍 Extraindo configurações de destino do Espião via banco SQLite...")
            dados_espiao = ler_alvos_espiao()
            atraso_dias = dados_espiao.get("intervalo_dias", 1)
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro ao resgatar configurações do Espião: {e}")
        
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
            # ✅ CORREÇÃO BLINDADA: Aceita qualquer formato de "True" para forçar a permanência
            if item.get("processado") in [True, 1, "true", "True"]:
                if str(item.get("data_postagem")) == hoje_str:
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
        
    elif tipo_fila == "Autorais":
        fila_limpa = []
        hoje_str = agora.strftime("%Y-%m-%d")
        houve_alteracao = False
        
        try:
            conexao = sqlite3.connect("banco_dados.db")
            cursor = conexao.cursor()
            
            for item in fila:
                if item.get("processado", False) or item.get("processado") == 1:
                    # O robô autoral usa o horario_disparo para marcar o momento exato da postagem
                    horario_disp = item.get("horario_disparo", "")
                    
                    # Se foi postado hoje, mantém ele vivo para aparecer no relatório!
                    if horario_disp and horario_disp.startswith(hoje_str):
                        if EXIBIR_LOGS: logger.info(f"👁️ Pente Fino (Relatório): Mantendo o vídeo autoral postado hoje ({item.get('id')}) no visual da fila.")
                        fila_limpa.append(item)
                    else:
                        # Se já virou o dia, apaga o registro do banco de dados para não acumular
                        cursor.execute("DELETE FROM fila_autorais WHERE id_unico = ?", (item["id"],))
                        houve_alteracao = True
                    continue
                
                # Se for pendente, continua na lista normalmente
                fila_limpa.append(item)
                
            if houve_alteracao:
                conexao.commit()
            conexao.close()
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro no pente fino da fila_autorais: {e}")
            
        pendentes = fila_limpa
        
    elif tipo_fila == "Espelhador":
        import painel_espelhos
        dados_rotas_atualizadas = painel_espelhos.ler_espelhos()
        lista_rotas = dados_rotas_atualizadas.get("rotas", [])

        fila_limpa = []
        houve_alteracao = False
        hoje_str = agora.strftime("%Y-%m-%d")
        
        for item in fila:
            # 🚀 AUTO-CORREÇÃO DINÂMICA: Entende cada espelho cruzando a origem, destino OU Nome
            nome_antigo = item.get("nome_rota", "")
            origem_item = str(item.get("chat_origem", item.get("origem", "")))
            
            # ✅ NOVO: Flag para verificar se a rota do vídeo ainda existe
            rota_encontrada = False
            atraso_dias_rota = 1
            
            for r in lista_rotas:
                # Compara usando a origem OU o nome da rota (para compatibilidade com itens antigos)
                if (origem_item and str(r.get("origem", "")) == origem_item) or (nome_antigo and r.get("nome", "") == nome_antigo):
                    rota_encontrada = True
                    nome_atualizado = r.get("nome")
                    atraso_dias_rota = int(r.get("intervalo_dias", 1))
                    
                    if nome_atualizado and nome_antigo != nome_atualizado:
                        item["nome_rota"] = nome_atualizado
                        houve_alteracao = True
                    break

            # 🛡️ PENTE FINO: Se a rota não existe mais, deleta o vídeo órfão!
            if not rota_encontrada:
                if EXIBIR_LOGS: logger.info(f"🧹 Pente Fino: Removendo vídeo órfão de uma rota excluída (Rota antiga: {nome_antigo}).")
                houve_alteracao = True
                caminho_video = item.get("caminho_video")
                if caminho_video and os.path.exists(caminho_video):
                    try: os.remove(caminho_video)
                    except: pass
                continue # Pula este item, ele não vai para a fila limpa

            # Mantém no visual os que foram postados HOJE no Espelhador.
            if item.get("processado", False):
                if item.get("data_postagem") == hoje_str:
                    if EXIBIR_LOGS: logger.info(f"👁️ Pente Fino (Relatório): Mantendo o vídeo postado hoje ({item.get('id', 'SemID')}) no visual da fila do Espelhador.")
                    fila_limpa.append(item)
                else:
                    houve_alteracao = True
                continue

            # ✅ NOVO: PENTE FINO DE VALIDADE (Padronizado com o Espião)
            data_cap_str = item.get("data_captura", "")
            if data_cap_str:
                try:
                    data_captura = datetime.strptime(data_cap_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario)
                    horas_na_fila = (agora - data_captura).total_seconds() / 3600
                    limite_horas = (atraso_dias_rota * 24) + 24 # Expiração baseada no atraso DAQUELA rota
                    
                    # Elimina os vídeos fantasmas que ficaram presos
                    if horas_na_fila > limite_horas:
                        if EXIBIR_LOGS: logger.info(f"🧹 Pente Fino (Relatório): Removendo clone do Espelhador expirado ({horas_na_fila:.1f}h). Rota: {item.get('nome_rota')}")
                        houve_alteracao = True
                        caminho_video = item.get("caminho_video")
                        if caminho_video and os.path.exists(caminho_video):
                            try: os.remove(caminho_video)
                            except: pass
                        continue # Pula este item, deletando-o da fila
                except ValueError:
                    pass
                
            fila_limpa.append(item)
            
        # Se encontrou lixo antigo ou atualizou os nomes dos robôs, salva o JSON silenciosamente
        if houve_alteracao:
            fila_data["fila"] = fila_limpa
            try:
                with open("fila_espelhador.json", "w", encoding="utf-8") as f:
                    json.dump(fila_data, f, indent=4)
                if EXIBIR_LOGS: logger.info("✅ Auto-correção: Nomes das rotas sincronizados e lixo antigo limpo.")
            except Exception as e:
                if EXIBIR_LOGS: logger.error(f"❌ Erro ao limpar fila espelhador: {e}")
            
        pendentes = fila_limpa
        
        # ✅ NOVO: Aplica o filtro de listagem caso o usuário tenha clicado em uma rota específica
        if rota_selecionada and rota_selecionada != "Todos os Espelhos 🌐":
            pendentes = [i for i in pendentes if i.get("nome_rota") == rota_selecionada]
    
    if not pendentes:
        await message.answer(f"📭 A fila do {tipo_fila} está vazia no momento.", parse_mode="HTML")
        if EXIBIR_LOGS: logger.info(f"✅ Relatório do {tipo_fila} gerado (Fila vazia).")
        return
        
    cache_nomes = ler_cache_nomes_grupos()
    rotas_agrupadas = {}
    
    if tipo_fila == "Espelhador":
        import painel_espelhos
        dados_rotas = painel_espelhos.ler_espelhos()
        mapa_rotas = {r["nome"]: r for r in dados_rotas.get("rotas", [])}
        
        for item in pendentes:
            nome_rota = item.get("nome_rota", "Rota Desconhecida")
            if nome_rota not in rotas_agrupadas: rotas_agrupadas[nome_rota] = []
            rotas_agrupadas[nome_rota].append(item)
            
    elif tipo_fila == "Autorais":
        mapa_rotas = {
            "Repostagem Autoral": {
                "inicio": 10,
                "fim": 20,
                "status_canais": {},
                "intervalo_dias": atraso_dias
            }
        }
        config_aut = ler_autorais_config()
        is_pausado = config_aut.get("pausar_repostagem", False) or config_aut.get("pausar_robo_completo", False)
        
        for item in pendentes:
            item["nome_rota"] = "Repostagem Autoral"
            item["is_pausado"] = is_pausado
        rotas_agrupadas["Repostagem Autoral"] = pendentes

    else: 
        mapa_rotas = {
            "Radar Global": {
                "inicio": dados_espiao.get("inicio", 10),
                "fim": dados_espiao.get("fim", 22),
                "status_canais": dados_espiao.get("status_alvos", {})
            }
        }
        rotas_agrupadas["Radar Global"] = pendentes

    # ✅ ORDENAÇÃO UNIVERSAL E INTELIGENTE (ESPIÃO E ESPELHADOR)
    def chave_ordenacao_universal(item):
        if item.get("processado", False) or item.get("processado") == 1:
            return (0, str(item.get("horario_postagem", "00:00")))
        elif item.get("horario_disparo"):
            return (1, str(item.get("horario_disparo")))
        elif item.get("data_alvo"): # Específico para a Fila de Autorais
            # 🛡️ TRAVA: Garante que data_alvo é uma string válida antes de concatenar
            return (1, str(item.get("data_alvo")) + " 10:00:00")
        else:
            return (2, str(item.get("data_captura", "2099-01-01 00:00:00")))

    for nome_rota in rotas_agrupadas:
        rotas_agrupadas[nome_rota].sort(key=chave_ordenacao_universal)
         
    titulo_atraso = f" (D+{atraso_dias})" if tipo_fila in ["Espião", "Autorais"] else ""

    mensagens_para_enviar = []
    primeira_rota = True

    for nome_rota, itens in rotas_agrupadas.items():
        # ✅ Insere uma mensagem divisória antes de começar a próxima rota
        if not primeira_rota:
            mensagens_para_enviar.append("➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n🔄 <i>Próximo Espelho...</i>\n➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖")

        if primeira_rota:
            texto_atual = f"📊 <b>Relatório da Fila {tipo_fila}{titulo_atraso}</b>\n\n"
            primeira_rota = False
        else:
            texto_atual = "" # Rota nova = Mensagem limpa nova

        rota_info = mapa_rotas.get(nome_rota, {})
        inicio = rota_info.get("inicio", 10)
        fim = rota_info.get("fim", 22)
        
        atraso_dias_rota = int(rota_info.get("intervalo_dias", atraso_dias)) 
        status_canais = rota_info.get("status_canais") or rota_info.get("status_alvos") or {}
        
        texto_postagem = "Imediata (D+0)" if atraso_dias_rota == 0 else f"D+{atraso_dias_rota}, entre {inicio}h e {fim}h"
        cabecalho_rota = f"📡 <b>Rota: {nome_rota}</b> ({len([i for i in itens if not i.get('processado')])} vídeos agendados)\n🕒 <b>Postagem:</b> {texto_postagem}\n\n"
        
        texto_atual += cabecalho_rota
        
        for i, v in enumerate(itens, 1):
            data_cap = v.get("data_captura", "Data não registrada")
            
            origem_bruta = str(v.get("chat_origem", v.get("origem", v.get("grupo_id", v.get("canal_id", "")))))
            link_original = v.get("link_original", "")
            msg_id = v.get("mensagem_id") or v.get("msg_id") or v.get("message_id")
            
            # --- 1. RESGATE ESTRUTURAL (Com suporte exclusivo a Autorais) ---
            if tipo_fila == "Autorais":
                origem_bruta = str(config_aut.get("destino", ""))
                id_destino = str(config_aut.get("origem", ""))
                msg_id = v.get("msg_id_destino")
                
                link_telegram = ""
                if msg_id and origem_bruta:
                    if origem_bruta.lstrip("-").isdigit():
                        chat_id_limpo = origem_bruta.replace("-100", "").replace("-", "")
                        link_telegram = f"https://t.me/c/{chat_id_limpo}/{msg_id}"
                    elif origem_bruta.startswith("@"):
                        username = origem_bruta.replace("@", "")
                        link_telegram = f"https://t.me/{username}/{msg_id}"
                
                link_final_exibicao = link_telegram
                
                # ✅ Extração Inteligente do Nome do Produto
                legenda = v.get("legenda", "")
                import re
                
                match_item = re.search(r'📦\s*Item:\s*([^\n<]+)', legenda)
                if match_item:
                    nome_produto = match_item.group(1).strip()
                else:
                    legenda_limpa = re.sub(r'<[^>]+>', '', legenda).strip()
                    linhas = legenda_limpa.split('\n')
                    nome_produto = ""
                    
                    for linha in linhas:
                        l = linha.strip()
                        if l and "http" not in l.lower() and "shp.ee" not in l.lower() and not l.startswith("#"):
                            match_video = re.search(r'(?i)^Vídeo\s+\d+\s*\|\s*(.+)', l)
                            if match_video:
                                nome_produto = match_video.group(1).strip()
                            else:
                                nome_produto = l
                            break
                            
                    if not nome_produto:
                        nome_produto = "Produto Autoral (Sem Descrição)"

                # 🔥 O VERDADEIRO PULO DO GATO:
                # 1. Colocamos o Nome do Canal (com emoji) na chave que o motor usa para o topo
                nome_origem_canal = cache_nomes.get(origem_bruta, origem_bruta)
                v["nome_origem"] = f"🎥 {nome_origem_canal[:30]}"
                
                # 2. Enganamos o motor injetando "📦 Item: " na legenda para ele exibir no '└ Nome:'
                v["legenda"] = f"📦 Item: {nome_produto[:45]}\n{legenda}"
                
                nome_origem = cache_nomes.get(origem_bruta, origem_bruta)
                display_origem = f"📦 Acervo: {nome_origem[:20]}"
                link_destino = None
            else:
                # O CÓDIGO NORMAL DA ORIGEM DOS OUTROS MÓDULOS COMEÇA AQUI
                if not origem_bruta or origem_bruta in ["Desconhecida", "Origem desconhecida", "Origem não mapeada", "None"]:
                    nome_rota_item = v.get("nome_rota")
                    if tipo_fila == "Espelhador" and nome_rota_item:
                        import painel_espelhos
                        dados_rotas_temp = painel_espelhos.ler_espelhos()
                        for r in dados_rotas_temp.get("rotas", []):
                            if r.get("nome") == nome_rota_item:
                                origem_bruta = str(r.get("origem", "Desconhecida"))
                                break
                    if not origem_bruta or origem_bruta == "None":
                        origem_bruta = "Desconhecida"

            if origem_bruta in ["Desconhecida", "Origem desconhecida", "Origem não mapeada", "None", ""]:
                if link_original and "t.me/c/" in link_original:
                    try: origem_bruta = "-100" + link_original.split("t.me/c/")[1].split("/")[0]
                    except: pass
                elif link_original and "t.me/" in link_original:
                    try: origem_bruta = "@" + link_original.split("t.me/")[1].split("/")[0]
                    except: pass

            # --- 2. CONSTRUÇÃO PRIORITÁRIA DO LINK DO TELEGRAM ---
            link_telegram = ""
            if msg_id and origem_bruta not in ["Desconhecida", "Origem desconhecida", "Origem não mapeada", "None", ""]:
                if origem_bruta.lstrip("-").isdigit():
                    chat_id_limpo = origem_bruta.replace("-100", "").replace("-", "")
                    link_telegram = f"https://t.me/c/{chat_id_limpo}/{msg_id}"
                elif origem_bruta.startswith("@"):
                    username = origem_bruta.replace("@", "")
                    link_telegram = f"https://t.me/{username}/{msg_id}"
            
            # --- 3. PREPARAÇÃO DO LINK DE ORIGEM ---
            link_final_exibicao = link_telegram if link_telegram else link_original
            
            if link_final_exibicao:
                if "t.me" in link_final_exibicao:
                    texto_link = "📥 Origem" if tipo_fila == "Espião" else "Ver Post no Telegram"
                elif "shopee" in link_final_exibicao or "shp.ee" in link_final_exibicao:
                    texto_link = "Ver Produto na Shopee"
                else:
                    texto_link = "Ver Link"
                link_display = f"<a href='{link_final_exibicao}'>{texto_link}</a>"
            else:
                link_display = "<i>Sem link de origem</i>"
                
            if v.get("processado", False) and tipo_fila == "Espião":
                id_destino = str(dados_espiao.get("canal_destino", ""))
                msg_id_postada = v.get("msg_postada_id")
                
                if id_destino and msg_id_postada:
                    if id_destino.lstrip("-").isdigit():
                        id_limpo = id_destino.replace("-100", "").replace("-", "")
                        link_dest = f"https://t.me/c/{id_limpo}/{msg_id_postada}"
                    else:
                        username_dest = id_destino.replace("@", "")
                        link_dest = f"https://t.me/{username_dest}/{msg_id_postada}"
                        
                    link_display += f" | <a href='{link_dest}'>📤 Destino</a>"
                elif id_destino and not id_destino.lstrip("-").isdigit():
                    link_display += f" | <a href='https://t.me/{id_destino.replace('@', '')}'>📤 Destino</a>"
                
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
                                str_id = str(dados.get("id", dados.get("chat_id", dados.get("origem", ""))))
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
                
                # ✅ CORREÇÃO: sem corte. O nome do canal sai sempre completo.
                display_origem = str(nome_origem) if nome_origem else str(origem_bruta)
                
            # --- 5. PREPARAÇÃO DO LINK DE DESTINO (Apenas se postado) ---
            link_destino = None
            if v.get("processado", False) or v.get("processado") == 1:
                if tipo_fila == "Espião":
                    id_destino = str(dados_espiao.get("canal_destino", ""))
                else:
                    id_destino = str(v.get("chat_destino") or v.get("destino") or "")
                    
                msg_id_postada = v.get("msg_postada_id") or v.get("mensagem_id_destino") or v.get("msg_id")
                
                if id_destino and msg_id_postada:
                    if id_destino.lstrip("-").isdigit():
                        id_limpo = id_destino.replace("-100", "").replace("-", "")
                        link_destino = f"https://t.me/c/{id_limpo}/{msg_id_postada}"
                    else:
                        username_dest = id_destino.replace("@", "")
                        link_destino = f"https://t.me/{username_dest}/{msg_id_postada}"
                elif id_destino and not id_destino.lstrip("-").isdigit():
                    link_destino = f"https://t.me/{id_destino.replace('@', '')}"

            # --- 6. ACIONANDO O MOTOR CENTRAL PARA O DESIGN DA FILA ---
            from motor_filas import gerar_layout_item_padrao
            
            linha_video = gerar_layout_item_padrao(
                index=i, 
                item=v, 
                tipo_fila=tipo_fila, 
                atraso_dias=atraso_dias_rota, 
                agora=agora, 
                fuso_horario=fuso_horario, 
                display_origem=display_origem, 
                link_origem=link_final_exibicao, 
                link_destino=link_destino
            )
            
            if len(texto_atual) + len(linha_video) > 3800:
                mensagens_para_enviar.append(texto_atual)
                texto_atual = f"📡 <b>Rota: {nome_rota} (Continuação)</b>\n\n"
                
            texto_atual += linha_video
            
        # ✅ Salva a rota atual na lista de mensagens ANTES de ir para a próxima rota
        if texto_atual.strip():
            mensagens_para_enviar.append(texto_atual)

    # Dispara todas as mensagens (Relatórios e Divisórias) separadamente
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
    return ler_config_bd("historico_financeiro", padrao={}, arquivo_legado="historico_financeiro.json")

def salvar_historico_financeiro(dados):
    salvar_config_bd("historico_financeiro", dados)

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
            
    total_pedidos_geral = pagos + pendentes + cancelados
    taxa_conversao = (pagos / total_pedidos_geral * 100) if total_pedidos_geral > 0 else 0.0
    
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
    
    # Estimativa de Faturamento
    import calendar
    dias_no_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    dia_atual = hoje.day
    
    dias_sincronizados = 0
    for i in range(1, dia_atual + 1):
        d_str = f"{hoje.year}-{hoje.month:02d}-{i:02d}"
        dados_d = historico_limpo.get(d_str, {})
        if dados_d.get("aprovado", 0) + dados_d.get("pendente", 0) + dados_d.get("cancelado", 0) > 0:
            dias_sincronizados = i
            
    faturamento_valido_mes = aprovado_mes + pendente_mes
    estimativa_mensal = 0.0
    
    if dias_sincronizados > 0 and faturamento_valido_mes > 0:
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

        pct_aprov_m = (dados_m['aprovado'] / total_m * 100) if total_m > 0 else 0.0
        pct_pend_m = (dados_m['pendente'] / total_m * 100) if total_m > 0 else 0.0
        pct_canc_m = (dados_m.get('cancelado', 0.0) / total_m * 100) if total_m > 0 else 0.0

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

        pct_aprov_a = (dados_a['aprovado'] / total_a * 100) if total_a > 0 else 0.0
        pct_pend_a = (dados_a['pendente'] / total_a * 100) if total_a > 0 else 0.0
        pct_canc_a = (dados_a.get('cancelado', 0.0) / total_a * 100) if total_a > 0 else 0.0

        texto += f"• <b>{ano}</b>: R$ {f_br(total_a)}{variacao_texto}\n"
        texto += f"  ├ Conf: R$ {f_br(dados_a['aprovado'])} ({dados_a['qtd_aprovado']} pedidos - {pct_aprov_a:.1f}%)\n"
        texto += f"  ├ Pend: R$ {f_br(dados_a['pendente'])} ({dados_a['qtd_pendente']} pedidos - {pct_pend_a:.1f}%)\n"
        texto += f"  └ Canc: R$ {f_br(dados_a.get('cancelado', 0.0))} ({dados_a.get('qtd_cancelado', 0)} pedidos - {pct_canc_a:.1f}%)\n\n"

    texto += (
        "📊 <b>MÉTRICAS DA VARREDURA (Últimos 30 Dias)</b>\n"
        f"• Taxa de Conversão: <b>{taxa_conversao:.1f}%</b>\n"
        f"• Pedidos Totais: {pagos} Pagos | {pendentes} Pendentes | {cancelados} Cancel.\n"
        "<blockquote><i>A Taxa de Conversão indica a porcentagem de pedidos que foram efetivamente PAGOS (Confirmados) em relação ao volume total de pedidos gerados, ajudando a medir a qualidade e o poder de compra do seu tráfego atual.</i></blockquote>\n\n"
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
        texto += f"• ⚖️ Média Diária: <b>R$ {f_br(media_global)}</b>\n"
        
        # ✅ LEGENDA DOS RECORDES DE VOLTA AQUI
        texto += f"<blockquote><i>O seu pico histórico de vendas ocorreu em {melhor_dia_br}, gerando um total de R$ {f_br(todos_totais[melhor_dia_str])}. O objetivo principal das automações é elevar gradativamente a sua Média Diária atual (R$ {f_br(media_global)}) para que os dias de recorde se tornem o novo padrão de recebimento.</i></blockquote>\n\n"

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
        
        pct_aprov_d = (v_aprov / v_tot * 100) if v_tot > 0 else 0.0
        pct_pend_d = (v_pend / v_tot * 100) if v_tot > 0 else 0.0
        pct_canc_d = (v_canc / v_tot * 100) if v_tot > 0 else 0.0
        
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
        
        # ✅ CORES CORRETAS APLICADAS (As suas escolhidas)
        bars = ax1.bar(labels_grafico, valores_comissao, color='#00008B', edgecolor='black', linewidth=0.5, label='Comissão Atual (R$)')
        line_est, = ax1.plot(labels_grafico, valores_estimativa, color='#FF0000', marker='^', linestyle=':', linewidth=2, label='Projeção / Fechamento')
        
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

        # ✅ ORDEM DA LEGENDA CORRIGIDA EXATAMENTE PARA: 1º Pedidos, 2º Projeção, 3º Comissão.
        lines_1, labels_1 = ax1.get_legend_handles_labels() 
        lines_2, labels_2 = ax2.get_legend_handles_labels() 
        
        todos_handles = lines_1 + lines_2
        todos_labels = labels_1 + labels_2
        mapa_legenda = dict(zip(todos_labels, todos_handles))
        
        ordem_desejada = ['Pedidos Gerados', 'Projeção / Fechamento', 'Comissão Atual (R$)']
        
        handles_ordenados = []
        labels_ordenados = []
        for label in ordem_desejada:
            if label in mapa_legenda:
                handles_ordenados.append(mapa_legenda[label])
                labels_ordenados.append(label)

        ax1.legend(handles_ordenados, labels_ordenados, loc='upper left', fontsize=9)

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

# ✅ Handlers para Envio Manual de Mensagens via Botões (Corrigidos com StateFilter)
@dp.message(F.text == "Disparar Bom Dia ☀️", StateFilter("*"))
async def manual_bom_dia(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🚀 Comando recebido: Forçando disparo de Bom Dia.")
    dados_rotina = ler_config_rotina()
    if dados_rotina.get("pausado", False):
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Sistema em pausa.")
        return await message.answer("⚠️ <b>Ação Bloqueada:</b> As rotinas do Canal Principal estão <b>PAUSADAS</b>.", parse_mode="HTML")
    hoje_str = datetime.now(fuso_horario).strftime("%Y-%m-%d")
    if dados_rotina.get("ultimo_bom_dia") == hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Bom Dia já enviado hoje.")
        return await message.answer("⚠️ <b>Bloqueio Anti-Acidente:</b> O 'Bom Dia' de hoje já foi enviado. Ação cancelada.", parse_mode="HTML")
    await message.answer("Gerando e enviando mensagem de Bom Dia... ⏳")
    await disparar_mensagem("bom_dia", forcar=True)
    await message.answer("Mensagem de Bom Dia enviada ao grupo com sucesso! ✅")

@dp.message(F.text == "Disparar Boa Noite 🌙", StateFilter("*"))
async def manual_boa_noite(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🚀 Comando recebido: Forçando disparo de Boa Noite.")
    dados_rotina = ler_config_rotina()
    if dados_rotina.get("pausado", False):
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Sistema em pausa.")
        return await message.answer("⚠️ <b>Ação Bloqueada:</b> As rotinas do Canal Principal estão <b>PAUSADAS</b>.", parse_mode="HTML")
    hoje_str = datetime.now(fuso_horario).strftime("%Y-%m-%d")
    if dados_rotina.get("ultimo_boa_noite") == hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Boa Noite já enviado hoje.")
        return await message.answer("⚠️ <b>Bloqueio Anti-Acidente:</b> O 'Boa Noite' de hoje já foi enviado. Ação cancelada.", parse_mode="HTML")
    await message.answer("Gerando e enviando mensagem de Boa Noite... ⏳")
    await disparar_mensagem("boa_noite", forcar=True)
    await message.answer("Mensagem de Boa Noite enviada ao grupo com sucesso! ✅")

@dp.message(F.text == "Disparar Incentivo 🔥", StateFilter("*"))
async def manual_incentivo(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🚀 Comando recebido: Forçando disparo de Incentivo.")
    dados_rotina = ler_config_rotina()
    if dados_rotina.get("pausado", False):
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Sistema em pausa.")
        return await message.answer("⚠️ <b>Ação Bloqueada:</b> As rotinas do Canal Principal estão <b>PAUSADAS</b>.", parse_mode="HTML")
    hoje_str = datetime.now(fuso_horario).strftime("%Y-%m-%d")
    if dados_rotina.get("ultimo_bom_dia") != hoje_str or dados_rotina.get("ultimo_boa_noite") == hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Fora do expediente permitido.")
        return await message.answer("⚠️ <b>Ação Bloqueada:</b> Dispare esta mensagem apenas durante o expediente.", parse_mode="HTML")
    await message.answer("Gerando e enviando mensagem de Incentivo... ⏳")
    await disparar_mensagem("incentivo", forcar=True)
    await message.answer("Mensagem de Incentivo enviada ao grupo com sucesso! ✅")

@dp.message(F.text == "Disparar Convite do Grupo 🔗", StateFilter("*"))
async def manual_link_grupo(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🚀 Comando recebido: Forçando disparo de Convite do Grupo.")
    dados_rotina = ler_config_rotina()
    if dados_rotina.get("pausado", False):
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Sistema em pausa.")
        return await message.answer("⚠️ <b>Ação Bloqueada:</b> As rotinas do Canal Principal estão <b>PAUSADAS</b>.", parse_mode="HTML")
    hoje_str = datetime.now(fuso_horario).strftime("%Y-%m-%d")
    if dados_rotina.get("ultimo_bom_dia") != hoje_str or dados_rotina.get("ultimo_boa_noite") == hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Fora do expediente permitido.")
        return await message.answer("⚠️ <b>Ação Bloqueada:</b> Dispare esta mensagem apenas durante o expediente.", parse_mode="HTML")
    await message.answer("Gerando e enviando divulgação do grupo... ⏳")
    await disparar_mensagem("link_grupo", forcar=True)
    await message.answer("Mensagem de divulgação enviada ao grupo com sucesso! ✅")

# --- Disparos Manuais (Viral) ---
@dp.message(F.text == "Disparar Convite Viral 🚀", StateFilter("*"))
async def manual_promo_viral(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🚀 Comando recebido: Forçando disparo de Promo Viral.")
    dados_rotina = ler_config_rotina()
    if dados_rotina.get("pausado", False):
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Sistema em pausa.")
        return await message.answer("⚠️ <b>Ação Bloqueada:</b> As rotinas do Canal Principal estão <b>PAUSADAS</b>.", parse_mode="HTML")
    hoje_str = datetime.now(fuso_horario).strftime("%Y-%m-%d")
    if dados_rotina.get("ultimo_bom_dia") != hoje_str or dados_rotina.get("ultimo_boa_noite") == hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Fora do expediente permitido.")
        return await message.answer("⚠️ <b>Ação Bloqueada:</b> Dispare esta mensagem apenas durante o expediente.", parse_mode="HTML")
    await message.answer("Gerando e enviando divulgação do canal parceiro... ⏳")
    await disparar_mensagem("promo_viral", forcar=True)
    await message.answer("Mensagem de Promo Viral enviada ao grupo com sucesso! ✅")

@dp.message(F.text == "Disparar Convite Afiliados 🚀", StateFilter("*"))
async def manual_promo_afiliados(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🚀 Comando recebido: Forçando disparo de Convite Afiliados.")
    dados_rotina = ler_config_rotina()
    if dados_rotina.get("pausado_viral", False):
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Sistema Viral em pausa.")
        return await message.answer("⚠️ <b>Ação Bloqueada:</b> As rotinas do Canal Viral estão <b>PAUSADAS</b>.", parse_mode="HTML")
    await message.answer("Gerando e enviando divulgação do canal de afiliados... ⏳")
    await disparar_mensagem("promo_principal", forcar=True)
    await message.answer("Propaganda do canal de afiliados enviada ao canal viral com sucesso! ✅")

@dp.message(F.text == "Disparar Convite do Grupo 🔗\u200b", StateFilter("*"))
async def manual_convite_viral(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🚀 Comando recebido: Forçando disparo de Convite do Grupo (Viral).")
    dados_rotina = ler_config_rotina()
    if dados_rotina.get("pausado_viral", False):
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Sistema Viral em pausa.")
        return await message.answer("⚠️ <b>Ação Bloqueada:</b> As rotinas do Canal Viral estão <b>PAUSADAS</b>.", parse_mode="HTML")
    await message.answer("Gerando e enviando convite do canal viral... ⏳")
    await disparar_mensagem("link_grupo_viral", forcar=True)
    await message.answer("Convite de recrutamento enviado ao canal viral com sucesso! ✅")

@dp.message(F.text == "Disparar Prompt GEM 🤖\u200b", StateFilter("*"))
async def manual_prompt_gem_viral(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🚀 Comando recebido: Forçando disparo de Prompt GEM (Viral).")
    dados_rotina = ler_config_rotina()
    if dados_rotina.get("pausado_viral", False):
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Sistema Viral em pausa.")
        return await message.answer("⚠️ <b>Ação Bloqueada:</b> As rotinas do Canal Viral estão <b>PAUSADAS</b>.", parse_mode="HTML")
    await message.answer("Gerando e enviando Prompt GEM para o canal viral... ⏳")
    await disparar_mensagem("divulgar_gem_viral", forcar=True)
    await message.answer("Prompt GEM enviado ao canal viral com sucesso! ✅")

@dp.message(F.text == "Disparar Promo Público 👥", StateFilter("*"))
async def manual_promo_publico_viral(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🚀 Comando recebido: Forçando disparo de Promo Público (Viral).")
    dados_rotina = ler_config_rotina()
    if dados_rotina.get("pausado_viral", False):
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Sistema Viral em pausa.")
        return await message.answer("⚠️ <b>Ação Bloqueada:</b> As rotinas do Canal Viral estão <b>PAUSADAS</b>.", parse_mode="HTML")
    await message.answer("Gerando e enviando divulgação do Grupo Público para o canal viral... ⏳")
    await disparar_mensagem("promo_publico_viral", forcar=True)
    await message.answer("Divulgação enviada ao canal viral com sucesso! ✅")

# --- Disparos Manuais (Grupo Público) ---
@dp.message(F.text == "Disparar Promo Público 🗣️", StateFilter("*"))
async def manual_promo_publico(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    dados_rotina = ler_config_rotina()
    if dados_rotina.get("pausado", False):
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Sistema em pausa.")
        return await message.answer("⚠️ <b>Ação Bloqueada:</b> As rotinas do Canal Principal estão <b>PAUSADAS</b>.", parse_mode="HTML")
    hoje_str = datetime.now(fuso_horario).strftime("%Y-%m-%d")
    if dados_rotina.get("ultimo_bom_dia") != hoje_str or dados_rotina.get("ultimo_boa_noite") == hoje_str:
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Fora do expediente permitido.")
        return await message.answer("⚠️ <b>Ação Bloqueada:</b> Dispare esta mensagem apenas durante o expediente.", parse_mode="HTML")
    await message.answer("Gerando e enviando divulgação do Grupo Público... ⏳")
    await disparar_mensagem("promo_publico", forcar=True)
    await message.answer("Mensagem de Promo Público enviada ao grupo com sucesso! ✅")

# ✅ NOVO: Disparos manuais do Público agora exigem confirmação em duas etapas
MAPA_DISPAROS_PUBLICO = {
    "Disparar Convite (Próprio) 🔗": ("link_grupo_publico", "Convite (Próprio Grupo) 🔗", "convite para o próprio Grupo Público"),
    "Disparar Promo Principal 🌟": ("promo_principal_publico", "Promo Canal Principal 🌟", "divulgação do Canal Principal"),
    "Disparar Promo Viral 💥": ("promo_viral_publico", "Promo Canal Viral 💥", "divulgação do Canal Viral")
}

@dp.message(F.text.in_(list(MAPA_DISPAROS_PUBLICO.keys())), StateFilter("*"))
async def pedir_confirmacao_disparo_publico(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return

    dados_rotina = ler_config_rotina()
    if dados_rotina.get("pausado_publico", False):
        if EXIBIR_LOGS: logger.warning("🛑 Disparo bloqueado: Sistema Público em pausa.")
        return await message.answer("⚠️ <b>Ação Bloqueada:</b> As rotinas do Grupo Público estão <b>PAUSADAS</b>.", parse_mode="HTML")

    tipo, nome_amigavel, descricao = MAPA_DISPAROS_PUBLICO[message.text]
    await state.update_data(tipo_disparo_publico=tipo, nome_disparo_publico=nome_amigavel, menu_origem="publico")

    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Confirmar Disparo ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )

    texto = (
        f"⚠️ Tem certeza de que deseja <b>DISPARAR AGORA</b> a rotina <b>{nome_amigavel}</b>?\n\n"
        f"<i>(A mensagem de {descricao} será gerada pela IA e enviada imediatamente aos tópicos configurados do Grupo Público)</i>"
    )
    if EXIBIR_LOGS: logger.info(f"🛡️ Disparo manual '{tipo}' interceptado. Aguardando confirmação do administrador...")
    await message.answer(texto, reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(ConfigRotina.aguardando_confirmacao_disparo)

@dp.message(ConfigRotina.aguardando_confirmacao_disparo)
async def processar_disparo_publico(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return

    if message.text == "Cancelar ❌":
        if EXIBIR_LOGS: logger.info("❌ Disparo manual do Público abortado pelo administrador.")
        await message.answer("Ação cancelada. Nenhuma mensagem foi enviada.")
        await state.update_data(menu_origem="publico")
        await state.set_state(ConfigRotina.menu_principal)
        await submenu_disparos_manuais(message, state)
        return

    if message.text != "Confirmar Disparo ✅":
        await message.answer("Por favor, clique em Confirmar Disparo ✅ ou Cancelar ❌.")
        return

    dados = await state.get_data()
    tipo = dados.get("tipo_disparo_publico")
    nome_amigavel = dados.get("nome_disparo_publico", "Rotina")

    if not tipo:
        await message.answer("⚠️ Sessão expirada. Selecione novamente o disparo desejado.")
        await state.update_data(menu_origem="publico")
        await state.set_state(ConfigRotina.menu_principal)
        await submenu_disparos_manuais(message, state)
        return

    await message.answer(f"⏳ Gerando e enviando <b>{nome_amigavel}</b>...", parse_mode="HTML")
    await disparar_mensagem(tipo, forcar=True)
    if EXIBIR_LOGS: logger.info(f"🚀 Disparo manual confirmado e executado: {tipo}")
    await message.answer(f"✅ <b>{nome_amigavel}</b> enviada ao Grupo Público com sucesso!", parse_mode="HTML")

    await state.update_data(menu_origem="publico")
    await state.set_state(ConfigRotina.menu_principal)
    await submenu_disparos_manuais(message, state)

# ✅ NOVO: Gestão dos alvos (tópicos) que recebem as rotinas do Grupo Público
@dp.message(ConfigRotina.menu_principal, F.text == "Gerenciar Alvos de Postagem 🎯")
async def pedir_alvos_rotina_publico(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🎯 Acessando gestão de alvos das rotinas do Grupo Público...")

    config_sub = ler_submissao_config()
    grupo_id_str = str(config_sub.get("grupo_id") or "")
    topicos_rotina = config_sub.get("topicos_rotina", [])
    cache_nomes = ler_cache_nomes_grupos()

    if topicos_rotina:
        linhas = []
        for t in topicos_rotina:
            chave = f"{grupo_id_str}_{t}"
            nome = cache_nomes.get(chave) or ("Geral" if str(t) == "1" else f"Tópico {t}")
            linhas.append(f"   ✅ {nome} (<code>{chave}</code>)")
        atual = "\n".join(linhas)
    else:
        atual = "   ✅ <i>Chat Geral (Padrão)</i>"

    texto = (
        "🎯 <b>Gerenciar Alvos de Postagem</b>\n\n"
        "Aqui você define <b>em quais tópicos do Grupo Público</b> as mensagens automáticas de divulgação "
        "serão publicadas (Convite ao Grupo, Promo Canal Principal e Promo Canal Viral).\n\n"
        f"📢 <b>Ativos hoje:</b>\n{atual}\n\n"
        "Envie a <b>nova lista</b> de tópicos ativos (ela substitui a atual):\n"
        "• Apenas um: <code>6</code>\n"
        "• Vários: <code>1, 6</code>\n"
        "• O link do tópico no Telegram também funciona\n\n"
        "Para desativar todos e publicar somente no Chat Geral, digite <b>0</b>."
    )
    await message.answer(texto, parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.update_data(menu_origem="publico")
    await state.set_state(ConfigRotina.aguardando_alvos_rotina)

@dp.message(ConfigRotina.aguardando_alvos_rotina)
async def confirmar_alvos_rotina_publico(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return

    if message.text == "Cancelar ❌":
        if EXIBIR_LOGS: logger.info("❌ Edição dos alvos de postagem cancelada.")
        await message.answer("Ação cancelada. Nenhum alvo foi alterado.")
        await gerenciar_rotina_publico(message, state)
        return

    texto_usuario = (message.text or "").strip()

    if texto_usuario == "0":
        topicos_finais = []
    else:
        topicos_finais = []
        for entrada in [t.strip() for t in texto_usuario.split(",")]:
            if not entrada: continue
            if "t.me/" in entrada:
                partes = entrada.split("/")
                if len(partes) >= 5: topicos_finais.append(partes[-1])
            elif "_" in entrada: topicos_finais.append(entrada.split("_")[-1])
            elif ":" in entrada: topicos_finais.append(entrada.split(":")[-1])
            elif entrada.isdigit():
                if entrada != "0": topicos_finais.append(entrada)

        if not topicos_finais:
            await message.answer("⚠️ Não identifiquei nenhum tópico válido. Envie os números separados por vírgula (Ex: <code>1, 6</code>) ou <b>0</b> para o Chat Geral.", parse_mode="HTML", reply_markup=teclado_cancelar)
            return

    await state.update_data(novos_alvos_rotina=topicos_finais)
    resumo = ", ".join(topicos_finais) if topicos_finais else "Chat Geral (Padrão)"

    teclado_conf = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True, is_persistent=True
    )
    await message.answer(
        f"🎯 As rotinas do Grupo Público passarão a ser publicadas em: <code>{resumo}</code>\n\n"
        "<i>(Os nomes reais dos tópicos serão sincronizados em background pelo Userbot)</i>\n\n"
        "Deseja confirmar esta alteração?",
        parse_mode="HTML", reply_markup=teclado_conf
    )
    await state.set_state(ConfigRotina.aguardando_confirmacao_alvos_rotina)

@dp.message(ConfigRotina.aguardando_confirmacao_alvos_rotina)
async def salvar_alvos_rotina_publico(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return

    if message.text == "Cancelar ❌":
        await message.answer("Ação cancelada. Nenhum alvo foi alterado.")
        await gerenciar_rotina_publico(message, state)
        return

    if message.text != "Aprovar ✅":
        await message.answer("Por favor, clique em Aprovar ✅ ou Cancelar ❌.")
        return

    dados_state = await state.get_data()
    novos_alvos = dados_state.get("novos_alvos_rotina", [])

    config = ler_submissao_config()
    config["topicos_rotina"] = novos_alvos
    salvar_submissao_config(config)

    if EXIBIR_LOGS: logger.info(f"🎯 Alvos das rotinas do Público atualizados para: {novos_alvos or 'Chat Geral'}")
    await message.answer("✅ <b>Alvos de postagem atualizados com sucesso!</b>", parse_mode="HTML")
    await gerenciar_rotina_publico(message, state)

@dp.message(F.text == "Disparar Repost Autoral ♻️", StateFilter("*"))
async def manual_repost_autoral(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    config_pub = ler_submissao_config()
    
    # ✅ Puxa a flexibilidade de roteamento
    grupo_id_base = config_pub.get("grupo_id")
    topico_destino_base = config_pub.get("topico_destino")
    repost_destino = config_pub.get("repost_destino")
    
    if repost_destino:
        if ":" in str(repost_destino):
            chat_destino = str(repost_destino).split(":")[0]
            topico_vitrine = int(str(repost_destino).split(":")[1])
        else:
            chat_destino = str(repost_destino)
            topico_vitrine = None
    else:
        chat_destino = grupo_id_base
        topico_vitrine = topico_destino_base
    
    if not config_pub.get("ativo") or not chat_destino:
        await message.answer("⚠️ <b>Ação Bloqueada:</b> O Painel do Grupo Público está desativado ou não possui um destino configurado.", parse_mode="HTML")
        return
        
    msg_status = await message.answer("♻️ Extraindo um vídeo legível do Canal Autoral...", parse_mode="HTML")
    
    try:
        conexao = sqlite3.connect("banco_dados.db")
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()
        
        # ✅ CORREÇÃO: Garante que ele não reposte manualmente algo que já foi pelo automático
        cursor.execute("SELECT * FROM fila_autorais WHERE processado = 1 AND repostado_publico = 0 ORDER BY id_unico DESC LIMIT 30")
        autorais_recentes = cursor.fetchall()
    except Exception as e:
        await msg_status.edit_text(f"❌ Erro ao ler banco de autorais: {e}")
        return
        
    if not autorais_recentes:
        await msg_status.edit_text("❌ Não há vídeos recentes ou disponíveis que ainda não tenham sido postados no Público.")
        conexao.close()
        return
        
    import random
    video_sorteado = random.choice(autorais_recentes)
    file_id = video_sorteado["msg_id_destino"] 
    id_unico = video_sorteado["id_unico"]
    
    if not file_id:
        await msg_status.edit_text("❌ Erro: O vídeo sorteado não tem um File ID válido na nuvem.")
        conexao.close()
        return
        
    nomes_fakes = ["Rafael", "Membro VIP", "Shopee Afiliado", "Dicas da Comunidade", "Ofertas Top"]
    user_mention = random.choice(nomes_fakes)
    
    legenda_original = video_sorteado["legenda"]
    import re
    match_link = re.search(r'(?:https?://)?(?:s\.shopee\.com\.br|shope\.ee|br\.shp\.ee|shp\.ee)/[^\s<]+', legenda_original, re.IGNORECASE)
    link_shopee = match_link.group(0) if match_link else "https://shopee.com.br"
    
    match_item = re.search(r'📦\s*Item:\s*([^\n<]+)', legenda_original)
    nome_produto = match_item.group(1).strip() if match_item else "Produto Exclusivo"

    legenda_final = (
        f"👤 Dica enviada por: {user_mention}\n\n"
        f"<b>{nome_produto}</b>\n\n"
        f"🔗 <b>Link do Produto:</b>\n{link_shopee}\n\n"
        f"<i>#Recomendado #Shopee</i>"
    )
    
    try:
        # ✅ NOVO: Tenta usar a origem personalizada. Se não tiver, usa a dos Autorais.
        canal_autorais = config_pub.get("repost_origem")
        if not canal_autorais:
            config_aut = ler_config_bd("autorais_config", {})
            canal_autorais = config_aut.get("destino")
        
        kwargs = {}
        if topico_vitrine: 
            kwargs["message_thread_id"] = int(topico_vitrine)
        
        await bot.copy_message(
            chat_id=chat_destino,
            from_chat_id=canal_autorais,
            message_id=int(file_id),
            caption=legenda_final,
            parse_mode="HTML",
            **kwargs
        )
        
        # Marca como repostado para garantir a integridade da fila autônoma
        agora_str = datetime.now(fuso_horario).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE fila_autorais SET repostado_publico = 1, data_repost_publico = ? WHERE id_unico = ?", (agora_str, id_unico))
        conexao.commit()
        
        await msg_status.edit_text("✅ <b>Repost Autoral realizado!</b>\nUm vídeo foi puxado e enviado formatado para o Tópico de Postagem do Grupo Público.", parse_mode="HTML")
        if EXIBIR_LOGS: logger.info(f"✅ Disparo de repost manual executado com sucesso: {nome_produto}")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao dar copy_message no repost manual: {e}")
        await msg_status.edit_text(f"❌ Erro técnico ao tentar enviar o vídeo: {e}")
        
    conexao.close()

# ❌ NOVO: Handler Global para Cancelar via Botão (Agora 100% à prova de falhas)
@dp.message(F.text == "Cancelar ❌", StateFilter("*"))
async def cancelar_fluxo_global(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    estado_atual = await state.get_state()
    if EXIBIR_LOGS: logger.info(f"❌ Ação cancelada via botão. Estado anterior: {estado_atual}")

    data = await state.get_data()

    # 🔁 Roteamento Inteligente: Se estiver na CONFIRMAÇÃO de Limpeza, volta para a SELEÇÃO de Limpeza
    if estado_atual == "ConfigFluxo:aguardando_acao_limpeza":
        if EXIBIR_LOGS: logger.info("🔙 Cancelamento: Voltando à seleção de limpeza de filas.")
        await message.answer("Ação cancelada. Retornando ao menu de limpeza...")
        await menu_zerar_filas_tarefas(message, state)
        return
        
    # 🔁 Roteamento Inteligente: Se cancelar da seleção de limpeza ou do reinício, volta pro painel de Servidor
    if estado_atual in ["ConfigFluxo:aguardando_selecao_limpeza", "ConfigFluxo:aguardando_confirmacao_reiniciar"]:
        await state.clear()
        await message.answer("Ação cancelada. Nenhuma alteração foi feita no servidor.", reply_markup=obter_teclado_opcoes_servidor())
        return
        
    # 🔁 Roteamento Inteligente: Se estiver no Gerenciador de Fila
    if estado_atual and estado_atual.startswith("GerenciarFilaFluxo"):
        await state.clear()
        await message.answer("Ação cancelada.")
        await menu_gerenciar_fila(message, state)
        return
        
    # 🔁 Roteamento Inteligente: Se estiver no Espião (Grupos Vigiados ou Configurando Tempos)
    if estado_atual == "EspiaoFluxo:aguardando_confirmacao_forcar_clones":
        await state.clear()
        await message.answer("Ação cancelada.")
        await menu_espiao_principal(message, state)
        return

    estados_espiao_vigiados = [
        "EspiaoFluxo:aguardando_novo_alvo",
        "EspiaoFluxo:aguardando_confirmacao_alvo", # ✅ O estado que falhou no seu vídeo!
        "EspiaoFluxo:aguardando_remocao_alvo",
        "EspiaoFluxo:aguardando_confirmacao_remocao",
        "EspiaoFluxo:aguardando_canal_destino",
        "EspiaoFluxo:aguardando_confirmacao_destino",
        "EspiaoFluxo:aguardando_acao_blacklist",
        "EspiaoFluxo:aguardando_blacklist_add",
        "EspiaoFluxo:aguardando_blacklist_remove",
        "EspiaoFluxo:aguardando_confirmacao_blacklist_conflito",
        "EspiaoFluxo:aguardando_acao_analise"
    ]
    
    if estado_atual and (estado_atual in estados_espiao_vigiados or estado_atual.startswith("ConfigRotinaEspiao")):
        await state.clear()
        await message.answer("Ação cancelada. Retornando aos Grupos Vigiados.")
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

    # 🔁 Roteamento Inteligente: Se estiver no Disparador de Notas
    if estado_atual and estado_atual.startswith("PainelNotasFluxo"):
        import painel_notas
        await message.answer("Ação cancelada. Voltando ao menu do disparador...", reply_markup=painel_notas.obter_teclado_menu_notas())
        await state.set_state(painel_notas.PainelNotasFluxo.menu_principal)
        return

    # 🔁 Roteamento Inteligente: Se estiver em Vídeos Autorais
    if estado_atual and estado_atual.startswith("AutoraisFluxo"):
        await state.clear()
        await message.answer("Ação cancelada.")
        
        # Verifica se estava editando Dias, Limites ou Janela para voltar ao SUBMENU de Retorno
        if estado_atual in ["AutoraisFluxo:aguardando_dias_retorno", "AutoraisFluxo:aguardando_limite_videos", "AutoraisFluxo:aguardando_confirmacao_dias_retorno", "AutoraisFluxo:aguardando_confirmacao_limite_videos", "AutoraisFluxo:aguardando_janela_autorais", "AutoraisFluxo:aguardando_confirmacao_janela_autorais"]:
            await submenu_regras_retorno(message, state)
            
        # Verifica se estava confirmando Pausas para voltar ao SUBMENU de Status
        elif estado_atual in ["AutoraisFluxo:aguardando_confirmacao_pausa_repost", "AutoraisFluxo:aguardando_confirmacao_pausa_robo"]:
            await submenu_status_robo(message, state)
            
        else:
            # Caso contrário (origem/destino), volta pro menu principal dos Autorais
            await painel_autorais(message, state)
            
        return
        
    # 🔁 Roteamento Inteligente: Se estiver nas Rotinas
    if estado_atual and estado_atual.startswith("ConfigRotina"):
        menu_orig = data.get('menu_origem')
        tipo_edicao = data.get('tipo_edicao')
        await state.clear()
        if EXIBIR_LOGS: logger.info("🔙 Cancelando configuração de rotina e redirecionando ao menu correto.")
        await message.answer("Ação cancelada.")

        # ✅ NOVO: cancelar a edição de uma rotina devolve ao submenu "Editar Rotinas",
        # e não ao menu raiz, preservando o contexto de edição.
        if estado_atual == "ConfigRotina:aguardando_novo_horario":
            if not menu_orig:
                if tipo_edicao in ["promo_principal", "link_grupo_viral", "divulgar_gem_viral", "promo_publico_viral"]:
                    menu_orig = "espiao"
                elif tipo_edicao in ["link_grupo_publico", "promo_principal_publico", "promo_viral_publico"]:
                    menu_orig = "publico"
                else:
                    menu_orig = "principal"
            await state.update_data(menu_origem=menu_orig)
            await state.set_state(ConfigRotina.menu_principal)
            await submenu_editar_rotinas(message, state)
            return

        if menu_orig == "espiao" or tipo_edicao in ["promo_principal", "link_grupo_viral", "divulgar_gem_viral", "promo_publico_viral"]:
            await gerenciar_rotina_espiao(message, state)
        elif menu_orig == "publico" or tipo_edicao in ["link_grupo_publico", "promo_principal_publico", "promo_viral_publico"]:
            await gerenciar_rotina_publico(message, state)
        else:
            await gerenciar_rotina(message, state)
        return

    # 🔁 Roteamento Inteligente: Cancelamento do toggle do Moderador volta ao submenu de origem
    if estado_atual == "SubmissaoAdminFluxo:aguardando_confirmacao_toggle":
        await state.clear()
        if EXIBIR_LOGS: logger.info("🔙 Cancelamento do toggle do Moderador. Retornando ao submenu de Configurações do Robô Moderador.")
        await message.answer("Ação cancelada.")
        await submenu_robo_moderador(message, state)
        return

    # 🔁 Roteamento Inteligente: Cancelamento na edição de um tópico volta ao menu de tópicos
    if estado_atual in ["SubmissaoAdminFluxo:aguardando_novo_valor_grupo", "SubmissaoAdminFluxo:aguardando_confirmacao_grupo"]:
        await state.clear()
        if EXIBIR_LOGS: logger.info("🔙 Cancelamento da edição de tópico. Retornando ao menu Definir Tópicos de Moderação.")
        await message.answer("Ação cancelada.")
        await menu_edicao_grupo_publico(message, state)
        return

    # 🔁 Roteamento Inteligente: Se estiver nas Submissões do Público
    if estado_atual and estado_atual.startswith("SubmissaoAdminFluxo"):
        await state.clear()
        if EXIBIR_LOGS: logger.info("🔙 Cancelamento do Painel de Submissões. Retornando ao painel do Grupo Público.")
        await message.answer("Ação cancelada.")
        await painel_submissoes(message, state) # ✅ CORREÇÃO: Agora volta para o painel correto
        return

    # 🔁 Roteamento Inteligente: Se estiver na Pausa Programada
    if estado_atual and estado_atual.startswith("PausaProgramadaFluxo"):
        await state.clear()
        if EXIBIR_LOGS: logger.info("🔙 Cancelamento da Pausa Programada. Voltando para Configurações Avançadas.")
        await message.answer("Ação cancelada. Retornando ao menu de configurações...")
        await menu_configuracoes(message, state)
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

@dp.message(F.text == "🔄 Atualizar Rotinas", StateFilter("*"))
async def resetar_expediente(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    if EXIBIR_LOGS: logger.info("🔄 Acionado o Recálculo Inteligente de Rotinas...")
    msg_status = await message.answer("🔄 Analisando o histórico de hoje e recalculando a grade restante. Aguarde...", reply_markup=teclado_cancelar)
    
    # --- 1. FOTO DO ANTES (Captura o estado atual da memória) ---
    jobs_antes = {}
    for job in scheduler.get_jobs():
        if getattr(job, 'next_run_time', None):
            jobs_antes[job.id] = job.next_run_time.astimezone(fuso_horario).strftime("%H:%M")

    # --- 2. EXECUTA O RECÁLCULO ---
    agendar_tarefas_diarias(escopo="principal")
    
    # --- 3. FOTO DO DEPOIS (Captura o novo estado da memória) ---
    jobs_depois = {}
    for job in scheduler.get_jobs():
        if getattr(job, 'next_run_time', None):
            jobs_depois[job.id] = job.next_run_time.astimezone(fuso_horario).strftime("%H:%M")

    await msg_status.delete()
    
    # --- 4. CONSTRUÇÃO DO PAINEL VISUAL ORDENADO ---
    texto = "🔄 <b>Grade Recalculada com Sucesso!</b>\n\n"
    texto += "Aqui está o relatório do que mudou no seu dia:\n\n"
    
    mudancas_rotinas = []
    mudancas_videos = []
    
    # Compara o Antes e o Depois
    for job_id, hora_nova in jobs_depois.items():
        hora_antiga = jobs_antes.get(job_id)
        
        # Avalia se a hora mudou ou se é um item totalmente novo
        if hora_antiga != hora_nova:
            marcador_tempo = f"{hora_antiga} ➡️ {hora_nova}" if hora_antiga else f"Novo Encaixe ➡️ {hora_nova}"
            
            if "rotina" in job_id or "campanha" in job_id:
                import re
                match = re.search(r'job_(?:rotina|campanha)_(.+)_(\d+)$', job_id)
                
                if match:
                    nome_base = match.group(1).replace("_", " ").title()
                    indice = int(match.group(2))
                    
                    if nome_base.lower() in ["bom dia", "boa noite"]:
                        nome_amigavel = nome_base
                    else:
                        nome_amigavel = f"{nome_base} ({indice + 1}º Envio)"
                else:
                    if job_id.startswith("job_campanha_"):
                        turno = job_id.split("_")[-1].title()
                        nome_amigavel = f"Aviso de Campanha ({turno})"
                    else:
                        nome_amigavel = job_id.replace("job_rotina_", "").replace("job_campanha_", "").replace("_", " ").title()
                        
                # Guarda na lista como uma tupla (hora_nova, texto_formatado) para ordenarmos depois
                mudancas_rotinas.append((hora_nova, f"🔹 <b>{nome_amigavel}:</b> {marcador_tempo}"))
                
            elif "fila_postagem" in job_id:
                # Faz um resgate cirúrgico no SQLite para descobrir o Número Visual do Vídeo
                id_unico = job_id.replace("job_fila_postagem_", "")
                nome_video = f"Vídeo {id_unico[:4]}"
                try:
                    import sqlite3, re
                    conexao = sqlite3.connect("banco_dados.db")
                    cursor = conexao.cursor()
                    cursor.execute("SELECT legenda FROM fila_postagens WHERE id_unico = ?", (id_unico,))
                    res = cursor.fetchone()
                    if res:
                        match = re.search(r'(?i)Vídeo\s+\d+', res[0])
                        if match: nome_video = match.group(0).title()
                    conexao.close()
                except: pass
                
                mudancas_videos.append((hora_nova, f"📦 <b>{nome_video}:</b> {marcador_tempo}"))
                
    # ✅ ORDENAÇÃO CRONOLÓGICA INTELIGENTE (Do mais cedo para o mais tarde)
    mudancas_rotinas.sort(key=lambda x: x[0])
    mudancas_videos.sort(key=lambda x: x[0])
    
    if mudancas_rotinas:
        texto += "⏰ <b>Rotinas e Avisos (Por Horário):</b>\n" + "\n".join([item[1] for item in mudancas_rotinas]) + "\n\n"
    if mudancas_videos:
        texto += "🎬 <b>Fila de Vídeos (Por Horário):</b>\n" + "\n".join([item[1] for item in mudancas_videos]) + "\n\n"
        
    if not mudancas_rotinas and not mudancas_videos:
        texto += "<i>Nenhuma mudança de horário ocorreu neste recálculo.</i>\n\n"
        
    texto += "✅ <b>Tudo pronto para rodar!</b>"

    await message.answer(texto, parse_mode="HTML", reply_markup=obter_teclado_principal())
    await state.clear()

@dp.message(F.text == "Zerar Filas e Tarefas 🧹", StateFilter("*"))
async def menu_zerar_filas_tarefas(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("⚠️ Solicitando seleção do tipo de limpeza de filas.")
    
    teclado_opcoes_limpeza = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Limpar Tudo (Geral) 💥")],
            [KeyboardButton(text="Limpar Fila do Espião 🕵️"), KeyboardButton(text="Limpar Fila Espelhador 🔄")],
            [KeyboardButton(text="Limpar Fila Autorais 🎥"), KeyboardButton(text="Cancelar ❌")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    
    texto = (
        "🧹 <b>CENTRAL DE LIMPEZA DO SERVIDOR</b>\n\n"
        "Escolha qual módulo você deseja esvaziar. As suas configurações do robô (textos, horários, alvos) <b>nunca</b> são apagadas.\n\n"
        "🛡️ <i>Nota: A Fila Principal (SQLite) está protegida e nunca será apagada por este menu.</i>\n\n"
        "👉 <b>Fila Espião:</b> Apaga clones retidos no radar e exclui os arquivos de vídeo do servidor.\n"
        "👉 <b>Fila Espelhador:</b> Apaga a repassagem de vídeos pendentes e seus respectivos arquivos.\n"
        "👉 <b>Fila Autorais:</b> Apaga os vídeos de retorno pendentes no banco de dados e arquivos físicos.\n"
        "👉 <b>Geral:</b> Esvazia o Espião, Espelhador, Autorais, apaga o lixo temporário, exclui backups e limpa logs do Ubuntu."
    )
    await message.answer(texto, reply_markup=teclado_opcoes_limpeza, parse_mode="HTML")
    await state.set_state(ConfigFluxo.aguardando_selecao_limpeza)

@dp.message(ConfigFluxo.aguardando_selecao_limpeza)
async def pedir_confirmacao_acao_limpeza(message: types.Message, state: FSMContext):
    opcoes_validas = [
        "Limpar Tudo (Geral) 💥", "Limpar Fila do Espião 🕵️", "Limpar Fila Espelhador 🔄", "Limpar Fila Autorais 🎥"
    ]

    if message.text == "Cancelar ❌":
        await cancelar_fluxo_global(message, state)
        return
        
    if message.text not in opcoes_validas:
        await message.answer("Por favor, utilize os botões abaixo para escolher a limpeza.")
        return

    await state.update_data(tipo_limpeza=message.text)

    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar Exclusão ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )

    await message.answer(f"⚠️ <b>Atenção:</b> Você está prestes a executar a operação: <b>{message.text}</b>.\n\nEsta ação apagará arquivos físicos e limpará a fila selecionada. Deseja continuar?", reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(ConfigFluxo.aguardando_acao_limpeza)

@dp.message(ConfigFluxo.aguardando_acao_limpeza)
async def processar_zerar_filas_tarefas(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await cancelar_fluxo_global(message, state)
        return
        
    if message.text != "Aprovar Exclusão ✅":
        await message.answer("Por favor, utilize os botões para aprovar ou cancelar a exclusão.")
        return

    data = await state.get_data()
    tipo_limpeza = data.get("tipo_limpeza")

    msg_status = await message.answer(f"🧹 <b>Executando: {tipo_limpeza}...</b> Isso pode levar alguns segundos. ⏳", reply_markup=teclado_cancelar, parse_mode="HTML")
    if EXIBIR_LOGS: logger.info(f"🚀 Iniciando protocolo de limpeza modular: {tipo_limpeza}")
    
    limpar_tudo = tipo_limpeza == "Limpar Tudo (Geral) 💥"
    limpar_espiao = tipo_limpeza == "Limpar Fila do Espião 🕵️" or limpar_tudo
    limpar_espelhador = tipo_limpeza == "Limpar Fila Espelhador 🔄" or limpar_tudo
    limpar_autorais = tipo_limpeza == "Limpar Fila Autorais 🎥" or limpar_tudo

    relatorio = {
        "espiao": 0,
        "espelhador": 0,
        "autorais": 0,
        "arquivos": 0,
        "espaco_mb": 0.0
    }

    def apagar_arquivo(caminho):
        if caminho and os.path.exists(caminho):
            try:
                tamanho = os.path.getsize(caminho) / (1024 * 1024)
                os.remove(caminho)
                relatorio["arquivos"] += 1
                relatorio["espaco_mb"] += tamanho
            except: pass

    # 1. Limpar Fila do Espião
    if limpar_espiao:
        try:
            fila_clonagem = ler_fila_clonagem()
            mantidos_espiao = []
            for item in fila_clonagem.get("fila", []):
                if item.get("processado") in [True, 1, "true", "True"]:
                    mantidos_espiao.append(item)
                else:
                    apagar_arquivo(item.get("caminho_video"))
                    relatorio["espiao"] += 1
            fila_clonagem["fila"] = mantidos_espiao
            salvar_fila_clonagem(fila_clonagem)
        except Exception as e:
            pass
            
    # 2. Limpar Fila do Espelhador
    if limpar_espelhador:
        try:
            with open("fila_espelhador.json", "r", encoding="utf-8") as f:
                fila_espelhador = json.load(f)
            mantidos_espelhador = []
            for item in fila_espelhador.get("fila", []):
                if item.get("processado") in [True, 1, "true", "True"]:
                    mantidos_espelhador.append(item)
                else:
                    apagar_arquivo(item.get("caminho_video"))
                    relatorio["espelhador"] += 1
            fila_espelhador["fila"] = mantidos_espelhador
            with open("fila_espelhador.json", "w", encoding="utf-8") as f:
                json.dump(fila_espelhador, f, indent=4)
        except Exception as e:
            pass

    # 3. Limpar Fila de Autorais
    if limpar_autorais:
        try:
            conexao = sqlite3.connect("banco_dados.db")
            cursor = conexao.cursor()
            
            cursor.execute("SELECT caminho_arquivo FROM fila_autorais WHERE processado = 0")
            para_apagar = cursor.fetchall()
            for item in para_apagar:
                apagar_arquivo(item[0])
                relatorio["autorais"] += 1
                
            cursor.execute("DELETE FROM fila_autorais WHERE processado = 0")
            conexao.commit()
            conexao.close()
        except Exception as e:
            pass

    # 4. Faxina Cega na Pasta Temp
    try:
        if os.path.exists("temp"):
            for filename in os.listdir("temp"):
                caminho_completo = os.path.join("temp", filename)
                if os.path.isfile(caminho_completo):
                    apagar_arquivo(caminho_completo)
    except Exception as e:
        pass

    # 5. Apagar arquivos de backup (.bkp) na raiz
    if limpar_tudo:
        try:
            for filename in os.listdir("."):
                if filename.endswith(".bkp") and os.path.isfile(filename):
                    apagar_arquivo(filename)
        except Exception as e:
            pass

    # 6. Limpeza de Logs do Servidor Linux
    status_ubuntu = "Não executada"
    if limpar_tudo:
        try:
            comando_linux = await asyncio.create_subprocess_exec(
                "sudo", "journalctl", "--vacuum-time=2d",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await comando_linux.communicate()
            if comando_linux.returncode == 0:
                status_ubuntu = "✅ Concluída (Mantendo últimos 2 dias)"
            else:
                status_ubuntu = "⚠️ Falha de permissão (sudo)"
        except Exception as e:
            status_ubuntu = "❌ Erro ao acessar terminal"

    await msg_status.delete()
    
    texto_final = (
        "✨ <b>Operação Concluída!</b>\n\n"
        "Relatório de eliminação:\n"
        f"🗑️ <b>{relatorio['espiao']}</b> clones do Espião\n"
        f"🗑️ <b>{relatorio['espelhador']}</b> itens do Espelhador\n"
        f"🗑️ <b>{relatorio['autorais']}</b> vídeos de Autorais\n"
        f"🧹 <b>{relatorio['arquivos']}</b> ficheiros físicos temporários apagados\n"
        f"💾 <b>{relatorio['espaco_mb']:.2f} MB</b> liberados no servidor!\n"
    )
    
    if limpar_tudo:
        texto_final += f"\n🖥️ <b>Limpeza do SO:</b>\nLogs do Ubuntu: {status_ubuntu}\n"
        
    texto_final += "\nO seu ambiente de trabalho está atualizado."
    
    # ✅ CORREÇÃO MESTRE: Exibe a mensagem de sucesso e puxa o menu de limpeza novamente
    await message.answer(texto_final, parse_mode="HTML")
    await menu_zerar_filas_tarefas(message, state)

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
    
    # 1. Obter quantidade de vídeos pendentes na fila (✅ BLINDADO)
    fila_data = ler_fila_clonagem()
    fila = fila_data.get("fila", [])
    videos_pendentes = len([item for item in fila if item.get("processado") not in [True, 1, "true", "True"]])
    
   # 2. Obter canais monitorizados e destino do ficheiro de configuração (CORRIGIDO)
    dados_espiao = ler_alvos_espiao()
    concorrentes = dados_espiao.get("alvos", [])
    qtd_concorrentes = len(concorrentes)
    canal_destino = dados_espiao.get("canal_destino")
    
    # Lógica Visual do Destino com Autocura (Puxa o nome em vez de só o ID)
    if not canal_destino:
        display_destino = "<i>Não definido</i>"
    else:
        status_destino = dados_espiao.get("status_destino", {})
        nome_dest = status_destino.get("nome", str(canal_destino))
        # Se não tiver o nome no status, tenta puxar do cache global
        if nome_dest == str(canal_destino):
            cache_nomes = ler_cache_nomes_grupos()
            nome_dest = cache_nomes.get(str(canal_destino), str(canal_destino))
        
        # Formata bonito: "Nome do Canal (ID)"
        display_destino = f"{nome_dest} (<code>{canal_destino}</code>)" if nome_dest != str(canal_destino) else f"<code>{canal_destino}</code>"

    # ✅ NOVO: Resgate das configurações de tempo e distribuição do Espião
    inicio_e = dados_espiao.get("inicio", 10)
    fim_e = dados_espiao.get("fim", 22)
    modo_e = dados_espiao.get("modo", "aleatorio").title()
    intervalo_e = dados_espiao.get("intervalo_dias", 1)
    
    # 3. Construir a mensagem unificada do painel
    texto = "🕵️ <b>Painel Principal do Espião</b>\n\n"
    texto += f"📦 <b>Fila de clonagem:</b> {videos_pendentes} vídeos aguardando.\n"
    texto += f"📡 <b>Radar operacional:</b> {qtd_concorrentes} concorrentes vigiados.\n"
    texto += f"🎯 <b>Canal de destino:</b> {display_destino}\n"
    texto += f"🕒 <b>Janela de Postagem:</b> {inicio_e}h às {fim_e}h\n"
    texto += f"📅 <b>Atraso (Defasagem):</b> D+{intervalo_e} (Modo: {modo_e})\n\n"
    texto += "Escolha uma opção para gerenciar:"
    
    if EXIBIR_LOGS: logger.info("✅ Sucesso: Painel unificado do Espião renderizado com logs operacionais.")
    await message.answer(texto, reply_markup=teclado_menu_espiao, parse_mode="HTML")

@dp.message(F.text == "Forçar Postagens 🚀", StateFilter("*"))
async def iniciar_esvaziar_clones(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    fila_data = ler_fila_clonagem()
    fila = fila_data.get("fila", [])
    
    # ✅ CORREÇÃO DE BLINDAGEM: Garante que só vai contar e forçar os pendentes reais
    qtd_pendentes = len([i for i in fila if i.get("processado") not in [True, 1, "true", "True"]])
    
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
            
            # ✅ CORREÇÃO DE BLINDAGEM: Filtra apenas os pendentes
            pendentes = [i for i in dados.get("fila", []) if i.get("processado") not in [True, 1, "true", "True"]]
            
            if not pendentes:
                if EXIBIR_LOGS: logger.info("✅ [Espião] Fila de clonagem esvaziada com sucesso!")
                await bot.send_message(chat_id, "✅ <b>Concluído!</b>\nTodos os vídeos retidos na fila do Espião foram analisados pela IA e publicados com sucesso no seu canal.", parse_mode="HTML")
                break
            
            dados["proximo_processamento"] = "2000-01-01 00:00:00"
            agora = datetime.now(fuso_horario)
            ontem_str = (agora - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            
            for item in dados.get("fila", []):
                # ✅ CORREÇÃO DE BLINDAGEM: Altera a data APENAS dos que NÃO foram processados
                if item.get("processado") not in [True, 1, "true", "True"]:
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
    
    dados = ler_alvos_espiao()
        
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
    texto += "📥 <b>Na Escuta:</b>\n"
    
    mensagens_para_enviar = []
    
    if alvos:
        cache_nomes_vigiados = ler_cache_nomes_grupos()
        linhas_geradas = []
        
        # 1. Pré-processa todas as linhas para saber quais têm erro
        for i, alvo in enumerate(alvos, 1):
            info = status_alvos.get(alvo, {})
            status_ico = "⏳"
            nome_cache = cache_nomes_vigiados.get(str(alvo))
            detalhe = f"{nome_cache} <code>({alvo})</code>" if nome_cache else alvo
            
            if info.get("status") == "ok":
                status_ico = "✅"
                detalhe = f"{info.get('nome')} <code>({alvo})</code>"
            elif info.get("status") == "erro":
                status_ico = "❌"
                detalhe = f"<code>{alvo}</code> - <i>Acesso negado/Link inválido</i>"
                
            linhas_geradas.append({
                "texto": f"<code>{i:02d}.</code> {status_ico} {detalhe}\n",
                "tem_erro": status_ico == "❌"
            })

        # 2. Motor de Ocultação Inteligente
        total = len(linhas_geradas)
        if total <= 15:
            # Se a lista for pequena, mostra tudo
            for linha in linhas_geradas:
                texto += linha["texto"]
        else:
            # Se for grande, mostra 5 primeiros, 5 últimos, e força exibição dos erros
            for i in range(5):
                texto += linhas_geradas[i]["texto"]

            ocultos_ok = 0
            for i in range(5, total - 5):
                if linhas_geradas[i]["tem_erro"]:
                    if ocultos_ok > 0:
                        texto += f"   <i>... e mais {ocultos_ok} canais operando normalmente ...</i>\n"
                        ocultos_ok = 0
                    texto += linhas_geradas[i]["texto"]
                else:
                    ocultos_ok += 1

            if ocultos_ok > 0:
                texto += f"   <i>... e mais {ocultos_ok} canais operando normalmente ...</i>\n"

            for i in range(total - 5, total):
                texto += linhas_geradas[i]["texto"]
    else:
        texto += "<i>Nenhum grupo sendo monitorado no momento.</i>\n\n"
        
    # Tratamento caso a lista de erros seja gigantesca (Limites do Telegram)
    while len(texto) > 3800:
        corte = texto.rfind('\n', 0, 3800)
        mensagens_para_enviar.append(texto[:corte])
        texto = texto[corte:]
        
    mensagens_para_enviar.append(texto)
    
    for i, msg in enumerate(mensagens_para_enviar):
        if i == len(mensagens_para_enviar) - 1:
            await message.answer(msg, reply_markup=teclado_opcoes_espiao, parse_mode="HTML")
        else:
            await message.answer(msg, parse_mode="HTML")
            
    await state.set_state(EspiaoFluxo.menu_principal)


@dp.message(EspiaoFluxo.aguardando_acao_analise, F.text == "Listar Todos 📜")
async def listar_todos_espiao(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    dados = ler_alvos_espiao()
    alvos = dados.get("alvos", [])
    
    if not alvos:
        await message.answer("Não há grupos sendo monitorados no momento.")
        return
        
    cache_nomes = ler_cache_nomes_grupos()
    status_alvos = dados.get("status_alvos", {})
    
    texto = "📜 <b>Lista Completa de Grupos Vigiados (Espião)</b>\n\n"
    mensagens = []
    
    for i, alvo in enumerate(alvos, 1):
        info = status_alvos.get(str(alvo), {})
        
        # Puxa o status para definir o ícone (✅ ou ❌)
        status_ico = "❌" if info.get("status") == "erro" else "✅"
        
        nome = info.get("nome") or cache_nomes.get(str(alvo), str(alvo))
        linha = f"<b>{i}.</b> {status_ico} {nome} (<code>{alvo}</code>)\n"
        
        # Quebra a mensagem se ficar muito grande para o limite do Telegram
        if len(texto) + len(linha) > 3800:
            mensagens.append(texto)
            texto = ""
        texto += linha
        
    mensagens.append(texto)
    
    for msg in mensagens:
        await message.answer(msg, parse_mode="HTML")

@dp.message(EspiaoFluxo.aguardando_acao_analise, F.text == "⚠️ Duplicados")
async def verificar_duplicados_espiao(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    dados = ler_alvos_espiao()
    alvos = dados.get("alvos", [])
    if len(alvos) < 2:
        await message.answer("Não há grupos suficientes para procurar duplicados.")
        return
        
    msg_status = await message.answer("⏳ Analisando a lista em busca de duplicados...")
    cache_nomes = ler_cache_nomes_grupos()
    status_alvos = dados.get("status_alvos", {})
    
    lista_analise = []
    for index, alvo in enumerate(alvos, 1):
        alvo_str = str(alvo)
        info = status_alvos.get(alvo_str, {})
        nome = info.get("nome") or cache_nomes.get(alvo_str, alvo_str)
        status_ico = "❌" if info.get("status") == "erro" else "✅"
        is_num = alvo_str.lstrip("-").replace(":", "").isdigit()
        base_id = alvo_str.split(":")[0].replace("-100", "").replace("-", "") if is_num else alvo_str.split(":")[0]
        topic = alvo_str.split(":")[1] if ":" in alvo_str else "0"
        
        lista_analise.append({
            "index": index, "original": alvo_str, "nome": nome,
            "is_num": is_num, "base_id": base_id, "topic": topic, "status_ico": status_ico
        })

    duplicados = []
    pares_verificados = set()

    for i in range(len(lista_analise)):
        for j in range(i + 1, len(lista_analise)):
            A = lista_analise[i]
            B = lista_analise[j]
            par_key = tuple(sorted([A["original"], B["original"]]))
            if par_key in pares_verificados: continue
            pares_verificados.add(par_key)
            
            if A["base_id"] == B["base_id"] and A["topic"] == B["topic"]:
                duplicados.append((A, B, "Mesmo ID Base"))
            elif A["nome"] == B["nome"] and (A["is_num"] != B["is_num"]):
                duplicados.append((A, B, "Mesmo nome (@Link vs ID)"))

    await msg_status.delete()

    if not duplicados:
        await message.answer("✅ <b>Tudo limpo!</b>\nO sistema não detectou nenhum canal duplicado na sua lista.", parse_mode="HTML")
        return
        
    texto = "⚠️ <b>Aviso: Possíveis Duplicados Detectados</b>\n\n"
    for A, B, motivo in duplicados:
        texto += f"🔹 <b>{A['nome']}</b>\n"
        texto += f"   ├ <b>{A['index']}.</b> {A['status_ico']} <code>{A['original']}</code>\n"
        texto += f"   └ <b>{B['index']}.</b> {B['status_ico']} <code>{B['original']}</code>\n"
        texto += f"   <i>(Motivo: {motivo})</i>\n\n"
        
    teclado_remover_dup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🤖 Auto-Remover Duplicados", callback_data="remover_duplicados_espiao")]]
    )
    await message.answer(texto, parse_mode="HTML", reply_markup=teclado_remover_dup)

@dp.callback_query(F.data == "remover_duplicados_espiao")
async def remover_duplicados_espiao_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    dados = ler_alvos_espiao()
    alvos = dados.get("alvos", [])
    status_alvos = dados.get("status_alvos", {})
    cache_nomes = ler_cache_nomes_grupos()
    
    lista_analise = []
    for index, alvo in enumerate(alvos, 1):
        alvo_str = str(alvo)
        info = status_alvos.get(alvo_str, {})
        nome = info.get("nome") or cache_nomes.get(alvo_str, alvo_str)
        is_num = alvo_str.lstrip("-").replace(":", "").isdigit()
        base_id = alvo_str.split(":")[0].replace("-100", "").replace("-", "") if is_num else alvo_str.split(":")[0]
        topic = alvo_str.split(":")[1] if ":" in alvo_str else "0"
        
        lista_analise.append({
            "original": alvo_str, "nome": nome, "is_num": is_num,
            "status": info.get("status", "ok"), "base_id": base_id, "topic": topic
        })

    alvos_para_remover = set()
    pares_verificados = set()

    for i in range(len(lista_analise)):
        for j in range(i + 1, len(lista_analise)):
            A = lista_analise[i]
            B = lista_analise[j]
            if A["original"] in alvos_para_remover or B["original"] in alvos_para_remover: continue
                
            par_key = tuple(sorted([A["original"], B["original"]]))
            if par_key in pares_verificados: continue
            pares_verificados.add(par_key)
            
            is_dup = False
            if A["base_id"] == B["base_id"] and A["topic"] == B["topic"]: is_dup = True
            elif A["nome"] == B["nome"] and (A["is_num"] != B["is_num"]): is_dup = True

            if is_dup:
                if A["status"] == "ok" and B["status"] == "erro": alvos_para_remover.add(B["original"])
                elif B["status"] == "ok" and A["status"] == "erro": alvos_para_remover.add(A["original"])
                elif A["is_num"] and not B["is_num"]: alvos_para_remover.add(B["original"])
                elif B["is_num"] and not A["is_num"]: alvos_para_remover.add(A["original"])
                else: alvos_para_remover.add(B["original"]) 
                    
    if alvos_para_remover:
        alvos_limpos = [a for a in alvos if str(a) not in alvos_para_remover]
        dados["alvos"] = alvos_limpos
        salvar_alvos_espiao(dados)
        texto_removidos = "✅ <b>Duplicados Removidos Automaticamente!</b>\nOs seguintes canais foram descartados:\n"
        for r in alvos_para_remover: texto_removidos += f"🗑️ <code>{r}</code>\n"
        await callback.message.edit_text(texto_removidos, parse_mode="HTML")
    else:
        await callback.message.edit_text("Nenhum duplicado válido para remoção automática encontrado.")
    await callback.answer()

@dp.message(EspiaoFluxo.menu_principal, F.text == "Adicionar Grupo ➕")
async def pedir_alvo_espiao(message: types.Message, state: FSMContext):
    teclado_dinamico = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Importar Banco Global 🌍")], 
            [KeyboardButton(text="Lista Negra (Blacklist) ⛔")],
            [KeyboardButton(text="Cancelar ❌")]
        ], 
        resize_keyboard=True, 
        is_persistent=True
    )
    await message.answer(
        "Envie os @usernames, links ou IDs dos grupos que deseja monitorar como ORIGEM.\n\n"
        "OBS: Você pode enviar vários separando por vírgula (Ex: @grupo1, -100123, https://t.me/grupo2, https://web.telegram.org/a/#-1002856422690):\n\n"
        "<blockquote>💡 <b>Dica:</b> Você pode colar uma lista ou clicar no botão abaixo para puxar o <b>Banco Global</b> (o robô ignorará os grupos duplicados e os da Lista Negra automaticamente).</blockquote>", 
        reply_markup=teclado_dinamico, 
        parse_mode="HTML"
    )
    await state.set_state(EspiaoFluxo.aguardando_novo_alvo)

@dp.message(EspiaoFluxo.aguardando_novo_alvo)
async def processar_novo_alvo_espiao(message: types.Message, state: FSMContext):
    texto = message.text
    
    # 🎯 NOVA REDIREÇÃO DA BLACKLIST (COM NOMES)
    if texto == "Lista Negra (Blacklist) ⛔":
        dados = ler_alvos_espiao()
        blacklist = dados.get("blacklist", [])
        cache_nomes = ler_cache_nomes_grupos()
        texto_bl = "⛔ <b>Lista Negra do Espião</b>\nOs canais abaixo <b>NUNCA</b> serão importados ou monitorados:\n\n"
        
        if blacklist:
            for i, b in enumerate(blacklist, 1): 
                nome = cache_nomes.get(str(b), str(b))
                texto_bl += f"{i}. {nome} (<code>{b}</code>)\n"
        else: 
            texto_bl += "<i>A lista negra está vazia.</i>\n"
        
        tcl = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="➕ Add à Blacklist"), KeyboardButton(text="🗑️ Remover da Blacklist")], 
                [KeyboardButton(text="Cancelar ❌")]
            ], 
            resize_keyboard=True, 
            is_persistent=True
        )
        await message.answer(texto_bl, reply_markup=tcl, parse_mode="HTML")
        await state.set_state(EspiaoFluxo.aguardando_acao_blacklist)
        return
        
    dados_existentes = ler_alvos_espiao()
    alvos_existentes = dados_existentes.get("alvos", [])
    canal_destino = str(dados_existentes.get("canal_destino", ""))
    blacklist = [str(b) for b in dados_existentes.get("blacklist", [])]
    
    is_importacao_global = texto == "Importar Banco Global 🌍"
    
    if is_importacao_global:
        msg_status = await message.answer("⏳ <b>Importando Banco Global e cruzando com a Lista Negra...</b>", parse_mode="HTML", reply_markup=teclado_cancelar)
        from utils import obter_banco_global_origens
        entradas_brutas = obter_banco_global_origens()
        if not entradas_brutas:
            await msg_status.delete()
            await message.answer("⚠️ O Banco Global está vazio no momento.", parse_mode="HTML")
            return
    else:
        import re
        padroes = re.findall(r'(-100\d+(?::\d+)?|@\w+|https?://t\.me/[^\s\)]+)', texto)
        if padroes: entradas_brutas = list(dict.fromkeys(padroes))
        else: entradas_brutas = texto.replace('\n', ',').split(',')
        msg_status = await message.answer("⏳ <b>Validando grupos...</b>", parse_mode="HTML", reply_markup=teclado_cancelar)

    alvos_novos_para_adicionar = []
    alvos_ja_monitorados = []
    alvos_rejeitados = []
    alvos_em_loop = [] 

    for entrada in entradas_brutas:
        entrada_limpa = entrada.strip()
        if not entrada_limpa: continue

        # Se for do Banco Global, pula a lentidão da rede
        if is_importacao_global:
            sucesso = True
            id_final = entrada_limpa
            nome = entrada_limpa
        else:
            sucesso, id_final, nome = await validar_e_formatar_alvo(bot, entrada_limpa)

        if sucesso:
            id_base = id_final.replace("-100", "")
            if id_final in blacklist or id_base in [b.replace("-100", "") for b in blacklist]:
                alvos_rejeitados.append(f"{entrada_limpa} (Blacklist ⛔)")
            elif canal_destino and id_base == canal_destino.replace("-100", ""):
                alvos_em_loop.append(entrada_limpa)
            elif id_final in alvos_existentes:
                alvos_ja_monitorados.append(entrada_limpa)
            elif id_final not in [a["id"] for a in alvos_novos_para_adicionar]:
                alvos_novos_para_adicionar.append({"id": id_final, "nome": nome})
                if not is_importacao_global:
                    salvar_nome_grupo(id_final, nome)
            else:
                alvos_ja_monitorados.append(entrada_limpa) 
        else:
            alvos_rejeitados.append(entrada_limpa)

    await msg_status.delete()

    texto_resposta = ""

    if alvos_novos_para_adicionar:
        texto_resposta += f"✅ <b>{len(alvos_novos_para_adicionar)} NOVO(S) alvo(s) válido(s):</b>\n"
        for av in alvos_novos_para_adicionar[:15]:
            texto_resposta += f"🔹 {av['nome']} (<code>{av['id']}</code>)\n"
        if len(alvos_novos_para_adicionar) > 15:
            texto_resposta += f"<i>... e mais {len(alvos_novos_para_adicionar) - 15} alvos.</i>\n"
        texto_resposta += "\n"

    if alvos_em_loop:
        texto_resposta += f"🛑 <b>{len(alvos_em_loop)} bloqueado(s) por Anti-Loop:</b>\n"
        for loop in alvos_em_loop[:10]:
            texto_resposta += f"🔻 <code>{loop}</code>\n"
        if len(alvos_em_loop) > 10:
            texto_resposta += f"<i>... e mais {len(alvos_em_loop) - 10} alvos.</i>\n"
        texto_resposta += "\n"

    if alvos_ja_monitorados:
        texto_resposta += f"ℹ️ <b>{len(alvos_ja_monitorados)} ignorado(s) por já estar no radar:</b>\n"
        for dup in alvos_ja_monitorados[:10]:
            texto_resposta += f"🔸 <code>{dup}</code>\n"
        if len(alvos_ja_monitorados) > 10:
            texto_resposta += f"<i>... e mais {len(alvos_ja_monitorados) - 10} alvos.</i>\n"
        texto_resposta += "\n"

    if alvos_rejeitados:
        texto_resposta += f"❌ <b>{len(alvos_rejeitados)} falharam (Formato inválido/Blacklist):</b>\n"
        for rej in alvos_rejeitados[:10]:
            texto_resposta += f"🔻 <code>{rej}</code>\n"
        if len(alvos_rejeitados) > 10:
            texto_resposta += f"<i>... e mais {len(alvos_rejeitados) - 10} alvos.</i>\n"
        texto_resposta += "\n"

    if not alvos_novos_para_adicionar:
        texto_resposta += "⚠️ <b>Nenhum alvo novo foi aprovado.</b>"
        await message.answer(texto_resposta, parse_mode="HTML")
        await state.clear()
        await menu_grupos_vigiados(message, state)
        return

    await state.update_data(novos_alvos_espiao=alvos_novos_para_adicionar)
    texto_resposta += "Confirma a adição dos novos alvos?"
    
    teclado_confirmacao = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]], resize_keyboard=True, is_persistent=True)
    await message.answer(texto_resposta, reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(EspiaoFluxo.aguardando_confirmacao_alvo)

@dp.message(EspiaoFluxo.aguardando_confirmacao_alvo)
async def confirmar_adicao_alvo_espiao(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, clique em Aprovar ✅ ou Cancelar ❌.", reply_markup=teclado_cancelar)
        return
        
    data = await state.get_data()
    alvos_novos = data.get("novos_alvos_espiao", [])
    
    dados = ler_alvos_espiao()
    alvos_existentes = dados.get("alvos", [])
    
    adicionados = 0
    for av in alvos_novos:
        if av['id'] not in alvos_existentes:
            alvos_existentes.append(av['id'])
            adicionados += 1
            
    if adicionados > 0:
        dados["alvos"] = alvos_existentes
        salvar_alvos_espiao(dados)
        if EXIBIR_LOGS: logger.info(f"✅ {adicionados} novos alvos do espião adicionados ao radar.")
        await message.answer(f"✅ <b>{adicionados} alvo(s) adicionado(s) ao radar com sucesso!</b>\nO Userbot verificará o acesso neste(s) canal(is) no próximo ciclo.", parse_mode="HTML")
    else:
        await message.answer("⚠️ Todos os alvos enviados já estavam sendo monitorados pelo Espião.")
        
    await state.clear()
    await menu_grupos_vigiados(message, state)

@dp.message(EspiaoFluxo.aguardando_acao_blacklist)
async def acao_blacklist_espiao(message: types.Message, state: FSMContext):
    if message.text == "➕ Add à Blacklist":
        texto_bl = (
            "Envie os @usernames, links ou IDs dos canais que deseja <b>BLOQUEAR</b> no Espião.\n\n"
            "OBS: Você pode enviar vários separando por vírgula (Ex: @grupo1, -100123, https://t.me/grupo2, https://web.telegram.org/a/#-1002856422690):\n\n"
            "<blockquote>💡 <b>Dica:</b> Você pode colar uma lista inteira. O robô irá ignorar formatos inválidos e bloquear os corretos automaticamente.</blockquote>"
        )
        await message.answer(texto_bl, reply_markup=teclado_cancelar, parse_mode="HTML")
        await state.set_state(EspiaoFluxo.aguardando_blacklist_add)
    elif message.text == "🗑️ Remover da Blacklist":
        await message.answer("Envie os IDs que deseja liberar (separados por vírgula):", reply_markup=teclado_cancelar)
        await state.set_state(EspiaoFluxo.aguardando_blacklist_remove)

@dp.message(EspiaoFluxo.aguardando_blacklist_add)
async def processar_add_blacklist_espiao(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await pedir_alvo_espiao(message, state)
        return

    import re
    texto = message.text
    padroes = re.findall(r'(-100\d+(?::\d+)?|@\w+|https?://t\.me/[^\s\)]+|https?://web\.telegram\.org/[^\s\)]+)', texto)
    if padroes: entradas_brutas = list(dict.fromkeys(padroes))
    else: entradas_brutas = texto.replace('\n', ',').split(',')

    msg_status = await message.answer("⏳ A processar e validar IDs para a Lista Negra...", reply_markup=teclado_cancelar)

    dados = ler_alvos_espiao()
    alvos_atuais = dados.get("alvos", [])
    blacklist = dados.get("blacklist", [])

    novos_blacklist = []
    conflitos = []

    for entrada in entradas_brutas:
        entrada_limpa = entrada.strip()
        if not entrada_limpa: continue

        sucesso, id_final, nome = await validar_e_formatar_alvo(bot, entrada_limpa)
        alvo_para_bl = id_final if sucesso else entrada_limpa

        if sucesso:
            salvar_nome_grupo(id_final, nome)

        if alvo_para_bl not in novos_blacklist and alvo_para_bl not in blacklist:
            novos_blacklist.append(alvo_para_bl)

        for alvo_monitorado in alvos_atuais:
            if alvo_para_bl == str(alvo_monitorado) and alvo_monitorado not in conflitos:
                conflitos.append(alvo_monitorado)

    await msg_status.delete()

    if not novos_blacklist:
        await message.answer("Nenhum canal novo válido detetado ou todos já estavam na Lista Negra.")
        await pedir_alvo_espiao(message, state)
        return

    if conflitos:
        await state.update_data(novos_blacklist=novos_blacklist, alvos_para_remover=conflitos)
        cache_nomes = ler_cache_nomes_grupos()
        texto_aviso = (
            f"⚠️ <b>Atenção: Conflito Detetado!</b>\n\n"
            f"Você está a tentar adicionar canais à Lista Negra que <b>já estão a ser monitorizados</b> pelo Espião.\n\n"
            f"Canais que serão <b>AUTOMATICAMENTE REMOVIDOS</b> da escuta:\n"
        )
        for c in conflitos:
            nome_conflito = cache_nomes.get(str(c), str(c))
            texto_aviso += f"🗑️ {nome_conflito} (<code>{c}</code>)\n"

        texto_aviso += "\nDeseja aprovar a adição à Lista Negra e a exclusão destes canais da escuta simultaneamente?"

        teclado_conf = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]], resize_keyboard=True, is_persistent=True)
        await message.answer(texto_aviso, reply_markup=teclado_conf, parse_mode="HTML")
        await state.set_state(EspiaoFluxo.aguardando_confirmacao_blacklist_conflito)
    else:
        for n in novos_blacklist:
            blacklist.append(n)
        dados["blacklist"] = blacklist
        salvar_alvos_espiao(dados)
        
        cache_nomes = ler_cache_nomes_grupos()
        txt_lista = "⛔ <b>Lista Negra do Espião</b>\n"
        for i, b in enumerate(blacklist, 1):
            nome = cache_nomes.get(str(b), str(b))
            txt_lista += f"{i}. {nome} (<code>{b}</code>)\n"
            
        texto_final = f"✅ <b>{len(novos_blacklist)} canal(is) bloqueado(s) com sucesso!</b>\n\n{txt_lista}"

        tcl_bl = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="➕ Add à Blacklist"), KeyboardButton(text="🗑️ Remover da Blacklist")], 
                [KeyboardButton(text="Cancelar ❌")]
            ], 
            resize_keyboard=True, 
            is_persistent=True
        )
        await message.answer(texto_final, parse_mode="HTML", reply_markup=tcl_bl)
        await state.set_state(EspiaoFluxo.aguardando_acao_blacklist)

@dp.message(EspiaoFluxo.aguardando_confirmacao_blacklist_conflito)
async def confirmar_blacklist_conflito_espiao(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Operação cancelada.", reply_markup=teclado_cancelar)
        await pedir_alvo_espiao(message, state)
        return

    data = await state.get_data()
    novos_blacklist = data.get("novos_blacklist", [])
    alvos_para_remover = data.get("alvos_para_remover", [])

    dados = ler_alvos_espiao()
    alvos_atuais = dados.get("alvos", [])
    blacklist = dados.get("blacklist", [])

    alvos_atualizados = [a for a in alvos_atuais if a not in alvos_para_remover]
    dados["alvos"] = alvos_atualizados

    for n in novos_blacklist:
        if n not in blacklist:
            blacklist.append(n)
    dados["blacklist"] = blacklist

    salvar_alvos_espiao(dados)

    cache_nomes = ler_cache_nomes_grupos()
    txt_lista = "\n⛔ <b>Lista Negra Atualizada:</b>\n"
    for i, b in enumerate(blacklist, 1):
        nome = cache_nomes.get(str(b), str(b))
        txt_lista += f"{i}. {nome} (<code>{b}</code>)\n"

    texto_final = f"✅ <b>Sucesso!</b>\n⛔ {len(novos_blacklist)} adicionado(s).\n🗑️ {len(alvos_para_remover)} removido(s) da escuta.\n{txt_lista}"

    tcl_bl = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Add à Blacklist"), KeyboardButton(text="🗑️ Remover da Blacklist")], 
            [KeyboardButton(text="Cancelar ❌")]
        ], 
        resize_keyboard=True, 
        is_persistent=True
    )
    await message.answer(texto_final, parse_mode="HTML", reply_markup=tcl_bl)
    await state.set_state(EspiaoFluxo.aguardando_acao_blacklist)

@dp.message(EspiaoFluxo.aguardando_blacklist_remove)
async def processar_rem_blacklist_espiao(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await pedir_alvo_espiao(message, state)
        return

    remover = [s.strip() for s in message.text.split(",")]
    dados = ler_alvos_espiao()
    blacklist = dados.get("blacklist", [])
    nova_blacklist = [b for b in blacklist if b not in remover]
    dados["blacklist"] = nova_blacklist
    salvar_alvos_espiao(dados)
    
    cache_nomes = ler_cache_nomes_grupos()
    txt_lista = "⛔ <b>Lista Negra do Espião</b>\n"
    if nova_blacklist:
        for i, b in enumerate(nova_blacklist, 1):
            nome = cache_nomes.get(str(b), str(b))
            txt_lista += f"{i}. {nome} (<code>{b}</code>)\n"
    else:
        txt_lista += "<i>Nenhuma restrição cadastrada.</i>\n"

    texto_final = f"✅ <b>Blacklist atualizada com sucesso!</b>\n\n{txt_lista}"
    
    tcl_bl = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Add à Blacklist"), KeyboardButton(text="🗑️ Remover da Blacklist")], 
            [KeyboardButton(text="Cancelar ❌")]
        ], 
        resize_keyboard=True, 
        is_persistent=True
    )
    await message.answer(texto_final, parse_mode="HTML", reply_markup=tcl_bl)
    await state.set_state(EspiaoFluxo.aguardando_acao_blacklist)

@dp.message(EspiaoFluxo.menu_principal, F.text == "Remover Grupo 🗑️")
async def pedir_remocao_espiao(message: types.Message, state: FSMContext):
    dados = ler_alvos_espiao()
    alvos = dados.get("alvos", [])
    if not alvos:
        await message.answer("Não há concorrentes para remover.", reply_markup=teclado_opcoes_espiao)
        return
    
    texto = "Qual alvo deseja excluir? Digite o <b>NÚMERO</b> correspondente.\n<i>(Para remover vários, separe por vírgula. Ex: 1, 3, 4)</i>\n\n"
    
    mensagens_para_enviar = []
    
    for i, alvo in enumerate(alvos, 1):
        linha = f"{i}. {alvo}\n"
        if len(texto) + len(linha) > 3800:
            mensagens_para_enviar.append(texto)
            texto = ""
        texto += linha
        
    mensagens_para_enviar.append(texto)
    
    for i, msg in enumerate(mensagens_para_enviar):
        if i == len(mensagens_para_enviar) - 1:
            await message.answer(msg, reply_markup=teclado_cancelar, parse_mode="HTML")
        else:
            await message.answer(msg, parse_mode="HTML")
            
    await state.set_state(EspiaoFluxo.aguardando_remocao_alvo)

@dp.message(EspiaoFluxo.aguardando_remocao_alvo)
async def confirmar_remocao_espiao(message: types.Message, state: FSMContext):
    entradas = message.text.replace(' ', '').split(',')
    indices_para_remover = []
    
    dados = ler_alvos_espiao()
    alvos = dados.get("alvos", [])
    
    for entrada in entradas:
        if entrada.isdigit():
            idx = int(entrada) - 1
            if 0 <= idx < len(alvos) and idx not in indices_para_remover:
                indices_para_remover.append(idx)
                
    if not indices_para_remover:
        await message.answer("⚠️ Nenhum número válido detectado. Tente novamente:", reply_markup=teclado_cancelar)
        return
        
    await state.update_data(indices_remocao=indices_para_remover)
    
    texto_confirmacao = f"Tem certeza de que deseja parar de monitorar os <b>{len(indices_para_remover)} alvo(s)</b> abaixo?\n\n"
    for idx in indices_para_remover:
        texto_confirmacao += f"🗑️ <b>{alvos[idx]}</b>\n"
        
    teclado_confirmacao = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]], resize_keyboard=True, is_persistent=True)
    await message.answer(texto_confirmacao, reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(EspiaoFluxo.aguardando_confirmacao_remocao)

@dp.message(EspiaoFluxo.aguardando_confirmacao_remocao)
async def processar_remocao_espiao(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, clique em Aprovar ou Cancelar.")
        return
        
    data = await state.get_data()
    indices = data.get("indices_remocao", [])
    
    dados = ler_alvos_espiao()
    alvos = dados.get("alvos", [])
    
    # IMPORTANTE: Ordena de trás para frente para não bagunçar os índices ao fazer o pop()
    indices.sort(reverse=True)
    
    removidos = []
    for idx in indices:
        if 0 <= idx < len(alvos):
            removidos.append(alvos.pop(idx))
            
    if removidos:
        salvar_alvos_espiao(dados)
        if EXIBIR_LOGS: logger.info(f"🗑️ {len(removidos)} alvos do espião removidos.")
        await message.answer(f"✅ <b>{len(removidos)} alvo(s) removido(s) do radar!</b>", parse_mode="HTML")
    else:
        await message.answer("⚠️ Erro de sincronização. Ação cancelada.")
        
    await menu_grupos_vigiados(message, state)

@dp.message(EspiaoFluxo.menu_principal, F.text == "Definir Destino 🎯")
async def pedir_destino_espiao(message: types.Message, state: FSMContext):
    await message.answer(
        "Envie o <b>ID Numérico, Link ou @username</b> do Canal de DESTINO (Para onde o robô vai enviar os vídeos clonados):\n"
        "<i>Exemplo: -100123456789 ou https://t.me/meucanal</i>", 
        parse_mode="HTML", 
        reply_markup=teclado_cancelar
    )
    await state.set_state(EspiaoFluxo.aguardando_canal_destino)

@dp.message(EspiaoFluxo.aguardando_canal_destino)
async def confirmar_destino_espiao(message: types.Message, state: FSMContext):
    msg_status = await message.answer("⏳ Validando o canal de destino e buscando nome...", reply_markup=teclado_cancelar)
    
    # Passa o link/ID pelo nosso Motor Inteligente de Validação
    sucesso, destino_id, nome = await validar_e_formatar_alvo(bot, message.text.strip())
    
    await msg_status.delete()
    
    if not sucesso:
        await message.answer("⚠️ <b>Canal não encontrado ou formato inválido.</b>\nCertifique-se de que o ID ou link está correto. Tente novamente:", reply_markup=teclado_cancelar, parse_mode="HTML")
        return
        
    # Salva o nome amigável no cache e guarda o ID limpo na memória da conversa
    salvar_nome_grupo(destino_id, nome)
    await state.update_data(novo_destino=destino_id)
    
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    
    # Mostra de forma bonita e padronizada (Nome + ID)
    nome_exibicao = f"{nome} (<code>{destino_id}</code>)" if nome != destino_id else f"<code>{destino_id}</code>"
    
    await message.answer(f"Os vídeos clonados serão enviados automaticamente para o canal:\n\n<b>{nome_exibicao}</b>\n\nConfirma essa alteração?", reply_markup=teclado_confirmacao, parse_mode="HTML")
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

@dp.message(F.text == "Editar Janela 🕒", StateFilter("*"))
async def iniciar_config_janela_espiao(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    if EXIBIR_LOGS: logger.info("🚀 Iniciando configuração isolada da janela de horário do Espião.")
    
    dados = ler_alvos_espiao()
    inicio = dados.get("inicio", 10)
    fim = dados.get("fim", 22)
    
    await message.answer(
        f"Defina a <b>Janela de Horário</b> útil em que o Espião pode postar os vídeos.\n\n"
        f"Envie no formato <code>Inicio-Fim</code> (Exemplo: <code>10-22</code>) ou clique no botão abaixo para rodar 24h:\n"
        f"<i>Janela atual: {inicio}h às {fim}h</i>", 
        reply_markup=teclado_janela_espiao, # ✅ Passa a usar o novo teclado
        parse_mode="HTML"
    )
    await state.set_state(ConfigRotinaEspiao.aguardando_janela)

@dp.message(ConfigRotinaEspiao.aguardando_janela)
async def receber_janela_espiao(message: types.Message, state: FSMContext):
    import re
    texto = message.text.strip()
    
    if texto == "Dia Todo (24h) 🕛" or texto.lower() == "dia todo":
        inicio, fim = 0, 24
    else:
        match = re.match(r"^(\d{1,2})-(\d{1,2})$", texto)
        if not match:
            await message.answer("Formato inválido! Use o formato exato como no exemplo: 10-22.", reply_markup=teclado_janela_espiao)
            return
        inicio, fim = map(int, match.groups())
        if inicio >= fim or inicio < 0 or fim > 24:
            await message.answer("Valores inválidos! A hora de início deve ser menor que a do fim.", reply_markup=teclado_janela_espiao)
            return

    await state.update_data(inicio=inicio, fim=fim)
    texto_exibicao = "24 horas por dia" if inicio == 0 and fim == 24 else f"estritamente entre {inicio}h e {fim}h"
    
    teclado_conf = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]], resize_keyboard=True, is_persistent=True)
    await message.answer(f"Deseja confirmar a nova janela para postar <b>{texto_exibicao}</b>?", parse_mode="HTML", reply_markup=teclado_conf)
    await state.set_state(ConfigRotinaEspiao.aguardando_confirmacao_janela)

@dp.message(ConfigRotinaEspiao.aguardando_confirmacao_janela)
async def confirmar_janela_espiao(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Operação cancelada.")
        await menu_grupos_vigiados(message, state)
        return
        
    data = await state.get_data()
    inicio = data.get("inicio")
    fim = data.get("fim")
    
    dados = ler_alvos_espiao()
    dados["inicio"] = inicio
    dados["fim"] = fim
    salvar_alvos_espiao(dados)
    
    texto_exibicao = "24 horas por dia" if inicio == 0 and fim == 24 else f"estritamente entre as {inicio}h e as {fim}h"
    await message.answer(f"✅ <b>Janela do Espião Salva!</b>\nO robô postará {texto_exibicao}.", parse_mode="HTML")
    await state.clear()
    await menu_grupos_vigiados(message, state)

@dp.message(F.text == "Editar Atraso ⏳", StateFilter("*"))
async def iniciar_config_atraso_espiao(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    
    teclado_dias = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Mesmo Dia (D+0) 🟢")],
            [KeyboardButton(text="Dia Seguinte (D+1) 🟡")],
            [KeyboardButton(text="Dois Dias (D+2) 🔵")],
            [KeyboardButton(text="Cancelar ❌")]
        ], resize_keyboard=True, is_persistent=True
    )
    await message.answer("Escolha a defasagem temporal (Atraso) das postagens extraídas do Espião:", reply_markup=teclado_dias)
    await state.set_state(ConfigRotinaEspiao.aguardando_intervalo_espiao)

@dp.message(ConfigRotinaEspiao.aguardando_intervalo_espiao)
async def receber_intervalo_espiao(message: types.Message, state: FSMContext):
    mapa_dias = {"Mesmo Dia (D+0) 🟢": 0, "Dia Seguinte (D+1) 🟡": 1, "Dois Dias (D+2) 🔵": 2}
    if message.text not in mapa_dias:
        await message.answer("Por favor, use os botões na tela para escolher o intervalo.", reply_markup=teclado_cancelar)
        return
        
    intervalo = mapa_dias[message.text]
    await state.update_data(intervalo_dias_espiao=intervalo)
    
    if intervalo == 0:
        await state.update_data(modo="ordem")
        teclado_conf = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]], resize_keyboard=True, is_persistent=True)
        await message.answer(f"Deseja confirmar o atraso de D+0 (Mesmo Dia) com modo de Ordem de Chegada?", reply_markup=teclado_conf)
        await state.set_state(ConfigRotinaEspiao.aguardando_confirmacao_tempo)
        return
        
    teclado_modo = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Aleatório 🔀"), KeyboardButton(text="Ordem de Chegada ⬇️")], [KeyboardButton(text="Cancelar ❌")]], resize_keyboard=True, is_persistent=True)
    await message.answer("Como deseja distribute os clones retidos dentro da janela estipulada?", reply_markup=teclado_modo)
    await state.set_state(ConfigRotinaEspiao.aguardando_modo)

@dp.message(ConfigRotinaEspiao.aguardando_modo)
async def salvar_config_tempo_espiao(message: types.Message, state: FSMContext):
    if message.text not in ["Aleatório 🔀", "Ordem de Chegada ⬇️"]:
        await message.answer("Por favor, use os botões de seleção para definir o modo.", reply_markup=teclado_cancelar)
        return
        
    modo = "aleatorio" if message.text == "Aleatório 🔀" else "ordem"
    await state.update_data(modo=modo)
    
    data = await state.get_data()
    intervalo = data.get("intervalo_dias_espiao", 1)
    
    teclado_conf = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]], resize_keyboard=True, is_persistent=True)
    await message.answer(f"Deseja confirmar o atraso de D+{intervalo} com distribuição {message.text}?", reply_markup=teclado_conf)
    await state.set_state(ConfigRotinaEspiao.aguardando_confirmacao_tempo)

@dp.message(ConfigRotinaEspiao.aguardando_confirmacao_tempo)
async def confirmar_tempo_espiao(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Operação cancelada.")
        await menu_grupos_vigiados(message, state)
        return
        
    data = await state.get_data()
    intervalo = data.get("intervalo_dias_espiao", 1)
    modo = data.get("modo", "aleatorio")
    
    dados = ler_alvos_espiao()
    intervalo_antigo = dados.get("intervalo_dias", 1)
    
    dados["intervalo_dias"] = intervalo
    dados["modo"] = modo
    salvar_alvos_espiao(dados)
    
    modo_texto = "Ordem de Chegada ⬇️" if modo == "ordem" else "Aleatório 🔀"
    await message.answer(f"✅ <b>Atraso do Espião Salvo!</b>\nAtraso: D+{intervalo}\nDistribuição: {modo_texto}", parse_mode="HTML")
    await state.clear()
    
    if intervalo_antigo != intervalo:
        fila_data = ler_fila_clonagem()
        houve_reset = False
        for item in fila_data.get("fila", []):
            if item.get("processado") not in [True, 1, "true", "True"]:
                item["horario_disparo"] = "" 
                houve_reset = True
        if houve_reset:
            salvar_fila_clonagem(fila_data)
        await message.answer(f"⚠️ <b>Gatilho de Recálculo Acionado!</b>\nComo você alterou a defasagem, todos os horários pendentes foram resetados.", parse_mode="HTML")
        
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

    # Resgata e exibe a rotina do Grupo Público no Canal Viral
    config_pub_viral = dados.get("promo_publico_viral", {"inicio": 10, "fim": 20, "frequencia": 1})
    texto += f"🔹 <b>Promoção do Grupo Público 👥 (Para o Canal Viral)</b>\n"
    texto += f"   Janela de Sorteio: {config_pub_viral['inicio']}h às {config_pub_viral['fim']}h\n"
    texto += f"   Disparos por Dia: {config_pub_viral['frequencia']}x\n\n"
    
    texto += "Selecione o que deseja editar abaixo:"
    
    # ✅ NOVO: Verificação do status e adição do botão de pausa dinâmico
    texto_botao_pausa = "Retomar Rotinas ▶️" if dados.get("pausado_viral") else "Pausar Rotinas ⏸️"
    
    teclado = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Editar Rotinas ✏️"), KeyboardButton(text="Disparos Manuais 🚀")],
            [KeyboardButton(text=texto_botao_pausa), KeyboardButton(text="Voltar às Automações 🔙")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer(texto, reply_markup=teclado, parse_mode="HTML")
    await state.update_data(menu_origem="espiao") # ✅ Salva a origem para não quebrar a navegação
    await state.set_state(ConfigRotina.menu_principal)

@dp.message(ConfigRotina.menu_principal, F.text == "Editar Rotinas ✏️")
async def submenu_editar_rotinas(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    data = await state.get_data()
    origem = data.get("menu_origem")
    
    if origem == "espiao":
        teclado = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Editar Convite do Grupo 🔗"), KeyboardButton(text="Editar Prompt GEM 🤖\u200b")],
                [KeyboardButton(text="Editar Convite Afiliados 🚀"), KeyboardButton(text="Editar Promo Público 👥")],
                [KeyboardButton(text="🔙 Voltar ao Menu Rotinas")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        texto = "✏️ <b>Editar Rotinas (Canal Viral)</b>\nSelecione qual rotina deseja configurar:"
    elif origem == "publico":
        teclado = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Editar Convite (Próprio) 🔗"), KeyboardButton(text="Editar Promo Principal 🌟")],
                [KeyboardButton(text="Editar Promo Viral 💥"), KeyboardButton(text="🔙 Voltar ao Menu Rotinas")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        texto = "✏️ <b>Editar Rotinas (Grupo Público)</b>\nSelecione qual rotina deseja configurar:"
    else:
        teclado = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Editar Bom Dia ☀️"), KeyboardButton(text="Editar Incentivo 🔥")],
                [KeyboardButton(text="Editar Convite 🔗"), KeyboardButton(text="Editar Prompt GEM 🤖")],
                [KeyboardButton(text="Editar Convite Viral 🚀"), KeyboardButton(text="Editar Promo Público 🗣️")],
                [KeyboardButton(text="Editar Boa Noite 🌙"), KeyboardButton(text="🔙 Voltar ao Menu Rotinas")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        texto = "✏️ <b>Editar Rotinas (Canal Principal)</b>\nSelecione qual rotina deseja configurar:"
        
    await message.answer(texto, reply_markup=teclado, parse_mode="HTML")

@dp.message(ConfigRotina.menu_principal, F.text == "Disparos Manuais 🚀")
async def submenu_disparos_manuais(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    data = await state.get_data()
    origem = data.get("menu_origem")
    
    if origem == "espiao":
        if EXIBIR_LOGS: logger.info("✅ Montando teclado manual para o Canal Viral.")
        teclado = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Disparar Convite Afiliados 🚀"), KeyboardButton(text="Disparar Convite do Grupo 🔗\u200b")],
                [KeyboardButton(text="Disparar Prompt GEM 🤖\u200b"), KeyboardButton(text="Disparar Promo Público 👥")],
                [KeyboardButton(text="🔙 Voltar ao Menu Rotinas")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        texto = "🚀 <b>Disparos Manuais (Canal Viral)</b>\nSelecione qual mensagem deseja forçar o envio agora:"
    elif origem == "publico":
        teclado = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Disparar Convite (Próprio) 🔗"), KeyboardButton(text="Disparar Promo Principal 🌟")],
                [KeyboardButton(text="Disparar Promo Viral 💥"), KeyboardButton(text="🔙 Voltar ao Menu Rotinas")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        texto = "🚀 <b>Disparos Manuais (Grupo Público)</b>\nSelecione qual mensagem deseja forçar o envio agora:"
    else:
        teclado = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Disparar Bom Dia ☀️"), KeyboardButton(text="Disparar Incentivo 🔥")],
                [KeyboardButton(text="Disparar Convite do Grupo 🔗"), KeyboardButton(text="Disparar Convite Viral 🚀")],
                [KeyboardButton(text="Disparar Promo Público 🗣️"), KeyboardButton(text="Disparar Boa Noite 🌙")],
                [KeyboardButton(text="🔙 Voltar ao Menu Rotinas")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        texto = "🚀 <b>Disparos Manuais (Canal Principal)</b>\nSelecione qual mensagem de rotina deseja forçar o envio agora:"
        
    await message.answer(texto, reply_markup=teclado, parse_mode="HTML")

@dp.message(F.text == "🔙 Voltar ao Menu Rotinas", StateFilter("*"))
async def voltar_menu_rotinas_dinamico(message: types.Message, state: FSMContext):
    # ✅ CORREÇÃO: antes este handler exigia o estado ConfigRotina.menu_principal.
    # Como o FSM vive em memória, qualquer restart do serviço ou expiração por
    # inatividade apagava o estado e o botão virava um beco sem saída silencioso
    # (log "Update is not handled"). Agora responde em qualquer estado, igual aos
    # botões "Disparar ..." do mesmo teclado, que já usavam StateFilter("*").
    if message.from_user.id != ADMIN_ID: return

    data = await state.get_data()
    origem = data.get("menu_origem")

    if origem == "espiao":
        await gerenciar_rotina_espiao(message, state)
    elif origem == "publico":
        try:
            await gerenciar_rotina_publico(message, state)
        except NameError:
            await message.answer("Retornando...", reply_markup=obter_teclado_configuracoes_gerais())
    elif origem:
        await gerenciar_rotina(message, state)
    else:
        # ✅ Sem "menu_origem" o estado foi perdido (restart/inatividade).
        # Em vez de ignorar o clique, devolve o usuário para a raiz.
        await state.clear()
        await state.update_data(painel_atual="raiz")
        await message.answer(
            "⚠️ A sessão anterior expirou (o bot foi reiniciado ou ficou ocioso).\n"
            "🏠 Voltando ao Painel Inicial.",
            reply_markup=obter_teclado_raiz()
        )

# ✅ NOVOS INTERRUPTORES INTERNOS DE PAUSA (COM CONFIRMAÇÃO)

# --- SPAM PRINCIPAL ---
@dp.message(ConfigDivulgacao.menu_principal, F.text.in_(["Pausar SPAM ⏸️", "Retomar SPAM ▶️"]))
async def pedir_confirmacao_pausa_spam(message: types.Message, state: FSMContext):
    acao = "pausar" if "Pausar" in message.text else "retomar"
    await state.update_data(acao_pausa_spam=acao)
    
    texto_botao = "Confirmar Pausa ✅" if acao == "pausar" else "Confirmar Retomada ✅"
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texto_botao), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    
    texto = f"⚠️ Tem certeza de que deseja <b>{'PAUSAR' if acao == 'pausar' else 'RETOMAR'}</b> o SPAM em Grupos?"
    await message.answer(texto, reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(ConfigDivulgacao.aguardando_confirmacao_pausa)

@dp.message(ConfigDivulgacao.aguardando_confirmacao_pausa)
async def processar_pausa_spam_interno(message: types.Message, state: FSMContext):
    if "Confirmar" not in message.text:
        await message.answer("Por favor, clique no botão para confirmar ou cancelar.")
        return

    data = await state.get_data()
    novo_status = True if data.get("acao_pausa_spam") == "pausar" else False

    dados = ler_alvos_divulgacao()
    dados["pausado"] = novo_status
    salvar_alvos_divulgacao(dados)

    if novo_status:
        if EXIBIR_LOGS: logger.info("⏸️ SPAM em grupos PAUSADO internamente.")
        await message.answer("⏸️ <b>SPAM em Grupos PAUSADO.</b>\nO Userbot não enviará mais convites.", parse_mode="HTML")
    else:
        if EXIBIR_LOGS: logger.info("▶️ SPAM em grupos ATIVADO internamente.")
        await message.answer("▶️ <b>SPAM em Grupos ATIVO.</b>\nO Userbot voltará a operar normalmente.", parse_mode="HTML")

    await gerenciar_divulgacao(message, state)


# --- SPAM VIRAL (ESPIÃO) ---
@dp.message(ConfigDivulgacaoViral.menu_principal, F.text.in_(["Pausar SPAM ⏸️", "Retomar SPAM ▶️"]))
async def pedir_confirmacao_pausa_spam_viral(message: types.Message, state: FSMContext):
    acao = "pausar" if "Pausar" in message.text else "retomar"
    await state.update_data(acao_pausa_spam_viral=acao)
    
    texto_botao = "Confirmar Pausa ✅" if acao == "pausar" else "Confirmar Retomada ✅"
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texto_botao), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    
    texto = f"⚠️ Tem certeza de que deseja <b>{'PAUSAR' if acao == 'pausar' else 'RETOMAR'}</b> o SPAM Viral?"
    await message.answer(texto, reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(ConfigDivulgacaoViral.aguardando_confirmacao_pausa)

@dp.message(ConfigDivulgacaoViral.aguardando_confirmacao_pausa)
async def processar_pausa_spam_viral_interno(message: types.Message, state: FSMContext):
    if "Confirmar" not in message.text:
        await message.answer("Por favor, clique no botão para confirmar ou cancelar.")
        return

    data = await state.get_data()
    novo_status = True if data.get("acao_pausa_spam_viral") == "pausar" else False

    dados = ler_alvos_divulgacao_viral()
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
async def pedir_confirmacao_pausa_rotinas(message: types.Message, state: FSMContext):
    acao = "pausar" if "Pausar" in message.text else "retomar"
    await state.update_data(acao_pausa_rotina=acao)
    
    texto_botao = "Confirmar Pausa ✅" if acao == "pausar" else "Confirmar Retomada ✅"
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texto_botao), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    
    if acao == "pausar":
        texto = "⚠️ Tem certeza de que deseja <b>PAUSAR</b> as mensagens de rotina deste módulo?"
    else:
        texto = (
            "⚠️ Tem certeza de que deseja <b>RETOMAR</b> as mensagens de rotina?\n\n"
            "🧠 <i>O sistema avaliará o histórico de hoje e distribuirá de forma inteligente apenas as mensagens "
            "que ainda estão faltando para o dia, garantindo uma postagem orgânica sem sobreposições.</i>"
        )
        
    await message.answer(texto, reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(ConfigRotina.aguardando_confirmacao_pausa)

@dp.message(ConfigRotina.aguardando_confirmacao_pausa)
async def processar_pausa_rotinas_interno(message: types.Message, state: FSMContext):
    if "Confirmar" not in message.text:
        await message.answer("Por favor, clique no botão para confirmar ou cancelar.")
        return

    data = await state.get_data()
    origem = data.get("menu_origem")
    acao = data.get("acao_pausa_rotina")
    dados_rotina = ler_config_rotina()
    
    novo_status = True if acao == "pausar" else False

    if origem == "espiao":
        dados_rotina["pausado_viral"] = novo_status
        salvar_config_rotina(dados_rotina)
        if novo_status: await message.answer("⏸️ <b>Rotinas do Canal Viral PAUSADAS.</b>", parse_mode="HTML")
        else:
            await message.answer("▶️ <b>Rotinas do Viral ATIVAS.</b>\n🔄 Recalculando grade...", parse_mode="HTML")
            agendar_tarefas_diarias(escopo="viral")
        await gerenciar_rotina_espiao(message, state)
        
    elif origem == "publico":
        dados_rotina["pausado_publico"] = novo_status
        salvar_config_rotina(dados_rotina)
        if novo_status: await message.answer("⏸️ <b>Rotinas do Público PAUSADAS.</b>", parse_mode="HTML")
        else:
            await message.answer("▶️ <b>Rotinas do Público ATIVAS.</b>\n🔄 Recalculando grade...", parse_mode="HTML")
            agendar_tarefas_diarias(escopo="principal")
        await gerenciar_rotina_publico(message, state)
        
    else:
        dados_rotina["pausado"] = novo_status
        salvar_config_rotina(dados_rotina)
        if novo_status: await message.answer("⏸️ <b>Rotinas Principais PAUSADAS.</b>", parse_mode="HTML")
        else:
            await message.answer("▶️ <b>Rotinas Principais ATIVAS.</b>\n🔄 Recalculando grade...", parse_mode="HTML")
            agendar_tarefas_diarias(escopo="principal")
        await gerenciar_rotina(message, state)

# ✅ NOVO: Handler específico para corrigir o "Voltar" na pausa programada
@dp.message(PausaProgramadaFluxo.aguardando_selecao_servicos, F.text == "Voltar 🔙")
@dp.message(PausaProgramadaFluxo.aguardando_data_retorno, F.text == "Voltar 🔙")
@dp.message(PausaProgramadaFluxo.aguardando_intencao_encerramento, F.text == "Voltar 🔙")
async def voltar_pausa_para_inicio(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if EXIBIR_LOGS: logger.info("🔙 Comando Voltar acionado na Pausa Programada.")
    await state.clear()
    await message.answer("Operação cancelada. Voltando ao menu de configurações...")
    await menu_configuracoes(message, state)

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
    if dados.get("pausado", False):
        await message.answer("⚠️ <b>Ação Bloqueada:</b> O SPAM Principal está <b>PAUSADO</b>. Retome-o antes de tentar disparos manuais.", parse_mode="HTML")
        return
        
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
    if dados.get("pausado", False):
        await message.answer("⚠️ <b>Ação Bloqueada:</b> O SPAM Viral está <b>PAUSADO</b>. Retome-o antes de tentar disparos manuais.", parse_mode="HTML")
        return
        
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
        "promo_viral": "Convite do Grupo Viral 🚀",
        "promo_publico": "Promo Público 🗣️"
    }
    
    # Ordem de exibição forçada para organizar o painel
    ordem_exibicao = ["bom_dia", "incentivo", "link_grupo", "divulgar_gem", "promo_viral", "promo_publico", "boa_noite"]
    
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
            [KeyboardButton(text="Editar Rotinas ✏️"), KeyboardButton(text="Disparos Manuais 🚀")],
            [KeyboardButton(text=texto_botao_pausa), KeyboardButton(text="Voltar às Configs 🔙")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    
    texto += "Selecione o que deseja gerir abaixo:"
    await message.answer(texto, reply_markup=teclado_dinamico_rotina, parse_mode="HTML")
    await state.update_data(menu_origem="principal") # ✅ Adicione esta linha exata aqui
    await state.set_state(ConfigRotina.menu_principal)

@dp.message(ConfigRotina.menu_principal, F.text.in_(["Editar Bom Dia ☀️", "Editar Boa Noite 🌙", "Editar Incentivo 🔥", "Editar Convite 🔗", "Editar Prompt GEM 🤖", "Editar Convite Viral 🚀", "Editar Promo Público 🗣️", "Editar Convite Afiliados 🚀", "Editar Convite do Grupo 🔗", "Editar Prompt GEM 🤖\u200b", "Editar Promo Público 👥", "Editar Convite (Próprio) 🔗", "Editar Promo Principal 🌟", "Editar Promo Viral 💥"]))
async def pedir_horario_rotina(message: types.Message, state: FSMContext):
    if EXIBIR_LOGS: logger.info(f"✏️ Iniciando edição da rotina: {message.text}")
    if EXIBIR_LOGS: logger.info(f"✏️ Processando edição da rotina selecionada: {message.text}")
    tipo_map = {
        "Editar Bom Dia ☀️": "bom_dia",
        "Editar Boa Noite 🌙": "boa_noite",
        "Editar Incentivo 🔥": "incentivo",
        "Editar Convite 🔗": "link_grupo",
        "Editar Prompt GEM 🤖": "divulgar_gem",
        "Editar Convite Viral 🚀": "promo_viral",
        "Editar Promo Público 🗣️": "promo_publico",
        "Editar Convite Afiliados 🚀": "promo_principal",
        "Editar Convite do Grupo 🔗": "link_grupo_viral",
        "Editar Prompt GEM 🤖\u200b": "divulgar_gem_viral",
        "Editar Promo Público 👥": "promo_publico_viral",
        "Editar Convite (Próprio) 🔗": "link_grupo_publico",
        "Editar Promo Principal 🌟": "promo_principal_publico",
        "Editar Promo Viral 💥": "promo_viral_publico"
    }
    tipo = tipo_map[message.text]
    if EXIBIR_LOGS: logger.info(f"✅ Sucesso: Botão mapeado internamente para a chave '{tipo}'.")
    
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
    origem = data.get("menu_origem")

    # ✅ CORREÇÃO: o Grupo Público não tinha ramo próprio e caía no "else",
    # jogando o usuário no menu do Canal Principal.
    if origem == "espiao":
        agendar_tarefas_diarias(escopo="viral")
        texto_ok = "✅ Configuração salva! Os novos horários do Canal Viral já foram sorteados e agendados para hoje."
    elif origem == "publico":
        agendar_tarefas_diarias(escopo="principal")
        texto_ok = "✅ Configuração salva! Os novos horários do Grupo Público já foram sorteados e agendados para hoje."
    else:
        origem = "principal"
        agendar_tarefas_diarias(escopo="principal")
        texto_ok = "✅ Configuração salva! Os novos horários do Canal Principal já foram sorteados e agendados para hoje."

    await message.answer(texto_ok)

    # ✅ Volta para o submenu "Editar Rotinas", permitindo editar outra rotina em seguida
    await state.update_data(menu_origem=origem)
    await state.set_state(ConfigRotina.menu_principal)
    await submenu_editar_rotinas(message, state)

# --- SISTEMA DE GERENCIAMENTO DE FILA (INTERATIVO) ---
class GerenciarFilaFluxo(StatesGroup):
    menu_principal = State()
    aguardando_posicao_excluir = State()
    aguardando_confirmacao_exclusao = State()
    aguardando_posicao_editar = State()
    aguardando_nova_legenda = State()
    aguardando_posicao_reordenar = State()
    aguardando_nova_posicao = State()
    aguardando_decisao_limiar = State() # ✅ NOVO: Estado de decisão de fronteira
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
            data_postagem_str = item.get("data_postagem", "")
            
            # 🛡️ PENTE FINO: Só exibe os vídeos PENDENTES ou os que foram POSTADOS HOJE
            if is_postado and data_postagem_str != hoje_str:
                continue
            
            # Identifica se o vídeo pertence ao dia de Hoje (para fins de exibição da divisória do Boa Noite)
            is_hoje = (data_adicao_str == "2000-01-01" or (data_adicao_str and data_adicao_str <= hoje_str))
            
            # Se for o primeiro vídeo de "Amanhã" (ou além) e ainda não imprimimos a tampa de Boa Noite, imprime agora
            if not is_hoje and not is_postado and not imprimiu_bn:
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
                    # ✅ CORREÇÃO MESTRE: Limite rígido. Qualquer data futura será tratada como Amanhã.
                    status_previsao = "Amanhã 🟡"

                # ✅ CORREÇÃO: Interrogação Silenciosa do Motor APENAS para vídeos de HOJE
                hora_agendada_str = ""
                if status_previsao == "Hoje 🟢":
                    job_id_esperado = f"job_fila_postagem_{item.get('id')}"
                    job_encontrado = scheduler.get_job(job_id_esperado)
                    
                    if job_encontrado and getattr(job_encontrado, 'next_run_time', None):
                        hora_exata = job_encontrado.next_run_time.astimezone(fuso_horario).strftime("%H:%M")
                        hora_agendada_str = f" às {hora_exata}"
                    
                status_previsao_final = f"{status_previsao}{hora_agendada_str}"
                
            texto += f"<b>{i}. {nome_video}</b> | 📦 {nome_item}\n"
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
            # ✅ CORREÇÃO MESTRE: O contador global SEMPRE herda o próximo número da cascata, 
            # independentemente de ser maior ou menor. Isso garante sincronia total.
            salvar_contador(numero_atual_cascata)
            if EXIBIR_LOGS: logger.info(f"✅ Auto-correção do banco concluída. Novo contador global forçado para: {numero_atual_cascata}.")

        # ✅ NOVO GATILHO INTELIGENTE: Aciona o recálculo automático da grade!
        # Isso faz exatamente a mesma coisa que o botão "Atualizar Rotinas",
        # garantindo que os horários sejam recalculados para respeitar a nova ordem da fila sem atropelos.
        if EXIBIR_LOGS: logger.info("🔄 Alteração na fila detectada. Acionando recálculo inteligente dos horários...")
        agendar_tarefas_diarias(escopo="principal") # Garante que mexer na fila não reseta o canal viral

        await message.answer("✅ Operação concluída com sucesso!\n🔄 A fila e os horários foram sincronizados perfeitamente.")
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
            resumo = legenda_limpa.split('\n')[0]
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
            resumo = legenda_limpa.split('\n')[0]
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
        # ✅ TRAVA DE PROTEÇÃO: Impede mover vídeo para a posição de vídeos postados
        if 0 <= nova_posicao < len(fila) and fila[nova_posicao].get("postado", False):
            await message.answer("⚠️ <b>Ação Bloqueada:</b> Você não pode mover um vídeo pendente para o lugar de um vídeo que já foi postado.\n\nEscolha uma posição livre abaixo dos postados:", parse_mode="HTML")
            return

        if nova_posicao < 0: nova_posicao = 0
        
        await state.update_data(nova_posicao=nova_posicao)
        
        # 1. Simulação Perfeita: Removemos o item da posição original
        fila_simulada = fila.copy()
        item_movido = fila_simulada.pop(posicao_origem)
        
        agora = datetime.now(fuso_horario)
        hoje_str = agora.strftime("%Y-%m-%d")
        amanha_str = (agora + timedelta(days=1)).strftime("%Y-%m-%d")
        
        def format_date(d_str):
            if d_str == "2000-01-01" or d_str <= hoje_str: return "Hoje 🟢"
            if d_str == amanha_str: return "Amanhã 🟡"
            try: return f"{datetime.strptime(d_str, '%Y-%m-%d').strftime('%d/%m/%Y')} 🔵"
            except: return "Data Desconhecida"
        
        # Se a fila ficou vazia (só havia 1 vídeo)
        if len(fila_simulada) == 0:
            dados_rotina = ler_config_rotina()
            expediente_encerrado = dados_rotina.get("ultimo_boa_noite") == hoje_str
            nova_data_adicao = amanha_str if expediente_encerrado else "2000-01-01"
            await state.update_data(nova_data_adicao=nova_data_adicao)
            await enviar_confirmacao_reordenar(message, state, fila, posicao_origem, nova_posicao)
            return
            
        # 2. Inserção Virtual: Colocamos o item na nova posição para testar os vizinhos
        is_ultimo_item = False
        if nova_posicao >= len(fila_simulada):
            fila_simulada.append(item_movido)
            nova_posicao_virtual = len(fila_simulada) - 1
            is_ultimo_item = True
        else:
            fila_simulada.insert(nova_posicao, item_movido)
            nova_posicao_virtual = nova_posicao
            
        # 3. Análise de Vizinhança e Detecção de Limiar
        date_prev = None
        date_next = None
        
        if is_ultimo_item:
            date_prev = fila_simulada[nova_posicao_virtual - 1].get("data_adicao", "2000-01-01")
            
            # ✅ CORREÇÃO: Limite rígido. Se o penúltimo for Hoje, o próximo pode ser Amanhã.
            # Se o penúltimo JÁ for Amanhã, o próximo TAMBÉM SERÁ Amanhã (Não existe "depois de amanhã").
            if date_prev == "2000-01-01" or date_prev <= hoje_str:
                date_next = amanha_str
            else:
                date_next = amanha_str # Trava a data no amanhã
                
            if EXIBIR_LOGS: logger.info(f"🚧 Fila: Movimento para o final da fila. Limiar aberto gerado com trava diária: {date_prev} vs {date_next}.")
        else:
            # Comportamento normal: O vídeo foi inserido no meio da fila.
            if nova_posicao_virtual > 0:
                date_prev = fila_simulada[nova_posicao_virtual - 1].get("data_adicao", "2000-01-01")
                
            if nova_posicao_virtual < len(fila_simulada) - 1:
                date_next = fila_simulada[nova_posicao_virtual + 1].get("data_adicao", "2000-01-01")
                
            # ✅ CORREÇÃO: Garante que os vizinhos nunca ultrapassem o limite de Amanhã
            if date_prev and date_prev > amanha_str: date_prev = amanha_str
            if date_next and date_next > amanha_str: date_next = amanha_str
        
        # 4. Verificação de Limiar (Aciona a Pergunta ao Usuário)
        if date_prev and date_next:
            label_prev = format_date(date_prev)
            label_next = format_date(date_next)
            
            # Se os rótulos de dia forem diferentes, detectamos um limiar!
            if label_prev != label_next:
                await state.update_data(data_limiar_prev=date_prev, data_limiar_next=date_next)
                
                botoes = [
                    [KeyboardButton(text=label_prev), KeyboardButton(text=label_next)],
                    [KeyboardButton(text="Cancelar ❌")]
                ]
                teclado_limiar = ReplyKeyboardMarkup(keyboard=botoes, resize_keyboard=True, is_persistent=True)
                
                texto_pergunta = (
                    f"🤔 <b>Decisão de Limiar</b>\n\n"
                    f"A posição escolhida fica na divisa de datas ou no final da fila.\n"
                    f"Você deseja que este vídeo seja agendado para <b>{label_prev}</b> ou empurrado para <b>{label_next}</b>?"
                )
                if EXIBIR_LOGS: logger.info(f"🚧 Fila: Limiar de data detectado ({label_prev} vs {label_next}). Solicitando decisão.")
                await message.answer(texto_pergunta, reply_markup=teclado_limiar, parse_mode="HTML")
                await state.set_state(GerenciarFilaFluxo.aguardando_decisao_limiar)
                return 

        # 5. Se não houver limiar (ex: moveu dentro do mesmo dia)
        if date_prev: nova_data_adicao = date_prev
        elif date_next: nova_data_adicao = date_next
        else: nova_data_adicao = "2000-01-01"
            
        await state.update_data(nova_data_adicao=nova_data_adicao)
        await enviar_confirmacao_reordenar(message, state, fila, posicao_origem, nova_posicao)
    else:
        await message.answer("Erro de sincronização. Operação cancelada.")
        await menu_gerenciar_fila(message, state)

# ✅ NOVO: Handler que processa o clique no botão do Limiar
@dp.message(GerenciarFilaFluxo.aguardando_decisao_limiar)
async def processar_decisao_limiar(message: types.Message, state: FSMContext):
    texto = message.text
    
    if texto == "Cancelar ❌":
        await cancelar_fluxo_global(message, state)
        return

    data = await state.get_data()
    date_prev = data.get("data_limiar_prev")
    date_next = data.get("data_limiar_next")
    posicao_origem = data.get("posicao_origem")
    nova_posicao = data.get("nova_posicao")
    
    agora = datetime.now(fuso_horario)
    hoje_str = agora.strftime("%Y-%m-%d")
    amanha_str = (agora + timedelta(days=1)).strftime("%Y-%m-%d")
    
    def format_date(d_str):
        if d_str == "2000-01-01" or d_str <= hoje_str: return "Hoje 🟢"
        if d_str == amanha_str: return "Amanhã 🟡"
        try: return f"{datetime.strptime(d_str, '%Y-%m-%d').strftime('%d/%m/%Y')} 🔵"
        except: return "Data Desconhecida"
        
    label_prev = format_date(date_prev)
    label_next = format_date(date_next)
    
    nova_data_adicao = None
    if texto == label_prev:
        nova_data_adicao = date_prev
    elif texto == label_next:
        nova_data_adicao = date_next
        
    if not nova_data_adicao:
        await message.answer("Por favor, utilize os botões na tela para escolher a data.")
        return
        
    if EXIBIR_LOGS: logger.info(f"✅ Decisão de limiar recebida: O vídeo herdará a data '{texto}'.")
    await state.update_data(nova_data_adicao=nova_data_adicao)
    
    fila_data = ler_fila_postagens()
    fila = fila_data.get("fila", [])
    
    # Continua o fluxo normalmente para a confirmação visual
    await enviar_confirmacao_reordenar(message, state, fila, posicao_origem, nova_posicao)

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
        resumo = legenda_limpa.split('\n')[0]
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
            
            # ✅ CORREÇÃO: Se o vídeo foi empurrado para o futuro, remove a "bomba relógio" da memória de hoje
            agora = datetime.now(fuso_horario)
            hoje_str = agora.strftime("%Y-%m-%d")
            if nova_data_adicao != "2000-01-01" and nova_data_adicao > hoje_str:
                job_id_remover = f"job_fila_postagem_{id_movido}"
                try:
                    scheduler.remove_job(job_id_remover)
                    if EXIBIR_LOGS: logger.info(f"🧹 Agendamento de memória removido para o vídeo {id_movido} (Movido para o futuro).")
                except: pass
                
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
            resumo = legenda_limpa.split('\n')[0]
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
            resumo = legenda_limpa.split('\n')[0]
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
    padrao = {"fila": []}
    return ler_config_bd("fila_clonagem", padrao, arquivo_legado="fila_clonagem.json")

def salvar_fila_clonagem(dados):
    salvar_config_bd("fila_clonagem", dados)

async def processar_fila_espiao(forcar=False):
    dados_espiao = ler_alvos_espiao()
    canal_destino = dados_espiao.get("canal_destino")
    if not canal_destino: return 
        
    fila_data = ler_fila_clonagem()
    fila = fila_data.get("fila", [])
    intervalo_dias = dados_espiao.get("intervalo_dias", 1)
    
    inicio_janela = dados_espiao.get("inicio", 10)
    fim_janela = dados_espiao.get("fim", 22)
    modo = dados_espiao.get("modo", "aleatorio")
    
    agora = datetime.now(fuso_horario)
    hoje_str = agora.strftime("%Y-%m-%d")

    # --- 1. MOTOR MATEMÁTICO DE DISTRIBUIÇÃO ---
    itens_para_agendar = []
    
    for item in fila:
        if item.get("processado"): continue
        
        # Se forçou descarga, limpa o horário para aplicar a catraca imediata
        if forcar: item["horario_disparo"] = ""
        
        if not item.get("horario_disparo"):
            data_cap_str = item.get("data_captura", "")
            if data_cap_str:
                try:
                    data_cap_obj = datetime.strptime(data_cap_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario)
                except ValueError:
                    data_cap_obj = datetime.strptime(data_cap_str.split(" ")[0], "%Y-%m-%d").replace(tzinfo=fuso_horario)
                    
                data_alvo_obj = data_cap_obj + timedelta(days=intervalo_dias)
                dia_alvo = data_alvo_obj.strftime("%Y-%m-%d")
                
                # Resgata o vídeo se for para hoje, ou se estivermos puxando o gatilho
                if dia_alvo <= hoje_str or forcar:
                    itens_para_agendar.append(item)

    if itens_para_agendar:
        # ✅ ACIONANDO O NOVO MOTOR MATEMÁTICO CENTRALIZADO
        config_fila = {
            "inicio": inicio_janela,
            "fim": fim_janela,
            "modo": modo,
            "intervalo_dias": intervalo_dias
        }
        
        # O Motor Central aplica a regra de D+X, catraca anti-ban e espaçamento orgânico
        calcular_horarios_distribuicao(itens_para_agendar, config_fila, forcar)
        
        salvar_fila_clonagem(fila_data)
        if EXIBIR_LOGS: logger.info(f"📅 [Espião] Motor Central acionado! {len(itens_para_agendar)} clones organizados com sucesso.")

    # --- 2. MOTOR DE EXECUÇÃO (A Catraca Anti-Ban) ---
    itens_para_disparar = []
    for item in fila:
        if not item.get("processado") and item.get("horario_disparo"):
            try:
                hd_obj = datetime.strptime(item["horario_disparo"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario)
                if hd_obj <= agora:
                    itens_para_disparar.append(item)
            except Exception: pass
                
    if not itens_para_disparar:
        hoje_faxina = agora.strftime("%Y-%m-%d")
        fila_limpa = [i for i in fila if not i.get("processado") or i.get("data_postagem") == hoje_faxina]
        if len(fila_limpa) != len(fila):
            fila_data["fila"] = fila_limpa
            salvar_fila_clonagem(fila_data)
        return

    for item_pendente in itens_para_disparar:
        # TRAVA DE SILÊNCIO (VIRAL)
        rotinas_virais = ["job_rotina_promo_principal", "job_rotina_link_grupo_viral", "job_rotina_divulgar_gem_viral"]
        conflito_silencio = False
        tempo_conflito = None
        
        for job in scheduler.get_jobs():
            if any(rv in job.id for rv in rotinas_virais) and getattr(job, 'next_run_time', None):
                tempo_rotina = job.next_run_time.astimezone(fuso_horario)
                # Mantemos a sua regra rigorosa de proteção de 15 minutos
                if abs((agora - tempo_rotina).total_seconds() / 60) <= 15:
                    conflito_silencio = True
                    tempo_conflito = tempo_rotina
                    break
                    
        if conflito_silencio:
            # ✅ REAGENDAMENTO EM CASCATA (EFEITO DOMINÓ)
            if tempo_conflito:
                novo_horario_seguro = tempo_conflito + timedelta(minutes=16)
                if novo_horario_seguro <= agora:
                    novo_horario_seguro = agora + timedelta(minutes=2)
            else:
                novo_horario_seguro = agora + timedelta(minutes=16)
                
            # Em vez de colocar todos no mesmo minuto, recriamos a fila mantendo espaçamento orgânico
            pendentes = [i for i in fila if not i.get("processado")]
            
            # Ordena pela previsão atual para manter o FIFO
            def sort_by_date(x):
                try: return datetime.strptime(x.get("horario_disparo", "2099-01-01 00:00:00"), "%Y-%m-%d %H:%M:%S")
                except: return datetime.max
            pendentes.sort(key=sort_by_date)
            
            tempo_acumulado = novo_horario_seguro
            houve_alteracao = False
            
            for p in pendentes:
                try:
                    h_atual = datetime.strptime(p.get("horario_disparo", "2000-01-01 00:00:00"), "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario)
                except:
                    h_atual = datetime.now(fuso_horario) - timedelta(days=1000)
                    
                # Se o vídeo está marcado para um horário dentro do bloqueio (ou antes), empurramos ele
                if h_atual < tempo_acumulado:
                    p["horario_disparo"] = tempo_acumulado.strftime("%Y-%m-%d %H:%M:%S")
                    tempo_acumulado += timedelta(seconds=20) # Espaçamento de segurança
                    houve_alteracao = True
                else:
                    # Se o vídeo já está seguro no futuro, a catraca pula para logo depois dele
                    tempo_acumulado = h_atual + timedelta(seconds=20)
                    
            if houve_alteracao:
                salvar_fila_clonagem(fila_data)
                if EXIBIR_LOGS: logger.info(f"🤫 [Espião] Trava ativada! Fila indiana empurrada com sucesso a partir de {novo_horario_seguro.strftime('%H:%M:%S')}.")
                
            break # Volta no próximo minuto
            
        caminho_video = item_pendente["caminho_video"]
        link_original = item_pendente["link_original"]
        item_id = item_pendente["id"]

        if not os.path.exists(caminho_video):
            item_pendente["processado"] = True
            salvar_fila_clonagem(fila_data)
            continue
            
        if EXIBIR_LOGS: logger.info(f"🕵️ Processando clone agendado: {item_id}")
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
            if not texto_ia: raise Exception("IA não retornou dados.")
        except Exception as e:
            registrar_erro_json(f"processar_fila_espiao IA: {e}", origem="espiao.py")
            texto_ia = "Vídeo do Produto 🛍️\n#Oferta"
            
        linhas_ia = texto_ia.split('\n')
        nome_produto = linhas_ia[0].strip()
        hashtags = '\n'.join(linhas_ia[1:]).strip() if len(linhas_ia) > 1 else ""
        
        legenda_postagem = f"<b>{nome_produto}</b>\n\n🔗 <b>Link do Produto:</b>\n{link_final}"
        if hashtags: legenda_postagem += f"\n\n<i>{hashtags}</i>"
        
        try:
            if caminho_video.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                raise Exception("O ficheiro retido é uma imagem.")
            arquivo = FSInputFile(caminho_video)
            msg_enviada = await bot.send_video(chat_id=canal_destino, video=arquivo, caption=legenda_postagem, parse_mode="HTML")
            
            # ✅ CORREÇÃO DUPLA: Grava o ID do Destino e a Legenda Nova (com o Nome da IA) no banco de dados!
            item_pendente["msg_postada_id"] = msg_enviada.message_id
            item_pendente["legenda"] = legenda_postagem
            
            if EXIBIR_LOGS: logger.info(f"✅ Clone {item_id} publicado com sucesso! ID: {msg_enviada.message_id}")
            try: os.remove(caminho_video)
            except: pass
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Falha ao postar clone: {e}")
            try: os.rename(caminho_video, caminho_video + ".pendente")
            except: pass
            
        item_pendente["processado"] = True
        item_pendente["data_postagem"] = agora.strftime("%Y-%m-%d")
        item_pendente["horario_postagem"] = agora.strftime("%H:%M")
        salvar_fila_clonagem(fila_data)
        
        # 🛡️ Catraca limitadora de segurança (Previne banimento no D+0)
        await asyncio.sleep(15)

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
    # Trava em 90 dias absolutos para respeitar a barreira da API "last 3 months"
    if dias_retroativos > 90: dias_retroativos = 90
    if dias_retroativos < 5: dias_retroativos = 5
    
    if EXIBIR_LOGS: logger.info(f"🔍 [Pente Fino] Pendentes antigos detetados! A requisitar relatório dos últimos {dias_retroativos} dias à Shopee...")
    
    conversoes = await buscar_dados_financeiros_shopee(dias_retroativos)
    if conversoes:
        processar_e_salvar_pedidos_api(conversoes)
        if EXIBIR_LOGS: logger.info("✅ [Pente Fino] Varredura profunda concluída! Pendentes antigos consolidados (Confirmados ou Cancelados).")

async def checkup_diario_grupos():
    if EXIBIR_LOGS: logger.info("🚀 Consolidando relatório de saúde diário do sistema...")
    
    relatorio = "📊 <b>Relatório Diário de Saúde dos Robôs</b>\n\n"
    
    # 1. Auditoria passiva do Espião (lendo o status do banco SQLite)
    try:
        dados_espiao = ler_alvos_espiao()
            
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
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"Erro na auditoria do espião: {e}")
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
        dados = ler_fila_clonagem()
        fila = dados.get("fila", [])
            
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

@dp.message(SubmissaoAdminFluxo.menu_principal, F.text.in_(["Pausar Robô Moderador ⏸️", "Retomar Robô Moderador ▶️", "Ativar Robô Moderador ⚙️", "Desativar Robô Moderador 🛑"]))
async def pedir_confirmacao_toggle(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    config = ler_submissao_config()
    if not config.get("grupo_id"):
        return await message.answer("⚠️ Você precisa configurar o Grupo e os Tópicos primeiro.")

    acao = "pausar" if config.get("ativo") else "retomar"
    await state.update_data(acao_moderador_pub=acao)

    texto_botao = "Confirmar Pausa ✅" if acao == "pausar" else "Confirmar Retomada ✅"
    teclado_confirmacao = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texto_botao), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )

    texto = (
        f"⚠️ Tem certeza de que deseja <b>{'PAUSAR' if acao == 'pausar' else 'RETOMAR'}</b> a moderação automática de vídeos neste grupo?\n\n"
        "<i>(Quando em execução, a IA analisa e aprova automaticamente os vídeos enviados pelos membros no tópico de escuta)</i>"
    )

    await message.answer(texto, reply_markup=teclado_confirmacao, parse_mode="HTML")
    await state.set_state(SubmissaoAdminFluxo.aguardando_confirmacao_toggle)

@dp.message(SubmissaoAdminFluxo.aguardando_confirmacao_toggle)
async def processar_toggle_submissoes(message: types.Message, state: FSMContext):
    if not message.text or "Confirmar" not in message.text:
        await message.answer("Por favor, clique no botão para confirmar ou cancelar.")
        return

    dados = await state.get_data()
    acao = dados.get("acao_moderador_pub")

    config = ler_submissao_config()
    if acao in ("pausar", "retomar"):
        config["ativo"] = (acao == "retomar")
    else:
        config["ativo"] = not config.get("ativo", False)
    salvar_submissao_config(config)

    if config["ativo"]:
        icone = "▶️"
        status = "RETOMADO"
    else:
        icone = "⏸️"
        status = "PAUSADO"

    if EXIBIR_LOGS: logger.info(f"⚙️ Status do Robô Moderador alterado para: {status}")
    await message.answer(f"{icone} O Robô Moderador foi <b>{status}</b> com sucesso.", parse_mode="HTML")
    await submenu_robo_moderador(message, state)

@dp.message(SubmissaoAdminFluxo.menu_principal, F.text == "Configurações do Robô de Rotina do Grupo Público ⏰")
async def gerenciar_rotina_publico(message: types.Message, state: FSMContext):
    dados = ler_config_rotina()
    
    # --- LÓGICA DE EXIBIÇÃO DOS TÓPICOS DE ROTINA ---
    config_sub = ler_submissao_config()
    grupo_id = config_sub.get("grupo_id")
    grupo_id_str = str(grupo_id) if grupo_id else ""
    
    topico_escuta = config_sub.get("topico_envio")
    topico_escuta_str = str(topico_escuta) if topico_escuta else ""
    chave_escuta = f"{grupo_id_str}_{topico_escuta_str}"
    
    topico_vitrine = config_sub.get("topico_destino")
    topico_vitrine_str = str(topico_vitrine) if topico_vitrine else ""
    chave_vitrine = f"{grupo_id_str}_{topico_vitrine_str}"
    
    cache_nomes = ler_cache_nomes_grupos()
    
    nome_escuta = cache_nomes.get(chave_escuta) or config_sub.get("nome_topico_envio") or "Tópico de Escuta"
    icone_escuta = "✅" if chave_escuta in cache_nomes else "⏳"
    
    nome_vitrine = cache_nomes.get(chave_vitrine) or config_sub.get("nome_topico_destino") or "Tópico de Postagem"
    icone_vitrine = "✅" if chave_vitrine in cache_nomes else "⏳"

    topicos_rotina = config_sub.get("topicos_rotina", [])
    nomes_rotinas_salvos = config_sub.get("nomes_topicos_rotina", {})

    def resolver_nome_topico(numero_topico):
        t_str = str(numero_topico)
        for chave in (f"{grupo_id_str}_{t_str}", f"{grupo_id_str}:{t_str}"):
            if cache_nomes.get(chave):
                return cache_nomes[chave], "✅"

        nome = nomes_rotinas_salvos.get(t_str)
        if nome:
            return nome, "✅"

        if topico_vitrine_str and t_str == topico_vitrine_str:
            return nome_vitrine, icone_vitrine
        if topico_escuta_str and t_str == topico_escuta_str:
            return nome_escuta, icone_escuta

        if t_str == "1":
            return "Geral", "✅"

        return f"Tópico {t_str}", "⏳"

    if topicos_rotina:
        lista_exibicao = []
        for t in topicos_rotina:
            id_completo_topico = f"{grupo_id_str}_{t}"
            nome_t, icone_t = resolver_nome_topico(t)
            lista_exibicao.append(f"   {icone_t} {nome_t} (<code>{id_completo_topico}</code>)")
        display_rotinas = "\n" + "\n".join(lista_exibicao)
    else:
        display_rotinas = "\n   ✅ <i>Chat Geral (Padrão)</i>"

    # --- MONTAGEM DO TEXTO ---
    texto = "⏰ <b>Rotinas do Grupo Público</b>\n\n"
    texto += f"📢 <b>Alvos das Rotinas:</b>{display_rotinas}\n"
    texto += "<i>(Use o botão \"Gerenciar Alvos de Postagem 🎯\" para ativar ou desativar estes locais)</i>\n\n"
    
    config_pub = dados.get("link_grupo_publico", {"inicio": 9, "fim": 21, "frequencia": 2})
    config_princ = dados.get("promo_principal_publico", {"inicio": 10, "fim": 20, "frequencia": 1})
    config_vir = dados.get("promo_viral_publico", {"inicio": 10, "fim": 20, "frequencia": 1})
    
    texto += f"🔹 <b>Convite (Próprio Grupo) 🔗</b>\n   Janela: {config_pub['inicio']}h às {config_pub['fim']}h | {config_pub['frequencia']}x/dia\n\n"
    texto += f"🔹 <b>Promo Canal Principal 🌟</b>\n   Janela: {config_princ['inicio']}h às {config_princ['fim']}h | {config_princ['frequencia']}x/dia\n\n"
    texto += f"🔹 <b>Promo Canal Viral 💥</b>\n   Janela: {config_vir['inicio']}h às {config_vir['fim']}h | {config_vir['frequencia']}x/dia\n\n"
    
    texto_botao_pausa = "Retomar Rotinas ▶️" if dados.get("pausado_publico") else "Pausar Rotinas ⏸️"
    teclado = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Editar Rotinas ✏️"), KeyboardButton(text="Disparos Manuais 🚀")],
            [KeyboardButton(text="Gerenciar Alvos de Postagem 🎯")],
            [KeyboardButton(text=texto_botao_pausa)],
            [KeyboardButton(text="Voltar ao Painel Público 🔙")]
        ], resize_keyboard=True, is_persistent=True
    )
    await message.answer(texto, reply_markup=teclado, parse_mode="HTML")
    await state.update_data(menu_origem="publico")
    await state.set_state(ConfigRotina.menu_principal)

@dp.message(ConfigRotina.menu_principal, F.text == "Voltar ao Painel Público 🔙")
async def voltar_pub_rotinas(message: types.Message, state: FSMContext):
    await state.clear()
    await painel_submissoes(message, state)

@dp.message(SubmissaoAdminFluxo.menu_principal, F.text == "Definir Tópicos de Moderação 💬")
async def menu_edicao_grupo_publico(message: types.Message, state: FSMContext):
    if EXIBIR_LOGS: logger.info("⚙️ Acessando submenu modular de configuração de tópicos.")
    
    teclado = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Editar Tópico de Escuta 💬"), KeyboardButton(text="Editar Tópico de Postagem 📤")],
            [KeyboardButton(text="Voltar às Configurações 🔙")]
        ], resize_keyboard=True, is_persistent=True
    )
    
    texto = (
        "💬 <b>Tópicos de Moderação</b>\n\n"
        "Defina os dois tópicos do Grupo Público em que o Robô Moderador atua:\n\n"
        "📥 <b>Tópico de Escuta:</b> o tópico que o robô fica vigiando. É onde os membros "
        "enviam os vídeos para serem analisados pela IA.\n\n"
        "📤 <b>Tópico de Postagem:</b> o tópico onde o robô publica automaticamente os vídeos "
        "que foram aprovados na análise.\n\n"
        "<i>(Os alvos das mensagens automáticas de divulgação ficam em Configurações do Robô de Rotina do Grupo Público ⏰)</i>\n\n"
        "Selecione qual tópico deseja alterar:"
    )
    await message.answer(texto, parse_mode="HTML", reply_markup=teclado)
    await state.set_state(SubmissaoAdminFluxo.aguardando_selecao_edicao_grupo)

@dp.message(SubmissaoAdminFluxo.aguardando_selecao_edicao_grupo)
async def selecionar_campo_grupo_publico(message: types.Message, state: FSMContext):
    if message.text == "Voltar às Configurações 🔙":
        await state.set_state(SubmissaoAdminFluxo.menu_principal)
        await submenu_robo_moderador(message, state)
        return

    # ✅ NOVO: o exemplo é montado com a configuração atual do próprio usuário
    config_atual = ler_submissao_config()
    grupo_id_atual = str(config_atual.get("grupo_id") or "")

    def montar_exemplo(topico_atual):
        if grupo_id_atual and topico_atual not in (None, ""):
            return f"<code>{grupo_id_atual}_{topico_atual}</code>"
        return "<code>-1001234567890_5</code>\n<i>(exemplo genérico: o grupo ainda não foi definido)</i>"

    opcoes = {
        "Editar Tópico de Escuta 💬": ("escuta",
            "📥 <b>Tópico de Escuta</b>\n\n"
            "Envie o Link ou o ID numérico do tópico onde os membros enviam os vídeos.\n\n"
            "<i>Exemplo atualizado com a sua configuração:</i>\n"
            f"{montar_exemplo(config_atual.get('topico_envio'))}"
        ),
        "Editar Tópico de Postagem 📤": ("vitrine",
            "📤 <b>Tópico de Postagem</b>\n\n"
            "Envie o Link ou o ID numérico do tópico onde o robô irá publicar automaticamente os vídeos aprovados.\n\n"
            "<i>Exemplo atualizado com a sua configuração:</i>\n"
            f"{montar_exemplo(config_atual.get('topico_destino'))}"
        )
    }
    
    selecao = opcoes.get(message.text)
    if not selecao:
        await message.answer("⚠️ Use os botões abaixo para escolher o que editar.")
        return
        
    campo, pergunta = selecao
    await state.update_data(campo_edicao_grupo=campo, nome_campo_visual=message.text)
    
    await message.answer(pergunta, parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(SubmissaoAdminFluxo.aguardando_novo_valor_grupo)

@dp.message(SubmissaoAdminFluxo.aguardando_novo_valor_grupo)
async def receber_novo_valor_grupo(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await message.answer("Operação cancelada.")
        await menu_edicao_grupo_publico(message, state)
        return

    data = await state.get_data()
    campo = data.get("campo_edicao_grupo")
    texto_usuario = message.text.strip()
    
    msg_status = await message.answer("⏳ Validando entrada...", reply_markup=teclado_cancelar)

    if campo not in ("escuta", "vitrine", "rotina"):
        await msg_status.delete()
        await message.answer("⚠️ Sessão de edição expirada. Selecione novamente o que deseja editar.")
        await menu_edicao_grupo_publico(message, state)
        return

    if campo in ["escuta", "vitrine"]:
        sucesso, id_final, nome = await validar_e_formatar_alvo(bot, texto_usuario)
        await msg_status.delete()
        
        if sucesso:
            if ":" in id_final:
                grupo_id, topico_id = id_final.split(":")
            else:
                grupo_id = id_final
                topico_id = "0"
            
            salvar_nome_grupo(grupo_id, nome)
            await state.update_data(novo_grupo_id=grupo_id, novo_topico_id=int(topico_id))
            texto_conf = f"✅ Canal/Tópico encontrado: <b>{nome}</b> (ID: <code>{topico_id}</code>)\n\nDeseja confirmar e salvar esta alteração?"
        else:
            import re
            if "t.me/c/" in texto_usuario:
                so_num = re.search(r't\.me/c/(\d+)', texto_usuario)
                grupo_id = f"-100{so_num.group(1)}" if so_num else texto_usuario
                topico_id = texto_usuario.split("/")[-1] if "/" in texto_usuario else "0"
            else:
                grupo_id = texto_usuario
                topico_id = "0"
                
            await state.update_data(novo_grupo_id=grupo_id, novo_topico_id=int(topico_id))
            texto_conf = f"⚠️ O bot não encontrou este chat na base. Os IDs extraídos foram:\nGrupo: <code>{grupo_id}</code>\nTópico: <code>{topico_id}</code>\n\nDeseja forçar o salvamento mesmo assim?"

    elif campo == "rotina":
        await msg_status.delete()
        if texto_usuario == "0":
            topicos_finais = []
            texto_conf = "✅ Você definiu que as rotinas irão para o <b>Chat Geral (Padrão)</b>.\n\nDeseja confirmar esta alteração?"
        else:
            entradas = [t.strip() for t in texto_usuario.split(",")]
            topicos_finais = []
            import re
            for entrada in entradas:
                if "t.me/" in entrada:
                    partes = entrada.split("/")
                    if len(partes) >= 5: topicos_finais.append(partes[-1])
                elif "_" in entrada: topicos_finais.append(entrada.split("_")[-1])
                elif ":" in entrada: topicos_finais.append(entrada.split(":")[-1])
                elif entrada.isdigit():
                    if entrada != "0": topicos_finais.append(entrada)

            texto_conf = f"✅ Tópicos de rotina extraídos: <code>{', '.join(topicos_finais)}</code>\n<i>(Os nomes reais serão sincronizados em background pelo Userbot)</i>\n\nDeseja confirmar esta alteração?"

        await state.update_data(novos_topicos_rotina=topicos_finais)

    teclado_conf = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
        resize_keyboard=True, is_persistent=True
    )
    await message.answer(texto_conf, parse_mode="HTML", reply_markup=teclado_conf)
    await state.set_state(SubmissaoAdminFluxo.aguardando_confirmacao_grupo)

@dp.message(SubmissaoAdminFluxo.aguardando_confirmacao_grupo)
async def confirmar_salvamento_grupo(message: types.Message, state: FSMContext):
    if message.text == "Cancelar ❌":
        await message.answer("Operação cancelada.")
        await menu_edicao_grupo_publico(message, state)
        return
        
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, clique em Aprovar ou Cancelar.")
        return

    data = await state.get_data()
    campo = data.get("campo_edicao_grupo")
    
    config = ler_submissao_config()
    
    if campo == "escuta":
        config["grupo_id"] = data.get("novo_grupo_id")
        config["topico_envio"] = data.get("novo_topico_id")
    elif campo == "vitrine":
        config["grupo_id"] = data.get("novo_grupo_id")
        config["topico_destino"] = data.get("novo_topico_id")
    elif campo == "rotina":
        config["topicos_rotina"] = data.get("novos_topicos_rotina")

    salvar_submissao_config(config)
    
    if EXIBIR_LOGS: logger.info(f"✅ Painel Público: Configuração '{campo}' atualizada com sucesso.")
    await message.answer("✅ <b>Configuração atualizada com sucesso!</b>", parse_mode="HTML")
    
    await painel_submissoes(message, state)

# ==========================================
# GERADOR DO BOTÃO FIXO (Aberto para Todos) 📌
# ==========================================
from aiogram.filters import Command

TEXTO_BOTAO_OFERTAS = (
    "👋 <b>Bem-vindo ao canal de submissões!</b>\n\n"
    "Quer divulgar a sua oferta da Shopee na nossa comunidade e faturar junto com a gente?\n\n"
    "Clique no botão abaixo e o nosso robô vai te guiar passo a passo para enviar o vídeo e os seus links!\n\n"
    "<i>(As ofertas aprovadas pela nossa IA serão postadas automaticamente no mural público com os seus créditos!)</i>"
)

# ✅ NOVO: mantém o painel de submissão SEMPRE como a última mensagem do tópico.
# Ele é apagado e recriado embaixo, então nunca sobe na tela nem some.
_lock_botao_ofertas = asyncio.Lock()

async def reenviar_botao_ofertas():
    async with _lock_botao_ofertas:
        config = ler_submissao_config()
        grupo_id = config.get("grupo_id")
        topico_envio = config.get("topico_envio")

        if not grupo_id or topico_envio is None:
            if EXIBIR_LOGS: logger.warning("⚠️ [Painel Fixo] Grupo ou Tópico de Escuta não configurado. Reenvio abortado.")
            return

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        teclado_iniciar = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Iniciar Postagem de Oferta", callback_data="iniciar_wizard_oferta")]
        ])

        thread_param = int(topico_envio) if int(topico_envio) not in (0, 1) else None

        try:
            msg = await bot.send_message(
                chat_id=grupo_id,
                text=TEXTO_BOTAO_OFERTAS,
                reply_markup=teclado_iniciar,
                parse_mode="HTML",
                message_thread_id=thread_param,
                disable_notification=True
            )
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ [Painel Fixo] Falha ao reenviar o painel de submissão: {e}")
            return

        # Só apaga o painel anterior DEPOIS que o novo já está no ar (evita ficar sem painel)
        msg_antiga = config.get("msg_botao_ofertas")
        if msg_antiga and msg_antiga != msg.message_id:
            try: await bot.delete_message(chat_id=grupo_id, message_id=int(msg_antiga))
            except Exception: pass

        config["msg_botao_ofertas"] = msg.message_id
        salvar_submissao_config(config)

        # ⚠️ NÃO fixar: cada pin_chat_message gera uma mensagem de serviço
        # ("Fulano fixou uma mensagem") que se acumula no tópico. Como o painel
        # já é sempre a última mensagem, fixar deixou de ser necessário.

        if EXIBIR_LOGS: logger.info(f"📌 [Painel Fixo] Painel de submissão recriado no fim do tópico (ID {msg.message_id}).")

@dp.message(Command("botao_ofertas"))
async def gerar_botao_permanente(message: types.Message):
    if EXIBIR_LOGS: 
        logger.info(f"📥 Solicitada criação do botão público no tópico. Usuário: {message.from_user.id}")
    
    await reenviar_botao_ofertas()
            
    # Remove a mensagem de comando para manter o tópico limpo
    try: 
        await message.delete()
    except Exception: 
        pass

# ==========================================
# FLUXO DO USUÁRIO: MODERAÇÃO GUIADA POR BOTÕES 🧠
# ==========================================

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio

def checar_permissao_topico(message: types.Message):
    """Valida se a mensagem pertence ao grupo e tópico configurados para submissão pública."""
    config = ler_submissao_config()
    if not config.get("ativo"): 
        return False, None
    grupo_id = config.get("grupo_id")
    topico_envio = config.get("topico_envio")
    if not grupo_id or topico_envio is None: 
        return False, None
        
    chat_id_str = str(message.chat.id)
    if chat_id_str != str(grupo_id) and chat_id_str.replace("-100", "") != str(grupo_id).replace("-100", ""): 
        return False, None
    if str(message.message_thread_id or 0) != str(topico_envio): 
        return False, None
    if message.from_user.is_bot: 
        return False, None # Filtra apenas outros bots para evitar loops
        
    return True, config

async def auto_limpar_sessao(chat_id, message_id, state: FSMContext, tempo=180):
    """Timer fantasma de 3 minutos. Apaga o painel se o usuário abandonar a submissão no meio."""
    await asyncio.sleep(tempo)
    try: 
        await bot.delete_message(chat_id, message_id)
    except: 
        pass
    
    # Limpa a memória apenas se o usuário ainda estiver na mesma sessão
    data = await state.get_data()
    if data.get("msg_wizard_id") == message_id:
        await state.clear()

# 1. GATILHO INICIAL: Qualquer mensagem fora de ordem aciona o botão de Iniciar
@dp.message(F.chat.type.in_(["supergroup", "group"]), StateFilter(None))
async def interceptar_envio_livre(message: types.Message, state: FSMContext):
    permitido, config = checar_permissao_topico(message)
    if not permitido: 
        return
    
    # Remove o envio avulso para evitar poluição visual
    try: 
        await message.delete()
    except Exception: 
        pass
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    teclado_iniciar = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Iniciar Postagem de Oferta", callback_data="iniciar_wizard_oferta")]
    ])
    
    user_mention = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    aviso = await message.answer(
        f"👋 Olá, {user_mention}! Para submeter uma oferta, por favor utilize o painel interativo abaixo:",
        reply_markup=teclado_iniciar,
        parse_mode="HTML"
    )
    
    # Remove a notificação temporária após 15 segundos
    await asyncio.sleep(15)
    try: 
        await aviso.delete()
    except Exception: 
        pass

    # ✅ Devolve o painel para o fim do tópico
    await reenviar_botao_ofertas()

# 2. PASSO 1: Clicou no botão -> Pede o Vídeo (Cria o Painel Deslizante)
@dp.callback_query(F.data == "iniciar_wizard_oferta")
async def wizard_pedir_video(callback: types.CallbackQuery, state: FSMContext):
    teclado_cancelar_inline = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancelar", callback_data="cancelar_wizard")]])
    
    msg_passo = await callback.message.answer(
        "📍 <b>PASSO 1 de 3:</b>\n\n"
        "Por favor, envie aqui o <b>VÍDEO</b> do produto que você deseja divulgar.",
        parse_mode="HTML",
        reply_markup=teclado_cancelar_inline
    )
    await state.set_state(SubmissaoUsuarioInterativa.aguardando_video)
    await state.update_data(msg_wizard_id=msg_passo.message_id)
    await callback.answer()
    
    # Inicia o timer de autodestruição caso o usuário abandone o menu
    asyncio.create_task(auto_limpar_sessao(callback.message.chat.id, msg_passo.message_id, state, 180))

# 3. PASSO 2: Recebe o Vídeo -> Edita o Painel pedindo a Shopee
@dp.message(SubmissaoUsuarioInterativa.aguardando_video)
async def wizard_receber_video(message: types.Message, state: FSMContext):
    permitido, config = checar_permissao_topico(message)
    if not permitido: return
    try: await message.delete() # Limpa o vídeo do usuário
    except: pass

    data = await state.get_data()
    msg_wizard_id = data.get("msg_wizard_id")

    if not message.video:
        aviso = await message.answer("⚠️ Por favor, envie um arquivo de <b>VÍDEO</b>.", parse_mode="HTML")
        await asyncio.sleep(4)
        try: await aviso.delete()
        except: pass
        return

    await state.update_data(video_file_id=message.video.file_id)
    teclado_cancelar_inline = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancelar", callback_data="cancelar_wizard")]])
    
    try:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg_wizard_id,
            text="📍 <b>PASSO 2 de 3:</b>\n\nÓtimo! Vídeo recebido. 🎬\n\nAgora, cole aqui o seu <b>Link de Afiliado da SHOPEE</b> 🛒 referente a este produto:",
            parse_mode="HTML",
            reply_markup=teclado_cancelar_inline
        )
    except: pass
    await state.set_state(SubmissaoUsuarioInterativa.aguardando_shopee)

# 4. PASSO 3: Recebe Shopee -> Edita o Painel pedindo TikTok (Opcional)
@dp.message(SubmissaoUsuarioInterativa.aguardando_shopee)
async def wizard_receber_shopee(message: types.Message, state: FSMContext):
    permitido, config = checar_permissao_topico(message)
    if not permitido: return
    try: await message.delete() # Limpa o link do usuário
    except: pass

    data = await state.get_data()
    msg_wizard_id = data.get("msg_wizard_id")
    link = message.text

    if not link or ("shopee" not in link.lower() and "shp.ee" not in link.lower()):
        aviso = await message.answer("⚠️ O link precisa ser da Shopee. Tente novamente colando o link correto:", parse_mode="HTML")
        await asyncio.sleep(4)
        try: await aviso.delete()
        except: pass
        return

    await state.update_data(link_shopee=link)
    teclado_tiktok = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Pular TikTok ⏭️", callback_data="pular_tiktok")],
        [InlineKeyboardButton(text="❌ Cancelar Tudo", callback_data="cancelar_wizard")]
    ])
    
    try:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg_wizard_id,
            text="📍 <b>PASSO 3 de 3 (Opcional):</b>\n\nVocê também tem o <b>Link de Afiliado do TIKTOK</b> 🎵 para este produto?\n\nSe sim, cole o link aqui. Se não tiver, basta clicar no botão <b>Pular</b> abaixo.",
            parse_mode="HTML",
            reply_markup=teclado_tiktok
        )
    except: pass
    await state.set_state(SubmissaoUsuarioInterativa.aguardando_tiktok)

# 5. PASSO FINAL: IA Processa e Posta (Edita o Painel para o Veredito)
@dp.message(SubmissaoUsuarioInterativa.aguardando_tiktok)
@dp.callback_query(F.data == "pular_tiktok", StateFilter("*"))
async def wizard_finalizar_processamento(event, state: FSMContext):
    is_callback = isinstance(event, types.CallbackQuery)
    message = event.message if is_callback else event
    
    if not is_callback:
        permitido, config = checar_permissao_topico(message)
        if not permitido: return
        try: await event.delete() # Limpa o link do tiktok
        except: pass
        
        link_tiktok = event.text
        if "tiktok" not in link_tiktok.lower():
            aviso = await message.answer("⚠️ Link inválido. Envie um link do TikTok ou clique em Pular.", parse_mode="HTML")
            await asyncio.sleep(4)
            try: await aviso.delete()
            except: pass
            return
    else:
        config = ler_submissao_config()
        link_tiktok = None

    data = await state.get_data()
    msg_wizard_id = data.get("msg_wizard_id")
    
    try:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg_wizard_id,
            text="⏳ <b>Avaliando Oferta...</b>\n\nA IA está analisando o seu vídeo para garantir que ele segue as regras da comunidade.",
            parse_mode="HTML"
        )
    except: pass
    
    await state.clear() # Libera a memória instantaneamente para novos envios

    try:
        video_id = data.get("video_file_id")
        link_shopee = data.get("link_shopee")
        
        file_info = await bot.get_file(video_id)
        video_path = f"temp/submissao_{video_id}.mp4"
        await bot.download_file(file_info.file_path, destination=video_path)
        
        prompt = (
            "Você atua como moderador de segurança de um grupo de e-commerce. Assista ao vídeo INTEIRO. "
            "REGRAS DE APROVAÇÃO: O vídeo DEVE ser a demonstração de um produto físico para venda. "
            "REGRAS DE REJEIÇÃO: NÃO PODE conter nudez, violência, memes, dancinhas, vídeos pessoais ou ser apenas texto. "
            "Sua resposta deve conter EXATAMENTE TRÊS linhas.\n"
            "Linha 1: Escreva estritamente '[APROVADO]' ou '[REJEITADO]'.\n"
            "Linha 2: Se rejeitado, dê um motivo curto. Se aprovado, escreva APENAS o nome do produto acompanhado de um emoji correspondente no final (Ex: Tênis Casual Feminino 👟).\n"
            "Linha 3: Se rejeitado, deixe em branco. Se aprovado, inclua as hashtags correspondentes aos setores do produto. IMPORTANTE: Separe-as APENAS com espaços em branco, NUNCA utilize vírgulas. "
            "REGRA ABSOLUTA DE HASHTAGS: Você SÓ PODE escolher hashtags desta lista exata, podendo combinar mais de uma se aplicável: "
            "#RoupasFemininas #SapatosFemininos #CelularesEDispositivos #AcessoriosParaVeiculos #Relogios "
            "#AlimentosEBebidas #CasaEDecoracao #SapatosMasculinos #EsportesELazer #BolsasMasculinas #BolsasFemininas "
            "#RoupasPlusSize #ModaInfantil #Eletrodomesticos #Motocicletas #AnimaisDomesticos #CamerasEDrones #Beleza "
            "#AcessoriosDeModa #BrinquedosEHobbies #Papelaria #LivrosERevistas #RoupasMasculinas #Automoveis #MaeEBebe "
            "#ComputadoresEAcessorios #Saude #ViagensEBagagens #JogosEConsoles #Audio. "
            "É estritamente proibido criar textos de vendas, descrições, inventar novas hashtags ou adicionar mensagens extras."
        )
        
        analise_ia = await analisar_video_gemini(video_path, prompt, EXIBIR_LOGS)
        os.remove(video_path)
        
        if not analise_ia:
            try: await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_wizard_id, text="❌ Falha temporária na IA. Tente submeter novamente.")
            except: pass
            return
            
        linhas = analise_ia.split('\n')
        veredicto = linhas[0].strip().upper()
        
        user_obj = event.from_user
        
        # Cria menção clicável: usa o @username ou força um link interno no nome da pessoa
        if user_obj.username:
            user_mention = f"@{user_obj.username}"
        else:
            user_mention = f"<a href='tg://user?id={user_obj.id}'>{user_obj.first_name}</a>"
        
        if "[APROVADO]" in veredicto:
            nome_produto = linhas[1].strip() if len(linhas) > 1 else "Oferta Exclusiva 🛍️"
            hashtags_ia = linhas[2].strip() if len(linhas) > 2 else ""
            
            # Montagem estruturada invertendo a ordem (Remetente primeiro, Nome depois)
            legenda_final = (
                f"👤 Dica enviada por: {user_mention}\n\n"
                f"<b>{nome_produto}</b>\n\n"
                f"🔗 <b>Link do Produto:</b>\n{link_shopee}"
            )
            
            if link_tiktok:
                legenda_final += f"\n\n🎵 <b>Link do TikTok:</b>\n{link_tiktok}"
            
            if hashtags_ia:
                legenda_final += f"\n\n<i>{hashtags_ia}</i>"
            
            # Posta na Vitrine
            await bot.send_video(
                chat_id=message.chat.id, 
                video=video_id, 
                caption=legenda_final, 
                parse_mode="HTML",
                message_thread_id=config.get("topico_destino")
            )
            
            try:
                await bot.edit_message_text(
                    chat_id=message.chat.id, 
                    message_id=msg_wizard_id, 
                    text=f"🎉 <b>Aprovado!</b> A dica de {user_mention} já está brilhando no mural!", 
                    parse_mode="HTML"
                )
            except: pass
            
        else:
            motivo = linhas[1].strip() if len(linhas) > 1 else "Conteúdo inadequado para e-commerce."
            try:
                await bot.edit_message_text(
                    chat_id=message.chat.id, 
                    message_id=msg_wizard_id, 
                    text=f"🛑 <b>Oferta Rejeitada.</b>\n👤 Usuário: {user_mention}\n<b>Motivo:</b> {motivo}", 
                    parse_mode="HTML"
                )
            except: pass
            
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro na submissão guiada: {e}")
        try: await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_wizard_id, text="❌ Ocorreu um erro interno ao processar o arquivo.")
        except: pass
        
    # Limpa a mensagem final da tela após 15 segundos para zerar a conversa
    await asyncio.sleep(15)
    try: await bot.delete_message(message.chat.id, msg_wizard_id)
    except: pass

    # ✅ Devolve o painel para o fim do tópico
    await reenviar_botao_ofertas()

# Cancelamento manual do usuário (Limpa tudo instantaneamente)
@dp.callback_query(F.data == "cancelar_wizard", StateFilter("*"))
async def wizard_cancelar(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_wizard_id = data.get("msg_wizard_id")
    await state.clear()
    
    try:
        await callback.message.edit_text("❌ Envio de oferta cancelado.")
    except: pass
    
    await asyncio.sleep(3)
    if msg_wizard_id:
        try: await bot.delete_message(callback.message.chat.id, msg_wizard_id)
        except: pass
    else:
        try: await callback.message.delete()
        except: pass

    # ✅ Devolve o painel para o fim do tópico
    await reenviar_botao_ofertas()

# ==========================================
# LIMPADOR DE TECLADO FANTASMA 🧹
# ==========================================
from aiogram.types import ReplyKeyboardRemove

@dp.message(Command("limpar_painel"))
async def limpar_teclado_fantasma(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    # O comando ReplyKeyboardRemove() força o Telegram a vaporizar os botões da tela
    aviso = await message.answer(
        "🧹 <b>Limpando lixo visual...</b>\nO painel de administração foi removido deste grupo!", 
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )
    
    # Apaga as mensagens após 4 segundos para ninguém perceber
    await asyncio.sleep(4)
    try: 
        await message.delete()
        await aviso.delete()
    except: pass

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
    
    # ✅ WATCHDOG: O Fiscal Híbrido bate a cada 1 minuto apenas para auditar a memória
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
