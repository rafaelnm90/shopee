"""Painel da Shopee Vídeo (Outros Canais): o assistente (pausa, vídeos por dia, horário e Enviar 1 Agora) e o robô automático (pausa, rascunhos por dia, horário, rascunhos para aprovar e treino)."""
import os

from conftest import consultar, rodar


def _textos(teclado):
    return [b.text for linha in teclado.keyboard for b in linha]


def _painel(bm):
    return bm.painel_shopee_video


def test_botao_fica_em_outros_canais_e_o_android_saiu_das_opcoes_do_servidor(bm):
    assert "Shopee Vídeo 🎬" in _textos(bm.obter_teclado_outros_canais())
    opcoes = _textos(bm.obter_teclado_opcoes_servidor())
    assert "Tutorial do Android 📖" not in opcoes and "Tela do Android 📱" not in opcoes


def test_painel_comeca_pausado_com_5_a_10_das_13h_as_22h(bm, Msg, Est):
    sv = _painel(bm)
    msg, est = Msg("Shopee Vídeo 🎬"), Est()
    rodar(sv.painel_handler(msg, est))
    texto = msg.saidas[-1]
    # A tela inicial diz quem posta agora e o que cada botão faz.
    assert "Quem posta agora" in texto and "ninguém" in texto and "O que cada botão faz" in texto
    assert "Fonte dos vídeos: <b>Autorais 🎥</b>" in texto
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.menu.state
    assert _textos(sv.teclado_painel(sv.ler_config())) == [
        "Rascunhos do Robô 📝", "Robô Automático 🤖", "Modo Assistente 📲", "Fonte dos Vídeos 🎞️",
        "Como Funciona ❓", "Voltar aos Canais 🔙"]
    msg = Msg("Modo Assistente 📲")
    rodar(sv.menu_assistente_handler(msg, est))
    texto = msg.saidas[-1]
    assert "Pausado" in texto and "5 a 10" in texto and "das 13h às 22h" in texto and "hoje:" in texto
    assert "Mandados hoje: <b>0</b>" in texto and "O que cada botão faz" in texto
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.menu_assistente.state
    teclado = _textos(sv.teclado_assistente(sv.ler_config()))
    for botao in ("Vídeos por Dia 📦", "Horário de Postagem ⏰", "Retomar Assistente ▶️", "Enviar 1 Agora 📤",
                  "Voltar à Shopee Vídeo 🔙"):
        assert botao in teclado
    assert "Tela do Android 📱" not in teclado and "Tutorial do Android 📖" not in teclado


def test_menu_do_robo_e_como_funciona(bm, Msg, Est):
    sv, est = _painel(bm), Est()
    msg = Msg("Robô Automático 🤖")
    rodar(sv.menu_robo_handler(msg, est))
    texto = msg.saidas[-1]
    assert "Robô Automático" in texto and "Pausado" in texto and "Celular: ⚠️" in texto
    assert "O que cada botão faz" in texto and "Testar Caminho 🧭" in texto and "Fila de Rascunhos 🗂️" in texto
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.menu_robo.state
    assert _textos(sv.teclado_robo(sv.ler_config())) == [
        "Retomar Postagem ▶️", "Rascunhos do Robô 📝", "Fila de Rascunhos 🗂️", "Preparar 1 Agora ⚡",
        "Histórico do Robô 📋", "Edição dos Vídeos ✂️",
        "Rascunhos por Dia 📦", "Horário do Robô 🕗", "Horário das Interações 💬",
        "Testar Caminho 🧭", "Celular do Robô 📱", "Voltar à Shopee Vídeo 🔙"]
    msg = Msg("Como Funciona ❓")
    rodar(sv.como_funciona_handler(msg, est))
    for trecho in ("Um cobre o outro", "Depuração por Wi-Fi", "Retomar Postagem ▶️", "Passo a Passo 📖"):
        assert trecho in msg.saidas[-1]
    assert len(msg.saidas[-1]) < 4096


def test_faixa_de_videos_por_dia_pede_confirmacao_e_grava(bm, Msg, Est):
    sv, est = _painel(bm), Est()
    rodar(sv.pedir_faixa(Msg("Vídeos por Dia 📦"), est))
    rodar(sv.confirmar_faixa(Msg("3 - 7"), est))
    assert sv.ler_config()["limite_min"] == 5                             # só grava depois de aprovar
    msg = Msg("Aprovar ✅")
    rodar(sv.salvar_faixa(msg, est))
    config = sv.ler_config()
    assert (config["limite_min"], config["limite_max"]) == (3, 7)
    assert "3 a 7" in msg.saidas[0] and config["pausado"] is True           # o resto não muda


def test_faixa_invalida_pede_de_novo(bm, Msg, Est):
    sv = _painel(bm)
    for texto in ("dez", "0", "8-4", "10-90"):
        est = Est(estado=sv.ShopeeVideoFluxo.aguardando_faixa)
        msg = Msg(texto)
        rodar(sv.confirmar_faixa(msg, est))
        assert "⚠️" in msg.saidas[0], texto
        assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.aguardando_faixa.state
    assert sv.interpretar_faixa("6") == (6, 6) and sv.interpretar_faixa("5-10") == (5, 10)


def test_horario_de_postagem_e_dia_todo(bm, Msg, Est):
    sv, est = _painel(bm), Est()
    rodar(sv.pedir_janela(Msg("Horário de Postagem ⏰"), est))
    rodar(sv.confirmar_janela(Msg("9-18"), est))
    rodar(sv.salvar_janela(Msg("Aprovar ✅"), est))
    config = sv.ler_config()
    assert (config["inicio"], config["fim"]) == (9, 18)
    assert sv.interpretar_janela("Dia Todo (24h) 🕛") == (0, 24)
    for errado in ("22-13", "8-25", "meio-dia"):
        assert sv.interpretar_janela(errado) is None, errado


def test_pausar_e_retomar_com_confirmacao(bm, Msg, Est):
    sv, est = _painel(bm), Est()
    msg = Msg("Retomar Assistente ▶️")
    rodar(sv.pedir_pausa(msg, est))
    assert "Retomar" in msg.saidas[0] and "assistente" in msg.saidas[0] and sv.ler_config()["pausado"] is True
    rodar(sv.salvar_pausa(Msg("Confirmar Retomada ✅"), est))
    assert sv.ler_config()["pausado"] is False and sv.ler_config()["robo_pausado"] is True
    assert "Pausar Assistente ⏸️" in _textos(sv.teclado_assistente(sv.ler_config()))
    rodar(sv.pedir_pausa(Msg("Pausar Assistente ⏸️"), est))
    rodar(sv.salvar_pausa(Msg("Confirmar Pausa ✅"), est))
    assert sv.ler_config()["pausado"] is True


def test_botao_antigo_do_teclado_ainda_pausa_o_assistente(bm, Msg, Est):
    sv, est = _painel(bm), Est()
    rodar(sv.pedir_pausa(Msg("Retomar Robô ▶️"), est))
    rodar(sv.salvar_pausa(Msg("Confirmar Retomada ✅"), est))
    assert sv.ler_config()["pausado"] is False and sv.ler_config()["robo_pausado"] is True


def test_pausa_do_robo_automatico_e_separada_e_o_botao_troca(bm, Msg, Est, monkeypatch):
    sv, est = _painel(bm), Est()
    monkeypatch.setattr(sv.celular_robo, "reconectar_sozinho", lambda: (True, "moto g(100)"))
    config = sv.ler_config()
    assert "Retomar Postagem ▶️" in _textos(sv.teclado_robo(config))           # os dois começam pausados
    assert "Retomar Assistente ▶️" in _textos(sv.teclado_assistente(config))
    msg = Msg("Retomar Postagem ▶️")
    rodar(sv.pedir_pausa_robo(msg, est))
    assert "robô automático" in msg.saidas[0]
    rodar(sv.salvar_pausa_robo(Msg("Confirmar Retomada ✅"), est))
    config = sv.ler_config()
    assert config["robo_pausado"] is False and config["pausado"] is True
    assert config["robo_retomado_em"]               # o alerta de robô sem rodar conta daqui
    assert "Pausar Postagem ⏸️" in _textos(sv.teclado_robo(config))
    assert "Retomar Assistente ▶️" in _textos(sv.teclado_assistente(config))
    rodar(sv.pedir_pausa_robo(Msg("Pausar Postagem ⏸️"), est))
    rodar(sv.salvar_pausa_robo(Msg("Confirmar Pausa ✅"), est))
    assert sv.ler_config()["robo_pausado"] is True


