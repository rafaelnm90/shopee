"""apelacoes_shopee_video.py: cada punição da Shopee Vídeo ganha o texto do recurso e é lembrada de hora em hora até o Rafael decidir."""
from datetime import datetime, timedelta

import apelacoes_shopee_video as ap
from conftest import rodar
from fuso import fuso_horario

AGORA = datetime(2026, 10, 23, 20, 0, tzinfo=fuso_horario)
TEXTO = ("O vídeo mostra o mesmo produto do anúncio: botijão térmico com torneira, que é um garrafão para bebidas, "
         "não botijão de gás.")


def _punicao(status="Não Recorrido", **campos):
    return ap.guardar("Produto Irrelevante", "23/10/2026 19:04:25", status,
                      **{"titulo": "Botijão Térmico com Torneira", "postado_em": "18:46:10 2026-10-23",
                         "texto": TEXTO, "agora": AGORA, **campos})


def test_punicao_e_lembrada_de_hora_em_hora_ate_um_dos_botoes():
    # Pedido do Rafael (23/10): o mesmo lembrete das perguntas, até ele recorrer ou desistir.
    ident = _punicao()
    enviados = []

    async def enviar(texto, p):
        enviados.append((texto, ap.botoes(p)))
        return True
    assert rodar(ap.lembrar(enviar, AGORA)) == 1
    texto, teclado = enviados[0]
    assert "dá para recorrer" in texto and "Produto Irrelevante" in texto and f"<code>{TEXTO}</code>" in texto
    assert "Apelar aqui" in texto and len(texto) < 4096
    dados = [b.callback_data for b in teclado.inline_keyboard[0]]
    assert dados == [f"apel_ok:{ident}", f"apel_nao:{ident}"]
    assert rodar(ap.lembrar(enviar, AGORA + timedelta(minutes=59))) == 0
    assert rodar(ap.lembrar(enviar, AGORA + timedelta(hours=1))) == 1 and "Lembrete 2" in enviados[-1][0]
    assert ap.marcar(ident, ap.NAO_VAI) and not ap.marcar(ident, ap.RECORRIDA)
    assert rodar(ap.lembrar(enviar, AGORA + timedelta(hours=5))) == 0


def test_recorrida_no_app_para_o_lembrete_e_a_mesma_punicao_nao_duplica():
    ident = _punicao()
    assert ap.conhecida("Produto Irrelevante", "23/10/2026  19:04:25")
    assert _punicao(status="Em análise") == ident
    assert ap.pegar(ident)["situacao"] == ap.RECORRIDA and ap.vencidas(AGORA) == []
    # Punição que o robô já acha recorrida nunca é lembrada; "Bem-sucedido" é o recurso aceito.
    outra = ap.guardar("Contrafeito", "06/10/2026 22:44:53", "Bem-sucedido", agora=AGORA)
    assert ap.pegar(outra)["situacao"] == ap.ACEITA and len(ap.todas()) == 2
    assert _punicao(status="Bem-sucedido") == ident and ap.pegar(ident)["situacao"] == ap.ACEITA


def test_punicao_que_some_da_saude_foi_tirada_pela_shopee_e_a_antiga_saiu_da_janela():
    # Pedido do Rafael (24/10): com o recurso aceito, a Shopee pode tirar a punição da lista.
    pendente = _punicao()
    nao_vai = ap.guardar("Produto Irrelevante", "18/10/2026 14:33:18", "Não Recorrido", agora=AGORA)
    ap.marcar(nao_vai, ap.NAO_VAI)
    antiga = ap.guardar("Contrafeito", "20/09/2026 10:00:00", "Não Recorrido", agora=AGORA)
    fica = ap.guardar("Violação de Propriedade Intelectual", "18/10/2026 20:20:56", "Não Recorrido", agora=AGORA)
    vistas = {ap.chave("Violação de Propriedade Intelectual", "18/10/2026 20:20:56")}
    retiradas = ap.retirar_ausentes(vistas, AGORA)
    assert [p["id"] for p in retiradas] == [pendente]          # só a que ele esperava ganha aviso
    assert ap.pegar(pendente)["situacao"] == ap.RETIRADA and ap.pegar(nao_vai)["situacao"] == ap.RETIRADA
    assert ap.pegar(antiga)["situacao"] == ap.FORA_DA_JANELA and ap.pegar(fica)["situacao"] == ap.PENDENTE
    assert [p["id"] for p in ap.vencidas(AGORA)] == [fica]


