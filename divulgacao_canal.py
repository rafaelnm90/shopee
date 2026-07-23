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
from utils import registrar_erro_json

# FORÇA O FUSO HORÁRIO DO BRASIL NA MEMÓRIA DO SCRIPT
import time
os.environ['TZ'] = 'America/Sao_Paulo'
time.tzset()
if EXIBIR_LOGS: print("⏰ Fuso horário ajustado internamente para America/Sao_Paulo")

# 1. CREDENCIAIS DA CONTA
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
GEMINI_API_KEY = os.getenv('GEMINI_KEY')

MODELOS_CASCATA_GEMINI = [
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-pro"
]

# Inicializa o cliente do Google
client_genai = genai.Client(api_key=GEMINI_API_KEY)

# 2. CONFIGURAÇÃO DE LOGS 🚀
if EXIBIR_LOGS:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    logger = logging.getLogger(__name__)

# 3. SISTEMA DE AUTOLIMPEZA E INICIALIZAÇÃO
def limpar_travas_fantasma(nome_sessao):
    import glob
    import os
    
    # ✅ NOVO: Destrói a trava de manutenção no exato segundo em que o script inicia
    if os.path.exists("trava_manutencao.txt"):
        try:
            os.remove("trava_manutencao.txt")
            print("🔓 [Auto-cura] Trava de manutenção removida! Monitoramento de erros reativado.")
        except:
            pass

    arquivos_trava = glob.glob(f"{nome_sessao}.session-journal") + glob.glob(f"{nome_sessao}.session.lock")
    for arquivo in arquivos_trava:
        try:
            os.remove(arquivo)
            if EXIBIR_LOGS: logger.info(f"🧹 [Auto-cura] Trava fantasma de crash removida: {arquivo}")
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ [Auto-cura] Falha ao tentar remover trava {arquivo}: {e}")

# ✅ Limpa resíduos de reboot forçado no servidor antes de tocar na base de dados
limpar_travas_fantasma('sessao_divulgacao')

# O nome da sessão é mantido independente
client = TelegramClient('sessao_divulgacao', API_ID, API_HASH)
scheduler = AsyncIOScheduler()

# 🚦 Semáforo de proteção assíncrona para o banco de dados SQLite
telegram_lock = asyncio.Lock()
if EXIBIR_LOGS: logger.info("🚦 Semáforo de controle de tráfego do Telegram ativado!")

import sqlite3

def ler_config_bd_divulgacao(chave, padrao=None):
    if padrao is None: padrao = {}
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave,))
        resultado = cursor.fetchone()
        conexao.close()
        if resultado:
            return json.loads(resultado[0])
        return padrao
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler '{chave}' do SQLite: {e}")
        return padrao

def salvar_config_bd_divulgacao(chave, dados):
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        dados_str = json.dumps(dados, ensure_ascii=False)
        cursor.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)", (chave, dados_str))
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao salvar '{chave}' no SQLite: {e}")

# 4. FUNÇÕES DE IA E AGENDAMENTO
def carregar_configuracoes():
    dados = ler_config_bd_divulgacao("alvos_divulgacao", padrao=None)
    if not dados and EXIBIR_LOGS:
        logger.warning("⚠️ Configuração 'alvos_divulgacao' não encontrada no banco. Aguardando o bot principal criá-la.")
    return dados

def carregar_configuracoes_viral():
    dados = ler_config_bd_divulgacao("alvos_divulgacao_viral", padrao=None)
    if not dados and EXIBIR_LOGS:
        logger.warning("⚠️ Configuração 'alvos_divulgacao_viral' não encontrada no banco. Aguardando o bot principal criá-la.")
    return dados

