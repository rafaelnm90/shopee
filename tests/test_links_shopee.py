"""links_shopee: achar link da Shopee do mesmo jeito em todos os robôs, num lugar só."""
import glob
import os
import re
from types import SimpleNamespace

import links_shopee as ls

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_primeiro_link_completa_o_https_e_tira_a_pontuacao_grudada():
    assert ls.primeiro_link("olha s.shopee.com.br/AbC1).") == "https://s.shopee.com.br/AbC1"
    assert ls.primeiro_link("HTTPS://SHP.EE/xyz, e mais") == "HTTPS://SHP.EE/xyz"
    assert ls.primeiro_link("link: https://br.shp.ee/k9!") == "https://br.shp.ee/k9"
    assert ls.primeiro_link('<a href="x">https://shope.ee/a1</a>') == "https://shope.ee/a1"   # para no "<" do HTML
    for sem_link in ("", None, "https://shopee.com.br/produto-i.1.2", "https://tiktok.com/x"):
        assert ls.primeiro_link(sem_link) is None, sem_link


def test_link_do_site_so_quando_pedido():
    produto = "https://shopee.com.br/Mochila-i.123.456"
    assert ls.primeiro_link(f"cole {produto}", ls.PADRAO_LINK_SHOPEE) == produto
    assert ls.primeiro_link("s.shopee.com.br/z", ls.PADRAO_LINK_SHOPEE) == "https://s.shopee.com.br/z"


def test_extrai_do_texto_visivel_ou_do_hiperlink():
    no_texto = SimpleNamespace(raw_text="Compre: s.shopee.com.br/AbC", entities=None)
    assert ls.extrair_link_shopee(no_texto) == "https://s.shopee.com.br/AbC"
    escondido = SimpleNamespace(raw_text="Compre aqui", entities=[
        SimpleNamespace(url=None), SimpleNamespace(url="https://google.com"),
        SimpleNamespace(url="https://s.shopee.com.br/Esc0ndido")])
    assert ls.extrair_link_shopee(escondido) == "https://s.shopee.com.br/Esc0ndido"
    assert ls.extrair_link_shopee(SimpleNamespace(raw_text=None, entities=None)) is None


def test_codigo_do_link_curto_em_minusculas():
    assert ls.codigo_do_link_curto("https://S.SHOPEE.COM.BR/AbC1?x=1") == "abc1"
    assert ls.codigo_do_link_curto("https://br.shp.ee/Zz9") == "zz9"
    assert ls.codigo_do_link_curto("https://shopee.com.br/produto") is None


def test_os_robos_usam_o_modulo_e_nao_uma_copia():
    import downloader_bot
    import espelhador_videos_autorais as autorais
    import motor_userbot
    assert motor_userbot.extrair_link_shopee is ls.extrair_link_shopee
    assert autorais.extrair_link_shopee is ls.extrair_link_shopee
    assert autorais.chave_produto("https://s.shopee.com.br/AbC1") == "curto_abc1"
    assert autorais.chave_produto("https://shopee.com.br/x-i.12.34") == "prod_12_34"
    assert downloader_bot.detectar_plataforma("baixa s.shopee.com.br/AbC).") == ("Shopee", "https://s.shopee.com.br/AbC")


def test_nenhum_arquivo_tem_a_propria_receita_de_link_da_shopee():
    # Uma cópia nova do padrão faria um conserto valer para um robô e não para outro.
    copias = []
    for arquivo in glob.glob(os.path.join(PASTA, "*.py")):
        if os.path.basename(arquivo) == "links_shopee.py":
            continue
        texto = open(arquivo, encoding="utf-8").read()
        if re.search(r"s\\\.shopee\\\.com\\\.br|shp\\\.ee|^def extrair_link_shopee", texto, re.MULTILINE):
            copias.append(os.path.basename(arquivo))
    assert copias == []
