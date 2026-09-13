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
from motor_filas import calcular_horarios_distribuicao, faixa_de_config, sortear_teto_do_dia # ⚙️ Motor Central Importado

# As chaves da Shopee e do Gemini foram movidas para os módulos centrais.

# Inicialização do Agendador
scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

if EXIBIR_LOGS:
    logger = configurar_logs(__name__)

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
        # 🚀 Migração local: o bot_mestre também cria esta coluna, mas os dois serviços
        # sobem em ordem imprevisível. Garantir aqui evita que o salvar_fila_retorno()
        # estoure "no such column" e perca a fila inteira num deploy.
        try:
            cursor.execute("ALTER TABLE fila_autorais ADD COLUMN data_postagem TEXT")
            conexao.commit()
        except sqlite3.OperationalError:
            pass

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
                "processado": bool(linha["processado"]),
                "data_postagem": dict(linha).get("data_postagem") or ""
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
                INSERT INTO fila_autorais (id_unico, msg_id_destino, legenda, caminho_arquivo, data_captura, data_alvo, horario_disparo, processado, data_postagem)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item.get("id_unico"), 
                item.get("msg_id_destino"), 
                item.get("legenda"), 
                item.get("caminho_arquivo"), 
                item.get("data_captura"), 
                item.get("data_alvo"), 
                item.get("horario_disparo", ""), 
                1 if item.get("processado") else 0,
                item.get("data_postagem", "")
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

_cache_id_origem = {}

def _id_curto(valor):
    """Converte qualquer forma de chat_id no ID interno do Telethon.

    A API de bots usa -100XXXXXXXXXX; o Telethon usa só o XXXXXXXXXX. Os dois
    lados da comparação passam por aqui, senão a captura nunca casa.
    """
    texto = str(valor or "").strip().lstrip("-")
    if texto.startswith("100") and len(texto) > 10:
        texto = texto[3:]
    return int(texto) if texto.isdigit() else None

async def resolver_entidade(alvo):
    """Resolve @username, link t.me ou ID numérico numa entidade do Telethon.

    get_entity() sozinho falha com ID numérico quando a entidade não está no
    cache da sessão — mesmo com a conta sendo membro do canal. Varrer os
    diálogos popula esse cache. É o mesmo caminho que o divulgacao_canal.py
    já usa para achar os fóruns.
    """
    alvo = str(alvo or "").strip()
    if not alvo:
        return None

    try:
        return await client.get_entity(alvo)
    except Exception:
        pass

    # Varrer diálogos só faz sentido para ID numérico.
    alvo_id = _id_curto(alvo)
    if alvo_id is None:
        return None

    try:
        async for dialogo in client.iter_dialogs():
            if int(getattr(dialogo.entity, "id", 0)) == alvo_id:
                return dialogo.entity
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [Parceiros] Falha ao varrer diálogos: {e}")

    return None

async def id_do_canal_origem(alvo):
    """ID numérico do canal de origem, com cache.

    Evita um get_entity por mensagem por parceiro no caminho quente da captura.
    """
    chave = str(alvo or "").strip()
    if not chave:
        return None
    if chave in _cache_id_origem:
        return _cache_id_origem[chave]

    direto = _id_curto(chave)
    if direto is not None:
        _cache_id_origem[chave] = direto
        return direto

    entidade = await resolver_entidade(chave)
    if entidade:
        _cache_id_origem[chave] = int(getattr(entidade, "id", 0))
        return _cache_id_origem[chave]
    return None

