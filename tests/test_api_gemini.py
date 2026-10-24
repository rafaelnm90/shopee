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
    estado = SimpleNamespace(respostas={}, chamadas=[])

    def generate_content(model, contents):
        estado.chamadas.append(model)
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
    respostas = {"gemini-a": "responde", "gemini-velho": "modelo não encontrado", "gemini-novo": "responde"}
    linhas = ia.relatorio_dos_modelos(["gemini-a", "gemini-novo"], testar=respostas.get)
    assert linhas == ["== Cascata (na ordem)", "gemini-a: na chave, responde",
                      "gemini-velho: fora da chave, modelo não encontrado",
                      "== Modelos de texto da chave fora da cascata", "gemini-novo: na chave, responde"]


def test_modelos_da_chave_so_os_de_texto(monkeypatch):
    modelos = [SimpleNamespace(name=f"models/{nome}", supported_actions=acoes) for nome, acoes in (
        ("gemini-z-flash", ["generateContent"]), ("gemini-z-flash-image", ["generateContent"]),
        ("gemini-z-tts", ["generateContent"]), ("text-embedding-9", ["embedContent"]), ("gemini-a-pro", None))]
    monkeypatch.setattr(ia, "client_genai", SimpleNamespace(models=SimpleNamespace(list=lambda: modelos)))
    assert ia.modelos_da_chave() == ["gemini-z-flash"]


def test_teste_do_modelo_diz_o_motivo_fixo(gemini):
    gemini.respostas.update(b=COTA_DO_DIA, c=NAO_EXISTE)
    assert [ia.testar_modelo(m) for m in "abc"] == ["responde", "cota do dia", "modelo não encontrado"]
