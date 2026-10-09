"""repetidos_publico: o mesmo vídeo não vai duas vezes ao Grupo Público."""
import os
from types import SimpleNamespace

import repetidos_publico as rp
from conftest import consultar, inserir, rodar

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _arquivo(nome, conteudo):
    with open(nome, "wb") as f:
        f.write(conteudo)
    return nome


def test_chaves_reconhecem_o_mesmo_video_encaminhado_ou_enviado_de_novo():
    a = rp.chaves_do_video(111, _arquivo("a.mp4", b"video"))
    b = rp.chaves_do_video(222, _arquivo("b.mp4", b"video"))              # enviado de novo, igual
    c = rp.chaves_do_video(111, _arquivo("c.mp4", b"outro"))              # encaminhado (mesmo arquivo)
    assert a[0] == "doc_111" and a[1].startswith("sha_")
    assert a[1] == b[1] and a[0] == c[0]
    assert rp.chaves_do_video(None, "sumiu.mp4") == []


def test_registrar_ja_foi_e_liberar():
    chaves = rp.chaves_do_video(111, _arquivo("a.mp4", b"video"))
    assert not rp.ja_foi(chaves)
    rp.registrar(chaves, "publico_1")
    assert rp.ja_foi(chaves) and rp.ja_foi([chaves[1]]) and rp.ja_foi(["doc_111", "doc_999"])
    assert not rp.ja_foi(["doc_999"]) and not rp.ja_foi([])
    rp.liberar("publico_1")                       # a vaga foi tomada antes de postar
    assert not rp.ja_foi(chaves)


def test_chaves_gravadas_na_fila_voltam_em_lista():
    assert rp.chaves_da_coluna('["doc_1", "sha_x"]') == ["doc_1", "sha_x"]
    for vazio in (None, "", "quebrado", '{"a": 1}'):
        assert rp.chaves_da_coluna(vazio) == []


def test_marca_do_repost_manual_nao_se_perde_quando_a_fila_e_salva(esp):
    # O botão Disparar Repost Autoral marca repostado_publico = 1. Regravar a fila
    # (toda captura e todo retorno regravam) zerava a marca, e o mesmo vídeo podia ir
    # de novo ao Grupo Público.
    esp.ler_fila_retorno()
    esp.salvar_fila_retorno({"fila": [{"id_unico": "a1", "processado": True, "legenda": "x",
                                       "chaves_video": '["doc_1"]'}]})
    inserir("UPDATE fila_autorais SET repostado_publico = 1, data_repost_publico = '2026-10-09 08:00:00' "
            "WHERE id_unico = 'a1'")
    esp.salvar_fila_retorno(esp.ler_fila_retorno())
    assert consultar("SELECT repostado_publico, data_repost_publico, chaves_video FROM fila_autorais "
                     "WHERE id_unico = 'a1'") == (1, "2026-10-09 08:00:00", '["doc_1"]')


def test_repost_manual_pula_video_que_ja_foi_ao_publico(bm, esp, Msg, monkeypatch):
    esp.ler_fila_retorno()
    esp.salvar_fila_retorno({"fila": [
        {"id_unico": "a1", "processado": True, "msg_id_destino": 10, "legenda": "📦 Item: Copo\n\nx",
         "chaves_video": '["doc_1"]'},
        {"id_unico": "a2", "processado": True, "msg_id_destino": 20, "legenda": "📦 Item: Copo\n\nx",
         "chaves_video": '["doc_2", "sha_mesmo"]'},
    ]})
    rp.registrar(["sha_mesmo"], "publico_antigo")          # o vídeo do a2 já foi pelo sorteio
    bm.salvar_submissao_config({**bm.ler_submissao_config(), "ativo": True, "grupo_id": -1001,
                                "topico_destino": 5, "repost_origem": "-1002"})
    copiados = []

    async def copy_message(**k):
        copiados.append(k["message_id"])
        return SimpleNamespace(message_id=1)

    async def credito():
        return "@Rafaelnm"
    monkeypatch.setattr(bm.bot, "copy_message", copy_message)
    monkeypatch.setattr(bm, "obter_credito_repost", credito)
    for _ in range(3):
        rodar(bm.manual_repost_autoral(Msg("Disparar Repost Autoral ♻️")))
    assert copiados == [10]                                  # só o a1, e uma vez só
    assert rp.ja_foi(["doc_1"])


def test_sorteio_do_publico_usa_a_trava():
    fonte = open(os.path.join(PASTA, "espelhador_videos_autorais.py"), encoding="utf-8").read()
    assert "repetidos_publico.ja_foi(chaves_video)" in fonte
    assert "repetidos_publico.registrar(chaves_video, id_unico_pub)" in fonte
    assert 'repetidos_publico.liberar(item_descartado_pub.get("id_unico"))' in fonte
    # As chaves saem do arquivo como chegou, antes da re-renderização para 720p.
    assert fonte.index("repetidos_publico.chaves_do_video(") < fonte.index(
        "caminho_video = await verificar_e_otimizar_video(caminho_video)")
