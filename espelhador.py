# 0. CONFIGURAÇÕES INICIAIS
EXIBIR_LOGS = True
import os
import json
import logging
import asyncio
import time
import hashlib
import aiohttp
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Router, Bot, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import StateFilter

if EXIBIR_LOGS:
    logger = logging.getLogger("Espelhador")

router = Router()
FUSO_STR = "America/Sao_Paulo"
fuso_horario = ZoneInfo(FUSO_STR)

bot_instance = None
scheduler_instance = None

def configurar_dependencias(bot: Bot, scheduler):
    global bot_instance, scheduler_instance
    bot_instance = bot
    scheduler_instance = scheduler
    if EXIBIR_LOGS: logger.info("🔌 Conexão estabelecida: Dependências do Espelhador injetadas com sucesso.")

# --- MÁQUINA DE ESTADOS E TECLADOS ---
class EspelhadorFluxo(StatesGroup):
    menu_principal = State()
    aguardando_origem = State()
    aguardando_destino = State()
    aguardando_delay = State()
    aguardando_confirmacao_criacao = State() # ✅ NOVO ESTADO
    aguardando_remocao = State()
    aguardando_confirmacao_remocao_rota = State() # ✅ NOVO ESTADO

teclado_espelhador_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Adicionar Rota ➕"), KeyboardButton(text="Remover Rota 🗑️")],
        [KeyboardButton(text="Voltar aos Canais 🔙")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

teclado_espelhador_cancelar = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Cancelar Operação ❌")]],
    resize_keyboard=True,
    is_persistent=True
)

# ✅ NOVO: Teclado de Dupla Confirmação
teclado_espelhador_confirmacao = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar ❌")]],
    resize_keyboard=True,
    is_persistent=True
)

