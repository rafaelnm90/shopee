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
from telethon import TelegramClient, events, functions
from telethon.tl.types import MessageMediaDocument
from telethon.errors import FloodWaitError, UserAlreadyParticipantError, InviteHashExpiredError
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils import registrar_erro_json

load_dotenv()

# 🕐 Trava de fuso centralizada: importar o modulo ja aplica America/Sao_Paulo.
from fuso import FUSO_STR, fuso_horario, configurar_logs

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

# ==========================================
# 👥 ENTRADA AUTOMÁTICA NOS CANAIS DOS PARCEIROS
# Uma por ciclo, com intervalo longo: entrar em vários canais seguidos é o
# padrão que o Telegram pune. A conta do userbot é a peça mais crítica do sistema.
# ==========================================
INTERVALO_ENTRADA_PARCEIROS = 900   # 15 min entre uma entrada e outra

def ler_parceiros_pendentes():
    """Parceiros ativos cujo canal de origem o userbot ainda não acessa."""
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()
        try:
            cursor.execute("SELECT * FROM parceiros WHERE ativo = 1 AND (origem_ok IS NULL OR origem_ok = 0)")
            dados = [dict(l) for l in cursor.fetchall()]
        except sqlite3.OperationalError:
            dados = []   # coluna/tabela ainda não existe
        conexao.close()
        return dados
    except Exception:
        return []

def marcar_origem_parceiro(parceiro_id, status, motivo=""):
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        cursor.execute("UPDATE parceiros SET origem_ok = ?, origem_erro = ? WHERE id = ?",
                       (int(status), str(motivo)[:200], int(parceiro_id)))
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [Parceiros] Erro ao marcar origem: {e}")

async def entrar_no_canal_parceiro(alvo):
    """
    Devolve (sucesso, motivo). O Telegram só permite entrar via @username ou
    link de convite — ID numérico não serve, por limitação da própria API.
    """
    alvo = str(alvo or "").strip()
    if not alvo:
        return False, "origem vazia"

    try:
        # Já temos acesso? Então não há o que fazer.
        try:
            await client.get_entity(alvo)
            return True, "já acessível"
        except Exception:
            pass

        if "+" in alvo or "joinchat" in alvo:
            hash_convite = alvo.split("+")[-1].split("/")[-1]
            await client(functions.messages.ImportChatInviteRequest(hash_convite))
            return True, "entrou pelo link de convite"

        if alvo.startswith("@") or ("t.me/" in alvo and "+" not in alvo):
            usuario = alvo.split("t.me/")[-1].replace("@", "").strip("/")
            await client(functions.channels.JoinChannelRequest(usuario))
            return True, "entrou pelo @username"

        return False, "ID numérico não permite entrada automática: use @username ou link de convite"

    except UserAlreadyParticipantError:
        return True, "já era membro"
    except InviteHashExpiredError:
        return False, "link de convite expirado"
    except FloodWaitError as e:
        return False, f"Telegram pediu espera de {e.seconds}s (limite anti-spam)"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

# ==========================================
# 🎣 CAPTURA POR PARCEIRO
# Roda no MESMO evento do userbot, depois do sorteio do dono — que já reservou
# o que era dele. Aqui cada parceiro sorteia a própria cota do que sobrou.
# ==========================================
def ler_parceiros_ativos_com_acesso():
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()
        try:
            cursor.execute("SELECT * FROM parceiros WHERE ativo = 1 AND origem_ok = 1")
            dados = [dict(l) for l in cursor.fetchall()]
        except sqlite3.OperationalError:
            dados = []
        conexao.close()
        return dados
    except Exception:
        return []

