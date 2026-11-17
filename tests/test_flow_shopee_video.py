"""flow_shopee_video: o teste da P229 1 monta o pedido no Flow como mapeado, só gera com tudo conferido e o log público não tem o produto."""
import contextlib
import io
import json
from xml.sax.saxutils import quoteattr

import pytest
from PIL import Image

import db
import flow_shopee_video as flow

CUSTOS = {"Omni 1.2 Flash": 24, "Omni 1.1 Flash": 12, "Veo 3.1 - Lite": 10}
SELETOR = flow.PACOTE_DO_SELETOR
# O arquivo que o Baixar do Flow deixa no celular (o nome é o título que o Flow dá ao vídeo).
BAIXADO = "/sdcard/Download/Mulher usando o copo.mp4"
MENU_DO_VIDEO = (("Gostei", 278, ""), ("Renomear", 425, ""), ("Reutilizar comando", 530, ""), ("Favorito", 635, ""),
                 ("Baixar", 740, "baixar"), ("Enviar", 845, ""), ("Compartilhar", 950, ""),
                 ("Compartilhar no YouTube", 1055, ""), ("Enviar feedback", 1202, ""))


def _no(caixa, classe="android.view.View", desc="", texto="", pacote=flow.PACOTE, clicavel=True, rid="", marcado=False,
        foco=False, ligado=True):
    x1, y1, x2, y2 = caixa
    return (f'<node index="0" text={quoteattr(texto)} resource-id={quoteattr(rid)} class="{classe}" '
            f'package="{pacote}" content-desc={quoteattr(desc)} clickable="{str(clicavel).lower()}" '
            f'checked="{str(marcado).lower()}" focused="{str(foco).lower()}" enabled="{str(ligado).lower()}" '
            f'visible-to-user="true" bounds="[{x1},{y1}][{x2},{y2}]" />')


class Campo:
    def __init__(self, celular):
        self.celular, self.exists = celular, True

    def set_text(self, texto):
        # O campo em foco: o nome do projeto no Renomear, ou o texto do pedido.
        if self.celular.tela == "renomear":
            if not self.celular.nome_nao_entra:
                self.celular.nome_no_campo = texto
        elif self.celular.tela == "estender":
            self.celular.texto_do_estender = texto
        else:
            self.celular.texto = texto


class Resposta:
    def __init__(self, output=""):
        self.output = output


class Flow:
    """O celular de mentira com o Flow: as telas mapeadas em 15/11/2026 e o que cada toque faz."""

    def __init__(self, custos=CUSTOS, termos=False):
        self.custos, self.termos = custos, termos
        self.tela, self.texto, self.modelo, self.foto = "fora", "", "Omni 1.2 Flash", False
        self.folha = self.lista = self.marcada = self.gerado = False
        self.na_galeria, self.comandos, self.toques = "", [], []
        # Depois do Gerar: quantas leituras o quadrado mostra "Gerando…", de que modelo é o vídeo pronto
        # e o que o Baixar faz.
        self.gerando_leituras, self.modelo_do_video, self.filtro = 0, "", False
        # Quantas leituras o "Gerando…" dura e em qual delas ele some da tela (como no vídeo 3, 15/11).
        self.leituras_ao_gerar, self.piscar_na_leitura = 2, None
        # Um vídeo gerado antes no projeto (o modelo dele), mais abaixo na grade, e se o robô o abriu.
        self.video_de_antes, self.abriu_o_de_antes = "", False
        self.falha_ao_gerar = self.baixado = False
        # A janela "Baixar vídeo" (15/11): o 720p "Tamanho original" vem marcado e o 1080p fica livre
        # (sem custo na tela); o 4K pede outro plano. Os toques no plano ficam em toques_proibidos.
        self.original_marcado, self.maior_marcado, self.toques_proibidos = True, False, []
        self.sem_1080p = self.custo_no_1080p = self.aviso_de_credito = self.maior_nao_marca = False
        self.geracoes, self.puxados = 0, []
        # A lista do início, de cima para baixo (o projeto novo entra no alto), quantos projetos cabem na
        # tela e quanto ela rolou; o projeto aberto, o nome no campo do Renomear e os toques fora do
        # projeto do robô (o Novo e outro projeto). O do robô o Rafael renomeou em 15/11.
        self.projetos, self.cabem, self.rolagem = ["nov. 15, 12:09\u202fPM", "Shopee Video"], 4, 0
        self.aberto, self.nome_no_campo, self.nome_nao_entra = "", "", False
        self.fora_do_projeto = []
        # As versões do vídeo aberto (o modelo de cada uma) e a que aparece; vazio = só a do vídeo gerado.
        self.versoes, self.versao = [], 0
        # Como no app (15/11): a coluna das versões só aparece algumas leituras depois do player.
        self.atraso_das_versoes, self.leituras_do_video = 2, 0
        # Quantas vezes o vídeo aberto mostra "Falha ao carregar o vídeo" no player (visto em 16/11) e se
        # a abertura de agora é uma delas.
        self.falhas_ao_carregar, self.falha_no_player = 0, False
        # O Estender (P246 1, mapeado em 16/11): o texto na caixa do painel, o rótulo da duração, quantas vezes o
        # Gerar do painel foi tocado (com o texto que levou), quantas leituras do projeto a versão estendida leva
        # para ficar pronta e as versões que cada Baixar baixou.
        self.texto_do_estender, self.rotulo_da_duracao, self.extensoes, self.texto_estendido = "", "Estender 8s", 0, ""
        self.leituras_ao_estender, self.estendendo_leituras, self.baixadas = 2, 0, []
        # Depois do Gerar do Estender, quantas leituras do vídeo aberto o Flow leva para mostrar a continuação sendo
        # gerada ("2 de 2", "Gerando…"); fechado à força antes disso, ele a perde, e o vídeo fica com uma versão só
        # (visto no 1º vídeo de IA de 16 s da produção, 17/11).
        self.atraso_da_continuacao, self.continuacao_pendente, self.continuacao_perdida = 0, 0, False

    def continuacao_registrada(self):
        return self.extensoes > 0 and not self.continuacao_perdida and self.continuacao_pendente <= 0

    def estendendo(self):
        return self.continuacao_registrada() and self.estendendo_leituras > 0

    def extensao_pronta(self):
        return self.continuacao_registrada() and self.estendendo_leituras <= 0

    def versoes_do_gerado(self):
        return self.versoes or ([self.modelo_do_video, ""] if self.extensao_pronta() else [self.modelo_do_video])

    # --- o que o uiautomator2 faz
    def app_start(self, pacote, stop=False, wait=False):
        if stop and self.continuacao_pendente > 0:
            self.continuacao_pendente, self.continuacao_perdida = 0, True
        self.tela, self.rolagem = "inicio", 0

    def screen_on(self):
        pass

    def window_size(self):
        return 1080, 2400

    def swipe(self, x1, y1, x2, y2, duracao=0):
        # O dedo de baixo para cima desce a lista do início, 3 projetos por vez, até o fim dela.
        if self.tela == "inicio" and y2 < y1:
            self.rolagem = min(self.rolagem + 3, max(0, len(self.projetos) - self.cabem))

    def __call__(self, **seletor):
        return Campo(self)

    def push(self, origem, destino):
        self.na_galeria = destino.rsplit("/", 1)[-1]

    def shell(self, partes):
        self.comandos.append(partes)
        if partes and partes[0] == "find":
            return Resposta(f"1763216000 2345678 {BAIXADO}\n" if self.baixado else "")
        return Resposta(self.na_galeria if "content" in partes else "")

    def pull(self, origem, destino):
        self.puxados.append(origem)
        # Cada Baixar traz o arquivo da versão que estava à vista.
        with open(destino, "wb") as arquivo:
            arquivo.write(b"\0" * 2048 + str(self.baixadas[-1] if self.baixadas else 0).encode())

    def nos(self):
        """(caixa, xml do nó, o que o toque faz) da tela de agora."""
        nos = []
        if self.tela == "inicio":
            nos.append(((775, 908, 1038, 1034), _no((775, 908, 1038, 1034), "android.widget.Button", "Novo"), "novo"))
            for i, nome in enumerate(self.projetos[self.rolagem:self.rolagem + self.cabem]):
                # Como no Flow (15/11): a descrição diz o título e, com algo dentro, quantos vídeos e
                # imagens o projeto tem; cada linha tem o seu Mais opções à direita.
                y = 1076 + 273 * i
                desc = f"O título do projeto é {nome}" + (", 1 vídeo, 4 imagens" if nome == "Shopee Video" else "")
                nos += [((42, y, 891, y + 252), _no((42, y, 891, y + 252), desc=desc, clicavel=False), f"abrir:{nome}"),
                        ((912, y + 63, 1038, y + 189), _no((912, y + 63, 1038, y + 189), "android.widget.Button",
                                                           "Mais opções"), "proibido")]
            if self.termos:
                nos.append(((0, 2300, 1080, 2400), _no((0, 2300, 1080, 2400), texto="Aceitar os Termos de Serviço"), ""))
        elif self.tela == "menu_projeto":
            # O menu do Mais opções do alto do projeto (15/11): o robô só pode tocar no Renomear.
            nos.append(((0, 0, 1080, 2520), _no((0, 0, 1080, 2520), desc="Dispensar menu"), "projeto"))
            nos += [((565, y1, 975, y2), _no((565, y1, 975, y2), "android.widget.Button", nome), acao)
                    for nome, y1, y2, acao in (("Renomear", 278, 383, "renomear"), ("Grade: Grande", 383, 488, ""),
                                                ("Ver lixeira", 530, 635, "proibido"),
                                                ("Excluir projeto", 677, 782, "proibido"))]
        elif self.tela == "renomear":
            # O Renomear (15/11): o nome num campo no alto, em foco, com o ✓ e o ✕ sem descrição ao lado.
            nos += [((0, 152, 1080, 278), _no((0, 152, 1080, 278), "android.widget.EditText", texto=self.nome_no_campo,
                                               foco=True), ""),
                    ((765, 152, 891, 278), _no((765, 152, 891, 278), "android.widget.Button"), "ok_nome"),
                    ((912, 152, 1038, 278), _no((912, 152, 1038, 278), "android.widget.Button"), "cancelar_nome")]
        elif self.tela == "projeto":
            nos += [((0, 152, 1080, 278), _no((0, 152, 1080, 278), desc=self.aberto, clicavel=False), ""),
                    ((42, 152, 168, 278), _no((42, 152, 168, 278), "android.widget.Button", "Voltar"), "inicio"),
                    ((912, 152, 1038, 278), _no((912, 152, 1038, 278), "android.widget.Button", "Mais opções"),
                     "menu_projeto"),
                    ((42, 330, 191, 425), _no((42, 330, 191, 425), "android.widget.Button", "Tudo", clicavel=False), ""),
                    ((500, 330, 737, 425), _no((500, 330, 737, 425), "android.widget.Button", "Vídeos", clicavel=False),
                     "filtro"),
                    ((403, 2171, 677, 2339), _no((403, 2171, 677, 2339), "android.widget.Button", "Criar"), "pedido")]
            if self.gerado and self.gerando_leituras > 0:
                if self.gerando_leituras != self.piscar_na_leitura:
                    nos.append(((0, 466, 537, 1422), _no((0, 466, 537, 1422), desc="1%\nGerando…"), ""))
            elif self.gerado:
                if self.estendendo():
                    nos.append(((0, 466, 537, 1422), _no((0, 466, 537, 1422), desc="1%\nGerando…", clicavel=False), ""))
                quantas = len(self.versoes_do_gerado())
                itens = f"{quantas} itens" if quantas > 1 else "1 item"
                quadro = _no((0, 466, 537, 1422), desc=f"Mulher usando o copo, {itens}")
                nos.append(((0, 466, 537, 1422), quadro, "video"))
            if self.video_de_antes:
                nos.append(((0, 1427, 537, 1964), _no((0, 1427, 537, 1964), desc="Copo de antes, 1 item"), "antes"))
            if not self.filtro:
                nos.append(((543, 466, 1080, 1004), _no((543, 466, 1080, 1004), desc="Copo na mesa, 1 item"), "foto"))
        elif self.tela == "video":
            versoes = [self.video_de_antes] if self.abriu_o_de_antes else self.versoes_do_gerado()
            # A versão estendida (a 2ª em diante) tem só o nome no título, sem o modelo.
            titulo = f"Mulher usando o copo\n{versoes[self.versao]}\n720p" if self.versao == 0 else "Mulher usando o copo"
            nos += [((0, 131, 1080, 299), _no((0, 131, 1080, 299), desc=titulo, clicavel=False), ""),
                    ((42, 152, 168, 278), _no((42, 152, 168, 278), "android.widget.Button", "Fechar"), "projeto"),
                    ((891, 152, 1017, 278), _no((891, 152, 1017, 278), "android.widget.Button", "Mais opções"), "menu_video"),
                    ((0, 309, 1080, 2184), _no((0, 309, 1080, 2184), desc=(
                        # Como no app (17/11): a continuação sendo gerada no lugar do player, logo depois do Gerar.
                        "2 de 2\n2%\nGerando…" if self.estendendo() and not self.abriu_o_de_antes
                        else f"{self.versao + 1} de {len(versoes)}\nFalha ao carregar o vídeo" if self.falha_no_player
                        else f"Vídeo tocando, {self.versao + 1} de {len(versoes)}\n0:08")), ""),
                    ((42, 2216, 530, 2363), _no((42, 2216, 530, 2363), "android.widget.Button", "Editar"), ""),
                    ((551, 2216, 1038, 2363), _no((551, 2216, 1038, 2363), "android.widget.Button", "Estender"),
                     "estender")]
            if len(versoes) > 1 and self.leituras_do_video >= self.atraso_das_versoes:
                nos += [((962, y, 1025, y + 63), _no((962, y, 1025, y + 63), "android.widget.ImageView"), f"versao:{i}")
                        for i, y in enumerate(range(1178, 1178 + 74 * len(versoes), 74))]
        elif self.tela == "estender":
            # O painel do Estender como no Motorola (16/11): o Gerar fica desligado com a caixa vazia.
            nos += [((42, 152, 168, 278), _no((42, 152, 168, 278), "android.widget.Button", "Voltar"), "video"),
                    ((0, 152, 1080, 1096), _no((0, 152, 1080, 1096), desc=f"1 de {len(self.versoes_do_gerado())}"), ""),
                    ((45, 1319, 1035, 1445), _no((45, 1319, 1035, 1445), "android.widget.EditText",
                                                 texto=self.texto_do_estender, foco=True), ""),
                    ((45, 1445, 171, 1571), _no((45, 1445, 171, 1571), "android.widget.Button", "Adicionar mídia"), ""),
                    ((620, 1445, 867, 1571), _no((620, 1445, 867, 1571), "android.widget.Button",
                                                 self.rotulo_da_duracao), "proibido"),
                    ((888, 1445, 1014, 1571), _no((888, 1445, 1014, 1571)), "gerar_estender"),
                    ((888, 1445, 1014, 1571), _no((888, 1445, 1014, 1571), "android.widget.Button", "Gerar",
                                                  clicavel=False, ligado=bool(self.texto_do_estender)),
                     "gerar_estender")]
        elif self.tela == "menu_video":
            nos.append(((0, 0, 1080, 2520), _no((0, 0, 1080, 2520), desc="Dispensar menu"), "video"))
            nos += [((341, y, 954, y + 105), _no((341, y, 954, y + 105), "android.widget.Button", nome), acao)
                    for nome, y, acao in MENU_DO_VIDEO]
        elif self.tela == "tamanho":
            nos += [((0, 0, 1080, 2520), _no((0, 0, 1080, 2520), desc="Dispensar"), "video"),
                    ((168, 874, 912, 947), _no((168, 874, 912, 947), desc="Baixar vídeo", clicavel=False), ""),
                    ((168, 989, 912, 1451), _no((168, 989, 912, 1451), "android.widget.RadioGroup", clicavel=False,
                                                desc="Escolha uma resolução para fazer o download.\n4K"), ""),
                    ((168, 1136, 912, 1241), _no((168, 1136, 912, 1241), desc="720p\nTamanho original"), "original"),
                    ((168, 1165, 215, 1212), _no((168, 1165, 215, 1212), "android.widget.RadioButton",
                                                 marcado=self.original_marcado), "original")]
            if self.aviso_de_credito:
                nos.append(((168, 947, 912, 989), _no((168, 947, 912, 989), clicavel=False,
                                                      desc="Aumentar a resolução usa 10 créditos de IA"), ""))
            if not self.sem_1080p:
                maior = "1080p\nAumentar a resolução" + ("\n10 créditos" if self.custo_no_1080p else "")
                nos += [((168, 1241, 912, 1346), _no((168, 1241, 912, 1346), desc=maior), "maior"),
                        ((168, 1270, 215, 1317), _no((168, 1270, 215, 1317), "android.widget.RadioButton",
                                                     marcado=self.maior_marcado), "maior")]
            nos.append(((302, 1378, 807, 1420), _no((302, 1378, 807, 1420), desc="Assine um plano com IA do Google"), "plano"))
            # Como no app (15/11): com o 1080p marcado, o botão vira "Aumentar resolução e baixar", mais largo.
            if self.maior_marcado:
                nos.append(((290, 1514, 912, 1640), _no((290, 1514, 912, 1640), "android.widget.Button",
                                                        "Aumentar resolução e baixar"), "confirmar"))
            else:
                nos.append(((677, 1514, 912, 1640), _no((677, 1514, 912, 1640), "android.widget.Button", "Baixar"), "confirmar"))
        elif self.tela == "seletor":
            nos += [((0, 630, 354, 984), _no((0, 630, 354, 984), "android.widget.FrameLayout",
                                              "Item Foto criado em 15 de nov. de 2026 9:48:38 AM", pacote=SELETOR), "marcar"),
                    ((700, 2230, 1070, 2330), _no((700, 2230, 1070, 2330), "android.widget.Button", texto="Adicionar (1)",
                                                   pacote=SELETOR, rid=f"{SELETOR}:id/button_add"), "adicionar")]
        elif self.tela in ("pedido", "menu"):
            nos += [((272, 900, 398, 1000), _no((272, 900, 398, 1000), "android.widget.Button", "Imagem"), ""),
                    ((419, 900, 661, 1000), _no((419, 900, 661, 1000), "android.widget.Button", "Vídeo"), ""),
                    ((45, 1100, 1035, 1200), _no((45, 1100, 1035, 1200), "android.widget.EditText", texto=self.texto), ""),
                    ((45, 1200, 171, 1300), _no((45, 1200, 171, 1300), "android.widget.Button", "Adicionar mídia"), "menu"),
                    ((548, 1200, 867, 1300), _no((548, 1200, 867, 1300), "android.widget.Button", f"{self.modelo}\nx1"), "folha"),
                    ((888, 1200, 1014, 1300), _no((888, 1200, 1014, 1300), "android.widget.Button", "Gerar"), "gerar")]
            if self.foto:
                nos.append(((66, 1000, 213, 1095), _no((66, 1000, 213, 1095), "android.widget.ImageView"), ""))
            if self.tela == "menu":
                nos += [((63, 700, 383, 790), _no((63, 700, 383, 790), "android.widget.Button", "Capturar"), ""),
                        ((63, 790, 383, 880), _no((63, 790, 383, 880), "android.widget.Button", "Imagens"), "seletor")]
            if self.folha:
                nos += [((259, 1400, 823, 1460), _no((259, 1400, 823, 1460), desc="A geração vai usar ", clicavel=False), ""),
                        ((535, 1460, 823, 1520), _no((535, 1460, 823, 1520), "android.widget.Button",
                                                      f"{self.custos[self.modelo]} créditos de IA"), ""),
                        ((540, 1550, 1051, 1650), _no((540, 1550, 1051, 1650), desc="9:16\nGuia 2 de 2"), "")]
                # Como no app (15/11): o Veo 3.1 - Lite não tem a escolha da resolução.
                if self.modelo != "Veo 3.1 - Lite":
                    nos.append(((540, 1660, 1051, 1760), _no((540, 1660, 1051, 1760), desc="720p\nGuia 2 de 2"), ""))
                nos += [((29, 1770, 284, 1870), _no((29, 1770, 284, 1870), desc="x1\nGuia 1 de 4"), ""),
                        ((24, 2244, 1056, 2370), _no((24, 2244, 1056, 2370), desc=self.modelo), "lista")]
            if self.lista:
                nos += [((24, 1880, 1056, 1990), _no((24, 1880, 1056, 1990), desc="Omni 1.1 Flash\n12 créditos / video"),
                         "Omni 1.1 Flash"),
                        ((24, 2000, 1056, 2100), _no((24, 2000, 1056, 2100), desc="Veo 3.1 - Lite\n10 créditos / video"),
                         "Veo 3.1 - Lite"),
                        ((24, 2110, 1056, 2230), _no((24, 2110, 1056, 2230), desc="Omni 1.2 Flash\n24 créditos / video"),
                         "Omni 1.2 Flash")]
        return nos

    def dump_hierarchy(self):
        xml = '<?xml version="1.0" ?><hierarchy rotation="0">' + "".join(no for _, no, _ in self.nos()) + "</hierarchy>"
        if self.tela == "projeto" and self.gerando_leituras > 0:
            self.gerando_leituras -= 1
        if self.tela == "projeto" and self.estendendo():
            self.estendendo_leituras -= 1
        if self.tela == "video":
            self.leituras_do_video += 1
            if self.continuacao_pendente > 0:
                self.continuacao_pendente -= 1
        return xml

    def click(self, x, y):
        self.toques.append((x, y))
        # O de cima ganha: a folha e a lista vêm depois na tela.
        for (x1, y1, x2, y2), _no_xml, acao in reversed(self.nos()):
            if x1 <= x <= x2 and y1 <= y <= y2:
                break
        else:
            return
        if acao in ("projeto", "pedido", "menu", "seletor"):
            self.tela = acao
        elif acao == "folha":
            self.folha = True
        elif acao == "lista":
            self.lista = True
        elif acao in CUSTOS:
            self.modelo, self.lista = acao, False
        elif acao == "marcar":
            self.marcada = True
        elif acao == "adicionar" and self.marcada:
            self.tela, self.foto = "pedido", True
        elif acao == "gerar":
            self.geracoes += 1
            self.tela = "projeto"
            if not self.falha_ao_gerar:
                self.gerado, self.gerando_leituras, self.modelo_do_video = True, self.leituras_ao_gerar, self.modelo
        elif acao == "estender":
            self.tela = "estender"
        elif acao == "gerar_estender":
            # Desligado com a caixa vazia: o toque não faz nada.
            if self.texto_do_estender:
                self.extensoes += 1
                self.texto_estendido, self.texto_do_estender = self.texto_do_estender, ""
                self.estendendo_leituras, self.tela = self.leituras_ao_estender, "video"
                self.continuacao_pendente = self.atraso_da_continuacao
        elif acao == "proibido":
            self.toques_proibidos.append((x, y))
        elif acao.startswith("versao:"):
            self.versao = int(acao.split(":")[1])
        elif acao.startswith("abrir:"):
            self.aberto, self.tela = acao.split(":", 1)[1], "projeto"
            if self.aberto != "Shopee Video":
                self.fora_do_projeto.append("outro")
        elif acao == "novo":
            # Como no Flow (15/11): o Novo cria um projeto vazio com o nome do dia e já o abre.
            self.projetos.insert(0, "nov. 15, 4:30\u202fPM")
            self.aberto, self.tela = "nov. 15, 4:30\u202fPM", "projeto"
            self.fora_do_projeto.append("novo")
        elif acao in ("inicio", "menu_projeto"):
            self.tela = acao
        elif acao == "renomear":
            self.tela, self.nome_no_campo = "renomear", self.aberto
        elif acao == "ok_nome":
            self.projetos[self.projetos.index(self.aberto)] = self.nome_no_campo
            self.aberto, self.tela = self.nome_no_campo, "projeto"
        elif acao == "cancelar_nome":
            self.tela = "projeto"
        elif acao == "filtro":
            self.filtro = True
        elif acao == "antes":
            self.tela, self.abriu_o_de_antes, self.leituras_do_video = "video", True, 0
        elif acao in ("video", "menu_video"):
            if acao == "video" and self.tela != "menu_video":
                self.leituras_do_video = 0
            if acao == "video" and self.tela == "projeto":
                self.falha_no_player = self.falhas_ao_carregar > 0
                self.falhas_ao_carregar -= int(self.falha_no_player)
            self.tela = acao
        elif acao == "baixar":
            self.tela = "tamanho"
        elif acao == "maior":
            if not self.maior_nao_marca:
                self.maior_marcado, self.original_marcado = True, False
        elif acao == "original":
            self.maior_marcado, self.original_marcado = False, True
        elif acao == "plano":
            self.toques_proibidos.append((x, y))
        elif acao == "confirmar":
            self.tela = "video"
            self.baixado = "1080p" if self.maior_marcado else "720p" if self.original_marcado else False
            self.baixadas.append(self.versao)


