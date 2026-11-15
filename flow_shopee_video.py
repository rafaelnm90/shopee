#!/usr/bin/env python3
"""
Vídeos feitos por IA no Google Flow, no celular do robô da Shopee Vídeo, com a conta Pro do
Rafael (P229 1, 15/11/2026). Por enquanto é só o teste que ele escolheu: 3 vídeos do mesmo
produto, um em cada modelo do Flow, que vão só ao privado dele, para ele escolher o modelo;
nada é postado. A IA vê a foto do anúncio e o nome do produto e escreve o pedido do vídeo (a
cena, o movimento da câmera e a luz), sempre com o produto igual ao da foto; o Flow gera o
vídeo a partir da foto.

O caminho no app (mapeado no Motorola em 15/11/2026, sem gerar nada; as telas estão no
roteiro_robo_shopee_video.md): o ícone "Flow" → o projeto do robô na lista (sem ele, Novo) →
Criar → Vídeo → + (Adicionar mídia) → Imagens → a foto no seletor do Android ("Item Foto ...")
→ Adicionar → a caixa "O que você quer fazer?" → o modelo (9:16, 720p, x1, 8 s e o modelo, com
o custo em créditos) → Gerar. Depois do Gerar, o teste guarda a tela de minuto em minuto
(casos_robo), para o caminho do vídeo pronto e do baixar ser mapeado no 1º vídeo.

Usado pelo workflow video_ia.yml (acao flow ou flow-sem-gerar). O log do Actions é público:
saem só estados, modelos e números; o produto e o pedido ficam no banco, e o vídeo, no privado.

    python3 flow_shopee_video.py teste              # o próximo vídeo do teste (um modelo por vez)
    python3 flow_shopee_video.py teste --sem-gerar  # tudo até o Gerar, sem tocar nele
"""
import asyncio
import io
import json
import logging
import os
import re
import sys
import time
from datetime import datetime

import api_gemini
import assistente_shopee_video as assistente
import casos_robo
import celular_robo
import db
import postador_shopee_video as ps
from fuso import fuso_horario

PACOTE = "com.google.android.apps.labs.whisk"
PACOTE_DO_SELETOR = "com.google.android.providers.media.module"
CHAVE = "flow_shopee_video"
PASTA = os.path.join(os.path.expanduser("~"), "shopee_video", "flow")
# Os modelos de vídeo do Flow na conta do Rafael e o custo de cada vídeo de 8 s em 720p,
# lidos no app em 15/11/2026. O teste vai do mais barato ao mais caro (46 créditos, dentro
# dos 50 grátis do dia): o 1º vídeo é o que mostra as telas depois do Gerar.
MODELOS_DO_TESTE = (("Veo 3.1 - Lite", 10), ("Omni 1.1 Flash", 12), ("Omni 1.2 Flash", 24))
# Quantos dos próximos vídeos da fonte o teste tenta até a IA achar a foto boa para o vídeo.
PRODUTOS_TENTADOS = 10
ESPERA_DA_TELA = 20
PAUSA_DA_LEITURA = 1.5
# Depois do Gerar, o teste olha a tela por este tempo e guarda um caso a cada intervalo.
ESPERA_DA_GERACAO = 6 * 60
INTERVALO_DOS_CASOS = 60
# O nome que o Flow dá ao projeto novo: o mês, o dia e a hora em que ele foi criado.
NOME_DE_PROJETO = re.compile(r"[a-zç]{3}\. \d{1,2}, \d{1,2}:\d{2} ?(?:AM|PM)", re.I)
CUSTO_NA_TELA = re.compile(r"(\d+)\s+créditos de IA", re.I)
# A tela de termos ou de consentimento: o robô nunca aceita nada pelo Rafael. Também o aviso do
# teclado (o do Google Tradutor, que abriu em 15/11 com um toque fora do lugar): OK e Cancelar
# num diálogo do teclado.
PALAVRAS_DE_TERMOS = ("termos de serviço", "aceitar", "concordo", "política de privacidade")
PACOTE_DO_TECLADO = "com.google.android.inputmethod.latin"
PEDIDO_DA_IA = (
    "Você é diretor de vídeos curtos de produto para a Shopee Vídeo, no Brasil. A imagem é a foto "
    "oficial do anúncio do produto \"{nome}\". O Google Flow vai gerar um vídeo de 8 segundos, em pé "
    "(9:16), a partir dessa foto. Responda só com um JSON, sem nada antes ou depois:\n"
    '{{"serve": true ou false, "motivo": "...", "prompt": "...", "cena": "..."}}\n'
    "- serve: false quando a foto não mostra o produto inteiro e com clareza (colagem de várias "
    "fotos, tabela de medidas, mais texto que produto, só a embalagem fechada) ou quando o produto "
    "é proibido nas diretrizes da Shopee Vídeo; motivo: o porquê, em poucas palavras.\n"
    "- prompt: em inglês, até 90 palavras, o pedido do vídeo: o mesmo produto da foto, idêntico "
    "(mesma forma, cor, material, tamanho, quantidade e detalhes; nada acrescentado, tirado ou "
    "trocado), num lugar real onde ele é usado no dia a dia do Brasil, com luz natural, um só "
    "movimento suave da câmera (aproximação lenta, giro em volta ou deslize) e, se fizer sentido, "
    "mãos usando o produto com naturalidade; fotorrealista; sem texto na tela, sem legenda, sem "
    "logotipo novo, sem outros produtos e sem rosto de pessoa em destaque.\n"
    "- cena: uma frase em português que descreve a cena, para o Rafael."
)


