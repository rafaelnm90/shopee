"""
🔍 Testa um par App ID + Secret direto contra a API da Shopee.

Serve para diagnosticar credencial de parceiro sem passar pelo wizard do
Telegram. Mostra a resposta crua da Shopee e faz uma varredura de caracteres
invisíveis, que é a causa silenciosa mais comum de 'Invalid Signature':
o secret parece certo na tela, mas veio com um caractere que não é ASCII.

Uso:
    python3 testar_chaves.py <APP_ID> <APP_SECRET>
    python3 testar_chaves.py            # testa as chaves do .env
"""
import asyncio
import sys
import unicodedata

from api_shopee import converter_link_shopee, SHOPEE_APP_ID, SHOPEE_APP_SECRET

LINK_TESTE = "https://shopee.com.br/product/366207309/22648772967"


def auditar(rotulo, valor):
    """Procura o que o olho não vê: caractere fora do ASCII, espaço estranho."""
    print(f"\n--- {rotulo}")
    print(f"    tamanho ......... {len(valor)} caracteres")
    print(f"    só ASCII ........ {'sim' if valor.isascii() else '❌ NÃO'}")
    print(f"    só letra/dígito . {'sim' if valor.isalnum() else '❌ NÃO'}")

    suspeitos = [
        (i, c) for i, c in enumerate(valor)
        if not c.isascii() or not c.isalnum()
    ]
    if suspeitos:
        print("    ⚠️  caracteres problemáticos encontrados:")
        for i, c in suspeitos:
            nome = unicodedata.name(c, "SEM NOME")
            print(f"        posição {i}: U+{ord(c):04X} ({nome})")
    else:
        print("    ✅ nenhum caractere invisível ou estranho")

    # O par 0/O e 1/l/I é onde erro de transcrição costuma morar.
    ambiguos = {i: c for i, c in enumerate(valor) if c in "0O1lI"}
    if ambiguos:
        posicoes = ", ".join(f"{i}:{c}" for i, c in ambiguos.items())
        print(f"    ℹ️  caracteres ambíguos (confira contra o painel): {posicoes}")


async def main():
    if len(sys.argv) == 3:
        app_id, app_secret = sys.argv[1].strip(), sys.argv[2].strip()
        origem = "argumentos da linha de comando"
    else:
        app_id, app_secret = SHOPEE_APP_ID, SHOPEE_APP_SECRET
        origem = "arquivo .env"

    if not app_id or not app_secret:
        print("❌ Sem chaves para testar.")
        return

    print(f"🔑 Chaves lidas de: {origem}")
    auditar("APP ID", app_id)
    auditar("APP SECRET", app_secret)

    print("\n🌐 Chamando a API da Shopee...")
    resultado = await converter_link_shopee(
        LINK_TESTE, "diagnostico", True, app_id=app_id, app_secret=app_secret
    )

    print()
    if resultado and resultado != LINK_TESTE:
        print(f"✅ CREDENCIAIS VÁLIDAS. Link gerado: {resultado}")
    else:
        print("❌ CREDENCIAIS RECUSADAS. O motivo está na linha [API Shopee] acima.")


if __name__ == "__main__":
    asyncio.run(main())
