"""
Arquivo de vídeo tratado do mesmo jeito em todos os robôs: medir a resolução
(ffprobe), subir para 720p o vídeo pequeno antes de postar e a assinatura SHA-256 que
reconhece o mesmo vídeo. Usado pelo Espião e pelo Espelhador (motor_userbot), pelos
Autorais (espelhador_videos_autorais, pelo repetidos_publico) e pelo Baixador
(downloader_bot, só a medição). Os quadros espalhados do vídeo (quadros) vão nos casos
das falhas do robô da Shopee Vídeo (casos_robo). A foto do produto no começo, com a
miniatura e a seta por cima (com_foto_e_miniatura), é a edição dos vídeos do Rafael
(edicao_video); o vídeo remontado sem as partes paradas, com trechos acelerados ou em
câmera lenta e textos por cima (movimento, com_cortes_e_ritmo), é o Editor 2 dela. O vídeo
sem som nenhum (mudo) ganha uma música da Shopee na hora de postar (assistente_shopee_video).

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
# A música de fundo entra e sai devagar, em segundos.
ENTRADA_DA_MUSICA = 0.3
SAIDA_DA_MUSICA = 1.5


def comando_foto_e_miniatura(foto, video, destino, segundos, miniatura, centro, com_audio, seta=None,
                             centro_seta=None, pulso_da_seta=(0, 1), capa=None, musica=None, total=0.0,
                             outra=None, troca=3):
    """
    O ffmpeg da edição: a foto em tela cheia (fundo preto) por `segundos`, ou a `capa` no
    lugar dela, quando vier (uma imagem já montada, como a da bebida alcoólica com os
    avisos), depois o vídeo em 720x1280 com a foto em miniatura (`miniatura` px de largura)
    com o centro em `centro` (x, y) até o fim; com `miniatura` 0, sem ela (o canto tem coisa
    do criador do vídeo, P81). Com `seta` (uma animação APNG com fundo transparente), a seta
    com o centro em `centro_seta`, do começo do vídeo, logo depois da foto, até o fim;
    `pulso_da_seta` = (primeiro quadro, quantos quadros) é o trecho do fim da animação que
    se repete até o fim do vídeo. O som do vídeo começa depois da foto, que vai em silêncio;
    vídeo sem som sai sem som. Com a `musica` (caminho de um arquivo de áudio), ela é o som do
    vídeo inteiro, foto incluída (`total` segundos), em laço se o vídeo for mais longo,
    entrando e saindo devagar; o som do vídeo não entra. Com a `outra` (caminho de outra foto
    do produto), a miniatura troca entre as duas a cada `troca` segundos, no mesmo lugar e do
    mesmo tamanho, a `foto` primeiro.
    """
    tela = f"{FILTRO_720P},setsar=1,fps={QUADROS_POR_SEGUNDO},format=yuv420p"
    # A foto vai no fundo preto do FILTRO_720P: o app usa o primeiro quadro como capa na grade
    # do perfil, e o número de visualizações, em letras brancas, só se lê no escuro.
    # Escolha do Rafael (29/10, P72): DECISOES.md, Shopee Vídeo.
    filtro = f"[0:v]{tela}[foto];[1:v]{tela}[corpo];"
    if miniatura:
        lugar = f"x={centro[0]}-w/2:y={centro[1]}-h/2:shortest=1"
        filtro += f"[2:v]scale={miniatura}:-2[mini];"
        if outra:
            # A outra foto entra por último na lista: os números das outras entradas não mudam.
            indice = 3 + (1 if seta else 0) + (1 if musica or com_audio else 0)
            ciclo = 2 * troca
            filtro += (f"[{indice}:v]scale={miniatura}:-2[mini2];"
                       f"[corpo][mini]overlay={lugar}:enable='lt(mod(t,{ciclo}),{troca})'[uma];"
                       f"[uma][mini2]overlay={lugar}:enable='gte(mod(t,{ciclo}),{troca})'[comfoto];")
        else:
            filtro += f"[corpo][mini]overlay={lugar}[comfoto];"
    else:
        # A entrada da foto em laço continua na lista (os números das outras não mudam), sem uso.
        filtro += "[corpo]null[comfoto];"
    entradas = ["-loop", "1", "-t", str(segundos), "-i", capa or foto, "-i", video, "-loop", "1", "-i", foto]
    if seta:
        inicio, quadros = pulso_da_seta
        entradas += ["-i", seta]
        filtro += (f"[3:v]loop=loop=-1:size={quadros}:start={inicio}[seta];"
                   f"[comfoto][seta]overlay=x={centro_seta[0]}-w/2:y={centro_seta[1]}-h/2:shortest=1,"
                   "format=yuv420p[editado];"
                   "[foto][editado]concat=n=2:v=1:a=0[v]")
    else:
        filtro += "[foto][comfoto]concat=n=2:v=1:a=0[v]"
    saida = ["-map", "[v]"]
    if musica:
        entradas += ["-stream_loop", "-1", "-i", musica]
        filtro += (f";[{4 if seta else 3}:a]aresample=44100,aformat=channel_layouts=stereo,"
                   f"atrim=0:{total:.3f},asetpts=PTS-STARTPTS,afade=t=in:d={ENTRADA_DA_MUSICA},"
                   f"afade=t=out:st={max(0.0, total - SAIDA_DA_MUSICA):.3f}:d={SAIDA_DA_MUSICA}[a]")
        saida += ["-map", "[a]", "-c:a", "aac", "-b:a", "128k"]
    elif com_audio:
        silencio = 4 if seta else 3
        entradas += ["-f", "lavfi", "-t", str(segundos), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        filtro += (";[1:a]aresample=44100,aformat=channel_layouts=stereo[som];"
                   f"[{silencio}:a][som]concat=n=2:v=0:a=1[a]")
        saida += ["-map", "[a]", "-c:a", "aac", "-b:a", "128k"]
    if miniatura and outra:
        entradas += ["-loop", "1", "-i", outra]
    return (["ffmpeg", "-v", "error", "-y"] + entradas + ["-filter_complex", filtro] + saida
            + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-movflags", "+faststart", destino])


def com_foto_e_miniatura(video, foto, destino, segundos=2, miniatura=180, centro=(576, 128), seta=None,
                         centro_seta=None, espera=300, pulso_da_seta=(0, 1), capa=None, musica=None, outra=None,
                         troca=3):
    """
    Grava em destino o vídeo com a foto (bytes) no começo e em miniatura por cima, e a seta
    (caminho de uma animação APNG com fundo transparente), se vier. Com a `capa` (bytes de
    uma imagem), ela abre o vídeo no lugar da foto. Com a `musica` (caminho de um arquivo de
    áudio), ela é o som do vídeo inteiro. Com a `outra` (bytes de outra foto do produto), a
    miniatura troca entre as duas a cada `troca` segundos; a outra que não abre fica de fora,
    sem derrubar a edição. Devolve "" quando deu certo, ou o motivo fixo de não ter dado (o
    destino não fica pela metade).
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
        caminho_da_capa = None
        if capa:
            caminho_da_capa = os.path.join(pasta, "capa.png")
            with open(caminho_da_capa, "wb") as arquivo:
                arquivo.write(capa)
            if not imagem_abre(caminho_da_capa):
                return "a capa não é uma imagem que abre"
        caminho_da_outra = None
        if outra and miniatura:
            caminho_da_outra = os.path.join(pasta, "outra.jpg")
            with open(caminho_da_outra, "wb") as arquivo:
                arquivo.write(outra)
            if not imagem_abre(caminho_da_outra):
                caminho_da_outra = None
        temporario = os.path.join(pasta, "editado.mp4")
        total = segundos + duracao(video) if musica else 0.0
        comando = comando_foto_e_miniatura(caminho_da_foto, video, temporario, segundos, miniatura, centro,
                                           tem_audio(video), seta, centro_seta, pulso_da_seta, caminho_da_capa,
                                           musica if total > segundos else None, total, caminho_da_outra, troca)
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


