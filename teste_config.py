# -*- coding: utf-8 -*-
"""Testa o motor de filas com a config REAL do banco, sem escrever nada."""
import sqlite3, json, sys
from datetime import datetime, timedelta
from motor_filas import calcular_horarios_distribuicao

con = sqlite3.connect("banco_dados.db")
cur = con.cursor()
cur.execute("SELECT valor FROM configuracoes WHERE chave='autorais_config'")
config_atual = json.loads(cur.fetchone()[0])
con.close()

inicio_janela = int(config_atual.get("inicio", 10))
fim_janela = int(config_atual.get("fim", 20))
modo = config_atual.get("modo", "aleatorio")
dias_retorno_cfg = int(config_atual.get("dias_retorno", 15))
limite = int(config_atual.get("limite_videos", 5))

print(f"Config lida: janela {inicio_janela}h-{fim_janela}h | modo {modo} | D+{dias_retorno_cfg} | {limite} videos/dia")

config_fila = {
    "inicio": inicio_janela, "fim": fim_janela, "modo": modo, "intervalo_dias": 1,
    "espacamento_base_min": 15, "espacamento_variacao_min": 6,
    "limite_dias_descarte": dias_retorno_cfg + 5,
}

captura = (datetime.now() - timedelta(days=dias_retorno_cfg)).strftime("%Y-%m-%d %H:%M:%S")
itens = [{"id_unico": f"teste_{i}", "data_captura": captura} for i in range(limite)]

calcular_horarios_distribuicao(itens, config_fila, forcar=False)

vazios = [i for i in itens if not i.get("horario_disparo")]
print("\nHorarios sorteados:")
for i in itens:
    print("  ", i["id_unico"], "->", i.get("horario_disparo") or "(VAZIO - descartado)")

print()
if vazios:
    print(f"FALHOU: {len(vazios)} item(ns) sem horario. O descarte por idade ainda esta cortando.")
    sys.exit(1)
print("PASSOU: config sem NameError e nenhum item descartado por idade.")
