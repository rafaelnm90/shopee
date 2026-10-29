"""IA: modelo sem cota ou inexistente sai da cascata por um tempo, em vez de gastar chamada a cada pedido."""
from types import SimpleNamespace

import pytest

import api_gemini as ia
from conftest import rodar

COTA_DO_DIA = "429 RESOURCE_EXHAUSTED. {'details': [{'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}]}"
COTA_DO_MINUTO = "429 RESOURCE_EXHAUSTED. Please retry in 41.3s. {'retryDelay': '41s'}"
NAO_EXISTE = "404 NOT_FOUND. models/gemini-x is not found"


@pytest.fixture
def gemini(monkeypatch):
    """Cascata de 3 modelos com respostas falsas: erro (texto) ou o texto devolvido."""
    monkeypatch.setattr(ia, "MODELOS_CASCATA_GEMINI", ["a", "b", "c"])
    monkeypatch.setattr(ia, "_fora_ate", {})
    estado = SimpleNamespace(respostas={}, chamadas=[], conteudos=[])

    def generate_content(model, contents):
        estado.chamadas.append(model)
        estado.conteudos.append(contents)
        resposta = estado.respostas.get(model, "ok")
        if resposta.startswith(("429", "404", "500")):
            raise RuntimeError(resposta)
        return SimpleNamespace(text=resposta)

    monkeypatch.setattr(ia, "client_genai", SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    return estado


def test_modelo_sem_cota_fica_de_fora_nas_proximas(gemini):
    gemini.respostas = {"a": COTA_DO_DIA, "b": NAO_EXISTE, "c": "texto do c"}
    assert rodar(ia.gerar_texto_gemini("p")) == "texto do c"
    assert rodar(ia.gerar_texto_gemini("p")) == "texto do c"
    assert gemini.chamadas == ["a", "b", "c", "c"]


def test_texto_com_imagem_manda_a_imagem_antes_do_pedido(gemini):
    # A IA do feed comenta vendo a tela do vídeo (P70): a imagem vai junto com o pedido.
    assert rodar(ia.gerar_texto_gemini("comente", imagens=[(b"\xff\xd8jpeg", "image/jpeg")])) == "ok"
    imagem, pedido = gemini.conteudos[-1]
    assert pedido == "comente" and imagem.inline_data.mime_type == "image/jpeg"
    assert imagem.inline_data.data == b"\xff\xd8jpeg"
    rodar(ia.gerar_texto_gemini("só texto"))
    assert gemini.conteudos[-1] == "só texto"


def test_erro_comum_nao_tira_da_cascata(gemini):
    gemini.respostas = {"a": "500 INTERNAL", "b": "texto do b"}
    rodar(ia.gerar_texto_gemini("p"))
    rodar(ia.gerar_texto_gemini("p"))
    assert gemini.chamadas == ["a", "b", "a", "b"]


def test_todos_de_fora_tenta_todos_mesmo_assim(gemini):
    gemini.respostas = {m: COTA_DO_MINUTO for m in "abc"}
    assert rodar(ia.gerar_texto_gemini("p")) is None
    gemini.respostas = {"a": COTA_DO_MINUTO, "b": "voltou", "c": COTA_DO_MINUTO}
    assert rodar(ia.gerar_texto_gemini("p")) == "voltou"
    assert gemini.chamadas == ["a", "b", "c", "a", "b"]


def test_prazos_de_cada_erro():
    segundos, motivo = ia.tempo_fora(COTA_DO_MINUTO)
    assert motivo == "cota do minuto" and 41 < segundos < 60
    segundos, motivo = ia.tempo_fora(COTA_DO_DIA)
    assert motivo == "cota do dia" and 0 < segundos <= 24 * 3600 + 300
    assert ia.tempo_fora(NAO_EXISTE)[0] == ia.ESPERA_MODELO_INEXISTENTE_S
    assert ia.tempo_fora("429 quota exceeded")[0] == ia.ESPERA_COTA_S
    assert ia.tempo_fora("500 INTERNAL") is None


def test_relatorio_dos_modelos_mostra_a_cascata_e_os_novos_so_com_nomes(monkeypatch):
    # O modelos_ia.yml mantém a cascata atualizada: o modelo que a chave não enxerga e o
    # modelo novo da chave que a cascata ainda não usa aparecem, com o motivo fixo do teste.
    monkeypatch.setattr(ia, "MODELOS_CASCATA_GEMINI", ["gemini-a", "gemini-velho"])
    monkeypatch.setattr(ia, "DESCONTINUADOS", ("gemini-saiu", "gemini-sumiu"))
    respostas = {"gemini-a": "responde", "gemini-velho": "modelo não encontrado", "gemini-novo": "responde",
                 "gemini-saiu": "responde"}
    linhas = ia.relatorio_dos_modelos(["gemini-a", "gemini-novo", "gemini-saiu"], testar=respostas.get)
    # O descontinuado que a chave ainda enxerga fica à parte, para não voltar à cascata como novo (P36).
    assert linhas == ["== Cascata (na ordem)", "gemini-a: na chave, responde",
                      "gemini-velho: fora da chave, modelo não encontrado",
                      "== Modelos de texto da chave fora da cascata", "gemini-novo: na chave, responde",
                      "== Descontinuados pelo Google que a chave ainda enxerga (não voltam)", "gemini-saiu"]


def test_modelos_da_chave_so_os_de_texto(monkeypatch):
    modelos = [SimpleNamespace(name=f"models/{nome}", supported_actions=acoes) for nome, acoes in (
        ("gemini-z-flash", ["generateContent"]), ("gemini-z-flash-image", ["generateContent"]),
        ("gemini-z-tts", ["generateContent"]), ("text-embedding-9", ["embedContent"]), ("gemini-a-pro", None),
        ("gemini-omni-9-flash", ["generateContent"]))]
    monkeypatch.setattr(ia, "client_genai", SimpleNamespace(models=SimpleNamespace(list=lambda: modelos)))
    assert ia.modelos_da_chave() == ["gemini-z-flash"]


def test_teste_do_modelo_diz_o_motivo_fixo(gemini):
    gemini.respostas.update(b=COTA_DO_DIA, c=NAO_EXISTE)
    assert [ia.testar_modelo(m) for m in "abc"] == ["responde", "cota do dia", "modelo não encontrado"]


def test_cascata_sem_repetidos_e_so_modelos_de_texto():
    # A cascata é atualizada à mão pelo resultado do modelos_ia.yml: um nome repetido gastaria
    # duas chamadas na mesma cota, e um modelo de imagem ou voz nunca devolve o texto pedido.
    assert len(set(ia.MODELOS_CASCATA_GEMINI)) == len(ia.MODELOS_CASCATA_GEMINI)
    assert all(m.startswith("gemini") and not any(p in m for p in ia.FORA_DOS_ROBOS) for m in ia.MODELOS_CASCATA_GEMINI)


def test_descontinuado_nao_fica_na_cascata():
    # Escolha do Rafael (P36): todo modelo que o Google descontinuou sai da cascata, mesmo que
    # ainda responda redirecionado para o modelo novo.
    assert not set(ia.DESCONTINUADOS) & set(ia.MODELOS_CASCATA_GEMINI)
    assert {"gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite-preview"} <= set(ia.DESCONTINUADOS)


BLOQUEADO = "block_reason=<BlockedReason.PROHIBITED_CONTENT: 'PROHIBITED_CONTENT'>"


@pytest.fixture
def video_no_gemini(monkeypatch):
    """A análise de vídeo com o Google de mentira: o upload sai pronto e cada modelo responde a resposta dada."""
    monkeypatch.setattr(ia, "MODELOS_CASCATA_GEMINI", ["a", "b", "c"])
    monkeypatch.setattr(ia, "_fora_ate", {})
    monkeypatch.setattr(ia, "ULTIMO_ERRO_IA", None)
    estado = SimpleNamespace(respostas={}, conteudos=[])
    arquivo = SimpleNamespace(name="files/1", state=SimpleNamespace(name="ACTIVE"))

    def generate_content(model, contents):
        estado.conteudos.append(contents)
        resposta = estado.respostas.get(model, "ok")
        if resposta.startswith(("429", "404", "500")):
            raise RuntimeError(resposta)
        if resposta == "bloqueado":
            return SimpleNamespace(text=None, prompt_feedback=BLOQUEADO, candidates=[])
        if resposta == "bloqueado com categoria":
            avaliacoes = [SimpleNamespace(category=SimpleNamespace(name="HARM_CATEGORY_SEXUALLY_EXPLICIT"),
                                          probability=SimpleNamespace(name="MEDIUM"), blocked=False),
                          SimpleNamespace(category="HarmCategory.HARM_CATEGORY_HATE_SPEECH",
                                          probability="HarmProbability.NEGLIGIBLE", blocked=False)]
            return SimpleNamespace(text=None, prompt_feedback=BLOQUEADO, candidates=[
                SimpleNamespace(finish_reason="STOP", safety_ratings=avaliacoes)])
        if resposta == "vazio":
            return SimpleNamespace(text=None, prompt_feedback=None,
                                   candidates=[SimpleNamespace(finish_reason="RECITATION", safety_ratings=None)])
        return SimpleNamespace(text=resposta)

    monkeypatch.setattr(ia, "client_genai", SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content),
        files=SimpleNamespace(upload=lambda file: arquivo, get=lambda name: arquivo, delete=lambda name: None)))
    return estado


