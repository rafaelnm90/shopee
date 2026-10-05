"""Painel da Shopee Vídeo (Outros Canais): pausa, vídeos por dia, horário de postagem e tutorial."""
import tela_android
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
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.menu.state
    teclado = _textos(sv.teclado_painel(sv.ler_config()))
    for botao in ("Vídeos por Dia 📦", "Horário de Postagem ⏰", "Retomar Robô ▶️",
                  "Tela do Android 📱", "Tutorial do Android 📖", "Voltar aos Canais 🔙"):
        assert botao in teclado


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
    botoes = ("painel_handler", "pedir_faixa", "pedir_janela", "pedir_pausa", "tutorial_android_handler")
    respostas = ("confirmar_faixa", "confirmar_janela", "confirmar_com_os_botoes")
    assert max(ordem.index(b) for b in botoes) < min(ordem.index(r) for r in respostas)


def test_so_o_admin_usa_o_painel(bm, Msg, Est):
    sv = _painel(bm)
    for handler, texto in ((sv.painel_handler, "Shopee Vídeo 🎬"), (sv.pedir_faixa, "Vídeos por Dia 📦"),
                           (sv.pedir_pausa, "Retomar Robô ▶️"), (sv.tutorial_android_handler, "Tutorial do Android 📖")):
        msg = Msg(texto, user_id=123)
        rodar(handler(msg, Est()))
        assert msg.saidas == [], texto


def test_tutorial_manda_as_quatro_partes_em_html_valido(bm, Msg, Est):
    sv = _painel(bm)
    msg = Msg("Tutorial do Android 📖")
    rodar(sv.tutorial_android_handler(msg, Est()))
    assert msg.saidas == list(sv.TUTORIAL_ANDROID) and len(msg.saidas) == 4
    for parte in msg.saidas:
        assert len(parte) <= 4096                                          # limite de uma mensagem
        assert parte.count("<b>") == parte.count("</b>")
        sem_tags = parte.replace("<b>", "").replace("</b>", "")
        assert "<" not in sem_tags and ">" not in sem_tags and "&" not in sem_tags
    assert "https://play.google.com/store/apps/details?id=com.mtv.sai" in msg.saidas[1]


def test_tutorial_usa_os_nomes_que_existem_no_bot_e_na_pagina(bm):
    sv = _painel(bm)
    texto = "".join(sv.TUTORIAL_ANDROID)
    for botao in ("📦 Enviar app", "🧹 Fechar apps", "🔄 Reiniciar Android", "🗑️ Resetar de fábrica",
                  "✅ Terminei", "Texto para digitar", "Digitar", "● Início", "Esperando a imagem do Android"):
        assert botao in texto and botao in tela_android.PAGINA, botao
    # O caminho citado no tutorial existe: Outros Canais → Shopee Vídeo → Tela do Android.
    assert "Outros Canais 🗂️" in _textos(bm.obter_teclado_raiz())
    assert "Shopee Vídeo 🎬" in _textos(bm.obter_teclado_outros_canais())
    assert "Tela do Android 📱" in _textos(sv.teclado_painel(sv.ler_config()))
    for passo in ("Outros Canais 🗂️", "Shopee Vídeo 🎬", "Tela do Android 📱"):
        assert passo in texto