# --- BANCO DE DADOS DO ESPELHADOR ---
def ler_espelhos():
    try:
        with open("espelhos_config.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"rotas": []}

def salvar_espelhos(dados):
    with open("espelhos_config.json", "w") as f:
        json.dump(dados, f, indent=4)

# --- VALIDAÇÃO DE ACESSO (MODO TRUST) ---
async def validar_link_ou_id_grupo(entrada):
    # Removemos a verificação bot_instance.get_chat() para evitar bloqueios de API.
    # O robô agora confia que o ID fornecido está correto.
    
    entrada_limpa = ''.join(c for c in entrada if c.isprintable()).strip()
    
    # Se for link t.me
    if "t.me/" in entrada_limpa:
        username = entrada_limpa.split("t.me/")[-1].split("/")[0]
        if not username.startswith("+"):
            return f"@{username}"
            
    # Se for ID numérico (ex: 3673555953 ou -1003673555953)
    if entrada_limpa.replace('-', '').isdigit():
        numeros = entrada_limpa.replace('-', '')
        # Normaliza o ID para o padrão -100...
        if numeros.startswith("100") and len(numeros) > 10:
            numeros = numeros[3:]
        return f"-100{numeros}"
    
    # Se for @username simples
    if entrada_limpa.startswith("@"):
        return entrada_limpa
        
    return None

# --- NAVEGAÇÃO E PAINEL ---
@router.message(F.text == "Cancelar Operação ❌", StateFilter("*"))
async def cancelar_espelhador(message: types.Message, state: FSMContext):
    await state.clear()
    await painel_espelhador(message, state)

@router.message(F.text == "Espelhador de Canais 🔄", StateFilter("*"))
async def painel_espelhador(message: types.Message, state: FSMContext):
    await state.clear()
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    
    texto = "🔄 <b>Painel do Espelhador de Canais</b>\n\n"
    texto += "Este módulo clona publicações de um grupo para outro automaticamente, convertendo os links e respeitando um atraso programado.\n\n"
    
    if rotas:
        texto += "📡 <b>Rotas Ativas:</b>\n"
        for i, rota in enumerate(rotas, 1):
            destino_rota = rota['destino']
            status_alerta = " 🔴 <i>[ROTA QUEBRADA - Sem Acesso]</i>" if rota.get("status_verificacao") == "erro" else ""
            
            # 🔍 Consulta o motor de agendamento em tempo real para contar a fila desta rota específica
            qtd_fila = 0
            if scheduler_instance:
                for job in scheduler_instance.get_jobs():
                    if job.id.startswith("espelho_") and f"_{destino_rota}_" in job.id:
                        qtd_fila += 1

            texto += f"<b>{i}. {rota['nome']}</b>{status_alerta}\n"
            texto += f"   Origem: <code>{rota['origem']}</code>\n"
            texto += f"   Destino: <code>{destino_rota}</code>\n"
            texto += f"   Atraso: ⏳ {rota['delay']} minutos\n"
            texto += f"   Fila: 📦 {qtd_fila} vídeos aguardando\n\n"
    else:
        texto += "<i>Nenhuma rota de espelhamento cadastrada no momento.</i>\n\n"
        
    await message.answer(texto, reply_markup=teclado_espelhador_menu, parse_mode="HTML")
    await state.set_state(EspelhadorFluxo.menu_principal)

@router.message(EspelhadorFluxo.menu_principal, F.text == "Adicionar Rota ➕")
async def iniciar_cadastro_rota(message: types.Message, state: FSMContext):
    if EXIBIR_LOGS: logger.info("🚀 Iniciando fluxo de cadastro de novas rotas em lote...")
    await message.answer("Envie os IDs numéricos, links ou @usernames dos <b>Canais de ORIGEM</b> (De onde o robô vai copiar).\nVocê pode enviar vários de uma vez separando por vírgula ou quebrando a linha:", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
    await state.set_state(EspelhadorFluxo.aguardando_origem)

@router.message(EspelhadorFluxo.aguardando_origem)
async def receber_origem(message: types.Message, state: FSMContext):
    msg_status = await message.answer("⏳ Validando lote de canais de origem...", reply_markup=teclado_espelhador_cancelar)
    
    entradas_brutas = message.text.replace('\n', ',').split(',')
    origens_validas = []
    origens_invalidas = []
    
    if EXIBIR_LOGS: logger.info(f"🚀 Iniciando processamento em lote para {len(entradas_brutas)} possíveis origens...")

    for entrada in entradas_brutas:
        entrada = entrada.strip()
        if not entrada:
            continue
            
        origem_id = await validar_link_ou_id_grupo(entrada)
        if origem_id:
            if origem_id not in origens_validas:
                origens_validas.append(origem_id)
                if EXIBIR_LOGS: logger.info(f"✅ Canal de origem validado e adicionado ao lote: {origem_id}")
        else:
            origens_invalidas.append(entrada)
            if EXIBIR_LOGS: logger.warning(f"⚠️ Falha na validação do canal de origem: {entrada}")

    await msg_status.delete()
    
    if origens_validas:
        await state.update_data(origens=origens_validas)
        
        texto_resposta = f"✅ <b>{len(origens_validas)} Origem(ns) confirmada(s):</b>\n"
        for o in origens_validas:
            texto_resposta += f"<code>{o}</code>\n"
            
        if origens_invalidas:
            texto_resposta += f"\n⚠️ <i>{len(origens_invalidas)} entrada(s) ignorada(s) por formato inválido.</i>\n"
            
        texto_resposta += "\nExcelente. Agora envie o ID numérico ou @username do <b>Canal de DESTINO</b> (Para onde o robô vai enviar as cópias):"
        await message.answer(texto_resposta, reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_destino)
    else:
        if EXIBIR_LOGS: logger.warning("❌ Nenhuma origem válida encontrada no lote.")
        await message.answer("⚠️ <b>Nenhum canal válido encontrado!</b>\nCertifique-se de que os IDs ou @usernames estão corretos.\n\nTente enviar novamente:", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")

@router.message(EspelhadorFluxo.aguardando_destino)
async def receber_destino(message: types.Message, state: FSMContext):
    msg_status = await message.answer("⏳ Validando permissões e acesso ao canal de destino...", reply_markup=teclado_espelhador_cancelar)
    destino_id = await validar_link_ou_id_grupo(message.text)
    await msg_status.delete()
    
    if destino_id:
        if EXIBIR_LOGS: logger.info(f"✅ Destino validado com sucesso: {destino_id}")
        await state.update_data(destino=destino_id)
        await message.answer(f"✅ Destino confirmado: <code>{destino_id}</code>\n\nPor fim, digite o <b>Atraso de Publicação em Minutos</b> (Apenas números, ex: 15):\nDigite 0 se quiser que a cópia seja imediata.", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_delay)
    else:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Falha na validação do destino: {message.text}")
        await message.answer("⚠️ <b>Canal não encontrado ou sem permissão!</b>\nCertifique-se de que o ID ou @username está correto e de que o bot é administrador do canal.\n\nTente enviar novamente:", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")

@router.message(EspelhadorFluxo.aguardando_delay)
async def receber_delay_rota(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas números inteiros para os minutos.", reply_markup=teclado_espelhador_cancelar)
        return
        
    delay = int(message.text)
    await state.update_data(delay=delay)
    
    data = await state.get_data()
    origens = data.get("origens", [])
    destino = data.get("destino")
    
    texto_confirmacao = (
        f"⚠️ <b>Confirmação de Criação em Lote ({len(origens)} rotas)</b>\n\n"
        f"<b>Origens Mapeadas:</b>\n"
    )
    for o in origens:
        texto_confirmacao += f"└ <code>{o}</code>\n"
        
    texto_confirmacao += (
        f"\n<b>Destino Único:</b> <code>{destino}</code>\n"
        f"<b>Atraso Aplicado:</b> ⏳ {delay} minutos\n\n"
        "Deseja aprovar e ativar estes espelhamentos agora?"
    )
    
    if EXIBIR_LOGS: logger.info(f"✅ Lote preparado para confirmação: {len(origens)} rotas apontando para {destino}.")
    await message.answer(texto_confirmacao, reply_markup=teclado_espelhador_confirmacao, parse_mode="HTML")
    await state.set_state(EspelhadorFluxo.aguardando_confirmacao_criacao)

@router.message(EspelhadorFluxo.aguardando_confirmacao_criacao)
async def finalizar_cadastro_rota(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, utilize os botões para Aprovar ✅ ou Cancelar ❌ a criação.")
        return

    data = await state.get_data()
    origens = data.get("origens", [])
    destino = data.get("destino")
    delay = data.get("delay")
    
    dados = ler_espelhos()
    
    if EXIBIR_LOGS: logger.info(f"🚀 Iniciando gravação no banco de dados para {len(origens)} novas rotas...")
    
    for origem in origens:
        num_rota = len(dados.get("rotas", [])) + 1
        nome_rota = f"Espelho {num_rota}"
        
        nova_rota = {
            "nome": nome_rota,
            "origem": origem,
            "destino": destino,
            "delay": delay
        }
        
        dados.setdefault("rotas", []).append(nova_rota)
        if EXIBIR_LOGS: logger.info(f"✅ Rota anexada: {nome_rota} (Origem {origem} > Destino {destino} | Atraso: {delay}min).")
        
    salvar_espelhos(dados)
    
    if EXIBIR_LOGS: logger.info("✅ Operação em lote concluída e persistida com sucesso.")
    
    await message.answer(f"✅ <b>{len(origens)} novas rotas</b> criadas e ativadas com sucesso!", parse_mode="HTML")
    await painel_espelhador(message, state)

@router.message(EspelhadorFluxo.menu_principal, F.text == "Remover Rota 🗑️")
async def iniciar_remocao_rota(message: types.Message, state: FSMContext):
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    
    if not rotas:
        await message.answer("Não há rotas ativas para remover.", reply_markup=teclado_espelhador_menu)
        return
        
    texto = "Digite o <b>NÚMERO</b> da rota que deseja remover:\n\n"
    for i, rota in enumerate(rotas, 1):
        texto += f"{i}. {rota['nome']} (Origem: {rota['origem']})\n"
        
    await message.answer(texto, reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
    await state.set_state(EspelhadorFluxo.aguardando_remocao)

@router.message(EspelhadorFluxo.aguardando_remocao)
async def pedir_confirmacao_remocao(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas o número da rota.", reply_markup=teclado_espelhador_cancelar)
        return
        
    indice = int(message.text) - 1
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    
    if 0 <= indice < len(rotas):
        rota_alvo = rotas[indice]
        await state.update_data(indice_remocao=indice)
        
        texto_confirmacao = (
            f"⚠️ Tem a certeza de que deseja remover permanentemente a rota <b>{rota_alvo['nome']}</b>?\n\n"
            f"<b>Origem:</b> <code>{rota_alvo['origem']}</code>\n"
            f"<b>Destino:</b> <code>{rota_alvo['destino']}</code>"
        )
        
        await message.answer(texto_confirmacao, reply_markup=teclado_espelhador_confirmacao, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_confirmacao_remocao_rota)
    else:
        await message.answer("Número inválido. Tente novamente ou clique em Cancelar ❌.", reply_markup=teclado_espelhador_cancelar)

@router.message(EspelhadorFluxo.aguardando_confirmacao_remocao_rota)
async def processar_remocao_rota(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, utilize os botões para Aprovar ✅ ou Cancelar ❌ a exclusão.")
        return

    data = await state.get_data()
    indice = data.get("indice_remocao")
    
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    
    if indice is not None and 0 <= indice < len(rotas):
        rota_removida = rotas.pop(indice)
        dados["rotas"] = rotas
        salvar_espelhos(dados)
        
        if EXIBIR_LOGS: logger.info(f"🗑️ Rota '{rota_removida['nome']}' removida permanentemente.")
        await message.answer(f"A rota <b>{rota_removida['nome']}</b> foi apagada e os espelhamentos foram interrompidos.", parse_mode="HTML")
        await painel_espelhador(message, state)
    else:
        await message.answer("Erro de sincronização. Operação cancelada.")
        await painel_espelhador(message, state)
