#!/usr/bin/env python3
"""
Checkup do dia: o que pode ter dado errado nos robôs, em números que o Claude
confere sozinho. Roda no servidor pelo checkup.yml (todo dia às 22:20 e à mão);
o Claude lê o resultado na rotina do checkup diário, investiga cada ponto de
atenção e corrige pelo PR. O que ainda não dá para conferir por aqui ganha uma
seção nova (DECISOES.md, Trabalho com o Claude).

Só lê. O repositório e os logs do Actions são públicos: saem só números,
estados, horários e trechos fixos do código (arquivo:linha e o texto fixo de
cada chamada de log ou de registrar_erro_json, com {…} no lugar das variáveis).
Nunca o texto de um erro, de um log, de uma fila ou do banco.

Seções: erros registrados (erros_logs), log de cada robô (quedas, rastros de
erro pelo tipo e pelo lugar do código, avisos e erros por lugar do código),
processos dos robôs (registro_processos.py), postagens de hoje por fila, robô
da Shopee Vídeo, Baixador e backup. No fim, os pontos de atenção.
"""
import os
import re
import sqlite3
import subprocess
from datetime import datetime, timedelta

import backup_dados
import db
import inventario
import registro_processos
from fuso import fuso_horario

# Erro que já tem seção própria no diagnostico.yml (Links sem conversão).
ORIGENS_A_PARTE = ("Link sem conversão",)
# Um erro é "novo" quando não apareceu nos 7 dias antes das últimas 24 h.
DIAS_PARA_NOVO = 7
# Item de fila com horário vencido há mais que isso e ainda não postado.
ATRASO_TOLERADO = timedelta(minutes=30)
# O backup roda às 03:40; mais de 26 h sem um novo quer dizer que um dia falhou.
IDADE_MAXIMA_BACKUP_H = 26
# Fila sem nenhum post até a noite, com média de pelo menos isso por dia, é ponto de atenção.
MEDIA_PARA_COBRAR = 2
HORA_PARA_COBRAR = 18
# Processo com pelo menos tantas falhas, e não menos falhas que acertos, é ponto de atenção.
FALHAS_PARA_COBRAR = 3
# Quantos lugares do código mostrar por robô no log.
LUGARES_POR_ROBO = 5
# As chaves do robo_shopee_video (sem importá-lo, que traz a IA e o celular junto; o
# tests/test_checkup.py confere que são as mesmas). O robô começa pausado.
CHAVE_CONFIG_SV, CHAVE_DIA_SV = "shopee_video", "shopee_video_robo_dia"
# Resultados do robô da Shopee Vídeo que pedem investigação.
RESULTADOS_RUINS = ("erro", "parou", "verificação", "treino parou")


def mascarar(texto):
    """Números longos (ids de chat, de mensagem) viram #."""
    return re.sub(r"-?\d{5,}", "#", str(texto or ""))


def _agora(agora=None):
    return agora or datetime.now(fuso_horario)


def _momento(quando):
    return quando.strftime("%Y-%m-%d %H:%M:%S")


# --- Erros registrados ---

def modelos_de_erro():
    """Cada registrar_erro_json do código, para ligar a linha do erros_logs ao lugar que a gravou."""
    def eh_registro(n):
        nome = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
        return "erro" if nome == "registrar_erro_json" else None
    return inventario.modelos_de_chamadas(eh_registro)


def lugar_do_erro(erro, modelos):
    """(arquivo:linha, texto fixo) de quem gravou o erro, ou None."""
    for regex, onde, texto, *_ in modelos:
        if regex.match(erro or ""):
            return onde, texto
    return None


def erros_registrados(agora=None):
    """
    Os erros_logs das últimas 24 h agrupados por origem, lugar do código e tipo da
    exceção: [{origem, lugar, texto, tipo, qtd, ultimo, novo}], o mais frequente primeiro.
    """
    agora = _agora(agora)
    desde, antes = agora - timedelta(hours=24), agora - timedelta(hours=24, days=DIAS_PARA_NOVO)
    try:
        with db.conexao() as conexao:
            linhas = conexao.execute(
                "SELECT timestamp, origem, erro, rastro_codigo FROM erros_logs WHERE timestamp >= ?",
                (_momento(antes),)).fetchall()
    except sqlite3.OperationalError:
        return []
    modelos = modelos_de_erro()
    grupos = {}
    for quando, origem, erro, rastro in linhas:
        if origem in ORIGENS_A_PARTE:
            continue
        lugar = lugar_do_erro(erro, modelos)
        onde, tipo = inventario.classificar_erro(erro, rastro)
        lugar, texto = lugar or ("(sem lugar no código)", mascarar(onde))
        grupo = grupos.setdefault((mascarar(origem), lugar, texto, tipo), {"qtd": 0, "ultimo": "", "antes": 0})
        if (quando or "") >= _momento(desde):
            grupo["qtd"] += 1
            grupo["ultimo"] = max(grupo["ultimo"], quando or "")
        else:
            grupo["antes"] += 1
    saida = [{"origem": origem, "lugar": lugar, "texto": texto, "tipo": tipo, "qtd": g["qtd"],
              "ultimo": g["ultimo"][11:16], "novo": not g["antes"]}
             for (origem, lugar, texto, tipo), g in grupos.items() if g["qtd"]]
    return sorted(saida, key=lambda e: -e["qtd"])


