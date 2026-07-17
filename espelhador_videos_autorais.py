# 0. CONFIGURAÇÕES INICIAIS
EXIBIR_LOGS = True

import os
import asyncio
import logging
import json
import random
import time
import hashlib
import aiohttp
import re
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils import registrar_erro_json

load_dotenv()

# ✅ Cria as pastas isoladas na inicialização
os.makedirs("temp", exist_ok=True)
os.makedirs("archive", exist_ok=True)

# Expressão regular para encontrar links da Shopee na legenda
PADRAO_SHOPEE = re.compile(r'(https?://(?:s\.shopee\.com\.br|shope\.ee|br\.shp\.ee|shp\.ee)/[^\s]+)')

# Chaves da Shopee
SHOPEE_APP_ID = os.getenv('SHOPEE_APP_ID')
SHOPEE_APP_SECRET = os.getenv('SHOPEE_APP_SECRET')

# Inicialização do Agendador
scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

if EXIBIR_LOGS:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    logger = logging.getLogger(__name__)

# 1. CREDENCIAIS E CONFIGURAÇÕES
API_ID = int(os.getenv('API_ID', 0)) 
API_HASH = os.getenv('API_HASH', '')

def carregar_config_autorais():
    try:
        with open("autorais_config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Valores de segurança caso o arquivo ainda não exista
        return {"origem": -1003673555953, "destino": "@videos_autorais"}

def salvar_config_autorais(config):
    with open("autorais_config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

config_atual = carregar_config_autorais()

NOME_SESSAO = 'sessao_espelhador_isolado'
client = TelegramClient(NOME_SESSAO, API_ID, API_HASH)

def ler_fila_retorno():
    try:
        with open("fila_retorno.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def salvar_fila_retorno(dados):
    with open("fila_retorno.json", "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

async def converter_link_shopee(link_original):
    if not SHOPEE_APP_ID or not SHOPEE_APP_SECRET:
        if EXIBIR_LOGS: logger.warning("⏳ Chaves da Shopee ausentes. A manter o link original.")
        return link_original

    link_processar = link_original
    if "shp.ee" in link_original or "shope.ee" in link_original or "s.shopee.com.br" in link_original:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(link_original, allow_redirects=True) as resp:
                    link_processar = str(resp.url)
                    # Limpeza vital para remover rastreadores do afiliado anterior
                    link_processar = link_processar.split('?')[0]
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro ao expandir URL: {e}")

    timestamp = int(time.time())
    endpoint = "https://open-api.affiliate.shopee.com.br/graphql"
    payload = {
        "query": "mutation generateShortLink($originUrl: String!, $subIds: [String]) { generateShortLink(input: {originUrl: $originUrl, subIds: $subIds}) { shortLink } }",
        "variables": {
            "originUrl": link_processar,
            "subIds": ["autorais"]
        }
    }
    payload_json = json.dumps(payload, separators=(',', ':'))
    fator_base = f"{SHOPEE_APP_ID}{timestamp}{payload_json}{SHOPEE_APP_SECRET}"
    assinatura = hashlib.sha256(fator_base.encode('utf-8')).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={SHOPEE_APP_ID}, Timestamp={timestamp}, Signature={assinatura}"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, data=payload_json) as response:
                resposta_dados = await response.json()
                if response.status == 200 and "data" in resposta_dados and resposta_dados["data"].get("generateShortLink"):
                    novo_link = resposta_dados["data"]["generateShortLink"]["shortLink"]
                    if EXIBIR_LOGS: logger.info(f"✅ Link de afiliado gerado com sucesso: {novo_link}")
                    return novo_link
                else:
                    if EXIBIR_LOGS: logger.error(f"❌ A API da Shopee recusou a conversão: {resposta_dados}")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro de comunicação com a Shopee: {e}")
        
    return link_original

@client.on(events.NewMessage(from_users='me', pattern=r'^/status_autorais|^/set_origem|^/set_destino'))
async def menu_comandos_autorais(event):
    global config_atual
    texto = event.raw_text.strip().split()
    comando = texto[0]

    if comando == '/status_autorais':
        if EXIBIR_LOGS: logger.info("⚙️ Comando /status_autorais acionado.")
        msg = (f"🤖 <b>Painel do Bot Vídeos Autorais</b>\n\n"
               f"📥 <b>Origem atual:</b> <code>{config_atual['origem']}</code>\n"
               f"📤 <b>Destino atual:</b> <code>{config_atual['destino']}</code>\n\n"
               f"<i>Para configurar, envie no chat:</i>\n"
               f"<code>/set_origem [ID numérico ou @username]</code>\n"
               f"<code>/set_destino [ID numérico ou @username]</code>")
        await event.reply(msg, parse_mode="html")

    elif comando == '/set_origem':
        if len(texto) > 1:
            novo_valor = int(texto[1]) if texto[1].lstrip('-').isdigit() else texto[1]
            config_atual['origem'] = novo_valor
            salvar_config_autorais(config_atual)
            if EXIBIR_LOGS: logger.info(f"✅ Nova origem definida via chat: {novo_valor}")
            await event.reply(f"✅ <b>Origem atualizada com sucesso!</b>\nO robô agora escutará: <code>{novo_valor}</code>", parse_mode="html")
        else:
            await event.reply("⚠️ Comando incompleto. Tente: <code>/set_origem -100123456789</code>", parse_mode="html")

    elif comando == '/set_destino':
        if len(texto) > 1:
            novo_valor = int(texto[1]) if texto[1].lstrip('-').isdigit() else texto[1]
            config_atual['destino'] = novo_valor
            salvar_config_autorais(config_atual)
            if EXIBIR_LOGS: logger.info(f"✅ Novo destino definido via chat: {novo_valor}")
            await event.reply(f"✅ <b>Destino atualizado com sucesso!</b>\nOs vídeos serão enviados para: <code>{novo_valor}</code>", parse_mode="html")
        else:
            await event.reply("⚠️ Comando incompleto. Tente: <code>/set_destino @seu_canal</code>", parse_mode="html")

@client.on(events.NewMessage())
async def interceptar_e_espelhar(event):
    config_atual = carregar_config_autorais() # ✅ Essa linha obriga o robô a ler a sua alteração em tempo real
    chat = await event.get_chat()
    origem_configurada = config_atual['origem']
    
    eh_origem = False  # 🐛 Correção: Garante que a variável exista desde o início
    
    if isinstance(origem_configurada, int) and getattr(event, 'chat_id', None) == origem_configurada:
        eh_origem = True
    elif isinstance(origem_configurada, str):
        username_chat = getattr(chat, 'username', None)
        if username_chat and f"@{username_chat}".lower() == origem_configurada.lower():
            eh_origem = True
            
    if not eh_origem:
        return

    if EXIBIR_LOGS: logger.info("🔍 Nova postagem detetada no grupo de origem configurado.")

    if getattr(event, 'media', None) is None:
        return

    if isinstance(event.media, MessageMediaDocument):
        texto_original = event.text or ""
        match_shopee = PADRAO_SHOPEE.search(texto_original)
        
        if not match_shopee:
            if EXIBIR_LOGS: logger.info("⏭️ Postagem ignorada: Não contém link da Shopee.")
            return

        link_capturado = match_shopee.group(1).rstrip(").,;!?")
        if EXIBIR_LOGS: logger.info("🔗 A converter o link da Shopee para o seu ID de afiliado...")
        link_novo = await converter_link_shopee(link_capturado)
        texto_convertido = texto_original.replace(link_capturado, link_novo)

        if EXIBIR_LOGS: logger.info("📥 Iniciando o download do vídeo...")
        caminho_video = await event.download_media(file="temp/temp_espelho_isolado_")
        
        if caminho_video:
            try:
                msg_enviada = await client.send_file(
                    config_atual['destino'],
                    file=caminho_video,
                    caption=texto_convertido,
                    parse_mode="html"
                )
                if EXIBIR_LOGS: logger.info("🚀 Vídeo publicado no canal de destino com o link atualizado!")
                
                # Regra dos 15 dias e limite de 5 vídeos
                data_alvo = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")
                fila_dados = ler_fila_retorno()
                if data_alvo not in fila_dados:
                    fila_dados[data_alvo] = []
                    
                if len(fila_dados[data_alvo]) < 5:
                    novo_caminho = f"archive/{os.path.basename(caminho_video)}"
                    os.rename(caminho_video, novo_caminho)
                    
                    fila_dados[data_alvo].append({
                        "msg_id_destino": msg_enviada.id,
                        "legenda": texto_convertido,
                        "caminho_arquivo": novo_caminho 
                    })
                    salvar_fila_retorno(fila_dados)
                    if EXIBIR_LOGS: logger.info(f"📅 Vídeo arquivado em 'archive/' para retorno no dia {data_alvo}.")
                else:
                    try:
                        os.remove(caminho_video)
                        if EXIBIR_LOGS: logger.info(f"⏭️ A cota para {data_alvo} já está cheia. Vídeo removido do disco.")
                    except Exception:
                        pass

            except Exception as e:
                if EXIBIR_LOGS: logger.error(f"❌ Falha ao tentar enviar o vídeo: {e}")
                registrar_erro_json(f"interceptar_e_espelhar: {e}", origem="espelhador_videos_autorais.py")
                
                # Etiqueta de Falha
                if os.path.exists(caminho_video):
                    try:
                        os.rename(caminho_video, caminho_video + ".pendente")
                        if EXIBIR_LOGS: logger.info(f"🏷️ Ficheiro isolado para limpeza posterior: {caminho_video}.pendente")
                    except Exception:
                        pass

async def executar_postagem_retorno(caminho_arquivo, legenda):
    if EXIBIR_LOGS: logger.info(f"🚀 [Fluxo] Iniciando retorno do vídeo arquivado: {caminho_arquivo}")
    try:
        if os.path.exists(caminho_arquivo):
            await client.send_file(
                config_atual['origem'],
                file=caminho_arquivo,
                caption=legenda,
                parse_mode="html"
            )
            if EXIBIR_LOGS: logger.info("✅ Vídeo de retorno publicado com sucesso no grupo de origem!")
            
            os.remove(caminho_arquivo)
            if EXIBIR_LOGS: logger.info("🧹 Ficheiro arquivado removido após postagem final.")
        else:
            if EXIBIR_LOGS: logger.warning(f"⚠️ Ficheiro de arquivo não encontrado em {caminho_arquivo}. A postagem falhou.")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha no disparo de retorno: {e}")

def agendar_tarefas_diarias():
    if EXIBIR_LOGS: logger.info("🗓️ A verificar a agenda de retornos do dia...")
    hoje_str = datetime.now().strftime("%Y-%m-%d")
    fila_dados = ler_fila_retorno()
    videos_hoje = fila_dados.get(hoje_str, [])

    if not videos_hoje:
        if EXIBIR_LOGS: logger.info("♻️ Nenhum vídeo antigo agendado para retornar hoje.")
        return

    random.shuffle(videos_hoje)
    agora = datetime.now()
    
    for i, video in enumerate(videos_hoje):
        hora_sorteio = random.randint(10, 20)
        minuto_sorteio = random.randint(0, 59)
        horario_disparo = agora.replace(hour=hora_sorteio, minute=minuto_sorteio, second=0, microsecond=0)
        
        if horario_disparo < agora:
            horario_disparo = agora + timedelta(minutes=random.randint(5, 45))
            
        scheduler.add_job(
            executar_postagem_retorno, 
            'date', 
            run_date=horario_disparo, 
            args=[video.get("caminho_arquivo", ""), video.get("legenda", "")] 
        )
        if EXIBIR_LOGS: logger.info(f"⏳ Vídeo de retorno {i+1} agendado para as {horario_disparo.strftime('%H:%M')}.")

    del fila_dados[hoje_str]
    salvar_fila_retorno(fila_dados)

async def main():
    if EXIBIR_LOGS: logger.info("⏳ Iniciando o robô Espelhador Isolado...")
    await client.start()
    
    if EXIBIR_LOGS: logger.info("🔄 Sincronizando banco de dados de grupos...")
    try:
        await client.get_dialogs()
        if EXIBIR_LOGS: logger.info("✅ Sincronização concluída! ID do grupo reconhecido.")
    except Exception as e:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Aviso na sincronização: {e}")

    scheduler.add_job(agendar_tarefas_diarias, 'cron', hour=1, minute=0)
    agendar_tarefas_diarias()
    scheduler.start()
    
    if EXIBIR_LOGS: logger.info("🤖 Sistema a rodar. A escutar o grupo de origem continuamente...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
