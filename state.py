from datetime import date, datetime, timezone

from utils import load_json, save_json


def initial_state():
    today = date.today().isoformat()
    return {
        "day": today,
        "daily_volume_usdc": "0",
        "daily_realized_pnl_usdc": "0",
        "consecutive_losses": 0,
        "paused_until": None,
        "stopped_for_day": False,
        "open_order_refs": {},
        "paper_positions": {},
        "paper_orders": {},
        "paper_fills": [],
        "last_error": None,
    }


class StateStore:
    def __init__(self, path):
        self.path = path
        self.state = initial_state()

    def load(self):
        try:
            self.state = load_json(self.path)
        except FileNotFoundError:
            self.save()
        if self.state.get("day") != date.today().isoformat():
            old_positions = self.state.get("paper_positions", {})
            self.state = initial_state()
            self.state["paper_positions"] = old_positions
            self.save()
        return self.state

    def save(self):
        save_json(self.path, self.state)

    def pause_minutes(self, minutes, reason):
        until = datetime.now(timezone.utc).timestamp() + minutes * 60
        self.state["paused_until"] = until
        self.state["last_error"] = reason
        self.save()

