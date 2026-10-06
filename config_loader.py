import os
import re

import yaml
from dotenv import load_dotenv


ENV_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
TELEGRAM_TOKEN = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")

def load_config(config_path="config.yaml"):
    """
    Carrega o ficheiro de configuração YAML e substitui as variáveis de ambiente.
    """
    # Carregar variáveis do .env
    load_dotenv()
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Ficheiro de configuração '{config_path}' não encontrado. Copia o config.example.yaml para {config_path} e edita-o.")
        
    with open(config_path, "r", encoding="utf-8") as f:
        # Lemos como string para poder fazer replace de variáveis de ambiente
        content = f.read()
        
    # Substituir placeholders, ex: ${TELEGRAM_TOKEN}, e indicar claramente
    # qualquer variável em falta em vez de enviar um token literal à API.
    missing_variables = []

    def replace_environment(match):
        key = match.group(1)
        value = os.environ.get(key)
        if value is None:
            missing_variables.append(key)
            return match.group(0)
        return value

    content = ENV_PLACEHOLDER.sub(replace_environment, content)
    if missing_variables:
        missing = ", ".join(sorted(set(missing_variables)))
        raise ValueError(
            f"Variáveis de ambiente em falta: {missing}. "
            "Cria o ficheiro .env a partir de .env.example."
        )
        
    config = yaml.safe_load(content)
    if not isinstance(config, dict):
        raise ValueError("O config.yaml está vazio ou não contém um objeto YAML válido.")
    
    # Validação básica
    if "telegram" not in config or not config["telegram"].get("token"):
        raise ValueError("O token do Telegram não está configurado. Verifica o teu ficheiro .env e config.yaml.")

    token = str(config["telegram"]["token"]).strip()
    if not TELEGRAM_TOKEN.fullmatch(token):
        raise ValueError(
            "O TELEGRAM_TOKEN não tem um formato válido. Gera um token novo no BotFather."
        )
    config["telegram"]["token"] = token
        
    if "telegram" not in config or not config["telegram"].get("destinations"):
        raise ValueError("Nenhum destino (chat_id) configurado no config.yaml.")

    for destination in config["telegram"]["destinations"]:
        if not isinstance(destination, dict) or not destination.get("chat_id"):
            raise ValueError("Cada destino Telegram precisa de um chat_id válido.")
        destination["chat_id"] = str(destination["chat_id"]).strip()
        
    return config
