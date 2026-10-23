"""
Em que canal sai cada rotina de texto (mensagens geradas pela IA: bom dia,
convites, divulgação dos outros canais). Usado pelo bot_mestre, que dispara as
rotinas, e pelo checkup do dia, que confere o espaçamento e a ordem dos assuntos
em cada canal.
"""
ROTINAS_VIRAIS = ("promo_principal", "link_grupo_viral", "divulgar_gem_viral", "promo_publico_viral",
                  "promo_achadinhos_viral")
ROTINAS_PUBLICO = ("link_grupo_publico", "promo_principal_publico", "promo_viral_publico",
                   "promo_achadinhos_publico")
CANAIS = ("canal principal", "Viral", "Grupo Público")


def canal_da_rotina(tipo):
    """"Viral", "Grupo Público" ou "canal principal". As campanhas do Público começam por campanha_pub_."""
    if tipo in ROTINAS_VIRAIS:
        return "Viral"
    if tipo in ROTINAS_PUBLICO or str(tipo).startswith("campanha_pub_"):
        return "Grupo Público"
    return "canal principal"
