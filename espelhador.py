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
# --- MÁQUINA DE ESTADOS E TECLADOS ---
class EspelhadorFluxo(StatesGroup):
    menu_principal = State()
    aguardando_origem = State()
    aguardando_destino = State()
    aguardando_janela = State()
    aguardando_modo = State()
    aguardando_confirmacao_criacao = State()
    aguardando_remocao = State()
    aguardando_confirmacao_remocao_rota = State()
    aguardando_edicao_escolha_rota = State()
    aguardando_acao_edicao = State()
    aguardando_edicao_novo_nome = State()
    aguardando_edicao_nova_janela = State()
    aguardando_edicao_novo_modo = State()
    aguardando_nova_origem = State()
    aguardando_confirmacao_nova_origem = State()
    aguardando_remocao_origem = State()
    aguardando_confirmacao_remocao_origem = State()
    aguardando_rota_esvaziar = State()
    aguardando_confirmacao_esvaziar = State()

teclado_espelhador_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Adicionar Rota ➕"), KeyboardButton(text="Remover Rota 🗑️")],
        [KeyboardButton(text="Editar Rota ✏️"), KeyboardButton(text="Forçar Postagens 🚀")],
        [KeyboardButton(text="Relatório da Fila 📊"), KeyboardButton(text="Voltar aos Canais 🔙")]
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
    keyboard=[[KeyboardButton(text="Aprovar ✅"), KeyboardButton(text="Cancelar Operação ❌")]],
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
            qtd_fila = ler_contador_espelhador(rota['nome'])
            status_canais = rota.get("status_canais", {})
            
            texto += f"<b>{i}. {rota['nome']}</b>\n"
            texto += f"   🕒 Janela de Postagem: {rota.get('inicio', 10)}h às {rota.get('fim', 22)}h\n"
            texto += f"   🔀 Distribuição: {rota.get('modo', 'ordem').title()}\n"
            texto += f"   📦 Fila de Espera: {qtd_fila} vídeo(s)\n"
            texto += "\n"
            texto += f"   📥 <b>Origens:</b>\n"
            
            origens = rota.get('origens', [])
            # Retrocompatibilidade com rotas antigas caso existam
            if not origens and 'origem' in rota:
                origens = [rota['origem']]
                
            for idx, o in enumerate(origens):
                info_o = status_canais.get(str(o), {})
                if isinstance(info_o, str): info_o = {"status": info_o, "nome": str(o)}
                
                status_ico = "❌" if info_o.get("status") == "erro" else "✅"
                nome_o = info_o.get("nome", str(o))
                display_o = f"{nome_o} (<code>{o}</code>)" if nome_o != str(o) else f"<code>{o}</code>"
                texto += f"      ├ {status_ico} {display_o}\n"

            texto += "\n"
                
            info_d = status_canais.get(str(destino_rota), {})
            if isinstance(info_d, str): info_d = {"status": info_d, "nome": str(destino_rota)}
            
            status_destino_ico = "❌" if info_d.get("status") == "erro" else "✅"
            nome_d = info_d.get("nome", str(destino_rota))
            display_d = f"{nome_d} (<code>{destino_rota}</code>)" if nome_d != str(destino_rota) else f"<code>{destino_rota}</code>"
            texto += f"   🎯 <b>Destino:</b>\n"
            texto += f"      └ {status_destino_ico} {display_d}\n\n"
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
        await message.answer(f"✅ Destino confirmado: <code>{destino_id}</code>\n\nDefina a <b>Janela de Horário</b> para a postagem no dia seguinte.\nEnvie no formato <code>Inicio-Fim</code> (Exemplo: <code>10-22</code> para distribuir entre as 10h e as 22h):", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_janela)
    else:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Falha na validação do destino: {message.text}")
        await message.answer("⚠️ <b>Canal não encontrado ou sem permissão!</b>\nCertifique-se de que o ID ou @username está correto e de que o bot é administrador do canal.\n\nTente enviar novamente:", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")

@router.message(EspelhadorFluxo.aguardando_janela)
async def receber_janela_rota(message: types.Message, state: FSMContext):
    import re
    match = re.match(r"^(\d{1,2})-(\d{1,2})$", message.text.strip())
    if not match:
        await message.answer("Formato inválido! Use o formato exato como no exemplo: 10-22", reply_markup=teclado_espelhador_cancelar)
        return
        
    inicio, fim = map(int, match.groups())
    if inicio >= fim or inicio < 0 or fim > 23:
        await message.answer("Valores inválidos! A hora de início deve ser menor que a do fim.", reply_markup=teclado_espelhador_cancelar)
        return

    await state.update_data(inicio=inicio, fim=fim)
    
    teclado_modo = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Aleatório 🔀"), KeyboardButton(text="Ordem de Chegada ⬇️")],
            [KeyboardButton(text="Cancelar Operação ❌")]
        ], resize_keyboard=True, is_persistent=True
    )
    await message.answer("Como deseja distribuir os vídeos retidos dentro dessa janela de horário no dia seguinte?", reply_markup=teclado_modo)
    await state.set_state(EspelhadorFluxo.aguardando_modo)

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
    
    texto_confirmacao = (
        f"⚠️ <b>Confirmação de Criação de Rota (D+1)</b>\n\n"
        f"<b>Origens Mapeadas ({len(origens)}):</b>\n"
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
    inicio = data.get("inicio")
    fim = data.get("fim")
    modo = data.get("modo")
    
    dados = ler_espelhos()
    
    if EXIBIR_LOGS: logger.info(f"🚀 A agrupar {len(origens)} origens numa única rota de espelhamento D+1 para o destino {destino}...")
    
    num_rota = len(dados.get("rotas", [])) + 1
    nome_rota = f"Espelho {num_rota}"
    
    nova_rota = {
        "nome": nome_rota,
        "origens": origens,
        "destino": destino,
        "inicio": inicio,
        "fim": fim,
        "modo": modo
    }
    
    dados.setdefault("rotas", []).append(nova_rota)
    salvar_espelhos(dados)
    
    if EXIBIR_LOGS: logger.info(f"✅ Rota inteligente criada com sucesso: {nome_rota}.")
    
    await message.answer(f"✅ <b>Rota {nome_rota}</b> ativada!\nOs vídeos capturados hoje serão postados amanhã entre as {inicio}h e as {fim}h.", parse_mode="HTML")
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
        qtd_origens = len(rota.get('origens', [rota.get('origem')]))
        texto += f"{i}. {rota['nome']} ({qtd_origens} origens agrupadas)\n"
        
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

@router.message(EspelhadorFluxo.menu_principal, F.text == "Editar Rota ✏️")
async def iniciar_edicao_rota(message: types.Message, state: FSMContext):
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    
    if not rotas:
        await message.answer("Não há rotas ativas para editar.", reply_markup=teclado_espelhador_menu)
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
        texto += f"🔀 Modo atual: {rota_alvo.get('modo', 'ordem').title()}\n"
        
        origens = rota_alvo.get('origens', [])
        if not origens and 'origem' in rota_alvo: origens = [rota_alvo['origem']]
        texto += f"📥 Origens: {len(origens)} canal(is)\n\n"
        texto += "Escolha a ação que deseja realizar:"
        
        teclado_submenu = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📝 Editar Nome"), KeyboardButton(text="🕒 Modificar Janela")],
                [KeyboardButton(text="🔀 Modificar Modo"), KeyboardButton(text="➕ Adicionar Origem")],
                [KeyboardButton(text="🗑️ Remover Origem"), KeyboardButton(text="Cancelar Operação ❌")]
            ], resize_keyboard=True, is_persistent=True)
            
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
    elif texto == "🕒 Modificar Janela":
        await message.answer("Digite a <b>NOVA JANELA</b> no formato <code>Inicio-Fim</code> (Ex: 10-22):", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_edicao_nova_janela)
    elif texto == "🔀 Modificar Modo":
        teclado_modo = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Aleatório 🔀"), KeyboardButton(text="Ordem de Chegada ⬇️")],
                [KeyboardButton(text="Cancelar Operação ❌")]
            ], resize_keyboard=True, is_persistent=True
        )
        await message.answer("Escolha o novo modo de distribuição:", reply_markup=teclado_modo)
        await state.set_state(EspelhadorFluxo.aguardando_edicao_novo_modo)
    elif texto == "➕ Adicionar Origem":
        await message.answer("Envie o ID numérico, link ou @username da nova origem que deseja adicionar a esta rota:", reply_markup=teclado_espelhador_cancelar)
        await state.set_state(EspelhadorFluxo.aguardando_nova_origem)
    elif texto == "🗑️ Remover Origem":
        data = await state.get_data()
        indice = data.get("indice_edicao")
        rotas = ler_espelhos().get("rotas", [])
        rota = rotas[indice]
        origens = rota.get('origens', [])
        if not origens and 'origem' in rota: origens = [rota['origem']]
        
        if not origens:
            await message.answer("Esta rota não possui origens para remover.")
            return
            
        msg_txt = "Qual origem deseja remover? Digite o <b>NÚMERO</b> correspondente:\n\n"
        for i, orig in enumerate(origens, 1):
            msg_txt += f"{i}. <code>{orig}</code>\n"
            
        await message.answer(msg_txt, reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_remocao_origem)
    else:
        await message.answer("Use os botões do menu para escolher a ação.", reply_markup=teclado_espelhador_cancelar)

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
    await painel_espelhador(message, state)

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
    await painel_espelhador(message, state)

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
    await painel_espelhador(message, state)

