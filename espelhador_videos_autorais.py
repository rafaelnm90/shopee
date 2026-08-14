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

## ✅ Importando os Módulos Centrais de IA e Shopee
from api_gemini import analisar_video_gemini
from api_shopee import converter_link_shopee
from motor_filas import calcular_horarios_distribuicao # ⚙️ Motor Central Importado

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
        
        # Prevenção: Cria a tabela caso o init não tenha rodado
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fila_autorais (
                id_unico TEXT PRIMARY KEY,
                msg_id_destino INTEGER,
                legenda TEXT,
                caminho_arquivo TEXT,
                data_captura TEXT,
                data_alvo TEXT,
                horario_disparo TEXT,
                processado INTEGER DEFAULT 0
            )
        ''')
        cursor.execute("SELECT * FROM fila_autorais")
        linhas = cursor.fetchall()
        conexao.close()
        
        fila = []
        for linha in linhas:
            fila.append({
                "id_unico": linha["id_unico"],
                "msg_id_destino": linha["msg_id_destino"],
                "legenda": linha["legenda"],
                "caminho_arquivo": linha["caminho_arquivo"],
                "data_captura": linha["data_captura"],
                "data_alvo": linha["data_alvo"],
                "horario_disparo": linha["horario_disparo"],
                "processado": bool(linha["processado"])
            })
        return {"fila": fila}
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler fila_autorais do SQLite: {e}")
        return {"fila": []}

def salvar_fila_retorno(dados):
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        
        cursor.execute("DELETE FROM fila_autorais")
        for item in dados.get("fila", []):
            cursor.execute('''
                INSERT INTO fila_autorais (id_unico, msg_id_destino, legenda, caminho_arquivo, data_captura, data_alvo, horario_disparo, processado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item.get("id_unico"), 
                item.get("msg_id_destino"), 
                item.get("legenda"), 
                item.get("caminho_arquivo"), 
                item.get("data_captura"), 
                item.get("data_alvo"), 
                item.get("horario_disparo", ""), 
                1 if item.get("processado") else 0
            ))
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao salvar fila_autorais no SQLite: {e}")

def ler_fila_publico():
    """Fila própria do Grupo Público. Espelha ler_fila_retorno(), com tabela separada."""
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fila_publico (
                id_unico TEXT PRIMARY KEY,
                msg_id_destino INTEGER,
                legenda TEXT,
                data_captura TEXT,
                data_alvo TEXT,
                horario_disparo TEXT,
                processado INTEGER DEFAULT 0,
                data_postagem TEXT
            )
        ''')
        cursor.execute("SELECT * FROM fila_publico")
        linhas = cursor.fetchall()
        conexao.close()

        fila = []
        for linha in linhas:
            fila.append({
                "id_unico": linha["id_unico"],
                "msg_id_destino": linha["msg_id_destino"],
                "legenda": linha["legenda"],
                "data_captura": linha["data_captura"],
                "data_alvo": linha["data_alvo"],
                "horario_disparo": linha["horario_disparo"],
                "processado": bool(linha["processado"]),
                "data_postagem": linha["data_postagem"]
            })
        return {"fila": fila}
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler fila_publico do SQLite: {e}")
        return {"fila": []}

def salvar_fila_publico(dados):
    """Espelha salvar_fila_retorno(), gravando na tabela fila_publico."""
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()

        cursor.execute("DELETE FROM fila_publico")
        for item in dados.get("fila", []):
            cursor.execute('''
                INSERT INTO fila_publico (id_unico, msg_id_destino, legenda, data_captura, data_alvo, horario_disparo, processado, data_postagem)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item.get("id_unico"),
                item.get("msg_id_destino"),
                item.get("legenda"),
                item.get("data_captura"),
                item.get("data_alvo"),
                item.get("horario_disparo", ""),
                1 if item.get("processado") else 0,
                item.get("data_postagem", "")
            ))
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao salvar fila_publico no SQLite: {e}")

