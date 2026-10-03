"""DECISOES.md: os comentários do código que apontam para o diário acham a área certa."""
import glob
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _areas():
    """Títulos "## " do diário, sem o parêntese do fim: "Canal Viral (Espião)" vale "Canal Viral"."""
    with open(os.path.join(RAIZ, "DECISOES.md"), encoding="utf-8") as f:
        return {re.sub(r"\s*\(.*\)$", "", linha[3:].strip()) for linha in f if linha.startswith("## ")}


def test_apontamentos_do_codigo_existem_no_diario():
    areas = _areas()
    # O nome da área termina no fim da frase ou na quebra do comentário.
    padrao = re.compile(r"DECISOES\.md, ([^)\n.:]+)")
    quebrados, total = [], 0
    for caminho in glob.glob(os.path.join(RAIZ, "*.py")):
        with open(caminho, encoding="utf-8") as f:
            for numero, linha in enumerate(f, 1):
                for area in padrao.findall(linha):
                    total += 1
                    if area.strip() not in areas:
                        quebrados.append(f"{os.path.basename(caminho)}:{numero} -> '{area.strip()}'")
    assert total > 0
    assert quebrados == [], "área inexistente no DECISOES.md: " + ", ".join(quebrados)
