"""
Robô dos Vídeos Autorais (userbot Telethon). As contas vêm do pool_contas: uma
captura e publica no destino; as do rodízio devolvem os vídeos ao grupo de origem.
Sem contas no pool, a sessão fixa sessao_espelhador_isolado faz tudo.

Captura: cada vídeo com link da Shopee postado no grupo de origem (autorais_config:
origem, com tópico opcional) é baixado, ganha legenda nova da IA com o link já
convertido para o afiliado e é publicado no canal de destino. A mensagem chega pelo
evento NewMessage e pela varredura_origem_loop (o evento nem sempre chega);
mensagem_ja_processada impede que a mesma seja processada duas vezes.

Retorno D+X: o vídeo pode entrar na fila_autorais para voltar ao grupo de origem
dias_retorno dias depois. Quantos entram por dia sai de um sorteio por reservatório
(todo vídeo do dia tem a mesma chance) com a cota diária do painel; o
processar_fila_autorais_loop devolve um por ciclo, dentro da janela e do teto.
Os arquivos ficam em archive/ até a publicação.

Grupo Público: sorteio independente, sobre o mesmo vídeo, para a fila_publico. Este
robô só baixa o arquivo (processar_fila_publico_loop); quem publica é o bot_mestre.

Parceiros: vídeos dos canais de origem dos parceiros vão para a fila_parceiros, em
parceiros/<id>/, e também são publicados pelo bot_mestre.
"""

import os
import json
import time
import asyncio
import random
import aiohttp
import re
from datetime import datetime, timedelta
from telethon import TelegramClient, events, functions
from telethon.tl.types import MessageMediaDocument
from telethon import errors as tg_errors
from telethon.errors import FloodWaitError, UserAlreadyParticipantError, InviteHashExpiredError
from dotenv import load_dotenv
from utils import registrar_erro_json

load_dotenv()

# Importar o fuso já fixa o processo em America/Sao_Paulo.
from fuso import configurar_logs

load_dotenv()

# temp/: downloads de passagem. archive/: vídeos da fila de retorno até a publicação.
os.makedirs("temp", exist_ok=True)
os.makedirs("archive", exist_ok=True)

from api_gemini import analisar_video_gemini
from api_shopee import converter_link_shopee
from links_shopee import extrair_link_shopee, codigo_do_link_curto
import legendas
from videos import verificar_e_otimizar_video
from motor_filas import calcular_horarios_distribuicao, faixa_de_config, sortear_teto_do_dia
import blacklist_captura  # de quem este robô nunca captura
import repetidos_publico  # vídeo que já foi ao Grupo Público não vai de novo
import pool_contas  # quem captura e quem reposta

logger = configurar_logs(__name__)

API_ID = int(os.getenv('API_ID', 0)) 
API_HASH = os.getenv('API_HASH', '')

import sqlite3
import db

def carregar_config_autorais():
    """autorais_config, gravado pelo painel do bot_mestre: origem, destino, dias_retorno, cota, janela e pausas."""
    padrao = {"origem": -1003673555953, "origem_topico": None, "destino": "@videos_autorais"}
    dados = db.ler_config("autorais_config", padrao)
    if not dados:
        logger.warning("⚠️ Configuração 'autorais_config' não encontrada. Aguardando o bot principal criá-la.")
    return dados

def salvar_config_autorais(config):
    db.salvar_config("autorais_config", config)


def pausa_ativa(escopo="autorais"):
    """Lê a pausa direto do banco, na hora.

    Para ser chamada logo antes de cada publicação: entre o topo do ciclo e o envio
    passam até 60 s de loop, ou dezenas de segundos de download, ffmpeg e IA, e a
    pausa pedida no painel nesse meio-tempo precisa valer.

    escopo "captura"  → só a pausa geral do robô autoral
    escopo "autorais" → pausa geral OU pausa da repostagem de retorno
    escopo "publico"  → módulo de submissão desligado OU repostagem pública pausada
    """
    try:
        if escopo == "publico":
            cfg = db.ler_config("submissao_config", {})
            return (not cfg.get("ativo", False)) or bool(cfg.get("repost_pausado", False))

        cfg = db.ler_config("autorais_config", {})
        if bool(cfg.get("pausar_robo_completo", False)):
            return True
        if escopo == "captura":
            return False
        return bool(cfg.get("pausar_repostagem", False))
    except Exception as e:
        logger.error(f"❌ Falha ao consultar a pausa ({escopo}): {e}")
        return False


config_atual = carregar_config_autorais()

# ==========================================================================
# Contas que operam neste robô (pool_contas)
#
# Captura (posto "espelho"): uma conta fica no grupo de origem, captura, publica no
# canal de destino, baixa os vídeos do Grupo Público e vigia os canais dos
# parceiros. Repostagem: as contas do rodízio devolvem os vídeos ao grupo de origem
# no D+X, cada vídeo por uma conta. A captura nunca reposta: se uma conta da
# repostagem for expulsa, a captura segue intacta.
#
# Quem ocupa cada posto é o pool_contas que decide; o plantao_contas_loop confere
# as contas de 10 em 10 minutos e troca os clientes daqui sozinho.
#
# Sem nenhuma conta no pool vale o modo antigo: a sessão fixa
# sessao_espelhador_isolado faz tudo (captura e repostagem).
#
# Um userbot só enxerga os grupos em que a conta dele está: a da captura precisa
# estar na origem e poder publicar no destino; as da repostagem, na origem.
# ==========================================================================
NOME_SESSAO = 'sessao_espelhador_isolado'
client = None               # cliente da captura (None = captura parada)
conta_captura = None        # conta do pool na captura (None no modo sessão fixa)
modo_sessao_fixa = False
clientes_repost = {}        # conta_id → (conta, cliente) do rodízio da repostagem
ordem_rodizio = []          # conta_ids na ordem do pool
_espera_repost = {}         # conta_id → até quando a conta fica fora do rodízio
_ultimo_repostador = None   # conta_id do último envio: o rodízio segue dali

INTERVALO_PLANTAO_MIN = 10
HORAS_ESPERA_SEM_PERMISSAO = 1   # conta sem permissão de postar descansa antes de tentar de novo


def ler_fila_retorno():
    """Fila de retorno (tabela fila_autorais) como {"fila": [itens]}. Cria a tabela e as colunas novas se faltarem."""
    try:
        conexao = db.conectar()
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()
        
        # Cria a tabela se o bot_mestre ainda não a criou.
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
        # Colunas novas. O bot_mestre também as cria, mas os serviços sobem em qualquer
        # ordem, e sem elas o salvar_fila_retorno() falharia com "no such column".
        try:
            cursor.execute("ALTER TABLE fila_autorais ADD COLUMN msg_postada_id INTEGER")
            conexao.commit()
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE fila_autorais ADD COLUMN data_postagem TEXT")
            conexao.commit()
        except sqlite3.OperationalError:
            pass
        _garantir_colunas_novas(cursor, conexao)

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
                "data_postagem": dict(linha).get("data_postagem") or "",
                "msg_postada_id": dict(linha).get("msg_postada_id"),
                "autor_id": dict(linha).get("autor_id"),
                "autor_username": dict(linha).get("autor_username") or "",
                "chaves_video": dict(linha).get("chaves_video") or ""
            })
        return {"fila": fila}
    except Exception as e:
        logger.error(f"❌ Erro ao ler fila_autorais do SQLite: {e}")
        return {"fila": []}

def _garantir_colunas_novas(cursor, conexao):
    """
    Colunas que a fila_autorais ganhou depois. autor_*: o autor do vídeo original, para
    a lista negra ser reconferida na hora de repostar (itens antigos: NULL, autor
    desconhecido). repostado_publico e data_repost_publico: o botão Disparar Repost
    Autoral do bot_mestre marca o que já foi ao Grupo Público. chaves_video: o que
    reconhece o vídeo (repetidos_publico).
    """
    for coluna, tipo in (("autor_id", "INTEGER"), ("autor_username", "TEXT"),
                         ("repostado_publico", "INTEGER DEFAULT 0"), ("data_repost_publico", "TEXT"),
                         ("chaves_video", "TEXT")):
        try:
            cursor.execute(f"ALTER TABLE fila_autorais ADD COLUMN {coluna} {tipo}")
            conexao.commit()
        except sqlite3.OperationalError:
            pass

