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
    aguardando_acao_blacklist = State()
    aguardando_blacklist_add = State()
    aguardando_blacklist_remove = State()

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

# ✅ NOVO: Teclado exclusivo de navegação para voltar sem "cancelar"
teclado_espelhador_voltar = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Voltar ao Menu Espelho 🔙")]],
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

def obter_teclado_importacao_espelhador():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Importar Banco Global 🌍")], [KeyboardButton(text="Cancelar Operação ❌")]], resize_keyboard=True, is_persistent=True)

# --- NAVEGAÇÃO E PAINEL ---
@router.message(F.text.in_(["Cancelar Operação ❌", "Voltar ao Menu Espelho 🔙"]), StateFilter("*"))
async def cancelar_espelhador(message: types.Message, state: FSMContext):
    estado_atual = await state.get_state()
    data = await state.get_data()
    
    # --- NÍVEL 3: Submenu de Origens (Volta para os botões Adicionar/Remover/Blacklist) ---
    estados_origem = [
        "EspelhadorFluxo:aguardando_nova_origem",
        "EspelhadorFluxo:aguardando_confirmacao_nova_origem",
        "EspelhadorFluxo:aguardando_remocao_origem",
        "EspelhadorFluxo:aguardando_confirmacao_remocao_origem",
        "EspelhadorFluxo:aguardando_acao_blacklist",
        "EspelhadorFluxo:aguardando_blacklist_add",
        "EspelhadorFluxo:aguardando_blacklist_remove"
    ]
    
    if estado_atual in estados_origem:
        if EXIBIR_LOGS: logger.info("🔙 Cancelamento: Voltando ao submenu de Origens.")
        teclado_origens = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="➕ Adicionar Canal"), KeyboardButton(text="🗑️ Remover Canal")],
                [KeyboardButton(text="📜 Listar Todos"), KeyboardButton(text="⚠️ Duplicados")],
                [KeyboardButton(text="🔙 Voltar ao Menu de Edição")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        await message.answer("Ação cancelada. O que você deseja fazer com os canais vigiados desta rota?", reply_markup=teclado_origens)
        await state.set_state(EspelhadorFluxo.aguardando_acao_origem)
        return

    # --- NÍVEL 2: Submenu de Edição da Rota (Volta para os botões de configuração) ---
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
    cache_nomes = ler_cache_nomes_grupos()  # 🚀 Fallback
    
    texto = "🔄 <b>Painel do Espelhador de Canais</b>\n\n"
    texto += "Este módulo clona publicações de um grupo para outro automaticamente, convertendo os links e respeitando um atraso programado.\n\n"
    
    houve_alteracao = False # ✅ Prepara a variável para salvar o arquivo se houver correção

    if rotas:
        texto += "📡 <b>Rotas Ativas:</b>\n"
        for i, rota in enumerate(rotas, 1):
            nome_rota = rota.get('nome', f'Rota {i}')
            destino_rota = rota.get('destino', '')
            status_canais = rota.get("status_canais", {})
            
            # ✅ NOVO: Autocura Inteligente Definitiva (Lê a própria memória)
            if "Espelho: -100" in nome_rota or "Espelho: @" in nome_rota or "https://" in nome_rota:
                nome_real = None
                
                # 1. Tenta achar o nome salvo no próprio arquivo JSON (Aonde vimos que funciona!)
                info_d = status_canais.get(str(destino_rota), {})
                if isinstance(info_d, dict) and info_d.get("nome") and info_d.get("nome") != str(destino_rota):
                    nome_real = info_d.get("nome")
                    
                # 2. Se não achar, tenta no cache global
                elif str(destino_rota) in cache_nomes and cache_nomes[str(destino_rota)] != str(destino_rota):
                    nome_real = cache_nomes[str(destino_rota)]
                    
                # 3. Em último caso, tenta bater na API do Telegram
                if not nome_real:
                    try:
                        chat_obj = await message.bot.get_chat(destino_rota)
                        nome_real = chat_obj.title or chat_obj.full_name
                    except Exception:
                        pass
                        
                # Se achou o nome real em qualquer um dos 3 passos, conserta a rota
                if nome_real:
                    nome_rota = f"Espelho: {nome_real}"
                    rota['nome'] = nome_rota
                    houve_alteracao = True

            qtd_fila = ler_contador_espelhador(rota['nome'])
            
            texto += f"<b>{i}. {nome_rota}</b>\n"
            texto += f"   🕒 Janela de Postagem: {rota.get('inicio', 10)}h às {rota.get('fim', 22)}h\n"
            texto += f"   🔀 Distribuição: {rota.get('modo', 'ordem').title()}\n"
            texto += f"   📦 Fila de Espera: {qtd_fila} vídeo(s)\n"
            texto += "\n"
            
            # --- 1. DESTINO MOSTRADO PRIMEIRO ---
            info_d = status_canais.get(str(destino_rota), {})
            if isinstance(info_d, str): info_d = {"status": info_d, "nome": str(destino_rota)}
            
            status_destino_ico = "❌" if info_d.get("status") == "erro" else "✅"
            nome_d = info_d.get("nome") or cache_nomes.get(str(destino_rota), str(destino_rota))
            display_d = f"{nome_d} (<code>{destino_rota}</code>)" if nome_d != str(destino_rota) else f"<code>{destino_rota}</code>"
            
            texto += f"🎯 <b>Canal de Destino:</b> {status_destino_ico} {display_d}\n\n"

            # --- 2. ORIGENS MOSTRADAS LOGO ABAIXO ---
            origens = rota.get('origens', [])
            if not origens and 'origem' in rota:
                origens = [rota['origem']]
                
            texto += f"📥 <b>Na escuta ({len(origens)}):</b>\n"
            
            linhas_origem = []
            for idx, o in enumerate(origens):
                info_o = status_canais.get(str(o), {})
                if isinstance(info_o, str): info_o = {"status": info_o, "nome": str(o)}
                
                status_ico = "❌" if info_o.get("status") == "erro" else "✅"
                nome_o = info_o.get("nome") or cache_nomes.get(str(o), str(o))
                display_o = f"{nome_o} (<code>{o}</code>)" if nome_o != str(o) else f"<code>{o}</code>"
                
                linhas_origem.append({
                    "texto": f"<code>{idx + 1:02d}.</code> {status_ico} {display_o}\n",
                    "tem_erro": status_ico == "❌"
                })

            total_origens = len(linhas_origem)
            
            # Lógica de Ocultação Inteligente (Muralha Anti-Crash)
            if total_origens <= 15:
                for linha in linhas_origem:
                    texto += linha["texto"]
            else:
                # Mostra os 5 primeiros
                for idx in range(5):
                    texto += linhas_origem[idx]["texto"]

                ocultos_ok = 0
                # Varre o meio da lista ocultando os OKs e exibindo apenas os ERROS
                for idx in range(5, total_origens - 5):
                    if linhas_origem[idx]["tem_erro"]:
                        if ocultos_ok > 0:
                            texto += f"   <i>... e mais {ocultos_ok} canais operando normalmente ...</i>\n"
                            ocultos_ok = 0
                        texto += linhas_origem[idx]["texto"]
                    else:
                        ocultos_ok += 1

                if ocultos_ok > 0:
                    texto += f"   <i>... e mais {ocultos_ok} canais operando normalmente ...</i>\n"

                # Mostra os 5 últimos
                for idx in range(total_origens - 5, total_origens):
                    texto += linhas_origem[idx]["texto"]
        
        # 👇 FORA DO LAÇO 'for'
        texto += "\nEscolha a ação que deseja realizar:"
            
        # ✅ NOVO: Salva as alterações no banco de dados se a autocura rodou
        if houve_alteracao:
            dados["rotas"] = rotas
            salvar_espelhos(dados)
            
    else:
        texto += "<i>Nenhuma rota de espelhamento cadastrada no momento.</i>\n\n"
        
    await message.answer(texto, reply_markup=teclado_espelhador_menu, parse_mode="HTML")
    await state.set_state(EspelhadorFluxo.menu_principal)

@router.message(EspelhadorFluxo.menu_principal, F.text == "Adicionar Espelho ➕")
async def iniciar_cadastro_rota(message: types.Message, state: FSMContext):
    if EXIBIR_LOGS: logger.info("🚀 Iniciando fluxo de cadastro de espelho (Passo 1: Destino)...")
    await message.answer(
        "Para começar, envie o <b>ID Numérico, Link ou @username</b> do Canal de DESTINO (Para onde o robô vai enviar as cópias):\n"
        "<i>Exemplo: -100123456789 ou https://t.me/meucanal</i>", 
        reply_markup=teclado_espelhador_cancelar, 
        parse_mode="HTML"
    )
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
            "OBS: Você pode enviar vários separando por vírgula (Ex: <code>@grupo1, -100123, https://t.me/grupo2</code>):"
        )
        await message.answer(texto_origens, reply_markup=obter_teclado_importacao_espelhador(), parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_origem_criacao)
    else:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Falha na validação do destino: {message.text}")
        await message.answer("⚠️ <b>Canal não encontrado ou sem permissão!</b>\nCertifique-se de que o ID ou @username está correto e de que o bot é administrador do canal.\n\nTente enviar novamente:", reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")

@router.message(EspelhadorFluxo.aguardando_origem_criacao)
async def receber_origem_criacao(message: types.Message, state: FSMContext):
    texto = message.text
    is_importacao_global = texto == "Importar Banco Global 🌍"
    
    if is_importacao_global:
        msg_status = await message.answer("⏳ <b>Importando Banco Global...</b>", parse_mode="HTML", reply_markup=teclado_espelhador_cancelar)
        from utils import obter_banco_global_origens
        entradas_brutas = obter_banco_global_origens()
        if not entradas_brutas:
            await msg_status.delete()
            await message.answer("⚠️ O Banco Global está vazio.")
            return
    else:
        import re
        padroes = re.findall(r'(-100\d+(?::\d+)?|@\w+|https?://t\.me/[^\s\)]+)', texto)
        if padroes: entradas_brutas = list(dict.fromkeys(padroes))
        else: entradas_brutas = texto.replace('\n', ',').split(',')
        msg_status = await message.answer("⏳ Validando lote de canais de origem e subgrupos...", reply_markup=teclado_espelhador_cancelar)
    
    data = await state.get_data()
    destino_atual = str(data.get("destino", ""))
    
    origens_validas = []
    origens_duplicadas = []
    origens_invalidas = []
    origens_em_loop = [] 
    
    for entrada in entradas_brutas:
        entrada_limpa = entrada.strip()
        if not entrada_limpa: continue
        
        # Pula a rede se vier do Banco Global
        if is_importacao_global:
            sucesso = True
            id_final = entrada_limpa
            nome = entrada_limpa
        else:
            sucesso, id_final, nome = await validar_e_formatar_alvo(bot_instance, entrada_limpa)
        
        if sucesso:
            id_base = id_final.replace("-100", "")
            if destino_atual and id_base == destino_atual.replace("-100", ""):
                origens_em_loop.append(entrada_limpa)
            elif id_final in [o['id'] for o in origens_validas]:
                origens_duplicadas.append(entrada_limpa)
            else:
                if not is_importacao_global:
                    salvar_nome_grupo(id_final, nome)
                origens_validas.append({"id": id_final, "nome": nome})
        else:
            origens_invalidas.append(entrada_limpa)

    await msg_status.delete()
    texto_resposta = ""

    if origens_validas:
        texto_resposta += f"✅ <b>{len(origens_validas)} Origem(ns) validada(s):</b>\n"
        for o in origens_validas[:15]:
            texto_resposta += f"🔹 <code>{o['id']}</code>\n"
        if len(origens_validas) > 15:
            texto_resposta += f"<i>... e mais {len(origens_validas) - 15} canais.</i>\n"
        texto_resposta += "\n"

    if origens_em_loop:
        texto_resposta += f"🛑 <b>{len(origens_em_loop)} bloqueada(s) por Anti-Loop:</b>\n"
        for loop in origens_em_loop[:10]:
            texto_resposta += f"🔻 <code>{loop}</code>\n"
        if len(origens_em_loop) > 10:
            texto_resposta += f"<i>... e mais {len(origens_em_loop) - 10} canais.</i>\n"
        texto_resposta += "\n"

    if origens_duplicadas:
        texto_resposta += f"ℹ️ <b>{len(origens_duplicadas)} repetida(s) no envio:</b>\n"
        for dup in origens_duplicadas[:10]:
            texto_resposta += f"🔸 <code>{dup}</code>\n"
        if len(origens_duplicadas) > 10:
            texto_resposta += f"<i>... e mais {len(origens_duplicadas) - 10} canais.</i>\n"
        texto_resposta += "\n"

    if origens_invalidas:
        texto_resposta += f"❌ <b>{len(origens_invalidas)} falharam (Formato inválido/Link Privado):</b>\n"
        for rej in origens_invalidas[:10]:
            texto_resposta += f"🔻 <code>{rej}</code>\n"
        if len(origens_invalidas) > 10:
            texto_resposta += f"<i>... e mais {len(origens_invalidas) - 10} canais.</i>\n"
        texto_resposta += "\n"
    
    if origens_validas:
        await state.update_data(origens=origens_validas)
        texto_resposta += "Excelente. Agora defina a <b>Janela de Horário</b> para a postagem.\nEnvie no formato <code>Inicio-Fim</code> (Exemplo: <code>10-22</code>) ou clique no botão abaixo para rodar 24h:"
        await message.answer(texto_resposta, reply_markup=teclado_espelhador_janela, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_janela)
    else:
        if EXIBIR_LOGS: logger.warning("❌ Nenhuma origem válida encontrada no lote.")
        texto_resposta += "⚠️ <b>Nenhum canal válido aprovado!</b>\nCertifique-se de que os IDs não são links de convite privados ou iguais ao destino.\n\nTente enviar novamente:"
        await message.answer(texto_resposta, reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")


@router.message(EspelhadorFluxo.aguardando_nova_origem)
async def confirmar_nova_origem(message: types.Message, state: FSMContext):
    texto = message.text
    data = await state.get_data()
    indice = data.get("indice_edicao")
    dados = ler_espelhos()
    rota_atual = dados["rotas"][indice]
    
    if texto == "Lista Negra (Blacklist) ⛔":
        bl = rota_atual.get("blacklist", [])
        txt = f"⛔ <b>Lista Negra da Rota '{rota_atual['nome']}'</b>\n"
        if bl:
            for i, b in enumerate(bl, 1): txt += f"{i}. <code>{b}</code>\n"
        else: txt += "<i>Nenhuma restrição cadastrada.</i>\n"
        tcl = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="➕ Add à Blacklist"), KeyboardButton(text="🗑️ Rem. da Blacklist")], [KeyboardButton(text="Cancelar Operação ❌")]], resize_keyboard=True)
        await message.answer(txt, reply_markup=tcl, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_acao_blacklist)
        return
        
    origens_atuais = rota_atual.get('origens', [])
    if not origens_atuais and 'origem' in rota_atual: origens_atuais = [rota_atual['origem']]
    destino_atual = str(rota_atual.get("destino", ""))
    blacklist = [str(b) for b in rota_atual.get("blacklist", [])]
    
    is_importacao_global = texto == "Importar Banco Global 🌍"
    
    if is_importacao_global:
        msg_status = await message.answer("⏳ <b>Importando e cruzando Banco Global com a Lista Negra da rota...</b>", parse_mode="HTML", reply_markup=teclado_espelhador_cancelar)
        from utils import obter_banco_global_origens
        entradas_brutas = obter_banco_global_origens()
        if not entradas_brutas:
            await msg_status.delete()
            await message.answer("⚠️ Banco Global vazio.")
            return
    else:
        import re
        padroes = re.findall(r'(-100\d+(?::\d+)?|@\w+|https?://t\.me/[^\s\)]+)', texto)
        if padroes: entradas_brutas = list(dict.fromkeys(padroes))
        else: entradas_brutas = texto.replace('\n', ',').split(',')
        msg_status = await message.answer("⏳ Validando grupos...", reply_markup=teclado_espelhador_cancelar)

    origens_validas = []
    origens_duplicadas = []
    origens_invalidas = []
    origens_em_loop = [] 

    for entrada in entradas_brutas:
        entrada_limpa = entrada.strip()
        if not entrada_limpa: continue
        
        if is_importacao_global:
            sucesso = True
            id_final = entrada_limpa
            nome = entrada_limpa
        else:
            sucesso, id_final, nome = await validar_e_formatar_alvo(bot_instance, entrada_limpa)
            
        if sucesso:
            id_base = id_final.replace("-100", "")
            
            if id_final in blacklist or id_base in [b.replace("-100", "") for b in blacklist]:
                origens_invalidas.append(f"{entrada_limpa} (Blacklist ⛔)")
            elif destino_atual and id_base == destino_atual.replace("-100", ""):
                origens_em_loop.append(entrada_limpa)
            elif id_final in origens_atuais or id_final in [o['id'] for o in origens_validas]:
                origens_duplicadas.append(entrada_limpa)
            else:
                if not is_importacao_global:
                    salvar_nome_grupo(id_final, nome)
                origens_validas.append({"id": id_final, "nome": nome})
        else:
            origens_invalidas.append(entrada_limpa)

    await msg_status.delete()
    texto_resumo = ""

    if origens_validas:
        texto_resumo += f"✅ <b>{len(origens_validas)} NOVO(S) canal(is) validado(s):</b>\n"
        for o in origens_validas[:15]:
            texto_resumo += f"🔹 {o['nome']} (<code>{o['id']}</code>)\n"
        if len(origens_validas) > 15:
            texto_resumo += f"<i>... e mais {len(origens_validas) - 15} canais.</i>\n"
        texto_resumo += "\n"

    if origens_em_loop:
        texto_resumo += f"🛑 <b>{len(origens_em_loop)} bloqueada(s) por Anti-Loop:</b>\n"
        for loop in origens_em_loop[:10]:
            texto_resumo += f"🔻 <code>{loop}</code>\n"
        if len(origens_em_loop) > 10:
            texto_resumo += f"<i>... e mais {len(origens_em_loop) - 10} canais.</i>\n"
        texto_resumo += "\n"

    if origens_duplicadas:
        texto_resumo += f"ℹ️ <b>{len(origens_duplicadas)} ignorado(s) por já estarem na rota:</b>\n"
        for dup in origens_duplicadas[:10]:
            texto_resumo += f"🔸 <code>{dup}</code>\n"
        if len(origens_duplicadas) > 10:
            texto_resumo += f"<i>... e mais {len(origens_duplicadas) - 10} canais.</i>\n"
        texto_resumo += "\n"

    if origens_invalidas:
        texto_resumo += f"❌ <b>{len(origens_invalidas)} falharam (Formato inválido/Blacklist):</b>\n"
        for rej in origens_invalidas[:10]:
            texto_resumo += f"🔻 <code>{rej}</code>\n"
        if len(origens_invalidas) > 10:
            texto_resumo += f"<i>... e mais {len(origens_invalidas) - 10} canais.</i>\n"
        texto_resumo += "\n"

    if not origens_validas:
        texto_resumo += "⚠️ <b>Nenhum canal novo foi aprovado.</b> Tente novamente:"
        await message.answer(texto_resumo, reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
        return

    await state.update_data(origens_para_adicionar=origens_validas)
    
    if len(dados.get("rotas", [])) > 1:
        texto_resumo += f"O seu sistema possui <b>{len(dados['rotas'])} rotas ativas</b>. Onde deseja adicionar?"
        await message.answer(texto_resumo, reply_markup=teclado_espelhador_abrangencia, parse_mode="HTML")
    else:
        texto_resumo += f"Deseja adicionar à rota <b>{rota_atual['nome']}</b>?"
        await message.answer(texto_resumo, reply_markup=teclado_espelhador_confirmacao, parse_mode="HTML")
    
    await state.set_state(EspelhadorFluxo.aguardando_confirmacao_nova_origem)

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
    
    # ✅ NOVO: Pula a pergunta de Modo se for D+0 e salva direto como "ordem"
    if intervalo == 0:
        if EXIBIR_LOGS: logger.info("⏭️ Atalho UX acionado: D+0 forçando modo 'Ordem de Chegada'.")
        msg_simulada = message.model_copy(update={"text": "Ordem de Chegada ⬇️"})
        await receber_modo_rota(msg_simulada, state)
        return
        
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
    
    # 🧹 CÓDIGO OTIMIZADO: Removida a redundância de busca de nomes aqui
    for i, rota in enumerate(rotas, 1):
        nome_exibicao = rota.get('nome', f'Rota {i}')
        qtd_origens = len(rota.get('origens', [rota.get('origem')]))
        texto += f"{i}. {nome_exibicao} ({qtd_origens} canais vigiados agrupados)\n"
        
    await message.answer(texto, reply_markup=teclado_espelhador_voltar, parse_mode="HTML")
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
    
    # 🧹 CÓDIGO OTIMIZADO: Removida a redundância de busca de nomes aqui
    for i, rota in enumerate(rotas, 1):
        nome_exibicao = rota.get('nome', f'Rota {i}')
        texto += f"{i}. {nome_exibicao}\n"
        
    await message.answer(texto, reply_markup=teclado_espelhador_voltar, parse_mode="HTML")
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

        # --- 1. DESTINO MOSTRADO PRIMEIRO NO MODO DE EDIÇÃO ---
        destino_rota = rota_alvo.get('destino')
        info_d = status_canais.get(str(destino_rota), {})
        if isinstance(info_d, str): info_d = {"status": info_d, "nome": str(destino_rota)}
        
        status_destino_ico = "❌" if info_d.get("status") == "erro" else "✅"
        nome_d = info_d.get("nome") or cache_nomes.get(str(destino_rota), str(destino_rota))
        display_d = f"{nome_d} (<code>{destino_rota}</code>)" if nome_d != str(destino_rota) else f"<code>{destino_rota}</code>"
        
        texto += f"\n🎯 <b>Canal de Destino:</b> {status_destino_ico} {display_d}\n\n"

        # --- 2. ORIGENS MOSTRADAS LOGO ABAIXO ---
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
            texto += f"<code>{idx + 1:02d}.</code> {status_ico} {display_o}\n"
        
        texto += "\nEscolha a ação que deseja realizar:"
        
        # ✅ Menu limpo sem Blacklist (Foi para dentro de Canais Vigiados)
        teclado_submenu = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📝 Editar Nome"), KeyboardButton(text="🔀 Modificar Modo")],
                [KeyboardButton(text="🎯 Editar Destino"), KeyboardButton(text="📥 Canais Vigiados")],
                [KeyboardButton(text="🕒 Modificar Janela"), KeyboardButton(text="📅 Modificar Dias")],
                [KeyboardButton(text="Voltar ao Menu Espelho 🔙")]
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
        await message.answer(
            "Envie o <b>ID Numérico, Link ou @username</b> do NOVO Canal de DESTINO para esta rota:\n"
            "<i>Exemplo: -100123456789 ou https://t.me/meucanal</i>", 
            reply_markup=teclado_espelhador_cancelar, 
            parse_mode="HTML"
        )
        await state.set_state(EspelhadorFluxo.aguardando_edicao_novo_destino)
    elif texto == "🕒 Modificar Janela":
        await message.answer(
            "Defina a <b>Nova Janela de Horário</b> para a postagem nesta rota.\n"
            "Envie no formato <code>Inicio-Fim</code> (Exemplo: <code>10-22</code>) ou clique no botão abaixo para rodar 24h:", 
            reply_markup=teclado_espelhador_janela, 
            parse_mode="HTML"
        )
        await state.set_state(EspelhadorFluxo.aguardando_edicao_nova_janela)
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
        teclado_origens = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="➕ Adicionar Canal"), KeyboardButton(text="🗑️ Remover Canal")],
                [KeyboardButton(text="📜 Listar Todos"), KeyboardButton(text="⚠️ Duplicados")],
                [KeyboardButton(text="🔙 Voltar ao Menu de Edição")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        await message.answer("O que você deseja fazer com os canais monitorados desta rota?", reply_markup=teclado_origens)
        await state.set_state(EspelhadorFluxo.aguardando_acao_origem)
    else:
        await message.answer("Use os botões do menu para escolher a ação.")

# ✅ NOVA FUNÇÃO PARA PROCESSAR O SUBMENU
@router.message(EspelhadorFluxo.aguardando_acao_origem)
async def processar_acao_origem(message: types.Message, state: FSMContext):
    texto = message.text
    if texto == "➕ Adicionar Canal":
        teclado_dinamico = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Importar Banco Global 🌍")], 
                [KeyboardButton(text="Lista Negra (Blacklist) ⛔")],
                [KeyboardButton(text="Cancelar Operação ❌")]
            ], 
            resize_keyboard=True, 
            is_persistent=True
        )
        await message.answer(
            "Envie os @usernames, links ou IDs dos grupos que deseja monitorar como ORIGEM.\n"
            "OBS: Você pode enviar vários separando por vírgula (Ex: @grupo1, -100123, https://t.me/grupo2):\n\n"
            "<blockquote>💡 <b>Dica:</b> Você pode colar uma lista ou clicar no botão abaixo para puxar o <b>Banco Global</b> (o robô ignorará os grupos duplicados e os da Lista Negra automaticamente).</blockquote>", 
            reply_markup=teclado_dinamico, 
            parse_mode="HTML"
        )
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

    elif texto == "📜 Listar Todos":
        data = await state.get_data()
        indice = data.get("indice_edicao")
        rotas = ler_espelhos().get("rotas", [])
        rota = rotas[indice]
        origens = rota.get('origens', [])
        if not origens and 'origem' in rota: origens = [rota['origem']]
        
        if not origens:
            await message.answer("Esta rota não possui canais vigiados.")
            return
            
        cache_nomes = ler_cache_nomes_grupos()
        status_canais = rota.get("status_canais", {})
        
        texto_lista = f"📜 <b>Lista Completa de Canais Vigiados: {rota['nome']}</b>\n\n"
        mensagens = []
        
        for i, o in enumerate(origens, 1):
            info = status_canais.get(str(o), {})
            if isinstance(info, str): info = {"status": info, "nome": str(o)}
            
            # Puxa o status para definir o ícone (✅ ou ❌)
            status_ico = "❌" if info.get("status") == "erro" else "✅"
            
            nome = info.get("nome") or cache_nomes.get(str(o), str(o))
            linha = f"<b>{i}.</b> {status_ico} {nome} (<code>{o}</code>)\n"
            
            if len(texto_lista) + len(linha) > 3800:
                mensagens.append(texto_lista)
                texto_lista = ""
            texto_lista += linha
            
        mensagens.append(texto_lista)
        
        for msg in mensagens:
            await message.answer(msg, parse_mode="HTML")

    elif texto == "⚠️ Duplicados":
        data = await state.get_data()
        indice = data.get("indice_edicao")
        rotas = ler_espelhos().get("rotas", [])
        rota = rotas[indice]
        origens = rota.get('origens', [])
        if not origens and 'origem' in rota: origens = [rota['origem']]
        
        if len(origens) < 2:
            await message.answer("Não há canais suficientes nesta rota para procurar duplicados.")
            return
            
        msg_status = await message.answer("⏳ Analisando a lista em busca de duplicados...")
        
        cache_nomes = ler_cache_nomes_grupos()
        status_canais = rota.get("status_canais", {})
        
        lista_analise = []
        # Usar enumerate(origens, 1) para guardar a posição real do canal na lista de remoção
        for index, o in enumerate(origens, 1):
            alvo_str = str(o)
            info = status_canais.get(alvo_str, {})
            if isinstance(info, str): info = {"status": info, "nome": alvo_str}
            nome = info.get("nome") or cache_nomes.get(alvo_str, alvo_str)
            
            # Puxa o status para definir o ícone (✅ ou ❌)
            status_ico = "❌" if info.get("status") == "erro" else "✅"
            
            is_num = alvo_str.lstrip("-").replace(":", "").isdigit()
            base_id = alvo_str.split(":")[0].replace("-100", "").replace("-", "") if is_num else alvo_str.split(":")[0]
            topic = alvo_str.split(":")[1] if ":" in alvo_str else "0"
            
            lista_analise.append({
                "index": index,
                "original": alvo_str,
                "nome": nome,
                "is_num": is_num,
                "base_id": base_id,
                "topic": topic,
                "status_ico": status_ico
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
            await message.answer("✅ <b>Tudo limpo!</b>\nO sistema não detectou nenhum canal duplicado nesta rota.", parse_mode="HTML")
            return
            
        texto_resp = "⚠️ <b>Aviso: Possíveis Duplicados Detectados</b>\n\n"
        for A, B, motivo in duplicados:
            texto_resp += f"🔹 <b>{A['nome']}</b>\n"
            texto_resp += f"   ├ <b>{A['index']}.</b> {A['status_ico']} <code>{A['original']}</code>\n"
            texto_resp += f"   └ <b>{B['index']}.</b> {B['status_ico']} <code>{B['original']}</code>\n"
            texto_resp += f"   <i>(Motivo: {motivo})</i>\n\n"
            
        texto_resp += "💡 <i>Dica: Se um deles for um duplicado indesejado, vá em 'Remover Canal' e exclua um dos IDs.</i>"
        await message.answer(texto_resp, parse_mode="HTML")
        
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
    texto = message.text.strip()
    
    # ✅ Identifica o clique no botão ou se foi digitado manualmente
    if texto == "Dia Todo (24h) 🕛" or texto.lower() == "dia todo":
        inicio = 0
        fim = 24
        if EXIBIR_LOGS: logger.info("🕛 Janela de edição configurada para Dia Todo (24h).")
    else:
        match = re.match(r"^(\d{1,2})-(\d{1,2})$", texto)
        if not match:
            await message.answer("Formato inválido! Use o formato exato como no exemplo: 10-22, ou clique em 'Dia Todo (24h) 🕛'.", reply_markup=teclado_espelhador_janela)
            return
            
        inicio, fim = map(int, match.groups())
        if inicio >= fim or inicio < 0 or fim > 24:
            await message.answer("Valores inválidos! A hora de início deve ser menor que a do fim.", reply_markup=teclado_espelhador_janela)
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
    
    # ✅ Mensagem dinâmica adaptada para o que o usuário escolheu
    texto_exibicao = "24 horas por dia" if inicio == 0 and fim == 24 else f"entre as {inicio}h e as {fim}h"
    await message.answer(f"✅ A janela foi atualizada para postar {texto_exibicao} com sucesso!", parse_mode="HTML")
    
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
    
    # ✅ NOVO: Se o usuário mudar para D+0, o robô força automaticamente o modo para "ordem"
    if intervalo == 0:
        rotas[indice]["modo"] = "ordem"
        if EXIBIR_LOGS: logger.info(f"🔄 Modo da rota '{rotas[indice]['nome']}' forçado para 'ordem' devido ao D+0.")
        
    dados["rotas"] = rotas
    salvar_espelhos(dados)
    
    try:
        fila_dados = ler_fila_espelhador()
        houve_reset = False
        for item in fila_dados.get("fila", []):
            if item.get("nome_rota") == rotas[indice]["nome"] and not item.get("processado"):
                item["horario_disparo"] = "" 
                houve_reset = True
        if houve_reset:
            salvar_fila_espelhador(fila_dados)
            if EXIBIR_LOGS: logger.info(f"🔄 Fila da rota '{rotas[indice]['nome']}' resetada para recálculo orgânico.")
    except Exception as e:
        pass
    
    if EXIBIR_LOGS: logger.info(f"✏️ Atraso dinâmico da rota '{rotas[indice]['nome']}' modificado para D+{intervalo}.")
    
    # ✅ Aviso dinâmico informando a mudança automática do modo
    aviso_extra = "\n⚠️ <b>Nota:</b> O modo de distribuição foi automaticamente alterado para <i>Ordem de Chegada</i> para garantir a postagem imediata no mesmo dia." if intervalo == 0 else ""
    await message.answer(f"✅ O intervalo temporal foi atualizado para D+{intervalo}!{aviso_extra}\nO Motor Central já está a recalcular os horários de forma orgânica e respeitando a janela.", parse_mode="HTML")
    
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
    texto = message.text
    data = await state.get_data()
    indice = data.get("indice_edicao")
    dados = ler_espelhos()
    rota_atual = dados["rotas"][indice]
    
    # 🎯 NOVA REDIREÇÃO DA BLACKLIST
    if texto == "Lista Negra (Blacklist) ⛔":
        bl = rota_atual.get("blacklist", [])
        txt = f"⛔ <b>Lista Negra da Rota '{rota_atual['nome']}'</b>\n"
        if bl:
            for i, b in enumerate(bl, 1): txt += f"{i}. <code>{b}</code>\n"
        else: txt += "<i>Nenhuma restrição cadastrada.</i>\n"
        tcl = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="➕ Add à Blacklist"), KeyboardButton(text="🗑️ Rem. da Blacklist")], [KeyboardButton(text="Cancelar Operação ❌")]], resize_keyboard=True)
        await message.answer(txt, reply_markup=tcl, parse_mode="HTML")
        await state.set_state(EspelhadorFluxo.aguardando_acao_blacklist)
        return
        
    origens_atuais = rota_atual.get('origens', [])
    if not origens_atuais and 'origem' in rota_atual: origens_atuais = [rota_atual['origem']]
    destino_atual = str(rota_atual.get("destino", ""))
    blacklist = [str(b) for b in rota_atual.get("blacklist", [])]
    
    if texto == "Importar Banco Global 🌍":
        msg_status = await message.answer("⏳ <b>Importando e cruzando Banco Global com a Lista Negra da rota...</b>", parse_mode="HTML", reply_markup=teclado_espelhador_cancelar)
        from utils import obter_banco_global_origens
        entradas_brutas = obter_banco_global_origens()
        if not entradas_brutas:
            await msg_status.delete()
            await message.answer("⚠️ Banco Global vazio.")
            return
    else:
        import re
        padroes = re.findall(r'(-100\d+(?::\d+)?|@\w+|https?://t\.me/[^\s\)]+)', texto)
        if padroes: entradas_brutas = list(dict.fromkeys(padroes))
        else: entradas_brutas = texto.replace('\n', ',').split(',')
        msg_status = await message.answer("⏳ Validando grupos...", reply_markup=teclado_espelhador_cancelar)

    origens_validas = []
    origens_duplicadas = []
    origens_invalidas = []
    origens_em_loop = [] 

    for entrada in entradas_brutas:
        entrada_limpa = entrada.strip()
        if not entrada_limpa: continue
        
        sucesso, id_final, nome = await validar_e_formatar_alvo(bot_instance, entrada_limpa)
        
        if sucesso:
            id_base = id_final.replace("-100", "")
            
            # ⛔ Verifica Blacklist
            if id_final in blacklist or id_base in [b.replace("-100", "") for b in blacklist]:
                origens_invalidas.append(f"{entrada_limpa} (Blacklist ⛔)")
            # 🛑 Trava Anti-Loop
            elif destino_atual and id_base == destino_atual.replace("-100", ""):
                origens_em_loop.append(entrada_limpa)
            # ℹ️ Verifica Duplicidade
            elif id_final in origens_atuais or id_final in [o['id'] for o in origens_validas]:
                origens_duplicadas.append(entrada_limpa)
            # ✅ Adiciona nova origem válida
            else:
                salvar_nome_grupo(id_final, nome)
                origens_validas.append({"id": id_final, "nome": nome})
        else:
            origens_invalidas.append(entrada_limpa)

    await msg_status.delete()

    # 5. Restauro do texto original conforme pedido
    texto_resumo = ""

    if origens_validas:
        texto_resumo += f"✅ <b>{len(origens_validas)} NOVO(S) canal(is) validado(s):</b>\n"
        for o in origens_validas:
            texto_resumo += f"🔹 {o['nome']} (<code>{o['id']}</code>)\n"
        texto_resumo += "\n"

    if origens_em_loop:
        texto_resumo += f"🛑 <b>{len(origens_em_loop)} bloqueada(s) por Anti-Loop (É o destino desta rota):</b>\n"
        for loop in origens_em_loop:
            texto_resumo += f"🔻 <code>{loop}</code>\n"
        texto_resumo += "\n"

    if origens_duplicadas:
        texto_resumo += f"ℹ️ <b>{len(origens_duplicadas)} ignorado(s) por já estarem na rota (Duplicados):</b>\n"
        for dup in origens_duplicadas:
            texto_resumo += f"🔸 <code>{dup}</code>\n"
        texto_resumo += "\n"

    if origens_invalidas:
        texto_resumo += f"❌ <b>{len(origens_invalidas)} falharam (Formato inválido ou link Privado):</b>\n"
        for rej in origens_invalidas:
            texto_resumo += f"🔻 <code>{rej}</code>\n"
        texto_resumo += "\n"

    if not origens_validas:
        texto_resumo += "⚠️ <b>Nenhum canal novo foi aprovado.</b> Tente novamente:"
        await message.answer(texto_resumo, reply_markup=teclado_espelhador_cancelar, parse_mode="HTML")
        return

    await state.update_data(origens_para_adicionar=origens_validas)
    
    if len(dados.get("rotas", [])) > 1:
        texto_resumo += f"O seu sistema possui <b>{len(dados['rotas'])} rotas ativas</b>. Onde deseja adicionar?"
        await message.answer(texto_resumo, reply_markup=teclado_espelhador_abrangencia, parse_mode="HTML")
    else:
        texto_resumo += f"Deseja adicionar à rota <b>{rota_atual['nome']}</b>?"
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