@pytest.fixture
def celular(bm, monkeypatch, tmp_path):
    aparelho = Flow()
    guardados = []
    monkeypatch.setattr(flow.time, "sleep", lambda segundos: None)
    monkeypatch.setattr(flow.celular_robo, "tela_acesa", lambda: True)
    monkeypatch.setattr(flow.celular_robo, "tela_de_bloqueio", lambda: False)
    monkeypatch.setattr(flow.ps, "conectar", lambda celular=False: aparelho)
    monkeypatch.setattr(flow.casos_robo, "guardar",
                        lambda d, acao, resultado, motivo, passo="", **extra: guardados.append((resultado, motivo)) or "caso")
    monkeypatch.setattr(flow, "ESPERA_DA_TELA", 0.2)
    monkeypatch.setattr(flow, "ESPERA_DA_LISTA", 0.2)
    monkeypatch.setattr(flow, "ESPERA_DA_GERACAO", 30)
    monkeypatch.setattr(flow, "ESPERA_DA_VERSAO", 0.2)
    monkeypatch.setattr(flow, "ESPERA_DO_PLAYER", 0.2)
    monkeypatch.setattr(flow, "ESPERA_DA_CONTINUACAO", 0.3)
    monkeypatch.setattr(flow, "ESPERA_SEM_CONTINUACAO", 0.2)
    monkeypatch.setattr(flow, "PASTA", str(tmp_path / "flow"))
    monkeypatch.setattr(flow.celular_robo, "conectado", lambda: True)
    monkeypatch.setattr(flow.ps, "no_horario_das_rodadas", lambda: True)
    monkeypatch.setattr(flow.celular_robo, "trava", contextlib.contextmanager(lambda: (yield True)))
    aparelho.mandados, aparelho.conferidos, aparelho.fotos = [], [], []

    async def conferir(caminho, prompt, imagens=None):
        aparelho.conferidos.append((caminho, imagens[0][1]))
        return '{"mesmo_produto": true, "diferencas": "", "defeitos": "a mão muda de forma no fim"}'

    monkeypatch.setattr(flow.api_gemini, "analisar_video_gemini", conferir)
    # O anúncio que o Rafael abre para comparar (sem rede nos testes): o link curto vira o do produto.
    async def converter(link):
        return "https://shopee.com.br/produto-i.123.456?sp_atk=x"

    monkeypatch.setattr(flow.api_shopee, "link_para_converter", converter)
    monkeypatch.setattr(flow.avisar_rafael, "mandar_foto",
                        lambda caminho, legenda="": aparelho.fotos.append((caminho, legenda)) or True)
    monkeypatch.setattr(flow.avisar_rafael, "mandar_video",
                        lambda caminho, legenda="": aparelho.mandados.append((caminho, legenda)) or True)
    foto = tmp_path / "foto.jpg"
    foto.write_bytes(_jpeg())
    aparelho.guardados = guardados
    aparelho.teste = {"link": "https://s.shopee.com.br/abc", "nome": "Copo Térmico Inox", "foto": str(foto),
                      "prompt": "The exact stainless steel tumbler from the photo on a kitchen counter, slow push-in.",
                      "cena": "O copo na bancada da cozinha.", "videos": {}}
    return aparelho


def _jpeg():
    saida = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(saida, "JPEG")
    return saida.getvalue()


def test_sem_gerar_monta_o_pedido_inteiro_e_nao_toca_no_gerar(celular, capsys):
    assert flow.no_celular(celular.teste, "Veo 3.1 - Lite", 10, sem_gerar=True) == 0
    assert not celular.gerado
    assert celular.foto and celular.modelo == "Veo 3.1 - Lite" and celular.texto == celular.teste["prompt"]
    assert ("tela", "pedido pronto, sem gerar") in celular.guardados
    # A foto do produto sai da galeria no fim.
    assert any(partes[:2] == ["rm", "-f"] for partes in celular.comandos)
    assert celular.fora_do_projeto == []
    saida = capsys.readouterr().out
    assert "Veo 3.1 - Lite, 10 créditos" in saida and "Copo" not in saida and "tumbler" not in saida


