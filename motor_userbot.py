import os
import json
import logging
import asyncio
import re
from datetime import datetime
import time
import hashlib
import aiohttp
from telethon import utils
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument
from dotenv import load_dotenv
from utils import registrar_erro_json
from motor_filas import calcular_horarios_distribuicao # ⚙️ Novo Motor Centralizado
from zoneinfo import ZoneInfo

load_dotenv()
EXIBIR_LOGS = True

FUSO_STR = "America/Sao_Paulo"
fuso_horario = ZoneInfo(FUSO_STR)

# ✅ Cria a pasta temp isolada na inicialização
os.makedirs("temp", exist_ok=True)

# FORÇA O FUSO HORÁRIO DO BRASIL NA MEMÓRIA DO SCRIPT
os.environ['TZ'] = 'America/Sao_Paulo'
time.tzset()
if EXIBIR_LOGS: print("⏰ Fuso horário ajustado internamente para America/Sao_Paulo")

# 1. CREDENCIAIS DA CONTA (Telegram)
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
# As chaves da Shopee e do Gemini foram movidas para os módulos centrais.

# ✅ Importando as pontes centrais da IA e da Shopee
from api_gemini import analisar_video_gemini
from api_shopee import converter_link_shopee

# 2. CONFIGURAÇÕES GERAIS DO ESPIÃO
LIMITE_REGISTROS_HASH = 1000

if EXIBIR_LOGS:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    logger = logging.getLogger(__name__)

# ✅ SISTEMA DE AUTOLIMPEZA E AUTO-CURA
def limpar_travas_fantasma(nome_sessao):
    import glob
    import os
    arquivos_trava = glob.glob(f"{nome_sessao}.session-journal") + glob.glob(f"{nome_sessao}.session.lock")
    for arquivo in arquivos_trava:
        try:
            os.remove(arquivo)
            if EXIBIR_LOGS: logger.info(f"🧹 [Auto-cura] Trava fantasma de crash removida: {arquivo}")
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ [Auto-cura] Falha ao tentar remover trava {arquivo}: {e}")

# Limpa resíduos de base de dados trancada antes de iniciar
limpar_travas_fantasma('sessao_espiao')

client = TelegramClient('sessao_espiao', API_ID, API_HASH)

import sqlite3
import random

def ler_config_bd_espiao(chave, padrao=None):
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

def salvar_config_bd_espiao(chave, dados):
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        dados_str = json.dumps(dados, ensure_ascii=False)
        cursor.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)", (chave, dados_str))
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao salvar '{chave}' no SQLite: {e}")

def carregar_alvos():
    dados = ler_config_bd_espiao("alvos_espiao", padrao={"alvos": []})
    return dados.get("alvos", [])

def ler_excecao_ponte():
    """Lê dinamicamente o destino configurado no painel Autorais para atuar como ponte imune."""
    dados = ler_config_bd_espiao("autorais_config", padrao={})
    val = str(dados.get("destino", "")).strip().lower()
    return val if val else None

def verificar_e_registrar_espelho(link_shopee, contexto="global"):
    agora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        
        # Limpeza de links com mais de 24 horas no contexto específico
        cursor.execute("DELETE FROM registros_unicos WHERE tipo = 'espelho' AND contexto = ? AND datetime(data_registro) <= datetime('now', '-1 day')", (contexto,))
        
        # Verifica se o link já existe
        cursor.execute("SELECT 1 FROM registros_unicos WHERE identificador = ? AND contexto = ? AND tipo = 'espelho'", (link_shopee, contexto))
        existe = cursor.fetchone()
        
        if existe:
            conexao.close()
            return True
            
        # Regista novo link se for novidade
        cursor.execute("INSERT INTO registros_unicos (identificador, contexto, tipo, data_registro) VALUES (?, ?, 'espelho', ?)", (link_shopee, contexto, agora_str))
        conexao.commit()
        conexao.close()
        return False
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao verificar espelho no SQLite: {e}")
        return False

def calcular_hash_video(caminho_arquivo):
    hash_sha256 = hashlib.sha256()
    try:
        if EXIBIR_LOGS: logger.info(f"🔍 A calcular a assinatura digital (SHA-256) do ficheiro: {caminho_arquivo}...")
        with open(caminho_arquivo, "rb") as f:
            for bloco in iter(lambda: f.read(4096), b""):
                hash_sha256.update(bloco)
        resultado = hash_sha256.hexdigest()
        if EXIBIR_LOGS: logger.info(f"✅ Assinatura única identificada: {resultado[:10]}...")
        return resultado
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro na leitura física para calcular hash do ficheiro {caminho_arquivo}: {e}")
        return None

def verificar_e_registrar_hash(hash_video, contexto="global"):
    agora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        
        cursor.execute("SELECT 1 FROM registros_unicos WHERE identificador = ? AND contexto = ? AND tipo = 'hash'", (hash_video, contexto))
        existe = cursor.fetchone()
        
        if existe:
            conexao.close()
            return True
            
        cursor.execute("INSERT INTO registros_unicos (identificador, contexto, tipo, data_registro) VALUES (?, ?, 'hash', ?)", (hash_video, contexto, agora_str))
        
        # Exclui os mais antigos para respeitar o limite global de segurança
        cursor.execute(f"DELETE FROM registros_unicos WHERE tipo = 'hash' AND contexto = ? AND identificador NOT IN (SELECT identificador FROM registros_unicos WHERE tipo = 'hash' AND contexto = ? ORDER BY data_registro DESC LIMIT {LIMITE_REGISTROS_HASH})", (contexto, contexto))
        
        conexao.commit()
        conexao.close()
        return False
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao verificar hash no SQLite: {e}")
        return False

def ler_fila_clonagem():
    return ler_config_bd_espiao("fila_clonagem", {"fila": []})

def salvar_fila_clonagem(dados):
    salvar_config_bd_espiao("fila_clonagem", dados)

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