class Parada(Exception):
    """O teste parou num passo: a mensagem é um texto fixo do código (vai para o log público)."""


def agora():
    return datetime.now(fuso_horario).strftime("%Y-%m-%d %H:%M:%S")


def ler_resposta(texto):
    """
    {"serve", "motivo", "prompt", "cena"} da resposta da IA; None quando ela não veio num JSON
    ou disse que serve sem escrever o pedido.
    """
    achado = re.search(r"\{.*\}", texto or "", re.S)
    if not achado:
        return None
    try:
        dados = json.loads(achado.group(0))
    except ValueError:
        return None
    if not isinstance(dados, dict):
        return None
    serve = dados.get("serve") is True
    prompt = " ".join(str(dados.get("prompt") or "").split())
    if serve and not prompt:
        return None
    return {"serve": serve, "motivo": " ".join(str(dados.get("motivo") or "").split())[:200],
            "prompt": prompt[:1000], "cena": " ".join(str(dados.get("cena") or "").split())[:300]}


def jpeg_sem_metadados(dados):
    """
    A foto regravada em JPEG, sem os dados de câmera (EXIF): no seletor de fotos do Android, a
    mais nova é a 1ª pela hora em que entrou na galeria, e não por uma data antiga da foto.
    None quando os bytes não são uma imagem.
    """
    from PIL import Image
    try:
        with Image.open(io.BytesIO(dados)) as imagem:
            saida = io.BytesIO()
            imagem.convert("RGB").save(saida, "JPEG", quality=95)
            return saida.getvalue()
    except Exception:
        return None


def escolher_o_produto():
    """
    O produto do teste: o 1º dos próximos vídeos da fonte do painel com a foto do anúncio que a
    IA acha boa para o vídeo, com o pedido dela. {"link", "nome", "foto" (bytes), "prompt",
    "cena", "tentados"}; None sem nenhum.
    """
    fonte = (db.ler_config(ps.CHAVE_PAINEL, {}) or {}).get("fonte", assistente.FONTE_PADRAO)
    tentados = 0
    for _, _, link, _ in assistente.candidatos_nao_usados(fonte)[:PRODUTOS_TENTADOS]:
        if not link:
            continue
        tentados += 1
        anuncio = ps.anuncio_do_produto({"link": link})
        foto = jpeg_sem_metadados(anuncio["foto"]) if anuncio.get("foto") and anuncio.get("nome") else None
        if not foto:
            continue
        resposta = ler_resposta(asyncio.run(api_gemini.gerar_texto_gemini(
            PEDIDO_DA_IA.format(nome=anuncio["nome"]), imagens=[(foto, "image/jpeg")])))
        if resposta and resposta["serve"]:
            return {"link": link, "nome": anuncio["nome"], "foto": foto, "prompt": resposta["prompt"],
                    "cena": resposta["cena"], "tentados": tentados}
    return None