def _garantir_fila_parceiros(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fila_parceiros (
            id_unico TEXT PRIMARY KEY,
            parceiro_id INTEGER,
            caminho_video TEXT,
            link_original TEXT,
            data_captura TEXT,
            data_alvo TEXT,
            horario_disparo TEXT DEFAULT '',
            processado INTEGER DEFAULT 0,
            data_postagem TEXT DEFAULT ''
        )
    ''')

def contar_fila_parceiro(parceiro_id, data_alvo):
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        _garantir_fila_parceiros(cursor)
        cursor.execute("SELECT COUNT(*) FROM fila_parceiros WHERE parceiro_id = ? AND data_alvo = ? AND processado = 0",
                       (int(parceiro_id), data_alvo))
        total = cursor.fetchone()[0]
        conexao.close()
        return total
    except Exception:
        return 0

def inserir_fila_parceiro(parceiro_id, caminho, link, data_alvo):
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        _garantir_fila_parceiros(cursor)
        id_unico = f"p{parceiro_id}_{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}"
        cursor.execute(
            "INSERT INTO fila_parceiros (id_unico, parceiro_id, caminho_video, link_original, data_captura, data_alvo) VALUES (?, ?, ?, ?, ?, ?)",
            (id_unico, int(parceiro_id), caminho, link, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), data_alvo)
        )
        conexao.commit()
        conexao.close()
        return id_unico
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [Parceiros] Erro ao inserir na fila: {e}")
        return None

async def capturar_para_parceiros(event, chat_id, link_capturado):
    """
    Chamada em TODA mensagem com vídeo + link Shopee. Para cada parceiro cujo
    canal de origem seja este chat, roda o sorteio dele sobre o que o dono não levou.
    """
    parceiros = ler_parceiros_ativos_com_acesso()
    if not parceiros:
        return

    try:
        doc_id = event.media.document.id
    except Exception:
        doc_id = None
    chaves = [f"doc_{doc_id}" if doc_id else None, chave_produto(link_capturado)]

    # 🔒 O dono já reservou? Então este vídeo não é de ninguém mais.
    if video_ja_reservado(chaves):
        return

    for p in parceiros:
        try:
            origem = str(p.get("canal_origem") or "")
            try:
                entidade = await client.get_entity(origem)
                if int(getattr(entidade, "id", 0)) != int(str(chat_id).replace("-100", "")):
                    continue
            except Exception:
                continue

            if not ha_espaco_para_parceiros():
                return

            dias = int(p.get("dias_atraso", 30))
            limite = int(p.get("limite_diario", 6))
            data_alvo = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")

            if contar_fila_parceiro(p.get("id"), data_alvo) >= limite:
                if EXIBIR_LOGS: logger.info(f"📦 [Parceiro {p.get('nome')}] Cota de {data_alvo} já cheia. Ignorando.")
                continue

            # 🔒 Reserva ANTES de baixar: se outro parceiro pegou no mesmo instante, para aqui
            if not reservar_video(chaves, parceiro_id=p.get("id")):
                continue

            destino = os.path.join(pasta_do_parceiro(p.get("id")), f"{int(datetime.now().timestamp())}_{random.randint(1000,9999)}.mp4")
            await client.download_media(event.media, file=destino)

            if not os.path.exists(destino):
                if EXIBIR_LOGS: logger.warning(f"⚠️ [Parceiro {p.get('nome')}] Download falhou.")
                continue

            inserir_fila_parceiro(p.get("id"), destino, link_capturado, data_alvo)
            if EXIBIR_LOGS:
                logger.info(f"🎯 [Parceiro {p.get('nome')}] Vídeo capturado e agendado para {data_alvo}. "
                            f"Disco: {espaco_usado_parceiros_gb():.2f} GB de {TETO_DISCO_PARCEIROS_GB} GB.")
            break   # um vídeo pertence a UM parceiro só

        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ [Parceiros] Falha ao capturar para '{p.get('nome')}': {e}")

async def loop_entrada_parceiros():
    """Entra em UM canal por ciclo. Nunca em lote."""
    await asyncio.sleep(60)
    while True:
        try:
            pendentes = ler_parceiros_pendentes()
            if pendentes:
                p = pendentes[0]
                if EXIBIR_LOGS: logger.info(f"👥 [Parceiros] Tentando acessar a origem de '{p.get('nome')}'...")
                ok, motivo = await entrar_no_canal_parceiro(p.get("canal_origem"))
                marcar_origem_parceiro(p.get("id"), 1 if ok else 0, motivo)
                if EXIBIR_LOGS:
                    icone = "✅" if ok else "⚠️"
                    logger.info(f"{icone} [Parceiros] '{p.get('nome')}': {motivo}")
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ [Parceiros] Falha no loop de entrada: {e}")

        await asyncio.sleep(INTERVALO_ENTRADA_PARCEIROS)

# ==========================================
# 💾 ARMAZENAMENTO DOS VÍDEOS DOS PARCEIROS
# Os arquivos ficam em disco até a data de publicação (D+X do parceiro).
# Teto rígido: se estourar, novas capturas são RECUSADAS em vez de encher o disco
# e derrubar todo o sistema (Espião, Autorais e o SQLite junto).
# ==========================================
PASTA_PARCEIROS = "parceiros"
TETO_DISCO_PARCEIROS_GB = 10

def espaco_usado_parceiros_gb():
    total = 0
    try:
        for raiz, _dirs, arquivos in os.walk(PASTA_PARCEIROS):
            for nome in arquivos:
                try:
                    total += os.path.getsize(os.path.join(raiz, nome))
                except OSError:
                    pass
    except Exception:
        pass
    return total / (1024 ** 3)

def ha_espaco_para_parceiros():
    usado = espaco_usado_parceiros_gb()
    if usado >= TETO_DISCO_PARCEIROS_GB:
        if EXIBIR_LOGS:
            logger.warning(f"🛑 [Parceiros] Teto de disco atingido ({usado:.1f} GB de {TETO_DISCO_PARCEIROS_GB} GB). "
                           "Novas capturas recusadas até liberar espaço.")
        return False
    return True

def pasta_do_parceiro(parceiro_id):
    caminho = os.path.join(PASTA_PARCEIROS, str(parceiro_id))
    os.makedirs(caminho, exist_ok=True)
    return caminho

def chave_produto(link):
    """
    Normaliza o link da Shopee para identificar o PRODUTO, não a URL.
    O mesmo item com dois links curtos diferentes gera a mesma chave.
    """
    import re
    if not link:
        return None
    alvo = str(link).split("?")[0].strip().lower()
    # Formato longo: /product/<loja>/<item> ou /<nome>-i.<loja>.<item>
    m = re.search(r'/product/(\d+)/(\d+)', alvo) or re.search(r'-i\.(\d+)\.(\d+)', alvo)
    if m:
        return f"prod_{m.group(1)}_{m.group(2)}"
    # Link curto: usa o código dele como identidade
    m = re.search(r'(?:s\.shopee\.com\.br|shp\.ee|shope\.ee|br\.shp\.ee)/([A-Za-z0-9]+)', alvo)
    if m:
        return f"curto_{m.group(1)}"
    return None

def _garantir_tabela_reservas(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS videos_reservados (
            video_id TEXT PRIMARY KEY,
            parceiro_id INTEGER,
            data_reserva TEXT
        )
    ''')

