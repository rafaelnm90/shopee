"""Modo assistente da Shopee Vídeo: quando mandar, qual vídeo, texto da IA, produtos e a mensagem do privado."""
import json
import os
import re
from datetime import datetime
from types import SimpleNamespace

import pytest

import assistente_shopee_video as asv
import edicao_video
from conftest import consultar, inserir, rodar
from fuso import fuso_horario

CONFIG = {"pausado": False, "limite_min": 5, "limite_max": 5, "inicio": 13, "fim": 22}


@pytest.fixture(autouse=True)
def tabela_de_configuracoes():
    # No servidor, quem cria é o bot_mestre ao subir; o assistente roda dentro dele.
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")


@pytest.fixture(autouse=True)
def sem_ia_de_texto(monkeypatch):
    """Os testes rodam sem rede: o pedido de texto à IA (o nome dos produtos no vídeo, P265 1) volta sem resposta."""
    async def sem_resposta(prompt, imagens=None):
        return None

    monkeypatch.setattr(asv.api_gemini, "gerar_texto_gemini", sem_resposta)


def _as(hora, dia=5):
    h, m = map(int, hora.split(":"))
    return datetime(2026, 10, dia, h, m, tzinfo=fuso_horario)


# --- Quando mandar ---

def test_plano_espalha_os_horarios_pela_janela_e_e_fixo_no_dia():
    horarios = asv.planejar(CONFIG, "2026-10-05")
    assert len(horarios) == 5 and horarios == sorted(horarios)
    assert all("13:00" <= h < "22:00" for h in horarios)
    assert asv.planejar(CONFIG, "2026-10-05") == horarios
    assert asv.planejar(CONFIG, "2026-10-06") != horarios


def test_plano_do_dia_todo_nao_passa_da_meia_noite():
    horarios = asv.planejar({**CONFIG, "inicio": 0, "fim": 24, "limite_min": 50, "limite_max": 50}, "2026-10-05")
    assert len(horarios) == 50 and all("00:00" <= h <= "23:59" for h in horarios)


def test_manda_um_por_horario_vencido_e_nunca_dois_de_uma_vez():
    primeiro, segundo = asv.planejar(CONFIG, "2026-10-05")[:2]
    antes = f"{primeiro[:2]}:{int(primeiro[3:]) - 1:02d}" if primeiro[3:] != "00" else "13:00"
    assert asv.decidir_envio(CONFIG, _as(antes)) is False
    assert asv.decidir_envio(CONFIG, _as(primeiro)) is True
    assert asv.decidir_envio(CONFIG, _as(primeiro)) is False                # o mesmo horário não repete
    assert asv.decidir_envio(CONFIG, _as("23:00")) is True                   # quatro vencidos: um envio só
    assert asv.decidir_envio(CONFIG, _as("23:30")) is False
    assert segundo > primeiro


def test_pausado_pula_os_horarios_e_retomar_nao_solta_tudo():
    pausado = {**CONFIG, "pausado": True}
    assert asv.decidir_envio(pausado, _as("21:00")) is False
    assert asv.decidir_envio(CONFIG, _as("21:00")) is False                  # retomou: nada acumulado
    ultimo = asv.planejar(CONFIG, "2026-10-05")[-1]
    if ultimo > "21:00":
        assert asv.decidir_envio(CONFIG, _as(ultimo)) is True


def test_dia_novo_tem_plano_novo():
    asv.decidir_envio(CONFIG, _as("23:00"))
    estado = asv.estado_do_dia(CONFIG, _as("10:00", dia=6))
    assert estado["data"] == "2026-10-06" and estado["feitos"] == 0


# --- Qual vídeo ---

def _fila(*itens):
    inserir("CREATE TABLE IF NOT EXISTS fila_autorais (id_unico TEXT PRIMARY KEY, legenda TEXT, "
            "caminho_arquivo TEXT, data_captura TEXT)")
    for id_unico, legenda, arquivo, data in itens:
        if arquivo and not arquivo.startswith("sumiu"):
            with open(arquivo, "wb") as f:
                f.write(b"video")
        inserir("INSERT INTO fila_autorais VALUES (?, ?, ?, ?)", id_unico, legenda, arquivo, data)


LEGENDA = "<b>Garrafa Térmica 🧊</b>\n\n🔗 <b>Link do Produto:</b>\nhttps://s.shopee.com.br/abc\n\n<i>#Casa</i>"


def test_proximo_video_e_o_mais_novo_com_arquivo_e_link_ainda_nao_mandado():
    assert asv.proximo_video() is None
    _fila(("velho", LEGENDA, "archive/velho.mp4", "2026-10-01 10:00"),
          ("sem_arquivo", LEGENDA, "sumiu.mp4", "2026-10-04 10:00"),
          ("sem_link", "<b>X</b> sem link", "archive/sem_link.mp4", "2026-10-03 10:00"),
          ("novo", LEGENDA, "archive/novo.mp4", "2026-10-02 10:00"))
    video = asv.proximo_video()
    assert video == {"id": "novo", "arquivo": "archive/novo.mp4", "link": "https://s.shopee.com.br/abc",
                     "nome": "Garrafa Térmica 🧊"}
    asv.registrar("novo", "enviado")
    assert asv.proximo_video()["id"] == "velho"
    asv.registrar("velho", "violacao", "marca")
    assert asv.proximo_video() is None


def test_conta_so_os_mandados_de_hoje():
    asv.registrar("a", "enviado", agora=_as("14:00"))
    asv.registrar("b", "violacao", "x", agora=_as("15:00"))
    asv.registrar("c", "enviado", agora=_as("14:00", dia=4))
    assert asv.enviados_hoje(_as("20:00")) == 1


# --- Texto da IA ---

def test_prompt_leva_as_regras_do_gem_e_as_diretrizes():
    prompt = asv.montar_prompt("Garrafa Térmica")
    assert "entre 130 e 150 caracteres" in prompt and "entre 400 e 450 caracteres" in prompt
    assert "Stanley" in prompt and "violacao" in prompt
    assert "Garrafa Térmica" in prompt
    assert "**Integridade.**" in prompt and "Só entram os produtos que o criador vinculou" in prompt


def test_le_o_json_da_ia_mesmo_com_texto_em_volta():
    texto = ('```json\n{"violacao": false, "motivo": "", "titulo": "Garrafa Térmica 🧊 #garrafa", '
             '"comentario": "Mantém gelado o dia todo #casa"}\n```')
    assert asv.ler_resposta(texto) == {"violacao": False, "motivo": "", "feito_por_ia": False, "sinal_ia": "",
                                       "bebida_alcoolica": False, "titulo": "Garrafa Térmica 🧊 #garrafa",
                                       "comentario": "Mantém gelado o dia todo #casa"}
    assert asv.ler_resposta("não sei") is None
    assert asv.ler_resposta("{quebrado") is None
    assert asv.ler_resposta('{"violacao": true, "motivo": "marca no vídeo"}')["violacao"] is True
    # Rótulo de IA (escolha do Rafael, 24/10, P8): só o true de verdade liga; "talvez" fica desligado.
    ia = asv.ler_resposta('{"feito_por_ia": true, "sinal_ia": "avatar falando com voz sintética", "titulo": "x"}')
    assert ia["feito_por_ia"] is True and ia["sinal_ia"] == "avatar falando com voz sintética"
    assert asv.ler_resposta('{"feito_por_ia": "talvez", "titulo": "x"}')["feito_por_ia"] is False
    assert "feito_por_ia" in asv.montar_prompt() and "na dúvida, false" in asv.montar_prompt()
    # Visto em 24/10: produto "artificial" no nome não faz o vídeo filmado ser de IA.
    assert "nunca o nome do produto" in asv.montar_prompt()


def test_titulo_comprido_perde_palavras_do_fim_sem_cortar_no_meio():
    titulo = "Garrafa Térmica 🧊 " + " ".join(f"#hashtag{i}" for i in range(30))
    encaixado = asv.encaixar_titulo(titulo)
    assert asv.tamanho_no_app(encaixado) <= 150 and titulo.startswith(encaixado)
    assert titulo[len(encaixado)] == " "
    assert asv.encaixar_titulo("curto   demais") == "curto demais"


def test_titulo_conta_como_o_contador_do_app_com_emoji_valendo_2():
    # No Motorola (23/10), "Teste 💡 ok 👗 fim ✨" (18 caracteres) apareceu como 20/150: um
    # título de 150 com emojis desses passava do limite do campo da legenda.
    assert asv.tamanho_no_app("Teste 💡 ok 👗 fim ✨") == 20
    titulo = "Luminária 💡 de Mesa 👗 " + "palavra " * 30
    encaixado = asv.encaixar_titulo(titulo)
    assert len(encaixado) < 150 and asv.tamanho_no_app(encaixado) <= 150
    assert titulo.startswith(encaixado) and titulo[len(encaixado)] == " "
    assert asv.tamanho_no_app(asv.encaixar_titulo("💡" * 100)) == 150


# --- Produtos ---

def test_ordem_dos_produtos_menor_preco_e_no_empate_maior_comissao():
    produtos = [{"nome": "A", "preco": 30.0, "comissao": 5.0}, {"nome": "B", "preco": 20.0, "comissao": 1.0},
                {"nome": "C", "preco": 30.0, "comissao": 9.0}]
    assert [p["nome"] for p in asv.ordenar_produtos(produtos)] == ["B", "C", "A"]


def test_produtos_de_um_link_de_produto_vem_da_api(monkeypatch):
    async def converter(link):
        return "https://shopee.com.br/opaanlp/11/22"

    async def consultar(loja, item):
        assert (loja, item) == ("11", "22")
        return {"nome": "Garrafa", "preco": 19.9, "comissao": 8.0}

    monkeypatch.setattr(asv.api_shopee, "link_para_converter", converter)
    monkeypatch.setattr(asv, "_consultar_produto", consultar)
    produtos, link = rodar(asv.produtos_do_link("https://s.shopee.com.br/abc"))
    # O item vai junto: o vídeo mandado guarda o produto, e o Postei ✅ o conta como postado (P166 1).
    assert produtos == [{"nome": "Garrafa", "preco": 19.9, "comissao": 8.0, "item": "22"}]
    assert link == "https://s.shopee.com.br/abc"


def test_link_de_video_nao_tem_produtos_na_api(monkeypatch):
    async def converter(link):
        return "https://sv.shopee.com.br/share-video/abc?share_obj=1"

    async def consultar(loja, item):
        raise AssertionError("não devia consultar")

    monkeypatch.setattr(asv.api_shopee, "link_para_converter", converter)
    monkeypatch.setattr(asv, "_consultar_produto", consultar)
    assert rodar(asv.produtos_do_link("https://s.shopee.com.br/v")) == ([], "https://s.shopee.com.br/v")


# --- Mensagem ---

TEXTOS = {"violacao": False, "motivo": "", "titulo": "Copo <Térmico> 🧊 #copo", "comentario": "Gelado & bom #casa"}


