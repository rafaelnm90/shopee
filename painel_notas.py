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
    aguardando_csv = State()
    aguardando_zip = State()
    revisando_similares = State()
    pareamento_manual = State()
    aguardando_aprovacao = State()

teclado_notas_cancelar = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Cancelar ❌")]],
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
            
            # LIMPEZA: Apaga o PDF físico imediatamente após o sucesso
            try:
                os.remove(pdf)
            except Exception: pass
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

    await msg_status.edit_text("✅ Extração concluída. Verificando histórico de envios e cruzando dados...")

    # CONSULTA O HISTÓRICO DE NOTAS JÁ ENVIADAS OU PENDENTES
    conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
    cursor = conexao.cursor()
    cursor.execute("SELECT caminho_pdf FROM fila_notas WHERE status IN ('ENVIADO', 'PENDENTE')")
    historico = cursor.fetchall()
    conexao.close()
    
    # Extrai apenas os nomes dos arquivos já processados
    pdfs_protegidos = [os.path.basename(row[0]).lower() for row in historico if row[0]]

    arquivos_pdf_pasta_brutos = [f for f in os.listdir(pasta_extracao) if f.lower().endswith('.pdf')]
    arquivos_pdf_pasta = []
    qtd_ignorados = 0
    
    for f in arquivos_pdf_pasta_brutos:
        if f.lower() in pdfs_protegidos:
            qtd_ignorados += 1
            # Remove o arquivo físico duplicado, já que ele não será enviado novamente
            try: os.remove(os.path.join(pasta_extracao, f)) except: pass
        else:
            arquivos_pdf_pasta.append(f)

    notas_validadas = []
    lojas_pendentes = []
    pdfs_pendentes = arquivos_pdf_pasta.copy()
    
    for index, row in df.iterrows():
        nome_loja = str(row.get('Nome da loja', '')).strip()
        email_loja = str(row.get('E-mail', '')).strip()
        
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
                    notas_validadas.append({'loja': nome_loja, 'email': email_loja, 'pdf': pdf_file, 'tipo': 'exato'})
                    pdfs_pendentes.remove(pdf_file)
                    encontrou_exato = True
                    break
                    
        if not encontrou_exato:
            lojas_pendentes.append({'loja': nome_loja, 'email': email_loja})
            
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
        notas_validadas.append({'loja': par_atual['loja_dict']['loja'], 'email': par_atual['loja_dict']['email'], 'pdf': par_atual['pdf'], 'tipo': 'similar'})
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
    
    texto = "⚠️ <b>Auditoria Manual Necessária</b>\nAs lojas e PDFs abaixo não parearam automaticamente.\n\n"
    texto += "🏬 <b>Lojas Pendentes:</b>\n"
    for i, loja in enumerate(lojas):
        texto += f"<b>{i}</b> - {loja['loja']}\n"
        
    texto += "\n📄 <b>PDFs Sobrando:</b>\n"
    for i, pdf in enumerate(pdfs):
        letra = chr(65 + (i % 26)) + (str(i // 26) if i >= 26 else "")
        texto += f"<b>{letra}</b> - {pdf}\n"
        
    texto += "\nPara associar, digite o número da loja e a letra do PDF (Ex: <b>0A</b>, <b>1B</b>).\nSe não houver mais associações, clique em Encerrar."
    
    teclado = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Encerrar e Ir para o Resumo ⏭️"), KeyboardButton(text="Cancelar ❌")]],
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
    if message.text == "Encerrar e Ir para o Resumo ⏭️":
        await gerar_resumo_final_notas(message, state)
        return
        
    codigo = message.text.upper().strip()
    match = re.match(r'^(\d+)([A-Z]\d*)$', codigo)
    
    if not match:
        await message.answer("⚠️ Formato inválido. Digite um número seguido de uma letra (Ex: 0A, 1B) ou clique em Encerrar.")
        return
        
    num_idx = int(match.group(1))
    letra_codigo = match.group(2)
    
    data = await state.get_data()
    lojas = data.get('lojas_pendentes', [])
    pdfs = data.get('pdfs_pendentes', [])
    notas_validadas = data.get('notas_validadas', [])
    
    letra_idx = -1
    for i in range(len(pdfs)):
        l = chr(65 + (i % 26)) + (str(i // 26) if i >= 26 else "")
        if l == letra_codigo:
            letra_idx = i
            break
            
    if num_idx >= len(lojas) or letra_idx == -1 or letra_idx >= len(pdfs):
        await message.answer("⚠️ Código não encontrado nas listas atuais. Tente novamente.")
        return
        
    loja_selecionada = lojas.pop(num_idx)
    pdf_selecionado = pdfs.pop(letra_idx)
    
    notas_validadas.append({'loja': loja_selecionada['loja'], 'email': loja_selecionada['email'], 'pdf': pdf_selecionado, 'tipo': 'manual'})
    if EXIBIR_LOGS: logger.info(f"✅ Pareamento manual aceito: {loja_selecionada['loja']} <> {pdf_selecionado}")
    
    await state.update_data(lojas_pendentes=lojas, pdfs_pendentes=pdfs, notas_validadas=notas_validadas)
    await message.answer(f"✅ <b>Associado com sucesso:</b>\n{loja_selecionada['loja']} ↔️ {pdf_selecionado}", parse_mode="HTML")
    
    if lojas and pdfs:
        await enviar_lista_manual(message, state)
    else:
        await gerar_resumo_final_notas(message, state)

async def gerar_resumo_final_notas(message: types.Message, state: FSMContext):
    data = await state.get_data()
    notas_validadas = data.get('notas_validadas', [])
    lojas_pendentes = data.get('lojas_pendentes', [])
    pasta_extracao = data.get('pasta_extracao')
    csv_path = data.get('csv_path_temp')
    caminho_zip = data.get('zip_path_temp')
    
    conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
    cursor = conexao.cursor()
    
    resumo_tabela = ""
    for nota in notas_validadas:
        caminho_completo = os.path.join(pasta_extracao, nota['pdf'])
        cursor.execute('''
            INSERT INTO fila_notas (nome_loja, email_destino, caminho_pdf, status)
            VALUES (?, ?, ?, 'RASCUNHO')
        ''', (nota['loja'], nota['email'], caminho_completo))
        
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
            keyboard=[[KeyboardButton(text="Aprovar Envio ✅"), KeyboardButton(text="Cancelar ❌")]],
            resize_keyboard=True,
            is_persistent=True
        )
        
        if len(resumo) > 3900:
            await message.answer(resumo[:3900] + "\n\n[...Lista truncada devido ao limite de texto...]", parse_mode="HTML", reply_markup=teclado_aprovacao)
        else:
            await message.answer(resumo, parse_mode="HTML", reply_markup=teclado_aprovacao)
            
        await state.set_state(PainelNotasFluxo.aguardando_aprovacao)
    else:
        resumo_falha = f"⚠️ <b>Nenhuma nota foi combinada com sucesso.</b>\n\n❌ <b>Lojas pendentes ({len(lojas_pendentes)}):</b>\n"
        for loja in lojas_pendentes:
            resumo_falha += f"   - {loja['loja']}\n"
        await message.answer(resumo_falha[:3900], parse_mode="HTML")
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
