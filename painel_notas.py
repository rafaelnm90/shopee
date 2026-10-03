"""
Disparador de notas fiscais: roteador do bot_mestre (botão "Disparador de Notas").

Fluxo: o admin envia o CSV de comissões da Shopee (loja, e-mail, valor) e um ZIP
com os PDFs das notas ("RNM <loja>.pdf"). O bot casa cada loja com seu PDF pelo
nome (exato; depois por semelhança, com confirmação; por fim manualmente, por
letra), mostra o resumo e, aprovado, manda um e-mail por loja pelo Brevo com a
nota anexada.

Estados na tabela fila_notas: RASCUNHO (lote montado, esperando aprovação) →
PENDENTE (aprovado) → ENVIADO ou ERRO.

Filtro anti-duplicidade: PDF com nome já ENVIADO ou PENDENTE é ignorado (os nomes
mudam a cada mês). Pode ser desligado pelo menu; volta sozinho depois de 5 minutos
ou depois de um lote.
"""
FILTRO_ANTI_DUPLICIDADE = True  # estado inicial; o botão do menu alterna em tempo de execução
import os
import zipfile
import pandas as pd
import asyncio
import aiohttp
import sqlite3
import db
import base64
import time
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

BREVO_API_KEY = os.getenv('BREVO_API_KEY')
EMAIL_REMETENTE = os.getenv('EMAIL_REMETENTE_NOTAS')
NOME_REMETENTE = os.getenv('NOME_REMETENTE_NOTAS')
EMAIL_ADMIN = 'rafaelnovaismiranda@gmail.com'

# Máximo de e-mails por rodada de envio; ao atingir, pausa PAUSA_HORAS horas e retoma
# sozinho. A contagem é por rodada: uma rodada nova recomeça do zero.
LIMITE_DIARIO = 290
PAUSA_HORAS = 26

logger = logging.getLogger("PainelNotas")

router = Router()
bot_instance = None
scheduler_instance = None

def garantir_tabela_fila_notas():
    """Cria a fila de envio de notas, se faltar. A coluna valor é acrescentada ao gravar o primeiro lote."""
    conexao = db.conectar()
    try:
        conexao.execute('''
            CREATE TABLE IF NOT EXISTS fila_notas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_loja TEXT,
                email_destino TEXT,
                caminho_pdf TEXT,
                status TEXT DEFAULT 'PENDENTE',
                motivo_erro TEXT
            )
        ''')
        conexao.commit()
    finally:
        conexao.close()

def _ler_retomada():
    """Horário salvo da retomada automática (datetime) ou None."""
    try:
        conexao = db.conectar()
        try:
            linha = conexao.execute("SELECT valor FROM configuracoes WHERE chave = 'retomada_notas'").fetchone()
        finally:
            conexao.close()
        return datetime.fromisoformat(linha[0]) if linha and linha[0] else None
    except Exception:
        return None


def _salvar_retomada(quando):
    """Grava o horário da retomada automática; None apaga. Falha só vai para o log."""
    try:
        conexao = db.conectar()
        try:
            if quando is None:
                conexao.execute("DELETE FROM configuracoes WHERE chave = 'retomada_notas'")
            else:
                conexao.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('retomada_notas', ?)",
                                (quando.isoformat(),))
            conexao.commit()
        finally:
            conexao.close()
    except Exception as e:
        logger.error(f"❌ [Notas] Não consegui gravar a retomada automática: {e}")


def _restaurar_retomada():
    """
    Reagenda a retomada da pausa de 26 h depois de um reinício, já que o
    agendador só guarda jobs na memória. Se o horário já passou, retoma em 1 min.
    """
    quando = _ler_retomada()
    if quando is None or scheduler_instance is None:
        return
    conexao = db.conectar()
    try:
        pendentes = conexao.execute("SELECT COUNT(*) FROM fila_notas WHERE status = 'PENDENTE'").fetchone()[0]
    finally:
        conexao.close()
    if not pendentes:
        _salvar_retomada(None)
        return
    quando = max(quando, datetime.now() + timedelta(minutes=1))
    scheduler_instance.add_job(processar_fila_envios, 'date', run_date=quando, kwargs={"retomada": True},
                               id='retomada_notas', replace_existing=True)
    logger.info(f"⏰ [Notas] Retomada de {pendentes} nota(s) pendente(s) reagendada para {quando.strftime('%d/%m %H:%M')}.")