def test_mensagem_com_produto_tem_titulo_e_comentario_para_copiar():
    texto = asv.montar_mensagem(TEXTOS, [{"nome": "Copo & Tampa", "preco": 19.9, "comissao": 8.0}],
                                "https://s.shopee.com.br/abc")
    assert "<code>Copo &lt;Térmico&gt; 🧊 #copo</code>" in texto
    assert "<code>Gelado &amp; bom #casa</code>" in texto
    assert "Copo &amp; Tampa: R$ 19,90, comissão 8%" in texto
    assert "https://s.shopee.com.br/abc" in texto and "Postar vídeo" in texto
    assert "Minhas Curtidas" in texto and "busque pelo nome" not in texto
    assert len(texto) <= 4096


def test_mensagem_vem_em_passos_com_o_produto_antes_da_postagem():
    # Salvar o vídeo e depois favoritar: abrir o link do produto no meio da postagem faz
    # a Shopee perder o que já foi feito.
    for produtos in ([{"nome": "Copo", "preco": 19.9, "comissao": 8.0}], []):
        texto = asv.montar_mensagem(TEXTOS, produtos, "https://s.shopee.com.br/abc")
        passos = ["1️⃣ <b>Salve o vídeo", "2️⃣ <b>Favorite", "https://s.shopee.com.br/abc", "3️⃣ <b>Poste",
                  "<code>Copo &lt;Térmico", "Minhas Curtidas", "4️⃣ <b>Depois de postar", "<code>Gelado"]
        posicoes = [texto.index(p) for p in passos]
        assert posicoes == sorted(posicoes), produtos


def test_mensagem_de_video_manda_ver_os_produtos_do_criador():
    texto = asv.montar_mensagem(TEXTOS, [], "https://s.shopee.com.br/v")
    assert "os que o criador vinculou" in texto and "menor preço primeiro" in texto


def test_mensagem_mostra_o_titulo_curto():
    curto = asv.montar_mensagem(TEXTOS, [], "https://s.shopee.com.br/v")
    # O tamanho como o contador do app (o 🧊 vale 2), para bater com o x/150 da legenda.
    assert f"({asv.tamanho_no_app(TEXTOS['titulo'])} caracteres, abaixo de {asv.TITULO_MIN} ⚠️;" in curto
    certo = asv.montar_mensagem({**TEXTOS, "titulo": "x" * asv.TITULO_MIN}, [], "https://s.shopee.com.br/v")
    assert f"({asv.TITULO_MIN} caracteres;" in certo and "abaixo de" not in certo


# --- Título fora do tamanho ---

def _respostas(monkeypatch, *respostas):
    chamadas = []

    async def gerar(arquivo, nome="", leves=False):
        chamadas.append(arquivo)
        return respostas[len(chamadas) - 1]

    monkeypatch.setattr(asv, "gerar_textos", gerar)
    return chamadas


def _com_titulo(tamanho, **extra):
    return {**TEXTOS, "titulo": "t" * tamanho, **extra}


def test_titulo_no_tamanho_pede_a_ia_uma_vez_so(monkeypatch):
    chamadas = _respostas(monkeypatch, _com_titulo(asv.TITULO_MIN))
    assert rodar(asv.textos_do_video("v.mp4"))["titulo"] == "t" * asv.TITULO_MIN
    assert len(chamadas) == 1


def test_titulo_curto_pede_de_novo_e_fica_com_o_mais_longo(monkeypatch):
    chamadas = _respostas(monkeypatch, _com_titulo(115), _com_titulo(140))
    assert len(rodar(asv.textos_do_video("v.mp4"))["titulo"]) == 140 and len(chamadas) == 2

    _respostas(monkeypatch, _com_titulo(120), _com_titulo(100))
    assert len(rodar(asv.textos_do_video("v.mp4"))["titulo"]) == 120

    _respostas(monkeypatch, _com_titulo(120), None)                       # a IA não respondeu de novo
    assert len(rodar(asv.textos_do_video("v.mp4"))["titulo"]) == 120


def test_titulo_curto_com_violacao_na_segunda_resposta_pula(monkeypatch):
    _respostas(monkeypatch, _com_titulo(115), _com_titulo(100, violacao=True, motivo="marca"))
    assert rodar(asv.textos_do_video("v.mp4"))["violacao"] is True


def test_violacao_ou_ia_sem_resposta_nao_pede_de_novo(monkeypatch):
    for primeira in (None, _com_titulo(50, violacao=True)):
        chamadas = _respostas(monkeypatch, primeira)
        assert rodar(asv.textos_do_video("v.mp4")) == primeira and len(chamadas) == 1


RECUSADO = ("Todos os modelos da cascata falharam → gemini-x: VAZIO "
            "(block_reason=<BlockedReason.PROHIBITED_CONTENT: 'PROHIBITED_CONTENT'>)")


def test_recusado_pelo_conteudo_pede_de_novo_com_as_regras_em_palavras_leves(monkeypatch):
    # Escolha do Rafael (P28): o Google recusou o título de vídeos comuns por causa das palavras
    # fortes das diretrizes; só nessa hora, mais um pedido com as mesmas regras em palavras leves.
    pedidos = []
    respostas = iter([None, _com_titulo(asv.TITULO_MIN)])

    async def gerar(arquivo, nome="", leves=False):
        pedidos.append(leves)
        resposta = next(respostas)
        asv.api_gemini.ULTIMO_ERRO_IA = None if resposta else RECUSADO
        return resposta

    monkeypatch.setattr(asv, "gerar_textos", gerar)
    monkeypatch.setattr(asv.api_gemini, "ULTIMA_RECUSA", {"codigos": ["PROHIBITED_CONTENT"], "categorias": []})
    textos = rodar(asv.textos_do_video("v.mp4"))
    assert pedidos == [False, True] and textos["regras_leves"] is True
    assert asv.ULTIMA_RECUSA == {"codigos": ["PROHIBITED_CONTENT"], "categorias": [], "leves": "passou"}

    # Recusado de novo: sem texto, e o motivo do Google continua para quem pediu.
    pedidos = []

    async def recusa_sempre(arquivo, nome="", leves=False):
        pedidos.append(leves)
        asv.api_gemini.ULTIMO_ERRO_IA = RECUSADO
        return None

    monkeypatch.setattr(asv, "gerar_textos", recusa_sempre)
    assert rodar(asv.textos_do_video("v.mp4")) is None and pedidos == [False, True]
    assert asv.recusado_pelo_conteudo() and asv.ULTIMA_RECUSA["leves"] == "recusado de novo"

    # Sem recusa do Google, nada para avisar.
    _respostas(monkeypatch, _com_titulo(asv.TITULO_MIN))
    rodar(asv.textos_do_video("v.mp4"))
    assert asv.ULTIMA_RECUSA is None


def test_aviso_da_recusa_diz_o_produto_o_que_o_google_disse_e_o_pedido_leve():
    texto = asv.texto_da_recusa({"codigos": ["PROHIBITED_CONTENT"], "leves": "passou",
                                 "categorias": [("HARM_CATEGORY_SEXUALLY_EXPLICIT", "MEDIUM")]}, "Máscara de Cílios")
    assert "Produto: Máscara de Cílios" in texto and "conteúdo proibido (o Google não diz qual parte)" in texto
    assert "sexual (médio)" in texto and "passou ✅" in texto
    texto = asv.texto_da_recusa({"codigos": [], "leves": "sem resposta"})
    assert "não identificado" in texto and "sem código" in texto and "Categorias" not in texto
    assert "não respondeu" in texto


def test_regras_em_palavras_leves_sao_as_mesmas_sem_as_palavras_fortes():
    normal, leves = asv.ler_diretrizes(), asv.ler_diretrizes(leves=True)
    fortes = ("nud", "sex", "infantil", "menor", "íntim", "fetiche", "suicíd", "automutila", "abuso",
              "terroris", "violênc", "mortos", "ferid")
    assert [f for f in fortes if f in normal.casefold()]
    assert not [f for f in fortes if f in leves.casefold()]
    regras = re.compile(r"^\s*(\d+)\. \*\*", re.M)
    assert regras.findall(leves) == regras.findall(normal) and len(regras.findall(normal)) == 15
    assert asv.ler_diretrizes(leves=True) in asv.montar_prompt(leves=True)
    assert normal in asv.montar_prompt()


# --- Envio ---

class Bot:
    def __init__(self):
        self.mensagens, self.videos = [], []

    async def send_message(self, chat_id, text, **kw):
        self.mensagens.append((chat_id, text))

    async def send_video(self, chat_id, video, **kw):
        self.videos.append((chat_id, os.path.basename(video.path)))


def _preparar(monkeypatch, textos):
    async def gerar(arquivo, nome="", leves=False):
        return textos

    async def produtos(link):
        return [{"nome": "Garrafa", "preco": 19.9, "comissao": 8.0}], link

    monkeypatch.setattr(asv, "gerar_textos", gerar)
    monkeypatch.setattr(asv, "produtos_do_link", produtos)
    _fila(("novo", LEGENDA, "archive/novo.mp4", "2026-10-02 10:00"))


def test_envio_manda_video_e_mensagem_e_registra(monkeypatch):
    _preparar(monkeypatch, TEXTOS)
    bot = Bot()
    assert rodar(asv.preparar_e_enviar(bot, 42, _as("14:00"))) == "postagem mandada no seu privado"
    assert bot.videos == [(42, "novo.mp4")] and "Postagem pronta" in bot.mensagens[0][1]
    assert "2️⃣ <b>Favorite o produto" in bot.mensagens[0][1]
    assert asv.enviados_hoje(_as("15:00")) == 1 and asv.proximo_video() is None


def test_violacao_pula_o_video_e_diz_o_motivo(monkeypatch):
    _preparar(monkeypatch, {**TEXTOS, "violacao": True, "motivo": "marca d'água do TikTok"})
    bot = Bot()
    assert "violação" in rodar(asv.preparar_e_enviar(bot, 42))
    assert bot.videos == [] and "marca d&#x27;água do TikTok" in bot.mensagens[0][1]
    assert asv.proximo_video() is None and asv.enviados_hoje() == 0


def test_ia_sem_resposta_pula_o_video_sem_mandar(monkeypatch):
    _preparar(monkeypatch, None)
    bot = Bot()
    assert "a IA não gerou" in rodar(asv.preparar_e_enviar(bot, 42))
    assert bot.videos == [] and bot.mensagens == [] and asv.proximo_video() is None


def test_sem_video_avisa_e_nao_chama_a_ia(monkeypatch):
    async def gerar(arquivo, nome="", leves=False):
        raise AssertionError("não devia chamar a IA")

    monkeypatch.setattr(asv, "gerar_textos", gerar)
    assert "não há vídeo" in rodar(asv.preparar_e_enviar(Bot(), 42))


def test_video_que_da_erro_e_pulado_para_nao_travar_a_fila(monkeypatch):
    _preparar(monkeypatch, TEXTOS)

    class BotQueRecusa(Bot):
        async def send_video(self, chat_id, video, **kw):
            raise RuntimeError("arquivo grande demais")

    with pytest.raises(RuntimeError):
        rodar(asv.preparar_e_enviar(BotQueRecusa(), 42))
    assert asv.proximo_video() is None


# --- Só vídeo editado (P40) ---

LEGENDA_VIDEO = LEGENDA.replace("https://s.shopee.com.br/abc", "https://s.shopee.com.br/video")


