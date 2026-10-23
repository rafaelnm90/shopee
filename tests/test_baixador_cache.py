"""downloader_bot: a chave do cache de vídeos entregues reconhece o mesmo vídeo e separa vídeos diferentes."""

import downloader_bot as dl

UNIVERSAL = ("https://shopee.com.br/universal-link?redir=https%3A%2F%2Fsv.shopee.com.br%2Fshare-video%2F{id}"
             "%3D%3D%3FfromSource%3Dcopy_link&fromShareLink=share-marker&contentType=0&jumpType=share")


def test_universal_link_de_videos_diferentes_nao_divide_o_cache():
    # Vídeo do Rafael (23/10): todo universal-link caía no mesmo vídeo do cache, porque a
    # chave tirava tudo depois do "?", e o vídeo está no redir.
    copos, cambio = UNIVERSAL.format(id="AAAAcopos"), UNIVERSAL.format(id="BBBBcambio")
    assert dl.chave_cache_video(copos) != dl.chave_cache_video(cambio)


def test_mesmo_video_com_rastreadores_diferentes_tem_a_mesma_chave():
    a = UNIVERSAL.format(id="AAAAcopos")
    b = a.replace("fromSource%3Dcopy_link", "fromSource%3Dwhatsapp").replace("jumpType=share", "jumpType=x")
    assert dl.chave_cache_video(a) == dl.chave_cache_video(b)
    assert (dl.chave_cache_video("https://br.shp.ee/5abc?fromSource=copy_link&smtt=0.0.9")
            == dl.chave_cache_video("https://br.shp.ee/5abc"))
    assert dl.chave_cache_video("https://br.shp.ee/5abc") != dl.chave_cache_video("https://br.shp.ee/6xyz")