def _niveis(caplog, trecho):
    return [registro.levelname for registro in caplog.records if trecho in registro.getMessage()]


def test_conteudo_recusado_e_aviso_nao_erro(video_no_gemini, caplog):
    # Um sem cota e os outros recusando o conteúdo: quem pediu põe o vídeo de lado.
    video_no_gemini.respostas = {"a": COTA_DO_DIA, "b": "bloqueado", "c": "bloqueado"}
    with caplog.at_level("WARNING", logger="API_Gemini"):
        assert rodar(ia.analisar_video_gemini("v.mp4", "p")) is None
    assert _niveis(caplog, "recusou o pedido pelo conteúdo") == ["WARNING"]
    assert not _niveis(caplog, "Falha crítica")
    assert ia.codigos_do_google(ia.ULTIMO_ERRO_IA) == {"PROHIBITED_CONTENT"}


def test_recusa_do_conteudo_com_outros_erros_tambem_e_aviso(video_no_gemini, caplog):
    # Checkup de 25/10: com a recusa num modelo e erro passageiro ou resposta vazia por outro
    # motivo nos outros, o robô já põe o vídeo de lado; o log continuava erro.
    video_no_gemini.respostas = {"a": "bloqueado", "b": "500 INTERNAL", "c": "vazio"}
    with caplog.at_level("WARNING", logger="API_Gemini"):
        assert rodar(ia.analisar_video_gemini("v.mp4", "p")) is None
    assert _niveis(caplog, "recusou o pedido pelo conteúdo") == ["WARNING"]
    assert not _niveis(caplog, "Falha crítica")


