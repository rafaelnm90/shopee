#!/usr/bin/env python3
"""
🔎 DIAGNÓSTICO DA PÁGINA DA SHOPEE
Mostra o que a página realmente devolve, para descobrir por que a matriz
não é encontrada. Não altera nada e não baixa vídeo.

Uso:  python3 diag_shopee.py "https://br.shp.ee/xxxxx"
"""
import sys
import re
import json
import asyncio
import urllib.parse

import aiohttp

CABECALHO = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
}


async def principal(url):
    async with aiohttp.ClientSession(headers=CABECALHO) as sessao:
        async with sessao.get(url, allow_redirects=True, timeout=25) as r:
            print(f"status inicial ......: {r.status}")
            html = await r.text()
            url_final = str(r.url)
        print(f"url final ...........: {url_final[:140]}")

        if "universal-link" in url_final and "redir=" in url_final:
            destino = urllib.parse.parse_qs(
                urllib.parse.urlparse(url_final).query).get("redir", [None])[0]
            if destino:
                destino = urllib.parse.unquote(destino)
                print(f"redir oculto ........: {destino[:140]}")
                async with sessao.get(destino, allow_redirects=True, timeout=25) as r2:
                    print(f"status do redir .....: {r2.status}")
                    if r2.status == 200:
                        html = await r2.text()
                        url_final = str(r2.url)

    print(f"tamanho do html .....: {len(html)} caracteres")
    print(f"tem __INITIAL_STATE__: {'SIM' if '__INITIAL_STATE__' in html else 'NAO'}")
    print(f"tem __NEXT_DATA__ ...: {'SIM' if '__NEXT_DATA__' in html else 'NAO'}")
    print(f"tem a palavra .mp4 ..: {html.lower().count('.mp4')} ocorrencia(s)")
    print(f"tem 'watermark' .....: {html.lower().count('watermark')} ocorrencia(s)")

    print("\n--- URLs .mp4 encontradas no HTML bruto ---")
    brutas = re.findall(r'https?:[^"\'\\\s<>]+\.mp4[^"\'\\\s<>]*', html)
    vistas = []
    for u in brutas:
        u = u.replace("\\u002F", "/").replace("\\/", "/")
        if u not in vistas:
            vistas.append(u)
    if vistas:
        for u in vistas[:15]:
            marca = "  [COM MARCA]" if "watermark" in u.lower() else "  [limpa?]"
            print(f"{marca} {u[:150]}")
    else:
        print("  (nenhuma)")

    print("\n--- Chaves de video vistas no HTML ---")
    chaves = re.findall(
        r'"(defaultVideoUrl|playUrl|play_url|videoUrl|video_url|playAddr|play_addr|downloadUrl|download_url)"\s*:\s*"([^"]{0,200})"',
        html)
    if chaves:
        for k, v in chaves[:15]:
            v = v.replace("\\u002F", "/").replace("\\/", "/")
            print(f"  {k} = {v[:140]}")
    else:
        print("  (nenhuma)")

    achado = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});\s*</script>', html, re.DOTALL)
    if achado:
        try:
            estado = json.loads(achado.group(1))
            print(f"\n--- __INITIAL_STATE__ decodificado, chaves de topo ---")
            print(" ", list(estado.keys())[:25])
        except Exception as e:
            print(f"\n__INITIAL_STATE__ existe mas nao decodifica: {e}")

    # Guarda o HTML para inspecao manual se nada acima ajudar.
    with open("pagina_shopee.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("\nHTML completo salvo em: pagina_shopee.html")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 diag_shopee.py \"https://br.shp.ee/xxxxx\"")
        sys.exit(1)
    asyncio.run(principal(sys.argv[1]))
