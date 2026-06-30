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

def verificar_e_registrar_espelho(link_shopee):
    arquivo_espelhos = "registro_espelhos.json"
    agora = datetime.now()
    try:
        with open(arquivo_espelhos, "r") as f:
            dados = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        dados = {"espelhos": {}}

    # Executa a limpeza automática de links registados há mais de 24 horas
    chaves_para_remover = []
    for link, data_str in dados.get("espelhos", {}).items():
        try:
            data_registro = datetime.strptime(data_str, "%Y-%m-%d %H:%M:%S")
            if (agora - data_registro).total_seconds() > 86400:
                chaves_para_remover.append(link)
        except ValueError:
            chaves_para_remover.append(link)
            
    for chave in chaves_para_remover:
        del dados["espelhos"][chave]

    # Verifica se o link novo já existe no radar recente
    if link_shopee in dados.get("espelhos", {}):
        with open(arquivo_espelhos, "w") as f:
            json.dump(dados, f, indent=4)
        return True 

    # Se for novidade, regista com a data e hora atuais
    dados.setdefault("espelhos", {})[link_shopee] = agora.strftime("%Y-%m-%d %H:%M:%S")
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
    
    if len(dados["hashes"]) > 500:
        dados["hashes"] = dados["hashes"][-500:]
        
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
        
        # ✅ NOVO: Bloqueio imediato de vídeos duplicados (Espelhos)
        if verificar_e_registrar_espelho(link_capturado):
            if EXIBIR_LOGS: logger.info(f"🪞 Espelho bloqueado! O produto {link_capturado} já foi capturado nas últimas 24 horas.")
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

def atualizar_contador_espelhador(incremento, nome_rota):
    arquivo = "status_espelhador.json"
    try:
        with open(arquivo, "r") as f:
            dados = json.load(f)
            # Transição limpa caso exista o ficheiro no formato antigo
            if not isinstance(dados, dict) or "ativas" in dados:
                dados = {}
    except (FileNotFoundError, json.JSONDecodeError):
        dados = {}
        
    dados[nome_rota] = max(0, dados.get(nome_rota, 0) + incremento)
    
    with open(arquivo, "w") as f:
        json.dump(dados, f)

async def converter_link_shopee_espelho(link_original):
    app_id = os.getenv('SHOPEE_APP_ID')
    app_secret = os.getenv('SHOPEE_APP_SECRET')
    
    if not app_id or not app_secret:
        return link_original

    link_processar = link_original
    
    if "shp.ee" in link_original or "shope.ee" in link_original or "s.shopee.com.br" in link_original:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(link_original, allow_redirects=True) as resp:
                    link_processar = str(resp.url)
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ [Espelhador] Erro ao expandir o link: {e}")

    timestamp = int(time.time())
    endpoint = "https://open-api.affiliate.shopee.com.br/graphql"

    payload = {
        "query": "mutation generateShortLink($originUrl: String!) { generateShortLink(input: {originUrl: $originUrl}) { shortLink } }",
        "variables": {"originUrl": link_processar}
    }
    
    payload_json = json.dumps(payload, separators=(',', ':'))
    fator_base = f"{app_id}{timestamp}{payload_json}{app_secret}"
    assinatura = hashlib.sha256(fator_base.encode('utf-8')).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={app_id}, Timestamp={timestamp}, Signature={assinatura}"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, data=payload_json) as response:
                resposta_dados = await response.json()
                if response.status == 200 and "data" in resposta_dados and resposta_dados["data"].get("generateShortLink"):
                    novo_link = resposta_dados["data"]["generateShortLink"]["shortLink"]
                    if EXIBIR_LOGS: logger.info("🔗 [Espelhador] Conversão de comissão aplicada ao link com sucesso.")
                    return novo_link
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [Espelhador] Falha de comunicação com a Shopee na conversão: {e}")
        
    return link_original

async def processar_fila_espelhador_loop():
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
                salvar_espelhos(config)
                    
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

    if EXIBIR_LOGS: logger.info(f"🔄 [Espelhador] Interceptação acionada! Nova postagem detectada na origem {chat_id_str}.")

    texto_original = event.text or ""
    texto_processado = texto_original
    
    match_shopee = PADRAO_SHOPEE.search(texto_original)
    if match_shopee:
        link_capturado = match_shopee.group(1).rstrip(").,;!?")
        if verificar_e_registrar_espelho(link_capturado):
            if EXIBIR_LOGS: logger.info(f"🪞 [Espelhador] Duplicidade barrada! O link {link_capturado} já circulou na rede nas últimas 24 horas.")
            return

    links = re.findall(r'(https?://\S+)', texto_original)
    if links:
        if EXIBIR_LOGS: logger.info(f"🔗 [Espelhador] Convertendo {len(links)} links encontrados na postagem...")
        for link in links:
            novo_link = await converter_link_shopee_espelho(link)
            texto_processado = texto_processado.replace(link, novo_link)

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
                
        await asyncio.sleep(30)

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
                
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"⚠️ Erro crítico no loop de monitoramento do espelhador: {e}")
            
        await asyncio.sleep(43200)

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
