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

async def gerar_texto_divulgacao(repeticoes=6):
    if EXIBIR_LOGS: print(f"✅ Função iniciada com {repeticoes} repetições.")
    if EXIBIR_LOGS: logger.info("🚀 Montando prompt persuasivo focado em engajamento e conversão...")
    prompt = (
        "Você atua como um copywriter persuasivo e focado em conversão, divulgando um grupo do Telegram exclusivo para afiliados da Shopee. "
        "Crie UMA ÚNICA FRASE curta, altamente chamativa, convidativa e diferente de todas as anteriores. "
        "Foque em atrair o usuário oferecendo acesso imediato a um acervo de ouro com vídeos prontos e validados que aumentam as comissões e visualizações na plataforma. "
        "OBRIGATÓRIO: Inicie a sua resposta com uma sequência de 10 a 15 emojis repetidos de impacto (como 🚨, 🚀, 🔥 ou 💰) para criar uma forte barreira visual na tela. "
        "Use um tom entusiasmado, adicione outros emojis variados ao longo do texto para despertar interesse orgânico, mas sem parecer apelativo ou alarmista. "
        "Entregue APENAS a frase final, sem aspas."
    )
    
    modelos_disponiveis = [
        "gemini-3.1-pro-preview",
        "gemini-3.5-flash",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite"
    ]
    
    frase_ia = None
    for modelo_nome in modelos_disponiveis:
        try:
            if EXIBIR_LOGS: logger.info(f"⏳ A consultar o motor de IA: {modelo_nome}...")
            response = await asyncio.to_thread(
                client_genai.models.generate_content,
                model=modelo_nome,
                contents=prompt
            )
            if response and response.text:
                if EXIBIR_LOGS: logger.info(f"✅ Sucesso com o modelo {modelo_nome}!")
                frase_ia = response.text.strip()
                break
        except Exception as e:
            erro_str = str(e)
            if "429" in erro_str:
                if EXIBIR_LOGS: logger.warning(f"⚠️ Limite atingido em {modelo_nome}. A tentar a próxima alternativa...")
            else:
                if EXIBIR_LOGS: logger.warning(f"⚠️ Modelo {modelo_nome} indisponível: {erro_str[:50]}...")
            continue

    if not frase_ia:
        if EXIBIR_LOGS: logger.error("❌ Todos os modelos falharam. A utilizar frase padrão de segurança.")
        frase_ia = "🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨\nQuer turbinar suas vendas hoje? Acesse nosso acervo de ouro com vídeos validados e prontos para viralizar na Shopee!"

    # Monta o bloco curto com o link obrigatório e a quebra de linha em branco
    bloco_unico = f"{frase_ia}\n\nLINK PARA O GRUPO:👇\nhttps://t.me/shopee_video_afiliado"
    
    if EXIBIR_LOGS: logger.info(f"🔄 Multiplicando bloco de texto {repeticoes} vezes na mesma mensagem.")
    
    texto_multiplicado = "\n\n\n".join([bloco_unico] * repeticoes)
    
    return texto_multiplicado

async def enviar_mensagem(alvo):
    if EXIBIR_LOGS: logger.info(f"🔍 Validando status de pausa antes do disparo para {alvo}...")
    config = carregar_configuracoes()
    if config and config.get("pausado", False):
        if EXIBIR_LOGS: logger.warning("🛑 Disparo cancelado: O sistema de SPAM está pausado no momento.")
        return
        
    config_alvos = config.get("config_alvos", {}) if config else {}
    conf_alvo = config_alvos.get(alvo, {})
    
    replicas = conf_alvo.get("replicas", config.get("replicas_mensagem", 5) if config else 5)
    repeticoes = conf_alvo.get("repeticoes", config.get("repeticoes_internas", 6) if config else 6)
    
    texto = await gerar_texto_divulgacao(repeticoes)
    try:
        entidade = await client.get_entity(alvo)
        
        if EXIBIR_LOGS: logger.info(f"📤 Iniciando disparo em rajada de {replicas} mensagens para {alvo}...")
        
        for i in range(replicas):
            await client.send_message(entidade, texto)
            if EXIBIR_LOGS: logger.info(f"📩 Mensagem {i+1}/{replicas} enviada.")
            if i < replicas - 1: # Pausa apenas se houver uma próxima mensagem
                await asyncio.sleep(1.5) # Pausa de segurança obrigatória contra bloqueio de flood
            
        if EXIBIR_LOGS: logger.info(f"✅ Rajada de {replicas} mensagens concluída com sucesso para {alvo}!")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha ao enviar rajada para {alvo}: {e}")

