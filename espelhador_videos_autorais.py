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

# ✅ Importando os Módulos Centrais de IA e Shopee
from api_gemini import analisar_video_gemini
from api_shopee import converter_link_shopee

# As chaves da Shopee e do Gemini foram movidas para os módulos centrais.

# Inicialização do Agendador
scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

if EXIBIR_LOGS:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    logger = logging.getLogger(__name__)

# 1. CREDENCIAIS E CONFIGURAÇÕES
API_ID = int(os.getenv('API_ID', 0)) 
API_HASH = os.getenv('API_HASH', '')

import sqlite3

def ler_config_bd_autorais(chave, padrao=None):
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

def salvar_config_bd_autorais(chave, dados):
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        dados_str = json.dumps(dados, ensure_ascii=False)
        cursor.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)", (chave, dados_str))
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao salvar '{chave}' no SQLite: {e}")

def carregar_config_autorais():
    padrao = {"origem": -1003673555953, "origem_topico": None, "destino": "@videos_autorais"}
    dados = ler_config_bd_autorais("autorais_config", padrao)
    if not dados and EXIBIR_LOGS:
        logger.warning("⚠️ Configuração 'autorais_config' não encontrada. Aguardando o bot principal criá-la.")
    return dados

def salvar_config_autorais(config):
    salvar_config_bd_autorais("autorais_config", config)

config_atual = carregar_config_autorais()

NOME_SESSAO = 'sessao_espelhador_isolado'
client = TelegramClient(NOME_SESSAO, API_ID, API_HASH)

def ler_fila_retorno():
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()
        cursor.execute("SELECT * FROM fila_autorais")
        linhas = cursor.fetchall()
        conexao.close()
        
        dados = {}
        for linha in linhas:
            dt = linha["data_alvo"]
            if dt not in dados:
                dados[dt] = []
            dados[dt].append({
                "msg_id_destino": linha["msg_id_destino"],
                "legenda": linha["legenda"],
                "caminho_arquivo": linha["caminho_arquivo"]
            })
        return dados
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler fila_autorais do SQLite: {e}")
        return {}

def salvar_fila_retorno(dados):
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        
        # Limpa e reconstrói a tabela baseada na memória manipulada para garantir integridade
        cursor.execute("DELETE FROM fila_autorais")
        for dt, lista in dados.items():
            for item in lista:
                cursor.execute('''
                    INSERT INTO fila_autorais (msg_id_destino, legenda, caminho_arquivo, data_alvo)
                    VALUES (?, ?, ?, ?)
                ''', (item.get("msg_id_destino"), item.get("legenda"), item.get("caminho_arquivo"), dt))
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao salvar fila_autorais no SQLite: {e}")

async def verificar_e_otimizar_video(caminho_video):
    """
    Inspeciona a resolução física do arquivo.
    Se for inferior a 720p, realiza o upscaling com FFmpeg em background.
    """
    if not caminho_video or not os.path.exists(caminho_video): return caminho_video
    
    try:
        if EXIBIR_LOGS: logger.info(f"🔎 [Upscaling] Inspecionando resolução física de: {caminho_video}")
        
        comando_probe = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-select_streams", "v:0", 
            "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", caminho_video,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await comando_probe.communicate()
        dimensoes = stdout.decode().strip()
        
        if not dimensoes or "x" not in dimensoes:
            if EXIBIR_LOGS: logger.warning("⚠️ [Upscaling] Falha ao ler metadados. Ignorando otimização.")
            return caminho_video
            
        largura, altura = map(int, dimensoes.split("x"))
        menor_dimensao = min(largura, altura)
        
        if menor_dimensao >= 720:
            if EXIBIR_LOGS: logger.info(f"✅ [Upscaling] Qualidade aprovada ({largura}x{altura}). Nenhuma maquiagem necessária.")
            return caminho_video
            
        if EXIBIR_LOGS: logger.info(f"🛠️ [Upscaling] Resolução baixa detectada ({largura}x{altura}). Iniciando renderização para 720p...")
        
        caminho_temp = f"{caminho_video}_upscaled.mp4"
        
        comando_ffmpeg = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", caminho_video, 
            "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black", 
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "copy", caminho_temp,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await comando_ffmpeg.communicate()
        
        if comando_ffmpeg.returncode == 0 and os.path.exists(caminho_temp):
            os.replace(caminho_temp, caminho_video)
            if EXIBIR_LOGS: logger.info(f"✨ [Upscaling] Sucesso! Vídeo re-renderizado para 720x1280 e substituído.")
        else:
            if EXIBIR_LOGS: logger.error("❌ [Upscaling] Falha na renderização do FFmpeg. Mantendo arquivo original.")
            if os.path.exists(caminho_temp): os.remove(caminho_temp)
            
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [Upscaling] Erro na função de otimização: {e}")
        
    return caminho_video