# --- Log de cada robô ---

def ler_journal(servico):
    r = subprocess.run(["sudo", "-n", "journalctl", "-u", f"{servico}.service", "--since", "24 hours ago",
                        "-o", "cat", "-q"], capture_output=True, text=True, timeout=180)
    if r.returncode and not r.stdout:
        # Sem acesso ao journal não é o mesmo que um dia sem log.
        raise PermissionError(f"journalctl saiu com {r.returncode}")
    return [linha for linha in r.stdout.splitlines() if linha.strip()]


def _lugar_do_quadro(caminho, linha, funcao):
    """O quadro do rastro como arquivo:linha (função); de biblioteca, o caminho dentro dela."""
    if "site-packages/" in caminho:
        return f"{caminho.split('site-packages/', 1)[1]}:{linha}"
    return f"{os.path.basename(caminho)}:{linha} ({funcao})"


def _eh_do_projeto(caminho):
    return caminho.endswith(".py") and "site-packages/" not in caminho and not caminho.startswith("/usr/")


def rastros_do_log(linhas):
    """
    Os rastros de erro do log agrupados pelo tipo da exceção e pelo último lugar do
    código do projeto por onde passaram (ou, sem nenhum, o último da biblioteca):
    [(tipo, lugar, quantidade)], o mais frequente primeiro. A mensagem da exceção,
    que pode ter dados, não sai.
    """
    grupos, i = {}, 0
    while i < len(linhas):
        if not linhas[i].startswith("Traceback (most recent call last)"):
            i += 1
            continue
        do_projeto = de_biblioteca = None
        i += 1
        while i < len(linhas) and linhas[i][:1] in (" ", "\t"):
            quadro = re.match(r'\s+File "([^"]+)", line (\d+), in (\S+)', linhas[i])
            if quadro:
                caminho, linha, funcao = quadro.groups()
                lugar = _lugar_do_quadro(caminho, linha, funcao)
                if _eh_do_projeto(caminho):
                    do_projeto = lugar
                else:
                    de_biblioteca = lugar
            i += 1
        tipo = re.match(r"([A-Za-z_][\w.]*)", linhas[i].strip()) if i < len(linhas) else None
        chave = (tipo.group(1) if tipo else "?", do_projeto or de_biblioteca or "?")
        grupos[chave] = grupos.get(chave, 0) + 1
    return sorted(((tipo, lugar, qtd) for (tipo, lugar), qtd in grupos.items()), key=lambda r: -r[2])


def resumo_do_log(linhas, modelos):
    """
    O que o log de um robô diz das últimas 24 h, só em números e lugares do código:
    inícios, quedas (o systemd reiniciou sozinho), rastros de erro, avisos e erros
    por lugar do código.
    """
    nivel_de = {onde: nivel for _r, onde, _t, _f, _i, nivel in modelos}
    ranking, _sem_modelo = inventario.perfil_do_log(linhas, modelos)
    problemas = [(onde, texto, nivel_de.get(onde), qtd) for (onde, texto), qtd in ranking
                 if nivel_de.get(onde) in ("warning", "error", "exception", "critical")]
    return {
        "inicios": sum(1 for l in linhas if l.startswith("Started ")),
        "quedas": sum(1 for l in linhas if "Scheduled restart job" in l or "Failed with result" in l),
        "rastros": sum(1 for l in linhas if l.startswith("Traceback (most recent call last)")),
        "rastros_por_lugar": rastros_do_log(linhas),
        "avisos": sum(qtd for _o, _t, nivel, qtd in problemas if nivel == "warning"),
        "erros": sum(qtd for _o, _t, nivel, qtd in problemas if nivel != "warning"),
        "problemas": problemas,
    }


# --- Processos dos robôs ---

