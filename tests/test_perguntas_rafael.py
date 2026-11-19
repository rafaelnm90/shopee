"""perguntas_rafael.py: a pergunta do Claude vai ao privado e é lembrada de hora em hora até a resposta."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import perguntas_rafael as pr
from conftest import rodar
from fuso import fuso_horario

AGORA = datetime(2026, 10, 23, 21, 0, tzinfo=fuso_horario)
LINK = "https://claude.ai/code/session_teste"
OPCOES = [{"rotulo": "Segurar e mandar depois (Recomendado)", "descricao": "Sai depois da próxima <de outro> assunto."},
          {"rotulo": "Deixar como está", "descricao": ""}]


def test_aviso_traz_pergunta_opcoes_texto_para_copiar_e_link():
    # Pedido do Rafael (23/10): a pergunta, as opções, o texto clicável para copiar e o link.
    pr.nova("Quer segurar a rotina do mesmo assunto & mandar depois?", OPCOES, LINK, AGORA)
    p = pr.abertas()[0]
    texto = pr.montar_aviso(p)
    assert p["codigo"] == "P1" and "Pergunta nova do Claude" in texto
    assert "mesmo assunto &amp; mandar depois?" in texto and "&lt;de outro&gt;" in texto
    assert "1. <b>Segurar e mandar depois (Recomendado)</b>" in texto and "2. <b>Deixar como está</b>" in texto
    copia = texto.split("<code>")[1].split("</code>")[0]
    assert copia.startswith("[P1] Vc me enviou anteriormente a pergunta &quot;Quer segurar")
    assert "(opções: 1) Segurar e mandar depois (Recomendado); 2) Deixar como está)" in copia
    assert copia.endswith("eu gostaria de responder: ")
    assert LINK in texto and len(texto) < 4096


def test_lembra_de_hora_em_hora_ate_a_resposta():
    pr.nova("Pergunta?", OPCOES, LINK, AGORA)
    enviados = []

    async def enviar(texto):
        enviados.append(texto)
        return True
    assert rodar(pr.lembrar(enviar, AGORA)) == 1                                 # nunca avisada: vai na hora
    assert rodar(pr.lembrar(enviar, AGORA + timedelta(minutes=59))) == 0
    assert rodar(pr.lembrar(enviar, AGORA + timedelta(minutes=60))) == 1
    assert "Lembrete 2" in enviados[-1]
    assert pr.marcar_respondida("p1", AGORA) and not pr.marcar_respondida("P1", AGORA)
    assert rodar(pr.lembrar(enviar, AGORA + timedelta(hours=5))) == 0 and pr.abertas() == []
    assert not pr.marcar_respondida("xyz")


def test_aviso_que_nao_sai_fica_para_a_proxima_volta():
    pr.nova("Pergunta?", [], "", AGORA)

    async def fora(texto):
        raise RuntimeError("Telegram fora")
    assert rodar(pr.lembrar(fora, AGORA)) == 0
    assert pr.vencidas(AGORA)[0]["avisos"] == 0


def test_pergunta_cifrada_chega_aberta_ao_servidor(monkeypatch):
    # O repositório e os logs do Actions são públicos: a pergunta viaja cifrada.
    from cryptography.fernet import Fernet
    import avisar_rafael
    import registro_privado
    chave = Fernet.generate_key()
    monkeypatch.setattr(registro_privado, "chave", lambda: chave)
    mandados = []
    monkeypatch.setattr(avisar_rafael, "mandar_texto_com_id",
                        lambda texto, html=False: mandados.append((texto, html)) or 501)
    cifrado = pr.cifrar({"pergunta": "Pergunta secreta?", "opcoes": OPCOES, "link": LINK}, chave)
    assert "secreta" not in cifrado
    assert pr.receber(cifrado, AGORA) == "P1"
    assert mandados[0][1] is True and "Pergunta secreta?" in mandados[0][0]
    assert pr.vencidas(AGORA + timedelta(minutes=30)) == []                     # já avisada agora
    assert pr.mensagens_de("P1") == [501]



def test_cifrar_recusa_o_que_o_aviso_do_privado_cortaria(tmp_path, monkeypatch, capsys):
    # O servidor guarda só 900 letras da pergunta e 220 de cada descrição, sem avisar: em 18/11, a cópia
    # de uma pergunta no privado perdeu o exemplo prático, que vinha no fim. O cifrar recusa antes.
    from cryptography.fernet import Fernet
    import registro_privado
    chave = Fernet.generate_key().decode()
    monkeypatch.setenv(registro_privado.VARIAVEL_CHAVE, chave)
    arquivo = tmp_path / "pergunta.json"
    arquivo.write_text(json.dumps({"pergunta": "palavra " * 120, "link": LINK,
                                   "opcoes": [{"rotulo": "Sim", "descricao": "d" * 221}]}), encoding="utf-8")
    assert pr.main(["cifrar", str(arquivo)]) == 1
    saida = capsys.readouterr()
    assert saida.out == ""                                                     # nada cifrado
    assert "pergunta com 959 letras" in saida.err and "descrição da opção 1 com 221 letras" in saida.err
    arquivo.write_text(json.dumps({"informacao": "i" * 3001, "link": LINK}), encoding="utf-8")
    assert pr.main(["cifrar", str(arquivo)]) == 1
    assert "informação com 3001 letras" in capsys.readouterr().err
    arquivo.write_text(json.dumps({"pergunta": "Cabe?", "opcoes": OPCOES, "link": LINK}), encoding="utf-8")
    assert pr.main(["cifrar", str(arquivo)]) == 0
    assert pr.abrir(capsys.readouterr().out, chave)["pergunta"] == "Cabe?"


def test_robo_lembra_pelo_privado(bm, monkeypatch):
    pr.nova("Pergunta?", OPCOES, LINK)
    enviados = []

    async def send_message(chat_id, texto, **k):
        enviados.append((chat_id, texto, k.get("parse_mode")))
        return SimpleNamespace(message_id=700 + len(enviados))
    monkeypatch.setattr(bm.bot, "send_message", send_message)
    rodar(bm.lembrar_perguntas_do_claude())
    assert enviados and enviados[0][0] == bm.ADMIN_ID and enviados[0][2] == "HTML"
    rodar(bm.lembrar_perguntas_do_claude())                                    # menos de 1 h: não repete
    assert len(enviados) == 1 and pr.mensagens_de("P1") == [701]


def test_lembrete_novo_da_pergunta_apaga_o_anterior():
    # Escolha do Rafael (10/11, P197 1): os lembretes das perguntas ficam enxutos como os das
    # informações: cada lembrete novo apaga o anterior; ficam a pergunta e o último lembrete, e na
    # resposta tudo sai, como antes. O que não sai na hora fica na lista, para sair na resposta.
    pr.nova("Pergunta?", OPCOES, LINK, AGORA)
    ids, apagadas = iter(range(51, 60)), []

    async def enviar(texto):
        return next(ids)

    async def apagar(ident):
        apagadas.append(ident)
        return ident != 54
    for horas in range(4):
        rodar(pr.lembrar(enviar, AGORA + timedelta(hours=horas), apagar=apagar))
    assert apagadas == [52, 53] and pr.mensagens_de("P1") == [51, 54]
    rodar(pr.lembrar(enviar, AGORA + timedelta(hours=4), apagar=apagar))
    assert apagadas == [52, 53, 54] and pr.mensagens_de("P1") == [51, 54, 55]
    # Respondida: a pergunta e os lembretes que ficaram saem do privado, como antes.
    assert pr.marcar_respondida("P1", AGORA + timedelta(hours=5))
    saidas = []
    assert pr.limpar_do_privado("P1", lambda m: saidas.append(m) or True, lambda m, texto: None) == (3, 3)
    assert saidas == [51, 54, 55]
    # Respondida enquanto o lembrete da hora saía: ele sai logo depois.
    pr.nova("Outra?", OPCOES, LINK, AGORA)

    async def enviar_e_responder(texto):
        pr.marcar_respondida("P2", AGORA)
        return 70
    apagadas.clear()
    rodar(pr.lembrar(enviar_e_responder, AGORA, apagar=apagar))
    assert apagadas == [70] and pr.mensagens_de("P2") == []


def test_robo_apaga_o_lembrete_anterior_da_pergunta(bm, monkeypatch):
    pr.nova("Pergunta?", OPCOES, LINK)
    enviados, apagadas = [], []

    async def send_message(chat_id, texto, **k):
        enviados.append(texto)
        return SimpleNamespace(message_id=700 + len(enviados))

    async def delete_message(chat_id, mensagem):
        assert chat_id == bm.ADMIN_ID
        apagadas.append(mensagem)
    monkeypatch.setattr(bm.bot, "send_message", send_message)
    monkeypatch.setattr(bm.bot, "delete_message", delete_message)
    for _vez in range(3):
        with pr.db.conexao() as con:
            con.execute("UPDATE perguntas_rafael SET ultimo_aviso = '2000-01-01 00:00:00'")
        rodar(bm.lembrar_perguntas_do_claude())
    # O 701 é a pergunta e fica; o 702 saiu quando o 703 chegou.
    assert len(enviados) == 3 and apagadas == [702] and pr.mensagens_de("P1") == [701, 703]


def test_respondida_sai_do_privado_com_os_lembretes(monkeypatch):
    # Pedido do Rafael (24/10): respondida aqui, a pergunta some do privado do bot, para ele
    # não achar que ficou sem resposta e responder de novo.
    import avisar_rafael
    pr.nova("Pergunta?", OPCOES, LINK, AGORA)
    ids = iter([31, 32, 33])

    async def enviar(texto):
        return next(ids)
    for horas in range(3):
        rodar(pr.lembrar(enviar, AGORA + timedelta(hours=horas)))
    assert pr.mensagens_de("p1") == [31, 32, 33]
    apagadas, editadas, mandadas = [], [], []
    # A de 31 passou das 48 h: o Telegram não deixa apagar, e o texto dela vira "respondida".
    monkeypatch.setattr(avisar_rafael, "apagar_mensagem", lambda ident: ident != 31 and not apagadas.append(ident))
    monkeypatch.setattr(avisar_rafael, "editar_texto", lambda ident, texto: editadas.append((ident, texto)) or True)
    monkeypatch.setattr(avisar_rafael, "mandar_texto", lambda texto, html=False: mandadas.append(texto) or True)
    assert pr.main(["respondida", "p1"]) == 0
    assert apagadas == [32, 33] and editadas[0][0] == 31 and "P1 respondida" in editadas[0][1]
    assert "Recebi a sua resposta da pergunta P1" in mandadas[0] and "2 mensagem(ns)" in mandadas[0]
    # A segunda vez não mexe em nada e não é erro (o avisar.yml fica verde); o código que não existe é.
    assert pr.main(["respondida", "P1"]) == 0 and len(mandadas) == 1 and apagadas == [32, 33]
    assert pr.main(["respondida", "P9"]) == 1
    assert "apaguei daqui a pergunta e os lembretes dela" in pr.texto_da_confirmacao("P2", 3, 3)
    assert pr.texto_da_confirmacao("P2", 0, 0).endswith("Parei de lembrar.")


# --- Informações importantes do Claude (pedido do Rafael, 09/11) ---

def test_informacao_lembrada_de_hora_em_hora_ate_o_vi():
    # "tudo q vc for trazer para mim seja persistente, até eu responder ok": a informação
    # importante é lembrada como as perguntas, com o próprio código e o botão Vi ✅.
    pr.nova("Pergunta?", OPCOES, LINK, AGORA)
    assert pr.nova_informacao("Vendas da semana: 0.\nSeguidores: +3 <subiu>", LINK, AGORA) == "I1"
    enviados = []

    async def enviar(texto, teclado):
        enviados.append((texto, teclado))
        return 900 + len(enviados)
    assert rodar(pr.lembrar_informacoes(enviar, AGORA)) == 1
    texto, teclado = enviados[0]
    assert "Informação importante do Claude" in texto and "(I1)" in texto and LINK in texto
    assert "Vendas da semana: 0.\nSeguidores: +3 &lt;subiu&gt;" in texto and len(texto) < 4096
    assert teclado == {"inline_keyboard": [[{"text": "Vi ✅", "callback_data": "info_vi:1"}]]}
    assert rodar(pr.lembrar_informacoes(enviar, AGORA + timedelta(minutes=59))) == 0
    assert rodar(pr.lembrar_informacoes(enviar, AGORA + timedelta(hours=1))) == 1 and "Lembrete 2" in enviados[-1][0]
    assert pr.mensagens_da_informacao("i1") == [901, 902]
    # A pergunta P1 e a informação I1 não se misturam.
    assert not pr.marcar_vista("P1") and pr.abertas()[0]["codigo"] == "P1"
    assert pr.marcar_vista("i1", AGORA) and not pr.marcar_vista("I1")
    assert rodar(pr.lembrar_informacoes(enviar, AGORA + timedelta(hours=5))) == 0 and pr.informacoes_abertas() == []
    assert pr.abertas()[0]["codigo"] == "P1"


def test_informacao_cifrada_chega_ao_servidor_com_o_vi(monkeypatch):
    # O repositório e os logs do Actions são públicos: a informação viaja cifrada, como a pergunta.
    from cryptography.fernet import Fernet
    import avisar_rafael
    import registro_privado
    chave = Fernet.generate_key()
    monkeypatch.setattr(registro_privado, "chave", lambda: chave)
    mandados = []
    monkeypatch.setattr(avisar_rafael, "mandar_texto_com_id",
                        lambda texto, html=False, teclado=None: mandados.append((texto, html, teclado)) or 601)
    cifrado = pr.cifrar({"informacao": "Resultado secreto da conferência.", "link": LINK}, chave)
    assert "secreto" not in cifrado
    assert pr.main(["informacao", cifrado]) == 0
    texto, html, teclado = mandados[0]
    assert html is True and "Resultado secreto da conferência." in texto
    assert teclado["inline_keyboard"][0][0]["callback_data"] == "info_vi:1"
    assert pr.informacoes_vencidas(AGORA.replace(year=2000)) == [] and pr.mensagens_da_informacao("I1") == [601]


def test_vista_pela_conversa_tira_os_lembretes_e_deixa_o_aviso(monkeypatch):
    # O "ok" na conversa com o Claude (avisar.yml, vista): os lembretes saem do privado, e o
    # aviso de onde a informação veio fica, marcado como visto, sem o botão, para consulta.
    import avisar_rafael
    pr.nova_informacao("Informação.", LINK, AGORA)
    ids = iter([41, 42, 43])

    async def enviar(texto, teclado):
        return next(ids)
    for horas in range(3):
        rodar(pr.lembrar_informacoes(enviar, AGORA + timedelta(hours=horas)))
    apagadas, editadas, sem_botao = [], [], []
    # A de 42 passou das 48 h: o Telegram não deixa apagar, e o texto dela vira "vista".
    monkeypatch.setattr(avisar_rafael, "apagar_mensagem", lambda ident: ident != 42 and not apagadas.append(ident))
    monkeypatch.setattr(avisar_rafael, "editar_texto",
                        lambda ident, texto, html=False: editadas.append((ident, texto, html)) or True)
    monkeypatch.setattr(avisar_rafael, "tirar_botoes", lambda ident: sem_botao.append(ident) or True)
    assert pr.main(["vista", "i1"]) == 0
    assert apagadas == [43] and editadas[0] == (42, pr.texto_da_vista("I1"), False) and sem_botao == []
    # O aviso fica com a informação e o link, o "você viu" no topo e sem o pedido do Vi ✅.
    ident, aviso, html = editadas[1]
    assert ident == 41 and html is True and "você viu em" in aviso and "(I1)" in aviso
    assert "Informação." in aviso and LINK in aviso and "Toque em" not in aviso and "Lembro" not in aviso
    assert pr.mensagens_da_informacao("I1") == [41, 42]
    assert pr.main(["vista", "I1"]) == 0 and apagadas == [43]          # a segunda vez: nada muda, sem erro
    assert pr.main(["vista", "P1"]) == 1 and pr.main(["vista", "I9"]) == 1


def test_ok_na_conversa_depois_do_vi_no_privado_nao_e_erro(monkeypatch):
    # 18/11: o Rafael tocou no Vi ✅ de 5 informações no privado e também mandou o "ok" delas na conversa;
    # os 5 avisar.yml (vista) saíram vermelhos, com as informações já vistas. A já vista não é erro: nada
    # muda no privado e o workflow fica verde. O código que não existe continua erro.
    import avisar_rafael
    pr.nova_informacao("Informação.", LINK, AGORA)
    assert pr.marcar_vista("I1", AGORA)                                  # o Vi ✅ no privado
    mexidas = []
    monkeypatch.setattr(avisar_rafael, "apagar_mensagem", lambda ident: mexidas.append(ident) or True)
    monkeypatch.setattr(avisar_rafael, "editar_texto",
                        lambda ident, texto, html=False: mexidas.append(ident) or True)
    monkeypatch.setattr(avisar_rafael, "tirar_botoes", lambda ident: mexidas.append(ident) or True)
    monkeypatch.setattr(avisar_rafael, "mandar_texto", lambda texto, html=False: mexidas.append(texto) or True)
    assert pr.main(["vista", "i1"]) == 0 and mexidas == []
    assert pr.main(["vista", "I2"]) == 1 and mexidas == []
    pr.nova("Pergunta?", OPCOES, LINK, AGORA)
    assert pr.marcar_respondida("P1", AGORA)
    assert pr.main(["respondida", "p1"]) == 0 and mexidas == []
    assert pr.main(["respondida", "P2"]) == 1 and pr.main(["respondida", "xyz"]) == 1


def test_lembrete_novo_da_informacao_apaga_o_anterior():
    # Pedido do Rafael (10/11): o lembrete visto não pode ficar no privado, e o Telegram só deixa
    # apagar até 48 h depois do envio. Cada lembrete novo apaga o anterior: ficam o aviso e o
    # último lembrete; o que não sai fica na lista, para sair no visto.
    pr.nova_informacao("Informação.", LINK, AGORA)
    ids, apagadas = iter(range(51, 60)), []

    async def enviar(texto, teclado):
        return next(ids)

    async def apagar(ident):
        apagadas.append(ident)
        return ident != 54
    for horas in range(4):
        rodar(pr.lembrar_informacoes(enviar, AGORA + timedelta(hours=horas), apagar=apagar))
    assert apagadas == [52, 53] and pr.mensagens_da_informacao("I1") == [51, 54]
    # O 54 não sai na hora: fica na lista com o lembrete novo.
    rodar(pr.lembrar_informacoes(enviar, AGORA + timedelta(hours=4), apagar=apagar))
    assert apagadas == [52, 53, 54] and pr.mensagens_da_informacao("I1") == [51, 54, 55]
    # Vista: saem os lembretes, também o tocado, e fica o aviso.
    assert pr.marcar_vista("I1", AGORA + timedelta(hours=5))
    assert pr.lembretes_para_tirar("I1", 55) == (51, [54, 55])
    assert pr.lembretes_para_tirar("I1", 99) == (51, [54, 55, 99])
    # Vista enquanto o lembrete da hora saía: ele sai logo depois.
    pr.nova_informacao("Outra.", LINK, AGORA)

    async def enviar_e_ver(texto, teclado):
        pr.marcar_vista("I2", AGORA)
        return 70
    apagadas.clear()
    rodar(pr.lembrar_informacoes(enviar_e_ver, AGORA, apagar=apagar))
    assert apagadas == [70] and pr.mensagens_da_informacao("I2") == []


def test_robo_lembra_a_informacao_e_o_vi_tira_os_lembretes(bm, monkeypatch):
    pr.nova_informacao("Informação.", LINK)
    enviados, apagadas = [], []

    async def send_message(chat_id, texto, **k):
        enviados.append((chat_id, texto, k.get("reply_markup")))
        return SimpleNamespace(message_id=800 + len(enviados))

    async def delete_message(chat_id, mensagem):
        apagadas.append(mensagem)
    monkeypatch.setattr(bm.bot, "send_message", send_message)
    monkeypatch.setattr(bm.bot, "delete_message", delete_message)
    rodar(bm.lembrar_perguntas_do_claude())
    assert enviados[0][0] == bm.ADMIN_ID and "(I1)" in enviados[0][1]
    botao = enviados[0][2].inline_keyboard[0][0]
    assert botao.text == "Vi ✅" and botao.callback_data == "info_vi:1"
    with pr.db.conexao() as con:
        con.execute("UPDATE informacoes_rafael SET ultimo_aviso = '2000-01-01 00:00:00'")
    rodar(bm.lembrar_perguntas_do_claude())
    assert pr.mensagens_da_informacao("I1") == [801, 802]
    # O lembrete seguinte apaga o anterior (o 801 é o aviso e fica).
    with pr.db.conexao() as con:
        con.execute("UPDATE informacoes_rafael SET ultimo_aviso = '2000-01-01 00:00:00'")
    rodar(bm.lembrar_perguntas_do_claude())
    assert apagadas == [802] and pr.mensagens_da_informacao("I1") == [801, 803]
    # O Vi ✅ no lembrete 803: a informação fica vista, o 803 sai e o 801, o aviso, fica marcado
    # como visto, sem o botão (pedido do Rafael, 10/11).
    avisos, teclados, editadas = [], [], []
    mensagem = SimpleNamespace(message_id=803)

    async def tirar(reply_markup=None):
        teclados.append(reply_markup)
    mensagem.edit_reply_markup = tirar

    async def responder(texto, **k):
        avisos.append(texto)

    async def edit_message_text(texto, chat_id=None, message_id=None, **k):
        editadas.append((message_id, texto, k.get("parse_mode")))
    monkeypatch.setattr(bm.bot, "edit_message_text", edit_message_text)
    clique = SimpleNamespace(data=botao.callback_data, from_user=SimpleNamespace(id=bm.ADMIN_ID), message=mensagem,
                             answer=responder)
    rodar(bm.informacao_vista(clique))
    assert "você viu" in avisos[0] and teclados == [None] and apagadas == [802, 803]
    assert [(ident, modo) for ident, _texto, modo in editadas] == [(801, "HTML")]
    assert "você viu em" in editadas[0][1] and "Toque em" not in editadas[0][1]
    assert pr.informacoes_abertas() == [] and pr.mensagens_da_informacao("I1") == [801]
    rodar(bm.lembrar_perguntas_do_claude())
    assert len(enviados) == 3
    # O Vi ✅ de novo (no aviso que ficou): nada mais sai.
    rodar(bm.informacao_vista(SimpleNamespace(data=botao.callback_data, from_user=SimpleNamespace(id=bm.ADMIN_ID),
                                              message=SimpleNamespace(message_id=801, edit_reply_markup=tirar),
                                              answer=responder)))
    assert "já estava vista" in avisos[-1] and apagadas == [802, 803]
    # Outra pessoa não marca.
    pr.nova_informacao("Outra.", LINK)
    estranho = SimpleNamespace(data="info_vi:2", from_user=SimpleNamespace(id=bm.ADMIN_ID + 1), message=mensagem,
                               answer=responder)
    rodar(bm.informacao_vista(estranho))
    assert [i["codigo"] for i in pr.informacoes_abertas()] == ["I2"]


# --- As informações abertas juntas numa mensagem (pedido do Rafael, 19/11) ---

def test_informacoes_abertas_vao_juntas_numa_mensagem_com_o_vi_de_cada_uma():
    # "qndo tiver varias assim, vc pode unificar em uma só, para facilitar": o lembrete da hora leva
    # todas as que esperam o ok numa mensagem, com o Vi ✅ de cada uma; o lembrete de antes sai uma
    # vez só, e o aviso de onde cada uma veio fica.
    pr.nova_informacao("Vendas: <subiram>.", LINK, AGORA)
    pr.nova_informacao("Seguidores: +3.", LINK, AGORA + timedelta(minutes=30))
    pr.marcar_aviso_da_informacao(1, AGORA, 11)
    pr.marcar_aviso_da_informacao(2, AGORA + timedelta(minutes=30), 12)
    enviados, apagadas = [], []

    async def enviar(texto, teclado):
        enviados.append((texto, teclado))
        return 20 + len(enviados)

    async def apagar(ident):
        apagadas.append(ident)
        return True
    assert rodar(pr.lembrar_informacoes(enviar, AGORA + timedelta(minutes=59), apagar=apagar)) == 0
    # A I1 faz 1 h: as duas vão juntas, também a I2, que ainda não fazia.
    assert rodar(pr.lembrar_informacoes(enviar, AGORA + timedelta(hours=1), apagar=apagar)) == 2
    texto, teclado = enviados[0]
    assert "2 informações do Claude esperam o seu ok" in texto and "(I1, I2)" in texto
    assert "Vendas: &lt;subiram&gt;." in texto and "Seguidores: +3." in texto
    assert "<b>I1</b> (de 23/10, 21:00)" in texto and "<b>I2</b> (de 23/10, 21:30)" in texto
    assert texto.count(LINK) == 1 and len(texto) < 4096
    assert teclado == {"inline_keyboard": [[{"text": "Vi I1 ✅", "callback_data": "info_vi:1"}],
                                           [{"text": "Vi I2 ✅", "callback_data": "info_vi:2"}]]}
    assert pr.mensagens_da_informacao("I1") == [11, 21] and pr.mensagens_da_informacao("I2") == [12, 21]
    assert apagadas == []
    # A hora seguinte: uma mensagem nova com as duas, e a de antes sai uma vez só.
    assert rodar(pr.lembrar_informacoes(enviar, AGORA + timedelta(hours=2), apagar=apagar)) == 2
    assert apagadas == [21] and pr.mensagens_da_informacao("I1") == [11, 22]
    assert pr.mensagens_da_informacao("I2") == [12, 22]


def test_informacoes_que_nao_cabem_vao_na_mensagem_seguinte():
    # O Telegram leva até 4096 caracteres por mensagem: a que não cabe vai na mensagem seguinte, e a
    # que fica sozinha vai no aviso de sempre, com o Vi ✅ dela.
    for n in range(3):
        pr.nova_informacao(f"Informação {n + 1}: " + "x" * 1600, LINK, AGORA)
    enviados = []

    async def enviar(texto, teclado):
        enviados.append((texto, teclado))
        return 30 + len(enviados)
    assert rodar(pr.lembrar_informacoes(enviar, AGORA)) == 3
    assert len(enviados) == 2 and all(pr._visivel(texto) <= pr.LIMITE_DA_MENSAGEM for texto, _t in enviados)
    assert "(I1, I2)" in enviados[0][0] and len(enviados[0][1]["inline_keyboard"]) == 2
    assert "(I3)" in enviados[1][0] and enviados[1][1] == pr.teclado_da_informacao({"id": 3})
    assert pr.mensagens_da_informacao("I1") == [31] and pr.mensagens_da_informacao("I3") == [32]


def test_reenviar_manda_as_abertas_na_hora(monkeypatch, capsys):
    # "Sempre qndo tiver essas I20, I21, I22, etc em aberto para eu ver, vai mandando no meu particular":
    # o Claude lista as abertas na conversa e chama o reenviar (avisar.yml, informacoes). Elas vão de
    # novo ao privado na hora, juntas, sem esperar a hora, e o lembrete de antes sai. No log, só os códigos.
    import avisar_rafael
    mandados, apagadas = [], []
    monkeypatch.setattr(avisar_rafael, "mandar_texto_com_id", lambda texto, html=False, teclado=None:
                        mandados.append((texto, html, teclado)) or 700 + len(mandados))
    monkeypatch.setattr(avisar_rafael, "apagar_mensagem", lambda ident: apagadas.append(ident) or True)
    assert pr.main(["reenviar"]) == 0 and "Nenhuma informação em aberto" in capsys.readouterr().out
    assert mandados == []
    pr.nova_informacao("Primeira.", LINK)
    pr.nova_informacao("Segunda.", LINK)
    pr.marcar_aviso_da_informacao(1, None, 61)
    pr.marcar_aviso_da_informacao(1, None, 62)                      # o lembrete da hora
    pr.marcar_aviso_da_informacao(2, None, 63)
    assert pr.main(["reenviar"]) == 0
    saida = capsys.readouterr().out
    assert "Em aberto: I1, I2. 2 de 2" in saida and "Primeira" not in saida and "Segunda" not in saida
    texto, html, teclado = mandados[0]
    assert html is True and "Primeira." in texto and "Segunda." in texto and len(teclado["inline_keyboard"]) == 2
    assert apagadas == [62] and pr.mensagens_da_informacao("I1") == [61, 701]
    assert pr.mensagens_da_informacao("I2") == [63, 701]


def test_vi_no_lembrete_junto_tira_so_a_vista(bm, monkeypatch):
    # O Vi I1 ✅ no lembrete junto: a I1 fica vista e sai da mensagem, que fica só com a I2 e o Vi ✅
    # dela; o aviso de onde a I1 veio fica marcado como visto. O Vi da última apaga o lembrete.
    pr.nova_informacao("Primeira.", LINK)
    pr.nova_informacao("Segunda.", LINK)
    pr.marcar_aviso_da_informacao(1, None, 801)
    pr.marcar_aviso_da_informacao(2, None, 802)
    enviados, apagadas, editadas, teclados, avisos = [], [], [], [], []

    async def send_message(chat_id, texto, **k):
        enviados.append((texto, k.get("reply_markup")))
        return SimpleNamespace(message_id=810 + len(enviados))

    async def delete_message(chat_id, mensagem):
        apagadas.append(mensagem)

    async def edit_message_text(texto, chat_id=None, message_id=None, **k):
        editadas.append((message_id, texto, k.get("reply_markup")))
    monkeypatch.setattr(bm.bot, "send_message", send_message)
    monkeypatch.setattr(bm.bot, "delete_message", delete_message)
    monkeypatch.setattr(bm.bot, "edit_message_text", edit_message_text)
    with pr.db.conexao() as con:
        con.execute("UPDATE informacoes_rafael SET ultimo_aviso = '2000-01-01 00:00:00'")
    rodar(bm.lembrar_perguntas_do_claude())
    texto, botoes = enviados[0]
    assert "(I1, I2)" in texto and [linha[0].text for linha in botoes.inline_keyboard] == ["Vi I1 ✅", "Vi I2 ✅"]
    mensagem = SimpleNamespace(message_id=811)

    async def tirar(reply_markup=None):
        teclados.append(reply_markup)
    mensagem.edit_reply_markup = tirar

    async def responder(texto, **k):
        avisos.append(texto)
    rodar(bm.informacao_vista(SimpleNamespace(data=botoes.inline_keyboard[0][0].callback_data, message=mensagem,
                                              from_user=SimpleNamespace(id=bm.ADMIN_ID), answer=responder)))
    assert "você viu" in avisos[0] and teclados == [] and apagadas == []
    (refeita, texto_novo, botoes_novos), (aviso, texto_visto, _b) = editadas
    assert refeita == 811 and "Segunda." in texto_novo and "Primeira." not in texto_novo
    assert [(b.text, b.callback_data) for linha in botoes_novos.inline_keyboard for b in linha] == [
        ("Vi ✅", "info_vi:2")]
    assert aviso == 801 and "você viu em" in texto_visto and "(I1)" in texto_visto
    assert pr.mensagens_da_informacao("I1") == [801] and pr.mensagens_da_informacao("I2") == [802, 811]
    # O Vi ✅ da I2 no mesmo lembrete: agora ele sai, e o aviso da I2 fica marcado como visto.
    rodar(bm.informacao_vista(SimpleNamespace(data="info_vi:2", from_user=SimpleNamespace(id=bm.ADMIN_ID),
                                              message=mensagem, answer=responder)))
    assert apagadas == [811] and teclados == [None] and editadas[-1][0] == 802
    assert pr.informacoes_abertas() == []


def test_ok_na_conversa_tira_a_vista_do_lembrete_junto(monkeypatch):
    # O "ok" na conversa (avisar.yml, vista): o lembrete junto fica, sem a vista e com o Vi ✅ da outra.
    import avisar_rafael
    pr.nova_informacao("Primeira.", LINK)
    pr.nova_informacao("Segunda.", LINK)
    for ident, mensagem in ((1, 61), (2, 62), (1, 70), (2, 70)):
        pr.marcar_aviso_da_informacao(ident, None, mensagem)
    apagadas, editadas = [], []
    monkeypatch.setattr(avisar_rafael, "apagar_mensagem", lambda ident: apagadas.append(ident) or True)
    monkeypatch.setattr(avisar_rafael, "editar_texto", lambda ident, texto, html=False, teclado=None:
                        editadas.append((ident, texto, teclado)) or True)
    monkeypatch.setattr(avisar_rafael, "tirar_botoes", lambda ident: True)
    assert pr.main(["vista", "I2"]) == 0 and apagadas == []
    (refeita, texto, teclado), (aviso, visto, _t) = editadas
    assert refeita == 70 and "Primeira." in texto and "Segunda." not in texto
    assert teclado == pr.teclado_da_informacao({"id": 1})
    assert aviso == 62 and "você viu" in visto
    assert pr.mensagens_da_informacao("I1") == [61, 70] and pr.mensagens_da_informacao("I2") == [62]
    # Sem o aviso guardado, o 1º da lista é um lembrete junto: ele é refeito, e nada fica marcado como visto.
    pr.nova_informacao("Terceira.", LINK)
    pr.marcar_aviso_da_informacao(3, None, 70)
    assert pr.marcar_vista("I3")
    fica, sair, refazer = pr.depois_da_vista("I3", 70)
    assert fica is None and sair == [70] and [i["codigo"] for i in refazer[70]] == ["I1"]