def contar_ofertas_dia_publico(data_alvo, incrementar=True):
    """
    🎲 Contador do Sorteio do Grupo Público (Amostragem de Reservatório)
    Espelha contar_ofertas_dia(), com tabela própria e independente.
    """
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contador_publico (
                data_alvo TEXT PRIMARY KEY,
                total INTEGER DEFAULT 0
            )
        ''')

        if incrementar:
            cursor.execute("UPDATE contador_publico SET total = total + 1 WHERE data_alvo = ?", (data_alvo,))
            if cursor.rowcount == 0:
                cursor.execute("INSERT INTO contador_publico (data_alvo, total) VALUES (?, 1)", (data_alvo,))

        cursor.execute("SELECT total FROM contador_publico WHERE data_alvo = ?", (data_alvo,))
        resultado = cursor.fetchone()
        conexao.commit()
        conexao.close()
        return resultado[0] if resultado else 0
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro no contador de sorteio do Público: {e}")
        return 0

def contar_ofertas_dia(data_alvo, incrementar=True):
    """
    🎲 Contador do Sorteio (Amostragem de Reservatório)
    Guarda quantos vídeos a origem já ofereceu para aquela data_alvo.
    É esse número que garante a chance justa de (limite/total) para cada vídeo do dia.
    """
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contador_autorais (
                data_alvo TEXT PRIMARY KEY,
                total INTEGER DEFAULT 0
            )
        ''')

        if incrementar:
            cursor.execute("UPDATE contador_autorais SET total = total + 1 WHERE data_alvo = ?", (data_alvo,))
            if cursor.rowcount == 0:
                cursor.execute("INSERT INTO contador_autorais (data_alvo, total) VALUES (?, 1)", (data_alvo,))

            # Faxina: contadores de datas já vencidas não servem mais para nada
            limite_faxina = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
            cursor.execute("DELETE FROM contador_autorais WHERE data_alvo < ?", (limite_faxina,))
            conexao.commit()

        cursor.execute("SELECT total FROM contador_autorais WHERE data_alvo = ?", (data_alvo,))
        linha = cursor.fetchone()
        conexao.close()
        return linha[0] if linha else 0
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro no contador de sorteio: {e}")
        return 0

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

def separar_alvo_e_topico(valor):
    """
    Recebe "-1003673555953:1", "-1003673555953", "@canal" ou None e devolve
    uma tupla (alvo_pronto_para_o_telethon, topico_id_ou_None).
    Resolve o formato composto que o painel do bot_mestre grava.
    """
    bruto = str(valor or "").strip()
    if not bruto or bruto in ["Não definida", "Não definido", "None"]:
        return None, None

    base = bruto
    topico = None

    if ":" in bruto:
        partes = bruto.split(":")
        base = partes[0].strip()
        if len(partes) > 1 and partes[1].strip().isdigit():
            topico = int(partes[1].strip())

    if base.lstrip('-').isdigit():
        return int(base), topico

    return base, topico

