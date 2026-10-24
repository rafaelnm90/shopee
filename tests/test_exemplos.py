"""Os exemplos das perguntas dos painéis mostram o que está valendo agora (exemplos.py)."""
from conftest import rodar


def test_faixa_e_fixo_mostram_o_de_agora_e_o_ultimo_mandado(bm):
    import exemplos
    # Nunca mandou um Fixo: fica o exemplo padrão; a Faixa é a de agora.
    assert exemplos.faixa_e_fixo("teste", (8, 12), "1-3", "2") == ("8-12", "2")
    exemplos.lembrar_faixa("teste", 10, 10)
    exemplos.lembrar_faixa("teste", 8, 12)
    # Em Faixa outra vez: o Fixo mostra o 10 que o Rafael mandou antes.
    assert exemplos.faixa_e_fixo("teste", (8, 12), "1-3", "2") == ("8-12", "10")
    # Em Fixo: a Faixa mostra a última faixa mandada.
    assert exemplos.faixa_e_fixo("teste", (10, 10), "1-3", "2") == ("8-12", "10")
    # Sem teto (0): os dois são os últimos mandados.
    assert exemplos.faixa_e_fixo("teste", (0, 0), "1-3", "2") == ("8-12", "10")
    assert exemplos.media("8-12") == "10" and exemplos.media("5-8") == "6,5"


def test_janela_em_dia_todo_mostra_o_ultimo_horario(bm):
    import exemplos
    assert exemplos.janela("teste", 10, 20, "8-22") == "10-20"
    assert exemplos.janela("teste", 0, 24, "8-22") == "8-22"
    exemplos.lembrar_janela("teste", 9, 18)
    exemplos.lembrar_janela("teste", 0, 24)                  # Dia Todo tem botão, não vira exemplo
    assert exemplos.janela("teste", 0, 24, "8-22") == "9-18"


def test_rascunhos_por_dia_mostra_a_faixa_de_hoje_e_o_ultimo_fixo(bm, Msg, Est):
    # Pedido do Rafael (vídeo de 24/10, 08:06): em Faixa 8 a 12, o exemplo é 8-12; o Fixo,
    # nunca mandado, fica 2; mandou Fixo 10 e voltou à Faixa, o exemplo do Fixo é 10.
    sv = bm.painel_shopee_video
    sv.alterar_config(robo_limite_min=8, robo_limite_max=12)
    msg = Msg("Rascunhos por Dia 📦")
    rodar(sv.pedir_faixa_robo(msg, Est()))
    assert "ex.: <code>8-12</code>" in msg.saidas[0] and "sorteia um número entre 8 e 12" in msg.saidas[0]
    assert "ex.: <code>2</code>), e são sempre 2 por dia" in msg.saidas[0]
    est = Est()
    rodar(sv.pedir_faixa_robo(Msg("Rascunhos por Dia 📦"), est))
    msg = Msg("Faixa 🎲")
    rodar(sv.escolher_tipo_faixa(msg, est))
    assert "Ex.: <code>8-12</code>" in msg.saidas[0]

    for texto, tipo in (("10", "Fixo 📌"), ("8-12", "Faixa 🎲")):
        est = Est()
        rodar(sv.pedir_faixa_robo(Msg("Rascunhos por Dia 📦"), est))
        rodar(sv.escolher_tipo_faixa(Msg(tipo), est))
        rodar(sv.confirmar_faixa_robo(Msg(texto), est))
        rodar(sv.salvar_faixa_robo(Msg("Aprovar ✅"), est))
    msg = Msg("Rascunhos por Dia 📦")
    rodar(sv.pedir_faixa_robo(msg, Est()))
    assert "ex.: <code>8-12</code>" in msg.saidas[0] and "ex.: <code>10</code>), e são sempre 10 por dia" in msg.saidas[0]
    # O aviso de número errado também usa o de agora.
    est = Est(estado=sv.ShopeeVideoFluxo.aguardando_faixa_robo)
    rodar(est.update_data(tipo_faixa="fixo"))
    msg = Msg("1-3")
    rodar(sv.confirmar_faixa_robo(msg, est))
    assert "<code>10</code>" in msg.saidas[0]


