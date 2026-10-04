"""inventario.py: cada linha do journal é ligada à chamada de log que a gerou."""
import inventario


def test_linha_do_journal_volta_para_o_lugar_do_codigo():
    modelos = inventario.modelos_de_log()
    assert len(modelos) > 500
    linhas = [
        "2026-10-03 19:11:52.123 -0300 - 🧹 [Faxina] Nada a remover. 3 arquivo(s) em fila protegidos.",
        "2026-10-03 19:11:52.123 -0300 - 🧹 [Faxina] Nada a remover. 7 arquivo(s) em fila protegidos.",
        "2026-10-03 19:11:53.000 -0300 - linha de biblioteca, sem modelo no código",
    ]
    ranking, sem_modelo = inventario.perfil_do_log(linhas, modelos)
    (onde, texto), qtd = ranking[0]
    assert onde.startswith("bot_mestre.py:") and qtd == 2
    assert "{…}" in texto           # o número variável vira coringa, nunca o valor
    assert sem_modelo == 1


def test_tamanho_legivel():
    assert inventario.tamanho_legivel(512) == "512 B"
    assert inventario.tamanho_legivel(5 * 1024 * 1024) == "5.0 MB"


def test_erros_por_origem_e_tipo_sem_o_texto_do_erro(capsys):
    from utils import registrar_erro_json
    for _ in range(2):
        try:
            raise ValueError("Could not find the input entity for -100123 (segredo)")
        except ValueError as e:
            registrar_erro_json(f"varredura_origem_loop: {e}", origem="espelhador_videos_autorais.py")
    registrar_erro_json("enviar_mensagem (principal/@grupo): falhou", origem="divulgacao_canal.py")

    inventario.erros_registrados()
    saida = capsys.readouterr().out
    assert "ValueError" in saida and "varredura_origem_loop" in saida
    assert "2x" in saida and "enviar_mensagem" in saida
    assert "segredo" not in saida and "-100123" not in saida and "@grupo" not in saida


def test_captura_dos_parceiros_so_numeros_e_motivos(bm, capsys):
    bm.db.salvar_config("diagnostico_parceiros", {"1": {
        "data": "2026-10-04", "mensagens": 12, "videos": 5, "com_link": 0, "capturados": 0,
        "recusados": {"vídeo sem link da Shopee": 5}, "ultima_mensagem": "2026-10-04 10:00:00"}})
    inventario.captura_dos_parceiros()
    saida = capsys.readouterr().out
    assert "parceiro #1 em 2026-10-04: 12 mensagem(ns), 5 vídeo(s), 0 com link" in saida
    assert "recusado: vídeo sem link da Shopee (5)" in saida


def test_contas_dos_autorais_so_estados_sem_nome_nem_telefone(bm, pc, capsys):
    pc.salvar_conta("joana", telefone="+5511999990000", user_id=777, username="joaninha",
                    nome_exibicao="Joana Silva")
    pc.atualizar_status("joana", status_grupo=pc.STATUS_NUNCA_ENTROU,
                        erro="grupo não encontrado nem depois de carregar as conversas")
    pc.salvar_conta("outra")
    pc.atualizar_status("outra", erro="ValueError: Could not find the input entity for PeerChannel(1234)")
    bm.db.salvar_config("autorais_config", {"origem": "-1001234:5"})

    inventario.contas_dos_autorais()
    saida = capsys.readouterr().out

    assert "conta #1: grupo NUNCA_ENTROU, sessão OK" in saida
    assert "erro: grupo não encontrado nem depois de carregar as conversas" in saida
    assert "erro: ValueError" in saida and "1234" not in saida.split("origem")[0]
    assert "STATUS_GRUPO (DESCONHECIDO → NUNCA_ENTROU)" in saida
    assert "origem dos Autorais gravada como str com tópico" in saida
    for privado in ("joana", "joaninha", "Joana", "99999", "777"):
        assert privado not in saida
