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


def test_hashtags_lidas_de_volta_da_legenda():
    autoral = "📦 Item: Copo 🥤\n\n" + legendas.legenda_da_ia("Copo 🥤\n#CasaEDecoracao #Saude", LINK)
    assert legendas.hashtags_da_legenda(autoral) == "#CasaEDecoracao #Saude"
    assert legendas.hashtags_da_legenda(legendas.legenda_da_ia("Copo & Cia 🥤\n#Beleza", LINK)) == "#Beleza"
    for sem in (legendas.legenda_sem_nome(LINK), legendas.legenda_so_link(LINK), "", None, "<i>Oferta</i>"):
        assert legendas.hashtags_da_legenda(sem) == "", sem


def test_repost_dos_autorais_no_publico_leva_as_hashtags_do_video(bm):
    autoral = "📦 Item: Kit Soul Care 🧴\n\n" + legendas.legenda_da_ia("Kit Soul Care 🧴\n#Beleza #Saude", LINK)
    legenda = bm.legenda_repost_publico("@Rafaelnm", "Kit Soul Care 🧴", LINK, autoral)
    assert legenda == (f"👤 Vídeo enviado por: @Rafaelnm\n\n<b>Kit Soul Care 🧴</b>\n\n"
                       f"🔶 <b>SHOPEE</b> 🔶\n🔗 Link do Produto:\n{LINK}\n\n<i>#Beleza #Saude</i>")
    sem = bm.legenda_repost_publico("@Rafaelnm", "Kit", LINK, legendas.legenda_sem_nome(LINK))
    assert sem.endswith(LINK) and "#" not in sem
    assert "#Recomendado" not in open(os.path.join(PASTA, "bot_mestre.py"), encoding="utf-8").read()


def test_padrao_do_grupo_publico_tem_credito_nome_um_bloco_por_plataforma_e_hashtags():
    # O padrão que o Rafael mostrou em 16/10 (os posts da Ana, da Mariana): quem postou,
    # o nome, "SHOPEE" e "TIKTOK" com o link de cada um, e as hashtags.
    tiktok = "https://vm.tiktok.com/ZMabc123/"
    assert legendas.legenda_grupo_publico("@ana", "Copo & Cia 🥤", LINK, tiktok, "#CasaEDecoracao") == (
        "👤 Vídeo enviado por: @ana\n\n<b>Copo &amp; Cia 🥤</b>\n\n"
        f"🔶 <b>SHOPEE</b> 🔶\n🔗 Link do Produto:\n{LINK}\n\n"
        f"⬛ <b>TIKTOK</b> ⬛\n🔗 Link do Produto:\n{tiktok}\n\n<i>#CasaEDecoracao</i>")
    # Só TikTok, sem crédito e sem hashtags: as partes que faltam não aparecem.
    assert legendas.legenda_grupo_publico("", "Copo 🥤", link_tiktok=tiktok) == (
        f"<b>Copo 🥤</b>\n\n⬛ <b>TIKTOK</b> ⬛\n🔗 Link do Produto:\n{tiktok}")


def test_padrao_do_canal_afiliados_como_os_posts_do_canal():
    # O padrão que o Rafael mostrou em vídeo em 28/10 (P64): o título numa linha, a linha
    # divisória, o bloco da Shopee Vídeo com o link do vídeo, o texto de apoio e os links numerados.
    video, links = "https://sv.shopee.com.br/share-video/abc", ["https://s.shopee.com.br/1", "https://s.shopee.com.br/2"]
    assert legendas.legenda_do_canal("Vídeo 120\n📦 Item: Copo & Tampa", shopee=(video, links)) == (
        "<b>Vídeo 120 | 📦 Item: Copo &amp; Tampa</b>\n\n━━━━━━━━━━━━━━━\n\n"
        f"🔶 <b>SHOPEE VÍDEO</b> 🔶\n\n🎬 Link do Vídeo:\n{video}\n" + legendas.APOIO_LONGO
        + f"🔗 Links dos Produtos:\n👉 1º: {links[0]}\n👉 2º: {links[1]}\n\n")
    # O "&" do link copiado do post não quebra o HTML.
    assert "share-video/abc?a=1&amp;b=2\n" in legendas.legenda_do_canal("Vídeo 1", shopee=(video + "?a=1&b=2", []))
    # As duas plataformas, a Shopee em cima, separadas pela linha.
    tiktok = ("https://vm.tiktok.com/ZMabc123/", [])
    duas = legendas.legenda_do_canal("Vídeo 120\n📦 Item: Copo", shopee=(video, links), tiktok=tiktok)
    assert duas.index("SHOPEE VÍDEO") < duas.index("━━━━━━━━━━━━━━━\n\n⬛ <b>TIKTOK</b> ⬛") < duas.index(tiktok[0])


