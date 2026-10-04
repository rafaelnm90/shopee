"""avisar_rafael: o aviso de pergunta pendente vai para o ADMIN_ID pelo bot principal."""
import io
import json
import urllib.parse

import avisar_rafael


def test_admin_id_vem_do_bot_mestre(bm):
    assert avisar_rafael.admin_id() == bm.ADMIN_ID


def test_texto_curto_com_assunto_e_link():
    texto = avisar_rafael.montar_texto("  Parceira: confirmar o canal de origem  ", "https://claude.ai/code/x")
    assert "esperando uma resposta sua" in texto and "📌 Parceira: confirmar o canal de origem" in texto
    assert texto.endswith("https://claude.ai/code/x")
    assert len(avisar_rafael.montar_texto("x" * 1000)) < 500


def test_envia_para_o_admin_pelo_bot(bm, monkeypatch):
    pedidos = []

    class Resposta(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(url, dados, timeout=None):
        pedidos.append((url, urllib.parse.parse_qs(dados.decode())))
        return Resposta(json.dumps({"ok": True}).encode())
    monkeypatch.setattr(avisar_rafael.urllib.request, "urlopen", urlopen)

    assert avisar_rafael.enviar("Pergunta pendente") is True
    url, campos = pedidos[0]
    assert url.endswith("/sendMessage") and campos["chat_id"] == [str(bm.ADMIN_ID)]
    assert "Pergunta pendente" in campos["text"][0]