def test_retomar_postagem_sem_o_celular_continua_pausado_e_diz_o_que_fazer(bm, Msg, Est, monkeypatch):
    sv, est = _painel(bm), Est()
    monkeypatch.setattr(sv.celular_robo, "reconectar_sozinho",
                        lambda: (False, "a Depuração por Wi-Fi está desligada no celular"))
    msg = Msg("Confirmar Retomada ✅")
    rodar(sv.salvar_pausa_robo(msg, est))
    assert sv.ler_config()["robo_pausado"] is True
    assert "Não retomei" in msg.saidas[1] and "Depuração por Wi-Fi" in msg.saidas[1]
    assert "Retomar Postagem ▶️" in _textos(sv.teclado_robo(sv.ler_config()))


def test_um_cobre_o_outro_robo_ativo_deixa_o_assistente_em_espera(bm, monkeypatch):
    sv = _painel(bm)
    pedidos = []

    async def preparar(bot, admin_id, agora=None, fonte=None):
        pedidos.append(fonte)
        return "postagem mandada no seu privado"

    monkeypatch.setattr(sv.assistente, "preparar_e_enviar", preparar)
    monkeypatch.setattr(sv.assistente, "decidir_envio", lambda config: not config["pausado"])
    sv.alterar_config(pausado=False, robo_pausado=False)
    rodar(sv.verificar_envio())
    assert pedidos == []
    assert "Em espera" in sv.texto_assistente(sv.ler_config())
    assert "o Robô Automático" in sv.texto_painel(sv.ler_config())
    # O celular desconectou: o robô pausou sozinho, e o assistente volta a mandar.
    sv.alterar_config(robo_pausado=True, robo_pausa_motivo="celular desconectado")
    rodar(sv.verificar_envio())
    assert pedidos == ["autorais"]
    assert "o Motorola desconectou" in sv.texto_painel(sv.ler_config())
    assert "o Motorola desconectou" in sv.texto_robo(sv.ler_config())


def test_pausa_sem_o_celular_guarda_os_horarios_e_a_do_rafael_pula(bm, monkeypatch):
    # 28/10: o celular caiu às 15:05 e, na volta, nenhum rascunho saiu pelos horários da tarde:
    # o painel pulava os horários em qualquer pausa. Escolha do Rafael (P16): na pausa sozinha,
    # sem o celular, eles ficam e na volta contam como um só.
    from datetime import datetime
    from fuso import fuso_horario
    sv = _painel(bm)
    rodadas = []

    async def rodar_robo(*argumentos):
        rodadas.append(argumentos)

    monkeypatch.setattr(sv, "rodar_robo", rodar_robo)
    sv.alterar_config(robo_pausado=True, robo_pausa_motivo="celular desconectado", robo_inicio=0, robo_fim=24)
    hoje = datetime.now(fuso_horario).strftime("%Y-%m-%d")
    sv.robo.db.salvar_config(sv.robo.CHAVE_DIA, {"data": hoje, "horarios": ["00:00"], "feitos": 0})
    rodar(sv.verificar_robo())
    assert sv.robo.estado_do_dia(sv.robo.ler_config())["feitos"] == 0 and rodadas == []
    # Pausado pelo Rafael, o horário passa sem rascunho (e sem cobrança no checkup).
    sv.alterar_config(robo_pausa_motivo="")
    rodar(sv.verificar_robo())
    estado = sv.robo.estado_do_dia(sv.robo.ler_config())
    assert (estado["feitos"], estado["sem_tentar"]) == (1, 1) and rodadas == []


def test_reconectar_acha_a_porta_sozinho_antes_de_pedir(bm, Msg, Est, monkeypatch):
    sv = _painel(bm)
    monkeypatch.setattr(sv.celular_robo, "ler", lambda: {"pareado_em": "2026-10-17 10:00:00", "ip": "100.1.2.3"})
    monkeypatch.setattr(sv.celular_robo, "reconectar_sozinho", lambda: (True, "motorola moto g(100), Android 12"))

    async def texto_celular():
        return "📱 Celular do Robô"

    monkeypatch.setattr(sv, "texto_celular", texto_celular)
    msg = Msg("Reconectar Celular 🔄")
    rodar(sv.pedir_reconexao(msg, Est()))
    assert "Celular conectado" in msg.saidas[1] and "porta" not in msg.saidas[1]


def test_rascunhos_por_dia_e_horario_do_robo(bm, Msg, Est):
    sv, est = _painel(bm), Est()
    rodar(sv.pedir_faixa_robo(Msg("Rascunhos por Dia 📦"), est))
    rodar(sv.confirmar_faixa_robo(Msg("2-4"), est))
    assert sv.ler_config()["robo_limite_max"] == 2                         # só grava depois de aprovar
    rodar(sv.salvar_faixa_robo(Msg("Aprovar ✅"), est))
    rodar(sv.pedir_janela_robo(Msg("Horário do Robô 🕗"), est))
    rodar(sv.confirmar_janela_robo(Msg("9-21"), est))
    rodar(sv.salvar_janela_robo(Msg("Aprovar ✅"), est))
    config = sv.ler_config()
    assert (config["robo_limite_min"], config["robo_limite_max"], config["robo_inicio"], config["robo_fim"]) == (2, 4, 9, 21)
    assert (config["limite_min"], config["inicio"]) == (5, 13)                # o assistente não muda
    texto = sv.texto_robo(config)
    assert "Rascunhos por dia: <b>2 a 4</b>" in texto and "Horário do robô: <b>das 9h às 21h</b>" in texto
    # O explorar no celular segue o mesmo horário.
    assert sv.robo.ps.horario_das_rodadas() == (9, 21)
    msg = Msg("30")
    rodar(sv.confirmar_faixa_robo(msg, Est(estado=sv.ShopeeVideoFluxo.aguardando_faixa_robo)))
    assert "⚠️" in msg.saidas[0]


def test_rascunhos_por_dia_com_os_botoes_faixa_e_fixo(bm, Msg, Est):
    # Pedido do Rafael (vídeo de 22/10): escolher Faixa ou Fixo num botão e só depois
    # digitar os números.
    sv, est = _painel(bm), Est()
    rodar(sv.pedir_faixa_robo(Msg("Rascunhos por Dia 📦"), est))
    assert _textos(sv.teclado_faixa_ou_fixo) == ["Faixa 🎲", "Fixo 📌", "Cancelar ❌"]
    assert est.estado == sv.ShopeeVideoFluxo.aguardando_tipo_faixa_robo
    rodar(sv.escolher_tipo_faixa(Msg("Faixa 🎲"), est))
    for errado in ("2", "3-3"):                                          # faixa pede mínimo < máximo
        msg = Msg(errado)
        rodar(sv.confirmar_faixa_robo(msg, est))
        assert "⚠️" in msg.saidas[0] and est.estado == sv.ShopeeVideoFluxo.aguardando_faixa_robo
    rodar(sv.confirmar_faixa_robo(Msg("1-3"), est))
    rodar(sv.salvar_faixa_robo(Msg("Aprovar ✅"), est))
    assert (sv.ler_config()["robo_limite_min"], sv.ler_config()["robo_limite_max"]) == (1, 3)

    est = Est()
    rodar(sv.pedir_faixa_robo(Msg("Rascunhos por Dia 📦"), est))
    rodar(sv.escolher_tipo_faixa(Msg("Fixo 📌"), est))
    msg = Msg("1-3")                                                     # fixo pede um número só
    rodar(sv.confirmar_faixa_robo(msg, est))
    assert "⚠️" in msg.saidas[0]
    msg = Msg("4")
    rodar(sv.confirmar_faixa_robo(msg, est))
    assert "<b>4 (fixo)</b>" in msg.saidas[0]
    rodar(sv.salvar_faixa_robo(Msg("Aprovar ✅"), est))
    assert (sv.ler_config()["robo_limite_min"], sv.ler_config()["robo_limite_max"]) == (4, 4)


def test_videos_por_dia_do_assistente_com_os_botoes_faixa_e_fixo(bm, Msg, Est):
    # Escolha do Rafael (22/10): o assistente igual ao robô.
    sv, est = _painel(bm), Est()
    msg = Msg("Vídeos por Dia 📦")
    rodar(sv.pedir_faixa(msg, est))
    assert "Faixa 🎲" in msg.saidas[0] and "Fixo 📌" in msg.saidas[0]
    assert est.estado == sv.ShopeeVideoFluxo.aguardando_tipo_faixa
    msg = Msg("Fixo 📌")
    rodar(sv.escolher_tipo_faixa(msg, est))
    assert "vídeos por dia" in msg.saidas[0] and est.estado == sv.ShopeeVideoFluxo.aguardando_faixa
    msg = Msg("5-10")
    rodar(sv.confirmar_faixa(msg, est))
    assert "⚠️" in msg.saidas[0]
    rodar(sv.confirmar_faixa(Msg("6"), est))
    rodar(sv.salvar_faixa(Msg("Aprovar ✅"), est))
    assert (sv.ler_config()["limite_min"], sv.ler_config()["limite_max"]) == (6, 6)
    assert (sv.ler_config()["robo_limite_min"], sv.ler_config()["robo_limite_max"]) == (1, 2)   # o robô não muda


