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
GEMINI_API_KEY = os.getenv('GEMINI_KEY')
from google import genai
client_genai = genai.Client(api_key=GEMINI_API_KEY)

MODELOS_CASCATA_GEMINI = [
    "gemini-3.1-pro-preview",
    "gemini-2.5-pro",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash-lite"
]

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
        # Valores genéricos de segurança. Tudo será editado pelo seu Bot Principal depois.
        return {"origem": -1003673555953, "origem_topico": None, "destino": "@videos_autorais"}
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

async def gerar_legenda_autoral(caminho_video):
    def processar_ia():
        import time
        if EXIBIR_LOGS: logger.info("🚀 [IA Autorais] A iniciar upload do vídeo para o Google Storage...")
        
        video_gemini = None
        for tentativa in range(3):
            try:
                video_gemini = client_genai.files.upload(file=caminho_video)
                if video_gemini:
                    break
            except Exception as erro_rede:
                if EXIBIR_LOGS: logger.warning(f"⚠️ [IA Autorais] Tentativa {tentativa+1}/3 falhou: {erro_rede}")
                if tentativa < 2: time.sleep(3)
                else: raise erro_rede
        
        while video_gemini.state.name == "PROCESSING":
            if EXIBIR_LOGS: logger.info("⏳ [IA Autorais] O vídeo está sendo processado nos servidores da Google...")
            time.sleep(2)
            video_gemini = client_genai.files.get(name=video_gemini.name)
            
        if video_gemini.state.name == "FAILED":
            raise Exception("Falha de processamento no servidor do Google.")
            
        if EXIBIR_LOGS: logger.info("✅ [IA Autorais] Processamento concluído! O vídeo está pronto para leitura.")

        prompt = (
            "Assista ao vídeo e identifique qual é o produto demonstrado. "
            "Sua resposta deve conter EXATAMENTE duas linhas.\n"
            "Na primeira linha, escreva APENAS o nome do produto acompanhado de um emoji correspondente no início (Exemplo: 👟 Tênis Casual Feminino).\n"
            "Na segunda linha, inclua as hashtags correspondentes aos setores do produto. IMPORTANTE: Se utilizar mais de uma hashtag, separe-as APENAS com espaços em branco, NUNCA utilize vírgulas.\n"
            "REGRA DE CONTEXTO: Categorize o produto baseando-se estritamente na sua utilidade prática e ambiente de uso. É terminantemente proibido utilizar atalhos semânticos ou associações literais de palavras (exemplo prático: um organizador de sacos plásticos de cozinha pertence a #CasaEDecoracao e NUNCA a #BolsasFemininas, pois não é um acessório de moda).\n"
            "REGRA ABSOLUTA: Você só pode escolher as hashtags desta lista exata, podendo combinar mais de uma se aplicável: "
            "#RoupasFemininas, #SapatosFemininos, #CelularesEDispositivos, #AcessoriosParaVeiculos, #Relogios, "
            "#AlimentosEBebidas, #CasaEDecoracao, #SapatosMasculinos, #EsportesELazer, #BolsasMasculinas, #BolsasFemininas, "
            "#RoupasPlusSize, #ModaInfantil, #Eletrodomesticos, #Motocicletas, #AnimaisDomesticos, #CamerasEDrones, #Beleza, "
            "#AcessoriosDeModa, #BrinquedosEHobbies, #Papelaria, #LivrosERevistas, #RoupasMasculinas, #Automoveis, #MaeEBebe, "
            "#ComputadoresEAcessorios, #Saude, #ViagensEBagagens, #JogosEConsoles, #Audio.\n"
            "É estritamente proibido criar textos de vendas, descrições, inventar novas hashtags, usar gatilhos mentais ou adicionar frases de encerramento."
        )

        try:
            for modelo_nome in MODELOS_CASCATA_GEMINI:
                try:
                    if EXIBIR_LOGS: logger.info(f"⏳ [IA Autorais] A consultar o motor {modelo_nome} enviando vídeo e texto...")
                    response = client_genai.models.generate_content(
                        model=modelo_nome,
                        contents=[video_gemini, prompt]
                    )
                    if response and response.text:
                        if EXIBIR_LOGS: logger.info(f"✅ [IA Autorais] Sucesso com o modelo {modelo_nome}!")
                        return response.text.strip()
                except Exception as erro_modelo:
                    erro_str = str(erro_modelo).lower()
                    if "429" in erro_str or "quota" in erro_str:
                        if EXIBIR_LOGS: logger.warning(f"⚠️ [IA Autorais] Limite atingido em {modelo_nome}. Pausando 3s...")
                        time.sleep(3)
                    else:
                        if EXIBIR_LOGS: logger.warning(f"⚠️ [IA Autorais] Erro no modelo {modelo_nome}: {erro_modelo}")
                    continue
            raise Exception("Todos os modelos da cascata falharam por limite de cota ou erro.")
        finally:
            if video_gemini:
                try:
                    client_genai.files.delete(name=video_gemini.name)
                    if EXIBIR_LOGS: logger.info("🧹 [IA Autorais] Ficheiro temporário removido da Cloud do Google.")
                except Exception:
                    pass

    try:
        titulo = await asyncio.to_thread(processar_ia)
        return titulo
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [IA Autorais] Falha na geração da legenda: {e}")
        return None

