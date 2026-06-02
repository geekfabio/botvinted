import argparse
import logging
import time
import schedule
import sys
import threading
from contextlib import nullcontext
from logging.handlers import RotatingFileHandler

from config_loader import load_config
from db import Database
from bot_state import BotState
from scraper import VintedScraper
from notifier import TelegramNotifier
from telegram_commands import TelegramCommandHandler
from filters import item_passes_global_filters, build_search_url_params

def setup_logging(config: dict, debug_mode: bool):
    log_config = config.get("logging", {})
    log_level_str = "DEBUG" if debug_mode else log_config.get("level", "INFO")
    
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    log_file = log_config.get("file", "logs/bot.log")
    
    # Garantir que a pasta de logs existe
    import os
    os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
    
    max_bytes = log_config.get("max_size_mb", 10) * 1024 * 1024
    backup_count = log_config.get("backup_count", 3)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count)
    file_handler.setFormatter(formatter)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Configurar root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    return root_logger

def run_searches(
    config: dict,
    db: Database,
    scraper: VintedScraper,
    notifier: TelegramNotifier,
    dry_run: bool,
    specific_search: str = None,
    operation_lock=None,
):
    logger = logging.getLogger("bot")
    
    global_filters = config.get("global_filters", {})
    scraping_config = config.get("scraping", {})
    detail_validation = config.get("detail_validation", {})
    detail_enabled = detail_validation.get("enabled", True)
    detail_delay = detail_validation.get("delay_between_detail_requests", 1)
    max_pages = scraping_config.get("max_pages_per_search", 1)
    
    searches = config.get("searches", [])
    
    for search in searches:
        name = search.get("name")
        search_filters = dict(global_filters)
        search_exclude_keywords = search.get("exclude_keywords", [])
        if search_exclude_keywords:
            search_filters["exclude_keywords"] = (
                global_filters.get("exclude_keywords", []) + search_exclude_keywords
            )
        
        if specific_search and specific_search.lower() not in name.lower():
            continue
            
        operation_context = operation_lock or nullcontext()
        with operation_context:
            logger.info(f"Running search: {name}")
            
            params = build_search_url_params(search, scraping_config)
            items = scraper.search(params, max_pages=max_pages)
            for item in items:
                if search.get("resale"):
                    item["resale"] = search.get("resale")
            
            logger.info(f"Found {len(items)} items for '{name}'")
            already_seen = 0
            filtered_out = 0
            matched = 0
            
            for item in items:
                item_id = str(item.get("id"))
                
                # Se jÃ¡ vimos este item, saltar
                if db.is_item_seen(item_id):
                    already_seen += 1
                    continue

                if detail_enabled:
                    item = scraper.get_item_details(item)
                    if detail_delay:
                        time.sleep(detail_delay)
                    
                # Verifica filtros globais
                if not item_passes_global_filters(item, search_filters):
                    filtered_out += 1
                    if not dry_run:
                        db.mark_item_seen(item_id)
                    continue
                    
                # Ã‰ uma listagem nova e vÃ¡lida!
                logger.info(f"NEW MATCH: {name} - Item {item_id}")
                matched += 1
                
                if not dry_run:
                    if notifier.send_alert(item, name):
                        db.mark_item_seen(item_id)

            logger.info(
                f"Search summary '{name}': matched={matched}, "
                f"already_seen={already_seen}, filtered_out={filtered_out}, dry_run={dry_run}"
            )
            
    # Limpeza da base de dados (remoÃ§Ã£o de itens > 90 dias)
    deleted = db.prune_old_items(days_old=90)
    if deleted > 0:
        logger.info(f"Database cleanup: Removed {deleted} old items.")

def main():
    parser = argparse.ArgumentParser(description="Vinted Alert Bot")
    parser.add_argument("--once", action="store_true", help="Executar apenas uma vez e terminar")
    parser.add_argument("--dry-run", action="store_true", help="Executar sem enviar notificaÃ§Ãµes para o Telegram")
    parser.add_argument("--search", type=str, help="Correr apenas a pesquisa que contÃ©m este nome")
    parser.add_argument("--debug", action="store_true", help="ForÃ§ar o nÃ­vel de logging para DEBUG")
    args = parser.parse_args()
    
    try:
        config = load_config()
    except Exception as e:
        print(f"Erro ao carregar a configuraÃ§Ã£o: {e}")
        sys.exit(1)
        
    logger = setup_logging(config, args.debug)
    logger.info("Starting Vinted Alert Bot...")
    
    db_path = config.get("database", {}).get("path", "data/seen_items.db")
    db = Database(db_path=db_path)
    state_path = config.get("telegram_commands", {}).get("state_path", "data/bot_state.json")
    bot_state = BotState(path=state_path)
    operation_lock = threading.Lock()
    
    scraper = VintedScraper(config.get("scraping", {}))
    
    telegram_token = config.get("telegram", {}).get("token")
    destinations = config.get("telegram", {}).get("destinations", [])
    notifier = TelegramNotifier(
        token=telegram_token,
        destinations=destinations,
        config={
            **config.get("telegram", {}),
            "resale": config.get("resale", {}),
        }
    )
    allowed_chat_ids = [dest.get("chat_id") for dest in destinations if dest.get("chat_id")]
    telegram_commands_config = config.get("telegram_commands", {})
    command_handler = None
    if telegram_commands_config.get("enabled", True) and not args.once and not args.dry_run:
        command_handler = TelegramCommandHandler(
            token=telegram_token,
            allowed_chat_ids=allowed_chat_ids,
            config=config,
            scraper=scraper,
            notifier=notifier,
            bot_state=bot_state,
            operation_lock=operation_lock
        )
        command_handler.bootstrap()
        logger.info("Telegram commands enabled: /pause, /resume, /status, /search")
    
    # Job execution function
    def job():
        if bot_state.is_paused():
            logger.info("--- Periodic check skipped: bot is paused ---")
            return
        logger.info("--- Starting periodic check ---")
        try:
            run_searches(config, db, scraper, notifier, args.dry_run, args.search, operation_lock=operation_lock)
        except Exception as e:
            logger.error(f"Periodic check failed: {e}", exc_info=True)
        logger.info("--- Finished periodic check ---")
        
    if args.once:
        logger.info("Running in '--once' mode.")
        job()
    else:
        interval_minutes = config.get("scheduler", {}).get("interval_minutes", 30)
        logger.info(f"Running in scheduler mode. Interval: {interval_minutes} minutes.")

        stop_event = threading.Event()
        command_thread = None

        def poll_commands():
            while not stop_event.is_set():
                command_handler.poll_once()
                stop_event.wait(1)

        if command_handler:
            command_thread = threading.Thread(target=poll_commands, daemon=True)
            command_thread.start()
        
        # Executar imediatamente a primeira vez
        job()
        
        # Agendar prÃ³ximas execuÃ§Ãµes
        schedule.every(interval_minutes).minutes.do(job)

        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            stop_event.set()
            if command_thread:
                command_thread.join(timeout=5)
            logger.info("Bot stopped manually.")

if __name__ == "__main__":
    main()