def test_cancelar_na_escolha_de_faixa_ou_fixo_volta_a_tela_de_origem(bm, Msg, Est):
    sv = _painel(bm)
    for estado, tela in (("aguardando_tipo_faixa_robo", sv.ShopeeVideoFluxo.menu_robo),
                         ("aguardando_tipo_faixa", sv.ShopeeVideoFluxo.menu_assistente)):
        est = Est()
        rodar(sv.voltar_depois_de_cancelar(Msg("Cancelar ❌"), est, f"ShopeeVideoFluxo:{estado}"))
        assert est.estado == tela


class MsgComMidia:
    """Mensagem que também guarda os vídeos e as fotos mandados."""

    def __init__(self, Msg, texto):
        self.msg, self.midias = Msg(texto), []

    def __getattr__(self, nome):
        return getattr(self.msg, nome)

    async def answer_video(self, video, **kwargs):
        self.midias.append(("video", video.path, kwargs.get("caption", "")))

    async def answer_photo(self, foto, **kwargs):
        self.midias.append(("foto", foto.path, kwargs.get("caption", "")))


def test_edicao_dos_videos_comeca_desligada_e_liga_pelo_painel(bm, Msg, Est):
    # Escolha do Rafael (P37): a edição só vale nos vídeos dele (Autorais) e começa desligada,
    # até ele ver o exemplo e ligar.
    sv, est = _painel(bm), Est()
    assert not sv.ler_config()["edicao_ligada"] and "Edição dos vídeos: ⏸️" in sv.texto_robo(sv.ler_config())
    msg = Msg("Edição dos Vídeos ✂️")
    rodar(sv.edicao_handler(msg, est))
    texto = msg.saidas[-1]
    assert "todos os vídeos que o robô usa" in texto and "Viral" in texto and "Grupo Público" in texto
    assert "desligada" in texto and "O que cada botão faz" in texto
    # Pedido do Rafael (27/10): dois botões só, o Editor 1 sem legendas e o Editor 2 com legendas,
    # cada um com o vídeo completo e as versões. Escolha dele (28/10, P50 e P51): vai ao ar o
    # completo do Editor 2, nos rascunhos e no modo assistente; sem ele, o Editor 1.
    assert _textos(sv.teclado_edicao(sv.ler_config())) == [
        "Editor 1 sem Legendas 👀", "Editor 2 com Legendas ✨", "Ligar Edição ✅", "Voltar ao Robô 🔙"]
    assert "Editor 2 com legendas</b> (o que vai ao ar)" in texto
    assert "o vídeo original do Editor 2, nos rascunhos do robô e no modo assistente" in texto
    assert "ele vai com o Editor 1, sem legendas" in texto and "nada delas vai ao ar" in texto
    assert "(Editor 2, só o vídeo original, sem cortes)" in texto and "em teste" not in texto
    # Pedido do Rafael (vídeo de 28/10): o 1º vídeo é o original, sem cortes; as versões são modificadas.
    assert "vídeo original, sem cortar nada nem mudar a velocidade" in texto
    assert "ou se o vídeo já tem texto próprio na tela, ele vai sem os nossos textos" in texto
    assert ("O exemplo de cada editor</b>: primeiro o vídeo original, inteiro e sem cortes, só com as edições do "
            "editor, como vai ao ar; depois até 2 versões modificadas dele") in texto
    assert "segue dali (o que vinha antes vai para o fim)" in texto
    assert "a 1ª tem até uns 3/4 do vídeo original e a 2ª é a mais curta (pelo menos 8 s" in texto
    assert "Editor 3" not in texto and "Editor 4" not in texto
    rodar(sv.ligar_edicao_handler(Msg("Ligar Edição ✅"), est))
    assert sv.ler_config()["edicao_ligada"] and sv.edicao_video.vale_para("autorais")
    assert "Desligar Edição ⏸️" in _textos(sv.teclado_edicao(sv.ler_config()))
    rodar(sv.ligar_edicao_handler(Msg("Desligar Edição ⏸️"), est))
    assert not sv.edicao_video.vale_para("autorais")


def _rascunho(sv, titulo="Vestido Infantil 👗 #vestido", criado="2026-10-22 10:00:00"):
    robo = sv.robo
    ident = robo.criar("video:%s" % titulo, None)
    os.makedirs(robo.PASTA_RASCUNHOS, exist_ok=True)
    arquivo, print_tela = (os.path.join(robo.PASTA_RASCUNHOS, f"{ident}.{ext}") for ext in ("mp4", "png"))
    for caminho in (arquivo, print_tela):
        with open(caminho, "wb") as f:
            f.write(b"x")
    robo.atualizar(ident, estado="rascunho", criado_em=criado, titulo=titulo, link="https://s.shopee.com.br/x",
                   produtos=["Vestido Infantil"], comentario="Amei!", arquivo=arquivo, print=print_tela)
    return ident


def test_rascunhos_um_por_um_com_video_print_titulo_e_link(bm, Msg, Est):
    sv, est = _painel(bm), Est()
    primeiro = _rascunho(sv, "Primeiro título #a")
    segundo = _rascunho(sv, "Segundo título #b", "2026-10-22 11:00:00")
    msg = MsgComMidia(Msg, "Rascunhos do Robô 📝")
    rodar(sv.rascunhos_handler(msg, est))
    assert [m[0] for m in msg.midias] == ["video", "foto"]
    texto = msg.saidas[-1]
    assert "Rascunho 1 de 2" in texto and "Primeiro título #a" in texto and "https://s.shopee.com.br/x" in texto
    assert "Vestido Infantil" in texto
    msg = MsgComMidia(Msg, "Aprovar Rascunho ✅")
    rodar(sv.aprovar_handler(msg, est))
    assert sv.robo.pegar(primeiro)["estado"] == "aprovado" and sv.robo.pegar(primeiro)["postar_em"]
    assert "Aprovado" in msg.saidas[0] and "Segundo título #b" in msg.saidas[-1]
    msg = MsgComMidia(Msg, "Recusar Rascunho ❌")
    rodar(sv.pedir_recusa(msg, est))
    assert sv.robo.pegar(segundo)["estado"] == "rascunho"                    # pede confirmação antes
    msg = MsgComMidia(Msg, "Confirmar Recusa ✅")
    rodar(sv.salvar_recusa(msg, est))
    assert sv.robo.pegar(segundo)["estado"] == "recusado"
    # Pedido do Rafael (24/10): no fim, só a frase, sem o texto do painel inteiro.
    assert msg.saidas[-2:] == ["❌ Recusado. O robô apaga o rascunho do celular na próxima rodada.",
                               "📝 Nenhum rascunho esperando a sua aprovação."]
    assert not any("Quem posta agora" in s for s in msg.saidas)


def test_aprovar_o_ultimo_mostra_so_as_duas_frases(bm, Msg, Est):
    # Pedido do Rafael (24/10): depois de aprovar, só o "Aprovado" e o "Nenhum rascunho",
    # com o teclado do painel, sem o texto do painel inteiro.
    sv, est = _painel(bm), Est()
    _rascunho(sv, "Único título #a")
    rodar(sv.rascunhos_handler(MsgComMidia(Msg, "Rascunhos do Robô 📝"), est))
    msg = MsgComMidia(Msg, "Aprovar Rascunho ✅")
    rodar(sv.aprovar_handler(msg, est))
    assert len(msg.saidas) == 2 and msg.saidas[0].startswith("✅ Aprovado.")
    assert msg.saidas[1] == "📝 Nenhum rascunho esperando a sua aprovação."
    assert est.estado == sv.ShopeeVideoFluxo.menu


def test_proximo_rascunho_da_a_volta(bm, Msg, Est):
    sv, est = _painel(bm), Est()
    _rascunho(sv, "Primeiro #a")
    _rascunho(sv, "Segundo #b", "2026-10-22 11:00:00")
    rodar(sv.rascunhos_handler(MsgComMidia(Msg, "Rascunhos do Robô 📝"), est))
    msg = MsgComMidia(Msg, "Próximo Rascunho ⏭️")
    rodar(sv.proximo_handler(msg, est))
    assert "Segundo #b" in msg.saidas[-1]
    msg = MsgComMidia(Msg, "Próximo Rascunho ⏭️")
    rodar(sv.proximo_handler(msg, est))
    assert "Primeiro #a" in msg.saidas[-1]