def test_texto_da_ia_cabe_em_200_caracteres(monkeypatch):
    import api_gemini
    respostas = iter(["x " * 150, TEXTO])

    async def gerar(prompt):
        assert "botijão de gás" in prompt and "Botijão Térmico" in prompt
        return next(respostas)
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", gerar)
    texto, observacao = rodar(ap.gerar_texto("Produto Irrelevante", titulo="Botijão Térmico com Torneira",
                                             produtos=["Botijão Térmico 5L"], fonte="viral"))
    assert texto == TEXTO and observacao == ""
    longo = "Primeira frase do recurso explica o produto. " * 8
    assert len(ap._encurtar(longo)) <= ap.TAMANHO_DO_TEXTO and ap._encurtar(longo).endswith(".")


def test_propriedade_intelectual_de_video_de_outro_canal_ganha_texto_sem_autoria(monkeypatch):
    # Escolha do Rafael (25/10, P31): o recurso sai com um texto verdadeiro, que não diz que o
    # vídeo é dele nem que é original, só que ele é afiliado e divulga o produto da Shopee.
    import api_gemini

    async def gerar(prompt):
        raise AssertionError("não devia pedir texto à IA")
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", gerar)
    texto, observacao = rodar(ap.gerar_texto("Violação de Propriedade Intelectual", fonte="viral",
                                             produtos=["Mesa de Jantar Redonda com 4 Cadeiras"]))
    assert texto.startswith("Sou afiliado da Shopee.") and "Mesa de Jantar Redonda com 4 Cadeiras" in texto
    assert "outro canal" in observacao and len(texto) <= ap.TAMANHO_DO_TEXTO
    assert not any(palavra in texto.casefold() for palavra in ("original", "meu vídeo", "autor", "gravei"))
    # Sem produto, o título sem as hashtags; nome longo é cortado numa palavra, dentro dos 200.
    pelo_titulo = ap.texto_sem_autoria(titulo="Mesa de Jantar Redonda #mesajantar #sala")
    assert "o produto Mesa de Jantar Redonda," in pelo_titulo and "#" not in pelo_titulo
    longo = ap.texto_sem_autoria(["Conjunto Mesa " + "Cadeira Madeira Maciça " * 10])
    assert len(longo) <= ap.TAMANHO_DO_TEXTO and longo.endswith("anexado ao vídeo.")
    # Sem pedir a revisão: o recurso já é o pedido (pedido do Rafael, 03/11).
    assert not ap.PEDIDO_DE_REVISAO.search(longo) and not ap.PEDIDO_DE_REVISAO.search(ap.texto_sem_autoria())
    assert ap.texto_sem_autoria() == ap.TEXTO_SEM_AUTORIA.format(produto="o produto do vídeo")
    assert ap.so_com_autoria_verdadeira("Violação de Propriedade Intelectual", "autorais")


