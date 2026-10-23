"""investigar_baixador: descreve a página da Shopee Vídeo só pela forma, sem endereços, nomes ou textos."""
import json

import investigar_baixador as ib
from conftest import inserir


def test_descreve_onde_ha_video_sem_mostrar_endereco_nem_id():
    dados = {"props": {"pageProps": {"videoInfo": {"watermarkVideoUrl": "https://cdn.exemplo/abc.123.mp4",
                                                   "titulo": "Copos de Vidro"},
                                     "123456789": {"url": "https://cdn.exemplo/x.m3u8"},
                                     "recomendados": [{"video_url": "https://cdn.exemplo/y.mp4"}]}}}
    html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(dados)}</script></html>'
    texto = "\n".join(ib.descrever_pagina(html))
    assert "$.props.pageProps.videoInfo.watermarkVideoUrl (mp4)" in texto
    assert "$.props.pageProps.#.url (m3u8)" in texto
    assert "$.props.pageProps.recomendados[0].video_url (mp4)" in texto
    assert "__NEXT_DATA__" in texto and "3 endereço(s) de vídeo" in texto
    assert "cdn.exemplo" not in texto and "Copos" not in texto and "123456789" not in texto


def test_pagina_sem_json_e_endereco_so_com_a_forma():
    assert "nenhum JSON embutido" in "\n".join(ib.descrever_pagina("<html>nada</html>"))
    forma = ib.forma_do_endereco("https://sv.shopee.com.br/share-video/XCA3abcdefghijk==?fromSource=copy_link")
    assert forma == "sv.shopee.com.br/share-video/…" and "fromSource" not in forma


def test_codigo_invalido_nao_roda():
    assert ib.main(["abc; rm -rf /"]) == 2


def test_pagina_sem_video_lista_as_chaves_e_as_apis_dos_scripts():
    dados = {"props": {"pageProps": {"shareId": "XCA3abc", "lang": "pt"}}, "page": "/share-video/[id]"}
    html = (f'<html><script id="__NEXT_DATA__">{json.dumps(dados)}</script>'
            '<script src="/_next/static/chunks/pages/app-1a2b.js"></script></html>')
    assert not ib.tem_video(html)
    texto = "\n".join(ib.descrever_pagina(html))
    assert "$.props.pageProps.shareId (texto de 7)" in texto and "XCA3abc" not in texto
    assert ib.scripts_da_pagina(html, "https://sv.shopee.com.br/share-video/x") == [
        "https://sv.shopee.com.br/_next/static/chunks/pages/app-1a2b.js"]
    codigo = 'fetch("/api/v4/video/get_share_info");x="https://sv.shopee.com.br/api/v1/feed";y="nada"'
    assert ib.apis_no_script(codigo) == {"/api/v4/video/get_share_info", "https://sv.shopee.com.br/api/v1/feed"}


def test_trechos_da_api_mostram_o_codigo_em_volta():
    codigo = "a" * 400 + 'fetch("/api/v2/timeline/single",{post_id:e})' + "b" * 400
    trechos = ib.trechos_da_api(codigo, "/api/v2/timeline/single")
    assert len(trechos) == 1 and "post_id" in trechos[0] and len(trechos[0]) <= 2 * ib.TRECHO + 30


def test_link_curto_e_forma_do_universal_link_com_o_redir():
    assert ib.main(["curto:abc; rm"]) == 2
    universal = ("https://shopee.com.br/universal-link?redir=https%3A%2F%2Fsv.shopee.com.br%2Fshare-video%2F"
                 "XCA3abcdefghijk%3D%3D&fromShareLink=1")
    forma = ib.forma_do_endereco(universal)
    assert forma == "shopee.com.br/… (redir: sv.shopee.com.br/share-video/…)"


def test_ultimo_usa_o_link_guardado_no_banco_sem_imprimir(monkeypatch, capsys):
    # A conferência semanal do Claude (pedido do Rafael em 23/10): o último vídeo pedido ao
    # Baixador, lido no servidor; o log do Actions é público e o link nunca aparece.
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    assert ib.main(["ultimo"]) == 0
    assert "nenhum vídeo da Shopee Vídeo pedido" in capsys.readouterr().out
    link = "https://shopee.com.br/universal-link?redir=https%3A%2F%2Fsv.shopee.com.br%2Fshare-video%2FXCA3abc%3D%3D"
    ib.dl.db.salvar_config(ib.dl.CHAVE_CONFERENCIA, {"ultimo_link": link})
    chamadas = []

    async def investigar(id_video="", curto=False, url=None):
        chamadas.append(url)

    monkeypatch.setattr(ib, "investigar", investigar)
    assert ib.main(["ultimo"]) == 0
    assert chamadas == [link] and "XCA3abc" not in capsys.readouterr().out
    # O código do vídeo sai do redir para a conferência da API.
    assert ib.id_do_video(link) == "XCA3abc=="
    assert ib.id_do_video("https://br.shp.ee/abc") == ""
