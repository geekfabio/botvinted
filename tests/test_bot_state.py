from bot_state import BotState


def test_bot_state_pause_and_resume(tmp_path):
    state = BotState(path=str(tmp_path / "bot_state.json"))

    assert state.is_paused() is False

    state.pause(chat_id="123")
    assert state.is_paused() is True

    state.resume(chat_id="123")
    assert state.is_paused() is False
