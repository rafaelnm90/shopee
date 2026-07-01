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

load_dotenv()
EXIBIR_LOGS = True

# 1. CREDENCIAIS DA CONTA
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
SHOPEE_APP_ID = os.getenv('SHOPEE_APP_ID')
SHOPEE_APP_SECRET = os.getenv('SHOPEE_APP_SECRET')

# 2. CONFIGURAÇÕES GERAIS DO ESPIÃO
LIMITE_REGISTROS_HASH = 1000
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

def verificar_e_registrar_espelho(link_shopee, contexto="global"):
    arquivo_espelhos = "registro_espelhos.json"
    agora = datetime.now()
    try:
        with open(arquivo_espelhos, "r") as f:
            dados = json.load(f)
            # Migração automática do formato antigo para o novo formato de contextos
            if "espelhos" in dados:
                dados_antigos = dados.pop("espelhos")
                dados["contextos"] = {"global": dados_antigos}
    except (FileNotFoundError, json.JSONDecodeError):
        dados = {"contextos": {}}

    if "contextos" not in dados:
        dados["contextos"] = {}

    if contexto not in dados["contextos"]:
        dados["contextos"][contexto] = {}

    historico = dados["contextos"][contexto]

    # Executa a limpeza automática de links registados há mais de 24 horas NESTE CONTEXTO
    chaves_para_remover = []
    for link, data_str in historico.items():
        try:
            data_registro = datetime.strptime(data_str, "%Y-%m-%d %H:%M:%S")
            if (agora - data_registro).total_seconds() > 86400:
                chaves_para_remover.append(link)
        except ValueError:
            chaves_para_remover.append(link)
            
    for chave in chaves_para_remover:
        del historico[chave]

    # Verifica se o link novo já existe no radar recente para o destino específico
    if link_shopee in historico:
        with open(arquivo_espelhos, "w") as f:
            json.dump(dados, f, indent=4)
        return True 

    # Se for novidade, regista com a data e hora atuais neste contexto
    historico[link_shopee] = agora.strftime("%Y-%m-%d %H:%M:%S")
    with open(arquivo_espelhos, "w") as f:
        json.dump(dados, f, indent=4)
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

def verificar_e_registrar_hash(hash_video):
    arquivo_hashes = "registro_hashes.json"
    try:
        with open(arquivo_hashes, "r") as f:
            dados = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        dados = {"hashes": []}
    
    if hash_video in dados.get("hashes", []):
        return True
        
    dados.setdefault("hashes", []).append(hash_video)
    
    if len(dados["hashes"]) > LIMITE_REGISTROS_HASH:
        if EXIBIR_LOGS: logger.info(f"🧹 Limite de {LIMITE_REGISTROS_HASH} hashes atingido. Removendo os registos mais antigos para libertar espaço...")
        dados["hashes"] = dados["hashes"][-LIMITE_REGISTROS_HASH:]
        
    with open(arquivo_hashes, "w") as f:
        json.dump(dados, f, indent=4)
    return False

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

def registrar_historico_espiao(nome_grupo):
    import json
    import os
    arquivo_hist = "historico_espiao.json"
    
    try:
        if os.path.exists(arquivo_hist):
            with open(arquivo_hist, "r") as f:
                historico = json.load(f)
        else:
            historico = {"total": 0, "grupos": {}}
    except (FileNotFoundError, json.JSONDecodeError):
        historico = {"total": 0, "grupos": {}}
        
    historico["total"] = historico.get("total", 0) + 1
    
    grupos = historico.get("grupos", {})
    grupos[nome_grupo] = grupos.get(nome_grupo, 0) + 1
    historico["grupos"] = grupos
    
    with open(arquivo_hist, "w") as f:
        json.dump(historico, f, indent=4)
        
    if EXIBIR_LOGS: logger.info(f"📊 [Estatística] +1 vídeo contabilizado para o histórico do grupo: {nome_grupo}")