async def gerar_texto_divulgacao(repeticoes=6):
    if EXIBIR_LOGS: print(f"✅ Função iniciada com {repeticoes} repetições.")
    if EXIBIR_LOGS: logger.info("🚀 Montando prompt persuasivo focado em engajamento e conversão...")
    prompt = (
        "Você atua como um copywriter persuasivo e focado em conversão, divulgando um grupo do Telegram exclusivo para afiliados da Shopee. "
        "Crie UMA ÚNICA FRASE curta, altamente chamativa, convidativa e diferente de todas as anteriores. A cada nova solicitação, varie completamente a estrutura, o tom e a estratégia de persuasão para garantir originalidade."
        "Foque em atrair o usuário oferecendo acesso imediato a um acervo de ouro com vídeos prontos e validados que aumentam as comissões e visualizações na plataforma. "
        "É OBRIGATÓRIO informar organicamente na frase que o acesso ao grupo é GRÁTIS (exatamente assim, em letras maiúsculas). "
        "OBRIGATÓRIO: Inicie a sua resposta com uma sequência de 10 a 15 emojis repetidos de impacto (como 🚨, 🚀, ⚠️, 🔥 ou 💰) para criar uma forte barreira visual na tela, trocando a combinação a cada execução. "
        "Use um tom entusiasmado, adicione outros emojis variados ao longo do texto para despertar interesse orgânico, mas sem parecer apelativo ou alarmista. "
        "Entregue APENAS a frase final, sem aspas."
    )
    
    frase_ia = None
    for modelo_nome in MODELOS_CASCATA_GEMINI:
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
        if EXIBIR_LOGS: logger.info(f"🚦 Aguardando sinal verde do banco de dados para {alvo}...")
        async with telegram_lock:
            # ✅ Proteção ativa: Reconecta caso o socket tenha caído em background
            if not client.is_connected():
                if EXIBIR_LOGS: logger.info("🔄 [Auto-cura] Conexão perdida detectada. Forçando reconexão com o Telegram...")
                await client.connect()
                
            if EXIBIR_LOGS: logger.info(f"🟢 Sinal verde! Acessando o Telegram para {alvo}...")
            entidade = await client.get_entity(alvo)
            
            if EXIBIR_LOGS: logger.info(f"📤 Iniciando disparo em rajada de {replicas} mensagens para {alvo}...")
            
            for i in range(replicas):
                await client.send_message(entidade, texto)
                if EXIBIR_LOGS: logger.info(f"📩 Mensagem {i+1}/{replicas} enviada.")
                if i < replicas - 1: # Pausa apenas se houver uma próxima mensagem
                    await asyncio.sleep(1.5) # Pausa de segurança obrigatória contra bloqueio de flood
            
            if EXIBIR_LOGS: logger.info(f"✅ Rajada de {replicas} mensagens concluída com sucesso para {alvo}!")
    except Exception as e:
        erro_str = str(e).lower()
        if "chat is restricted" in erro_str or "forbidden" in erro_str:
            if EXIBIR_LOGS: logger.warning(f"🚫 Omitido: O chat {alvo} é restrito ou o bot foi silenciado neste grupo.")
        elif "database is locked" in erro_str:
            if EXIBIR_LOGS: logger.error(f"🔒 Bloqueio de concorrência no SQLite ao acessar {alvo}. Tentando recuperar na próxima rodada.")
        else:
            if EXIBIR_LOGS: logger.error(f"❌ Falha crítica ao enviar rajada para {alvo}: {e}")
            registrar_erro_json(f"enviar_mensagem ({alvo}): {e}", origem="divulgacao_canal.py")

