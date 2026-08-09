EXIBIR_LOGS = True
FILTRO_ANTI_DUPLICIDADE = True  # Mude para False para ignorar o histórico e enviar notas repetidas
import os
import zipfile
import pandas as pd
import asyncio
import aiohttp
import sqlite3
import base64
import logging
import shutil
import unicodedata
import re
import difflib
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Router, Bot, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import StateFilter

load_dotenv()

# ==========================================
# CONFIGURAÇÕES E CHAVES
# ==========================================
BREVO_API_KEY = os.getenv('BREVO_API_KEY')
EMAIL_REMETENTE = os.getenv('EMAIL_REMETENTE_NOTAS')
NOME_REMETENTE = os.getenv('NOME_REMETENTE_NOTAS')
EMAIL_ADMIN = 'rafaelnovaismiranda@gmail.com'

LIMITE_DIARIO = 290
PAUSA_HORAS = 26

if EXIBIR_LOGS:
    logger = logging.getLogger("PainelNotas")

router = Router()
bot_instance = None
scheduler_instance = None

def configurar_dependencias(bot: Bot, scheduler):
    global bot_instance, scheduler_instance
    bot_instance = bot
    scheduler_instance = scheduler
    if EXIBIR_LOGS: logger.info("🔌 Conexão estabelecida: Dependências do Disparador de Notas injetadas com sucesso.")

class PainelNotasFluxo(StatesGroup):
    menu_principal = State()
    aguardando_csv = State()
    aguardando_zip = State()
    revisando_similares = State()
    pareamento_manual = State()
    inspecionando_pdf_manual = State()  
    aguardando_aprovacao = State()
    inspecionando_pdf_final = State()   
    enviando_notas = State() # 🛡️ NOVO: Estado de bloqueio total

def obter_teclado_menu_notas():
    status_filtro = "LIGADO 🟢" if FILTRO_ANTI_DUPLICIDADE else "DESLIGADO 🔴"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Iniciar Envios 🚀")],
            [KeyboardButton(text=f"Filtro Anti-Duplicidade: {status_filtro}")],
            [KeyboardButton(text="Informações de Acesso ℹ️")],
            [KeyboardButton(text="Voltar ↩️")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

teclado_notas_cancelar = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Abortar ❌")]],
    resize_keyboard=True,
    is_persistent=True
)

PASTA_TEMP = "temp/notas_fiscais"
os.makedirs(PASTA_TEMP, exist_ok=True)

def normalizar_texto(texto):
    if not isinstance(texto, str):
        return ""
    # Remove acentos
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    # Coloca em minúsculo
    texto = texto.lower()
    # Remove caracteres especiais (mantém apenas letras, números e espaços)
    texto = re.sub(r'[^a-z0-9\s]', ' ', texto)
    # Remove espaços duplos
    return re.sub(r'\s+', ' ', texto).strip()

# ==========================================
# INTEGRAÇÃO COM A API DO BREVO
# ==========================================
async def enviar_email_brevo(para_email, para_nome, assunto, corpo_html, caminho_anexo=None):
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY or "",
        "content-type": "application/json"
    }
    
    payload = {
        "sender": {"name": NOME_REMETENTE, "email": EMAIL_REMETENTE},
        "to": [{"email": para_email, "name": para_nome}],
        "subject": assunto,
        "htmlContent": corpo_html
    }
    
    if caminho_anexo and os.path.exists(caminho_anexo):
        with open(caminho_anexo, "rb") as f:
            dados_arquivo = f.read()
            conteudo_b64 = base64.b64encode(dados_arquivo).decode('utf-8')
            nome_arquivo = os.path.basename(caminho_anexo)
            payload["attachment"] = [{"content": conteudo_b64, "name": nome_arquivo}]
            
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resposta:
            texto_resposta = await resposta.text()
            return resposta.status, texto_resposta

