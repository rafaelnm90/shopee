"""legendas: a legenda dos posts e o pedido de nome e hashtags à IA, iguais em todos os robôs."""
import glob
import os

import legendas
import motor_userbot as mu
from conftest import rodar

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINK = "https://s.shopee.com.br/AbC1"


def test_separa_o_nome_das_hashtags():
    assert legendas.separar_nome_e_hashtags("Copo Térmico 🥤\n#CasaEDecoracao #Saude") == \
        ("Copo Térmico 🥤", "#CasaEDecoracao #Saude")
    assert legendas.separar_nome_e_hashtags("  Só o nome 🛍️  ") == ("Só o nome 🛍️", "")
    assert legendas.separar_nome_e_hashtags(None) == ("", "")


def test_legenda_com_nome_link_e_hashtags():
    assert legendas.legenda_da_ia("Copo Térmico 🥤\n#CasaEDecoracao", LINK) == (
        f"<b>Copo Térmico 🥤</b>\n\n🔗 <b>Link do Produto:</b>\n{LINK}\n\n<i>#CasaEDecoracao</i>")
    assert legendas.legenda_da_ia("Copo Térmico 🥤", LINK) == (
        f"<b>Copo Térmico 🥤</b>\n\n🔗 <b>Link do Produto:</b>\n{LINK}")
    assert legendas.legenda_so_link(LINK) == f"🔗 <b>Link do Produto:</b>\n{LINK}"


def test_nome_com_e_comercial_nao_quebra_o_html():
    legenda = legendas.legenda_da_ia("Copo & Garrafa <2L> 🥤\n#CasaEDecoracao", LINK)
    assert "<b>Copo &amp; Garrafa &lt;2L&gt; 🥤</b>" in legenda
    # Quem lê a legenda de volta recebe o nome como a IA escreveu.
    assert legendas.nome_da_legenda(legenda) == "Copo & Garrafa <2L> 🥤"


def test_nome_generico_sem_ia_conta_como_sem_nome():
    assert legendas.legenda_sem_nome(LINK) == (
        f"<b>Vídeo do Produto</b> 🛍️\n\n🔗 <b>Link do Produto:</b>\n{LINK}")
    assert legendas.nome_da_legenda(legendas.legenda_sem_nome(LINK)) == ""
    assert legendas.nome_da_legenda(legendas.legenda_so_link(LINK)) == "Link do Produto:"
    assert legendas.nome_da_legenda("sem negrito") == ""
    assert legendas.nome_da_legenda(None) == ""


def test_prompt_pede_o_emoji_no_fim_e_traz_todas_as_hashtags():
    prompt = legendas.PROMPT_NOME_E_HASHTAGS
    assert "emoji correspondente no final (Exemplo: Tênis Casual Feminino 👟)" in prompt
    assert ", ".join(legendas.HASHTAGS) in prompt
    assert len(legendas.HASHTAGS) == len(set(legendas.HASHTAGS)) == 30
    # Nos Autorais, o emoji no início; o resto do pedido é o mesmo.
    autorais = legendas.prompt_nome_e_hashtags(emoji_no_inicio=True)
    assert "emoji correspondente no início (Exemplo: 👟 Tênis Casual Feminino)" in autorais
    assert autorais.replace("no início (Exemplo: 👟 Tênis Casual Feminino)",
                            "no final (Exemplo: Tênis Casual Feminino 👟)") == prompt


def test_os_robos_pedem_a_ia_pelo_modulo(monkeypatch):
    import espelhador_videos_autorais as autorais
    pedidos = []

    async def analisar(caminho, prompt):
        pedidos.append(prompt)
        return "Copo 🥤\n#CasaEDecoracao"

    monkeypatch.setattr(mu, "analisar_video_gemini", analisar)
    monkeypatch.setattr(autorais, "analisar_video_gemini", analisar)
    rodar(mu.gerar_legenda_com_ia_espelhador("video.mp4"))
    rodar(autorais.gerar_legenda_autoral("video.mp4"))
    assert pedidos == [legendas.PROMPT_NOME_E_HASHTAGS, legendas.prompt_nome_e_hashtags(emoji_no_inicio=True)]

    fonte = open(os.path.join(PASTA, "bot_mestre.py"), encoding="utf-8").read()
    assert fonte.count("= legendas.PROMPT_NOME_E_HASHTAGS") == 2   # Parceiros e Espião


def test_espelhador_monta_a_legenda_do_disparo_pelo_modulo(monkeypatch):
    monkeypatch.setattr(mu, "consultar_cache_ia", lambda chave: "Copo & Tampa 🥤\n#CasaEDecoracao")
    texto = rodar(mu.montar_legenda_no_disparo("video.mp4", -100123, 7, {"link_convertido": LINK}))
    assert texto == legendas.legenda_da_ia("Copo & Tampa 🥤\n#CasaEDecoracao", LINK)


def test_nenhum_arquivo_tem_a_propria_copia_do_prompt_ou_da_legenda():
    # Uma cópia nova faria uma categoria ou o formato mudar num canal e não nos outros.
    copias = []
    for arquivo in glob.glob(os.path.join(PASTA, "*.py")):
        if os.path.basename(arquivo) == "legendas.py":
            continue
        texto = open(arquivo, encoding="utf-8").read()
        for receita in ("#JogosEConsoles", "produto demonstrado", "linhas_ia"):
            if receita in texto:
                copias.append((os.path.basename(arquivo), receita))
    assert copias == []