def test_aprovar_rascunho_ja_resolvido_mostra_o_proximo(bm, Msg, Est):
    sv = _painel(bm)
    ident = _rascunho(sv)
    sv.robo.recusar(ident)
    msg = MsgComMidia(Msg, "Aprovar Rascunho ✅")
    rodar(sv.aprovar_handler(msg, Est(dados={"rascunho_id": ident})))
    assert sv.robo.pegar(ident)["estado"] == "recusado" and "já foi resolvido" in msg.saidas[0]


def test_robo_roda_a_cada_15_min_so_ativo_e_no_horario(bm, monkeypatch):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    sv = _painel(bm)
    agendador = AsyncIOScheduler(timezone=bm.FUSO_STR)
    sv.configurar_dependencias(sv.bot_instance, agendador, sv.ADMIN_ID)
    from datetime import datetime
    from fuso import fuso_horario
    job = agendador.get_job("shopee_video_robo")
    assert job.trigger.interval.total_seconds() == 900
    # Depois de um reinício, a primeira volta sai em 2 min, não em 15 (23/10: os deploys
    # seguidos atrasaram o post aprovado).
    falta = (job.next_run_time - datetime.now(fuso_horario)).total_seconds()
    assert 60 < falta <= 120
    rodadas = []

    async def rodar_robo(*argumentos):
        rodadas.append(argumentos)

    monkeypatch.setattr(sv, "rodar_robo", rodar_robo)
    rodar(sv.verificar_robo())
    assert rodadas == []                                                     # começa pausado
    sv.alterar_config(robo_pausado=False, robo_inicio=0, robo_fim=24)
    rodar(sv.verificar_robo())
    assert rodadas == [("--rodada",)]


def test_testar_caminho_roda_o_treino_na_hora(bm, Msg, Est, monkeypatch):
    sv = _painel(bm)
    rodadas = []

    async def rodar_robo(*argumentos):
        rodadas.append(argumentos)

    monkeypatch.setattr(sv, "rodar_robo", rodar_robo)

    async def tocar():
        msg = Msg("Testar Caminho 🧭")
        await sv.treino_handler(msg, Est())
        await __import__("asyncio").sleep(0)
        return msg

    msg = rodar(tocar())
    assert rodadas == [("--treino",)] and "Treino começando" in msg.saidas[0]


def test_cancelar_volta_ao_painel_sem_mudar_nada(bm, Msg, Est):
    sv = _painel(bm)
    est = Est(estado=sv.ShopeeVideoFluxo.aguardando_faixa)
    msg = Msg("Cancelar ❌")
    rodar(bm.cancelar_fluxo_global(msg, est))
    # Volta à tela de onde o ajuste saiu: o Modo Assistente.
    assert "cancelada" in msg.saidas[0] and "Modo Assistente" in msg.saidas[-1]
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.menu_assistente.state
    assert sv.ler_config()["limite_min"] == 5


def test_ajuste_grava_sem_apagar_o_que_o_motor_guardou(bm):
    sv = _painel(bm)
    bm.db.salvar_config("shopee_video", {"ultimo_post": "2026-10-04 13:10"})
    sv.alterar_config(pausado=False)
    assert bm.db.ler_config("shopee_video")["ultimo_post"] == "2026-10-04 13:10"


def test_botoes_vem_antes_das_respostas_de_texto(bm):
    # No aiogram ganha o primeiro handler que casar: um botão tocado no meio de um ajuste
    # tem de abrir o botão, e não ser lido como resposta.
    sv = _painel(bm)
    ordem = [h.callback.__name__ for h in sv.router.message.handlers]
    botoes = ("painel_handler", "menu_robo_handler", "menu_assistente_handler", "como_funciona_handler",
              "voltar_ao_robo", "pedir_faixa", "pedir_janela", "pedir_pausa", "enviar_agora_handler",
              "pedir_fonte", "pedir_pausa_robo", "pedir_faixa_robo", "escolher_tipo_faixa", "pedir_janela_robo",
              "pedir_janela_interacoes", "treino_handler", "preparar_handler",
              "rascunhos_handler", "aprovar_handler", "pedir_recusa", "proximo_handler")
    respostas = ("confirmar_faixa", "confirmar_janela", "salvar_fonte", "confirmar_com_os_botoes",
                 "confirmar_faixa_robo", "confirmar_janela_robo", "confirmar_janela_interacoes", "salvar_recusa")
    assert max(ordem.index(b) for b in botoes) < min(ordem.index(r) for r in respostas)


def test_so_o_admin_usa_o_painel(bm, Msg, Est):
    sv = _painel(bm)
    for handler, texto in ((sv.painel_handler, "Shopee Vídeo 🎬"), (sv.pedir_faixa, "Vídeos por Dia 📦"),
                           (sv.pedir_pausa, "Retomar Robô ▶️"), (sv.enviar_agora_handler, "Enviar 1 Agora 📤"),
                           (sv.pedir_pausa_robo, "Retomar Postagem ▶️"), (sv.rascunhos_handler, "Rascunhos do Robô 📝"),
                           (sv.treino_handler, "Testar Caminho 🧭"), (sv.preparar_handler, "Preparar 1 Agora ⚡"), (sv.aprovar_handler, "Aprovar Rascunho ✅")):
        msg = Msg(texto, user_id=123)
        rodar(handler(msg, Est()))
        assert msg.saidas == [], texto


def test_enviar_agora_manda_mesmo_pausado(bm, Msg, Est, monkeypatch):
    sv = _painel(bm)
    pedidos = []

    async def preparar(bot, admin_id, agora=None, fonte=None):
        pedidos.append((admin_id, fonte))
        return "postagem mandada no seu privado"

    monkeypatch.setattr(sv.assistente, "preparar_e_enviar", preparar)
    msg = Msg("Enviar 1 Agora 📤")
    rodar(sv.enviar_agora_handler(msg, Est()))
    assert pedidos == [(sv.ADMIN_ID, "autorais")] and sv.ler_config()["pausado"] is True
    assert "Preparando" in msg.saidas[0] and len(msg.saidas) == 1


def test_enviar_agora_diz_por_que_nao_mandou(bm, Msg, Est, monkeypatch):
    sv = _painel(bm)

    async def sem_video(bot, admin_id, agora=None, fonte=None):
        return "não há vídeo em Autorais 🎥 para mandar (a fila está vazia ou sem arquivos)"

    async def quebra(bot, admin_id, agora=None, fonte=None):
        raise RuntimeError("segredo")

    monkeypatch.setattr(sv.assistente, "preparar_e_enviar", sem_video)
    msg = Msg("Enviar 1 Agora 📤")
    rodar(sv.enviar_agora_handler(msg, Est()))
    assert "Não mandei: não há vídeo em Autorais 🎥" in msg.saidas[-1]
    monkeypatch.setattr(sv.assistente, "preparar_e_enviar", quebra)
    msg = Msg("Enviar 1 Agora 📤")
    rodar(sv.enviar_agora_handler(msg, Est()))
    assert "deu erro ao preparar (RuntimeError)" in msg.saidas[-1] and "segredo" not in msg.saidas[-1]


def test_agendador_so_manda_quando_chega_a_hora_e_nao_pausado(bm, monkeypatch):
    sv = _painel(bm)
    pedidos = []

    async def preparar(bot, admin_id, agora=None, fonte=None):
        pedidos.append(fonte)
        return "postagem mandada no seu privado"

    monkeypatch.setattr(sv.assistente, "preparar_e_enviar", preparar)
    monkeypatch.setattr(sv.assistente, "decidir_envio", lambda config: not config["pausado"])
    rodar(sv.verificar_envio())
    assert pedidos == []                                                   # começa pausado
    sv.alterar_config(pausado=False, fonte="viral")
    rodar(sv.verificar_envio())
    assert pedidos == ["viral"]


def test_envio_fica_no_agendador_a_cada_5_min(bm):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    sv = _painel(bm)
    agendador = AsyncIOScheduler(timezone=bm.FUSO_STR)
    sv.configurar_dependencias(sv.bot_instance, agendador, sv.ADMIN_ID)
    job = agendador.get_job("shopee_video_assistente")
    assert job is not None and job.trigger.interval.total_seconds() == 300


