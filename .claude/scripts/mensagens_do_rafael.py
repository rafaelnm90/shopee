"""
As mensagens do Rafael nesta conversa desde um momento, para a conferência de cada retomada (pedido
dele em 21/11: nada do que ele manda, também com o crédito do Claude acabado, pode passar despercebido;
DECISOES.md, Trabalho com o Claude).

Lê o histórico da sessão (o .jsonl mais novo de ~/.claude/projects/-home-user-shopee, ou o --historico)
e mostra, na hora de Brasília:
- cada mensagem dele, com o caminho por onde chegou: "direto" (o Claude estava livre), "no meio do
  turno" (chegou enquanto o Claude trabalhava) ou "fila" (esperou o Claude terminar ou o crédito voltar);
- a mensagem da fila que não chegou ao Claude (a lista tem de ficar vazia);
- quando o crédito do Claude acabou no período.

Só mostra no terminal da sessão: o texto dele nunca vai para commit, PR, comentário ou log.

Uso: python3 .claude/scripts/mensagens_do_rafael.py [--desde "AAAA-MM-DD HH:MM"] [--historico ARQUIVO]
(sem o --desde, as últimas 24 h).
"""
import argparse
import glob
import json
import os
import re
import signal
from datetime import datetime, timedelta, timezone

BRASILIA = timezone(timedelta(hours=-3))
PASTA_DO_HISTORICO = os.path.expanduser("~/.claude/projects/-home-user-shopee")
# O que entra na conversa sem ser do Rafael: avisos do sistema, tarefas, subagentes e o resumo.
NAO_SAO_DELE = ("<task-notification>", "<system-reminder>", "<agent-message", "[SYSTEM NOTIFICATION",
                "This session is being continued", "<local-command", "<command-name>", "Caveat:", "<wake",
                "[Request interrupted")
# A mensagem da fila chega ao histórico alguns milissegundos antes ou depois do registro dela.
FOLGA_DA_ENTREGA = timedelta(seconds=5)
LETRAS_POR_MENSAGEM = 600
# O aviso do limite diz quando o crédito volta, na hora UTC: "resets 3:50pm (UTC)".
VOLTA_DO_CREDITO = re.compile(r"resets (\d{1,2})(?::(\d{2}))?\s*(am|pm) \(UTC\)", re.I)


def historico_mais_novo():
    arquivos = glob.glob(os.path.join(PASTA_DO_HISTORICO, "*.jsonl"))
    return max(arquivos, key=os.path.getmtime) if arquivos else None


def quando(texto):
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def hora(momento):
    return momento.astimezone(BRASILIA).strftime("%d/%m %H:%M")


def texto_de(conteudo):
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        return " ".join(b.get("text") or "" for b in conteudo if isinstance(b, dict) and b.get("type") == "text")
    return ""


def dele(texto):
    texto = (texto or "").strip()
    return bool(texto) and not texto.startswith(NAO_SAO_DELE) and "Stop hook feedback" not in texto[:60]


def normal(texto):
    return " ".join((texto or "").split())


def chave(texto):
    """O começo da mensagem: as que esperam juntas na fila chegam numa mensagem só, uma depois da outra."""
    return normal(texto)[:80]


def ler(caminho, desde):
    """As mensagens dele (momento, caminho, texto), as da fila (momento, texto) e as faltas de crédito."""
    mensagens, fila, sem_credito = [], [], []
    with open(caminho, encoding="utf-8") as arquivo:
        for linha in arquivo:
            try:
                item = json.loads(linha)
            except ValueError:
                continue
            if not item.get("timestamp"):
                continue
            momento = quando(item["timestamp"])
            if momento < desde - FOLGA_DA_ENTREGA:
                continue
            tipo = item.get("type")
            if tipo == "assistant":
                if item.get("isApiErrorMessage") or item.get("error"):
                    sem_credito.append((momento, volta_do_credito(momento, item)))
            elif tipo == "user" and not item.get("isMeta") and not item.get("isCompactSummary"):
                texto = texto_de((item.get("message") or {}).get("content"))
                if dele(texto):
                    mensagens.append((momento, "direto", texto))
            elif tipo == "attachment" and (item.get("attachment") or {}).get("type") == "queued_command":
                texto = texto_de(item["attachment"].get("prompt"))
                if dele(texto):
                    mensagens.append((momento, "no meio do turno", texto))
            elif tipo == "queue-operation" and item.get("operation") == "enqueue":
                texto = texto_de(item.get("content"))
                if dele(texto):
                    fila.append((momento, texto))
    return mensagens, fila, sem_credito


