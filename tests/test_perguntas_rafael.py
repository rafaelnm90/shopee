"""perguntas_rafael.py: a pergunta do Claude vai ao privado e é lembrada de hora em hora até a resposta."""
from datetime import datetime, timedelta

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
    monkeypatch.setattr(avisar_rafael, "mandar_texto", lambda texto, html=False: mandados.append((texto, html)) or True)
    cifrado = pr.cifrar({"pergunta": "Pergunta secreta?", "opcoes": OPCOES, "link": LINK}, chave)
    assert "secreta" not in cifrado
    assert pr.receber(cifrado, AGORA) == "P1"
    assert mandados[0][1] is True and "Pergunta secreta?" in mandados[0][0]
    assert pr.vencidas(AGORA + timedelta(minutes=30)) == []                     # já avisada agora


def test_robo_lembra_pelo_privado(bm, monkeypatch):
    pr.nova("Pergunta?", OPCOES, LINK)
    enviados = []

    async def send_message(chat_id, texto, **k):
        enviados.append((chat_id, texto, k.get("parse_mode")))
    monkeypatch.setattr(bm.bot, "send_message", send_message)
    rodar(bm.lembrar_perguntas_do_claude())
    assert enviados and enviados[0][0] == bm.ADMIN_ID and enviados[0][2] == "HTML"
    rodar(bm.lembrar_perguntas_do_claude())                                    # menos de 1 h: não repete
    assert len(enviados) == 1
