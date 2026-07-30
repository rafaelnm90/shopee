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
from utils import registrar_erro_json, ler_cache_nomes_grupos, salvar_nome_grupo, validar_e_formatar_alvo
from motor_filas import calcular_horarios_distribuicao # ⚙️ Novo Motor Centralizado
EXIBIR_LOGS = True

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
    aguardando_destino_criacao = State() # ✅ NOVO: Passo 1 da criação
    aguardando_origem_criacao = State()  # ✅ NOVO: Passo 2 da criação
    aguardando_janela = State()
    aguardando_intervalo_dias = State()
    aguardando_modo = State()
    aguardando_confirmacao_criacao = State()
    aguardando_remocao = State()
    aguardando_confirmacao_remocao_rota = State()
    aguardando_edicao_escolha_rota = State()
    aguardando_acao_edicao = State()
    aguardando_edicao_novo_nome = State()
    aguardando_edicao_novo_destino = State() # ✅ NOVO ESTADO ADICIONADO AQUI
    aguardando_edicao_nova_janela = State()
    aguardando_edicao_intervalo_dias = State() # ✅ ESTADO QUE HAVIA SUMIDO
    aguardando_edicao_novo_modo = State()
    aguardando_acao_origem = State() # ✅ ESTADO ADICIONADO PARA O SUBMENU
    aguardando_nova_origem = State()
    aguardando_confirmacao_nova_origem = State()
    aguardando_remocao_origem = State()
    aguardando_confirmacao_remocao_origem = State()
    aguardando_rota_esvaziar = State()
    aguardando_confirmacao_esvaziar = State()

teclado_espelhador_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Adicionar Espelho ➕"), KeyboardButton(text="Remover Espelho 🗑️")],
        [KeyboardButton(text="Editar Espelho ✏️")],
        [KeyboardButton(text="Forçar Postagens 🚀")],
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

# ✅ NOVO: Teclado para Definição da Janela de Horário da Rota
teclado_espelhador_janela = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Dia Todo (24h) 🕛")],
        [KeyboardButton(text="Cancelar Operação ❌")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

# ✅ NOVO: Teclado de Dupla Confirmação
teclado_espelhador_confirmacao = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar Operação ❌")]],
    resize_keyboard=True,
    is_persistent=True
)

# ✅ NOVO: Teclado Inteligente para Injeção Múltipla de Origens
teclado_espelhador_abrangencia = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Apenas nesta Rota 🎯")],
        [KeyboardButton(text="Em TODAS as Rotas 🌍")],
        [KeyboardButton(text="Cancelar Operação ❌")]
    ],
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

def ler_contador_espelhador(nome_rota):
    try:
        with open("fila_espelhador.json", "r") as f:
            dados = json.load(f)
            return len([item for item in dados.get("fila", []) if item.get("nome_rota") == nome_rota])
    except (FileNotFoundError, json.JSONDecodeError):
        return 0

def salvar_espelhos(dados):
    with open("espelhos_config.json", "w") as f:
        json.dump(dados, f, indent=4)

