# ==========================================
# 📥 SHOPEE DOWNLOADER — serviço independente
# Bot próprio (@ShopeedownloadVideoBot) para isolar o risco: se este serviço
# cair, tomar limite do Telegram ou quebrar por causa do yt-dlp, os quatro
# robôs que geram receita continuam intactos.
#
# FASE 0: apenas a trava de acesso. Nenhum download acontece ainda.
# ==========================================
EXIBIR_LOGS = True

import os
import re
import asyncio
import logging
import shutil
import tempfile
import sqlite3
import hashlib
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# 🕐 Trava de fuso centralizada: importar o modulo ja aplica America/Sao_Paulo.
from fuso import FUSO_STR, fuso_horario, configurar_logs

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command, ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage

if EXIBIR_LOGS:
    logger = configurar_logs(__name__)

FUSO = ZoneInfo("America/Sao_Paulo")

TOKEN = os.getenv("TELEGRAM_TOKEN_DOWNLOADER")
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# --- ONDE O ROBÔ ATUA ---
GRUPO_DOWNLOADER = -1003892378604      # Grupo Público para Afiliados
TOPICO_DOWNLOADER = 1054               # tópico "Downloader Videos"

# --- CANAIS OBRIGATÓRIOS (a ordem é a que o usuário vê) ---
CANAIS_OBRIGATORIOS = [
    (-1003909405581, "Acervo Afiliados Shopee",   "https://t.me/shopee_video_afiliado"),
    (-1003932482573, "Acervo Viral Shopee",       "https://t.me/acervo_viral_shopee"),
    (-1003892378604, "Grupo Público",             "https://t.me/GrupoPublicoAfiliados"),
    (-1004460669033, "Central de Achadinhos VIP", "https://t.me/centraldeachadinhosvip"),
]

LIMITE_DIARIO_DOWNLOADS = 10

# 💡 EMPURRÃOZINHO PARA A COMUNIDADE
# O tópico do baixador fica DENTRO do Grupo Público, então quem baixa já é
# membro: basta apontar para o tópico ao lado. O convite sai de vez em quando,
# logo depois de a pessoa RECEBER um vídeo — o pico de boa vontade dela.
CONVITE_COMUNIDADE_ATIVO = True
CONVITE_A_CADA = 5               # a cada N downloads da pessoa. 0 desliga.
CONVITE_SEGUNDOS_NA_TELA = 40    # depois some sozinho

# 🎁 CORTESIA: os primeiros downloads saem sem exigir os canais. Precisa ficar
# aqui em cima porque o texto do painel usa este valor antes das funções.
DOWNLOADS_CORTESIA = 5

# ♾️ Quem está aqui não tem limite diário. Usado para testar o bot sem
# queimar cota e para atender pedidos manuais.
IDS_SEM_LIMITE = {1226920464}   # Rafael (admin)

# Piloto: YouTube fica de fora — é a plataforma que mais quebra o yt-dlp
# e a que gera arquivos acima do limite de 50 MB do Telegram.
PADROES_SUPORTADOS = {
    "TikTok":    r'(?:vm\.tiktok\.com|vt\.tiktok\.com|tiktok\.com)/\S+',
    "Instagram": r'instagram\.com/(?:p|reel|reels|tv)/\S+',
    "Pinterest": r'(?:pin\.it|pinterest\.[a-z.]+)/\S+',
    "Shopee":    r'(?:s\.shopee\.com\.br|shope\.ee|br\.shp\.ee|shp\.ee|shopee\.com\.br)/\S+',
}

PASTA_TEMP_DOWNLOAD = "temp_downloads"
LIMITE_TELEGRAM_MB = 48          # o teto real é 50; margem para a legenda
TIMEOUT_DOWNLOAD_SEG = 180       # 3 min por vídeo
ALTURA_MAXIMA = 720              # 1080p estoura o limite do Telegram com facilidade

os.makedirs(PASTA_TEMP_DOWNLOAD, exist_ok=True)

# 🚦 Fila: um download por vez. Em paralelo, o ffmpeg derruba a CPU do ARM.
semaforo_download = asyncio.Semaphore(1)

BANCO_DOWNLOADER = "banco_dados.db"

def _garantir_tabela_downloads(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS downloads_usuarios (
            user_id INTEGER,
            data TEXT,
            quantidade INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, data)
        )
    ''')

# 📌 Painel fixo do tópico: explica para que serve e o que dá para baixar.
TEXTO_PAINEL_DOWNLOADER = (
    "📥 <b>BAIXADOR DE VÍDEOS</b>\n\n"
    "Cole aqui o <b>link</b> do vídeo e eu devolvo o arquivo, "
    "<b>sem marca d'água</b>, pronto para postar.\n\n"
    "<b>Plataformas que funcionam:</b>\n"
    "🔶 <b>Shopee</b> — vídeos de produto e de afiliado\n"
    "⬛ <b>TikTok</b>\n"
    "📌 <b>Pinterest</b>\n"
    "📸 <b>Instagram</b> — posts, reels e IGTV\n\n"
    "<i>🔴 O YouTube está sendo trabalhado.</i>\n\n"
    "<b>Como usar:</b>\n"
    "1️⃣ Copie o link do vídeo no aplicativo de origem\n"
    "2️⃣ Cole aqui neste tópico, sozinho, sem texto junto\n"
    "3️⃣ Aguarde — um vídeo por vez, costuma levar menos de 1 minuto"
)


def _garantir_tabela_cortesia(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS downloads_totais (
            user_id INTEGER PRIMARY KEY,
            total INTEGER DEFAULT 0
        )
    ''')


def downloads_totais(user_id):
    """Quantos a pessoa já baixou desde sempre. Nunca é zerado."""
    try:
        conexao = sqlite3.connect(BANCO_DOWNLOADER, timeout=20.0)
        cursor = conexao.cursor()
        _garantir_tabela_cortesia(cursor)
        cursor.execute("SELECT total FROM downloads_totais WHERE user_id = ?", (user_id,))
        linha = cursor.fetchone()
        conexao.close()
        return linha[0] if linha else 0
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler o total: {e}")
        # Na dúvida, considera cortesia esgotada: melhor exigir a mais do que liberar de graça.
        return DOWNLOADS_CORTESIA


def topico_submissao():
    """
    💡 Lê o tópico "Poste seus Vídeos Aqui" da config do bot_mestre.

    Os dois bots usam o mesmo banco_dados.db, então não precisa hardcodear o
    número: se você trocar o tópico no painel, o convite acompanha sozinho.
    Devolve None quando não achar — e aí o convite simplesmente não sai.
    """
    try:
        conexao = sqlite3.connect(BANCO_DOWNLOADER, timeout=20.0)
        cursor = conexao.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'submissao_config'")
        linha = cursor.fetchone()
        conexao.close()
        if not linha:
            return None
        topico = (json.loads(linha[0]) or {}).get("topico_envio")
        return int(topico) if topico else None
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Não consegui ler o tópico de submissão: {e}")
        return None