def test_gera_com_tudo_conferido_espera_pronto_e_baixa_o_video(celular, capsys):
    flow.guardar(teste=celular.teste)
    assert flow.no_celular(celular.teste, "Omni 1.1 Flash", 12, sem_gerar=False) == 0
    assert celular.gerado and celular.geracoes == 1
    videos = db.ler_config(flow.CHAVE, {})["teste"]["videos"]
    assert videos["Omni 1.1 Flash"]["estado"] == "baixado" and videos["Omni 1.1 Flash"]["custo"] == 12
    assert videos["Omni 1.1 Flash"]["arquivo"].endswith("video_2.mp4")
    assert any("esperando o vídeo" in motivo for _, motivo in celular.guardados)
    # O arquivo veio do celular, e o celular ficou sem ele e sem a marca do Baixar.
    assert celular.puxados == [BAIXADO]
    assert ["rm", "-f", BAIXADO, flow.MARCA_DO_BAIXAR] in celular.comandos
    saida = capsys.readouterr().out
    assert "Gerar tocado (Omni 1.1 Flash, 12 créditos)" in saida and "Flow: vídeo baixado (1080p, 0.0 MB" in saida
    assert "Mulher" not in saida and ".mp4" not in saida
    assert flow.proximo_modelo(db.ler_config(flow.CHAVE, {})["teste"]) == ("Veo 3.1 - Lite", 10)


def test_teste_gera_baixa_confere_e_manda_no_privado(celular, capsys):
    flow.guardar(teste=celular.teste)
    assert flow.teste() == 0
    assert celular.geracoes == 1 and celular.modelo_do_video == "Veo 3.1 - Lite"
    assert len(celular.mandados) == 1 and celular.conferidos[0][1] == "image/jpeg"
    caminho, legenda = celular.mandados[0]
    assert caminho.endswith("video_1.mp4")
    for trecho in ("vídeo 1 de 3", "Veo 3.1 - Lite (10 créditos de IA)", "Copo Térmico Inox", "O copo na bancada",
                   "o produto é o mesmo da foto do anúncio", "a mão muda de forma no fim", "Nada foi postado"):
        assert trecho in legenda
    video = db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]
    assert video["estado"] == "enviado" and video["mesmo_produto"] is True
    # Pedido do Rafael (15/11): logo depois do vídeo, a foto do anúncio com o link dele, para comparar.
    assert celular.fotos == [(celular.teste["foto"], "🖼️ Foto do anúncio, para comparar com o vídeo 1 de 3 do teste "
                                                     "do Flow\n🔗 Anúncio: https://shopee.com.br/product/123/456")]
    saida = capsys.readouterr().out
    assert "conferência da IA: mesmo produto" in saida and "vídeo mandado no privado do Rafael" in saida
    assert "foto e link do anúncio mandados" in saida and "shopee.com.br" not in saida
    assert "Copo" not in saida and "tumbler" not in saida and "Mulher" not in saida


def test_foto_do_anuncio_que_nao_vai_nao_desfaz_o_envio_do_video(celular, monkeypatch, capsys):
    def falha(caminho, legenda=""):
        raise OSError("sem rede")

    monkeypatch.setattr(flow.avisar_rafael, "mandar_foto", falha)
    flow.guardar(teste=celular.teste)
    assert flow.teste() == 0
    assert len(celular.mandados) == 1
    assert db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]["estado"] == "enviado"
    assert "a foto do anúncio não foi ao privado" in capsys.readouterr().out


def test_link_do_anuncio_sem_o_produto_fica_o_da_fonte(monkeypatch):
    async def falha(link):
        raise OSError("sem rede")

    monkeypatch.setattr(flow.api_shopee, "link_para_converter", falha)
    assert flow.link_do_anuncio("https://s.shopee.com.br/abc") == "https://s.shopee.com.br/abc"

    async def busca(link):
        return "https://shopee.com.br/search?keyword=copo"

    monkeypatch.setattr(flow.api_shopee, "link_para_converter", busca)
    assert flow.link_do_anuncio("https://s.shopee.com.br/abc") == "https://s.shopee.com.br/abc"


def test_video_ja_gerado_e_baixado_e_mandado_sem_gerar_outro(celular):
    celular.teste["videos"] = {"Veo 3.1 - Lite": {"custo": 10, "estado": "gerando"}}
    flow.guardar(teste=celular.teste)
    celular.gerado, celular.modelo_do_video = True, "Veo 3.1 - Lite"
    assert flow.teste() == 0
    assert celular.geracoes == 0 and celular.na_galeria == ""
    assert len(celular.mandados) == 1
    teste = db.ler_config(flow.CHAVE, {})["teste"]
    assert teste["videos"]["Veo 3.1 - Lite"]["estado"] == "enviado"
    assert flow.proximo_modelo(teste) == ("Omni 1.1 Flash", 12)


def test_video_mais_novo_de_outro_modelo_nao_e_baixado_nem_mandado(celular):
    celular.teste["videos"] = {"Veo 3.1 - Lite": {"custo": 10, "estado": "gerando"}}
    flow.guardar(teste=celular.teste)
    celular.gerado, celular.modelo_do_video = True, "Omni 1.1 Flash"
    assert flow.teste() == 1
    assert ("parou", "baixar: o vídeo mais novo não é do modelo do teste") in celular.guardados
    assert not celular.baixado and celular.mandados == []
    assert db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]["estado"] == "gerando"


def test_baixar_marca_o_1080p_e_confirma(celular):
    # O Rafael (15/11): "Mas se podemos baixar 1080 pq vou baixar 720?". Na janela da resolução, o robô
    # marca o 1080p, confere que ficou marcado e só então toca no Baixar dela; nunca no plano do 4K.
    flow.guardar(teste=celular.teste)
    assert flow.teste() == 0
    assert celular.baixado == "1080p" and celular.toques_proibidos == [] and len(celular.mandados) == 1
    video = db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]
    assert video["resolucao"] == "1080p" and video["estado"] == "enviado"
    assert "📐 Resolução: 1080p (aumentada pelo Flow no Baixar)" in celular.mandados[0][1]


def test_baixar_com_custo_no_1080p_baixa_o_tamanho_original(celular):
    # Com crédito na linha do 1080p (ou na janela), o robô não o escolhe: o tamanho original vem marcado.
    celular.custo_no_1080p = True
    flow.guardar(teste=celular.teste)
    assert flow.teste() == 0
    assert celular.baixado == "720p" and (191, 1293) not in celular.toques and celular.toques_proibidos == []
    assert db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]["resolucao"] == "720p"
    assert "📐 Resolução: 720p (o tamanho original)" in celular.mandados[0][1]


def test_aviso_de_credito_na_janela_tira_o_1080p():
    aparelho = Flow()
    aparelho.tela = "tamanho"
    assert flow.janela_do_baixar(aparelho.dump_hierarchy())["1080p"] == {
        "centro": (191, 1293), "marcada": False, "texto": "1080p aumentar a resolução "}
    aparelho.maior_marcado, aparelho.original_marcado = True, False
    janela = flow.janela_do_baixar(aparelho.dump_hierarchy())
    assert janela["1080p"]["marcada"] and not janela["original"]["marcada"] and janela["baixar"] == (601, 1577)
    aparelho.maior_marcado, aparelho.original_marcado = False, True
    aparelho.aviso_de_credito = True
    janela = flow.janela_do_baixar(aparelho.dump_hierarchy())
    assert janela["1080p"] is None and janela["original"]["marcada"] and janela["baixar"] == (794, 1577)


def test_baixar_sem_o_1080p_baixa_o_tamanho_original(celular):
    celular.sem_1080p = True
    flow.guardar(teste=celular.teste)
    assert flow.teste() == 0
    assert celular.baixado == "720p" and celular.toques_proibidos == [] and len(celular.mandados) == 1


def test_baixar_com_o_1080p_que_nao_fica_marcado_para(celular, monkeypatch):
    monkeypatch.setattr(flow, "ESPERA_DA_JANELA_DO_BAIXAR", 0.2)
    celular.maior_nao_marca = True
    flow.guardar(teste=celular.teste)
    assert flow.teste() == 1
    assert celular.tela == "tamanho" and not celular.baixado and celular.mandados == []
    assert ("parou", "baixar: o 1080p não ficou marcado; o robô não baixa sem conferir a resolução") \
        in celular.guardados
    assert db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]["estado"] == "gerando"


def test_baixar_sem_nada_marcado_para_sem_escolher(celular):
    celular.sem_1080p, celular.original_marcado = True, False
    flow.guardar(teste=celular.teste)
    assert flow.teste() == 1
    assert celular.tela == "tamanho" and celular.mandados == [] and celular.toques_proibidos == []
    assert ("parou", "baixar: nem o 1080p nem o tamanho original estão marcados; o robô não escolhe outra resolução") \
        in celular.guardados
    assert db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]["estado"] == "gerando"


def test_gerar_sem_o_gerando_para_e_guarda_a_tela(celular, monkeypatch):
    monkeypatch.setattr(flow, "ESPERA_DO_GERANDO", 0.05)
    celular.falha_ao_gerar = True
    flow.guardar(teste=celular.teste)
    assert flow.no_celular(celular.teste, "Veo 3.1 - Lite", 10, sem_gerar=False) == 1
    assert ("parou", "gerar: o Flow não mostrou o vídeo sendo gerado") in celular.guardados
    assert celular.puxados == []


def test_baixado_que_nao_chegou_ao_rafael_vai_sem_o_celular(celular, monkeypatch, tmp_path):
    arquivo = tmp_path / "video_1.mp4"
    arquivo.write_bytes(b"\0" * 2048)
    celular.teste["videos"] = {"Veo 3.1 - Lite": {"custo": 10, "estado": "baixado", "arquivo": str(arquivo)}}
    flow.guardar(teste=celular.teste)
    monkeypatch.setattr(flow.celular_robo, "conectado", lambda: False)
    assert flow.teste() == 0
    assert celular.toques == [] and celular.mandados[0][0] == str(arquivo)


def test_envio_recusado_fica_para_o_proximo_teste(celular, monkeypatch, capsys):
    flow.guardar(teste=celular.teste)
    monkeypatch.setattr(flow.avisar_rafael, "mandar_video", lambda caminho, legenda="": False)
    assert flow.teste() == 1
    assert db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]["estado"] == "baixado"
    assert "o próximo teste manda de novo" in capsys.readouterr().out


def test_conferencia_e_legenda():
    assert flow.ler_conferencia('ok {"mesmo_produto": false, "diferencas": "a  tampa\\nmudou", "defeitos": ""}') == \
        {"mesmo": False, "diferencas": "a tampa mudou", "defeitos": ""}
    assert flow.ler_conferencia("sem json") == {"mesmo": None, "diferencas": "", "defeitos": ""}
    assert flow.ler_conferencia('{"mesmo_produto": "sim"}')["mesmo"] is None
    teste = {"nome": "Copo Térmico Inox", "cena": "O copo na bancada.", "estilo": "fala"}
    diferente = flow.legenda_do_video(teste, "Omni 1.1 Flash", 12, {"mesmo": False, "diferencas": "a tampa mudou",
                                                                     "defeitos": ""})
    assert "vídeo 2 de 3" in diferente and "o produto muda: a tampa mudou" in diferente
    assert "🎭 Estilo: pessoa falando do produto" in diferente
    # O teste de antes, sem o estilo guardado, foi uma demonstração.
    assert "🎭 Estilo: demonstração" in flow.legenda_do_video({"nome": "Copo"}, "Omni 1.1 Flash", 12,
                                                              {"mesmo": True, "diferencas": "", "defeitos": ""})
    assert "O que parece IA" not in diferente and "último dos 3" not in diferente
    ultimo = flow.legenda_do_video(dict(teste, nome="X" * 2000), "Omni 1.2 Flash", 24,
                                   {"mesmo": None, "diferencas": "", "defeitos": ""})
    assert "vídeo 3 de 3" in ultimo and len(ultimo) <= 1000
    assert "último dos 3" in flow.legenda_do_video(teste, "Omni 1.2 Flash", 24,
                                                   {"mesmo": True, "diferencas": "", "defeitos": ""})


def test_leitura_das_telas_depois_do_gerar():
    projeto = ('<hierarchy>' + _no((0, 466, 537, 1422), desc="1%\nGerando…")
               + _no((543, 466, 1080, 1004), desc="Copo na mesa, 1 item") + '</hierarchy>')
    assert flow.gerando(projeto) and flow.quadro_mais_novo(projeto) == (811, 735)
    pronto = projeto.replace("1%&#10;Gerando…", "Mulher usando o copo, 1 item")
    assert not flow.gerando(pronto) and flow.quadro_mais_novo(pronto) == (268, 944)
    aberto = ('<hierarchy>' + _no((0, 131, 1080, 299), desc="Mulher usando o copo\nVeo 3.1 - Lite\n720p", clicavel=False)
              + _no((0, 309, 1080, 2184), desc="Vídeo tocando, 1 de 1\n0:07") + '</hierarchy>')
    assert flow.titulo_do_video(aberto) == ["Mulher usando o copo", "Veo 3.1 - Lite", "720p"]
    assert flow.titulo_do_video(projeto) is None
    assert not flow.pede_escolha(aberto)
    assert flow.janela_do_baixar(aberto) is None
    assert flow.pede_escolha('<hierarchy>' + _no((100, 1000, 980, 1100), "android.widget.Button", "1080p") + '</hierarchy>')
    assert flow.pede_escolha('<hierarchy>' + _no((0, 0, 10, 10), texto="Permitir",
                                                 pacote="com.google.android.permissioncontroller") + '</hierarchy>')


def test_arquivos_novos_do_baixar():
    class Celular:
        def shell(self, partes):
            assert partes[0] == "find" and flow.MARCA_DO_BAIXAR in partes and "*.mp4" in partes
            return Resposta("find: /sdcard/Movies: No such file or directory\n"
                            "1763216000 100 /sdcard/Download/velho.mp4\n"
                            "1763216200 512 /sdcard/Download/.pending-1763216200-Vídeo novo.mp4\n"
                            "1763216100 2048 /sdcard/Download/Vídeo com espaço.mp4\n")

    assert flow.arquivos_novos(Celular()) == [("/sdcard/Download/Vídeo com espaço.mp4", 2048),
                                              ("/sdcard/Download/velho.mp4", 100)]