async def converter_link_shopee(link_original):
    if not SHOPEE_APP_ID or not SHOPEE_APP_SECRET:
        if EXIBIR_LOGS: logger.warning("⏳ [API Shopee] Chaves ausentes no .env. Ignorando conversão e mantendo o link original.")
        return link_original

    link_processar = link_original
    
    if "shp.ee" in link_original or "shope.ee" in link_original or "s.shopee.com.br" in link_original:
        if EXIBIR_LOGS: logger.info(f"🔍 Detectado link encurtado. A iniciar a expansão do URL: {link_original}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(link_original, allow_redirects=True) as resp:
                    link_processar = str(resp.url)
                    if EXIBIR_LOGS: logger.info(f"✅ Expansão concluída. URL longo obtido: {link_processar}")
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro ao tentar expandir o link: {e}. Será mantido o original.")

    if EXIBIR_LOGS: logger.info(f"🔗 [API Shopee] A iniciar criptografia para o link: {link_processar}")

    timestamp = int(time.time())
    endpoint = "https://open-api.affiliate.shopee.com.br/graphql"

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

    if EXIBIR_LOGS: logger.info("📤 [API Shopee] Enviando requisição assinada para os servidores...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, data=payload_json) as response:
                resposta_dados = await response.json()

                if response.status == 200 and "data" in resposta_dados and resposta_dados["data"].get("generateShortLink"):
                    novo_link = resposta_dados["data"]["generateShortLink"]["shortLink"]
                    if EXIBIR_LOGS: logger.info(f"✅ [API Shopee] Link convertido com sucesso: {novo_link}")
                    return novo_link
                else:
                    if EXIBIR_LOGS: logger.error(f"❌ [API Shopee] Falha na conversão. Resposta: {resposta_dados}")
                    return link_original

    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [API Shopee] Erro de comunicação com o servidor: {e}")
        return link_original

async def gerar_legenda_com_ia_espelhador(caminho_video):
    def processar_ia():
        import time
        if EXIBIR_LOGS: logger.info("📤 [IA] A fazer upload do vídeo para o Google Storage...")
        video_gemini = client_genai.files.upload(file=caminho_video)
        
        while video_gemini.state.name == "PROCESSING":
            time.sleep(2)
            video_gemini = client_genai.files.get(name=video_gemini.name)
            
        if video_gemini.state.name == "FAILED":
            raise Exception("Falha de processamento no servidor do Google.")

        prompt = (
            "Assista ao vídeo e crie um título MUITO CURTO para o produto demonstrado. "
            "REGRA ABSOLUTA: O título deve ter no máximo 5 palavras e conter apenas 1 emoji no início. "
            "Não adicione ponto final, descrições ou textos persuasivos. Entregue APENAS o título."
        )

        for modelo_nome in MODELOS_CASCATA_GEMINI:
            try:
                if EXIBIR_LOGS: logger.info(f"⏳ [IA] A consultar o motor: {modelo_nome}...")
                response = client_genai.models.generate_content(
                    model=modelo_nome,
                    contents=[video_gemini, prompt]
                )
                if response and response.text:
                    if EXIBIR_LOGS: logger.info(f"✅ [IA] Sucesso com o modelo {modelo_nome}!")
                    return response.text.strip()
            except Exception as erro_modelo:
                if "429" in str(erro_modelo):
                    if EXIBIR_LOGS: logger.warning(f"⚠️ [IA] Limite atingido em {modelo_nome}. A tentar o próximo...")
                    continue
                else:
                    if EXIBIR_LOGS: logger.warning(f"⚠️ [IA] Erro no modelo {modelo_nome}: {erro_modelo}")
                    continue
        raise Exception("Todos os modelos da cascata falharam por limite de cota ou erro.")

    try:
        titulo = await asyncio.to_thread(processar_ia)
        return titulo
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [IA] Falha na geração da legenda: {e}")
        return None

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
    
    if event.out and chat_username.lower() != "@shopee_video_afiliado":
        if EXIBIR_LOGS: logger.info("🛡️ [Espião] Trava de autoria ativada: Ignorando postagem própria fora do canal imune para evitar loop.")
        return
    
    if chat_username not in alvos and chat_id not in alvos and chat_id_completo not in alvos:
        return

    texto = event.raw_text
    match = PADRAO_SHOPEE.search(texto)
    
    # Ignora mensagens de bate-papo, processa apenas se tiver link e mídia de vídeo
    if match:
        link_capturado = match.group(1)
        
        # Limpa pontuações que possam ter ficado agarradas ao final do link
        link_capturado = link_capturado.rstrip(").,;!?")
        
        # ✅ NOVO: Bloqueio de vídeos duplicados no módulo Espião (Contexto Isolado)
        if verificar_e_registrar_espelho(link_capturado, contexto="espiao"):
            if EXIBIR_LOGS: logger.info(f"🪞 [Espião] Duplicidade barrada! O produto {link_capturado} já foi capturado nas últimas 24 horas.")
            return # Encerra o processamento da mensagem aqui mesmo, sem baixar o vídeo
            
        if event.media and isinstance(event.media, MessageMediaDocument):
            if EXIBIR_LOGS: logger.info(f"🎯 ALVO LOCALIZADO! Link da Shopee extraído cirurgicamente: {link_capturado}")
            
            if "magazineluiza" in texto.lower() or "meli.li" in texto.lower() or "mercadolivre" in texto.lower():
                if EXIBIR_LOGS: logger.info("✂️ Concorrência ignorada: A postagem continha outros domínios, mas apenas o da Shopee foi filtrado.")
            
            if EXIBIR_LOGS: logger.info("📥 Iniciando download do vídeo em segundo plano...")
            caminho_salvo = await event.download_media(file="temp_clone_")
            
            hash_arquivo = calcular_hash_video(caminho_salvo)
            
            if hash_arquivo and verificar_e_registrar_hash(hash_arquivo):
                if EXIBIR_LOGS: logger.warning(f"🚫 Clone bloqueado! O vídeo possui uma assinatura digital idêntica a um ficheiro já processado.")
                try:
                    os.remove(caminho_salvo)
                    if EXIBIR_LOGS: logger.info("🧹 Ficheiro físico duplicado eliminado com sucesso para poupar espaço.")
                except Exception as e:
                    if EXIBIR_LOGS: logger.error(f"❌ Erro ao tentar remover ficheiro duplicado: {e}")
                return
                
            salvar_na_fila_clonagem(caminho_salvo, link_capturado)
            
            # 📊 Adiciona a pontuação ao painel estatístico do Espião
            nome_chat = getattr(chat, 'title', chat_username if chat_username else chat_id)
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
    from datetime import timedelta # ✅ Correção 1: Injetando a importação de tempo ausente
    while True:
        try:
            fila_dados = ler_fila_espelhador()
            fila = fila_dados.get("fila", [])
            if not fila:
                await asyncio.sleep(5)
                continue
                
            config = ler_espelhos_config()
            rotas = {r.get("nome"): r for r in config.get("rotas", [])}
            
            itens_restantes = []
            agora = datetime.now()
            houve_alteracao_rota = False
            
            for item in fila:
                nome_rota = item.get("nome_rota")
                rota_config = rotas.get(nome_rota)
                
                if not rota_config:
                    continue
                    
                data_captura = datetime.strptime(item["data_captura"], "%Y-%m-%d %H:%M:%S")
                delay_minutos = int(rota_config.get("delay", 0))
                esvaziar_agora = rota_config.get("esvaziar_agora", False)
                
                hora_disparo = data_captura + timedelta(minutes=delay_minutos)
                
                if agora >= hora_disparo or esvaziar_agora:
                    try:
                        chat_origem = int(item["chat_origem"])
                        msg_id = item["msg_id"]
                        destino = item["destino"]
                        texto = item["texto_processado"]
                        
                        mensagem_original = await client.get_messages(chat_origem, ids=msg_id)
                        if mensagem_original:
                            try:
                                entidade_destino = await client.get_entity(destino)
                            except ValueError:
                                id_teste = int(destino) if str(destino).lstrip('-').isdigit() else destino
                                entidade_destino = await client.get_entity(id_teste)

                            await client.send_message(entidade_destino, texto, file=mensagem_original.media, parse_mode="html")
                            if EXIBIR_LOGS: logger.info(f"✅ [Espelhador] Disparo dinâmico concluído na rota '{nome_rota}' para {destino}.")
                        else:
                            if EXIBIR_LOGS: logger.warning(f"⚠️ [Espelhador] Mensagem original apagada antes do disparo na rota '{nome_rota}'.")
                    except Exception as e:
                        if EXIBIR_LOGS: logger.error(f"❌ [Espelhador] Falha no disparo dinâmico da rota '{nome_rota}': {e}")
                else:
                    itens_restantes.append(item)
                    
            for r in config.get("rotas", []):
                if r.get("esvaziar_agora"):
                    r["esvaziar_agora"] = False
                    houve_alteracao_rota = True
            
            if houve_alteracao_rota:
                # ✅ Correção 2: Salvando diretamente o arquivo JSON em vez de chamar função de outro script
                with open("espelhos_config.json", "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
                    
            fila_dados["fila"] = itens_restantes
            salvar_fila_espelhador(fila_dados)
            
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro crítico no loop dinâmico do espelhador: {e}")
        
        await asyncio.sleep(5)

@client.on(events.NewMessage)
async def motor_espelhador_userbot(event):
    chat = await event.get_chat()
    chat_id_str = str(chat.id)
    chat_username = f"@{chat.username.lower()}" if getattr(chat, 'username', None) else ""
    chat_id_completo = f"-100{chat.id}" if not chat_id_str.startswith("-100") else chat_id_str

    if event.out and chat_username != "@shopee_video_afiliado":
        if EXIBIR_LOGS: logger.info("🛡️ [Espelhador] Trava de autoria ativada: Postagem própria ignorada para evitar loop cruzado.")
        return

    dados = ler_espelhos_config()
    rotas_ativas = []
    
    for r in dados.get("rotas", []):
        origens_rota = [str(o).lower() for o in r.get("origens", [])]
        if "origem" in r:
            origens_rota.append(str(r["origem"]).lower())
            
        if chat_id_str in origens_rota or chat_id_completo in origens_rota or chat_username in origens_rota:
            rotas_ativas.append(r)
    
    if not rotas_ativas:
        return

    # ✅ TRAVA DE MÍDIA FLEXÍVEL: Exige anexo visual, mas não restringe o formato técnico
    if getattr(event, 'media', None) is None:
        if EXIBIR_LOGS: logger.info("⏭️ [Espelhador] Postagem descartada: Não contém um anexo visual.")
        return

    texto_original = event.text or ""
    
    # ✅ REGRA DE NEGÓCIO: Exige obrigatoriamente a presença de um link da Shopee
    match_shopee = PADRAO_SHOPEE.search(texto_original)
    if not match_shopee:
        if EXIBIR_LOGS: logger.info("⏭️ [Espelhador] Postagem descartada: Contém mídia, mas não possui link de afiliado da Shopee.")
        return
        
    link_capturado = match_shopee.group(1).rstrip(").,;!?")
    
    if EXIBIR_LOGS: logger.info(f"🔄 [Espelhador] Interceptação acionada! Mídia e link detetados na origem {chat_id_str}.")
    if EXIBIR_LOGS: logger.info("🔗 [Espelhador] A converter o link da Shopee encontrado...")
    link_final_convertido = await converter_link_shopee(link_capturado)
    if EXIBIR_LOGS: logger.info("✅ [Espelhador] Sucesso: Link convertido utilizando a função nativa correta.")

    if EXIBIR_LOGS: logger.info("📥 [Espelhador] Descarregando vídeo temporário para análise da IA e verificação de duplicidade...")
    caminho_video_temp = await event.download_media(file="temp_analise_espelho_")
    
    if caminho_video_temp:
        # ✅ NOVA TRAVA ANTI-LOOP (Assinatura Digital do Vídeo)
        hash_arquivo = calcular_hash_video(caminho_video_temp)
        if hash_arquivo and verificar_e_registrar_hash(hash_arquivo):
            if EXIBIR_LOGS: logger.warning("🚫 [Espelhador] Loop evitado! Este vídeo exato já foi processado recentemente pelo sistema. Ignorando...")
            try:
                os.remove(caminho_video_temp)
            except Exception:
                pass
            return # Aborta todo o processo de espelhamento e quebra o ciclo
            
        titulo_ia = await gerar_legenda_com_ia_espelhador(caminho_video_temp)
        
        try:
            os.remove(caminho_video_temp)
            if EXIBIR_LOGS: logger.info("🧹 [Espelhador] Vídeo temporário removido do servidor após análise.")
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ [Espelhador] Erro ao remover vídeo temporário: {e}")
    else:
        titulo_ia = None

    if titulo_ia:
        texto_processado = f"<b>{titulo_ia}</b>\n\n🔗 Link do Produto:\n{link_final_convertido}"
        if EXIBIR_LOGS: logger.info("✅ [Espelhador] Legenda inteligente construída com sucesso.")
    else:
        texto_processado = f"🔗 Link do Produto:\n{link_final_convertido}"
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
            
        # ✅ VERIFICAÇÃO DE DUPLICIDADE ISOLADA POR ROTA (Usa o destino como contexto)
        if link_capturado and verificar_e_registrar_espelho(link_capturado, contexto=str(destino)):
            if EXIBIR_LOGS: logger.info(f"🪞 [Espelhador] Duplicidade barrada na rota '{nome_rota}'! O produto já foi postado neste destino nas últimas 24h.")
            continue
            
        fila_dados = ler_fila_espelhador()
        item = {
            "id": f"espelho_{int(datetime.now().timestamp())}_{chat_id_str}",
            "chat_origem": chat_id_completo,
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
                return ent, var
            except Exception:
                continue
        raise Exception("Nenhuma variação de username funcionou.")

    # 3. Tratamento de IDs Numéricos
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
            return ent, str(var)
        except Exception:
            continue
            
    raise Exception("Nenhuma variação de ID numérico funcionou.")

async def monitorar_status_alvos():
    while True:
        # 1. Leitura inicial para saber quem devemos verificar agora
        try:
            with open("alvos_espiao.json", "r") as f:
                dados_iniciais = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            dados_iniciais = {"alvos": [], "canal_destino": None, "status_alvos": {}}
            
        alvos_para_verificar = dados_iniciais.get("alvos", [])
        destino_para_verificar = dados_iniciais.get("canal_destino")
        novos_status_coletados = {}
        mapa_correcoes = {}
        
        # 2. Verificação com Teste de Variações de ID (Origens)
        for alvo in alvos_para_verificar:
            try:
                entidade, alvo_correto = await validar_e_obter_entidade(client, alvo)
                nome = getattr(entidade, 'title', getattr(entidade, 'username', str(alvo_correto)))
                novo_status = {"status": "ok", "nome": nome}
                
                if str(alvo) != alvo_correto:
                    mapa_correcoes[str(alvo)] = alvo_correto
                    
                novos_status_coletados[alvo_correto] = novo_status
                
            except Exception:
                novos_status_coletados[str(alvo)] = {"status": "erro", "erro": "Acesso negado/Link inválido"}
                
            await asyncio.sleep(2) # Pausa de segurança anti-flood da API
            
        # 2.1 Verificação do Canal de Destino
        status_destino_coletado = None
        if destino_para_verificar:
            try:
                entidade_dest, dest_correto = await validar_e_obter_entidade(client, destino_para_verificar)
                nome_dest = getattr(entidade_dest, 'title', getattr(entidade_dest, 'username', str(dest_correto)))
                status_destino_coletado = {"status": "ok", "nome": nome_dest}
                
                if str(destino_para_verificar) != dest_correto:
                    mapa_correcoes["_destino"] = dest_correto
            except Exception:
                status_destino_coletado = {"status": "erro", "nome": str(destino_para_verificar)}
            await asyncio.sleep(2)
            
        # 3. Leitura FRESCA logo antes de gravar para evitar sobrescrever exclusões recentes
        try:
            with open("alvos_espiao.json", "r") as f:
                dados_frescos = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            dados_frescos = {"alvos": [], "canal_destino": None, "status_alvos": {}}
            
        alvos_reais_agora = [str(a) for a in dados_frescos.get("alvos", [])]
        status_alvos_antigos = dados_frescos.get("status_alvos", {})
        
        status_alvos_final = {}
        nova_lista_alvos = []
        houve_alteracao = False
        
        # 4. Aplica as auto-correções na lista principal de alvos
        for alvo in alvos_reais_agora:
            alvo_final = mapa_correcoes.get(alvo, alvo)
            nova_lista_alvos.append(alvo_final)
            
            if alvo != alvo_final:
                houve_alteracao = True
                if EXIBIR_LOGS: logger.info(f"🔧 Auditor corrigiu automaticamente o ID: {alvo} -> {alvo_final}")
        
        # 5. Atualiza os status APENAS dos alvos que sobreviveram na lista
        for alvo_final in nova_lista_alvos:
            if alvo_final in novos_status_coletados:
                status_alvos_final[alvo_final] = novos_status_coletados[alvo_final]
                if status_alvos_antigos.get(alvo_final) != novos_status_coletados[alvo_final]:
                    houve_alteracao = True
            elif alvo_final in status_alvos_antigos:
                status_alvos_final[alvo_final] = status_alvos_antigos[alvo_final]
                
        # 6. Deteta se houve remoção de alvos durante a verificação
        for alvo_antigo in status_alvos_antigos.keys():
            if alvo_antigo not in nova_lista_alvos:
                houve_alteracao = True
                
        # 6.1 Atualiza o Destino na base de dados
        destino_fresco = dados_frescos.get("canal_destino")
        if destino_fresco:
            if "_destino" in mapa_correcoes and str(destino_fresco) == str(destino_para_verificar):
                dados_frescos["canal_destino"] = mapa_correcoes["_destino"]
                houve_alteracao = True
                
        if status_destino_coletado and dados_frescos.get("status_destino") != status_destino_coletado:
            dados_frescos["status_destino"] = status_destino_coletado
            houve_alteracao = True
                
        # 7. Gravação limpa e definitiva
        if houve_alteracao:
            dados_frescos["alvos"] = nova_lista_alvos
            dados_frescos["status_alvos"] = status_alvos_final
            with open("alvos_espiao.json", "w") as f:
                json.dump(dados_frescos, f, indent=4)
                
        if EXIBIR_LOGS: logger.info("✅ Auditoria de inicialização dos alvos concluída. Encerrando ciclo de verificação.")
        break

async def monitorar_status_espelhos():
    if EXIBIR_LOGS: logger.info("🚀 Iniciando monitoramento contínuo das rotas do Espelhador (suporte a grupos de canais)...")
    while True:
        try:
            try:
                with open("espelhos_config.json", "r", encoding="utf-8") as f:
                    dados_espelho = json.load(f)
            except FileNotFoundError:
                dados_espelho = {"rotas": []}
            
            rotas = dados_espelho.get("rotas", [])
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
                    if not canal:
                        continue
                        
                    try:
                        # ✅ NOVO: Utiliza a mesma inteligência de validação e correção do Grupos Vigiados
                        entidade, canal_correto = await validar_e_obter_entidade(client, canal)
                        
                        # Aplica a auto-correção na rota se a variação for diferente do que estava salvo
                        if str(canal) != canal_correto:
                            if tipo_ponta == "origem_lista":
                                rota["origens"][idx] = canal_correto
                            elif tipo_ponta == "origem_legado":
                                rota["origem"] = canal_correto
                            elif tipo_ponta == "destino":
                                rota["destino"] = canal_correto
                            
                            alterado = True
                            if EXIBIR_LOGS: logger.info(f"🔧 [Espelhador] ID corrigido automaticamente: {canal} -> {canal_correto}")
                            canal = canal_correto # Atualiza a variável local para salvar o status
                        
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
                            if EXIBIR_LOGS: logger.info(f"✅ Acesso restaurado para a rota: {rota['nome']}")
                            
                    except Exception as e:
                        if EXIBIR_LOGS: logger.warning(f"⚠️ Falha de acesso em {canal} ({tipo_ponta}) da rota {rota['nome']}: {e}")
                        
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
                if EXIBIR_LOGS: logger.info("✅ Arquivo de banco do Espelhador atualizado após auditoria de grupos de canais.")
                
            if EXIBIR_LOGS: logger.info("✅ Auditoria de inicialização dos espelhos concluída. Encerrando ciclo de verificação.")
            break
            
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"⚠️ Erro crítico na auditoria de inicialização do espelhador: {e}")
            break

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
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
