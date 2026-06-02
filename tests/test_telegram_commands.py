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
    def __init__(self):
        self.params = None

    def search(self, params, max_pages=1):
        self.params = params
        return [
            {
                "id": 1,
                "title": "iPhone 11",
                "url": "https://example.com/item",
                "user": {"feedback_count": 3, "feedback_reputation": 1.0},
                "created_at_ts": 2000000000,
            }
        ]


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