async def gerar_texto_divulgacao_viral(repeticoes=6):
    if EXIBIR_LOGS: logger.info(f"🚀 [VIRAL] Montando prompt persuasivo para o Acervo Viral...")
    prompt = (
        "Você atua como um copywriter persuasivo e focado em conversão, divulgando um grupo do Telegram exclusivo para afiliados da Shopee chamado 'Acervo Viral Shopee'. "
        "Crie UMA ÚNICA FRASE curta, altamente chamativa, convidativa e diferente de todas as anteriores. "
        "Foque em atrair os afiliados oferecendo acesso imediato aos vídeos mais virais, achados do TikTok e tendências do momento, mantendo a mesma pegada agressiva de aumentar comissões e faturamento em alta. "
        "É OBRIGATÓRIO informar organicamente na frase que o acesso ao grupo é GRÁTIS (exatamente assim, em letras maiúsculas). "
        "OBRIGATÓRIO: Inicie a sua resposta com uma sequência de 10 a 15 emojis repetidos de impacto (como 🚨, 🚀, ⚠️, 🔥 ou 💰) para criar uma forte barreira visual na tela. "
        "Use um tom entusiasmado e adicione outros emojis variados. Entregue APENAS a frase final, sem aspas."
    )
    
    frase_ia = None
    for modelo_nome in MODELOS_CASCATA_GEMINI:
        try:
            if EXIBIR_LOGS: logger.info(f"⏳ [VIRAL] A consultar o motor de IA: {modelo_nome}...")
            response = await asyncio.to_thread(
                client_genai.models.generate_content,
                model=modelo_nome,
                contents=prompt
            )
            if response and response.text:
                if EXIBIR_LOGS: logger.info(f"✅ [VIRAL] Sucesso com o modelo {modelo_nome}!")
                frase_ia = response.text.strip()
                break
        except Exception as e:
            erro_str = str(e)
            if "429" in erro_str:
                if EXIBIR_LOGS: logger.warning(f"⚠️ [VIRAL] Limite atingido em {modelo_nome}. A tentar a próxima alternativa...")
            else:
                if EXIBIR_LOGS: logger.warning(f"⚠️ [VIRAL] Modelo {modelo_nome} indisponível: {erro_str[:50]}...")
            continue

    if not frase_ia:
        if EXIBIR_LOGS: logger.error("❌ [VIRAL] Todos os modelos falharam. A utilizar frase padrão de segurança.")
        frase_ia = "🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨\nAfiliado, venha pegar os produtos mais virais e bombados do momento no nosso acervo 100% GRÁTIS!"

    bloco_unico = f"{frase_ia}\n\nLINK PARA O GRUPO VIRAL:👇\nhttps://t.me/acervo_viral_shopee"
    
    if EXIBIR_LOGS: logger.info(f"🔄 [VIRAL] Multiplicando bloco de texto {repeticoes} vezes na mesma mensagem.")
    
    texto_multiplicado = "\n\n\n".join([bloco_unico] * repeticoes)
    
    return texto_multiplicado

async def enviar_mensagem_viral(alvo):
    if EXIBIR_LOGS: logger.info(f"🔍 [VIRAL] Validando status de pausa antes do disparo para {alvo}...")
    config = carregar_configuracoes_viral()
    if config and config.get("pausado", False):
        if EXIBIR_LOGS: logger.warning("🛑 [VIRAL] Disparo cancelado: O sistema de SPAM Viral está pausado no momento.")
        return
        
    config_alvos = config.get("config_alvos", {}) if config else {}
    conf_alvo = config_alvos.get(alvo, {})
    
    replicas = conf_alvo.get("replicas", config.get("replicas_mensagem", 5) if config else 5)
    repeticoes = conf_alvo.get("repeticoes", config.get("repeticoes_internas", 6) if config else 6)
    
    texto = await gerar_texto_divulgacao_viral(repeticoes)
    try:
        if EXIBIR_LOGS: logger.info(f"🚦 [VIRAL] Aguardando sinal verde do banco de dados para {alvo}...")
        async with telegram_lock:
            # ✅ Proteção ativa: Reconecta caso o socket tenha caído em background
            if not client.is_connected():
                if EXIBIR_LOGS: logger.info("🔄 [Auto-cura] Conexão perdida detectada no módulo Viral. Forçando reconexão...")
                await client.connect()
                
            if EXIBIR_LOGS: logger.info(f"🟢 [VIRAL] Sinal verde! Acessando o Telegram para {alvo}...")
            entidade = await client.get_entity(alvo)
            
            if EXIBIR_LOGS: logger.info(f"📤 [VIRAL] Iniciando disparo em rajada de {replicas} mensagens para {alvo}...")
            
            for i in range(replicas):
                await client.send_message(entidade, texto)
                if EXIBIR_LOGS: logger.info(f"📩 [VIRAL] Mensagem {i+1}/{replicas} enviada.")
                if i < replicas - 1:
                    await asyncio.sleep(1.5)
            
            if EXIBIR_LOGS: logger.info(f"✅ [VIRAL] Rajada de {replicas} mensagens concluída com sucesso para {alvo}!")
    except Exception as e:
        erro_str = str(e).lower()
        if "chat is restricted" in erro_str or "forbidden" in erro_str:
            if EXIBIR_LOGS: logger.warning(f"🚫 [VIRAL] Omitido: Permissão negada no chat {alvo}.")
        elif "database is locked" in erro_str:
            if EXIBIR_LOGS: logger.error(f"🔒 [VIRAL] Bloqueio de concorrência no SQLite ao acessar {alvo}.")
        else:
            if EXIBIR_LOGS: logger.error(f"❌ [VIRAL] Falha ao enviar rajada para {alvo}: {e}")
            registrar_erro_json(f"enviar_mensagem_viral ({alvo}): {e}", origem="divulgacao_canal.py")

