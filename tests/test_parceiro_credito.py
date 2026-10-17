"""Vídeo de parceiro no Grupo Público: o padrão do grupo, com "👤 Vídeo enviado por: @parceiro"."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from conftest import inserir, rodar

GRUPO_PUBLICO = -1003892378604
TOPICO_COMUNIDADE = 5


@pytest.mark.parametrize("digitado, esperado", [
    ("@joao_silva", "@joao_silva"), ("joao_silva", "@joao_silva"),
    ("https://t.me/joao_silva", "@joao_silva"), ("t.me/joao_silva/", "@joao_silva"),
    ("-", ""), ("@jo", None), ("@1joao", None), ("joão silva", None), ("", None),
])
def test_arroba_do_parceiro_aceita_os_jeitos_comuns_de_escrever(bm, digitado, esperado):
    assert bm.normalizar_arroba(digitado) == esperado


def _publicar_um_video(bm, monkeypatch, destino, arroba, origem="-1001234567890"):
    """Roda o motor dos parceiros com um vídeo vencido e devolve a legenda publicada."""
    bm.salvar_submissao_config({**bm.ler_submissao_config(), "grupo_id": GRUPO_PUBLICO,
                                "topico_destino": TOPICO_COMUNIDADE})
    pid = bm.salvar_parceiro({"nome": "Loja da Ana", "arroba": arroba, "app_id": "123456",
                              "app_secret": "x" * 20, "canal_origem": origem,
                              "canal_destino": destino, "limite_diario": 6})
    inserir("CREATE TABLE IF NOT EXISTS fila_parceiros (id_unico TEXT PRIMARY KEY, parceiro_id INTEGER, "
            "caminho_video TEXT, link_original TEXT, data_captura TEXT, data_alvo TEXT, "
            "horario_disparo TEXT DEFAULT '', processado INTEGER DEFAULT 0, data_postagem TEXT DEFAULT '', "
            "link_post_origem TEXT DEFAULT '', msg_postada_id INTEGER, nome_produto TEXT DEFAULT '')")
    agora = datetime.now(bm.fuso_horario)
    with open("temp/video.mp4", "wb") as arquivo:
        arquivo.write(b"video")
    inserir("INSERT INTO fila_parceiros (id_unico, parceiro_id, caminho_video, link_original, data_captura, "
            "data_alvo, horario_disparo) VALUES (?, ?, ?, ?, ?, ?, ?)", f"{pid}-1", pid, "temp/video.mp4",
            "https://s.shopee.com.br/original", agora.strftime("%Y-%m-%d"), agora.strftime("%Y-%m-%d"),
            (agora - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"))

    legendas = []

    async def converter(*a, **k):
        return "https://s.shopee.com.br/afiliado"

    async def analisar(*a, **k):
        return "Tênis Casual Feminino 👟\n#SapatosFemininos"

    async def send_video(chat_id=None, video=None, caption=None, **k):
        legendas.append(caption)
        return SimpleNamespace(message_id=9)

    async def nada(*a, **k):
        return None

    monkeypatch.setattr(bm, "converter_link_shopee", converter)
    monkeypatch.setattr(bm, "analisar_video_gemini", analisar)
    monkeypatch.setattr(bm, "fechar_dia_captura_parceiros", nada)
    monkeypatch.setattr(bm.bot, "send_video", send_video)
    rodar(bm.motor_parceiros_step())
    assert len(legendas) == 1
    return legendas[0]


def test_parceiro_na_comunidade_sai_com_o_arroba_dele(bm, monkeypatch, relogio):
    # Pedido do Rafael em 16/10: os vídeos da Vídeos da Comunidade voltam a ter o
    # "Vídeo enviado por", e nos do parceiro vai o @ dele.
    relogio("15:00")
    legenda = _publicar_um_video(bm, monkeypatch, f"{GRUPO_PUBLICO}:{TOPICO_COMUNIDADE}", "@loja_da_ana")
    assert legenda == ("👤 Vídeo enviado por: @loja_da_ana\n\n<b>Tênis Casual Feminino 👟</b>\n\n"
                       "🔶 <b>SHOPEE</b> 🔶\n🔗 Link do Produto:\nhttps://s.shopee.com.br/afiliado\n\n"
                       "<i>#SapatosFemininos</i>")


def test_parceiro_sem_nenhum_arroba_sai_com_o_nome_do_cadastro(bm, monkeypatch, relogio):
    # Escolha do Rafael em 16/10: sem @ cadastrado e com canal privado, vai o nome do
    # cadastro, como o membro sem @ (o caso da parceira sem @ no Telegram).
    relogio("15:00")
    legenda = _publicar_um_video(bm, monkeypatch, f"{GRUPO_PUBLICO}:{TOPICO_COMUNIDADE}", "")
    assert legenda.startswith("👤 Vídeo enviado por: Loja da Ana\n\n<b>Tênis Casual Feminino 👟</b>\n\n"
                              "🔶 <b>SHOPEE</b> 🔶")


@pytest.mark.parametrize("origem", ["@canal_da_ana", "https://t.me/canal_da_ana", "-1001234567890"])
def test_parceiro_sem_arroba_sai_com_o_arroba_do_canal_de_origem(bm, monkeypatch, relogio, origem):
    # Escolha do Rafael em 16/10: no canal o Telegram não diz quem postou; sem @
    # cadastrado, vai o @ público do canal do parceiro (dito pela origem ou guardado
    # pelos userbots ao ler as conversas).
    import links_grupos
    relogio("15:00")
    links_grupos.guardar("-1001234567890", "canal_da_ana")
    legenda = _publicar_um_video(bm, monkeypatch, f"{GRUPO_PUBLICO}:{TOPICO_COMUNIDADE}", "", origem)
    assert legenda.startswith("👤 Vídeo enviado por: @canal_da_ana\n\n<b>Tênis Casual Feminino 👟</b>")


def test_arroba_cadastrado_vale_mais_que_o_do_canal(bm, monkeypatch, relogio):
    relogio("15:00")
    legenda = _publicar_um_video(bm, monkeypatch, f"{GRUPO_PUBLICO}:{TOPICO_COMUNIDADE}", "@loja_da_ana",
                                 "@canal_da_ana")
    assert legenda.startswith("👤 Vídeo enviado por: @loja_da_ana\n\n")


@pytest.mark.parametrize("origem", ["https://t.me/+AbCdEfGh", "t.me/joinchat/AbCdEfGh", "", None, "-100999"])
def test_canal_sem_arroba_publico_nao_inventa_credito(bm, origem):
    import links_grupos
    assert links_grupos.arroba(origem) is None
    assert bm.credito_do_parceiro({"arroba": "", "canal_origem": origem}) == ""
    assert bm.credito_do_parceiro({"arroba": "", "canal_origem": origem, "nome": "Ana & <Cia>"}) == \
        "Ana &amp; &lt;Cia&gt;"


def test_padrao_vale_para_o_grupo_publico_inteiro(bm, monkeypatch, relogio):
    # "O padrão para esse grupo, o grupo público" (Rafael, 16/10): em qualquer tópico dele.
    relogio("15:00")
    legenda = _publicar_um_video(bm, monkeypatch, f"{GRUPO_PUBLICO}:99", "@loja_da_ana")
    assert legenda.startswith("👤 Vídeo enviado por: @loja_da_ana\n\n") and "🔶 <b>SHOPEE</b> 🔶" in legenda


def test_parceiro_em_outro_destino_nao_ganha_a_linha_do_credito(bm, monkeypatch, relogio):
    relogio("15:00")
    legenda = _publicar_um_video(bm, monkeypatch, "-1009999999999", "@loja_da_ana")
    assert legenda == ("<b>Tênis Casual Feminino 👟</b>\n\n🔗 <b>Link do Produto:</b>\n"
                       "https://s.shopee.com.br/afiliado\n\n<i>#SapatosFemininos</i>")


def test_arroba_cadastrado_e_editado_pelo_painel(bm, Msg, Est):
    estado = Est(estado=bm.SubmissaoAdminFluxo.parceiro_arroba)
    rodar(bm.parceiro_receber_arroba(Msg("t.me/loja_da_ana"), estado))
    assert estado.dados["arroba"] == "@loja_da_ana"
    assert estado.estado == bm.SubmissaoAdminFluxo.parceiro_app_id

    pid = bm.salvar_parceiro({"nome": "Loja da Ana", "arroba": "", "app_id": "123456",
                              "app_secret": "x" * 20, "canal_origem": "@origem", "canal_destino": "-1001"})
    msg = Msg("@loja_da_ana")
    rodar(bm.salvar_edicao_parceiro(msg, Est({"parceiro_id": pid, "campo_edicao": "arroba"})))
    assert bm.buscar_parceiro(pid)["arroba"] == "@loja_da_ana"
    assert any("@ no Telegram: @loja_da_ana" in s for s in msg.saidas)

    rodar(bm.salvar_edicao_parceiro(Msg("nome com espaço"), Est({"parceiro_id": pid, "campo_edicao": "arroba"})))
    assert bm.buscar_parceiro(pid)["arroba"] == "@loja_da_ana"   # inválido não grava
    rodar(bm.salvar_edicao_parceiro(Msg("-"), Est({"parceiro_id": pid, "campo_edicao": "arroba"})))
    assert bm.buscar_parceiro(pid)["arroba"] == ""


def test_tela_do_parceiro_mostra_de_onde_sai_o_credito(bm):
    assert bm.rotulo_arroba_parceiro({"arroba": "@loja_da_ana", "canal_origem": "@canal_da_ana"}) == "@loja_da_ana"
    assert "o crédito sai com @canal_da_ana" in bm.rotulo_arroba_parceiro({"arroba": "", "canal_origem": "@canal_da_ana"})
    assert "o crédito sai com o nome: Loja da Ana" in bm.rotulo_arroba_parceiro(
        {"arroba": "", "canal_origem": "-100999", "nome": "Loja da Ana"})
    assert "sem a linha do crédito" in bm.rotulo_arroba_parceiro({"arroba": "", "canal_origem": "-100999"})