def teste_guardado():
    """O teste de agora (o produto, o pedido e os vídeos já gerados), do banco; {} sem nenhum."""
    teste = (db.ler_config(CHAVE, {}) or {}).get("teste") or {}
    return teste if teste.get("foto") and os.path.exists(teste["foto"]) else {}


def guardar(**campos):
    """Grava os campos na chave do Flow (o projeto do robô e o teste)."""
    db.atualizar_config(CHAVE, lambda dados: dados.update(campos))


def proximo_modelo(teste):
    """(nome, custo) do próximo modelo do teste, do mais barato ao mais caro; None com os 3 gerados."""
    gerados = (teste or {}).get("videos") or {}
    return next(((nome, custo) for nome, custo in MODELOS_DO_TESTE if nome not in gerados), None)


# --- As telas do Flow -----------------------------------------------------------------------

def _tela(d):
    try:
        return d.dump_hierarchy()
    except Exception:
        return ""


def esperar(d, condicao, espera=ESPERA_DA_TELA):
    """A tela (o xml) assim que a condição vale nela, esperando até `espera` s; "" se não veio."""
    fim = time.monotonic() + espera
    while True:
        xml = _tela(d)
        if xml and condicao(xml):
            return xml
        if time.monotonic() >= fim:
            return ""
        time.sleep(PAUSA_DA_LEITURA)


def tem_termos(xml):
    """A tela pede para aceitar termos ou dar consentimento (ou o teclado abriu um aviso)? O robô para."""
    for el in ps.elementos(xml):
        if any(palavra in f"{el['texto']} {el['descricao']}".casefold() for palavra in PALAVRAS_DE_TERMOS):
            return True
        if el["pacote"] == PACOTE_DO_TECLADO and el["texto"] in ("OK", "Cancelar"):
            return True
    return False


def ponto_parado(d, achar_ponto, passo, espera=ESPERA_DA_TELA):
    """
    O ponto (achar_ponto(xml)) quando ele para de se mexer: duas leituras seguidas no mesmo lugar.
    O pedido do Flow sobe com o teclado, e o toque no meio da subida cai em outro lugar (em 15/11,
    no Traduzir do teclado). Parada na tela de termos; None sem o ponto.
    """
    fim, anterior = time.monotonic() + espera, None
    while True:
        xml = _tela(d)
        if xml and tem_termos(xml):
            raise Parada(f"{passo}: tela de termos ou aviso do teclado; o robô nunca aceita pelo Rafael")
        ponto = achar_ponto(xml) if xml else None
        if ponto and ponto == anterior:
            return ponto
        anterior = ponto
        if time.monotonic() >= fim:
            return None
        time.sleep(PAUSA_DA_LEITURA)


def tocar(d, alvo, passo, espera=ESPERA_DA_TELA):
    """Toca no elemento (texto, descrição ou @id, como no ps.achar) quando ele aparece parado; Parada sem ele."""
    ponto = ponto_parado(d, lambda xml: ps.achar(xml, alvo), passo, espera)
    if not ponto:
        raise Parada(f"{passo}: não achei o botão na tela")
    d.click(*ponto)


def centro_da_caixa(xml):
    """O centro da caixa do pedido; None sem ela."""
    campo = next((el for el in ps.elementos(xml) if el["pacote"] == PACOTE and el["classe"] == "EditText"), None)
    if not campo:
        return None
    x1, y1, x2, y2 = campo["caixa"]
    return (x1 + x2) // 2, (y1 + y2) // 2


def projeto_na_lista(xml, nome=""):
    """O centro do projeto do robô na lista do início: o de nome guardado ou, sem ele, o 1º com nome de projeto."""
    for el in ps.elementos(xml):
        if el["pacote"] != PACOTE:
            continue
        for valor in (el["descricao"], el["texto"]):
            valor = " ".join(valor.split())
            if valor and (nome in valor if nome else NOME_DE_PROJETO.search(valor)):
                x1, y1, x2, y2 = el["caixa"]
                return (x1 + x2) // 2, (y1 + y2) // 2
    return None