def test_gerando_que_some_numa_leitura_nao_conta_como_pronto(celular):
    # O vídeo 3 do teste (15/11): o "Gerando…" sumiu de uma leitura no meio da geração e o robô abriu
    # o vídeo de antes. Agora o pronto pede 3 leituras seguidas do projeto sem ele.
    celular.leituras_ao_gerar, celular.piscar_na_leitura, celular.video_de_antes = 6, 5, "Omni 1.1 Flash"
    flow.guardar(teste=celular.teste)
    assert flow.no_celular(celular.teste, "Omni 1.2 Flash", 24, sem_gerar=False) == 0
    assert celular.baixado and celular.modelo_do_video == "Omni 1.2 Flash" and not celular.abriu_o_de_antes
    assert not any(resultado == "parou" for resultado, _ in celular.guardados)


def test_flow_aberto_no_veo_lite_troca_o_modelo_antes_das_opcoes(celular):
    # O vídeo 2 do teste (15/11): o Flow abriu no último modelo usado, o Veo 3.1 - Lite, que não tem
    # a escolha da resolução; o robô parava procurando o 720p. Agora escolhe o modelo e depois as opções.
    celular.modelo = "Veo 3.1 - Lite"
    flow.guardar(teste=celular.teste)
    assert flow.no_celular(celular.teste, "Omni 1.1 Flash", 12, sem_gerar=False) == 0
    assert celular.gerado and celular.modelo_do_video == "Omni 1.1 Flash"
    assert not any(resultado == "parou" for resultado, _ in celular.guardados)


def test_custo_diferente_na_tela_nao_gera(celular, capsys):
    celular.custos = dict(CUSTOS, **{"Omni 1.2 Flash": 30})
    assert flow.no_celular(celular.teste, "Omni 1.2 Flash", 24, sem_gerar=False) == 1
    assert not celular.gerado
    assert ("parou", "antes do Gerar: o custo na tela não é o esperado") in celular.guardados
    assert "Flow: parou: antes do Gerar: o custo na tela não é o esperado" in capsys.readouterr().out


def test_tela_de_termos_para_sem_tocar(celular):
    celular.termos = True
    assert flow.no_celular(celular.teste, "Veo 3.1 - Lite", 10, sem_gerar=False) == 1
    assert not celular.gerado and celular.toques == []
    assert any("termos" in motivo for resultado, motivo in celular.guardados if resultado == "parou")


def test_pedido_com_foto_de_antes_para_sem_por_outra_e_sem_gerar(celular):
    celular.foto = True
    assert flow.no_celular(celular.teste, "Veo 3.1 - Lite", 10, sem_gerar=False) == 1
    assert not celular.gerado and celular.tela == "pedido" and not celular.marcada
    assert ("parou", "pedido: já tinha foto ou texto de antes") in celular.guardados


def test_tela_de_bloqueio_nao_toca_em_nada(celular, monkeypatch, capsys):
    monkeypatch.setattr(flow.celular_robo, "tela_de_bloqueio", lambda: True)
    assert flow.no_celular(celular.teste, "Veo 3.1 - Lite", 10, sem_gerar=False) == 1
    assert celular.toques == [] and celular.na_galeria == ""
    assert "tela de bloqueio" in capsys.readouterr().out


class Subindo:
    """O pedido que sobe com o teclado: o Vídeo aparece embaixo e, na leitura seguinte, já no lugar."""

    def __init__(self, dialogo=False):
        self.leituras, self.toques, self.dialogo = 0, [], dialogo

    def dump_hierarchy(self):
        self.leituras += 1
        y = 1900 if self.leituras == 1 else 900
        nos = _no((419, y, 661, y + 100), "android.widget.Button", "Vídeo")
        if self.dialogo:
            nos += _no((154, 1335, 435, 1461), "android.widget.Button", texto="Cancelar", pacote=flow.PACOTE_DO_TECLADO)
        return f'<hierarchy>{nos}</hierarchy>'

    def click(self, x, y):
        self.toques.append((x, y))


def test_toca_so_quando_o_botao_para_de_subir(monkeypatch):
    monkeypatch.setattr(flow.time, "sleep", lambda segundos: None)
    celular = Subindo()
    flow.tocar(celular, "Vídeo", "modo vídeo")
    assert celular.toques == [(540, 950)] and celular.leituras >= 3


def test_aviso_do_teclado_para_sem_tocar(monkeypatch):
    monkeypatch.setattr(flow.time, "sleep", lambda segundos: None)
    celular = Subindo(dialogo=True)
    with pytest.raises(flow.Parada, match="aviso do teclado"):
        flow.tocar(celular, "Vídeo", "modo vídeo")
    assert celular.toques == []


def test_ordem_dos_modelos_do_mais_barato_ao_mais_caro():
    assert flow.proximo_modelo({}) == ("Veo 3.1 - Lite", 10)
    assert flow.proximo_modelo({"videos": {"Veo 3.1 - Lite": {}}}) == ("Omni 1.1 Flash", 12)
    assert flow.proximo_modelo({"videos": {"Veo 3.1 - Lite": {}, "Omni 1.1 Flash": {}}}) == ("Omni 1.2 Flash", 24)
    assert flow.proximo_modelo({"videos": dict.fromkeys(CUSTOS, {})}) is None
    assert sum(custo for _, custo in flow.MODELOS_DO_TESTE) <= 50


def test_resposta_da_ia():
    texto = 'Claro!\n{"serve": true, "motivo": "", "prompt": "Slow orbit  around\\nthe mug", "cena": "A caneca na mesa."}'
    # Sem o muda_na_ia na resposta, o produto não sai pela IA de vídeo (P245 1): só o true conta.
    assert flow.ler_resposta(texto) == {"serve": True, "muda_na_ia": False, "motivo": "", "estilo": "demonstracao",
                                        "prompt": "Slow orbit around the mug", "cena": "A caneca na mesa."}
    assert flow.ler_resposta('{"serve": true, "muda_na_ia": "talvez", "prompt": "p"}')["muda_na_ia"] is False
    assert flow.ler_resposta('{"serve": true, "muda_na_ia": true, "prompt": "p"}')["muda_na_ia"] is True
    # O estilo como a IA escrever, com ou sem acento; o que não é nenhum vira a demonstração.
    for escrito, estilo in (("Comédia", "comedia"), ("fala", "fala"), ("inusitado", "inusitado"),
                            ("demonstração", "demonstracao"), ("dança", "demonstracao")):
        resposta = flow.ler_resposta(json.dumps({"serve": True, "estilo": escrito, "prompt": "p", "cena": "c"}))
        assert resposta["estilo"] == estilo, escrito
    assert flow.ler_resposta('{"serve": false, "motivo": "colagem de fotos"}')["serve"] is False
    assert flow.ler_resposta('{"serve": true, "prompt": ""}') is None
    assert flow.ler_resposta("não sei") is None and flow.ler_resposta(None) is None


def test_escolhe_o_primeiro_produto_com_foto_boa_e_o_log_nao_tem_o_produto(bm, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(flow, "PASTA", str(tmp_path))
    monkeypatch.setattr(flow.assistente, "candidatos_nao_usados",
                        lambda fonte: [("a", "a.mp4", "https://s.shopee.com.br/sem-foto", ""),
                                       ("b", "b.mp4", "https://s.shopee.com.br/com-foto", "")])
    monkeypatch.setattr(flow.ps, "anuncio_do_produto",
                        lambda video: {"foto": _jpeg(), "nome": "Copo Térmico Inox"} if "com-foto" in video["link"] else {})

    pedidos = []

    async def ia(prompt, imagens=None):
        assert "Copo Térmico Inox" in prompt and imagens[0][1] == "image/jpeg"
        pedidos.append(prompt)
        return json.dumps({"serve": True, "motivo": "", "estilo": "comedia", "prompt": "The exact tumbler, slow push-in.",
                           "cena": "O copo na bancada."})

    monkeypatch.setattr(flow.api_gemini, "gerar_texto_gemini", ia)
    monkeypatch.setattr(flow.celular_robo, "conectado", lambda: False)
    assert flow.main(["teste", "--sem-gerar"]) == 1
    saida = capsys.readouterr().out
    assert "o 2º dos próximos vídeos da fonte" in saida and "celular: desconectado" in saida
    assert "Copo" not in saida and "tumbler" not in saida
    teste = db.ler_config(flow.CHAVE, {})["teste"]
    assert teste["nome"] == "Copo Térmico Inox" and teste["link"].endswith("com-foto") and teste["videos"] == {}
    # A foto do teste fica guardada para os 3 vídeos serem do mesmo produto.
    assert flow.teste_guardado()["foto"].endswith("foto_do_teste.jpg")
    # Pedido do Rafael (15/11): o vídeo pode ter fala em português, ser inusitado ou de comédia, sem zombar de
    # ninguém; o estilo fica guardado e entra na lista dos últimos, e o próximo pedido pede outro.
    assert "português do Brasil" in pedidos[0] and "zombar" in pedidos[0] and "comedia" in pedidos[0]
    assert "prefira outro estilo" not in pedidos[0]
    assert teste["estilo"] == "comedia" and db.ler_config(flow.CHAVE, {})["estilos"] == ["comedia"]
    db.atualizar_config(flow.CHAVE, lambda dados: dados.pop("teste"))
    flow.escolher_o_produto()
    assert 'Os últimos vídeos foram "comedia": prefira outro estilo' in pedidos[-1]


def test_foto_contada_com_as_opcoes_do_modelo_abertas():
    # Como no ensaio de 15/11: com as opções abertas, a caixa do pedido ocupa a tela toda, e a
    # miniatura da foto fica dentro dela, acima do +.
    aberta = ('<hierarchy>' + _no((0, 950, 1080, 2394), "android.widget.EditText", texto="The exact product, slow push-in.")
              + _no((63, 992, 210, 1118), "android.widget.ImageView")
              + _no((42, 1643, 168, 1769), "android.widget.Button", "Adicionar mídia")
              + _no((573, 1643, 870, 1769), "android.widget.Button", "Veo 3.1 - Lite\nx1")
              + _no((536, 1866, 820, 1929), "android.widget.Button", "10 créditos de IA") + '</hierarchy>')
    assert flow.fotos_no_pedido(aberta) == 1
    assert flow.pronto_para_gerar(aberta, "The exact product, slow push-in.", "Veo 3.1 - Lite", 10) == ""
    # Sem as opções: a miniatura acima da caixa do pedido, e o + embaixo dela.
    fechada = ('<hierarchy>' + _no((66, 1950, 213, 2076), "android.widget.ImageView")
               + _no((45, 2076, 1035, 2202), "android.widget.EditText")
               + _no((45, 2202, 171, 2328), "android.widget.Button", "Adicionar mídia") + '</hierarchy>')
    assert flow.fotos_no_pedido(fechada) == 1
    duas = fechada.replace('</hierarchy>', _no((230, 1950, 377, 2076), "android.widget.ImageView") + '</hierarchy>')
    assert flow.fotos_no_pedido(duas) == 2


def test_leitura_das_telas():
    folha = ('<hierarchy>' + _no((535, 1460, 823, 1520), "android.widget.Button", "24 créditos de IA")
             + _no((548, 1200, 867, 1300), "android.widget.Button", "Omni 1.2 Flash\nx1")
             + _no((24, 2110, 1056, 2230), desc="Veo 3.1 - Lite\n10 créditos / video") + '</hierarchy>')
    assert flow.custo_na_tela(folha) == 24 and flow.modelo_no_pedido(folha) == "Omni 1.2 Flash"
    inicio = ('<hierarchy>' + _no((42, 900, 1038, 1080), desc="O título do projeto é nov. 15, 12:09 PM")
              + _no((42, 1100, 1038, 1300), desc="O título do projeto é Shopee Video, 1 vídeo, 4 imagens")
              + '</hierarchy>')
    assert flow.projeto_na_lista(inicio) == (540, 1200)
    assert flow.projeto_na_lista(inicio.replace("Shopee Video,", "Shopee Video 2,")) is None
    assert flow.projeto_na_lista(inicio.replace("O título do projeto é Shopee Video", "shopee video")) == (540, 1200)
    assert flow.projeto_na_lista('<hierarchy>' + _no((42, 1100, 1038, 1300), desc="Shopee Video") + '</hierarchy>') \
        == (540, 1200)
    assert flow.custo_na_tela('<hierarchy></hierarchy>') is None


def test_sem_o_projeto_shopee_video_cria_um_com_o_nome_e_usa(celular, capsys):
    # Pedido do Rafael (15/11): sem o projeto Shopee Video na lista (apagado), o robô cria outro com esse
    # nome e o usa de padrão. O Novo abre um projeto vazio com o nome do dia; o Renomear o troca.
    celular.projetos.remove("Shopee Video")
    assert flow.no_celular(celular.teste, "Veo 3.1 - Lite", 10, sem_gerar=True) == 0
    assert celular.projetos == ["Shopee Video", "nov. 15, 12:09\u202fPM"]
    assert celular.fora_do_projeto == ["novo"] and celular.toques_proibidos == []
    assert celular.aberto == "Shopee Video" and celular.foto and celular.texto == celular.teste["prompt"]
    assert db.ler_config(flow.CHAVE, {})["projeto_criado_em"][:10] == flow.agora()[:10]
    assert f"o projeto {flow.PROJETO_DO_ROBO} não estava na lista; criado" in capsys.readouterr().out


def test_projeto_ja_criado_hoje_nao_vira_outro(celular):
    # O projeto criado que não ficou com o nome (ou que sumiu de novo) não vira outro no mesmo dia.
    celular.projetos.remove("Shopee Video")
    flow.guardar(projeto_criado_em=flow.agora())
    assert flow.no_celular(celular.teste, "Veo 3.1 - Lite", 10, sem_gerar=True) == 1
    assert celular.fora_do_projeto == [] and celular.projetos == ["nov. 15, 12:09\u202fPM"]
    assert any("já criou um projeto hoje" in motivo for _, motivo in celular.guardados)


def test_nome_que_nao_entra_no_campo_nao_e_confirmado(celular):
    celular.projetos.remove("Shopee Video")
    celular.nome_nao_entra = True
    assert flow.no_celular(celular.teste, "Veo 3.1 - Lite", 10, sem_gerar=True) == 1
    assert (828, 215) not in celular.toques and celular.projetos[0] == "nov. 15, 4:30\u202fPM"
    assert ("parou", "renomear o projeto: o nome não entrou no campo") in celular.guardados
    assert not celular.gerado and celular.toques_proibidos == []


def test_projeto_mais_abaixo_na_lista_e_achado_rolando_sem_criar_outro(celular):
    # O projeto novo entra no alto da lista e empurra o do robô para baixo, para fora da tela.
    celular.projetos[:0] = [f"nov. {dia}, 10:00\u202fAM" for dia in range(16, 22)]
    assert flow.no_celular(celular.teste, "Veo 3.1 - Lite", 10, sem_gerar=True) == 0
    assert celular.fora_do_projeto == [] and celular.aberto == "Shopee Video" and celular.rolagem == 4
    assert len(celular.projetos) == 8


def test_leitura_do_alto_do_projeto_e_do_renomear():
    # Como no Flow (15/11): o título do projeto no alto; no Renomear, o campo com o ✓ e o ✕ à direita.
    projeto = ('<hierarchy>' + _no((0, 152, 1080, 278), desc="Shopee Video", clicavel=False)
               + _no((42, 152, 168, 278), "android.widget.Button", "Voltar")
               + _no((912, 152, 1038, 278), "android.widget.Button", "Mais opções")
               + _no((0, 466, 537, 1422), desc="Copo na mesa, 1 item")
               + _no((891, 1300, 1017, 1400), "android.widget.Button", "Mais opções") + '</hierarchy>')
    assert flow.titulo_do_projeto(projeto) == "Shopee Video"
    assert flow.botao_do_alto(projeto, "Mais opções") == (975, 215)
    renomear = ('<hierarchy>' + _no((0, 152, 1080, 278), "android.widget.EditText", texto="nov. 15", foco=True)
                + _no((912, 152, 1038, 278), "android.widget.Button") + _no((765, 152, 891, 278), "android.widget.Button")
                + _no((400, 1200, 680, 1300), "android.widget.Button") + '</hierarchy>')
    assert flow.campo_do_nome(renomear)["texto"] == "nov. 15"
    assert flow.botoes_do_nome(renomear) == [(828, 215), (975, 215)]
    assert flow.titulo_do_projeto(renomear) == "" and flow.botoes_do_nome(projeto) == []


def test_video_com_a_versao_estendida_escolhe_a_do_modelo_do_teste(celular):
    # O Estender que o Rafael fez no vídeo do teste (15/11) ficou junto do original: no celular dele, o
    # vídeo abriu na versão estendida (Omni 1.2 Flash). O robô passa para a versão do Veo antes de baixar.
    celular.teste["videos"] = {"Veo 3.1 - Lite": {"custo": 10, "estado": "gerando"}}
    flow.guardar(teste=celular.teste)
    celular.gerado, celular.versoes, celular.versao = True, ["Veo 3.1 - Lite", "Omni 1.2 Flash"], 1
    assert flow.teste() == 0
    assert celular.versao == 0 and celular.baixado and len(celular.mandados) == 1
    assert db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]["estado"] == "enviado"