def juntar(mensagens, fila, desde):
    """
    Uma linha por mensagem dele desde o momento, na hora em que ele mandou, e as da fila que não
    chegaram. A da fila chega sozinha ou junto de outras (o texto delas, uma depois da outra).
    """
    chegadas = sorted(mensagens)
    vistas, nao_chegaram, da_fila = [], [], set()
    for momento, texto in sorted(fila):
        entregue = next((c for c in chegadas
                         if c[0] >= momento - FOLGA_DA_ENTREGA and chave(texto) in normal(c[2])), None)
        if entregue is None:
            nao_chegaram.append((momento, texto))
            continue
        da_fila.add(entregue)
        if entregue[1] == "no meio do turno":
            caminho = "no meio do turno"
        elif entregue[0] - momento > FOLGA_DA_ENTREGA:
            caminho = f"fila, chegou às {hora(entregue[0])}"
        else:
            caminho = "direto"
        vistas.append((momento, caminho, texto))
    vistas += [c for c in chegadas if c not in da_fila]
    vistas = [v for v in sorted(vistas, key=lambda v: v[0]) if v[0] >= desde]
    return vistas, [n for n in nao_chegaram if n[0] >= desde]


def volta_do_credito(momento, item):
    """Quando o crédito volta, pelo aviso do limite (a próxima hora dita depois do aviso), ou None."""
    texto = texto_de((item.get("message") or {}).get("content"))
    achado = VOLTA_DO_CREDITO.search(texto)
    if not achado:
        return None
    horas = int(achado.group(1)) % 12 + (12 if achado.group(3).lower() == "pm" else 0)
    volta = momento.astimezone(timezone.utc).replace(hour=horas, minute=int(achado.group(2) or 0),
                                                     second=0, microsecond=0)
    return volta if volta > momento else volta + timedelta(days=1)


def faltas(sem_credito):
    """
    As faltas de crédito juntas: o 1º aviso de cada trecho e a volta do crédito (a dita no último
    aviso do trecho; sem ela, o último aviso). Avisos até a volta do anterior são do mesmo trecho.
    """
    trechos = []
    for momento, volta in sorted(sem_credito, key=lambda f: f[0]):
        fim = volta or momento
        if trechos and momento <= trechos[-1][1] + timedelta(minutes=1):
            trechos[-1][1] = max(trechos[-1][1], fim)
        else:
            trechos.append([momento, fim])
    return trechos


def main():
    # Lido pela metade (ex.: com o head), sai calado.
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    partes = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    partes.add_argument("--desde", help='AAAA-MM-DD HH:MM, na hora de Brasília (padrão: 24 h atrás)')
    partes.add_argument("--historico", help="o .jsonl da sessão (padrão: o mais novo da pasta)")
    args = partes.parse_args()
    caminho = args.historico or historico_mais_novo()
    if not caminho or not os.path.exists(caminho):
        raise SystemExit("Histórico da sessão não encontrado.")
    if args.desde:
        desde = datetime.strptime(args.desde, "%Y-%m-%d %H:%M").replace(tzinfo=BRASILIA)
    else:
        desde = datetime.now(BRASILIA) - timedelta(hours=24)
    mensagens, fila, sem_credito = ler(caminho, desde)
    vistas, nao_chegaram = juntar(mensagens, fila, desde)
    print(f"Mensagens do Rafael desde {hora(desde)}: {len(vistas)}")
    for momento, caminho_dela, texto in vistas:
        print(f"[{hora(momento)}] ({caminho_dela}) {' '.join(texto.split())[:LETRAS_POR_MENSAGEM]}")
    print(f"\nDa fila sem chegar ao Claude: {len(nao_chegaram)}")
    for momento, texto in nao_chegaram:
        print(f"[{hora(momento)}] {' '.join(texto.split())[:LETRAS_POR_MENSAGEM]}")
    trechos = faltas([f for f in sem_credito if f[0] >= desde])
    print(f"\nCrédito do Claude acabado no período: {len(trechos)} vez(es)")
    for inicio, fim in trechos:
        print(f"de {hora(inicio)} até a volta, às {hora(fim)}" if fim > inicio else f"às {hora(inicio)}")


if __name__ == "__main__":
    main()
