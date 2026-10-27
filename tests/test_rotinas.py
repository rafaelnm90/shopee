"""rotinas.py e as rotinas de texto do bot_mestre: só as que o código conhece são agendadas e disparadas."""
import inspect
from datetime import datetime

import pytest

import rotinas
from conftest import rodar

ANTIGA = "rotina_antiga_publico"


def test_toda_rotina_conhecida_tem_texto_no_codigo(bm):
    codigo = inspect.getsource(bm._disparar_mensagem)
    for tipo in rotinas.ROTINAS_PRINCIPAIS + rotinas.ROTINAS_VIRAIS + rotinas.ROTINAS_PUBLICO:
        assert f'"{tipo}"' in codigo, tipo
    assert rotinas.conhecida("campanha_pub_0_11.11") and not rotinas.conhecida(ANTIGA)


def _config(bm, hoje):
    r = bm.ler_config_rotina()
    r.update({"pausado": False, "ultimo_bom_dia": hoje, "hora_ultimo_bom_dia": "06:00",
              "historico_diario": {"data": hoje, "contagem": {}},
              "incentivo": {"inicio": 8, "fim": 20, "frequencia": 2},
              ANTIGA: {"inicio": 8, "fim": 20, "frequencia": 5}})
    bm.salvar_config_rotina(r)


def test_chave_antiga_do_banco_nao_quebra_nem_entra_no_historico(bm, relogio, monkeypatch):
    relogio("15:00")
    hoje = datetime.now(bm.fuso_horario).strftime("%Y-%m-%d")
    _config(bm, hoje)

    async def gerar(prompt):
        pytest.fail("não devia pedir texto à IA")
    monkeypatch.setattr(bm, "gerar_mensagem_gemini", gerar)
    rodar(bm.disparar_mensagem(ANTIGA))
    assert ANTIGA not in bm.ler_config_rotina()["historico_diario"]["contagem"]
    linhas = bm.registro_processos.contagem("2000-01-01 00:00:00")
    assert any(l[2] == "ignorada (rotina sem texto no código)" and l[4] == 0 for l in linhas)


def test_chave_antiga_do_banco_nao_ganha_horario(bm, relogio):
    relogio("10:00")
    hoje = datetime.now(bm.fuso_horario).strftime("%Y-%m-%d")
    _config(bm, hoje)

    async def cenario():
        bm.scheduler.start()
        try:
            bm.agendar_tarefas_diarias("principal")
            return [job.id for job in bm.scheduler.get_jobs()]
        finally:
            bm.scheduler.shutdown(wait=False)
    ids = rodar(cenario())
    assert any(i.startswith("job_rotina_incentivo_") for i in ids)
    assert not any(ANTIGA in i for i in ids)


class Parou(Exception):
    pass


def _viral_ate_a_ia(bm, monkeypatch):
    """Sem vídeo na fila (sem intercalação); a IA levanta Parou, sinal de que a rotina ia sair."""
    monkeypatch.setattr(bm, "contar_videos_pendentes", lambda chat: 0)

    async def gerar(prompt):
        raise Parou()
    monkeypatch.setattr(bm, "gerar_mensagem_gemini", gerar)


def _historico(bm, hoje, contagem):
    r = bm.ler_config_rotina()
    r.update({"pausado_viral": False, "historico_diario": {"data": hoje, "contagem": contagem}})
    bm.salvar_config_rotina(r)


