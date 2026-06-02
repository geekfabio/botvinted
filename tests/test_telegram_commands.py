import pytest

from telegram_commands import CommandParseError, parse_search_command
from telegram_commands import TelegramCommandHandler


def test_parse_search_command_with_min_and_max_comma():
    command = parse_search_command('/search "iphone 13", "200", "700"')

    assert command.query == "iphone 13"
    assert command.price_min == 200
    assert command.price_max == 700


def test_parse_search_command_with_only_max_comma():
    command = parse_search_command("/search iphone 13, 700")

    assert command.query == "iphone 13"
    assert command.price_min == 0
    assert command.price_max == 700


def test_parse_search_command_with_min_and_max_spaces():
    command = parse_search_command("/search iphone 13 200 700")

    assert command.query == "iphone 13"
    assert command.price_min == 200
    assert command.price_max == 700


def test_parse_search_command_accepts_product_without_price():
    command = parse_search_command("/search iphone 13")

    assert command.query == "iphone 13"
    assert command.price_min == 0
    assert command.price_max is None


def test_parse_search_command_accepts_plain_text_product():
    command = parse_search_command("iphone 13")

    assert command.query == "iphone 13"
    assert command.price_min == 0
    assert command.price_max is None


def test_parse_search_command_rejects_min_greater_than_max():
    with pytest.raises(CommandParseError):
        parse_search_command("/search iphone 13, 800, 700")


class FakeState:
    def __init__(self):
        self.paused = False

    def pause(self, chat_id=None):
        self.paused = True

    def resume(self, chat_id=None):
        self.paused = False

    def is_paused(self):
        return self.paused


class FakeNotifier:
    def __init__(self):
        self.messages = []
        self.alerts = []

    def send_text_to_chat(self, chat_id, text):
        self.messages.append((chat_id, text))

    def send_alert_to_chat(self, item, search_name, chat_id):
        self.alerts.append((chat_id, search_name, item))
        return True


class FakeScraper:
    def __init__(self, items=None):
        self.params = None
        self.items = items or [
            {
                "id": 1,
                "title": "iPhone 11",
                "price": {"amount": "100", "currency_code": "EUR"},
                "url": "https://example.com/item",
                "user": {"feedback_count": 3, "feedback_reputation": 1.0},
                "created_at_ts": 2000000000,
            }
        ]

    def search(self, params, max_pages=1):
        self.params = params
        return self.items


def test_control_commands_pause_resume_and_status():
    state = FakeState()
    notifier = FakeNotifier()
    handler = TelegramCommandHandler(
        token="token",
        allowed_chat_ids=["123"],
        config={},
        scraper=None,
        notifier=notifier,
        bot_state=state,
    )
    message = {"chat": {"id": "123"}}

    handler._handle_control_message(message, "/pause")
    assert state.is_paused() is True

    handler._handle_control_message(message, "/status")
    assert notifier.messages[-1] == ("123", "Monitorizacao: pausada.")

    handler._handle_control_message(message, "/resume")
    assert state.is_paused() is False


def test_poll_once_processes_control_and_search_commands_without_restart():
    state = FakeState()
    notifier = FakeNotifier()
    scraper = FakeScraper()
    handler = TelegramCommandHandler(
        token="token",
        allowed_chat_ids=["123"],
        config={
            "telegram_commands": {"max_results": 1, "max_pages": 1},
            "scraping": {"currency": "EUR", "results_per_page": 10},
            "detail_validation": {"enabled": False},
        },
        scraper=scraper,
        notifier=notifier,
        bot_state=state,
    )
    handler._get_updates = lambda timeout: [
        {"update_id": 10, "message": {"chat": {"id": "123"}, "text": "/pause"}},
        {"update_id": 11, "message": {"chat": {"id": "123"}, "text": "/resume"}},
        {"update_id": 12, "message": {"chat": {"id": "123"}, "text": "/search iphone 11, 50, 100"}},
    ]

    handler.poll_once()

    assert state.is_paused() is False
    assert handler.offset == 13
    assert scraper.params["search_text"] == "iphone 11"
    assert scraper.params["price_from"] == 50
    assert scraper.params["price_to"] == 100
    assert notifier.alerts[0][0] == "123"