def configurar_dependencias(bot: Bot, scheduler):
    """Recebe o bot e o agendador do bot_mestre, cria a tabela e restaura a retomada pendente."""
    global bot_instance, scheduler_instance
    bot_instance = bot
    scheduler_instance = scheduler
    garantir_tabela_fila_notas()
    try:
        _restaurar_retomada()
    except Exception as e:
        logger.error(f"❌ [Notas] Não consegui restaurar a retomada automática: {e}")
    logger.info("🔌 Conexão estabelecida: Dependências do Disparador de Notas injetadas com sucesso.")

class PainelNotasFluxo(StatesGroup):
    menu_principal = State()
    aguardando_csv = State()
    aguardando_zip = State()
    revisando_similares = State()
    pareamento_manual = State()
    inspecionando_pdf_manual = State()  
    aguardando_aprovacao = State()
    inspecionando_pdf_final = State()   
    enviando_notas = State()  # bloqueio da tela durante o envio (ver ignorar_durante_envio)

def obter_teclado_menu_notas():
    status_filtro = "LIGADO 🟢" if FILTRO_ANTI_DUPLICIDADE else "DESLIGADO 🔴"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Iniciar Envios 🚀")],
            [KeyboardButton(text=f"Filtro Anti-Duplicidade: {status_filtro}")],
            [KeyboardButton(text="Informações de Acesso ℹ️")],
            [KeyboardButton(text="Voltar aos Relatórios 🔙")]
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
    """Texto para comparar nomes: sem acento, minúsculo, só letras, números e espaços simples."""
    if not isinstance(texto, str):
        return ""
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    texto = texto.lower()
    texto = re.sub(r'[^a-z0-9\s]', ' ', texto)
    return re.sub(r'\s+', ' ', texto).strip()

async def enviar_email_brevo(para_email, para_nome, assunto, corpo_html, caminho_anexo=None):
    """E-mail HTML pelo Brevo, com o arquivo anexado se ele existir. Devolve (status HTTP, resposta)."""
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

