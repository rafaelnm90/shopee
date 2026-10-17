"""
Cópia cifrada do registro dos administradores no próprio repositório dos robôs:
o arquivo administradores.md.cifrado do ramo registro-admins. O repositório é
público, então o arquivo vai embaralhado: só abre com a chave do servidor, que o
Rafael guarda nas configurações do ambiente do Claude (REGISTRO_ADMINS_CHAVE).
Pedido do Rafael: um registro só "para nós", no mesmo repositório, que o Claude lê
quando precisar.

Quem usa:
- workflow registro_admins.yml: roda "registro_privado.py cifrado" no servidor e
  grava a saída no ramo (só quando mudou);
- bot_mestre (painel_admins): manda a chave ao Rafael no privado, uma vez por chave;
- Claude: "registro_privado.py ler ARQUIVO" abre o arquivo do ramo com a chave do ambiente.
A chave fica num arquivo do servidor (CHAVE_ARQUIVO): nunca no banco, no log ou no git.
Decisão do Rafael: DECISOES.md, Monitor, deploy e servidor.
"""
import hashlib
import os
import sys
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken

import db
import links_grupos
import registro_admins
from fuso import fuso_horario

RAMO = "registro-admins"
ARQUIVO = "administradores.md.cifrado"
CHAVE_ARQUIVO = os.path.expanduser("~/.config/registro_admins.chave")
VARIAVEL_CHAVE = "REGISTRO_ADMINS_CHAVE"
CHAVE_STATUS = "registro_privado"
HORARIO_COPIA = "05:47"  # o cron do registro_admins.yml, depois da conferência das 04:20
LIMITE_HISTORICO = 200
SEM_CONFERENCIA = "# Administradores dos grupos e canais do Rafael\n\nAinda sem conferência.\n"


def chave():
    """A chave do servidor, criada na primeira vez por quem chegar antes (bot ou workflow)."""
    try:
        with open(CHAVE_ARQUIVO, "rb") as arquivo:
            return arquivo.read().strip()
    except FileNotFoundError:
        pass
    os.makedirs(os.path.dirname(CHAVE_ARQUIVO), mode=0o700, exist_ok=True)
    provisoria = f"{CHAVE_ARQUIVO}.{os.getpid()}"
    descritor = os.open(provisoria, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descritor, "wb") as arquivo:
        arquivo.write(Fernet.generate_key())
    try:
        # O link só cria se ainda não existe: os dois robôs nunca ficam com chaves diferentes.
        os.link(provisoria, CHAVE_ARQUIVO)
    except FileExistsError:
        pass
    finally:
        os.unlink(provisoria)
    with open(CHAVE_ARQUIVO, "rb") as arquivo:
        return arquivo.read().strip()


def id_da_chave(valor):
    """Marca curta da chave, para saber se ela mudou sem guardar a chave no banco."""
    return hashlib.sha256(valor).hexdigest()[:12]


def _celula(texto):
    return str(texto or "").replace("|", "\\|").replace("\n", " ")


