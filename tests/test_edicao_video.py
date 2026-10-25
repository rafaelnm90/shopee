"""edicao_video e videos.com_foto_e_miniatura: a foto do produto no começo e a miniatura no topo, só nos vídeos do Rafael (P37), com o ffmpeg de mentira."""
import os
import subprocess
from types import SimpleNamespace

import db
import edicao_video
from conftest import inserir


def _programas(monkeypatch, largura_da_foto="800", audio="1", codigo_ffmpeg=0):
    """ffprobe e ffmpeg de mentira: guarda cada comando e, no ffmpeg que dá certo, cria a saída."""
    comandos = []

    def run(comando, capture_output=True, text=False, timeout=None):
        comandos.append(comando)
        if comando[0] == "ffprobe":
            saida = largura_da_foto if "v:0" in comando else audio
            return SimpleNamespace(returncode=0, stdout=saida + "\n")
        if codigo_ffmpeg == 0:
            with open(comando[-1], "wb") as arquivo:
                arquivo.write(b"editado")
        return SimpleNamespace(returncode=codigo_ffmpeg, stdout=b"")

    monkeypatch.setattr(edicao_video.videos.subprocess, "run", run)
    return comandos


def test_so_vale_ligada_e_nos_videos_do_rafael():
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    # Escolha do Rafael (P37): nunca nos vídeos de outras pessoas, e só depois de ele ligar.
    assert not edicao_video.vale_para("autorais")
    db.salvar_config("shopee_video", {"edicao_ligada": True})
    assert edicao_video.vale_para("autorais")
    for fonte in ("viral", "principal", "publico"):
        assert not edicao_video.vale_para(fonte)
    assert edicao_video.FONTES_COM_EDICAO == ("autorais",)


def test_edita_com_a_foto_no_comeco_e_a_miniatura_no_topo(monkeypatch, tmp_path):
    comandos = _programas(monkeypatch)
    destino = str(tmp_path / "rascunho.mp4")
    assert edicao_video.editar("video.mp4", b"foto", destino) == ""
    assert open(destino, "rb").read() == b"editado"
    ffmpeg = comandos[-1]
    filtro = ffmpeg[ffmpeg.index("-filter_complex") + 1]
    assert "concat=n=2:v=1:a=0" in filtro and "overlay=(W-w)/2:" in filtro and "720:1280" in filtro
    assert f"-t {edicao_video.SEGUNDOS_DA_FOTO}" in " ".join(ffmpeg) and "scale=220:-2" in filtro
    assert "overlay=(W-w)/2:60" in filtro
    # Com som: o áudio do vídeo começa depois da foto, que vai em silêncio.
    assert "[3:a][som]concat=n=2:v=0:a=1[a]" in filtro and "[a]" in ffmpeg


def test_video_sem_som_sai_sem_som(monkeypatch, tmp_path):
    comandos = _programas(monkeypatch, audio="")
    assert edicao_video.editar("video.mp4", b"foto", str(tmp_path / "r.mp4")) == ""
    ffmpeg = comandos[-1]
    assert "anullsrc" not in " ".join(ffmpeg) and "[a]" not in ffmpeg


def test_sem_foto_foto_que_nao_abre_ou_ffmpeg_falhou_nao_deixa_arquivo(monkeypatch, tmp_path):
    destino = str(tmp_path / "r.mp4")
    assert edicao_video.editar("video.mp4", None, destino) == "a foto do anúncio não veio"
    # Uma imagem que não abre prenderia o ffmpeg em laço: nem chega a ele.
    comandos = _programas(monkeypatch, largura_da_foto="0")
    assert edicao_video.editar("video.mp4", b"x", destino) == "a foto do anúncio não é uma imagem que abre"
    assert all(c[0] == "ffprobe" for c in comandos)
    _programas(monkeypatch, codigo_ffmpeg=1)
    assert edicao_video.editar("video.mp4", b"foto", destino) == "o ffmpeg falhou (código 1)"
    assert not os.path.exists(destino)


def test_ffmpeg_que_demora_demais_desiste(monkeypatch, tmp_path):
    def run(comando, **kwargs):
        if comando[0] == "ffprobe":
            return SimpleNamespace(returncode=0, stdout="800\n")
        raise subprocess.TimeoutExpired(comando, kwargs.get("timeout"))

    monkeypatch.setattr(edicao_video.videos.subprocess, "run", run)
    assert edicao_video.editar("video.mp4", b"foto", str(tmp_path / "r.mp4")).startswith("o ffmpeg passou de")


def test_exemplo_usa_o_video_mais_novo_dos_autorais_com_foto(monkeypatch, tmp_path):
    sem_arquivo, com_foto = str(tmp_path / "sumiu.mp4"), str(tmp_path / "a.mp4")
    open(com_foto, "wb").close()
    candidatos = [("1", sem_arquivo, "https://s.shopee.com.br/a", ""), ("2", com_foto, None, ""),
                  ("3", com_foto, "https://s.shopee.com.br/sem-foto", ""), ("4", com_foto, "https://s.shopee.com.br/b", "")]
    monkeypatch.setattr(edicao_video.assistente, "_candidatos", lambda fonte: candidatos if fonte == "autorais" else [])
    monkeypatch.setattr(edicao_video.ps, "foto_do_produto",
                        lambda video: None if "sem-foto" in video["link"] else b"foto")
    monkeypatch.setattr(edicao_video.ps, "nome_do_produto", lambda video: "Copo Térmico")
    editados = []
    monkeypatch.setattr(edicao_video, "editar", lambda video, foto, destino: editados.append(video) or "")
    assert edicao_video.exemplo("exemplo.mp4") == ("Copo Térmico", "")
    assert editados == [com_foto]


def test_exemplo_sem_video_dos_autorais_diz_o_motivo(monkeypatch):
    monkeypatch.setattr(edicao_video.assistente, "_candidatos", lambda fonte: [])
    nome, motivo = edicao_video.exemplo("exemplo.mp4")
    assert nome is None and "chip novo" in motivo
