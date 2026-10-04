"""Relatório da fila dos parceiros: um botão só, com o resumo no topo e a lista vídeo a vídeo."""
from datetime import datetime, timedelta

from conftest import inserir, rodar


def _parceiro(bm, nome):
    return bm.salvar_parceiro({"nome": nome, "app_id": "123456", "app_secret": "x" * 20,
                               "canal_origem": "@a", "canal_destino": "-1001", "limite_diario": 1})


def _video(pid, n, dia):
    inserir("CREATE TABLE IF NOT EXISTS fila_parceiros (id_unico TEXT PRIMARY KEY, parceiro_id INTEGER, "
            "caminho_video TEXT, link_original TEXT, data_captura TEXT, data_alvo TEXT, "
            "horario_disparo TEXT DEFAULT '', processado INTEGER DEFAULT 0, data_postagem TEXT DEFAULT '')")
    inserir("INSERT INTO fila_parceiros (id_unico, parceiro_id, link_original, data_captura, data_alvo) "
            "VALUES (?, ?, ?, ?, ?)", f"{pid}-{n}", pid, f"https://s.shopee.com.br/v{n}?a=1&b=2", dia, dia)


def test_teclado_tem_um_botao_de_parceiros_so(bm):
    textos = [b.text for linha in bm.obter_teclado_relatorios_filas().keyboard for b in linha]
    assert [t for t in textos if "Parceiros" in t] == ["Fila dos Parceiros 🔍"]


def test_um_parceiro_abre_direto_com_resumo_e_lista(bm, Msg, Est):
    pid = _parceiro(bm, "Loja & Cia")
    amanha = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    for n in (1, 2, 3):
        _video(pid, n, amanha)

    msg = Msg("Fila dos Parceiros 🔍")
    rodar(bm.pedir_parceiro_detalhe(msg, Est()))

    texto = msg.saidas[-1]
    assert "Loja &amp; Cia" in texto and "Na fila: <b>3</b>" in texto and "Cota Diária" in texto
    assert "descarta 2" in texto                          # prévia do fechamento: cota 1, três na fila
    assert texto.count("ver produto") == 3 and "a=1&amp;b=2" in texto


def test_com_dois_parceiros_pergunta_qual_e_mostra_o_escolhido(bm, Msg, Est):
    _parceiro(bm, "Primeiro")
    pid = _parceiro(bm, "Segundo")
    _video(pid, 1, datetime.now().strftime("%Y-%m-%d"))
    est = Est()

    msg = Msg("Filas dos Parceiros 👥")                  # botão antigo, ainda no teclado do celular
    rodar(bm.pedir_parceiro_detalhe(msg, est))
    assert "Qual fila" in msg.saidas[-1]

    resposta = Msg(str(pid))
    rodar(bm.detalhar_fila_parceiro(resposta, est))
    assert "Segundo" in resposta.saidas[-1] and "ver produto" in resposta.saidas[-1]