def titulo_do_projeto(xml):
    """O nome do projeto aberto: o texto no alto da tela que tem cara de nome de projeto; "" sem ele."""
    for el in ps.elementos(xml):
        achado = NOME_DE_PROJETO.search(" ".join((el["descricao"] or el["texto"]).split()))
        if el["pacote"] == PACOTE and el["caixa"][1] < 400 and achado:
            return achado.group(0)
    return ""


def modelo_no_pedido(xml):
    """O modelo que está marcado no pedido (o botão "Omni 1.2 Flash\\nx1"); "" sem ele."""
    for el in ps.elementos(xml):
        achado = re.fullmatch(r"(.+?)\s*\n\s*x\d", el["descricao"] or "")
        if el["pacote"] == PACOTE and achado:
            return " ".join(achado.group(1).split())
    return ""


def custo_na_tela(xml):
    """Quantos créditos a geração vai usar, como o app diz ("24 créditos de IA"); None sem o aviso."""
    for el in ps.elementos(xml):
        achado = CUSTO_NA_TELA.search(f"{el['descricao']} {el['texto']}")
        if achado:
            return int(achado.group(1))
    return None


def texto_do_pedido(xml):
    """O que está escrito na caixa do pedido ("" vazia)."""
    for el in ps.elementos(xml):
        if el["pacote"] == PACOTE and el["classe"] == "EditText":
            return el["texto"]
    return ""


def fotos_no_pedido(xml):
    """
    Quantas miniaturas de foto o pedido tem: as imagens tocáveis do app, sem descrição, logo acima do
    + (Adicionar mídia). Com as opções do modelo abertas, a caixa do pedido ocupa a tela toda e a
    miniatura fica dentro dela (visto no ensaio de 15/11); o + fica abaixo da miniatura nos dois jeitos.
    """
    elementos = ps.elementos(xml)
    mais = next((el["caixa"] for el in elementos
                 if el["pacote"] == PACOTE and el["descricao"] == "Adicionar mídia"), None)
    if not mais:
        return 0
    return sum(1 for el in elementos
               if el["pacote"] == PACOTE and el["classe"] == "ImageView" and el["clicavel"] and not el["descricao"]
               and 60 <= el["caixa"][2] - el["caixa"][0] <= 300 and mais[1] - 900 <= el["caixa"][3] <= mais[1])


def foto_no_pedido(xml):
    """A miniatura da foto do produto já está no pedido?"""
    return fotos_no_pedido(xml) > 0


def pronto_para_gerar(xml, prompt, modelo, custo):
    """"" quando o pedido está como o teste quer (foto, texto, modelo e custo); senão, o que falta (texto fixo)."""
    if fotos_no_pedido(xml) != 1:
        return "o pedido não tem uma foto só"
    if " ".join(texto_do_pedido(xml).split())[:40] != " ".join(prompt.split())[:40]:
        return "o texto do pedido não entrou"
    if modelo_no_pedido(xml) != modelo:
        return "o modelo marcado não é o do teste"
    if custo_na_tela(xml) != custo:
        return "o custo na tela não é o esperado"
    return ""


def abrir_o_projeto(d, nome):
    """Abre o Flow do zero e entra no projeto do robô (sem ele, cria um). Devolve o nome do projeto."""
    d.app_start(PACOTE, stop=True, wait=True)
    xml = esperar(d, lambda x: ps.achar(x, "Novo") or tem_termos(x), 30)
    if not xml or tem_termos(xml):
        raise Parada("abrir o Flow: o início não apareceu" if not xml else
                     "abrir o Flow: tela de termos; o robô nunca aceita pelo Rafael")
    ponto = ponto_parado(d, lambda x: projeto_na_lista(x, nome), "projeto do robô", 8)
    if ponto:
        d.click(*ponto)
    else:
        tocar(d, "Novo", "projeto novo")
    xml = esperar(d, lambda x: ps.achar(x, "Criar"))
    if not xml:
        raise Parada("abrir o projeto: o Criar não apareceu")
    return titulo_do_projeto(xml) or nome


