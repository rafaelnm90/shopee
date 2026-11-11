"""videos: medir a resolução, subir para 720p e a assinatura do arquivo do mesmo jeito em todos os robôs."""
import asyncio
import glob
import os

import videos
from conftest import rodar

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Processo:
    """Processo de mentira: devolve a saída combinada e, no ffmpeg, cria o arquivo de saída."""

    def __init__(self, comando, saida=b"", codigo=0, demora=0):
        self.comando, self.saida, self.returncode, self.demora = comando, saida, codigo, demora
        self.morto = False

    async def communicate(self):
        await asyncio.sleep(self.demora)
        if self.comando[0] == "ffmpeg" and self.returncode == 0:
            open(self.comando[-1], "wb").write(b"video 720p")
        return self.saida, b""

    def kill(self):
        self.morto = True


def _programas(monkeypatch, sonda=b"480x854\n", codigo_sonda=0, codigo_ffmpeg=0, demora_sonda=0):
    chamados = []

    async def executar(*comando, **_):
        if comando[0] == "ffprobe":
            processo = _Processo(comando, sonda, codigo_sonda, demora_sonda)
        else:
            processo = _Processo(comando, codigo=codigo_ffmpeg)
        chamados.append(processo)
        return processo

    monkeypatch.setattr(videos.asyncio, "create_subprocess_exec", executar)
    return chamados


def test_dimensoes_le_o_ffprobe(monkeypatch):
    _programas(monkeypatch, sonda=b"720x1280\n")
    assert rodar(videos.dimensoes("v.mp4")) == (720, 1280)
    for sonda, codigo in ((b"", 0), (b"N/A\n", 0), (b"720x1280\n", 1)):
        _programas(monkeypatch, sonda=sonda, codigo_sonda=codigo)
        assert rodar(videos.dimensoes("v.mp4")) == (None, None), (sonda, codigo)


def test_dimensoes_desiste_no_tempo_limite(monkeypatch):
    chamados = _programas(monkeypatch, demora_sonda=5)
    assert rodar(videos.dimensoes("v.mp4", timeout=0.01)) == (None, None)
    assert chamados[0].morto


def test_video_pequeno_vira_720p_no_mesmo_caminho(monkeypatch, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"video 480p")
    chamados = _programas(monkeypatch, sonda=b"480x854\n")
    relatorio = {}
    assert rodar(videos.verificar_e_otimizar_video(str(video), relatorio)) == str(video)
    assert video.read_bytes() == b"video 720p"
    assert relatorio == {"upscaled": True}
    assert videos.FILTRO_720P in chamados[1].comando
    assert not os.path.exists(f"{video}_upscaled.mp4")


def test_video_bom_ou_ilegivel_fica_como_esta(monkeypatch, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"original")
    for sonda in (b"720x1280\n", b"1080x1920\n", b""):
        chamados = _programas(monkeypatch, sonda=sonda)
        relatorio = {}
        rodar(videos.verificar_e_otimizar_video(str(video), relatorio))
        assert [p.comando[0] for p in chamados] == ["ffprobe"], sonda
        assert relatorio == {} and video.read_bytes() == b"original"


def test_ffmpeg_falhou_mantem_o_original(monkeypatch, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"original")
    _programas(monkeypatch, codigo_ffmpeg=1)
    relatorio = {}
    rodar(videos.verificar_e_otimizar_video(str(video), relatorio))
    assert relatorio == {} and video.read_bytes() == b"original"
    assert rodar(videos.verificar_e_otimizar_video(str(tmp_path / "sumiu.mp4"))) == str(tmp_path / "sumiu.mp4")


def test_assinatura_igual_para_o_mesmo_conteudo(tmp_path):
    a, b, c = tmp_path / "a.mp4", tmp_path / "b.mp4", tmp_path / "c.mp4"
    a.write_bytes(b"video" * 50000)
    b.write_bytes(b"video" * 50000)
    c.write_bytes(b"outro" * 50000)
    assert videos.calcular_hash_video(str(a)) == videos.calcular_hash_video(str(b))
    assert videos.calcular_hash_video(str(a)) != videos.calcular_hash_video(str(c))
    assert videos.calcular_hash_video(str(tmp_path / "sumiu.mp4")) is None


