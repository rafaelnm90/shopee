#!/usr/bin/env python3
"""
🔎 SONDA DO CDN DE VIDEO DA SHOPEE
Descobre se existe uma renderizacao SEM marca do mesmo video.

NAO altera nada no bot. NAO baixa o video inteiro na etapa de teste
(usa pedidos de 1 byte so para ler o tamanho do arquivo).

Uso:  python3 probe_shopee.py "https://br.shp.ee/xxxxx"

So usa biblioteca padrao: nao precisa do venv.
"""
import sys
import re
import os
import json
import urllib.request
import urllib.parse
import urllib.error

NAVEGADOR = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
}
PASTA_SAIDA = "variantes"


def abrir(url, metodo="GET", extra=None):
    cabecalhos = dict(NAVEGADOR)
    if extra:
        cabecalhos.update(extra)
    pedido = urllib.request.Request(url, headers=cabecalhos, method=metodo)
    return urllib.request.urlopen(pedido, timeout=25)


def baixar_html(url):
    """Segue o redirecionamento do br.shp.ee ate a pagina real do video."""
    with abrir(url) as r:
        html = r.read().decode("utf-8", errors="ignore")
        url_final = r.geturl()

    if "universal-link" in url_final and "redir=" in url_final:
        destino = urllib.parse.parse_qs(
            urllib.parse.urlparse(url_final).query).get("redir", [None])[0]
        if destino:
            destino = urllib.parse.unquote(destino)
            print(f"redirecionou para : {destino[:130]}")
            with abrir(destino) as r2:
                html = r2.read().decode("utf-8", errors="ignore")
                url_final = r2.geturl()
    return html, url_final


def etapa_1_mediainfo(html):
    print("\n" + "=" * 60)
    print("ETAPA 1 - mediaInfo completo da pagina")
    print("=" * 60)

    achado = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not achado:
        print("  __NEXT_DATA__ nao encontrado.")
        return None
    try:
        dados = json.loads(achado.group(1))
    except Exception as e:
        print(f"  __NEXT_DATA__ nao decodificou: {e}")
        return None

    info = dados.get("props", {}).get("pageProps", {}).get("mediaInfo")
    if info is None:
        print("  mediaInfo ausente. Chaves de pageProps:")
        print("   ", list(dados.get("props", {}).get("pageProps", {}).keys()))
        return None

    texto = json.dumps(info, indent=2, ensure_ascii=False)
    if len(texto) > 6000:
        texto = texto[:6000] + "\n  ... (cortado)"
    print(texto)
    return info


def montar_variantes(url):
    """A URL termina em <arquivo>.<idVideo>.<perfil>.mp4
    O <perfil> define a renderizacao. Testamos outros valores."""
    base, arquivo = url.rsplit("/", 1)
    partes = arquivo.split(".")
    variantes = []

    def somar(nome, motivo):
        alvo = f"{base}/{nome}"
        if alvo != url and all(alvo != v for v, _ in variantes):
            variantes.append((alvo, motivo))

    if len(partes) >= 4 and partes[-1] == "mp4":
        prefixo = ".".join(partes[:-3])
        id_video = partes[-3]
        perfil = partes[-2]

        somar(f"{prefixo}.{id_video}.mp4", "sem o campo de perfil")
        somar(f"{prefixo}.mp4", "so o nome do arquivo")

        candidatos = ["9744", "9746", "9747", "9749", "9750", "9640", "9600",
                      "9000", "1080", "720", "480", "0", "1", "2", "3", "16000000"]
        if perfil.isdigit():
            n = int(perfil)
            candidatos += [str(n - 1), str(n + 1), str(n - 4), str(n + 4)]
        for c in candidatos:
            if c != perfil:
                somar(f"{prefixo}.{id_video}.{c}.mp4", f"perfil {c}")

    # Caminhos alternativos no mesmo CDN
    for de, para in [("/mms/", "/raw/"), ("/mms/", "/origin/"), ("/api/v4/", "/api/v2/")]:
        if de in url:
            alvo = url.replace(de, para)
            if all(alvo != v for v, _ in variantes):
                variantes.append((alvo, f"caminho {para}"))

    return variantes


def medir(url):
    """Devolve (status, tamanho). Pede 1 byte so, para nao baixar o video."""
    try:
        with abrir(url, "GET", {"Range": "bytes=0-0"}) as r:
            faixa = r.headers.get("Content-Range", "")
            if "/" in faixa:
                return r.status, int(faixa.split("/")[-1])
            return r.status, int(r.headers.get("Content-Length") or 0)
    except urllib.error.HTTPError as e:
        return e.code, 0
    except Exception as e:
        return f"erro({type(e).__name__})", 0


def humano(n):
    return f"{n/1048576:.2f} MB" if n else "-"


def principal(url_entrada):
    html, url_final = baixar_html(url_entrada)
    print(f"pagina final ....: {url_final[:130]}")
    print(f"tamanho do html .: {len(html)}")

    etapa_1_mediainfo(html)

    brutas = []
    for u in re.findall(r'https?:[^"\'\\\s<>]+\.mp4[^"\'\\\s<>]*', html):
        u = u.replace("\\u002F", "/").replace("\\/", "/")
        if u not in brutas:
            brutas.append(u)

    if not brutas:
        print("\nNenhuma URL .mp4 na pagina. Nada a sondar.")
        return

    original = brutas[0]
    print("\n" + "=" * 60)
    print("ETAPA 2 - sondando variantes do CDN")
    print("=" * 60)
    print(f"origem: {original}\n")

    status, tamanho_base = medir(original)
    print(f"  {'ORIGINAL':<24} {str(status):<8} {humano(tamanho_base)}")

    diferentes = []
    for alvo, motivo in montar_variantes(original):
        status, tamanho = medir(alvo)
        marca = ""
        if status == 206 or status == 200:
            if tamanho and tamanho != tamanho_base:
                marca = "  <<< TAMANHO DIFERENTE"
                diferentes.append((motivo, alvo, tamanho))
            else:
                marca = "  (igual ao original)"
        print(f"  {motivo:<24} {str(status):<8} {humano(tamanho)}{marca}")

    print("\n" + "=" * 60)
    print("ETAPA 3 - baixando as diferentes")
    print("=" * 60)
    if not diferentes:
        print("  Nenhuma variante diferente. A Shopee so publica esta renderizacao.")
        return

    os.makedirs(PASTA_SAIDA, exist_ok=True)
    for motivo, alvo, tamanho in diferentes:
        nome = re.sub(r"[^a-zA-Z0-9]+", "_", motivo).strip("_") + ".mp4"
        caminho = os.path.join(PASTA_SAIDA, nome)
        try:
            with abrir(alvo) as r, open(caminho, "wb") as f:
                f.write(r.read())
            print(f"  salvo: {caminho}  ({humano(os.path.getsize(caminho))})")
        except Exception as e:
            print(f"  falhou {motivo}: {e}")

    print(f"\nVeja os arquivos em ./{PASTA_SAIDA}/ e confira se algum veio sem marca.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Uso: python3 probe_shopee.py "https://br.shp.ee/xxxxx"')
        sys.exit(1)
    principal(sys.argv[1])
