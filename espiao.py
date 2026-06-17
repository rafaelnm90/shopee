import os
import json
import logging
import asyncio
import re
from datetime import datetime
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

# ✅ O padrão foi ampliado para capturar links com parâmetros complexos e domínios mais curtos
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
            
            salvar_na_fila_clonagem(caminho_salvo, link_capturado)
        else:
            if EXIBIR_LOGS: logger.info(f"⏭️ Ignorado: O link {link_capturado} foi encontrado, mas a postagem não contém um anexo de vídeo direto.")

async def validar_e_obter_entidade(client, alvo):
    alvo_str = str(alvo).strip()
    
    # Se não for um ID numérico (ex: @username ou link t.me)
    if not alvo_str.lstrip('-').isdigit():
        return await client.get_entity(alvo_str), alvo_str

    so_numeros = alvo_str.replace("-", "")
    
    # Lista de variações inteligentes a testar na API
    variacoes = [
        alvo_str, 
        f"-100{so_numeros}", 
        f"-{so_numeros}", 
        so_numeros
    ]
    
    variacoes_unicas = []
    for v in variacoes:
        if v not in variacoes_unicas:
            variacoes_unicas.append(v)
            
    for var in variacoes_unicas:
        try:
            ent = await client.get_entity(int(var))
            return ent, str(var) # Retorna a entidade e a variação exata que funcionou
        except Exception:
            continue
            
    raise Exception("Nenhuma variação funcionou.")

# ✅ NOVO: Radar assíncrono que varre a lista, testa variações e audita a permissão
async def monitorar_status_alvos():
    while True:
        # 1. Leitura inicial para saber quem devemos verificar agora
        try:
            with open("alvos_espiao.json", "r") as f:
                dados_iniciais = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            dados_iniciais = {"alvos": [], "canal_destino": None, "status_alvos": {}}
            
        alvos_para_verificar = dados_iniciais.get("alvos", [])
        novos_status_coletados = {}
        mapa_correcoes = {}
        
        # 2. Verificação com Teste de Variações de ID
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
                # Mantém status antigo de canais adicionados há segundos pelo bot
                status_alvos_final[alvo_final] = status_alvos_antigos[alvo_final]
                
        # 6. Deteta se houve remoção de alvos durante a verificação
        for alvo_antigo in status_alvos_antigos.keys():
            if alvo_antigo not in nova_lista_alvos:
                houve_alteracao = True
                
        # 7. Gravação limpa e definitiva
        if houve_alteracao:
            dados_frescos["alvos"] = nova_lista_alvos
            dados_frescos["status_alvos"] = status_alvos_final
            with open("alvos_espiao.json", "w") as f:
                json.dump(dados_frescos, f, indent=4)
                
        await asyncio.sleep(30)

async def main():
    if EXIBIR_LOGS: logger.info("🕵️ Iniciando o Módulo Espião de Clonagem...")
    await client.start()
    
    # ✅ NOVO: Força o cache do histórico para o Userbot reconhecer os IDs numéricos privados
    if EXIBIR_LOGS: logger.info("🔄 Sincronizando banco de dados de grupos e access_hashes...")
    try:
        await client.get_dialogs()
        if EXIBIR_LOGS: logger.info("✅ Sincronização concluída! IDs numéricos agora serão reconhecidos pelo Auditor.")
    except Exception as e:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Aviso na sincronização: {e}")
        
    alvos = carregar_alvos()
    if EXIBIR_LOGS: logger.info(f"📡 Radar ativo para {len(alvos)} concorrentes.")
    
    # Inicia a tarefa fantasma que auditará os grupos
    asyncio.create_task(monitorar_status_alvos())
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
