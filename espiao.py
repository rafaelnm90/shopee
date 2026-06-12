import os
import json
import logging
import asyncio
import re
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument
from dotenv import load_dotenv

load_dotenv()
EXIBIR_LOGS = True

# 1. CREDENCIAIS DA CONTA
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')

if EXIBIR_LOGS:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    logger = logging.getLogger(__name__)

client = TelegramClient('sessao_espiao', API_ID, API_HASH)

def carregar_alvos():
    try:
        with open("alvos_espiao.json", "r") as f:
            dados = json.load(f)
            return dados.get("alvos", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def salvar_na_fila_clonagem(caminho_video, link_shopee):
    arquivo_fila = "fila_clonagem.json"
    try:
        with open(arquivo_fila, "r") as f:
            dados = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        dados = {"fila": []}
        
    item = {
        "id": f"clone_{int(datetime.now().timestamp())}",
        "caminho_video": caminho_video,
        "link_original": link_shopee,
        "processado": False,
        "data_captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    dados["fila"].append(item)
    with open(arquivo_fila, "w") as f:
        json.dump(dados, f, indent=4)
    if EXIBIR_LOGS: logger.info(f"📦 Item salvo na fila de clonagem com sucesso (ID: {item['id']}).")

# ✅ O padrão foi ampliado para capturar links com parâmetros complexos e domínios mais curtos
PADRAO_SHOPEE = re.compile(r'(https?://(?:s\.shopee\.com\.br|shope\.ee|br\.shp\.ee|shp\.ee)/[^\s]+)')

@client.on(events.NewMessage)
async def interceptar_mensagem(event):
    alvos = carregar_alvos()
    
    # Verifica se a mensagem veio de um dos grupos monitorados
    chat = await event.get_chat()
    chat_id = str(chat.id)
    chat_username = f"@{chat.username}" if getattr(chat, 'username', None) else ""
    
    # Corrige formatações de IDs que o Telegram envia (com ou sem o -100)
    chat_id_completo = f"-100{chat.id}" if not chat_id.startswith("-100") else chat_id
    
    if chat_username not in alvos and chat_id not in alvos and chat_id_completo not in alvos:
        return

    texto = event.raw_text
    match = PADRAO_SHOPEE.search(texto)
    
    # Ignora mensagens de bate-papo, processa apenas se tiver link e mídia de vídeo
    if match:
        link_capturado = match.group(1)
        
        # Limpa pontuações que possam ter ficado agarradas ao final do link
        link_capturado = link_capturado.rstrip(").,;!?")
        
        if event.media and isinstance(event.media, MessageMediaDocument):
            if event.file.mime_type and 'video' in event.file.mime_type:
                if EXIBIR_LOGS: logger.info(f"🎯 ALVO LOCALIZADO! Link da Shopee extraído cirurgicamente: {link_capturado}")
                
                if "magazineluiza" in texto.lower() or "meli.li" in texto.lower() or "mercadolivre" in texto.lower():
                    if EXIBIR_LOGS: logger.info("✂️ Concorrência ignorada: A postagem continha outros domínios, mas apenas o da Shopee foi filtrado.")
                
                if EXIBIR_LOGS: logger.info("📥 Iniciando download do vídeo em segundo plano...")
                caminho_salvo = await event.download_media(file="temp_clone_")
                
                salvar_na_fila_clonagem(caminho_salvo, link_capturado)
            else:
                if EXIBIR_LOGS: logger.info(f"⏭️ Ignorado: O link {link_capturado} foi encontrado, mas o anexo não é um formato de vídeo suportado.")
        else:
            if EXIBIR_LOGS: logger.info(f"⏭️ Ignorado: O link {link_capturado} foi encontrado, mas a postagem não contém um anexo de vídeo direto.")

async def main():
    if EXIBIR_LOGS: logger.info("🕵️ Iniciando o Módulo Espião de Clonagem...")
    await client.start()
    alvos = carregar_alvos()
    if EXIBIR_LOGS: logger.info(f"📡 Radar ativo para {len(alvos)} concorrentes.")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
