"""
As visualizações dos vídeos da Shopee Vídeo na grade do Perfil: a medição da capa com chamada
(escolha do Rafael de 29/10/2026, P76: DECISOES.md, Shopee Vídeo).

A grade mostra o número de visualizações embaixo de cada vídeo, mas não diz qual vídeo é qual.
Logo depois de postar, o robô da Shopee Vídeo (robo_shopee_video) guarda a marca da capa do vídeo
novo, e uma vez por dia acha cada vídeo dele na grade pela marca e anota o número. Aqui ficam a
marca (um dHash de 64 bits do miolo do quadro na tela: só o desenho da capa, nunca a imagem), o
casamento dos quadros da grade com os vídeos e a comparação dos vídeos com e sem a chamada, que o
painel (Capa com Chamada 🏷️, no privado, com os números) e o checkup (só em %) mostram.
"""
import statistics
from datetime import datetime

# A faixa do quadro, em fração da altura, que entra na marca: sem o selo "Fixado" e a
# sacolinha, em cima, e sem o número de visualizações, embaixo, que muda todo dia.
MIOLO_DO_QUADRO = (0.22, 0.78)
# A marca compara 8 linhas de 9 pontos do miolo, cada ponto com o vizinho da direita; diferença
# de até MARGEM_DA_MARCA (de 0 a 255) conta como igual, para o ruído da imagem não virar bit.
MARGEM_DA_MARCA = 3
# Até quantos bits diferentes (de 64) duas marcas são a mesma capa.
MARCA_PARECIDA = 10
# Miolo quase de uma cor só (o desvio abaixo disto): a capa ainda não carregou.
QUADRO_SEM_CAPA = 6
# As idades do vídeo (dias depois do post) em que os dois grupos são comparados, e a folga da
# leitura: a leitura do dia mais perto da idade, até FOLGA_DA_IDADE_HORAS antes ou depois.
IDADES_DA_COMPARACAO = (1, 3)
FOLGA_DA_IDADE_HORAS = 12
FORMATO = "%Y-%m-%d %H:%M:%S"


def marca_da_capa(imagem, caixa):
    """
    A marca (16 dígitos hexadecimais) da capa do quadro da grade em caixa (x1, y1, x2, y2) do
    print da tela (imagem do PIL). None quando o miolo é quase de uma cor só (a capa ainda não
    carregou) ou pequeno demais.
    """
    from PIL import Image, ImageStat
    x1, y1, x2, y2 = caixa
    cima, baixo = MIOLO_DO_QUADRO
    miolo = imagem.crop((x1, y1 + int((y2 - y1) * cima), x2, y1 + int((y2 - y1) * baixo))).convert("L")
    if min(miolo.size) < 9 or ImageStat.Stat(miolo).stddev[0] < QUADRO_SEM_CAPA:
        return None
    pontos = list(miolo.resize((9, 8), Image.BOX).tobytes())
    bits = 0
    for linha in range(8):
        for coluna in range(8):
            esquerda, direita = pontos[linha * 9 + coluna], pontos[linha * 9 + coluna + 1]
            bits = bits << 1 | (esquerda > direita + MARGEM_DA_MARCA)
    return f"{bits:016x}"


def diferenca(marca, outra):
    """Quantos bits as duas marcas têm diferentes (0: a mesma capa)."""
    return bin(int(marca, 16) ^ int(outra, 16)).count("1")


def casar(quadros, procurados):
    """
    Os vídeos achados na grade. quadros: [(marca, vistas)] na ordem da grade; procurados:
    [(ident, marca)] do mais novo para o mais velho. Cada quadro fica com o procurado ainda não
    achado de marca mais parecida (até MARCA_PARECIDA); no empate, o mais novo, e assim dois
    posts com a mesma foto de capa casam na ordem da grade. Devolve {ident: vistas}.
    """
    achados = {}
    for marca, vistas in quadros:
        if not marca or vistas is None:
            continue
        candidatos = [(diferenca(marca, outra), i, ident) for i, (ident, outra) in enumerate(procurados)
                      if outra and ident not in achados]
        if candidatos:
            distancia, _i, ident = min(candidatos)
            if distancia <= MARCA_PARECIDA:
                achados[ident] = vistas
    return achados


def _horas(depois, antes):
    try:
        return (datetime.strptime(depois, FORMATO) - datetime.strptime(antes, FORMATO)).total_seconds() / 3600
    except (TypeError, ValueError):
        return None


def vistas_com_a_idade(postado_em, leituras, dias):
    """As visualizações da leitura mais perto de `dias` dias depois do post (dentro da folga), ou None."""
    alvo, melhor = dias * 24, None
    for momento, numero in leituras or []:
        horas = _horas(momento, postado_em)
        if horas is None or abs(horas - alvo) > FOLGA_DA_IDADE_HORAS:
            continue
        if melhor is None or abs(horas - alvo) < melhor[0]:
            melhor = (abs(horas - alvo), numero)
    return melhor[1] if melhor else None


def comparar(videos, desde=None):
    """
    A comparação da capa com chamada. videos: os postados pelo robô, [{"postado_em",
    "chamada", "marca", "vistas"}]; desde: o momento em que o Rafael ligou a capa (só os de
    depois entram; com ela ligada, a chamada vai em todos, P100, e os sem são os que ficaram
    sem a vantagem da IA).
    Devolve {"com": grupo, "sem": grupo, "sem_marca": n}: cada grupo é {"videos", "lidos",
    "idades": {dias: (quantos, mediana ou None)}}, e sem_marca conta os postados sem a marca da
    capa desde o primeiro que a teve (os de antes da medição nunca a tiveram).
    """
    if desde:
        videos = [v for v in videos if (v.get("postado_em") or "") >= desde]
    com_marca = [v for v in videos if v.get("marca")]
    inicio = min((v["postado_em"] or "" for v in com_marca), default=None)
    grupos = {"com": [], "sem": []}
    for video in com_marca:
        grupos["com" if video.get("chamada") else "sem"].append(video)
    resultado = {"sem_marca": sum(1 for v in videos if not v.get("marca") and inicio
                                  and (v.get("postado_em") or "") >= inicio)}
    for nome, lista in grupos.items():
        idades = {}
        for dias in IDADES_DA_COMPARACAO:
            numeros = [n for n in (vistas_com_a_idade(v["postado_em"], v.get("vistas"), dias) for v in lista)
                       if n is not None]
            idades[dias] = (len(numeros), statistics.median(numeros) if numeros else None)
        resultado[nome] = {"videos": len(lista), "lidos": sum(1 for v in lista if v.get("vistas")), "idades": idades}
    return resultado


def diferenca_em_porcento(medicao, dias):
    """Quanto a mediana com a chamada fica acima (+) ou abaixo (-) da sem, em %, com `dias` dias; None sem as duas."""
    com, sem = medicao["com"]["idades"][dias][1], medicao["sem"]["idades"][dias][1]
    if com is None or not sem:
        return None
    return round((com - sem) * 100 / sem)