def _com_edicao(monkeypatch, conteudos, ias, editados=None):
    """
    Edição ligada, com a edição e a foto de mentira; o link de vídeo não traz produto (sem
    foto). editados recebe (foto, produto, avisos) de cada edição.
    """
    import db
    import edicao_video
    import postador_shopee_video as ps
    db.salvar_config("shopee_video", {"edicao_ligada": True})

    async def gerar(arquivo, nome="", leves=False):
        ias.append(arquivo)
        return TEXTOS

    async def produtos(link):
        if "video" in link:
            return [], link
        return [{"nome": "Garrafa", "preco": 19.9, "comissao": 8.0, "imagem": "https://cf.shopee.com.br/g"}], link

    editados = [] if editados is None else editados

    def editar_para_postar(video, foto, destino, produto="", avisos=False):
        editados.append((foto, produto, avisos))
        if not foto:
            return "a foto do anúncio não veio", edicao_video.SO_COM_O_EDITOR_1, ""
        with open(destino, "wb") as arquivo:
            arquivo.write(b"capa com os avisos" if avisos else b"editado com " + foto)
        return "", edicao_video.COM_LEGENDAS + (edicao_video.COM_OS_AVISOS if avisos else ""), ""

    class BotQueLe(Bot):
        async def send_video(self, chat_id, video, **kw):
            with open(video.path, "rb") as arquivo:
                conteudos.append(arquivo.read())
            await super().send_video(chat_id, video, **kw)

    monkeypatch.setattr(asv, "gerar_textos", gerar)
    monkeypatch.setattr(asv, "produtos_do_link", produtos)
    monkeypatch.setattr(ps, "baixar_foto", lambda endereco: b"foto")
    monkeypatch.setattr(edicao_video, "editar_para_postar", editar_para_postar)
    return BotQueLe()


def test_com_a_edicao_ligada_o_assistente_manda_o_video_editado(monkeypatch):
    # Pedidos do Rafael (25/10, P40): na Shopee Vídeo, só vídeo editado, também no assistente;
    # (28/10, P50) com o Editor 2, como nos rascunhos do robô: as legendas com o nome, a vantagem
    # e a chamada para o produto (sem o preço, P80).
    conteudos, ias, editados = [], [], []
    bot = _com_edicao(monkeypatch, conteudos, ias, editados)
    _fila(("novo", LEGENDA, "archive/novo.mp4", "2026-10-02 10:00"))
    assert rodar(asv.preparar_e_enviar(bot, 42)) == "postagem mandada no seu privado"
    assert conteudos == [b"editado com foto"] and "Postagem pronta" in bot.mensagens[0][1]
    assert editados == [(b"foto", "Garrafa", False)]
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = 'edição do vídeo: assistente'") \
        == (edicao_video.COM_LEGENDAS, 1)
    # A IA assiste ao vídeo original, sem a foto e a seta por cima.
    assert set(ias) == {"archive/novo.mp4"}


def test_com_a_edicao_ligada_o_som_e_conferido_no_video_que_vai(monkeypatch):
    # Escolha do Rafael (28/10, P55): o vídeo editado já leva a música de fundo; o lembrete da
    # música da Shopee (P48) só vem quando o vídeo que vai ainda está sem som.
    conteudos, ias = [], []
    bot = _com_edicao(monkeypatch, conteudos, ias)
    conferidos = []
    monkeypatch.setattr(asv.videos, "mudo", lambda caminho, timeout=120: conferidos.append(caminho) or False)
    _fila(("novo", LEGENDA, "archive/novo.mp4", "2026-10-02 10:00"))
    assert rodar(asv.preparar_e_enviar(bot, 42)) == "postagem mandada no seu privado"
    assert len(conferidos) == 1 and conferidos[0] != "archive/novo.mp4"
    assert "Vídeo sem som" not in bot.mensagens[-1][1]


def test_sem_o_editor_2_o_assistente_manda_com_o_editor_1_e_o_registro_anota(monkeypatch):
    # Escolha do Rafael (28/10, P51): se o Editor 2 não sai, o vídeo vai com o Editor 1, sem
    # legendas; o registro anota (como falha, para o checkup ver).
    conteudos, ias = [], []
    bot = _com_edicao(monkeypatch, conteudos, ias)

    def editar_para_postar(video, foto, destino, produto="", avisos=False):
        with open(destino, "wb") as arquivo:
            arquivo.write(b"editor 1")
        return "", edicao_video.SO_COM_O_EDITOR_1, "o Editor 2 não saiu: o ffmpeg falhou"
    monkeypatch.setattr(edicao_video, "editar_para_postar", editar_para_postar)
    _fila(("novo", LEGENDA, "archive/novo.mp4", "2026-10-02 10:00"))
    assert rodar(asv.preparar_e_enviar(bot, 42)) == "postagem mandada no seu privado"
    assert conteudos == [b"editor 1"]
    assert consultar("SELECT resultado, detalhe, ok FROM registro_processos "
                     "WHERE processo = 'edição do vídeo: assistente'") == (
        edicao_video.SO_COM_O_EDITOR_1, "o Editor 2 não saiu: o ffmpeg falhou", 0)


def test_o_que_nao_sai_editado_fica_de_lado_e_vai_o_proximo_sem_gastar_a_ia(monkeypatch):
    conteudos, ias = [], []
    bot = _com_edicao(monkeypatch, conteudos, ias)
    _fila(("produto", LEGENDA, "archive/produto.mp4", "2026-10-02 09:00"),
          ("video", LEGENDA_VIDEO, "archive/video.mp4", "2026-10-02 10:00"))
    assert rodar(asv.preparar_e_enviar(bot, 42)) == "postagem mandada no seu privado"
    assert conteudos == [b"editado com foto"] and set(ias) == {"archive/produto.mp4"}
    # O de link de vídeo (sem uma foto só) ficou de lado e não volta.
    assert asv.proximo_video() is None and asv.enviados_hoje() == 1
    # Sem o celular, o link de vídeo não tem a foto do anúncio: de lado, sem contar como falha
    # (28/10: o checkup cobrava 9 falhas assim) e sem tentar a edição.
    assert consultar("SELECT ok FROM registro_processos WHERE processo = 'assistente: envio' AND resultado = ?",
                     asv.SEM_PRODUTO_NO_LINK) == (None,)
    assert consultar("SELECT COUNT(*) FROM registro_processos WHERE processo = 'edição do vídeo: assistente' "
                     "AND detalhe = 'a foto do anúncio não veio'") == (0,)


def test_produto_ja_postado_fica_de_lado_e_vai_o_proximo_da_fonte(monkeypatch):
    # Escolha do Rafael (06/11, P167 1): o assistente confere o produto como o robô (P166 1). O já
    # postado (pelo robô ou marcado com Postei ✅) fica de lado, sem gastar a edição nem a IA.
    import robo_shopee_video as robo
    conteudos, ias = [], []
    bot = _com_edicao(monkeypatch, conteudos, ias)

    async def produtos(link):
        item = {"repetido": "22", "dorobo": "44"}.get(link.rsplit("/", 1)[-1], "33")
        return [{"nome": "Garrafa", "preco": 19.9, "comissao": 8.0, "imagem": "https://cf.shopee.com.br/g",
                 "item": item}], link

    monkeypatch.setattr(asv, "produtos_do_link", produtos)
    _fila(("novo", LEGENDA, "archive/novo.mp4", "2026-10-02 09:00"),
          ("dorobo", LEGENDA.replace("/abc", "/dorobo"), "archive/dorobo.mp4", "2026-10-02 10:00"),
          ("repetido", LEGENDA.replace("/abc", "/repetido"), "archive/repetido.mp4", "2026-10-02 11:00"))
    asv.registrar("antes", "enviado", "", item="22")
    asv.marcar_postado(asv.chave_do_envio("antes"))
    postado = robo.criar("video:9", None)
    robo.atualizar(postado, estado="postado", itens_do_video=["44"])
    assert asv.produtos_ja_postados() == {"22", "44"}
    assert rodar(asv.preparar_e_enviar(bot, 42)) == "postagem mandada no seu privado"
    assert set(ias) == {"archive/novo.mp4"} and len(conteudos) == 1
    assert consultar("SELECT COUNT(*) FROM shopee_video_enviados WHERE status = 'ja_postado' AND motivo = ?",
                     asv.JA_POSTADO) == (2,)
    assert consultar("SELECT COUNT(*), MAX(ok) FROM registro_processos WHERE processo = 'assistente: envio' "
                     "AND resultado = ?", asv.JA_POSTADO) == (2, None)
    # O registro diz onde estava o produto de cada vídeo de lado, como no robô.
    linhas = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DO_JA_POSTADO, "2000-01-01 00:00:00")
    assert sorted((r[2], r[3]) for r in linhas) == sorted([(robo.ONDE_JA_FOI["postado"], "assistente"),
                                                         (robo.POSTEI_NO_ASSISTENTE, "assistente")])
    # O vídeo de lado não volta.
    assert asv.proximo_video() is None


def test_produto_postado_ha_7_dias_volta_no_assistente(monkeypatch):
    # P307: o produto marcado com Postei ✅ há 7 dias ou mais volta em outro vídeo; a 6 dias, ainda não.
    from datetime import datetime
    conteudos, ias = [], []
    bot = _com_edicao(monkeypatch, conteudos, ias)

    async def produtos(link):
        return [{"nome": "Garrafa", "preco": 19.9, "comissao": 8.0, "imagem": "https://cf.shopee.com.br/g",
                 "item": "22"}], link

    monkeypatch.setattr(asv, "produtos_do_link", produtos)
    _fila(("repetido", LEGENDA, "archive/repetido.mp4", "2026-10-02 11:00"))
    asv.registrar("antes", "enviado", "", datetime(2026, 11, 1, 10, 0, tzinfo=asv.fuso_horario), item="22")
    asv.marcar_postado(asv.chave_do_envio("antes"), datetime(2026, 11, 1, 10, 0, tzinfo=asv.fuso_horario))
    assert asv.produtos_ja_postados(datetime(2026, 11, 7, 10, 0, tzinfo=asv.fuso_horario)) == {"22"}
    agora = datetime(2026, 11, 8, 10, 1, tzinfo=asv.fuso_horario)
    assert rodar(asv.preparar_e_enviar(bot, 42, agora)) == "postagem mandada no seu privado"
    assert set(ias) == {"archive/repetido.mp4"} and len(conteudos) == 1


