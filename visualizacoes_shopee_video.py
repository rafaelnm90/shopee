"""
As visualizações dos vídeos da Shopee Vídeo na grade do Perfil: a medição da capa com chamada
(escolha do Rafael de 29/10/2026, P76: DECISOES.md, Shopee Vídeo).

A grade mostra o número de visualizações embaixo de cada vídeo, mas não diz qual vídeo é qual.
Logo depois de postar, o robô da Shopee Vídeo (robo_shopee_video) guarda a marca da capa do vídeo
novo, e uma vez por dia acha cada vídeo dele na grade pela marca e anota o número. Aqui ficam a
marca (um dHash de 64 bits do miolo do quadro na tela: só o desenho da capa, nunca a imagem), o
casamento dos quadros da grade com os vídeos e a comparação dos vídeos com e sem a chamada, que o
painel (Capa com Chamada 🏷️, no privado, com os números) e o checkup (só em %) mostram. Do mesmo jeito, o
checkup compara a foto do começo de 1,5 s com a de 2 s de antes (escolha do Rafael de 13/11/2026, P221 1).
A mesma marca, tirada da capa pequena de cada linha de curtida das Notificações (marca_da_miniatura), junta as
curtidas do mesmo vídeo: o vídeo que começa a viralizar vai para os fixados do Perfil (P263 1).
O checkup compara também as visualizações de cada formato do vídeo de IA com as dos outros vídeos de IA, como a
propaganda de TV (escolha do Rafael de 21/11/2026, P269 1: comparar_os_formatos).
"""
import statistics
from collections import Counter
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
# A capa pequena das linhas das Notificações (P263 1) tem os cantos arredondados: a marca pula esta
# fração da beirada de cada lado.
MARGEM_DA_MINIATURA = 0.12
# As idades do vídeo (dias depois do post) em que os dois grupos são comparados, e a folga da
# leitura: a leitura do dia mais perto da idade, até FOLGA_DA_IDADE_HORAS antes ou depois.
IDADES_DA_COMPARACAO = (1, 3)
FOLGA_DA_IDADE_HORAS = 12
# O formato da propaganda de TV do vídeo de IA (P269 1), o mesmo de flow_shopee_video.ESTILO_DA_PROPAGANDA (conferido
# no teste), sem importar o flow aqui: a medição dos formatos o mostra sempre, mesmo antes do 1º vídeo dele.
FORMATO_DA_PROPAGANDA = "propaganda_tv"
FORMATO = "%Y-%m-%d %H:%M:%S"


def marca_da_capa(imagem, caixa):
    """
    A marca (16 dígitos hexadecimais) da capa do quadro da grade em caixa (x1, y1, x2, y2) do
    print da tela (imagem do PIL). None quando o miolo é quase de uma cor só (a capa ainda não
    carregou) ou pequeno demais.
    """
    x1, y1, x2, y2 = caixa
    cima, baixo = MIOLO_DO_QUADRO
    return _marca_do_recorte(imagem.crop((x1, y1 + int((y2 - y1) * cima), x2, y1 + int((y2 - y1) * baixo))))


def marca_da_miniatura(imagem, caixa):
    """
    A marca da capa pequena do vídeo numa linha das Notificações (o quadrado de cantos
    arredondados, em caixa), sem a beirada do arredondado: as linhas de curtida do mesmo vídeo
    ficam com marcas parecidas (P263 1). None quando a capa ainda não carregou.
    """
    x1, y1, x2, y2 = caixa
    margem_x, margem_y = int((x2 - x1) * MARGEM_DA_MINIATURA), int((y2 - y1) * MARGEM_DA_MINIATURA)
    return _marca_do_recorte(imagem.crop((x1 + margem_x, y1 + margem_y, x2 - margem_x, y2 - margem_y)))


def _marca_do_recorte(recorte):
    """O dHash de 64 bits do recorte (imagem do PIL), ou None quando ele é quase de uma cor só ou pequeno demais."""
    from PIL import Image, ImageStat
    miolo = recorte.convert("L")
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


def comparar(videos, desde=None, grupo=None):
    """
    A comparação da capa com chamada. videos: os postados pelo robô, [{"postado_em",
    "chamada", "marca", "vistas"}]; desde: o momento em que o Rafael ligou a capa (só os de
    depois entram; com ela ligada, a chamada vai em todos, P100, e os sem são os que ficaram
    sem a vantagem da IA). grupo: a função que diz se o vídeo vai no grupo "com" (verdadeiro) ou no
    "sem"; sem ela, a chamada diz (comparar_a_foto usa a foto do começo).
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
        grupos["com" if (grupo(video) if grupo else video.get("chamada")) else "sem"].append(video)
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


def comparar_a_foto(videos):
    """
    A comparação da foto do começo (P221 1), como a da capa com chamada: no grupo "com", os vídeos que anotaram o
    tempo da foto (segundos_da_foto, os feitos depois da P221 1, com 1,5 s); no "sem", os de antes, que não o
    anotavam e foram com 2 s. O vídeo que foi sem a edição (segundos_da_foto "0", sem a foto) fica de fora.
    videos: [{"postado_em", "segundos_da_foto", "marca", "vistas"}]. Devolve o mesmo que comparar e, em
    "segundos", os tempos anotados nos do grupo "com", como se escrevem ("1,5"), do menor para o maior.
    """
    com_a_foto = [v for v in videos if (v.get("segundos_da_foto") or "") != "0"]
    medicao = comparar(com_a_foto, grupo=lambda video: bool(video.get("segundos_da_foto")))
    anotados = {v["segundos_da_foto"] for v in com_a_foto if v.get("segundos_da_foto")}
    medicao["segundos"] = [s.replace(".", ",") for s in sorted(anotados, key=_numero)]
    return medicao


def comparar_os_formatos(videos):
    """
    A medição dos formatos do vídeo de IA (P269 1): cada formato contra os outros vídeos de IA, como a da capa com
    chamada (comparar), com o formato no grupo "com" e os outros vídeos de IA no "sem". videos: [{"postado_em",
    "formato", "marca", "vistas"}], só os vídeos de IA postados. Devolve [(formato, a comparação)]: a propaganda de TV
    (FORMATO_DA_PROPAGANDA) primeiro, mesmo sem nenhum vídeo dela, e depois os outros formatos com vídeo, dos que têm
    mais vídeos com a marca da capa (os que entram na comparação) para os que têm menos.
    """
    contagem = Counter(v.get("formato") or "" for v in videos if v.get("marca"))
    presentes = {v.get("formato") or "" for v in videos} - {"", FORMATO_DA_PROPAGANDA}
    formatos = [FORMATO_DA_PROPAGANDA] + sorted(presentes, key=lambda f: (-contagem[f], f))
    return [(formato, comparar(videos, grupo=lambda video, f=formato: (video.get("formato") or "") == f))
            for formato in formatos]


def _numero(texto):
    try:
        return float(texto)
    except ValueError:
        return 0.0
