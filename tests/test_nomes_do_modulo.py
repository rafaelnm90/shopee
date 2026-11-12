"""Nenhum módulo do projeto dá o mesmo nome a duas coisas no nível do módulo."""
import ast
import glob
import os
from collections import Counter

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def nomes_repetidos(codigo):
    """Os nomes que o código atribui mais de uma vez no nível do módulo, em ordem."""
    contagem = Counter()
    for no in ast.parse(codigo).body:
        if isinstance(no, ast.Assign):
            alvos = no.targets
        elif isinstance(no, ast.AnnAssign) and no.value is not None:
            alvos = [no.target]
        else:
            continue
        for alvo in alvos:
            contagem.update(n.id for n in ast.walk(alvo) if isinstance(n, ast.Name))
    return sorted(nome for nome, vezes in contagem.items() if vezes > 1)


def test_nenhum_nome_atribuido_duas_vezes_no_nivel_do_modulo():
    # A 2ª atribuição vale por cima da 1ª para o módulo inteiro, e quem contava com a 1ª passa a usar
    # a outra sem aviso (12/11: a tira das faixas brancas da P206 1, 5%, ficou com o nome da tira da
    # conferência da faixa na grade, 0,8%, e a detecção das faixas usava 0,8%). O pyflakes não acusa.
    repetidos = {}
    for arquivo in sorted(glob.glob(os.path.join(PASTA, "*.py"))):
        with open(arquivo, encoding="utf-8") as f:
            nomes = nomes_repetidos(f.read())
        if nomes:
            repetidos[os.path.basename(arquivo)] = nomes
    assert repetidos == {}


def test_a_conferencia_acha_o_nome_repetido():
    assert nomes_repetidos("A = 1\nB, A = 2, 3\nC: int = 4\nC: int = 5\n") == ["A", "C"]
    assert nomes_repetidos("A = 1\ndef f():\n    A = 2\n") == []