# --- NAVEGAÇÃO E PAINEL ---
@router.message(F.text == "Cancelar Operação ❌", StateFilter("*"))
async def cancelar_espelhador(message: types.Message, state: FSMContext):
    estado_atual = await state.get_state()
    data = await state.get_data()
    
    # --- NÍVEL 3: Submenu de Origens (Volta para os botões Adicionar/Remover Origem) ---
    estados_origem = [
        "EspelhadorFluxo:aguardando_nova_origem",
        "EspelhadorFluxo:aguardando_confirmacao_nova_origem",
        "EspelhadorFluxo:aguardando_remocao_origem",
        "EspelhadorFluxo:aguardando_confirmacao_remocao_origem"
    ]
    
    if estado_atual in estados_origem:
        if EXIBIR_LOGS: logger.info("🔙 Cancelamento: Voltando ao submenu de Origens.")
        teclado_origens = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="➕ Adicionar Canal"), KeyboardButton(text="🗑️ Remover Canal")],
                [KeyboardButton(text="🔙 Voltar ao Menu de Edição")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        await message.answer("Ação cancelada. O que você deseja fazer com os canais vigiados desta rota?", reply_markup=teclado_origens)
        await state.set_state(EspelhadorFluxo.aguardando_acao_origem)
        return

    # --- NÍVEL 2: Submenu de Edição da Rota (Volta para os 8 botões de configuração) ---
    estados_edicao = [
        "EspelhadorFluxo:aguardando_acao_origem", # Cancelando de dentro do menu de origens
        "EspelhadorFluxo:aguardando_edicao_novo_nome",
        "EspelhadorFluxo:aguardando_edicao_novo_destino",
        "EspelhadorFluxo:aguardando_edicao_nova_janela",
        "EspelhadorFluxo:aguardando_edicao_intervalo_dias",
        "EspelhadorFluxo:aguardando_edicao_novo_modo"
    ]
    
    if estado_atual in estados_edicao and data.get("indice_edicao") is not None:
        if EXIBIR_LOGS: logger.info("🔙 Cancelamento: Voltando ao menu de Edição da Rota.")
        await message.answer("Ação cancelada. Retornando às configurações da rota...")
        novo_texto = str(data["indice_edicao"] + 1)
        msg_simulada = message.model_copy(update={"text": novo_texto})
        await selecionar_acao_edicao(msg_simulada, state)
        return

    # --- NÍVEL 1: Cancelamento Raiz (Volta para o Painel Principal do Espelhador) ---
    if EXIBIR_LOGS: logger.info("🔙 Cancelamento Global: Voltando ao Painel Principal do Espelhador.")
    await state.clear()
    await message.answer("Operação cancelada.", reply_markup=teclado_espelhador_menu)
    await painel_espelhador(message, state)

@router.message(F.text == "Espelhador de Canais 🔄", StateFilter("*"))
async def painel_espelhador(message: types.Message, state: FSMContext):
    await state.clear()
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    cache_nomes = ler_cache_nomes_grupos()  # 🚀 Fallback para quando o status_canais ainda não foi auditado
    
    texto = "🔄 <b>Painel do Espelhador de Canais</b>\n\n"
    texto += "Este módulo clona publicações de um grupo para outro automaticamente, convertendo os links e respeitando um atraso programado.\n\n"
    
    if rotas:
        texto += "📡 <b>Rotas Ativas:</b>\n"
        for i, rota in enumerate(rotas, 1):
            destino_rota = rota['destino']
            qtd_fila = ler_contador_espelhador(rota['nome'])
            status_canais = rota.get("status_canais", {})
            
            texto += f"<b>{i}. {rota['nome']}</b>\n"
            texto += f"   🕒 Janela de Postagem: {rota.get('inicio', 10)}h às {rota.get('fim', 22)}h\n"
            texto += f"   🔀 Distribuição: {rota.get('modo', 'ordem').title()}\n"
            texto += f"   📦 Fila de Espera: {qtd_fila} vídeo(s)\n"
            texto += "\n"
            # --- 1. ORIGENS MOSTRADAS PRIMEIRO ---
            origens = rota.get('origens', [])
            if not origens and 'origem' in rota:
                origens = [rota['origem']]
                
            texto += f"📥 <b>Na escuta:</b>\n"
                
            for idx, o in enumerate(origens):
                info_o = status_canais.get(str(o), {})
                if isinstance(info_o, str): info_o = {"status": info_o, "nome": str(o)}
                
                status_ico = "❌" if info_o.get("status") == "erro" else "✅"
                nome_o = info_o.get("nome") or cache_nomes.get(str(o), str(o))
                display_o = f"{nome_o} (<code>{o}</code>)" if nome_o != str(o) else f"<code>{o}</code>"
                # ✅ Alinhamento perfeito com 01, 02
                texto += f"<code>{idx + 1:02d}.</code> {status_ico} {display_o}\n"

            # --- 2. DESTINO MOSTRADO LOGO ABAIXO ---
            info_d = status_canais.get(str(destino_rota), {})
            if isinstance(info_d, str): info_d = {"status": info_d, "nome": str(destino_rota)}
            
            status_destino_ico = "❌" if info_d.get("status") == "erro" else "✅"
            nome_d = info_d.get("nome") or cache_nomes.get(str(destino_rota), str(destino_rota))
            display_d = f"{nome_d} (<code>{destino_rota}</code>)" if nome_d != str(destino_rota) else f"<code>{destino_rota}</code>"
            
            texto += f"\n🎯 <b>Canal de Destino:</b> {status_destino_ico} {display_d}\n\n"
    else:
        texto += "<i>Nenhuma rota de espelhamento cadastrada no momento.</i>\n\n"
        
    await message.answer(texto, reply_markup=teclado_espelhador_menu, parse_mode="HTML")
    await state.set_state(EspelhadorFluxo.menu_principal)

@router.message(EspelhadorFluxo.menu_principal, F.text == "Adicionar Espelho ➕")
async def iniciar_cadastro_rota(message: types.Message, state: FSMContext):
    if EXIBIR_LOGS: logger.info("🚀 Iniciando fluxo de cadastro de espelho (Passo 1: Destino)...")
    await message.answer("Para começar, envie o ID numérico ou @username do <b>Canal de DESTINO</b> (Para onde o robô vai enviar as cópias):", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
    await state.set_state(EspelhadorFluxo.aguardando_destino_criacao)

@router.message(EspelhadorFluxo.aguardando_destino_criacao)
async def receber_destino_criacao(message: types.Message, state: FSMContext):
    msg_status = await message.answer("⏳ Validando permissões e acesso ao canal de destino...", reply_markup=teclado_espelhador_cancelar)
    sucesso, destino_id, nome = await validar_e_formatar_alvo(bot_instance, message.text)
    await msg_status.delete()
    
    if sucesso:
        salvar_nome_grupo(destino_id, nome)
        if EXIBIR_LOGS: logger.info(f"✅ Destino validado com sucesso: {destino_id}")
        await state.update_data(destino=destino_id, nome_destino=nome) # Salva o nome para usar lá no Passo 3
        
        texto_origens = (
            f"✅ Destino confirmado: <code>{destino_id}</code>\n\n"
            "Agora, envie os @usernames, links ou IDs dos grupos/canais que deseja <b>MONITORAR</b> (Na Escuta).\n"
            "Você pode enviar vários separando por vírgula (Ex: <code>@grupo1, -100123, https://t.me/grupo2</code>):"
        )
        await message.answer(texto_origens, reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_origem_criacao)
    else:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Falha na validação do destino: {message.text}")
        await message.answer("⚠️ <b>Canal não encontrado ou sem permissão!</b>\nCertifique-se de que o ID ou @username está correto e de que o bot é administrador do canal.\n\nTente enviar novamente:", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")

@router.message(EspelhadorFluxo.aguardando_origem_criacao)
async def receber_origem_criacao(message: types.Message, state: FSMContext):
    msg_status = await message.answer("⏳ Validando lote de canais de origem e subgrupos...", reply_markup=teclado_espelhador_cancelar)
    entradas_brutas = message.text.replace('\n', ',').split(',')
    origens_validas = []
    origens_invalidas = []
    
    for entrada in entradas_brutas:
        if not entrada.strip(): continue
        sucesso, id_final, nome = await validar_e_formatar_alvo(bot_instance, entrada)
        if sucesso:
            if id_final not in origens_validas:
                origens_validas.append(id_final)
                salvar_nome_grupo(id_final, nome)
        else:
            origens_invalidas.append(entrada)

    await msg_status.delete()
    
    if origens_validas:
        await state.update_data(origens=origens_validas)
        
        texto_resposta = f"✅ <b>{len(origens_validas)} Origem(ns) confirmada(s):</b>\n"
        for o in origens_validas:
            texto_resposta += f"<code>{o}</code>\n"
            
        if origens_invalidas:
            texto_resposta += f"\n⚠️ <i>{len(origens_invalidas)} entrada(s) ignorada(s) por formato inválido.</i>\n"
            
        texto_resposta += "\nExcelente. Agora defina a <b>Janela de Horário</b> para a postagem.\nEnvie no formato <code>Inicio-Fim</code> (Exemplo: <code>10-22</code>) ou clique no botão abaixo para rodar 24h:"
        await message.answer(texto_resposta, reply_markup=teclado_espelhador_janela, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_janela)
    else:
        if EXIBIR_LOGS: logger.warning("❌ Nenhuma origem válida encontrada no lote.")
        await message.answer("⚠️ <b>Nenhum canal válido encontrado!</b>\nCertifique-se de que os IDs ou @usernames estão corretos.\n\nTente enviar novamente:", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")

@router.message(EspelhadorFluxo.aguardando_janela)
async def receber_janela_rota(message: types.Message, state: FSMContext):
    import re
    texto = message.text.strip()
    
    if texto == "Dia Todo (24h) 🕛" or texto.lower() == "dia todo":
        inicio = 0
        fim = 24
        if EXIBIR_LOGS: logger.info("🕛 Janela configurada para Dia Todo (24h).")
    else:
        match = re.match(r"^(\d{1,2})-(\d{1,2})$", texto)
        if not match:
            await message.answer("Formato inválido! Use o formato exato como no exemplo: 10-22, ou clique em 'Dia Todo (24h) 🕛'.", reply_markup=teclado_espelhador_janela)
            return
            
        inicio, fim = map(int, match.groups())
        if inicio >= fim or inicio < 0 or fim > 24:
            await message.answer("Valores inválidos! A hora de início deve ser menor que a do fim.", reply_markup=teclado_espelhador_janela)
            return

    await state.update_data(inicio=inicio, fim=fim)
    if EXIBIR_LOGS: logger.info(f"✅ Janela da rota configurada com sucesso: {inicio}h as {fim}h.")
    
    teclado_dias = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Mesmo Dia (D+0) 🟢")],
            [KeyboardButton(text="Dia Seguinte (D+1) 🟡")],
            [KeyboardButton(text="Dois Dias (D+2) 🔵")],
            [KeyboardButton(text="Cancelar Operação ❌")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer("Excelente! Agora escolha o intervalo de dias de maturação para a postagem (D+0 significa publicar no próprio dia em que o vídeo foi capturado):", reply_markup=teclado_dias)
    await state.set_state(EspelhadorFluxo.aguardando_intervalo_dias)

@router.message(EspelhadorFluxo.aguardando_intervalo_dias)
async def receber_intervalo_dias_rota(message: types.Message, state: FSMContext):
    mapa_dias = {"Mesmo Dia (D+0) 🟢": 0, "Dia Seguinte (D+1) 🟡": 1, "Dois Dias (D+2) 🔵": 2}
    
    if message.text not in mapa_dias:
        await message.answer("Por favor, utilize os botões em ecrã para escolher o intervalo de dias.", reply_markup=teclado_espelhador_cancelar)
        return
        
    intervalo = mapa_dias[message.text]
    await state.update_data(intervalo_dias=intervalo)
    
    teclado_modo = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Aleatório 🔀"), KeyboardButton(text="Ordem de Chegada ⬇️")],
            [KeyboardButton(text="Cancelar Operação ❌")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer("Como deseja distribuir os vídeos retidos dentro dessa janela de horário?", reply_markup=teclado_modo)
    await state.set_state(EspelhadorFluxo.aguardando_modo)

# BLOCO ESPECIFICAMENTE MODIFICADO (Apague tudo o que estiver quebrado e cole isto)
@router.message(EspelhadorFluxo.aguardando_modo)
async def receber_modo_rota(message: types.Message, state: FSMContext):
    if message.text not in ["Aleatório 🔀", "Ordem de Chegada ⬇️"]:
        await message.answer("Por favor, use os botões para escolher o modo.", reply_markup=teclado_espelhador_cancelar)
        return
        
    modo = "aleatorio" if message.text == "Aleatório 🔀" else "ordem"
    await state.update_data(modo=modo)
    
    data = await state.get_data()
    origens = data.get("origens", [])
    destino = data.get("destino")
    inicio = data.get("inicio")
    fim = data.get("fim")
    
    intervalo_dias = data.get("intervalo_dias", 1)
    
    texto_confirmacao = (
        f"⚠️ <b>Confirmação de Criação de Rota (D+{intervalo_dias})</b>\n\n"
        f"<b>Canais Vigiados ({len(origens)}):</b>\n"
    )
    for o in origens:
        texto_confirmacao += f"└ <code>{o}</code>\n"
        
    texto_confirmacao += (
        f"\n<b>Destino:</b> <code>{destino}</code>\n"
        f"<b>Distribuição:</b> {inicio}h às {fim}h\n"
        f"<b>Ordem:</b> {message.text}\n\n"
        "Deseja aprovar e ativar este espelhamento inteligente agora?"
    )
    
    if EXIBIR_LOGS: logger.info(f"✅ Rota preparada para confirmação: {len(origens)} origens para {destino}.")
    await message.answer(texto_confirmacao, reply_markup=teclado_espelhador_confirmacao, parse_mode="HTML")
    await state.set_state(EspelhadorFluxo.aguardando_confirmacao_criacao)

@router.message(EspelhadorFluxo.aguardando_confirmacao_criacao)
async def finalizar_cadastro_rota(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, utilize os botões para Aprovar ✅ ou Cancelar Operação ❌ a criação.")
        return

    data = await state.get_data()
    origens = data.get("origens", [])
    destino = data.get("destino")
    nome_destino = data.get("nome_destino", destino) # ✅ Pega o nome do destino salvo no Passo 1
    inicio = data.get("inicio")
    fim = data.get("fim")
    intervalo_dias = data.get("intervalo_dias", 1)
    modo = data.get("modo")
    
    dados = ler_espelhos()
    
    # ✅ NOVO: Nomeação Inteligente Baseada no Destino (Como pediu no vídeo)
    nome_base = f"Espelho: {nome_destino}"
    nome_rota = nome_base
    contador = 1
    
    rotas_existentes = dados.get("rotas", [])
    while any(r.get("nome") == nome_rota for r in rotas_existentes):
        contador += 1
        nome_rota = f"{nome_base} ({contador})"
        
    if EXIBIR_LOGS: logger.info(f"🏷️ Rota nomeada automaticamente como: {nome_rota}")

    nova_rota = {
        "nome": nome_rota,
        "origens": origens,
        "destino": destino,
        "inicio": inicio,
        "fim": fim,
        "intervalo_dias": intervalo_dias,
        "modo": modo
    }
    
    dados.setdefault("rotas", []).append(nova_rota)
    salvar_espelhos(dados)
    
    if EXIBIR_LOGS: logger.info(f"✅ Rota inteligente criada com sucesso: {nome_rota}.")
    
    dia_texto = "no próprio dia (D+0)" if intervalo_dias == 0 else f"com {intervalo_dias} dia(s) de atraso"
    await message.answer(f"✅ <b>Rota {nome_rota}</b> ativada!\nOs vídeos capturados serão postados {dia_texto} entre as {inicio}h e as {fim}h.", parse_mode="HTML")
    await painel_espelhador(message, state)

@router.message(EspelhadorFluxo.menu_principal, F.text == "Remover Espelho 🗑️")
async def iniciar_remocao_rota(message: types.Message, state: FSMContext):
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    
    if not rotas:
        await message.answer("Não há rotas ativas para remover.", reply_markup=teclado_espelhador_menu)
        return

    # ✅ NOVO: Atalho Inteligente! Se houver apenas 1 rota, pula a pergunta e vai direto para a confirmação de remoção.
    if len(rotas) == 1:
        if EXIBIR_LOGS: logger.info("⏭️ Atalho UX acionado: Apenas 1 rota disponível. Pulando tela de seleção para remoção.")
        msg_simulada = message.model_copy(update={"text": "1"})
        if EXIBIR_LOGS: logger.info("🔄 Criada mensagem simulada para desvio seguro (Pydantic).")
        await pedir_confirmacao_remocao(msg_simulada, state)
        return
        
    texto = "Digite o <b>NÚMERO</b> da rota que deseja remover:\n\n"
    for i, rota in enumerate(rotas, 1):
        qtd_origens = len(rota.get('origens', [rota.get('origem')]))
        texto += f"{i}. {rota['nome']} ({qtd_origens} canais vigiados agrupados)\n"
        
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
        
        origens = rota_alvo.get('origens', [])
        if not origens and 'origem' in rota_alvo:
            origens = [rota_alvo['origem']]
        
        texto_confirmacao = (
            f"⚠️ Tem a certeza de que deseja remover permanentemente a rota agrupada <b>{rota_alvo['nome']}</b>?\n\n"
            f"<b>Canais de Origem que serão desconectados:</b> {len(origens)}\n"
            f"<b>Destino:</b> <code>{rota_alvo['destino']}</code>"
        )
        
        await message.answer(texto_confirmacao, reply_markup=teclado_espelhador_confirmacao, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_confirmacao_remocao_rota)
    else:
        await message.answer("Número inválido. Tente novamente ou clique em Cancelar ❌.", reply_markup=teclado_espelhador_cancelar)

@router.message(EspelhadorFluxo.aguardando_confirmacao_remocao_rota)
async def processar_remocao_rota(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, utilize os botões para Aprovar ✅ ou Cancelar Operação ❌ a exclusão.")
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

@router.message(EspelhadorFluxo.menu_principal, F.text == "Editar Espelho ✏️")
async def iniciar_edicao_rota(message: types.Message, state: FSMContext):
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    
    if not rotas:
        await message.answer("Não há rotas ativas para editar.", reply_markup=teclado_espelhador_menu)
        return
        
    # ✅ NOVO: Atalho Inteligente! Se houver apenas 1 rota, pula a pergunta e vai direto para a edição.
    if len(rotas) == 1:
        if EXIBIR_LOGS: logger.info("⏭️ Atalho UX acionado: Apenas 1 rota disponível. Pulando tela de seleção.")
        msg_simulada = message.model_copy(update={"text": "1"})
        if EXIBIR_LOGS: logger.info("🔄 Criada mensagem simulada para desvio seguro (Pydantic).")
        await selecionar_acao_edicao(msg_simulada, state)
        return
        
    texto = "Digite o <b>NÚMERO</b> da rota que deseja configurar:\n\n"
    for i, rota in enumerate(rotas, 1):
        texto += f"{i}. {rota['nome']}\n"
        
    await message.answer(texto, reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
    await state.set_state(EspelhadorFluxo.aguardando_edicao_escolha_rota)

@router.message(EspelhadorFluxo.aguardando_edicao_escolha_rota)
async def selecionar_acao_edicao(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas o número da rota.", reply_markup=teclado_espelhador_cancelar)
        return
        
    indice = int(message.text) - 1
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    
    if 0 <= indice < len(rotas):
        rota_alvo = rotas[indice]
        await state.update_data(indice_edicao=indice)
        
        texto = f"⚙️ <b>Editando Rota: {rota_alvo['nome']}</b>\n"
        texto += f"🕒 Janela atual: {rota_alvo.get('inicio', 10)}h às {rota_alvo.get('fim', 22)}h\n"
        
        intervalo_atual = rota_alvo.get('intervalo_dias', 1)
        texto += f"📅 Intervalo de Dias: D+{intervalo_atual}\n"
        texto += f"🔀 Modo atual: {rota_alvo.get('modo', 'ordem').title()}\n"
        
        from utils import ler_cache_nomes_grupos
        cache_nomes = ler_cache_nomes_grupos()
        status_canais = rota_alvo.get("status_canais", {})

        # --- 1. ORIGENS MOSTRADAS PRIMEIRO NO MODO DE EDIÇÃO ---
        origens = rota_alvo.get('origens', [])
        if not origens and 'origem' in rota_alvo:
            origens = [rota_alvo['origem']]
            
        texto += f"📥 <b>Na escuta ({len(origens)}):</b>\n"
        
        for idx, o in enumerate(origens):
            info_o = status_canais.get(str(o), {})
            if isinstance(info_o, str): info_o = {"status": info_o, "nome": str(o)}
            
            status_ico = "❌" if info_o.get("status") == "erro" else "✅"
            nome_o = info_o.get("nome") or cache_nomes.get(str(o), str(o))
            display_o = f"{nome_o} (<code>{o}</code>)" if nome_o != str(o) else f"<code>{o}</code>"
            # ✅ Alinhamento perfeito com 01, 02
            texto += f"<code>{idx + 1:02d}.</code> {status_ico} {display_o}\n"

        # --- 2. DESTINO MOSTRADO LOGO ABAIXO ---
        destino_rota = rota_alvo.get('destino')
        info_d = status_canais.get(str(destino_rota), {})
        if isinstance(info_d, str): info_d = {"status": info_d, "nome": str(destino_rota)}
        
        status_destino_ico = "❌" if info_d.get("status") == "erro" else "✅"
        nome_d = info_d.get("nome") or cache_nomes.get(str(destino_rota), str(destino_rota))
        display_d = f"{nome_d} (<code>{destino_rota}</code>)" if nome_d != str(destino_rota) else f"<code>{destino_rota}</code>"
        
        texto += f"\n🎯 <b>Canal de Destino:</b> {status_destino_ico} {display_d}\n\n"
        
        texto += "Escolha a ação que deseja realizar:"
        
        # ✅ BUG CORRIGIDO AQUI: Trocado "Editar Origens" por "Canais Vigiados"
        teclado_submenu = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📝 Editar Nome"), KeyboardButton(text="🎯 Editar Destino")],
                [KeyboardButton(text="🕒 Modificar Janela"), KeyboardButton(text="📅 Modificar Dias")],
                [KeyboardButton(text="🔀 Modificar Modo"), KeyboardButton(text="📥 Canais Vigiados")],
                [KeyboardButton(text="Cancelar Operação ❌")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
            
        await message.answer(texto, reply_markup=teclado_submenu, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_acao_edicao)
    else:
        await message.answer("Número inválido. Tente novamente ou clique em Cancelar.", reply_markup=teclado_espelhador_cancelar)

@router.message(EspelhadorFluxo.aguardando_acao_edicao)
async def processar_acao_edicao(message: types.Message, state: FSMContext):
    texto = message.text
    if texto == "📝 Editar Nome":
        await message.answer("Digite o <b>NOVO NOME</b> para esta rota (Ex: Espelho Principal):", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_edicao_novo_nome)
    elif texto == "🎯 Editar Destino":
        await message.answer("Envie o ID numérico, link ou @username do <b>NOVO CANAL DE DESTINO</b> para esta rota:", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_edicao_novo_destino)
    elif texto == "📅 Modificar Dias":
        teclado_dias = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Mesmo Dia (D+0) 🟢")],
                [KeyboardButton(text="Dia Seguinte (D+1) 🟡")],
                [KeyboardButton(text="Dois Dias (D+2) 🔵")],
                [KeyboardButton(text="Cancelar Operação ❌")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        await message.answer("Escolha o novo intervalo temporal de atraso para o espelhamento:", reply_markup=teclado_dias)
        await state.set_state(EspelhadorFluxo.aguardando_edicao_intervalo_dias)
    elif texto == "🔀 Modificar Modo":
        teclado_modo = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Aleatório 🔀"), KeyboardButton(text="Ordem de Chegada ⬇️")],
                [KeyboardButton(text="Cancelar Operação ❌")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        await message.answer("Escolha o novo modo de distribuição:", reply_markup=teclado_modo)
        await state.set_state(EspelhadorFluxo.aguardando_edicao_novo_modo)
    elif texto == "📥 Canais Vigiados":
        # ✅ BUG CORRIGIDO AQUI: Botões atualizados para "Canal" para bater com o processar_acao_origem
        teclado_origens = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="➕ Adicionar Canal"), KeyboardButton(text="🗑️ Remover Canal")],
                [KeyboardButton(text="🔙 Voltar ao Menu de Edição")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        await message.answer("O que você deseja fazer com os canais monitorados desta rota?", reply_markup=teclado_origens)
        await state.set_state(EspelhadorFluxo.aguardando_acao_origem)
    else:
        await message.answer("Use os botões do menu para escolher a ação.", reply_markup=teclado_espelhador_cancelar)

# ✅ NOVA FUNÇÃO PARA PROCESSAR O SUBMENU
@router.message(EspelhadorFluxo.aguardando_acao_origem)
async def processar_acao_origem(message: types.Message, state: FSMContext):
    texto = message.text
    if texto == "➕ Adicionar Canal":
        await message.answer("Envie os @usernames, links ou IDs dos grupos/canais adicionais que deseja <b>MONITORAR</b>.\nVocê pode enviar vários separando por vírgula (Ex: <code>@grupo1, -100123, https://t.me/grupo2</code>):", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_nova_origem)
    elif texto == "🗑️ Remover Canal":
        data = await state.get_data()
        indice = data.get("indice_edicao")
        rotas = ler_espelhos().get("rotas", [])
        rota = rotas[indice]
        origens = rota.get('origens', [])
        if not origens and 'origem' in rota: origens = [rota['origem']]
        
        if not origens:
            await message.answer("Esta rota não possui canais vigiados para remover.")
            return
            
        msg_txt = "Qual canal deseja parar de vigiar? Digite o <b>NÚMERO</b> correspondente.\n<i>(Para remover vários de uma vez, separe por vírgula. Ex: 1, 3, 4)</i>\n\n"
        for i, orig in enumerate(origens, 1):
            msg_txt += f"<b>{i}.</b> <code>{orig}</code>\n"
            
        await message.answer(msg_txt, reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_remocao_origem)
    elif texto == "🔙 Voltar ao Menu de Edição":
        data = await state.get_data()
        novo_texto = str(data.get("indice_edicao") + 1)
        msg_simulada = message.model_copy(update={"text": novo_texto})
        if EXIBIR_LOGS: logger.info("🔙 Retornando ao menu de edição via mensagem simulada.")
        await selecionar_acao_edicao(msg_simulada, state)
    else:
        await message.answer("Use os botões do menu para escolher a ação.")

@router.message(EspelhadorFluxo.aguardando_edicao_novo_nome)
async def salvar_edicao_nome(message: types.Message, state: FSMContext):
    novo_nome = message.text.strip()
    data = await state.get_data()
    indice = data.get("indice_edicao")
    
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    
    nome_antigo = rotas[indice]["nome"]
    rotas[indice]["nome"] = novo_nome
    dados["rotas"] = rotas
    salvar_espelhos(dados)
    
    # Sincroniza a fila de espelhamento para que os vídeos retidos não fiquem órfãos
    try:
        fila_dados = ler_fila_espelhador()
        fila = fila_dados.get("fila", [])
        houve_alteracao = False
        for item in fila:
            if item.get("nome_rota") == nome_antigo:
                item["nome_rota"] = novo_nome
                houve_alteracao = True
        if houve_alteracao:
            salvar_fila_espelhador(fila_dados)
            if EXIBIR_LOGS: logger.info(f"🔄 Fila de espelhamento sincronizada com o novo nome da rota.")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao sincronizar a fila de espelhamento após mudança de nome: {e}")

    if EXIBIR_LOGS: logger.info(f"✏️ Nome da rota '{nome_antigo}' atualizado para '{novo_nome}'.")
    await message.answer(f"✅ O nome da rota foi atualizado para <b>{novo_nome}</b> com sucesso!", parse_mode="HTML")
    # ✅ CORREÇÃO: Volta para o menu de edição da rota atual
    novo_texto = str(indice + 1)
    msg_simulada = message.model_copy(update={"text": novo_texto})
    if EXIBIR_LOGS: logger.info("🔙 Retornando ao menu da rota atual via mensagem simulada (Nome).")
    await selecionar_acao_edicao(msg_simulada, state)

@router.message(EspelhadorFluxo.aguardando_edicao_novo_destino)
async def salvar_edicao_destino(message: types.Message, state: FSMContext):
    msg_status = await message.answer("⏳ Validando o novo canal de destino...", reply_markup=teclado_espelhador_cancelar)
    sucesso, novo_destino, nome = await validar_e_formatar_alvo(bot_instance, message.text)

    if not sucesso:
        await msg_status.delete()
        await message.answer("⚠️ Canal não encontrado ou formato inválido. Tente novamente:", reply_markup=teclado_espelhador_cancelar)
        return

    salvar_nome_grupo(novo_destino, nome)
    await msg_status.delete()
    data = await state.get_data()
    indice = data.get("indice_edicao")

    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    nome_rota = rotas[indice]["nome"]
    rotas[indice]["destino"] = novo_destino
    dados["rotas"] = rotas
    salvar_espelhos(dados)

    if EXIBIR_LOGS: logger.info(f"✏️ Destino da rota '{nome_rota}' atualizado para {novo_destino}.")
    await message.answer(f"✅ O destino da rota <b>{nome_rota}</b> foi atualizado para <code>{novo_destino}</code> com sucesso!", parse_mode="HTML")
    # ✅ CORREÇÃO: Volta para o menu de edição da rota atual
    novo_texto = str(indice + 1)
    msg_simulada = message.model_copy(update={"text": novo_texto})
    if EXIBIR_LOGS: logger.info("🔙 Retornando ao menu da rota atual via mensagem simulada (Destino).")
    await selecionar_acao_edicao(msg_simulada, state)

@router.message(EspelhadorFluxo.aguardando_edicao_nova_janela)
async def salvar_edicao_janela(message: types.Message, state: FSMContext):
    import re
    match = re.match(r"^(\d{1,2})-(\d{1,2})$", message.text.strip())
    if not match:
        await message.answer("Formato inválido! Use o formato exato como no exemplo: 10-22", reply_markup=teclado_espelhador_cancelar)
        return
        
    inicio, fim = map(int, match.groups())
    if inicio >= fim or inicio < 0 or fim > 23:
        await message.answer("Valores inválidos! A hora de início deve ser menor que a do fim.", reply_markup=teclado_espelhador_cancelar)
        return
        
    data = await state.get_data()
    indice = data.get("indice_edicao")
    
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    rotas[indice]["inicio"] = inicio
    rotas[indice]["fim"] = fim
    dados["rotas"] = rotas
    salvar_espelhos(dados)
    
    if EXIBIR_LOGS: logger.info(f"✏️ Janela da rota '{rotas[indice]['nome']}' atualizada para {inicio}h-{fim}h.")
    await message.answer(f"✅ A janela foi atualizada para {inicio}h às {fim}h com sucesso!", parse_mode="HTML")
    # ✅ CORREÇÃO: Volta para o menu de edição da rota atual
    novo_texto = str(indice + 1)
    msg_simulada = message.model_copy(update={"text": novo_texto})
    if EXIBIR_LOGS: logger.info("🔙 Retornando ao menu da rota atual via mensagem simulada (Janela).")
    await selecionar_acao_edicao(msg_simulada, state)

@router.message(EspelhadorFluxo.aguardando_edicao_intervalo_dias)
async def salvar_edicao_intervalo_dias(message: types.Message, state: FSMContext):
    mapa_dias = {"Mesmo Dia (D+0) 🟢": 0, "Dia Seguinte (D+1) 🟡": 1, "Dois Dias (D+2) 🔵": 2}
    
    if message.text not in mapa_dias:
        await message.answer("Por favor, utilize os botões para escolher o intervalo.", reply_markup=teclado_espelhador_cancelar)
        return
        
    intervalo = mapa_dias[message.text]
    data = await state.get_data()
    indice = data.get("indice_edicao")
    
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    
    rotas[indice]["intervalo_dias"] = intervalo
    dados["rotas"] = rotas
    salvar_espelhos(dados)
    
    # 🔫 O NOVO GATILHO INTELIGENTE: Limpa o carimbo de horário para forçar o Motor a recalcular!
    try:
        fila_dados = ler_fila_espelhador()
        houve_reset = False
        for item in fila_dados.get("fila", []):
            if item.get("nome_rota") == rotas[indice]["nome"] and not item.get("processado"):
                item["horario_disparo"] = "" # Limpa para o Motor agir
                houve_reset = True
        if houve_reset:
            salvar_fila_espelhador(fila_dados)
            if EXIBIR_LOGS: logger.info(f"🔄 Fila da rota '{rotas[indice]['nome']}' resetada para recálculo orgânico.")
    except Exception as e:
        pass
    
    if EXIBIR_LOGS: logger.info(f"✏️ Atraso dinâmico da rota '{rotas[indice]['nome']}' modificado para D+{intervalo}.")
    await message.answer(f"✅ O intervalo temporal foi atualizado para D+{intervalo}!\nO Motor Central já está a recalcular os horários de forma orgânica e respeitando a janela.", parse_mode="HTML")
    # ✅ CORREÇÃO: Volta para o menu de edição da rota atual
    novo_texto = str(indice + 1)
    msg_simulada = message.model_copy(update={"text": novo_texto})
    if EXIBIR_LOGS: logger.info("🔙 Retornando ao menu da rota atual via mensagem simulada (Dias).")
    await selecionar_acao_edicao(msg_simulada, state)

@router.message(EspelhadorFluxo.aguardando_edicao_novo_modo)
async def salvar_edicao_modo(message: types.Message, state: FSMContext):
    if message.text not in ["Aleatório 🔀", "Ordem de Chegada ⬇️"]:
        await message.answer("Por favor, use os botões para escolher o modo.", reply_markup=teclado_espelhador_cancelar)
        return
        
    modo = "aleatorio" if message.text == "Aleatório 🔀" else "ordem"
    data = await state.get_data()
    indice = data.get("indice_edicao")
    
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    rotas[indice]["modo"] = modo
    dados["rotas"] = rotas
    salvar_espelhos(dados)
    
    if EXIBIR_LOGS: logger.info(f"✏️ Modo da rota '{rotas[indice]['nome']}' atualizado para {modo}.")
    await message.answer(f"✅ O modo de distribuição foi atualizado para {message.text} com sucesso!", parse_mode="HTML")
    # ✅ CORREÇÃO: Volta para o menu de edição da rota atual
    novo_texto = str(indice + 1)
    msg_simulada = message.model_copy(update={"text": novo_texto})
    if EXIBIR_LOGS: logger.info("🔙 Retornando ao menu da rota atual via mensagem simulada (Modo).")
    await selecionar_acao_edicao(msg_simulada, state)

@router.message(EspelhadorFluxo.aguardando_nova_origem)
async def confirmar_nova_origem(message: types.Message, state: FSMContext):
    entradas_brutas = message.text.replace('\n', ',').split(',')
    origens_validas = []
    
    msg_status = await message.answer("⏳ Validando links, subgrupos e buscando nomes...", reply_markup=teclado_espelhador_cancelar)
    
    for entrada in entradas_brutas:
        if not entrada.strip(): continue
        
        sucesso, id_final, nome = await validar_e_formatar_alvo(bot_instance, entrada)
        
        if sucesso and id_final not in [o['id'] for o in origens_validas]:
            salvar_nome_grupo(id_final, nome)
            origens_validas.append({"id": id_final, "nome": nome})

    await msg_status.delete()

    if not origens_validas:
        await message.answer("⚠️ Nenhum canal válido encontrado ou formato incorreto. Tente novamente:", reply_markup=teclado_espelhador_cancelar)
        return

    data = await state.get_data()
    indice = data.get("indice_edicao")
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    rota_atual = rotas[indice]
    
    origens_atuais = rota_atual.get('origens', [])
    if not origens_atuais and 'origem' in rota_atual: origens_atuais = [rota_atual['origem']]
    
    # Filtra as que já estão na rota atual
    origens_para_adicionar = [o for o in origens_validas if o['id'] not in origens_atuais]
    
    if not origens_para_adicionar:
        await message.answer("⚠️ Todas as origens enviadas já estão cadastradas nesta rota.", reply_markup=teclado_espelhador_cancelar)
        return

    await state.update_data(origens_para_adicionar=origens_para_adicionar)
    
    texto_resumo = f"✅ <b>{len(origens_para_adicionar)} Origem(ns) Validada(s):</b>\n"
    for o in origens_para_adicionar:
        texto_resumo += f"└ {o['nome']} (<code>{o['id']}</code>)\n"
    
    if len(rotas) > 1:
        texto_resumo += f"\nO seu sistema possui <b>{len(rotas)} rotas ativas</b>. Onde deseja adicionar?"
        await message.answer(texto_resumo, reply_markup=teclado_espelhador_abrangencia, parse_mode="HTML")
    else:
        texto_resumo += f"\nDeseja adicionar à rota <b>{rota_atual['nome']}</b>?"
        await message.answer(texto_resumo, reply_markup=teclado_espelhador_confirmacao, parse_mode="HTML")
    
    await state.set_state(EspelhadorFluxo.aguardando_confirmacao_nova_origem)

@router.message(EspelhadorFluxo.aguardando_confirmacao_nova_origem)
async def processar_nova_origem(message: types.Message, state: FSMContext):
    opcoes_validas = ["Aprovar ✅", "Apenas nesta Rota 🎯", "Em TODAS as Rotas 🌍"]
    
    if message.text not in opcoes_validas:
        await message.answer("Por favor, utilize os botões para confirmar.")
        return

    data = await state.get_data()
    indice_atual = data.get("indice_edicao")
    origens_novas = data.get("origens_para_adicionar", [])
    
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    
    insercoes = 0
    
    if message.text == "Em TODAS as Rotas 🌍":
        for r in rotas:
            origens_r = r.get('origens', [])
            if not origens_r and 'origem' in r: origens_r = [r['origem']]
            
            for o in origens_novas:
                if o['id'] not in origens_r:
                    origens_r.append(o['id'])
                    insercoes += 1
            
            r['origens'] = origens_r
            if 'origem' in r: del r['origem']
            
        msg_final = f"✅ <b>{len(origens_novas)} Origem(ns) processada(s) globalmente nas rotas!</b>"
            
    else:
        rota = rotas[indice_atual]
        origens_r = rota.get('origens', [])
        if not origens_r and 'origem' in rota: origens_r = [rota['origem']]
        
        for o in origens_novas:
            if o['id'] not in origens_r:
                origens_r.append(o['id'])
                insercoes += 1
                
        rota['origens'] = origens_r
        if 'origem' in rota: del rota['origem']
        msg_final = f"✅ <b>{len(origens_novas)} Origem(ns) adicionada(s) à rota '{rota['nome']}'!</b>"
    
    if insercoes > 0:
        salvar_espelhos(dados)
        
    await message.answer(msg_final, parse_mode="HTML")
    
    # 🚀 CORREÇÃO: Volta suavemente ao menu da rota após aprovar
    novo_texto = str(indice_atual + 1)
    msg_simulada = message.model_copy(update={"text": novo_texto})
    await selecionar_acao_edicao(msg_simulada, state)

@router.message(EspelhadorFluxo.aguardando_remocao_origem)
async def confirmar_remocao_origem(message: types.Message, state: FSMContext):
    entradas = message.text.replace(' ', '').split(',')
    indices_para_remover = []
    
    data = await state.get_data()
    indice = data.get("indice_edicao")
    dados = ler_espelhos()
    rota = dados["rotas"][indice]
    origens = rota.get('origens', [])
    if not origens and 'origem' in rota: origens = [rota['origem']]
    
    for entrada in entradas:
        if entrada.isdigit():
            idx = int(entrada) - 1
            if 0 <= idx < len(origens) and idx not in indices_para_remover:
                indices_para_remover.append(idx)
                
    if not indices_para_remover:
        await message.answer("⚠️ Nenhum número válido detectado. Tente novamente:", reply_markup=teclado_espelhador_cancelar)
        return
        
    await state.update_data(indices_origem_remocao=indices_para_remover)
    
    texto_confirmacao = f"⚠️ Tem certeza de que deseja desvincular <b>{len(indices_para_remover)} origem(ns)</b> da rota <b>{rota['nome']}</b>?\n\n"
    for idx in indices_para_remover:
        texto_confirmacao += f"🗑️ <code>{origens[idx]}</code>\n"
        
    await message.answer(texto_confirmacao, reply_markup=teclado_espelhador_confirmacao, parse_mode="HTML")
    await state.set_state(EspelhadorFluxo.aguardando_confirmacao_remocao_origem)

@router.message(EspelhadorFluxo.aguardando_confirmacao_remocao_origem)
async def processar_remocao_origem(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Por favor, utilize os botões para Aprovar ✅ ou Cancelar Operação ❌.")
        return

    data = await state.get_data()
    indice_rota = data.get("indice_edicao")
    indices_remover = data.get("indices_origem_remocao", [])
    
    dados = ler_espelhos()
    rota = dados["rotas"][indice_rota]
    origens = rota.get('origens', [])
    if not origens and 'origem' in rota: origens = [rota['origem']]
    
    # Ordena de trás para frente para evitar bugs na remoção múltipla
    indices_remover.sort(reverse=True)
    
    removidos = 0
    for idx in indices_remover:
        if 0 <= idx < len(origens):
            origens.pop(idx)
            removidos += 1
            
    if removidos > 0:
        rota['origens'] = origens
        salvar_espelhos(dados)
        await message.answer(f"✅ <b>{removidos} origem(ns) desvinculada(s) com sucesso!</b>", parse_mode="HTML")
    else:
        await message.answer("Erro de sincronização. As origens não puderam ser removidas.")
        
    # 🚀 CORREÇÃO: Volta suavemente ao menu da rota após aprovar
    novo_texto = str(indice_rota + 1)
    msg_simulada = message.model_copy(update={"text": novo_texto})
    await selecionar_acao_edicao(msg_simulada, state)

@router.message(EspelhadorFluxo.menu_principal, F.text == "Forçar Postagens 🚀")
async def iniciar_esvaziar_fila(message: types.Message, state: FSMContext):
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    if not rotas:
        await message.answer("Não há rotas ativas no sistema.", reply_markup=teclado_espelhador_menu)
        return
        
    texto = "Selecione de qual rota deseja <b>PUBLICAR AGORA</b> todos os vídeos pendentes:\n\n"
    for i, rota in enumerate(rotas, 1):
        qtd_fila = ler_contador_espelhador(rota['nome'])
        texto += f"{i}. {rota['nome']} ({qtd_fila} vídeos retidos)\n"
        
    await message.answer(texto, reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
    await state.set_state(EspelhadorFluxo.aguardando_rota_esvaziar)

@router.message(EspelhadorFluxo.aguardando_rota_esvaziar)
async def confirmar_esvaziar(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas o número da rota.", reply_markup=teclado_espelhador_cancelar)
        return
        
    indice = int(message.text) - 1
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    
    if 0 <= indice < len(rotas):
        rota = rotas[indice]
        qtd_fila = ler_contador_espelhador(rota['nome'])
        if qtd_fila == 0:
            await message.answer("A fila de disparo desta rota já está vazia.", reply_markup=teclado_espelhador_menu)
            await state.set_state(EspelhadorFluxo.menu_principal)
            return
            
        await state.update_data(indice_esvaziar=indice)
        await message.answer(f"🚀 Tem certeza que deseja forçar o disparo de <b>{qtd_fila} vídeos</b> da rota <b>{rota['nome']}</b> imediatamente?", reply_markup=teclado_espelhador_confirmacao, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_confirmacao_esvaziar)
    else:
        await message.answer("Número inválido. Tente novamente.", reply_markup=teclado_espelhador_cancelar)

# BLOCO MODIFICADO (Substituir todo o bloco @dp.callback_query_handler antigo por este)
@router.message(EspelhadorFluxo.aguardando_confirmacao_esvaziar)
async def processar_esvaziar_fila(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Operação cancelada.", reply_markup=teclado_espelhador_menu)
        await painel_espelhador(message, state)
        return

    if EXIBIR_LOGS: logger.info("🚀 Iniciando processo de forçar postagens para o espelhador...")
    
    data = await state.get_data()
    indice_rota = data.get("indice_esvaziar")
    
    if indice_rota is None:
        if EXIBIR_LOGS: logger.error("❌ Erro: Rota não encontrada no estado da máquina.")
        await message.answer("Erro ao identificar a rota selecionada.")
        return

    try:
        dados = ler_espelhos()
        rotas = dados.get("rotas", [])
        
        if 0 <= indice_rota < len(rotas):
            rota_alvo = rotas[indice_rota]
            rota_alvo["esvaziar_agora"] = True
            
            salvar_espelhos(dados)
            
            if EXIBIR_LOGS: logger.info(f"✅ Sucesso: Rota '{rota_alvo['nome']}' marcada para esvaziamento imediato.")
            await message.answer(f"✅ <b>Postagens Forçadas!</b>\nTodos os vídeos pendentes na rota <b>{rota_alvo['nome']}</b> serão publicados nos canais em instantes.", parse_mode="HTML", reply_markup=teclado_espelhador_menu)
        else:
            await message.answer("A rota selecionada é inválida ou expirou.")
            
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao atualizar configuração do espelhador: {e}")
        await message.answer("Ocorreu um erro interno ao processar o esvaziamento.")
        
    await state.clear()

