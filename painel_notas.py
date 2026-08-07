EXIBIR_LOGS = True
import os
import zipfile
import pandas as pd
import asyncio
import aiohttp
import sqlite3
import base64
import logging
import shutil
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
    aguardando_csv = State()
    aguardando_zip = State()
    aguardando_aprovacao = State()

teclado_notas_cancelar = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Cancelar ❌")]],
    resize_keyboard=True,
    is_persistent=True
)

PASTA_TEMP = "temp/notas_fiscais"
os.makedirs(PASTA_TEMP, exist_ok=True)

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

# ==========================================
# MOTOR DE DISPARO EM LOTE
# ==========================================
async def processar_fila_envios(chat_id=None, message_id=None):
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
    falhas_etapa = []
    relatorio_visual = "📋 <b>Relatório de Envio de Notas</b>\n\n"
    
    for idx, item in enumerate(pendentes, 1):
        id_registro = item["id"]
        loja = item["nome_loja"]
        email = item["email_destino"]
        pdf = item["caminho_pdf"]
        nome_arquivo = os.path.basename(pdf)
        
        if chat_id and message_id and bot_instance:
            try:
                await bot_instance.edit_message_text(f"⏳ <b>Enviando nota {idx}/{total_notas}</b> : Conectando com a loja {loja}...", chat_id=chat_id, message_id=message_id, parse_mode="HTML")
            except Exception: pass

        if envios_realizados >= LIMITE_DIARIO:
            if EXIBIR_LOGS: logger.warning(f"⏳ Limite diário atingido. Programando retomada para {PAUSA_HORAS} horas.")
            agora = datetime.now()
            retomada = agora + timedelta(hours=PAUSA_HORAS)
            scheduler_instance.add_job(processar_fila_envios, 'date', run_date=retomada, id='retomada_notas', replace_existing=True)
            
            assunto_admin = "[Sistema de Notas Shopee] Aviso de Pausa: Etapa Concluída"
            corpo_admin = f"<p>O limite diário de {LIMITE_DIARIO} foi atingido.</p><p>O script foi programado para retomar a próxima etapa em {retomada.strftime('%d/%m/%Y %H:%M')}.</p><p>Envios realizados nesta etapa: {envios_realizados}</p>"
            
            relatorio_visual += f"\n⏸️ <b>PAUSA DE SEGURANÇA:</b> O limite de {LIMITE_DIARIO} envios foi atingido. A esteira foi pausada e voltará automaticamente em {retomada.strftime('%d/%m às %H:%M')}."
            
            if chat_id and message_id and bot_instance:
                try: await bot_instance.edit_message_text(relatorio_visual[:4000], chat_id=chat_id, message_id=message_id, parse_mode="HTML")
                except Exception: pass
            
            if falhas_etapa:
                corpo_admin += "<p><b>ATENÇÃO: Foram registrados os seguintes erros:</b></p><ul>"
                for f in falhas_etapa: corpo_admin += f"<li>{f}</li>"
                corpo_admin += "</ul>"
            
            await enviar_email_brevo(EMAIL_ADMIN, "Administrador", assunto_admin, corpo_admin)
            conexao.close()
            return

        assunto = f"Sua Nota Fiscal de Comissão - {loja}"
        corpo = f"<p>Olá, {loja}.</p><p>Segue em anexo a Nota Fiscal referente às comissões do programa de afiliados da Shopee.</p><p>Qualquer dúvida, estamos à disposição.</p>"
        
        if EXIBIR_LOGS: logger.info(f"⚙️ Processando envio para Loja: {loja}...")
        status_api, resposta_api = await enviar_email_brevo(email, loja, assunto, corpo, pdf)
        
        if status_api in [200, 201]:
            cursor.execute("UPDATE fila_notas SET status = 'ENVIADO' WHERE id = ?", (id_registro,))
            envios_realizados += 1
            relatorio_visual += f"🟢 <b>Concluído</b> | {loja} | {email} | {nome_arquivo}\n"
            if EXIBIR_LOGS: logger.info(f"✅ Sucesso: Nota enviada para {loja} ({email}).")
        else:
            erro_msg = f"Erro API {status_api}: {resposta_api}"
            cursor.execute("UPDATE fila_notas SET status = 'ERRO', motivo_erro = ? WHERE id = ?", (erro_msg, id_registro))
            falhas_etapa.append(f"⚠️ Falha ao processar loja {loja}: {erro_msg}")
            relatorio_visual += f"🔴 <b>Erro API</b> | {loja} | {email} | {nome_arquivo}\n"
            relatorio_visual += f"   └ ⚠️ <b>O que houve:</b> O e-mail foi rejeitado pelo servidor ou o arquivo possui falhas.\n"
            relatorio_visual += f"   └ 🛠️ <b>Como corrigir:</b> Verifique o contato no CSV e a validade do PDF, e submeta a loja novamente.\n"
            if EXIBIR_LOGS: logger.error(f"❌ Erro ao enviar para {loja}: {erro_msg}")
            
        conexao.commit()
        await asyncio.sleep(1)

    conexao.close()
    
    if chat_id and message_id and bot_instance:
        try: await bot_instance.edit_message_text(relatorio_visual[:4000], chat_id=chat_id, message_id=message_id, parse_mode="HTML")
        except Exception: pass
    
    assunto_final = "[Sistema de Notas Shopee] Processo Totalmente Concluído"
    corpo_final = f"<p>Todas as notas pendentes na planilha foram processadas com sucesso.</p><p>Envios realizados nesta última etapa: {envios_realizados}</p>"
    if falhas_etapa:
        corpo_final += "<p><b>Erros registrados nesta etapa:</b></p><ul>"
        for f in falhas_etapa: corpo_final += f"<li>{f}</li>"
        corpo_final += "</ul>"
        
    await enviar_email_brevo(EMAIL_ADMIN, "Administrador", assunto_final, corpo_final)
    
    if bot_instance and not chat_id:
        from bot_mestre import ADMIN_ID
        await bot_instance.send_message(ADMIN_ID, f"🎉 <b>Processamento de Notas Finalizado!</b>\nForam processados {envios_realizados} envios. O relatório detalhado foi enviado para o seu e-mail.", parse_mode="HTML")

