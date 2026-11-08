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

