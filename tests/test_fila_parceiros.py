"""Relatório da fila dos parceiros: um botão só, com o resumo no topo e a lista vídeo a vídeo."""
from datetime import datetime, timedelta

from conftest import consultar, inserir, rodar


def _parceiro(bm, nome):
    return bm.salvar_parceiro({"nome": nome, "app_id": "123456", "app_secret": "x" * 20,
                               "canal_origem": "@a", "canal_destino": "-1001", "limite_diario": 1})


def _video(pid, n, dia, link_post=None):
    inserir("CREATE TABLE IF NOT EXISTS fila_parceiros (id_unico TEXT PRIMARY KEY, parceiro_id INTEGER, "
            "caminho_video TEXT, link_original TEXT, data_captura TEXT, data_alvo TEXT, "
            "horario_disparo TEXT DEFAULT '', processado INTEGER DEFAULT 0, data_postagem TEXT DEFAULT '', "
            "link_post_origem TEXT DEFAULT '', msg_postada_id INTEGER, nome_produto TEXT DEFAULT '')")
    inserir("INSERT INTO fila_parceiros (id_unico, parceiro_id, link_original, data_captura, data_alvo, "
            "link_post_origem) VALUES (?, ?, ?, ?, ?, ?)", f"{pid}-{n}", pid,
            f"https://s.shopee.com.br/v{n}?a=1&b=2", dia, dia,
            f"https://t.me/c/1234/{n}?a=1&b=2" if link_post is None else link_post)


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

    resumo, lista = msg.saidas
    assert "Loja &amp; Cia" in resumo and "Na fila: <b>3</b>" in resumo and "Cota Diária" in resumo
    assert "descarta 2" in resumo                         # prévia do fechamento: cota 1, três na fila
    # Os vídeos vêm no mesmo card das outras filas, com a data-alvo gravada na captura.
    assert "📡 <b>Rota: Loja &amp; Cia</b> (3 vídeos agendados)" in lista
    # Origem: o post no Telegram, nunca o produto na Shopee (esse link só gera o de afiliado).
    assert lista.count("Ver Post no Telegram (Origem)") == 3 and "t.me/c/1234/1?a=1&amp;b=2" in lista
    assert "Shopee" not in lista
    assert lista.count("🟡 Agendado p/ Amanhã") == 3 and "Aguardando postagem (Destino)" in lista


def test_fila_comprida_continua_em_outra_mensagem_sem_cortar_videos(bm, Msg, Est):
    pid = _parceiro(bm, "Grande")
    dia = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
    for n in range(40):
        _video(pid, n, dia)
    msg = Msg("Fila dos Parceiros 🔍")
    rodar(bm.pedir_parceiro_detalhe(msg, Est()))
    assert len(msg.saidas) >= 3 and all(len(s) < 4096 for s in msg.saidas)
    assert "(Continuação)" in msg.saidas[2]
    assert sum(s.count("Ver Post no Telegram (Origem)") for s in msg.saidas) == 40


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
    assert "Segundo" in resposta.saidas[0] and "Ver Post no Telegram" in resposta.saidas[-1]


