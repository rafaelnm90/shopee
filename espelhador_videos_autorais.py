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

# Expressão regular aprimorada (ignora maiúsculas e aceita sem http)
PADRAO_SHOPEE = re.compile(r'(?:https?://)?(?:s\.shopee\.com\.br|shope\.ee|br\.shp\.ee|shp\.ee)/[^\s]+', re.IGNORECASE)

def extrair_link_shopee(event):
    """Busca links no texto puro e dentro de hiperlinks escondidos no Telegram"""
    if EXIBIR_LOGS: logger.info("🔍 Analisando mensagem em busca de links...")
    texto = event.raw_text or ""
    match = PADRAO_SHOPEE.search(texto)
    if match:
        link = match.group(0)
        if not link.startswith("http"):
            link = "https://" + link
        if EXIBIR_LOGS: logger.info("✅ Link encontrado no texto visível.")
        return link.rstrip(").,;!?")
        
    if event.entities:
        for entity in event.entities:
            if hasattr(entity, 'url') and entity.url:
                if PADRAO_SHOPEE.search(entity.url):
                    if EXIBIR_LOGS: logger.info("✅ Link encontrado embutido/escondido na formatação.")
                    return entity.url
    if EXIBIR_LOGS: logger.info("⏭️ Nenhum link válido da Shopee encontrado.")
    return None

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

