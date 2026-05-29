import os
import yaml
from dotenv import load_dotenv

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
        
    # Substituir placeholders, ex: ${TELEGRAM_TOKEN}
    # Para ser robusto, iteramos sobre as chaves do ambiente
    for key, value in os.environ.items():
        placeholder = f"${{{key}}}"
        content = content.replace(placeholder, value)
        
    config = yaml.safe_load(content)
    
    # Validação básica
    if "telegram" not in config or not config["telegram"].get("token"):
        raise ValueError("O token do Telegram não está configurado. Verifica o teu ficheiro .env e config.yaml.")
        
    if "telegram" not in config or not config["telegram"].get("destinations"):
        raise ValueError("Nenhum destino (chat_id) configurado no config.yaml.")
        
    return config
