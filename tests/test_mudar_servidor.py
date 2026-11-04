"""
O kit de mudança de servidor (P147 1): os robôs nunca ficam ligados nos dois servidores, o de
agora volta sozinho quando o novo não sobe, e o log não mostra o endereço dos servidores.
"""
import os
import re

import pytest

import mudar_servidor as ms
import servicos_afetados


class ServidorDeMentira:
    """Guarda cada comando e responde pelas regras do teste: [(trecho do comando, (código, saída))]."""

    def __init__(self, nome, regras, host="203.0.113.7"):
        self.nome, self.host, self.regras, self.comandos = nome, host, regras, []

    def rodar(self, comando, entrada=None, tempo=600):
        self.comandos.append(comando)
        for trecho, resposta in self.regras:
            if re.search(trecho, comando):
                return resposta
        return 0, ""

    def ok(self, comando, entrada=None, tempo=600):
        return self.rodar(comando, entrada, tempo)[0] == 0


ATIVOS = "\n".join(["active"] * len(ms.SERVICOS))


def _o_de_agora(rodada="0"):
    return ServidorDeMentira("de agora", [
        (r"list-units 'robo-shopee-video-\*'", (0, rodada)),
        (r"backup_dados.py >/dev/null", (0, "/home/ubuntu/backups/shopee_backup_2026-11-04_0100.tar.gz")),
        (r"^systemctl is-active bot_mestre_bot ;", (0, ATIVOS)),
    ])


def _o_novo(ativos=ATIVOS, preparado=True):
    return ServidorDeMentira("novo", [
        (r"test -x ~/shopee/venv/bin/python3", (0 if preparado else 1, "")),
        (r"systemctl is-active --quiet", (3, "")),          # nenhum robô ligado antes da mudança
        (r"^crontab -l", (1, "")),                           # nem tarefa no crontab
        (r"^systemctl is-active bot_mestre_bot ;", (0, ativos)),
    ])


@pytest.fixture
def transferencias(monkeypatch):
    feitas = []

    def transferir(de, comando_de, para, comando_para, tempo=3600):
        feitas.append((de.nome, comando_de, para.nome, comando_para))
        return True
    monkeypatch.setattr(ms, "transferir", transferir)
    return feitas


def _posicao(servidor, trecho):
    return next(i for i, c in enumerate(servidor.comandos) if trecho in c)


def test_mudanca_para_o_de_agora_antes_de_ligar_o_novo(transferencias):
    agora, novo = _o_de_agora(), _o_novo()
    linhas = ms.mudar(agora, novo, esperar=lambda s: None)

    assert linhas[-1].startswith("✅ Robôs no servidor novo")
    # O bot (que chama as rodadas do robô) para primeiro; depois os outros saem do início automático.
    assert agora.comandos.index("sudo -n systemctl stop bot_mestre_bot") < _posicao(agora, "systemctl disable")
    # O backup é feito com tudo parado, e a pasta do de agora sai do lugar antes de o novo ligar.
    assert _posicao(agora, "systemctl disable") < _posicao(agora, "backup_dados.py")
    assert "mv ~/shopee ~/shopee.antes_da_mudanca" in agora.comandos
    assert not any("enable" in c for c in agora.comandos)
    assert _posicao(novo, "backup_dados.py restaurar") < _posicao(novo, "enable --quiet --now")
    # O crontab do de agora sai de cena junto com os robôs, antes do backup.
    guardar = "crontab -l > ~/crontab.antes_da_mudanca && crontab -r"
    assert _posicao(agora, "systemctl disable") < agora.comandos.index(guardar) < _posicao(agora, "backup_dados.py")
    # O que passa de um para o outro: o pacote, a mesma senha da cópia, os vídeos dos rascunhos
    # e as tarefas do crontab.
    assert [t[1] for t in transferencias] == ["cat /home/ubuntu/backups/shopee_backup_2026-11-04_0100.tar.gz",
                                              "cat ~/.config/backup_fora.chave", "tar czf - -C ~ shopee_video",
                                              "cat ~/crontab.antes_da_mudanca"]
    assert transferencias[-1][3] == "crontab -"
    assert all(de == "de agora" and para == "novo" for de, _c, para, _d in transferencias)


def test_novo_que_nao_sobe_devolve_os_robos_ao_de_agora(transferencias):
    caido = "\n".join(["active"] * (len(ms.SERVICOS) - 1) + ["failed"])
    agora, novo = _o_de_agora(), _o_novo(ativos=caido)
    # A pasta guardada de lado e nenhuma no lugar: a volta a devolve.
    agora.regras.insert(0, (r"test -d ~/shopee.antes_da_mudanca && ! test -e ~/shopee", (0, "")))

    with pytest.raises(ms.Falha, match="voltaram ao servidor de agora"):
        ms.mudar(agora, novo, esperar=lambda s: None)

    assert any("disable --quiet --now" in c for c in novo.comandos)
    assert "mv ~/shopee.antes_da_mudanca ~/shopee" in agora.comandos
    assert any(c.startswith("sudo -n systemctl enable --quiet --now bot_mestre_bot") for c in agora.comandos)
    assert _posicao(novo, "disable --quiet --now") >= 0
    # O crontab copiado sai do novo, e o do de agora volta ao lugar.
    assert "crontab -r 2>/dev/null || true" in novo.comandos
    assert "crontab ~/crontab.antes_da_mudanca && rm -f ~/crontab.antes_da_mudanca" in agora.comandos