def test_mesmo_assunto_em_seguida_sai_depois_da_proxima_de_outro_assunto(bm, relogio, monkeypatch):
    # Escolha do Rafael (23/10): a rotina segura e sai depois da próxima de outro assunto.
    relogio("11:00")
    agora = datetime.now(bm.fuso_horario)
    hoje = agora.strftime("%Y-%m-%d")
    _viral_ate_a_ia(bm, monkeypatch)
    _historico(bm, hoje, {"promo_publico_viral": ["09:00"], "link_grupo_viral": ["10:00"],
                          "incentivo": ["10:30"]})      # outro canal não conta

    async def cenario():
        bm.scheduler.start()
        try:
            outra = agora.replace(hour=14, minute=0, second=0, microsecond=0)
            bm.scheduler.add_job(bm.disparar_mensagem, 'date', run_date=outra, args=["promo_principal"],
                                 id="job_rotina_promo_principal_0")
            await bm.disparar_mensagem("link_grupo_viral")
            return [(j.id, j.next_run_time.astimezone(bm.fuso_horario)) for j in bm.scheduler.get_jobs()]
        finally:
            bm.scheduler.shutdown(wait=False)
    jobs = dict(rodar(cenario()))
    adiado = next(quando for ident, quando in jobs.items() if ident.startswith("job_rotina_link_grupo_viral_seguido_"))
    assert "14:10" <= adiado.strftime("%H:%M") <= "14:25"
    assert bm.descobrir_escopo_job(next(i for i in jobs if "_seguido_" in i)) == "viral"
    assert bm.ler_config_rotina()["historico_diario"]["contagem"]["link_grupo_viral"] == ["10:00"]
    linhas = bm.registro_processos.contagem("2000-01-01 00:00:00")
    assert any(l[1] == "rotina Viral" and l[2] == "adiada (mesmo assunto em seguida)" for l in linhas)


@pytest.mark.parametrize("contagem, forcar, com_outra", [
    ({"link_grupo_viral": ["10:00"]}, False, False),                                  # nenhuma outra marcada
    ({"link_grupo_viral": ["09:00"], "promo_publico_viral": ["10:00"]}, False, True),  # a anterior é de outro assunto
    ({"link_grupo_viral": ["10:00"]}, True, True),                                    # disparo manual
])
def test_sem_assunto_seguido_ou_sem_outra_marcada_sai_na_hora(bm, relogio, monkeypatch, contagem, forcar, com_outra):
    relogio("11:00")
    agora = datetime.now(bm.fuso_horario)
    _viral_ate_a_ia(bm, monkeypatch)
    _historico(bm, agora.strftime("%Y-%m-%d"), contagem)

    async def cenario():
        bm.scheduler.start()
        try:
            if com_outra:
                bm.scheduler.add_job(bm.disparar_mensagem, 'date', args=["promo_principal"],
                                     run_date=agora.replace(hour=14, minute=0, second=0, microsecond=0),
                                     id="job_rotina_promo_principal_0")
            await bm.disparar_mensagem("link_grupo_viral", forcar=forcar)
        finally:
            bm.scheduler.shutdown(wait=False)
    with pytest.raises(Parou):
        rodar(cenario())


def test_ligar_o_bot_mantem_os_horarios_das_rotinas_de_hoje(bm, relogio):
    # 24/10: com muitos deploys no dia, cada reinício sorteava de novo e empurrava a rotina
    # para o meio da lacuna que sobrava, até depois do Boa Noite (promo_publico 0 de 1).
    from datetime import timedelta
    relogio("10:00")
    hoje = datetime.now(bm.fuso_horario).strftime("%Y-%m-%d")
    _config(bm, hoje)

    def horarios():
        return {job.id: job.next_run_time for job in bm.scheduler.get_jobs() if job.id.startswith("job_rotina_incentivo_")}

    async def cenario():
        bm.scheduler.start()
        try:
            bm.agendar_tarefas_diarias("principal")
            antes = horarios()
            # O deploy: o bot liga de novo e refaz a grade.
            bm.agendar_tarefas_diarias("principal", manter_horarios=True)
            depois = horarios()
            # Um horário que passou com o bot fora do ar sai daqui a poucos minutos.
            grade = bm.db.ler_config(bm.CHAVE_HORARIOS_ROTINAS)
            primeiro = sorted(grade["horarios"])[0]
            grade["horarios"][primeiro] = f"{hoje} 09:00:00"
            bm.db.salvar_config(bm.CHAVE_HORARIOS_ROTINAS, grade)
            bm.agendar_tarefas_diarias("principal", manter_horarios=True)
            atrasado = bm.scheduler.get_job(primeiro).next_run_time
            return antes, depois, atrasado
        finally:
            bm.scheduler.shutdown(wait=False)

    antes, depois, atrasado = rodar(cenario())
    assert len(antes) == 2 and antes == depois
    agora = datetime.now(bm.fuso_horario)
    assert agora + timedelta(minutes=2, seconds=-2) <= atrasado <= agora + timedelta(minutes=5, seconds=1)