async def _liberar_painel(chat_id):
    """Devolve o teclado de Relatórios, que a aprovação tira da tela durante o envio."""
    if not bot_instance:
        return
    teclado_outros = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Relatório Financeiro 💰"), KeyboardButton(text="Diagnóstico de IA 🧠")],
            [KeyboardButton(text="Relatórios de Filas 📋"), KeyboardButton(text="Logs de Erros ⚠️")],
            [KeyboardButton(text="Disparador de Notas 🧾")],
            [KeyboardButton(text="Voltar ao Início 🔙")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    try:
        await bot_instance.send_message(chat_id, "O painel principal está liberado.", reply_markup=teclado_outros)
    except Exception: pass


# Uma rodada de envio por vez: duas rodadas juntas leriam as mesmas notas PENDENTE
# e mandariam cada uma duas vezes.
_trava_envio = asyncio.Lock()


async def processar_fila_envios(msg_progresso: types.Message = None, retomada=False):
    """
    Porta de entrada do envio de notas: uma rodada por vez e respeito à pausa de
    segurança. Se outra rodada está em andamento, esta espera ela terminar. Com a
    pausa ativa, uma rodada pedida pela aprovação não envia nada: as notas ficam
    PENDENTE e saem na retomada automática (agendada com retomada=True).
    """
    if _trava_envio.locked():
        logger.info("⏳ [Notas] Já há um envio em andamento; este lote espera ele terminar.")
        if msg_progresso:
            try:
                await msg_progresso.edit_text("⏳ <i>Há um envio em andamento. Este lote sai assim que ele terminar.</i>", parse_mode="HTML")
            except Exception:
                pass

    async with _trava_envio:
        pausa_ate = _ler_retomada()
        if not retomada and pausa_ate and pausa_ate > datetime.now():
            logger.info(f"⏸️ [Notas] Pausa ativa até {pausa_ate.strftime('%d/%m %H:%M')}; as notas aprovadas saem na retomada.")
            if msg_progresso:
                try:
                    await msg_progresso.edit_text(
                        f"⏸️ <b>Pausa de segurança ativa</b> até {pausa_ate.strftime('%d/%m às %H:%M')}.\n"
                        "As notas aprovadas ficaram na fila e saem na retomada automática.",
                        parse_mode="HTML")
                except Exception:
                    pass
                await _liberar_painel(msg_progresso.chat.id)
            return
        await _enviar_pendentes(msg_progresso)


async def _enviar_pendentes(msg_progresso: types.Message = None):
    """
    Envia por e-mail todas as notas PENDENTE, uma por segundo, e apaga o PDF de
    cada nota enviada. msg_progresso, se vier, é editada a cada nota.

    Ao chegar a LIMITE_DIARIO envios na rodada, pausa: agenda a retomada para
    PAUSA_HORAS depois (salva no banco para sobreviver a reinício), avisa o admin
    por e-mail e sai. Ao esvaziar a fila, apaga a pasta de extração, varre pastas
    antigas e manda o resumo ao admin.
    """
    logger.info("🚀 Iniciando esteira de disparos de notas fiscais...")
    
    conexao = db.conectar()
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
        
        # Progresso na tela: a mesma mensagem é editada a cada nota.
        if msg_progresso:
            try:
                loja_segura = str(loja).replace('<', '').replace('>', '')  # o nome vai num texto HTML
                status_dinamico = f"🚀 <i>Disparando notas fiscais...</i>\n⏳ Enviando nota ({idx}/{total_notas}): <code>{loja_segura}</code>"
                await msg_progresso.edit_text(status_dinamico, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao atualizar interface do Telegram: {e}")
                pass

        if envios_realizados >= LIMITE_DIARIO:
            logger.warning(f"⏳ Limite diário atingido. Programando retomada para {PAUSA_HORAS} horas.")
            agora = datetime.now()
            retomada = agora + timedelta(hours=PAUSA_HORAS)
            scheduler_instance.add_job(processar_fila_envios, 'date', run_date=retomada, kwargs={"retomada": True},
                                       id='retomada_notas', replace_existing=True)
            _salvar_retomada(retomada)

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
                    logger.warning(f"⚠️ Erro ao atualizar mensagem de pausa no Telegram: {e}")
                    pass
                await _liberar_painel(msg_progresso.chat.id)
            return

        assunto = f"Sua Nota Fiscal de Comissão Shopee - {loja}"
        corpo = (
            f"<p>Olá, equipe da <b>{loja}</b>.</p>"
            f"<p>Envio em anexo a Nota Fiscal de prestação de serviços referente às comissões geradas através do programa de afiliados da Shopee, no valor de R$ {valor}. O documento já está processado e pode ser direcionado para o controle contábil e financeiro da empresa.</p>"
            f"<p>Fico à disposição caso precisem de algum esclarecimento.</p>"
            f"<p>Atenciosamente,<br><b>RNM Comércio e Intermediações LTDA</b></p>"
        )
        
        logger.info(f"⚙️ Processando envio para Loja: {loja} no valor de R$ {valor}...")

        # Sem o PDF, o e-mail sairia sem a nota: marca como erro em vez de enviar.
        if not pdf or not os.path.exists(pdf):
            erro_msg = f"PDF não encontrado no disco ({os.path.basename(pdf or '') or 'sem caminho'})"
            cursor.execute("UPDATE fila_notas SET status = 'ERRO', motivo_erro = ? WHERE id = ?", (erro_msg, id_registro))
            conexao.commit()
            erros += 1
            falhas_etapa.append(f"⚠️ Falha ao processar loja {loja}: {erro_msg}")
            logger.error(f"❌ Nota de {loja} não enviada: {erro_msg}")
            continue

        try:
            status_api, resposta_api = await enviar_email_brevo(email, loja, assunto, corpo, pdf)
            
            if status_api in [200, 201]:
                cursor.execute("UPDATE fila_notas SET status = 'ENVIADO' WHERE id = ?", (id_registro,))
                envios_realizados += 1
                
                logger.info(f"✅ Sucesso: Nota enviada para {loja} ({email}).")
                try: os.remove(pdf)
                except Exception: pass
            else:
                erro_msg = f"Erro API {status_api}: {resposta_api}"
                cursor.execute("UPDATE fila_notas SET status = 'ERRO', motivo_erro = ? WHERE id = ?", (erro_msg, id_registro))
                erros += 1
                falhas_etapa.append(f"⚠️ Falha ao processar loja {loja}: {erro_msg}")
                logger.error(f"❌ Erro ao enviar para {loja}: {erro_msg}")
                
        except Exception as e:
            erro_msg = f"Erro Interno: {e}"
            cursor.execute("UPDATE fila_notas SET status = 'ERRO', motivo_erro = ? WHERE id = ?", (erro_msg, id_registro))
            erros += 1
            falhas_etapa.append(f"⚠️ Erro de rede/crítico na loja {loja}: {e}")
            logger.error(f"❌ Erro Crítico ao enviar para {loja}: {e}")
            
        conexao.commit()
        await asyncio.sleep(1)

    conexao.close()
    _salvar_retomada(None)

    # A pasta de extração é apagada mesmo quando houve erro de envio; senão os PDFs
    # das falhas se acumulam no disco.
    try:
        if pasta_extracao and os.path.exists(pasta_extracao) and "extraido_" in pasta_extracao:
            shutil.rmtree(pasta_extracao)
            logger.info(f"🧹 [Notas] Pasta de extração removida: {pasta_extracao}")
    except Exception as e:
        logger.warning(f"⚠️ [Notas] Não consegui remover {pasta_extracao}: {e}")

    # Também apaga pastas de rodadas antigas que ficaram para trás por erro ou queda.
    try:
        # Pasta com nota ainda pendente (pausa de 26 h) ou em rascunho fica, mesmo antiga.
        conexao = db.conectar()
        try:
            em_uso = {os.path.normpath(os.path.dirname(c)) for (c,) in conexao.execute(
                "SELECT caminho_pdf FROM fila_notas WHERE status IN ('PENDENTE', 'RASCUNHO')") if c}
        finally:
            conexao.close()

        removidas = 0
        if os.path.exists(PASTA_TEMP):
            limite = time.time() - 86400   # poupa as últimas 24h
            for nome in os.listdir(PASTA_TEMP):
                caminho = os.path.join(PASTA_TEMP, nome)
                if not nome.startswith("extraido_") or not os.path.isdir(caminho):
                    continue
                if os.path.getmtime(caminho) > limite or os.path.normpath(caminho) in em_uso:
                    continue
                shutil.rmtree(caminho, ignore_errors=True)
                removidas += 1
        if removidas:
            logger.info(f"🧹 [Notas] {removidas} pasta(s) de extração antiga(s) removida(s).")
    except Exception:
        pass
    
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
            logger.warning(f"⚠️ Erro ao postar conclusão no Telegram: {e}")
            pass
    
    assunto_final = "[Sistema de Notas Shopee] Processo Totalmente Concluído"
    corpo_final = f"<p>Todas as notas pendentes na fila foram processadas.</p><p>Envios realizados nesta etapa: {envios_realizados}</p>"
    if falhas_etapa:
        corpo_final += "<p><b>Erros registrados nesta etapa:</b></p><ul>"
        for f in falhas_etapa: corpo_final += f"<li>{f}</li>"
        corpo_final += "</ul>"
        
    await enviar_email_brevo(EMAIL_ADMIN, "Administrador", assunto_final, corpo_final)
    
    if msg_progresso:
        await _liberar_painel(msg_progresso.chat.id)

# Fluxo no Telegram: menu → CSV → ZIP → pareamento → resumo → aprovação → envio.

@router.message(F.text == "Abortar ❌", StateFilter("*"))
async def abortador_universal_notas(message: types.Message, state: FSMContext):
    """
    "Abortar" em qualquer etapa das notas: volta ao menu. Os rascunhos do lote
    abortado são apagados quando o próximo lote é montado.
    """
    logger.info("❌ Operação de notas abortada pelo usuário.")
    await message.answer("Operação cancelada. Retornando ao menu do disparador...", reply_markup=obter_teclado_menu_notas())
    await state.set_state(PainelNotasFluxo.menu_principal)

@router.message(PainelNotasFluxo.enviando_notas)
async def ignorar_durante_envio(message: types.Message):
    """
    Responde a qualquer mensagem enquanto o estado é enviando_notas. Na prática
    quase não age: processar_aprovacao_envio limpa o estado logo depois de
    iniciar o envio, que segue em segundo plano. Quem impede dois envios ao
    mesmo tempo é a trava em processar_fila_envios.
    """
    await message.answer("⚠️ <b>Aguarde o fim do processo!</b>\nO robô está enviando as notas fiscais passo a passo. Nenhuma outra ação pode ser feita agora.", parse_mode="HTML")

@router.message(F.text == "Disparador de Notas 🧾", StateFilter("*"))
async def iniciar_painel_notas(message: types.Message, state: FSMContext):
    await state.clear()
    logger.info("🧾 Acessando o menu do Disparador de Notas Fiscais.")
    texto = "🧾 <b>Painel do Disparador de Notas</b>\nSelecione uma das opções abaixo:"
    await message.answer(texto, reply_markup=obter_teclado_menu_notas(), parse_mode="HTML")
    await state.set_state(PainelNotasFluxo.menu_principal)

async def reativar_filtro_automaticamente(chat_id):
    """Religa o filtro anti-duplicidade 5 min depois de ser desligado (agendado no menu)."""
    global FILTRO_ANTI_DUPLICIDADE
    if not FILTRO_ANTI_DUPLICIDADE:
        FILTRO_ANTI_DUPLICIDADE = True
        logger.info("⏰ Timer de segurança: Filtro Anti-Duplicidade reativado automaticamente após 5 minutos.")
        try:
            if bot_instance:
                # Manda o teclado de novo para o botão mostrar o estado novo do filtro.
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
    # Mensagem sem texto (ex.: arquivo enviado antes de clicar em Iniciar Envios).
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
        logger.info(f"⚙️ Alternância de segurança: O Filtro Anti-Duplicidade foi alterado para {FILTRO_ANTI_DUPLICIDADE}.")
        
        await message.answer(f"⚙️ O Filtro Anti-Duplicidade foi <b>{estado_texto}</b>.", reply_markup=obter_teclado_menu_notas(), parse_mode="HTML")
        
        if not FILTRO_ANTI_DUPLICIDADE:
            # Desligado: religa sozinho em 5 min (um timer anterior é substituído).
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
            # Ligado na mão: cancela o timer.
            if scheduler_instance and scheduler_instance.get_job('reativar_filtro_notas'):
                scheduler_instance.remove_job('reativar_filtro_notas')
        
    elif "Informações" in opcao:
        logger.info("🔐 Consultando credenciais seguras no .env.")
        
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
        logger.info("🔙 Retornando à gaveta de Relatórios de forma isolada.")
        
        # Volta para o submenu de Relatórios do bot_mestre.
        teclado_relatorios = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Disparador de Notas 🧾")],
                [KeyboardButton(text="Voltar ao Início 🔙")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        await message.answer("Retornando aos Relatórios...", reply_markup=teclado_relatorios)
        await state.clear()
        
    else:
        await message.answer("⚠️ Por favor, escolha uma das opções utilizando os botões do teclado.")

# Sem filtro F.document no decorator, de propósito: um texto enviado por engano
# recebe uma orientação em vez de cair em outro handler.
@router.message(PainelNotasFluxo.aguardando_csv)
async def receber_csv(message: types.Message, state: FSMContext):
    # Texto em vez de arquivo: orienta, salvo se for o Abortar.
    if not message.document:
        if message.text and message.text == "Abortar ❌":
            return  # o abortador_universal_notas cuida
        await message.answer("⚠️ <b>Ação Inválida:</b> Eu estou aguardando o arquivo <b>.csv</b>. Por favor, anexe o documento ou clique em Abortar ❌.", parse_mode="HTML")
        return

    doc = message.document
    if not doc.file_name.lower().endswith('.csv'):
        await message.answer("⚠️ O arquivo enviado não é válido. Por favor, envie um arquivo com o formato <b>.csv</b>.", parse_mode="HTML")
        return
        
    caminho_csv = os.path.join(PASTA_TEMP, doc.file_name)
    await bot_instance.download(doc, destination=caminho_csv)
    
    await state.update_data(csv_path=caminho_csv)
    logger.info(f"✅ Arquivo CSV da Shopee recebido e salvo em {caminho_csv}.")
    
    await message.answer("✅ Arquivo CSV recebido!\n\nAgora envie o arquivo <b>.ZIP</b> contendo todos os PDFs das Notas Fiscais.", parse_mode="HTML", reply_markup=teclado_notas_cancelar)
    await state.set_state(PainelNotasFluxo.aguardando_zip)


@router.message(PainelNotasFluxo.aguardando_zip)
async def receber_zip_e_cruzar(message: types.Message, state: FSMContext):
    """
    Recebe o ZIP, extrai os PDFs e casa cada loja do CSV com um PDF: primeiro por
    nome contido, depois por semelhança (confirmada pelo admin) e por fim à mão.
    """
    global FILTRO_ANTI_DUPLICIDADE
    
    # Texto em vez de arquivo: orienta, salvo se for o Abortar.
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
        logger.info(f"📂 ZIP extraído com sucesso em {pasta_extracao}.")
    except Exception as e:
        logger.error(f"❌ Erro ao descompactar ZIP: {e}")
        await msg_status.edit_text(f"❌ Erro ao descompactar o ZIP: {e}")
        return
        
    try:
        df = pd.read_csv(csv_path, sep=None, engine='python')
    except Exception as e:
        logger.error(f"❌ Erro ao ler CSV: {e}")
        await msg_status.edit_text(f"❌ Erro ao ler o arquivo CSV: {e}")
        return

    if FILTRO_ANTI_DUPLICIDADE:
        await msg_status.edit_text("✅ Extração concluída. Verificando histórico de envios e cruzando dados...")
        
        # PDFs com nome já ENVIADO ou PENDENTE não entram de novo.
        conexao = db.conectar()
        cursor = conexao.cursor()
        cursor.execute("SELECT caminho_pdf FROM fila_notas WHERE status IN ('ENVIADO', 'PENDENTE')")
        historico = cursor.fetchall()
        conexao.close()
        
        pdfs_protegidos = [os.path.basename(row[0]).lower() for row in historico if row[0]]
    else:
        await msg_status.edit_text("✅ Extração concluída. ⚠️ Filtro Anti-Duplicidade DESATIVADO. Cruzando todos os dados...")
        logger.warning("⚠️ Filtro Anti-Duplicidade desligado. O histórico do banco de dados será ignorado.")
        pdfs_protegidos = []
        
        # O filtro desligado vale só para este lote: religa na hora.
        FILTRO_ANTI_DUPLICIDADE = True
        
        if scheduler_instance and scheduler_instance.get_job('reativar_filtro_notas'):
            scheduler_instance.remove_job('reativar_filtro_notas')
            
        await message.answer("🛡️ <b>Segurança Reativada:</b> O Filtro Anti-Duplicidade voltou a ser ligado automaticamente após a importação deste lote.", parse_mode="HTML")

    arquivos_pdf_pasta_brutos = [f for f in os.listdir(pasta_extracao) if f.lower().endswith('.pdf')]
    arquivos_pdf_pasta = []
    qtd_ignorados = 0
    
    for f in arquivos_pdf_pasta_brutos:
        if f.lower() in pdfs_protegidos:
            qtd_ignorados += 1
            # Já enviado antes: apaga o arquivo, que não será usado.
            try:
                os.remove(os.path.join(pasta_extracao, f))
            except Exception:
                pass
        else:
            arquivos_pdf_pasta.append(f)

    notas_validadas = []
    lojas_pendentes = []
    pdfs_pendentes = arquivos_pdf_pasta.copy()
    
    # 1º casamento: o nome da loja (normalizado) contido no nome do PDF ("RNM <loja>.pdf") ou vice-versa.
    for index, row in df.iterrows():
        nome_loja = str(row.get('Nome da loja', '')).strip()
        email_loja = str(row.get('E-mail', '')).strip()
        
        # Valor da comissão, citado no corpo do e-mail.
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
            
    # 2º: para as lojas que sobraram, o PDF mais parecido acima de 75% (difflib), a confirmar.
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
        logger.info("🔍 Inspecionando similaridades de notas fiscais...")
        await enviar_proxima_similaridade(message, state)
    elif lojas_pendentes and pdfs_pendentes:
        logger.info("🛠️ Entrando no modo de pareamento manual de notas fiscais...")
        await enviar_lista_manual(message, state)
    else:
        logger.info("📊 Gerando resumo final do cruzamento...")
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
        logger.info(f"✅ Associação aprovada: {par_atual['loja_dict']['loja']} <> {par_atual['pdf']}")
    else:
        lojas_pendentes.append(par_atual['loja_dict'])
        pdfs_pendentes.append(par_atual['pdf'])
        logger.info(f"❌ Associação recusada: {par_atual['loja_dict']['loja']} <> {par_atual['pdf']}")
        
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
            # Com um PDF só, mostra direto e continua no pareamento.
            pdf_alvo = pdfs[0]
            caminho_completo = os.path.join(pasta_extracao, pdf_alvo)
            try:
                arquivo_telegram = types.FSInputFile(caminho_completo)
                await message.answer_document(arquivo_telegram, caption=f"🔎 <b>Arquivo:</b> {pdf_alvo}\n\n👉 Digite <b>A</b> para associar ou pule a loja.", parse_mode="HTML")
            except Exception as e:
                await message.answer(f"❌ Erro ao enviar o arquivo: {e}")
            return
        
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
    logger.info(f"✅ Pareamento manual aceito: {loja_selecionada['loja']} <> {pdf_selecionado}")
    
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

    # Botão do teclado durante a visualização: repassa para o pareamento.
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
        # Letra inválida: continua no modo de visualização.
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
    """
    Grava o lote casado como RASCUNHO, apaga o CSV e o ZIP e mostra o resumo
    para aprovação. Sem nenhuma nota casada, volta ao menu.
    """
    data = await state.get_data()
    notas_validadas = data.get('notas_validadas', [])
    lojas_pendentes = data.get('lojas_pendentes', [])
    pasta_extracao = data.get('pasta_extracao')
    csv_path = data.get('csv_path_temp')
    caminho_zip = data.get('zip_path_temp')
    
    conexao = db.conectar()
    cursor = conexao.cursor()
    
    try:
        cursor.execute("ALTER TABLE fila_notas ADD COLUMN valor TEXT")
    except sqlite3.OperationalError:
        pass

    # Só existe um lote em aprovação por vez: rascunho que sobrou é de lote abortado
    # (ou interrompido por reinício) e seria enviado junto com este se ficasse.
    cursor.execute("DELETE FROM fila_notas WHERE status = 'RASCUNHO'")

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
    
    resumo = "✅ <b>Validação finalizada!</b>\n\n"
    resumo += "📊 <b>Balanço Geral:</b>\n"
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
    """Na aprovação: "Ver PDF" mostra uma nota; "Aprovar" passa os RASCUNHO para PENDENTE e inicia o envio."""
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

    # Muda de estado antes de tudo, para um segundo clique em Aprovar não iniciar outro envio.
    await state.set_state(PainelNotasFluxo.enviando_notas)

    conexao = db.conectar()
    cursor = conexao.cursor()
    cursor.execute("UPDATE fila_notas SET status = 'PENDENTE' WHERE status = 'RASCUNHO'")
    conexao.commit()
    conexao.close()
    
    # A mensagem de progresso é editada a cada nota e precisa ir sem teclado; por
    # isso o teclado é removido numa mensagem à parte, antes dela.
    await message.answer("⏳ <b>Preparando o motor de envios...</b>", parse_mode="HTML", reply_markup=types.ReplyKeyboardRemove())
    
    msg_dinamica = await message.answer("🚀 <i>Sincronizando com a base de dados...</i>", parse_mode="HTML")
    
    logger.info("⏰ Acionando motor de envio via Brevo.")
    
    # O envio roda em segundo plano e a conversa fica livre.
    asyncio.create_task(processar_fila_envios(msg_progresso=msg_dinamica))
    
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
            return  # continua no modo de visualização
    except ValueError:
        await message.answer("⚠️ Por favor, digite apenas o <b>NÚMERO</b> correspondente à nota (Ex: 1, 2).", parse_mode="HTML")
        return  # continua no modo de visualização

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
