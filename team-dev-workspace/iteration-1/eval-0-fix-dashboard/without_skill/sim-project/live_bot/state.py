""
Bot State - handles persistence of trading bot state to JSON.
"
import json
import os
from copy import deepcopy


class BotState:
    def __init__(self, state_path=None):
        self.state_path = state_path or os.path.join(os.path.dirname(__file__), "state.json")
        self.data = self._load()

    def _load(self):
        """Load state from JSON file."""
        if os.path.exists(self.state_path):
            with open(self.state_path, "r") as f:
                return json.load(f)
        return self._default_state()

    def _default_state(self):
        return {
            "total_trades": 0,
            "total_volume": 0.0,
            "cycles_completed": 0,
            "last_exchange_name": "",
            "last_cycle_time": "",
            "is_live": False,
            "win_trades": 0,
            "loss_trades": 0,
            "started_at": ""
        }

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def increment(self, key, amount=1):
        self.data[key] = self.data.get(key, 0) + amount

    def save(self):
        with open(self.state_path, "w") as f:
            json.dump(self.data, f, indent=2)

    def reset(self):
        self.data = self._default_state()
        self.save()
