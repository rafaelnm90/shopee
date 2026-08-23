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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# 🕐 Fuso travado no processo: o servidor roda em UTC.
os.environ['TZ'] = 'America/Sao_Paulo'
import time
time.tzset()

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage

if EXIBIR_LOGS:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    logger = logging.getLogger(__name__)

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
    (-1003909405581, "Acervo Afiliados Shopee", "https://t.me/shopee_video_afiliado"),
    (-1003932482573, "Acervo Viral Shopee",     "https://t.me/acervo_viral_shopee"),
    (-1003892378604, "Grupo Público",           "https://t.me/GrupoPublicoAfiliados"),
]

LIMITE_DIARIO_DOWNLOADS = 10

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

async def expandir_encurtador(url):
    """
    O pin.it redireciona para a home do Pinterest quando não parece um navegador.
    Sem os cabeçalhos certos, o yt-dlp recebe a página inicial e não acha vídeo.
    """
    if "pin.it" not in url.lower():
        return url
    try:
        import aiohttp
        cabecalhos = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
        async with aiohttp.ClientSession(headers=cabecalhos) as sessao:
            async with sessao.get(url, allow_redirects=True, timeout=15) as resposta:
                final = str(resposta.url)
                if "/pin/" in final:
                    if EXIBIR_LOGS: logger.info(f"🔗 pin.it expandido para {final}")
                    return final
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

            # 3. Engenharia Reversa: Captura o JSON de estado interno do App (matriz)
            link_mp4 = None
            match_json = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});\s*</script>', html, re.DOTALL)
            
            if match_json:
                try:
                    estado_interno = json.loads(match_json.group(1))
                    
                    # Função recursiva para varrer o JSON e isolar apenas URLs limpas
                    def buscar_video_limpo(dados):
                        if isinstance(dados, dict):
                            # Procura por chaves de vídeo conhecidas
                            chaves_limpas = ["playUrl", "play_url", "defaultVideoUrl", "videoUrl", "video_url", "url"]
                            for chave in chaves_limpas:
                                if chave in dados and isinstance(dados[chave], str) and dados[chave].startswith("http"):
                                    # 🛡️ TRAVA: A URL jamais pode conter a palavra watermark
                                    if "watermark" not in dados[chave].lower():
                                        return dados[chave]
                                        
                            # Continua a escavação nos sub-níveis
                            for k, v in dados.items():
                                if "watermark" in k.lower():
                                    continue # Isola e abandona nós contaminados
                                resultado = buscar_video_limpo(v)
                                if resultado: return resultado
                        elif isinstance(dados, list):
                            for item in dados:
                                resultado = buscar_video_limpo(item)
                                if resultado: return resultado
                        return None

                    link_mp4 = buscar_video_limpo(estado_interno)
                    if EXIBIR_LOGS and link_mp4: logger.info("🧠 Vídeo Matriz limpo extraído via JSON interno!")

                except Exception as e:
                    if EXIBIR_LOGS: logger.warning(f"⚠️ Erro ao decodificar a matriz interna da Shopee: {e}")

            # 4. Fallback de Segurança (Se o JSON estiver criptografado)
            if not link_mp4:
                PADROES_LIMPOS = [
                    r'"defaultVideoUrl"\s*:\s*"([^"]+)"',
                    r'"playUrl"\s*:\s*"([^"]+)"',
                    r'"play_url"\s*:\s*"([^"]+)"',
                    r'"videoUrl"\s*:\s*"([^"]+)"',
                    r'"video_url"\s*:\s*"([^"]+)"',
                ]
                for padrao in PADROES_LIMPOS:
                    achado = re.search(padrao, html)
                    if achado:
                        url_encontrada = achado.group(1).replace("\\u002F", "/").replace("\\/", "/")
                        # Trava dupla na Regex para garantir a rejeição do watermark
                        if url_encontrada.startswith("http") and "watermark" not in url_encontrada.lower():
                            link_mp4 = url_encontrada
                            if EXIBIR_LOGS: logger.info("🔍 Matriz limpa encontrada via varredura profunda (Regex)!")
                            break

            if not link_mp4:
                return None, ("não consegui extrair o vídeo limpo. "
                              "A Shopee ocultou o arquivo matriz original nesta página.")

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
        "-f", f"best[height<={ALTURA_MAXIMA}][ext=mp4]/best[height<={ALTURA_MAXIMA}]/best",
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

