import json
import os
import time


class BotState:
    def __init__(self, path="data/bot_state.json"):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)

    def _read(self):
        if not os.path.exists(self.path):
            return {"paused": False}

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"paused": False}

    def _write(self, state):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def is_paused(self):
        return bool(self._read().get("paused", False))

    def pause(self, chat_id=None):
        state = self._read()
        state.update({
            "paused": True,
            "updated_at": int(time.time()),
            "updated_by_chat_id": str(chat_id) if chat_id is not None else None,
        })
        self._write(state)

    def resume(self, chat_id=None):
        state = self._read()
        state.update({
            "paused": False,
            "updated_at": int(time.time()),
            "updated_by_chat_id": str(chat_id) if chat_id is not None else None,
        })
        self._write(state)