def salvar_fila_retorno(dados):
    """
    Regrava a tabela fila_autorais a partir de dados (DELETE + INSERT de cada item).

    processado, data_postagem e msg_postada_id de quem já está no banco são relidos
    aqui e mantidos: o loop de retorno grava esses campos com UPDATE logo depois de
    publicar, e regravar a partir de um retrato antigo devolveria o vídeo a
    "pendente" (seria publicado de novo). O mesmo vale para repostado_publico e
    data_repost_publico, que o botão Disparar Repost Autoral grava: sem isso o vídeo
    voltaria a poder ir ao Grupo Público outra vez. horario_disparo vem do retrato, que é quem
    sorteia os horários; o do banco só vale quando o retrato não tem.
    """
    # É a transação de escrita mais longa do sistema: a conexão fecha no finally
    # mesmo se estourar no meio, senão o lock fica preso com o DELETE aberto.
    conexao = None
    try:
        conexao = db.conectar()
        cursor = conexao.cursor()
        
        _garantir_colunas_novas(cursor, conexao)
        status_atual = {}
        try:
            cursor.execute("SELECT id_unico, horario_disparo, processado, data_postagem, msg_postada_id, "
                           "repostado_publico, data_repost_publico FROM fila_autorais")
            for linha in cursor.fetchall():
                status_atual[linha[0]] = linha[1:]
        except Exception:
            pass

        cursor.execute("DELETE FROM fila_autorais")
        for item in dados.get("fila", []):
            gravado = status_atual.get(item.get("id_unico"))
            if gravado:
                horario_bd, processado_final, postagem_final, msg_post_final, repost_pub, data_repost_pub = gravado
            else:
                horario_bd, processado_final, postagem_final = "", (1 if item.get("processado") else 0), item.get("data_postagem", "")
                msg_post_final = item.get("msg_postada_id")
                repost_pub, data_repost_pub = 0, None

            horario_final = item.get("horario_disparo") or horario_bd or ""

            cursor.execute('''
                INSERT INTO fila_autorais (id_unico, msg_id_destino, legenda, caminho_arquivo, data_captura, data_alvo, horario_disparo, processado, data_postagem, msg_postada_id, autor_id, autor_username, repostado_publico, data_repost_publico, chaves_video)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item.get("id_unico"),
                item.get("msg_id_destino"),
                item.get("legenda"),
                item.get("caminho_arquivo"),
                item.get("data_captura"),
                item.get("data_alvo"),
                horario_final,
                processado_final,
                postagem_final,
                msg_post_final,
                item.get("autor_id"),
                item.get("autor_username") or "",
                repost_pub or 0,
                data_repost_pub,
                item.get("chaves_video") or ""
            ))
        conexao.commit()
        conexao.close()
    except Exception as e:
        logger.error(f"❌ Erro ao salvar fila_autorais no SQLite: {e}")
    finally:
        if conexao is not None:
            try: conexao.close()
            except Exception: pass

def ler_fila_publico():
    """Fila do Grupo Público (tabela fila_publico), no mesmo formato de ler_fila_retorno()."""
    try:
        conexao = db.conectar()
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
        # Colunas novas (caminho_arquivo guarda o vídeo baixado pelo Correio Público).
        # O bot_mestre também as cria, mas os serviços sobem em qualquer ordem.
        try:
            cursor.execute("ALTER TABLE fila_publico ADD COLUMN msg_postada_id INTEGER")
            conexao.commit()
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE fila_publico ADD COLUMN caminho_arquivo TEXT")
            conexao.commit()
        except sqlite3.OperationalError:
            pass

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
                "data_postagem": linha["data_postagem"],
                "caminho_arquivo": dict(linha).get("caminho_arquivo") or "",
                "msg_postada_id": dict(linha).get("msg_postada_id")
            })
        return {"fila": fila}
    except Exception as e:
        logger.error(f"❌ Erro ao ler fila_publico do SQLite: {e}")
        return {"fila": []}

# --- Entrada automática nos canais dos parceiros ---
# Uma por ciclo, com intervalo longo: entrar em vários canais seguidos é o
# padrão que o Telegram pune, e a conta do userbot é a peça mais crítica do sistema.
INTERVALO_ENTRADA_PARCEIROS = 900   # 15 min entre uma entrada e outra
INTERVALO_RECONFERIR_PARCEIROS = 6 * 3600   # de quanto em quanto a conta é reconferida nos canais

def ler_parceiros_pendentes():
    """Parceiros ativos cujo canal de origem o userbot ainda não acessa."""
    try:
        conexao = db.conectar()
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
    """Grava em parceiros se o userbot acessa o canal de origem (origem_ok) e, se não, o motivo."""
    try:
        conexao = db.conectar()
        cursor = conexao.cursor()
        cursor.execute("UPDATE parceiros SET origem_ok = ?, origem_erro = ? WHERE id = ?",
                       (int(status), str(motivo)[:200], int(parceiro_id)))
        conexao.commit()
        conexao.close()
    except Exception as e:
        logger.error(f"❌ [Parceiros] Erro ao marcar origem: {e}")

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
    if not alvo or client is None:
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
        logger.error(f"❌ [Parceiros] Falha ao varrer diálogos: {e}")

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

def e_membro(entidade):
    """
    A conta está dentro do canal ou grupo. Achar o canal não basta: um @ público
    qualquer conta acha, mas o Telegram só entrega as mensagens novas a quem é
    membro. Fora dele, o Telegram devolve o canal com left=True.
    """
    return entidade is not None and not getattr(entidade, "left", False)

async def entrar_no_canal_parceiro(alvo):
    """
    Devolve (sucesso, motivo). Se a conta da captura já é membro, qualquer formato
    serve, inclusive ID numérico. Quando ela NÃO é membro, o Telegram exige
    @username ou link de convite para a entrada automática.
    """
    alvo = str(alvo or "").strip()
    if not alvo:
        return False, "origem vazia"

    try:
        entidade = await resolver_entidade(alvo)
        if e_membro(entidade):
            return True, "a conta da captura já é membro"

        if "+" in alvo or "joinchat" in alvo:
            hash_convite = alvo.split("+")[-1].split("/")[-1]
            await client(functions.messages.ImportChatInviteRequest(hash_convite))
            return True, "entrou pelo link de convite"

        if alvo.startswith("@") or ("t.me/" in alvo and "+" not in alvo):
            usuario = alvo.split("t.me/")[-1].replace("@", "").strip("/")
            await client(functions.channels.JoinChannelRequest(usuario))
            return True, "entrou pelo @username"

        return False, ("a conta da captura não é membro e ID numérico não permite entrada "
                       "automática: adicione a conta no canal ou use @username / link de convite")

    except UserAlreadyParticipantError:
        return True, "já era membro"
    except InviteHashExpiredError:
        return False, "link de convite expirado"
    except FloodWaitError as e:
        return False, f"Telegram pediu espera de {e.seconds}s (limite anti-spam)"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

# --- Diagnóstico da captura dos parceiros ---
# Conta, por parceiro e por dia, o que chega do canal de origem e o que acontece com
# cada vídeo. Sem isso, uma captura parada não diz se o canal parou de postar, se a
# conta não recebe o canal ou se o vídeo foi recusado (e por quê). Vai para o banco
# (chave diagnostico_parceiros) a cada 5 min e aparece na fila do parceiro no bot_mestre.
CHAVE_DIAGNOSTICO_PARCEIROS = "diagnostico_parceiros"
INTERVALO_GRAVAR_DIAGNOSTICO = 300
_diagnostico_parceiros = {}
_diagnostico_gravado_em = 0.0
_origens_parceiros = {"ids": {}, "quando": None}   # id curto da origem -> id do parceiro

def ler_parceiros_ativos():
    try:
        conexao = db.conectar()
        conexao.row_factory = sqlite3.Row
        try:
            dados = [dict(l) for l in conexao.execute("SELECT * FROM parceiros WHERE ativo = 1").fetchall()]
        except sqlite3.OperationalError:
            dados = []
        conexao.close()
        return dados
    except Exception:
        return []

async def parceiro_da_origem(chat_id):
    """Id do parceiro cujo canal de origem é este chat, ou None. Refaz o mapa a cada 10 min."""
    agora = time.monotonic()
    if _origens_parceiros["quando"] is None or agora - _origens_parceiros["quando"] >= 600:
        ids = {}
        for p in ler_parceiros_ativos():
            try:
                id_origem = await id_do_canal_origem(p.get("canal_origem"))
            except Exception:
                id_origem = None
            if id_origem:
                ids[id_origem] = p.get("id")
        _origens_parceiros.update(ids=ids, quando=agora)
    return _origens_parceiros["ids"].get(_id_curto(chat_id))

def _diagnostico_do_dia(parceiro_id):
    """Contadores de hoje do parceiro; ao subir, continua de onde o banco parou."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    chave = str(parceiro_id)
    atual = _diagnostico_parceiros.get(chave)
    if atual is None:
        atual = (db.ler_config(CHAVE_DIAGNOSTICO_PARCEIROS, {}) or {}).get(chave)
    if not atual or atual.get("data") != hoje:
        atual = {"data": hoje, "mensagens": 0, "videos": 0, "com_link": 0, "capturados": 0,
                 "recusados": {}, "ultima_mensagem": (atual or {}).get("ultima_mensagem")}
    _diagnostico_parceiros[chave] = atual
    return atual

def anotar_parceiro(parceiro_id, campo, motivo=None):
    """Soma 1 no contador do dia (campo) ou no motivo de recusa (campo="recusado")."""
    global _diagnostico_gravado_em
    if not parceiro_id:
        return
    try:
        dia = _diagnostico_do_dia(parceiro_id)
        if campo == "recusado":
            dia["recusados"][motivo] = dia["recusados"].get(motivo, 0) + 1
        else:
            dia[campo] = dia.get(campo, 0) + 1
        if campo == "mensagens":
            dia["ultima_mensagem"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if time.monotonic() - _diagnostico_gravado_em >= INTERVALO_GRAVAR_DIAGNOSTICO or campo == "capturados":
            _diagnostico_gravado_em = time.monotonic()
            copia = {k: dict(v, recusados=dict(v["recusados"])) for k, v in _diagnostico_parceiros.items()}
            db.atualizar_config(CHAVE_DIAGNOSTICO_PARCEIROS, lambda dados: dados.update(copia))
    except Exception as e:
        logger.warning(f"⚠️ [Parceiros] Falha no diagnóstico: {e}")

# --- Captura por parceiro ---
# Roda no mesmo evento do userbot, antes do fluxo do dono. Vídeo ou produto que o
# dono já reservou (no sorteio do Grupo Público) fica de fora. Se o canal do
# parceiro for a própria origem do dono, o parceiro passa na frente: a reserva do
# dono para aquele vídeo só acontece mais adiante no mesmo evento.
def ler_parceiros_ativos_com_acesso():
    try:
        conexao = db.conectar()
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
            data_postagem TEXT DEFAULT '',
            link_post_origem TEXT DEFAULT '',
            msg_postada_id INTEGER,
            nome_produto TEXT DEFAULT ''
        )
    ''')
    # Colunas que a tabela antiga não tinha: o link do post de origem (no Telegram,
    # não o da Shopee), a mensagem publicada no destino e o nome do produto.
    for coluna in ("link_post_origem TEXT DEFAULT ''", "msg_postada_id INTEGER", "nome_produto TEXT DEFAULT ''"):
        try:
            cursor.execute(f"ALTER TABLE fila_parceiros ADD COLUMN {coluna}")
        except sqlite3.OperationalError:
            pass  # coluna já existe

def link_do_post(chat, msg_id):
    """Link da mensagem no Telegram: t.me/<@>/<id> se o canal tem @, t.me/c/<id>/<id> se não."""
    if not chat or not msg_id:
        return ""
    if getattr(chat, "username", None):
        return f"https://t.me/{chat.username}/{msg_id}"
    id_interno = _id_curto(getattr(chat, "id", None))
    return f"https://t.me/c/{id_interno}/{msg_id}" if id_interno else ""

def contar_fila_parceiro(parceiro_id, data_alvo):
    try:
        conexao = db.conectar()
        cursor = conexao.cursor()
        _garantir_fila_parceiros(cursor)
        cursor.execute("SELECT COUNT(*) FROM fila_parceiros WHERE parceiro_id = ? AND data_alvo = ? AND processado = 0",
                       (int(parceiro_id), data_alvo))
        total = cursor.fetchone()[0]
        conexao.close()
        return total
    except Exception:
        return 0

def inserir_fila_parceiro(parceiro_id, caminho, link, data_alvo, link_post=""):
    try:
        conexao = db.conectar()
        cursor = conexao.cursor()
        _garantir_fila_parceiros(cursor)
        id_unico = f"p{parceiro_id}_{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}"
        cursor.execute(
            "INSERT INTO fila_parceiros (id_unico, parceiro_id, caminho_video, link_original, data_captura, "
            "data_alvo, link_post_origem) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (id_unico, int(parceiro_id), caminho, link, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), data_alvo,
             link_post or "")
        )
        conexao.commit()
        conexao.close()
        return id_unico
    except Exception as e:
        logger.error(f"❌ [Parceiros] Erro ao inserir na fila: {e}")
        return None