def test_rotinas_atrasadas_pelo_reinicio_saem_espacadas_no_mesmo_canal(bm, relogio):
    # 25/10: depois de um deploy, as rotinas que passaram saíam "daqui a 2 a 5 min"; duas no
    # mesmo segundo saíram coladas no Viral (0 min). Agora ficam a 10 min ou mais no canal.
    from datetime import timedelta
    relogio("10:00")
    agora = datetime.now(bm.fuso_horario)
    hoje = agora.strftime("%Y-%m-%d")
    passou = f"{hoje} 09:00:00"
    bm.db.salvar_config(bm.CHAVE_HORARIOS_ROTINAS, {"data": hoje, "horarios": {
        "job_rotina_link_grupo_viral_0": passou, "job_rotina_promo_principal_0": passou,
        "job_rotina_divulgar_gem_viral_0": passou, "job_rotina_incentivo_0": passou}})
    viral = sorted(bm.horario_da_rotina(j, agora, True) for j in (
        "job_rotina_link_grupo_viral_0", "job_rotina_promo_principal_0", "job_rotina_divulgar_gem_viral_0"))
    assert all((b - a) >= timedelta(minutes=bm.ESPACO_DAS_ATRASADAS) for a, b in zip(viral, viral[1:]))
    assert agora + timedelta(minutes=2, seconds=-2) <= viral[0] <= agora + timedelta(minutes=5, seconds=1)
    # Outro canal não espera pelo Viral.
    principal = bm.horario_da_rotina("job_rotina_incentivo_0", agora, True)
    assert principal <= agora + timedelta(minutes=5, seconds=1)


def test_duas_rotinas_do_mesmo_canal_juntas_saem_uma_de_cada_vez(bm, monkeypatch):
    # A segunda espera a primeira terminar: assim já vê o último post como texto na
    # intercalação, em vez de as duas passarem juntas.
    import asyncio
    passos = []

    async def disparo(tipo, forcar=False):
        passos.append(("começa", tipo))
        await asyncio.sleep(0.05)
        passos.append(("acaba", tipo))
    monkeypatch.setattr(bm, "_disparar_mensagem", disparo)

    async def juntas(*tipos):
        await asyncio.gather(*(bm.disparar_mensagem(t) for t in tipos))
    rodar(juntas("link_grupo_viral", "promo_principal"))          # as duas do Viral
    assert [p[0] for p in passos] == ["começa", "acaba", "começa", "acaba"]
    passos.clear()
    rodar(juntas("link_grupo_viral", "incentivo"))                # canais diferentes não esperam
    assert [p[0] for p in passos] == ["começa", "começa", "acaba", "acaba"]


def test_rotina_do_principal_depois_do_boa_noite_fica_no_registro(bm, relogio, monkeypatch):
    relogio("22:30")
    hoje = datetime.now(bm.fuso_horario).strftime("%Y-%m-%d")
    _config(bm, hoje)
    r = bm.ler_config_rotina()
    r["ultimo_boa_noite"] = hoje
    bm.salvar_config_rotina(r)
    monkeypatch.setattr(bm, "contar_videos_pendentes", lambda chat: 0)
    rodar(bm.disparar_mensagem("incentivo"))
    linhas = bm.registro_processos.contagem("2000-01-01 00:00:00")
    assert any(l[2] == "fora do expediente (depois do Boa Noite)" and l[3] == "incentivo" for l in linhas)