def salvar_na_fila_clonagem(caminho_video, link_shopee, chat_origem="Desconhecida", nome_origem=None, msg_id=None):
    id_unico = f"clone_{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}"
    data_captura = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nome_origem_str = str(nome_origem) if nome_origem else str(chat_origem)
    
    try:
        dados = ler_fila_clonagem()
        item = {
            "id": id_unico,
            "chat_origem": str(chat_origem),
            "nome_origem": nome_origem_str,
            "msg_id": msg_id,
            "caminho_video": caminho_video,
            "link_original": link_shopee,
            "processado": False,
            "data_captura": data_captura
        }
        dados.setdefault("fila", []).append(item)
        salvar_fila_clonagem(dados)
        if EXIBIR_LOGS: logger.info(f"📦 Clone salvo de forma unificada no SQLite com sucesso (ID: {id_unico}).")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao salvar na fila unificada do SQLite: {e}")

def registrar_historico_espiao(nome_grupo):
    historico = ler_config_bd_espiao("historico_espiao", padrao={"total": 0, "grupos": {}})
    
    historico["total"] = historico.get("total", 0) + 1
    grupos = historico.get("grupos", {})
    grupos[nome_grupo] = grupos.get(nome_grupo, 0) + 1
    historico["grupos"] = grupos
    
    salvar_config_bd_espiao("historico_espiao", historico)
    if EXIBIR_LOGS: logger.info(f"📊 [Estatística] +1 vídeo contabilizado no SQLite para o grupo: {nome_grupo}")

# A função converter_link_shopee foi deletada daqui. O script usará a importada de api_shopee.py.