# ==========================================
# FLUXO INTERATIVO (TELEGRAM)
# ==========================================
@router.message(F.text == "Disparador de Notas 🧾", StateFilter("*"))
async def iniciar_painel_notas(message: types.Message, state: FSMContext):
    await state.clear()
    if EXIBIR_LOGS: logger.info("🧾 Acessando o painel do Disparador de Notas Fiscais.")
    texto = (
        "🧾 <b>Disparador Automático de Notas Fiscais</b>\n\n"
        "Para iniciar, por favor envie o arquivo <b>CSV extraído da Shopee</b> contendo as comissões e os e-mails dos lojistas."
    )
    await message.answer(texto, reply_markup=teclado_notas_cancelar, parse_mode="HTML")
    await state.set_state(PainelNotasFluxo.aguardando_csv)

@router.message(PainelNotasFluxo.aguardando_csv, F.document)
async def receber_csv(message: types.Message, state: FSMContext):
    doc = message.document
    if not doc.file_name.lower().endswith('.csv'):
        await message.answer("⚠️ Por favor, envie um arquivo com o formato <b>.csv</b>.", parse_mode="HTML")
        return
        
    caminho_csv = os.path.join(PASTA_TEMP, doc.file_name)
    await bot_instance.download(doc, destination=caminho_csv)
    
    await state.update_data(csv_path=caminho_csv)
    if EXIBIR_LOGS: logger.info(f"✅ Arquivo CSV da Shopee recebido e salvo em {caminho_csv}.")
    
    await message.answer("✅ Arquivo CSV recebido!\n\nAgora envie o arquivo <b>.ZIP</b> contendo todos os PDFs das Notas Fiscais.", parse_mode="HTML", reply_markup=teclado_notas_cancelar)
    await state.set_state(PainelNotasFluxo.aguardando_zip)