def test_fonte_dos_videos_muda_pelos_botoes(bm, Msg, Est):
    sv, est = _painel(bm), Est()
    msg = Msg("Fonte dos Vídeos 🎞️")
    rodar(sv.pedir_fonte(msg, est))
    assert "Hoje: <b>Autorais 🎥</b>" in msg.saidas[0] and "7.2.1" in msg.saidas[0]
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.aguardando_fonte.state
    msg = Msg("Canal Afiliados 📺")
    rodar(sv.salvar_fonte(msg, est))
    assert sv.ler_config()["fonte"] == "principal" and "Canal Afiliados 📺" in msg.saidas[0]
    assert "Fonte dos vídeos: <b>Canal Afiliados 📺</b>" in msg.saidas[-1]


def test_fonte_cancelada_nao_muda_nada(bm, Msg, Est):
    sv = _painel(bm)
    est = Est(estado=sv.ShopeeVideoFluxo.aguardando_fonte)
    rodar(bm.cancelar_fluxo_global(Msg("Cancelar ❌"), est))
    assert sv.ler_config()["fonte"] == "autorais"


def test_rascunho_mostra_a_origem_e_o_que_a_ia_conferiu(bm):
    # Escolha do Rafael (23/10): validar cada rascunho também pela origem do vídeo (com o
    # alerta de vídeo copiado) e pelo que a IA viu nas duas conferências.
    sv = _painel(bm)
    rascunho = {"criado_em": "2026-10-23 10:00:00", "titulo": "Lustre", "produtos": ["Lustre Escandinavo"],
                "link": "https://s.shopee.com.br/x", "motivo": "", "fonte": "viral",
                "conferencia": '["o vídeo mostra um lustre de 3 cores", "lustre igual ao do link"]'}
    texto = sv.texto_rascunho(rascunho, 1, 1)
    assert "Origem do vídeo:</b> Viral (Espião)" in texto and "propriedade intelectual" in texto
    assert "(2 vezes)" in texto and "1ª: o vídeo mostra um lustre de 3 cores" in texto and "2ª: lustre igual" in texto
    texto = sv.texto_rascunho(dict(rascunho, fonte="autorais"), 1, 1)
    assert "Autorais" in texto and "propriedade intelectual" not in texto
    # Rascunho de antes desta mudança: sem origem nem conferência, o texto continua certo.
    texto = sv.texto_rascunho(dict(rascunho, fonte=None, conferencia=None), 1, 1)
    assert "Origem" not in texto and "A IA conferiu" not in texto and "Lustre Escandinavo" in texto


def test_rascunho_mostra_o_link_de_cada_produto_a_mais(bm):
    # Os espaços livres (P59): o mesmo item de outras lojas, com o link de cada um, na ordem do post.
    sv = _painel(bm)
    rascunho = {"criado_em": "2026-10-29 10:00:00", "titulo": "Garrafa", "produtos": ["Garrafa A", "Garrafa B"],
                "link": "https://s.shopee.com.br/a", "motivo": "", "fonte": "viral", "conferencia": None,
                "mais_produtos": [{"nome": "Garrafa B", "link": "https://s.shopee.com.br/b", "endereco": ""}]}
    texto = sv.texto_rascunho(rascunho, 1, 1)
    assert "Produtos anexados" in texto and texto.index("🔗 https://s.shopee.com.br/a") < texto.index(
        "🔗 https://s.shopee.com.br/b")
    # O rascunho de antes, sem os produtos a mais, continua com o link dele.
    assert "🔗 https://s.shopee.com.br/a" in sv.texto_rascunho(dict(rascunho, mais_produtos=None), 1, 1)


def test_preparar_1_agora_roda_o_robo_na_hora(bm, Msg, Est, monkeypatch):
    sv = _painel(bm)
    chamadas = []

    async def rodar_robo(*argumentos):
        chamadas.append(argumentos)

    monkeypatch.setattr(sv, "rodar_robo", rodar_robo)
    msg = Msg("Preparar 1 Agora ⚡")

    async def tocar():
        await sv.preparar_handler(msg, Est())
        await sv.asyncio.sleep(0)

    rodar(tocar())
    assert chamadas == [("--preparar",)] and "Preparando 1 rascunho" in msg.saidas[0]


def test_treino_sem_resultado_depois_de_meia_hora_diz_que_nao_terminou(bm):
    # Painel do Rafael (23/10, 04:53): "Treino: ⚠️ rodando em 23/10 às 00:00", parado assim
    # desde a meia-noite, porque o treino não terminou e nada gravou o resultado.
    from datetime import datetime
    sv = _painel(bm)
    sv.robo.gravar_estado(treino_em="2026-10-23 00:00:00", treino_resultado="")
    assert sv._linha_treino(datetime(2026, 10, 23, 0, 10)) == "⏳ rodando desde 23/10 às 00:00"
    linha = sv._linha_treino(datetime(2026, 10, 23, 4, 53))
    assert linha.startswith("⚠️ o treino de 23/10 às 00:00 não terminou") and sv.BOTAO_TREINO in linha
    sv.robo.gravar_estado(treino_resultado="ok")
    assert sv._linha_treino(datetime(2026, 10, 23, 4, 53)) == "✅ caminho OK em 23/10 às 00:00"



def test_treino_adiado_pela_suspensao_aparece_no_painel(bm):
    # Escolha do Rafael (P41): o treino da segunda que caiu na suspensão roda logo depois dela.
    sv = _painel(bm)
    sv.robo.gravar_estado(treino_em="2026-10-19 10:00:00", treino_resultado="ok", treino_depois_da_suspensao=True)
    assert sv._linha_treino() == "⏳ o desta semana roda logo que a suspensão acabar"
    sv.robo.gravar_estado(treino_depois_da_suspensao=False)
    assert sv._linha_treino().startswith("✅ caminho OK")


def test_historico_do_robo_mostra_as_tentativas_e_o_resumo_das_22h(bm, Msg, Est, monkeypatch):
    # Escolha do Rafael (23/10): ver o que o robô já tentou, o que deu errado e onde parou.
    sv, est = _painel(bm), Est()
    msg = Msg("Histórico do Robô 📋")
    rodar(sv.historico_handler(msg, est))
    assert "Nenhuma tentativa" in msg.saidas[-1]
    sv.robo.registrar_tentativa("rascunho", "pulado", "o nome do produto do vídeo não está na página: nada tocado",
                                "Copo <Térmico>")
    rodar(sv.historico_handler(msg, est))
    texto = msg.saidas[-1]
    assert "⏭️ 1 pulado" in texto and "Copo &lt;Térmico&gt;" in texto and "curtir o produto" in texto
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.menu_robo.state
    enviados = []

    class Bot:
        async def send_message(self, chat, texto, **kwargs):
            enviados.append((chat, texto))

    monkeypatch.setattr(sv, "bot_instance", Bot())
    rodar(sv.mandar_resumo_do_robo())
    assert enviados and "Resumo do Robô" in enviados[0][1] and "curtir o produto: 1×" in enviados[0][1]


def test_fila_de_rascunhos_mostra_a_lista_no_menu_do_robo(bm, Msg, Est):
    # Pedido do Rafael (25/10): ver os rascunhos esperando aprovação e os aprovados.
    sv, est = _painel(bm), Est()
    msg = Msg("Fila de Rascunhos 🗂️")
    rodar(sv.fila_handler(msg, est))
    assert "Fila de Rascunhos" in msg.saidas[-1] and msg.saidas[-1].count("nenhum") == 2
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.menu_robo.state


