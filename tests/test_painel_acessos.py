"""Acessos do Servidor (Opções do Servidor): Tailscale, Oracle e onde está a senha do backup."""
import json
import logging

from cryptography.fernet import Fernet

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
    assert "Onde está a senha" in texto and texto.count("não cadastrad") == 5
    assert rodar(est.get_state()) == ac.AcessosFluxo.menu.state
    teclado = _textos(ac.teclado_painel())
    assert "Editar Tailscale ✏️" in teclado and "Editar Oracle ✏️" in teclado and ac.EDITAR_BACKUP in teclado


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
                           (ac.pedir_oracle_conta, "Editar Oracle ✏️"), (ac.pedir_backup, ac.EDITAR_BACKUP)):
        msg = Msg(texto, user_id=123)
        rodar(handler(msg, Est()))
        assert msg.saidas == [], texto
    est = Est(dados={"conta": "x", "email": "rafa@exemplo.com"}, estado=ac.AcessosFluxo.aguardando_oracle_senha)
    rodar(ac.salvar_oracle(Msg("senha-de-teste", user_id=123), est))
    rodar(ac.salvar_backup(Msg("https://exemplo.com/outro", user_id=123), Est(estado=ac.AcessosFluxo.aguardando_backup_onde)))
    assert ac.ler_acessos()["oracle"] == {} and ac.ler_acessos()["backup"] == {}


def test_botoes_vem_antes_das_respostas_de_texto(bm):
    # No aiogram ganha o primeiro handler que casar: um botão tocado no meio de uma edição
    # tem de abrir o botão, e não ser gravado como e-mail ou senha.
    ac = _ac(bm)
    ordem = [h.callback.__name__ for h in ac.router.message.handlers]
    botoes = ("painel_handler", "pedir_tailscale", "pedir_oracle_conta", "pedir_backup")
    respostas = ("salvar_tailscale", "receber_oracle_conta", "receber_oracle_email", "salvar_oracle", "salvar_backup")
    assert max(ordem.index(b) for b in botoes) < min(ordem.index(r) for r in respostas)


# --- Onde está a senha da cópia do backup ---

LINK = "https://exemplo.com/arquivo/1?ver=2&x=3"


def _guardar_backup(ac, Msg, Est, texto):
    est = Est()
    rodar(ac.pedir_backup(Msg(ac.EDITAR_BACKUP), est))
    msg = Msg(texto)
    rodar(ac.salvar_backup(msg, est))
    return msg, est


def test_backup_guarda_onde_esta_a_senha_com_o_link_clicavel(bm, Msg, Est):
    ac, est = _ac(bm), Est()
    msg = Msg(ac.EDITAR_BACKUP)
    rodar(ac.pedir_backup(msg, est))
    assert "nunca a senha" in msg.saidas[0]
    assert rodar(est.get_state()) == ac.AcessosFluxo.aguardando_backup_onde.state
    msg, est = _guardar_backup(ac, Msg, Est, f"  {LINK} ")
    assert ac.ler_acessos()["backup"] == {"onde": LINK} and ac.onde_esta_a_senha() == LINK
    link = LINK.replace("&", "&amp;")
    assert f'<a href="{link}">{link}</a>' in msg.saidas[-1] and not msg.apagada
    assert rodar(est.get_state()) == ac.AcessosFluxo.menu.state
    # Um lugar escrito aparece como veio, escapado.
    msg, _est = _guardar_backup(ac, Msg, Est, "no caderno <azul> & na gaveta")
    assert "no caderno &lt;azul&gt; &amp; na gaveta" in msg.saidas[-1] and "<a href" not in msg.saidas[-1]


def test_backup_recusa_a_propria_senha_e_apaga_a_mensagem(bm, Msg, Est):
    ac = _ac(bm)
    senha = Fernet.generate_key().decode()
    for texto in (senha, f"a senha é {senha} ok"):
        msg, est = _guardar_backup(ac, Msg, Est, texto)
        assert msg.apagada and "parece a própria senha" in msg.saidas[0]
        assert ac.ler_acessos()["backup"] == {}
        assert rodar(est.get_state()) == ac.AcessosFluxo.aguardando_backup_onde.state
    # Um link comum, mesmo comprido, não parece a senha.
    _guardar_backup(ac, Msg, Est, "https://exemplo.com/file/d/" + "a1B2-c3_D4" * 5 + "/view")
    assert ac.onde_esta_a_senha().endswith("/view")