def test_video_que_nao_carrega_no_player_e_fechado_e_aberto_de_novo(celular, capsys):
    # Amostra nº 2 (16/11): o vídeo ficou pronto, mas abriu com "Falha ao carregar o vídeo" no player, e
    # o robô parou sem baixar. Agora ele fecha e abre de novo, como uma pessoa faria, e baixa.
    flow.comecar_producao("2026-11-16", _escolhido(), 1)
    flow.guardar_producao(estado="gerando", gerado_em="2026-11-16 08:00:00")
    celular.gerado, celular.modelo_do_video, celular.falhas_ao_carregar = True, "Omni 1.2 Flash", 2
    assert flow.producao_no_celular(celular, flow.producao()) is True
    assert celular.falhas_ao_carregar == 0 and celular.baixado and celular.geracoes == 0
    assert capsys.readouterr().out.count("o vídeo não carregou no player; fechado para abrir de novo") == 2


def test_video_que_nunca_carrega_no_player_para_sem_baixar(celular):
    flow.comecar_producao("2026-11-16", _escolhido(), 1)
    flow.guardar_producao(estado="gerando", gerado_em="2026-11-16 08:00:00")
    celular.gerado, celular.modelo_do_video, celular.falhas_ao_carregar = True, "Omni 1.2 Flash", 99
    with pytest.raises(flow.Parada, match="o Flow não carregou o vídeo"):
        flow.producao_no_celular(celular, flow.producao())
    # Três aberturas, nenhum Baixar; o vídeo continua "gerando" para a próxima rodada baixar.
    assert celular.falhas_ao_carregar == 99 - flow.ABERTURAS_DO_VIDEO
    assert not celular.baixado and flow.producao()["estado"] == "gerando"


def test_versoes_sem_a_do_modelo_do_teste_nao_baixam(celular):
    celular.teste["videos"] = {"Veo 3.1 - Lite": {"custo": 10, "estado": "gerando"}}
    flow.guardar(teste=celular.teste)
    celular.gerado, celular.versoes = True, ["Omni 1.2 Flash", "Omni 1.1 Flash"]
    assert flow.teste() == 1
    assert not celular.baixado and celular.mandados == []
    assert ("parou", "baixar: o vídeo mais novo não é do modelo do teste") in celular.guardados


# --- A produção: 1 vídeo de IA por dia, que vira rascunho do robô (P232 1) ---

def _escolhido():
    return {"id": "ia:2026-11-16", "link": "https://s.shopee.com.br/abc", "nome": "Copo Térmico Inox", "foto": _jpeg(),
            "estilo": "comedia", "prompt": "The exact stainless steel tumbler from the photo, a funny kitchen scene.",
            "cena": "O copo na bancada da cozinha.", "item": "456", "valor": 3.5,
            "origem": "os produtos em alta da Shopee"}


def test_producao_gera_no_omni_1_2_baixa_e_confere_sem_mandar_ao_privado(celular, capsys):
    # Escolha do Rafael (15/11, P232 1): 1 vídeo por dia no Omni 1.2 Flash, que vira rascunho do robô.
    atual = flow.comecar_producao("2026-11-16", _escolhido(), 1)
    assert atual["estado"] == "escolhido" and (atual["modelo"], atual["custo"]) == ("Omni 1.2 Flash", 24)
    assert atual["foto"].endswith("producao_2026-11-16.jpg") and atual["id_video"] == "ia:2026-11-16"
    # De que lista da API de afiliado o produto veio (P234 1) fica no andamento, para o aviso do rascunho.
    assert atual["origem"] == "os produtos em alta da Shopee"
    assert flow.estilos_recentes()[-1] == "comedia"
    # Até o Gerar, o produto ainda pode voltar à escolha; tocado o Gerar, ele não ganha outro vídeo (P234 1).
    assert flow.itens_gerados() == []
    assert flow.producao_no_celular(celular, atual) is True
    assert celular.geracoes == 1 and celular.modelo == "Omni 1.2 Flash"
    assert flow.itens_gerados() == ["456"]
    atual = flow.producao()
    assert atual["estado"] == "baixado" and atual["arquivo"].endswith("producao_2026-11-16.mp4")
    assert atual["gerado_em"] and atual["custo"] == 24
    assert flow.video_pronto() is None
    assert flow.conferir_a_producao() == "pronto"
    assert flow.video_pronto()["conferencia"]["mesmo"] is True
    # A foto sai da galeria, e nada vai ao privado: o vídeo vira um rascunho do robô.
    assert any(partes[:2] == ["rm", "-f"] for partes in celular.comandos) and celular.mandados == []
    # A espera do vídeo não guarda a tela de minuto em minuto: os casos ficam para as falhas.
    assert not any("esperando o vídeo" in motivo for _, motivo in celular.guardados)
    saida = capsys.readouterr().out
    assert "Gerar tocado (Omni 1.2 Flash, 24 créditos)" in saida and "Copo" not in saida and "tumbler" not in saida


def test_producao_com_outro_produto_no_video_e_descartada(celular, monkeypatch):
    async def conferir(caminho, prompt, imagens=None):
        return '{"mesmo_produto": false, "diferencas": "a tampa é outra", "defeitos": ""}'

    monkeypatch.setattr(flow.api_gemini, "analisar_video_gemini", conferir)
    atual = flow.comecar_producao("2026-11-16", _escolhido(), 1)
    assert flow.producao_no_celular(celular, atual) is True
    assert flow.conferir_a_producao() == "descartado" and flow.video_pronto() is None
    assert "o produto muda: a tampa é outra" in flow.legenda_da_producao(flow.producao())


def test_producao_ja_gerada_so_baixa_sem_gerar_outro(celular):
    flow.comecar_producao("2026-11-16", _escolhido(), 1)
    flow.guardar_producao(estado="gerando", gerado_em="2026-11-16 08:00:00")
    celular.gerado, celular.modelo_do_video = True, "Omni 1.2 Flash"
    assert flow.producao_no_celular(celular, flow.producao()) is True
    assert celular.geracoes == 0 and flow.producao()["estado"] == "baixado"


def test_producao_parada_no_flow_guarda_o_caso(celular, monkeypatch):
    monkeypatch.setattr(flow, "ESPERA_DO_GERANDO", 0.05)
    celular.falha_ao_gerar = True
    atual = flow.comecar_producao("2026-11-16", _escolhido(), 1)
    with pytest.raises(flow.Parada):
        flow.producao_no_celular(celular, atual)
    assert ("parou", "gerar: o Flow não mostrou o vídeo sendo gerado") in celular.guardados
    assert flow.producao()["estado"] == "gerando"
    # O Gerar foi tocado (o crédito pode ter sido gasto): o produto já fica de fora das próximas escolhas.
    assert flow.itens_gerados() == ["456"]


def test_producao_nova_tira_os_arquivos_da_de_antes(celular):
    flow.comecar_producao("2026-11-15", _escolhido(), 1)
    antiga = flow.producao()["foto"]
    flow.comecar_producao("2026-11-16", _escolhido(), 1)
    import os
    assert not os.path.exists(antiga) and os.path.exists(flow.producao()["foto"])


def test_legenda_da_producao_e_bebida_em_espera_no_pedido(monkeypatch):
    legenda = flow.legenda_da_producao({"modelo": "Omni 1.2 Flash", "custo": 24, "estilo": "fala",
                                        "cena": "Uma moça mostra o copo.",
                                        "conferencia": {"mesmo": True, "diferencas": "", "defeitos": "a mão muda"}})
    for trecho in ("Omni 1.2 Flash (24 créditos de IA)", "pessoa falando do produto", "Uma moça mostra o copo.",
                   "o produto é o mesmo da foto do anúncio", "O que parece IA: a mão muda"):
        assert trecho in legenda
    # Bebida alcoólica em espera (P111): a IA diz que a foto não serve, antes de gastar o crédito do vídeo.
    pedidos = []

    async def ia(prompt, imagens=None):
        pedidos.append(prompt)
        return json.dumps({"serve": False, "motivo": "bebida", "estilo": "", "prompt": "", "cena": ""})

    monkeypatch.setattr(flow.ps, "anuncio_do_produto", lambda video: {"foto": _jpeg(), "nome": "Vinho Tinto"})
    monkeypatch.setattr(flow.api_gemini, "gerar_texto_gemini", ia)
    monkeypatch.setattr(flow.assistente, "BEBIDA_EM_ESPERA", True)
    assert flow.pedido_para_o_produto("https://s.shopee.com.br/vinho") is None
    assert flow.TRECHO_DA_BEBIDA in pedidos[0]
    monkeypatch.setattr(flow.assistente, "BEBIDA_EM_ESPERA", False)
    flow.pedido_para_o_produto("https://s.shopee.com.br/vinho")
    assert flow.TRECHO_DA_BEBIDA not in pedidos[1]


def test_pedido_pelo_anuncio_diz_se_a_foto_serve(monkeypatch):
    # A escolha pela lista da API de afiliado (P234 1) já tem o nome e a foto do anúncio, e precisa saber se a IA
    # recusou a foto (o produto não volta à escolha) ou se não deu para saber (ele volta).
    respostas = []

    async def ia(prompt, imagens=None):
        assert "Copo Térmico Inox" in prompt and imagens[0][1] == "image/jpeg"
        return respostas.pop(0)

    monkeypatch.setattr(flow.api_gemini, "gerar_texto_gemini", ia)
    link = "https://s.shopee.com.br/copo"
    respostas.append(json.dumps({"serve": True, "motivo": "", "estilo": "fala", "prompt": "The exact tumbler.",
                                 "cena": "Uma moça mostra o copo."}))
    pedido, serve = flow.pedido_para_o_anuncio(link, "Copo Térmico Inox", _jpeg())
    assert serve is True and pedido["link"] == link and pedido["nome"] == "Copo Térmico Inox"
    assert pedido["estilo"] == "fala" and pedido["prompt"] == "The exact tumbler." and pedido["foto"]
    respostas.append(json.dumps({"serve": False, "motivo": "colagem de fotos"}))
    assert flow.pedido_para_o_anuncio(link, "Copo Térmico Inox", _jpeg()) == (None, False)
    # Sem a resposta da IA, sem a foto ou sem o nome, não dá para saber: None, e a IA nem é chamada sem a foto.
    respostas.append("não sei")
    assert flow.pedido_para_o_anuncio(link, "Copo Térmico Inox", _jpeg()) == (None, None)
    assert flow.pedido_para_o_anuncio(link, "Copo Térmico Inox", None) == (None, None)
    assert flow.pedido_para_o_anuncio(link, "Copo Térmico Inox", b"nao e imagem") == (None, None)