def test_conta_suspensa_deixa_os_dois_em_espera_e_o_fim_avisa_no_privado(bm, monkeypatch):
    # Escolha do Rafael (23/10, P4): com a conta suspensa pela Shopee, o assistente espera e o
    # robô não posta; no fim, os dois voltam sozinhos e o privado recebe o aviso. Pedido de
    # 25/10: na suspensão a rodada do robô segue (ele só não prepara, não posta e não treina).
    from datetime import datetime, timedelta
    from fuso import fuso_horario
    sv = _painel(bm)
    pedidos, rodadas, enviados = [], [], []

    async def preparar(bot, admin_id, agora=None, fonte=None):
        pedidos.append(fonte)
        return "postagem mandada no seu privado"

    async def rodar_robo(*argumentos):
        rodadas.append(argumentos)

    class Bot:
        async def send_message(self, chat, texto, **kwargs):
            enviados.append(texto)

    monkeypatch.setattr(sv.assistente, "preparar_e_enviar", preparar)
    monkeypatch.setattr(sv.assistente, "decidir_envio", lambda config: not config["pausado"])
    monkeypatch.setattr(sv, "rodar_robo", rodar_robo)
    monkeypatch.setattr(sv, "bot_instance", Bot())
    fim = datetime.now(fuso_horario) + timedelta(days=2)
    sv.alterar_config(pausado=False, robo_pausado=True, robo_inicio=0, robo_fim=24,
                      robo_suspenso_ate=fim.strftime("%Y-%m-%d %H:%M:%S"))
    # O Rafael pausou o robô no meio da suspensão: mesmo assim o assistente espera.
    rodar(sv.verificar_envio())
    assert pedidos == [] and "suspensa pela Shopee" in sv.texto_assistente(sv.ler_config())
    assert "suspendeu a conta" in sv.texto_painel(sv.ler_config())
    assert "Pausado" in sv.texto_robo(sv.ler_config()) and "suspensa" in sv.texto_robo(sv.ler_config())
    rodar(sv.verificar_robo())
    assert rodadas == []                                   # pausado pelo Rafael: nada roda
    sv.alterar_config(robo_pausado=False)
    rodar(sv.verificar_robo())
    assert rodadas == [("--rodada",)] and enviados == [] and "Sem postar" in sv.texto_robo(sv.ler_config())
    # Acabou (com a folga): o aviso chega, e o robô roda na mesma volta.
    sv.alterar_config(robo_suspenso_ate=(datetime.now(fuso_horario) - timedelta(minutes=20)).strftime(
        "%Y-%m-%d %H:%M:%S"))
    rodar(sv.verificar_robo())
    assert len(enviados) == 1 and "acabou" in enviados[0] and rodadas == [("--rodada",), ("--rodada",)]
    assert "robo_suspenso_ate" not in sv.ler_config()


def test_saude_em_relatorio_geral_lembra_as_punicoes_e_os_botoes_param(bm, Msg, Est, monkeypatch):
    # Pedidos do Rafael (23/10): a Saúde em Relatório Geral, o texto do recurso no privado e
    # o lembrete de hora em hora até Já recorri ou Não vou recorrer.
    from types import SimpleNamespace
    sv = _painel(bm)
    assert sv.BOTAO_SAUDE in _textos(bm.obter_teclado_relatorios())
    ident = sv.apelacoes.guardar("Produto Irrelevante", "23/10/2026 19:04:25", "Não Recorrido",
                                 titulo="Botijão Térmico", texto="O vídeo mostra o produto do anúncio.")
    sv.robo.gravar_estado(saude_lida_em="2026-10-24 10:00:00", saude_pontos=6)
    msg = Msg(sv.BOTAO_SAUDE)
    rodar(sv.saude_handler(msg, Est()))
    assert "Pontos de penalidade: <b>6</b>" in msg.saidas[-1] and "Botijão Térmico" in msg.saidas[-1]
    assert sv.BOTAO_GERAR_APELACAO in _textos(sv.teclado_saude())
    rodadas = []

    async def rodar_robo(*argumentos):
        rodadas.append(argumentos)
    monkeypatch.setattr(sv, "rodar_robo", rodar_robo)
    rodar(sv.gerar_apelacao_handler(Msg(sv.BOTAO_GERAR_APELACAO), Est()))
    rodar(__import__("asyncio").sleep(0))
    assert rodadas == [("--saude",)]

    enviados, apagadas, editadas = [], [], []

    class Bot:
        async def send_message(self, chat, texto, **kwargs):
            enviados.append((texto, kwargs.get("reply_markup")))
            return SimpleNamespace(message_id=900 + len(enviados))

        async def delete_message(self, chat, mensagem):
            if mensagem == 901:
                # O primeiro aviso passou das 48 h: o Telegram não deixa apagar.
                raise RuntimeError("message can't be deleted")
            apagadas.append(mensagem)

        async def edit_message_text(self, text, chat_id=None, message_id=None):
            editadas.append((message_id, text))
    monkeypatch.setattr(sv, "bot_instance", Bot())
    rodar(sv.lembrar_apelacoes())
    texto, teclado = enviados[0]
    assert "<code>O vídeo mostra o produto do anúncio.</code>" in texto
    # Mais dois lembretes, de hora em hora; os ids ficam guardados para apagar depois.
    for _ in range(2):
        with sv.db.conexao() as con:
            con.execute("UPDATE shopee_video_punicoes SET ultimo_aviso = '2000-01-01 00:00:00'")
        rodar(sv.lembrar_apelacoes())
    assert sv.apelacoes.mensagens_de(ident) == [901, 902, 903]
    botao_recorri = enviados[-1][1].inline_keyboard[0][0]
    respostas, teclados = [], []
    mensagem = Msg()
    mensagem.message_id = 903

    async def editar(reply_markup=None):
        teclados.append(reply_markup)
    mensagem.edit_reply_markup = editar

    async def responder(texto, **k):
        respostas.append(texto)
    clique = SimpleNamespace(data=botao_recorri.callback_data, from_user=SimpleNamespace(id=bm.ADMIN_ID),
                             message=mensagem, answer=responder)
    rodar(sv.decisao_da_apelacao(clique))
    assert "você recorreu" in respostas[0] and teclados == [None]
    assert sv.apelacoes.pegar(ident)["situacao"] == "recorrida"
    # Escolha do Rafael (24/10, P7): os lembretes de antes saem do privado; fica a tocada.
    assert apagadas == [902] and editadas == [(901, sv.LEMBRETE_RESOLVIDO)]
    assert sv.apelacoes.mensagens_de(ident) == [903]
    rodar(sv.lembrar_apelacoes())
    assert len(enviados) == 3


def _comandos(sv, monkeypatch, criada=0, voltas_ativa=1):
    """O systemd falso: o systemd-run devolve `criada`; a unidade fica ativa por `voltas_ativa` consultas."""
    pedidos = []

    async def comando(*partes, espera=30):
        pedidos.append(partes)
        if "systemd-run" in partes:
            return criada
        return 0 if sum("is-active" in p for p in pedidos) <= voltas_ativa else 3

    async def sem_espera(segundos):
        pass

    monkeypatch.setattr(sv, "_comando", comando)
    monkeypatch.setattr(sv.asyncio, "sleep", sem_espera)
    return pedidos


def test_rodada_roda_numa_unidade_propria_e_o_reinicio_do_bot_nao_a_mata(bm, monkeypatch):
    from conftest import consultar
    sv = _painel(bm)
    pedidos = _comandos(sv, monkeypatch, voltas_ativa=2)
    monkeypatch.setattr(sv.asyncio, "create_subprocess_exec",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("não devia rodar dentro do bot")))
    rodar(sv.rodar_robo("--rodada"))
    criar = pedidos[0]
    assert criar[:3] == ("sudo", "-n", "systemd-run") and criar[-2:] == (sv.ROBO, "--rodada")
    assert "--property=SyslogIdentifier=robo_shopee_video" in criar and any(p.startswith("--uid=") for p in criar)
    # O bot espera a unidade acabar (uma rodada de cada vez) e anota no registro.
    assert sum("is-active" in p for p in pedidos) == 3 and not sv._rodada.locked()
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = 'rodada fora do bot'") == (
        "unidade própria", 1)


def test_sem_o_systemd_run_a_rodada_vai_como_processo_do_bot(bm, monkeypatch):
    from conftest import consultar
    sv = _painel(bm)
    _comandos(sv, monkeypatch, criada=1)
    iniciados = []

    class Processo:
        async def wait(self):
            return 0

    async def iniciar(*partes, **opcoes):
        iniciados.append(partes)
        return Processo()

    monkeypatch.setattr(sv.asyncio, "create_subprocess_exec", iniciar)
    rodar(sv.rodar_robo("--preparar"))
    assert iniciados == [(sv.sys.executable, sv.ROBO, "--preparar")]
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = 'rodada fora do bot'") == (
        "sem systemd-run", 0)


def test_rodada_de_antes_do_reinicio_no_celular_segura_os_botoes_e_o_agendador(bm, Msg, Est, monkeypatch):
    sv = _painel(bm)
    rodadas = []

    async def rodar_robo(*argumentos):
        rodadas.append(argumentos)

    monkeypatch.setattr(sv, "rodar_robo", rodar_robo)
    monkeypatch.setattr(sv.celular_robo, "ocupado", lambda: True)
    sv.alterar_config(robo_pausado=False, robo_inicio=0, robo_fim=24)
    rodar(sv.verificar_robo())
    for botao, handler in (("Preparar 1 Agora ⚡", sv.preparar_handler), ("Testar Caminho 🧭", sv.treino_handler)):
        msg = Msg(botao)
        rodar(handler(msg, Est()))
        assert "no meio de uma rodada" in msg.saidas[0]
    assert rodadas == []


