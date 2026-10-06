import csv
import logging
import re
import shlex
import threading
from contextlib import nullcontext
from dataclasses import dataclass
from io import StringIO
from typing import Optional

import requests

from filters import build_search_url_params, item_passes_global_filters

logger = logging.getLogger(__name__)

CONTROL_COMMANDS = {"/pause", "/stop", "/resume", "/startbot", "/status"}
PLAIN_CONTROL_ALIASES = {"pause", "stop", "resume", "startbot", "status"}
MORE_COMMANDS = {"/mais"}
PLAIN_MORE_ALIASES = {"mais"}
PACK_KEYWORDS = ("pack", "packs", "lote", "lot", "lots", "conjunto", "kit", "bundle")


def _safe_telegram_error(error: Exception) -> str:
    """Summarize request failures without logging the token-bearing URL."""
    if isinstance(error, requests.RequestException):
        response = getattr(error, "response", None)
        if response is not None:
            return f"HTTP {response.status_code}"
        return type(error).__name__
    return type(error).__name__


@dataclass
class ManualSearchCommand:
    query: str
    price_min: float
    price_max: Optional[float]


class CommandParseError(ValueError):
    pass


def _parse_price(value: str) -> float:
    cleaned = value.strip().replace("EUR", "").replace("eur", "").replace("\u20ac", "")
    cleaned = cleaned.replace(" ", "").replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", cleaned):
        raise CommandParseError("preco invalido")
    return float(cleaned)


def _strip_search_command(text: str) -> str:
    text = text.strip()
    if not text.startswith("/"):
        if not text:
            raise CommandParseError("nome do item em falta")
        return text

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

        if len(tokens) < 3:
            query_tokens = tokens
            price_min = 0.0
            price_max = None
        else:
            try:
                price_max = _parse_price(tokens[-1])
            except CommandParseError:
                price_min = 0.0
                price_max = None
                query_tokens = tokens
            else:
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
    if price_min < 0 or (price_max is not None and price_max < 0):
        raise CommandParseError("precos nao podem ser negativos")
    if price_max is not None and price_min > price_max:
        raise CommandParseError("preco minimo nao pode ser maior que o maximo")

    return ManualSearchCommand(query=query, price_min=price_min, price_max=price_max)


def _normalize_command(text: str) -> str:
    first_token = text.strip().split(maxsplit=1)[0] if text.strip() else ""
    command = first_token.split("@", 1)[0].lower()
    if command in PLAIN_CONTROL_ALIASES:
        return f"/{command}"
    if command in PLAIN_MORE_ALIASES:
        return f"/{command}"
    return command


def _price_value(item: dict) -> float:
    price = item.get("price")
    if isinstance(price, dict):
        value = price.get("amount", price.get("numeric"))
    else:
        value = item.get("price_numeric", price)

    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return float("inf")


def _is_pack_item(item: dict) -> bool:
    text = f"{item.get('title', '')} {item.get('description', '')}".lower()
    return any(keyword in text for keyword in PACK_KEYWORDS)


def _sort_manual_items(items: list) -> list:
    return sorted(items, key=lambda item: (not _is_pack_item(item), _price_value(item)))


