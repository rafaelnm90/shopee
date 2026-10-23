"""investigar_baixador: descreve a página da Shopee Vídeo só pela forma, sem endereços, nomes ou textos."""
import json

import investigar_baixador as ib


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