def processos_do_dia(agora=None):
    """
    O registro dos processos das últimas 24 h por robô e processo: acertos, falhas,
    neutros e cada resultado com o detalhe (textos fixos do código).
    """
    desde = _momento(_agora(agora) - timedelta(hours=24))
    processos = {}
    for robo, processo, resultado, detalhe, ok, qtd in registro_processos.contagem(desde):
        p = processos.setdefault((robo, processo), {"ok": 0, "falhas": 0, "neutros": 0, "resultados": []})
        p["ok" if ok == 1 else "falhas" if ok == 0 else "neutros"] += qtd
        p["resultados"].append((resultado, detalhe, ok, qtd))
    return processos


# --- Postagens de hoje ---

def _contar(sql, *params):
    try:
        with db.conexao() as conexao:
            return conexao.execute(sql, params).fetchone()[0] or 0
    except sqlite3.OperationalError:
        return None


def _media_da_metrica(chave, hoje):
    """Média de posts por dia nos 7 dias antes de hoje, pelo retrato das 23:50 (historico_metricas)."""
    try:
        with db.conexao() as conexao:
            valores = [v for (v,) in conexao.execute(
                "SELECT valor FROM historico_metricas WHERE chave = ? AND data < ? ORDER BY data DESC LIMIT 7",
                (chave, hoje))]
    except sqlite3.OperationalError:
        return None
    return sum(valores) / len(valores) if valores else None


