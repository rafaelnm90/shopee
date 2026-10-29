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


@pytest.mark.parametrize("contagem, forcar, com_outra, anotada", [
    ({"link_grupo_viral": ["10:00"]}, False, False, True),                                  # nenhuma outra marcada
    ({"link_grupo_viral": ["09:00"], "promo_publico_viral": ["10:00"]}, False, True, False),  # a anterior é de outro assunto
    ({"link_grupo_viral": ["10:00"]}, True, True, False),                                   # disparo manual
])
def test_sem_assunto_seguido_ou_sem_outra_marcada_sai_na_hora(bm, relogio, monkeypatch, contagem, forcar, com_outra,
                                                             anotada):
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
    # A que sai em seguida porque não havia outra marcada fica anotada: o checkup não a cobra.
    linhas = bm.registro_processos.contagem("2000-01-01 00:00:00")
    assert any(l[1] == "rotina Viral" and l[2] == bm.rotinas.EM_SEGUIDA_SEM_OUTRO for l in linhas) == anotada


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


def _texto_por_ultimo_e_video_na_fila(bm, monkeypatch):
    """O último post do canal foi texto e há vídeo do dia na fila: a intercalação segura a rotina."""
    monkeypatch.setattr(bm, "contar_videos_pendentes", lambda chat: 2)
    monkeypatch.setattr(bm, "obter_ultimo_post", lambda chat: "texto")

    async def gerar(prompt):
        raise Parou()
    monkeypatch.setattr(bm, "gerar_mensagem_gemini", gerar)


def _disparos(bm, tipo, horas, boa_noite=None):
    """
    Dispara a rotina em cada hora de horas (o relógio anda entre um e outro, como o bot que
    tenta de novo) e devolve, de cada uma, o horário do novo disparo ou "saiu".
    """
    import time_machine
    from conftest import _instante

    async def cenario():
        bm.scheduler.start()
        try:
            if boa_noite:
                bm.scheduler.add_job(bm.disparar_mensagem, 'cron', hour=boa_noite[0], minute=boa_noite[1],
                                     timezone=bm.FUSO_STR, args=["boa_noite"], id="job_rotina_boa_noite_0")
            resultados = []
            for hora in horas:
                with time_machine.travel(_instante(hora), tick=True):
                    try:
                        await bm.disparar_mensagem(tipo)
                    except Parou:
                        resultados.append("saiu")
                        continue
                    adiados = [j for j in bm.scheduler.get_jobs() if "_intercalado_" in j.id]
                    resultados.append(adiados[0].next_run_time.astimezone(bm.fuso_horario).strftime("%H:%M:%S"))
                    for job in adiados:
                        job.remove()
            return resultados
        finally:
            bm.scheduler.shutdown(wait=False)
    return rodar(cenario())


def test_rotina_espera_o_video_no_maximo_1_hora_e_depois_sai(bm, relogio, monkeypatch):
    # 29/10, Canal Afiliados: com 1 ou 2 vídeos por dia, a rotina esperava um vídeo o dia todo
    # e se perdia depois do Boa Noite (2 de 9 até as 16:31). Escolha do Rafael (P84): espera no
    # máximo 1 h. Cada disparo aqui é uma chamada nova, como depois de um reinício do bot: a
    # espera fica no banco e não começa de novo.
    relogio("14:00")
    hoje = datetime.now(bm.fuso_horario).strftime("%Y-%m-%d")
    _config(bm, hoje)
    _texto_por_ultimo_e_video_na_fila(bm, monkeypatch)
    primeiro, segundo, terceiro = _disparos(bm, "incentivo", ["14:00", "14:50", "15:01"])
    assert "14:20:00" <= primeiro <= "14:45:59"
    assert segundo == "15:00:00"                     # o novo disparo não passa de 1 h de espera
    assert terceiro == "saiu"
    assert bm.ler_config_rotina()["historico_diario"]["contagem"]["incentivo"] == ["15:01"]
    linhas = bm.registro_processos.contagem("2000-01-01 00:00:00")
    assert any(l[2] == "sem esperar mais o vídeo (1 h)" and l[3] == "incentivo" for l in linhas)
    # Saiu: a próxima do mesmo assunto espera do zero.
    assert "incentivo" not in bm.db.ler_config(bm.CHAVE_ESPERA_PELO_VIDEO)["desde"]