def test_horario_das_interacoes_separa_as_horas_de_postar(bm, Msg, Est):
    # Escolha do Rafael (24/10, P22 a P24): um botão próprio; nele só responder e o feed,
    # fora dele só preparar e postar.
    sv, est = _painel(bm), Est()
    sv.alterar_config(robo_inicio=8, robo_fim=22)
    assert "Horário das interações: <b>junto com o Horário do Robô</b>" in sv.texto_robo(sv.ler_config())
    msg = Msg("Horário das Interações 💬")
    rodar(sv.pedir_janela_interacoes(msg, est))
    assert "só volta a preparar e postar quando acaba" in msg.saidas[0]
    msg = Msg("12-15")
    rodar(sv.confirmar_janela_interacoes(msg, est))
    assert sv.ler_config()["robo_interacoes_inicio"] is None                 # só grava depois de aprovar
    assert "preparar e postar <b>das 8h às 12h e das 15h às 22h</b>" in msg.saidas[0]
    rodar(sv.salvar_janela_interacoes(Msg("Aprovar ✅"), est))
    config = sv.ler_config()
    assert (config["robo_interacoes_inicio"], config["robo_interacoes_fim"]) == (12, 15)
    assert config["robo_interacoes_desde"]                                   # o checkup cobra só daqui
    texto = sv.texto_robo(config)
    assert "Horário das interações: <b>das 12h às 15h</b>" in texto
    assert "prepara e posta das 8h às 12h e das 15h às 22h" in texto
    # Os rascunhos que faltam hoje saem do plano novo, fora da janela.
    assert all(not "12:00" <= h < "15:00" for h in bm.db.ler_config(sv.robo.CHAVE_DIA)["horarios"])


def test_horario_das_interacoes_recusa_o_que_tira_toda_a_hora_de_postar(bm, Msg, Est):
    sv = _painel(bm)
    sv.alterar_config(robo_inicio=9, robo_fim=12)
    for texto in ("Dia Todo", "8-13", "15-12"):
        msg = Msg(texto)
        rodar(sv.confirmar_janela_interacoes(msg, Est(estado=sv.ShopeeVideoFluxo.aguardando_janela_interacoes)))
        assert "⚠️" in msg.saidas[0], texto
    assert sv.ler_config()["robo_interacoes_inicio"] is None


def test_junto_com_o_robo_volta_as_interacoes_para_o_horario_do_robo(bm, Msg, Est):
    sv, est = _painel(bm), Est()
    sv.alterar_config(robo_interacoes_inicio=12, robo_interacoes_fim=15)
    rodar(sv.confirmar_janela_interacoes(Msg("Junto com o Robô 🔁"), est))
    rodar(sv.salvar_janela_interacoes(Msg("Aprovar ✅"), est))
    assert sv.robo.janela_das_interacoes(sv.ler_config()) is None


def test_exemplo_cortado_por_um_reinicio_e_avisado_ao_ligar(bm, Msg, Est, monkeypatch):
    # 27/10: o Rafael tocou no Editor 2 às 23:05 e o deploy reiniciou o bot às 23:07; o
    # exemplo sumiu sem aviso. Ao ligar, o bot avisa e pede para tocar de novo.
    from datetime import datetime, timedelta
    sv, est = _painel(bm), Est()
    enviados = []

    class Bot:
        async def send_message(self, chat, texto, **kwargs):
            enviados.append((chat, texto))

    monkeypatch.setattr(sv, "bot_instance", Bot())
    agora = datetime.now(sv.fuso_horario)
    sv.db.salvar_config(sv.CHAVE_EXEMPLO_EM_ANDAMENTO, {"editor": 2, "desde": (agora - timedelta(minutes=2)).isoformat()})
    rodar(sv.avisar_exemplo_interrompido())
    assert len(enviados) == 1 and enviados[0][0] == sv.ADMIN_ID
    assert "Editor 2 (com legendas) foi interrompido" in enviados[0][1] and "Editor 2 com Legendas ✨" in enviados[0][1]
    assert not sv.db.ler_config(sv.CHAVE_EXEMPLO_EM_ANDAMENTO, {})
    # Ligar de novo não repete; anotação velha (de horas atrás) não avisa.
    rodar(sv.avisar_exemplo_interrompido())
    sv.db.salvar_config(sv.CHAVE_EXEMPLO_EM_ANDAMENTO, {"editor": 1, "desde": (agora - timedelta(hours=3)).isoformat()})
    rodar(sv.avisar_exemplo_interrompido())
    assert len(enviados) == 1
    # O exemplo que termina (saindo ou não) apaga a anotação.
    monkeypatch.setattr(sv.edicao_video, "exemplo_editor_1", lambda destino: (None, "nenhum vídeo dos Autorais", None))
    rodar(sv.exemplo_editor_1_handler(MsgComMidia(Msg, "Editor 1 sem Legendas 👀"), est))
    assert not sv.db.ler_config(sv.CHAVE_EXEMPLO_EM_ANDAMENTO, {})
    # A anotação de antes da junção dos editores (Editor 3) avisa com o botão do Editor 1.
    sv.db.salvar_config(sv.CHAVE_EXEMPLO_EM_ANDAMENTO, {"editor": 3, "desde": (agora - timedelta(minutes=5)).isoformat()})
    rodar(sv.avisar_exemplo_interrompido())
    assert "Editor 1 (sem legendas) foi interrompido" in enviados[-1][1] and "Editor 1 sem Legendas 👀" in enviados[-1][1]


def _exemplo_com_versoes(sv, destino, versoes):
    """Grava os arquivos do exemplo e devolve a lista de resumo["versoes"] com eles."""
    lista = []
    for numero, versao in enumerate(versoes, 1):
        arquivo = sv.edicao_video.arquivo_da_versao(destino, numero)
        with open(arquivo, "wb") as saida:
            saida.write(b"editado")
        lista.append(dict(versao, arquivo=arquivo))
    return lista


def test_exemplo_do_editor_1_manda_o_completo_e_as_versoes_sem_legendas(bm, Msg, Est, monkeypatch):
    # Pedidos do Rafael (27/10): o Editor 1 sem legendas manda o vídeo completo, como ele entrega,
    # e as versões, sem textos; nada fica no servidor.
    sv, est = _painel(bm), Est()

    def exemplo_editor_1(destino):
        versoes = _exemplo_com_versoes(sv, destino, [
            {"remontado": 12.0, "curta": False, "textos": [], "gancho": None, "vantagem": ""},
            {"remontado": 9.0, "curta": True, "textos": [], "gancho": (4.0, 6.0), "vantagem": "Fechamento com zíper",
             "musica": "calma"}])
        return "Bolsa", "", {"original": 12.0, "inteiro": 12.0, "com_fala": 0, "versoes_da_ia": 1, "lugar_da_ia": False,
                             "remontagem": {"cortado": 2.0, "acelerados": 1, "camera_lenta": 1, "com_fala": 0},
                             "versoes": versoes}

    monkeypatch.setattr(sv.edicao_video, "exemplo_editor_1", exemplo_editor_1)
    msg = MsgComMidia(Msg, "Editor 1 sem Legendas 👀")
    rodar(sv.exemplo_editor_1_handler(msg, est))
    assert any("Montando o exemplo do Editor 1 (sem legendas)" in t for t in msg.saidas)
    completo, versao = msg.midias[0][2], msg.midias[1][2]
    assert "Exemplo do Editor 1 (sem legendas), vídeo 1 de 2 (não foi postado): Bolsa." in completo
    # Pedidos do Rafael (vídeos de 28/10): fica claro qual é o original e qual é versão
    # modificada, com o título no alto da legenda e uma linha em branco antes do resto.
    assert completo.startswith("🎬 <b>VÍDEO ORIGINAL</b>\n\n👀 Exemplo do Editor 1")
    assert ("\nInteiro, na ordem e na velocidade dele, sem cortes; só com as edições que você "
            "pediu (a foto no começo, a miniatura e a seta).") in completo
    assert "vai ao ar" not in completo and "(mais os 2 s da foto): o vídeo inteiro" in completo
    assert versao.startswith("✂️ <b>VERSÃO MODIFICADA 1 de 1</b>\n\n👀 Exemplo do Editor 1 (sem legendas), vídeo 2 de 2")
    assert "\nSó no exemplo, não vai ao ar: abre com o trecho de 4,0 s a 6,0 s" in versao
    assert "do vídeo original (o que ele mostra: “Fechamento com zíper”) e segue dali; o que vinha antes vai para o fim" in versao
    assert "(mais os 2 s da foto): 75% do vídeo completo, a mais curta" in versao
    assert not any("Textos na tela" in legenda or "Lugar do texto" in legenda for legenda in (completo, versao))
    # Pedido do Rafael (vídeo de 28/10, 00:12): as versões do Editor 1 seguem o padrão do Editor 2
    # (remontadas), só sem legendas; a legenda diz o que cada uma mudou.
    assert "Partes paradas tiradas: 2 s" in versao and "Trechos acelerados: 1 | 🐢 Em câmera lenta: 1" in versao
    assert "Partes paradas" not in completo
    # Escolha do Rafael (P55): o vídeo sem som leva uma música de fundo, e a legenda diz qual.
    assert "🎵 Música de fundo: calma (o vídeo original não tem som)" in versao and "Música" not in completo
    assert "rendeu o vídeo original e mais 1 versão modificada, diferentes de verdade" in versao
    assert "compare com o Editor 2 com Legendas ✨" in versao
    assert not any(os.path.exists(m[1]) for m in msg.midias)
    assert consultar("SELECT processo, resultado FROM registro_processos ORDER BY rowid DESC") == (
        "edição do vídeo: exemplo do editor 1", "mandado")
    so_completo = {"inteiro": 12.0, "versoes_da_ia": 0,
                   "versoes": [{"remontado": 12.0, "curta": False, "gancho": None, "textos": []}]}
    assert "rendeu só o vídeo original, sem versões modificadas (a IA não sugeriu momentos diferentes)" in sv.legenda_das_versoes(
        "Bolsa", so_completo, 0, 1)
    # Os botões de antes, que ainda podem estar no teclado, valem como o Editor 1.
    monkeypatch.setattr(sv.edicao_video, "exemplo_editor_1", lambda destino: (None, "nenhum vídeo dos Autorais", None))
    for antigo in ("Ver Exemplo Editor 1 👀", "Ver Exemplo da Edição 👀", "Ver Exemplo Editor 3 🔀"):
        assert antigo in sv.BOTOES_ANTIGOS_EDITOR_1
        msg = MsgComMidia(Msg, antigo)
        rodar(sv.exemplo_editor_1_handler(msg, est))
        assert not msg.midias and any("O exemplo do Editor 1 (sem legendas) não saiu: nenhum vídeo dos Autorais" in t
                                      for t in msg.saidas)