def montar_o_pedido(d, prompt, modelo, custo):
    """Criar → Vídeo → a foto → o texto → o modelo; devolve a tela pronta para o Gerar (Parada no que falhar)."""
    tocar(d, "Criar", "criar")
    tocar(d, "Vídeo", "modo vídeo")
    # O pedido guardado de antes (foto ou texto) não é apagado às cegas: o teste para, e
    # nunca gera com duas fotos ou com o texto de outro pedido.
    xml = esperar(d, lambda x: any(el["classe"] == "EditText" for el in ps.elementos(x)))
    if not xml:
        raise Parada("pedido: a caixa do pedido não apareceu")
    if fotos_no_pedido(xml) or texto_do_pedido(xml).strip():
        raise Parada("pedido: já tinha foto ou texto de antes")
    tocar(d, "Adicionar mídia", "adicionar mídia")
    tocar(d, "Imagens", "imagens")
    if not esperar(d, lambda x: PACOTE_DO_SELETOR in x and ps.achar(x, "Item Foto")):
        raise Parada("seletor de fotos: a foto do produto não apareceu")
    tocar(d, "Item Foto", "escolher a foto")
    tocar(d, "@button_add", "adicionar a foto")
    if not esperar(d, foto_no_pedido, 30):
        raise Parada("foto no pedido: a miniatura não apareceu")
    ponto = ponto_parado(d, centro_da_caixa, "texto do pedido")
    if not ponto:
        raise Parada("texto do pedido: a caixa não apareceu")
    d.click(*ponto)
    time.sleep(1)
    ps.escrever(d, prompt)
    if not esperar(d, lambda x: " ".join(texto_do_pedido(x).split())[:40] == " ".join(prompt.split())[:40], 10):
        raise Parada("texto do pedido: o texto não entrou na caixa")
    xml = _tela(d)
    atual = modelo_no_pedido(xml)
    if not atual:
        raise Parada("modelo: o botão do modelo não apareceu")
    tocar(d, f"{atual} x", "abrir o modelo")
    for opcao in ("9:16", "720p", "x1"):
        tocar(d, opcao, f"opção {opcao}")
    if atual != modelo:
        tocar(d, atual, "lista de modelos")
        tocar(d, modelo, "escolher o modelo")
        if not esperar(d, lambda x: modelo_no_pedido(x) == modelo):
            raise Parada("modelo: o escolhido não ficou marcado")
    return esperar(d, lambda x: custo_na_tela(x) is not None) or _tela(d)


def acompanhar_a_geracao(d):
    """Depois do Gerar: guarda a tela agora e a cada INTERVALO_DOS_CASOS, até ESPERA_DA_GERACAO. Quantos guardou."""
    guardados, inicio = 0, time.monotonic()
    while True:
        passado = int(time.monotonic() - inicio)
        if casos_robo.guardar(d, "flow", "tela", f"depois do Gerar, aos {passado} s", passo="flow gerar"):
            guardados += 1
            print(f"Flow: tela guardada aos {passado} s depois do Gerar")
        if passado >= ESPERA_DA_GERACAO:
            return guardados
        time.sleep(min(INTERVALO_DOS_CASOS, max(1, ESPERA_DA_GERACAO - passado)))


def foto_na_galeria(d, foto):
    """Põe a foto do produto na galeria do celular, com nome novo; o nome do arquivo ("" se não apareceu)."""
    with open(foto, "rb") as arquivo:
        return ps.por_foto_na_galeria(d, arquivo.read(), nome=f"flow_{int(time.time())}")


def tirar_da_galeria(d, nome):
    """Tira a foto do produto da galeria e avisa a galeria."""
    if not nome:
        return
    caminho = f"{ps.GALERIA}/{nome}"
    d.shell(["rm", "-f", caminho])
    d.shell(["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", "file://" + caminho])