async def capturar_para_parceiros(event, chat_id, link_capturado, parceiro_origem=None, link_post=""):
    """
    Chamada em toda mensagem com vídeo e link da Shopee. Se o chat é o canal de
    origem de um parceiro com acesso, baixa o vídeo para a pasta dele e o agenda
    para o D+X do parceiro. Vídeo ou produto já reservado fica de fora, e cada
    vídeo vai para um parceiro só.
    """
    # Cada saída antecipada registra o motivo no log: sem isso, uma fila de
    # parceiro parada em zero não diz onde o fluxo parou.
    parceiros = ler_parceiros_ativos_com_acesso()
    if not parceiros:
        logger.info("👥 [Parceiros] Vídeo visto, mas nenhum parceiro ativo com acesso liberado.")
        anotar_parceiro(parceiro_origem, "recusado", "acesso à origem não confirmado")
        return

    try:
        doc_id = event.media.document.id
    except Exception:
        doc_id = None
    chaves = [f"doc_{doc_id}" if doc_id else None, await chave_produto_resolvida(link_capturado)]

    # Já reservado (pelo dono ou por outro parceiro): não é de mais ninguém.
    if video_ja_reservado(chaves):
        logger.info(f"👥 [Parceiros] Vídeo já reservado por outro. Chat {chat_id}.")
        anotar_parceiro(parceiro_origem, "recusado", "vídeo ou produto já reservado")
        return

    logger.info(f"👥 [Parceiros] Vídeo com link no chat {_id_curto(chat_id)} — "
                f"conferindo {len(parceiros)} parceiro(s) com acesso.")

    for p in parceiros:
        try:
            origem = str(p.get("canal_origem") or "")
            id_origem = await id_do_canal_origem(origem)
            if not id_origem or id_origem != _id_curto(chat_id):
                logger.info(f"👥 [Parceiro {p.get('nome')}] Origem '{origem}' resolve para "
                            f"{id_origem or 'NADA'}, e o vídeo veio de {_id_curto(chat_id)}. Ignorado.")
                continue

            logger.info(f"👥 [Parceiro {p.get('nome')}] Origem bateu. Capturando...")

            if not ha_espaco_para_parceiros():
                anotar_parceiro(p.get("id"), "recusado", "teto de disco dos parceiros")
                return

            dias = int(p.get("dias_atraso", 30))
            data_alvo = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")

            # O limite diário do parceiro não corta aqui: captura tudo, e o bot_mestre
            # escolhe na publicação o que vai ao ar. Na captura, o único freio é o
            # teto de disco, checado acima.

            # Reserva antes de baixar: se outro parceiro pegou no mesmo instante, para aqui.
            if not reservar_video(chaves, parceiro_id=p.get("id")):
                anotar_parceiro(p.get("id"), "recusado", "vídeo ou produto já reservado")
                continue

            destino = os.path.join(pasta_do_parceiro(p.get("id")), f"{int(datetime.now().timestamp())}_{random.randint(1000,9999)}.mp4")
            await client.download_media(event.media, file=destino)

            if not os.path.exists(destino):
                logger.warning(f"⚠️ [Parceiro {p.get('nome')}] Download falhou.")
                anotar_parceiro(p.get("id"), "recusado", "download do vídeo falhou")
                continue

            inserir_fila_parceiro(p.get("id"), destino, link_capturado, data_alvo, link_post)
            anotar_parceiro(p.get("id"), "capturados")
            logger.info(f"🎯 [Parceiro {p.get('nome')}] Vídeo capturado e agendado para {data_alvo}. "
                        f"Disco: {espaco_usado_parceiros_gb():.2f} GB de {TETO_DISCO_PARCEIROS_GB} GB.")
            break   # um vídeo vai para um parceiro só

        except Exception as e:
            logger.error(f"❌ [Parceiros] Falha ao capturar para '{p.get('nome')}': {e}")

async def reconferir_parceiros_com_acesso():
    """
    Confere se a conta da captura continua dentro do canal de cada parceiro marcado
    com acesso. Saiu (ou nunca entrou: o acesso era marcado só por achar o canal)?
    Volta para pendente, e o laço tenta entrar de novo.
    """
    for p in ler_parceiros_ativos_com_acesso():
        origem = str(p.get("canal_origem") or "").strip()
        try:
            entidade = await resolver_entidade(origem)
        except Exception:
            continue   # falha de rede não é prova de que saiu
        # Um @ público que não resolveu agora é falha de rede ou @ trocado, não prova
        # de que a conta saiu: fica para a próxima. Fora dele, o @ volta com left=True.
        publico = origem.startswith("@") or ("t.me/" in origem and "+" not in origem and "joinchat" not in origem)
        if entidade is None and publico:
            continue
        if not e_membro(entidade):
            marcar_origem_parceiro(p.get("id"), 0, "a conta da captura não está no canal de origem")
            logger.warning(f"⚠️ [Parceiros] '{p.get('nome')}': a conta da captura não está no canal "
                           f"de origem. Vou tentar entrar de novo.")
        await asyncio.sleep(2)

async def loop_entrada_parceiros():
    """
    Tenta acessar o canal de origem de um parceiro pendente por ciclo, nunca em
    lote. Ao subir e a cada 6 h, reconfere os que estão marcados com acesso.
    """
    await asyncio.sleep(60)
    ultima_reconferencia = None
    while True:
        if client is None:   # captura sem conta: os canais seriam testados com ninguém
            await asyncio.sleep(60)
            continue
        try:
            if ultima_reconferencia is None or time.monotonic() - ultima_reconferencia >= INTERVALO_RECONFERIR_PARCEIROS:
                ultima_reconferencia = time.monotonic()
                await reconferir_parceiros_com_acesso()
            pendentes = ler_parceiros_pendentes()
            if pendentes:
                p = pendentes[0]
                logger.info(f"👥 [Parceiros] Tentando acessar a origem de '{p.get('nome')}'...")
                ok, motivo = await entrar_no_canal_parceiro(p.get("canal_origem"))
                marcar_origem_parceiro(p.get("id"), 1 if ok else 0, motivo)
                icone = "✅" if ok else "⚠️"
                logger.info(f"{icone} [Parceiros] '{p.get('nome')}': {motivo}")
        except Exception as e:
            logger.error(f"❌ [Parceiros] Falha no loop de entrada: {e}")

        await asyncio.sleep(INTERVALO_ENTRADA_PARCEIROS)

# --- Armazenamento dos vídeos dos parceiros ---
# Os arquivos ficam em disco até a data de publicação (D+X do parceiro).
# Teto rígido: estourou, novas capturas são recusadas, em vez de encher o disco
# e derrubar o sistema inteiro (Espião, Autorais e o SQLite junto).
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
    if not link:
        return None
    alvo = str(link).split("?")[0].strip().lower()
    # Formato longo: /product/<loja>/<item> ou /<nome>-i.<loja>.<item>
    m = re.search(r'/product/(\d+)/(\d+)', alvo) or re.search(r'-i\.(\d+)\.(\d+)', alvo)
    if m:
        return f"prod_{m.group(1)}_{m.group(2)}"
    # Link curto: usa o código dele como identidade
    codigo = codigo_do_link_curto(alvo)
    return f"curto_{codigo}" if codigo else None

# Validade do cache de encurtadores. O par código → produto não muda, mas guardar
# para sempre acumula campanha velha: link de um ano atrás dificilmente volta.
DIAS_VALIDADE_CACHE_LINKS = 365