def test_falha_sem_recusa_do_conteudo_continua_erro(video_no_gemini, caplog):
    video_no_gemini.respostas = {"a": "500 INTERNAL", "b": "vazio", "c": COTA_DO_MINUTO}
    with caplog.at_level("WARNING", logger="API_Gemini"):
        assert rodar(ia.analisar_video_gemini("v.mp4", "p")) is None
    assert _niveis(caplog, "Falha crítica") == ["ERROR"]
    assert not _niveis(caplog, "recusou o pedido pelo conteúdo")
    video_no_gemini.respostas = {"a": "bloqueado", "b": "texto do b"}
    assert rodar(ia.analisar_video_gemini("v.mp4", "p")) == "texto do b"


def test_recusa_guarda_o_que_o_google_disse_para_o_aviso(video_no_gemini):
    # Escolha do Rafael (P29): o aviso diz o código e as categorias marcadas (nível médio ou
    # alto); o Google não dá o motivo detalhado.
    video_no_gemini.respostas = {"a": "bloqueado com categoria", "b": "bloqueado", "c": COTA_DO_DIA}
    assert rodar(ia.analisar_video_gemini("v.mp4", "p")) is None
    assert ia.ULTIMA_RECUSA == {"codigos": ["PROHIBITED_CONTENT"],
                                "categorias": [("HARM_CATEGORY_SEXUALLY_EXPLICIT", "MEDIUM")]}
    video_no_gemini.respostas = {"a": "texto"}
    assert rodar(ia.analisar_video_gemini("v.mp4", "p")) == "texto" and ia.ULTIMA_RECUSA is None


def test_video_com_fotos_rotuladas_manda_cada_rotulo_antes_da_foto(video_no_gemini):
    # Os produtos a mais (P59): a IA confere de uma vez várias fotos de anúncio com o vídeo,
    # e cada foto vai logo depois do número e do nome dela.
    imagens = [(b"\xff\xd8um", "image/jpeg", "Anúncio 1: Garrafa"), (b"\xff\xd8dois", "image/jpeg"),
               (b"\xff\xd8tres", "image/jpeg", "Anúncio 3: Caneca")]
    assert rodar(ia.analisar_video_gemini("v.mp4", "compare", imagens=imagens)) == "ok"
    video, rotulo_1, foto_1, foto_2, rotulo_3, foto_3, pedido = video_no_gemini.conteudos[-1]
    assert video.name == "files/1" and pedido == "compare"
    assert (rotulo_1, rotulo_3) == ("Anúncio 1: Garrafa", "Anúncio 3: Caneca")
    assert [foto.inline_data.data for foto in (foto_1, foto_2, foto_3)] == [b"\xff\xd8um", b"\xff\xd8dois", b"\xff\xd8tres"]