def test_o_mesmo_video_nunca_vai_de_novo_nem_noutro_arquivo(monkeypatch):
    # P307: o vídeo que o robô ou o assistente já usou fica de lado pela assinatura da imagem, mesmo noutro arquivo e
    # com outro id na fonte, e vai o próximo; o mandado guarda a dele.
    import robo_shopee_video as robo
    conteudos, ias = [], []
    bot = _com_edicao(monkeypatch, conteudos, ias)
    copo, garrafa = "12.0;" + ";".join(["f0f0f0f0f0f0f0f0"] * 4), "30.0;" + ";".join(["0f0f0f0f0f0f0f0f"] * 4)
    assinaturas = {"copia.mp4": copo, "novo.mp4": garrafa}
    monkeypatch.setattr(robo.videos, "assinatura_do_video", lambda arquivo: assinaturas[os.path.basename(arquivo)])
    _fila(("novo", LEGENDA, "archive/novo.mp4", "2026-10-02 09:00"),
          ("copia", LEGENDA, "archive/copia.mp4", "2026-10-02 11:00"))
    postado = robo.criar("video:9", None)
    robo.atualizar(postado, estado="postado", assinatura=copo)
    assert rodar(asv.preparar_e_enviar(bot, 42)) == "postagem mandada no seu privado"
    assert set(ias) == {"archive/novo.mp4"} and len(conteudos) == 1
    assert consultar("SELECT status, motivo FROM shopee_video_enviados WHERE id_unico = 'copia'") == (
        "mesmo_video", asv.MESMO_VIDEO)
    assert consultar("SELECT assinatura FROM shopee_video_enviados WHERE id_unico = 'novo'") == (garrafa,)
    assert consultar("SELECT COUNT(*), MAX(ok) FROM registro_processos WHERE processo = 'assistente: envio' "
                     "AND resultado = ?", asv.MESMO_VIDEO) == (1, None)
    # O mandado aqui também não volta para o robô.
    assert asv.assinaturas_mandadas() == [garrafa] and robo.video_ja_usado(garrafa)


def test_nenhum_editado_avisa_sem_mandar_nada(monkeypatch):
    conteudos, ias = [], []
    bot = _com_edicao(monkeypatch, conteudos, ias)
    _fila(*[(f"v{i}", LEGENDA_VIDEO, f"archive/v{i}.mp4", f"2026-10-02 1{i}:00") for i in range(6)])
    resultado = rodar(asv.preparar_e_enviar(bot, 42))
    assert resultado.startswith(f"nenhum dos {asv.VIDEOS_POR_ENVIO} próximos vídeos deu para mandar")
    assert conteudos == [] and ias == [] and bot.mensagens == []
    # Tentou só VIDEOS_POR_ENVIO numa vez; o 6º fica para o próximo horário.
    assert asv.proximo_video()["id"] == "v0"


# --- Fontes ---

def _arquivo(caminho):
    with open(caminho, "wb") as f:
        f.write(b"video")
    return caminho


def test_viral_usa_a_fila_do_espiao_com_o_link_original():
    import db
    db.salvar_config("fila_clonagem", {"fila": [
        {"id": "c1", "caminho_video": _arquivo("temp/c1.mp4"), "link_original": "https://s.shopee.com.br/v1",
         "data_captura": "2026-10-05 09:00:00"},
        {"id": "c2", "caminho_video": "temp/sumiu.mp4", "link_original": "https://s.shopee.com.br/v2",
         "data_captura": "2026-10-05 10:00:00"},
    ]})
    video = asv.proximo_video("viral")
    assert video == {"id": "viral:c1", "arquivo": "temp/c1.mp4", "link": "https://s.shopee.com.br/v1", "nome": ""}
    asv.registrar("viral:c1", "enviado")
    assert asv.proximo_video("viral") is None


def test_viral_deixa_de_fora_o_que_veio_do_canal_afiliados_e_o_video_que_o_robo_levou_ao_canal():
    # Vídeo do Rafael (30/10, 22:28): o vídeo que o robô posta vai ao Canal Afiliados, o Espião
    # traz o canal para a fila do Viral, e o robô pegava de volta o que tinha postado (o loop).
    import db
    import pedidos_do_canal

    def _video(caminho, conteudo):
        with open(caminho, "wb") as f:
            f.write(conteudo)
        return caminho

    postado = _video("temp/postado.mp4", b"o video que o robo postou")
    pedidos_do_canal.pedir(1, postado, "https://sv.shopee.com.br/share-video/abc", [])
    db.salvar_config("fila_clonagem", {"fila": [
        {"id": "do_canal", "chat_origem": pedidos_do_canal.CANAL, "caminho_video": _video("temp/c1.mp4", b"outro"),
         "link_original": "https://br.shp.ee/post", "data_captura": "2026-10-30 21:52:00"},
        {"id": "espelhado", "chat_origem": "-1001", "caminho_video": _video("temp/c2.mp4", b"o video que o robo postou"),
         "link_original": "https://s.shopee.com.br/v2", "data_captura": "2026-10-30 21:51:00"},
        {"id": "de_fora", "chat_origem": "-1002", "caminho_video": _video("temp/c3.mp4", b"de um criador"),
         "link_original": "https://s.shopee.com.br/v3", "data_captura": "2026-10-30 21:00:00"},
    ]})
    # O do canal nem entra na lista; o mesmo arquivo do robô, vindo de outro grupo, fica de fora na escolha.
    assert [c[0] for c in asv.candidatos_nao_usados("viral")] == ["viral:espelhado", "viral:de_fora"]
    assert asv.proximo_video("viral")["id"] == "viral:de_fora"


def test_viral_deixa_de_fora_o_item_cujo_arquivo_e_de_outro_clone():
    # 07/11, 15:57 e 16:11 (o Rafael: "vc está comparando 2 vídeos diferentes"): o Espião salvava o
    # vídeo com o primeiro nome livre ("temp_clone_ (N)"). O vídeo do clone de 06/11 14:50 foi postado
    # no Viral e saiu do disco, o clone de 07/11 11:13 pegou o mesmo nome, e o item antigo, que fica na
    # fila até o fim do dia, apontava para o vídeo novo: o robô juntou o link de um com o arquivo do outro.
    import db
    antigo, novo = 1793987407, 1794060832
    caminho = _arquivo("temp/temp_clone_ (17).mp4")
    os.utime(caminho, (novo - 5, novo - 5))                      # escrito na captura do clone novo
    proprio = _arquivo("temp/temp_clone_clone_1794079659_9443.mp4")   # o id no nome: o arquivo é dele
    db.salvar_config("fila_clonagem", {"fila": [
        {"id": f"clone_{antigo}_2982", "caminho_video": caminho, "link_original": "https://br.shp.ee/antigo",
         "data_captura": "2026-11-06 14:50:07"},
        {"id": f"clone_{novo}_5595", "caminho_video": caminho, "link_original": "https://s.shopee.com.br/novo",
         "data_captura": "2026-11-07 11:13:52"},
        {"id": "clone_1794079659_9443", "caminho_video": proprio, "link_original": "https://s.shopee.com.br/outro",
         "data_captura": "2026-11-07 16:27:39"},
    ]})
    assert [c[0] for c in asv.candidatos_nao_usados("viral")] == [
        "viral:clone_1794079659_9443", f"viral:clone_{novo}_5595"]
    assert not asv.arquivo_do_proprio_clone({"id": f"clone_{antigo}_2982", "caminho_video": caminho})
    # Sem a hora no id, ou sem o arquivo, não há o que comparar.
    assert asv.arquivo_do_proprio_clone({"id": "c1", "caminho_video": caminho})
    assert asv.arquivo_do_proprio_clone({"id": f"clone_{antigo}_2982", "caminho_video": "temp/sumiu.mp4"})


def test_canal_afiliados_pula_imagem_e_usa_a_legenda():
    inserir("CREATE TABLE fila_postagens (id INTEGER PRIMARY KEY AUTOINCREMENT, id_unico TEXT UNIQUE, "
            "caminho_video TEXT, legenda TEXT)")
    inserir("INSERT INTO fila_postagens (id_unico, caminho_video, legenda) VALUES (?, ?, ?)",
            "p1", _arquivo("temp/p1.mp4"), LEGENDA)
    inserir("INSERT INTO fila_postagens (id_unico, caminho_video, legenda) VALUES (?, ?, ?)",
            "p2", _arquivo("temp/p2.jpg"), LEGENDA)
    video = asv.proximo_video("principal")
    assert video["id"] == "principal:p1" and video["nome"] == "Garrafa Térmica 🧊"


def test_grupo_publico_e_ids_de_fontes_diferentes_nao_colidem():
    inserir("CREATE TABLE fila_publico (id_unico TEXT PRIMARY KEY, legenda TEXT, caminho_arquivo TEXT, "
            "data_captura TEXT)")
    inserir("INSERT INTO fila_publico VALUES (?, ?, ?, ?)", "x1", LEGENDA, _arquivo("temp/x1.mp4"), "2026-10-05")
    _fila(("x1", LEGENDA, "archive/x1.mp4", "2026-10-05 10:00"))
    asv.registrar("x1", "enviado")                                         # o Autoral x1 já foi
    assert asv.proximo_video("publico")["id"] == "publico:x1"
    assert asv.proximo_video("autorais") is None


def test_fonte_sem_fila_ou_desconhecida_nao_quebra():
    assert asv.proximo_video("principal") is None                          # tabela nem existe
    _fila(("a1", LEGENDA, "archive/a1.mp4", "2026-10-05 10:00"))
    assert asv.proximo_video("inventada")["id"] == "a1"                    # cai no padrão (Autorais)


def test_sem_video_diz_qual_fonte_esta_vazia():
    assert "Viral (Espião) 🕵️" in rodar(asv.preparar_e_enviar(Bot(), 42, fonte="viral"))



# --- Bebida alcoólica e airsoft (e-mail da Shopee de 26/10/2026) ---

def test_bebida_alcoolica_tem_os_avisos_no_fim_do_titulo_dentro_dos_150():
    # Escolha do Rafael (P43): o robô põe os avisos; no app o título é a legenda, de 150.
    titulo = "Kit Cerveja Artesanal 🍺 " + " ".join(f"#cerveja{i}" for i in range(20))
    resposta = json.dumps({"violacao": False, "bebida_alcoolica": True, "titulo": titulo, "comentario": "c"})
    textos = asv.ler_resposta(resposta)
    assert textos["bebida_alcoolica"] is True
    assert textos["titulo"].startswith("Kit Cerveja Artesanal 🍺 #cerveja0")
    assert textos["titulo"].endswith("Produto destinado a adultos. Consumo proibido para menores de 18 anos. "
                                     "Beba com moderação.")
    assert asv.TITULO_MAX - 12 <= asv.tamanho_no_app(textos["titulo"]) <= asv.TITULO_MAX
    # Sem bebida alcoólica (ou na dúvida, sem o true), o título fica como sempre.
    for valor in (False, "true", None):
        textos = asv.ler_resposta(json.dumps({"bebida_alcoolica": valor, "titulo": titulo}))
        assert textos["bebida_alcoolica"] is False and asv.TEXTO_DOS_AVISOS not in textos["titulo"]


def test_regras_novas_de_bebida_alcoolica_e_airsoft_no_resumo_e_no_pedido():
    diretrizes = asv.ler_diretrizes()
    assert "bebida alcoólica\n   (venda ou consumo)" not in diretrizes and "Airsoft" in diretrizes
    for aviso in asv.AVISOS_DE_ALCOOL:
        assert aviso in " ".join(diretrizes.split())
    prompt = asv.montar_prompt()
    assert '"bebida_alcoolica": false' in prompt and "Bebida alcoólica sozinha não é violação" in prompt