def test_exemplo_do_editor_2_manda_o_completo_com_o_que_mudou_e_as_versoes(bm, Msg, Est, monkeypatch):
    # Pedidos do Rafael (27/10): o Editor 2 com legendas manda o vídeo completo e as versões; (vídeo
    # de 28/10) o 1º é o vídeo original, sem cortes, com as legendas, como vai ao ar, e as versões
    # modificadas dizem o que a remontagem mudou.
    sv, est = _painel(bm), Est()
    remontagem = {"cortado": 6.4, "acelerados": 3, "camera_lenta": 1, "com_fala": 0}
    resumo = {"original": 24.0, "inteiro": 24.0, "lugar": "alto", "lugar_da_ia": True, "com_fala": 0,
              "textos_da_ia": True, "versoes_da_ia": 3, "remontagem": remontagem}

    def exemplo_editor_2(destino):
        resumo["versoes"] = _exemplo_com_versoes(sv, destino, [
            {"remontado": 24.0, "curta": False, "gancho": None, "vantagem": "Mantém gelado",
             "textos": ["Copo Térmico", "Mantém gelado", "A partir de R$ 39,90"]},
            {"remontado": 18.0, "curta": True, "gancho": (9.0, 10.5), "vantagem": "Tampa firme",
             "textos": ["Tampa firme", "Copo Térmico", "Chamada 2"]}])
        return "Copo Térmico <inox>", "", resumo

    monkeypatch.setattr(sv.edicao_video, "exemplo_editor_2", exemplo_editor_2)
    msg = MsgComMidia(Msg, "Editor 2 com Legendas ✨")
    rodar(sv.exemplo_editor_2_handler(msg, est))
    assert [m[0] for m in msg.midias] == ["video", "video"]
    # Pedido do Rafael (vídeo de 28/10, 00:30): depois dos vídeos, o texto da Edição dos Vídeos
    # não volta (ele escondia os vídeos); o teclado do painel continua embaixo.
    assert not any("O que cada botão faz" in t for t in msg.saidas)
    assert all(len(m[2]) <= 1024 for m in msg.midias)
    primeira, segunda = msg.midias[0][2], msg.midias[1][2]
    assert "Exemplo do Editor 2 (com legendas), vídeo 1 de 2 (não foi postado): Copo Térmico &lt;inox&gt;" in primeira
    assert primeira.startswith("🎬 <b>VÍDEO ORIGINAL</b>\n\n✨ Exemplo do Editor 2")
    assert ("\nInteiro, na ordem e na velocidade dele, sem cortes; só com as edições que você "
            "pediu (a foto no começo, a miniatura e a seta, e as legendas). É assim que ele vai ao ar.") in primeira
    assert "(mais os 2 s da foto): o vídeo inteiro" in primeira
    assert "“Mantém gelado”" in primeira and "Com fala" not in primeira and "A IA não escreveu" not in primeira
    # O original não tem partes paradas tiradas: isso é das versões modificadas.
    assert "Lugar do texto" not in primeira and "Partes paradas" not in primeira and "acelerados" not in primeira
    assert "Partes paradas tiradas: 6 s" in segunda and "Trechos acelerados: 3 | 🐢 Em câmera lenta: 1" in segunda
    assert segunda.startswith("✂️ <b>VERSÃO MODIFICADA 1 de 1</b>\n\n✨ Exemplo do Editor 2 (com legendas), vídeo 2 de 2")
    assert "\nSó no exemplo, não vai ao ar: abre" in segunda
    assert "abre com o trecho de 9,0 s a 10,5 s do vídeo original e segue dali" in segunda
    assert "(o que ele mostra" not in segunda and "“Tampa firme”" in segunda
    assert "(mais os 2 s da foto): 75% do vídeo completo, a mais curta" in segunda
    assert "rendeu o vídeo original e mais 1 versão modificada, diferentes de verdade" in segunda
    assert "Lugar do texto: no alto, ao lado da miniatura (a IA escolheu)" in segunda
    assert "compare com o Editor 1 sem Legendas 👀" in segunda
    assert not any(os.path.exists(m[1]) for m in msg.midias)
    assert consultar("SELECT processo, resultado FROM registro_processos ORDER BY rowid DESC") == (
        "edição do vídeo: exemplo do editor 2", "mandado")
    # Sem os textos da IA, o original sai com o preço e avisa; na versão, a fala mantida aparece (P45).
    remontagem.update(cortado=0, com_fala=7.5)
    resumo.update(textos_da_ia=False)
    msg = MsgComMidia(Msg, "Ver Exemplo Editor 4 🎬")
    rodar(sv.exemplo_editor_2_handler(msg, est))
    primeira, segunda = msg.midias[0][2], msg.midias[1][2]
    assert "A IA não escreveu o nome e a vantagem" in primeira
    assert "Nenhuma parte parada para tirar" in segunda
    assert "Com fala, ficou inteiro e na velocidade normal: 8 s" in segunda
    # Escolha do Rafael (P47): os lados também valem e, sem lugar livre, o vídeo vai sem texto.
    resumo.update(lugar="direita")
    assert "Lugar do texto: do lado direito, no meio da altura (a IA escolheu)" in sv.legenda_das_versoes(
        "Copo", resumo, 1, 2)
    for versao in resumo["versoes"]:
        versao["textos"] = []
    resumo.update(lugar="nenhum")
    legenda = sv.legenda_das_versoes("Copo", resumo, 1, 2)
    assert "Sem texto na tela: a IA não achou lugar" in legenda and "Textos na tela" not in legenda
    # Escolha do Rafael (P52): o vídeo que já tem texto próprio na tela vai sem as nossas legendas.
    resumo.update(texto_no_video=True)
    assert "📍 Sem as nossas legendas: o vídeo já tem texto próprio na tela." in sv.legenda_das_versoes(
        "Copo", resumo, 1, 2)
    # Os botões de antes do Editor 2 e do 4 valem como o Editor 2.
    assert sv.BOTOES_ANTIGOS_EDITOR_2 == ["Ver Exemplo Editor 2 ✨", "Ver Exemplo Editor 4 🎬"]
    monkeypatch.setattr(sv.edicao_video, "exemplo_editor_2", lambda destino: (None, "o vídeo não abre", None))
    msg = MsgComMidia(Msg, "Ver Exemplo Editor 2 ✨")
    rodar(sv.exemplo_editor_2_handler(msg, est))
    assert not msg.midias and any("O exemplo do Editor 2 (com legendas) não saiu: o vídeo não abre" in t
                                  for t in msg.saidas)