def test_video_antigo_sem_post_guardado_nao_mostra_a_shopee(bm, Msg, Est):
    pid = _parceiro(bm, "Antiga")
    _video(pid, 1, (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"), link_post="")
    msg = Msg("Fila dos Parceiros 🔍")
    rodar(bm.pedir_parceiro_detalhe(msg, Est()))
    assert "Sem link de origem" in msg.saidas[-1] and "Shopee" not in msg.saidas[-1]


def test_publicado_fica_na_fila_com_o_link_do_destino(bm, Msg, Est, tmp_path):
    pid = _parceiro(bm, "Postou")
    hoje = datetime.now().strftime("%Y-%m-%d")
    _video(pid, 1, hoje)
    _video(pid, 2, hoje)
    arquivo = tmp_path / "v.mp4"
    arquivo.write_bytes(b"x")
    bm.marcar_parceiro_postado(f"{pid}-1", str(arquivo), 77, "Garrafa Térmica 🍶")
    assert not arquivo.exists()                                    # o vídeo sai do disco

    msg = Msg("Fila dos Parceiros 🔍")
    rodar(bm.pedir_parceiro_detalhe(msg, Est()))
    lista = msg.saidas[-1]
    assert "(1 vídeos agendados)" in lista
    primeiro = lista.split("<b>2.</b>")[0]                         # publicados de hoje primeiro
    assert "✅ Postado" in primeiro and "Garrafa Térmica 🍶" in primeiro
    assert "https://t.me/c/1/77" in primeiro and "Ver Post no Telegram (Destino)" in primeiro


def test_publicado_antigo_sai_do_registro(bm):
    pid = _parceiro(bm, "Velho")
    _video(pid, 1, "2026-01-01")
    inserir("UPDATE fila_parceiros SET processado = 1, data_postagem = '2026-01-01 10:00:00'")
    _video(pid, 2, datetime.now().strftime("%Y-%m-%d"))
    bm.marcar_parceiro_postado(f"{pid}-2", None, 5)
    assert consultar("SELECT COUNT(*) FROM fila_parceiros WHERE id_unico = ?", f"{pid}-1")[0] == 0
    assert consultar("SELECT processado, msg_postada_id FROM fila_parceiros WHERE id_unico = ?",
                     f"{pid}-2") == (1, 5)


def test_link_do_post_no_destino(bm):
    assert bm.link_post_destino("-1003909405581", 12) == "https://t.me/c/3909405581/12"
    assert bm.link_post_destino("-1003909405581:5", 12) == "https://t.me/c/3909405581/12"
    assert bm.link_post_destino("@meucanal", 12) == "https://t.me/meucanal/12"
    assert bm.link_post_destino("-1001", None) is None


def test_resumo_diz_que_ninguem_captura_com_o_posto_vago(bm, pc, Msg, Est):
    pid = _parceiro(bm, "Rafa")
    pc.salvar_conta("fora", sessao="x")                            # conta no pool, fora do grupo
    pc.aplicar_funcoes()
    _video(pid, 1, (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"))
    msg = Msg("Fila dos Parceiros 🔍")
    rodar(bm.pedir_parceiro_detalhe(msg, Est()))
    assert "Acesso à origem: ❌ nenhuma conta está capturando" in msg.saidas[0]


def test_captura_guarda_o_link_do_post_no_telegram(esp):
    from types import SimpleNamespace
    assert esp.link_do_post(SimpleNamespace(username="canal_x", id=5), 9) == "https://t.me/canal_x/9"
    assert esp.link_do_post(SimpleNamespace(username=None, id=3673555953), 9) == "https://t.me/c/3673555953/9"
    assert esp.link_do_post(SimpleNamespace(username=None, id=-1003673555953), 9) == "https://t.me/c/3673555953/9"
    assert esp.link_do_post(None, 9) == ""
    # Tabela antiga, sem as colunas novas: a captura acrescenta e grava.
    inserir("CREATE TABLE fila_parceiros (id_unico TEXT PRIMARY KEY, parceiro_id INTEGER, caminho_video TEXT, "
            "link_original TEXT, data_captura TEXT, data_alvo TEXT, horario_disparo TEXT DEFAULT '', "
            "processado INTEGER DEFAULT 0, data_postagem TEXT DEFAULT '')")
    id_unico = esp.inserir_fila_parceiro(1, "/tmp/x.mp4", "https://s.shopee.com.br/x", "2026-10-10",
                                         "https://t.me/c/1/9")
    assert consultar("SELECT link_original, link_post_origem FROM fila_parceiros WHERE id_unico = ?",
                     id_unico) == ("https://s.shopee.com.br/x", "https://t.me/c/1/9")