@router.message(EspelhadorFluxo.aguardando_nova_origem)
async def confirmar_nova_origem(message: types.Message, state: FSMContext):
    msg_status = await message.answer("⏳ Validando permissões da nova origem...", reply_markup=teclado_espelhador_cancelar)
    origem_id = await validar_link_ou_id_grupo(message.text)
    await msg_status.delete()
    
    if origem_id:
        data = await state.get_data()
        indice = data.get("indice_edicao")
        dados = ler_espelhos()
        rota = dados["rotas"][indice]
        origens = rota.get('origens', [])
        if not origens and 'origem' in rota: origens = [rota['origem']]
        
        if origem_id not in origens:
            await state.update_data(origem_para_adicionar=origem_id)
            await message.answer(f"Deseja adicionar a origem <code>{origem_id}</code> à rota <b>{rota['nome']}</b>?", reply_markup=teclado_espelhador_confirmacao, parse_mode="HTML")
            await state.set_state(EspelhadorFluxo.aguardando_confirmacao_nova_origem)
        else:
            await message.answer("⚠️ Esta origem já está cadastrada nesta rota.", reply_markup=teclado_espelhador_cancelar)
    else:
        await message.answer("⚠️ Canal não encontrado ou inválido. Tente novamente:", reply_markup=teclado_espelhador_cancelar)

