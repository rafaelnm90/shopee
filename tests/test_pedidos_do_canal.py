"""pedidos_do_canal: os vídeos do robô da Shopee Vídeo que esperam a fila do Canal Afiliados."""
import os
import time
from datetime import datetime, timedelta

import pytest

import pedidos_do_canal as pedidos
from conftest import inserir
from fuso import fuso_horario

AGORA = datetime(2026, 10, 28, 15, 0, tzinfo=fuso_horario)
LINK_DO_POST = "https://sv.shopee.com.br/share-video/abc"


@pytest.fixture(autouse=True)
def configuracoes():
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")


def _video(tmp_path, nome="rascunho.mp4", conteudo=b"video"):
    caminho = tmp_path / nome
    caminho.write_bytes(conteudo)
    return str(caminho)


def test_pedido_guarda_uma_copia_e_o_mesmo_rascunho_nao_dobra(tmp_path):
    video = _video(tmp_path, conteudo=b"primeiro")
    copia = pedidos.pedir(7, video, LINK_DO_POST, ["https://s.shopee.com.br/1"], "Copo Térmico", agora=AGORA)
    assert os.path.dirname(copia) == pedidos.PASTA and open(copia, "rb").read() == b"primeiro"
    _video(tmp_path, conteudo=b"segundo")
    pedidos.pedir(7, video, "https://sv.shopee.com.br/share-video/outro", [], "Copo Térmico", agora=AGORA)
    [pedido] = pedidos.pendentes()
    assert (pedido["link_post"], pedido["links"], pedido["tentativas"], pedido["pedido_em"]) == (
        "https://sv.shopee.com.br/share-video/outro", [], 0, "2026-10-28 15:00:00")
    assert open(copia, "rb").read() == b"segundo"
    pedidos.atualizar(7, numero=120, tentativas=1)
    assert (pedidos.pendentes()[0]["numero"], pedidos.pendentes()[0]["tentativas"]) == (120, 1)
    pedidos.concluir(7)
    assert pedidos.pendentes() == []


def test_a_marca_do_video_levado_ao_canal_reconhece_o_mesmo_arquivo_por_outro_caminho(tmp_path, monkeypatch):
    # Contra o loop (vídeo do Rafael, 30/10, 22:28): o vídeo que o robô levou ao canal volta
    # pelo Viral com outro nome de arquivo; a marca (SHA-256) o reconhece.
    video = _video(tmp_path, conteudo=b"postado")
    assert not pedidos.ja_foi_ao_canal(video)
    pedidos.pedir(1, video, LINK_DO_POST, [], agora=AGORA)
    de_volta = _video(tmp_path, "de_volta.mp4", b"postado")
    assert pedidos.ja_foi_ao_canal(de_volta)
    assert not pedidos.ja_foi_ao_canal(_video(tmp_path, "outro.mp4", b"outro"))
    # Ficam só as marcas mais novas.
    monkeypatch.setattr(pedidos, "MARCAS_GUARDADAS", 2)
    for n in range(2, 4):
        pedidos.pedir(n, _video(tmp_path, f"v{n}.mp4", f"video {n}".encode()), LINK_DO_POST, [], agora=AGORA)
    assert not pedidos.ja_foi_ao_canal(de_volta)


def test_parados_sao_so_os_que_esperam_mais_que_o_prazo(tmp_path):
    video = _video(tmp_path)
    pedidos.pedir(1, video, LINK_DO_POST, [], agora=AGORA - timedelta(minutes=40))
    pedidos.pedir(2, video, LINK_DO_POST, [], agora=AGORA - timedelta(minutes=10))
    assert pedidos.parados(30, AGORA) == 1
    assert pedidos.parados(5, AGORA) == 2


def test_faxina_tira_so_a_copia_que_saiu_da_fila_e_ja_passou_do_prazo(tmp_path):
    inserir("CREATE TABLE IF NOT EXISTS fila_postagens (id_unico TEXT, caminho_video TEXT, status TEXT)")
    assert pedidos.faxina() == (0, 0)          # sem a pasta, nada a fazer
    os.makedirs(pedidos.PASTA)
    velho = time.time() - (pedidos.HORAS_PROTEGIDAS + 1) * 3600
    caminhos = {}
    for nome in ("na_fila", "com_erro", "excluida", "nova"):
        caminhos[nome] = os.path.join(pedidos.PASTA, f"{nome}.mp4")
        open(caminhos[nome], "wb").write(b"1234")
        if nome != "nova":
            os.utime(caminhos[nome], (velho, velho))
    caminhos["pedida"] = pedidos.pedir(9, _video(tmp_path), LINK_DO_POST, [])
    os.utime(caminhos["pedida"], (velho, velho))
    inserir("INSERT INTO fila_postagens VALUES ('a', ?, 'PENDENTE')", caminhos["na_fila"])
    inserir("INSERT INTO fila_postagens VALUES ('b', ?, 'ERRO')", caminhos["com_erro"])
    # Recém-copiada, a cópia pode estar entre o robô copiar o vídeo e guardar o pedido.
    os.utime(caminhos["nova"], (time.time(), time.time()))
    assert pedidos.faxina() == (2, 8)
    assert sorted(os.listdir(pedidos.PASTA)) == ["9.mp4", "na_fila.mp4", "nova.mp4"]


def test_faxina_do_disco_do_bot_tira_as_copias_do_canal(bm, tmp_path):
    os.makedirs(pedidos.PASTA)
    sobra = os.path.join(pedidos.PASTA, "excluida.mp4")
    open(sobra, "wb").write(b"1234")
    velho = time.time() - (pedidos.HORAS_PROTEGIDAS + 1) * 3600
    os.utime(sobra, (velho, velho))
    removidos, liberados = bm.limpar_arquivos_orfaos()
    assert (removidos, liberados) == (1, 4) and not os.path.exists(sobra)