def test_mensagem_da_bebida_alcoolica_pede_para_deixar_a_capa_e_os_avisos():
    texto = asv.montar_mensagem({**TEXTOS, "bebida_alcoolica": True}, [], "https://s.shopee.com.br/abc")
    assert "🔞 <b>Bebida alcoólica:</b>" in texto and "Deixe a capa no 1º quadro" in texto
    assert "🔞" not in asv.montar_mensagem(TEXTOS, [], "https://s.shopee.com.br/abc")


def test_bebida_alcoolica_vai_editada_com_os_avisos_na_capa(monkeypatch):
    # O caminho da P43, que volta quando a página oficial trouxer a regra nova (P111).
    monkeypatch.setattr(asv, "BEBIDA_EM_ESPERA", False)
    conteudos, ias, editados = [], [], []
    bot = _com_edicao(monkeypatch, conteudos, ias, editados)

    async def gerar(arquivo, nome="", leves=False):
        ias.append(arquivo)
        return {**TEXTOS, "bebida_alcoolica": True}
    monkeypatch.setattr(asv, "gerar_textos", gerar)
    _fila(("cerveja", LEGENDA, "archive/cerveja.mp4", "2026-10-02 10:00"))
    assert rodar(asv.preparar_e_enviar(bot, 42)) == "postagem mandada no seu privado"
    assert [e[-1] for e in editados] == [False, True] and conteudos == [b"capa com os avisos"]
    assert consultar("SELECT resultado FROM registro_processos WHERE processo = 'edição do vídeo: assistente' "
                     "ORDER BY rowid DESC LIMIT 1") == (edicao_video.COM_LEGENDAS + edicao_video.COM_OS_AVISOS,)


def test_bebida_alcoolica_sem_a_edicao_fica_de_lado_e_vai_o_proximo(monkeypatch):
    # Sem a edição não há como pôr os avisos na capa: o vídeo de bebida alcoólica fica de lado
    # (o caminho da P43, que volta quando a página oficial trouxer a regra nova, P111).
    monkeypatch.setattr(asv, "BEBIDA_EM_ESPERA", False)
    ias = []

    async def gerar(arquivo, nome="", leves=False):
        ias.append(arquivo)
        return {**TEXTOS, "bebida_alcoolica": "cerveja" in arquivo}

    async def produtos(link):
        return [], link
    monkeypatch.setattr(asv, "gerar_textos", gerar)
    monkeypatch.setattr(asv, "produtos_do_link", produtos)
    bot = Bot()
    # O mais novo (a cerveja) vem primeiro, fica de lado, e o copo vai na mesma hora.
    _fila(("copo", LEGENDA, "archive/copo.mp4", "2026-10-02 09:00"),
          ("cerveja", LEGENDA, "archive/cerveja.mp4", "2026-10-02 10:00"))
    assert rodar(asv.preparar_e_enviar(bot, 42)) == "postagem mandada no seu privado"
    assert bot.videos == [(42, "copo.mp4")] and asv.proximo_video() is None


def test_bebida_alcoolica_em_espera_fica_de_lado_e_vai_o_proximo(monkeypatch):
    # Escolha do Rafael (31/10, P111): a página oficial das diretrizes da Shopee Vídeo ainda
    # proíbe divulgar bebida alcoólica; até ela trazer a regra nova, o vídeo de bebida
    # alcoólica fica de lado, mesmo com a edição ligada, e vai o próximo.
    assert asv.BEBIDA_EM_ESPERA
    conteudos, ias, editados = [], [], []
    bot = _com_edicao(monkeypatch, conteudos, ias, editados)

    async def gerar(arquivo, nome="", leves=False):
        ias.append(arquivo)
        return {**TEXTOS, "bebida_alcoolica": "cerveja" in arquivo}
    monkeypatch.setattr(asv, "gerar_textos", gerar)
    _fila(("copo", LEGENDA, "archive/copo.mp4", "2026-10-02 09:00"),
          ("cerveja", LEGENDA, "archive/cerveja.mp4", "2026-10-02 10:00"))
    assert rodar(asv.preparar_e_enviar(bot, 42)) == "postagem mandada no seu privado"
    # A cerveja não ganha a capa dos avisos: só o copo vai, editado sem os avisos.
    assert list(dict.fromkeys(os.path.basename(arquivo) for arquivo in ias)) == ["cerveja.mp4", "copo.mp4"]
    assert all(not avisos for _foto, _produto, avisos in editados) and b"capa com os avisos" not in conteudos
    assert consultar("SELECT status, motivo FROM shopee_video_enviados WHERE id_unico = 'cerveja'") == (
        "bebida_em_espera", asv.MOTIVO_BEBIDA_EM_ESPERA)
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = 'assistente: envio' "
                     "ORDER BY rowid LIMIT 1") == (asv.SEM_BEBIDA, None)


def test_bebida_em_espera_so_com_o_true_da_ia_e_a_espera_ligada(monkeypatch):
    assert asv.bebida_em_espera({"bebida_alcoolica": True})
    for textos in ({"bebida_alcoolica": False}, {"bebida_alcoolica": "true"}, {}, None):
        assert not asv.bebida_em_espera(textos)
    monkeypatch.setattr(asv, "BEBIDA_EM_ESPERA", False)
    assert not asv.bebida_em_espera({"bebida_alcoolica": True})


def test_resumo_das_diretrizes_segue_a_pagina_oficial_e_a_politica_de_relevancia():
    # P111 (31/10): o resumo que a IA recebe ganhou os detalhes da página oficial e a regra dos
    # produtos irrelevantes da Política de Relevância de Produto (o vídeo do Rafael de 31/10).
    diretrizes = " ".join(asv.ler_diretrizes().split())
    for trecho in ("beijo erótico", "print de conversa sem autorização", "procedimento estético que dá aflição",
                   "fingir ser a loja oficial da marca", "logo ou tela de outro app",
                   "título, capa ou descrição que prometem", "por 3, 7 ou 30 dias ou para sempre",
                   "Com mais da metade dos produtos do vídeo irrelevantes, o vídeo é excluído e a conta ganha 1 ponto",
                   "com menos, só os links irrelevantes saem", "em espera desde 31/10/2026"):
        assert trecho in diretrizes, trecho
    assert "15 e 30 dias" not in diretrizes


def test_video_mudo_pede_musica_da_shopee_na_postagem(monkeypatch):
    # Escolha do Rafael (P48, 27/10): o vídeo sem som ganha uma música da Shopee na hora de
    # postar; no modo assistente, quem põe é ele, e a mensagem lembra.
    texto = asv.montar_mensagem(TEXTOS, [], "https://s.shopee.com.br/abc", mudo=True)
    assert "🔇 <b>Vídeo sem som:</b>" in texto and "Adicionar Música" in texto
    assert texto.index("Vídeo sem som") < texto.index("Título")
    assert "🔇" not in asv.montar_mensagem(TEXTOS, [], "https://s.shopee.com.br/abc")
    _preparar(monkeypatch, TEXTOS)
    conferidos = []

    def mudo(caminho, timeout=120):
        conferidos.append(os.path.basename(caminho))
        return True
    monkeypatch.setattr(asv.videos, "mudo", mudo)
    bot = Bot()
    assert rodar(asv.preparar_e_enviar(bot, 42)) == "postagem mandada no seu privado"
    assert conferidos == ["novo.mp4"] and "Vídeo sem som" in bot.mensagens[-1][1]


def test_envios_do_dia_seguem_a_escada_dos_pontos():
    # Escolha do Rafael (03/11, P145): o teto pelos pontos de penalidade vale também para o modo assistente.
    import apelacoes_shopee_video as apelacoes
    import db
    config = {"limite_min": 4, "limite_max": 6, "inicio": 9, "fim": 21}
    db.salvar_config(apelacoes.CHAVE_DA_SAUDE, {"saude_pontos": 9, "saude_lida_em": "2026-11-03 10:00:00"})
    assert asv.quantos_hoje(config, "2026-11-10") == 2 and len(asv.planejar(config, "2026-11-10")) == 2
    db.salvar_config(apelacoes.CHAVE_DA_SAUDE, {"saude_pontos": 2, "saude_lida_em": "2026-11-03 10:00:00"})
    assert 4 <= asv.quantos_hoje(config, "2026-11-10") <= 6


# --- Postei ✅ (P156 1) ---

class BotComBotao(Bot):
    def __init__(self):
        super().__init__()
        self.botoes = []

    async def send_message(self, chat_id, text, **kw):
        await super().send_message(chat_id, text, **kw)
        self.botoes.append(kw.get("reply_markup"))


def test_video_mandado_cobrindo_o_robo_tem_o_postei_e_conta_no_plano_dele(monkeypatch):
    # Escolha do Rafael (05/11, P156 1): sem o celular, o assistente cobre o robô no privado; cada
    # vídeo ganha o Postei ✅, e o que ele marca conta no plano do dia do robô.
    _preparar(monkeypatch, TEXTOS)
    bot = BotComBotao()
    assert rodar(asv.preparar_e_enviar(bot, 42, _as("14:00"), cobrindo=True)) == "postagem mandada no seu privado"
    [teclado] = bot.botoes
    [[botao]] = teclado.inline_keyboard
    chave = asv.chave_do_envio("novo")
    assert botao.text == "Postei ✅" and botao.callback_data == asv.CALLBACK_POSTEI + chave
    assert len(botao.callback_data.encode()) <= 64
    texto = bot.mensagens[0][1]
    assert "5️⃣ <b>Postou?</b> Toque em <b>Postei ✅</b>" in texto and "conta no plano de hoje" in texto
    assert texto.index("4️⃣") < texto.index("5️⃣")
    assert asv.sem_postei_cobrindo_o_robo("2026-10-05") == 1 and asv.postados_cobrindo_o_robo("2026-10-05") == []
    assert asv.marcar_postado(chave, _as("14:30")) == (asv.MARCADO, True)
    assert asv.marcar_postado(chave, _as("14:40")) == (asv.JA_MARCADO, True)
    assert asv.marcar_postado("0" * 16, _as("14:40")) == (asv.NAO_ACHADO, False)
    assert consultar("SELECT cobrindo, postado_em FROM shopee_video_enviados WHERE id_unico = 'novo'") == (
        "1", "2026-10-05 14:30:00")
    assert asv.postados_cobrindo_o_robo("2026-10-05") == ["novo"] and asv.postados_cobrindo_o_robo("2026-10-06") == []
    assert asv.sem_postei_cobrindo_o_robo("2026-10-05") == 0


def test_video_mandado_com_o_robo_no_ar_tem_o_postei_mas_nao_conta_no_plano_dele(monkeypatch):
    _preparar(monkeypatch, TEXTOS)
    bot = BotComBotao()
    assert rodar(asv.preparar_e_enviar(bot, 42, _as("14:00"))) == "postagem mandada no seu privado"
    assert bot.botoes[0].inline_keyboard[0][0].text == "Postei ✅"
    assert "5️⃣ <b>Postou?</b>" in bot.mensagens[0][1] and "conta no plano" not in bot.mensagens[0][1]
    assert asv.marcar_postado(asv.chave_do_envio("novo"), _as("14:30")) == (asv.MARCADO, False)
    assert asv.postados_cobrindo_o_robo("2026-10-05") == [] and asv.sem_postei_cobrindo_o_robo("2026-10-05") == 0


