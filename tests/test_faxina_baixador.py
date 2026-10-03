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