async def convidar_para_comunidade(message, mencao, total_downloads):
    """
    💡 Convite ocasional para publicar no Vídeos da Comunidade.

    Dispara no melhor instante possível: a pessoa acabou de receber um vídeo de
    graça. Nunca aparece na primeira entrega — deixa ela usar antes de pedir algo.
    Some sozinho e é registrado na faxina para não sobrar lixo no tópico.
    """
    if not CONVITE_COMUNIDADE_ATIVO or CONVITE_A_CADA <= 0:
        return
    if total_downloads < CONVITE_A_CADA or total_downloads % CONVITE_A_CADA != 0:
        return

    topico = topico_submissao()
    if not topico:
        return

    # 🔗 Link direto do tópico. Funciona porque o baixador vive DENTRO do grupo:
    # quem está lendo isto já é membro e o Telegram abre o tópico na hora.
    interno = str(GRUPO_DOWNLOADER).lstrip("-")
    if interno.startswith("100"):
        interno = interno[3:]
    link = f"https://t.me/c/{interno}/{topico}"

    try:
        convite = await message.answer(
            f"💡 {mencao}, você também pode <b>publicar os seus vídeos</b> aqui no grupo.\n\n"
            f"Seu nome aparece na legenda para todo mundo ver, e a galera aproveita "
            f"o achado que você trouxe.\n\n"
            f"👉 <b><a href='{link}'>Toque aqui para enviar o seu vídeo</a></b>\n"
            f"<i>Abre o tópico «Poste seus Vídeos Aqui», aqui mesmo no grupo.</i>",
            parse_mode="HTML", disable_web_page_preview=True
        )
        registrar_mensagem(convite.message_id)
        if EXIBIR_LOGS:
            logger.info(f"💡 [Convite Comunidade] Enviado para {message.from_user.id} "
                        f"(download nº {total_downloads}).")
        await asyncio.sleep(CONVITE_SEGUNDOS_NA_TELA)
        try: await convite.delete()
        except Exception: pass
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha ao enviar o convite da comunidade: {e}")


def somar_download_total(user_id):
    try:
        conexao = sqlite3.connect(BANCO_DOWNLOADER, timeout=20.0)
        cursor = conexao.cursor()
        _garantir_tabela_cortesia(cursor)
        cursor.execute("""
            INSERT INTO downloads_totais (user_id, total) VALUES (?, 1)
            ON CONFLICT(user_id) DO UPDATE SET total = total + 1
        """, (user_id,))
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao somar o total: {e}")