@client.on(events.NewMessage())
async def interceptar_e_espelhar(event):
    config_atual = carregar_config_autorais()
    
    # ✅ VERIFICAÇÃO DE PAUSA GLOBAL DO ROBÔ AUTORAL
    if config_atual.get("pausar_robo_completo", False):
        return
        
    chat = await event.get_chat()
    
    # --- A MÁGICA ACONTECE AQUI ---
    if chat and hasattr(chat, 'title'):
        salvar_nome_grupo(str(chat.id), chat.title)
    # ------------------------------
    
    origem_configurada, topico_embutido = separar_alvo_e_topico(config_atual.get('origem'))
    topico_configurado = config_atual.get('origem_topico')

    # ✅ O tópico colado no ID pelo painel tem prioridade sobre a chave separada
    if topico_embutido is not None:
        topico_configurado = topico_embutido
    if isinstance(topico_configurado, str) and topico_configurado.strip().isdigit():
        topico_configurado = int(topico_configurado.strip())

    eh_origem = False

    if isinstance(origem_configurada, int):
        # ✅ Compara pelo número puro, ignorando prefixo -100 e sinal negativo
        num_config = str(origem_configurada).replace("-100", "").lstrip("-")
        num_evento = str(getattr(event, 'chat_id', "") or "").replace("-100", "").lstrip("-")
        if num_config and num_config == num_evento:
            eh_origem = True
    elif isinstance(origem_configurada, str):
        username_chat = getattr(chat, 'username', None)
        if username_chat and username_chat.lower() == origem_configurada.lstrip('@').lower():
            eh_origem = True

    # ✅ VERIFICAÇÃO DE TÓPICO (Subcanal) - None significa "ler tudo"
    if eh_origem and topico_configurado is not None:
        topic_id = None
        reply_info = getattr(event.message, 'reply_to', None)
        if reply_info:
            topic_id = getattr(reply_info, 'reply_to_top_id', None) or getattr(reply_info, 'reply_to_msg_id', None)

        # O Tópico "Geral" costuma ser o ID 1 ou vir nulo na API do Telegram
        t_evento = topic_id if topic_id else 1
        t_config = topico_configurado if topico_configurado else 1

        if t_evento != t_config:
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

                # ✅ Destino também pode vir no formato composto "-100123:5"
                destino_final, destino_topico = separar_alvo_e_topico(config_atual.get('destino'))
                if destino_final is None:
                    raise ValueError("Destino não configurado no painel de Vídeos Autorais.")

                kwargs_envio = {}
                if destino_topico and destino_topico > 1:
                    kwargs_envio['reply_to'] = destino_topico

                msg_enviada = await client.send_file(
                    destino_final,
                    file=caminho_video,
                    caption=legenda_final,
                    parse_mode='html',
                    **kwargs_envio
                )
                if EXIBIR_LOGS: logger.info("🚀 Vídeo publicado no canal de destino com a nova legenda autoral!")
                
                # ✅ Regra dinâmica de dias e limite de vídeos lida diretamente do painel
                dias_retorno = config_atual.get('dias_retorno', 15)
                limite_videos = config_atual.get('limite_videos', 5)
                
                agora = datetime.now()
                data_alvo = (agora + timedelta(days=dias_retorno)).strftime("%Y-%m-%d")
                
                fila_dados = ler_fila_retorno()
                # 🎲 SORTEIO JUSTO (Amostragem de Reservatório)
                # Todo vídeo do dia tem a mesma chance de ser escolhido, e não só os primeiros.
                total_ofertas = contar_ofertas_dia(data_alvo)
                candidatos = [v for v in fila_dados.get("fila", []) if v.get("data_alvo") == data_alvo and not v.get("processado")]

                foi_sorteado = False
                item_descartado = None

                if len(candidatos) < limite_videos:
                    # Ainda há vaga aberta: entra direto para começar a encher o reservatório
                    foi_sorteado = True
                elif total_ofertas > 0 and random.random() < (limite_videos / total_ofertas):
                    # Reservatório cheio: este vídeo compra a vaga de um sorteado anterior
                    foi_sorteado = True
                    item_descartado = random.choice(candidatos)

                if foi_sorteado:
                    novo_caminho = f"archive/{os.path.basename(caminho_video)}"
                    os.rename(caminho_video, novo_caminho)
                    
                    id_unico = f"autoral_{int(agora.timestamp())}_{random.randint(1000, 9999)}"

                    if item_descartado:
                        # Devolve a vaga: apaga o arquivo do antigo e tira ele da fila
                        caminho_antigo = item_descartado.get("caminho_arquivo")
                        if caminho_antigo and os.path.exists(caminho_antigo):
                            try: os.remove(caminho_antigo)
                            except Exception: pass
                        fila_dados["fila"] = [v for v in fila_dados.get("fila", []) if v.get("id_unico") != item_descartado.get("id_unico")]
                        if EXIBIR_LOGS: logger.info(f"🔄 [Sorteio Autorais] Vídeo nº {total_ofertas} do dia tomou a vaga de {item_descartado.get('id_unico')}.")
                    
                    fila_dados.setdefault("fila", []).append({
                        "id_unico": id_unico,
                        "msg_id_destino": msg_enviada.id,
                        "legenda": texto_convertido,
                        "caminho_arquivo": novo_caminho,
                        "data_captura": agora.strftime("%Y-%m-%d %H:%M:%S"),
                        "data_alvo": data_alvo,
                        "horario_disparo": "",
                        "processado": False
                    })
                    salvar_fila_retorno(fila_dados)
                    if EXIBIR_LOGS: logger.info(f"🎯 [Sorteio Autorais] Vídeo nº {total_ofertas} do dia SORTEADO para retorno em {data_alvo}.")
                else:
                    try:
                        os.remove(caminho_video)
                        if EXIBIR_LOGS: logger.info(f"🎲 [Sorteio Autorais] Vídeo nº {total_ofertas} do dia não sorteado (chance era {limite_videos}/{total_ofertas}). Removido do disco.")
                    except Exception:
                        pass

                # 🎲 SORTEIO JUSTO DO GRUPO PÚBLICO (Amostragem de Reservatório)
                # Loteria INDEPENDENTE, disparada pelo mesmo evento e sobre o mesmo vídeo.
                # Motor idêntico ao dos Autorais, com contador, fila e regras próprias.
                try:
                    config_pub = ler_config_bd_autorais("submissao_config", {})
                    if config_pub.get("ativo") and not config_pub.get("repost_pausado", False):
                        dias_publico = config_pub.get("repost_dias", 15)
                        limite_publico = config_pub.get("repost_limite", 6)
                        data_alvo_pub = (agora + timedelta(days=dias_publico)).strftime("%Y-%m-%d")

                        fila_pub = ler_fila_publico()
                        total_ofertas_pub = contar_ofertas_dia_publico(data_alvo_pub)
                        candidatos_pub = [v for v in fila_pub.get("fila", []) if v.get("data_alvo") == data_alvo_pub and not v.get("processado")]

                        foi_sorteado_pub = False
                        item_descartado_pub = None

                        if len(candidatos_pub) < limite_publico:
                            # Ainda há vaga aberta: entra direto para começar a encher o reservatório
                            foi_sorteado_pub = True
                        elif total_ofertas_pub > 0 and random.random() < (limite_publico / total_ofertas_pub):
                            # Reservatório cheio: este vídeo compra a vaga de um sorteado anterior
                            foi_sorteado_pub = True
                            item_descartado_pub = random.choice(candidatos_pub)

                        if foi_sorteado_pub:
                            id_unico_pub = f"publico_{int(agora.timestamp())}_{random.randint(1000, 9999)}"

                            # ✅ Grava o nome real do produto na legenda, no formato que o
                            # painel e o motor de repostagem sabem ler ("📦 Item:").
                            nome_produto_pub = texto_ia.split('\n')[0].strip() if texto_ia else "Produto Exclusivo"
                            legenda_publico = f"📦 Item: {nome_produto_pub}\n\n{legenda_final}"

                            if item_descartado_pub:
                                # Devolve a vaga: o antigo sai da fila do Público
                                fila_pub["fila"] = [v for v in fila_pub.get("fila", []) if v.get("id_unico") != item_descartado_pub.get("id_unico")]
                                if EXIBIR_LOGS: logger.info(f"🔄 [Sorteio Público] Vídeo nº {total_ofertas_pub} do dia tomou a vaga de {item_descartado_pub.get('id_unico')}.")

                            fila_pub.setdefault("fila", []).append({
                                "id_unico": id_unico_pub,
                                "msg_id_destino": msg_enviada.id,
                                "legenda": legenda_publico,
                                "data_captura": agora.strftime("%Y-%m-%d %H:%M:%S"),
                                "data_alvo": data_alvo_pub,
                                "horario_disparo": "",
                                "processado": False,
                                "data_postagem": ""
                            })
                            salvar_fila_publico(fila_pub)
                            if EXIBIR_LOGS: logger.info(f"🎯 [Sorteio Público] Vídeo nº {total_ofertas_pub} do dia SORTEADO para o Grupo Público em {data_alvo_pub}.")
                        else:
                            if EXIBIR_LOGS: logger.info(f"🎲 [Sorteio Público] Vídeo nº {total_ofertas_pub} do dia não sorteado (chance era {limite_publico}/{total_ofertas_pub}).")
                except Exception as e:
                    if EXIBIR_LOGS: logger.error(f"❌ [Sorteio Público] Falha no sorteio: {e}")

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

