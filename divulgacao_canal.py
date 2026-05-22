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
API_ID = 12054608
API_HASH = '9a18338a2cfdd7cfef97fa86c853bb3b'
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
        "Você é um divulgador chamativo de um grupo gratuito do Telegram para afiliados da Shopee. "
        "Crie um texto de convite agressivo, animado e persuasivo. "
        "REGRA 1: O texto deve focar na seguinte promessa: Os vídeos do nosso grupo NÃO geram infração de 'Produto Irrelevante' nem 'Contrafeito'. "
        "REGRA 2: Seja criativo e mude as palavras da chamada central a cada geração para não parecer um robô repetitivo. "
        "REGRA 3: Você deve OBRIGATORIAMENTE começar a mensagem com exatamente isso: ⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️\n"
        "REGRA 4: Você deve OBRIGATORIAMENTE terminar a mensagem com exatamente isso:\n"
        "Acervo Afiliados Shopee:👇\nLink de Convite: https://t.me/shopee_video_afiliado\n"
        "REGRA 5: Entregue apenas a mensagem final pronta, sem aspas, formatações markdown extras ou explicações."
    )
    try:
        response = await asyncio.to_thread(
            client_genai.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao gerar texto com IA: {e}")
        return (
            "⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️\n"
            "Fugindo de ban por Produto Irrelevante ou Contrafeito? 🚀\n"
            "Vem pro nosso grupo 100% gratuito e pegue vídeos limpos e validados para afiliados Shopee!\n\n"
            "Acervo Afiliados Shopee:👇\nLink de Convite: https://t.me/shopee_video_afiliado"
        )

async def enviar_mensagem(alvo):
    texto = await gerar_texto_divulgacao()
    try:
        entidade = await client.get_entity(alvo)
        await client.send_message(entidade, texto)
        if EXIBIR_LOGS: logger.info(f"✅ Divulgação enviada com sucesso para {alvo}!")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha ao enviar para {alvo}: {e}")

def programar_envios_da_hora():
    config = carregar_configuracoes()
    if not config or not config.get("alvos"):
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

async def main():
    if EXIBIR_LOGS: logger.info("⏳ Iniciando o Userbot de Divulgação...")
    await client.start()
    
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