def test_tabela_dos_enviados_de_antes_ganha_as_colunas_do_postei():
    # No servidor a tabela já existe com as 4 colunas de antes, e o robô também grava nela.
    inserir("CREATE TABLE shopee_video_enviados (id_unico TEXT PRIMARY KEY, enviado_em TEXT, status TEXT, motivo TEXT)")
    inserir("INSERT INTO shopee_video_enviados VALUES ('velho', '2026-10-01 10:00:00', 'enviado', '')")
    asv.registrar("novo", "enviado", "", _as("14:00"), cobrindo=True)
    asv.registrar("do_robo", "robo", "rascunho do robô", _as("14:05"))
    assert consultar("SELECT cobrindo FROM shopee_video_enviados WHERE id_unico = 'novo'") == ("1",)
    assert consultar("SELECT status, cobrindo FROM shopee_video_enviados WHERE id_unico = 'do_robo'") == ("robo", "")
    assert asv.marcar_postado(asv.chave_do_envio("velho"), _as("15:00")) == (asv.MARCADO, False)
    assert asv.marcar_postado(asv.chave_do_envio("do_robo"), _as("15:00")) == (asv.NAO_ACHADO, False)


def test_video_mandado_guarda_o_produto_e_o_postei_o_conta_como_postado():
    # Escolha do Rafael (06/11, P166 1): o robô não repete o produto que o Rafael postou pelo
    # assistente; o envio guarda o número do produto, e só o marcado com Postei ✅ conta.
    from datetime import datetime
    agora = datetime(2026, 11, 5, 10, 0, tzinfo=asv.fuso_horario)
    asv.registrar("v1", "enviado", "", agora, item="123")
    asv.registrar("v2", "enviado", "", agora, item="456")
    asv.registrar("v3", "enviado", "", agora)
    assert asv.itens_postados() == []
    assert asv.marcar_postado(asv.chave_do_envio("v1"), agora)[0] == asv.MARCADO
    assert asv.marcar_postado(asv.chave_do_envio("v3"), agora)[0] == asv.MARCADO
    assert asv.itens_postados() == ["123"]
    # Com desde, só os marcados dali em diante: os 7 dias em que o produto não volta (P307).
    assert asv.itens_postados("2026-11-05 10:00:00") == ["123"] and asv.itens_postados("2026-11-05 10:00:01") == []


# --- O nome de cada produto no vídeo (P265 1) ---

def test_nomes_da_ia_passam_pela_regua():
    # Vídeos do Rafael das 15:26 e 15:27 (21/11): o nome do cartão do produto, curto, sem marca (diretriz 7) e sem
    # promoção (diretriz 14). O que não passa, ou repete o nome de outro, fica com o do anúncio.
    nomes = ["Caneca Personagem X Presente Geek Nerd Colecionável", "Garrafa Térmica Marca Y 1L",
             "Kit Panelas Antiaderente 5 Peças", "Fone Bluetooth Sem Fio", "Escova Secadora 3 em 1"]
    resposta = "Aqui está: " + json.dumps([
        {"n": 1, "nome": "Caneca Geek Colecionável para Presente ☕", "tirados": ["Personagem X"]},
        {"n": 2, "nome": "Garrafa Térmica Marca Y que Mantém Gelado", "tirados": ["Marca Y"]},
        {"n": 3, "nome": "Kit de Panelas com Frete Grátis 🍳", "tirados": []},
        {"n": 4, "nome": "Fone 🎧", "tirados": []},
        {"n": 5, "nome": "Caneca Geek Colecionável para Presente ☕", "tirados": []},
        {"n": 9, "nome": "Produto que não está na lista", "tirados": []},
    ], ensure_ascii=False)
    assert asv.ler_os_nomes(resposta, nomes) == {nomes[0]: "Caneca Geek Colecionável para Presente ☕"}
    assert asv.ler_os_nomes("sem a lista", nomes) == {} and asv.ler_os_nomes(None, nomes) == {}


def test_nome_comprido_demais_fica_de_fora():
    # O nome tem de caber no cartão do vídeo: até LETRAS_MAXIMAS_DO_NOME no contador da Shopee (o emoji vale 2).
    assert asv.nome_valido("Garrafa Térmica que Mantém Gelado 🧊")
    assert not asv.nome_valido("Garrafa Térmica de Inox Que Mantém Gelado o Dia Inteiro 🧊")
    assert not asv.nome_valido("Garrafa Térmica #promo Gelada 🧊")


def test_nomes_no_video_pede_uma_vez_so_para_a_lista(monkeypatch):
    pedidos = []

    async def gerar(prompt, imagens=None):
        pedidos.append(prompt)
        return json.dumps([{"n": 1, "nome": "Caneca Geek Colecionável para Presente ☕", "tirados": []},
                           {"n": 2, "nome": "Garrafa Térmica que Mantém Gelado 🧊", "tirados": []}],
                          ensure_ascii=False)

    monkeypatch.setattr(asv.api_gemini, "gerar_texto_gemini", gerar)
    # O mesmo anúncio duas vezes e o nome vazio não vão ao pedido.
    nomes = rodar(asv.nomes_no_video(["Caneca A", "Garrafa B", "Caneca A", ""]))
    assert nomes == {"Caneca A": "Caneca Geek Colecionável para Presente ☕",
                     "Garrafa B": "Garrafa Térmica que Mantém Gelado 🧊"}
    assert len(pedidos) == 1 and "1. Caneca A\n2. Garrafa B" in pedidos[0]
    assert "diretriz 7" in pedidos[0] and "diretriz 14" in pedidos[0] and "Fiel ao anúncio" in pedidos[0]


def test_sem_resposta_da_ia_cada_produto_fica_com_o_do_anuncio():
    assert rodar(asv.nomes_no_video(["Caneca A"])) == {} and rodar(asv.nomes_no_video([])) == {}


def test_mensagem_traz_o_nome_de_cada_produto_para_colar():
    # O assistente manda o nome junto, para o Rafael colar em Nome do produto, na janela do Adicionar (P265 1).
    produtos = [{"nome": "Caneca A", "preco": 19.9, "comissao": 8.0},
                {"nome": "Garrafa B", "preco": 29.9, "comissao": 5.0}]
    texto = asv.montar_mensagem(TEXTOS, produtos, "https://s.shopee.com.br/abc",
                                nomes={"Caneca A": "Caneca Geek & Presente ☕"})
    assert "🏷️ <b>Nome no vídeo:</b>" in texto
    assert "1. <code>Caneca Geek &amp; Presente ☕</code>\n2. fica o nome do anúncio" in texto
    # No passo de postar: depois do título e antes do comentário.
    assert texto.index("<code>Copo &lt;Térmico") < texto.index("Nome no vídeo") < texto.index("4️⃣")
    um = asv.montar_mensagem(TEXTOS, produtos[:1], "https://s.shopee.com.br/abc",
                             nomes={"Caneca A": "Caneca Geek de Presente ☕"})
    assert "\n<code>Caneca Geek de Presente ☕</code>\n" in um
    assert "Nome no vídeo" not in asv.montar_mensagem(TEXTOS, produtos, "https://s.shopee.com.br/abc")


def test_envio_manda_o_nome_da_ia_para_colar(monkeypatch):
    _preparar(monkeypatch, TEXTOS)

    async def gerar(prompt, imagens=None):
        return '[{"n": 1, "nome": "Garrafa Térmica que Mantém Gelado 🧊", "tirados": []}]'

    monkeypatch.setattr(asv.api_gemini, "gerar_texto_gemini", gerar)
    bot = Bot()
    assert rodar(asv.preparar_e_enviar(bot, 42, _as("14:00"))) == "postagem mandada no seu privado"
    assert "<code>Garrafa Térmica que Mantém Gelado 🧊</code>" in bot.mensagens[0][1]


# --- Grupo dos amigos (P271 2 a P277 1) ---

class BotDoGrupo:
    """O bot falso do grupo dos amigos: guarda cada envio com o destino e a mensagem a que responde."""

    def __init__(self):
        self.envios, self.proximo = [], 100

    def _guardar(self, tipo, chat_id, conteudo, kw):
        self.proximo += 1
        resposta = kw.get("reply_parameters")
        self.envios.append({"tipo": tipo, "chat": chat_id, "conteudo": conteudo, "id": self.proximo,
                            "responde_a": getattr(resposta, "message_id", None), "botoes": kw.get("reply_markup")})
        return SimpleNamespace(message_id=self.proximo)

    async def send_message(self, chat_id, text, **kw):
        return self._guardar("mensagem", chat_id, text, kw)

    async def send_video(self, chat_id, video, **kw):
        return self._guardar("video", chat_id, kw.get("caption", ""), kw)


AMIGO = {"id": 7, "mencao": "@ana_teste", "grupo": -1001, "responder_a": 55}
LEGENDA_2 = LEGENDA.replace("https://s.shopee.com.br/abc", "https://s.shopee.com.br/def")


def _preparar_do_amigo(monkeypatch, textos=TEXTOS):
    """
    Dois vídeos na fonte, cada um com um produto (o do link abc é o 11, o do def é o 22). O link convertido sai sem a
    rede: https://s.shopee.com.br/rafa-ETIQUETA/o fim do link da fonte.
    """
    async def gerar(arquivo, nome="", leves=False):
        return textos

    async def produtos(link):
        item = "11" if link.endswith("abc") else "22"
        return [{"nome": "Garrafa", "preco": 19.9, "comissao": 8.0, "item": item}], link

    async def converter(link, etiqueta):
        return f"https://s.shopee.com.br/rafa-{etiqueta}/{link.rsplit('/', 1)[-1]}"

    monkeypatch.setattr(asv, "gerar_textos", gerar)
    monkeypatch.setattr(asv, "produtos_do_link", produtos)
    monkeypatch.setattr(asv.api_shopee, "converter_link_shopee", converter)
    _fila(("novo", LEGENDA, "archive/novo.mp4", "2026-10-02 10:00"),
          ("velho", LEGENDA_2, "archive/velho.mp4", "2026-10-01 10:00"))


def test_amigo_recebe_no_grupo_em_resposta_ao_pedido_e_o_video_nao_vai_a_mais_ninguem(monkeypatch):
    # Decisão do Rafael (P272 2 e P277 1): o vídeo vai no grupo, em resposta à mensagem do pedido, com os passos em
    # resposta ao vídeo e sem o Postei ✅, que é do plano dele; cada vídeo vai a uma pessoa só (P271 2).
    _preparar_do_amigo(monkeypatch)
    bot = BotDoGrupo()
    assert rodar(asv.preparar_para_o_amigo(bot, 42, AMIGO, _as("14:00"))) == asv.MANDADO_AO_AMIGO
    video, passos = bot.envios
    assert video["tipo"] == "video" and video["chat"] == -1001 and video["responde_a"] == 55
    assert "@ana_teste" in video["conteudo"]
    assert passos["chat"] == -1001 and passos["responde_a"] == video["id"] and passos["botoes"] is None
    assert passos["conteudo"].startswith("🎬 @ana_teste, a sua postagem para a Shopee Vídeo está pronta")
    assert "4️⃣" in passos["conteudo"] and "5️⃣" not in passos["conteudo"] and "Postei" not in passos["conteudo"]
    assert consultar("SELECT status, item, amigo FROM shopee_video_enviados WHERE id_unico = 'novo'") == (
        "enviado", "11", "7")
    # O vídeo não volta para ninguém (nem para o Rafael), e o do amigo não conta no plano do dia do assistente.
    assert asv.proximo_video()["id"] == "velho" and asv.enviados_hoje(_as("15:00")) == 0
    assert asv.enviados_aos_amigos(_as("15:00")) == (1, 1) and asv.itens_do_amigo(7) == {"11"}
    assert asv.itens_postados() == []
    # A mensagem do Rafael continua com o Postei ✅.
    assert "5️⃣ <b>Postou?</b>" in asv.montar_mensagem(TEXTOS, [], "https://s.shopee.com.br/abc")