@router.message(EspelhadorFluxo.aguardando_acao_blacklist)
async def acao_bl_espelhador(message: types.Message, state: FSMContext):
    if message.text == "➕ Add à Blacklist":
        await message.answer("Envie o(s) ID(s) para BLOQUEAR NESTA ROTA (separados por vírgula):", reply_markup=teclado_espelhador_cancelar)
        await state.set_state(EspelhadorFluxo.aguardando_blacklist_add)
    elif message.text == "🗑️ Rem. da Blacklist":
        await message.answer("Envie os IDs para LIBERAR NESTA ROTA (separados por vírgula):", reply_markup=teclado_espelhador_cancelar)
        await state.set_state(EspelhadorFluxo.aguardando_blacklist_remove)

@router.message(EspelhadorFluxo.aguardando_blacklist_add)
async def salvar_bl_add_espelhador(message: types.Message, state: FSMContext):
    novos = [s.strip() for s in message.text.split(",")]
    data = await state.get_data()
    idx = data.get("indice_edicao")
    dados = ler_espelhos()
    bl = dados["rotas"][idx].get("blacklist", [])
    for n in novos:
        if n and n not in bl: bl.append(n)
    dados["rotas"][idx]["blacklist"] = bl
    salvar_espelhos(dados)
    
    teclado_origens = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Adicionar Canal"), KeyboardButton(text="🗑️ Remover Canal")],
            [KeyboardButton(text="📜 Listar Todos"), KeyboardButton(text="⚠️ Duplicados")],
            [KeyboardButton(text="🔙 Voltar ao Menu de Edição")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer("✅ Blacklist da rota atualizada!", reply_markup=teclado_origens)
    await state.set_state(EspelhadorFluxo.aguardando_acao_origem)

@router.message(EspelhadorFluxo.aguardando_blacklist_remove)
async def salvar_bl_rem_espelhador(message: types.Message, state: FSMContext):
    remover = [s.strip() for s in message.text.split(",")]
    data = await state.get_data()
    idx = data.get("indice_edicao")
    dados = ler_espelhos()
    bl = dados["rotas"][idx].get("blacklist", [])
    dados["rotas"][idx]["blacklist"] = [b for b in bl if b not in remover]
    salvar_espelhos(dados)
    
    teclado_origens = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Adicionar Canal"), KeyboardButton(text="🗑️ Remover Canal")],
            [KeyboardButton(text="📜 Listar Todos"), KeyboardButton(text="⚠️ Duplicados")],
            [KeyboardButton(text="🔙 Voltar ao Menu de Edição")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer("✅ Blacklist da rota atualizada!", reply_markup=teclado_origens)
    await state.set_state(EspelhadorFluxo.aguardando_acao_origem)