def montar_relatorio():
    """O administradores.md. Sem a hora de agora: o arquivo só muda quando o registro muda."""
    registro_admins.inicializar_tabelas()
    resumo = db.ler_config(registro_admins.CHAVE_RESUMO, {}) or {}
    if not resumo.get("ultima"):
        return None
    quando = datetime.strptime(resumo["ultima"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y às %H:%M")
    linhas = ["# Administradores dos grupos e canais do Rafael", "",
              f"Conferência de {quando}: {resumo.get('grupos', 0)} grupo(s) e canal(is) em que a conta principal "
              f"é dona ou admin, {resumo.get('admins', 0)} administradores no total.",
              "Arquivo montado pelo servidor dos robôs (registro_privado.py); não editar à mão.", ""]
    for grupo in sorted(registro_admins._foto_atual().values(), key=lambda g: (g["tipo"], g["nome"].lower())):
        nomes = {a["user_id"]: a["nome"] for a in grupo["admins"]}
        link = links_grupos.link(grupo["chat_id"])
        linhas += [f"## {'📢' if grupo['tipo'] == 'canal' else '👥'} {grupo['nome']} ({grupo['tipo']})", "",
                   f"ID `{grupo['chat_id']}`" + (f" · {link}" if link else ""), "",
                   "| Quem | @ | Papel | Pode | Promovido por | Título |", "|---|---|---|---|---|---|"]
        for a in sorted(grupo["admins"], key=lambda a: (a["papel"] != "dono", a["bot"], a["nome"].lower())):
            pode = "tudo" if a["papel"] == "dono" else (registro_admins._lista(a["permissoes"]) or "nada")
            linhas.append("| " + " | ".join(_celula(c) for c in (
                a["nome"] + (" (bot)" if a["bot"] else ""), f"@{a['usuario']}" if a["usuario"] else "",
                a["papel"], pode, nomes.get(a["promovido_por"], ""), a["titulo"])) + " |")
        linhas.append("")
    linhas += [f"## Histórico de mudanças (as {LIMITE_HISTORICO} mais recentes)", ""]
    mudancas = registro_admins.ultimas_mudancas(LIMITE_HISTORICO)
    for m in mudancas:
        data = datetime.strptime(m["quando"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
        quem = f"{m['nome']} " if m.get("nome") else ""
        linhas.append(f"- {data} · {m['chat_nome']}: {quem}{m['mudanca']}")
    if not mudancas:
        linhas.append("Nenhuma mudança desde que o registro começou.")
    return "\n".join(linhas) + "\n"


def cifrado():
    """O registro cifrado. Enquanto o registro e a chave não mudam, devolve o mesmo texto
    cifrado de antes (cifrar de novo daria outro texto e um commit à toa no ramo)."""
    texto = montar_relatorio() or SEM_CONFERENCIA
    valor = chave()
    marca = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    status = situacao()
    if status.get("marca") == marca and status.get("chave_id") == id_da_chave(valor) and status.get("cifrado"):
        saida = status["cifrado"]
    else:
        saida = Fernet(valor).encrypt(texto.encode("utf-8")).decode("ascii")
    campos = {"marca": marca, "chave_id": id_da_chave(valor), "cifrado": saida,
              "ultima_copia": datetime.now(fuso_horario).strftime("%Y-%m-%d %H:%M:%S")}
    db.atualizar_config(CHAVE_STATUS, lambda s: s.update(campos))
    return saida


def abrir(texto_cifrado, valor_chave):
    """O registro em texto, a partir do arquivo do ramo e da chave."""
    return Fernet(valor_chave.strip().encode("ascii")).decrypt(texto_cifrado.strip().encode("ascii")).decode("utf-8")


def situacao():
    """O estado da cópia, para o painel e o aviso do bot_mestre."""
    return db.ler_config(CHAVE_STATUS, {}) or {}


def _ler(caminho):
    valor = os.environ.get(VARIAVEL_CHAVE, "")
    if not valor:
        print(f"Falta a variável {VARIAVEL_CHAVE} no ambiente do Claude (a chave que o bot mandou ao Rafael).")
        return 1
    with open(caminho, encoding="ascii") as arquivo:
        texto_cifrado = arquivo.read()
    try:
        print(abrir(texto_cifrado, valor), end="")
    except (InvalidToken, ValueError):
        print("A chave do ambiente não abre este arquivo: o servidor pode ter gerado outra (o bot manda a nova).")
        return 1
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["cifrado"]:
        print(cifrado())
    elif sys.argv[1:2] == ["ler"]:
        sys.exit(_ler(sys.argv[2] if len(sys.argv) > 2 else ARQUIVO))
    else:
        print("Uso: registro_privado.py cifrado | ler [ARQUIVO]")
        sys.exit(2)