def test_novo_com_crontab_proprio_nada_para_no_de_agora(transferencias):
    # O voltar apaga o crontab do novo: com tarefas que não são a cópia, a mudança nem começa.
    agora, novo = _o_de_agora(), _o_novo()
    novo.regras.insert(0, (r"^crontab -l", (0, "")))
    with pytest.raises(ms.Falha, match="crontab"):
        ms.mudar(agora, novo, esperar=lambda s: None)
    assert agora.comandos == [] and transferencias == []


def test_sem_crontab_no_de_agora_nada_de_crontab_vai(transferencias):
    agora, novo = _o_de_agora(), _o_novo()
    agora.regras[:0] = [(r"^crontab -l", (1, "")), (r"test -f ~/crontab.antes_da_mudanca", (1, ""))]
    ms.mudar(agora, novo, esperar=lambda s: None)
    assert not any("crontab -r" in c for c in agora.comandos)
    assert "cat ~/crontab.antes_da_mudanca" not in [t[1] for t in transferencias]


def test_sem_o_novo_preparado_nada_para_no_de_agora(transferencias):
    agora, novo = _o_de_agora(), _o_novo(preparado=False)
    with pytest.raises(ms.Falha, match="preparar"):
        ms.mudar(agora, novo, esperar=lambda s: None)
    assert agora.comandos == [] and transferencias == []


def test_rodada_do_robo_que_nao_acaba_devolve_o_bot(monkeypatch, transferencias):
    monkeypatch.setattr(ms, "ESPERA_DA_RODADA", 0)
    agora, novo = _o_de_agora(rodada="1"), _o_novo()
    with pytest.raises(ms.Falha, match="rodada do robô"):
        ms.mudar(agora, novo, esperar=lambda s: None)
    assert not any("backup_dados.py" in c for c in agora.comandos) and transferencias == []
    assert any(c.startswith("sudo -n systemctl enable --quiet --now") for c in agora.comandos)


def test_voltar_desliga_o_novo_e_religa_o_de_agora():
    agora, novo = _o_de_agora(), _o_novo()
    agora.regras.insert(0, (r"test -d ~/shopee.antes_da_mudanca && ! test -e ~/shopee", (0, "")))
    linhas = ms.voltar(agora, novo, esperar=lambda s: None)
    assert linhas[-1].startswith("servidor de agora: os 5 robôs ligados")
    assert "mv ~/shopee.antes_da_mudanca ~/shopee" in agora.comandos
    assert any("disable --quiet --now" in c for c in novo.comandos)


def test_conferir_nao_mostra_o_endereco_dos_servidores():
    agora, novo = _o_de_agora(), _o_novo()
    texto = "\n".join(ms.conferir(agora, novo))
    assert "203.0.113.7" not in texto and "acesso por SSH: ok" in texto
    assert "segredos NOVO_HOST" in "\n".join(ms.conferir(agora, None))
    with pytest.raises(ms.Falha):
        ms.conferir(None, novo)


def test_chaves_dos_segredos_vao_para_arquivos_so_do_dono(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    for prefixo in ("ORACLE", "NOVO"):
        monkeypatch.setenv(f"{prefixo}_HOST", "203.0.113.7")
        monkeypatch.setenv(f"{prefixo}_USER", "ubuntu")
        monkeypatch.setenv(f"{prefixo}_SSH_KEY", "chave de teste")
    agora, novo = ms.servidores()
    assert agora.nome == "de agora" and novo.nome == "novo"
    assert oct(os.stat(agora.chave).st_mode & 0o777) == "0o600"
    monkeypatch.delenv("NOVO_HOST")
    assert ms.servidores()[1] is None


def test_kit_usa_os_mesmos_nomes_do_resto_do_codigo():
    import painel_shopee_video
    assert ms.UNIDADE_DA_RODADA == painel_shopee_video.UNIDADE_DA_RODADA
    assert ms.SERVICOS == tuple(servicos_afetados.SERVICOS)
    pasta = os.path.dirname(ms.INSTALADOR)
    assert all(os.path.isfile(os.path.join(pasta, f"{s}.service")) for s in ms.SERVICOS)
    # O instalador sem a lista do kit usa a mesma lista de pacotes.
    with open(ms.INSTALADOR, encoding="utf-8") as arquivo:
        assert f'${{PACOTES:-{" ".join(ms.PACOTES)}}}' in arquivo.read()