def test_os_robos_usam_o_modulo():
    import downloader_bot
    import espelhador_videos_autorais as autorais
    import motor_userbot
    assert motor_userbot.verificar_e_otimizar_video is videos.verificar_e_otimizar_video
    assert motor_userbot.calcular_hash_video is videos.calcular_hash_video
    assert autorais.verificar_e_otimizar_video is videos.verificar_e_otimizar_video
    assert downloader_bot.videos is videos


def test_nenhum_arquivo_tem_a_propria_receita_de_video():
    # Uma cópia nova faria um ajuste no tratamento do vídeo valer para um robô e não para outro.
    copias = []
    for arquivo in glob.glob(os.path.join(PASTA, "*.py")):
        if os.path.basename(arquivo) == "videos.py":
            continue
        texto = open(arquivo, encoding="utf-8").read()
        for receita in ('"ffprobe"', "scale=720:1280", "def verificar_e_otimizar_video",
                        "def calcular_hash_video"):
            if receita in texto:
                copias.append((os.path.basename(arquivo), receita))
    assert copias == []


def test_quadros_espalhados_do_video(tmp_path):
    # Os casos das falhas do robô da Shopee Vídeo levam alguns quadros do vídeo (casos_robo).
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        assert videos.quadros("nao_existe.mp4", str(tmp_path)) == 0
        return
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=10",
                    str(video)], check=True)
    assert videos.quadros(str(video), str(tmp_path), quantos=3, largura=160) == 3
    assert sorted(p.name for p in tmp_path.glob("quadro_*.jpg")) == ["quadro_1.jpg", "quadro_2.jpg", "quadro_3.jpg"]
    lixo = tmp_path / "lixo.mp4"
    lixo.write_bytes(b"nao e video")
    assert videos.quadros(str(lixo), str(tmp_path / "x")) == 0


def test_video_mudo_sem_trilha_ou_em_silencio(tmp_path):
    # Escolha do Rafael (P48): o vídeo sem som nenhum ganha uma música da Shopee na postagem.
    import shutil
    import subprocess
    assert videos.mudo(str(tmp_path / "nao_existe.mp4")) is False
    if not shutil.which("ffmpeg"):
        return

    def gravar(nome, *som):
        caminho = str(tmp_path / nome)
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:size=64x64:rate=10:duration=2",
                        *som, "-shortest", caminho], check=True)
        return caminho
    assert videos.mudo(gravar("sem_trilha.mp4")) is True
    assert videos.mudo(gravar("silencio.mp4", "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=8000",
                              "-map", "0:v", "-map", "1:a")) is True
    assert videos.mudo(gravar("apito.mp4", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                              "-map", "0:v", "-map", "1:a")) is False


def test_palavras_faladas_pelo_reconhecimento_de_voz(monkeypatch, tmp_path):
    # O tempo de cada palavra vem do som do vídeo (o faster-whisper, em CPU), para as legendas da fala.
    import sys
    import types
    video = tmp_path / "v.mp4"
    video.write_bytes(b"video")
    pedidos = []

    class Modelo:
        def __init__(self, nome, device, compute_type):
            pedidos.append((nome, device, compute_type))

        def transcribe(self, caminho, language, vad_filter, word_timestamps):
            pedidos.append((language, vad_filter, word_timestamps))
            palavra = lambda inicio, fim, texto: types.SimpleNamespace(start=inicio, end=fim, word=texto)
            return iter([types.SimpleNamespace(words=[palavra(1.0, 1.3, " Olha"), palavra(1.3, 1.5, " só")]),
                         types.SimpleNamespace(words=[palavra(1.5, 1.6, " "), palavra(2.0, 2.6, " vestido.")])]), None

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Modelo))
    assert videos.palavras_faladas(str(video)) == [(1.0, 1.3, "Olha"), (1.3, 1.5, "só"), (2.0, 2.6, "vestido.")]
    assert pedidos == [(videos.MODELO_DA_FALA, "cpu", "int8"), ("pt", True, True)]
    # O vídeo que não existe, o reconhecimento que não abre e a biblioteca que falta: None.
    assert videos.palavras_faladas(str(tmp_path / "outro.mp4")) is None

    class SemModelo:
        def __init__(self, *args, **kwargs):
            raise OSError("sem o modelo")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=SemModelo))
    assert videos.palavras_faladas(str(video)) is None
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    assert videos.palavras_faladas(str(video)) is None