def test_backup_manter_cancelar_e_texto_comprido_nao_mudam_nada(bm, Msg, Est):
    ac = _ac(bm)
    _guardar_backup(ac, Msg, Est, LINK)
    msg, _est = _guardar_backup(ac, Msg, Est, ac.MANTER)
    assert ac.onde_esta_a_senha() == LINK and ac.MANTER not in msg.saidas[0]
    msg, est = _guardar_backup(ac, Msg, Est, "x" * (ac.LIMITE_DO_ONDE + 1))
    assert "⚠️" in msg.saidas[0] and ac.onde_esta_a_senha() == LINK
    msg = Msg("Cancelar ❌")
    rodar(bm.cancelar_fluxo_global(msg, est))
    assert "Nada foi alterado" in msg.saidas[0] and ac.onde_esta_a_senha() == LINK


def test_guardar_cifrado_grava_so_os_campos_dos_botoes(bm):
    ac = _ac(bm)
    chave = Fernet.generate_key()
    assert ac.guardar_cifrado(ac.cifrar({"backup": {"onde": f" {LINK} "}}, chave), chave) == ["backup"]
    assert ac.ler_acessos()["backup"] == {"onde": LINK}
    # Serviço ou campo que os botões não têm, vazio ou a própria senha: recusa tudo, sem gravar nada.
    for dados in ({"github": {"token": "x"}}, {"oracle": {"conta": "nova", "cartao": "1"}}, {"backup": {"onde": " "}},
                  {"tailscale": {"email": "nova@exemplo.com"}, "backup": {"onde": chave.decode()}}, {}, ["backup"]):
        try:
            ac.guardar_cifrado(ac.cifrar(dados, chave), chave)
        except ac.Recusado:
            pass
        else:
            raise AssertionError(dados)
    assert ac.ler_acessos() == {"tailscale": {}, "oracle": {}, "backup": {"onde": LINK}}


def test_guardar_pelo_workflow_avisa_o_rafael_e_o_log_nao_mostra_o_dado(bm, monkeypatch, capsys, caplog):
    import avisar_rafael
    import registro_privado
    ac, chave = _ac(bm), Fernet.generate_key()
    monkeypatch.setattr(registro_privado, "chave", lambda caminho=None: chave)
    avisos = []
    monkeypatch.setattr(avisar_rafael, "mandar_texto", lambda texto, html=False: avisos.append(texto) or True)
    caplog.set_level(logging.DEBUG)

    assert ac.main(["guardar", ac.cifrar({"backup": {"onde": LINK}}, chave)]) == 0
    assert ac.onde_esta_a_senha() == LINK
    saida = capsys.readouterr().out
    assert "backup" in saida and LINK not in saida and LINK not in caplog.text
    assert len(avisos) == 1 and "Acessos do Servidor 🔐" in avisos[0] and LINK not in avisos[0]
    # Cifrado com outra chave ou recusado: só o tipo ou o motivo fixo, e nada muda.
    assert ac.main(["guardar", ac.cifrar({"backup": {"onde": "https://exemplo.com/b"}}, Fernet.generate_key())]) == 1
    assert ac.main(["guardar", ac.cifrar({"github": {"token": "x"}}, chave)]) == 1
    saida = capsys.readouterr().out
    assert "InvalidToken" in saida and "Recusado" in saida and "exemplo.com" not in saida
    assert ac.onde_esta_a_senha() == LINK and len(avisos) == 1


def test_cifrar_usa_a_chave_do_ambiente_do_claude(bm, monkeypatch, capsys, tmp_path):
    import registro_privado
    ac, chave = _ac(bm), Fernet.generate_key()
    arquivo = tmp_path / "acesso.json"
    arquivo.write_text(json.dumps({"backup": {"onde": LINK}}), encoding="utf-8")
    monkeypatch.delenv(registro_privado.VARIAVEL_CHAVE, raising=False)
    assert ac.main(["cifrar", str(arquivo)]) == 1
    monkeypatch.setenv(registro_privado.VARIAVEL_CHAVE, chave.decode())
    capsys.readouterr()
    assert ac.main(["cifrar", str(arquivo)]) == 0
    cifrado = capsys.readouterr().out.strip()
    assert LINK not in cifrado and json.loads(Fernet(chave).decrypt(cifrado.encode())) == {"backup": {"onde": LINK}}
    assert ac.main(["outra", "x"]) == 2