def duracao(caminho, timeout=30):
    """A duração do vídeo em segundos, pelo ffprobe; 0 quando não dá para ler."""
    try:
        saida = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", caminho],
            capture_output=True, text=True, timeout=timeout).stdout.strip()
        return max(0.0, float(saida or 0))
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


# O movimento é medido em quadros pequenos, em tons de cinza: basta para ver se a imagem
# mexe, e um vídeo de um minuto passa em poucos segundos.
LADO_DO_MOVIMENTO = 64


def movimento(caminho, por_segundo=10, timeout=120):
    """
    Quanto a imagem muda de um quadro para o seguinte, por_segundo vezes por segundo: a
    diferença média entre os dois (0 a 255). Imagem parada fica perto de 0; mão mexendo no
    produto, bem acima. Vídeo que não abre dá [].
    """
    import numpy
    lado = LADO_DO_MOVIMENTO
    try:
        feito = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", caminho, "-vf", f"fps={por_segundo},scale={lado}:{lado},format=gray",
             "-f", "rawvideo", "-"], capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return []
    if feito.returncode != 0:
        return []
    bruto = numpy.frombuffer(feito.stdout, dtype=numpy.uint8)
    total = len(bruto) // (lado * lado)
    if total < 2:
        return []
    quadros = bruto[:total * lado * lado].reshape(total, lado * lado).astype(numpy.int16)
    return [float(valor) for valor in numpy.abs(numpy.diff(quadros, axis=0)).mean(axis=1)]