def test_abertura_do_exemplo_com_a_passagem_de_uma_capa_para_a_outra(tmp_path):
    # P175 1: só a abertura, para o exemplo do painel; o 1º quadro é a capa da grade inteira e, em
    # `passagem` segundos, ela se desfaz na do vídeo aberto.
    import io
    import shutil
    import subprocess

    from PIL import Image
    if not shutil.which("ffmpeg"):
        return

    def png(cor):
        saida = io.BytesIO()
        Image.new("RGB", (720, 1280), cor).save(saida, "PNG")
        return saida.getvalue()

    destino = str(tmp_path / "abertura.mp4")
    assert videos.abertura_com_passagem(png((220, 30, 30)), png((30, 30, 220)), destino, 2, 0.3) == ""
    assert abs(videos.duracao(destino) - 2) < 0.1

    def vermelho(numero):
        saida = subprocess.run(["ffmpeg", "-v", "error", "-i", destino, "-vf", f"select=eq(n\\,{numero})",
                                "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
        return Image.open(io.BytesIO(saida)).convert("RGB").getpixel((360, 640))[0]

    assert vermelho(0) > 200 and 60 < vermelho(5) < 190 and vermelho(12) < 40 and vermelho(50) < 40
    assert videos.abertura_com_passagem(b"nao e imagem", png((0, 0, 0)), destino) == "a capa não é uma imagem que abre"


def test_passagem_entre_as_capas_so_com_o_tempo_dela():
    # Sem a passagem, a capa do resto cobre a do 1º quadro do 2º quadro em diante (P129); com ela, a
    # do resto entra aos poucos por cima (P175 1).
    corte = videos.comando_foto_e_miniatura("f.jpg", "v.mp4", "d.mp4", 2, 180, (576, 128), False, capa="c.png",
                                            capa_do_resto="r.png")
    assert "enable='gte(n,1)'" in corte[corte.index("-filter_complex") + 1]
    suave = videos.comando_foto_e_miniatura("f.jpg", "v.mp4", "d.mp4", 2, 180, (576, 128), False, capa="c.png",
                                            capa_do_resto="r.png", passagem=0.3)
    filtro = suave[suave.index("-filter_complex") + 1]
    assert "fade=t=in:st=0.0167:d=0.300:alpha=1" in filtro and "gte(n,1)" not in filtro



# --- As cores no celular (P204 1) ---

def _cadeias(comando):
    """{entrada: o filtro que começa nela} do -filter_complex de um comando do ffmpeg."""
    filtro = comando[comando.index("-filter_complex") + 1]
    return {parte.split("]", 1)[0] + "]": parte for parte in filtro.split(";") if parte.startswith("[")}


def test_cada_imagem_entra_na_tabela_do_hd_e_o_video_do_criador_fica_como_veio():
    # P204 1: o celular lê o vídeo em HD na tabela BT.709. Cada imagem (a capa, a do resto da
    # abertura, a miniatura e as outras fotos, a seta e a moldura) passa por ela antes de entrar no
    # vídeo, e o arquivo sai com a etiqueta; o vídeo do criador não passa por conversão nenhuma.
    comando = videos.comando_foto_e_miniatura(
        "f.jpg", "v.mp4", "d.mp4", 2, 180, (576, 128), True, seta="s.apng", centro_seta=(360, 900),
        capa="c.png", outras=["o.jpg"], troca=1.0, capa_do_resto="r.png", moldura="m.png", passagem=0.3)
    cadeias = _cadeias(comando)
    # A capa, a foto da miniatura, a seta, a outra foto, a capa do resto e a moldura.
    for entrada in ("[0:v]", "[2:v]", "[3:v]", "[5:v]", "[6:v]", "[7:v]"):
        assert videos.NA_TABELA_DO_HD in cadeias[entrada], entrada
    assert videos.NA_TABELA_DO_HD not in cadeias["[1:v]"] and "color_matrix" not in cadeias["[1:v]"]
    assert comando[-len(videos.ETIQUETA_DAS_CORES) - 3:-3] == videos.ETIQUETA_DAS_CORES
    so_a_miniatura = videos.comando_foto_e_miniatura("f.jpg", "v.mp4", "d.mp4", 2, 180, (576, 128), False)
    assert videos.NA_TABELA_DO_HD in _cadeias(so_a_miniatura)["[2:v]"]
    remontado = videos.comando_cortes_e_ritmo("v.mp4", [(0, 2, 1.0)], "d.mp4", False,
                                              [("t.png", 0, 1, 10, 10), ("l.png", 1, 2, 10, 10)])
    assert all(videos.NA_TABELA_DO_HD in _cadeias(remontado)[e] for e in ("[1:v]", "[2:v]"))
    assert "color_matrix" not in _cadeias(remontado)["[0:v]"]
    assert remontado[-len(videos.ETIQUETA_DAS_CORES) - 3:-3] == videos.ETIQUETA_DAS_CORES


def test_cores_das_imagens_no_video_como_o_celular_le(tmp_path):
    # P204 1, com o ffmpeg de verdade: lido na tabela do HD, como o celular lê, o rosa da capa e da
    # miniatura e o vermelho da moldura saem com a cor escolhida (antes, o rosa saía mais claro), o
    # arquivo leva a etiqueta e o vídeo do criador fica com as cores que veio.
    import io
    import json
    import shutil
    import subprocess

    from PIL import Image, ImageDraw
    if not shutil.which("ffmpeg"):
        return
    rosa, vermelho = (230, 90, 150), (220, 30, 40)

    def imagem(im, formato="PNG"):
        saida = io.BytesIO()
        im.save(saida, formato)
        return saida.getvalue()

    def quadro(video, segundo):
        saida = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(segundo), "-i", video, "-vf",
                                "scale=in_color_matrix=bt709:out_color_matrix=bt709,format=rgb24", "-frames:v", "1",
                                "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, check=True).stdout
        return Image.open(io.BytesIO(saida)).convert("RGB")

    def perto(cor, esperada, folga=6):
        return all(abs(a - b) <= folga for a, b in zip(cor, esperada))

    criador = str(tmp_path / "criador.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "smptehdbars=size=720x1280:rate=30:duration=2",
                    "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", "-c:v", "libx264", "-crf", "16",
                    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", criador], check=True)
    capa = Image.new("RGB", (720, 1280), (0, 0, 0))
    ImageDraw.Draw(capa).rectangle([0, 0, 719, 299], fill=rosa)
    moldura = Image.new("RGBA", (720, 1280), (0, 0, 0, 0))
    ImageDraw.Draw(moldura).rectangle([100, 900, 620, 1100], outline=vermelho + (255,), width=20)
    destino = str(tmp_path / "editado.mp4")
    assert videos.com_foto_e_miniatura(criador, imagem(Image.new("RGB", (400, 400), rosa), "JPEG"), destino,
                                       segundos=1, capa=imagem(capa), moldura=imagem(moldura)) == ""
    etiqueta = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=color_space,color_primaries,"
         "color_transfer", "-of", "json", destino], capture_output=True, text=True).stdout)["streams"][0]
    assert etiqueta == {"color_space": "bt709", "color_primaries": "bt709", "color_transfer": "bt709"}
    assert perto(quadro(destino, 0).getpixel((360, 150)), rosa)
    corpo, fonte = quadro(destino, 2.4), quadro(criador, 1.4)
    assert perto(corpo.getpixel((576, 128)), rosa) and perto(corpo.getpixel((110, 1000)), vermelho)
    for ponto in ((50, 400), (300, 400), (650, 400), (400, 1200)):
        assert perto(corpo.getpixel(ponto), fonte.getpixel(ponto), 4), ponto