def _media_da_tabela(tabela, hoje):
    """Média de posts por dia nos 7 dias antes de hoje, pela data_postagem da própria fila."""
    inicio = (datetime.strptime(hoje, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    total = _contar(f"SELECT COUNT(*) FROM {tabela} WHERE processado = 1 "
                    "AND substr(data_postagem, 1, 10) >= ? AND substr(data_postagem, 1, 10) < ?", inicio, hoje)
    return None if total is None else total / 7


def postagens_de_hoje(agora=None):
    """
    Por fila: postados hoje, ainda na fila para hoje, atrasados (horário vencido há mais
    de 30 min, ou dia anterior no canal principal) e a média dos 7 dias anteriores.
    """
    agora = _agora(agora)
    hoje, limite = agora.strftime("%Y-%m-%d"), _momento(agora - ATRASO_TOLERADO)
    filas = {}

    filas["Canal principal"] = {
        "postados": _contar("SELECT COUNT(*) FROM fila_postagens WHERE status = 'CONCLUIDO' AND data_postagem = ?", hoje),
        "para_hoje": _contar("SELECT COUNT(*) FROM fila_postagens WHERE status = 'PENDENTE' AND data_alvo = ?", hoje),
        # '2000-01-01' é a marca de "postar já", não um dia atrasado.
        "atrasados": _contar("SELECT COUNT(*) FROM fila_postagens WHERE status = 'PENDENTE' "
                             "AND data_alvo < ? AND data_alvo != '2000-01-01'", hoje),
        "media": _media_da_metrica("posts_dia_principal", hoje),
    }

    fila_viral = (db.ler_config("fila_clonagem", {}) or {}).get("fila", [])
    pendentes = [i for i in fila_viral if not i.get("processado")]
    filas["Viral"] = {
        "postados": sum(1 for i in fila_viral if i.get("processado") and str(i.get("data_postagem")) == hoje),
        "para_hoje": sum(1 for i in pendentes if str(i.get("horario_disparo") or "").startswith(hoje)),
        "atrasados": sum(1 for i in pendentes if i.get("horario_disparo") and i["horario_disparo"] < limite),
        "media": _media_da_metrica("posts_dia_viral", hoje),
    }

    for nome, tabela, metrica in (("Grupo Público", "fila_publico", "posts_dia_publico"),
                                  ("Autorais", "fila_autorais", None),
                                  ("Parceiros", "fila_parceiros", None)):
        filas[nome] = {
            "postados": _contar(f"SELECT COUNT(*) FROM {tabela} WHERE processado = 1 "
                                "AND substr(data_postagem, 1, 10) = ?", hoje),
            "para_hoje": _contar(f"SELECT COUNT(*) FROM {tabela} WHERE processado = 0 AND data_alvo = ?", hoje),
            "atrasados": _contar(f"SELECT COUNT(*) FROM {tabela} WHERE processado = 0 "
                                 "AND horario_disparo != '' AND horario_disparo < ?", limite),
            "media": _media_da_metrica(metrica, hoje) if metrica else _media_da_tabela(tabela, hoje),
        }
    return filas


# --- Robô da Shopee Vídeo ---

def robo_da_shopee_video(agora=None):
    """Plano de hoje, rascunhos salvos hoje e as tentativas ruins das últimas 24 h (ação, resultado, passo)."""
    agora = _agora(agora)
    pausado = (db.ler_config(CHAVE_CONFIG_SV, {}) or {}).get("robo_pausado", True)
    plano = db.ler_config(CHAVE_DIA_SV, {}) or {}
    hoje = agora.strftime("%Y-%m-%d")
    horarios = plano.get("horarios", []) if plano.get("data") == hoje else []
    vencidos = sum(1 for h in horarios if h <= agora.strftime("%H:%M"))
    # Pela tabela dos rascunhos, que guarda todos; o histórico das tentativas pode ter
    # começado depois.
    salvos = _contar("SELECT COUNT(*) FROM shopee_video_rascunhos WHERE criado_em >= ? "
                     "AND estado NOT IN ('pulado', 'preparando')", hoje)
    try:
        with db.conexao() as conexao:
            ruins = conexao.execute(
                "SELECT acao, resultado, passo, COUNT(*) FROM shopee_video_tentativas WHERE momento >= ? "
                f"AND resultado IN ({','.join('?' * len(RESULTADOS_RUINS))}) GROUP BY 1, 2, 3 ORDER BY 4 DESC",
                (_momento(agora - timedelta(hours=24)), *RESULTADOS_RUINS)).fetchall()
    except sqlite3.OperationalError:
        ruins = []
    pulados = _contar("SELECT COUNT(*) FROM shopee_video_rascunhos WHERE criado_em >= ? AND estado = 'pulado'", hoje)
    return {"ativo": not pausado, "horarios": len(horarios), "vencidos": vencidos,
            "salvos": salvos or 0, "pulados": pulados or 0, "ruins": ruins}


# --- Baixador e backup ---

def baixador(linhas):
    """Entregues e falhas de download nas últimas 24 h, pelas linhas fixas do log do Baixador."""
    total = {}
    for contagem in inventario.contar_baixador(linhas).values():
        for evento, qtd in contagem.items():
            total[evento] = total.get(evento, 0) + qtd
    return total


# --- Pontos de atenção ---

def pontos_de_atencao(erros, logs, filas, robo_sv, baixados, backup, agora=None, processos=None):
    """As frases fixas, com números, do que o Claude precisa investigar."""
    agora = _agora(agora)
    pontos = []
    for e in erros:
        if e["novo"] or e["qtd"] >= 3:
            marca = "erro novo" if e["novo"] else "erro repetido"
            pontos.append(f"{marca}: {e['qtd']}x {e['lugar']} ({e['tipo']}, origem {e['origem']})")
    for servico, r in logs.items():
        if r["quedas"]:
            pontos.append(f"{servico}: caiu e o systemd reiniciou {r['quedas']} vez(es)")
        if r["rastros"]:
            tipo, lugar, qtd = (r.get("rastros_por_lugar") or [("?", "?", r["rastros"])])[0]
            pontos.append(f"{servico}: {r['rastros']} rastro(s) de erro no log (mais comum: {tipo} em {lugar}, {qtd}x)")
        erros_do_log = [p for p in r["problemas"] if p[2] != "warning"]
        if erros_do_log:
            onde, _t, _n, qtd = erros_do_log[0]
            pontos.append(f"{servico}: {r['erros']} linha(s) de erro no log (mais comum: {onde}, {qtd}x)")
    for nome, f in filas.items():
        if f["atrasados"]:
            pontos.append(f"{nome}: {f['atrasados']} item(ns) atrasado(s) na fila")
        if (f["postados"] == 0 and (f["media"] or 0) >= MEDIA_PARA_COBRAR and agora.hour >= HORA_PARA_COBRAR):
            pontos.append(f"{nome}: nenhum post hoje (média de {f['media']:.1f} por dia)")
    if robo_sv["ativo"] and robo_sv["salvos"] < robo_sv["vencidos"]:
        pontos.append(f"Robô da Shopee Vídeo: {robo_sv['vencidos']} horário(s) vencido(s) hoje e "
                      f"{robo_sv['salvos']} rascunho(s) salvo(s) ({robo_sv.get('pulados', 0)} vídeo(s) pulado(s))")
    for acao, resultado, passo, qtd in robo_sv["ruins"]:
        pontos.append(f"Robô da Shopee Vídeo: {acao} → {resultado} em \"{passo or '?'}\" {qtd}x")
    for (robo, processo), p in (processos or {}).items():
        if p["falhas"] >= FALHAS_PARA_COBRAR and p["falhas"] >= p["ok"]:
            resultado, detalhe, _ok, qtd = max((r for r in p["resultados"] if r[2] == 0), key=lambda r: r[3])
            pontos.append(f"{robo}: {processo}: {p['falhas']} falha(s) e {p['ok']} acerto(s) "
                          f"(mais comum: {resultado}{f' - {detalhe}' if detalhe else ''}, {qtd}x)")
    falhas = baixados.get("falha(s) de download", 0)
    if falhas >= 3 and falhas > baixados.get("entregue(s)", 0):
        pontos.append(f"Baixador: {falhas} falha(s) de download e {baixados.get('entregue(s)', 0)} entregue(s)")
    if backup is None:
        pontos.append("Backup: nenhum em ~/backups")
    elif backup[1] > IDADE_MAXIMA_BACKUP_H:
        pontos.append(f"Backup: o último tem {backup[1]:.0f} h")
    return pontos


# --- Saída ---

def _num(valor):
    return "?" if valor is None else valor


def main():
    agora = _agora()
    print(f"Checkup de {agora.strftime('%d/%m %H:%M')} (últimas 24 h)")

    print("\n== Erros registrados (erros_logs, sem os Links sem conversão)")
    erros = erros_registrados(agora)
    for e in erros:
        print(f"{e['qtd']:4}x  origem {e['origem']} | {e['lugar']} \"{e['texto']}\" | {e['tipo']} | "
              f"último {e['ultimo']}{' | NOVO' if e['novo'] else ''}")
    if not erros:
        print("nenhum")

    print("\n== Log de cada robô")
    modelos = inventario.modelos_de_log()
    logs, linhas_baixador, sem_journal = {}, [], []
    for servico in inventario.SERVICOS:
        try:
            linhas = ler_journal(servico)
        except Exception as e:
            print(f"{servico}: sem acesso ao journal ({type(e).__name__})")
            sem_journal.append(f"{servico}: sem acesso ao journal, o log não foi conferido")
            continue
        if servico == "downloader_bot":
            linhas_baixador = linhas
        r = logs[servico] = resumo_do_log(linhas, modelos)
        print(f"{servico}: {len(linhas)} linha(s) | inícios {r['inicios']} | quedas {r['quedas']} | "
              f"rastros {r['rastros']} | avisos {r['avisos']} | erros {r['erros']}")
        for onde, texto, nivel, qtd in r["problemas"][:LUGARES_POR_ROBO]:
            print(f"   {qtd:5}x {nivel:8} {onde:34} {texto}")
        for tipo, lugar, qtd in r["rastros_por_lugar"][:LUGARES_POR_ROBO]:
            print(f"   {qtd:5}x rastro   {tipo} em {lugar}")

    print("\n== Processos dos robôs (registro, últimas 24 h)")
    processos = processos_do_dia(agora)
    for (robo, processo), p in processos.items():
        print(f"{robo}: {processo}: acertos {p['ok']} | falhas {p['falhas']} | outros {p['neutros']}")
        for resultado, detalhe, _ok, qtd in p["resultados"]:
            print(f"   {qtd:5}x {resultado}{f' - {detalhe}' if detalhe else ''}")
    if not processos:
        print("nenhum processo registrado")

    print("\n== Postagens de hoje")
    filas = postagens_de_hoje(agora)
    for nome, f in filas.items():
        media = "?" if f["media"] is None else f"{f['media']:.1f}"
        print(f"{nome}: postados {_num(f['postados'])} | ainda para hoje {_num(f['para_hoje'])} | "
              f"atrasados {_num(f['atrasados'])} | média dos 7 dias anteriores {media}/dia")

    print("\n== Robô da Shopee Vídeo")
    robo_sv = robo_da_shopee_video(agora)
    print(f"{'ativo' if robo_sv['ativo'] else 'pausado'} | horários hoje {robo_sv['horarios']} | "
          f"vencidos {robo_sv['vencidos']} | rascunhos salvos hoje {robo_sv['salvos']} | "
          f"vídeos pulados hoje {robo_sv['pulados']}")
    for acao, resultado, passo, qtd in robo_sv["ruins"]:
        print(f"   {qtd}x {acao} → {resultado} em \"{passo or '?'}\"")

    print("\n== Baixador e backup")
    baixados = baixador(linhas_baixador)
    print(" | ".join(f"{evento}: {qtd}" for evento, qtd in sorted(baixados.items())) or "nenhum evento")
    backup = backup_dados.ultimo_backup()
    print("Backup: nenhum" if backup is None else f"Backup: o último tem {backup[1]:.1f} h")

    pontos = sem_journal + pontos_de_atencao(erros, logs, filas, robo_sv, baixados, backup, agora, processos)
    print(f"\n== Pontos de atenção ({len(pontos)})")
    for ponto in pontos:
        print(f"⚠️ {ponto}")
    if not pontos:
        print("nenhum")


if __name__ == "__main__":
    main()
