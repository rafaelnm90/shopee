"""
Varre TODOS os grupos de fórum que cada sessão Telethon enxerga e lista os
tópicos de cada um. É o levantamento que decide qual sessão usar e mostra
quantos nomes o cache vai ganhar.

Uso:  ~/shopee/venv/bin/python3 checar_topicos.py

Não altera nada. Só conecta, pergunta e desconecta.
"""
import os
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.messages import GetForumTopicsRequest

load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

SESSOES = ["sessao_espiao", "sessao_divulgacao"]


async def testar(nome_sessao):
    print(f"\n{'=' * 62}")
    print(f"SESSÃO: {nome_sessao}")
    print("=" * 62)

    client = TelegramClient(nome_sessao, API_ID, API_HASH)
    try:
        await client.connect()

        if not await client.is_user_authorized():
            print("  ❌ Sessão não autorizada (arquivo ausente ou expirado).")
            return

        eu = await client.get_me()
        print(f"  👤 Conta: {eu.first_name} (@{eu.username or 'sem username'}) · id {eu.id}\n")

        foruns = []
        async for dialogo in client.iter_dialogs():
            entidade = dialogo.entity
            if getattr(entidade, "forum", False):
                foruns.append(entidade)

        if not foruns:
            print("  ⚠️ Esta conta não está em nenhum grupo com tópicos ativados.")
            return

        print(f"  🗂️ {len(foruns)} grupo(s) de fórum encontrados:\n")

        total_topicos = 0
        for entidade in foruns:
            chat_id = f"-100{entidade.id}"
            print(f"  ┌─ {entidade.title}")
            print(f"  │  {chat_id}")
            try:
                resposta = await client(GetForumTopicsRequest(
                    peer=entidade,
                    offset_date=0,
                    offset_id=0,
                    offset_topic=0,
                    limit=100,
                ))
                for t in resposta.topics:
                    titulo = getattr(t, "title", "(sem título)")
                    print(f"  │     {t.id:>6}  {titulo}")
                    total_topicos += 1
            except Exception as e:
                print(f"  │     ❌ {type(e).__name__}: {e}")
            print("  └─")

        print(f"\n  ✅ Total: {len(foruns)} grupo(s), {total_topicos} tópico(s).")
        print(f"     São {total_topicos} nomes que o cache passaria a ter.")

    except Exception as e:
        print(f"  ❌ Falha: {type(e).__name__}: {e}")
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def main():
    for s in SESSOES:
        await testar(s)
    print(f"\n{'=' * 62}")
    print("Me mande a saída acima.")
    print("=" * 62)


if __name__ == "__main__":
    asyncio.run(main())
