#!/usr/bin/env python3
"""
Os casos das falhas do robô da Shopee Vídeo, para o Claude fazer o checkup completo de
cada uma. Em toda tentativa que não dá certo, o robô guarda numa pasta do servidor o que
viu: o motivo inteiro e o passo, o vídeo em alguns quadros, o título e o comentário da IA,
os produtos do link e o que a IA conferiu, o print e a forma da tela do celular na hora, e
as últimas ações no celular antes da falha (cada toque, com a tela de antes e em que ele caiu).

O repositório e os logs do Actions são públicos: o workflow casos_robo.yml leva os casos
cifrados ao ramo casos-robo (só abrem com a chave do registro_privado, que fica no
servidor, no privado do Rafael e no ambiente do Claude). Depois de analisado e resolvido,
o mesmo workflow apaga tudo, no servidor e no ramo. Nada se acumula: ficam no máximo
MAXIMO_DE_CASOS casos, por até DIAS_DOS_CASOS dias, mesmo sem ninguém apagar.
Pedido do Rafael: DECISOES.md, Shopee Vídeo.

Quem usa:
- robo_shopee_video: com_historico(d) no celular de cada rodada e guardar(...) em cada
  tentativa que não deu certo;
- postador_shopee_video: o passo caso do explorar guarda do mesmo jeito a tela do celular
  (o print e a forma), para o Claude ver a imagem de uma tela que está mapeando;
- casos_robo.yml: "casos_robo.py contar", "casos_robo.py cifrado" e "casos_robo.py apagar";
- Claude: "casos_robo.py ler ARQUIVO PASTA" abre no scratchpad o arquivo do ramo.

    python3 casos_robo.py contar | cifrado | apagar | ler ARQUIVO PASTA
"""
import io
import json
import logging
import os
import re
import shutil
import sys
import zipfile
from collections import deque
from datetime import datetime, timedelta
from xml.etree import ElementTree

from cryptography.fernet import Fernet, InvalidToken

import registro_processos
import videos
from fuso import fuso_horario

logger = logging.getLogger(__name__)

# Fora do repositório, na pasta de trabalho do robô (a mesma dos rascunhos).
PASTA = os.path.expanduser("~/shopee_video/casos")
RAMO = "casos-robo"
ARQUIVO = "casos.zip.cifrado"
MAXIMO_DE_CASOS = 30
DIAS_DOS_CASOS = 3
# O print vai menor (dá para ler a tela e não pesa no ramo) e o vídeo, em alguns quadros.
LARGURA_DO_PRINT = 540
QUADROS_DO_VIDEO = 4
LARGURA_DOS_QUADROS = 360
# Sem o começo do rascunho, o registro do caso volta até estes minutos antes dele.
MINUTOS_DO_REGISTRO = 30
# As últimas ações no celular que o caso guarda, cada uma com a tela lida logo antes dela
# (antes_N.xml): o print mostra só a tela da falha, e não o que levou a ela (o que o toque em
# Feito abriu, o aviso do Telegram que pegou um toque). Pedido do Rafael (30/10): o que
# dificulta achar a causa vira registro. DECISOES.md, Trabalho com o Claude.
ACOES_DO_CASO = 8


class CelularComHistorico:
    """
    O celular do uiautomator2 com as últimas ACOES_DO_CASO ações anotadas (toque, tecla e
    arrasto, com a última tela lida antes de cada uma); todo o resto passa direto para ele.
    Só anota: não toca, não espera e não lê a tela a mais.
    """

    def __init__(self, d):
        object.__setattr__(self, "_d", d)
        object.__setattr__(self, "_tela", "")
        object.__setattr__(self, "acoes", deque(maxlen=ACOES_DO_CASO))

    def __getattr__(self, nome):
        return getattr(self._d, nome)

    def __setattr__(self, nome, valor):
        setattr(self._d, nome, valor)

    def __call__(self, *args, **kwargs):
        return self._d(*args, **kwargs)

    def dump_hierarchy(self, *args, **kwargs):
        tela = self._d.dump_hierarchy(*args, **kwargs)
        object.__setattr__(self, "_tela", tela)
        return tela

    def _anotar(self, acao, ponto=None):
        self.acoes.append({"hora": datetime.now(fuso_horario).strftime("%H:%M:%S"), "acao": acao,
                           "ponto": ponto, "tela": self._tela})

    def click(self, x, y, *args, **kwargs):
        self._anotar(f"toque em ({x},{y})", (x, y))
        return self._d.click(x, y, *args, **kwargs)

    def press(self, tecla, *args, **kwargs):
        self._anotar(f"tecla {tecla}")
        return self._d.press(tecla, *args, **kwargs)

    def swipe(self, *args, **kwargs):
        self._anotar("arrasto " + " ".join(str(numero) for numero in args[:4]),
                     tuple(args[:2]) if len(args) >= 2 else None)
        return self._d.swipe(*args, **kwargs)


def com_historico(d):
    """O celular com as últimas ações anotadas para o caso (o mesmo, se ele já anota)."""
    return d if isinstance(d, CelularComHistorico) else CelularComHistorico(d)