def test_pedido_do_rafael_no_grupo_vai_ao_privado_com_o_postei_e_ao_grupo(monkeypatch):
    # P281 1: o vídeo que o Rafael pede pelo botão do grupo é preparado como o Enviar 1 Agora e vai ao privado, com o
    # Postei ✅, e o mesmo vídeo ao grupo, em resposta ao pedido, com os passos sem o Postei ✅. Fica anotado como dele
    # (sem amigo): o produto conta para não repetir para ele (P166 1).
    _preparar_do_amigo(monkeypatch)
    bot = BotDoGrupo()
    rafael = {"id": 42, "mencao": "@rafa_teste", "grupo": -1001, "responder_a": 77}
    assert rodar(asv.preparar_e_enviar(bot, 42, _as("14:00"), no_grupo=rafael)) == asv.MANDADO_NO_PRIVADO
    video, passos, no_grupo, passos_no_grupo = bot.envios
    assert (video["tipo"], video["chat"], passos["chat"]) == ("video", 42, 42)
    assert passos["botoes"] is not None and "5️⃣ <b>Postou?</b>" in passos["conteudo"]
    assert (no_grupo["tipo"], no_grupo["chat"], no_grupo["responde_a"]) == ("video", -1001, 77)
    assert "@rafa_teste" in no_grupo["conteudo"]
    assert passos_no_grupo["responde_a"] == no_grupo["id"] and passos_no_grupo["botoes"] is None
    assert passos_no_grupo["conteudo"].startswith("🎬 @rafa_teste, a sua postagem") and \
        "Postei" not in passos_no_grupo["conteudo"]
    assert consultar("SELECT status, item, amigo FROM shopee_video_enviados WHERE id_unico = 'novo'") == (
        "enviado", "11", "")
    # Pelo privado (o Enviar 1 Agora), só no privado.
    bot = BotDoGrupo()
    assert rodar(asv.preparar_e_enviar(bot, 42, _as("14:05"))) == asv.MANDADO_NO_PRIVADO
    assert {envio["chat"] for envio in bot.envios} == {42}


def test_link_que_vai_ao_grupo_dos_amigos_e_o_do_rafael_com_a_etiqueta_do_grupo(monkeypatch):
    # Pedido do Rafael (22/11): o link dos passos no grupo é o dele, convertido com a etiqueta do grupo, para a compra
    # de quem o abre, nos 7 dias da Shopee, dar a comissão a ele. No privado dele, o link continua o da fonte.
    _preparar_do_amigo(monkeypatch)
    bot = BotDoGrupo()
    assert rodar(asv.preparar_para_o_amigo(bot, 42, AMIGO, _as("14:00"))) == asv.MANDADO_AO_AMIGO
    passos = bot.envios[-1]["conteudo"]
    assert "🔗 https://s.shopee.com.br/rafa-grupoamigos/abc\n" in passos
    assert "s.shopee.com.br/abc" not in passos
    bot = BotDoGrupo()
    rafael = {"id": 42, "mencao": "@rafa_teste", "grupo": -1001, "responder_a": 77}
    assert rodar(asv.preparar_e_enviar(bot, 42, _as("14:05"), no_grupo=rafael)) == asv.MANDADO_NO_PRIVADO
    no_privado, no_grupo = bot.envios[1], bot.envios[3]
    assert no_privado["chat"] == 42 and "🔗 https://s.shopee.com.br/def\n" in no_privado["conteudo"]
    assert no_grupo["chat"] == -1001 and "🔗 https://s.shopee.com.br/rafa-grupoamigos/def\n" in no_grupo["conteudo"]


# --- Os links a mais (P283 1) ---

MAIS_DOIS = [{"nome": "Garrafa Loja B", "preco": 21.0, "comissao": 12.0, "endereco": "https://shopee.com.br/product/2/22",
              "item": "22"},
             {"nome": "Garrafa Loja C", "preco": 20.0, "comissao": 10.0, "endereco": "https://shopee.com.br/product/3/33",
              "item": "33"}]


def test_links_a_mais_vao_depois_do_produto_do_video_no_privado_e_no_grupo(monkeypatch):
    # P283 1: até 6 links, o do vídeo e o mesmo produto em outras lojas, para o Rafael e os amigos; cada link a mais
    # com o link curto na etiqueta de quem abre (o do Rafael no privado, o do grupo no grupo).
    _preparar_do_amigo(monkeypatch)
    pedidos = []

    async def links(video, produtos, do_rafael=True):
        pedidos.append(do_rafael)
        return [dict(p) for p in MAIS_DOIS]

    async def converter(link, etiqueta, avisar_falha=True):
        return f"https://s.shopee.com.br/{etiqueta}-{link.rsplit('/', 1)[-1]}"

    monkeypatch.setattr(asv, "links_a_mais", links)
    monkeypatch.setattr(asv.api_shopee, "converter_link_shopee", converter)
    bot = BotDoGrupo()
    assert rodar(asv.preparar_para_o_amigo(bot, 42, AMIGO, _as("14:00"))) == asv.MANDADO_AO_AMIGO
    passos = bot.envios[-1]["conteudo"]
    assert ("1. Garrafa: R$ 19,90, comissão 8%\n🔗 https://s.shopee.com.br/grupoamigos-abc\n"
            "2. Garrafa Loja B: R$ 21,00, comissão 12%\n🔗 https://s.shopee.com.br/grupoamigos-22\n"
            "3. Garrafa Loja C: R$ 20,00, comissão 10%\n🔗 https://s.shopee.com.br/grupoamigos-33\n") in passos
    assert "Abra cada link" in passos and "os produtos, na ordem da lista" in passos
    bot = Bot()
    assert rodar(asv.preparar_e_enviar(bot, 42, _as("14:05"))) == asv.MANDADO_NO_PRIVADO
    privado = bot.mensagens[0][1]
    assert "🔗 https://s.shopee.com.br/def\n2. Garrafa Loja B" in privado
    assert "https://s.shopee.com.br/shopeevideo-22" in privado and "grupoamigos" not in privado
    # Os do amigo não seguem os produtos a mais do robô (a conta é dele); os do Rafael, sim.
    assert pedidos == [False, True]


def test_sem_links_a_mais_a_mensagem_fica_como_antes(monkeypatch):
    _preparar(monkeypatch, TEXTOS)

    async def nenhum(video, produtos, do_rafael=True):
        return []

    monkeypatch.setattr(asv, "links_a_mais", nenhum)
    bot = Bot()
    assert rodar(asv.preparar_e_enviar(bot, 42, _as("14:00"))) == asv.MANDADO_NO_PRIVADO
    assert "2️⃣ <b>Favorite o produto</b> ❤️\nGarrafa: R$ 19,90" in bot.mensagens[0][1]


def _oferta(nome, preco, comissao, item):
    return {"productName": nome, "priceMin": str(preco), "commissionRate": str(comissao / 100),
            "productLink": f"https://shopee.com.br/product/9/{item}", "itemId": item, "imageUrl": f"foto-{item}"}


def test_links_a_mais_buscam_o_mesmo_produto_e_a_ia_confere_pela_foto(monkeypatch):
    # A busca da API pelo nome; ficam os de nome parecido, até 25% mais caros, do que paga mais por venda para o que
    # paga menos; a IA confirma pela foto, e o de outra cor fica de fora (P142 1). No máximo 5 além do do vídeo.
    import postador_shopee_video as ps
    import robo_shopee_video as robo
    original = {"nome": "Garrafa Térmica Inox 500ml Azul", "preco": 50.0, "comissao": 10.0, "imagem": "foto-1",
                "item": "1"}
    ofertas = [_oferta("Garrafa Térmica Inox 500ml Azul Loja A", 55.0, 20.0, "2"),
               _oferta("Garrafa Térmica Inox 500ml Azul Loja B", 52.0, 30.0, "3"),
               _oferta("Garrafa Térmica Inox 500ml Azul Cara", 70.0, 30.0, "4"),
               _oferta("Cadeira de Escritório Giratória", 50.0, 30.0, "5"),
               _oferta("Garrafa Térmica Inox 500ml Azul Rosa", 51.0, 25.0, "6"),
               _oferta("Garrafa Térmica Inox 500ml Azul", 50.0, 10.0, "1")]
    conferidos = []

    async def buscar(termo, limite=10, sort_type=2, **kw):
        return ofertas

    def conferir(video, nome, anuncios, capa=None, precos=(), preco_do_post=None, outra_cor=None, **kw):
        conferidos.append([n for n, _f in anuncios])
        # Confirma os três de nome e preço parecidos; o rosa é o mesmo modelo em outra cor.
        rosa = [n for n, _f in anuncios].index("Garrafa Térmica Inox 500ml Azul Rosa")
        outra_cor.add(rosa)
        return list(range(len(anuncios))), ""

    monkeypatch.setattr(robo, "foto_do_anuncio", lambda endereco: b"foto" if endereco else None)
    monkeypatch.setattr(robo, "sem_os_a_mais", lambda: None)
    monkeypatch.setattr(asv.api_shopee, "buscar_ofertas_shopee", buscar)
    monkeypatch.setattr(ps, "ia_confere_iguais", conferir)
    mais = rodar(asv.links_a_mais({"arquivo": "v.mp4"}, [original]))
    # O mais caro (40% acima), o de outro nome e o próprio produto do vídeo nem vão à IA.
    assert conferidos == [["Garrafa Térmica Inox 500ml Azul Loja B", "Garrafa Térmica Inox 500ml Azul Rosa",
                           "Garrafa Térmica Inox 500ml Azul Loja A"]]
    assert [m["item"] for m in mais] == ["3", "2"]
    # A comissão é a do vídeo (P297 1): os 30% da API são 1,5% da Shopee e 27% do vendedor.
    assert mais[0] == {"nome": "Garrafa Térmica Inox 500ml Azul Loja B", "preco": 52.0, "comissao": 28.5,
                       "endereco": "https://shopee.com.br/product/9/3", "item": "3"}
    # Nos vídeos do Rafael, sem os produtos a mais do robô (desligados ou pelos pontos), nenhum; os do amigo seguem.
    monkeypatch.setattr(robo, "sem_os_a_mais", lambda: ("nenhum - desligados", ""))
    assert rodar(asv.links_a_mais({"arquivo": "v.mp4"}, [original])) == []
    assert len(rodar(asv.links_a_mais({"arquivo": "v.mp4"}, [original], do_rafael=False))) == 2
    # Sem o preço do produto do link ou no vídeo de link de vídeo (sem produto), nenhum, sem buscar.
    assert rodar(asv.links_a_mais({"arquivo": "v.mp4"}, [{**original, "preco": 0}], do_rafael=False)) == []
    assert rodar(asv.links_a_mais({"arquivo": "v.mp4"}, [], do_rafael=False)) == []
    assert len(conferidos) == 2