@router.message(EspelhadorFluxo.aguardando_confirmacao_nova_origem)
async def processar_nova_origem(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Operação cancelada.", reply_markup=teclado_espelhador_menu)
        await painel_espelhador(message, state)
        return

    data = await state.get_data()
    indice = data.get("indice_edicao")
    origem_id = data.get("origem_para_adicionar")
    
    dados = ler_espelhos()
    rota = dados["rotas"][indice]
    origens = rota.get('origens', [])
    if not origens and 'origem' in rota: origens = [rota['origem']]
    
    origens.append(origem_id)
    rota['origens'] = origens
    if 'origem' in rota: del rota['origem']
    salvar_espelhos(dados)
    
    if EXIBIR_LOGS: logger.info(f"➕ Nova origem {origem_id} inserida na rota '{rota['nome']}'.")
    await message.answer(f"✅ Origem <code>{origem_id}</code> adicionada com sucesso!", parse_mode="HTML")
    await painel_espelhador(message, state)

@router.message(EspelhadorFluxo.aguardando_remocao_origem)
async def confirmar_remocao_origem(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas o número correspondente.", reply_markup=teclado_espelhador_cancelar)
        return
        
    idx_origem = int(message.text) - 1
    data = await state.get_data()
    indice = data.get("indice_edicao")
    
    dados = ler_espelhos()
    rota = dados["rotas"][indice]
    origens = rota.get('origens', [])
    if not origens and 'origem' in rota: origens = [rota['origem']]
    
    if 0 <= idx_origem < len(origens):
        origem_alvo = origens[idx_origem]
        await state.update_data(indice_origem_remocao=idx_origem)
        
        await message.answer(f"⚠️ Tem certeza de que deseja desvincular a origem <code>{origem_alvo}</code> da rota <b>{rota['nome']}</b>?", reply_markup=teclado_espelhador_confirmacao, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_confirmacao_remocao_origem)
    else:
        await message.answer("Número de origem inválido. Tente novamente:", reply_markup=teclado_espelhador_cancelar)

@router.message(EspelhadorFluxo.aguardando_confirmacao_remocao_origem)
async def processar_remocao_origem(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Operação cancelada.", reply_markup=teclado_espelhador_menu)
        await painel_espelhador(message, state)
        return

    data = await state.get_data()
    indice_rota = data.get("indice_edicao")
    idx_origem = data.get("indice_origem_remocao")
    
    dados = ler_espelhos()
    rota = dados["rotas"][indice_rota]
    origens = rota.get('origens', [])
    if not origens and 'origem' in rota: origens = [rota['origem']]
    
    if 0 <= idx_origem < len(origens):
        removido = origens.pop(idx_origem)
        rota['origens'] = origens
        salvar_espelhos(dados)
        
        if EXIBIR_LOGS: logger.info(f"🗑️ Origem {removido} removida da rota '{rota['nome']}'.")
        await message.answer(f"✅ Origem <code>{removido}</code> desvinculada com sucesso!", parse_mode="HTML")
    else:
        await message.answer("Erro de sincronização. A origem não pôde ser removida.")
        
    await painel_espelhador(message, state)

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

@router.message(EspelhadorFluxo.aguardando_confirmacao_esvaziar)
async def processar_esvaziar(message: types.Message, state: FSMContext):
    if message.text != "Aprovar ✅":
        await message.answer("Ação de esvaziamento cancelada.", reply_markup=teclado_espelhador_menu)
        await painel_espelhador(message, state)
        return
        
    data = await state.get_data()
    indice = data.get("indice_esvaziar")
    dados = ler_espelhos()
    rota = dados["rotas"][indice]
    
    rota["esvaziar_agora"] = True
    salvar_espelhos(dados)
    
    if EXIBIR_LOGS: logger.info(f"🚀 Comando de esvaziamento imediato acionado para a rota '{rota['nome']}'.")
    await message.answer(f"🚀 <b>Comando Enviado!</b>\nO motor reconheceu a instrução e iniciará a publicação de todos os vídeos pendentes da rota <b>{rota['nome']}</b> em poucos segundos.", parse_mode="HTML")
    await painel_espelhador(message, state)

@router.message(EspelhadorFluxo.menu_principal, F.text == "Relatório da Fila 📊")
async def gerar_relatorio_fila_principal(message: types.Message, state: FSMContext):
    try:
        with open("fila_espelhador.json", "r", encoding="utf-8") as f:
            dados_fila = json.load(f)
            fila = dados_fila.get("fila", [])
    except (FileNotFoundError, json.JSONDecodeError):
        fila = []

    if not fila:
        await message.answer("📭 A fila de espelhamento D+1 está vazia no momento.", parse_mode="HTML")
        return

    rotas_agrupadas = {}
    for item in fila:
        nome = item.get("nome_rota", "Rota Desconhecida")
        if nome not in rotas_agrupadas:
            rotas_agrupadas[nome] = []
        rotas_agrupadas[nome].append(item)

    texto = "📊 <b>Relatório da Fila (D+1)</b>\n\n"
    for nome_rota, itens in rotas_agrupadas.items():
        texto += f"📡 <b>Rota: {nome_rota}</b> ({len(itens)} vídeos aguardando)\n"
        
        # Limita a exibição aos primeiros 15 vídeos de cada rota para não travar o Telegram
        for i, v in enumerate(itens[:15], 1):
            data_cap = v.get("data_captura", "Data não registrada")
            origem = v.get("origem", "Origem não mapeada")
            texto += f"  ├ {i}. Origem: <code>{origem}</code> | Captura: {data_cap}\n"
        
        if len(itens) > 15:
            texto += f"  └ <i>... e mais {len(itens) - 15} vídeos aguardando.</i>\n"
        texto += "\n"

    await message.answer(texto, parse_mode="HTML")
