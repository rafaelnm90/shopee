"""IA (Opções do Servidor): o Claude IA manda o link da conversa com o Claude."""
from conftest import rodar


def _textos(teclado):
    return [b.text for linha in teclado.keyboard for b in linha]


def test_botao_ia_fica_nas_opcoes_do_servidor_e_mostra_o_claude_ia(bm, Msg, Est):
    # Pedido do Rafael (vídeo de 25/10): Opções do Servidor → IA → Claude IA.
    ia = bm.painel_ia
    assert ia.BOTAO in _textos(bm.obter_teclado_opcoes_servidor())
    msg, est = Msg(ia.BOTAO), Est(estado="AcessosFluxo:menu")
    rodar(ia.painel_handler(msg, est))
    assert ia.BOTAO_CLAUDE in msg.saidas[0] and rodar(est.get_state()) is None
    assert _textos(ia.teclado_painel()) == [ia.BOTAO_CLAUDE, ia.VOLTAR]
    # O Voltar é tratado pelo handler das Opções do Servidor, no bot_mestre.
    assert ia.VOLTAR == bm.painel_acessos.VOLTAR


def test_claude_ia_manda_o_link_da_conversa(bm, Msg, Est):
    ia = bm.painel_ia
    msg = Msg(ia.BOTAO_CLAUDE)
    rodar(ia.claude_handler(msg, Est()))
    assert len(msg.saidas) == 1 and ia.LINK_CLAUDE in msg.saidas[0]
    assert ia.LINK_CLAUDE.startswith("https://claude.ai/code/session_")


def test_so_o_rafael_ve_o_link(bm, Msg, Est):
    ia = bm.painel_ia
    for handler, texto in ((ia.painel_handler, ia.BOTAO), (ia.claude_handler, ia.BOTAO_CLAUDE)):
        msg = Msg(texto, user_id=bm.ADMIN_ID + 1)
        rodar(handler(msg, Est()))
        assert msg.saidas == []