async def processar_fila_autorais_loop():
    if EXIBIR_LOGS: logger.info("🚀 [Motor Autorais] Loop de processamento autônomo iniciado.")
    
    while True:
        try:
            fila_dados = ler_fila_retorno()
            fila = fila_dados.get("fila", [])
            
            if not fila:
                await asyncio.sleep(60)
                continue
                
            config_atual = carregar_config_autorais()
            
            # Se pausado, não processa postagens (empurra organicamente)
            if config_atual.get("pausar_robo_completo", False) or config_atual.get("pausar_repostagem", False):
                await asyncio.sleep(60)
                continue

            agora = datetime.now()
            hoje_str = agora.strftime("%Y-%m-%d")
            
            # --- 1. MOTOR MATEMÁTICO E FAXINA DE ATRASADOS ---
            itens_desagendados = []
            houve_limpeza = False
            
            for item in fila:
                if item.get("processado"): continue
                
                if not item.get("horario_disparo"):
                    data_alvo = item.get("data_alvo")
                    
                    # ✅ TRAVA DE SEGURANÇA: Se a data ficou no passado, o vídeo perde a validade e é excluído sumariamente
                    if data_alvo < hoje_str:
                        caminho_arquivo = item.get("caminho_arquivo")
                        if caminho_arquivo and os.path.exists(caminho_arquivo):
                            try: os.remove(caminho_arquivo)
                            except: pass
                        
                        try:
                            conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
                            cursor = conexao.cursor()
                            cursor.execute("DELETE FROM fila_autorais WHERE id_unico = ?", (item["id_unico"],))
                            conexao.commit()
                            conexao.close()
                            houve_limpeza = True
                            if EXIBIR_LOGS: logger.info(f"🧹 [Auto-Limpeza] Vídeo Autoral retido e vencido ({data_alvo}) foi deletado para evitar avalanche.")
                        except Exception as e:
                            pass
                        continue # Pula para o próximo vídeo, este já foi apagado
                        
                    # Se for EXATAMENTE o dia de hoje, adiciona para ser postado!
                    if data_alvo == hoje_str:
                        itens_desagendados.append(item)
            
            if houve_limpeza:
                # Recarrega a fila do banco de dados para evitar tentar processar os arquivos que acabamos de deletar
                fila_dados = ler_fila_retorno()
                fila = fila_dados.get("fila", [])
                    
            if itens_desagendados:
                # ⏰ Janela lida do painel (Regras de Repostagem > Janela de Horário)
                config_fila = {
                    "inicio": int(config_atual.get("inicio", 10)),
                    "fim": int(config_atual.get("fim", 20)),
                    "modo": "aleatorio", # Vídeos de retorno misturam-se naturalmente
                    "intervalo_dias": 1  # 1 = usa o ramo diluído (a data_alvo já cuidou do atraso)
                }
                
                if EXIBIR_LOGS: logger.info(f"⚙️ [Motor Autorais] Acionando Motor Central para {len(itens_desagendados)} vídeos de retorno...")
                calcular_horarios_distribuicao(itens_desagendados, config_fila, forcar=False)
                salvar_fila_retorno(fila_dados)

            # --- 2. EXECUÇÃO DOS DISPAROS (Catraca do Motor) ---
            houve_disparo = False
            itens_restantes = []
            
            for item in fila:
                if item.get("processado"):
                    itens_restantes.append(item)
                    continue
                    
                hd_str = item.get("horario_disparo")
                deve_disparar = False
                
                if hd_str:
                    try:
                        hd_obj = datetime.strptime(hd_str, "%Y-%m-%d %H:%M:%S")
                        if agora >= hd_obj:
                            deve_disparar = True
                    except: pass
                    
                if deve_disparar:
                    caminho_arquivo = item.get("caminho_arquivo")
                    legenda = item.get("legenda")
                    
                    try:
                        if os.path.exists(caminho_arquivo):
                            await client.send_file(
                                config_atual['origem'],
                                file=caminho_arquivo,
                                caption=legenda,
                                parse_mode='md'
                            )
                            if EXIBIR_LOGS: logger.info(f"✅ [Motor Autorais] Vídeo de retorno {item.get('id_unico')} publicado com sucesso!")
                            
                            os.remove(caminho_arquivo)
                            if EXIBIR_LOGS: logger.info("🧹 Ficheiro arquivado removido após postagem final.")
                        else:
                            if EXIBIR_LOGS: logger.warning(f"⚠️ Ficheiro arquivado não encontrado em {caminho_arquivo}.")
                    except Exception as e:
                        if EXIBIR_LOGS: logger.error(f"❌ Falha no disparo de retorno: {e}")
                        
                    item["processado"] = True
                    houve_disparo = True
                    
                itens_restantes.append(item)
                
            if houve_disparo:
                fila_dados["fila"] = itens_restantes
                salvar_fila_retorno(fila_dados)

        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro no loop de postagem de autorais: {e}")
            
        await asyncio.sleep(60) # Respira 1 minuto e volta a procurar

