"""Modo assistente da Shopee Vídeo: quando mandar, qual vídeo, texto da IA, produtos e a mensagem do privado."""
import os
from datetime import datetime

import pytest

import assistente_shopee_video as asv
from conftest import inserir, rodar
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


def test_nome_da_legenda():
    assert asv.nome_da_legenda(LEGENDA) == "Garrafa Térmica 🧊"
    assert asv.nome_da_legenda("<b>Vídeo do Produto</b> 🛍️") == ""
    assert asv.nome_da_legenda("sem negrito") == ""


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
    assert asv.ler_resposta(texto) == {"violacao": False, "motivo": "", "titulo": "Garrafa Térmica 🧊 #garrafa",
                                       "comentario": "Mantém gelado o dia todo #casa"}
    assert asv.ler_resposta("não sei") is None
    assert asv.ler_resposta("{quebrado") is None
    assert asv.ler_resposta('{"violacao": true, "motivo": "marca no vídeo"}')["violacao"] is True


def test_titulo_comprido_perde_palavras_do_fim_sem_cortar_no_meio():
    titulo = "Garrafa Térmica 🧊 " + " ".join(f"#hashtag{i}" for i in range(30))
    encaixado = asv.encaixar_titulo(titulo)
    assert len(encaixado) <= 150 and titulo.startswith(encaixado)
    assert titulo[len(encaixado)] == " "
    assert asv.encaixar_titulo("curto   demais") == "curto demais"


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
    assert "1. Copo &amp; Tampa: R$ 19,90, comissão 8%" in texto
    assert "https://s.shopee.com.br/abc" in texto and "Postar vídeo" in texto
    assert len(texto) <= 4096


def test_mensagem_de_video_manda_ver_os_produtos_do_criador():
    texto = asv.montar_mensagem(TEXTOS, [], "https://s.shopee.com.br/v")
    assert "os que o criador vinculou" in texto and "menor preço primeiro" in texto


# --- Envio ---

class Bot:
    def __init__(self):
        self.mensagens, self.videos = [], []

    async def send_message(self, chat_id, text, **kw):
        self.mensagens.append((chat_id, text))

    async def send_video(self, chat_id, video, **kw):
        self.videos.append((chat_id, os.path.basename(video.path)))


def _preparar(monkeypatch, textos):
    async def gerar(arquivo, nome=""):
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
    async def gerar(arquivo, nome=""):
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
