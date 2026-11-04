# Mudar de servidor

O passo a passo para levar os robôs do servidor de agora para um servidor novo, do jeito
que estão rodando: os dados, as filas, os logins das contas do Telegram, as chaves, o
pareamento do celular do robô, os vídeos e prints dos rascunhos que esperam a aprovação e as
tarefas do crontab do servidor.
Pedido do Rafael (P147 1); o que cada parte faz está no `mudar_servidor.py`.

## Antes da mudança (só o Rafael faz)

1. **Criar o servidor novo.** Na Oracle Cloud: Compute → Instances → Create instance.
   - Imagem: Ubuntu, a mesma versão do servidor de agora (o `conferir` mostra qual é).
   - O usuário tem de ser `ubuntu`, com sudo sem senha. É o padrão da Oracle.
   - Chave SSH: "Generate a key pair for me" e baixar a chave privada (o arquivo `.key`).
   - Anotar o endereço IP público.
   - A cota grátis de ARM da Oracle é de 4 núcleos e 24 GB no total, e o servidor de agora
     já usa toda ela: um segundo servidor ARM grátis só cabe em outra conta, ou o novo é pago.
2. **Pôr o servidor novo no GitHub.** Em rafaelnm90/shopee → Settings → Secrets and
   variables → Actions → New repository secret, criar três segredos:
   - `NOVO_HOST`: o IP público do servidor novo;
   - `NOVO_USER`: `ubuntu`;
   - `NOVO_SSH_KEY`: o conteúdo inteiro da chave privada (abrir o `.key` num editor de texto e
     copiar tudo, da linha `-----BEGIN` até a `-----END`).
3. **Avisar o Claude.**

## A mudança (o Claude faz, pelo workflow "Mudar de servidor")

1. `conferir`: só lê os dois servidores (o sistema, o disco, o que está instalado). Nada muda.
2. `preparar`: instala no servidor novo o sistema, o código e os robôs, ainda desligados.
   Leva uns 15 minutos. Os robôs continuam trabalhando no servidor de agora.
3. `mudar` (numa hora combinada com o Rafael, porque os robôs ficam parados uns 10 a 20
   minutos): para os robôs do servidor de agora, leva tudo para o novo e liga os robôs lá.
   Se o novo não subir, os robôs voltam sozinhos ao servidor de agora.
   - A rodada do robô da Shopee Vídeo que estiver tocando no celular termina antes.
   - Os dois servidores nunca ficam ligados juntos: o mesmo bot em dois lugares atrapalha.
   - No servidor antigo, a pasta do projeto fica guardada de lado (`~/shopee.antes_da_mudanca`),
     para nenhum deploy ou workflow religar os robôs lá. As tarefas do crontab também
     (`~/crontab.antes_da_mudanca`): passam a rodar só no novo.

## Logo depois da mudança (só o Rafael faz)

1. **Trocar os segredos.** No GitHub, em Secrets and variables → Actions, trocar o valor de
   `ORACLE_HOST`, `ORACLE_USER` e `ORACLE_SSH_KEY` pelos do servidor novo (os mesmos dos `NOVO_*`)
   e depois apagar os três `NOVO_*`. Até a troca, o deploy, o diagnóstico e o checkup ainda vão ao
   servidor antigo e falham de propósito.
2. **Tailscale (a rede privada do celular do robô).** A chave do segredo `TAILSCALE_AUTHKEY` vence
   (vale até 90 dias). Se o `preparar` disser que a rede não ligou, gerar outra em
   login.tailscale.com → Settings → Keys → Generate auth key, trocar o segredo e avisar o Claude.
3. **Celular do robô.** Nada a fazer: o pareamento vai junto. Se o bot pedir para parear, é pelo
   caminho de sempre (Outros Canais → Shopee Vídeo 🎬 → Celular do Robô 📱).
4. **O servidor antigo.** Deixar parado (Stop) uns dias e só depois apagar (Terminate).

## Voltar atrás

Antes de trocar os segredos, o `voltar` desliga o servidor novo e religa o de agora, com a pasta
de volta ao lugar.

## Se o servidor de agora sumir de repente

O `mudar` precisa dos dois servidores ligados. Se o de agora se perder (disco, conta), os dados
estão na cópia cifrada do backup que o bot manda todo dia no privado do Rafael, e ela só abre
com a senha que ele guardou fora do Telegram (onde ela está aparece na legenda da própria
cópia). Nesse caso: criar o servidor novo e os segredos `NOVO_*` como acima e avisar o Claude,
que roda o `preparar` e combina com o Rafael como levar a cópia até lá
(`python3 backup_dados.py abrir ARQUIVO PASTA`).