def test_links_a_mais_so_com_os_da_faixa_do_mais_barato(monkeypatch):
    # Escolha do Rafael (22/11, P284 1): a busca também pelos mais vendidos, os mais baratos que o do vídeo vão
    # à IA primeiro, e dos confirmados só ficam os até 25% acima do mais barato: a garrafa de R$ 30 deixa de fora
    # as de R$ 52 e R$ 55. O do vídeo vai sempre, em 1º, fora da lista dos a mais.
    import postador_shopee_video as ps
    import robo_shopee_video as robo
    original = {"nome": "Garrafa Térmica Inox 500ml Azul", "preco": 50.0, "comissao": 10.0, "imagem": "foto-1",
                "item": "1"}
    ofertas = [_oferta("Garrafa Térmica Inox 500ml Azul Loja A", 55.0, 20.0, "2"),
               _oferta("Garrafa Térmica Inox 500ml Azul Loja B", 52.0, 30.0, "3"),
               _oferta("Garrafa Térmica Inox 500ml Azul Barata", 30.0, 10.0, "7")]
    ordens, conferidos = [], []

    async def buscar(termo, limite=10, sort_type=2, **kw):
        ordens.append(sort_type)
        return ofertas

    def conferir(video, nome, anuncios, **kw):
        conferidos.append([n for n, _f in anuncios])
        return list(range(len(anuncios))), ""

    monkeypatch.setattr(robo, "foto_do_anuncio", lambda endereco: b"foto" if endereco else None)
    monkeypatch.setattr(robo, "sem_os_a_mais", lambda: None)
    monkeypatch.setattr(asv.api_shopee, "buscar_ofertas_shopee", buscar)
    monkeypatch.setattr(ps, "ia_confere_iguais", conferir)
    mais = rodar(asv.links_a_mais({"arquivo": "v.mp4"}, [original]))
    assert ordens == [5, 2]
    assert conferidos == [["Garrafa Térmica Inox 500ml Azul Barata", "Garrafa Térmica Inox 500ml Azul Loja B",
                           "Garrafa Térmica Inox 500ml Azul Loja A"]]
    assert [m["item"] for m in mais] == ["7"]
    registro = asv.registro_processos.sequencia("shopee_video", asv.PROCESSO_DOS_LINKS, "2000-01-01 00:00:00")
    assert registro[-1][2] == "1 a mais" and "3 confirmados, 2 fora da faixa do mais barato" in registro[-1][3]


def test_produto_que_o_amigo_ja_recebeu_fica_para_os_outros(monkeypatch):
    # P271 2: o produto só não repete para a mesma pessoa. O vídeo dele fica na fonte, sem ser anotado, e vai o
    # próximo; outro amigo (e o Rafael) ainda pode receber esse produto.
    _preparar_do_amigo(monkeypatch)
    asv.registrar("antigo", "enviado", "", _as("09:00"), item="11", amigo="7")
    bot = BotDoGrupo()
    assert rodar(asv.preparar_para_o_amigo(bot, 42, AMIGO, _as("14:00"))) == asv.MANDADO_AO_AMIGO
    assert consultar("SELECT amigo FROM shopee_video_enviados WHERE id_unico = 'velho'") == ("7",)
    assert consultar("SELECT 1 FROM shopee_video_enviados WHERE id_unico = 'novo'") is None
    assert asv.proximo_video()["id"] == "novo"
    outro = {**AMIGO, "id": 8, "mencao": "@outro"}
    assert rodar(asv.preparar_para_o_amigo(BotDoGrupo(), 42, outro, _as("14:10"))) == asv.MANDADO_AO_AMIGO
    assert consultar("SELECT amigo FROM shopee_video_enviados WHERE id_unico = 'novo'") == ("8",)


def test_o_mesmo_video_nao_vai_ao_amigo(monkeypatch):
    # P307: cada vídeo vai a uma pessoa só, também noutro arquivo: o vídeo que o Rafael já recebeu fica de lado pela
    # assinatura, e vai o próximo da fonte ao amigo, com a assinatura dele guardada.
    import robo_shopee_video as robo
    _preparar_do_amigo(monkeypatch)
    usado, outro = "12.0;" + ";".join(["f0f0f0f0f0f0f0f0"] * 4), "30.0;" + ";".join(["0f0f0f0f0f0f0f0f"] * 4)
    assinaturas = {"novo.mp4": usado, "velho.mp4": outro}
    monkeypatch.setattr(robo.videos, "assinatura_do_video", lambda arquivo: assinaturas[os.path.basename(arquivo)])
    asv.registrar("do_rafael", "enviado", "", _as("09:00"), item="99", assinatura=usado)
    assert rodar(asv.preparar_para_o_amigo(BotDoGrupo(), 42, AMIGO, _as("14:00"))) == asv.MANDADO_AO_AMIGO
    assert consultar("SELECT status FROM shopee_video_enviados WHERE id_unico = 'novo'") == ("mesmo_video",)
    assert consultar("SELECT amigo, assinatura FROM shopee_video_enviados WHERE id_unico = 'velho'") == ("7", outro)


def test_amigo_sem_video_na_fonte_e_com_a_ia_sem_resposta(monkeypatch):
    _preparar_do_amigo(monkeypatch, textos=None)
    bot = BotDoGrupo()
    # A IA sem o texto: o pedido para no 1º vídeo (cada um que passasse sairia da fonte).
    assert rodar(asv.preparar_para_o_amigo(bot, 42, AMIGO)) == asv.SEM_TEXTO_DA_IA
    assert bot.envios == [] and asv.proximo_video()["id"] == "velho"
    asv.registrar("velho", "enviado", "", item="22", amigo="9")
    assert rodar(asv.preparar_para_o_amigo(bot, 42, AMIGO)) == asv.SEM_VIDEO_PARA_O_AMIGO


def test_violacao_no_video_do_amigo_avisa_o_rafael_e_vai_o_proximo(monkeypatch):
    _preparar_do_amigo(monkeypatch)
    chamadas = []

    async def gerar(arquivo, nome="", leves=False):
        chamadas.append(os.path.basename(arquivo))
        return {**TEXTOS, "violacao": True, "motivo": "marca"} if len(chamadas) == 1 else TEXTOS

    monkeypatch.setattr(asv, "gerar_textos", gerar)
    bot = BotDoGrupo()
    assert rodar(asv.preparar_para_o_amigo(bot, 42, AMIGO)) == asv.MANDADO_AO_AMIGO
    # (a IA é chamada mais de uma vez quando o título vem curto)
    assert list(dict.fromkeys(chamadas)) == ["novo.mp4", "velho.mp4"]
    aviso = bot.envios[0]
    assert aviso["chat"] == 42 and "violação" in aviso["conteudo"]
    assert [e["chat"] for e in bot.envios[1:]] == [-1001, -1001]


def test_video_que_o_robo_pega_no_meio_do_preparo_nao_vai_ao_amigo(monkeypatch):
    # O robô roda em outro processo: o vídeo que ele pegou enquanto o do amigo era preparado fica com ele, e vai o
    # próximo (P271 2: um vídeo, uma pessoa só).
    _preparar_do_amigo(monkeypatch)
    vistos = []

    async def gerar(arquivo, nome="", leves=False):
        if not vistos:
            asv.registrar("novo", "robo", "rascunho do robô")
        vistos.append(os.path.basename(arquivo))
        return TEXTOS

    monkeypatch.setattr(asv, "gerar_textos", gerar)
    bot = BotDoGrupo()
    assert rodar(asv.preparar_para_o_amigo(bot, 42, AMIGO)) == asv.MANDADO_AO_AMIGO
    assert consultar("SELECT status FROM shopee_video_enviados WHERE id_unico = 'novo'") == ("robo",)
    assert consultar("SELECT amigo FROM shopee_video_enviados WHERE id_unico = 'velho'") == ("7",)
    assert [e["chat"] for e in bot.envios] == [-1001, -1001]


def _sessao_da_api(monkeypatch, nos, pedidos=None):
    """aiohttp.ClientSession falso: o POST da API de afiliado responde com estes produtos (nodes); pedidos (lista),
    quando vem, guarda o corpo de cada POST."""
    class Resposta:
        async def json(self, content_type=None):
            return {"data": {"productOfferV2": {"nodes": nos}}}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class Sessao:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def post(self, url, headers=None, data=None):
            if pedidos is not None:
                pedidos.append(data)
            return Resposta()

    monkeypatch.setattr(asv.aiohttp, "ClientSession", Sessao)


def test_produto_da_api_e_a_mensagem_dizem_a_comissao_do_video(monkeypatch):
    # Escolha do Rafael (24/11/2026, P297 1): a comissão é a dos vídeos da Shopee Vídeo, 1,5% da Shopee mais a extra do
    # vendedor, e não os 3% das redes sociais que a API dá. O de R$ 30 a 13% na API (10% de extra) paga 11,5% no vídeo.
    _sessao_da_api(monkeypatch, [{"productName": "Garrafa", "priceMin": "30", "priceMax": "30",
                                  "commissionRate": "0.13", "imageUrl": "foto"}])
    produto = rodar(asv._consultar_produto("11", "22"))
    assert produto["comissao"] == 11.5 and produto["preco"] == 30.0
    texto = asv.montar_mensagem(TEXTOS, [produto], "https://s.shopee.com.br/abc")
    assert "Garrafa: R$ 30,00, comissão 11,5%" in texto
    # Sem extra do vendedor, 1,5%, escrito com a vírgula.
    _sessao_da_api(monkeypatch, [{"productName": "Copo", "priceMin": "18", "commissionRate": "0.03"}])
    produto = rodar(asv._consultar_produto("11", "23"))
    assert produto["comissao"] == 1.5
    assert "Copo: R$ 18,00, comissão 1,5%" in asv.montar_mensagem(TEXTOS, [produto], "https://s.shopee.com.br/abc")


def test_o_produto_da_api_pede_a_parte_do_vendedor(monkeypatch):
    # P297 1: a consulta pede a parte da Shopee e a do vendedor (a sonda de 24/11/2026 achou as duas em todos os
    # produtos), e a comissão do vídeo sai delas: 2% da Shopee e 5% do vendedor (7% na API) pagam 6,5% no vídeo.
    pedidos = []
    _sessao_da_api(monkeypatch, [{"productName": "Pote", "priceMin": "20", "commissionRate": "0.07",
                                  "sellerCommissionRate": "0.05", "shopeeCommissionRate": "0.02"}], pedidos)
    produto = rodar(asv._consultar_produto("11", "24"))
    assert produto["comissao"] == 6.5
    assert len(pedidos) == 1 and "sellerCommissionRate" in str(pedidos[0]) and "shopeeCommissionRate" in str(pedidos[0])