def test_produto_que_a_ia_de_video_muda_sai_da_escolha_mesmo_com_a_foto_boa(monkeypatch):
    # Escolha do Rafael (16/11, P245 1): em 16/11, os 2 vídeos de IA pedidos no De IA ✨ foram gerados e descartados
    # pelas conferências (a TV não saiu igual à da foto). A IA que olha a foto diz também se o produto tem o que a IA
    # de vídeo costuma mudar (tela, marca ou letras no corpo, muitos botões), e ele sai antes de gastar o crédito.
    respostas, pedidos = [], []

    async def ia(prompt, imagens=None):
        pedidos.append(prompt)
        return respostas.pop(0)

    monkeypatch.setattr(flow.api_gemini, "gerar_texto_gemini", ia)
    link = "https://s.shopee.com.br/tv"
    respostas.append(json.dumps({"serve": True, "muda_na_ia": True, "motivo": "tela e marca", "estilo": "fala",
                                 "prompt": "The exact TV.", "cena": "Uma família vê a TV."}))
    assert flow.pedido_para_o_anuncio(link, "Smart TV 50", _jpeg()) == (None, flow.MUDA_NA_IA)
    assert '"muda_na_ia"' in pedidos[0] and "tela (TV, celular" in pedidos[0] and "letras no corpo" in pedidos[0]
    # Com a marca falsa (ou sem ela, como antes), vale a foto boa.
    respostas.append(json.dumps({"serve": True, "muda_na_ia": False, "motivo": "", "estilo": "fala",
                                 "prompt": "The exact tumbler.", "cena": "Uma moça mostra o copo."}))
    pedido, serve = flow.pedido_para_o_anuncio(link, "Copo Térmico Inox", _jpeg())
    assert serve is True and pedido["prompt"] == "The exact tumbler."
    # A foto que não serve continua recusada pela foto, mesmo com a marca.
    respostas.append(json.dumps({"serve": False, "muda_na_ia": True, "motivo": "colagem de fotos"}))
    assert flow.pedido_para_o_anuncio(link, "Smart TV 50", _jpeg()) == (None, False)
    # O aviso do vídeo que outra conferência descartou vai sem a do Flow, que o deixou passar.
    atual = {"modelo": "Omni 1.2 Flash", "custo": 24, "estilo": "fala", "cena": "Uma família vê a TV.",
             "conferencia": {"mesmo": True, "diferencas": "", "defeitos": ""}}
    assert "🔎" in flow.legenda_da_producao(atual)
    assert "🔎" not in flow.legenda_da_producao(atual, com_a_conferencia=False)
    assert "Omni 1.2 Flash (24 créditos de IA)" in flow.legenda_da_producao(atual, com_a_conferencia=False)
    assert flow.pedido_para_o_anuncio(link, "", _jpeg()) == (None, None) and respostas == []


def test_memoria_dos_produtos_que_nao_voltam_a_escolha(bm, monkeypatch):
    # P234 1: a lista da API muda pouco de um dia para o outro. O produto que já teve um vídeo gerado e o de foto
    # que a IA recusou ficam lembrados (só os números), sem repetir, os mais novos por último.
    assert flow.itens_gerados() == [] and flow.fotos_recusadas() == []
    flow.lembrar_item_gerado("11")
    flow.lembrar_item_gerado(22)
    flow.lembrar_item_gerado("11")
    flow.lembrar_item_gerado("")
    flow.lembrar_foto_recusada("33")
    assert flow.itens_gerados() == ["22", "11"] and flow.fotos_recusadas() == ["33"]
    # O resto da chave do Flow (o andamento do dia, os estilos) fica como estava.
    flow.guardar_producao(estado="pronto")
    flow.lembrar_foto_recusada("44")
    assert flow.producao()["estado"] == "pronto" and flow.fotos_recusadas() == ["33", "44"]
    monkeypatch.setattr(flow, "ITENS_LEMBRADOS", 2)
    flow.lembrar_foto_recusada("55")
    assert flow.fotos_recusadas() == ["44", "55"]


# --- As amostras: vídeos de teste da produção, só no privado do Rafael (P236 1) ---

def _escolha_da_amostra(monkeypatch):
    """A escolha do robô (P234 1) de mentira: cada pedido dá o próximo produto; guarda o que foi deixado de fora."""
    import robo_shopee_video as robo
    pedidos = []

    def escolher(agora=None, fora=(), amostra=False, longo=False):
        pedidos.append((list(fora), amostra))
        item = str(455 + len(pedidos))
        return ({"id": "ia:2026-11-16", "link": f"https://s.shopee.com.br/curto{item}", "nome": "Copo Térmico Inox",
                 "foto": _jpeg(), "estilo": "fala", "prompt": "The exact tumbler from the photo, a woman talks.",
                 "cena": "Uma moça mostra o copo.", "item": item, "valor": 6.5, "posicao": 1,
                 "origem": "os produtos em alta da Shopee"}, "os produtos em alta da Shopee", True)

    monkeypatch.setattr(robo, "escolher_para_o_video_de_ia", escolher)
    return pedidos


def test_amostra_gera_no_modelo_da_producao_e_vai_so_ao_privado(celular, monkeypatch, capsys):
    # Pedido do Rafael (16/11, P236 1): ver como os vídeos de IA estão ficando sem esperar o do dia. A amostra é um
    # vídeo como o da produção, que vai só ao privado dele; roda fora do Horário do Robô, porque ele pediu.
    pedidos = _escolha_da_amostra(monkeypatch)
    monkeypatch.setattr(flow.ps, "no_horario_das_rodadas", lambda: False)
    assert flow.main(["amostra"]) == 0
    assert pedidos == [([], True)] and celular.geracoes == 1 and celular.modelo == "Omni 1.2 Flash"
    (caminho, legenda), = celular.mandados
    assert caminho.endswith("amostra.mp4")
    for trecho in ("Amostra do vídeo de IA nº 1", "Omni 1.2 Flash (24 créditos de IA)", "Copo Térmico Inox",
                   "Paga R$ 6,50 por venda", "os produtos em alta da Shopee", "Uma moça mostra o copo.",
                   "pessoa falando do produto", "o produto é o mesmo da foto do anúncio", "Nada foi postado"):
        assert trecho in legenda, trecho
    assert len(celular.fotos) == 1 and "amostra nº 1" in celular.fotos[0][1]
    assert "Anúncio: https://shopee.com.br/product/123/456" in celular.fotos[0][1]
    # Não vira rascunho nem muda o vídeo do dia: a produção fica como estava, e o produto pode ser o do dia.
    assert flow.producao() == {} and flow.itens_gerados() == [] and flow.amostras_feitas() == ["456"]
    assert flow.estilos_recentes()[-1] == "fala"
    # A próxima amostra deixa de fora o produto da anterior.
    monkeypatch.setattr(flow.ps, "conectar", lambda celular=False, novo=Flow(): novo)
    assert flow.main(["amostra"]) == 0
    assert pedidos[-1] == (["456"], True) and flow.amostras_feitas() == ["456", "457"]
    assert len(celular.mandados) == 2 and "Amostra do vídeo de IA nº 2" in celular.mandados[-1][1]
    # O log público não tem o produto, o pedido nem o link.
    saida = capsys.readouterr().out
    assert "Gerar tocado (Omni 1.2 Flash, 24 créditos)" in saida and "Amostra nº 2: vídeo mandado" in saida
    for privado in ("Copo", "tumbler", "shopee.com.br", "6,50"):
        assert privado not in saida, privado


def test_amostra_ja_gerada_so_baixa_e_a_que_nao_foi_ao_privado_vai_sem_gerar(celular, monkeypatch, capsys):
    pedidos = _escolha_da_amostra(monkeypatch)
    # A rodada de antes tocou no Gerar e o vídeo não ficou pronto a tempo: esta só baixa e manda, sem outro Gerar.
    no_celular = flow._amostra_no_celular
    monkeypatch.setattr(flow, "_amostra_no_celular", lambda atual, sem_gerar, so_baixar: 1)
    assert flow.main(["amostra"]) == 1 and len(pedidos) == 1
    flow.marcar_amostra(estado="gerando", gerado_em="2026-11-16 00:30:00")
    monkeypatch.setattr(flow, "_amostra_no_celular", no_celular)
    celular.gerado, celular.modelo_do_video = True, "Omni 1.2 Flash"
    assert flow.amostra() == 0
    assert len(pedidos) == 1 and celular.geracoes == 0 and len(celular.mandados) == 1
    assert "já gerada; falta baixar e mandar" in capsys.readouterr().out
    # O vídeo baixado que o Telegram recusou vai na próxima vez, sem o celular.
    flow.marcar_amostra(estado="baixado")
    monkeypatch.setattr(flow.celular_robo, "conectado", lambda: pytest.fail("não precisa do celular"))
    assert flow.amostra() == 0 and len(pedidos) == 1 and len(celular.mandados) == 2
    assert flow.amostra_guardada()["estado"] == "enviado" and flow.amostras_feitas() == ["456"]


def test_amostra_sem_produto_ou_com_a_lista_negada_nao_toca_no_celular(celular, monkeypatch, capsys):
    import robo_shopee_video as robo

    def negada(agora=None, fora=(), amostra=False, longo=False):
        raise robo.api_shopee.BuscaNegada("código 10.000")

    monkeypatch.setattr(robo, "escolher_para_o_video_de_ia", negada)
    assert flow.amostra() == 1
    monkeypatch.setattr(robo, "escolher_para_o_video_de_ia",
                        lambda agora=None, fora=(), amostra=False, longo=False: (None, "os produtos em alta da Shopee",
                                                                               False))
    assert flow.amostra() == 1
    saida = capsys.readouterr().out
    assert "negou a lista de produtos (código 10.000)" in saida and "nenhum produto da lista serviu" in saida
    assert celular.toques == [] and celular.geracoes == 0 and celular.mandados == []


