"""
Arquivo de vídeo tratado do mesmo jeito em todos os robôs: medir a resolução
(ffprobe) e subir para 720p o vídeo pequeno antes de postar. Usado pelo Espião e
pelo Espelhador (motor_userbot), pelos Autorais (espelhador_videos_autorais) e pelo
Baixador (downloader_bot, só a medição).

Um lugar só para que um ajuste no tratamento valha para todos os canais
(DECISOES.md, Código e manutenção).
"""
import asyncio
import logging
import os

logger = logging.getLogger("Videos")

# Vídeo com o lado menor abaixo disto é re-renderizado em 720x1280, com bordas pretas
# no que sobrar, para não sair borrado no Telegram.
LADO_MINIMO = 720
FILTRO_720P = "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black"


async def dimensoes(caminho, timeout=None):
    """
    (largura, altura) do vídeo pelo ffprobe, ou (None, None) se não der para ler.
    Com timeout (segundos), encerra o ffprobe que passar disso e devolve (None, None).
    """
    try:
        processo = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", caminho,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except OSError:
        return None, None
    try:
        saida, _ = await asyncio.wait_for(processo.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        processo.kill()
        return None, None
    if processo.returncode != 0:
        return None, None
    try:
        largura, altura = saida.decode().strip().splitlines()[0].split("x")[:2]
        return int(largura), int(altura)
    except (ValueError, IndexError):
        return None, None


async def verificar_e_otimizar_video(caminho_video, relatorio=None):
    """
    Vídeo com o lado menor abaixo de 720 px é re-renderizado para 720x1280 e substitui
    o original no mesmo caminho, que é sempre o devolvido. Em qualquer falha, o arquivo
    fica como está.

    Como o caminho não muda, quem precisa saber se houve re-renderização passa um dict
    em `relatorio` e recebe relatorio["upscaled"] = True quando ela aconteceu.
    """
    if not caminho_video or not os.path.exists(caminho_video):
        return caminho_video

    try:
        logger.info(f"🔎 [Upscaling] Inspecionando resolução física de: {caminho_video}")
        largura, altura = await dimensoes(caminho_video)
        if not largura or not altura:
            logger.warning("⚠️ [Upscaling] Falha ao ler metadados. Ignorando otimização.")
            return caminho_video

        if min(largura, altura) >= LADO_MINIMO:
            logger.info(f"✅ [Upscaling] Qualidade aprovada ({largura}x{altura}). Nenhuma maquiagem necessária.")
            return caminho_video

        logger.info(f"🛠️ [Upscaling] Resolução baixa detectada ({largura}x{altura}). Iniciando renderização para 720p...")
        caminho_temp = f"{caminho_video}_upscaled.mp4"
        comando_ffmpeg = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", caminho_video,
            "-vf", FILTRO_720P,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "copy", caminho_temp,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await comando_ffmpeg.communicate()

        if comando_ffmpeg.returncode == 0 and os.path.exists(caminho_temp):
            os.replace(caminho_temp, caminho_video)
            if relatorio is not None:
                relatorio["upscaled"] = True
            logger.info("✨ [Upscaling] Sucesso! Vídeo re-renderizado para 720x1280 e substituído.")
        else:
            logger.error("❌ [Upscaling] Falha na renderização do FFmpeg. Mantendo arquivo original.")
            if os.path.exists(caminho_temp):
                os.remove(caminho_temp)

    except Exception as e:
        logger.error(f"❌ [Upscaling] Erro na função de otimização: {e}")

    return caminho_video
