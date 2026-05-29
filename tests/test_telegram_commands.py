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

    def send_text_to_chat(self, chat_id, text):
        self.messages.append((chat_id, text))


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
