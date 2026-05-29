import csv
import logging
import re
import shlex
from dataclasses import dataclass
from io import StringIO

import requests

from filters import build_search_url_params, item_passes_global_filters

logger = logging.getLogger(__name__)


@dataclass
class ManualSearchCommand:
    query: str
    price_min: float
    price_max: float


class CommandParseError(ValueError):
    pass


def _parse_price(value: str) -> float:
    cleaned = value.strip().replace("EUR", "").replace("eur", "").replace("\u20ac", "")
    cleaned = cleaned.replace(" ", "").replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", cleaned):
        raise CommandParseError("preco invalido")
    return float(cleaned)


def _strip_search_command(text: str) -> str:
    match = re.match(r"^/search(?:@\w+)?(?:\s+|$)(.*)$", text.strip(), flags=re.IGNORECASE)
    if not match:
        raise CommandParseError("comando invalido")
    body = match.group(1).strip()
    if not body:
        raise CommandParseError("faltam parametros")
    return body


def parse_search_command(text: str) -> ManualSearchCommand:
    """
    Aceita:
      /search iphone 13, 200, 700
      /search "iphone 13", "200", "700"
      /search iphone 13, 700
      /search iphone 13 200 700
    """
    body = _strip_search_command(text)

    if "," in body:
        parts = next(csv.reader(StringIO(body), skipinitialspace=True))
        parts = [part.strip().strip("\"'") for part in parts if part.strip()]
        if len(parts) < 2:
            raise CommandParseError("usa: /search nome, preco_min, preco_max")
        if len(parts) == 2:
            query = parts[0]
            price_min = 0.0
            price_max = _parse_price(parts[1])
        else:
            query = ", ".join(parts[:-2])
            price_min = _parse_price(parts[-2])
            price_max = _parse_price(parts[-1])
    else:
        try:
            tokens = shlex.split(body)
        except ValueError as exc:
            raise CommandParseError("aspas invalidas") from exc

        if len(tokens) < 2:
            raise CommandParseError("usa: /search nome preco_max")

        price_max = _parse_price(tokens[-1])
        try:
            price_min = _parse_price(tokens[-2])
            query_tokens = tokens[:-2]
        except CommandParseError:
            price_min = 0.0
            query_tokens = tokens[:-1]

        query = " ".join(query_tokens)

    query = query.strip()
    if not query:
        raise CommandParseError("nome do item em falta")
    if price_min < 0 or price_max < 0:
        raise CommandParseError("precos nao podem ser negativos")
    if price_min > price_max:
        raise CommandParseError("preco minimo nao pode ser maior que o maximo")

    return ManualSearchCommand(query=query, price_min=price_min, price_max=price_max)


class TelegramCommandHandler:
    def __init__(self, token: str, allowed_chat_ids: list, config: dict, scraper, notifier, bot_state=None):
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.allowed_chat_ids = {str(chat_id) for chat_id in allowed_chat_ids}
        self.config = config
        self.scraper = scraper
        self.notifier = notifier
        self.bot_state = bot_state
        self.offset = None

    def bootstrap(self):
        """Processa comandos de controlo pendentes e ignora pesquisas antigas ao arrancar."""
        try:
            updates = self._get_updates(timeout=0)
            for update in updates:
                self.offset = update["update_id"] + 1
                message = update.get("message") or update.get("edited_message") or {}
                text = message.get("text", "")
                if not text:
                    continue
                command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()
                if command in ("/pause", "/stop", "/resume", "/startbot", "/status"):
                    self._handle_control_message(message, command)
        except Exception as e:
            logger.error(f"Failed to bootstrap Telegram commands: {e}")

    def poll_once(self):
        try:
            updates = self._get_updates(timeout=0)
        except Exception as e:
            logger.error(f"Failed to fetch Telegram updates: {e}")
            return

        for update in updates:
            self.offset = update["update_id"] + 1
            message = update.get("message") or update.get("edited_message") or {}
            text = message.get("text", "")
            command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()
            if command == "/search":
                self._handle_search_message(message, text)
            elif command in ("/pause", "/stop", "/resume", "/startbot", "/status"):
                self._handle_control_message(message, command)

    def _get_updates(self, timeout: int):
        params = {"timeout": timeout, "allowed_updates": '["message","edited_message"]'}
        if self.offset is not None:
            params["offset"] = self.offset
        response = requests.get(f"{self.api_url}/getUpdates", params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(data)
        return data.get("result", [])

    def _handle_search_message(self, message: dict, text: str):
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))

        if chat_id not in self.allowed_chat_ids:
            logger.warning(f"Ignoring unauthorized /search from chat {chat_id}")
            return

        try:
            command = parse_search_command(text)
        except CommandParseError as e:
            self.notifier.send_text_to_chat(
                chat_id,
                f"Comando invalido: {e}\nUsa: /search nome, preco_min, preco_max"
            )
            return

        commands_config = self.config.get("telegram_commands", {})
        max_results = int(commands_config.get("max_results", 5))
        max_pages = int(commands_config.get("max_pages", 1))
        scraping_config = self.config.get("scraping", {})
        detail_validation = self.config.get("detail_validation", {})
        currency = scraping_config.get("currency", "EUR")

        self.notifier.send_text_to_chat(
            chat_id,
            f"A procurar '{command.query}' entre {command.price_min:g} e {command.price_max:g} {currency}..."
        )

        search_config = {
            "name": f"Pesquisa manual: {command.query}",
            "query": command.query,
            "price_min": command.price_min,
            "price_max": command.price_max,
            "condition": []
        }

        params = build_search_url_params(search_config, scraping_config)
        items = self.scraper.search(params, max_pages=max_pages)
        global_filters = self.config.get("global_filters", {})
        matches = []
        for item in items:
            resale_profiles = self.config.get("resale", {}).get("profiles", {})
            for profile_name, profile in resale_profiles.items():
                if profile_name.lower() in command.query.lower():
                    item["resale"] = profile
                    break
            if detail_validation.get("enabled", True):
                item = self.scraper.get_item_details(item)
            if item_passes_global_filters(item, global_filters):
                matches.append(item)
            if len(matches) >= max_results:
                break

        if not matches:
            self.notifier.send_text_to_chat(chat_id, "Nao encontrei resultados com esses filtros.")
            return

        for item in matches:
            self.notifier.send_alert_to_chat(item, search_config["name"], chat_id)

        remaining = len(matches) - max_results
        if remaining > 0:
            self.notifier.send_text_to_chat(chat_id, f"Mostrei {max_results} resultados. Existem mais {remaining}.")

    def _handle_control_message(self, message: dict, command: str):
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))

        if chat_id not in self.allowed_chat_ids:
            logger.warning(f"Ignoring unauthorized {command} from chat {chat_id}")
            return

        if self.bot_state is None:
            self.notifier.send_text_to_chat(chat_id, "Estado do bot indisponivel.")
            return

        if command in ("/pause", "/stop"):
            self.bot_state.pause(chat_id=chat_id)
            self.notifier.send_text_to_chat(chat_id, "Monitorizacao pausada. Usa /resume para voltar a iniciar.")
            return

        if command in ("/resume", "/startbot"):
            self.bot_state.resume(chat_id=chat_id)
            self.notifier.send_text_to_chat(chat_id, "Monitorizacao ativa.")
            return

        if command == "/status":
            status = "pausada" if self.bot_state.is_paused() else "ativa"
            self.notifier.send_text_to_chat(chat_id, f"Monitorizacao: {status}.")
