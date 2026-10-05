"""Acessos do Servidor (Opções do Servidor): Tailscale e Oracle, editados pelo bot."""
import logging

from conftest import rodar


def _textos(teclado):
    return [b.text for linha in teclado.keyboard for b in linha]


def _ac(bm):
    return bm.painel_acessos


def _cadastrar_oracle(ac, Msg, Est, conta="minha-nuvem", email="rafa@exemplo.com", senha="senha-de-teste"):
    est = Est()
    rodar(ac.pedir_oracle_conta(Msg("Editar Oracle ✏️"), est))
    rodar(ac.receber_oracle_conta(Msg(conta), est))
    rodar(ac.receber_oracle_email(Msg(email), est))
    msg = Msg(senha)
    rodar(ac.salvar_oracle(msg, est))
    return msg, est


def test_botao_fica_nas_opcoes_do_servidor_e_o_voltar_volta_para_elas(bm, Msg, Est):
    ac = _ac(bm)
    assert "Acessos do Servidor 🔐" in _textos(bm.obter_teclado_opcoes_servidor())
    assert ac.VOLTAR in _textos(ac.teclado_painel())
    # O Voltar é tratado pelo handler das Opções do Servidor, no bot_mestre.
    handler = next(h for h in bm.dp.message.handlers if h.callback is bm.menu_opcoes_servidor_handler)
    assert rodar(handler.check(Msg(ac.VOLTAR), raw_state="AcessosFluxo:menu"))[0]
    msg, est = Msg(ac.VOLTAR), Est(estado=ac.AcessosFluxo.menu)
    rodar(bm.menu_opcoes_servidor_handler(msg, est))
    assert "Opções do Servidor" in msg.saidas[0] and rodar(est.get_state()) is None


def test_painel_vazio_mostra_os_sites_e_o_que_falta_cadastrar(bm, Msg, Est):
    ac = _ac(bm)
    msg, est = Msg("Acessos do Servidor 🔐"), Est()
    rodar(ac.painel_handler(msg, est))
    texto = msg.saidas[-1]
    assert "https://login.tailscale.com/" in texto and "Sign in with Google" in texto
    assert "a da sua conta Google" in texto
    assert "https://cloud.oracle.com/" in texto and "Nome da conta na nuvem" in texto
    assert texto.count("não cadastrad") == 4
    assert rodar(est.get_state()) == ac.AcessosFluxo.menu.state
    teclado = _textos(ac.teclado_painel())
    assert "Editar Tailscale ✏️" in teclado and "Editar Oracle ✏️" in teclado


def test_tailscale_guarda_so_a_conta_google(bm, Msg, Est):
    ac, est = _ac(bm), Est()
    msg = Msg("Editar Tailscale ✏️")
    rodar(ac.pedir_tailscale(msg, est))
    assert "não fica guardada" in msg.saidas[0]
    assert rodar(est.get_state()) == ac.AcessosFluxo.aguardando_tailscale_email.state
    msg = Msg("sem arroba")
    rodar(ac.salvar_tailscale(msg, est))
    assert "⚠️" in msg.saidas[0] and ac.ler_acessos()["tailscale"] == {}
    msg = Msg("rafa@exemplo.com")
    rodar(ac.salvar_tailscale(msg, est))
    assert ac.ler_acessos()["tailscale"] == {"email": "rafa@exemplo.com"}
    assert "<code>rafa@exemplo.com</code>" in msg.saidas[-1]
    assert rodar(est.get_state()) == ac.AcessosFluxo.menu.state


def test_oracle_guarda_os_tres_campos_e_apaga_a_mensagem_da_senha(bm, Msg, Est):
    ac = _ac(bm)
    msg, est = _cadastrar_oracle(ac, Msg, Est, senha="a<b&c")
    assert ac.ler_acessos()["oracle"] == {"conta": "minha-nuvem", "email": "rafa@exemplo.com", "senha": "a<b&c"}
    assert msg.apagada and "Apaguei a sua mensagem" in msg.saidas[0]
    painel = msg.saidas[-1]
    assert "<tg-spoiler>a&lt;b&amp;c</tg-spoiler>" in painel             # escondida e escapada
    assert "<code>minha-nuvem</code>" in painel and "<code>rafa@exemplo.com</code>" in painel
    assert rodar(est.get_data()) == {}                                     # a senha não fica no fluxo


def test_senha_nao_vai_para_o_log(bm, Msg, Est, caplog):
    caplog.set_level(logging.DEBUG)
    _cadastrar_oracle(_ac(bm), Msg, Est, senha="senha-de-teste")
    assert "senha-de-teste" not in caplog.text and "rafa@exemplo.com" not in caplog.text


def test_email_invalido_na_oracle_pede_de_novo(bm, Msg, Est):
    ac, est = _ac(bm), Est()
    rodar(ac.pedir_oracle_conta(Msg("Editar Oracle ✏️"), est))
    rodar(ac.receber_oracle_conta(Msg("minha-nuvem"), est))
    msg = Msg("nome sem arroba")
    rodar(ac.receber_oracle_email(msg, est))
    assert "⚠️" in msg.saidas[0]
    assert rodar(est.get_state()) == ac.AcessosFluxo.aguardando_oracle_email.state


