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
    aguardando_remocao = State()

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

# --- VALIDAÇÃO DE ACESSO ---
async def validar_link_ou_id_grupo(entrada):
    if not bot_instance: return None
    
    entradas_para_testar = []
    entrada_limpa = entrada.strip()
    
    if "t.me/" in entrada_limpa:
        username = entrada_limpa.split("t.me/")[-1].split("/")[0]
        if not username.startswith("+"):
            entradas_para_testar.append(f"@{username}")
    else:
        entradas_para_testar.append(entrada_limpa)
        if entrada_limpa.replace('-', '').isdigit():
            if not entrada_limpa.startswith("-100") and not entrada_limpa.startswith("@"):
                entradas_para_testar.append(f"-100{entrada_limpa.replace('-', '')}")
        elif not entrada_limpa.startswith("@"):
            entradas_para_testar.append(f"@{entrada_limpa}")

    for teste in entradas_para_testar:
        try:
            chat = await bot_instance.get_chat(teste)
            return str(chat.id)
        except Exception:
            continue
            
    return None

# --- CONVERSÃO DE LINKS SHOPEE ---
async def converter_link_shopee_espelho(link_original):
    app_id = os.getenv('SHOPEE_APP_ID')
    app_secret = os.getenv('SHOPEE_APP_SECRET')
    
    if not app_id or not app_secret:
        return link_original

    link_processar = link_original
    
    if "shp.ee" in link_original or "shope.ee" in link_original or "s.shopee.com.br" in link_original:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(link_original, allow_redirects=True) as resp:
                    link_processar = str(resp.url)
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro ao expandir o link no espelho: {e}")

    timestamp = int(time.time())
    endpoint = "https://open-api.affiliate.shopee.com.br/graphql"

    payload = {
        "query": "mutation generateShortLink($originUrl: String!) { generateShortLink(input: {originUrl: $originUrl}) { shortLink } }",
        "variables": {"originUrl": link_processar}
    }
    
    payload_json = json.dumps(payload, separators=(',', ':'))
    fator_base = f"{app_id}{timestamp}{payload_json}{app_secret}"
    assinatura = hashlib.sha256(fator_base.encode('utf-8')).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={app_id}, Timestamp={timestamp}, Signature={assinatura}"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, data=payload_json) as response:
                resposta_dados = await response.json()
                if response.status == 200 and "data" in resposta_dados and resposta_dados["data"].get("generateShortLink"):
                    novo_link = resposta_dados["data"]["generateShortLink"]["shortLink"]
                    if EXIBIR_LOGS: logger.info("🔗 Conversão de comissão aplicada ao link com sucesso.")
                    return novo_link
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha de comunicação com a Shopee na conversão do espelho: {e}")
        
    return link_original

# --- MOTOR DE DISPARO ATRASADO ---
async def disparar_espelho(destino, texto, media_id, tipo_media):
    try:
        if tipo_media == "text":
            await bot_instance.send_message(chat_id=destino, text=texto, parse_mode="HTML")
        elif tipo_media == "photo":
            await bot_instance.send_photo(chat_id=destino, photo=media_id, caption=texto, parse_mode="HTML")
        elif tipo_media == "video":
            await bot_instance.send_video(chat_id=destino, video=media_id, caption=texto, parse_mode="HTML")
        elif tipo_media == "document":
            await bot_instance.send_document(chat_id=destino, document=media_id, caption=texto, parse_mode="HTML")
        elif tipo_media == "animation":
            await bot_instance.send_animation(chat_id=destino, animation=media_id, caption=texto, parse_mode="HTML")
            
        if EXIBIR_LOGS: logger.info(f"✅ Mídia espelhada entregue no destino {destino}.")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha no disparo do espelho para {destino}: {e}")