async def entrar_no_canal_parceiro(alvo):
    """
    Devolve (sucesso, motivo). Se o userbot já enxerga o canal, qualquer
    formato serve — inclusive ID numérico. Só quando ele NÃO é membro é que
    o Telegram exige @username ou link de convite para a entrada automática.
    """
    alvo = str(alvo or "").strip()
    if not alvo:
        return False, "origem vazia"

    try:
        # Já temos acesso? Então não há o que fazer.
        if await resolver_entidade(alvo):
            return True, "já acessível"

        if "+" in alvo or "joinchat" in alvo:
            hash_convite = alvo.split("+")[-1].split("/")[-1]
            await client(functions.messages.ImportChatInviteRequest(hash_convite))
            return True, "entrou pelo link de convite"

        if alvo.startswith("@") or ("t.me/" in alvo and "+" not in alvo):
            usuario = alvo.split("t.me/")[-1].replace("@", "").strip("/")
            await client(functions.channels.JoinChannelRequest(usuario))
            return True, "entrou pelo @username"

        return False, ("userbot não é membro e ID numérico não permite entrada "
                       "automática: adicione a conta no canal ou use @username / link de convite")

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
    # 🔎 DIAGNÓSTICO: cada saída antecipada daqui era silenciosa, então uma fila
    # parada em zero não dizia NADA sobre onde o fluxo tinha morrido. Agora cada
    # porta fechada se anuncia, com o dado que permite conferir a configuração.
    parceiros = ler_parceiros_ativos_com_acesso()
    if not parceiros:
        if EXIBIR_LOGS: logger.info("👥 [Parceiros] Vídeo visto, mas nenhum parceiro ativo com acesso liberado.")
        return

    try:
        doc_id = event.media.document.id
    except Exception:
        doc_id = None
    chaves = [f"doc_{doc_id}" if doc_id else None, await chave_produto_resolvida(link_capturado)]

    # 🔒 O dono já reservou? Então este vídeo não é de ninguém mais.
    if video_ja_reservado(chaves):
        if EXIBIR_LOGS: logger.info(f"👥 [Parceiros] Vídeo já reservado por outro. Chat {chat_id}.")
        return

    if EXIBIR_LOGS:
        logger.info(f"👥 [Parceiros] Vídeo com link no chat {_id_curto(chat_id)} — "
                    f"conferindo {len(parceiros)} parceiro(s) com acesso.")

    for p in parceiros:
        try:
            origem = str(p.get("canal_origem") or "")
            id_origem = await id_do_canal_origem(origem)
            if not id_origem or id_origem != _id_curto(chat_id):
                if EXIBIR_LOGS:
                    logger.info(f"👥 [Parceiro {p.get('nome')}] Origem '{origem}' resolve para "
                                f"{id_origem or 'NADA'}, e o vídeo veio de {_id_curto(chat_id)}. Ignorado.")
                continue

            if EXIBIR_LOGS: logger.info(f"👥 [Parceiro {p.get('nome')}] Origem bateu. Capturando...")

            if not ha_espaco_para_parceiros():
                return

            dias = int(p.get("dias_atraso", 30))
            data_alvo = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")

            # 📦 O 'limite_diario' NÃO corta mais aqui: captura-se tudo e a escolha de
            # quais vídeos vão ao ar passou para o motor de publicação (bot_mestre).
            # O único freio na captura passa a ser o teto de disco, checado acima.

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

    ATENÇÃO: sozinha, esta função NÃO reconhece o mesmo item por trás de dois
    encurtadores diferentes — para link curto ela usa o código do encurtador
    como identidade. Quem precisa dessa garantia chama chave_produto_resolvida,
    que abre o link antes e assim chega ao ID real do produto.
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

# 🗓️ Prazo de validade do cache de encurtadores. O par código → produto em si
# nunca muda, mas guardar para sempre acumula lixo de campanha velha sem
# proveito: link de um ano atrás dificilmente volta a aparecer.
DIAS_VALIDADE_CACHE_LINKS = 365