# 🔁 O TikTok/Instagram derruba pedidos vindos de servidor de forma aleatória:
# o MESMO link falha agora e funciona 5s depois. Sem retentativa, o usuário
# leva um "não deu certo" que não é culpa dele nem do link.
ERROS_QUE_MERECEM_NOVA_TENTATIVA = (
    "não consegui acessar esse vídeo",
    "o download não gerou arquivo",
    "erro inesperado ao baixar",
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
        # Vídeo privado, grande demais ou link não suportado: repetir não resolve.
        if erro not in ERROS_QUE_MERECEM_NOVA_TENTATIVA:
            return None, erro

        if n < tentativas:
            if EXIBIR_LOGS:
                logger.warning(f"🔁 Tentativa {n}/{tentativas} falhou ({erro}). Repetindo em {3 * n}s...")
            await asyncio.sleep(3 * n)

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

def teclado_entrar(faltando):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"➕ Entrar no {nome}", url=link)] for nome, link in faltando
    ])

@router.message(F.chat.id == GRUPO_DOWNLOADER, F.message_thread_id == TOPICO_DOWNLOADER)
async def receber_link(message: types.Message):
    if message.from_user.is_bot:
        return

    plataforma, url = detectar_plataforma(message.text or message.caption or "")
    mencao = mencao_usuario(message.from_user)

    # 1️⃣ Não é link reconhecido: orienta e some
    if not url:
        aviso = await message.answer(
            f"👋 {mencao}, cole aqui o <b>link do vídeo</b> que você quer baixar.\n\n"
            "Aceito por enquanto:\n"
            "🎵 TikTok  ·  📸 Instagram  ·  📌 Pinterest  ·  🛒 Shopee",
            parse_mode="HTML"
        )
        await asyncio.sleep(20)
        try: await aviso.delete()
        except Exception: pass
        return

    # 2️⃣ Trava de acesso
    faltando = await canais_faltantes(message.from_user.id)
    if faltando:
        lista = "\n".join(f"• {nome}" for nome, _ in faltando)
        await message.answer(
            f"🔒 {mencao}, para baixar vídeos você precisa estar nos nossos canais.\n\n"
            f"<b>Falta entrar em:</b>\n{lista}\n\n"
            "<i>Entre pelos botões abaixo e mande o link de novo. É de graça.</i>",
            parse_mode="HTML", reply_markup=teclado_entrar(faltando)
        )
        if EXIBIR_LOGS: logger.info(f"🔒 {message.from_user.id} bloqueado: falta {len(faltando)} canal(is).")
        return

    # 3️⃣ Limite diário
    usados = downloads_hoje(message.from_user.id)
    if usados >= LIMITE_DIARIO_DOWNLOADS:
        await message.answer(
            f"📦 {mencao}, você já baixou <b>{usados} vídeos hoje</b> e atingiu o limite diário.\n\n"
            f"<b>Cada membro pode baixar até {LIMITE_DIARIO_DOWNLOADS} vídeos por dia.</b>\n"
            "<i>Sua cota volta a zerar à meia-noite. Até lá!</i>",
            parse_mode="HTML"
        )
        if EXIBIR_LOGS: logger.info(f"📦 {message.from_user.id} atingiu o limite ({usados}).")
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
        try:
            await message.answer_video(
                video=file_id_guardado,
                caption=f"📥 Vídeo solicitado por: {mencao}\n\n🔗 <b>Link:</b>\n{url}",
                parse_mode="HTML"
            )
            registrar_download(message.from_user.id)
            if EXIBIR_LOGS: logger.info(f"♻️ Entregue do cache para {message.from_user.id} ({plataforma}).")
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
            restantes = LIMITE_DIARIO_DOWNLOADS - downloads_hoje(message.from_user.id)
            if restantes <= 3:
                aviso_cota = await message.answer(
                    f"📦 {mencao}, restam <b>{restantes}</b> download(s) hoje "
                    f"(limite de {LIMITE_DIARIO_DOWNLOADS} por dia).",
                    parse_mode="HTML"
                )
                await asyncio.sleep(30)
                try: await aviso_cota.delete()
                except Exception: pass

            if EXIBIR_LOGS: logger.info(f"📤 Vídeo entregue para {message.from_user.id} ({plataforma}).")

        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ Falha ao entregar: {e}")
            try:
                await status.edit_text(f"❌ {mencao}, algo deu errado no envio. Tente de novo.")
            except Exception: pass
        finally:
            # 🧹 Nada fica no servidor: apaga a pasta inteira, dê certo ou não.
            shutil.rmtree(pasta, ignore_errors=True)

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
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