class TelegramCommandHandler:
    def __init__(
        self,
        token: str,
        allowed_chat_ids: list,
        config: dict,
        scraper,
        notifier,
        bot_state=None,
        operation_lock=None,
    ):
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.allowed_chat_ids = {str(chat_id) for chat_id in allowed_chat_ids}
        self.config = config
        self.scraper = scraper
        self.notifier = notifier
        self.bot_state = bot_state
        self.offset = None
        self.operation_lock = operation_lock
        self.manual_search_sessions = {}

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
                command = _normalize_command(text)
                if command in CONTROL_COMMANDS:
                    self._handle_control_message(message, command)
        except Exception as e:
            logger.error(
                f"Failed to bootstrap Telegram commands: {_safe_telegram_error(e)}"
            )

    def poll_once(self):
        try:
            updates = self._get_updates(timeout=0)
        except Exception as e:
            logger.error(
                f"Failed to fetch Telegram updates: {_safe_telegram_error(e)}"
            )
            return

        for update in updates:
            self.offset = update["update_id"] + 1
            message = update.get("message") or update.get("edited_message") or {}
            text = message.get("text", "")
            command = _normalize_command(text)
            if command == "/search":
                self._start_search_message(message, text)
            elif command in MORE_COMMANDS:
                self._start_more_message(message)
            elif command in CONTROL_COMMANDS:
                self._handle_control_message(message, command)
            elif text.strip() and not text.strip().startswith("/"):
                self._start_search_message(message, text)

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

    def _start_search_message(self, message: dict, text: str):
        if self.operation_lock is None:
            self._handle_search_message(message, text)
            return

        thread = threading.Thread(
            target=self._handle_search_message,
            args=(message, text),
            daemon=True,
        )
        thread.start()

    def _start_more_message(self, message: dict):
        if self.operation_lock is None:
            self._handle_more_message(message)
            return

        thread = threading.Thread(
            target=self._handle_more_message,
            args=(message,),
            daemon=True,
        )
        thread.start()

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

        logger.info(
            f"Manual search requested from chat {chat_id}: query='{command.query}', "
            f"price_min={command.price_min:g}, price_max={command.price_max}"
        )

        if command.price_max is None:
            price_text = f"a partir de {command.price_min:g} {currency}, sem limite maximo"
        else:
            price_text = f"entre {command.price_min:g} e {command.price_max:g} {currency}"

        self.notifier.send_text_to_chat(chat_id, f"A procurar '{command.query}' {price_text}...")

        search_config = {
            "name": f"Pesquisa manual: {command.query}",
            "query": command.query,
            "price_min": command.price_min,
            "price_max": command.price_max,
            "condition": []
        }

        operation_context = self.operation_lock or nullcontext()
        with operation_context:
            params = build_search_url_params(search_config, scraping_config)
            items = _sort_manual_items(self.scraper.search(params, max_pages=max_pages))
            logger.info(f"Manual search '{command.query}' fetched {len(items)} items")

            apply_global_filters = commands_config.get("apply_global_filters", False)
            matches = []
            filtered_out = 0
            cursor = 0

            while cursor < len(items) and len(matches) < max_results:
                item = self._prepare_manual_item(items[cursor], command, detail_validation)
                cursor += 1

                if self._manual_item_filtered(item, apply_global_filters):
                    filtered_out += 1
                    continue

                matches.append(item)

            if filtered_out:
                logger.info(f"Manual search '{command.query}' filtered out {filtered_out} items")

            if not matches:
                if apply_global_filters:
                    logger.info(f"Manual search '{command.query}' finished with 0 matches after filters")
                    self.notifier.send_text_to_chat(chat_id, "Nao encontrei resultados com esses filtros.")
                else:
                    logger.info(f"Manual search '{command.query}' finished with 0 items")
                    self.notifier.send_text_to_chat(chat_id, "Nao encontrei resultados para essa pesquisa.")
                return

            logger.info(f"Manual search '{command.query}' sending {len(matches)} matches")
            for item in matches:
                self.notifier.send_alert_to_chat(item, search_config["name"], chat_id)

            self.manual_search_sessions[chat_id] = {
                "items": items,
                "cursor": cursor,
                "command": command,
                "search_name": search_config["name"],
                "apply_global_filters": apply_global_filters,
            }

            remaining = max(0, len(items) - cursor)
            if remaining > 0:
                self.notifier.send_text_to_chat(
                    chat_id,
                    f"Mostrei {len(matches)} resultados. Existem mais {remaining}. Usa /mais para ver os proximos 10.",
                )

    def _prepare_manual_item(self, item: dict, command: ManualSearchCommand, detail_validation: dict) -> dict:
        item = dict(item)
        resale_profiles = self.config.get("resale", {}).get("profiles", {})
        for profile_name, profile in resale_profiles.items():
            if profile_name.lower() in command.query.lower():
                item["resale"] = profile
                break

        if detail_validation.get("enabled", True):
            item = self.scraper.get_item_details(item)

        return item

    def _manual_item_filtered(self, item: dict, apply_global_filters: bool) -> bool:
        return apply_global_filters and not item_passes_global_filters(item, self.config.get("global_filters", {}))

    def _handle_more_message(self, message: dict):
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))

        if chat_id not in self.allowed_chat_ids:
            logger.warning(f"Ignoring unauthorized /mais from chat {chat_id}")
            return

        session = self.manual_search_sessions.get(chat_id)
        if not session:
            self.notifier.send_text_to_chat(chat_id, "Nao ha pesquisa anterior. Envia uma pesquisa primeiro.")
            return

        commands_config = self.config.get("telegram_commands", {})
        detail_validation = self.config.get("detail_validation", {})
        batch_size = int(commands_config.get("more_results", 10))
        items = session["items"]
        cursor = session["cursor"]
        command = session["command"]
        matches = []
        filtered_out = 0

        operation_context = self.operation_lock or nullcontext()
        with operation_context:
            while cursor < len(items) and len(matches) < batch_size:
                item = self._prepare_manual_item(items[cursor], command, detail_validation)
                cursor += 1

                if self._manual_item_filtered(item, session["apply_global_filters"]):
                    filtered_out += 1
                    continue

                matches.append(item)

            session["cursor"] = cursor

            if filtered_out:
                logger.info(f"Manual search '{command.query}' /mais filtered out {filtered_out} items")

            if not matches:
                self.notifier.send_text_to_chat(chat_id, "Nao ha mais resultados para mostrar.")
                return

            logger.info(f"Manual search '{command.query}' /mais sending {len(matches)} matches")
            for item in matches:
                self.notifier.send_alert_to_chat(item, session["search_name"], chat_id)

            remaining = max(0, len(items) - cursor)
            if remaining > 0:
                self.notifier.send_text_to_chat(chat_id, f"Mostrei mais {len(matches)} resultados. Existem mais {remaining}.")
            else:
                self.notifier.send_text_to_chat(chat_id, f"Mostrei mais {len(matches)} resultados. Nao ha mais resultados.")

    def _handle_control_message(self, message: dict, command: str):
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))

        if chat_id not in self.allowed_chat_ids:
            logger.warning(f"Ignoring unauthorized {command} from chat {chat_id}")
            return

        logger.info(f"Control command received from chat {chat_id}: {command}")

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
