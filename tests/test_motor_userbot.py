"""motor_userbot.py: mensagem de canal a que a conta perdeu o acesso não vira erro no Espião nem no Espelhador."""
from telethon.errors import ChannelPrivateError

import motor_userbot as mu
from conftest import rodar


class EventoSemAcesso:
    async def get_chat(self):
        raise ChannelPrivateError(request=None)


def test_canal_sem_acesso_e_ignorado_sem_erro():
    # Checkup de 23/10: o ChannelPrivateError no get_chat virava rastro de erro no log,
    # 12 vezes num dia.
    assert rodar(mu.interceptar_mensagem(EventoSemAcesso())) is None
    assert rodar(mu.motor_espelhador_userbot(EventoSemAcesso())) is None


def test_falha_no_disparo_do_espelhador_diz_em_que_passo_aconteceu():
    # Checkup de 26/10: "desistiu após 3 tentativas - ValueError" não dizia onde. Cada passo
    # do disparo tem um rótulo fixo, que vai ao registro junto com o tipo do erro.
    import inspect
    import re
    fonte = inspect.getsource(mu.processar_fila_espelhador_loop)
    assert re.findall(r'etapa = "([^"]+)"', fonte) == [
        "ler a origem", "baixar o vídeo", "renovar o link", "legenda da IA", "achar o destino", "enviar ao destino"]
    assert fonte.count('f"{type(erro_disparo).__name__} em {etapa}"') == 2


def test_ultima_mensagem_de_cada_grupo_vigiado_vai_ao_banco(monkeypatch):
    # Checkup de 06/11/2026: do grupo que parou de mandar vídeo, o checkup diz se ainda chega
    # mensagem dele. O motor anota na memória a última mensagem de cada grupo (pelo apelido do
    # registro) e grava no banco de tempos em tempos, juntando com o que já estava.
    import db
    import registro_processos as rp
    from conftest import inserir
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    mu._ultimas_mensagens["espiao"].clear()
    mu._ultimas_mensagens["espelhador"].clear()
    mu.anotar_mensagem_da_origem("espiao", "@GrupoA")
    mu.anotar_mensagem_da_origem("espelhador", "-1009:5")
    mu.gravar_ultimas_mensagens()
    dados = db.ler_config(mu.CHAVE_DAS_ULTIMAS_MENSAGENS, {})
    assert set(dados["espiao"]) == {rp.apelido("@grupoa")} and set(dados["espelhador"]) == {rp.apelido("-1009:5")}
    assert dados["desde"] and mu._ultimas_mensagens == {"espiao": {}, "espelhador": {}}
    mu.anotar_mensagem_da_origem("espiao", "@GrupoB")
    mu.gravar_ultimas_mensagens()
    dados_depois = db.ler_config(mu.CHAVE_DAS_ULTIMAS_MENSAGENS, {})
    assert set(dados_depois["espiao"]) == {rp.apelido("@grupoa"), rp.apelido("@grupob")}
    assert dados_depois["desde"] == dados["desde"]
    # Sem nada novo, nada muda; com o banco falhando, o anotado fica para a próxima.
    mu.gravar_ultimas_mensagens()
    mu.anotar_mensagem_da_origem("espiao", "@GrupoC")
    monkeypatch.setattr(mu.db, "atualizar_config", lambda chave, alterar, padrao=None: None)
    mu.gravar_ultimas_mensagens()
    assert set(mu._ultimas_mensagens["espiao"]) == {rp.apelido("@grupoc")}
    mu._ultimas_mensagens["espiao"].clear()


