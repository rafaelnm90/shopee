# 0. CONFIGURAÇÕES INICIAIS
EXIBIR_LOGS = True
import os
import json
import logging
import asyncio
import random
from datetime import datetime, timedelta
from telethon import TelegramClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google import genai
from dotenv import load_dotenv
load_dotenv()

# 1. CREDENCIAIS DA CONTA
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
GEMINI_API_KEY = os.getenv('GEMINI_KEY')

# Inicializa o cliente do Google
client_genai = genai.Client(api_key=GEMINI_API_KEY)

# 2. CONFIGURAÇÃO DE LOGS 🚀
if EXIBIR_LOGS:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    logger = logging.getLogger(__name__)

# 3. INICIALIZAÇÃO DO CLIENTE E SCHEDULER
client = TelegramClient('sessao_userbot', API_ID, API_HASH)
scheduler = AsyncIOScheduler()

# 4. FUNÇÕES DE IA E AGENDAMENTO
def carregar_configuracoes():
    try:
        with open("alvos_divulgacao.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        if EXIBIR_LOGS: logger.warning("⚠️ Arquivo alvos_divulgacao.json não encontrado. Aguardando o bot principal criá-lo.")
        return None

async def gerar_texto_divulgacao():
    prompt = (
        "Você atua divulgando um grupo do Telegram para afiliados da Shopee. "
        "Crie UMA ÚNICA FRASE curta, direta e muito chamativa. "
        "A frase deve focar na seguinte promessa: Os vídeos do nosso grupo NÃO geram infração de 'Produto Irrelevante' nem 'Contrafeito'. "
        "Seja criativo e mude as palavras a cada geração. "
        "Comece a frase com ⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️. "
        "Entregue apenas a frase final, sem aspas ou formatações extras."
    )
    try:
        response = await asyncio.to_thread(
            client_genai.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt
        )
        frase_ia = response.text.strip()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao gerar texto com IA: {e}")
        frase_ia = "⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️\nFugindo de ban por Produto Irrelevante ou Contrafeito? Pegue vídeos validados aqui!"

    # Monta o bloco curto com o link obrigatório e a quebra de linha em branco
    bloco_unico = f"{frase_ia}\n\nLINK PARA O GRUPO:👇\nhttps://t.me/shopee_video_afiliado"
    
    # Multiplica o bloco 6 vezes na mesma mensagem, separando por quebras de linha duplas
    texto_multiplicado = "\n\n\n".join([bloco_unico] * 6)
    
    return texto_multiplicado

async def enviar_mensagem(alvo):
    texto = await gerar_texto_divulgacao()
    try:
        entidade = await client.get_entity(alvo)
        
        # Envia a primeira mensagem com o bloco multiplicado
        if EXIBIR_LOGS: logger.info(f"📤 Iniciando disparo em rajada para {alvo}...")
        await client.send_message(entidade, texto)
        
        # Envia as 4 mensagens idênticas adicionais (totalizando 5 envios seguidos)
        for i in range(4):
            await asyncio.sleep(1.5) # Pausa de segurança obrigatória contra bloqueio de flood
            await client.send_message(entidade, texto)
            
        if EXIBIR_LOGS: logger.info(f"✅ Rajada de 5 mensagens enviada com sucesso para {alvo}!")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha ao enviar rajada para {alvo}: {e}")

def programar_envios_da_hora():
    config = carregar_configuracoes()
    if not config or not config.get("alvos"):
        return
        
    if config.get("pausado", False):
        if EXIBIR_LOGS: logger.info("⏸️ Divulgação pausada pelo painel. Pulando sorteio desta hora.")
        return

    alvos = config["alvos"]
    freq = config["frequencia_por_hora"]
    
    agora = datetime.now()
    if EXIBIR_LOGS: logger.info(f"🔄 Sorteando {freq} envios para a hora atual ({agora.hour}h)...")

    for _ in range(freq):
        minuto_sorteado = random.randint(1, 58)
        horario_disparo = agora.replace(minute=minuto_sorteado, second=random.randint(0, 59))
        
        # Impede que horários no passado travem o agendamento, jogando para os próximos minutos
        if horario_disparo < agora:
            horario_disparo = agora + timedelta(minutes=random.randint(1, 5))

        for alvo in alvos:
            scheduler.add_job(enviar_mensagem, 'date', run_date=horario_disparo, args=[alvo])
            
        if EXIBIR_LOGS: logger.info(f"⏰ Disparo para {alvo} agendado para: {horario_disparo.strftime('%H:%M:%S')}")

async def monitorar_comandos():
    while True:
        config = carregar_configuracoes()
        if config and config.get("forcar_disparo"):
            if EXIBIR_LOGS: logger.info("🚀 Comando de DISPARO FORÇADO detectado! Iniciando rajada...")
            
            # Limpa a flag imediatamente no JSON para o bot não ficar repetindo em loop
            config["forcar_disparo"] = False
            with open("alvos_divulgacao.json", "w") as f:
                json.dump(config, f, indent=4)
                
            alvos = config.get("alvos", [])
            for alvo in alvos:
                await enviar_mensagem(alvo)
        await asyncio.sleep(5)

async def main():
    if EXIBIR_LOGS: logger.info("⏳ Iniciando o Userbot de Divulgação...")
    await client.start()
    
    # Inicia a tarefa paralela que vigia o arquivo JSON a cada 5 segundos
    asyncio.create_task(monitorar_comandos())
    
    # Executa imediatamente o agendamento da hora atual ao iniciar o script
    programar_envios_da_hora()
    
    # Agenda a função para rodar toda vez que o relógio virar a hora (minuto 0)
    scheduler.add_job(programar_envios_da_hora, 'cron', minute=0)
    
    scheduler.start()
    if EXIBIR_LOGS: logger.info("🤖 Sistema automático rodando. Pressione Ctrl+C para parar.")
    
    # Mantém a sessão do Telegram aberta escutando os eventos do agendador
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
