"""Painel da Shopee Vídeo (Outros Canais, modo assistente): pausa, vídeos por dia, horário e Enviar 1 Agora."""
from conftest import rodar


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
    assert "Pausado" in texto and "5 a 10" in texto and "das 13h às 22h" in texto and "hoje:" in texto
    assert "modo assistente" in texto and "Mandados hoje: <b>0</b>" in texto
    assert "Fonte dos vídeos: <b>Autorais 🎥</b>" in texto
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.menu.state
    teclado = _textos(sv.teclado_painel(sv.ler_config()))
    for botao in ("Vídeos por Dia 📦", "Horário de Postagem ⏰", "Retomar Robô ▶️", "Enviar 1 Agora 📤",
                  "Fonte dos Vídeos 🎞️", "Voltar aos Canais 🔙"):
        assert botao in teclado
    assert "Tela do Android 📱" not in teclado and "Tutorial do Android 📖" not in teclado


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
    msg = Msg("Retomar Robô ▶️")
    rodar(sv.pedir_pausa(msg, est))
    assert "Retomar" in msg.saidas[0] and sv.ler_config()["pausado"] is True
    rodar(sv.salvar_pausa(Msg("Confirmar Retomada ✅"), est))
    assert sv.ler_config()["pausado"] is False
    assert "Pausar Robô ⏸️" in _textos(sv.teclado_painel(sv.ler_config()))
    rodar(sv.pedir_pausa(Msg("Pausar Robô ⏸️"), est))
    rodar(sv.salvar_pausa(Msg("Confirmar Pausa ✅"), est))
    assert sv.ler_config()["pausado"] is True


def test_cancelar_volta_ao_painel_sem_mudar_nada(bm, Msg, Est):
    sv = _painel(bm)
    est = Est(estado=sv.ShopeeVideoFluxo.aguardando_faixa)
    msg = Msg("Cancelar ❌")
    rodar(bm.cancelar_fluxo_global(msg, est))
    assert "cancelada" in msg.saidas[0] and "Shopee Vídeo" in msg.saidas[-1]
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.menu.state
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
    botoes = ("painel_handler", "pedir_faixa", "pedir_janela", "pedir_pausa", "enviar_agora_handler",
              "pedir_fonte")
    respostas = ("confirmar_faixa", "confirmar_janela", "salvar_fonte", "confirmar_com_os_botoes")
    assert max(ordem.index(b) for b in botoes) < min(ordem.index(r) for r in respostas)


def test_so_o_admin_usa_o_painel(bm, Msg, Est):
    sv = _painel(bm)
    for handler, texto in ((sv.painel_handler, "Shopee Vídeo 🎬"), (sv.pedir_faixa, "Vídeos por Dia 📦"),
                           (sv.pedir_pausa, "Retomar Robô ▶️"), (sv.enviar_agora_handler, "Enviar 1 Agora 📤")):
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