# Novo dicionário global para rastrear os agendamentos cruzando a virada das horas
ultimos_agendamentos_por_alvo = {}

def programar_envios_da_hora():
    global ultimos_agendamentos_por_alvo
    config = carregar_configuracoes()
    if not config or not config.get("alvos"):
        return
        
    if config.get("pausado", False):
        if EXIBIR_LOGS: logger.info("⏸️ Divulgação pausada pelo painel. Pulando sorteio desta hora.")
        return

    alvos = config["alvos"]
    freq_global = config.get("frequencia_por_hora", 0)
    config_alvos = config.get("config_alvos", {})
    
    agora = datetime.now()
    INTERVALO_MINIMO = 15 # Distanciamento rigoroso de 15 minutos
    
    for alvo in alvos:
        conf_alvo = config_alvos.get(alvo, {})
        freq_alvo = conf_alvo.get("frequencia", freq_global)
        
        if freq_alvo <= 0: continue
        
        if EXIBIR_LOGS: logger.info(f"🔄 Sorteando {freq_alvo} envios para {alvo} na hora atual ({agora.hour}h)...")

        # Fatiamento da hora para alocação otimizada
        espacamento_ideal = 58 // freq_alvo if freq_alvo > 0 else 58

        for i in range(freq_alvo):
            sucesso = False
            
            min_inicio_busca = (i * espacamento_ideal) + 1
            min_fim_busca = min(((i + 1) * espacamento_ideal), 59)
            if min_fim_busca <= min_inicio_busca:
                min_fim_busca = 59
                
            for tentativa in range(100):
                minuto_sorteado = random.randint(min_inicio_busca, min_fim_busca)
                horario_disparo = agora.replace(minute=minuto_sorteado, second=random.randint(0, 59))
                
                # Checagem de colisão com o histórico
                ultimo_envio = ultimos_agendamentos_por_alvo.get(alvo)
                colisao = False
                
                if ultimo_envio:
                    diferenca = (horario_disparo - ultimo_envio).total_seconds() / 60
                    if abs(diferenca) < INTERVALO_MINIMO:
                        colisao = True
                
                # Impede agendamentos no passado
                if horario_disparo < agora:
                    colisao = True
                    
                if not colisao:
                    ultimos_agendamentos_por_alvo[alvo] = horario_disparo
                    scheduler.add_job(enviar_mensagem, 'date', run_date=horario_disparo, args=[alvo])
                    if EXIBIR_LOGS: logger.info(f"✅ Disparo {i+1}/{freq_alvo} para {alvo} agendado às {horario_disparo.strftime('%H:%M:%S')} (Tentativas: {tentativa+1})")
                    sucesso = True
                    break
                    
            if not sucesso:
                if EXIBIR_LOGS: logger.warning(f"⚠️ {alvo} [{i+1}/{freq_alvo}]: Janela muito curta. Acionando fallback forçado para empurrar o envio.")
                
                ultimo_conhecido = ultimos_agendamentos_por_alvo.get(alvo, agora)
                # Adiciona 15 minutos de segurança mais um fator aleatório curto
                horario_disparo_fallback = ultimo_conhecido + timedelta(minutes=INTERVALO_MINIMO + random.randint(1, 3))
                
                ultimos_agendamentos_por_alvo[alvo] = horario_disparo_fallback
                scheduler.add_job(enviar_mensagem, 'date', run_date=horario_disparo_fallback, args=[alvo])
                if EXIBIR_LOGS: logger.info(f"🛡️ Fallback ativado: Disparo {i+1} empurrado para as {horario_disparo_fallback.strftime('%H:%M:%S')}")

async def monitorar_comandos():
    while True:
        config = carregar_configuracoes()
        if config and config.get("forcar_disparo"):
            if config.get("pausado", False):
                if EXIBIR_LOGS: logger.warning("🛑 Comando forçado ignorado: O sistema de SPAM está pausado.")
                config["forcar_disparo"] = False
                with open("alvos_divulgacao.json", "w") as f:
                    json.dump(config, f, indent=4)
            else:
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