@router.message(PainelNotasFluxo.aguardando_zip, F.document)
async def receber_zip_e_cruzar(message: types.Message, state: FSMContext):
    doc = message.document
    if not doc.file_name.lower().endswith('.zip'):
        await message.answer("⚠️ Por favor, envie um arquivo compactado <b>.zip</b>.", parse_mode="HTML")
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

    conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
    cursor = conexao.cursor()
    
    arquivos_pdf_pasta = [f for f in os.listdir(pasta_extracao) if f.lower().endswith('.pdf')]
    notas_encontradas = 0
    lojas_sem_pdf = []
    
    conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
    cursor = conexao.cursor()
    
    arquivos_pdf_pasta = [f for f in os.listdir(pasta_extracao) if f.lower().endswith('.pdf')]
    notas_encontradas = 0
    lojas_sem_pdf = []
    resumo_tabela = ""
    
    for index, row in df.iterrows():
    try:
        df = pd.read_csv(csv_path, sep=None, engine='python')
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler CSV: {e}")
        await msg_status.edit_text(f"❌ Erro ao ler o arquivo CSV: {e}")
        return

    conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
    cursor = conexao.cursor()
    
    arquivos_pdf_pasta = [f for f in os.listdir(pasta_extracao) if f.lower().endswith('.pdf')]
    notas_encontradas = 0
    lojas_sem_pdf = []
    resumo_tabela = ""
    
    for index, row in df.iterrows():
        nome_loja = str(row.get('Nome da loja', '')).strip()
        email_loja = str(row.get('E-mail', '')).strip()
        
        if pd.isna(nome_loja) or pd.isna(email_loja) or not nome_loja or not email_loja:
            continue
            
        pdf_encontrado = None
        nome_busca = nome_loja.lower()
        
        for pdf_file in arquivos_pdf_pasta:
            pdf_lower = pdf_file.lower()
            if f"rnm- {nome_busca}" in pdf_lower or f"rnm-{nome_busca}" in pdf_lower:
                pdf_encontrado = os.path.join(pasta_extracao, pdf_file)
                break
                
        if pdf_encontrado:
            cursor.execute('''
                INSERT INTO fila_notas (nome_loja, email_destino, caminho_pdf, status)
                VALUES (?, ?, ?, 'RASCUNHO')
            ''', (nome_loja, email_loja, pdf_encontrado))
            notas_encontradas += 1
            resumo_tabela += f"📄 {nome_loja} | {email_loja} | {pdf_file}\n"
        else:
            lojas_sem_pdf.append(nome_loja)
            
    conexao.commit()
    conexao.close()
    
    try:
        os.remove(csv_path)
        os.remove(caminho_zip)
    except: pass
    
    resumo = f"✅ <b>Cruzamento finalizado!</b>\n\n"
    resumo += f"📄 Notas mapeadas: <b>{notas_encontradas}</b>\n"
    if lojas_sem_pdf:
        resumo += f"⚠️ Lojas sem PDF encontrado: <b>{len(lojas_sem_pdf)}</b>\n\n"
        
    if notas_encontradas > 0:
        resumo += "📋 <b>Resumo do que será enviado:</b>\n"
        resumo += resumo_tabela
        resumo += "\nDeseja aprovar e iniciar os envios agora?"
        
        teclado_aprovacao = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Aprovar Envio ✅"), KeyboardButton(text="Cancelar ❌")]],
            resize_keyboard=True,
            is_persistent=True
        )
        await msg_status.edit_text(resumo[:3900], parse_mode="HTML")
        await message.answer("Por favor, valide o resumo acima:", reply_markup=teclado_aprovacao)
        await state.set_state(PainelNotasFluxo.aguardando_aprovacao)
    else:
        await msg_status.edit_text(f"⚠️ Nenhuma nota foi combinada com sucesso.\nLojas que falharam: {len(lojas_sem_pdf)}", parse_mode="HTML")
        from bot_mestre import obter_teclado_outros_canais
        await message.answer("Operação abortada.", reply_markup=obter_teclado_outros_canais())
        await state.clear()

@router.message(PainelNotasFluxo.aguardando_aprovacao)
async def processar_aprovacao_envio(message: types.Message, state: FSMContext):
    if message.text != "Aprovar Envio ✅":
        await message.answer("Por favor, utilize os botões em ecrã para Aprovar Envio ✅ ou Cancelar ❌.")
        return

    conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
    cursor = conexao.cursor()
    cursor.execute("UPDATE fila_notas SET status = 'PENDENTE' WHERE status = 'RASCUNHO'")
    conexao.commit()
    conexao.close()
    
    msg_dinamica = await message.answer("⏳ <b>Preparando o motor de envios...</b>", parse_mode="HTML", reply_markup=types.ReplyKeyboardRemove())
    
    if EXIBIR_LOGS: logger.info("⏰ Acionando motor de envio via Brevo.")
    asyncio.create_task(processar_fila_envios(chat_id=message.chat.id, message_id=msg_dinamica.message_id))
    
    from bot_mestre import obter_teclado_outros_canais
    await message.answer("O painel principal está liberado. A tabela acima será atualizada em tempo real.", reply_markup=obter_teclado_outros_canais())
    await state.clear()
