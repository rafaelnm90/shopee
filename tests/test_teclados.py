"""Teclados do bot_mestre: um jeito só de montar, e um teclado só para cada um repetido."""
import ast
import os

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _botoes(teclado):
    return [[b.text for b in linha] for linha in teclado.keyboard]


def test_montar_teclado_fixa_embaixo_e_ajusta_o_tamanho(bm):
    teclado = bm.montar_teclado([[bm.KeyboardButton(text="A")]])
    assert teclado.resize_keyboard is True and teclado.is_persistent is True
    assert _botoes(bm.teclado_com_cancelar("Salvar ✅")) == [["Salvar ✅", "Cancelar ❌"]]
    assert _botoes(bm.teclado_aprovar_cancelar) == [["Aprovar ✅", "Cancelar ❌"]]
    assert _botoes(bm.teclado_janela_dia_todo) == [["Dia Todo (24h) 🕛"], ["Cancelar ❌"]]


def test_ninguem_monta_teclado_do_padrao_a_mao():
    # O padrão (fixo e ajustado) sai só do montar_teclado: assim um ajuste vale para todos.
    arvore = ast.parse(open(os.path.join(PASTA, "bot_mestre.py"), encoding="utf-8").read())
    fora = []
    for funcao in ast.walk(arvore):
        if isinstance(funcao, ast.FunctionDef) and funcao.name == "montar_teclado":
            dentro = {id(n) for n in ast.walk(funcao)}
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call) and getattr(no.func, "id", None) == "ReplyKeyboardMarkup" and id(no) not in dentro:
            nomes = sorted(k.arg for k in no.keywords)
            if nomes == ["is_persistent", "keyboard", "resize_keyboard"]:
                fora.append(no.lineno)
    assert fora == []