# Novo dicionário global para rastrear os agendamentos cruzando a virada das horas
ultimos_agendamentos_por_alvo = {}

def programar_envios_da_hora():
    global ultimos_agendamentos_por_alvo
    agora = datetime.now()
    INTERVALO_MINIMO = 15 # Distanciamento rigoroso de 15 minutos
    
    # --- PARTE 1: AGENDAMENTO DO SPAM PRINCIPAL ---
    config_princ = carregar_configuracoes()
    if config_princ and config_princ.get("alvos") and not config_princ.get("pausado", False):
        alvos_princ = config_princ["alvos"]
        freq_global_princ = config_princ.get("frequencia_por_hora", 0)
        config_alvos_princ = config_princ.get("config_alvos", {})
        
        for alvo in alvos_princ:
            conf_alvo = config_alvos_princ.get(alvo, {})
            freq_alvo = conf_alvo.get("frequencia", freq_global_princ)
            
            if freq_alvo <= 0: continue
            if EXIBIR_LOGS: logger.info(f"🔄 Sorteando {freq_alvo} envios PRINCIPAIS para {alvo} na hora atual ({agora.hour}h)...")
            espacamento_ideal = 58 // freq_alvo if freq_alvo > 0 else 58

            for i in range(freq_alvo):
                sucesso = False
                min_inicio_busca = (i * espacamento_ideal) + 1
                min_fim_busca = min(((i + 1) * espacamento_ideal), 59)
                if min_fim_busca <= min_inicio_busca: min_fim_busca = 59
                    
                for tentativa in range(100):
                    minuto_sorteado = random.randint(min_inicio_busca, min_fim_busca)
                    horario_disparo = agora.replace(minute=minuto_sorteado, second=random.randint(0, 59))
                    
                    ultimo_envio = ultimos_agendamentos_por_alvo.get(alvo)
                    colisao = False
                    
                    if ultimo_envio and abs((horario_disparo - ultimo_envio).total_seconds() / 60) < INTERVALO_MINIMO:
                        colisao = True
                    if horario_disparo < agora:
                        colisao = True
                        
                    if not colisao:
                        ultimos_agendamentos_por_alvo[alvo] = horario_disparo
                        scheduler.add_job(enviar_mensagem, 'date', run_date=horario_disparo, args=[alvo])
                        if EXIBIR_LOGS: logger.info(f"✅ Disparo PRINCIPAL {i+1}/{freq_alvo} para {alvo} agendado às {horario_disparo.strftime('%H:%M:%S')}")
                        sucesso = True
                        break
                        
                if not sucesso:
                    if EXIBIR_LOGS: logger.warning(f"⚠️ {alvo} [{i+1}/{freq_alvo}]: Acionando fallback forçado PRINCIPAL.")
                    ultimo_conhecido = ultimos_agendamentos_por_alvo.get(alvo, agora)
                    horario_disparo_fallback = ultimo_conhecido + timedelta(minutes=INTERVALO_MINIMO + random.randint(1, 3))
                    ultimos_agendamentos_por_alvo[alvo] = horario_disparo_fallback
                    scheduler.add_job(enviar_mensagem, 'date', run_date=horario_disparo_fallback, args=[alvo])
                    if EXIBIR_LOGS: logger.info(f"🛡️ Fallback: Disparo {i+1} empurrado para {horario_disparo_fallback.strftime('%H:%M:%S')}")

    # --- PARTE 2: AGENDAMENTO DO SPAM VIRAL ---
    config_viral = carregar_configuracoes_viral()
    if config_viral and config_viral.get("alvos") and not config_viral.get("pausado", False):
        alvos_viral = config_viral["alvos"]
        freq_global_viral = config_viral.get("frequencia_por_hora", 0)
        config_alvos_viral = config_viral.get("config_alvos", {})
        
        for alvo in alvos_viral:
            conf_alvo = config_alvos_viral.get(alvo, {})
            freq_alvo = conf_alvo.get("frequencia", freq_global_viral)
            
            if freq_alvo <= 0: continue
            if EXIBIR_LOGS: logger.info(f"🔄 [VIRAL] Sorteando {freq_alvo} envios para {alvo} na hora atual ({agora.hour}h)...")
            espacamento_ideal = 58 // freq_alvo if freq_alvo > 0 else 58

            for i in range(freq_alvo):
                sucesso = False
                min_inicio_busca = (i * espacamento_ideal) + 1
                min_fim_busca = min(((i + 1) * espacamento_ideal), 59)
                if min_fim_busca <= min_inicio_busca: min_fim_busca = 59
                    
                for tentativa in range(100):
                    minuto_sorteado = random.randint(min_inicio_busca, min_fim_busca)
                    horario_disparo = agora.replace(minute=minuto_sorteado, second=random.randint(0, 59))
                    
                    # A mágica do cruzamento: Ele checa o mesmo dicionário de histórico do alvo, evitando colisões com o Principal
                    ultimo_envio = ultimos_agendamentos_por_alvo.get(alvo)
                    colisao = False
                    
                    if ultimo_envio and abs((horario_disparo - ultimo_envio).total_seconds() / 60) < INTERVALO_MINIMO:
                        colisao = True
                    if horario_disparo < agora:
                        colisao = True
                        
                    if not colisao:
                        ultimos_agendamentos_por_alvo[alvo] = horario_disparo
                        scheduler.add_job(enviar_mensagem_viral, 'date', run_date=horario_disparo, args=[alvo])
                        if EXIBIR_LOGS: logger.info(f"✅ [VIRAL] Disparo {i+1}/{freq_alvo} para {alvo} agendado às {horario_disparo.strftime('%H:%M:%S')}")
                        sucesso = True
                        break
                        
                if not sucesso:
                    if EXIBIR_LOGS: logger.warning(f"⚠️ [VIRAL] {alvo} [{i+1}/{freq_alvo}]: Acionando fallback forçado.")
                    ultimo_conhecido = ultimos_agendamentos_por_alvo.get(alvo, agora)
                    horario_disparo_fallback = ultimo_conhecido + timedelta(minutes=INTERVALO_MINIMO + random.randint(1, 3))
                    ultimos_agendamentos_por_alvo[alvo] = horario_disparo_fallback
                    scheduler.add_job(enviar_mensagem_viral, 'date', run_date=horario_disparo_fallback, args=[alvo])
                    if EXIBIR_LOGS: logger.info(f"🛡️ [VIRAL] Fallback: Disparo {i+1} empurrado para {horario_disparo_fallback.strftime('%H:%M:%S')}")

