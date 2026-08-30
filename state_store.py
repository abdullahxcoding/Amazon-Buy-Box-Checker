import json
import os

import config


def load_state() -> dict:
    if not os.path.exists(config.STATE_JSON_PATH):
        return {}
    with open(config.STATE_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(config.STATE_JSON_PATH), exist_ok=True)
    with open(config.STATE_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