from utils import salvar_nome_grupo # Adicione isso caso não esteja no topo do arquivo

@client.on(events.NewMessage())
async def interceptar_e_espelhar(event):
    config_atual = carregar_config_autorais() # Lê a configuração salva pelo seu Bot Principal
    chat = await event.get_chat()
    
    # --- A MÁGICA ACONTECE AQUI ---
    if chat and hasattr(chat, 'title'):
        salvar_nome_grupo(str(chat.id), chat.title)
    # ------------------------------
    
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
    if eh_origem and topico_configurado is not None:
        topic_id = None
        if event.message.reply_to:
            topic_id = getattr(event.message.reply_to, 'forum_topic_id', getattr(event.message.reply_to, 'reply_to_msg_id', None))
        
        # O Tópico "Geral" costuma ser o ID 1 ou vir nulo na API do Telegram
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
        
        # ✅ Novo motor de substituição: Telethon usa Markdown por padrão na propriedade .text
        texto_base = event.text or ""
        texto_convertido = PADRAO_SHOPEE.sub(link_novo, texto_base)
        
        # Prevenção extra: Se o concorrente escondeu o link na formatação, injetamos no final em formato Markdown
        if link_novo not in texto_convertido:
            texto_convertido += f"\n\n🔗 **Link do Produto:**\n{link_novo}"

        if EXIBIR_LOGS: logger.info("📥 Iniciando o download do vídeo...")
        caminho_video = await event.download_media(file="temp/temp_espelho_isolado_")
        
        if caminho_video:
            try:
                if EXIBIR_LOGS: logger.info("🧠 Solicitando à IA a criação de uma nova Copy autoral...")
                texto_ia = await gerar_legenda_autoral(caminho_video)
                
                if texto_ia:
                    linhas_ia = texto_ia.split('\n')
                    nome_produto = linhas_ia[0].strip()
                    hashtags = '\n'.join(linhas_ia[1:]).strip() if len(linhas_ia) > 1 else ""
                    
                    legenda_final = f"**{nome_produto}**\n\n🔗 **Link do Produto:**\n{link_novo}"
                    if hashtags:
                        legenda_final += f"\n\n{hashtags}"
                else:
                    legenda_final = f"🛍️ **Vídeo do Produto**\n\n🔗 **Link do Produto:**\n{link_novo}"

                # O parse_mode foi removido para o Telethon aplicar os negritos originais automaticamente
                msg_enviada = await client.send_file(
                    config_atual['destino'],
                    file=caminho_video,
                    caption=legenda_final
                )
                if EXIBIR_LOGS: logger.info("🚀 Vídeo publicado no canal de destino com a nova legenda autoral!")
                
                # ✅ Regra dinâmica de dias e limite de vídeos lida diretamente do painel
                dias_retorno = config_atual.get('dias_retorno', 15)
                limite_videos = config_atual.get('limite_videos', 5)
                
                data_alvo = (datetime.now() + timedelta(days=dias_retorno)).strftime("%Y-%m-%d")
                fila_dados = ler_fila_retorno()
                if data_alvo not in fila_dados:
                    fila_dados[data_alvo] = []
                    
                if len(fila_dados[data_alvo]) < limite_videos:
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
        config_atualizada = carregar_config_autorais() # Lê a configuração em tempo real para o retorno
        if os.path.exists(caminho_arquivo):
            await client.send_file(
                config_atualizada['origem'],
                file=caminho_arquivo,
                caption=legenda
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