def elemento_no_ponto(tela, x, y):
    """
    Em que o toque caiu: o menor elemento da tela que tem o ponto, com o app, o id, o texto e
    a descrição (no caso cifrado). "" quando a tela não abre ou nada tem o ponto.
    """
    try:
        raiz = ElementTree.fromstring(tela)
    except (ElementTree.ParseError, ValueError):
        return ""
    achado, menor = None, None
    for no in raiz.iter("node"):
        caixa = [int(n) for n in re.findall(r"\d+", no.get("bounds", ""))]
        if len(caixa) != 4:
            continue
        x1, y1, x2, y2 = caixa
        area = (x2 - x1) * (y2 - y1)
        if x1 <= x <= x2 and y1 <= y <= y2 and (menor is None or area <= menor):
            achado, menor = no, area
    if achado is None:
        return ""
    partes = [achado.get("package", "")]
    if achado.get("resource-id"):
        partes.append("id=" + achado.get("resource-id").rsplit("/", 1)[-1])
    if achado.get("text"):
        partes.append(f'"{achado.get("text")[:60]}"')
    if achado.get("content-desc"):
        partes.append(f'desc="{achado.get("content-desc")[:60]}"')
    return " ".join(parte for parte in partes if parte)


def _agora(agora=None):
    return agora or datetime.now(fuso_horario)


def registro_do_caso(desde, momento):
    """
    O que o robô da Shopee Vídeo anotou no registro dos processos desde o começo do rascunho
    ("AAAA-MM-DD HH:MM:SS"; sem ele, MINUTOS_DO_REGISTRO antes do caso) até o caso:
    [[HH:MM:SS, processo, resultado, detalhe]].
    """
    desde = desde or (momento - timedelta(minutes=MINUTOS_DO_REGISTRO)).strftime("%Y-%m-%d %H:%M:%S")
    ate = momento.strftime("%Y-%m-%d %H:%M:%S")
    return [[quando[11:19], processo, resultado, detalhe]
            for quando, processo, resultado, detalhe, _origem in registro_processos.sequencia("shopee_video", "", desde)
            if quando <= ate]


def casos():
    """As pastas dos casos guardados, da mais velha para a mais nova."""
    try:
        return sorted(nome for nome in os.listdir(PASTA) if os.path.isdir(os.path.join(PASTA, nome)))
    except FileNotFoundError:
        return []


def guardar(d, acao, resultado, motivo, passo="", video=None, rascunho=None, agora=None):
    """
    Guarda o caso de uma tentativa que não deu certo. d é o celular (None sem ele): o
    print e a tela saem dele, só lendo, sem tocar em nada. Nunca derruba a rodada: o que
    não der para guardar fica de fora. Devolve a pasta do caso, ou None.
    """
    try:
        momento = _agora(agora)
        os.makedirs(PASTA, exist_ok=True)
        pasta = os.path.join(PASTA, f"{momento:%Y%m%d-%H%M%S}-{acao}")
        while os.path.exists(pasta):
            pasta += "+"
        os.makedirs(pasta)
        video, rascunho = dict(video or {}), dict(rascunho or {})
        caso = {
            "momento": momento.strftime("%Y-%m-%d %H:%M:%S"), "acao": acao, "resultado": resultado,
            "passo": passo, "motivo": str(motivo or ""),
            "video": {chave: video.get(chave) for chave in ("id", "link", "nome", "produto", "de_video", "arquivo")
                      if video.get(chave) is not None},
            "rascunho": {chave: rascunho.get(chave) for chave in (
                "id", "id_video", "estado", "fonte", "link", "titulo", "comentario", "produtos", "conferencia",
                "rotulo_ia", "motivo", "criado_em", "postar_em") if rascunho.get(chave) is not None},
        }
        # Os passos que o robô anotou desde o começo do rascunho (textos fixos e números): a
        # ordem do que aconteceu antes da falha, como o produto curtido antes do anexar.
        caso["registro"] = registro_do_caso(rascunho.get("criado_em"), momento)
        if d is not None:
            caso["app"] = _tela_do_celular(d, pasta)
        if isinstance(d, CelularComHistorico):
            caso["antes_da_falha"] = _acoes_antes(d, pasta)
        arquivo = rascunho.get("arquivo") or video.get("arquivo")
        caso["quadros_do_video"] = (videos.quadros(arquivo, pasta, QUADROS_DO_VIDEO, LARGURA_DOS_QUADROS)
                                    if arquivo and os.path.exists(arquivo) else 0)
        with open(os.path.join(pasta, "caso.json"), "w", encoding="utf-8") as f:
            json.dump(caso, f, ensure_ascii=False, indent=1, default=str)
        faxina(agora)
        logger.info(f"🗂️ [Casos do robô] Caso guardado para o checkup ({acao} → {resultado}).")
        return pasta
    except Exception as e:
        logger.warning(f"⚠️ [Casos do robô] Não guardei o caso: {type(e).__name__}")
        return None