def test_os_gerar_do_dia_passam_de_um_andamento_ao_outro(monkeypatch, tmp_path):
    # O limite de vídeos de IA do dia (P243) conta o do robô e os do Preparar 1 Agora ⚡: cada Gerar soma uma vez, e a
    # conta passa ao andamento seguinte do mesmo dia; o do botão guarda se o do robô já tinha saído.
    monkeypatch.setattr(flow, "PASTA", str(tmp_path))
    # No servidor a tabela já existe (o bot_mestre cria).
    with db.conexao() as con:
        con.execute("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    flow.recomecar_producao("2026-10-22", estado="escolhido", item="1")
    assert flow.gerados_no_dia("2026-10-22") == 0
    flow._marcar_a_producao(estado="gerando", gerado_em="2026-10-22 08:00:00")
    assert flow.gerados_no_dia("2026-10-22") == 1
    # O mesmo Gerar anotado de novo não conta duas vezes.
    flow._marcar_a_producao(gerado_em="2026-10-22 08:00:05")
    assert flow.gerados_no_dia("2026-10-22") == 1
    flow.guardar_producao(estado="usado")
    flow.recomecar_producao("2026-10-22", estado="escolhido", item="2", do_botao=True)
    atual = flow.producao()
    assert atual["do_botao"] is True and atual["do_robo_fechado"] is True
    assert flow.gerados_no_dia("2026-10-22") == 1 and flow.o_do_robo_saiu("2026-10-22")
    flow._marcar_a_producao(estado="gerando", gerado_em="2026-10-22 15:00:00")
    assert flow.gerados_no_dia("2026-10-22") == 2
    # Outro dia, outra conta, e o do robô ainda não saiu nele.
    assert flow.gerados_no_dia("2026-10-23") == 0 and not flow.o_do_robo_saiu("2026-10-23")
    flow.recomecar_producao("2026-10-23", estado="escolhido", item="3")
    assert flow.gerados_no_dia("2026-10-23") == 0 and flow.producao().get("do_botao") is None


# --- O vídeo de IA de 16 s com uma pessoa vendendo o produto (P246 1) ---

CONTINUACAO = "She keeps talking while using the exact tumbler, shows it keeps ice and ends with a call to buy."


def _escolha_longa(monkeypatch):
    """A escolha do robô de mentira para a amostra de 16 s: o pedido com a continuação do Estender e a fala."""
    import robo_shopee_video as robo
    pedidos = []

    def escolher(agora=None, fora=(), amostra=False, longo=False):
        pedidos.append((list(fora), amostra, longo))
        item = str(455 + len(pedidos))
        return ({"id": "ia:2026-11-16", "link": f"https://s.shopee.com.br/curto{item}", "nome": "Copo Térmico Inox",
                 "foto": _jpeg(), "estilo": flow.ESTILO_DO_VENDEDOR,
                 "prompt": "A woman holds the exact tumbler and says the hook.", "continuacao": CONTINUACAO,
                 "fala": "Gelo que dura o dia todo? Olha esse copo! Garanta já o seu!",
                 "cena": "Uma moça vende o copo na cozinha.", "item": item, "valor": 6.5, "posicao": 1,
                 "origem": "os produtos em alta da Shopee"}, "os produtos em alta da Shopee", True)

    monkeypatch.setattr(robo, "escolher_para_o_video_de_ia", escolher)
    return pedidos


def _duracoes(monkeypatch, celular, estendida):
    """A duração de cada vídeo baixado (a versão estendida com `estendida` s, a original com 8) e o juntar falso."""
    juntados = []

    def duracao(caminho, timeout=30):
        if juntados and caminho == juntados[-1][1]:
            return 16.0
        return float(estendida) if celular.baixadas and celular.baixadas[-1] == 1 else 8.0

    def juntar(partes, destino, espera=300):
        juntados.append(([p.rsplit(".", 2)[-2] for p in partes], destino))
        with open(destino, "wb") as arquivo:
            arquivo.write(b"\0" * 4096)
        return ""

    monkeypatch.setattr(flow.videos, "duracao", duracao)
    monkeypatch.setattr(flow.videos, "juntar", juntar)
    return juntados


def test_amostra_de_16_s_gera_estende_baixa_a_versao_estendida_e_vai_so_ao_privado(celular, monkeypatch, capsys):
    # Escolha do Rafael (16/11, P246 1): os vídeos de IA estavam "fracos e sem graça, além de curtos"; a amostra do
    # formato novo tem 16 s, os 8 s gerados pela foto e mais 8 s do Estender, com uma pessoa vendendo o produto.
    pedidos = _escolha_longa(monkeypatch)
    juntados = _duracoes(monkeypatch, celular, estendida=16)
    estilos = flow.estilos_recentes()
    assert flow.main(["amostra", "--longa"]) == 0
    assert pedidos == [([], True, True)]
    # Um Gerar para os 8 s e um para o Estender, com a continuação escrita no painel; o botão da duração nunca é tocado.
    assert celular.geracoes == 1 and celular.extensoes == 1 and celular.texto_estendido == CONTINUACAO
    assert celular.toques_proibidos == [] and celular.baixadas == [1] and juntados == []
    (caminho, legenda), = celular.mandados
    assert caminho.endswith("amostra.mp4")
    for trecho in ("Amostra nº 1 do vídeo de IA de 16 s", "48 créditos de IA: 24 dos 8 s gerados e 24 do Estender",
                   "Gelo que dura o dia todo? Olha esse copo! Garanta já o seu!", "Copo Térmico Inox",
                   "o produto é o mesmo da foto do anúncio", "16 s",
                   "como os vídeos de IA de 16 s estão ficando. O vídeo de IA do dia sai normalmente"):
        assert trecho in legenda, trecho
    atual = flow.amostra_guardada()
    assert atual["estado"] == "enviado" and atual["custo"] == 48 and atual["duracao"] == 16 and atual["longa"]
    # O jeito do vídeo de 16 s fica fora da variação dos estilos dos vídeos de 8 s.
    assert flow.estilos_recentes() == estilos
    saida = capsys.readouterr().out
    for trecho in ("Gerar dos 8 s tocado (Omni 1.2 Flash, 24 créditos)", "Gerar do Estender tocado (8 s, 24 créditos)",
                   "versão estendida pronta", "vídeo de 16 s baixado"):
        assert trecho in saida, trecho
    for privado in ("Copo", "tumbler", "Gelo", "shopee.com.br", "6,50"):
        assert privado not in saida, privado


def test_amostra_de_16_s_com_so_a_continuacao_baixa_a_original_e_junta_as_duas(celular, monkeypatch, capsys):
    # A versão estendida que o Flow baixa com menos de 12 s é só a continuação: a original vem também, e as duas são
    # juntadas no servidor, a original primeiro.
    _escolha_longa(monkeypatch)
    juntados = _duracoes(monkeypatch, celular, estendida=8)
    assert flow.main(["amostra", "--longa"]) == 0
    assert celular.baixadas == [1, 0]
    (partes, destino), = juntados
    assert partes == ["original", "continuacao"] and destino.endswith("amostra.mp4")
    assert flow.amostra_guardada()["duracao"] == 16
    assert "a original e a continuação foram juntadas" in capsys.readouterr().out
    assert [n for n in __import__("os").listdir(flow.PASTA) if "continuacao" in n or "original" in n] == []


def test_baixar_que_traz_a_mesma_versao_duas_vezes_nao_junta(celular, monkeypatch):
    # Se o Baixar do menu trouxesse sempre a mesma versão, a "continuação" curta seria a própria original: o robô
    # para em vez de mandar um vídeo com a original repetida.
    _escolha_longa(monkeypatch)
    juntados = _duracoes(monkeypatch, celular, estendida=8)
    monkeypatch.setattr(flow.videos, "calcular_hash_video", lambda caminho: "mesmo")
    assert flow.main(["amostra", "--longa"]) == 1
    assert juntados == [] and celular.mandados == [] and flow.amostra_guardada()["estado"] == "estendendo"
    assert celular.guardados[-1] == ("parou", "juntar as duas partes: o Baixar trouxe a mesma versão duas vezes")


def test_estender_so_gera_com_tudo_conferido_e_continua_de_onde_parou(celular, monkeypatch, capsys):
    _escolha_longa(monkeypatch)
    _duracoes(monkeypatch, celular, estendida=16)
    # O painel com outra duração: o robô não toca no Gerar do Estender, e os 8 s já gerados ficam esperando.
    celular.rotulo_da_duracao = "Estender 10s"
    assert flow.main(["amostra", "--longa"]) == 1
    assert celular.geracoes == 1 and celular.extensoes == 0
    assert flow.amostra_guardada()["estado"] == "gerando" and celular.mandados == []
    assert "antes do Gerar do Estender: a duração não é a de 8 s" in capsys.readouterr().out
    # A próxima vez não gera os 8 s de novo: só estende. A versão estendida que não fica pronta a tempo é baixada na
    # vez seguinte, sem outro Gerar nem outro Estender.
    celular.rotulo_da_duracao, celular.texto_do_estender = "Estender 8s", ""
    celular.leituras_ao_estender = 10 ** 6
    monkeypatch.setattr(flow, "ESPERA_DA_GERACAO", 0.3)
    assert flow.main(["amostra", "--longa"]) == 1
    assert celular.geracoes == 1 and celular.extensoes == 1 and flow.amostra_guardada()["estado"] == "estendendo"
    assert "já gerada; falta estender, baixar e mandar" in capsys.readouterr().out
    celular.estendendo_leituras = 0
    monkeypatch.setattr(flow, "ESPERA_DA_GERACAO", 30)
    assert flow.main(["amostra", "--longa"]) == 0
    assert celular.geracoes == 1 and celular.extensoes == 1 and len(celular.mandados) == 1
    assert "já estendida; falta baixar e mandar" in capsys.readouterr().out


def test_video_que_ja_tem_a_versao_estendida_nao_e_estendido_de_novo(celular, monkeypatch):
    # A vez que caiu logo depois do Gerar do Estender, antes de anotar: o vídeo já tem a 2ª versão, e o robô segue
    # para baixar sem tocar no Estender outra vez.
    _escolha_longa(monkeypatch)
    _duracoes(monkeypatch, celular, estendida=16)
    celular.versoes = ["Omni 1.2 Flash", ""]
    assert flow.main(["amostra", "--longa"]) == 0
    assert celular.geracoes == 1 and celular.extensoes == 0 and len(celular.mandados) == 1


def test_estender_so_sai_do_video_com_a_continuacao_a_vista(celular, monkeypatch, capsys):
    # Visto no 1º vídeo de IA de 16 s da produção (17/11): o Flow fechado logo depois do Gerar do Estender, antes de
    # mostrar a continuação sendo gerada, a perdeu, e o vídeo ficou com uma versão só. O robô só sai do vídeo (o Flow
    # é aberto de novo, do zero) com a continuação à vista, e o vídeo de 16 s sai na mesma vez.
    _escolha_longa(monkeypatch)
    _duracoes(monkeypatch, celular, estendida=16)
    celular.atraso_da_continuacao = 3
    assert flow.main(["amostra", "--longa"]) == 0
    assert not celular.continuacao_perdida and celular.extensoes == 1 and len(celular.mandados) == 1
    assert flow.amostra_guardada()["duracao"] == 16
    assert "Flow: a continuação está sendo gerada" in capsys.readouterr().out


def test_continuacao_que_nao_aparece_para_e_a_vez_seguinte_nao_estende_de_novo(celular, monkeypatch, capsys):
    # Sem a continuação à vista depois do Gerar do Estender, a vez para ali, já anotada como "estendendo" (o crédito
    # pode ter ido): a seguinte nunca toca no Estender de novo. Com o vídeo de uma versão só e nada sendo gerado no
    # projeto, ela acaba em ESPERA_SEM_CONTINUACAO, sem esperar a ESPERA_DA_GERACAO inteira, e anota o porquê.
    _escolha_longa(monkeypatch)
    _duracoes(monkeypatch, celular, estendida=16)
    celular.atraso_da_continuacao = 10 ** 6
    assert flow.main(["amostra", "--longa"]) == 1
    assert flow.amostra_guardada()["estado"] == "estendendo" and celular.extensoes == 1
    assert celular.guardados[-1] == ("parou", "estender: a continuação não apareceu sendo gerada no vídeo")
    capsys.readouterr()
    monkeypatch.setattr(flow, "ESPERA_DA_GERACAO", 600)
    inicio = flow.time.monotonic()
    assert flow.main(["amostra", "--longa"]) == 1
    assert flow.time.monotonic() - inicio < 60
    assert celular.continuacao_perdida and celular.extensoes == 1 and celular.mandados == []
    atual = flow.amostra_guardada()
    assert atual["estado"] == "estendendo" and atual["espera"] == flow.SEM_CONTINUACAO
    assert "a versão estendida não ficou pronta (a continuação não veio)" in capsys.readouterr().out


class _Tela:
    """Um celular de mentira que mostra sempre a mesma tela."""

    def __init__(self, *nos):
        self.xml = "<hierarchy>" + "".join(nos) + "</hierarchy>"

    def dump_hierarchy(self):
        return self.xml


def test_espera_da_extensao_diz_por_que_acabou(monkeypatch):
    # O quadro mais novo de uma versão só e nada sendo gerado (a tela do projeto em 17/11, com a foto do anúncio no
    # quadro ao lado): a continuação não vem. Com o "Gerando…" na tela, a espera vai até a ESPERA_DA_GERACAO.
    monkeypatch.setattr(flow.time, "sleep", lambda segundos: None)
    monkeypatch.setattr(flow, "ESPERA_SEM_CONTINUACAO", 0.05)
    monkeypatch.setattr(flow, "ESPERA_DA_GERACAO", 0.3)
    uma = _no((0, 466, 537, 1422), desc="Mulher usando o copo, 1 item")
    duas = _no((0, 466, 537, 1422), desc="Mulher usando o copo, 2 itens")
    gerando = _no((0, 466, 537, 1422), desc="1%\nGerando…", clicavel=False)
    foto = _no((543, 466, 1080, 1004), desc="Copo na mesa, 1 item")
    assert flow.esperar_a_extensao(_Tela(uma, foto), guardar_telas=False) == (None, flow.SEM_CONTINUACAO)
    assert flow.esperar_a_extensao(_Tela(gerando, uma, foto), guardar_telas=False) == (None, flow.ESPERA_DA_EXTENSAO)
    segundos, porque = flow.esperar_a_extensao(_Tela(duas, foto), guardar_telas=False)
    assert segundos is not None and porque == ""


def test_leitura_do_painel_do_estender():
    painel = ('<hierarchy>' + _no((0, 152, 1080, 1096), desc="1 de 1")
              + _no((45, 1319, 1035, 1445), "android.widget.EditText", texto=CONTINUACAO)
              + _no((620, 1445, 867, 1571), "android.widget.Button", "Estender 8s")
              + _no((888, 1445, 1014, 1571), "android.widget.Button", "Gerar", clicavel=False) + '</hierarchy>')
    lido = flow.painel_do_estender(painel)
    assert lido["caixa"] == (540, 1382) and lido["duracao"] == "Estender 8s" and lido["versoes"] == (1, 1)
    assert lido["gerar"] == (951, 1508) and lido["gerar_ligado"] is True
    assert flow.pronto_para_estender(painel, CONTINUACAO) == ""
    assert flow.pronto_para_estender(painel, "Other text") == "o texto da continuação não entrou"
    assert flow.pronto_para_estender(painel.replace("1 de 1", "1 de 2"), CONTINUACAO) == \
        "o vídeo de cima não é o de uma versão só"
    assert flow.pronto_para_estender(painel.replace('enabled="true" visible-to-user="true" bounds="[888',
                                                    'enabled="false" visible-to-user="true" bounds="[888'),
                                     CONTINUACAO) == "o Gerar está desligado"
    # O pedido do Criar (sem o botão da duração) e o vídeo aberto não são o painel do Estender.
    assert flow.painel_do_estender(painel.replace("Estender 8s", "Omni 1.2 Flash\nx1")) is None


def test_resposta_e_pedido_do_video_de_16_s(monkeypatch):
    resposta = ('{"serve": true, "muda_na_ia": false, "motivo": "", "prompt": "Part one.", "continuacao": "Part two.", '
                '"fala": "Gancho! Vantagens. Garanta já o seu!", "cena": "Uma moça vende o copo."}')
    lida = flow.ler_resposta(resposta, longo=True)
    assert lida["estilo"] == flow.ESTILO_DO_VENDEDOR and lida["continuacao"] == "Part two."
    assert lida["fala"] == "Gancho! Vantagens. Garanta já o seu!"
    # Sem a continuação, o pedido de 16 s não serve; o de 8 s nem olha para ela.
    assert flow.ler_resposta(resposta.replace('"Part two."', '""'), longo=True) is None
    assert "continuacao" not in flow.ler_resposta(resposta)
    pedidos = []

    async def gerar(texto, imagens=None):
        pedidos.append(texto)
        return resposta

    monkeypatch.setattr(flow.api_gemini, "gerar_texto_gemini", gerar)
    pedido, serve = flow.pedido_para_o_anuncio("https://s.shopee.com.br/abc", "Copo Térmico Inox", _jpeg(), longo=True)
    assert serve is True and pedido["continuacao"] == "Part two." and pedido["fala"].startswith("Gancho")
    for trecho in ("16 segundos", "continuacao", "gancho", "Garanta a sua!", "muda_na_ia", "Copo Térmico Inox"):
        assert trecho in pedidos[-1], trecho
    flow.pedido_para_o_anuncio("https://s.shopee.com.br/abc", "Copo Térmico Inox", _jpeg())
    assert "8 segundos" in pedidos[-1] and "continuacao" not in pedidos[-1]


# --- Contra as alucinações do vídeo de 16 s (P248 1) ---

FALA_DA_1A_AMOSTRA = [(1.8, 2.4, "Cansado"), (2.5, 2.6, "de"), (2.7, 2.9, "comida"), (2.9, 3.5, "grudando"),
                      (3.6, 3.7, "na"), (3.7, 4.2, "panela?"), (6.3, 6.5, "Vou"), (6.5, 7.0, "feitecer"),
                      (7.0, 7.2, "já"), (7.2, 7.4, "essa"), (7.4, 7.9, "sela?"), (11.7, 12.2, "Limpeza"),
                      (12.3, 12.7, "super"), (12.8, 13.0, "fácil"), (13.1, 13.2, "e"), (13.5, 13.7, "nada"),
                      (13.8, 14.3, "gruda!"), (14.8, 15.1, "Aproveite"), (15.2, 15.3, "e"), (15.4, 15.6, "garanta"),
                      (15.6, 15.7, "o"), (15.8, 16.0, "seu...")]


def test_pedido_de_16_s_pede_acoes_simples_no_mesmo_lugar_e_fala_curta():
    # Escolha do Rafael (17/11, P248 1): na 1ª amostra, a tampa ficou grudada na alça, a pessoa foi a outro fogão com
    # uma panqueca do nada e voltou, o rosto mudou, e a fala saiu embolada e cortada. O pedido à IA não manda mais
    # abrir, cozinhar ou mostrar "em uso", deixa os 16 s no mesmo lugar e encurta a fala.
    pedido = flow.PEDIDO_DO_VENDEDOR.format(nome="Jogo de Panelas", evitar="", bebida="")
    for trecho in ("só segura o produto, vira devagar e aponta", "sem abrir, fechar, desmontar", "cozinhar",
                   "no mesmo lugar, com o mesmo fundo e o mesmo enquadramento", "câmera parada", "sem corte",
                   "sem aparecer comida, objeto ou pessoa nova", "o vídeo já começa lá",
                   f"até {flow.PALAVRAS_POR_PARTE} palavras", "terminando antes dos 6 segundos",
                   "palavras simples", "Jogo de Panelas"):
        assert trecho in pedido, trecho
    assert flow.PALAVRAS_POR_PARTE == 10
    assert "em uso" not in pedido and "16 palavras" not in pedido and "celular na mão" not in pedido


def test_conferir_a_fala_acha_a_embolada_e_a_cortada_da_1a_amostra(monkeypatch):
    monkeypatch.setattr(flow.videos, "palavras_faladas", lambda caminho: FALA_DA_1A_AMOSTRA)
    monkeypatch.setattr(flow.videos, "duracao", lambda caminho, timeout=30: 16.04)
    pedida = ("Cansado de comida grudando na panela? Olha só essa panela! Limpeza super fácil e nada gruda. "
              "Aproveite e garanta o seu na Shopee!")
    conferida = flow.conferir_a_fala("amostra.mp4", pedida)
    assert conferida["situacao"] == "embolada e cortada" and conferida["ouvidas"] == 22
    # "já" e "e" são curtas demais para contar como estranhas; "essa" está na fala pedida.
    assert conferida["estranhas"] == ["vou", "feitecer", "sela"] and conferida["aos"] == 6
    assert conferida["faltou"] == ["na", "shopee"]
    linha = flow.texto_da_fala(conferida)
    assert linha.startswith("⚠️ Fala no vídeo: embolada aos 6 s")
    assert '"feitecer", "sela"' in linha and 'cortada no fim (faltou "na shopee")' in linha
    # A fala que termina antes do fim do vídeo, sem o fim da pedida, não é cortada: ela só não disse.
    monkeypatch.setattr(flow.videos, "duracao", lambda caminho, timeout=30: 18.0)
    assert flow.conferir_a_fala("amostra.mp4", pedida)["situacao"] == "embolada"


def test_conferir_a_fala_igual_quase_igual_e_sem_ouvir(monkeypatch):
    pedida = "Comida grudando na panela? Acabou! Nada gruda e limpa fácil. Garanta a sua pra hoje!"
    ouvidas = [(0.5 * i, 0.5 * i + 0.4, palavra) for i, palavra in enumerate(
        "Gente, comida grudando na panela? Acabou! Nada gruda e limpa fácil. Garanta a sua para hoje!".split())]
    monkeypatch.setattr(flow.videos, "palavras_faladas", lambda caminho: ouvidas)
    monkeypatch.setattr(flow.videos, "duracao", lambda caminho, timeout=30: 16.0)
    conferida = flow.conferir_a_fala("amostra.mp4", pedida)
    # "para" no lugar de "pra" conta como a mesma; uma palavra a mais ("gente") não faz a fala embolada.
    assert conferida["situacao"] == "igual" and conferida["estranhas"] == ["gente"] and conferida["faltou"] == []
    assert flow.texto_da_fala(conferida) == ('👂 Fala no vídeo: igual à pedida (16 palavras ouvidas; '
                                             'fora dela só "gente")')
    monkeypatch.setattr(flow.videos, "palavras_faladas", lambda caminho: [])
    assert flow.texto_da_fala(flow.conferir_a_fala("amostra.mp4", pedida)) == "⚠️ Fala no vídeo: nenhuma palavra ouvida"
    monkeypatch.setattr(flow.videos, "palavras_faladas", lambda caminho: None)
    assert flow.conferir_a_fala("amostra.mp4", pedida)["situacao"] is None
    assert flow.texto_da_fala({"situacao": None}) == "👂 Fala no vídeo: não deu para ouvir"
    # Sem a fala pedida, nada é ouvido.
    monkeypatch.setattr(flow.videos, "palavras_faladas", lambda caminho: pytest.fail("sem fala pedida"))
    assert flow.conferir_a_fala("amostra.mp4", "")["situacao"] is None


def test_amostra_de_16_s_de_novo_com_o_mesmo_produto_e_a_fala_conferida(celular, monkeypatch, capsys):
    # Escolha do Rafael (17/11, P248 1): outra amostra de 16 s com o mesmo produto da anterior, para comparar as duas,
    # com o pedido novo da IA; o servidor confere a fala do vídeo pronto e põe o resultado na legenda.
    pedidos = _escolha_longa(monkeypatch)
    _duracoes(monkeypatch, celular, estendida=16)
    assert flow.main(["amostra", "--longa"]) == 0
    assert "Fala no vídeo: não deu para ouvir" in celular.mandados[-1][1]
    anterior = flow.amostra_guardada()
    pedidos_da_ia = []
    resposta = ('{"serve": true, "muda_na_ia": false, "motivo": "", "prompt": "She holds the same tumbler, still.", '
                '"continuacao": "Same shot, she points at the lid.", "fala": "Gelo o dia todo? Olha! Tampa firme. '
                'Garanta o seu!", "cena": "A moça no mesmo balcão."}')

    async def gerar(texto, imagens=None):
        pedidos_da_ia.append((texto, imagens))
        return resposta

    monkeypatch.setattr(flow.api_gemini, "gerar_texto_gemini", gerar)
    ouvidas = [(0.6 * i, 0.6 * i + 0.5, palavra) for i, palavra in enumerate(
        "Gelo o dia todo? Olha! Tampa firme. Garanta o seu!".split())]
    monkeypatch.setattr(flow.videos, "palavras_faladas", lambda caminho: ouvidas)
    # O celular de mentira da vez anterior ficou com o pedido na tela: esta vez começa num limpo.
    novo = Flow()
    monkeypatch.setattr(flow.ps, "conectar", lambda celular=False: novo)
    assert flow.main(["amostra", "--longa", "--mesmo"]) == 0
    # A escolha da lista não roda de novo: a IA escreve o pedido novo para o mesmo anúncio, com as regras de agora.
    assert len(pedidos) == 1 and len(pedidos_da_ia) == 1
    assert "Copo Térmico Inox" in pedidos_da_ia[0][0] and "câmera parada" in pedidos_da_ia[0][0]
    atual = flow.amostra_guardada()
    assert atual["item"] == anterior["item"] and atual["link"] == anterior["link"] and atual["numero"] == 2
    assert atual["mesmo_de"] == 1 and atual["continuacao"] == "Same shot, she points at the lid."
    assert atual["estado"] == "enviado" and atual["fala_conferida"] == "igual"
    assert novo.texto_estendido == "Same shot, she points at the lid." and novo.geracoes == novo.extensoes == 1
    legenda = celular.mandados[-1][1]
    for trecho in ("Amostra nº 2 do vídeo de IA de 16 s", "com o mesmo produto da nº 1 e as mudanças contra as "
                   "alucinações (P248 1)", "Gelo o dia todo? Olha! Tampa firme. Garanta o seu!",
                   "👂 Fala no vídeo: igual à pedida (10 palavras ouvidas)"):
        assert trecho in legenda, trecho
    # O produto não entra duas vezes nas amostras feitas, e a próxima amostra comum continua a conta.
    assert flow.amostras_feitas() == [anterior["item"]]
    saida = capsys.readouterr().out
    assert "Amostra nº 2: o mesmo produto da amostra nº 1" in saida and "fala conferida: igual à pedida" in saida
    for privado in ("Copo", "tumbler", "Gelo", "shopee.com.br", "6,50"):
        assert privado not in saida, privado


def test_amostra_com_o_mesmo_produto_sem_a_anterior_nao_toca_no_celular(celular, monkeypatch, capsys):
    monkeypatch.setattr(flow.api_gemini, "gerar_texto_gemini", lambda *a, **k: pytest.fail("sem a anterior"))
    assert flow.main(["amostra", "--longa", "--mesmo"]) == 1
    assert "sem a amostra anterior ou sem o pedido novo da IA" in capsys.readouterr().out
    assert celular.toques == [] and celular.geracoes == 0 and celular.mandados == []


# --- O vídeo de IA de 16 s vira o padrão da produção (P247 1) ---

FALA_PEDIDA = "Gelo que dura o dia todo? Olha esse copo! Garanta a sua!"


def _escolhido_longo():
    """O pedido de 16 s que a escolha do robô dá desde a P247 1: com a continuação do Estender e a fala."""
    return dict(_escolhido(), estilo=flow.ESTILO_DO_VENDEDOR,
                prompt="A woman holds the exact tumbler and says the hook.", continuacao=CONTINUACAO,
                fala=FALA_PEDIDA, cena="Uma moça vende o copo na cozinha.")


def _ouvir(monkeypatch, texto):
    """O reconhecimento de voz de mentira: as palavras do texto, uma a cada 0,6 s."""
    ouvidas = [(0.6 * i, 0.6 * i + 0.5, palavra) for i, palavra in enumerate(texto.split())]
    monkeypatch.setattr(flow.videos, "palavras_faladas", lambda caminho: ouvidas)
    return ouvidas


def test_producao_de_16_s_gera_estende_baixa_e_ouve_a_fala(celular, monkeypatch, capsys):
    # Escolha do Rafael (17/11, P247 1): o formato da amostra de 16 s, uma pessoa vendendo o produto do começo ao
    # fim, vira o do vídeo de IA do dia e do De IA ✨: os 8 s gerados pela foto e mais 8 s do Estender (24 + 24).
    _duracoes(monkeypatch, celular, estendida=16)
    estilos = flow.estilos_recentes()
    atual = flow.comecar_producao("2026-11-17", _escolhido_longo(), 1)
    assert atual["longa"] is True and atual["continuacao"] == CONTINUACAO and atual["fala"] == FALA_PEDIDA
    assert atual["custo"] == 24 and atual["estilo"] == flow.ESTILO_DO_VENDEDOR
    # O jeito do vídeo de 16 s fica fora da variação dos estilos das amostras de 8 s.
    assert flow.estilos_recentes() == estilos
    assert flow.producao_no_celular(celular, atual) is True
    # Um Gerar para os 8 s e um para o Estender, com a continuação escrita no painel.
    assert celular.geracoes == 1 and celular.extensoes == 1 and celular.texto_estendido == CONTINUACAO
    assert celular.toques_proibidos == [] and celular.baixadas == [1]
    atual = flow.producao()
    assert atual["estado"] == "baixado" and atual["arquivo"].endswith("producao_2026-11-17.mp4")
    assert atual["custo"] == flow.CUSTO_DA_PRODUCAO == 48 and atual["duracao"] == 16
    assert flow.itens_gerados() == ["456"] and flow.gerados_no_dia("2026-11-17") == 1
    # Nenhuma tela do Estender nos casos: todo dia, elas tirariam do servidor os casos das falhas.
    assert not any("Estender" in motivo or "esperando" in motivo for _, motivo in celular.guardados)
    ouvidas = _ouvir(monkeypatch, FALA_PEDIDA)
    assert flow.conferir_a_producao() == "pronto"
    pronto = flow.video_pronto()
    assert pronto["fala_conferida"]["situacao"] == "igual"
    legenda = flow.legenda_da_producao(pronto)
    for trecho in ("Omni 1.2 Flash, 16 s (48 créditos de IA: 24 dos 8 s gerados e 24 do Estender)",
                   "pessoa vendendo o produto", f"🗣️ Fala: {FALA_PEDIDA}", "o produto é o mesmo da foto do anúncio",
                   f"👂 Fala no vídeo: igual à pedida ({len(ouvidas)} palavras ouvidas)"):
        assert trecho in legenda, trecho
    # O vídeo vira rascunho do robô: nada vai ao privado.
    assert celular.mandados == []
    saida = capsys.readouterr().out
    assert "Gerar do Estender tocado (8 s, 24 créditos)" in saida and "vídeo de 16 s baixado" in saida
    for privado in ("Copo", "tumbler", "Gelo"):
        assert privado not in saida, privado


def test_producao_de_16_s_continua_de_onde_parou_sem_outro_gerar(celular, monkeypatch):
    # A rodada que acabou depois do Gerar dos 8 s: a seguinte só estende; a versão estendida que não ficou pronta a
    # tempo é baixada na outra, sem outro Gerar nem outro Estender.
    _duracoes(monkeypatch, celular, estendida=16)
    flow.comecar_producao("2026-11-17", _escolhido_longo(), 1)
    flow._marcar_a_producao(estado="gerando", gerado_em="2026-11-17 08:00:00", custo=24)
    celular.gerado, celular.modelo_do_video = True, "Omni 1.2 Flash"
    celular.leituras_ao_estender = 10 ** 6
    monkeypatch.setattr(flow, "ESPERA_DA_GERACAO", 0.3)
    assert flow.producao_no_celular(celular, flow.producao()) is False
    atual = flow.producao()
    assert celular.geracoes == 0 and celular.extensoes == 1
    assert atual["estado"] == "estendendo" and atual["custo"] == 48 and atual["estendido_em"]
    assert "estendendo" in flow.ESTADOS_PENDENTES
    celular.estendendo_leituras = 0
    monkeypatch.setattr(flow, "ESPERA_DA_GERACAO", 30)
    assert flow.producao_no_celular(celular, flow.producao()) is True
    assert celular.geracoes == 0 and celular.extensoes == 1 and flow.producao()["estado"] == "baixado"
    # O Estender não é um Gerar a mais no dia (o limite do P243 conta os vídeos).
    assert flow.gerados_no_dia("2026-11-17") == 1


def test_producao_com_a_fala_embolada_vira_rascunho_com_o_aviso(celular, monkeypatch):
    # P248 1 (D): a fala embolada ou cortada não descarta o vídeo; o aviso vai no rascunho, e o Rafael decide na
    # aprovação.
    _duracoes(monkeypatch, celular, estendida=16)
    flow.comecar_producao("2026-11-17", _escolhido_longo(), 1)
    assert flow.producao_no_celular(celular, flow.producao()) is True
    _ouvir(monkeypatch, "Gelo que dura o dia todo? Vou feitecer esse sela! Garanta a sua!")
    assert flow.conferir_a_producao() == "pronto"
    pronto = flow.video_pronto()
    assert pronto["fala_conferida"]["situacao"] == "embolada"
    assert '⚠️ Fala no vídeo: embolada aos 4 s (ouvi "vou", "feitecer", "sela"' in flow.legenda_da_producao(pronto)


def test_producao_de_8_s_de_antes_da_p247_continua_pelo_caminho_de_8_s(celular):
    # O andamento de 8 s que estava gerando na hora do deploy é baixado como era, sem Estender.
    flow.comecar_producao("2026-11-16", _escolhido(), 1)
    flow.guardar_producao(estado="gerando", gerado_em="2026-11-16 08:00:00")
    assert "longa" not in flow.producao()
    celular.gerado, celular.modelo_do_video = True, "Omni 1.2 Flash"
    assert flow.producao_no_celular(celular, flow.producao()) is True
    assert celular.geracoes == 0 and celular.extensoes == 0 and flow.producao()["estado"] == "baixado"
    # Sem a fala pedida, o servidor não ouve nada: o de 8 s fica como sempre foi.
    assert flow.conferir_a_producao() == "pronto" and "fala_conferida" not in flow.producao()
    assert "Omni 1.2 Flash (24 créditos de IA)" in flow.legenda_da_producao(flow.producao())
