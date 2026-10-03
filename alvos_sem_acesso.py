"""
Alvos da divulgação a que a conta perdeu o acesso (foi removida, banida ou o
grupo ficou privado). Decisão do Rafael: DECISOES.md, Divulgação.

- O divulgacao_canal marca o alvo quando o Telegram responde que não há acesso.
  Daí em diante o alvo não recebe envios em nenhum escopo: a conta é a mesma.
- O bot_mestre avisa uma vez no privado, mostra o alvo como "sem acesso" nos
  painéis de SPAM e oferece o botão de reativar.
- Alvo excluído de todos os painéis sai daqui: se voltar, volta ativo.

Fica numa chave própria da tabela configuracoes, e não na config de cada
escopo, porque o painel regrava a config inteira do escopo ao editar e apagaria
a marca. Formato: {alvo: {"desde": "AAAA-MM-DD HH:MM:SS", "motivo": "...", "avisado": bool}}.
"""
import hashlib
from datetime import datetime

import db

CHAVE = "alvos_sem_acesso"


def ler():
    return db.ler_config(CHAVE, {}) or {}


def marcar(alvo, motivo):
    """Pausa o alvo. True se acabou de ser marcado (não estava antes)."""
    alvo = str(alvo)

    def alterar(dados):
        if alvo in dados:
            return False
        dados[alvo] = {"desde": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                       "motivo": motivo, "avisado": False}
        return True
    return bool(db.atualizar_config(CHAVE, alterar))


def reativar(alvo):
    """Tira a marca. True se o alvo estava pausado."""
    return bool(db.atualizar_config(CHAVE, lambda dados: dados.pop(str(alvo), None) is not None))


def pendentes_de_aviso():
    """{alvo: info} dos alvos marcados que o Rafael ainda não recebeu no privado."""
    return {alvo: info for alvo, info in ler().items() if not info.get("avisado")}


def marcar_avisados(alvos):
    def alterar(dados):
        for alvo in alvos:
            if alvo in dados:
                dados[alvo]["avisado"] = True
    db.atualizar_config(CHAVE, alterar)


def esquecer_fora_da_lista(alvos_cadastrados):
    """Tira os alvos que não estão mais em nenhum painel. Devolve quantos saíram."""
    cadastrados = {str(a) for a in alvos_cadastrados}
    if all(alvo in cadastrados for alvo in ler()):
        return 0   # o caso de sempre: nada a gravar

    def alterar(dados):
        sobra = [alvo for alvo in dados if alvo not in cadastrados]
        for alvo in sobra:
            del dados[alvo]
        return len(sobra)
    return db.atualizar_config(CHAVE, alterar) or 0


def codigo(alvo):
    """Código curto do alvo para o botão (o callback do Telegram aceita até 64 bytes)."""
    return hashlib.sha1(str(alvo).encode("utf-8")).hexdigest()[:12]


def alvo_do_codigo(cod):
    return next((alvo for alvo in ler() if codigo(alvo) == cod), None)