def test_cancelar_no_meio_nao_grava_nada(bm, Msg, Est):
    ac, est = _ac(bm), Est()
    rodar(ac.pedir_oracle_conta(Msg("Editar Oracle ✏️"), est))
    rodar(ac.receber_oracle_conta(Msg("minha-nuvem"), est))
    rodar(ac.receber_oracle_email(Msg("rafa@exemplo.com"), est))
    msg = Msg("Cancelar ❌")
    rodar(bm.cancelar_fluxo_global(msg, est))
    assert "Nada foi alterado" in msg.saidas[0] and "Acessos do Servidor" in msg.saidas[-1]
    assert ac.ler_acessos()["oracle"] == {}
    assert rodar(est.get_state()) == ac.AcessosFluxo.menu.state and rodar(est.get_data()) == {}


def test_manter_troca_so_a_senha(bm, Msg, Est):
    ac = _ac(bm)
    _cadastrar_oracle(ac, Msg, Est)
    est = Est()
    msg = Msg("Editar Oracle ✏️")
    rodar(ac.pedir_oracle_conta(msg, est))
    assert ac.MANTER in _textos(ac.teclado_pergunta(True)) and ac.MANTER not in _textos(ac.teclado_pergunta(False))
    rodar(ac.receber_oracle_conta(Msg(ac.MANTER), est))
    rodar(ac.receber_oracle_email(Msg(ac.MANTER), est))
    rodar(ac.salvar_oracle(Msg("outra-senha"), est))
    assert ac.ler_acessos()["oracle"] == {"conta": "minha-nuvem", "email": "rafa@exemplo.com", "senha": "outra-senha"}
    # Manter também na senha: nada muda e nada é apagado.
    est = Est()
    rodar(ac.pedir_oracle_conta(Msg("Editar Oracle ✏️"), est))
    rodar(ac.receber_oracle_conta(Msg(ac.MANTER), est))
    rodar(ac.receber_oracle_email(Msg(ac.MANTER), est))
    msg = Msg(ac.MANTER)
    rodar(ac.salvar_oracle(msg, est))
    assert ac.ler_acessos()["oracle"]["senha"] == "outra-senha" and not msg.apagada


def test_editar_um_servico_nao_mexe_no_outro(bm, Msg, Est):
    ac = _ac(bm)
    _cadastrar_oracle(ac, Msg, Est)
    est = Est()
    rodar(ac.pedir_tailscale(Msg("Editar Tailscale ✏️"), est))
    rodar(ac.salvar_tailscale(Msg("outra@exemplo.com"), est))
    acessos = ac.ler_acessos()
    assert acessos["oracle"]["senha"] == "senha-de-teste" and acessos["tailscale"]["email"] == "outra@exemplo.com"


def test_mensagem_que_nao_pode_ser_apagada_pede_para_apagar_na_mao(bm, Msg, Est):
    ac = _ac(bm)

    class SemApagar(Msg):
        async def delete(self):
            raise RuntimeError("sem permissão")

    est = Est()
    rodar(ac.pedir_oracle_conta(Msg("Editar Oracle ✏️"), est))
    rodar(ac.receber_oracle_conta(Msg("minha-nuvem"), est))
    rodar(ac.receber_oracle_email(Msg("rafa@exemplo.com"), est))
    msg = SemApagar("senha-de-teste")
    rodar(ac.salvar_oracle(msg, est))
    assert "apague-a você" in msg.saidas[0] and ac.ler_acessos()["oracle"]["senha"] == "senha-de-teste"


def test_so_o_admin_ve_e_edita(bm, Msg, Est):
    ac = _ac(bm)
    for handler, texto in ((ac.painel_handler, "Acessos do Servidor 🔐"), (ac.pedir_tailscale, "Editar Tailscale ✏️"),
                           (ac.pedir_oracle_conta, "Editar Oracle ✏️")):
        msg = Msg(texto, user_id=123)
        rodar(handler(msg, Est()))
        assert msg.saidas == [], texto
    est = Est(dados={"conta": "x", "email": "rafa@exemplo.com"}, estado=ac.AcessosFluxo.aguardando_oracle_senha)
    rodar(ac.salvar_oracle(Msg("senha-de-teste", user_id=123), est))
    assert ac.ler_acessos()["oracle"] == {}


def test_botoes_vem_antes_das_respostas_de_texto(bm):
    # No aiogram ganha o primeiro handler que casar: um botão tocado no meio de uma edição
    # tem de abrir o botão, e não ser gravado como e-mail ou senha.
    ac = _ac(bm)
    ordem = [h.callback.__name__ for h in ac.router.message.handlers]
    botoes = ("painel_handler", "pedir_tailscale", "pedir_oracle_conta")
    respostas = ("salvar_tailscale", "receber_oracle_conta", "receber_oracle_email", "salvar_oracle")
    assert max(ordem.index(b) for b in botoes) < min(ordem.index(r) for r in respostas)
