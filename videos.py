"""
Arquivo de vídeo tratado do mesmo jeito em todos os robôs: medir a resolução
(ffprobe), subir para 720p o vídeo pequeno antes de postar e a assinatura SHA-256 que
reconhece o mesmo vídeo. Usado pelo Espião e pelo Espelhador (motor_userbot), pelos
Autorais (espelhador_videos_autorais, pelo repetidos_publico) e pelo Baixador
(downloader_bot, só a medição). Os quadros espalhados do vídeo (quadros) vão nos casos
das falhas do robô da Shopee Vídeo (casos_robo). A foto do produto no começo, com a
miniatura e a seta por cima (com_foto_e_miniatura), é a edição dos vídeos do Rafael
(edicao_video).

Um lugar só para que um ajuste no tratamento valha para todos os canais
(DECISOES.md, Código e manutenção).
"""
import asyncio
import hashlib
import logging
import os
import subprocess
import tempfile

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


def quadros(caminho, pasta, quantos=4, largura=360, timeout=20):
    """
    Grava em pasta quantos quadros do vídeo (quadro_1.jpg...), espalhados do começo ao fim,
    com essa largura. Devolve quantos saíram; vídeo que não abre dá 0, sem erro.
    """
    try:
        duracao = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", caminho],
            capture_output=True, text=True, timeout=timeout).stdout.strip() or 0)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0
    feitos = 0
    for i in range(quantos if duracao > 0 else 0):
        destino = os.path.join(pasta, f"quadro_{i + 1}.jpg")
        try:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{duracao * (i + 0.5) / quantos:.2f}", "-i", caminho,
                            "-frames:v", "1", "-vf", f"scale={largura}:-2", destino],
                           capture_output=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            continue
        feitos += os.path.exists(destino)
    return feitos


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


def imagem_abre(caminho):
    """A imagem abre no ffmpeg? Uma que não abre, repetida em laço, prende o ffmpeg até o tempo acabar."""
    try:
        saida = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width", "-of", "csv=p=0",
             caminho], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    largura = saida.stdout.strip().splitlines()[0] if saida.stdout.strip() else ""
    return saida.returncode == 0 and largura.isdigit() and int(largura) > 0


def tem_audio(caminho):
    try:
        saida = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0",
             caminho], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(saida.strip())


QUADROS_POR_SEGUNDO = 30


def comando_foto_e_miniatura(foto, video, destino, segundos, miniatura, centro, com_audio, seta=None,
                             centro_seta=None):
    """
    O ffmpeg da edição: a foto em tela cheia (fundo branco) por `segundos`, depois o vídeo
    em 720x1280 com a foto em miniatura (`miniatura` px de largura) com o centro em
    `centro` (x, y) e, com `seta` (uma imagem com fundo transparente), a seta com o centro em
    `centro_seta`, as duas até o fim do vídeo. O som do vídeo começa depois da foto, que vai
    em silêncio; vídeo sem som sai sem som.
    """
    tela = f"{FILTRO_720P},setsar=1,fps={QUADROS_POR_SEGUNDO},format=yuv420p"
    filtro = (f"[0:v]{tela.replace('color=black', 'color=white')}[foto];"
              f"[1:v]{tela}[corpo];"
              f"[2:v]scale={miniatura}:-2[mini];"
              f"[corpo][mini]overlay=x={centro[0]}-w/2:y={centro[1]}-h/2:shortest=1[comfoto];")
    entradas = ["-loop", "1", "-t", str(segundos), "-i", foto, "-i", video, "-loop", "1", "-i", foto]
    if seta:
        entradas += ["-loop", "1", "-i", seta]
        filtro += (f"[comfoto][3:v]overlay=x={centro_seta[0]}-w/2:y={centro_seta[1]}-h/2:shortest=1[editado];"
                   "[foto][editado]concat=n=2:v=1:a=0[v]")
    else:
        filtro += "[foto][comfoto]concat=n=2:v=1:a=0[v]"
    saida = ["-map", "[v]"]
    if com_audio:
        silencio = 4 if seta else 3
        entradas += ["-f", "lavfi", "-t", str(segundos), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        filtro += (";[1:a]aresample=44100,aformat=channel_layouts=stereo[som];"
                   f"[{silencio}:a][som]concat=n=2:v=0:a=1[a]")
        saida += ["-map", "[a]", "-c:a", "aac", "-b:a", "128k"]
    return (["ffmpeg", "-v", "error", "-y"] + entradas + ["-filter_complex", filtro] + saida
            + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-movflags", "+faststart", destino])


def com_foto_e_miniatura(video, foto, destino, segundos=2, miniatura=180, centro=(576, 128), seta=None,
                         centro_seta=None, espera=300):
    """
    Grava em destino o vídeo com a foto (bytes) no começo e em miniatura por cima, e a seta
    (caminho de uma imagem com fundo transparente), se vier. Devolve "" quando deu certo, ou
    o motivo fixo de não ter dado (o destino não fica pela metade).
    """
    if not foto:
        return "a foto do anúncio não veio"
    # Ao lado do destino: o os.replace no fim não atravessa disco.
    with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(destino))) as pasta:
        caminho_da_foto = os.path.join(pasta, "foto.jpg")
        with open(caminho_da_foto, "wb") as arquivo:
            arquivo.write(foto)
        if not imagem_abre(caminho_da_foto):
            return "a foto do anúncio não é uma imagem que abre"
        temporario = os.path.join(pasta, "editado.mp4")
        comando = comando_foto_e_miniatura(caminho_da_foto, video, temporario, segundos, miniatura, centro,
                                           tem_audio(video), seta, centro_seta)
        try:
            feito = subprocess.run(comando, capture_output=True, timeout=espera)
        except subprocess.TimeoutExpired:
            return f"o ffmpeg passou de {espera // 60} min"
        except OSError:
            return "o ffmpeg não abriu"
        if feito.returncode != 0 or not os.path.exists(temporario) or not os.path.getsize(temporario):
            return f"o ffmpeg falhou (código {feito.returncode})"
        os.replace(temporario, destino)
    return ""


def calcular_hash_video(caminho_arquivo):
    """SHA-256 do arquivo (identifica o mesmo vídeo em qualquer canal), ou None se não der para ler."""
    hash_sha256 = hashlib.sha256()
    try:
        with open(caminho_arquivo, "rb") as f:
            for bloco in iter(lambda: f.read(65536), b""):
                hash_sha256.update(bloco)
        return hash_sha256.hexdigest()
    except Exception as e:
        logger.error(f"❌ Erro na leitura física para calcular hash do ficheiro {caminho_arquivo}: {e}")
        return None
