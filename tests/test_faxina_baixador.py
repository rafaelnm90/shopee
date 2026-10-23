"""faxina_baixador: um painel só no tópico do Baixador, sem avisos de fixação; vídeos ficam."""
from types import SimpleNamespace

import faxina_baixador as fb
from conftest import inserir, rodar

BOT = 999          # id do bot do Baixador nos testes
PESSOA = 123


class MessageActionPinMessage:
    """Mesma classe (pelo nome) da mensagem de serviço "fixou uma mensagem" do Telethon."""


class TelegramFalso:
    def __init__(self, mensagens, falha=None):
        self.mensagens, self.falha, self.lotes = mensagens, falha, []

    async def iter_messages(self, grupo, reply_to=None, limit=None):
        assert grupo == fb.GRUPO_DOWNLOADER and reply_to == fb.TOPICO_DOWNLOADER
        for m in sorted(self.mensagens, key=lambda m: -m.id):
            yield m

    async def delete_messages(self, grupo, ids):
        if self.falha:
            raise self.falha
        self.lotes.append(list(ids))

    def apagados(self):
        return sorted(i for lote in self.lotes for i in lote)


def painel(id_):
    return SimpleNamespace(id=id_, sender_id=BOT, sender=None, action=None,
                           message="📥 BAIXADOR DE VÍDEOS\n\nCole aqui o link do vídeo...")


def video(id_):
    return SimpleNamespace(id=id_, sender_id=BOT, sender=None, action=None,
                           message="📥 Vídeo solicitado por: @alguem\n\n🔗 Link:\nhttps://s.shopee.com.br/x")


def aviso_fixou(id_):
    return SimpleNamespace(id=id_, sender_id=BOT, sender=None, action=MessageActionPinMessage(), message="")


def _sem_espera(monkeypatch):
    async def nada(*a, **k):
        pass
    monkeypatch.setattr(fb.asyncio, "sleep", nada)


def _registrar_painel(id_):
    inserir("CREATE TABLE IF NOT EXISTS painel_downloader (chave TEXT PRIMARY KEY, valor TEXT)")
    inserir("INSERT OR REPLACE INTO painel_downloader (chave, valor) VALUES ('msg_id', ?)", str(id_))


def test_apaga_paineis_antigos_e_avisos_e_poupa_videos(monkeypatch):
    _sem_espera(monkeypatch)
    _registrar_painel(300)
    de_pessoa = SimpleNamespace(id=220, sender_id=PESSOA, sender=None, action=None,
                                message="alguém colou o texto BAIXADOR DE VÍDEOS aqui")
    tg = TelegramFalso([
        SimpleNamespace(id=fb.TOPICO_DOWNLOADER, sender_id=None, sender=None, action=None, message=""),
        painel(100), aviso_fixou(101), video(110),
        painel(200), aviso_fixou(201), video(210), de_pessoa,
        painel(300), video(310),
        painel(350),                        # mais novo que o registrado: o registro ainda vai mudar
    ])

    apagadas, falha = rodar(fb.limpar_topico(tg, bots={BOT}))

    assert falha is None and apagadas == 4
    assert tg.apagados() == [100, 101, 200, 201]


def test_sem_painel_registrado_fica_o_mais_novo(monkeypatch):
    _sem_espera(monkeypatch)
    tg = TelegramFalso([painel(10), painel(20), video(15)])
    assert rodar(fb.limpar_topico(tg, bots={BOT})) == (1, None)
    assert tg.apagados() == [10]


def test_muitos_avisos_saem_em_lotes(monkeypatch):
    _sem_espera(monkeypatch)
    tg = TelegramFalso([aviso_fixou(i) for i in range(1, 251)])
    apagadas, _ = rodar(fb.limpar_topico(tg, bots={BOT}))
    assert apagadas == 250 and all(len(lote) <= fb.LOTE for lote in tg.lotes) and len(tg.lotes) == 3


def test_sem_permissao_para_e_avisa_sem_derrubar(monkeypatch):
    _sem_espera(monkeypatch)
    tg = TelegramFalso([painel(10), painel(20)], falha=PermissionError("sem direito de apagar"))
    apagadas, falha = rodar(fb.limpar_topico(tg, bots={BOT}))
    assert apagadas == 0 and "PermissionError" in falha


def test_ids_dos_bots_vem_dos_tokens(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN_DOWNLOADER", "111:abc")
    monkeypatch.setenv("TELEGRAM_TOKEN", "222:def")
    assert fb.ids_dos_bots() == {111, 222}


# --- Respostas de erro (escolhas do Rafael em 23/10: somem em 5 min, as antigas também) ---

from datetime import datetime, timedelta, timezone

AGORA = datetime(2026, 10, 23, 22, 0, tzinfo=timezone.utc)


def erro(id_, membro, minutos_atras):
    mencao = SimpleNamespace(user_id=membro)
    return SimpleNamespace(id=id_, sender_id=BOT, sender=None, action=None, entities=[mencao],
                           date=AGORA - timedelta(minutes=minutos_atras),
                           message="❌ Vânia, não deu certo: não achei nenhum arquivo de vídeo.")


def link(id_, membro, minutos_atras):
    return SimpleNamespace(id=id_, sender_id=membro, sender=None, action=None, entities=[],
                           date=AGORA - timedelta(minutes=minutos_atras),
                           message="https://br.shp.ee/abc?fromSource=copy_link")


def test_erro_vencido_sai_com_o_link_do_membro_e_o_recente_fica(monkeypatch):
    _sem_espera(monkeypatch)
    outra = 456
    mensagens = [
        link(10, PESSOA, 60 * 30), erro(11, PESSOA, 60 * 30 - 1),          # de ontem: os dois saem
        link(20, outra, 20), video(21),                                     # vídeo entregue fica
        link(30, PESSOA, 8), erro(31, PESSOA, 7),                           # 7 min: saem
        link(40, outra, 3), erro(41, outra, 2),                             # 2 min: ainda ficam
    ]
    for m in mensagens:
        m.date = getattr(m, "date", AGORA)
    assert sorted(fb.erros_vencidos(mensagens, {BOT}, AGORA)) == [10, 11, 30, 31]


def test_link_longe_do_erro_ou_de_outra_pessoa_fica():
    antigo = link(5, PESSOA, 120)                          # 2 h antes do erro: outro pedido
    alheio = link(6, 789, 9)
    assert fb.erros_vencidos([antigo, alheio, erro(7, PESSOA, 8)], {BOT}, AGORA) == [7]


def test_mencao_pelo_link_tg_user_tambem_vale():
    resposta = erro(9, PESSOA, 10)
    resposta.entities = [SimpleNamespace(url=f"tg://user?id={PESSOA}")]
    assert fb.mencionado(resposta) == PESSOA
    assert fb.erros_vencidos([link(8, PESSOA, 11), resposta], {BOT}, AGORA) == [9, 8]


def test_faxina_apaga_o_erro_vencido_e_o_link_do_tópico(monkeypatch):
    _sem_espera(monkeypatch)
    _registrar_painel(1)
    agora = datetime.now(timezone.utc)
    pedido = link(2, PESSOA, 0)
    pedido.date = agora - timedelta(days=3)
    resposta = erro(3, PESSOA, 0)
    resposta.date = agora - timedelta(days=3)
    tg = TelegramFalso([painel(1), pedido, resposta])
    assert rodar(fb.limpar_topico(tg, bots={BOT})) == (2, None)
    assert tg.apagados() == [2, 3]