def test_legenda_do_canal_encurta_o_apoio_ate_caber_no_telegram():
    video, tiktok = "https://sv.shopee.com.br/share-video/abc", "https://vm.tiktok.com/ZMabc123/"

    def com(n, tamanho=100, duas=False):
        links = ["https://s.shopee.com.br/" + "x" * tamanho] * n
        return legendas.legenda_do_canal_que_cabe("Vídeo 1\n📦 Item: Copo", shopee=(video, links),
                                                  tiktok=(tiktok, links) if duas else None)
    longa, coube = com(1)
    assert legendas.APOIO_LONGO in longa and coube
    curta, coube = com(6)
    assert legendas.APOIO_CURTO in curta and legendas.APOIO_LONGO not in curta and coube
    # Com as duas plataformas, o texto de apoio vai uma vez só, no fim.
    rodape, coube = com(2, tamanho=140, duas=True)
    assert rodape.endswith(legendas.APOIO_RODAPE) and rodape.count("Grupo 100% gratuito") == 1 and coube
    assert len(rodape) <= legendas.LIMITE_DA_LEGENDA
    assert com(7)[1] is False


def test_titulo_do_item_pela_ia_e_sem_ela_pelo_nome_do_produto():
    assert legendas.titulo_do_item("Vídeo 99\n📦 Item: Copo Térmico", 7) == "Vídeo 7\n📦 Item: Copo Térmico"
    comprido = "Copo Térmico Inox Com Tampa E Canudo 500ml Para Café Chá Água Gelada Quente"
    item = legendas.titulo_do_item("", 7, comprido).split("Item: ")[1]
    assert len(item) <= legendas.TAMANHO_DO_ITEM and comprido.startswith(item) and comprido[len(item)] == " "
    assert legendas.titulo_do_item(None, 7) == f"Vídeo 7\n📦 Item: {legendas.NOME_SEM_IA}"
    assert "Vídeo 7" in legendas.prompt_do_item(7) and "📦 Item: " in legendas.prompt_do_item(7)


def test_prompt_pede_o_emoji_no_fim_e_traz_todas_as_hashtags():
    prompt = legendas.PROMPT_NOME_E_HASHTAGS
    assert "emoji correspondente no final (Exemplo: Tênis Casual Feminino 👟)" in prompt
    assert ", ".join(legendas.HASHTAGS) in prompt
    assert len(legendas.HASHTAGS) == len(set(legendas.HASHTAGS)) == 30


def test_os_robos_pedem_a_ia_com_o_mesmo_prompt(monkeypatch):
    import espelhador_videos_autorais as autorais
    pedidos = []

    async def analisar(caminho, prompt):
        pedidos.append(prompt)
        return "Copo 🥤\n#CasaEDecoracao"

    monkeypatch.setattr(mu, "analisar_video_gemini", analisar)
    monkeypatch.setattr(autorais, "analisar_video_gemini", analisar)
    rodar(mu.gerar_legenda_com_ia_espelhador("video.mp4"))
    rodar(autorais.gerar_legenda_autoral("video.mp4"))
    # Autorais inclusive: o emoji vai no fim do nome em todos os robôs.
    assert pedidos == [legendas.PROMPT_NOME_E_HASHTAGS] * 2

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
        for receita in ("#JogosEConsoles", "produto demonstrado", "linhas_ia", "🔶 <b>SHOPEE</b> 🔶",
                        "🔶 <b>SHOPEE VÍDEO</b> 🔶", "100% gratuito", "identificar o produto ou kit principal"):
            if receita in texto:
                copias.append((os.path.basename(arquivo), receita))
    assert copias == []