async def main():
    if EXIBIR_LOGS: logger.info("⏳ Iniciando o robô Espelhador Isolado...")
    await client.start()
    
    if EXIBIR_LOGS: logger.info("🔄 Sincronizando banco de dados de grupos...")
    try:
        await client.get_dialogs()
        
        # ✅ Lógica de Identificação Automática Visual
        config_atual = carregar_config_autorais()
        for chave in ['origem', 'destino']:
            alvo, _topico_ignorado = separar_alvo_e_topico(config_atual.get(chave))
            if alvo is not None:
                try:
                    entidade = await client.get_entity(alvo)
                    nome_alvo = getattr(entidade, 'title', getattr(entidade, 'username', str(alvo)))
                    # ✅ Grava no cache com a chave crua E com o ID base, para o painel achar
                    salvar_nome_grupo(str(alvo), nome_alvo)
                    salvar_nome_grupo(str(config_atual.get(chave)), nome_alvo)
                    if EXIBIR_LOGS: logger.info(f"✅ Nome da {chave} ({nome_alvo}) extraído e salvo no cache automaticamente.")
                except Exception as err:
                    if EXIBIR_LOGS: logger.warning(f"⚠️ Não foi possível auditar a {chave} na inicialização: {err}")
                    
        if EXIBIR_LOGS: logger.info("✅ Sincronização concluída! ID do grupo reconhecido.")
    except Exception as e:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Aviso na sincronização: {e}")

    # Aciona o Loop do motor em Background
    asyncio.create_task(processar_fila_autorais_loop())
    
    if EXIBIR_LOGS: logger.info("🤖 Sistema a rodar. A escutar o grupo de origem continuamente...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
