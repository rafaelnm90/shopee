"""moderacao_publico.py: a verificação semanal do Grupo Público só avisa, e no banco ficam só números."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import moderacao_publico as mp
from conftest import inserir, rodar

AGORA = datetime(2026, 10, 26, 10, 47, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def configuracoes():
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")


def test_links_de_fora_e_convites_saem_sem_ia():
    assert mp.regra_sem_ia("olha que achado https://s.shopee.com.br/AbC1") is None
    assert mp.regra_sem_ia("compre em https://shopee.com.br/produto-i.1.2") is None
    assert mp.regra_sem_ia("entra no meu grupo t.me/outrogrupo") == (4, "convite de outro grupo ou canal")
    assert mp.regra_sem_ia("chama no https://chat.whatsapp.com/abc") == (4, "convite de outro grupo ou canal")
    assert mp.regra_sem_ia("mais barato em https://mercadolivre.com.br/x") == (5, "link que não é da Shopee")


def test_a_mesma_mensagem_da_mesma_pessoa_vira_flood_a_partir_da_terceira():
    mensagens = [{"id": i, "autor_id": 7, "texto": "Compre  já!"} for i in (1, 2, 3, 4)]
    mensagens.append({"id": 5, "autor_id": 8, "texto": "compre já!"})
    suspeitas = mp.suspeitas_sem_ia(mensagens)
    assert set(suspeitas) == {3, 4} and suspeitas[3][0] == 6


def test_resposta_da_ia_aceita_so_regras_1_a_3_e_ids_do_lote():
    lote = [{"id": 101}, {"id": 102}]
    texto = '```json\n[{"id": 0, "regra": 1, "motivo": "xingou"}, {"id": 1, "regra": 5}, {"id": 9, "regra": 2}]\n```'
    assert mp.ler_resposta(texto, lote) == {101: (1, "xingou")}
    assert mp.ler_resposta("não entendi", lote) is None


class Cliente:
    def __init__(self, mensagens, admins=()):
        self.mensagens, self.admins = mensagens, admins

    async def get_entity(self, grupo):
        return SimpleNamespace(id=grupo, username=None)

    async def iter_participants(self, entidade, filter=None):
        for admin in self.admins:
            yield SimpleNamespace(id=admin)

    async def iter_messages(self, entidade):
        for m in self.mensagens:
            yield m


def _msg(id_msg, autor, texto, horas_atras=1, bot=False, out=False, action=None):
    return SimpleNamespace(id=id_msg, sender_id=autor, message=texto, out=out, action=action,
                           date=AGORA - timedelta(hours=horas_atras),
                           sender=SimpleNamespace(bot=bot, username=f"pessoa{autor}", first_name="Ana", last_name=None))


def test_semana_conferida_avisa_no_privado_e_guarda_so_numeros(monkeypatch):
    import db
    db.salvar_config("submissao_config", {"grupo_id": "-1001234567890"})
    avisos = []
    monkeypatch.setattr(mp.avisar_rafael, "mandar_texto", avisos.append)

    async def ia(prompt):
        return '[{"id": 0, "regra": 2, "motivo": "pede pix adiantado"}]'
    monkeypatch.setattr(mp, "gerar_texto_gemini", ia)
    cliente = Cliente([
        _msg(10, 1, "manda o pix que eu libero o curso"),
        _msg(11, 2, "olha https://s.shopee.com.br/AbC1"),
        _msg(12, 3, "entra t.me/outro"),
        _msg(13, 4, "sou admin"),
        _msg(14, 5, "sou um bot", bot=True),
        _msg(15, 6, "", ),
        _msg(16, -1009876543210, "post do canal ligado com t.me/canal"),
        _msg(17, 7, "", action="entrou no grupo"),
        _msg(9, 1, "velha", horas_atras=24 * 8),
    ], admins=(4,))
    rodar(mp.conferir_semana(cliente, AGORA))

    texto = "\n".join(avisos)
    assert "conferi 3 mensagem(ns) de membros e 2 pode(m) ser contra as regras" in texto
    assert "golpe ou fraude (pede pix adiantado)" in texto and "https://t.me/c/1234567890/10" in texto
    assert "divulgação de outros grupos ou canais" in texto and "Só aviso: nada foi apagado." in texto
    guardado = db.ler_config(mp.CHAVE)
    assert guardado["de_membros"] == 3 and guardado["suspeitas"] == 2 and guardado["so_midia"] == 1
    assert "pix" not in str(guardado) and "Ana" not in str(guardado)


def test_sem_grupo_configurado_nao_faz_nada(monkeypatch):
    monkeypatch.setattr(mp.avisar_rafael, "mandar_texto", lambda t: pytest.fail("não devia avisar"))
    rodar(mp.conferir_semana(Cliente([]), AGORA))