def test_tela_saude_mostra_o_texto_de_cada_punicao_sem_recurso():
    # Pedido do Rafael (25/10): "onde que eu posso ver?" o texto para recorrer, a qualquer hora.
    import robo_shopee_video as robo
    _punicao()
    sem_texto = ap.guardar("Violação de Propriedade Intelectual", "25/10/2026 14:41:08", "Não Recorrido",
                           titulo="Mesa de Jantar Redonda #mesajantar", fonte="viral", agora=AGORA)
    texto = ap.texto_saude({**robo.PADRAO}, {}, AGORA)
    assert "Para recorrer" in texto and f"<code>{TEXTO}</code>" in texto
    # A guardada sem texto (antes da P31) ganha o texto sem autoria pelo título, aqui e no aviso.
    sem_autoria = ap.texto_sem_autoria(titulo="Mesa de Jantar Redonda #mesajantar")
    assert f"<code>{sem_autoria}</code>" in texto and "Apelar aqui" in texto and "Já recorri" in texto
    assert sem_autoria in ap.montar_aviso(ap.pegar(sem_texto))
    ap.marcar(sem_texto, ap.RECORRIDA, AGORA)
    assert sem_autoria not in ap.texto_saude({**robo.PADRAO}, {}, AGORA)


def test_tela_saude_mostra_suspensao_e_punicoes():
    import robo_shopee_video as robo
    _punicao()
    config = {**robo.PADRAO, "robo_suspenso_ate": "2026-10-26 19:04:26"}
    texto = ap.texto_saude(config, {"saude_lida_em": "2026-10-23 20:00:00", "saude_pontos": 6}, AGORA)
    assert "suspensa pela Shopee até <b>26/10 às 19:04</b>" in texto and "23/10 às 20:00" in texto
    assert "Pontos de penalidade: <b>6</b> (com 6 ou mais, a Shopee suspende" in texto
    texto = ap.texto_saude({**robo.PADRAO}, {"saude_pontos": 5}, AGORA)
    assert "a 1 ponto da suspensão" in texto and "Conta sem suspensão" in texto
    assert "Punições dos últimos 30 dias: 1" in texto and "não recorrida" in texto and "Botijão" in texto
    assert "Gerar Apelação" in texto
    assert ap.ler_explicacao("Conteúdos   publicados devem promover. Apelar aqui.") == "Conteúdos publicados devem promover."


def test_recurso_nao_gasta_caracteres_pedindo_a_revisao(monkeypatch):
    # Print do Rafael de 03/11, 07:05: o texto terminava com "Solicito a revisao da punicao.", e quem
    # recorre já está pedindo a revisão; o espaço vai para os fatos, com os acentos certos.
    import api_gemini
    pedidos = []
    respostas = iter(["O vídeo mostra o removedor de fiapos do anúncio. Solicito a revisao da punicao.",
                      "O vídeo mostra o removedor de fiapos elétrico do anúncio tirando bolinhas de roupas."])

    async def gerar(prompt):
        pedidos.append(prompt)
        return next(respostas)
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", gerar)
    texto, observacao = rodar(ap.gerar_texto("Diretrizes da Comunidade", titulo="Removedor de Fiapos"))
    # A resposta que pede a revisão vai de novo à IA.
    assert texto == "O vídeo mostra o removedor de fiapos elétrico do anúncio tirando bolinhas de roupas."
    assert len(pedidos) == 2 and observacao == ""
    assert "Não peça a revisão" in pedidos[0] and "acentuação" in pedidos[0] and "termine pedindo" not in pedidos[0]
    # As duas pedindo: sai só a frase do pedido.
    respostas = iter(["O vídeo mostra o removedor de fiapos do anúncio. Peço a revisão da penalidade."] * 2)
    texto, _ = rodar(ap.gerar_texto("Diretrizes da Comunidade", titulo="Removedor de Fiapos"))
    assert texto == "O vídeo mostra o removedor de fiapos do anúncio."
    # O texto guardado antes, com o pedido, vai para copiar sem ele; o que só pede fica como está.
    guardado = _punicao(texto="O vídeo mostra o garrafão térmico do anúncio. Solicito a revisão da punição.")
    assert ap.texto_para_copiar(ap.pegar(guardado)) == "O vídeo mostra o garrafão térmico do anúncio."
    assert ap.sem_pedido_de_revisao("Peço a revisão.") == "Peço a revisão."
    assert ap.sem_pedido_de_revisao(TEXTO) == TEXTO
