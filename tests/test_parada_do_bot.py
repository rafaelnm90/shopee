"""bot_mestre: parado pelo systemd (deploy), o bot sai na hora, sem esperar as threads da IA."""
import inspect

import pytest


class Saiu(Exception):
    pass


def test_parado_pelo_systemd_o_bot_sai_sem_esperar_as_threads(bm, monkeypatch):
    # Checkup de 16/11: no deploy das 10:11, o systemd matou o bot_mestre ("não parou no tempo"), com uma resposta da
    # IA a caminho numa thread (api_gemini, até 4 min): o asyncio e o Python esperavam a thread acabar antes de sair.
    chamadas = []
    monkeypatch.setattr(bm.os, "_exit", lambda codigo: chamadas.append(codigo) or (_ for _ in ()).throw(Saiu()))
    monkeypatch.setattr("logging.shutdown", lambda: chamadas.append("logs"))
    with pytest.raises(Saiu):
        bm.sair_sem_esperar_as_threads()
    assert chamadas == ["logs", 0]
    # O fim do main(): o polling acaba quando o systemd para o bot, e logo depois o bot sai.
    fonte = inspect.getsource(bm.main)
    depois = fonte.split("await dp.start_polling(bot)", 1)[1]
    assert "sair_sem_esperar_as_threads()" in depois
