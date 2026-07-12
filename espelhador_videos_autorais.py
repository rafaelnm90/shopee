# 0. CONFIGURAÇÕES INICIAIS
EXIBIR_LOGS = True

import os
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument
from dotenv import load_dotenv

load_dotenv()

if EXIBIR_LOGS:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    logger = logging.getLogger(__name__)

# 1. CREDENCIAIS E CONFIGURAÇÕES FIXAS
API_ID = int(os.getenv('API_ID', 0)) 
API_HASH = os.getenv('API_HASH', '')

GRUPO_ORIGEM = -1003673555953 
GRUPO_DESTINO = '@videos_autorais'

NOME_SESSAO = 'sessao_espelhador_isolado'

client = TelegramClient(NOME_SESSAO, API_ID, API_HASH)

@client.on(events.NewMessage(chats=GRUPO_ORIGEM))
async def interceptar_e_espelhar(event):
    if EXIBIR_LOGS: logger.info("🔍 Nova postagem detetada no grupo de origem.")

    if getattr(event, 'media', None) is None:
        if EXIBIR_LOGS: logger.info("⏭️ Postagem ignorada: Não contém um anexo visual.")
        return

    if isinstance(event.media, MessageMediaDocument):
        if EXIBIR_LOGS: logger.info("📥 Iniciando o download do vídeo...")
        caminho_video = await event.download_media(file="temp_espelho_isolado_")
        
        if caminho_video:
            if EXIBIR_LOGS: logger.info("✅ Download concluído. A preparar o envio para o destino...")
            texto_original = event.text or ""
            
            try:
                await client.send_file(
                    GRUPO_DESTINO,
                    file=caminho_video,
                    caption=texto_original,
                    parse_mode="html"
                )
                if EXIBIR_LOGS: logger.info("🚀 Vídeo espelhado com sucesso no grupo de destino!")
            except Exception as e:
                if EXIBIR_LOGS: logger.error(f"❌ Falha ao tentar enviar o vídeo: {e}")
            finally:
                try:
                    os.remove(caminho_video)
                    if EXIBIR_LOGS: logger.info("🧹 Ficheiro de vídeo temporário removido do servidor.")
                except Exception as e:
                    if EXIBIR_LOGS: logger.error(f"❌ Erro ao apagar ficheiro temporário: {e}")
    else:
        if EXIBIR_LOGS: logger.info("⏭️ Mídia ignorada: O formato não corresponde a um vídeo válido.")

async def main():
    if EXIBIR_LOGS: logger.info("⏳ Iniciando o robô Espelhador Isolado...")
    await client.start()
    if EXIBIR_LOGS: logger.info("🤖 Sistema a rodar. A escutar o grupo de origem continuamente...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
