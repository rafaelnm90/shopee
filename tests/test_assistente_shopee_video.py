"""Modo assistente da Shopee Vídeo: quando mandar, qual vídeo, texto da IA, produtos e a mensagem do privado."""
import json
import os
import re
from datetime import datetime

import pytest

import assistente_shopee_video as asv
from conftest import consultar, inserir, rodar
from fuso import fuso_horario

CONFIG = {"pausado": False, "limite_min": 5, "limite_max": 5, "inicio": 13, "fim": 22}


@pytest.fixture(autouse=True)
def tabela_de_configuracoes():
    # No servidor, quem cria é o bot_mestre ao subir; o assistente roda dentro dele.
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")


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
    assert produtos == [{"nome": "Garrafa", "preco": 19.9, "comissao": 8.0}]
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


def _com_edicao(monkeypatch, conteudos, ias):
    """Edição ligada, com o ffmpeg e a foto de mentira; o link de vídeo não traz produto (sem foto)."""
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

    def editar(video, foto, destino, avisos=False):
        if not foto:
            return "a foto do anúncio não veio"
        with open(destino, "wb") as arquivo:
            arquivo.write(b"editado com " + foto)
        return ""

    class BotQueLe(Bot):
        async def send_video(self, chat_id, video, **kw):
            with open(video.path, "rb") as arquivo:
                conteudos.append(arquivo.read())
            await super().send_video(chat_id, video, **kw)

    monkeypatch.setattr(asv, "gerar_textos", gerar)
    monkeypatch.setattr(asv, "produtos_do_link", produtos)
    monkeypatch.setattr(ps, "baixar_foto", lambda endereco: b"foto")
    monkeypatch.setattr(edicao_video, "editar", editar)
    return BotQueLe()


def test_com_a_edicao_ligada_o_assistente_manda_o_video_editado(monkeypatch):
    # Pedido do Rafael (25/10, P40): na Shopee Vídeo, só vídeo editado, também no assistente.
    conteudos, ias = [], []
    bot = _com_edicao(monkeypatch, conteudos, ias)
    _fila(("novo", LEGENDA, "archive/novo.mp4", "2026-10-02 10:00"))
    assert rodar(asv.preparar_e_enviar(bot, 42)) == "postagem mandada no seu privado"
    assert conteudos == [b"editado com foto"] and "Postagem pronta" in bot.mensagens[0][1]
    # A IA assiste ao vídeo original, sem a foto e a seta por cima.
    assert set(ias) == {"archive/novo.mp4"}


def test_o_que_nao_sai_editado_fica_de_lado_e_vai_o_proximo_sem_gastar_a_ia(monkeypatch):
    conteudos, ias = [], []
    bot = _com_edicao(monkeypatch, conteudos, ias)
    _fila(("produto", LEGENDA, "archive/produto.mp4", "2026-10-02 09:00"),
          ("video", LEGENDA_VIDEO, "archive/video.mp4", "2026-10-02 10:00"))
    assert rodar(asv.preparar_e_enviar(bot, 42)) == "postagem mandada no seu privado"
    assert conteudos == [b"editado com foto"] and set(ias) == {"archive/produto.mp4"}
    # O de link de vídeo (sem uma foto só) ficou de lado e não volta.
    assert asv.proximo_video() is None and asv.enviados_hoje() == 1


def test_nenhum_editado_avisa_sem_mandar_nada(monkeypatch):
    conteudos, ias = [], []
    bot = _com_edicao(monkeypatch, conteudos, ias)
    _fila(*[(f"v{i}", LEGENDA_VIDEO, f"archive/v{i}.mp4", f"2026-10-02 1{i}:00") for i in range(6)])
    resultado = rodar(asv.preparar_e_enviar(bot, 42))
    assert resultado.startswith(f"nenhum dos {asv.VIDEOS_POR_ENVIO} próximos vídeos saiu editado")
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
    conteudos, ias = [], []
    bot = _com_edicao(monkeypatch, conteudos, ias)
    import edicao_video
    editados = []

    def editar(video, foto, destino, avisos=False):
        editados.append(avisos)
        with open(destino, "wb") as arquivo:
            arquivo.write(b"capa com os avisos" if avisos else b"editado")
        return ""
    monkeypatch.setattr(edicao_video, "editar", editar)

    async def gerar(arquivo, nome="", leves=False):
        ias.append(arquivo)
        return {**TEXTOS, "bebida_alcoolica": True}
    monkeypatch.setattr(asv, "gerar_textos", gerar)
    _fila(("cerveja", LEGENDA, "archive/cerveja.mp4", "2026-10-02 10:00"))
    assert rodar(asv.preparar_e_enviar(bot, 42)) == "postagem mandada no seu privado"
    assert editados == [False, True] and conteudos == [b"capa com os avisos"]
    assert consultar("SELECT resultado FROM registro_processos WHERE processo = 'edição do vídeo: assistente' "
                     "ORDER BY rowid DESC LIMIT 1") == ("editado com os avisos",)


def test_bebida_alcoolica_sem_a_edicao_fica_de_lado_e_vai_o_proximo(monkeypatch):
    # Sem a edição não há como pôr os avisos na capa: o vídeo de bebida alcoólica fica de lado.
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