def video_ja_reservado(chaves):
    """True se QUALQUER uma das chaves já pertence a alguém."""
    chaves = [str(c) for c in chaves if c]
    if not chaves:
        return False
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        _garantir_tabela_reservas(cursor)
        marcadores = ",".join("?" * len(chaves))
        cursor.execute(f"SELECT 1 FROM videos_reservados WHERE video_id IN ({marcadores}) LIMIT 1", chaves)
        achou = cursor.fetchone() is not None
        conexao.close()
        return achou
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [Reserva] Erro ao consultar: {e}")
        return True   # na dúvida, não arrisca duplicar

def reservar_video(chaves, parceiro_id=0):
    """
    🔒 RESERVA GLOBAL DUPLA — bloqueia por ARQUIVO e por PRODUTO.
    Assim o mesmo item não sai duas vezes nem quando os vídeos são diferentes.
    parceiro_id = 0 significa "reservado pelo dono", que sorteia primeiro.
    """
    if not isinstance(chaves, (list, tuple)):
        chaves = [chaves]
    chaves = [str(c) for c in chaves if c]
    if not chaves:
        return False
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        _garantir_tabela_reservas(cursor)
        agora_txt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        reservou = False
        for c in chaves:
            cursor.execute(
                "INSERT OR IGNORE INTO videos_reservados (video_id, parceiro_id, data_reserva) VALUES (?, ?, ?)",
                (c, int(parceiro_id), agora_txt)
            )
            if cursor.rowcount > 0:
                reservou = True
        conexao.commit()
        conexao.close()
        return reservou
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [Reserva] Erro ao reservar {chaves}: {e}")
        return False

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

        # 👥 Oferece o vídeo aos PARCEIROS. Roda antes do fluxo do dono porque
        # a função consulta a reserva: se o vídeo já for seu, ela sai na hora.
        try:
            await capturar_para_parceiros(event, getattr(chat, 'id', None), link_capturado)
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ [Parceiros] Erro na captura paralela: {e}")

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
                    
                    # ✅ Grava o nome que a IA já produziu, no formato que o painel lê.
                    # Antes salvava o texto do concorrente, e o relatório caía no
                    # placeholder "Aguardando análise da IA".
                    nome_produto_autoral = texto_ia.split('\n')[0].strip() if texto_ia else "Produto Exclusivo"
                    legenda_autoral = f"📦 Item: {nome_produto_autoral}\n\n{legenda_final}"

                    fila_dados.setdefault("fila", []).append({
                        "id_unico": id_unico,
                        "msg_id_destino": msg_enviada.id,
                        "legenda": legenda_autoral,
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

                            # 🔒 Marca o vídeo como do DONO, por ARQUIVO e por PRODUTO.
                            # Parceiros consultam esta tabela antes de sortear.
                            try:
                                doc_id = event.media.document.id
                            except Exception:
                                doc_id = None
                            reservar_video([f"doc_{doc_id}" if doc_id else None,
                                            chave_produto(link_capturado)], parceiro_id=0)

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
                # ⏰ Janela e regras lidas do painel (Regras de Repostagem > Janela de Horário).
                # ✅ CORREÇÃO: estas quatro variáveis não existiam no arquivo e o bloco
                # inteiro quebrava com NameError a cada ciclo do loop.
                inicio_janela = int(config_atual.get("inicio", 10))
                fim_janela = int(config_atual.get("fim", 20))
                modo = config_atual.get("modo", "aleatorio")
                dias_retorno_cfg = int(config_atual.get("dias_retorno", 15))
                # A data_alvo já aplicou o atraso D+X lá na captura. Aqui basta cair
                # no ramo diluído do motor, que é quem espalha os vídeos pela janela.
                intervalo_dias = 1

                config_fila = {
                    "inicio": inicio_janela,
                    "fim": fim_janela,
                    "modo": modo,
                    "intervalo_dias": intervalo_dias,
                    # ⏱️ PISO de segurança, não intervalo padrão: com poucos vídeos o motor
                    # divide a janela e espalha pelo dia. O piso só age em volume alto.
                    "espacamento_base_min": 15,
                    "espacamento_variacao_min": 6,
                    # ✅ CORREÇÃO: o descarte por idade precisa acompanhar o D+X da fila.
                    # Com 5 fixo e dias_retorno=15, todo vídeo nascia vencido e voltava
                    # do motor sem horário nenhum.
                    "limite_dias_descarte": dias_retorno_cfg + 5
                }
                
                if EXIBIR_LOGS: logger.info(f"⚙️ [Motor Autorais] Acionando Motor Central para {len(itens_desagendados)} vídeos de retorno...")
                calcular_horarios_distribuicao(itens_desagendados, config_fila, forcar=False)

                # 🗑️ O motor marcou algum item como velho demais? Sai da fila e do disco,
                # senão ele fica sem horário e volta a ser reprocessado a cada 60s.
                marcados = [i for i in itens_desagendados if i.get("descartar_por_idade")]
                if marcados:
                    ids_marcados = {i.get("id_unico") for i in marcados}
                    for velho in marcados:
                        caminho_velho = velho.get("caminho_arquivo")
                        if caminho_velho and os.path.exists(caminho_velho):
                            try: os.remove(caminho_velho)
                            except Exception: pass
                    fila_dados["fila"] = [i for i in fila_dados.get("fila", []) if i.get("id_unico") not in ids_marcados]
                    fila = fila_dados.get("fila", [])
                    if EXIBIR_LOGS: logger.info(f"🗑️ [Motor Autorais] {len(marcados)} vídeo(s) descartado(s) por idade.")

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
    asyncio.create_task(loop_entrada_parceiros())   # 👥 entrada nos canais dos parceiros
    
    if EXIBIR_LOGS: logger.info("🤖 Sistema a rodar. A escutar o grupo de origem continuamente...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
