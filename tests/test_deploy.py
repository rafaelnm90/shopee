"""
O deploy.yml: o reinício do bot_mestre espera o pedido do grupo dos amigos terminar, até 10 min, e o tempo do SSH
cabe essa espera (DECISOES.md, Monitor, deploy e servidor, 24/11/2026).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

import db

RAIZ = Path(__file__).resolve().parent.parent


def _passo_do_ssh():
    fluxo = yaml.safe_load((RAIZ / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8"))
    for trabalho in fluxo["jobs"].values():
        for passo in trabalho.get("steps") or []:
            if "ssh-action" in str(passo.get("uses", "")):
                return passo["with"]
    raise AssertionError("o deploy.yml não tem o passo do SSH")


def _pedidos_pela_sonda(script):
    """Roda a sonda do deploy, como no servidor, na pasta do teste (com o banco do teste)."""
    sonda = re.search(r'PEDIDOS=\$\(python3 -c "([^"]+)"', script)
    assert sonda, "o deploy não confere a fila do grupo dos amigos antes do reinício"
    saida = subprocess.run([sys.executable, "-c", sonda.group(1)], cwd=os.getcwd(), capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": str(RAIZ)}, timeout=60)
    return (saida.stdout.strip().splitlines() or [""])[-1]


def test_o_reinicio_do_bot_mestre_espera_a_fila_do_grupo_dos_amigos():
    passo = _passo_do_ssh()
    script = passo["script"]
    espera = script.index("grupo_dos_amigos")
    assert espera < script.index('echo "🔄 Reiniciando $SERVICO..."')
    assert '"$SERVICO" = "bot_mestre_bot"' in script[script.rindex("for SERVICO in", 0, espera):espera]
    # Até 40 voltas de 15 s (10 min), e o SSH com tempo para a espera e a conferência dos robôs depois.
    assert "seq 1 40" in script and "sleep 15" in script
    assert int(re.fullmatch(r"(\d+)m", str(passo["command_timeout"])).group(1)) >= 20

    assert _pedidos_pela_sonda(script) == "0"
    with db.conexao() as conexao:
        conexao.execute("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    assert _pedidos_pela_sonda(script) == "0"
    db.salvar_config("grupo_dos_amigos", {"fila": [{"quem": 1}, {"quem": 2}], "preparos": [60]})
    assert _pedidos_pela_sonda(script) == "2"
