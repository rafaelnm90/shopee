"""video_ia: o teste do vídeo feito por IA (P34) escolhe o modelo mais barato e só mostra números no log público."""
import video_ia


def test_escolhe_o_veo_mais_novo_e_mais_barato():
    nomes = ["veo-2.0-generate-001", "veo-3.1-generate-001", "veo-3.1-fast-generate-001", "veo-3.1-lite-generate-001"]
    assert video_ia.escolher_modelo(nomes) == "veo-3.1-lite-generate-001"
    assert video_ia.escolher_modelo(["veo-3.0-generate-001", "veo-3.0-fast-generate-001"]) == "veo-3.0-fast-generate-001"
    assert video_ia.escolher_modelo(["veo-2.0-generate-001"]) == "veo-2.0-generate-001"
    assert video_ia.escolher_modelo([]) is None


def test_teste_manda_o_video_so_no_privado_e_o_log_so_tem_numeros(monkeypatch, capsys):
    mandados = []

    def gerar(modelo, foto, destino):
        with open(destino, "wb") as arquivo:
            arquivo.write(b"video")
        return ""

    async def dimensoes(caminho, timeout=None):
        return 720, 1280

    monkeypatch.setattr(video_ia, "PASTA", "video_ia")
    monkeypatch.setattr(video_ia, "modelos_de_video", lambda: ["veo-3.1-fast-generate-001"])
    monkeypatch.setattr(video_ia, "produto_para_teste", lambda: ("Copo Térmico Inox", b"foto"))
    monkeypatch.setattr(video_ia, "gerar", gerar)
    monkeypatch.setattr(video_ia.videos, "dimensoes", dimensoes)
    monkeypatch.setattr(video_ia.avisar_rafael, "mandar_video",
                        lambda caminho, legenda="": mandados.append(legenda) or True)
    assert video_ia.main(["testar"]) == 0
    saida = capsys.readouterr().out
    assert "720x1280" in saida and "Mandado no privado do Rafael: sim" in saida and "Copo" not in saida
    assert "Copo Térmico Inox" in mandados[0] and "Não foi postado" in mandados[0]


def test_sem_modelo_de_video_ou_sem_foto_o_teste_nao_roda(monkeypatch, capsys):
    monkeypatch.setattr(video_ia, "modelos_de_video", lambda: [])
    assert video_ia.main(["testar"]) == 1
    assert "não enxerga nenhum modelo de vídeo" in capsys.readouterr().out
    monkeypatch.setattr(video_ia, "modelos_de_video", lambda: ["veo-3.1-lite-generate-001"])
    monkeypatch.setattr(video_ia, "produto_para_teste", lambda: None)
    assert video_ia.main(["testar"]) == 1
    assert video_ia.main(["outra"]) == 2
