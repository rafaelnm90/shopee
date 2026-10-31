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


def test_lembrete_do_dia_nao_diz_que_espera_resposta():
    # O Rafael (23/10) recebeu o lembrete das pendências dizendo "esperando uma resposta sua"
    # e procurou uma pergunta que não existia.
    texto = avisar_rafael.montar_texto("Lembrete do dia: 3 pendências (chips dos Autorais)")
    assert texto.startswith("🤖 Lembrete do Claude") and "esperando uma resposta" not in texto
    assert "para ver a lista" in texto and "📌 Lembrete do dia: 3 pendências" in texto


def test_pedido_de_ajuda_diz_o_que_o_claude_pediu():
    # Pedido do Rafael (31/10): o Claude pode pedir uma ajuda dele (um vídeo ensinando algo) e
    # lembrar até ele entregar; o aviso não pode parecer uma pergunta esperando resposta.
    texto = avisar_rafael.montar_texto("Pedido de ajuda: gravar o toque no Ver Mais do Ver Produtos")
    assert texto.startswith("🤖 O Claude pediu uma ajuda sua.") and "esperando uma resposta" not in texto
    assert "📌 Pedido de ajuda: gravar o toque no Ver Mais do Ver Produtos" in texto
    assert "para ver o que ele precisa" in texto


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


def test_id_da_mensagem_para_apagar_e_editar_depois(bm, monkeypatch):
    pedidos = []

    class Resposta(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(url, dados, timeout=None):
        pedidos.append((url.rsplit("/", 1)[1], urllib.parse.parse_qs(dados.decode())))
        if url.endswith("/deleteMessage"):
            # O Telegram recusa apagar o que passou de 48 h.
            return Resposta(json.dumps({"ok": False, "description": "message can't be deleted"}).encode())
        return Resposta(json.dumps({"ok": True, "result": {"message_id": 88}}).encode())
    monkeypatch.setattr(avisar_rafael.urllib.request, "urlopen", urlopen)

    assert avisar_rafael.mandar_texto_com_id("Pergunta", html=True) == 88
    assert avisar_rafael.mandar_texto("Pergunta") is True
    assert avisar_rafael.apagar_mensagem(88) is False and avisar_rafael.editar_texto(88, "Respondida") is True
    assert [p[0] for p in pedidos] == ["sendMessage", "sendMessage", "deleteMessage", "editMessageText"]
    assert pedidos[2][1]["message_id"] == ["88"] and pedidos[3][1]["chat_id"] == [str(bm.ADMIN_ID)]


def test_foto_vai_para_o_admin_pelo_bot(bm, monkeypatch, tmp_path):
    pedidos = []

    class Resposta(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(pedido, timeout=None):
        pedidos.append(pedido)
        return Resposta(json.dumps({"ok": True}).encode())
    monkeypatch.setattr(avisar_rafael.urllib.request, "urlopen", urlopen)
    imagem = tmp_path / "tela.png"
    imagem.write_bytes(b"\x89PNG imagem")

    assert avisar_rafael.mandar_foto(str(imagem), "Rascunho") is True
    pedido = pedidos[0]
    assert pedido.full_url.endswith("/sendPhoto") and b"\x89PNG imagem" in pedido.data
    assert f'name="chat_id"\r\n\r\n{bm.ADMIN_ID}\r\n'.encode() in pedido.data
    assert b'name="caption"\r\n\r\nRascunho\r\n' in pedido.data


def test_video_vai_para_o_admin_pelo_bot_e_o_grande_demais_nao(bm, monkeypatch, tmp_path):
    # O vídeo que o Google recusou (P29) chega no privado; acima do limite do Bot API, o
    # robô manda só o texto.
    pedidos = []

    class Resposta(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(pedido, timeout=None):
        pedidos.append(pedido)
        return Resposta(json.dumps({"ok": True}).encode())
    monkeypatch.setattr(avisar_rafael.urllib.request, "urlopen", urlopen)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"\x00\x00\x00 ftypmp42 video")

    assert avisar_rafael.mandar_video(str(video), "Recusado pelo Google") is True
    pedido = pedidos[0]
    assert pedido.full_url.endswith("/sendVideo") and b"ftypmp42 video" in pedido.data
    assert b'name="video"; filename="video.mp4"' in pedido.data
    assert b'name="caption"\r\n\r\nRecusado pelo Google\r\n' in pedido.data

    monkeypatch.setattr(avisar_rafael, "LIMITE_DO_VIDEO", 5)
    assert avisar_rafael.mandar_video(str(video), "grande") is False and len(pedidos) == 1