def som_por_janela(caminho, janela=0.5, timeout=120):
    """
    O volume do som (dBFS, de -100 a 0) em cada janela de `janela` segundos do vídeo, do
    começo ao fim. Vídeo sem som ou que não abre dá [].
    """
    import numpy
    amostras_por_segundo = 8000
    try:
        feito = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", caminho, "-vn", "-ac", "1", "-ar", str(amostras_por_segundo),
             "-f", "s16le", "-"], capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return []
    if feito.returncode != 0 or not feito.stdout:
        return []
    som = numpy.frombuffer(feito.stdout[:len(feito.stdout) // 2 * 2], dtype=numpy.int16).astype(numpy.float64)
    por_janela = int(amostras_por_segundo * janela)
    volumes = []
    for inicio in range(0, len(som), por_janela):
        pedaco = som[inicio:inicio + por_janela]
        rms = float(numpy.sqrt(numpy.mean(pedaco ** 2))) if len(pedaco) else 0.0
        volumes.append(max(-100.0, float(20 * numpy.log10(rms / 32768))) if rms > 0 else -100.0)
    return volumes


# Abaixo disto do começo ao fim, o vídeo é mudo: o silêncio digital fica em -100 e o chiado
# mais baixo de uma gravação, perto de -60; fala e música passam de -40.
VOLUME_DO_MUDO = -60.0


def mudo(caminho, timeout=120):
    """
    True quando o vídeo não tem som que se ouça: sem a trilha de áudio, ou com ela abaixo de
    VOLUME_DO_MUDO do começo ao fim. Arquivo que não existe não é mudo.
    """
    if not os.path.exists(caminho):
        return False
    if not tem_audio(caminho):
        return True
    volumes = som_por_janela(caminho, timeout=timeout)
    return bool(volumes) and max(volumes) <= VOLUME_DO_MUDO


# Na emenda de dois trechos, o som entra e sai em 30 ms, sem estalo.
EMENDA_DO_SOM = 0.03


def comando_cortes_e_ritmo(video, trechos, destino, com_audio, letreiros=()):
    """
    O ffmpeg do vídeo remontado: trechos = [(início, fim, velocidade)], cada pedaço do vídeo
    original na ordem da lista (que pode trocar a ordem do original), na velocidade dele (o som acompanha, sem mudar o tom; o que não está
    em nenhum trecho sai). Sai em 720x1280. letreiros = [(imagem, início, fim, x, y)]: cada
    imagem (PNG com fundo transparente) por cima, com o canto de cima à esquerda em (x, y),
    nesses segundos do vídeo já remontado.
    """
    quantos = len(trechos)
    filtro = f"[0:v]split={quantos}" + "".join(f"[v{i}]" for i in range(quantos)) + ";"
    if com_audio:
        filtro += f"[0:a]asplit={quantos}" + "".join(f"[a{i}]" for i in range(quantos)) + ";"
    juntar = ""
    for i, (inicio, fim, velocidade) in enumerate(trechos):
        filtro += (f"[v{i}]trim=start={inicio:.3f}:end={fim:.3f},"
                   f"setpts=(PTS-STARTPTS)/{velocidade:g}[c{i}];")
        juntar += f"[c{i}]"
        if com_audio:
            fica = (fim - inicio) / velocidade
            filtro += (f"[a{i}]atrim=start={inicio:.3f}:end={fim:.3f},asetpts=PTS-STARTPTS,"
                       f"atempo={velocidade:g},afade=t=in:d={EMENDA_DO_SOM},"
                       f"afade=t=out:st={max(0.0, fica - EMENDA_DO_SOM):.3f}:d={EMENDA_DO_SOM}[b{i}];")
            juntar += f"[b{i}]"
    filtro += f"{juntar}concat=n={quantos}:v=1:a={1 if com_audio else 0}[corpo]" + ("[som]" if com_audio else "") + ";"
    filtro += f"[corpo]fps={QUADROS_POR_SEGUNDO},{FILTRO_720P},setsar=1,format=yuv420p[t0]"
    entradas = ["-i", video]
    for i, (imagem, inicio, fim, x, y) in enumerate(letreiros):
        entradas += ["-i", imagem]
        filtro += (f";[t{i}][{i + 1}:v]overlay=x={x}:y={y}:enable='between(t,{inicio:.2f},{fim:.2f})',"
                   f"format=yuv420p[t{i + 1}]")
    saida = ["-map", f"[t{len(letreiros)}]"]
    if com_audio:
        saida += ["-map", "[som]", "-c:a", "aac", "-b:a", "128k"]
    # Qualidade alta aqui: o vídeo remontado ainda passa pela edição do Editor 1 depois.
    return (["ffmpeg", "-v", "error", "-y"] + entradas + ["-filter_complex", filtro] + saida
            + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-movflags", "+faststart", destino])


def com_cortes_e_ritmo(video, trechos, destino, letreiros=(), espera=300):
    """
    Grava em destino o vídeo remontado pelos trechos (início, fim, velocidade), com os
    letreiros (imagem PNG em bytes, início, fim, x, y) por cima. Devolve "" quando deu
    certo, ou o motivo fixo de não ter dado (o destino não fica pela metade).
    """
    if not trechos:
        return "o vídeo não tem nenhum trecho para montar"
    with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(destino))) as pasta:
        imagens = []
        for i, (imagem, inicio, fim, x, y) in enumerate(letreiros):
            caminho = os.path.join(pasta, f"letreiro_{i}.png")
            with open(caminho, "wb") as arquivo:
                arquivo.write(imagem)
            imagens.append((caminho, inicio, fim, x, y))
        temporario = os.path.join(pasta, "remontado.mp4")
        comando = comando_cortes_e_ritmo(video, trechos, temporario, tem_audio(video), imagens)
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
