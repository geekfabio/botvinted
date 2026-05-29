# 🤖 Vinted Alert Bot 
 
Bot de monitorização da Vinted com notificações automáticas via Telegram. Suporta **pesquisas completamente customizáveis** — iPhones, consolas, roupa, qualquer categoria — com filtros de preço, condição e rating do vendedor. 
 
--- 
 
## Índice 
 
- [Funcionalidades](#funcionalidades) 
- [Pré-requisitos](#pré-requisitos) 
- [Instalação no VPS Linux](#instalação-no-vps-linux) 
- [Configuração do Bot Telegram](#configuração-do-bot-telegram) 
- [Ficheiro de Configuração](#ficheiro-de-configuração-configyaml) 
- [Estrutura do Projecto](#estrutura-do-projecto) 
- [Como Correr](#como-correr) 
- [Correr como Serviço (systemd)](#correr-como-serviço-systemd) 
- [Exemplos de Pesquisas](#exemplos-de-pesquisas) 
- [Formato das Notificações](#formato-das-notificações) 
- [Troubleshooting](#troubleshooting) 
- [FAQ](#faq) 
 
--- 
 
## Funcionalidades 
 
- **Pesquisas customizadas** — qualquer termo de pesquisa, não só iPhones 
- **Filtros por preço** — define mínimo e máximo por pesquisa 
- **Filtro de vendedor** — mínimo de estrelas e número de avaliações configurável 
- **Filtro de condição** — novo, como novo, bom estado, etc. 
- **Deduplicação** — nunca recebes a mesma listagem duas vezes 
- **Paginação automática** — percorre todas as páginas de resultados 
- **Notificações ricas** — foto, preço, estado, localização, link directo 
- **Múltiplos destinos** — envia para o teu chat pessoal e/ou grupos 
- **Agendamento configurável** — de 5 em 5 minutos a de hora em hora 
- **Logging completo** — registo de todas as actividades em ficheiro 
 
--- 
 
## Pré-requisitos 
 
- VPS com Ubuntu 20.04+ (ou Debian 11+) 
- Python 3.11 ou superior 
- Acesso root ou utilizador com `sudo` 
- Conta Telegram 
 
--- 
 
## Instalação no VPS Linux 
 
### 1. Ligar ao VPS e actualizar o sistema 
 
```bash 
ssh user@IP_DO_SEU_VPS 
 
sudo apt update && sudo apt upgrade -y 
sudo apt install -y python3.11 python3.11-venv python3-pip git 
``` 
 
### 2. Clonar o projecto 
 
```bash 
cd /opt 
sudo git clone https://github.com/SEU_UTILIZADOR/vinted-bot.git 
sudo chown -R $USER:$USER /opt/vinted-bot 
cd /opt/vinted-bot 
``` 
 
### 3. Criar ambiente virtual e instalar dependências 
 
```bash 
python3.11 -m venv venv 
source venv/bin/activate 
 
pip install --upgrade pip 
pip install -r requirements.txt 
``` 
 
### 4. Criar o ficheiro de ambiente 
 
```bash 
cp .env.example .env 
nano .env 
``` 
 
Preenche com o teu token do Telegram (ver secção seguinte): 
 
```env 
TELEGRAM_TOKEN=1234567890:AABBCCDDEEFFaabbccddeeff-xxxxxxxxxx 
``` 
 
### 5. Copiar e editar a configuração 
 
```bash 
cp config.example.yaml config.yaml 
nano config.yaml 
``` 
 
--- 
 
## Configuração do Bot Telegram 
 
### Passo 1 — Criar o bot 
 
1. Abre o Telegram e pesquisa por `@BotFather` 
2. Envia `/newbot` 
3. Escolhe um nome (ex: `Vinted Monitor`) 
4. Escolhe um username único terminado em `bot` (ex: `meu_vinted_alert_bot`) 
5. Copia o **token** que o BotFather te dá → vai para o `.env` 
 
### Passo 2 — Obter o teu Chat ID 
 
1. Pesquisa por `@userinfobot` no Telegram 
2. Envia `/start` 
3. Copia o número do **Id** → vai para o `config.yaml` 
 
### Passo 3 — Iniciar conversa com o bot 
 
Pesquisa pelo username do teu bot no Telegram e envia `/start`. O bot precisa de ter uma conversa iniciada contigo para poder enviar mensagens. 
 
### (Opcional) Enviar para um grupo 
 
1. Adiciona o teu bot ao grupo 
2. Envia uma mensagem no grupo 
3. Acede a `https://api.telegram.org/botTEU_TOKEN/getUpdates` 
4. Encontra o `"chat": {"id": -XXXXXXXXX}` — os IDs de grupo são negativos 
 
--- 
 
## Ficheiro de Configuração (`config.yaml`) 
 
```yaml 
# ───────────────────────────────────────────── 
# Telegram 
# ───────────────────────────────────────────── 
telegram: 
  token: "${TELEGRAM_TOKEN}"       # lido do .env — não colocar aqui directamente 
  destinations: 
    - chat_id: "123456789"         # o teu chat pessoal 
      label: "Pessoal" 
    # - chat_id: "-987654321"      # (opcional) grupo 
    #   label: "Grupo Família" 
 
# ───────────────────────────────────────────── 
# Agendamento 
# ───────────────────────────────────────────── 
scheduler: 
  interval_minutes: 30             # intervalo entre verificações (mín. 10 recomendado) 
 
# ───────────────────────────────────────────── 
# Filtros globais (aplicados a todas as pesquisas) 
# ───────────────────────────────────────────── 
global_filters: 
  seller_min_stars: 3              # estrelas mínimas do vendedor (0–5) 
  seller_min_reviews: 3            # nº mínimo de avaliações do vendedor 
  exclude_keywords:                # ignora listagens com estas palavras no título 
    - "avariado" 
    - "para peças" 
    - "partido" 
 
# ───────────────────────────────────────────── 
# Pesquisas — adiciona quantas quiseres! 
# ───────────────────────────────────────────── 
searches: 
 
  # ── iPhones ────────────────────────────── 
  - name: "iPhone 11" 
    query: "iphone 11" 
    price_min: 80 
    price_max: 200 
    condition: []                  # [] = todos; ou: ["new","like_new","good","satisfactory"] 
 
  - name: "iPhone 12 / Pro / Max" 
    query: "iphone 12" 
    price_min: 130 
    price_max: 320 
    condition: ["new", "like_new"] 
 
  - name: "iPhone 13 série" 
    query: "iphone 13" 
    price_min: 200 
    price_max: 450 
 
  - name: "iPhone 14 Pro" 
    query: "iphone 14 pro" 
    price_min: 350 
    price_max: 700 
 
  - name: "iPhone 15 Pro Max" 
    query: "iphone 15 pro max" 
    price_min: 700 
    price_max: 1100 
 
  - name: "iPhone 16 Pro Max" 
    query: "iphone 16 pro max" 
    price_min: 900 
    price_max: 1400 
 
  - name: "iPhone 17 Pro / Pro Max" 
    query: "iphone 17 pro" 
    price_min: 1000 
    price_max: 1600 
 
  # ── Pesquisas customizadas ───────────────── 
  - name: "AirPods Pro 2" 
    query: "airpods pro 2" 
    price_min: 80 
    price_max: 200 
 
  - name: "PlayStation 5" 
    query: "ps5 playstation 5" 
    price_min: 200 
    price_max: 450 
    condition: ["new", "like_new", "good"] 
 
  - name: "MacBook Air M2" 
    query: "macbook air m2" 
    price_min: 600 
    price_max: 1200 
 
  - name: "Nike Air Force 1 42" 
    query: "nike air force 1 42" 
    price_min: 20 
    price_max: 80 
 
  # Pesquisa de texto livre — sem limite de preço máximo 
  - name: "Lego Technic" 
    query: "lego technic" 
    price_min: 10 
    price_max: null                # null = sem limite máximo 
    condition: ["new", "like_new"] 
 
# ───────────────────────────────────────────── 
# Scraping 
# ───────────────────────────────────────────── 
scraping: 
  delay_between_requests: 2       # segundos entre pedidos (não reduzir abaixo de 1) 
  max_pages_per_search: 5         # páginas máximas por pesquisa (96 itens/página) 
  results_per_page: 96 
  country: "pt"                   # pt, es, fr, de, it, etc. 
  currency: "EUR" 
 
# ───────────────────────────────────────────── 
# Base de dados 
# ───────────────────────────────────────────── 
database: 
  path: "data/seen_items.db"      # SQLite — guarda IDs já notificados 
 
# ───────────────────────────────────────────── 
# Logging 
# ───────────────────────────────────────────── 
logging: 
  level: "INFO"                   # DEBUG, INFO, WARNING, ERROR 
  file: "logs/bot.log" 
  max_size_mb: 10 
  backup_count: 3 
``` 
 
--- 
 
## Estrutura do Projecto 
 
``` 
vinted-bot/ 
│ 
├── bot.py                  # Entry point — inicia o scheduler 
├── scraper.py              # Comunicação com a API da Vinted 
├── filters.py              # Lógica de filtros (preço, vendedor, condição, keywords) 
├── notifier.py             # Envio de mensagens via Telegram 
├── db.py                   # SQLite — deduplicação de IDs 
├── config_loader.py        # Lê e valida config.yaml + .env 
│ 
├── config.yaml             # ← Edita este ficheiro com as tuas pesquisas 
├── config.example.yaml     # Exemplo de configuração (não editar) 
├── .env                    # Token do Telegram (nunca commitar no git!) 
├── .env.example            # Exemplo de .env 
├── .gitignore 
│ 
├── requirements.txt 
├── README.md 
│ 
├── data/ 
│   └── seen_items.db       # Base de dados SQLite (criada automaticamente) 
│ 
├── logs/ 
│   └── bot.log             # Logs de execução (criado automaticamente) 
│ 
└── tests/ 
    ├── test_filters.py 
    └── test_scraper.py 
``` 
 
--- 
 
## Como Correr 
 
### Execução manual (teste) 
 
```bash 
cd /opt/vinted-bot 
source venv/bin/activate 
 
# Correr uma vez (sem agendamento) — útil para testar 
python bot.py --once 
 
# Correr com agendamento 
python bot.py 
 
# Ver logs em tempo real 
tail -f logs/bot.log 
``` 
 
### Flags disponíveis 
 
```bash 
python bot.py --once              # executa uma vez e termina 
python bot.py --dry-run           # executa mas não envia para o Telegram 
python bot.py --search "iphone"   # corre apenas a pesquisa com este nome 
python bot.py --debug             # logging detalhado no terminal 
``` 
 
--- 
 
## Correr como Serviço (systemd) 
 
Para que o bot inicie automaticamente com o VPS e reinicie em caso de erro: 
 
### 1. Criar o ficheiro de serviço 
 
```bash 
sudo nano /etc/systemd/system/vinted-bot.service 
``` 
 
```ini 
[Unit] 
Description=Vinted Alert Bot 
After=network.target 
Wants=network-online.target 
 
[Service] 
Type=simple 
User=ubuntu                          # substitui pelo teu utilizador 
WorkingDirectory=/opt/vinted-bot 
ExecStart=/opt/vinted-bot/venv/bin/python bot.py 
Restart=always 
RestartSec=30 
StandardOutput=journal 
StandardError=journal 
 
# Variáveis de ambiente 
EnvironmentFile=/opt/vinted-bot/.env 
 
[Install] 
WantedBy=multi-user.target 
``` 
 
### 2. Activar e iniciar 
 
```bash 
sudo systemctl daemon-reload 
sudo systemctl enable vinted-bot 
sudo systemctl start vinted-bot 
``` 
 
### 3. Verificar estado 
 
```bash 
sudo systemctl status vinted-bot 
 
# Ver logs do serviço 
sudo journalctl -u vinted-bot -f 
 
# Ver últimas 100 linhas 
sudo journalctl -u vinted-bot -n 100 
``` 
 
### Comandos úteis 
 
```bash 
sudo systemctl stop vinted-bot       # parar 
sudo systemctl restart vinted-bot    # reiniciar (após alterar config.yaml) 
sudo systemctl disable vinted-bot    # desactivar início automático 
``` 
 
--- 
 
## Exemplos de Pesquisas 
 
O bot não está limitado a iPhones. Aqui ficam exemplos para o `config.yaml`: 
 
```yaml 
searches: 
  # Electrónica 
  - name: "Samsung Galaxy S24" 
    query: "samsung galaxy s24" 
    price_min: 300 
    price_max: 700 
 
  - name: "iPad Pro M4" 
    query: "ipad pro m4" 
    price_min: 500 
    price_max: 1000 
 
  # Roupa / Moda 
  - name: "Jacket Stone Island L" 
    query: "stone island jacket size L" 
    price_min: 50 
    price_max: 250 
 
  - name: "Adidas Samba 44" 
    query: "adidas samba 44" 
    price_min: 30 
    price_max: 100 
 
  # Coleccionáveis / Jogos 
  - name: "Nintendo Switch OLED" 
    query: "nintendo switch oled" 
    price_min: 150 
    price_max: 300 
    condition: ["new", "like_new"] 
 
  - name: "Câmara Sony A7" 
    query: "sony a7 camera" 
    price_min: 400 
    price_max: 900 
 
  # Livros / Outros 
  - name: "Livros de programação" 
    query: "clean code programming" 
    price_min: 3 
    price_max: 20 
``` 
 
--- 
 
## Formato das Notificações 
 
Cada notificação enviada ao Telegram tem este aspecto: 
 
``` 
📱 iPhone 14 Pro — 320 € 
 
📦 Estado: Como novo 
📍 Porto 
⭐ Vendedor: 4.8 estrelas (47 avaliações) 
👤 @nome_do_vendedor 
 
🔗 Ver listagem → vinted.pt/items/12345678 
``` 
 
Se o produto tiver foto, esta é enviada junto com a mensagem. 
 
--- 
 
## Troubleshooting 
 
### O bot não envia mensagens 
 
- Verifica que iniciaste conversa com o bot no Telegram (`/start`) 
- Confirma que o `TELEGRAM_TOKEN` no `.env` está correcto 
- Confirma que o `chat_id` no `config.yaml` é o teu e não tem aspas a mais 
- Testa com: `python bot.py --once --debug` 
 
### "Unauthorized" ou "403 Forbidden" 
 
- O token está errado ou foi revogado → gera um novo com o `@BotFather` 
 
### "Chat not found" 
 
- O `chat_id` está incorrecto → usa o `@userinfobot` para confirmar 
 
### Sem resultados nas pesquisas 
 
- Os filtros podem estar demasiado restritivos — tenta remover o filtro de condição ou alargar o intervalo de preços 
- A Vinted pode estar temporariamente a bloquear — aumenta o `delay_between_requests` 
 
### O serviço systemd não inicia 
 
```bash 
sudo journalctl -u vinted-bot -n 50   # ver erros detalhados 
``` 
 
Causa comum: caminho incorrecto no `ExecStart` ou utilizador errado no `User=`. 
 
### Logs de actividade 
 
```bash 
# Em tempo real 
tail -f /opt/vinted-bot/logs/bot.log 
 
# Últimas notificações enviadas 
grep "SENT" /opt/vinted-bot/logs/bot.log 
 
# Erros 
grep "ERROR" /opt/vinted-bot/logs/bot.log 
``` 
 
--- 
 
## Comandos Telegram

No modo continuo, podes pedir uma pesquisa imediata pelo Telegram:

```text
/search iphone 13, 200, 700
```

Formato:

```text
/search nome do item, preco_minimo, preco_maximo
```

Tambem funciona com aspas:

```text
/search "iphone 13 pro", "300", "700"
```

E continua a aceitar a forma curta, sem preco minimo:

```text
/search iphone 13, 700
```

A pesquisa manual respeita os filtros globais do `config.yaml`, responde apenas ao chat que enviou o comando e nao marca os resultados como vistos na base de dados.

Para pausar e retomar a monitorizacao automatica:

```text
/pause
/resume
/status
```

Tambem existem os aliases:

```text
/stop
/startbot
```

O estado fica guardado em `data/bot_state.json`, por isso a pausa continua ativa mesmo depois de reiniciar o processo.

---

## FAQ 
 
**Posso adicionar pesquisas sem reiniciar o bot?** 
Não — após editar o `config.yaml`, reinicia o serviço: 
```bash 
sudo systemctl restart vinted-bot 
``` 
 
**O bot vai alertar-me para listagens antigas?** 
Não. Na primeira execução, o bot regista todos os IDs actuais sem notificar. A partir daí, só notifica listagens novas. 
 
**Posso monitorizar outros países da Vinted?** 
Sim — muda o campo `country` no `config.yaml` para `es`, `fr`, `de`, `it`, `be`, etc. Podes também ter múltiplas instâncias com configs diferentes. 
 
**Qual o intervalo mínimo recomendado?** 
10 minutos. Abaixo disso aumentas o risco de bloqueio por parte da Vinted. 
 
**Como apagar o histórico e recomeçar?** 
```bash 
rm data/seen_items.db 
sudo systemctl restart vinted-bot 
``` 
 
**Como actualizar o bot para uma nova versão?** 
```bash 
cd /opt/vinted-bot 
git pull 
source venv/bin/activate 
pip install -r requirements.txt 
sudo systemctl restart vinted-bot 
``` 
 
--- 
 
## Notas Técnicas 
 
O bot usa a **API interna não documentada** da Vinted (`/api/v2/catalog/items`), que é a mesma que o site usa internamente. Isto é mais estável e eficiente do que fazer parse do HTML. 
 
O sistema de rating da Vinted usa `feedback_reputation` (valor de 0.0 a 1.0). O valor de "3 estrelas" corresponde a `0.6` nesta escala, o que equivale a 60% de feedback positivo. 
 
--- 
 
## Licença 
 
MIT License 
