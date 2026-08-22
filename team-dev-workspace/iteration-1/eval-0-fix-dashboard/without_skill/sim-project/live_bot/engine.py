""
Trading Bot Engine - manages trading logic and state transitions.
Supports both dry_run and live modes.
""
import json
import os
from datetime import datetime
from live_bot.state import BotState


class TradingEngine:
    def __init__(self, config_path=None, state_path=None, trade_log_path=None):
        self.dry_run = True  # Default to dry_run mode
        self.exchange_name = ""
        self.state_path = state_path or os.path.join(os.path.dirname(__file__), "state.json")
        self.trade_log_path = trade_log_path or os.path.join(os.path.dirname(__file__), "..", "trade_log.json")
        self.state = BotState(self.state_path)
        
        if config_path and os.path.exists(config_path):
            self._load_config(config_path)

    def _load_config(self, config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
        self.dry_run = config.get("dry_run", True)
        self.exchange_name = config.get("exchange_name", "")

    def execute_trade(self, symbol, side, amount, price):
        """Execute a trade and log it."""
        trade_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": price,
            "dry_run": self.dry_run,
            "exchange": self.exchange_name,
            "status": "simulated" if self.dry_run else "executed"
        }
        
        # Append to trade log
        trades = []
        if os.path.exists(self.trade_log_path):
            with open(self.trade_log_path, "r") as f:
                trades = json.load(f)
        trades.append(trade_entry)
        with open(self.trade_log_path, "w") as f:
            json.dump(trades, f, indent=2)
        
        # Update state
        if not self.dry_run:
            self.state.increment("total_trades")
            self.state.set("last_exchange_name", self.exchange_name)
            self.state.increment("total_volume", amount * price)
            self.state.save()
        
        return trade_entry

    def run_cycle(self):
        """Run one trading cycle."""
        self.state.set("last_cycle_time", datetime.utcnow().isoformat())
        self.state.increment("cycles_completed")
        self.state.save()