def test_poll_once_processes_plain_text_as_manual_search():
    state = FakeState()
    notifier = FakeNotifier()
    scraper = FakeScraper()
    handler = TelegramCommandHandler(
        token="token",
        allowed_chat_ids=["123"],
        config={
            "telegram_commands": {"max_results": 1, "max_pages": 1},
            "scraping": {"currency": "EUR", "results_per_page": 10},
            "detail_validation": {"enabled": False},
        },
        scraper=scraper,
        notifier=notifier,
        bot_state=state,
    )
    handler._get_updates = lambda timeout: [
        {"update_id": 20, "message": {"chat": {"id": "123"}, "text": "iphone 13"}},
    ]

    handler.poll_once()

    assert handler.offset == 21
    assert scraper.params["search_text"] == "iphone 13"
    assert "price_to" not in scraper.params
    assert notifier.alerts[0][0] == "123"


def test_poll_once_processes_plain_status_as_control_command():
    state = FakeState()
    notifier = FakeNotifier()
    scraper = FakeScraper()
    handler = TelegramCommandHandler(
        token="token",
        allowed_chat_ids=["123"],
        config={
            "telegram_commands": {"max_results": 1, "max_pages": 1},
            "scraping": {"currency": "EUR", "results_per_page": 10},
            "detail_validation": {"enabled": False},
        },
        scraper=scraper,
        notifier=notifier,
        bot_state=state,
    )
    handler._get_updates = lambda timeout: [
        {"update_id": 30, "message": {"chat": {"id": "123"}, "text": "status"}},
    ]

    handler.poll_once()

    assert handler.offset == 31
    assert scraper.params is None
    assert notifier.messages[-1] == ("123", "Monitorizacao: ativa.")


def test_manual_search_does_not_apply_global_filters_by_default():
    state = FakeState()
    notifier = FakeNotifier()
    scraper = FakeScraper()
    handler = TelegramCommandHandler(
        token="token",
        allowed_chat_ids=["123"],
        config={
            "telegram_commands": {"max_results": 1, "max_pages": 1},
            "scraping": {"currency": "EUR", "results_per_page": 10},
            "detail_validation": {"enabled": False},
            "global_filters": {
                "require_seller_feedback": True,
                "seller_min_reviews": 10,
            },
        },
        scraper=scraper,
        notifier=notifier,
        bot_state=state,
    )

    handler._handle_search_message({"chat": {"id": "123"}}, "/search boticario, 10, 50")

    assert notifier.alerts[0][0] == "123"


def test_mais_sends_next_10_prioritizing_packs_then_cheapest():
    state = FakeState()
    notifier = FakeNotifier()
    items = [
        {"id": 1, "title": "Produto normal caro", "price": {"amount": "30", "currency_code": "EUR"}, "url": "https://example.com/1"},
        {"id": 2, "title": "Produto normal barato", "price": {"amount": "12", "currency_code": "EUR"}, "url": "https://example.com/2"},
        {"id": 3, "title": "Pack Boticario", "price": {"amount": "20", "currency_code": "EUR"}, "url": "https://example.com/3"},
        {"id": 4, "title": "Lote perfume", "price": {"amount": "18", "currency_code": "EUR"}, "url": "https://example.com/4"},
    ]
    scraper = FakeScraper(items=items)
    handler = TelegramCommandHandler(
        token="token",
        allowed_chat_ids=["123"],
        config={
            "telegram_commands": {"max_results": 1, "max_pages": 1, "more_results": 10},
            "scraping": {"currency": "EUR", "results_per_page": 10},
            "detail_validation": {"enabled": False},
        },
        scraper=scraper,
        notifier=notifier,
        bot_state=state,
    )

    handler._handle_search_message({"chat": {"id": "123"}}, "/search boticario, 10, 50")
    handler._handle_more_message({"chat": {"id": "123"}})

    sent_ids = [alert[2]["id"] for alert in notifier.alerts]
    assert sent_ids == [4, 3, 2, 1]
    assert "Nao ha mais resultados" in notifier.messages[-1][1]


def test_mais_without_previous_search_sends_help_message():
    state = FakeState()
    notifier = FakeNotifier()
    handler = TelegramCommandHandler(
        token="token",
        allowed_chat_ids=["123"],
        config={},
        scraper=FakeScraper(),
        notifier=notifier,
        bot_state=state,
    )

    handler._handle_more_message({"chat": {"id": "123"}})

    assert notifier.messages[-1] == ("123", "Nao ha pesquisa anterior. Envia uma pesquisa primeiro.")
