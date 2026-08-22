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

async def faxina_diaria_loop():
    """Uma vez por dia, poda a tabela de contagem."""
    while True:
        await asyncio.sleep(86400)
        limpar_downloads_antigos()

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

async def baixar_video(url, pasta):
    """
    Roda o yt-dlp em SUBPROCESSO. Chamar direto travaria o bot inteiro,
    porque a biblioteca é síncrona e o download demora.
    Devolve (caminho, erro).
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
            return None, "não consegui acessar esse vídeo"

        for nome in os.listdir(pasta):
            caminho = os.path.join(pasta, nome)
            if os.path.isfile(caminho) and os.path.getsize(caminho) > 0:
                return caminho, None
        return None, "o download não gerou arquivo"

    except FileNotFoundError:
        return None, "o yt-dlp não está instalado no servidor"
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro inesperado no download: {e}")
        return None, "erro inesperado ao baixar"

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

    async with semaforo_download:
        if aguarde:
            try: await aguarde.delete()
            except Exception: pass

        status = await message.answer(f"⏬ {mencao}, baixando o seu vídeo do <b>{plataforma}</b>...", parse_mode="HTML")
        url = await expandir_encurtador(url)
        pasta = tempfile.mkdtemp(dir=PASTA_TEMP_DOWNLOAD)

        try:
            caminho, erro = await baixar_video(url, pasta)

            if erro:
                await status.edit_text(
                    f"❌ {mencao}, não deu certo: <b>{erro}</b>.\n\n"
                    "<i>Confira se o link está certo e se o vídeo é público.</i>",
                    parse_mode="HTML"
                )
                return

            legenda = (
                f"📥 Vídeo de {mencao}\n\n"
                f"🔗 <b>Link original:</b>\n{url}"
            )
            await message.answer_video(
                video=FSInputFile(caminho),
                caption=legenda,
                parse_mode="HTML"
            )
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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
