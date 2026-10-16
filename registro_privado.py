"""
Cópia privada do registro dos administradores no GitHub: o arquivo administradores.md
do repositório privado rafaelnm90/shopee-privado, que só o Rafael e o Claude abrem.
Pedido do Rafael: um registro só "para nós", que o Claude lê quando precisar. O
repositório dos robôs é público, então esses nomes nunca passam por ele nem pelo log
do Actions.

Roda no divulgacao_canal (loop_publicacao): a cada 10 min monta o arquivo a partir do
registro (registro_admins) e, se mudou, faz o commit e o push. Escreve com uma chave
SSH própria do servidor (~/.ssh/registro_privado), que o Rafael cadastra uma vez como
deploy key com escrita só nesse repositório; a chave privada nunca sai do servidor.
Enquanto o envio não funciona, o bot_mestre manda a parte pública ao Rafael
(painel_admins.avisar_registro_privado).
Decisão do Rafael: DECISOES.md, Monitor, deploy e servidor.
"""
import asyncio
import hashlib
import logging
import os
import subprocess
from datetime import datetime

import db
import links_grupos
import registro_admins

logger = logging.getLogger("Registro_Privado")

REPOSITORIO = "rafaelnm90/shopee-privado"
# Porta 443: passa mesmo onde a saída pela 22 é fechada.
URL_SSH = f"ssh://git@ssh.github.com:443/{REPOSITORIO}.git"
LINK_NOVO_REPOSITORIO = "https://github.com/new"
LINK_CADASTRAR_CHAVE = f"https://github.com/{REPOSITORIO}/settings/keys/new"
CHAVE = os.path.expanduser("~/.ssh/registro_privado")
CONHECIDOS = os.path.expanduser("~/.ssh/registro_privado_known_hosts")
PASTA = os.path.expanduser("~/registro_privado")
ARQUIVO = "administradores.md"
INTERVALO_S = 600
CHAVE_STATUS = "registro_privado"
LIMITE_HISTORICO = 200

# Respostas do git/ssh que querem dizer "o repositório não existe ou a chave não escreve nele".
SINAIS_SEM_ACESSO = ("permission denied", "repository not found", "could not read from remote repository",
                     "denied to deploy key", "read only", "access denied")


def preparar_chave():
    """Gera a chave do servidor na primeira vez. Devolve a parte pública, ou None se não deu."""
    try:
        if not os.path.exists(CHAVE):
            os.makedirs(os.path.dirname(CHAVE), mode=0o700, exist_ok=True)
            subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-C", "robo-shopee-registro",
                            "-f", CHAVE], check=True, capture_output=True, timeout=30)
        with open(CHAVE + ".pub", encoding="utf-8") as arquivo:
            return arquivo.read().strip()
    except Exception as e:
        logger.error(f"❌ [Registro Privado] Não consegui preparar a chave: {type(e).__name__}.")
        return None


def _git(*argumentos, pasta=None):
    ambiente = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_SSH_COMMAND=(
        f"ssh -i {CHAVE} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new "
        f"-o UserKnownHostsFile={CONHECIDOS}"))
    return subprocess.run(["git", *argumentos], cwd=pasta, env=ambiente, capture_output=True, text=True, timeout=120)


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
              "Arquivo mantido pelo servidor dos robôs (registro_privado.py); não editar à mão.", ""]
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


def _sem_acesso(resultado):
    return any(sinal in (resultado.stderr or "").lower() for sinal in SINAIS_SEM_ACESSO)


def publicar(texto):
    """Grava o arquivo no repositório privado: 'ok', 'sem_mudanca', 'sem_acesso' ou 'erro'."""
    if not os.path.isdir(os.path.join(PASTA, ".git")):
        resultado = _git("clone", URL_SSH, PASTA)
        if resultado.returncode != 0:
            return "sem_acesso" if _sem_acesso(resultado) else "erro"
    for passo in (("fetch", "origin"), ("reset", "--hard", "origin/HEAD")):
        resultado = _git(*passo, pasta=PASTA)
        if resultado.returncode != 0:
            return "sem_acesso" if _sem_acesso(resultado) else "erro"
    with open(os.path.join(PASTA, ARQUIVO), "w", encoding="utf-8") as arquivo:
        arquivo.write(texto)
    _git("add", ARQUIVO, pasta=PASTA)
    if _git("diff", "--cached", "--quiet", pasta=PASTA).returncode == 0:
        return "sem_mudanca"
    _git("-c", "user.name=Robô Shopee", "-c", "user.email=robo-shopee@localhost",
         "commit", "-m", "Administradores: registro atualizado", pasta=PASTA)
    resultado = _git("push", "origin", "HEAD", pasta=PASTA)
    if resultado.returncode != 0:
        return "sem_acesso" if _sem_acesso(resultado) else "erro"
    return "ok"


def _atualizar_status(**campos):
    db.atualizar_config(CHAVE_STATUS, lambda status: status.update(campos))


async def publicar_se_mudou(chave_publica=None):
    """Um passo do loop: publica se o arquivo mudou desde o último envio ou se o último falhou."""
    texto = montar_relatorio()
    if texto is None:
        return None
    marca = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    status = situacao()
    if status.get("situacao") == "ok" and status.get("marca") == marca:
        return "sem_mudanca"
    resultado = await asyncio.to_thread(publicar, texto)
    campos = {"situacao": "ok" if resultado in ("ok", "sem_mudanca") else resultado,
              "chave_publica": chave_publica or status.get("chave_publica"), "ultimo_resultado": resultado}
    if campos["situacao"] == "ok":
        campos.update(marca=marca, ultimo_envio=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if resultado != status.get("ultimo_resultado"):
        logger.info(f"📁 [Registro Privado] Envio ao repositório privado: {resultado}.")
    _atualizar_status(**campos)
    return resultado


async def loop_publicacao():
    """A cada INTERVALO_S, publica o registro se ele mudou."""
    await asyncio.sleep(150)  # depois da primeira conferência do registro ao subir
    chave_publica = await asyncio.to_thread(preparar_chave)
    while True:
        try:
            await publicar_se_mudou(chave_publica)
        except Exception as e:
            logger.error(f"❌ [Registro Privado] Falhou: {type(e).__name__}.")
        await asyncio.sleep(INTERVALO_S)


def situacao():
    """O estado do envio, para o painel e o aviso do bot_mestre."""
    return db.ler_config(CHAVE_STATUS, {}) or {}