def _garantir_tabela_links(cursor):
    # A versão anterior guardava a URL inteira na coluna 'url_final'. Como isto
    # é só cache, o mais limpo na migração é derrubar a tabela velha e deixar
    # reconstruir-se sozinha: nada de valor se perde, apenas se resolve de novo
    # na primeira vez que cada link voltar a aparecer.
    try:
        colunas = [c[1] for c in cursor.execute("PRAGMA table_info(links_resolvidos)").fetchall()]
        if colunas and "chave_final" not in colunas:
            cursor.execute("DROP TABLE links_resolvidos")
    except Exception:
        pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS links_resolvidos (
            codigo_curto TEXT PRIMARY KEY,
            chave_final TEXT,
            data_resolucao TEXT
        )
    ''')

async def resolver_chave_curta(link):
    """
    🔗 Descobre qual PRODUTO está por trás de um link curto da Shopee.

    Existe por causa de uma brecha na trava anti-duplicata: dois afiliados que
    divulgam o MESMO item geram encurtadores diferentes, e a chave saía
    `curto_AbCd123` contra `curto_XyZw789` — duas identidades para um produto
    só, e o item aparecia duas vezes no grupo. Resolvido o destino, os dois
    viram o mesmo `prod_loja_item` e a trava pega.

    Guarda só a CHAVE, não a URL inteira: é o único dado usado, ocupa bem menos
    e dispensa reprocessar a URL a cada leitura.

    O cache vale DIAS_VALIDADE_CACHE_LINKS dias. Passado o prazo a linha é
    ignorada e some na próxima gravação, então a tabela se recicla sozinha sem
    precisar de tarefa agendada só para isso.

    Guarda também o resultado VAZIO de um link que abriu mas não tinha produto,
    senão a rede seria consultada de novo por algo que nunca vai resolver. Falha
    de rede NÃO é gravada, para poder tentar outra vez mais tarde.
    """
    achado = re.search(r'(?:s\.shopee\.com\.br|shp\.ee|shope\.ee|br\.shp\.ee)/([A-Za-z0-9]+)', str(link or "").lower())
    if not achado:
        return None
    codigo = achado.group(1)
    limite_validade = (datetime.now() - timedelta(days=DIAS_VALIDADE_CACHE_LINKS)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        _garantir_tabela_links(cursor)
        conexao.commit()
        cursor.execute(
            "SELECT chave_final FROM links_resolvidos WHERE codigo_curto = ? AND data_resolucao >= ?",
            (codigo, limite_validade)
        )
        linha = cursor.fetchone()
        conexao.close()
        if linha is not None:
            return linha[0] or None   # vazio = já tentámos e não havia produto
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [Link Curto] Erro ao ler o cache: {e}")

    try:
        tempo = aiohttp.ClientTimeout(total=8)
        cabecalhos = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile"}
        async with aiohttp.ClientSession(timeout=tempo, headers=cabecalhos) as sessao:
            async with sessao.get(str(link), allow_redirects=True) as resposta:
                url_final = str(resposta.url)
    except Exception as e:
        if EXIBIR_LOGS: logger.warning(f"⚠️ [Link Curto] Não resolveu {codigo}, tentará de novo depois: {e}")
        return None

    chave_final = chave_produto(url_final) or ""
    if chave_final.startswith("curto_"):
        chave_final = ""   # o destino também era curto: não serve de identidade

    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        _garantir_tabela_links(cursor)
        cursor.execute(
            "INSERT OR REPLACE INTO links_resolvidos (codigo_curto, chave_final, data_resolucao) VALUES (?, ?, ?)",
            (codigo, chave_final, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        # 🧹 Faxina de carona: aproveita a gravação para varrer o que venceu. Só
        # corre quando aparece um encurtador novo, que é raro, e a tabela é
        # pequena — não justifica uma tarefa agendada própria.
        cursor.execute("DELETE FROM links_resolvidos WHERE data_resolucao < ?", (limite_validade,))
        vencidos = cursor.rowcount
        conexao.commit()
        conexao.close()
        if vencidos and EXIBIR_LOGS:
            logger.info(f"🧹 [Link Curto] {vencidos} link(s) fora do prazo de {DIAS_VALIDADE_CACHE_LINKS} dias removido(s).")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [Link Curto] Erro ao gravar o cache: {e}")

    if EXIBIR_LOGS:
        logger.info(f"🔗 [Link Curto] {codigo} -> {chave_final or 'sem produto'}, guardado em cache.")
    return chave_final or None

async def chave_produto_resolvida(link):
    """
    A chave do produto, abrindo o encurtador quando preciso.

    Só vai à rede quando a chave direta sai como `curto_`, ou seja, quando o
    link não trazia o ID do produto. Link longo nem consulta o cache.
    """
    chave = chave_produto(link)
    if chave and not chave.startswith("curto_"):
        return chave

    return await resolver_chave_curta(link) or chave

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

    # 👥 PARCEIROS: cada parceiro vigia o PRÓPRIO canal de origem, que quase nunca
    # é o mesmo canal do dono. Por isso esta chamada precisa vir ANTES do corte do
    # "eh_origem" — abaixo dele o evento já foi descartado e o parceiro nunca vê nada.
    if isinstance(getattr(event, 'media', None), MessageMediaDocument):
        link_parceiro = extrair_link_shopee(event)
        if link_parceiro:
            try:
                await capturar_para_parceiros(event, getattr(chat, 'id', None), link_parceiro)
            except Exception as e:
                if EXIBIR_LOGS: logger.error(f"❌ [Parceiros] Erro na captura paralela: {e}")

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

                agora = datetime.now()
                data_alvo = (agora + timedelta(days=dias_retorno)).strftime("%Y-%m-%d")

                # 🎲 A cota do dia sai de um sorteio dentro da faixa, e não mais de um
                # número fixo. Reservatório do mesmo tamanho todo santo dia é assinatura
                # de robô; variando, a quantidade publicada parece decisão de gente. O
                # sorteio é determinístico pela DATA-ALVO, então o reservatório não muda
                # de tamanho no meio do próprio dia nem depois de um reinício.
                piso_aut, topo_aut = faixa_de_config(config_atual, "limite_min", "limite_max", "limite_videos")
                limite_videos = sortear_teto_do_dia("autorais", data_alvo, piso_aut, topo_aut) or piso_aut or 5
                
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
                        data_alvo_pub = (agora + timedelta(days=dias_publico)).strftime("%Y-%m-%d")

                        # 🎲 Mesma ideia dos autorais: o tamanho do reservatório do Grupo
                        # Público varia por dia, com semente própria para não sortear o
                        # mesmo número que os autorais na mesma data.
                        piso_pub, topo_pub = faixa_de_config(config_pub, "repost_limite_min", "repost_limite_max", "repost_limite")
                        limite_publico = sortear_teto_do_dia("publico", data_alvo_pub, piso_pub, topo_pub) or piso_pub or 6

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
                                            await chave_produto_resolvida(link_capturado)], parceiro_id=0)

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
                    
                    # 🎯 A origem pode estar gravada no formato composto "-100123:5".
                    # Este era o ÚNICO ponto do arquivo que usava o valor cru: o Telethon
                    # não resolve "-100123:5" como entidade e o envio morria aqui.
                    origem_final, origem_topico = separar_alvo_e_topico(config_atual.get('origem'))
                    kwargs_retorno = {}
                    if origem_topico and origem_topico > 1:
                        kwargs_retorno['reply_to'] = origem_topico

                    encerrar_item = False
                    if origem_final is None:
                        if EXIBIR_LOGS: logger.error("❌ [Motor Autorais] Origem não configurada no painel. Vídeo mantido na fila.")
                    else:
                        try:
                            if os.path.exists(caminho_arquivo):
                                await client.send_file(
                                    origem_final,
                                    file=caminho_arquivo,
                                    caption=legenda,
                                    parse_mode='md',
                                    **kwargs_retorno
                                )
                                encerrar_item = True
                                # ⏱️ Carimba a hora REAL da publicação — é o que o relatório
                                # precisa mostrar nos itens já postados.
                                item["data_postagem"] = agora.strftime("%Y-%m-%d %H:%M:%S")
                                if EXIBIR_LOGS: logger.info(f"✅ [Motor Autorais] Vídeo de retorno {item.get('id_unico')} publicado com sucesso!")
                                
                                os.remove(caminho_arquivo)
                                if EXIBIR_LOGS: logger.info("🧹 Ficheiro arquivado removido após postagem final.")
                            else:
                                # Arquivo sumiu do disco: não há o que reenviar. Sai da fila,
                                # senão fica a ser tentado de 60 em 60 segundos para sempre.
                                encerrar_item = True
                                if EXIBIR_LOGS: logger.warning(f"⚠️ Ficheiro arquivado não encontrado em {caminho_arquivo}. Item encerrado.")
                        except Exception as e:
                            if EXIBIR_LOGS: logger.error(f"❌ Falha no disparo de retorno: {e}")

                    if encerrar_item:
                        # ✅ Só sai da fila quando REALMENTE saiu. Antes esta linha vivia fora
                        # do try e marcava "processado" mesmo depois de exceção: o relatório
                        # mostrava "✅ Postado" e o vídeo nunca tinha ido ao ar.
                        item["processado"] = True
                    else:
                        # 🚦 ANTI-TRAVA: adia 30 min e tenta de novo, sem segurar os seguintes.
                        item["horario_disparo"] = (agora + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
                    houve_disparo = True
                    
                itens_restantes.append(item)
                
            if houve_disparo:
                fila_dados["fila"] = itens_restantes
                salvar_fila_retorno(fila_dados)

        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro no loop de postagem de autorais: {e}")
            
        await asyncio.sleep(60) # Respira 1 minuto e volta a procurar

# ==========================================
# 📬 MOTOR DO GRUPO PÚBLICO — o disparo mora aqui, não no bot_mestre
#
# O canal onde os autorais são publicados não é nosso: o bot do aiogram não pode ser
# adicionado lá e, sem ser membro, o copy_message dele devolve "chat not found" em todo
# ciclo. Esta conta tem acesso — é ela que publica no canal todos os dias. Por isso o
# ENVIO vive aqui. O bot_mestre continua dono da fila, da faxina e do sorteio de
# horários; lá a trava 'repost_via_userbot' desliga só a parte do envio.
# ==========================================
ADMIN_ID_CREDITO = 1226920464   # mesmo ADMIN_ID do bot_mestre, só para assinar o post
_cache_credito_publico = {"valor": None, "expira": None}


async def obter_credito_repost_userbot():
    """@ do administrador para assinar a repostagem, com cache de 24h."""
    agora = datetime.now()
    if _cache_credito_publico["valor"] and _cache_credito_publico["expira"] and agora < _cache_credito_publico["expira"]:
        return _cache_credito_publico["valor"]
    try:
        usuario = await client.get_entity(ADMIN_ID_CREDITO)
        if getattr(usuario, "username", None):
            credito = f"@{usuario.username}"
        else:
            nome = getattr(usuario, "first_name", None) or "Administrador"
            credito = f"<a href='tg://user?id={ADMIN_ID_CREDITO}'>{nome}</a>"
        _cache_credito_publico["valor"] = credito
        _cache_credito_publico["expira"] = agora + timedelta(hours=24)
        return credito
    except Exception as e:
        if EXIBIR_LOGS: logger.warning(f"⚠️ [Motor Público] Não consegui resolver o @ do admin ({e}).")
        return "um membro"


def registrar_ultimo_post_userbot(chat_destino, tipo_conteudo):
    """Alimenta a intercalação: o bot_mestre lê exatamente esta chave no SQLite."""
    try:
        dados = ler_config_bd_autorais("ultimo_post_canais", {})
        dados[str(chat_destino)] = {
            "tipo": tipo_conteudo,
            "hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        salvar_config_bd_autorais("ultimo_post_canais", dados)
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [Motor Público] Erro ao registrar último post: {e}")


async def processar_fila_publico_loop():
    if EXIBIR_LOGS: logger.info("📬 [Motor Público] Loop de repostagem no Grupo Público iniciado.")
    ja_auditou = False

    while True:
        try:
            config = ler_config_bd_autorais("submissao_config", {})

            if not config.get("repost_via_userbot", True):
                await asyncio.sleep(120)
                continue
            if not config.get("ativo") or config.get("repost_pausado", False):
                await asyncio.sleep(60)
                continue

            # 📤 Destino: "repost_destino" no formato "-100123:6"; senão grupo + tópico padrão
            destino_final, destino_topico = separar_alvo_e_topico(config.get("repost_destino"))
            if destino_final is None:
                destino_final, _ = separar_alvo_e_topico(config.get("grupo_id"))
                destino_topico = config.get("topico_destino")

            # 📥 Origem: o canal onde o vídeo autoral foi publicado
            origem_final, _ = separar_alvo_e_topico(
                config.get("repost_origem") or carregar_config_autorais().get("destino")
            )

            if destino_final is None or origem_final is None:
                await asyncio.sleep(60)
                continue

            # 🔎 Auditoria única por execução. Sem acesso aos dois lados nada sai daqui, e
            # é melhor dizer isso uma vez no log do que falhar em silêncio para sempre.
            if not ja_auditou:
                ja_auditou = True
                for rotulo, alvo_audit in (("origem", origem_final), ("destino", destino_final)):
                    try:
                        entidade = await client.get_entity(alvo_audit)
                        if EXIBIR_LOGS: logger.info(f"✅ [Motor Público] Acesso à {rotulo} OK: {getattr(entidade, 'title', alvo_audit)}")
                    except Exception as err:
                        if EXIBIR_LOGS: logger.error(f"❌ [Motor Público] SEM acesso à {rotulo} ({alvo_audit}): {err}")

            agora = datetime.now()
            agora_txt = agora.strftime("%Y-%m-%d %H:%M:%S")

            # ⏰ Janela de postagem. O disparo antigo (no bot_mestre) só olhava o
            # horario_disparo, então item atrasado de ontem saía de madrugada — o oposto
            # do que a fila tenta parecer. Fora da janela, espera; nada é perdido, os
            # itens continuam na fila esperando a abertura.
            janela_inicio = int(config.get("repost_inicio", 10))
            janela_fim = int(config.get("repost_fim", 20))
            if not (janela_inicio <= agora.hour < janela_fim):
                await asyncio.sleep(300)
                continue

            # 🎯 UPDATE pontual, nunca salvar_fila_publico(): aquela função apaga a tabela
            # e reinsere tudo, e o bot_mestre escreve os horários na MESMA fila. Um save
            # daqui apagaria o que ele acabou de sortear.
            conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
            conexao.row_factory = sqlite3.Row
            cursor = conexao.cursor()
            cursor.execute('''
                SELECT * FROM fila_publico
                WHERE processado = 0
                AND horario_disparo IS NOT NULL
                AND horario_disparo != ''
                AND horario_disparo <= ?
                ORDER BY horario_disparo ASC LIMIT 1
            ''', (agora_txt,))
            alvo = cursor.fetchone()

            if not alvo:
                conexao.close()
                await asyncio.sleep(60)
                continue

            id_unico = alvo["id_unico"]
            msg_id = alvo["msg_id_destino"]
            legenda_original = alvo["legenda"] or ""

            try:
                match_link = re.search(r'(?:https?://)?(?:s\.shopee\.com\.br|shope\.ee|br\.shp\.ee|shp\.ee)/[^\s<]+', legenda_original, re.IGNORECASE)
                link_shopee = match_link.group(0) if match_link else "https://shopee.com.br"

                match_item = re.search(r'📦\s*Item:\s*([^\n<]+)', legenda_original)
                nome_produto = match_item.group(1).strip() if match_item else "Produto Exclusivo"

                credito = await obter_credito_repost_userbot()
                legenda_final = (
                    f"👤 Vídeo enviado por: {credito}\n\n"
                    f"<b>{nome_produto}</b>\n\n"
                    f"🔗 <b>Link do Produto:</b>\n{link_shopee}\n\n"
                    f"<i>#Recomendado #Shopee</i>"
                )

                if not msg_id:
                    raise ValueError("item sem msg_id_destino")

                msg_origem = await client.get_messages(origem_final, ids=int(msg_id))
                if not msg_origem or not getattr(msg_origem, "media", None):
                    # Mensagem apagada na origem: não há o que repostar e nunca mais vai
                    # haver. Sai da fila, senão fica a ser tentada para sempre.
                    cursor.execute("DELETE FROM fila_publico WHERE id_unico = ?", (id_unico,))
                    conexao.commit()
                    conexao.close()
                    if EXIBIR_LOGS: logger.warning(f"🧹 [Motor Público] Mensagem {msg_id} sumiu da origem. Item {id_unico} removido da fila.")
                    await asyncio.sleep(60)
                    continue

                kwargs_envio = {}
                if destino_topico and int(destino_topico) > 1:
                    kwargs_envio['reply_to'] = int(destino_topico)

                # 📎 file=msg.media reaproveita o arquivo que já está no servidor do
                # Telegram. Não baixa, não reenvia bytes, não gasta disco.
                await client.send_file(
                    destino_final,
                    file=msg_origem.media,
                    caption=legenda_final,
                    parse_mode='html',
                    **kwargs_envio
                )

                registrar_ultimo_post_userbot(destino_final, "video")   # 🚦 Intercalação
                cursor.execute(
                    "UPDATE fila_publico SET processado = 1, data_postagem = ?, horario_disparo = ? WHERE id_unico = ?",
                    (agora_txt, agora_txt, id_unico)
                )
                conexao.commit()
                if EXIBIR_LOGS: logger.info(f"✅ [Motor Público] '{nome_produto}' publicado no Grupo Público.")

            except FloodWaitError as e:
                # Telegram mandou esperar. Respeitar não é opcional: esta conta é a peça
                # mais frágil do sistema e uma rajada teimosa derruba ela.
                espera = int(getattr(e, "seconds", 60))
                if EXIBIR_LOGS: logger.warning(f"⏳ [Motor Público] FloodWait de {espera}s. Item adiado.")
                cursor.execute(
                    "UPDATE fila_publico SET horario_disparo = ? WHERE id_unico = ?",
                    ((agora + timedelta(seconds=espera + 60)).strftime("%Y-%m-%d %H:%M:%S"), id_unico)
                )
                conexao.commit()
                conexao.close()
                await asyncio.sleep(espera + 5)
                continue

            except Exception as e:
                if EXIBIR_LOGS:
                    logger.error(f"❌ [Motor Público] Falha ao publicar: {e} "
                                 f"| origem={origem_final!r} destino={destino_final!r} "
                                 f"topico={destino_topico!r} msg_id={msg_id!r}")
                # 🚦 ANTI-TRAVA: adia 30 min, senão este item segura a fila inteira atrás.
                cursor.execute(
                    "UPDATE fila_publico SET horario_disparo = ? WHERE id_unico = ?",
                    ((agora + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"), id_unico)
                )
                conexao.commit()

            conexao.close()

        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ [Motor Público] Erro estrutural no loop: {e}")

        await asyncio.sleep(60)


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
    asyncio.create_task(processar_fila_publico_loop())   # 📬 repostagem no Grupo Público
    asyncio.create_task(loop_entrada_parceiros())   # 👥 entrada nos canais dos parceiros
    
    if EXIBIR_LOGS: logger.info("🤖 Sistema a rodar. A escutar o grupo de origem continuamente...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