async def gerar_legenda_com_ia_espelhador(caminho_video):
    prompt = (
        "Assista ao vídeo e identifique qual é o produto demonstrado. "
        "Sua resposta deve conter EXATAMENTE duas linhas.\n"
        "Na primeira linha, escreva APENAS o nome do produto acompanhado de um emoji correspondente no início (Exemplo: 👟 Tênis Casual Feminino).\n"
        "Na segunda linha, inclua as hashtags correspondentes aos setores do produto. IMPORTANTE: Se utilizar mais de uma hashtag, separe-as APENAS com espaços em branco, NUNCA utilize vírgulas.\n"
        "REGRA DE CONTEXTO: Categorize o produto baseando-se estritamente na sua utilidade prática e ambiente de uso. É terminantemente proibido utilizar atalhos semânticos ou associações literais de palavras.\n"
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

PADRAO_SHOPEE = re.compile(r'(?:https?://)?(?:s\.shopee\.com\.br|shope\.ee|br\.shp\.ee|shp\.ee)/[^\s]+', re.IGNORECASE)

def extrair_link_shopee(event):
    """Busca links no texto puro e dentro de hiperlinks escondidos no Telegram"""
    # 1. Tenta achar no texto visível
    texto = event.raw_text or ""
    match = PADRAO_SHOPEE.search(texto)
    if match:
        link = match.group(0)
        if not link.startswith("http"):
            link = "https://" + link
        return link.rstrip(").,;!?")
        
    # 2. Busca profunda: procura nos botões e textos embutidos (hiperlinks)
    if event.entities:
        for entity in event.entities:
            if hasattr(entity, 'url') and entity.url:
                if PADRAO_SHOPEE.search(entity.url):
                    return entity.url
    return None

@client.on(events.NewMessage)
async def interceptar_mensagem(event):
    alvos = carregar_alvos()
    
    destino_autorais = ler_excecao_ponte()
    
    # Verifica se a mensagem veio de um dos grupos monitorados
    chat = await event.get_chat()
    chat_id = str(chat.id)
    chat_username = f"@{chat.username.lower()}" if getattr(chat, 'username', None) else ""
    
    # Corrige formatações de IDs que o Telegram envia (com ou sem o -100)
    chat_id_completo = f"-100{chat.id}" if not chat_id.startswith("-100") else chat_id
    
    eh_ponte = False
    if destino_autorais and destino_autorais in [chat_username, chat_id, chat_id_completo]:
        eh_ponte = True

    # Injeção dinâmica: Se for a ponte, garante que ela será ouvida como alvo
    if eh_ponte and destino_autorais not in [str(a).lower() for a in alvos]:
        alvos.append(destino_autorais)

    # Identificação de Autoria Absoluta (Perfil Principal e Bot Oficial)
    try:
        me = await client.get_me()
        remetente_id = getattr(event, 'sender_id', None)
        
        # Puxa o ID do Bot Oficial direto do seu Token (os números antes do ':')
        bot_token = os.getenv('TELEGRAM_TOKEN', '')
        bot_oficial_id = int(bot_token.split(':')[0]) if ':' in bot_token else None
        
        # Bloqueia se foi enviado pelo Userbot OU pelo Bot Oficial
        foi_nossa_equipe = (remetente_id == me.id) or (remetente_id == bot_oficial_id)
    except Exception:
        foi_nossa_equipe = False

    if foi_nossa_equipe and chat_username != "@shopee_video_afiliado":
        if EXIBIR_LOGS: logger.info("🛡️ [Espião] Postagem do próprio sistema bloqueada (Userbot ou Bot Oficial).")
        return

    if event.out and not eh_ponte and chat_username != "@shopee_video_afiliado":
        if EXIBIR_LOGS: logger.info("🛡️ [Espião] Trava de canais ativada: Ignorando evento.")
        return
    
    # ✅ NOVO: Identifica se a mensagem foi enviada em um Tópico (Subgrupo)
    topico_id_evento = None
    if event.message.reply_to:
        topico_id_evento = getattr(event.message.reply_to, 'forum_topic_id', getattr(event.message.reply_to, 'reply_to_msg_id', None))

    # ✅ NOVO: Verifica se o grupo e o subgrupo batem com os alvos do banco de dados
    eh_alvo_espiao = False
    for alvo in alvos:
        alvo_str = str(alvo).lower()
        alvo_base = alvo_str.split(':')[0]
        alvo_topico = int(alvo_str.split(':')[1]) if ':' in alvo_str and alvo_str.split(':')[1].isdigit() else None
        
        if alvo_base in [chat_id, chat_id_completo, chat_username]:
            if alvo_topico is not None:
                # Trata o Tópico Geral (pode vir como 1 ou vazio)
                t_evento = topico_id_evento if topico_id_evento else 1
                t_alvo = alvo_topico if alvo_topico else 1
                if t_evento == t_alvo:
                    eh_alvo_espiao = True
                    break
            else:
                # Se não tem tópico na configuração, escuta o grupo todo
                eh_alvo_espiao = True
                break

    if not eh_alvo_espiao:
        return

    texto_original = event.text or ""
    link_capturado = extrair_link_shopee(event)
    
    # Ignora mensagens de bate-papo, processa apenas se tiver link e mídia
    if link_capturado:
        
        # ✅ NOVO: Bloqueio de vídeos duplicados no módulo Espião (Contexto Isolado)
        if verificar_e_registrar_espelho(link_capturado, contexto="espiao"):
            if EXIBIR_LOGS: logger.info(f"🪞 [Espião] Duplicidade barrada! O produto {link_capturado} já foi capturado nas últimas 24 horas.")
            return # Encerra o processamento da mensagem aqui mesmo, sem baixar o vídeo
            
        # ✅ TRAVA ESTRITA DE MÍDIA: Filtra rigorosamente apenas vídeos, ignorando fotos
        if getattr(event, 'video', None) is not None:
            if EXIBIR_LOGS: logger.info(f"🎯 ALVO LOCALIZADO! Link da Shopee extraído cirurgicamente: {link_capturado}")
            
            # ✅ CORREÇÃO DO ERRO FATAL (texto_original em vez de texto)
            if "magazineluiza" in texto_original.lower() or "meli.li" in texto_original.lower() or "mercadolivre" in texto_original.lower():
                if EXIBIR_LOGS: logger.info("✂️ Concorrência ignorada: A postagem continha outros domínios, mas apenas o da Shopee foi filtrado.")
            
            if EXIBIR_LOGS: logger.info("📥 Iniciando download do vídeo em segundo plano...")
            caminho_salvo = await event.download_media(file="temp/temp_clone_")

            # ✅ NOVA TRAVA DE QUALIDADE E UPSCALING
            caminho_salvo = await verificar_e_otimizar_video(caminho_salvo)
            
            hash_arquivo = calcular_hash_video(caminho_salvo)
            
            if hash_arquivo and verificar_e_registrar_hash(hash_arquivo):
                if EXIBIR_LOGS: logger.warning(f"🚫 Clone bloqueado! O vídeo possui uma assinatura digital idêntica a um ficheiro já processado.")
                try:
                    os.remove(caminho_salvo)
                    if EXIBIR_LOGS: logger.info("🧹 Ficheiro físico duplicado eliminado com sucesso para poupar espaço.")
                except Exception as e:
                    if EXIBIR_LOGS: logger.error(f"❌ Erro ao tentar remover ficheiro duplicado: {e}")
                return
                
            # 📊 Nome real do grupo, já disponível via Telethon neste momento
            nome_chat = getattr(chat, 'title', chat_username if chat_username else chat_id)

            salvar_na_fila_clonagem(caminho_salvo, link_capturado, chat_origem=chat_id_completo, nome_origem=nome_chat, msg_id=event.id)
            
            # 📊 Adiciona a pontuação ao painel estatístico do Espião
            registrar_historico_espiao(nome_chat)
        else:
            if EXIBIR_LOGS: logger.info(f"⏭️ Ignorado: O link {link_capturado} foi encontrado, mas a postagem não contém um anexo de vídeo direto.")

# --- MOTOR DO ESPELHADOR (USERBOT) ---
def ler_espelhos_config():
    try:
        with open("espelhos_config.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"rotas": []}

def ler_fila_espelhador():
    try:
        with open("fila_espelhador.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"fila": []}

def salvar_fila_espelhador(dados):
    with open("fila_espelhador.json", "w") as f:
        json.dump(dados, f, indent=4)

async def processar_fila_espelhador_loop():
    from datetime import timedelta
    import random
    while True:
        try:
            fila_dados = ler_fila_espelhador()
            fila = fila_dados.get("fila", [])
            if not fila:
                await asyncio.sleep(60) # Atraso alargado para poupar recursos na rede
                continue
                
            config = ler_espelhos_config()
            rotas = {r.get("nome"): r for r in config.get("rotas", [])}
            
            itens_restantes = []
            agora = datetime.now(fuso_horario) # ✅ Usa o fuso horário oficial
            hoje_str = agora.strftime("%Y-%m-%d")
            houve_alteracao_rota = False
            houve_agendamento = False
            houve_disparo = False
            
            # --- 1. PREPARAÇÃO PARA O MOTOR CENTRAL ---
            itens_por_rota_desagendados = {}
            for item in fila:
                nome_rota = item.get("nome_rota")
                rota_config = rotas.get(nome_rota)
                
                if not rota_config: continue
                
                # Se o botão de Forçar for apertado no Telegram, limpa o horário!
                esvaziar_agora = rota_config.get("esvaziar_agora", False)
                if esvaziar_agora and not item.get("processado"):
                    item["horario_disparo"] = ""
                    
                if item.get("horario_disparo") or item.get("processado"):
                    continue # Já tem carimbo de distribuição matemática ou já foi postado
                
                data_captura_obj = datetime.strptime(item["data_captura"], "%Y-%m-%d %H:%M:%S")
                data_captura_str = data_captura_obj.strftime("%Y-%m-%d")
                intervalo_dias = int(rota_config.get("intervalo_dias", 1))
                
                if intervalo_dias == 0 or data_captura_str < hoje_str or esvaziar_agora:
                    itens_por_rota_desagendados.setdefault(nome_rota, []).append(item)

            for nome_rota, itens in itens_por_rota_desagendados.items():
                rota_config = rotas.get(nome_rota)
                if not rota_config: continue
                
                config_fila = {
                    "inicio": int(rota_config.get("inicio", 10)),
                    "fim": int(rota_config.get("fim", 22)),
                    "modo": rota_config.get("modo", "ordem"),
                    "intervalo_dias": int(rota_config.get("intervalo_dias", 1))
                }
                
                forcar_rota = rota_config.get("esvaziar_agora", False)
                
                if EXIBIR_LOGS: logger.info(f"📅 [Espelhador] Motor Central acionado para {len(itens)} vídeos na rota '{nome_rota}' (Forçar: {forcar_rota})...")
                calcular_horarios_distribuicao(itens, config_fila, forcar=forcar_rota)
                houve_agendamento = True
            
            # --- 2. EXECUÇÃO DOS DISPAROS (Confiando 100% no Motor) ---
            for item in fila:
                nome_rota = item.get("nome_rota")
                rota_config = rotas.get(nome_rota)
                
                if not rota_config:
                    itens_restantes.append(item)
                    continue
                    
                horario_disparo_str = item.get("horario_disparo")
                deve_disparar = False
                
                if not item.get("processado") and horario_disparo_str:
                    try:
                        horario_disparo_obj = datetime.strptime(horario_disparo_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario)
                        if agora >= horario_disparo_obj:
                            deve_disparar = True
                    except Exception: pass
                
                if deve_disparar:
                    try:
                        chat_origem_bruto = item["chat_origem"]
                        chat_origem = int(chat_origem_bruto) if str(chat_origem_bruto).lstrip('-').isdigit() else chat_origem_bruto
                        msg_id = item["msg_id"]
                        destino = item["destino"]
                        texto = item["texto_processado"]
                        
                        mensagem_original = await client.get_messages(chat_origem, ids=msg_id)
                        if mensagem_original:
                            # ✅ SEGUNDA TRAVA DE SEGURANÇA: Verifica novamente o tipo de mídia antes de enviar
                            if getattr(mensagem_original, 'video', None) is None:
                                if EXIBIR_LOGS: logger.warning(f"🚫 [Segurança] Espelhador abortou o envio! A mensagem {msg_id} perdeu o formato de vídeo.")
                            else:
                                try:
                                    entidade_destino = await client.get_entity(destino)
                                except ValueError:
                                    id_teste = int(destino) if str(destino).lstrip('-').isdigit() else destino
                                    entidade_destino = await client.get_entity(id_teste)

                                msg_enviada = await client.send_message(entidade_destino, texto, file=mensagem_original.media, parse_mode="html")
                                
                                item["msg_postada_id"] = msg_enviada.id # Grava o ID para o painel mostrar o link de destino
                                if EXIBIR_LOGS: logger.info(f"✅ [Espelhador] Disparo concluído na rota '{nome_rota}' para {destino}.")
                                
                                await asyncio.sleep(15) # Catraca anti-ban
                        else:
                            if EXIBIR_LOGS: logger.warning(f"⚠️ [Espelhador] Mensagem original {msg_id} apagada antes do disparo na rota '{nome_rota}'.")
                    except Exception as e:
                        if EXIBIR_LOGS: logger.error(f"❌ [Espelhador] Falha no disparo da rota '{nome_rota}': {e}")
                    
                    # ✅ MANTÉM NO HISTÓRICO: O vídeo foi enviado, e agora fica salvo para aparecer no relatório!
                    item["processado"] = True
                    item["data_postagem"] = agora.strftime("%Y-%m-%d")
                    item["horario_postagem"] = agora.strftime("%H:%M")
                    itens_restantes.append(item)
                    houve_disparo = True
                else:
                    itens_restantes.append(item)
                    
            # 3. Trata comandos de ação manual e guarda os resultados
            for r in config.get("rotas", []):
                if r.get("esvaziar_agora"):
                    r["esvaziar_agora"] = False
                    houve_alteracao_rota = True
            
            if houve_alteracao_rota:
                with open("espelhos_config.json", "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
                    
            # Salva a fila se houver matemática nova, vídeos processados ou faxina.
            if len(fila) != len(itens_restantes) or houve_agendamento or houve_disparo:
                fila_dados["fila"] = itens_restantes
                salvar_fila_espelhador(fila_dados)
            
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro crítico no motor de distribuição do espelhador: {e}")
            registrar_erro_json(f"processar_fila_espelhador_loop: {e}", origem="espelhador.py")
        
        await asyncio.sleep(60) # Intervalo alargado para reduzir o peso na memória

@client.on(events.NewMessage)
async def motor_espelhador_userbot(event):
    chat = await event.get_chat()
    chat_id_str = str(chat.id)
    chat_username = f"@{chat.username.lower()}" if getattr(chat, 'username', None) else ""
    chat_id_completo = f"-100{chat.id}" if not chat_id_str.startswith("-100") else chat_id_str
    nome_chat = getattr(chat, 'title', chat_username if chat_username else chat_id_str)

    destino_autorais = ler_excecao_ponte()
    eh_ponte = False
    if destino_autorais and destino_autorais in [chat_username, chat_id_str, chat_id_completo]:
        eh_ponte = True

    # Identificação de Autoria Absoluta (Perfil Principal e Bot Oficial)
    try:
        me = await client.get_me()
        remetente_id = getattr(event, 'sender_id', None)
        
        # Puxa o ID do Bot Oficial direto do seu Token (os números antes do ':')
        bot_token = os.getenv('TELEGRAM_TOKEN', '')
        bot_oficial_id = int(bot_token.split(':')[0]) if ':' in bot_token else None
        
        # Bloqueia se foi enviado pelo Userbot OU pelo Bot Oficial
        foi_nossa_equipe = (remetente_id == me.id) or (remetente_id == bot_oficial_id)
    except Exception:
        foi_nossa_equipe = False

    if foi_nossa_equipe and chat_username != "@shopee_video_afiliado":
        if EXIBIR_LOGS: logger.info("🛡️ [Espelhador] Postagem do próprio sistema bloqueada (Userbot ou Bot Oficial).")
        return

    if event.out and not eh_ponte and chat_username != "@shopee_video_afiliado":
        if EXIBIR_LOGS: logger.info("🛡️ [Espelhador] Trava de canais ativada: Postagem própria ignorada.")
        return

    # ✅ NOVO: Identifica se a mensagem foi enviada em um Tópico (Subgrupo)
    topico_id_evento = None
    if event.message.reply_to:
        topico_id_evento = getattr(event.message.reply_to, 'forum_topic_id', getattr(event.message.reply_to, 'reply_to_msg_id', None))

    dados = ler_espelhos_config()
    rotas_ativas = []
    
    for r in dados.get("rotas", []):
        origens_rota = [str(o).lower() for o in r.get("origens", [])]
        if "origem" in r:
            origens_rota.append(str(r["origem"]).lower())
            
        # ✅ NOVO: Faz a checagem inteligente de origem + tópico
        para_esta_rota = False
        for origem in origens_rota:
            origem_base = origem.split(':')[0]
            origem_topico = int(origem.split(':')[1]) if ':' in origem and origem.split(':')[1].isdigit() else None
            
            if origem_base in [chat_id_str, chat_id_completo, chat_username]:
                if origem_topico is not None:
                    t_evento = topico_id_evento if topico_id_evento else 1
                    t_origem = origem_topico if origem_topico else 1
                    if t_evento == t_origem:
                        para_esta_rota = True
                        break
                else:
                    para_esta_rota = True
                    break
                    
        if para_esta_rota:
            rotas_ativas.append(r)
    
    if not rotas_ativas:
        return

    # ✅ TRAVA ESTRITA DE MÍDIA: Exige estritamente formato de vídeo, bloqueando fotografias
    if getattr(event, 'video', None) is None:
        if EXIBIR_LOGS: logger.info("⏭️ [Espelhador] Postagem descartada: Contém o link, mas a mídia não é um vídeo.")
        return

    texto_original = event.text or ""
    link_capturado = extrair_link_shopee(event)
    
    if not link_capturado:
        if EXIBIR_LOGS: logger.info("⏭️ Postagem ignorada: Não contém link da Shopee (nem embutido).")
        return
    
    if EXIBIR_LOGS: logger.info(f"🔄 [Espelhador] Interceptação acionada! Mídia e link detetados na origem {chat_id_str}.")
    if EXIBIR_LOGS: logger.info("🔗 [Espelhador] A converter o link da Shopee encontrado via API Central...")
    link_final_convertido = await converter_link_shopee(link_capturado, "geral", EXIBIR_LOGS)
    if EXIBIR_LOGS: logger.info("✅ [Espelhador] Sucesso: Link convertido utilizando a função nativa correta.")

    if EXIBIR_LOGS: logger.info("📥 [Espelhador] Descarregando vídeo temporário para análise da IA e verificação de duplicidade...")
    caminho_video_temp = await event.download_media(file="temp/temp_analise_espelho_")

    # ✅ NOVA TRAVA DE QUALIDADE E UPSCALING
    caminho_video_temp = await verificar_e_otimizar_video(caminho_video_temp)
    
    hash_arquivo = None
    if caminho_video_temp:
        # ✅ Calcula o hash uma única vez para usar de forma isolada em cada rota
        hash_arquivo = calcular_hash_video(caminho_video_temp)
        
        # ✅ MURALHA ANTI-LOOP REVERSO: Regista o vídeo na memória do canal de ORIGEM.
        # Assim, o robô sabe que o ficheiro já passou por lá e bloqueia qualquer reflexo de volta.
        if hash_arquivo:
            verificar_e_registrar_hash(hash_arquivo, contexto=chat_id_str)
            if chat_id_completo != chat_id_str:
                verificar_e_registrar_hash(hash_arquivo, contexto=chat_id_completo)
                
        titulo_ia = await gerar_legenda_com_ia_espelhador(caminho_video_temp)
        
        try:
            os.remove(caminho_video_temp)
            if EXIBIR_LOGS: logger.info("🧹 [Espelhador] Vídeo temporário removido do servidor após análise.")
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ [Espelhador] Erro ao remover vídeo temporário: {e}")
    else:
        titulo_ia = None

    if titulo_ia:
        linhas_ia = titulo_ia.split('\n')
        nome_produto = linhas_ia[0].strip()
        hashtags = '\n'.join(linhas_ia[1:]).strip() if len(linhas_ia) > 1 else ""
        
        texto_processado = f"<b>{nome_produto}</b>\n\n🔗 <b>Link do Produto:</b>\n{link_final_convertido}"
        if hashtags:
            texto_processado += f"\n\n<i>{hashtags}</i>"
            
        if EXIBIR_LOGS: logger.info("✅ [Espelhador] Legenda inteligente construída com sucesso (Título -> Link -> Hashtags).")
    else:
        texto_processado = f"🔗 <b>Link do Produto:</b>\n{link_final_convertido}"
        if EXIBIR_LOGS: logger.warning("⚠️ [Espelhador] Fallback de segurança ativado: Legenda base apenas com o link.")

    forward_origem_id = None
    if getattr(event, 'fwd_from', None) and getattr(event.fwd_from, 'from_id', None):
        try:
            fwd_id = utils.get_peer_id(event.fwd_from.from_id)
            forward_origem_id = f"-100{fwd_id}" if not str(fwd_id).startswith("-100") else str(fwd_id)
        except Exception:
            pass

    for rota in rotas_ativas:
        destino = rota["destino"]
        nome_rota = rota.get("nome", "Desconhecida")
        
        if forward_origem_id and (destino == forward_origem_id or destino.replace("-100", "") == forward_origem_id.replace("-100", "")):
            if EXIBIR_LOGS: logger.warning(f"🚫 [Anti-Loop Ativado] O vídeo nasceu no destino ({destino}). Ignorando a clonagem nesta rota.")
            continue
            
        # ✅ VERIFICAÇÃO DE DUPLICIDADE DE LINK (Usa o destino como contexto)
        if link_capturado and verificar_e_registrar_espelho(link_capturado, contexto=str(destino)):
            if EXIBIR_LOGS: logger.info(f"🪞 [Espelhador] Duplicidade barrada na rota '{nome_rota}'! O link já foi postado neste destino nas últimas 24h.")
            continue
            
        # ✅ VERIFICAÇÃO DE DUPLICIDADE FÍSICA (Usa o destino como contexto)
        if hash_arquivo and verificar_e_registrar_hash(hash_arquivo, contexto=str(destino)):
            if EXIBIR_LOGS: logger.warning(f"🚫 [Espelhador] Loop evitado na rota '{nome_rota}'! O ficheiro de vídeo exato já foi postado neste destino.")
            continue
            
        fila_dados = ler_fila_espelhador()
        item = {
            "id": f"espelho_{int(datetime.now().timestamp())}_{chat_id_str}",
            "chat_origem": chat_id_completo,
            "nome_origem": nome_chat,
            "msg_id": event.id,
            "destino": destino,
            "nome_rota": nome_rota,
            "texto_processado": texto_processado,
            "data_captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        fila_dados["fila"].append(item)
        salvar_fila_espelhador(fila_dados)
        if EXIBIR_LOGS: logger.info(f"📦 [Espelhador] Vídeo enfileirado dinamicamente na rota '{nome_rota}'.")

async def validar_e_obter_entidade(client, alvo):
    alvo_str = str(alvo).strip()
    
    if EXIBIR_LOGS: logger.info(f"🧹 [Auditor] Higienizando alvo bruto: {alvo_str}")

    # ✅ NOVO: Separa e guarda o ID do tópico (se existir) para não quebrar a API
    topico_id = None
    if ":" in alvo_str:
        partes = alvo_str.split(":", 1)
        alvo_str = partes[0]
        if partes[1].isdigit():
            topico_id = partes[1]

    # 1. Filtro de Links Privados (ex: https://t.me/c/12345678/10)
    match_privado = re.search(r't\.me/c/(\d+)', alvo_str)
    if match_privado:
        numero_extraido = match_privado.group(1)
        alvo_str = f"-100{numero_extraido}"
        if EXIBIR_LOGS: logger.info(f"🔗 [Auditor] Link privado detetado. Convertido para ID base: {alvo_str}")

    # 2. Filtro de Usernames e Links Públicos (ex: https://t.me/username)
    elif "t.me/" in alvo_str or alvo_str.startswith("@") or not alvo_str.lstrip('-').isdigit():
        username_puro = re.sub(r'https?://(www\.)?t\.me/', '', alvo_str)
        username_puro = username_puro.split('/')[0].split('?')[0]
        username_puro = username_puro.lstrip('@')
        
        variacoes_publicas = [f"@{username_puro}", username_puro]
        
        for var in variacoes_publicas:
            try:
                if EXIBIR_LOGS: logger.info(f"🔍 [Auditor] Testando variação de username: {var}")
                ent = await client.get_entity(var)
                if EXIBIR_LOGS: logger.info(f"✅ [Auditor] Variação {var} aceite pela API do Telegram!")
                id_final = f"{var}:{topico_id}" if topico_id else var
                return ent, id_final
            except Exception:
                continue
        raise Exception("Nenhuma variação de username funcionou.")

    # 3. Tratamento de IDs Numéricos (Agora sem duplicação!)
    so_numeros = re.sub(r'^-?(100)?', '', alvo_str)
    
    variacoes_numericas = [
        alvo_str, 
        f"-100{so_numeros}", 
        f"-{so_numeros}", 
        so_numeros
    ]
    
    variacoes_unicas = []
    for v in variacoes_numericas:
        if v not in variacoes_unicas:
            variacoes_unicas.append(v)
            
    for var in variacoes_unicas:
        try:
            if EXIBIR_LOGS: logger.info(f"🔍 [Auditor] Testando variação numérica de ID: {var}")
            ent = await client.get_entity(int(var))
            if EXIBIR_LOGS: logger.info(f"✅ [Auditor] Variação {var} aceite pela API do Telegram!")
            id_final = f"{var}:{topico_id}" if topico_id else str(var)
            return ent, id_final
        except Exception:
            continue
            
    raise Exception("Nenhuma variação de ID numérico funcionou.")

async def monitorar_status_alvos():
    ultimo_alvos = None
    ultimo_destino = None
    ultima_modificacao = 0

    if EXIBIR_LOGS: logger.info("🚀 Iniciando monitoramento ultraleve (1 min) para os alvos do Espião...")
    
    while True:
        try:
            # 1. Verifica a data de modificação do banco de dados (Custo zero pro CPU)
            try:
                modificacao_atual = os.path.getmtime("banco_dados.db")
            except OSError:
                modificacao_atual = 0

            if modificacao_atual != ultima_modificacao:
                # 2. Se o arquivo foi modificado, carregamos a lista
                dados_iniciais = ler_config_bd_espiao("alvos_espiao", {"alvos": [], "canal_destino": None, "status_alvos": {}})
                
                alvos_atuais = [str(a) for a in dados_iniciais.get("alvos", [])]
                destino_atual = str(dados_iniciais.get("canal_destino")) if dados_iniciais.get("canal_destino") else None

                # 3. Compara a "foto" (Snapshot). Mudou algo nos alvos ou no destino?
                if alvos_atuais != ultimo_alvos or destino_atual != ultimo_destino:
                    if EXIBIR_LOGS: logger.info("🔍 [Auditor] Mudança detectada nos alvos do Espião. Iniciando validação...")
                    
                    novos_status_coletados = {}
                    mapa_correcoes = {}
                    
                    for alvo in alvos_atuais:
                        try:
                            entidade, alvo_correto = await validar_e_obter_entidade(client, alvo)
                            nome = getattr(entidade, 'title', getattr(entidade, 'username', str(alvo_correto)))
                            novos_status_coletados[alvo_correto] = {"status": "ok", "nome": nome}
                            
                            if str(alvo) != alvo_correto:
                                mapa_correcoes[str(alvo)] = alvo_correto
                        except Exception:
                            novos_status_coletados[str(alvo)] = {"status": "erro", "erro": "Acesso negado/Link inválido"}
                            
                        await asyncio.sleep(2) # Pausa de segurança
                        
                    status_destino_coletado = None
                    if destino_atual:
                        try:
                            entidade_dest, dest_correto = await validar_e_obter_entidade(client, destino_atual)
                            nome_dest = getattr(entidade_dest, 'title', getattr(entidade_dest, 'username', str(dest_correto)))
                            status_destino_coletado = {"status": "ok", "nome": nome_dest}
                            if str(destino_atual) != dest_correto:
                                mapa_correcoes["_destino"] = dest_correto
                        except Exception:
                            status_destino_coletado = {"status": "erro", "nome": str(destino_atual)}
                        await asyncio.sleep(2)
                        
                    dados_frescos = ler_config_bd_espiao("alvos_espiao", {"alvos": [], "canal_destino": None, "status_alvos": {}})
                    alvos_reais_agora = [str(a) for a in dados_frescos.get("alvos", [])]
                    status_alvos_antigos = dados_frescos.get("status_alvos", {})
                    
                    status_alvos_final = {}
                    nova_lista_alvos = []
                    houve_alteracao = False
                    
                    for alvo in alvos_reais_agora:
                        alvo_final = mapa_correcoes.get(alvo, alvo)
                        nova_lista_alvos.append(alvo_final)
                        if alvo != alvo_final:
                            houve_alteracao = True
                    
                    for alvo_final in nova_lista_alvos:
                        if alvo_final in novos_status_coletados:
                            status_alvos_final[alvo_final] = novos_status_coletados[alvo_final]
                            if status_alvos_antigos.get(alvo_final) != novos_status_coletados[alvo_final]:
                                houve_alteracao = True
                        elif alvo_final in status_alvos_antigos:
                            status_alvos_final[alvo_final] = status_alvos_antigos[alvo_final]
                            
                    for alvo_antigo in status_alvos_antigos.keys():
                        if alvo_antigo not in nova_lista_alvos:
                            houve_alteracao = True
                            
                    destino_fresco = dados_frescos.get("canal_destino")
                    if destino_fresco:
                        if "_destino" in mapa_correcoes and str(destino_fresco) == str(destino_atual):
                            dados_frescos["canal_destino"] = mapa_correcoes["_destino"]
                            houve_alteracao = True
                            
                    if status_destino_coletado and dados_frescos.get("status_destino") != status_destino_coletado:
                        dados_frescos["status_destino"] = status_destino_coletado
                        houve_alteracao = True
                            
                    if houve_alteracao:
                        dados_frescos["alvos"] = nova_lista_alvos
                        dados_frescos["status_alvos"] = status_alvos_final
                        salvar_config_bd_espiao("alvos_espiao", dados_frescos)
                        
                    # 4. Salva a nova foto e atualiza a data de modificação
                    ultimo_alvos = nova_lista_alvos
                    ultimo_destino = str(dados_frescos.get("canal_destino")) if dados_frescos.get("canal_destino") else None
                    
                    try:
                        ultima_modificacao = os.path.getmtime("banco_dados.db")
                    except OSError:
                        ultima_modificacao = modificacao_atual
                        
                    if EXIBIR_LOGS: logger.info("✅ Auditoria do Espião concluída. Nomes atualizados!")
                else:
                    # O arquivo mudou, mas foram outras configurações e não a lista. Apenas ignora.
                    ultima_modificacao = modificacao_atual

        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"⚠️ Erro no loop de monitoramento do Espião: {e}")

        # 5. Dorme exatamente 60 segundos
        await asyncio.sleep(60)

async def monitorar_status_espelhos():
    ultima_assinatura_rotas = None
    ultima_modificacao = 0

    if EXIBIR_LOGS: logger.info("🚀 Iniciando monitoramento ultraleve (1 min) para as rotas do Espelhador...")
    while True:
        try:
            # 1. Verifica a data de modificação do arquivo (Custo zero pro CPU)
            try:
                modificacao_atual = os.path.getmtime("espelhos_config.json")
            except OSError:
                modificacao_atual = 0

            if modificacao_atual != ultima_modificacao:
                try:
                    with open("espelhos_config.json", "r", encoding="utf-8") as f:
                        dados_espelho = json.load(f)
                except FileNotFoundError:
                    dados_espelho = {"rotas": []}
                
                rotas = dados_espelho.get("rotas", [])
                
                # 2. Cria a "foto" da assinatura atual
                assinatura_atual = str([{ "origens": r.get("origens", [r.get("origem")]), "destino": r.get("destino") } for r in rotas])
                
                # 3. Compara se os canais alvos realmente mudaram
                if assinatura_atual != ultima_assinatura_rotas:
                    if EXIBIR_LOGS: logger.info("🔍 [Auditor] Mudança detectada nas rotas do Espelhador. Iniciando validação...")
                    alterado = False
                    
                    for rota in rotas:
                        canais_para_verificar = []
                        
                        if "origens" in rota:
                            for i, c in enumerate(rota["origens"]):
                                canais_para_verificar.append(("origem_lista", c, i))
                        elif "origem" in rota:
                            canais_para_verificar.append(("origem_legado", rota["origem"], None))
                            
                        canais_para_verificar.append(("destino", rota.get("destino"), None))
                        
                        for tipo_ponta, canal, idx in canais_para_verificar:
                            if not canal: continue
                                
                            try:
                                entidade, canal_correto = await validar_e_obter_entidade(client, canal)
                                
                                if str(canal) != canal_correto:
                                    if tipo_ponta == "origem_lista": rota["origens"][idx] = canal_correto
                                    elif tipo_ponta == "origem_legado": rota["origem"] = canal_correto
                                    elif tipo_ponta == "destino": rota["destino"] = canal_correto
                                    alterado = True
                                    canal = canal_correto 
                                
                                nome_canal = getattr(entidade, 'title', getattr(entidade, 'username', str(canal)))
                                if "status_canais" not in rota: rota["status_canais"] = {}
                                
                                info_atual = rota["status_canais"].get(str(canal), {})
                                if not isinstance(info_atual, dict): info_atual = {}
                                
                                if info_atual.get("status") != "ok" or info_atual.get("nome") != nome_canal:
                                    rota["status_canais"][str(canal)] = {"status": "ok", "nome": nome_canal}
                                    alterado = True

                                if rota.get("status_verificacao") == "erro":
                                    rota["status_verificacao"] = "ok"
                                    alterado = True
                                    
                            except Exception as e:
                                if "status_canais" not in rota: rota["status_canais"] = {}
                                info_atual = rota["status_canais"].get(str(canal), {})
                                if not isinstance(info_atual, dict): info_atual = {}
                                
                                if info_atual.get("status") != "erro":
                                    rota["status_canais"][str(canal)] = {"status": "erro", "nome": str(canal)}
                                    alterado = True
                                    
                                if rota.get("status_verificacao") != "erro":
                                    rota["status_verificacao"] = "erro"
                                    alterado = True
                                    
                    if alterado:
                        with open("espelhos_config.json", "w", encoding="utf-8") as f:
                            json.dump(dados_espelho, f, indent=4, ensure_ascii=False)
                        if EXIBIR_LOGS: logger.info("✅ Arquivo do Espelhador atualizado e sincronizado após auditoria.")
                        
                    # 4. Atualiza as assinaturas
                    ultima_assinatura_rotas = str([{ "origens": r.get("origens", [r.get("origem")]), "destino": r.get("destino") } for r in rotas])
                    
                    try:
                        ultima_modificacao = os.path.getmtime("espelhos_config.json")
                    except OSError:
                        ultima_modificacao = modificacao_atual
                        
                    if EXIBIR_LOGS: logger.info("✅ Auditoria do Espelhador concluída. Nomes atualizados!")
                else:
                    ultima_modificacao = modificacao_atual

        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"⚠️ Erro na auditoria do espelhador: {e}")
            
        # 5. Dorme exatamente 60 segundos
        await asyncio.sleep(60)

async def monitorar_topicos_submissao():
    """Varredura em background que resgata o nome real dos tópicos para o Bot Mestre"""
    if EXIBIR_LOGS: logger.info("🚀 Iniciando monitoramento para auto-preenchimento de tópicos de submissão...")
    while True:
        try:
            config = ler_config_bd_espiao("submissao_config", padrao={})
            grupo_id = config.get("grupo_id")
            
            if grupo_id:
                alterou = False
                
                for chave_id, chave_nome in [("topico_envio", "nome_topico_envio"), ("topico_destino", "nome_topico_destino")]:
                    t_id = config.get(chave_id)
                    n_atual = config.get(chave_nome)
                    
                    if n_atual == "⏳ Sincronizando..." and t_id is not None:
                        if str(t_id) == "0":
                            config[chave_nome] = "Tópico Geral"
                            alterou = True
                        else:
                            try:
                                # Na API Telethon, a mensagem raiz (com ID igual ao do tópico) contém o título na 'action'
                                msg = await client.get_messages(int(grupo_id), ids=int(t_id))
                                if msg and hasattr(msg, 'action') and hasattr(msg.action, 'title'):
                                    config[chave_nome] = msg.action.title
                                    if EXIBIR_LOGS: logger.info(f"✅ [Integração] Nome do Tópico resgatado com sucesso: {msg.action.title}")
                                else:
                                    config[chave_nome] = f"Tópico {t_id}"
                                    if EXIBIR_LOGS: logger.warning(f"⚠️ [Integração] Título não encontrado para o tópico {t_id}.")
                                alterou = True
                            except Exception as e:
                                if EXIBIR_LOGS: logger.error(f"❌ [Integração] Erro de API ao buscar tópico {t_id}: {e}")
                                config[chave_nome] = f"Tópico {t_id}"
                                alterou = True
                                
                if alterou:
                    salvar_config_bd_espiao("submissao_config", config)
                    
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"⚠️ Erro na thread de monitoramento de submissão: {e}")
            
        # O Userbot varre isso a cada 15 segundos para dar a sensação de tempo real no painel
        await asyncio.sleep(15)

async def main():
    if EXIBIR_LOGS: logger.info("🕵️ Iniciando o Módulo Espião de Clonagem...")
    try:
        with open("status_espelhador.json", "w") as f:
            json.dump({}, f)
    except Exception:
        pass
    await client.start()
    
    if EXIBIR_LOGS: logger.info("🔄 Sincronizando banco de dados de grupos e access_hashes...")
    try:
        await client.get_dialogs()
        if EXIBIR_LOGS: logger.info("✅ Sincronização concluída! IDs numéricos agora serão reconhecidos pelo Auditor.")
    except Exception as e:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Aviso na sincronização: {e}")
        
    alvos = carregar_alvos()
    if EXIBIR_LOGS: logger.info(f"📡 Radar ativo para {len(alvos)} concorrentes.")
    
    asyncio.create_task(processar_fila_espelhador_loop())
    asyncio.create_task(monitorar_status_alvos())
    asyncio.create_task(monitorar_status_espelhos())
    asyncio.create_task(monitorar_topicos_submissao()) # ✅ NOVO GATILHO
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
