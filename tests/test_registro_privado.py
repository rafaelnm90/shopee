"""Registro privado: o registro dos administradores cifrado no ramo registro-admins, só o Claude abre."""
import os
import stat
import subprocess
import sys

import pytest

from conftest import rodar

PASTA_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def rp(monkeypatch, tmp_path):
    import registro_admins
    import registro_privado
    monkeypatch.setattr(registro_privado, "CHAVE_ARQUIVO", str(tmp_path / "config" / "registro_admins.chave"))
    registro_admins.inicializar_tabelas()
    grupos = [{"chat_id": "-1003932482573", "nome": "Acervo Viral Shopee", "tipo": "canal", "admins": [
        {"user_id": 1, "nome": "Rafael", "usuario": "Rafaelnm", "bot": False, "papel": "dono", "titulo": "",
         "permissoes": [], "promovido_por": None},
        {"user_id": 2, "nome": "Bot | Vídeos", "usuario": "ShopeeVbot", "bot": True, "papel": "admin", "titulo": "",
         "permissoes": ["post_messages", "delete_messages"], "promovido_por": 1}]}]
    registro_admins.gravar(grupos)
    grupos[0]["admins"].pop()
    registro_admins.gravar(grupos)
    return registro_privado


def test_arquivo_tem_os_admins_de_cada_grupo_e_o_historico(rp):
    texto = rp.montar_relatorio()
    assert "## 📢 Acervo Viral Shopee (canal)" in texto and "ID `-1003932482573`" in texto
    assert "| Rafael | @Rafaelnm | dono | tudo |  |  |" in texto
    assert "· Acervo Viral Shopee: Bot | Vídeos deixou de ser admin" in texto
    assert rp.montar_relatorio() == texto                               # sem hora de agora: não muda à toa


def test_chave_criada_uma_vez_so_para_o_dono(rp):
    chave = rp.chave()
    assert rp.chave() == chave
    assert stat.S_IMODE(os.stat(rp.CHAVE_ARQUIVO).st_mode) == 0o600
    assert os.listdir(os.path.dirname(rp.CHAVE_ARQUIVO)) == ["registro_admins.chave"]


def test_cifrado_nao_mostra_nomes_e_so_a_chave_abre(rp):
    saida = rp.cifrado()
    assert "Rafael" not in saida and "Acervo" not in saida and saida.startswith("gAAAAA")
    assert rp.abrir(saida, rp.chave().decode()) == rp.montar_relatorio()
    from cryptography.fernet import Fernet, InvalidToken
    with pytest.raises(InvalidToken):
        rp.abrir(saida, Fernet.generate_key().decode())


def test_mesmo_registro_da_o_mesmo_arquivo_e_mudanca_da_outro(rp):
    import registro_admins
    primeiro = rp.cifrado()
    assert rp.cifrado() == primeiro                                     # o workflow não faz commit à toa
    assert rp.situacao()["ultima_copia"]
    registro_admins.gravar([])                                          # o grupo saiu do registro
    assert rp.cifrado() != primeiro


def test_sem_conferencia_ainda_sai_um_arquivo_que_diz_isso(rp):
    import db
    db.salvar_config("registro_admins", {})
    assert "Ainda sem conferência" in rp.abrir(rp.cifrado(), rp.chave().decode())


def test_claude_le_o_arquivo_com_a_chave_do_ambiente(rp, tmp_path):
    arquivo = tmp_path / rp.ARQUIVO
    arquivo.write_text(rp.cifrado(), encoding="ascii")
    comando = [sys.executable, os.path.join(PASTA_PROJETO, "registro_privado.py"), "ler", str(arquivo)]
    ambiente = dict(os.environ, **{rp.VARIAVEL_CHAVE: rp.chave().decode()})
    resultado = subprocess.run(comando, capture_output=True, text=True, env=ambiente, cwd=tmp_path, timeout=60)
    assert resultado.returncode == 0 and resultado.stdout == rp.montar_relatorio()
    ambiente.pop(rp.VARIAVEL_CHAVE)
    resultado = subprocess.run(comando, capture_output=True, text=True, env=ambiente, cwd=tmp_path, timeout=60)
    assert resultado.returncode == 1 and rp.VARIAVEL_CHAVE in resultado.stdout


def test_bot_manda_a_chave_uma_vez_por_chave(bm, rp, monkeypatch):
    import painel_admins
    enviadas = []

    async def send_message(chat_id, texto, **k):
        enviadas.append(texto)

    monkeypatch.setattr(bm.bot, "send_message", send_message)
    assert "a primeira sai às 05:47" in painel_admins.linha_registro_privado()
    rodar(painel_admins.avisar_registro_privado())
    rodar(painel_admins.avisar_registro_privado())
    assert len(enviadas) == 1 and f"{rp.VARIAVEL_CHAVE}={rp.chave().decode()}" in enviadas[0]

    os.remove(rp.CHAVE_ARQUIVO)                                         # o servidor perdeu a chave e gera outra
    rodar(painel_admins.avisar_registro_privado())
    assert len(enviadas) == 2 and rp.chave().decode() in enviadas[1]

    bm.db.atualizar_config(rp.CHAVE_STATUS, lambda s: s.update(ultima_copia="2026-10-17 05:47:10"))
    assert "última em 17/10 às 05:47" in painel_admins.linha_registro_privado()
