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