def _garantir_tabela_links(cursor):
    # Tabela no formato antigo (URL inteira em url_final, sem chave_final) é
    # apagada e recriada: é só cache, cada link se resolve de novo quando voltar.
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
    Descobre qual produto está por trás de um link curto da Shopee.

    Dois afiliados que divulgam o mesmo item geram encurtadores diferentes, e a
    chave sairia `curto_AbCd123` contra `curto_XyZw789`: duas identidades para um
    produto só, que a trava anti-duplicata deixaria passar. Abrindo o link, os dois
    viram o mesmo `prod_loja_item`.

    Guarda só a chave, não a URL. O cache vale DIAS_VALIDADE_CACHE_LINKS dias; o
    que vence é apagado na próxima gravação. Link que abriu mas não tinha produto
    também é guardado (vazio), para não consultar de novo; falha de rede não é
    guardada, para tentar outra vez depois.
    """
    codigo = codigo_do_link_curto(link)
    if not codigo:
        return None
    limite_validade = (datetime.now() - timedelta(days=DIAS_VALIDADE_CACHE_LINKS)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        conexao = db.conectar()
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
            return linha[0] or None   # vazio = já foi aberto e não tinha produto
    except Exception as e:
        logger.error(f"❌ [Link Curto] Erro ao ler o cache: {e}")

    try:
        tempo = aiohttp.ClientTimeout(total=8)
        cabecalhos = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile"}
        async with aiohttp.ClientSession(timeout=tempo, headers=cabecalhos) as sessao:
            async with sessao.get(str(link), allow_redirects=True) as resposta:
                url_final = str(resposta.url)
    except Exception as e:
        logger.warning(f"⚠️ [Link Curto] Não resolveu {codigo}, tentará de novo depois: {e}")
        return None

    chave_final = chave_produto(url_final) or ""
    if chave_final.startswith("curto_"):
        chave_final = ""   # o destino também era curto: não serve de identidade

    try:
        conexao = db.conectar()
        cursor = conexao.cursor()
        _garantir_tabela_links(cursor)
        cursor.execute(
            "INSERT OR REPLACE INTO links_resolvidos (codigo_curto, chave_final, data_resolucao) VALUES (?, ?, ?)",
            (codigo, chave_final, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        # Aproveita a gravação para apagar o que venceu. Só roda quando aparece
        # encurtador novo, e a tabela é pequena.
        cursor.execute("DELETE FROM links_resolvidos WHERE data_resolucao < ?", (limite_validade,))
        vencidos = cursor.rowcount
        conexao.commit()
        conexao.close()
        if vencidos:
            logger.info(f"🧹 [Link Curto] {vencidos} link(s) fora do prazo de {DIAS_VALIDADE_CACHE_LINKS} dias removido(s).")
    except Exception as e:
        logger.error(f"❌ [Link Curto] Erro ao gravar o cache: {e}")

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
        conexao = db.conectar()
        cursor = conexao.cursor()
        _garantir_tabela_reservas(cursor)
        marcadores = ",".join("?" * len(chaves))
        cursor.execute(f"SELECT 1 FROM videos_reservados WHERE video_id IN ({marcadores}) LIMIT 1", chaves)
        achou = cursor.fetchone() is not None
        conexao.close()
        return achou
    except Exception as e:
        logger.error(f"❌ [Reserva] Erro ao consultar: {e}")
        return True   # na dúvida, não arrisca duplicar

def reservar_video(chaves, parceiro_id=0):
    """
    Reserva o vídeo por arquivo (doc_<id>) e por produto, para o mesmo item não
    sair duas vezes nem com vídeos diferentes. parceiro_id 0 = dono. Devolve True
    se reservou alguma chave nova.
    """
    if not isinstance(chaves, (list, tuple)):
        chaves = [chaves]
    chaves = [str(c) for c in chaves if c]
    if not chaves:
        return False
    try:
        conexao = db.conectar()
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
        logger.error(f"❌ [Reserva] Erro ao reservar {chaves}: {e}")
        return False

def salvar_fila_publico(dados):
    """
    Regrava a tabela fila_publico a partir de dados (DELETE + INSERT).

    O bot_mestre e o Correio gravam horario_disparo, processado, data_postagem,
    caminho_arquivo e msg_postada_id nas mesmas linhas, de outro processo. Para quem
    já está no banco esses campos são relidos aqui e mantidos; regravar a partir de
    um retrato antigo devolveria o vídeo a "pendente" (seria publicado de novo).
    """
    # Mesma transação longa de salvar_fila_retorno: fecha no finally.
    conexao = None
    try:
        conexao = db.conectar()
        cursor = conexao.cursor()

        status_atual = {}
        try:
            cursor.execute("SELECT id_unico, horario_disparo, processado, data_postagem, caminho_arquivo, msg_postada_id FROM fila_publico")
            for linha in cursor.fetchall():
                status_atual[linha[0]] = linha[1:]
        except Exception:
            pass

        cursor.execute("DELETE FROM fila_publico")
        for item in dados.get("fila", []):
            gravado = status_atual.get(item.get("id_unico"))
            if gravado:
                horario_final, processado_final, postagem_final, caminho_final, msg_post_final = gravado
            else:
                horario_final = item.get("horario_disparo", "")
                processado_final = 1 if item.get("processado") else 0
                postagem_final = item.get("data_postagem", "")
                msg_post_final = item.get("msg_postada_id")
                caminho_final = item.get("caminho_arquivo", "")
            cursor.execute('''
                INSERT INTO fila_publico (id_unico, msg_id_destino, legenda, data_captura, data_alvo, horario_disparo, processado, data_postagem, caminho_arquivo, msg_postada_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item.get("id_unico"),
                item.get("msg_id_destino"),
                item.get("legenda"),
                item.get("data_captura"),
                item.get("data_alvo"),
                horario_final,
                processado_final,
                postagem_final,
                caminho_final,
                msg_post_final
            ))
        conexao.commit()
        conexao.close()
    except Exception as e:
        logger.error(f"❌ Erro ao salvar fila_publico no SQLite: {e}")
    finally:
        if conexao is not None:
            try: conexao.close()
            except Exception: pass

def contar_ofertas_dia_publico(data_alvo, incrementar=True):
    """Contador do sorteio do Grupo Público: o mesmo que contar_ofertas_dia(), com tabela própria."""
    try:
        conexao = db.conectar()
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
        logger.error(f"❌ Erro no contador de sorteio do Público: {e}")
        return 0

def contar_ofertas_dia(data_alvo, incrementar=True):
    """
    Contador do sorteio dos autorais: quantos vídeos a origem já ofereceu para a
    data_alvo (incrementa e devolve). É o total que dá a cada vídeo do dia a mesma
    chance, limite/total.
    """
    try:
        conexao = db.conectar()
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

            # Contador de data com mais de 90 dias não serve mais.
            limite_faxina = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
            cursor.execute("DELETE FROM contador_autorais WHERE data_alvo < ?", (limite_faxina,))
            conexao.commit()

        cursor.execute("SELECT total FROM contador_autorais WHERE data_alvo = ?", (data_alvo,))
        linha = cursor.fetchone()
        conexao.close()
        return linha[0] if linha else 0
    except Exception as e:
        logger.error(f"❌ Erro no contador de sorteio: {e}")
        return 0

async def gerar_legenda_autoral(caminho_video):
    """Pede à IA o nome do produto com o emoji no fim (linha 1) e as hashtags de categoria (linha 2)."""
    return await analisar_video_gemini(caminho_video, legendas.PROMPT_NOME_E_HASHTAGS)

from utils import salvar_nome_grupo

DIAS_REGISTRO_MENSAGENS_ORIGEM = 30

def mensagem_ja_processada(chat_id, msg_id):
    """
    Registra a mensagem (chat, id) da origem e devolve True se ela já estava registrada.

    A origem chega por dois caminhos: o evento NewMessage e a varredura_origem_loop.
    Sem este registro, a mesma mensagem vinda pelos dois seria publicada duas vezes
    no canal e entraria duas vezes na fila. Fica no banco, então vale depois de
    reiniciar. Sem msg_id ou com erro no banco devolve False (a mensagem é processada).
    """
    if msg_id is None:
        return False
    chave = f"{_id_curto(chat_id)}:{msg_id}"
    agora_txt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # A varredura só olha as últimas mensagens da origem; registro mais velho não serve.
    limite = (datetime.now() - timedelta(days=DIAS_REGISTRO_MENSAGENS_ORIGEM)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conexao = db.conectar()
        cursor = conexao.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS mensagens_origem_autorais (chave TEXT PRIMARY KEY, data_registro TEXT)")
        cursor.execute("INSERT OR IGNORE INTO mensagens_origem_autorais (chave, data_registro) VALUES (?, ?)", (chave, agora_txt))
        ja_registrada = cursor.rowcount == 0
        cursor.execute("DELETE FROM mensagens_origem_autorais WHERE data_registro < ?", (limite,))
        conexao.commit()
        conexao.close()
        return ja_registrada
    except Exception as e:
        logger.error(f"❌ Erro ao consultar o registro de mensagens da origem: {e}")
        return False

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

# incoming=True: sem ele o Telethon entrega também as mensagens que esta conta envia.
# O retorno autoral publica no grupo de ORIGEM, e cada retorno seria recapturado e
# republicado como vídeo novo.
async def interceptar_e_espelhar(event):
    # Repete o incoming=True: a varredura chama este handler direto, sem o filtro do evento.
    if getattr(event, "out", False):
        return

    parceiro_origem = await parceiro_da_origem(getattr(event, "chat_id", None))
    anotar_parceiro(parceiro_origem, "mensagens")

    # Lista negra global. O 'out' acima só cobre a conta desta sessão. Com o pool de
    # contas, espelho e repostagem podem ser contas diferentes: o retorno publicado
    # pela outra conta chega aqui como mensagem de terceiro e seria recapturado em laço.
    if blacklist_captura.deve_ignorar(getattr(event, "sender_id", None),
                                      contexto=blacklist_captura.ESCOPO_GLOBAL):
        logger.info(f"🚫 [Lista Negra] Ignorado: autor {getattr(event, 'sender_id', '?')} "
                    f"é uma conta própria ou está bloqueado globalmente.")
        anotar_parceiro(parceiro_origem, "recusado", "autor na lista negra")
        return

    config_atual = carregar_config_autorais()
    
    if config_atual.get("pausar_robo_completo", False):
        anotar_parceiro(parceiro_origem, "recusado", "robô dos Autorais pausado")
        return
        
    chat = await event.get_chat()
    
    # Nome do chat no cache que o painel usa para mostrar nomes.
    if chat and hasattr(chat, 'title'):
        salvar_nome_grupo(str(chat.id), chat.title)
    
    origem_configurada, topico_embutido = separar_alvo_e_topico(config_atual.get('origem'))
    topico_configurado = config_atual.get('origem_topico')

    # Tópico colado no ID ("-100123:5") tem prioridade sobre a chave origem_topico.
    if topico_embutido is not None:
        topico_configurado = topico_embutido
    if isinstance(topico_configurado, str) and topico_configurado.strip().isdigit():
        topico_configurado = int(topico_configurado.strip())

    eh_origem = False

    if isinstance(origem_configurada, int):
        # Compara só o número, sem o -100 e o sinal.
        num_config = str(origem_configurada).replace("-100", "").lstrip("-")
        num_evento = str(getattr(event, 'chat_id', "") or "").replace("-100", "").lstrip("-")
        if num_config and num_config == num_evento:
            eh_origem = True
    elif isinstance(origem_configurada, str):
        username_chat = getattr(chat, 'username', None)
        if username_chat and username_chat.lower() == origem_configurada.lstrip('@').lower():
            eh_origem = True

    # Com tópico configurado, só vale mensagem desse tópico (None = o grupo todo).
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

    # Parceiros: cada um vigia o próprio canal de origem, que quase nunca é a origem
    # do dono. Por isso esta chamada vem antes do corte de eh_origem.
    if isinstance(getattr(event, 'media', None), MessageMediaDocument):
        anotar_parceiro(parceiro_origem, "videos")
        link_parceiro = extrair_link_shopee(event)
        if link_parceiro:
            anotar_parceiro(parceiro_origem, "com_link")
            try:
                await capturar_para_parceiros(event, getattr(chat, 'id', None), link_parceiro, parceiro_origem,
                                              link_do_post(chat, getattr(event, 'id', None)))
            except Exception as e:
                logger.error(f"❌ [Parceiros] Erro na captura paralela: {e}")
        else:
            anotar_parceiro(parceiro_origem, "recusado", "vídeo sem link da Shopee")

    if not eh_origem:
        return

    # Lista negra do grupo dos autorais. Fica ANTES do sorteio de propósito: vídeo de
    # autor bloqueado nem disputa vaga (se disputasse, poderia tirar da fila um vídeo
    # bom, o item_descartado). Não mover para depois do sorteio.
    # O autor identificado aqui também é gravado no item da fila.
    try:
        autor_evento = await event.get_sender()
    except Exception:
        autor_evento = None
    autor_id_evento = getattr(autor_evento, "id", None) or getattr(event, "sender_id", None)
    autor_user_evento = getattr(autor_evento, "username", None)

    if blacklist_captura.deve_ignorar(autor_id_evento, autor_user_evento):
        logger.info(f"🚫 [Lista Negra] Fora do sorteio: autor "
                    f"@{autor_user_evento or '?'} (id {autor_id_evento or '?'}) está na lista negra.")
        return

    logger.info("🔍 Nova postagem detetada no grupo/tópico de origem configurado.")

    if getattr(event, 'media', None) is None:
        return

    if isinstance(event.media, MessageMediaDocument):
        link_capturado = extrair_link_shopee(event)
        
        if not link_capturado:
            logger.info("⏭️ Postagem ignorada: Não contém link da Shopee (nem embutido).")
            return

        if mensagem_ja_processada(getattr(event, 'chat_id', None), getattr(event, 'id', None)):
            logger.info(f"⏭️ Mensagem {getattr(event, 'id', '?')} da origem já foi processada (evento e varredura pegaram a mesma). Ignorada.")
            return

        logger.info("🔗 A converter o link da Shopee para o seu ID de afiliado via API Central...")
        link_novo = await converter_link_shopee(link_capturado, "geral")

        logger.info("📥 Iniciando o download do vídeo...")
        caminho_video = await event.download_media(file="temp/temp_espelho_isolado_")
        # Antes de re-renderizar: o arquivo como chegou é o que se repete se a origem
        # mandar o mesmo vídeo de novo.
        try:
            doc_id_video = event.media.document.id
        except Exception:
            doc_id_video = None
        chaves_video = repetidos_publico.chaves_do_video(doc_id_video, caminho_video)
        caminho_video = await verificar_e_otimizar_video(caminho_video)
        
        if caminho_video:
            try:
                logger.info("🧠 Solicitando à IA a criação de uma nova Copy autoral...")
                texto_ia = await gerar_legenda_autoral(caminho_video)
                
                if texto_ia:
                    legenda_final = legendas.legenda_da_ia(texto_ia, link_novo)
                else:
                    legenda_final = legendas.legenda_sem_nome(link_novo)

                # O destino também pode ter tópico ("-100123:5").
                destino_final, destino_topico = separar_alvo_e_topico(config_atual.get('destino'))
                if destino_final is None:
                    raise ValueError("Destino não configurado no painel de Vídeos Autorais.")

                kwargs_envio = {}
                if destino_topico and destino_topico > 1:
                    kwargs_envio['reply_to'] = destino_topico

                # Última checagem antes de publicar: download, otimização e IA levam
                # dezenas de segundos, e a pausa pedida nesse meio-tempo precisa valer.
                if pausa_ativa("captura"):
                    logger.info("⏸️ [Captura] Pausa pedida durante o processamento. Vídeo descartado sem publicar.")
                    try: os.remove(caminho_video)
                    except Exception: pass
                    return

                try:
                    msg_enviada = await client.send_file(
                        destino_final,
                        file=caminho_video,
                        caption=legenda_final,
                        parse_mode='html',
                        **kwargs_envio
                    )
                except Exception as e:
                    registrar_atividade_captura(False, f"{type(e).__name__}: {e}")
                    raise
                registrar_atividade_captura(True)
                logger.info("🚀 Vídeo publicado no canal de destino com a nova legenda autoral!")
                
                dias_retorno = config_atual.get('dias_retorno', 15)

                agora = datetime.now()
                data_alvo = (agora + timedelta(days=dias_retorno)).strftime("%Y-%m-%d")

                # A cota do dia é sorteada dentro da faixa do painel: reservatório do mesmo
                # tamanho todo dia é assinatura de robô. O sorteio é determinístico pela
                # data-alvo (não muda no meio do dia nem ao reiniciar), e o loop de retorno
                # usa o mesmo número como teto de saída.
                piso_aut, topo_aut = faixa_de_config(config_atual, "limite_min", "limite_max", "limite_videos")
                limite_videos = sortear_teto_do_dia("autorais", data_alvo, piso_aut, topo_aut) or piso_aut or 5
                
                fila_dados = ler_fila_retorno()
                # Amostragem por reservatório: todo vídeo do dia tem a mesma chance de
                # ficar, não só os primeiros.
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
                    id_unico = f"autoral_{int(agora.timestamp())}_{random.randint(1000, 9999)}"

                    # Nome único em archive/. Reaproveitar o nome do temp/ colide: o
                    # Telethon só evita colisão dentro de temp/, e o os.rename
                    # sobrescreveria em silêncio o vídeo de outro item da fila.
                    extensao = os.path.splitext(caminho_video)[1] or ".mp4"
                    novo_caminho = f"archive/{id_unico}{extensao}"
                    os.rename(caminho_video, novo_caminho)

                    if item_descartado:
                        # Devolve a vaga: apaga o arquivo do antigo e tira ele da fila
                        caminho_antigo = item_descartado.get("caminho_arquivo")
                        if caminho_antigo and os.path.exists(caminho_antigo):
                            try: os.remove(caminho_antigo)
                            except Exception: pass
                        fila_dados["fila"] = [v for v in fila_dados.get("fila", []) if v.get("id_unico") != item_descartado.get("id_unico")]
                        logger.info(f"🔄 [Sorteio Autorais] Vídeo nº {total_ofertas} do dia tomou a vaga de {item_descartado.get('id_unico')}.")
                    
                    # "📦 Item: <nome>" é o formato que o painel e o relatório leem.
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
                        "processado": False,
                        # Autor original, para reconferir a lista negra na hora de repostar.
                        "autor_id": autor_id_evento,
                        "autor_username": autor_user_evento or "",
                        "chaves_video": json.dumps(chaves_video)
                    })
                    salvar_fila_retorno(fila_dados)
                    logger.info(f"🎯 [Sorteio Autorais] Vídeo nº {total_ofertas} do dia SORTEADO para retorno em {data_alvo}.")
                else:
                    try:
                        os.remove(caminho_video)
                        logger.info(f"🎲 [Sorteio Autorais] Vídeo nº {total_ofertas} do dia não sorteado (chance era {limite_videos}/{total_ofertas}). Removido do disco.")
                    except Exception:
                        pass

                # Sorteio do Grupo Público: independente, sobre o mesmo vídeo, com
                # contador, fila e regras próprias (submissao_config).
                try:
                    config_pub = db.ler_config("submissao_config", {})
                    ativo_pub = config_pub.get("ativo") and not config_pub.get("repost_pausado", False)
                    if ativo_pub and repetidos_publico.ja_foi(chaves_video):
                        # O mesmo vídeo de novo na origem: não volta ao Grupo Público
                        # (DECISOES.md, Grupo Público e Achadinhos).
                        logger.info("♻️ [Sorteio Público] Este vídeo já foi para o Grupo Público. Fica de fora do sorteio.")
                        ativo_pub = False
                    if ativo_pub:
                        dias_publico = config_pub.get("repost_dias", 15)
                        data_alvo_pub = (agora + timedelta(days=dias_publico)).strftime("%Y-%m-%d")

                        # Cota sorteada como a dos autorais, com semente própria para não
                        # sair o mesmo número na mesma data.
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

                            # Mesmo formato "📦 Item:" que o painel e a repostagem leem.
                            nome_produto_pub = texto_ia.split('\n')[0].strip() if texto_ia else "Produto Exclusivo"
                            legenda_publico = f"📦 Item: {nome_produto_pub}\n\n{legenda_final}"

                            if item_descartado_pub:
                                # Devolve a vaga: o antigo sai da fila do Público, e o vídeo
                                # dele, que nunca chegou ao grupo, pode voltar a concorrer.
                                fila_pub["fila"] = [v for v in fila_pub.get("fila", []) if v.get("id_unico") != item_descartado_pub.get("id_unico")]
                                repetidos_publico.liberar(item_descartado_pub.get("id_unico"))
                                logger.info(f"🔄 [Sorteio Público] Vídeo nº {total_ofertas_pub} do dia tomou a vaga de {item_descartado_pub.get('id_unico')}.")

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
                            repetidos_publico.registrar(chaves_video, id_unico_pub)

                            # Reserva para o dono, por arquivo e por produto: parceiros
                            # consultam a reserva antes de capturar.
                            try:
                                doc_id = event.media.document.id
                            except Exception:
                                doc_id = None
                            reservar_video([f"doc_{doc_id}" if doc_id else None,
                                            await chave_produto_resolvida(link_capturado)], parceiro_id=0)

                            logger.info(f"🎯 [Sorteio Público] Vídeo nº {total_ofertas_pub} do dia SORTEADO para o Grupo Público em {data_alvo_pub}.")
                        else:
                            logger.info(f"🎲 [Sorteio Público] Vídeo nº {total_ofertas_pub} do dia não sorteado (chance era {limite_publico}/{total_ofertas_pub}).")
                except Exception as e:
                    logger.error(f"❌ [Sorteio Público] Falha no sorteio: {e}")

            except Exception as e:
                logger.error(f"❌ Falha ao tentar enviar o vídeo: {e}")
                registrar_erro_json(f"interceptar_e_espelhar: {e}", origem="espelhador_videos_autorais.py")
                
                # Fica como .pendente em temp/; a faxina do bot_mestre apaga depois.
                if os.path.exists(caminho_video):
                    try:
                        os.rename(caminho_video, caminho_video + ".pendente")
                        logger.info(f"🏷️ Ficheiro isolado para limpeza posterior: {caminho_video}.pendente")
                    except Exception:
                        pass

# Pausa do motor (teto do dia, fora da janela) já avisada no log: o aviso sai uma
# vez quando o motor para, e não a cada volta do laço (eram centenas de linhas por
# dia iguais). Volta a ser None quando o motor segue para publicar.
_pausa_avisada = None


def avisar_pausa(chave, texto):
    global _pausa_avisada
    if chave != _pausa_avisada:
        _pausa_avisada = chave
        logger.info(texto)


def fim_da_pausa():
    global _pausa_avisada
    _pausa_avisada = None


async def processar_fila_autorais_loop():
    """
    Fila de retorno D+X. A cada minuto agenda na janela do painel os vídeos com
    data-alvo hoje e devolve ao grupo de origem no máximo um por ciclo, respeitando
    pausa, janela, teto diário e as travas de idade, lista negra e arquivo trocado.
    """
    logger.info("🚀 [Motor Autorais] Loop de processamento autônomo iniciado.")
    
    while True:
        try:
            fila_dados = ler_fila_retorno()
            fila = fila_dados.get("fila", [])
            
            if not fila:
                await asyncio.sleep(60)
                continue
                
            config_atual = carregar_config_autorais()
            
            # Pausado: nada é agendado nem publicado.
            if config_atual.get("pausar_robo_completo", False) or config_atual.get("pausar_repostagem", False):
                await asyncio.sleep(60)
                continue

            agora = datetime.now()
            hoje_str = agora.strftime("%Y-%m-%d")
            
            # 1) Agenda os vídeos de hoje; apaga os que perderam o dia sem horário.
            itens_desagendados = []
            houve_limpeza = False
            
            for item in fila:
                if item.get("processado"): continue
                
                if not item.get("horario_disparo"):
                    data_alvo = item.get("data_alvo")
                    
                    # Data-alvo passou sem horário: o vídeo perde a validade e é apagado.
                    if data_alvo < hoje_str:
                        caminho_arquivo = item.get("caminho_arquivo")
                        if caminho_arquivo and os.path.exists(caminho_arquivo):
                            try: os.remove(caminho_arquivo)
                            except: pass
                        
                        try:
                            conexao = db.conectar()
                            cursor = conexao.cursor()
                            cursor.execute("DELETE FROM fila_autorais WHERE id_unico = ?", (item["id_unico"],))
                            conexao.commit()
                            conexao.close()
                            houve_limpeza = True
                            logger.info(f"🧹 [Auto-Limpeza] Vídeo Autoral retido e vencido ({data_alvo}) foi deletado para evitar avalanche.")
                        except Exception:
                            pass
                        continue
                        
                    if data_alvo == hoje_str:
                        itens_desagendados.append(item)
            
            if houve_limpeza:
                # Relê a fila sem os itens apagados.
                fila_dados = ler_fila_retorno()
                fila = fila_dados.get("fila", [])
                    
            if itens_desagendados:
                # Janela e modo do painel (Regras de Repostagem).
                inicio_janela = int(config_atual.get("inicio", 10))
                fim_janela = int(config_atual.get("fim", 20))
                modo = config_atual.get("modo", "aleatorio")
                dias_retorno_cfg = int(config_atual.get("dias_retorno", 15))
                # A data_alvo já tem o D+X aplicado na captura; intervalo 1 só faz o
                # motor espalhar os vídeos pela janela.
                intervalo_dias = 1

                config_fila = {
                    "inicio": inicio_janela,
                    "fim": fim_janela,
                    "modo": modo,
                    "intervalo_dias": intervalo_dias,
                    # Piso de segurança, não intervalo padrão: com poucos vídeos o motor
                    # divide a janela e espalha pelo dia. O piso só age em volume alto.
                    "espacamento_base_min": 15,
                    "espacamento_variacao_min": 6,
                    # O descarte por idade conta da captura: com atraso + 7, vídeo empurrado
                    # mais de uma semana além da data-alvo perde a validade.
                    "limite_dias_descarte": dias_retorno_cfg + 7
                }
                
                logger.info(f"⚙️ [Motor Autorais] Acionando Motor Central para {len(itens_desagendados)} vídeos de retorno...")
                calcular_horarios_distribuicao(itens_desagendados, config_fila, forcar=False)

                # Item que o motor marcou como velho demais sai da fila e do disco,
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
                    logger.info(f"🗑️ [Motor Autorais] {len(marcados)} vídeo(s) descartado(s) por idade.")

                salvar_fila_retorno(fila_dados)

            # 2) Publica.
            # Teto diário de saída: sem ele, uma fila com atraso acumulado sairia toda de
            # uma vez no grupo dos outros. É a mesma cota que a captura sorteou para esta
            # data (mesma semente e dia): sai no dia exatamente o que foi guardado para ele.
            piso_aut, topo_aut = faixa_de_config(config_atual, "limite_min", "limite_max", "limite_videos")
            limite_dia = sortear_teto_do_dia("autorais", hoje_str, piso_aut, topo_aut) or piso_aut or 5
            try:
                conexao_ct = db.conectar()
                ja_saiu = conexao_ct.execute(
                    "SELECT COUNT(*) FROM fila_autorais WHERE processado = 1 AND data_postagem LIKE ?",
                    (hoje_str + "%",)
                ).fetchone()[0]
                conexao_ct.close()
            except Exception:
                ja_saiu = 0

            if ja_saiu >= limite_dia:
                avisar_pausa(("teto", hoje_str),
                             f"🚦 [Motor Autorais] Teto diário atingido ({ja_saiu}/{limite_dia}). Nada mais sai hoje.")
                await asyncio.sleep(60)
                continue

            # Fora da janela nada sai, nem item atrasado de ontem nem item cuja janela
            # mudou depois do agendamento.
            janela_ini = int(config_atual.get("inicio", 0))
            janela_fim = int(config_atual.get("fim", 24))
            if not (janela_ini <= agora.hour < janela_fim):
                avisar_pausa(("janela", hoje_str, janela_ini, janela_fim),
                             f"⏰ [Motor Autorais] Fora da janela ({janela_ini}h-{janela_fim}h). "
                             f"São {agora.hour}h. Nada será publicado até as {janela_ini}h.")
                await asyncio.sleep(300)
                continue
            fim_da_pausa()

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
                    # Reconfere a pausa a cada item, não só no topo do ciclo.
                    if pausa_ativa("autorais"):
                        logger.info("⏸️ [Motor Autorais] Pausa detetada. Nenhum vídeo será publicado neste ciclo.")
                        break

                    # Trava de idade: a data_alvo pode estar errada (configuração mudada,
                    # item recapturado, fila migrada). Aqui vale a idade real: nada
                    # capturado há menos de dias_retorno volta ao grupo, para não
                    # devolver ao autor um vídeo que ele publicou esta semana.
                    dias_min = int(config_atual.get("dias_retorno", 15))
                    cap_str = item.get("data_captura", "")
                    idade_dias = None
                    cap_obj = None
                    if cap_str:
                        try:
                            cap_obj = datetime.strptime(cap_str, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            try:
                                cap_obj = datetime.strptime(cap_str.split(" ")[0], "%Y-%m-%d")
                            except Exception:
                                cap_obj = None
                        if cap_obj:
                            idade_dias = (agora - cap_obj).days

                    if idade_dias is not None and idade_dias < dias_min:
                        nova_alvo = (cap_obj + timedelta(days=dias_min)).strftime("%Y-%m-%d")
                        logger.warning(f"🛡️ [Motor Autorais] Vídeo {item.get('id_unico')} tem só {idade_dias} "
                                       f"dia(s) (mínimo {dias_min}). NÃO publicado. Reagendado para {nova_alvo}.")
                        try:
                            conexao_ag = db.conectar()
                            conexao_ag.execute(
                                "UPDATE fila_autorais SET data_alvo = ?, horario_disparo = '' WHERE id_unico = ?",
                                (nova_alvo, item.get("id_unico"))
                            )
                            conexao_ag.commit()
                            conexao_ag.close()
                        except Exception as e:
                            logger.error(f"❌ [Motor Autorais] Falha ao reagendar o vídeo novo demais: {e}")
                        break

                    caminho_arquivo = item.get("caminho_arquivo")
                    legenda = item.get("legenda")

                    # Lista negra de novo: o autor pode ter sido bloqueado depois de o
                    # vídeo entrar na fila. Item antigo, sem autor gravado, passa.
                    if item.get("autor_id") or item.get("autor_username"):
                        if blacklist_captura.deve_ignorar(item.get("autor_id"),
                                                          item.get("autor_username")):
                            logger.info(f"🚫 [Lista Negra] Item {item.get('id_unico')} descartado "
                                        f"sem publicar: autor @{item.get('autor_username') or '?'} "
                                        f"entrou na lista negra depois da captura.")
                            try:
                                if caminho_arquivo and os.path.exists(caminho_arquivo):
                                    os.remove(caminho_arquivo)
                            except Exception:
                                pass
                            conexao_bl = db.conectar()
                            conexao_bl.execute("DELETE FROM fila_autorais WHERE id_unico = ?",
                                               (item.get("id_unico"),))
                            conexao_bl.commit()
                            conexao_bl.close()
                            break

                    # O arquivo é mesmo daquele dia? Item gravado quando o nome do
                    # arquivo ainda era reciclado pode apontar para um vídeo baixado
                    # depois. Arquivo muito mais novo que a captura = original perdido;
                    # publicar devolveria ao grupo um vídeo recente.
                    if caminho_arquivo and os.path.exists(caminho_arquivo):
                        try:
                            cap_txt = (item.get("data_captura") or "")[:10]
                            cap_dia = datetime.strptime(cap_txt, "%Y-%m-%d") if cap_txt else None
                            mtime = datetime.fromtimestamp(os.path.getmtime(caminho_arquivo))
                            if cap_dia and (mtime - cap_dia).days >= 1:
                                logger.error(f"🛡️ [Motor Autorais] Vídeo {item.get('id_unico')} "
                                             f"capturado em {cap_txt}, mas o arquivo é de "
                                             f"{mtime.strftime('%d/%m')}. Nome reciclado: o original "
                                             "foi sobrescrito. Item descartado sem publicar.")
                                conexao_bd = db.conectar()
                                conexao_bd.execute("DELETE FROM fila_autorais WHERE id_unico = ?", (item.get("id_unico"),))
                                conexao_bd.commit()
                                conexao_bd.close()
                                break
                        except Exception as e:
                            logger.error(f"❌ [Motor Autorais] Falha ao auditar a idade do arquivo: {e}")
                    
                    # A origem pode ter tópico ("-100123:5"), que o Telethon não resolve
                    # como entidade.
                    origem_final, origem_topico = separar_alvo_e_topico(config_atual.get('origem'))
                    kwargs_retorno = {}
                    if origem_topico and origem_topico > 1:
                        kwargs_retorno['reply_to'] = origem_topico

                    encerrar_item = False
                    adiar_item = True   # falha comum: tenta de novo em 30 min
                    escolha = proxima_conta_repost() if origem_final is not None else None
                    if origem_final is None:
                        logger.error("❌ [Motor Autorais] Origem não configurada no painel. Vídeo mantido na fila.")
                    elif escolha is None:
                        # Sem conta de repostagem agora: o vídeo espera, sem perder o lugar.
                        adiar_item = False
                        avisar_sem_conta_repost()
                    else:
                        conta_rep, cliente_rep = escolha
                        try:
                            if os.path.exists(caminho_arquivo):
                                # O id da mensagem publicada monta o link "(Destino)" no relatório.
                                msg_publicada = await cliente_rep.send_file(
                                    origem_final,
                                    file=caminho_arquivo,
                                    caption=legenda,
                                    parse_mode='md',
                                    **kwargs_retorno
                                )
                                registrar_envio_repost(conta_rep)
                                encerrar_item = True
                                item["msg_postada_id"] = getattr(msg_publicada, "id", None)
                                # Hora real da publicação, mostrada no relatório.
                                item["data_postagem"] = agora.strftime("%Y-%m-%d %H:%M:%S")
                                logger.info(f"✅ [Motor Autorais] Vídeo de retorno {item.get('id_unico')} publicado com sucesso!")
                                
                                os.remove(caminho_arquivo)
                                logger.info("🧹 Ficheiro arquivado removido após postagem final.")
                            else:
                                # Arquivo sumiu do disco: não há o que reenviar. Sai da fila,
                                # senão fica a ser tentado de 60 em 60 segundos para sempre.
                                encerrar_item = True
                                logger.warning(f"⚠️ Ficheiro arquivado não encontrado em {caminho_arquivo}. Item encerrado.")
                        except Exception as e:
                            logger.error(f"❌ Falha no disparo de retorno: {e}")
                            # Problema da conta (expulsa, sem permissão, espera): outra conta
                            # do rodízio tenta no próximo ciclo, sem adiar o vídeo.
                            if await registrar_falha_repost(conta_rep, e):
                                adiar_item = False

                    if encerrar_item:
                        # Só marca processado se publicou de fato (ou se o arquivo sumiu).
                        item["processado"] = True
                    elif adiar_item:
                        # Falhou: adia 30 min e tenta de novo, sem segurar os seguintes.
                        item["horario_disparo"] = (agora + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")

                    # UPDATE pontual, nunca salvar_fila_retorno() aqui: ela regrava a tabela
                    # a partir do retrato lido no início do ciclo, antes do envio, e
                    # desfaria o processado (o vídeo seria publicado de novo).
                    # O vídeo já foi para o grupo: se o processado = 1 não gravar, o ciclo
                    # seguinte republica. Por isso insiste ("database is locked" é comum
                    # com vários serviços no mesmo banco).
                    marcou = False
                    for tentativa in range(1, 7):
                        try:
                            conexao_st = db.conectar()
                            cursor_st = conexao_st.cursor()
                            if encerrar_item:
                                cursor_st.execute(
                                    "UPDATE fila_autorais SET processado = 1, data_postagem = ?, msg_postada_id = ? WHERE id_unico = ?",
                                    (item.get("data_postagem", ""), item.get("msg_postada_id"), item.get("id_unico"))
                                )
                            else:
                                cursor_st.execute(
                                    "UPDATE fila_autorais SET horario_disparo = ? WHERE id_unico = ?",
                                    (item.get("horario_disparo", ""), item.get("id_unico"))
                                )
                            conexao_st.commit()
                            conexao_st.close()
                            marcou = True
                            break
                        except Exception as e:
                            logger.warning(f"⏳ [Motor Autorais] Tentativa {tentativa}/6 de gravar o status "
                                           f"de {item.get('id_unico')} falhou: {e}")
                            await asyncio.sleep(2 * tentativa)

                    if not marcou and encerrar_item:
                        # Publicado e não registrado: dormir 10 min é mais seguro que republicar.
                        logger.error(f"🛑 [Motor Autorais] {item.get('id_unico')} foi PUBLICADO mas não foi "
                                     "possível marcar no banco. Loop pausado 10 min para não republicar.")
                        await asyncio.sleep(600)

                    # Um vídeo por ciclo: espaça os posts e deixa a pausa valer entre um e outro.
                    break

                itens_restantes.append(item)
                
            # Sem salvar a fila inteira no fim: o status de cada vídeo já foi gravado com
            # UPDATE logo depois do envio, e regravar a partir do retrato o desfaria.

        except Exception as e:
            logger.error(f"❌ Erro no loop de postagem de autorais: {e}")
            
        await asyncio.sleep(60)

# --- Correio do Grupo Público: o userbot baixa, quem publica é o bot ---
#
# O canal onde os autorais são publicados não é nosso: o bot não pode entrar lá e o
# copy_message dele devolve "chat not found". Esta conta tem acesso, mas publicar
# direto no grupo assinaria o post com um perfil pessoal — e o tópico do mural é
# fechado, o que ainda exigiria dar admin à conta.
#
# Então o userbot não publica nada: ele só faz a ponte. Baixa o arquivo para o disco e
# anota o caminho na fila. O bot_mestre publica a partir do arquivo e credita o perfil
# na legenda, como já faz com os vídeos dos parceiros.
HORAS_ANTECEDENCIA_PUBLICO = 3   # baixa o vídeo com esta folga antes do horário dele

# Teto de upload da Bot API. Quem publica é o bot, e acima disso o send_video dele é
# recusado. Como o item nunca conseguiria sair, não vale nem gastar banda baixando: ele
# é descartado aqui, antes do download.
LIMITE_UPLOAD_BOT_MB = 50


async def processar_fila_publico_loop():
    """
    Um item por ciclo: baixa o vídeo de cada item da fila_publico com horário
    marcado até HORAS_ANTECEDENCIA_PUBLICO à frente e grava o caminho no item.
    """
    logger.info("📬 [Correio Público] Loop de preparo dos vídeos do Grupo Público iniciado.")
    ja_auditou = None   # cliente já auditado (a conta da captura pode mudar)

    while True:
        if client is None:   # a captura está sem conta: é ela que lê o canal de destino
            await asyncio.sleep(60)
            continue
        try:
            config = db.ler_config("submissao_config", {})

            if not config.get("ativo") or config.get("repost_pausado", False):
                await asyncio.sleep(120)
                continue

            # Origem: o canal onde o vídeo autoral foi publicado (repost_origem ou o destino dos autorais).
            origem_final, _ = separar_alvo_e_topico(
                config.get("repost_origem") or carregar_config_autorais().get("destino")
            )
            if origem_final is None:
                await asyncio.sleep(120)
                continue

            # Confere uma vez por execução o acesso à origem: sem ele nada é baixado, e é
            # melhor dizer isso uma vez no log do que falhar em silêncio para sempre.
            if ja_auditou is not client:
                ja_auditou = client
                try:
                    entidade = await client.get_entity(origem_final)
                    logger.info(f"✅ [Correio Público] Acesso à origem OK: {getattr(entidade, 'title', origem_final)}")
                except Exception as err:
                    logger.error(f"❌ [Correio Público] SEM acesso à origem ({origem_final}): {err}")

            agora = datetime.now()
            # Sem janela de horário aqui: baixar de madrugada não incomoda ninguém, e
            # quanto antes o arquivo estiver no disco, mais certo o bot publica no horário.
            limite = (agora + timedelta(hours=HORAS_ANTECEDENCIA_PUBLICO)).strftime("%Y-%m-%d %H:%M:%S")

            # UPDATE pontual, nunca salvar_fila_publico(): aquela função apaga a tabela
            # e reinsere tudo, e o bot_mestre escreve os horários na MESMA fila.
            conexao = db.conectar()
            conexao.row_factory = sqlite3.Row
            cursor = conexao.cursor()
            cursor.execute('''
                SELECT * FROM fila_publico
                WHERE processado = 0
                AND horario_disparo IS NOT NULL
                AND horario_disparo != ''
                AND horario_disparo <= ?
                AND (caminho_arquivo IS NULL OR caminho_arquivo = '')
                ORDER BY horario_disparo ASC LIMIT 1
            ''', (limite,))
            alvo = cursor.fetchone()

            if not alvo:
                conexao.close()
                await asyncio.sleep(60)
                continue

            id_unico = alvo["id_unico"]
            msg_id = alvo["msg_id_destino"]

            try:
                if not msg_id:
                    raise ValueError("item sem msg_id_destino")

                msg_origem = await client.get_messages(origem_final, ids=int(msg_id))
                if not msg_origem or not getattr(msg_origem, "media", None):
                    # Mensagem apagada na origem: não há o que baixar e nunca mais vai
                    # haver. Sai da fila, senão fica a ser tentada para sempre.
                    cursor.execute("DELETE FROM fila_publico WHERE id_unico = ?", (id_unico,))
                    conexao.commit()
                    conexao.close()
                    logger.warning(f"🧹 [Correio Público] Mensagem {msg_id} sumiu da origem. Item {id_unico} removido da fila.")
                    await asyncio.sleep(30)
                    continue

                # Grande demais para o bot publicar: sai da fila agora. Sem isto ele
                # seria baixado, recusado no envio, adiado 30 min e tentado para sempre.
                tamanho_origem = getattr(getattr(msg_origem, "file", None), "size", 0) or 0
                if tamanho_origem > LIMITE_UPLOAD_BOT_MB * 1024 * 1024:
                    cursor.execute("DELETE FROM fila_publico WHERE id_unico = ?", (id_unico,))
                    conexao.commit()
                    conexao.close()
                    logger.warning(f"🚫 [Correio Público] Vídeo {id_unico} tem "
                                   f"{tamanho_origem / (1024**2):.1f} MB, acima do teto de "
                                   f"{LIMITE_UPLOAD_BOT_MB} MB que o bot consegue enviar. Descartado.")
                    await asyncio.sleep(30)
                    continue

                # Reconfere antes de gastar banda: a pausa pode ter chegado durante
                # o minuto de espera do ciclo.
                if pausa_ativa("publico"):
                    conexao.close()
                    logger.info("⏸️ [Correio Público] Pausa detetada. Nenhum download será feito.")
                    await asyncio.sleep(60)
                    continue

                destino_arquivo = os.path.join("temp", f"publico_{id_unico}.mp4")
                caminho = await client.download_media(msg_origem, file=destino_arquivo)
                if not caminho or not os.path.exists(caminho):
                    raise ValueError("o download não gerou arquivo")

                cursor.execute(
                    "UPDATE fila_publico SET caminho_arquivo = ? WHERE id_unico = ?",
                    (caminho, id_unico)
                )
                conexao.commit()
                logger.info(f"📥 [Correio Público] Vídeo {id_unico} baixado "
                            f"({os.path.getsize(caminho) / (1024**2):.1f} MB). O bot publica no horário.")

            except FloodWaitError as e:
                # Telegram mandou esperar. Respeitar não é opcional: esta conta é a peça
                # mais frágil do sistema e uma rajada teimosa derruba ela.
                espera = int(getattr(e, "seconds", 60))
                logger.warning(f"⏳ [Correio Público] FloodWait de {espera}s.")
                conexao.close()
                await asyncio.sleep(espera + 5)
                continue

            except Exception as e:
                logger.error(f"❌ [Correio Público] Falha ao baixar o vídeo {id_unico}: {e} "
                             f"| origem={origem_final!r} msg_id={msg_id!r}")
                # Falhou: adia 30 min, senão este item segura o preparo dos seguintes.
                cursor.execute(
                    "UPDATE fila_publico SET horario_disparo = ? WHERE id_unico = ?",
                    ((agora + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"), id_unico)
                )
                conexao.commit()

            conexao.close()

        except Exception as e:
            logger.error(f"❌ [Correio Público] Erro estrutural no loop: {e}")

        await asyncio.sleep(60)

# --- Varredura da origem: captura por busca ativa ---
# Mensagem que o Telethon recupera por getDifference não passa pelo NewMessage, e o
# grupo de origem chega assim (o log mostra "Got difference for channel ..." sem
# evento nenhum). Aqui o robô pergunta de tempos em tempos o que há de novo, o que
# também recupera o que foi postado com o serviço fora do ar. Alguns minutos de
# atraso não importam numa fila que só reposta dias depois.
INTERVALO_VARREDURA_MIN = 5
LIMITE_VARREDURA = 30


class EventoSimulado:
    """Casca fina que faz uma Message parecer um evento do NewMessage.

    O handler usa só seis atributos, e a Message do Telethon tem cinco deles
    nativamente. O único que conflita é o `.message`: num evento ele aponta para a
    mensagem, mas numa Message ele é o TEXTO. Daí o redirecionamento explícito.
    """

    def __init__(self, msg):
        self._msg = msg
        self.message = msg
        self.out = bool(getattr(msg, "out", False))

    def __getattr__(self, nome):
        return getattr(self._msg, nome)


# Erro da varredura que vai para o erros_logs (e o /status): o mesmo erro repetido
# a cada volta só é gravado de novo depois de uma hora, para não empurrar os outros
# erros para fora da tabela, que guarda só os 50 mais recentes.
_ultimo_erro_varredura = {"chave": None, "quando": 0.0}


def registrar_erro_varredura(e):
    chave = f"{type(e).__name__}: {e}"
    agora = time.monotonic()
    if chave != _ultimo_erro_varredura["chave"] or agora - _ultimo_erro_varredura["quando"] >= 3600:
        _ultimo_erro_varredura.update(chave=chave, quando=agora)
        registrar_erro_json(f"varredura_origem_loop: {chave}", origem="espelhador_videos_autorais.py")


async def varredura_origem_loop():
    """
    A cada INTERVALO_VARREDURA_MIN minutos lê as últimas LIMITE_VARREDURA mensagens
    da origem e passa as novas (id acima do último visto, guardado em
    ultimo_id_varredura) para interceptar_e_espelhar.
    """
    logger.info("🔭 [Varredura] Loop de captura por busca ativa iniciado.")
    await asyncio.sleep(30)   # deixa o client assentar antes da primeira consulta

    while True:
        if client is None:   # captura sem conta
            await asyncio.sleep(60)
            continue
        try:
            config_atual = carregar_config_autorais()

            if config_atual.get("pausar_robo_completo", False):
                await asyncio.sleep(120)
                continue

            origem_final, _ = separar_alvo_e_topico(config_atual.get("origem"))
            if origem_final is None:
                await asyncio.sleep(300)
                continue

            marcadores = db.ler_config("ultimo_id_varredura", {}) or {}
            chave = str(origem_final)
            ultimo_id = int(marcadores.get(chave, 0) or 0)

            mensagens = await client.get_messages(origem_final, limit=LIMITE_VARREDURA)
            if not mensagens:
                await asyncio.sleep(INTERVALO_VARREDURA_MIN * 60)
                continue

            maior_id = max(m.id for m in mensagens if m)

            # Primeira volta: só anota o último id. Sem isso, as últimas mensagens do
            # grupo entrariam todas de uma vez.
            if ultimo_id == 0:
                marcadores[chave] = maior_id
                db.salvar_config("ultimo_id_varredura", marcadores)
                logger.info(f"🔭 [Varredura] Marco inicial gravado na origem (id {maior_id}). "
                            "A captura começa a valer da próxima mensagem.")
                await asyncio.sleep(INTERVALO_VARREDURA_MIN * 60)
                continue

            novas = sorted([m for m in mensagens if m and m.id > ultimo_id], key=lambda m: m.id)
            if novas:
                logger.info(f"🔭 [Varredura] {len(novas)} mensagem(ns) nova(s) na origem desde o id {ultimo_id}.")

            for msg in novas:
                if not getattr(msg, "media", None):
                    continue
                try:
                    # Se o evento também entregar esta mensagem, mensagem_ja_processada()
                    # garante que só um dos dois caminhos a processa.
                    await interceptar_e_espelhar(EventoSimulado(msg))
                except Exception as e:
                    logger.error(f"❌ [Varredura] Falha ao processar a mensagem {msg.id}: {e}")
                await asyncio.sleep(3)

            if maior_id > ultimo_id:
                marcadores[chave] = maior_id
                db.salvar_config("ultimo_id_varredura", marcadores)

        except FloodWaitError as e:
            espera = int(getattr(e, "seconds", 60))
            logger.warning(f"⏳ [Varredura] FloodWait de {espera}s.")
            await asyncio.sleep(espera + 5)
            continue
        except Exception as e:
            logger.error(f"❌ [Varredura] Erro estrutural no loop ({type(e).__name__}): {e}")
            registrar_erro_varredura(e)

        await asyncio.sleep(INTERVALO_VARREDURA_MIN * 60)


# --- Contas: captura e rodízio da repostagem, vindas do pool_contas ---

# Erros de envio que dizem algo sobre a CONTA, não sobre o vídeo.
ERROS_FORA_DO_GRUPO = (tg_errors.UserBannedInChannelError, tg_errors.ChannelPrivateError)
ERROS_SEM_PERMISSAO = (tg_errors.ChatWriteForbiddenError, tg_errors.ChatSendMediaForbiddenError,
                       tg_errors.ChatSendVideosForbiddenError, tg_errors.ChatRestrictedError,
                       tg_errors.ChatGuestSendForbiddenError, tg_errors.ChatAdminRequiredError)
ERROS_SESSAO = (tg_errors.AuthKeyUnregisteredError, tg_errors.SessionRevokedError,
                tg_errors.UserDeactivatedBanError, tg_errors.UserDeactivatedError)

_ultimo_aviso_sem_conta = None


def registrar_atividade_captura(ok, detalhe=""):
    """Resultado da publicação no destino, para o ✅/❌ da captura no painel."""
    if conta_captura:
        pool_contas.registrar_atividade(conta_captura["id"], pool_contas.FUNCAO_ESPELHO, ok, detalhe)


def registrar_envio_repost(conta):
    """Envio de retorno feito: a conta passa a ser a última do rodízio."""
    global _ultimo_repostador
    if conta:
        _ultimo_repostador = conta["id"]
        pool_contas.registrar_atividade(conta["id"], pool_contas.FUNCAO_REPOSTAGEM, True)


def avisar_sem_conta_repost():
    """Loga no máximo a cada 10 min que a repostagem está sem conta disponível."""
    global _ultimo_aviso_sem_conta
    agora = datetime.now()
    if _ultimo_aviso_sem_conta and (agora - _ultimo_aviso_sem_conta).total_seconds() < 600:
        return
    _ultimo_aviso_sem_conta = agora
    logger.warning("⏸️ [Motor Autorais] Nenhuma conta de repostagem disponível agora. "
                   "Os vídeos esperam na fila (a captura não reposta).")


def proxima_conta_repost():
    """
    (conta, cliente) da vez no rodízio, ou None se nenhuma estiver disponível.

    Segue a ordem do pool a partir da última que postou e pula as que estão em
    espera. No modo sessão fixa a própria conta da captura reposta (conta None).
    """
    if modo_sessao_fixa:
        return (None, client) if client is not None else None
    agora = datetime.now()
    disponiveis = [cid for cid in ordem_rodizio
                   if cid in clientes_repost and _espera_repost.get(cid, agora) <= agora]
    if not disponiveis:
        return None
    if _ultimo_repostador in ordem_rodizio:
        pos = ordem_rodizio.index(_ultimo_repostador)
        seguintes = ordem_rodizio[pos + 1:] + ordem_rodizio[:pos + 1]
        disponiveis = [cid for cid in seguintes if cid in disponiveis]
    return clientes_repost[disponiveis[0]]


async def registrar_falha_repost(conta, erro):
    """
    Registra a falha de envio da conta da repostagem e decide o que fazer com ela.

    Devolve True quando o problema é da conta (o vídeo não deve ser adiado: outra
    conta tenta no próximo ciclo). Expulsa ou sessão morta sai do rodízio na hora;
    sem permissão de postar ou em FloodWait, descansa um tempo.
    """
    if not conta:
        return False   # modo sessão fixa: mantém o comportamento de adiar 30 min
    detalhe = f"{type(erro).__name__}: {erro}"
    pool_contas.registrar_atividade(conta["id"], pool_contas.FUNCAO_REPOSTAGEM, False, detalhe)
    agora = datetime.now()

    if isinstance(erro, (FloodWaitError, tg_errors.SlowModeWaitError)):
        _espera_repost[conta["id"]] = agora + timedelta(seconds=int(getattr(erro, "seconds", 60) or 60) + 5)
        return True
    if isinstance(erro, ERROS_SEM_PERMISSAO):
        _espera_repost[conta["id"]] = agora + timedelta(hours=HORAS_ESPERA_SEM_PERMISSAO)
        logger.warning(f"🚫 [Rodízio] {conta['apelido']} sem permissão de postar na origem "
                       f"({type(erro).__name__}). Fora do rodízio por {HORAS_ESPERA_SEM_PERMISSAO} h.")
        return True

    if isinstance(erro, ERROS_FORA_DO_GRUPO):
        pool_contas.atualizar_status(conta["apelido"], status_grupo=pool_contas.STATUS_BANIDA_GRUPO,
                                     erro=detalhe)
    elif isinstance(erro, tg_errors.UserNotParticipantError):
        pool_contas.atualizar_status(conta["apelido"], status_grupo=pool_contas.STATUS_SAIU, erro=detalhe)
    elif isinstance(erro, ERROS_SESSAO):
        pool_contas.atualizar_status(conta["apelido"], status_sessao=pool_contas.SESSAO_MORTA, erro=detalhe)
    else:
        return False   # erro do vídeo ou da rede: adia o vídeo, a conta segue

    logger.error(f"🛑 [Rodízio] {conta['apelido']} perdeu acesso à origem ({type(erro).__name__}). "
                 "Saindo do rodízio.")
    pool_contas.aplicar_funcoes()
    await montar_contas()
    return True


async def _preparar_cliente(cliente):
    """Carrega as conversas: a StringSession nasce sem cache de entidades e get_entity por ID falharia."""
    try:
        await cliente.get_dialogs()
    except Exception as e:
        logger.warning(f"⚠️ [Contas] Não consegui carregar as conversas: {e}")


async def _desligar_cliente(cliente):
    try:
        cliente.remove_event_handler(interceptar_e_espelhar)
    except Exception:
        pass
    try:
        await cliente.disconnect()
    except Exception:
        pass


async def _conectar_conta(conta):
    """Cliente conectado e com o cache carregado, ou None (sessão inválida)."""
    try:
        cliente = await pool_contas.criar_cliente(conta)
    except Exception as e:
        logger.error(f"❌ [Contas] Falha ao conectar '{conta.get('apelido')}': {e}")
        return None
    if cliente is not None:
        await _preparar_cliente(cliente)
    return cliente


async def _apos_trocar_captura():
    """
    Captura nova: grava os nomes da origem e do destino no cache do painel e, se
    a conta mudou desde a última vez, manda reconferir os canais dos parceiros
    (a conta nova pode não estar neles).
    """
    config_atual = carregar_config_autorais()
    for chave in ['origem', 'destino']:
        alvo, _topico_ignorado = separar_alvo_e_topico(config_atual.get(chave))
        if alvo is None:
            continue
        try:
            entidade = await client.get_entity(alvo)
            nome_alvo = getattr(entidade, 'title', getattr(entidade, 'username', str(alvo)))
            # Com a chave sem tópico e com o valor como está gravado no painel.
            salvar_nome_grupo(str(alvo), nome_alvo)
            salvar_nome_grupo(str(config_atual.get(chave)), nome_alvo)
            logger.info(f"✅ Nome da {chave} ({nome_alvo}) extraído e salvo no cache automaticamente.")
        except Exception as err:
            logger.warning(f"⚠️ Não foi possível auditar a {chave} com a conta da captura: {err}")

    try:
        eu = await client.get_me()
        id_atual = getattr(eu, "id", None)
        logger.info(f"👤 [Captura] Conta: {getattr(eu, 'first_name', '')} "
                    f"(@{getattr(eu, 'username', None) or 'sem @'}) · id {id_atual}")
    except Exception as e:
        id_atual = None
        logger.warning(f"⚠️ [Captura] Não consegui identificar a conta: {e}")

    anterior = (db.ler_config("conta_captura_atual", {}) or {}).get("user_id")
    if id_atual and anterior and anterior != id_atual:
        try:
            conexao = db.conectar()
            conexao.execute("UPDATE parceiros SET origem_ok = NULL WHERE ativo = 1")
            conexao.commit()
            conexao.close()
            logger.info("👥 [Parceiros] Conta da captura mudou: canais dos parceiros serão reconferidos.")
        except sqlite3.OperationalError:
            pass   # tabela de parceiros ainda não existe
    if id_atual:
        db.salvar_config("conta_captura_atual", {"user_id": id_atual})


async def montar_contas():
    """
    Liga as contas conforme o pool: a da captura (com o handler de mensagens) e as
    do rodízio. Roda no start e a cada plantão; só mexe no que mudou.
    """
    global client, conta_captura, modo_sessao_fixa, ordem_rodizio

    if not pool_contas.listar_contas():
        if not modo_sessao_fixa:
            logger.info(f"👤 [Contas] Nenhuma conta no pool: usando a sessão fixa '{NOME_SESSAO}'.")
            cliente = TelegramClient(NOME_SESSAO, API_ID, API_HASH)
            await cliente.start()
            await _preparar_cliente(cliente)
            cliente.add_event_handler(interceptar_e_espelhar, events.NewMessage(incoming=True))
            client, conta_captura, modo_sessao_fixa = cliente, None, True
            await _apos_trocar_captura()
        return

    if modo_sessao_fixa:
        # Contas cadastradas com o robô rodando: deixa a sessão fixa e passa para o pool.
        logger.info("👤 [Contas] Contas no pool: deixando a sessão fixa.")
        await _desligar_cliente(client)
        client, conta_captura, modo_sessao_fixa = None, None, False

    # Rodízio: sai quem não está mais; as novas conectam.
    rodizio = pool_contas.obter_contas_repostagem()
    desejadas = {c["id"]: c for c in rodizio}
    for cid in list(clientes_repost):
        if cid not in desejadas:
            _conta, cliente = clientes_repost.pop(cid)
            await _desligar_cliente(cliente)
            logger.info(f"♻️ [Rodízio] {_conta['apelido']} saiu do rodízio.")
    for cid, conta in desejadas.items():
        if cid in clientes_repost:
            clientes_repost[cid] = (conta, clientes_repost[cid][1])
            continue
        cliente = await _conectar_conta(conta)
        if cliente is not None:
            clientes_repost[cid] = (conta, cliente)
            logger.info(f"♻️ [Rodízio] {conta['apelido']} entrou no rodízio.")
    ordem_rodizio = [c["id"] for c in rodizio]

    # Captura: troca o cliente só se a conta do posto mudou.
    nova = pool_contas.obter_conta_da_funcao(pool_contas.FUNCAO_ESPELHO)
    if (nova or {}).get("id") == (conta_captura or {}).get("id") and (client is not None or nova is None):
        conta_captura = nova
        return
    if client is not None:
        await _desligar_cliente(client)
    client, conta_captura = None, None
    if nova is None:
        logger.error("🛑 [Captura] Posto VAGO: nenhuma conta apta. A captura está parada.")
        return
    cliente = await _conectar_conta(nova)
    if cliente is None:
        logger.error(f"🛑 [Captura] Não consegui conectar '{nova['apelido']}'. Captura parada até o próximo plantão.")
        return
    cliente.add_event_handler(interceptar_e_espelhar, events.NewMessage(incoming=True))
    client, conta_captura = cliente, nova
    logger.info(f"🪞 [Captura] {nova['apelido']} assumiu a captura.")
    await _apos_trocar_captura()


async def plantao_contas_loop():
    """
    De INTERVALO_PLANTAO_MIN em INTERVALO_PLANTAO_MIN minutos: checa as contas do
    pool no Telegram (reaproveitando os clientes já conectados), redistribui os
    postos e religa as contas deste robô se algo mudou.
    """
    while True:
        try:
            if pool_contas.listar_contas():
                ativos = {cid: cliente for cid, (_conta, cliente) in clientes_repost.items()}
                if conta_captura and client is not None:
                    ativos[conta_captura["id"]] = client
                mudancas = await pool_contas.sincronizar_pool(clientes=ativos)
                if mudancas:
                    logger.info(f"🔄 [Contas] {len(mudancas)} mudança(s) de posto no plantão.")
            await montar_contas()
            blacklist_captura.sincronizar_contas_do_pool()
        except Exception as e:
            logger.error(f"❌ [Contas] Falha no plantão: {e}")
        await asyncio.sleep(INTERVALO_PLANTAO_MIN * 60)


async def main():
    logger.info("⏳ Iniciando o robô Espelhador Isolado...")

    # Contas próprias na lista negra antes de começar a escutar: o retorno publicado
    # por uma conta do rodízio chega à captura como mensagem de terceiro.
    try:
        _bl_add, _bl_rem = blacklist_captura.sincronizar_contas_do_pool()
        logger.info(f"🚫 [Lista Negra] Contas próprias protegidas "
                    f"(+{_bl_add} / -{_bl_rem}).")
    except Exception as e:
        logger.error(f"❌ [Lista Negra] Falha ao sincronizar no start: {e}")

    await montar_contas()

    criar_tarefa_fundo(processar_fila_autorais_loop())
    criar_tarefa_fundo(processar_fila_publico_loop())   # baixa os vídeos do Grupo Público
    criar_tarefa_fundo(loop_entrada_parceiros())   # entrada nos canais dos parceiros
    criar_tarefa_fundo(varredura_origem_loop())   # captura por busca ativa na origem
    criar_tarefa_fundo(plantao_contas_loop())   # troca de contas e checagem de 10 em 10 min

    logger.info("🤖 Sistema a rodar. A escutar o grupo de origem continuamente...")
    # Os clientes recebem as mensagens em segundo plano; o processo só precisa ficar vivo.
    await asyncio.Event().wait()


_tarefas_fundo = set()

def criar_tarefa_fundo(coro):
    """create_task guardando a referência (task sem referência pode ser coletada no meio)."""
    tarefa = asyncio.create_task(coro)
    _tarefas_fundo.add(tarefa)
    tarefa.add_done_callback(_tarefas_fundo.discard)
    return tarefa

if __name__ == '__main__':
    asyncio.run(main())