def _jobs_depois_de(bm, tipo, **kwargs):
    async def cenario():
        bm.scheduler.start()
        try:
            await bm.disparar_mensagem(tipo, **kwargs)
            return {j.id: j.next_run_time.astimezone(bm.fuso_horario) for j in bm.scheduler.get_jobs()}
        finally:
            bm.scheduler.shutdown(wait=False)
    return rodar(cenario())


def test_rotina_a_menos_de_10_min_da_ultima_do_canal_espera_completar(bm, relogio, monkeypatch):
    # 26/10, Viral: 21:39 divulgar_gem_viral e 21:48 promo_publico_viral. Sem vídeo do dia na
    # fila, a intercalação não segurava. As rotinas saem espaçadas (DECISOES.md).
    relogio("21:48")
    agora = datetime.now(bm.fuso_horario)
    _viral_ate_a_ia(bm, monkeypatch)
    _historico(bm, agora.strftime("%Y-%m-%d"), {"divulgar_gem_viral": ["21:39"], "incentivo": ["21:47"]})
    jobs = _jobs_depois_de(bm, "promo_publico_viral")
    adiado = next(quando for ident, quando in jobs.items()
                  if ident.startswith("job_rotina_promo_publico_viral_reagendado_"))
    assert "21:50" <= adiado.strftime("%H:%M") <= "21:59"
    assert bm.descobrir_escopo_job(next(i for i in jobs if "_reagendado_" in i)) == "viral"
    assert "promo_publico_viral" not in bm.ler_config_rotina()["historico_diario"]["contagem"]
    linhas = bm.registro_processos.contagem("2000-01-01 00:00:00")
    assert any(l[1] == "rotina Viral" and l[2] == "adiada (espaçamento)" for l in linhas)


@pytest.mark.parametrize("hora, contagem, forcar", [
    ("21:50", {"divulgar_gem_viral": ["21:39"]}, False),     # 11 min depois: sai
    ("21:48", {"incentivo": ["21:45"]}, False),               # a de 3 min atrás é de outro canal
    ("21:48", {"divulgar_gem_viral": ["21:39"]}, True),      # disparo manual
])
def test_rotina_espacada_ou_de_outro_canal_sai_na_hora(bm, relogio, monkeypatch, hora, contagem, forcar):
    relogio(hora)
    _viral_ate_a_ia(bm, monkeypatch)
    _historico(bm, datetime.now(bm.fuso_horario).strftime("%Y-%m-%d"), contagem)
    with pytest.raises(Parou):
        _jobs_depois_de(bm, "promo_publico_viral", forcar=forcar)


def test_rotina_espera_o_tempo_que_o_telegram_pede_e_tenta_de_novo(bm, monkeypatch):
    # 26/10, Viral: link_grupo_viral falhou com TelegramRetryAfter e se perdeu.
    from aiogram.exceptions import TelegramRetryAfter
    from aiogram.methods import SendMessage
    esperas, tentativas = [], []

    async def dormir(segundos):
        esperas.append(segundos)
    monkeypatch.setattr(bm.asyncio, "sleep", dormir)

    def envio(pede):
        async def enviar():
            tentativas.append(1)
            if len(tentativas) == 1:
                raise TelegramRetryAfter(method=SendMessage(chat_id=1, text="x"), message="Flood", retry_after=pede)
            return "enviada"
        return enviar

    assert rodar(bm.com_espera_do_telegram(envio(7))) == "enviada"
    assert esperas == [8] and len(tentativas) == 2
    # Espera longa demais: não segura a rotina, a falha fica no registro como antes.
    tentativas.clear()
    with pytest.raises(TelegramRetryAfter):
        rodar(bm.com_espera_do_telegram(envio(bm.ESPERA_MAXIMA_DO_TELEGRAM + 1)))
    assert len(tentativas) == 1