async def processar_fila_envios(msg_progresso: types.Message = None):
    global bot_instance
    if EXIBIR_LOGS: logger.info("🚀 Iniciando esteira de disparos de notas fiscais...")
    
    conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
    conexao.row_factory = sqlite3.Row
    cursor = conexao.cursor()
    cursor.execute("SELECT * FROM fila_notas WHERE status = 'PENDENTE'")
    pendentes = cursor.fetchall()
    
    if not pendentes:
        conexao.close()
        return

    total_notas = len(pendentes)
    envios_realizados = 0
    erros = 0
    falhas_etapa = []
    
    pasta_extracao = None
    if pendentes:
        pasta_extracao = os.path.dirname(pendentes[0]["caminho_pdf"])
    
    for idx, item in enumerate(pendentes, 1):
        id_registro = item["id"]
        loja = item["nome_loja"]
        email = item["email_destino"]
        pdf = item["caminho_pdf"]
        
        valor = item["valor"] if "valor" in item.keys() and item["valor"] else "0,00"
        
        # 🔥 MÁGICA DA CONTAGEM DINÂMICA (Exatamente como no bot_mestre.py) 🔥
        if msg_progresso:
            try:
                loja_segura = str(loja).replace('<', '').replace('>', '') # Blindagem HTML
                status_dinamico = f"🚀 <i>Disparando notas fiscais...</i>\n⏳ Enviando nota ({idx}/{total_notas}): <code>{loja_segura}</code>"
                # Usa a edição direta do objeto da mensagem para driblar o bloqueio do Telegram
                await msg_progresso.edit_text(status_dinamico, parse_mode="HTML")
            except Exception as e:
                if EXIBIR_LOGS: logger.warning(f"⚠️ Erro ao atualizar interface do Telegram: {e}")
                pass

        if envios_realizados >= LIMITE_DIARIO:
            if EXIBIR_LOGS: logger.warning(f"⏳ Limite diário atingido. Programando retomada para {PAUSA_HORAS} horas.")
            agora = datetime.now()
            retomada = agora + timedelta(hours=PAUSA_HORAS)
            scheduler_instance.add_job(processar_fila_envios, 'date', run_date=retomada, id='retomada_notas', replace_existing=True)
            
            assunto_admin = "[Sistema de Notas Shopee] Aviso de Pausa: Etapa Concluída"
            corpo_admin = f"<p>O limite diário de {LIMITE_DIARIO} foi atingido.</p><p>O script foi programado para retomar a próxima etapa em {retomada.strftime('%d/%m/%Y %H:%M')}.</p><p>Envios realizados nesta etapa: {envios_realizados}</p>"
            
            if falhas_etapa:
                corpo_admin += "<p><b>ATENÇÃO: Foram registrados os seguintes erros:</b></p><ul>"
                for f in falhas_etapa: corpo_admin += f"<li>{f}</li>"
                corpo_admin += "</ul>"
            
            await enviar_email_brevo(EMAIL_ADMIN, "Administrador", assunto_admin, corpo_admin)
            conexao.close()
            
            if msg_progresso:
                try: 
                    await msg_progresso.edit_text(f"⏸️ <b>PAUSA DE SEGURANÇA:</b> Limite de {LIMITE_DIARIO} atingido.\nRetomada automática programada para {retomada.strftime('%d/%m às %H:%M')}.", parse_mode="HTML")
                except Exception as e: 
                    if EXIBIR_LOGS: logger.warning(f"⚠️ Erro ao atualizar mensagem de pausa no Telegram: {e}")
                    pass
            return

        assunto = f"Sua Nota Fiscal de Comissão Shopee - {loja}"
        corpo = (
            f"<p>Olá, equipe da <b>{loja}</b>.</p>"
            f"<p>Envio em anexo a Nota Fiscal de prestação de serviços referente às comissões geradas através do programa de afiliados da Shopee, no valor de R$ {valor}. O documento já está processado e pode ser direcionado para o controle contábil e financeiro da empresa.</p>"
            f"<p>Fico à disposição caso precisem de algum esclarecimento.</p>"
            f"<p>Atenciosamente,<br><b>RNM Comércio e Intermediações LTDA</b></p>"
        )
        
        if EXIBIR_LOGS: logger.info(f"⚙️ Processando envio para Loja: {loja} no valor de R$ {valor}...")
        
        try:
            status_api, resposta_api = await enviar_email_brevo(email, loja, assunto, corpo, pdf)
            
            if status_api in [200, 201]:
                cursor.execute("UPDATE fila_notas SET status = 'ENVIADO' WHERE id = ?", (id_registro,))
                envios_realizados += 1
                
                if EXIBIR_LOGS: logger.info(f"✅ Sucesso: Nota enviada para {loja} ({email}).")
                try: os.remove(pdf)
                except Exception: pass
            else:
                erro_msg = f"Erro API {status_api}: {resposta_api}"
                cursor.execute("UPDATE fila_notas SET status = 'ERRO', motivo_erro = ? WHERE id = ?", (erro_msg, id_registro))
                erros += 1
                falhas_etapa.append(f"⚠️ Falha ao processar loja {loja}: {erro_msg}")
                if EXIBIR_LOGS: logger.error(f"❌ Erro ao enviar para {loja}: {erro_msg}")
                
        except Exception as e:
            erro_msg = f"Erro Interno: {e}"
            cursor.execute("UPDATE fila_notas SET status = 'ERRO', motivo_erro = ? WHERE id = ?", (erro_msg, id_registro))
            erros += 1
            falhas_etapa.append(f"⚠️ Erro de rede/crítico na loja {loja}: {e}")
            if EXIBIR_LOGS: logger.error(f"❌ Erro Crítico ao enviar para {loja}: {e}")
            
        conexao.commit()
        await asyncio.sleep(1)

    conexao.close()
    
    try:
        if pasta_extracao and os.path.exists(pasta_extracao) and "extraido_" in pasta_extracao:
            shutil.rmtree(pasta_extracao)
    except Exception: pass
    
    if msg_progresso:
        try:
            texto_conclusao = (
                f"✅ <b>Operação finalizada!</b>\n"
                f"Todos os e-mails foram processados e a interface foi liberada.\n\n"
                f"📊 <b>Resumo:</b>\n"
                f"✅ Sucessos: <b>{envios_realizados}</b>\n"
                f"❌ Erros: <b>{erros}</b>"
            )
            await msg_progresso.edit_text(texto_conclusao, parse_mode="HTML")
        except Exception as e: 
            if EXIBIR_LOGS: logger.warning(f"⚠️ Erro ao postar conclusão no Telegram: {e}")
            pass
    
    assunto_final = "[Sistema de Notas Shopee] Processo Totalmente Concluído"
    corpo_final = f"<p>Todas as notas pendentes na fila foram processadas.</p><p>Envios realizados nesta etapa: {envios_realizados}</p>"
    if falhas_etapa:
        corpo_final += "<p><b>Erros registrados nesta etapa:</b></p><ul>"
        for f in falhas_etapa: corpo_final += f"<li>{f}</li>"
        corpo_final += "</ul>"
        
    await enviar_email_brevo(EMAIL_ADMIN, "Administrador", assunto_final, corpo_final)
    
    if msg_progresso and bot_instance:
        teclado_outros = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Espião Afiliados 🕵️"), KeyboardButton(text="Espelhador de Canais 🔄")],
                [KeyboardButton(text="Vídeos Autorais 🎥"), KeyboardButton(text="Grupo Público 📬")],
                [KeyboardButton(text="Gerador de Achadinhos 🛍️"), KeyboardButton(text="Disparador de Notas 🧾")],
                [KeyboardButton(text="Voltar ao Início 🔙")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        try:
            await bot_instance.send_message(msg_progresso.chat.id, "O painel principal está liberado.", reply_markup=teclado_outros)
        except Exception: pass

# ==========================================
# FLUXO INTERATIVO (TELEGRAM)
# ==========================================

# 🛡️ Interceptador Universal de Cancelamento exclusivo para as Notas
@router.message(F.text == "Abortar ❌", StateFilter("*"))
async def abortador_universal_notas(message: types.Message, state: FSMContext):
    if EXIBIR_LOGS: logger.info("❌ Operação de notas abortada pelo usuário.")
    await message.answer("Operação cancelada. Retornando ao menu do disparador...", reply_markup=obter_teclado_menu_notas())
    await state.set_state(PainelNotasFluxo.menu_principal)

# 🛡️ Bloqueio total de botões enquanto as notas são enviadas
@router.message(PainelNotasFluxo.enviando_notas)
async def ignorar_durante_envio(message: types.Message):
    await message.answer("⚠️ <b>Aguarde o fim do processo!</b>\nO robô está enviando as notas fiscais passo a passo. Nenhuma outra ação pode ser feita agora.", parse_mode="HTML")

@router.message(F.text == "Disparador de Notas 🧾", StateFilter("*"))
async def iniciar_painel_notas(message: types.Message, state: FSMContext):
    await state.clear()
    if EXIBIR_LOGS: logger.info("🧾 Acessando o menu do Disparador de Notas Fiscais.")
    texto = "🧾 <b>Painel do Disparador de Notas</b>\nSelecione uma das opções abaixo:"
    await message.answer(texto, reply_markup=obter_teclado_menu_notas(), parse_mode="HTML")
    await state.set_state(PainelNotasFluxo.menu_principal)

# 🛡️ Função de segurança para reativar o filtro automaticamente
async def reativar_filtro_automaticamente(chat_id):
    global FILTRO_ANTI_DUPLICIDADE
    if not FILTRO_ANTI_DUPLICIDADE:
        FILTRO_ANTI_DUPLICIDADE = True
        if EXIBIR_LOGS: logger.info("⏰ Timer de segurança: Filtro Anti-Duplicidade reativado automaticamente após 5 minutos.")
        try:
            if bot_instance:
                # Usa o teclado atualizado para refletir o status correto na tela do usuário
                await bot_instance.send_message(
                    chat_id, 
                    "🛡️ <b>Segurança Ativada:</b> O Filtro Anti-Duplicidade foi reativado automaticamente após 5 minutos de inatividade.", 
                    parse_mode="HTML",
                    reply_markup=obter_teclado_menu_notas()
                )
        except Exception:
            pass

@router.message(PainelNotasFluxo.menu_principal)
async def processar_menu_notas(message: types.Message, state: FSMContext):
    # 🛡️ MURALHA DE BLINDAGEM 1: Evita crash se o usuário não enviar texto (ex: se enviar um documento aqui no menu)
    if not message.text:
        await message.answer("⚠️ <b>Ação Inválida:</b> Por favor, clique no botão <b>Iniciar Envios 🚀</b> antes de anexar as planilhas.", parse_mode="HTML")
        return

    opcao = message.text.strip()
    
    if "Iniciar Envios" in opcao:
        texto = (
            "🧾 <b>Disparador Automático de Notas Fiscais</b>\n\n"
            "Para iniciar, por favor envie o arquivo <b>CSV extraído da Shopee</b> contendo as comissões e os e-mails dos lojistas."
        )
        await message.answer(texto, reply_markup=teclado_notas_cancelar, parse_mode="HTML")
        await state.set_state(PainelNotasFluxo.aguardando_csv)
        
    elif "Filtro Anti-Duplicidade" in opcao:
        global FILTRO_ANTI_DUPLICIDADE
        FILTRO_ANTI_DUPLICIDADE = not FILTRO_ANTI_DUPLICIDADE
        
        estado_texto = "ATIVADO ✅" if FILTRO_ANTI_DUPLICIDADE else "DESATIVADO ⚠️ (Cuidado com duplicatas)"
        if EXIBIR_LOGS: logger.info(f"⚙️ Alternância de segurança: O Filtro Anti-Duplicidade foi alterado para {FILTRO_ANTI_DUPLICIDADE}.")
        
        await message.answer(f"⚙️ O Filtro Anti-Duplicidade foi <b>{estado_texto}</b>.", reply_markup=obter_teclado_menu_notas(), parse_mode="HTML")
        
        # 🛡️ Lógica do Timer de 5 minutos
        if not FILTRO_ANTI_DUPLICIDADE:
            # Remove temporizador antigo se existir e cria um novo de 5 minutos
            if scheduler_instance and scheduler_instance.get_job('reativar_filtro_notas'):
                scheduler_instance.remove_job('reativar_filtro_notas')
                
            tempo_reativacao = datetime.now() + timedelta(minutes=5)
            if scheduler_instance:
                scheduler_instance.add_job(
                    reativar_filtro_automaticamente,
                    'date',
                    run_date=tempo_reativacao,
                    args=[message.chat.id],
                    id='reativar_filtro_notas',
                    replace_existing=True
                )
        else:
            # Se o usuário ligar o filtro manualmente, cancelamos a bomba-relógio
            if scheduler_instance and scheduler_instance.get_job('reativar_filtro_notas'):
                scheduler_instance.remove_job('reativar_filtro_notas')
        
    elif "Informações" in opcao:
        if EXIBIR_LOGS: logger.info("🔐 Consultando credenciais seguras no .env.")
        
        brevo_link = "https://app.brevo.com/"
        brevo_login = "rnm.notas@gmail.com"
        brevo_senha = os.getenv('BREVO_SENHA', 'Não configurada')
        
        gmail_link = "https://mail.google.com/"
        gmail_login = "rnm.notas@gmail.com"
        gmail_senha = os.getenv('GMAIL_SENHA', 'Não configurada')
        
        texto = (
            "🔐 <b>Informações de Acesso (Privado)</b>\n\n"
            "✉️ <b>Plataforma Brevo (Disparos API):</b>\n"
            f"🔗 <b>Link:</b> {brevo_link}\n"
            f"👤 <b>Login:</b> <code>{brevo_login}</code>\n"
            f"🔑 <b>Senha:</b> <tg-spoiler>{brevo_senha}</tg-spoiler>\n\n"
            "📧 <b>Conta Gmail (E-mail Remetente):</b>\n"
            f"🔗 <b>Link:</b> {gmail_link}\n"
            f"👤 <b>Login:</b> <code>{gmail_login}</code>\n"
            f"🔑 <b>Senha:</b> <tg-spoiler>{gmail_senha}</tg-spoiler>\n\n"
            "<i>(Toque nas senhas para revelá-las ou nos logins para copiar)</i>"
        )
        await message.answer(texto, parse_mode="HTML")
        
    elif "Voltar" in opcao:
        if EXIBIR_LOGS: logger.info("🔙 Retornando à gaveta do Centro Financeiro de forma isolada.")
        
        # O teclado agora reflete o novo menu "Centro Financeiro"
        teclado_financeiro = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Disparador de Notas 🧾")],
                [KeyboardButton(text="Voltar ao Início 🔙")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        await message.answer("Retornando ao Centro Financeiro...", reply_markup=teclado_financeiro)
        await state.clear()
        
    else:
        await message.answer("⚠️ Por favor, escolha uma das opções utilizando os botões do teclado.")

# Observe que eu tirei a trava rígida 'F.document' do decorador abaixo.
# Isso permite que o bot intercepte o seu clique caso você clique em algo errado.
@router.message(PainelNotasFluxo.aguardando_csv)
async def receber_csv(message: types.Message, state: FSMContext):
    # 🛡️ MURALHA DE BLINDAGEM 2: Evita crash caso você digite texto (ex: clicar no botão Anti-Duplicidade sem querer)
    if not message.document:
        if message.text and message.text == "Abortar ❌":
            return # Deixa o interceptador de cancelamento agir
        await message.answer("⚠️ <b>Ação Inválida:</b> Eu estou aguardando o arquivo <b>.csv</b>. Por favor, anexe o documento ou clique em Abortar ❌.", parse_mode="HTML")
        return

    doc = message.document
    if not doc.file_name.lower().endswith('.csv'):
        await message.answer("⚠️ O arquivo enviado não é válido. Por favor, envie um arquivo com o formato <b>.csv</b>.", parse_mode="HTML")
        return
        
    caminho_csv = os.path.join(PASTA_TEMP, doc.file_name)
    await bot_instance.download(doc, destination=caminho_csv)
    
    await state.update_data(csv_path=caminho_csv)
    if EXIBIR_LOGS: logger.info(f"✅ Arquivo CSV da Shopee recebido e salvo em {caminho_csv}.")
    
    await message.answer("✅ Arquivo CSV recebido!\n\nAgora envie o arquivo <b>.ZIP</b> contendo todos os PDFs das Notas Fiscais.", parse_mode="HTML", reply_markup=teclado_notas_cancelar)
    await state.set_state(PainelNotasFluxo.aguardando_zip)


@router.message(PainelNotasFluxo.aguardando_zip)
async def receber_zip_e_cruzar(message: types.Message, state: FSMContext):
    global FILTRO_ANTI_DUPLICIDADE # Declara a permissão para alterar o estado global
    
    # 🛡️ MURALHA DE BLINDAGEM 3: Evita crash caso o usuário digite texto em vez do ZIP
    if not message.document:
        if message.text and message.text == "Abortar ❌":
            return
        await message.answer("⚠️ <b>Ação Inválida:</b> Eu estou aguardando o arquivo <b>.zip</b>. Por favor, anexe o documento ou clique em Abortar ❌.", parse_mode="HTML")
        return

    doc = message.document
    if not doc.file_name.lower().endswith('.zip'):
        await message.answer("⚠️ O arquivo enviado não é válido. Por favor, envie um arquivo compactado <b>.zip</b>.", parse_mode="HTML")
        return
        
    msg_status = await message.answer("📦 Arquivo ZIP recebido. Descompactando e iniciando o cruzamento de dados... ⏳")
    
    caminho_zip = os.path.join(PASTA_TEMP, doc.file_name)
    await bot_instance.download(doc, destination=caminho_zip)
    
    data = await state.get_data()
    csv_path = data.get("csv_path")
    
    pasta_extracao = os.path.join(PASTA_TEMP, f"extraido_{int(datetime.now().timestamp())}")
    os.makedirs(pasta_extracao, exist_ok=True)
    
    try:
        with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
            zip_ref.extractall(pasta_extracao)
        if EXIBIR_LOGS: logger.info(f"📂 ZIP extraído com sucesso em {pasta_extracao}.")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao descompactar ZIP: {e}")
        await msg_status.edit_text(f"❌ Erro ao descompactar o ZIP: {e}")
        return
        
    try:
        df = pd.read_csv(csv_path, sep=None, engine='python')
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler CSV: {e}")
        await msg_status.edit_text(f"❌ Erro ao ler o arquivo CSV: {e}")
        return

    if FILTRO_ANTI_DUPLICIDADE:
        await msg_status.edit_text("✅ Extração concluída. Verificando histórico de envios e cruzando dados...")
        
        # CONSULTA O HISTÓRICO DE NOTAS JÁ ENVIADAS OU PENDENTES
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        cursor.execute("SELECT caminho_pdf FROM fila_notas WHERE status IN ('ENVIADO', 'PENDENTE')")
        historico = cursor.fetchall()
        conexao.close()
        
        # Extrai apenas os nomes dos arquivos já processados
        pdfs_protegidos = [os.path.basename(row[0]).lower() for row in historico if row[0]]
    else:
        await msg_status.edit_text("✅ Extração concluída. ⚠️ Filtro Anti-Duplicidade DESATIVADO. Cruzando todos os dados...")
        if EXIBIR_LOGS: logger.warning("⚠️ Filtro Anti-Duplicidade desligado. O histórico do banco de dados será ignorado.")
        pdfs_protegidos = []
        
        # 🛡️ Auto-reativação imediata após a leitura do lote
        FILTRO_ANTI_DUPLICIDADE = True
        
        if scheduler_instance and scheduler_instance.get_job('reativar_filtro_notas'):
            scheduler_instance.remove_job('reativar_filtro_notas')
            
        await message.answer("🛡️ <b>Segurança Reativada:</b> O Filtro Anti-Duplicidade voltou a ser ligado automaticamente após a importação deste lote.", parse_mode="HTML")

    # O resto do código continua normalmente a partir daqui
    arquivos_pdf_pasta_brutos = [f for f in os.listdir(pasta_extracao) if f.lower().endswith('.pdf')]
    arquivos_pdf_pasta = []
    qtd_ignorados = 0
    
    for f in arquivos_pdf_pasta_brutos:
        if f.lower() in pdfs_protegidos:
            qtd_ignorados += 1
            # Remove o arquivo físico duplicado, já que ele não será enviado novamente
            try:
                os.remove(os.path.join(pasta_extracao, f))
            except Exception:
                pass
        else:
            arquivos_pdf_pasta.append(f)

    notas_validadas = []
    lojas_pendentes = []
    pdfs_pendentes = arquivos_pdf_pasta.copy()
    
    for index, row in df.iterrows():
        nome_loja = str(row.get('Nome da loja', '')).strip()
        email_loja = str(row.get('E-mail', '')).strip()
        
        # Extração do valor contábil para injeção no e-mail
        valor_bruto = str(row.get('Comissão Total do Vendedor', '0,00')).strip()
        valor_limpo = valor_bruto.replace('R$', '').replace('R$ ', '').strip()
        
        if pd.isna(nome_loja) or pd.isna(email_loja) or not nome_loja or not email_loja:
            continue
            
        nome_csv_norm = normalizar_texto(nome_loja)
        encontrou_exato = False
        
        for pdf_file in pdfs_pendentes.copy():
            nome_pdf_norm = normalizar_texto(pdf_file)
            match_pdf = re.search(r'rnm\s*(.+)\s*pdf', nome_pdf_norm)
            if match_pdf:
                nome_loja_pdf = match_pdf.group(1).strip()
                if nome_loja_pdf in nome_csv_norm or nome_csv_norm in nome_loja_pdf:
                    notas_validadas.append({'loja': nome_loja, 'email': email_loja, 'pdf': pdf_file, 'tipo': 'exato', 'valor': valor_limpo})
                    pdfs_pendentes.remove(pdf_file)
                    encontrou_exato = True
                    break
                    
        if not encontrou_exato:
            lojas_pendentes.append({'loja': nome_loja, 'email': email_loja, 'valor': valor_limpo})
            
    pares_similares = []
    for loja_dict in lojas_pendentes.copy():
        nome_csv_norm = normalizar_texto(loja_dict['loja'])
        melhor_ratio = 0
        melhor_pdf = None
        
        for pdf_file in pdfs_pendentes:
            nome_pdf_norm = normalizar_texto(pdf_file)
            match_pdf = re.search(r'rnm\s*(.+)\s*pdf', nome_pdf_norm)
            if match_pdf:
                nome_loja_pdf = match_pdf.group(1).strip()
                ratio = difflib.SequenceMatcher(None, nome_csv_norm, nome_loja_pdf).ratio()
                if ratio > 0.75 and ratio > melhor_ratio:
                    melhor_ratio = ratio
                    melhor_pdf = pdf_file
                    
        if melhor_pdf:
            pares_similares.append({'loja_dict': loja_dict, 'pdf': melhor_pdf})
            lojas_pendentes.remove(loja_dict)
            pdfs_pendentes.remove(melhor_pdf)

    await state.update_data(
        notas_validadas=notas_validadas,
        lojas_pendentes=lojas_pendentes,
        pdfs_pendentes=pdfs_pendentes,
        pares_similares=pares_similares,
        pasta_extracao=pasta_extracao,
        csv_path_temp=csv_path,
        zip_path_temp=caminho_zip,
        qtd_ignorados=qtd_ignorados
    )
    
    if pares_similares:
        if EXIBIR_LOGS: logger.info("🔍 Inspecionando similaridades de notas fiscais...")
        await enviar_proxima_similaridade(message, state)
    elif lojas_pendentes and pdfs_pendentes:
        if EXIBIR_LOGS: logger.info("🛠️ Entrando no modo de pareamento manual de notas fiscais...")
        await enviar_lista_manual(message, state)
    else:
        if EXIBIR_LOGS: logger.info("📊 Gerando resumo final do cruzamento...")
        await gerar_resumo_final_notas(message, state)

async def enviar_proxima_similaridade(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pares_similares = data.get('pares_similares', [])
    
    if not pares_similares:
        lojas_pendentes = data.get('lojas_pendentes', [])
        pdfs_pendentes = data.get('pdfs_pendentes', [])
        if lojas_pendentes and pdfs_pendentes:
            await enviar_lista_manual(message, state)
        else:
            await gerar_resumo_final_notas(message, state)
        return

    par_atual = pares_similares[0]
    texto = (
        "🔍 <b>Similaridade Encontrada:</b>\n\n"
        f"Loja na Planilha: <b>{par_atual['loja_dict']['loja']}</b>\n"
        f"Arquivo PDF: <b>{par_atual['pdf']}</b>\n\n"
        "Deseja associar estes dois?"
    )
    teclado = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Sim ✅"), KeyboardButton(text="Não ❌")]],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer(texto, reply_markup=teclado, parse_mode="HTML")
    await state.set_state(PainelNotasFluxo.revisando_similares)

@router.message(PainelNotasFluxo.revisando_similares)
async def processar_resposta_similaridade(message: types.Message, state: FSMContext):
    resposta = message.text
    if resposta not in ["Sim ✅", "Não ❌"]:
        await message.answer("⚠️ Use os botões em ecrã: Sim ✅ ou Não ❌.")
        return
        
    data = await state.get_data()
    pares_similares = data.get('pares_similares', [])
    notas_validadas = data.get('notas_validadas', [])
    lojas_pendentes = data.get('lojas_pendentes', [])
    pdfs_pendentes = data.get('pdfs_pendentes', [])
    
    par_atual = pares_similares.pop(0)
    
    if resposta == "Sim ✅":
        notas_validadas.append({'loja': par_atual['loja_dict']['loja'], 'email': par_atual['loja_dict']['email'], 'pdf': par_atual['pdf'], 'tipo': 'similar', 'valor': par_atual['loja_dict']['valor']})
        if EXIBIR_LOGS: logger.info(f"✅ Associação aprovada: {par_atual['loja_dict']['loja']} <> {par_atual['pdf']}")
    else:
        lojas_pendentes.append(par_atual['loja_dict'])
        pdfs_pendentes.append(par_atual['pdf'])
        if EXIBIR_LOGS: logger.info(f"❌ Associação recusada: {par_atual['loja_dict']['loja']} <> {par_atual['pdf']}")
        
    await state.update_data(pares_similares=pares_similares, notas_validadas=notas_validadas, lojas_pendentes=lojas_pendentes, pdfs_pendentes=pdfs_pendentes)
    await enviar_proxima_similaridade(message, state)

async def enviar_lista_manual(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lojas = data.get('lojas_pendentes', [])
    pdfs = data.get('pdfs_pendentes', [])
    
    if not lojas or not pdfs:
        await gerar_resumo_final_notas(message, state)
        return
        
    loja_atual = lojas[0]
    
    texto = "⚠️ <b>Auditoria Manual Passo a Passo</b>\n\n"
    texto += f"🏬 <b>Loja Pendente:</b> {loja_atual['loja']}\n"
    texto += f"✉️ <b>E-mail:</b> {loja_atual['email']}\n\n"
    texto += "📄 <b>PDFs Disponíveis:</b>\n"
    
    for i, pdf in enumerate(pdfs):
        letra = chr(65 + (i % 26)) + (str(i // 26) if i >= 26 else "")
        texto += f"<b>{letra}</b> - {pdf}\n"
        
    texto += "\n👉 <b>Digite a LETRA</b> correspondente ao PDF desta loja.\n"
    texto += "🔎 <i>Dica: Para visualizar um PDF antes de associar, clique em <b>Ver PDF 👁️</b>.</i>"
    
    teclado = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Pular Loja ⏭️"), KeyboardButton(text="Encerrar e Ir para o Resumo ⏭️")],
            [KeyboardButton(text="Ver PDF 👁️"), KeyboardButton(text="Abortar ❌")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    
    if len(texto) > 3900:
        await message.answer(texto[:3900] + "\n[Lista truncada...]", reply_markup=teclado, parse_mode="HTML")
    else:
        await message.answer(texto, reply_markup=teclado, parse_mode="HTML")
        
    await state.set_state(PainelNotasFluxo.pareamento_manual)

@router.message(PainelNotasFluxo.pareamento_manual)
async def processar_pareamento_manual(message: types.Message, state: FSMContext):
    texto_usuario = message.text.strip().upper()
    
    if texto_usuario == "ENCERRAR E IR PARA O RESUMO ⏭️":
        await gerar_resumo_final_notas(message, state)
        return

    if "VER PDF" in texto_usuario:
        data = await state.get_data()
        pdfs = data.get('pdfs_pendentes', [])
        pasta_extracao = data.get('pasta_extracao')
        
        if len(pdfs) == 1:
            # Se só tem 1 PDF, envia ele direto na tela sem mudar de estado
            pdf_alvo = pdfs[0]
            caminho_completo = os.path.join(pasta_extracao, pdf_alvo)
            try:
                arquivo_telegram = types.FSInputFile(caminho_completo)
                await message.answer_document(arquivo_telegram, caption=f"🔎 <b>Arquivo:</b> {pdf_alvo}\n\n👉 Digite <b>A</b> para associar ou pule a loja.", parse_mode="HTML")
            except Exception as e:
                await message.answer(f"❌ Erro ao enviar o arquivo: {e}")
            return
        
        # Se tem mais de 1, pergunta qual quer ver
        texto_opcoes = "🔎 <b>Qual PDF você deseja visualizar?</b>\nDigite a <b>LETRA</b> correspondente (Ex: A, B, C):\n\n"
        for i, pdf in enumerate(pdfs):
            letra = chr(65 + (i % 26)) + (str(i // 26) if i >= 26 else "")
            texto_opcoes += f"<b>{letra}</b> - {pdf}\n"
            
        await message.answer(texto_opcoes, parse_mode="HTML")
        await state.set_state(PainelNotasFluxo.inspecionando_pdf_manual)
        return
        
    data = await state.get_data()
    lojas = data.get('lojas_pendentes', [])
    pdfs = data.get('pdfs_pendentes', [])
    notas_validadas = data.get('notas_validadas', [])
    
    if "PULAR LOJA" in texto_usuario:
        if lojas:
            loja_pulada = lojas.pop(0)
            lojas.append(loja_pulada)
            await state.update_data(lojas_pendentes=lojas)
            await message.answer(f"⏭️ Loja <b>{loja_pulada['loja']}</b> movida para o final da fila.", parse_mode="HTML")
            await enviar_lista_manual(message, state)
        return
        
    letra_idx = -1
    for i in range(len(pdfs)):
        l = chr(65 + (i % 26)) + (str(i // 26) if i >= 26 else "")
        if l == texto_usuario:
            letra_idx = i
            break
            
    if letra_idx == -1:
        await message.answer("⚠️ Letra inválida. Digite apenas a letra correspondente ao PDF (Ex: A, B, C) ou use os botões.")
        return
        
    loja_selecionada = lojas.pop(0)
    pdf_selecionado = pdfs.pop(letra_idx)
    
    notas_validadas.append({'loja': loja_selecionada['loja'], 'email': loja_selecionada['email'], 'pdf': pdf_selecionado, 'tipo': 'manual', 'valor': loja_selecionada['valor']})
    if EXIBIR_LOGS: logger.info(f"✅ Pareamento manual aceito: {loja_selecionada['loja']} <> {pdf_selecionado}")
    
    await state.update_data(lojas_pendentes=lojas, pdfs_pendentes=pdfs, notas_validadas=notas_validadas)
    await message.answer(f"✅ <b>Associado com sucesso:</b>\n{loja_selecionada['loja']} ↔️ {pdf_selecionado}", parse_mode="HTML")
    
    if lojas and pdfs:
        await enviar_lista_manual(message, state)
    else:
        await gerar_resumo_final_notas(message, state)

@router.message(PainelNotasFluxo.inspecionando_pdf_manual)
async def processar_inspecao_manual(message: types.Message, state: FSMContext):
    texto_usuario = message.text.strip().upper()
    data = await state.get_data()
    pdfs = data.get('pdfs_pendentes', [])
    pasta_extracao = data.get('pasta_extracao')

    # Se o usuário clicar em qualquer botão do teclado enquanto tenta visualizar, 
    # repassa a ação para a função de pareamento para não quebrar o fluxo.
    if texto_usuario in ["ENCERRAR E IR PARA O RESUMO ⏭️"] or "PULAR LOJA" in texto_usuario:
        await state.set_state(PainelNotasFluxo.pareamento_manual)
        await processar_pareamento_manual(message, state)
        return

    if texto_usuario == "VER PDF 👁️":
        await message.answer("🔎 Digite a <b>LETRA</b> do PDF que você deseja visualizar (Ex: A, B, C):", parse_mode="HTML")
        return

    letra_idx = -1
    for i in range(len(pdfs)):
        l = chr(65 + (i % 26)) + (str(i // 26) if i >= 26 else "")
        if l == texto_usuario:
            letra_idx = i
            break

    if letra_idx == -1:
        # Aqui estava o erro! Agora ele dá o aviso e dá o 'return' para manter o estado no Modo de Visualização.
        await message.answer("⚠️ Letra não encontrada.\nDigite a letra correta para visualizar ou clique em um dos botões abaixo.", parse_mode="HTML")
        return

    pdf_alvo = pdfs[letra_idx]
    caminho_completo = os.path.join(pasta_extracao, pdf_alvo)
    try:
        arquivo_telegram = types.FSInputFile(caminho_completo)
        await message.answer_document(arquivo_telegram, caption=f"🔎 <b>Arquivo Inspecionado:</b> {pdf_alvo}", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Erro ao enviar o arquivo: {e}")

    await message.answer("✅ <b>Visualização concluída.</b>\n\n👉 <b>Atenção:</b> Você voltou para o modo de Associação.\nDigite a <b>LETRA</b> da nota se quiser associar à loja.", parse_mode="HTML")
    await state.set_state(PainelNotasFluxo.pareamento_manual)

async def gerar_resumo_final_notas(message: types.Message, state: FSMContext):
    data = await state.get_data()
    notas_validadas = data.get('notas_validadas', [])
    lojas_pendentes = data.get('lojas_pendentes', [])
    pasta_extracao = data.get('pasta_extracao')
    csv_path = data.get('csv_path_temp')
    caminho_zip = data.get('zip_path_temp')
    
    conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
    cursor = conexao.cursor()
    
    try:
        cursor.execute("ALTER TABLE fila_notas ADD COLUMN valor TEXT")
    except sqlite3.OperationalError:
        pass
    
    resumo_tabela = ""
    for nota in notas_validadas:
        caminho_completo = os.path.join(pasta_extracao, nota['pdf'])
        cursor.execute('''
            INSERT INTO fila_notas (nome_loja, email_destino, caminho_pdf, status, valor)
            VALUES (?, ?, ?, 'RASCUNHO', ?)
        ''', (nota['loja'], nota['email'], caminho_completo, nota['valor']))
        
        tipo_icone = "📄"
        if nota['tipo'] == 'similar':
            tipo_icone = "🔍"
        elif nota['tipo'] == 'manual':
            tipo_icone = "✍️"
            
        resumo_tabela += f"{tipo_icone} <b>{nota['pdf']}</b>\n   └ Loja: {nota['loja']} | E-mail: {nota['email']}\n\n"
        
    conexao.commit()
    conexao.close()
    
    try:
        os.remove(csv_path)
        os.remove(caminho_zip)
    except: pass
    
    resumo = f"✅ <b>Validação finalizada!</b>\n\n"
    resumo += f"📊 <b>Balanço Geral:</b>\n"
    resumo += f"✅ Notas prontas para envio: <b>{len(notas_validadas)}</b>\n"
    resumo += f"❌ Lojas sem PDF: <b>{len(lojas_pendentes)}</b>\n"
    
    qtd_ignorados = data.get('qtd_ignorados', 0)
    if qtd_ignorados > 0:
        resumo += f"♻️ Ignorados (Já enviados anteriormente): <b>{qtd_ignorados}</b>\n"
    resumo += "\n"
    
    if lojas_pendentes:
        resumo += "⚠️ <b>Não localizadas na auditoria:</b>\n"
        for loja in lojas_pendentes:
            resumo += f"   ❌ {loja['loja']}\n"
        resumo += "\n"
        
    if notas_validadas:
        resumo += "📋 <b>Resumo do que será enviado:</b>\n"
        resumo += resumo_tabela
        resumo += "\nDeseja aprovar e iniciar os envios agora?"
        
        teclado_aprovacao = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Aprovar Envio ✅"), KeyboardButton(text="Abortar ❌")],
                [KeyboardButton(text="Ver PDF 👁️")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        
        if len(resumo) > 3900:
            await message.answer(resumo[:3900] + "\n\n[...Lista truncada devido ao limite de texto...]", parse_mode="HTML", reply_markup=teclado_aprovacao)
        else:
            await message.answer(resumo, parse_mode="HTML", reply_markup=teclado_aprovacao)
            
        await state.set_state(PainelNotasFluxo.aguardando_aprovacao)
    else:
        qtd_ignorados = data.get('qtd_ignorados', 0)
        resumo_falha = ""
        
        if qtd_ignorados > 0:
            resumo_falha += f"🛑 <b>Bloqueio Anti-Duplicidade:</b> <b>{qtd_ignorados}</b> arquivo(s) bloqueado(s) pois já constam como ENVIADOS no histórico.\n\n"
            
        resumo_falha += f"⚠️ <b>Nenhuma nota foi combinada com sucesso.</b>\n\n❌ <b>Lojas pendentes ({len(lojas_pendentes)}):</b>\n"
        for loja in lojas_pendentes:
            resumo_falha += f"   - {loja['loja']}\n"
            
        await message.answer(resumo_falha[:3900], parse_mode="HTML")
        
        await message.answer("Operação abortada.", reply_markup=obter_teclado_menu_notas())
        await state.set_state(PainelNotasFluxo.menu_principal)

@router.message(PainelNotasFluxo.aguardando_aprovacao)
async def processar_aprovacao_envio(message: types.Message, state: FSMContext):
    texto_usuario = message.text.strip()
    
    if "VER PDF" in texto_usuario.upper():
        data = await state.get_data()
        notas_validadas = data.get('notas_validadas', [])
        pasta_extracao = data.get('pasta_extracao')
        
        if not notas_validadas:
            await message.answer("⚠️ Nenhuma nota validada para visualizar.")
            return

        if len(notas_validadas) == 1:
            nota = notas_validadas[0]
            caminho_completo = os.path.join(pasta_extracao, nota['pdf'])
            try:
                arquivo_telegram = types.FSInputFile(caminho_completo)
                await message.answer_document(arquivo_telegram, caption=f"🔎 <b>Arquivo Validado:</b> {nota['pdf']}", parse_mode="HTML")
            except Exception as e:
                await message.answer(f"❌ Erro ao enviar o arquivo: {e}")
            return
        
        texto = "🔎 <b>Qual nota você deseja visualizar?</b>\nDigite o <b>NÚMERO</b> correspondente:\n\n"
        for i, nota in enumerate(notas_validadas, 1):
            texto += f"<b>{i}</b> - {nota['pdf']}\n"

        await message.answer(texto, parse_mode="HTML")
        await state.set_state(PainelNotasFluxo.inspecionando_pdf_final)
        return

    if texto_usuario != "Aprovar Envio ✅":
        await message.answer("Por favor, utilize os botões em ecrã para Aprovar Envio ✅, Ver PDF 👁️ ou Abortar ❌.")
        return

    # 🛡️ TRAVA: Muda o estado imediatamente para bloquear a tela e impedir duplos cliques
    await state.set_state(PainelNotasFluxo.enviando_notas)

    conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
    cursor = conexao.cursor()
    cursor.execute("UPDATE fila_notas SET status = 'PENDENTE' WHERE status = 'RASCUNHO'")
    conexao.commit()
    conexao.close()
    
    # -------------------------------------------------------------
    # 🔥 A CORREÇÃO DO BLOQUEIO DE EDIÇÃO (Telegram API Rate Limit)
    # -------------------------------------------------------------
    # 1. Apaga o teclado do usuário de forma isolada
    await message.answer("⏳ <b>Preparando o motor de envios...</b>", parse_mode="HTML", reply_markup=types.ReplyKeyboardRemove())
    
    # 2. Cria uma mensagem totalmente LIMPA (sem comandos de teclado) para ser o nosso quadro de animação
    msg_dinamica = await message.answer("🚀 <i>Sincronizando com a base de dados...</i>", parse_mode="HTML")
    
    if EXIBIR_LOGS: logger.info("⏰ Acionando motor de envio via Brevo.")
    
    # A tarefa é lançada em segundo plano enviando O OBJETO DA MENSAGEM diretamente
    asyncio.create_task(processar_fila_envios(msg_progresso=msg_dinamica))
    
    # Limpa o estado atual
    await state.clear()

@router.message(PainelNotasFluxo.inspecionando_pdf_final)
async def processar_inspecao_final(message: types.Message, state: FSMContext):
    data = await state.get_data()
    notas_validadas = data.get('notas_validadas', [])
    pasta_extracao = data.get('pasta_extracao')
    texto_usuario = message.text.strip().upper()

    if texto_usuario in ["APROVAR ENVIO ✅"]:
        await state.set_state(PainelNotasFluxo.aguardando_aprovacao)
        await processar_aprovacao_envio(message, state)
        return

    if "VER PDF" in texto_usuario:
        await message.answer("🔎 Digite o <b>NÚMERO</b> da nota que deseja visualizar (Ex: 1, 2):", parse_mode="HTML")
        return

    try:
        idx = int(texto_usuario) - 1
        if 0 <= idx < len(notas_validadas):
            nota = notas_validadas[idx]
            caminho_completo = os.path.join(pasta_extracao, nota['pdf'])
            arquivo_telegram = types.FSInputFile(caminho_completo)
            await message.answer_document(arquivo_telegram, caption=f"🔎 <b>Arquivo Validado:</b> {nota['pdf']}", parse_mode="HTML")
        else:
            await message.answer("⚠️ Número não encontrado. Digite um número válido para visualizar.")
            return # Trava a tela de visualização
    except ValueError:
        await message.answer("⚠️ Por favor, digite apenas o <b>NÚMERO</b> correspondente à nota (Ex: 1, 2).", parse_mode="HTML")
        return # Trava a tela de visualização

    teclado_aprovacao = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Aprovar Envio ✅"), KeyboardButton(text="Abortar ❌")],
            [KeyboardButton(text="Ver PDF 👁️")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    await message.answer("✅ <b>Visualização concluída.</b>\n\nDeseja aprovar e iniciar os envios agora?", reply_markup=teclado_aprovacao, parse_mode="HTML")
    await state.set_state(PainelNotasFluxo.aguardando_aprovacao)