def test_horario_do_robo_em_dia_todo_mostra_o_ultimo_horario(bm, Msg, Est):
    sv = bm.painel_shopee_video
    sv.alterar_config(robo_inicio=0, robo_fim=24)
    msg = Msg("Horário do Robô 🕗")
    rodar(sv.pedir_janela_robo(msg, Est()))
    assert "ex.: <code>9-21</code>" in msg.saidas[0]
    est = Est()
    rodar(sv.confirmar_janela_robo(Msg("8-20"), est))
    rodar(sv.salvar_janela_robo(Msg("Aprovar ✅"), est))
    msg = Msg("Horário do Robô 🕗")
    rodar(sv.pedir_janela_robo(msg, Est()))
    assert "ex.: <code>8-20</code>" in msg.saidas[0]
    est = Est()
    rodar(sv.confirmar_janela_robo(Msg("Dia Todo (24h) 🕛"), est))
    rodar(sv.salvar_janela_robo(Msg("Aprovar ✅"), est))
    msg = Msg("Horário do Robô 🕗")
    rodar(sv.pedir_janela_robo(msg, Est()))
    assert "ex.: <code>8-20</code>" in msg.saidas[0] and "o dia todo" in msg.saidas[0]


def test_cota_dos_autorais_e_do_publico_mostram_a_de_agora(bm, Msg, Est):
    config = bm.ler_autorais_config()
    config.update(limite_min=3, limite_max=7)
    bm.salvar_autorais_config(config)
    msg = Msg("Editar Limite 📦")
    rodar(bm.pedir_limite_autorais(msg, Est()))
    assert "<code>3-7</code> — cada dia sorteia um número entre 3 e 7 (média 5)" in msg.saidas[0]
    assert "<code>6</code> — sempre 6 por dia" in msg.saidas[0]

    config = bm.ler_submissao_config()
    config.update(repost_limite_min=4, repost_limite_max=4, repost_dias=21)
    bm.salvar_submissao_config(config)
    msg = Msg("Editar Limite (Público) 📦")
    rodar(bm.pedir_limite_repost_publico(msg, Est()))
    assert "<code>4-8</code>" in msg.saidas[0] and "<code>4</code> — sempre 4 por dia" in msg.saidas[0]
    msg = Msg("Editar Dias (Público) ⏳")
    rodar(bm.pedir_dias_repost_publico(msg, Est()))
    assert "(Ex: 21)" in msg.saidas[0]


def test_parceiro_cota_e_janela_com_os_dele(bm, Msg, Est):
    pid = bm.salvar_parceiro({"nome": "Loja", "app_id": "123456", "app_secret": "x" * 20,
                              "canal_origem": "@a", "canal_destino": "-1001", "limite_diario": 1})
    bm.atualizar_parceiro(pid, "limite_min", 5)
    bm.atualizar_parceiro(pid, "limite_max", 9)
    bm.atualizar_parceiro(pid, "janela_inicio", 7)
    bm.atualizar_parceiro(pid, "janela_fim", 19)
    for botao, trecho in (("Editar Cota 📦", "<code>5-9</code>"), ("Editar Janela 🕒", "<code>7-19</code>")):
        msg = Msg(botao)
        rodar(bm.acoes_parceiro(msg, Est({"parceiro_id": pid})))
        assert trecho in msg.saidas[-1], msg.saidas
    msg = Msg("muitos")
    rodar(bm.salvar_edicao_parceiro(msg, Est({"parceiro_id": pid, "campo_edicao": "cota"})))
    assert "<code>5-9</code>" in msg.saidas[0]


def test_spam_e_contador_com_os_valores_de_agora(bm, Msg, Est):
    dados = bm.ler_alvos_divulgacao()
    dados.update(frequencia_por_hora=2, repeticoes_internas=4, replicas_mensagem=3)
    bm.salvar_alvos_divulgacao(dados)
    msg = Msg("2 3")
    rodar(bm.salvar_valores_unificados(msg, Est({"edicao_global": True})))
    assert "(Exemplo: 2, 4, 3)" in msg.saidas[0]
    bm.salvar_contador(57)
    msg = Msg("cinquenta")
    rodar(bm.salvar_novo_numero(msg, Est()))
    assert "Exemplo: 57" in msg.saidas[0]