def _garantir_tabela_painel(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS painel_downloader (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    ''')

def ler_msg_painel():
    """ID da última mensagem do painel. Sobrevive a reinício do serviço."""
    try:
        conexao = sqlite3.connect(BANCO_DOWNLOADER, timeout=20.0)
        cursor = conexao.cursor()
        _garantir_tabela_painel(cursor)
        cursor.execute("SELECT valor FROM painel_downloader WHERE chave = 'msg_id'")
        linha = cursor.fetchone()
        conexao.close()
        return int(linha[0]) if linha and linha[0] else None
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler o painel: {e}")
        return None


def salvar_msg_painel(msg_id):
    try:
        conexao = sqlite3.connect(BANCO_DOWNLOADER, timeout=20.0)
        cursor = conexao.cursor()
        _garantir_tabela_painel(cursor)
        cursor.execute("INSERT OR REPLACE INTO painel_downloader (chave, valor) VALUES ('msg_id', ?)",
                       (str(msg_id),))
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao salvar o painel: {e}")

# 🧹 Auto-limpeza: o tópico guarda mensagens por este tanto de dias.
DIAS_RETENCAO_TOPICO = 3


def _garantir_tabela_mensagens(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mensagens_topico (
            message_id INTEGER PRIMARY KEY,
            criado_em TEXT
        )
    ''')


def registrar_mensagem(message_id):
    """Anota o ID para a faxina achar depois. A API de bots não lê histórico,
    então o que não for anotado aqui nunca será apagado."""
    try:
        conexao = sqlite3.connect(BANCO_DOWNLOADER, timeout=20.0)
        cursor = conexao.cursor()
        _garantir_tabela_mensagens(cursor)
        cursor.execute(
            "INSERT OR IGNORE INTO mensagens_topico (message_id, criado_em) VALUES (?, ?)",
            (int(message_id), datetime.now(FUSO).strftime("%Y-%m-%d %H:%M:%S"))
        )
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao registrar mensagem: {e}")


def mensagens_vencidas():
    try:
        corte = (datetime.now(FUSO) - timedelta(days=DIAS_RETENCAO_TOPICO)).strftime("%Y-%m-%d %H:%M:%S")
        conexao = sqlite3.connect(BANCO_DOWNLOADER, timeout=20.0)
        cursor = conexao.cursor()
        _garantir_tabela_mensagens(cursor)
        cursor.execute("SELECT message_id FROM mensagens_topico WHERE criado_em < ?", (corte,))
        ids = [linha[0] for linha in cursor.fetchall()]
        conexao.close()
        return ids
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao listar vencidas: {e}")
        return []


def esquecer_mensagens(ids):
    if not ids:
        return
    try:
        conexao = sqlite3.connect(BANCO_DOWNLOADER, timeout=20.0)
        cursor = conexao.cursor()
        _garantir_tabela_mensagens(cursor)
        cursor.executemany("DELETE FROM mensagens_topico WHERE message_id = ?", [(i,) for i in ids])
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao limpar registro: {e}")


def downloads_hoje(user_id):
    """Quantos já usou hoje. Persistente: reiniciar o bot não zera o contador."""
    try:
        hoje = datetime.now(FUSO).strftime("%Y-%m-%d")
        conexao = sqlite3.connect(BANCO_DOWNLOADER, timeout=20.0)
        cursor = conexao.cursor()
        _garantir_tabela_downloads(cursor)
        cursor.execute("SELECT quantidade FROM downloads_usuarios WHERE user_id = ? AND data = ?", (user_id, hoje))
        linha = cursor.fetchone()
        conexao.close()
        return linha[0] if linha else 0
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao contar downloads: {e}")
        return 0

def registrar_download(user_id):
    """Conta APÓS a entrega: tentativa que falhou não gasta a cota do usuário."""
    try:
        hoje = datetime.now(FUSO).strftime("%Y-%m-%d")
        conexao = sqlite3.connect(BANCO_DOWNLOADER, timeout=20.0)
        cursor = conexao.cursor()
        _garantir_tabela_downloads(cursor)
        cursor.execute('''
            INSERT INTO downloads_usuarios (user_id, data, quantidade) VALUES (?, ?, 1)
            ON CONFLICT(user_id, data) DO UPDATE SET quantidade = quantidade + 1
        ''', (user_id, hoje))
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao registrar download: {e}")

def limpar_downloads_antigos(dias=7):
    """A contagem só importa no dia. Guardar uma semana já é folga."""
    try:
        corte = (datetime.now(FUSO) - timedelta(days=dias)).strftime("%Y-%m-%d")
        conexao = sqlite3.connect(BANCO_DOWNLOADER, timeout=20.0)
        cursor = conexao.cursor()
        _garantir_tabela_downloads(cursor)
        cursor.execute("DELETE FROM downloads_usuarios WHERE data < ?", (corte,))
        removidos = cursor.rowcount
        conexao.commit()
        conexao.close()
        if removidos and EXIBIR_LOGS:
            logger.info(f"🧹 {removidos} registro(s) de download antigos removidos.")
    except Exception:
        pass

async def atualizar_yt_dlp():
    """Atualiza o yt-dlp silenciosamente via subprocesso no servidor."""
    if EXIBIR_LOGS: logger.info("🔄 Iniciando verificação automática de atualização do pacote yt-dlp...")
    try:
        proc = await asyncio.create_subprocess_exec(
            "/home/ubuntu/shopee/venv/bin/python3", "-m", "pip", "install", "-U", "yt-dlp",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            if EXIBIR_LOGS: logger.info("✅ Sucesso: pacote yt-dlp está atualizado com a versão mais recente.")
        else:
            if EXIBIR_LOGS: logger.error(f"❌ Falha na execução do pip update: {stderr.decode(errors='ignore').strip()}")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro sistêmico ao tentar rodar a atualização: {e}")

async def faxina_diaria_loop():
    """Uma vez por dia, poda a tabela de contagem e atualiza os motores de extração."""
    if EXIBIR_LOGS: logger.info("🚀 Loop de manutenção diária (Faxina e Updates) iniciado em background.")
    # Executa a primeira atualização imediatamente ao ligar o bot
    await atualizar_yt_dlp()
    while True:
        await asyncio.sleep(86400) # Pausa de 24 horas
        await atualizar_yt_dlp()
        limpar_downloads_antigos()

# ♻️ CACHE DE VÍDEOS
# O file_id é só uma string (~80 bytes) — o vídeo fica nos servidores do Telegram.
# Reenviar o mesmo id custa zero download, zero banda e zero disco.
DIAS_CACHE_VIDEO = 30

def chave_cache_video(url):
    """Ignora rastreadores (?fromSource=, ?_t=) para o mesmo vídeo gerar a mesma chave."""
    limpo = str(url or "").strip().lower().split("?")[0].rstrip("/")
    return hashlib.md5(limpo.encode()).hexdigest()[:20]

def _garantir_cache_videos(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cache_videos (
            chave TEXT PRIMARY KEY,
            file_id TEXT,
            plataforma TEXT,
            data_cache TEXT,
            usos INTEGER DEFAULT 1
        )
    ''')

def buscar_cache_video(url):
    """Devolve o file_id já guardado, ou None."""
    try:
        conexao = sqlite3.connect(BANCO_DOWNLOADER, timeout=20.0)
        cursor = conexao.cursor()
        _garantir_cache_videos(cursor)
        chave = chave_cache_video(url)
        cursor.execute("SELECT file_id FROM cache_videos WHERE chave = ?", (chave,))
        linha = cursor.fetchone()
        if linha:
            cursor.execute("UPDATE cache_videos SET usos = usos + 1 WHERE chave = ?", (chave,))
            conexao.commit()
        conexao.close()
        return linha[0] if linha else None
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao consultar o cache: {e}")
        return None

def guardar_cache_video(url, file_id, plataforma):
    try:
        conexao = sqlite3.connect(BANCO_DOWNLOADER, timeout=20.0)
        cursor = conexao.cursor()
        _garantir_cache_videos(cursor)
        cursor.execute(
            "INSERT OR IGNORE INTO cache_videos (chave, file_id, plataforma, data_cache, usos) VALUES (?, ?, ?, ?, 1)",
            (chave_cache_video(url), file_id, plataforma, datetime.now(FUSO).strftime("%Y-%m-%d %H:%M:%S"))
        )
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao guardar no cache: {e}")

def limpar_cache_videos_antigos(dias=DIAS_CACHE_VIDEO):
    """file_id antigo pode expirar no Telegram — melhor rebaixar do que entregar quebrado."""
    try:
        corte = (datetime.now(FUSO) - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
        conexao = sqlite3.connect(BANCO_DOWNLOADER, timeout=20.0)
        cursor = conexao.cursor()
        _garantir_cache_videos(cursor)
        cursor.execute("DELETE FROM cache_videos WHERE data_cache < ?", (corte,))
        removidos = cursor.rowcount
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(usos - 1), 0) FROM cache_videos")
        total, economizados = cursor.fetchone()
        conexao.commit()
        conexao.close()
        if EXIBIR_LOGS:
            logger.info(f"♻️ [Cache] {total} vídeo(s) guardado(s) · {economizados} download(s) economizado(s)"
                        + (f" · {removidos} expirado(s) removido(s)" if removidos else ""))
    except Exception:
        pass

def remover_cache_video(url):
    """Chamado quando o file_id guardado não funciona mais."""
    try:
        conexao = sqlite3.connect(BANCO_DOWNLOADER, timeout=20.0)
        cursor = conexao.cursor()
        cursor.execute("DELETE FROM cache_videos WHERE chave = ?", (chave_cache_video(url),))
        conexao.commit()
        conexao.close()
    except Exception:
        pass

def normalizar_pinterest(url):
    """
    🧭 Reduz qualquer URL do Pinterest à forma canônica do pin.

    O botão Compartilhar gera /pin/<id>/sent/?invite_code=...&sender=...&sfo=1,
    que é a página de CONVITE. O yt-dlp lê o id certo a partir dela, mas volta
    sem nenhum formato de vídeo — o famoso 'Requested format is not available'.
    Links de outras plataformas passam intactos.
    """
    achado = re.search(r'(https?://[a-z0-9.]*pinterest\.[a-z.]+/pin/\d+)', url, re.IGNORECASE)
    if achado:
        limpa = achado.group(1) + "/"
        if limpa != url and EXIBIR_LOGS:
            logger.info(f"🧭 URL do Pinterest normalizada para {limpa}")
        return limpa
    return url


async def expandir_encurtador(url):
    """
    O pin.it redireciona para a home do Pinterest quando não parece um navegador.
    Sem os cabeçalhos certos, o yt-dlp recebe a página inicial e não acha vídeo.
    """
    if "pin.it" not in url.lower():
        # 🧭 Link do Pinterest colado direto também pode vir com /sent/ e query.
        return normalizar_pinterest(url)
    try:
        import aiohttp
        cabecalhos = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
        async with aiohttp.ClientSession(headers=cabecalhos) as sessao:
            async with sessao.get(url, allow_redirects=True, timeout=15) as resposta:
                final = str(resposta.url)
                if "/pin/" in final:
                    if EXIBIR_LOGS: logger.info(f"🔗 pin.it expandido para {final}")
                    return normalizar_pinterest(final)

                # 🔍 O Pinterest às vezes devolve uma página intersticial em JS em
                # vez de um redirect 30x. Nesse caso resposta.url continua sendo o
                # pin.it, mas o link real está no <link rel="canonical"> do corpo.
                # Antes esta função caía no 'return url' SEM logar nada, e o yt-dlp
                # recebia o link curto e morria sem ninguém saber o porquê.
                try:
                    corpo = await resposta.text()
                except Exception:
                    corpo = ""

                achado = re.search(r'https?://[a-z0-9.]*pinterest\.[a-z.]+/pin/\d+', corpo, re.IGNORECASE)
                if achado:
                    if EXIBIR_LOGS: logger.info(f"🔗 pin.it expandido pelo HTML para {achado.group(0)}")
                    return normalizar_pinterest(achado.group(0))

                if EXIBIR_LOGS:
                    logger.warning(f"⚠️ pin.it NÃO expandiu: parou em {final} "
                                   f"(HTTP {resposta.status}, corpo com {len(corpo)} bytes). "
                                   f"Provável bloqueio por IP ou limite de requisições.")
    except Exception as e:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Não consegui expandir o pin.it: {e}")
    return url

# 🛒 A Shopee não é suportada pelo yt-dlp, mas a URL do MP4 vem embutida
# no HTML da página. O CDN alterna entre hosts (down-ws, down-tx, down-bs),
# por isso o padrão aceita qualquer um deles.
CABECALHO_NAVEGADOR = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
}

# ==========================================================
# 🧼 LIMPEZA DO RENDER DA SHOPEE
# Quando a matriz limpa não está exposta na página, o que sobra é o render
# do app: marca "Shopee Video / @usuario" queimada no pixel e uma cartela
# laranja no fim. O ffmpeg resolve os dois localmente, sem API de terceiro.
# ==========================================================
LIMPAR_VIDEO_SHOPEE = True
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
COR_CARTELA_SHOPEE = (238, 77, 45)
TOLERANCIA_CARTELA = 60
# Caixa da marca em PROPORÇÃO do quadro (x, y, largura, altura):
# o arquivo vem 480x854 ou 720x1280 dependendo do vídeo.
MARCA_SHOPEE_PROPORCAO = (0.010, 0.440, 0.385, 0.100)
TIMEOUT_LIMPEZA_SEG = 120

async def _executar(comando, timeout, capturar=True):
    """Roda um processo externo sem travar o bot. Devolve (saida, erro, falha)."""
    proc = await asyncio.create_subprocess_exec(
        *comando,
        stdout=asyncio.subprocess.PIPE if capturar else asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        saida, erro = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return None, None, "tempo esgotado"
    if proc.returncode != 0:
        return None, None, (erro or b"").decode(errors="ignore")[-300:]
    return saida, erro, None

async def _dimensoes_video(caminho):
    comando = [FFPROBE, "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height", "-of", "csv=p=0", caminho]
    saida, _, falha = await _executar(comando, 30)
    if falha or not saida:
        return None, None
    try:
        largura, altura = saida.decode().strip().split(",")[:2]
        return int(largura), int(altura)
    except Exception:
        return None, None

async def _inicio_cartela_shopee(caminho):
    """Reduz cada quadro a 1 pixel e acha onde começa o bloco laranja FINAL.
    Devolve o segundo do corte, ou None se não houver cartela."""
    comando = [FFMPEG, "-v", "error", "-i", caminho,
               "-vf", "fps=10,scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    bruto, _, falha = await _executar(comando, 60)
    if falha or not bruto:
        return None

    cores = [bruto[i:i + 3] for i in range(0, len(bruto) - 2, 3)]
    if not cores:
        return None

    def e_laranja(c):
        return all(abs(c[i] - COR_CARTELA_SHOPEE[i]) <= TOLERANCIA_CARTELA for i in range(3))

    # Só corta se o vídeo TERMINA em laranja: senão é cor de cena, não cartela.
    if not e_laranja(cores[-1]):
        return None

    i = len(cores) - 1
    while i >= 0 and e_laranja(cores[i]):
        i -= 1

    inicio = (i + 1) / 10.0
    duracao = len(cores) / 10.0
    # 🛡️ Trava: nunca engolir metade do vídeo por causa de uma cena laranja.
    if inicio < 1.0 or inicio < duracao * 0.5:
        return None
    return inicio

async def limpar_video_shopee(caminho, pasta):
    """Devolve o caminho do vídeo limpo. Se algo falhar, devolve o original:
    entregar com marca é melhor do que não entregar nada."""
    filtros = []
    # 🧼 Só borra se o download veio da versão marcada (ver baixar_video_shopee).
    tem_marca = os.path.exists(os.path.join(pasta, "COM_MARCA"))
    largura, altura = await _dimensoes_video(caminho)
    if tem_marca and largura and altura:
        px, py, pw, ph = MARCA_SHOPEE_PROPORCAO
        x, y = max(1, int(largura * px)), max(1, int(altura * py))
        w, h = int(largura * pw), int(altura * ph)
        if x + w < largura - 1 and y + h < altura - 1:
            filtros.append(f"delogo=x={x}:y={y}:w={w}:h={h}")

    corte = await _inicio_cartela_shopee(caminho)

    if not filtros and not corte:
        if EXIBIR_LOGS: logger.info("🧼 Nada a limpar neste vídeo da Shopee.")
        return caminho

    destino = os.path.join(pasta, "limpo.mp4")
    comando = [FFMPEG, "-v", "error", "-y", "-i", caminho]
    if corte:
        comando += ["-t", f"{corte:.2f}"]
    if filtros:
        comando += ["-vf", ",".join(filtros)]
        comando += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
    else:
        comando += ["-c:v", "copy"]
    comando += ["-c:a", "copy", "-movflags", "+faststart", destino]

    _, _, falha = await _executar(comando, TIMEOUT_LIMPEZA_SEG, capturar=False)
    if falha or not os.path.exists(destino) or os.path.getsize(destino) == 0:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Limpeza falhou, entregando o original: {falha}")
        return caminho

    if EXIBIR_LOGS:
        logger.info(f"🧼 Limpo (marca: {'sim' if filtros else 'nao'} | "
                    f"cartela cortada em {corte or 'nenhuma'}s).")
    return destino

async def baixar_video_shopee(url, pasta):
    """Busca o vídeo matriz limpo via Engenharia Reversa do estado (JSON) interno da Shopee."""
    try:
        import aiohttp
        import json
        import urllib.parse

        async with aiohttp.ClientSession(headers=CABECALHO_NAVEGADOR) as sessao:
            # 1. Resolve o link encurtado (br.shp.ee)
            async with sessao.get(url, allow_redirects=True, timeout=25) as resposta:
                if resposta.status != 200:
                    return None, "não consegui abrir a página da Shopee"
                html = await resposta.text()
                url_final = str(resposta.url)

            # 2. Desvenda o redirecionamento universal-link oculto
            if "universal-link" in url_final and "redir=" in url_final:
                destino_real = urllib.parse.parse_qs(urllib.parse.urlparse(url_final).query).get("redir", [None])[0]
                if destino_real:
                    destino_real = urllib.parse.unquote(destino_real)
                    if EXIBIR_LOGS: logger.info(f"🛒 Link real localizado: {destino_real[:70]}...")
                    async with sessao.get(destino_real, allow_redirects=True, timeout=25) as r2:
                        if r2.status == 200:
                            html = await r2.text()

            # 3. Coleta candidatos a vídeo. A Shopee serve DUAS gerações de página:
            # a antiga com window.__INITIAL_STATE__ e a nova em Next.js com
            # <script id="__NEXT_DATA__">. Hoje o link de compartilhamento só
            # expõe "watermarkVideoUrl" — não existe matriz limpa aqui.
            candidatos = []   # lista de (chave, url)

            def _normalizar(u):
                return u.replace("\\u002F", "/").replace("\\/", "/") if isinstance(u, str) else ""

            def guardar(chave, valor):
                u = _normalizar(valor)
                if not u.startswith("http"):
                    return
                if any(u.lower().split("?")[0].endswith(e) for e in (".jpg", ".jpeg", ".png", ".webp")):
                    return
                chave_l = str(chave).lower()
                if ".mp4" not in u.lower() and "video" not in chave_l:
                    return
                # Dedupe por URL: a mesma URL achada 2x não pode trocar de classificação.
                if any(u == existente for _, existente in candidatos):
                    return
                candidatos.append((str(chave), u))

            def varrer(dados):
                if isinstance(dados, dict):
                    for k, v in dados.items():
                        if isinstance(v, str):
                            guardar(k, v)
                        else:
                            varrer(v)
                elif isinstance(dados, list):
                    for item in dados:
                        varrer(item)

            blocos = []
            achado = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});\s*</script>', html, re.DOTALL)
            if achado:
                blocos.append(achado.group(1))
            achado = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if achado:
                blocos.append(achado.group(1))

            for bruto in blocos:
                try:
                    varrer(json.loads(bruto))
                except Exception as e:
                    if EXIBIR_LOGS: logger.warning(f"⚠️ JSON da página não decodificou: {e}")

            # Rede de segurança, por último: qualquer .mp4 solto no HTML.
            for solto in re.findall(r'https?:[^"\'\\\s<>]+\.mp4[^"\'\\\s<>]*', html):
                guardar("html", solto)

            if EXIBIR_LOGS:
                logger.info(f"🛒 {len(candidatos)} candidato(s): "
                            + ", ".join(k for k, _ in candidatos[:6]))

            # ⚠️ É a CHAVE que denuncia a marca: a URL de watermarkVideoUrl
            # não contém a palavra "watermark" em lugar nenhum.
            def tem_marca(chave, url):
                return "watermark" in chave.lower() or "watermark" in url.lower()

            limpos = [u for k, u in candidatos if not tem_marca(k, u)]
            marcados = [u for k, u in candidatos if tem_marca(k, u)]            

            # 🎯 A URL marcada termina em <arquivo>.<idVideo>.<perfil>.mp4.
            # Esses dois campos finais são o carimbo do render de compartilhamento,
            # que é onde a marca e a cartela de 3s são queimadas. Sem eles sobra o
            # arquivo ORIGINAL do criador: medido 3,03 MB em 720x1280 contra
            # 0,94 MB em 480x854, e a duração bate ao ms com o metadado da página.
            def _derivar_matriz(u):
                base, arquivo = u.rsplit("/", 1)
                partes = arquivo.split(".")
                if len(partes) >= 4 and partes[-1] == "mp4":
                    return f"{base}/{'.'.join(partes[:-3])}.mp4"
                return None

            for marcada in list(marcados):
                matriz = _derivar_matriz(marcada)
                if not matriz:
                    continue
                try:
                    # Pede 1 byte só: confirma que existe sem baixar o arquivo.
                    async with sessao.get(matriz, headers={"Range": "bytes=0-0"},
                                          timeout=15) as teste:
                        if teste.status in (200, 206):
                            limpos.insert(0, matriz)
                            if EXIBIR_LOGS: logger.info("🎯 Matriz original localizada!")
                            break
                except Exception as e:
                    if EXIBIR_LOGS: logger.warning(f"⚠️ Matriz não respondeu: {e}")

            link_mp4 = None
            if limpos:
                link_mp4 = limpos[0]
                if EXIBIR_LOGS: logger.info("🧠 Matriz limpa encontrada.")
            elif marcados:
                link_mp4 = marcados[0]
                # 🧼 Sinaliza para a limpeza que este arquivo tem marca queimada.
                try:
                    open(os.path.join(pasta, "COM_MARCA"), "w").close()
                except Exception:
                    pass
                if EXIBIR_LOGS: logger.warning("⚠️ Só há a versão com marca: o ffmpeg limpa depois.")

            if not link_mp4:
                return None, ("não achei nenhum arquivo de vídeo nesta página da Shopee. "
                              "Talvez o link seja de produto, e não de vídeo")

            if EXIBIR_LOGS: logger.info(f"🛒 MP4 Limpo pronto para download: {link_mp4[:70]}...")

            # 5. Baixa o arquivo direto do CDN
            destino = os.path.join(pasta, "video.mp4")
            async with sessao.get(link_mp4, timeout=TIMEOUT_DOWNLOAD_SEG) as fluxo:
                if fluxo.status != 200:
                    return None, "o vídeo matriz não está mais disponível no servidor da Shopee"
                total = 0
                limite = LIMITE_TELEGRAM_MB * 1024 * 1024
                with open(destino, "wb") as arquivo:
                    async for pedaco in fluxo.content.iter_chunked(65536):
                        total += len(pedaco)
                        if total > limite:
                            return None, f"o vídeo passa de {LIMITE_TELEGRAM_MB} MB"
                        arquivo.write(pedaco)

            if os.path.getsize(destino) > 0:
                return destino, None
            return None, "o download da matriz veio vazio"

    except asyncio.TimeoutError:
        return None, "a Shopee demorou demais para responder"
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro crítico na extração da matriz da Shopee: {e}")
        return None, "erro interno ao extrair matriz da Shopee"

    except asyncio.TimeoutError:
        return None, "a API externa demorou demais para responder"
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro crítico na comunicação com a API de extração: {e}")
        return None, "erro interno ao processar a extração via API"

async def _baixar_video_uma_vez(url, pasta):
    """
    Roda o yt-dlp em SUBPROCESSO. Chamar direto travaria o bot inteiro,
    porque a biblioteca é síncrona e o download demora.
    Devolve (caminho, erro). Não chame direto: use baixar_video().
    """
    modelo = os.path.join(pasta, "video.%(ext)s")
    comando = [
        "/home/ubuntu/shopee/venv/bin/yt-dlp",
        # 🎬 'best' sozinho exige vídeo E áudio no MESMO arquivo. Quando o site
        # serve streams separados (HLS), os três fallbacks antigos falhavam em
        # cascata -> 'Requested format is not available'. As entradas com bv*+ba
        # cobrem esse caso juntando os dois com ffmpeg.
        "-f", (f"b[height<={ALTURA_MAXIMA}][ext=mp4]/b[height<={ALTURA_MAXIMA}]/"
               f"bv*[height<={ALTURA_MAXIMA}]+ba/b/bv*+ba/bv*"),
        "--merge-output-format", "mp4",
        "--no-playlist",              # link de perfil não vira 200 downloads
        "--no-warnings",
        "--socket-timeout", "30",
        "--max-filesize", f"{LIMITE_TELEGRAM_MB}M",
        "-o", modelo,
        url,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *comando,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _saida, erro = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_DOWNLOAD_SEG)
        except asyncio.TimeoutError:
            proc.kill()
            return None, "o download passou de 3 minutos"

        if proc.returncode != 0:
            msg = (erro or b"").decode(errors="ignore")
            if "max-filesize" in msg or "larger than" in msg:
                return None, f"o vídeo passa de {LIMITE_TELEGRAM_MB} MB"
            if "Private" in msg or "login" in msg.lower():
                return None, "o vídeo é privado ou exige login"
            if "Unsupported URL" in msg:
                return None, "este link não é suportado"
            # 🎬 Formato indisponível não muda com retentativa: 3 tentativas só
            # fazem a pessoa esperar 15s para receber o mesmo erro.
            if "Requested format is not available" in msg:
                if EXIBIR_LOGS:
                    logger.error(f"🎬 Sem formato de vídeo utilizável em {url}\n{msg.strip()[-400:]}")
                return None, "esse link não tem vídeo, só imagem"
            # 🚦 Limite de requisições: é temporário, mas 3s de espera não resolve.
            if any(t in msg.lower() for t in ("http error 429", "too many requests",
                                              "rate-limit", "rate limit")):
                return None, "o site limitou os pedidos por excesso de acessos"
            # 🔍 Sem isso o motivo real some e não dá para investigar depois.
            if EXIBIR_LOGS:
                logger.error(f"❌ yt-dlp saiu com código {proc.returncode} em {url}\n{msg.strip()[-600:]}")
            return None, "não consegui acessar esse vídeo"

        for nome in sorted(os.listdir(pasta)):
            # ⚠️ Sobra de tentativa anterior: enviar isso entrega vídeo corrompido.
            if nome.endswith((".part", ".ytdl", ".temp")):
                continue
            caminho = os.path.join(pasta, nome)
            if os.path.isfile(caminho) and os.path.getsize(caminho) > 0:
                return caminho, None
        return None, "o download não gerou arquivo"

    except FileNotFoundError:
        return None, "o yt-dlp não está instalado no servidor"
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro inesperado no download: {e}")
        return None, "erro inesperado ao baixar"

# 🔁 O TikTok derruba pedidos vindos de servidor de forma aleatória: o MESMO
# link falha agora e funciona 5s depois. Sem retentativa, o usuário leva um
# "não deu certo" que não é culpa dele nem do link.
ERROS_QUE_MERECEM_NOVA_TENTATIVA = (
    "não consegui acessar esse vídeo",
    "o download não gerou arquivo",
    "erro inesperado ao baixar",
    "o site limitou os pedidos por excesso de acessos",
)

async def baixar_video(url, pasta, tentativas=3):
    """Tenta até 3 vezes com espera crescente. Erro definitivo sai na hora."""
    ultimo_erro = None
    for n in range(1, tentativas + 1):
        caminho, erro = await _baixar_video_uma_vez(url, pasta)
        if not erro:
            if n > 1 and EXIBIR_LOGS:
                logger.info(f"✅ Deu certo na tentativa {n}/{tentativas}: {url}")
            return caminho, None

        ultimo_erro = erro
        if erro not in ERROS_QUE_MERECEM_NOVA_TENTATIVA:
            return None, erro

        if n < tentativas:
            # 🚦 Bloqueio por excesso de acesso não passa em 3s. Espera bem mais.
            espera = (30 * n) if "limitou os pedidos" in erro else (3 * n)
            if EXIBIR_LOGS:
                logger.warning(f"🔁 Tentativa {n}/{tentativas} falhou ({erro}). Repetindo em {espera}s...")
            for lixo in os.listdir(pasta):
                try: os.remove(os.path.join(pasta, lixo))
                except Exception: pass
            await asyncio.sleep(espera)

    return None, ultimo_erro

def detectar_plataforma(texto):
    """Devolve (plataforma, url) do primeiro link reconhecido, ou (None, None)."""
    for nome, padrao in PADROES_SUPORTADOS.items():
        achado = re.search(padrao, texto or "", re.IGNORECASE)
        if achado:
            url = achado.group(0).rstrip(").,;!?")
            if not url.lower().startswith("http"):
                url = "https://" + url
            return nome, url
    return None, None

def mencao_usuario(user):
    """No tópico há muita conversa: sem o @, ninguém sabe de quem é o vídeo."""
    if getattr(user, "username", None):
        return f"@{user.username}"
    nome = getattr(user, "first_name", None) or "Membro"
    return f"<a href='tg://user?id={user.id}'>{nome}</a>"

async def canais_faltantes(user_id):
    """Canais em que a pessoa NÃO está. Lista vazia = acesso liberado."""
    faltando = []
    for chat_id, nome, link in CANAIS_OBRIGATORIOS:
        try:
            membro = await bot.get_chat_member(chat_id, user_id)
            if membro.status in ("left", "kicked"):
                faltando.append((nome, link))
        except Exception as e:
            # Falha nossa não pode punir quem talvez já esteja no canal.
            if EXIBIR_LOGS: logger.warning(f"⚠️ Não consegui verificar {nome}: {e}")
    return faltando

# 🔗 Guarda o link que a pessoa mandou enquanto ela cumpre as etapas, para
# que o download comece sozinho depois. Some se o serviço reiniciar — nesse
# caso ela só manda o link de novo.
LINKS_PENDENTES = {}

# 🔔 Aviso de trava aberto no momento, por usuário. Sem isto o evento de entrada
# no canal chega mas o bot não sabe qual mensagem repintar.
GATES_ABERTOS = {}


def teclado_entrar(faltando, user_id):
    """Cumpridos viram ✅ e param de ser clicáveis; os que faltam seguem com o link."""
    nomes_faltando = {nome for nome, _ in faltando}
    linhas = []

    for _, nome, link in CANAIS_OBRIGATORIOS:
        if nome in nomes_faltando:
            linhas.append([InlineKeyboardButton(text=f"➕ Entrar no {nome}", url=link)])
        else:
            linhas.append([InlineKeyboardButton(text=f"✅ {nome}", callback_data="canal_ok")])

    linhas.append([InlineKeyboardButton(text="🔄 Já entrei — verificar",
                                        callback_data=f"verificar:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=linhas)

# ⏳ Quanto tempo o aviso de trava fica no tópico antes de sumir sozinho.
EXPIRACAO_AVISO_TRAVA_SEG = 180


async def expirar_aviso_trava(user_id, msg_id):
    await asyncio.sleep(EXPIRACAO_AVISO_TRAVA_SEG)

    # Já foi resolvido ou substituído por outro aviso? Não mexe.
    aviso = GATES_ABERTOS.get(user_id)
    if not aviso or aviso.message_id != msg_id:
        return

    GATES_ABERTOS.pop(user_id, None)
    LINKS_PENDENTES.pop(user_id, None)
    try: await aviso.delete()
    except Exception: pass
    if EXIBIR_LOGS: logger.info(f"⏳ Aviso de trava de {user_id} expirou e foi removido.")

# ⏳ Respiro antes de apagar o link original. Sumir no mesmo instante da entrega
# dá a impressão de que algo deu errado.
ATRASO_APAGAR_LINK_SEG = 3


async def apagar_link_original(message):
    await asyncio.sleep(ATRASO_APAGAR_LINK_SEG)
    try: await message.delete()
    except Exception: pass

# ⏳ O aviso de cota estourada não fica exposto no tópico: quanto menos gente
# souber que existe limite, menos gente tenta contornar.
EXPIRACAO_AVISO_LIMITE_SEG = 180


async def expirar_aviso_limite(aviso, link_original=None):
    await asyncio.sleep(EXPIRACAO_AVISO_LIMITE_SEG)
    try: await aviso.delete()
    except Exception: pass
    # Sem o aviso, o link solto vira lixo no tópico. Vai junto.
    if link_original is not None:
        try: await link_original.delete()
        except Exception: pass
    if EXIBIR_LOGS: logger.info("⏳ Aviso de limite diário expirou e foi removido do tópico.")

@router.message(F.chat.id == GRUPO_DOWNLOADER, F.message_thread_id == TOPICO_DOWNLOADER)
async def receber_link(message: types.Message):
    # 🧹 Anota TODA mensagem que entra no tópico, inclusive as que serão
    # ignoradas logo abaixo. O que não for anotado aqui a faxina nunca acha.
    registrar_mensagem(message.message_id)

    # 📌 Aviso de serviço "fixou uma mensagem": não interessa a ninguém, some.
    # Precisa vir ANTES do teste de is_bot, senão o return abaixo o deixa passar.
    if message.pinned_message:
        try: await message.delete()
        except Exception: pass
        return

    if message.from_user.is_bot:
        return

    plataforma, url = detectar_plataforma(message.text or message.caption or "")
    mencao = mencao_usuario(message.from_user)

    # 1️⃣ Não é link reconhecido: orienta e some
    if not url:
        # 📎 Arquivo no lugar do link é um caso diferente de recado solto: a pessoa
        # acha que mandou "o vídeo" e não entende por que o bot pediu link de novo.
        tem_midia = bool(message.video or message.photo or message.document
                         or message.animation or message.video_note or message.sticker)

        if tem_midia:
            texto_aviso = (
                f"📎 {mencao}, não consigo trabalhar com o <b>arquivo</b> — preciso do "
                "<b>link</b> de onde o vídeo está publicado.\n\n"
                "No app: abra o vídeo → <b>Compartilhar</b> → <b>Copiar link</b> → cole aqui."
            )
            segundos = 25
        else:
            texto_aviso = (
                f"👋 {mencao}, cole aqui o <b>link do vídeo</b> que você quer baixar.\n\n"
                "Aceito por enquanto:\n"
                "🔶 Shopee  ·  ⬛ TikTok  ·  📌 Pinterest  ·  📸 Instagram"
            )
            segundos = 20

        aviso = await message.answer(texto_aviso, parse_mode="HTML")

        # 🧹 A mensagem que não é link sai NA HORA. Antes só o aviso do bot sumia e
        # o arquivo ficava até a faxina de DIAS_RETENCAO_TOPICO passar, empurrando
        # o painel para cima o tempo todo.
        try:
            await message.delete()
        except Exception as e:
            if EXIBIR_LOGS:
                logger.warning(f"⚠️ Não apaguei a mensagem sem link de {message.from_user.id}: {e}. "
                               f"Confira se o bot tem a permissão 'Apagar mensagens' no grupo.")

        # O aviso fica um pouco mais para a pessoa ler, depois some também.
        await asyncio.sleep(segundos)
        try: await aviso.delete()
        except Exception: pass
        return

    # 2️⃣ Trava de acesso
    # 🎁 Cortesia: os primeiros downloads saem livres, sem pedir nada.
    ja_baixou = downloads_totais(message.from_user.id)
    faltando = await canais_faltantes(message.from_user.id) if ja_baixou >= DOWNLOADS_CORTESIA else []

    if faltando:
        lista = "\n".join(f"• {nome}" for nome, _ in faltando)
        # Segura o link: quando ela clicar em verificar, o download sai sozinho.
        LINKS_PENDENTES[message.from_user.id] = message
        aviso_trava = await message.answer(
            f"🎁 {mencao}, seus <b>{DOWNLOADS_CORTESIA} downloads de cortesia</b> acabaram.\n\n"
            f"Para continuar baixando, entre nos nossos canais:\n{lista}\n\n"
            "<b>Depois disso é liberado para sempre</b> — sem pagar nada, sem assinatura, "
            "sem limite de tempo.\n\n"
            "<i>Entre pelos botões abaixo e toque em «Já entrei». Seu link fica guardado.</i>",
            parse_mode="HTML", reply_markup=teclado_entrar(faltando, message.from_user.id)
        )
        GATES_ABERTOS[message.from_user.id] = aviso_trava
        if EXIBIR_LOGS: logger.info(f"🔒 {message.from_user.id} bloqueado: falta {len(faltando)} canal(is).")

        # ⏳ Desistiu? O aviso não fica encalhado no tópico. Se ela entrar nos canais
        # nesse meio-tempo, o fluxo normal já terá apagado e o GATES_ABERTOS estará
        # limpo — por isso a conferência antes de remover.
        asyncio.create_task(expirar_aviso_trava(message.from_user.id, aviso_trava.message_id))
        return

    # 3️⃣ Limite diário
    usados = downloads_hoje(message.from_user.id)
    if usados >= LIMITE_DIARIO_DOWNLOADS and message.from_user.id not in IDS_SEM_LIMITE:
        aviso_limite = await message.answer(
            f"📦 {mencao}, você já baixou <b>{usados} vídeos hoje</b> e atingiu o limite diário.\n\n"
            f"<b>Cada membro pode baixar até {LIMITE_DIARIO_DOWNLOADS} vídeos por dia.</b>\n"
            "<i>Sua cota volta a zerar à meia-noite. Até lá!</i>",
            parse_mode="HTML"
        )
        if EXIBIR_LOGS: logger.info(f"📦 {message.from_user.id} atingiu o limite ({usados}).")
        asyncio.create_task(expirar_aviso_limite(aviso_limite, message))
        return

    # 4️⃣ Liberado — baixa e entrega
    if EXIBIR_LOGS: logger.info(f"✅ {message.from_user.id} liberado ({usados}/{LIMITE_DIARIO_DOWNLOADS}). {plataforma}: {url}")

    if semaforo_download.locked():
        aguarde = await message.answer(f"⏳ {mencao}, tem outro vídeo baixando. Você é o próximo!")
    else:
        aguarde = None

    # ♻️ Alguém já pediu este vídeo? Entrega na hora, sem baixar de novo.
    file_id_guardado = buscar_cache_video(url)
    if file_id_guardado:
        # Veio do cache: não há fila para esperar, o aviso perde o sentido.
        if aguarde:
            try: await aguarde.delete()
            except Exception: pass
            aguarde = None
        try:
            await message.answer_video(
                video=file_id_guardado,
                caption=f"📥 Vídeo solicitado por: {mencao}\n\n🔗 <b>Link:</b>\n{url}",
                parse_mode="HTML"
            )
            registrar_download(message.from_user.id)
            somar_download_total(message.from_user.id)

            # 💡 Momento de maior boa vontade: acabou de receber o vídeo.
            asyncio.create_task(convidar_para_comunidade(
                message, mencao, downloads_totais(message.from_user.id)))

            # 🧹 Mesmo raciocínio da entrega normal: o link original vira ruído.
            asyncio.create_task(apagar_link_original(message))

            if EXIBIR_LOGS: logger.info(f"♻️ Entregue do cache para {message.from_user.id} ({plataforma}).")

            # 📌 O painel também desce quando a entrega vem do cache. Sem isto ele
            # só acompanha os downloads reais e fica para trás nas repetições.
            agendar_painel()
            return
        except Exception as e:
            # file_id expirou ou foi invalidado: apaga do cache e baixa normalmente
            if EXIBIR_LOGS: logger.warning(f"⚠️ file_id do cache falhou ({e}). Rebaixando.")
            remover_cache_video(url)

    async with semaforo_download:
        if aguarde:
            try: await aguarde.delete()
            except Exception: pass

        status = await message.answer(f"⏬ {mencao}, baixando o seu vídeo do <b>{plataforma}</b>...", parse_mode="HTML")
        url_pedido = url                      # o que o usuário colou, para mostrar na legenda
        url = await expandir_encurtador(url)  # o que o downloader vai usar
        pasta = tempfile.mkdtemp(dir=PASTA_TEMP_DOWNLOAD)

        try:
            if plataforma == "Shopee":
                caminho, erro = await baixar_video_shopee(url, pasta)
            else:
                caminho, erro = await baixar_video(url, pasta)

            # 🧼 Tira a marca queimada e a cartela final do render da Shopee.
            if not erro and caminho and plataforma == "Shopee" and LIMPAR_VIDEO_SHOPEE:
                caminho = await limpar_video_shopee(caminho, pasta)

            if erro:
                await status.edit_text(
                    f"❌ {mencao}, não deu certo: <b>{erro}</b>.\n\n"
                    "<i>Confira se o link está certo e se o vídeo é público.</i>",
                    parse_mode="HTML"
                )
                return

            legenda = (
                f"📥 Vídeo solicitado por: {mencao}\n\n"
                f"🔗 <b>Link:</b>\n{url_pedido}"
            )
            enviado = await message.answer_video(
                video=FSInputFile(caminho),
                caption=legenda,
                parse_mode="HTML"
            )
            # ♻️ Guarda o id para quem pedir o mesmo link depois
            if enviado and enviado.video:
                guardar_cache_video(url_pedido, enviado.video.file_id, plataforma)

            try: await status.delete()
            except Exception: pass

            # ✅ Só conta o que foi entregue: falha não gasta a cota de ninguém
            registrar_download(message.from_user.id)
            somar_download_total(message.from_user.id)

            # 💡 Momento de maior boa vontade: acabou de receber o vídeo.
            asyncio.create_task(convidar_para_comunidade(
                message, mencao, downloads_totais(message.from_user.id)))

            # 🧹 O link que a pessoa colou já cumpriu o papel: a legenda do vídeo
            # traz ele de volta, bem mais organizado. Só apaga DEPOIS da entrega,
            # senão uma falha no download deixaria ela sem o link. O atraso evita
            # o susto de ver a própria mensagem sumir no mesmo instante.
            asyncio.create_task(apagar_link_original(message))

            restantes = LIMITE_DIARIO_DOWNLOADS - downloads_hoje(message.from_user.id)
            if restantes <= 3 and message.from_user.id not in IDS_SEM_LIMITE:
                aviso_cota = await message.answer(
                    f"📦 {mencao}, restam <b>{restantes}</b> download(s) hoje "
                    f"(limite de {LIMITE_DIARIO_DOWNLOADS} por dia).",
                    parse_mode="HTML"
                )
                await asyncio.sleep(30)
                try: await aviso_cota.delete()
                except Exception: pass

            if EXIBIR_LOGS: logger.info(f"📤 Vídeo entregue para {message.from_user.id} ({plataforma}).")

            # 📌 Marca o painel para descer daqui a 3 min, não na hora.
            agendar_painel()

        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Falha ao entregar: {e}")
            try:
                await status.edit_text(f"❌ {mencao}, algo deu errado no envio. Tente de novo.")
            except Exception: pass
        finally:
            # 🧹 Nada fica no servidor: apaga a pasta inteira, dê certo ou não.
            shutil.rmtree(pasta, ignore_errors=True)

# 📌 Mantém o painel SEMPRE como a última mensagem do tópico. Envia o novo
# primeiro e só então apaga o antigo, para o tópico nunca ficar sem painel.
# Não usa pin_chat_message de propósito: cada fixação gera uma mensagem de
# serviço ("Fulano fixou...") que se acumula no tópico.
_lock_painel = asyncio.Lock()

@router.callback_query(F.data == "canal_ok")
async def canal_ja_cumprido(callback: types.CallbackQuery):
    await callback.answer("Esse já está cumprido ✅")


@router.callback_query(F.data.startswith("verificar:"))
async def verificar_canais(callback: types.CallbackQuery):
    # 🔒 Só o dono do aviso mexe no próprio aviso.
    dono_id = int(callback.data.split(":")[1])
    if callback.from_user.id != dono_id:
        await callback.answer("Este aviso é de outra pessoa.", show_alert=True)
        return

    faltando = await canais_faltantes(dono_id)
    if faltando:
        nomes = ", ".join(nome for nome, _ in faltando)
        await callback.answer(f"Ainda falta: {nomes}", show_alert=True)
    else:
        await callback.answer("Liberado! Baixando seu vídeo…")

    # O botão vira rede de segurança: faz o mesmo que o evento automático,
    # para quando o bot não é admin do canal ou o evento se perde.
    GATES_ABERTOS.setdefault(dono_id, callback.message)
    await concluir_liberacao(dono_id)

async def concluir_liberacao(user_id):
    """Repinta o aviso ou, se tudo foi cumprido, apaga e solta o download."""
    aviso = GATES_ABERTOS.get(user_id)
    if not aviso:
        return

    faltando = await canais_faltantes(user_id)

    if faltando:
        try:
            await aviso.edit_reply_markup(reply_markup=teclado_entrar(faltando, user_id))
        except Exception:
            pass   # Teclado idêntico ao anterior; o Telegram recusa a edição
        return

    GATES_ABERTOS.pop(user_id, None)
    try: await aviso.delete()
    except Exception: pass

    original = LINKS_PENDENTES.pop(user_id, None)
    if original:
        await receber_link(original)


@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> IS_MEMBER))
async def entrou_em_canal(evento: types.ChatMemberUpdated):
    # 🔔 Só interessa entrada nos canais da trava, e só de quem tem aviso aberto.
    if evento.chat.id not in {cid for cid, _, _ in CANAIS_OBRIGATORIOS}:
        return

    user_id = evento.new_chat_member.user.id
    tem_gate = user_id in GATES_ABERTOS
    if EXIBIR_LOGS:
        logger.info(f"🔔 {user_id} entrou em {evento.chat.title} "
                    f"(aviso aberto: {'sim' if tem_gate else 'não'}).")

    if not tem_gate:
        return

    await concluir_liberacao(user_id)


async def reenviar_painel_downloader():
    async with _lock_painel:
        try:
            nova = await bot.send_message(
                chat_id=GRUPO_DOWNLOADER,
                text=TEXTO_PAINEL_DOWNLOADER,
                parse_mode="HTML",
                message_thread_id=TOPICO_DOWNLOADER,
                disable_notification=True,
                disable_web_page_preview=True
            )
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ [Painel] Falha ao enviar o painel: {e}")
            return

        antiga = ler_msg_painel()
        if antiga and antiga != nova.message_id:
            try: await bot.delete_message(chat_id=GRUPO_DOWNLOADER, message_id=antiga)
            except Exception: pass

        # 📌 Fixa no topo do tópico. Sem notificação, para não tocar sino em ninguém.
        # O pin antigo cai sozinho quando a mensagem anterior é apagada acima.
        try:
            await bot.pin_chat_message(
                chat_id=GRUPO_DOWNLOADER,
                message_id=nova.message_id,
                disable_notification=True
            )
        except Exception as e:
            if EXIBIR_LOGS: logger.warning(f"⚠️ [Painel] Não consegui fixar: {e}")

        salvar_msg_painel(nova.message_id)
        if EXIBIR_LOGS: logger.info(f"📌 [Painel] Painel recriado no fim do tópico (ID {nova.message_id}).")

# ⏳ Prazo antes do painel descer. Numa rajada de downloads ele desce UMA vez,
# no fim do prazo, em vez de pular de lugar a cada vídeo entregue.
ATRASO_PAINEL_SEG = 180

_painel_agendado = None


async def _painel_depois_do_prazo():
    try:
        await asyncio.sleep(ATRASO_PAINEL_SEG)
        await reenviar_painel_downloader()
    except asyncio.CancelledError:
        pass
    finally:
        global _painel_agendado
        _painel_agendado = None


def agendar_painel():
    """Marca o painel para descer daqui a 3 min. Se já houver um agendamento em
    curso, não reinicia a contagem — senão, com entregas seguidas a cada 2 min,
    o prazo se renovaria para sempre e o painel nunca desceria."""
    global _painel_agendado
    if _painel_agendado and not _painel_agendado.done():
        return
    _painel_agendado = asyncio.create_task(_painel_depois_do_prazo())


@router.message(Command("painel_downloader"))
async def comando_painel_downloader(message: types.Message):
    if message.from_user.id not in IDS_SEM_LIMITE:
        return
    await reenviar_painel_downloader()
    try: await message.delete()
    except Exception: pass

# 🧹 Um único gancho para TUDO que o bot envia. Sem isto eu teria que
# lembrar de anotar o ID em cada send_message/answer_video espalhado no arquivo.
@bot.session.middleware()
async def registrar_saidas(make_request, bot_, method, *args, **kwargs):
    resultado = await make_request(bot_, method, *args, **kwargs)
    try:
        if (isinstance(resultado, types.Message)
                and resultado.chat.id == GRUPO_DOWNLOADER
                and resultado.message_thread_id == TOPICO_DOWNLOADER):
            registrar_mensagem(resultado.message_id)
    except Exception:
        pass
    return resultado


async def faxina_topico_loop():
    """De hora em hora, apaga o que passou de DIAS_RETENCAO_TOPICO dias."""
    await asyncio.sleep(120)   # deixa o bot terminar de subir
    while True:
        try:
            vencidas = mensagens_vencidas()
            if vencidas:
                painel_atual = ler_msg_painel()
                apagou_painel = False
                sucesso = 0
                falhou = 0

                for msg_id in vencidas:
                    try:
                        await bot.delete_message(chat_id=GRUPO_DOWNLOADER, message_id=msg_id)
                        sucesso += 1
                        if painel_atual and msg_id == painel_atual:
                            apagou_painel = True
                    except Exception:
                        # Já apagada, ou a API recusou por idade. De qualquer forma
                        # sai do registro: insistir todo ciclo só gastaria chamada.
                        falhou += 1
                    await asyncio.sleep(0.4)   # folga para não levar flood wait

                esquecer_mensagens(vencidas)
                if EXIBIR_LOGS:
                    logger.info(f"🧹 [Faxina Tópico] {sucesso} apagada(s), {falhou} recusada(s) pela API.")

                # O painel foi junto? Recria, senão o tópico fica sem orientação.
                if apagou_painel:
                    await reenviar_painel_downloader()

        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Erro na faxina do tópico: {e}")

        await asyncio.sleep(3600)


async def main():
    if not TOKEN:
        logger.error("❌ TELEGRAM_TOKEN_DOWNLOADER não encontrado no .env. Encerrando.")
        return
    dp.include_router(router)
    me = await bot.get_me()
    logger.info(f"📥 Downloader no ar como @{me.username} "
                f"(privacy {'desligado ✅' if me.can_read_all_group_messages else 'LIGADO ⚠️'})")
# Inicia a rotina autônoma de manutenção (Limpeza de BD e Update do yt-dlp)
    asyncio.create_task(faxina_diaria_loop())

    # 🧹 Faxina do tópico: apaga mensagens com mais de 3 dias.
    asyncio.create_task(faxina_topico_loop())

    # 📌 Garante que o painel exista no tópico assim que o serviço sobe.
    asyncio.create_task(reenviar_painel_downloader())

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
