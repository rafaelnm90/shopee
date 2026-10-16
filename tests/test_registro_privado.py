"""Registro privado: o administradores.md no repositório privado do GitHub, só para o Rafael e o Claude."""
import os
from types import SimpleNamespace

import pytest

from conftest import rodar

CHAVE_PUBLICA = "ssh-ed25519 CHAVEPUBLICADETESTE robo-shopee-registro"


@pytest.fixture
def rp(monkeypatch, tmp_path):
    import registro_admins
    import registro_privado
    monkeypatch.setattr(registro_privado, "PASTA", str(tmp_path / "clone"))
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


class GitFalso:
    """Respostas do git por comando; cria a pasta do clone quando o clone dá certo."""

    def __init__(self, rp, respostas=None):
        self.rp, self.respostas, self.chamadas = rp, respostas or {}, []

    def __call__(self, *argumentos, pasta=None):
        comando = argumentos[0] if argumentos[0] != "-c" else argumentos[4]
        self.chamadas.append(comando)
        codigo, erro = self.respostas.get(comando, (0, ""))
        if comando == "clone" and codigo == 0:
            os.makedirs(os.path.join(self.rp.PASTA, ".git"))
        return SimpleNamespace(returncode=codigo, stderr=erro, stdout="")


def test_arquivo_tem_os_admins_de_cada_grupo_e_o_historico(rp):
    texto = rp.montar_relatorio()
    assert "## 📢 Acervo Viral Shopee (canal)" in texto and "ID `-1003932482573`" in texto
    assert "| Rafael | @Rafaelnm | dono | tudo |  |  |" in texto
    assert "Bot \\| Vídeos (bot): deixou de ser admin" not in texto     # o nome vai na mudança, sem escapar
    assert "· Acervo Viral Shopee: Bot | Vídeos deixou de ser admin" in texto
    assert rp.montar_relatorio() == texto                               # sem hora de agora: não muda à toa


def test_sem_repositorio_ou_sem_chave_vira_sem_acesso(rp, monkeypatch):
    monkeypatch.setattr(rp, "_git", GitFalso(rp, {"clone": (128, "ERROR: Repository not found.")}))
    assert rp.publicar("texto") == "sem_acesso"
    git = GitFalso(rp, {"diff": (1, ""), "push": (128, "ERROR: The key you are authenticating with has been "
                                                        "marked as read only.")})
    monkeypatch.setattr(rp, "_git", git)
    assert rp.publicar("texto") == "sem_acesso"


def test_envia_so_quando_o_arquivo_muda(rp, monkeypatch):
    git = GitFalso(rp, {"diff": (1, "")})
    monkeypatch.setattr(rp, "_git", git)
    assert rp.publicar("versão 1") == "ok" and git.chamadas[-2:] == ["commit", "push"]
    assert open(os.path.join(rp.PASTA, rp.ARQUIVO), encoding="utf-8").read() == "versão 1"
    git = GitFalso(rp, {"diff": (0, "")})
    monkeypatch.setattr(rp, "_git", git)
    assert rp.publicar("versão 1") == "sem_mudanca" and "push" not in git.chamadas


def test_loop_guarda_a_situacao_e_nao_reenvia_o_mesmo_arquivo(rp, monkeypatch):
    respostas, enviados = ["sem_acesso", "ok"], []

    def publicar(texto):
        enviados.append(texto)
        return respostas.pop(0)

    monkeypatch.setattr(rp, "publicar", publicar)
    assert rodar(rp.publicar_se_mudou(CHAVE_PUBLICA)) == "sem_acesso"
    assert rp.situacao()["situacao"] == "sem_acesso" and rp.situacao()["chave_publica"] == CHAVE_PUBLICA
    assert rodar(rp.publicar_se_mudou(CHAVE_PUBLICA)) == "ok"
    assert rodar(rp.publicar_se_mudou(CHAVE_PUBLICA)) == "sem_mudanca" and len(enviados) == 2


def test_bot_manda_a_chave_uma_vez_e_avisa_quando_liga(bm, rp, monkeypatch):
    import painel_admins
    enviadas = []

    async def send_message(chat_id, texto, **k):
        enviadas.append(texto)

    monkeypatch.setattr(bm.bot, "send_message", send_message)
    bm.db.salvar_config(rp.CHAVE_STATUS, {"situacao": "sem_acesso", "chave_publica": CHAVE_PUBLICA})
    rodar(painel_admins.avisar_registro_privado())
    rodar(painel_admins.avisar_registro_privado())
    assert len(enviadas) == 1 and CHAVE_PUBLICA in enviadas[0] and rp.LINK_CADASTRAR_CHAVE in enviadas[0]
    assert "esperando o repositório e a chave" in painel_admins.linha_registro_privado()

    bm.db.atualizar_config(rp.CHAVE_STATUS, lambda s: s.update(situacao="ok", ultimo_envio="2026-10-16 21:00:00"))
    rodar(painel_admins.avisar_registro_privado())
    rodar(painel_admins.avisar_registro_privado())
    assert len(enviadas) == 2 and "Registro privado ligado" in enviadas[1]
    assert "✅ em dia (último envio em 16/10 às 21:00)" in painel_admins.linha_registro_privado()

    outra = CHAVE_PUBLICA.replace("TESTE", "NOVA")                       # o servidor perdeu a chave e gerou outra
    bm.db.atualizar_config(rp.CHAVE_STATUS, lambda s: s.update(situacao="sem_acesso", chave_publica=outra))
    rodar(painel_admins.avisar_registro_privado())
    assert len(enviadas) == 3 and outra in enviadas[2]