async def gerar_legenda_autoral(caminho_video):
    prompt = (
        "Assista ao vídeo e identifique qual é o produto demonstrado. "
        "Sua resposta deve conter EXATAMENTE duas linhas.\n"
        "Na primeira linha, escreva APENAS o nome do produto acompanhado de um emoji correspondente no final (Exemplo: Tênis Casual Feminino 👟).\n"
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
    
    titulo = await analisar_video_gemini(caminho_video, prompt, EXIBIR_LOGS)
    return titulo

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

        if EXIBIR_LOGS: logger.info("🔗 A converter o link da Shopee para o seu ID de afiliado via API Central...")
        link_novo = await converter_link_shopee(link_capturado, "geral", EXIBIR_LOGS)
        
        # ✅ Novo motor de substituição: Telethon usa Markdown por padrão na propriedade .text
        texto_base = event.text or ""
        texto_convertido = PADRAO_SHOPEE.sub(link_novo, texto_base)
        
        # Prevenção extra: Se o concorrente escondeu o link na formatação, injetamos no final em formato Markdown
        if link_novo not in texto_convertido:
            texto_convertido += f"\n\n🔗 **Link do Produto:**\n{link_novo}"

        if EXIBIR_LOGS: logger.info("📥 Iniciando o download do vídeo...")
        caminho_video = await event.download_media(file="temp/temp_espelho_isolado_")
        # ✅ NOVA TRAVA DE QUALIDADE E UPSCALING
        caminho_video = await verificar_e_otimizar_video(caminho_video)
        
        if caminho_video:
            try:
                if EXIBIR_LOGS: logger.info("🧠 Solicitando à IA a criação de uma nova Copy autoral...")
                texto_ia = await gerar_legenda_autoral(caminho_video)
                
                if texto_ia:
                    linhas_ia = texto_ia.split('\n')
                    nome_produto = linhas_ia[0].strip()
                    hashtags = '\n'.join(linhas_ia[1:]).strip() if len(linhas_ia) > 1 else ""
                    
                    legenda_final = f"<b>{nome_produto}</b>\n\n🔗 <b>Link do Produto:</b>\n{link_novo}"
                    if hashtags:
                        legenda_final += f"\n\n<i>{hashtags}</i>"
                else:
                    legenda_final = f"<b>Vídeo do Produto</b> 🛍️\n\n🔗 <b>Link do Produto:</b>\n{link_novo}"

                msg_enviada = await client.send_file(
                    config_atual['destino'],
                    file=caminho_video,
                    caption=legenda_final,
                    parse_mode='html'
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
                caption=legenda,
                parse_mode='md'
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
        
        # ✅ Lógica de Identificação Automática Visual
        config_atual = carregar_config_autorais()
        for chave in ['origem', 'destino']:
            alvo = config_atual.get(chave)
            if alvo and str(alvo) not in ["Não definida", "Não definido"]:
                try:
                    entidade = await client.get_entity(alvo)
                    nome_alvo = getattr(entidade, 'title', getattr(entidade, 'username', str(alvo)))
                    salvar_nome_grupo(str(alvo), nome_alvo)
                    if EXIBIR_LOGS: logger.info(f"✅ Nome da {chave} ({nome_alvo}) extraído e salvo no cache automaticamente.")
                except Exception as err:
                    if EXIBIR_LOGS: logger.warning(f"⚠️ Não foi possível auditar a {chave} na inicialização: {err}")
                    
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
