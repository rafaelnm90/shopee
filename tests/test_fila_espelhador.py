"""fila_espelhador: a fila do Espelhador no banco, sem um robô apagar a gravação do outro."""
import glob
import json
import os
import re

import fila_espelhador as fe
from conftest import rodar

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _item(id_, destino="-100200", msg_id=1, **extra):
    return {"id": id_, "destino": destino, "msg_id": msg_id, "nome_rota": "R", **extra}


def _arquivo(itens):
    with open(fe.ARQUIVO, "w", encoding="utf-8") as f:
        json.dump({"fila": itens}, f)


def _ids():
    return [i["id"] for i in fe.ler()["fila"]]


def test_sem_nada_a_fila_vem_vazia():
    assert fe.ler() == {"fila": []}


def test_antes_da_passagem_le_o_arquivo_e_a_primeira_gravacao_leva_tudo_para_o_banco():
    _arquivo([_item("a"), _item("b")])
    assert _ids() == ["a", "b"]
    fe.atualizar(lambda dados: dados["fila"].append(_item("c")))
    assert _ids() == ["a", "b", "c"]
    assert not os.path.exists(fe.ARQUIVO) and os.path.exists(fe.ARQUIVO + ".bkp")


def test_passagem_ao_ligar_o_motor():
    fe.passar_arquivo_para_o_banco()                       # sem arquivo: nada a fazer
    assert fe.db.ler_config(fe.CHAVE, None) == {}
    _arquivo([_item("a")])
    fe.passar_arquivo_para_o_banco()
    assert fe.db.ler_config(fe.CHAVE)["fila"][0]["id"] == "a"
    assert os.path.exists(fe.ARQUIVO + ".bkp") and not os.path.exists(fe.ARQUIVO)


def test_arquivo_que_reaparece_depois_da_passagem_nao_repete_post_nem_perde_captura():
    fe.atualizar(lambda dados: dados["fila"].extend([_item("a"), _item("b")]))
    # Uma versão velha do motor gravou o arquivo depois: publicou "a" e capturou "c".
    _arquivo([_item("a", processado=True), _item("b"), _item("c")])
    fe.passar_arquivo_para_o_banco()
    fila = {i["id"]: i for i in fe.ler()["fila"]}
    assert sorted(fila) == ["a", "b", "c"]
    assert fila["a"].get("processado") is True
    assert not os.path.exists(fe.ARQUIVO)


def test_arquivo_ilegivel_e_posto_de_lado_sem_mexer_na_fila():
    fe.atualizar(lambda dados: dados["fila"].append(_item("a")))
    with open(fe.ARQUIVO, "w") as f:
        f.write("{quebrado")
    fe.passar_arquivo_para_o_banco()
    assert _ids() == ["a"] and os.path.exists(fe.ARQUIVO + ".ilegivel.bkp")


def test_mesmo_id_em_outra_rota_ou_no_mesmo_album_sao_itens_diferentes():
    a = _item("x", destino="-1001", msg_id=5)
    assert fe.chave_do_item(a) != fe.chave_do_item(_item("x", destino="-1002", msg_id=5))
    assert fe.chave_do_item(a) != fe.chave_do_item(_item("x", destino="-1001", msg_id=6))
    assert fe.chave_do_item(a) == fe.chave_do_item(dict(a, nome_rota="Renomeada"))


def test_ciclo_longo_grava_so_o_que_mudou():
    fe.atualizar(lambda dados: dados["fila"].extend(
        [_item("publica"), _item("descarta"), _item("limpa"), _item("painel")]))
    fila = fe.ler()["fila"]
    foto = fe.fotografar(fila)

    # Enquanto o laço publica: a captura acrescenta, o Limpar Filas tira um e o painel
    # renomeia a rota de outro.
    fe.atualizar(lambda dados: dados["fila"].append(_item("capturado")))
    fe.atualizar(lambda dados: dados.update(fila=[i for i in dados["fila"] if i["id"] != "limpa"]))

    def renomear(dados):
        for i in dados["fila"]:
            if i["id"] == "painel":
                i["nome_rota"] = "Nova"
    fe.atualizar(renomear)

    # O laço: publicou um, tirou outro pelo teto do dia, não mexeu nos demais.
    por_id = {i["id"]: i for i in fila}
    por_id["publica"]["processado"] = True
    restantes = [por_id["publica"], por_id["limpa"], por_id["painel"]]
    fe.gravar_mudancas(foto, restantes)

    fila = {i["id"]: i for i in fe.ler()["fila"]}
    assert sorted(fila) == ["capturado", "painel", "publica"]
    assert fila["publica"]["processado"] is True
    assert fila["painel"]["nome_rota"] == "Nova"


def test_painel_renomeia_e_conta_no_banco():
    import painel_espelhos
    fe.atualizar(lambda dados: dados["fila"].extend(
        [_item("a"), _item("b", processado=True), _item("c", nome_rota="Outra")]))
    assert painel_espelhos.ler_contador_espelhador("R") == 1
    painel_espelhos._renomear_rota_na_fila("R", "R2")
    assert [i["nome_rota"] for i in fe.ler()["fila"]] == ["R2", "R2", "Outra"]


def test_limpar_fila_do_espelhador_tira_so_os_pendentes(bm, Msg, Est):
    fe.atualizar(lambda dados: dados["fila"].extend([_item("pendente"), _item("saiu", processado=True)]))
    estado = Est({"tipo_limpeza": "Limpar Fila Espelhador 🔄"})
    rodar(bm.processar_zerar_filas_tarefas(Msg("Aprovar Exclusão ✅"), estado))
    assert _ids() == ["saiu"]


def test_motor_usa_o_banco_na_captura_e_no_disparo():
    fonte = open(os.path.join(PASTA, "motor_userbot.py"), encoding="utf-8").read()
    assert "fila_espelhador.gravar_mudancas(foto, itens_restantes)" in fonte
    assert "fila_espelhador.atualizar(lambda dados, novo=item: dados[\"fila\"].append(novo))" in fonte
    assert fonte.index("fila_espelhador.passar_arquivo_para_o_banco()") < \
        fonte.index("asyncio.create_task(processar_fila_espelhador_loop())")


def test_ninguem_mais_le_ou_grava_o_arquivo_da_fila():
    # Gravar o arquivo de novo traria de volta a perda de vídeos entre os robôs.
    quem = []
    for arquivo in glob.glob(os.path.join(PASTA, "*.py")):
        if os.path.basename(arquivo) == "fila_espelhador.py":
            continue
        if re.search(r"""["']fila_espelhador\.json["']""", open(arquivo, encoding="utf-8").read()):
            quem.append(os.path.basename(arquivo))
    assert quem == []