async def monitorar_comandos():
    while True:
        # 1. Verifica Comandos do SPAM Principal
        config_princ = carregar_configuracoes()
        if config_princ and config_princ.get("forcar_disparo"):
            if config_princ.get("pausado", False):
                if EXIBIR_LOGS: logger.warning("🛑 Comando forçado ignorado: O sistema de SPAM Principal está pausado.")
                config_princ["forcar_disparo"] = False
                salvar_config_bd_divulgacao("alvos_divulgacao", config_princ)
            else:
                if EXIBIR_LOGS: logger.info("🚀 Comando de DISPARO FORÇADO PRINCIPAL detectado! Iniciando rajada...")
                config_princ["forcar_disparo"] = False
                salvar_config_bd_divulgacao("alvos_divulgacao", config_princ)
                
                alvos_princ = config_princ.get("alvos", [])
                for alvo in alvos_princ:
                    await enviar_mensagem(alvo)

        # 2. Verifica Comandos do SPAM Viral
        config_viral = carregar_configuracoes_viral()
        if config_viral and config_viral.get("forcar_disparo"):
            if config_viral.get("pausado", False):
                if EXIBIR_LOGS: logger.warning("🛑 [VIRAL] Comando forçado ignorado: O sistema de SPAM Viral está pausado.")
                config_viral["forcar_disparo"] = False
                salvar_config_bd_divulgacao("alvos_divulgacao_viral", config_viral)
            else:
                if EXIBIR_LOGS: logger.info("🚀 [VIRAL] Comando de DISPARO FORÇADO VIRAL detectado! Iniciando rajada...")
                config_viral["forcar_disparo"] = False
                salvar_config_bd_divulgacao("alvos_divulgacao_viral", config_viral)
                
                alvos_viral = config_viral.get("alvos", [])
                for alvo in alvos_viral:
                    await enviar_mensagem_viral(alvo)

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
