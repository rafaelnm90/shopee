"""
Descobre qual sessão Telethon consegue ler os tópicos do grupo.
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

GRUPO = -1004460669033
SESSOES = ["sessao_espiao", "sessao_divulgacao"]


async def testar(nome_sessao):
    print(f"\n{'='*58}")
    print(f"SESSÃO: {nome_sessao}")
    print("=" * 58)

    client = TelegramClient(nome_sessao, API_ID, API_HASH)
    try:
        await client.connect()

        if not await client.is_user_authorized():
            print("  ❌ Sessão não autorizada (arquivo ausente ou expirado).")
            return

        eu = await client.get_me()
        print(f"  👤 Conta: {eu.first_name} (@{eu.username or 'sem username'}) · id {eu.id}")

        try:
            entidade = await client.get_entity(GRUPO)
            print(f"  ✅ Enxerga o grupo: {entidade.title}")
        except Exception as e:
            print(f"  ❌ NÃO está no grupo: {type(e).__name__}: {e}")
            return

        resposta = await client(GetForumTopicsRequest(
            peer=entidade,
            offset_date=0,
            offset_id=0,
            offset_topic=0,
            limit=100,
        ))

        print(f"  🧵 {len(resposta.topics)} tópico(s) encontrados:\n")
        for t in resposta.topics:
            titulo = getattr(t, "title", "(sem título)")
            print(f"     {t.id:>6}  {titulo}")

        print(f"\n  ✅ ESTA SESSÃO SERVE.")

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
    print(f"\n{'='*58}")
    print("Me mande a saída acima.")
    print("=" * 58)


if __name__ == "__main__":
    asyncio.run(main())