def no_celular(teste, modelo, custo, sem_gerar):
    """O teste no celular, com a trava na mão: a tela, a foto, o Flow e o Gerar. 0 deu certo, 1 parou."""
    if celular_robo.tela_acesa() is False:
        ps.conectar(celular=True).screen_on()
        time.sleep(2)
    if celular_robo.tela_acesa() is False or celular_robo.tela_de_bloqueio():
        print("celular: a tela está apagada ou na tela de bloqueio; nada foi tocado")
        return 1
    d = ps.conectar(celular=True)
    nome_na_galeria = foto_na_galeria(d, teste["foto"])
    if not nome_na_galeria:
        print("celular: a foto do produto não apareceu na galeria; nada foi tocado no Flow")
        return 1
    try:
        projeto = abrir_o_projeto(d, (db.ler_config(CHAVE, {}) or {}).get("projeto", ""))
        if projeto:
            guardar(projeto=projeto)
        print("Flow: aberto no projeto do robô")
        xml = montar_o_pedido(d, teste["prompt"], modelo, custo)
        falta = pronto_para_gerar(xml, teste["prompt"], modelo, custo)
        if falta:
            raise Parada(f"antes do Gerar: {falta}")
        print(f"Flow: pedido pronto (foto, texto, {modelo}, {custo} créditos)")
        if sem_gerar:
            casos_robo.guardar(d, "flow", "tela", "pedido pronto, sem gerar", passo="flow sem gerar")
            print("Flow: sem gerar; a tela do pedido pronto foi guardada")
            return 0
        tocar(d, "Gerar", "gerar")
        videos = dict(teste.get("videos") or {})
        videos[modelo] = {"custo": custo, "gerado_em": agora(), "estado": "gerando"}
        guardar(teste={**teste, "videos": videos})
        print(f"Flow: Gerar tocado ({modelo}, {custo} créditos)")
        acompanhar_a_geracao(d)
        return 0
    except Parada as e:
        casos_robo.guardar(d, "flow", "parou", str(e), passo="flow")
        print(f"Flow: parou: {e}")
        return 1
    finally:
        tirar_da_galeria(d, nome_na_galeria)


def teste(sem_gerar=False):
    """O próximo vídeo do teste (um modelo por vez); com sem_gerar, tudo até o Gerar, sem tocar nele."""
    teste_de_agora = teste_guardado()
    if not teste_de_agora:
        escolhido = escolher_o_produto()
        if not escolhido:
            print(f"Nenhum dos próximos {PRODUTOS_TENTADOS} vídeos da fonte tem uma foto boa para o vídeo: "
                  "o teste não roda.")
            return 1
        os.makedirs(PASTA, exist_ok=True)
        caminho = os.path.join(PASTA, "foto_do_teste.jpg")
        with open(caminho, "wb") as arquivo:
            arquivo.write(escolhido["foto"])
        teste_de_agora = {"link": escolhido["link"], "nome": escolhido["nome"], "foto": caminho,
                          "prompt": escolhido["prompt"], "cena": escolhido["cena"], "criado_em": agora(),
                          "videos": {}}
        guardar(teste=teste_de_agora)
        print(f"Produto do teste: escolhido (o {escolhido['tentados']}º dos próximos vídeos da fonte); "
              f"pedido da IA com {len(escolhido['prompt'].split())} palavras")
    proximo = proximo_modelo(teste_de_agora)
    if not proximo:
        print("Os 3 vídeos do teste já foram gerados.")
        return 0
    modelo, custo = proximo
    print(f"Vídeo do teste: {modelo} ({custo} créditos)")
    if not celular_robo.conectado():
        print("celular: desconectado; conecte pelo bot (Shopee Vídeo 🎬 → Celular do Robô 📱)")
        return 1
    if not ps.no_horario_das_rodadas():
        inicio, fim = ps.horario_das_rodadas()
        print(f"celular: fora do horário das rodadas ({inicio}h às {fim}h de Brasília); nada foi tocado")
        return 1
    tentativas = ps.ESPERA_DO_CELULAR // ps.PAUSA_DA_ESPERA + 1
    for tentativa in range(tentativas):
        with celular_robo.trava() as livre:
            if livre:
                return no_celular(teste_de_agora, modelo, custo, sem_gerar)
        if tentativa == 0:
            print(f"celular: o robô automático está tocando no celular; esperando ele soltar "
                  f"(até {ps.ESPERA_DO_CELULAR // 60} min)")
        if tentativa < tentativas - 1:
            time.sleep(ps.PAUSA_DA_ESPERA)
    print("celular: o robô automático continua tocando no celular; nada foi tocado")
    return 1


def main(argumentos):
    if argumentos and argumentos[0] == "teste" and set(argumentos[1:]) <= {"--sem-gerar"}:
        # Os módulos logam nomes e links; aqui o log é público, e o resultado sai pelos prints.
        logging.disable(logging.CRITICAL)
        try:
            return teste(sem_gerar="--sem-gerar" in argumentos)
        finally:
            logging.disable(logging.NOTSET)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