def test_cada_clone_baixa_num_arquivo_com_o_proprio_id(monkeypatch):
    # 07/11 (15:57 e 16:11): com o prefixo "temp/temp_clone_", o Telethon dava o primeiro nome livre
    # ("temp_clone_ (N)"), que volta a ficar livre quando o vídeo de um clone já postado no Viral sai
    # do disco: o item antigo, que fica na fila até o fim do dia, passava a apontar para o vídeo novo,
    # e o robô da Shopee Vídeo juntava o link de um vídeo com o arquivo de outro. Cada clone baixa no
    # arquivo com o próprio id.
    import os
    from types import SimpleNamespace
    from conftest import inserir
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    os.makedirs("temp", exist_ok=True)
    pedidos = []

    class Evento:
        sender_id, out, id, text, video = 999, False, 55, "olha o achado", object()
        message = SimpleNamespace(reply_to=None)

        async def download_media(self, file):
            pedidos.append(file)
            with open(file + ".mp4", "wb") as f:
                f.write(b"video")
            return file + ".mp4"

    async def chat(_evento):
        return SimpleNamespace(id=123, username="GrupoA", title="Grupo A")

    async def eu():
        return SimpleNamespace(id=1)

    async def otimizar(caminho, *_a):
        return caminho

    monkeypatch.setattr(mu, "carregar_alvos", lambda: ["@grupoa"])
    monkeypatch.setattr(mu, "ler_excecao_ponte", lambda: "")
    monkeypatch.setattr(mu, "chat_do_evento", chat)
    monkeypatch.setattr(mu.client, "get_me", eu)
    monkeypatch.setattr(mu, "extrair_link_shopee", lambda _evento: "https://s.shopee.com.br/achado")
    monkeypatch.setattr(mu, "verificar_e_registrar_espelho", lambda _link, contexto=None: False)
    monkeypatch.setattr(mu, "verificar_e_otimizar_video", otimizar)
    monkeypatch.setattr(mu, "verificar_e_registrar_hash", lambda _h, contexto=None: False)
    monkeypatch.setattr(mu, "registrar_historico_espiao", lambda _nome: None)
    for _ in range(2):
        rodar(mu.interceptar_mensagem(Evento()))
    mu._ultimas_mensagens["espiao"].clear()
    fila = mu.ler_fila_clonagem()["fila"]
    assert pedidos == [f"temp/temp_clone_{item['id']}" for item in fila] and len(set(pedidos)) == 2
    assert [item["caminho_video"] for item in fila] == [f"temp/temp_clone_{item['id']}.mp4" for item in fila]


def test_video_sem_link_de_um_grupo_vigiado_conta_no_registro(monkeypatch):
    # Checkup de 07/11/2026: o nº 5 do Espião e do Espelhador parou de mandar vídeo com link, mas a
    # última mensagem dele era de pouco antes; não dava para saber se ele ainda manda vídeo (com o
    # link num jeito que o robô não reconhece, ou em outra mensagem) ou se parou de mandar vídeo.
    # O vídeo sem link reconhecido conta por grupo (só o apelido), no Espião e no Espelhador.
    from types import SimpleNamespace
    import registro_processos as rp
    from conftest import inserir
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")

    class Evento:
        sender_id, out, id, text, video = 999, False, 56, "olha o achado", object()
        message = SimpleNamespace(reply_to=None)

    async def chat(_evento):
        return SimpleNamespace(id=123, username="GrupoA", title="Grupo A")

    async def eu():
        return SimpleNamespace(id=1)

    monkeypatch.setattr(mu, "carregar_alvos", lambda: ["@grupoa"])
    monkeypatch.setattr(mu, "ler_excecao_ponte", lambda: "")
    monkeypatch.setattr(mu, "chat_do_evento", chat)
    monkeypatch.setattr(mu.client, "get_me", eu)
    monkeypatch.setattr(mu, "extrair_link_shopee", lambda _evento: None)
    monkeypatch.setattr(mu, "ler_espelhos_config", lambda: {"rotas": [{"nome": "r1", "origens": ["@grupoa"]}]})
    rodar(mu.interceptar_mensagem(Evento()))
    rodar(mu.motor_espelhador_userbot(Evento()))
    # Mensagem só de texto, sem vídeo, não conta.
    Evento.video = None
    rodar(mu.interceptar_mensagem(Evento()))
    mu._ultimas_mensagens["espiao"].clear()
    mu._ultimas_mensagens["espelhador"].clear()
    linhas = [(robo, processo, origem) for robo, processo in (("espiao", mu.PROCESSO_DO_VIDEO_SEM_LINK_ESPIAO),
                                                              ("espelhador", mu.PROCESSO_DO_VIDEO_SEM_LINK_ESPELHADOR))
              for _m, _p, _r, _d, origem in rp.sequencia(robo, processo, "2000-01-01 00:00:00")]
    assert linhas == [("espiao", "vídeo sem link no grupo vigiado", rp.apelido("@grupoa")),
                      ("espelhador", "vídeo sem link na origem da rota", rp.apelido("@grupoa"))]