@pytest.mark.parametrize("tipo, horas, boa_noite, adiado, motivo", [
    ("incentivo", ["19:50", "20:00:30"], None, "20:00:00", "fim da janela"),            # janela 8h às 20h
    ("divulgar_gem", ["20:30", "20:41"], (21, 10), "20:40:00", "antes do Boa Noite"),   # janela 8h às 22h
    ("link_grupo_viral", ["20:45", "21:00:30"], (21, 10), "21:00:00", "fim da janela"),  # o Viral não tem Boa Noite
])
def test_a_espera_pelo_video_nao_passa_do_fim_da_janela_nem_do_boa_noite(bm, relogio, monkeypatch, tipo, horas,
                                                                       boa_noite, adiado, motivo):
    relogio(horas[0])
    hoje = datetime.now(bm.fuso_horario).strftime("%Y-%m-%d")
    _config(bm, hoje)
    _texto_por_ultimo_e_video_na_fila(bm, monkeypatch)
    assert _disparos(bm, tipo, horas, boa_noite) == [adiado, "saiu"]
    linhas = bm.registro_processos.contagem("2000-01-01 00:00:00")
    assert any(l[2] == f"sem esperar mais o vídeo ({motivo})" and l[3] == tipo for l in linhas)


# As janelas que o Rafael usa no Canal Afiliados (vídeo de 29/10, 16:44).
JANELAS_DO_CANAL = {"bom_dia": (7, 8, 1), "incentivo": (10, 20, 2), "link_grupo": (9, 21, 1), "divulgar_gem": (8, 22, 1),
                    "promo_viral": (10, 20, 1), "promo_publico": (10, 20, 1), "promo_achadinhos": (10, 20, 1),
                    "boa_noite": (21, 23, 1)}


def _janelas_do_canal(bm, **extras):
    r = bm.ler_config_rotina()
    r.update({tipo: {"inicio": i, "fim": f, "frequencia": q} for tipo, (i, f, q) in JANELAS_DO_CANAL.items()})
    r.update({"pausado": False, "historico_diario": {"data": "", "contagem": {}}}, **extras)
    bm.salvar_config_rotina(r)


def _horarios_do_principal(bm):
    async def cenario():
        bm.scheduler.start()
        try:
            bm.agendar_tarefas_diarias("principal")
            return {j.id: j.next_run_time.astimezone(bm.fuso_horario) for j in bm.scheduler.get_jobs()
                    if j.id.startswith("job_rotina_")}
        finally:
            bm.scheduler.shutdown(wait=False)
    return rodar(cenario())


def test_rotinas_do_canal_afiliados_saem_na_janela_do_painel(bm, relogio):
    # 29/10: no Canal Afiliados a janela do painel não entrava no sorteio, e uma rotina de 10h
    # às 20h podia sair às 9:45. Escolha do Rafael (P85): cada uma sai na janela dela.
    import random
    from datetime import timedelta
    relogio("00:30")
    _janelas_do_canal(bm)
    for semente in range(30):
        random.seed(semente)
        horarios = _horarios_do_principal(bm)
        rotinas_do_dia = {ident: quando for ident, quando in horarios.items()
                          if not ident.startswith(("job_rotina_bom_dia", "job_rotina_boa_noite"))}
        assert len(rotinas_do_dia) == 7, semente
        for ident, quando in rotinas_do_dia.items():
            inicio, fim, _q = JANELAS_DO_CANAL[ident[len("job_rotina_"):].rsplit("_", 1)[0]]
            assert inicio * 60 <= quando.hour * 60 + quando.minute <= fim * 60, (semente, ident, quando)
        todas = sorted(horarios.values())
        assert all(b - a >= timedelta(minutes=10) for a, b in zip(todas, todas[1:])), semente


def test_rotina_com_a_janela_de_hoje_ja_passada_sai_logo_antes_do_boa_noite(bm, relogio):
    # O bot fora do ar ou o painel editado depois do fim da janela: a rotina sai logo, antes do
    # Boa Noite, para não se perder.
    relogio("20:30")
    hoje = datetime.now(bm.fuso_horario).strftime("%Y-%m-%d")
    _janelas_do_canal(bm, ultimo_bom_dia=hoje, hora_ultimo_bom_dia="07:30")
    horarios = _horarios_do_principal(bm)
    boa_noite = horarios["job_rotina_boa_noite_0"]
    incentivos = [quando for ident, quando in horarios.items() if ident.startswith("job_rotina_incentivo_")]
    assert len(incentivos) == 2
    agora = datetime.now(bm.fuso_horario)
    assert all(agora < quando < boa_noite for quando in incentivos)


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