API_ID = int(os.getenv('API_ID', 0))
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
            # Máscara de navegador para a Shopee não bloquear a leitura do link curto
            headers_redirect = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            async with aiohttp.ClientSession() as session:
                async with session.get(link_original, allow_redirects=True, headers=headers_redirect) as resp:
                    link_processar = str(resp.url).split('?')[0]
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro ao expandir URL: {e}")

    timestamp = int(time.time())
    endpoint = "https://open-api.affiliate.shopee.com.br/graphql"
    
    # Payload limpo, idêntico ao do seu Robô Espião (100% de aceitação)
    payload = {
        "query": "mutation generateShortLink($originUrl: String!) { generateShortLink(input: {originUrl: $originUrl}) { shortLink } }",
        "variables": {
            "originUrl": link_processar
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

async def validar_chat(valor):
    """Tenta acessar o chat para garantir que ele existe e o robô tem permissão"""
    try:
        alvo = int(valor) if str(valor).lstrip('-').isdigit() else valor
        entidade = await client.get_entity(alvo)
        nome = getattr(entidade, 'title', getattr(entidade, 'username', str(valor)))
        return True, nome, alvo
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha ao validar acesso ao chat {valor}: {e}")
        return False, str(e), None

@client.on(events.NewMessage(func=lambda e: e.is_private, pattern=r'^/status_autorais|^/set_origem|^/set_destino|^/set_topico'))
async def menu_comandos_autorais(event):
    global config_atual
    texto = event.raw_text.strip().split()
    comando = texto[0]

    if comando == '/status_autorais':
        if EXIBIR_LOGS: logger.info("⚙️ Comando /status_autorais acionado via chat privado.")
        
        sucesso_orig, nome_origem, _ = await validar_chat(config_atual.get('origem'))
        texto_origem = nome_origem if sucesso_orig else "ID Inválido ou Sem Acesso"
        
        sucesso_dest, nome_destino, _ = await validar_chat(config_atual.get('destino'))
        texto_destino = nome_destino if sucesso_dest else "ID Inválido ou Sem Acesso"
        
        topico = config_atual.get('origem_topico', 'Todos (Geral)')
        
        msg = (f"🤖 <b>Painel do Bot Vídeos Autorais</b>\n\n"
               f"📥 <b>Origem atual:</b> <code>{config_atual.get('origem')}</code>\n"
               f"🏷️ <i>{texto_origem}</i>\n"
               f"📂 <b>Tópico (Subcanal):</b> <code>{topico}</code>\n\n"
               f"📤 <b>Destino atual:</b> <code>{config_atual.get('destino')}</code>\n"
               f"🏷️ <i>{texto_destino}</i>\n\n"
               f"<i>Para configurar, envie no chat:</i>\n"
               f"<code>/set_origem [ID numérico ou @username]</code>\n"
               f"<code>/set_topico [ID numérico do tópico, ex: 1]</code>\n"
               f"<code>/set_destino [ID numérico ou @username]</code>")
        await event.reply(msg, parse_mode="html")

    elif comando == '/set_origem':
        if len(texto) > 1:
            valor_entrada = texto[1]
            await event.reply("⏳ <b>Validando grupo de origem...</b>", parse_mode="html")
            sucesso, nome_chat, id_real = await validar_chat(valor_entrada)
            
            if sucesso:
                config_atual['origem'] = id_real
                salvar_config_autorais(config_atual)
                if EXIBIR_LOGS: logger.info(f"✅ Nova origem definida e validada: {id_real} ({nome_chat})")
                await event.reply(f"✅ <b>Origem verificada e salva com sucesso!</b>\n🏷️ <b>{nome_chat}</b>\n🆔 <code>{id_real}</code>", parse_mode="html")
            else:
                await event.reply("❌ <b>Erro:</b> O perfil secundário não conseguiu encontrar ou não tem acesso a esse grupo.\nVerifique se o ID está correto e se a conta faz parte do grupo.", parse_mode="html")
        else:
            await event.reply("⚠️ Comando incompleto. Tente: <code>/set_origem -100123456789</code>", parse_mode="html")

    elif comando == '/set_topico':
        if len(texto) > 1:
            novo_topico = int(texto[1]) if texto[1].isdigit() else None
            if novo_topico is not None:
                config_atual['origem_topico'] = novo_topico
                salvar_config_autorais(config_atual)
                if EXIBIR_LOGS: logger.info(f"✅ Novo tópico definido: {novo_topico}")
                await event.reply(f"✅ <b>Tópico atualizado!</b>\nO robô escutará apenas o subcanal: <code>{novo_topico}</code>", parse_mode="html")
            else:
                await event.reply("⚠️ ID de tópico inválido. Use apenas números. Ex: <code>/set_topico 1</code>", parse_mode="html")
        else:
            config_atual['origem_topico'] = None
            salvar_config_autorais(config_atual)
            await event.reply("✅ <b>Filtro de tópico removido!</b> O robô agora lerá todos os subcanais deste grupo.", parse_mode="html")

    elif comando == '/set_destino':
        if len(texto) > 1:
            valor_entrada = texto[1]
            await event.reply("⏳ <b>Validando canal de destino...</b>", parse_mode="html")
            sucesso, nome_chat, id_real = await validar_chat(valor_entrada)
            
            if sucesso:
                config_atual['destino'] = id_real
                salvar_config_autorais(config_atual)
                if EXIBIR_LOGS: logger.info(f"✅ Novo destino definido e validado: {id_real} ({nome_chat})")
                await event.reply(f"✅ <b>Destino verificado e salvo com sucesso!</b>\n🏷️ <b>{nome_chat}</b>\n🆔 <code>{id_real}</code>", parse_mode="html")
            else:
                await event.reply("❌ <b>Erro:</b> O perfil secundário não encontrou ou não tem permissão para postar nesse destino.", parse_mode="html")
        else:
            await event.reply("⚠️ Comando incompleto. Tente: <code>/set_destino @seu_canal</code>", parse_mode="html")

@client.on(events.NewMessage())
async def interceptar_e_espelhar(event):
    config_atual = carregar_config_autorais() # Lendo a configuração em tempo real
    chat = await event.get_chat()
    origem_configurada = config_atual.get('origem')
    topico_configurado = config_atual.get('origem_topico')
    
    eh_origem = False  
    
    if isinstance(origem_configurada, int) and getattr(event, 'chat_id', None) == origem_configurada:
        eh_origem = True
    elif isinstance(origem_configurada, str):
        username_chat = getattr(chat, 'username', None)
        if username_chat and f"@{username_chat}".lower() == origem_configurada.lower():
            eh_origem = True

    # ✅ VERIFICAÇÃO DE TÓPICO (Subcanal)
    if eh_origem and topico_configurado:
        topic_id = None
        if event.message.reply_to:
            topic_id = getattr(event.message.reply_to, 'forum_topic_id', getattr(event.message.reply_to, 'reply_to_msg_id', None))
        
        # O Tópico "Geral" do Telegram costuma ser o ID 1 ou vir nulo na API
        if topico_configurado == 1 and topic_id is None:
            pass 
        elif topic_id != topico_configurado:
            eh_origem = False
            
    if not eh_origem:
        return

    if EXIBIR_LOGS: logger.info("🔍 Nova postagem detetada no grupo/tópico de origem configurado.")

    if getattr(event, 'media', None) is None:
        return

    if isinstance(event.media, MessageMediaDocument):
        texto_original = event.text or ""
        link_capturado = extrair_link_shopee(event)
        
        if not link_capturado:
            if EXIBIR_LOGS: logger.info("⏭️ Postagem ignorada: Não contém link da Shopee (nem embutido).")
            return

        if EXIBIR_LOGS: logger.info("🔗 A converter o link da Shopee para o seu ID de afiliado...")
        link_novo = await converter_link_shopee(link_capturado)
        
        # ✅ Novo motor de substituição: Mantém a formatação original (negritos/emojis) e troca o link à força
        texto_html = event.html or ""
        texto_convertido = PADRAO_SHOPEE.sub(link_novo, texto_html)
        
        # Prevenção extra: Se o concorrente escondeu tanto o link que a substituição falhou, injetamos no final
        if link_novo not in texto_convertido:
            texto_convertido += f"\n\n🔗 <b>Link do Produto:</b>\n{link_novo}"

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