def _acoes_antes(d, pasta):
    """
    As últimas ações no celular antes da falha, da mais velha para a mais nova: a hora, a
    ação, em que o toque caiu e o arquivo com a tela lida logo antes (antes_N.xml).
    """
    lista = []
    for numero, acao in enumerate(list(d.acoes), 1):
        item = {"hora": acao["hora"], "acao": acao["acao"]}
        if acao["tela"]:
            nome = f"antes_{numero}.xml"
            with open(os.path.join(pasta, nome), "w", encoding="utf-8") as f:
                f.write(acao["tela"])
            item["tela"] = nome
            if acao["ponto"]:
                x, y = acao["ponto"]
                item["caiu_em"] = elemento_no_ponto(acao["tela"], x, y)
        lista.append(item)
    return lista


def _tela_do_celular(d, pasta):
    """O app e a tela de agora, o print (menor, em JPEG) e a forma da tela (o XML do uiautomator)."""
    app = {}
    try:
        atual = d.app_current() or {}
        app = {"pacote": atual.get("package"), "tela": atual.get("activity")}
    except Exception:
        pass
    try:
        with open(os.path.join(pasta, "tela.xml"), "w", encoding="utf-8") as f:
            f.write(d.dump_hierarchy())
    except Exception as e:
        app["sem_tela"] = type(e).__name__
    caminho = os.path.join(pasta, "tela.png")
    try:
        d.screenshot(caminho)
        _diminuir(caminho, os.path.join(pasta, "tela.jpg"), LARGURA_DO_PRINT)
    except Exception as e:
        app["sem_print"] = type(e).__name__
    return app


def _diminuir(origem, destino, largura):
    """A imagem menor, em JPEG; sem conseguir abrir (não é imagem), fica a de origem."""
    try:
        from PIL import Image
        with Image.open(origem) as imagem:
            imagem = imagem.convert("RGB")
            if imagem.width > largura:
                imagem = imagem.resize((largura, round(imagem.height * largura / imagem.width)))
            imagem.save(destino, "JPEG", quality=70)
        os.remove(origem)
    except Exception:
        pass


def faxina(agora=None):
    """Tira os casos com mais de DIAS_DOS_CASOS dias e os mais velhos além de MAXIMO_DE_CASOS."""
    limite = (_agora(agora) - timedelta(days=DIAS_DOS_CASOS)).strftime("%Y%m%d-%H%M%S")
    lista = casos()
    velhos = [nome for nome in lista if nome < limite]
    sobra = [nome for nome in lista if nome >= limite]
    velhos += sobra[:max(0, len(sobra) - MAXIMO_DE_CASOS)]
    for nome in velhos:
        shutil.rmtree(os.path.join(PASTA, nome), ignore_errors=True)
    return len(velhos)


def pacote():
    """Os casos num zip, em bytes."""
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as arquivo_zip:
        for nome in casos():
            for raiz, _, arquivos in os.walk(os.path.join(PASTA, nome)):
                for arquivo in arquivos:
                    caminho = os.path.join(raiz, arquivo)
                    arquivo_zip.write(caminho, os.path.relpath(caminho, PASTA))
    return memoria.getvalue()


def cifrado():
    """O pacote dos casos cifrado com a chave do servidor (a do registro_privado)."""
    import registro_privado   # aqui dentro: o robô não precisa dele para guardar os casos
    return Fernet(registro_privado.chave()).encrypt(pacote()).decode("ascii")


def apagar():
    """Apaga todos os casos do servidor. Devolve quantos eram."""
    quantos = len(casos())
    shutil.rmtree(PASTA, ignore_errors=True)
    return quantos


def abrir(texto_cifrado, valor_chave, destino):
    """Abre o arquivo do ramo numa pasta (no scratchpad do Claude, nunca no repositório). Devolve os casos."""
    dados = Fernet(valor_chave.strip().encode("ascii")).decrypt(texto_cifrado.strip().encode("ascii"))
    with zipfile.ZipFile(io.BytesIO(dados)) as arquivo_zip:
        arquivo_zip.extractall(destino)
    return sorted(nome for nome in os.listdir(destino) if os.path.isdir(os.path.join(destino, nome)))


def _ler(caminho, destino):
    import registro_privado
    valor = os.environ.get(registro_privado.VARIAVEL_CHAVE, "")
    if not valor:
        print(f"Falta a variável {registro_privado.VARIAVEL_CHAVE} no ambiente do Claude.")
        return 1
    with open(caminho, encoding="ascii") as arquivo:
        texto_cifrado = arquivo.read()
    try:
        nomes = abrir(texto_cifrado, valor, destino)
    except (InvalidToken, ValueError):
        print("A chave do ambiente não abre este arquivo: o servidor pode ter gerado outra (o bot manda a nova).")
        return 1
    print(f"{len(nomes)} caso(s) em {destino}:")
    for nome in nomes:
        print(f"   {nome}")
    return 0


def main(argumentos):
    if argumentos == ["contar"]:
        print(len(casos()))
    elif argumentos == ["cifrado"]:
        print(cifrado())
    elif argumentos == ["apagar"]:
        print(f"{apagar()} caso(s) apagado(s) do servidor.")
    elif len(argumentos) == 3 and argumentos[0] == "ler":
        return _ler(argumentos[1], argumentos[2])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