# --- INTERCEPTADOR GLOBAL ---
@router.message(F.chat.type.in_({"group", "supergroup"}))
@router.channel_post()
async def motor_interceptacao(message: types.Message):
    if not bot_instance or not scheduler_instance:
        return

    chat_id_str = str(message.chat.id)
    dados = ler_espelhos()
    rotas_ativas = [r for r in dados.get("rotas", []) if r["origem"] == chat_id_str]
    
    if not rotas_ativas:
        return

    if EXIBIR_LOGS: logger.info(f"🔄 Interceptação acionada! Nova postagem detectada na origem {chat_id_str}.")

    texto_original = message.html_text or ""
    texto_processado = texto_original
    links = re.findall(r'(https?://\S+)', texto_original)
    
    if links:
        if EXIBIR_LOGS: logger.info(f"🔗 Convertendo {len(links)} links encontrados na postagem...")
        for link in links:
            novo_link = await converter_link_shopee_espelho(link)
            texto_processado = texto_processado.replace(link, novo_link)

    tipo_media = "text"
    media_id = None
    
    if message.photo:
        tipo_media = "photo"
        media_id = message.photo[-1].file_id
    elif message.video:
        tipo_media = "video"
        media_id = message.video.file_id
    elif message.document:
        tipo_media = "document"
        media_id = message.document.file_id
    elif message.animation:
        tipo_media = "animation"
        media_id = message.animation.file_id

    agora = datetime.now(fuso_horario)

    for rota in rotas_ativas:
        destino = rota["destino"]
        delay_minutos = int(rota.get("delay", 0))
        nome_rota = rota.get("nome", "Desconhecida")
        
        horario_disparo = agora + timedelta(minutes=delay_minutos)
        
        job_id = f"espelho_{message.message_id}_{destino}_{int(agora.timestamp())}"
        
        scheduler_instance.add_job(
            disparar_espelho, 
            'date', 
            run_date=horario_disparo, 
            args=[destino, texto_processado, media_id, tipo_media], 
            id=job_id
        )
        
        if EXIBIR_LOGS: logger.info(f"⏳ Cópia da rota '{nome_rota}' agendada para daqui a {delay_minutos} minutos.")

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
    await message.answer("Envie o ID numérico ou @username do <b>Canal de ORIGEM</b> (De onde o robô vai copiar):", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
    await state.set_state(EspelhadorFluxo.aguardando_origem)

@router.message(EspelhadorFluxo.aguardando_origem)
async def receber_origem(message: types.Message, state: FSMContext):
    msg_status = await message.answer("⏳ Validando permissões e acesso ao canal de origem...", reply_markup=teclado_espelhador_cancelar)
    origem_id = await validar_link_ou_id_grupo(message.text)
    await msg_status.delete()
    
    if origem_id:
        if EXIBIR_LOGS: logger.info(f"✅ Origem validada com sucesso: {origem_id}")
        await state.update_data(origem=origem_id)
        await message.answer(f"✅ Origem confirmada: <code>{origem_id}</code>\n\nExcelente. Agora envie o ID numérico ou @username do <b>Canal de DESTINO</b> (Para onde o robô vai enviar a cópia):", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_destino)
    else:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Falha na validação da origem: {message.text}")
        await message.answer("⚠️ <b>Canal não encontrado ou sem permissão!</b>\nCertifique-se de que o ID ou @username está correto e de que o bot é administrador do canal.\n\nTente enviar novamente:", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")

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
async def finalizar_cadastro_rota(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas números inteiros para os minutos.", reply_markup=teclado_espelhador_cancelar)
        return
        
    data = await state.get_data()
    origem = data.get("origem")
    destino = data.get("destino")
    delay = int(message.text)
    
    dados = ler_espelhos()
    num_rota = len(dados.get("rotas", [])) + 1
    nome_rota = f"Espelho {num_rota}"
    
    nova_rota = {
        "nome": nome_rota,
        "origem": origem,
        "destino": destino,
        "delay": delay
    }
    
    dados.setdefault("rotas", []).append(nova_rota)
    salvar_espelhos(dados)
    
    if EXIBIR_LOGS: logger.info(f"✅ Rota de espelho cadastrada: Origem {origem} > Destino {destino} com delay de {delay}min.")
    
    await message.answer(f"✅ Rota <b>{nome_rota}</b> criada com sucesso!", parse_mode="HTML")
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
async def processar_remocao_rota(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Por favor, digite apenas o número da rota.", reply_markup=teclado_espelhador_cancelar)
        return
        
    indice = int(message.text) - 1
    dados = ler_espelhos()
    rotas = dados.get("rotas", [])
    
    if 0 <= indice < len(rotas):
        rota_removida = rotas.pop(indice)
        dados["rotas"] = rotas
        salvar_espelhos(dados)
        
        if EXIBIR_LOGS: logger.info(f"🗑️ Rota '{rota_removida['nome']}' removida permanentemente.")
        await message.answer(f"A rota <b>{rota_removida['nome']}</b> foi apagada e os espelhamentos foram interrompidos.", parse_mode="HTML")
        await painel_espelhador(message, state)
    else:
        await message.answer("Número inválido. Tente novamente ou clique em cancelar.", reply_markup=teclado_espelhador_cancelar)
