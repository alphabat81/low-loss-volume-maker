from utils import D


class LowLossVolumeMaker:
    def __init__(self, config):
        self.config = config

    def quote_plan(self, snapshot, equity, risk_multiplier):
        mid = snapshot["mid"]
        spread = snapshot["spread_pct"]
        tp = min(max(spread / D("2"), D(self.config["take_profit_min_pct"])), D(self.config["take_profit_max_pct"]))
        entry_offset = max(spread / D("2"), D(self.config["entry_offset_pct"]))
        order_notional = D(equity) * D(self.config["order_size_pct_equity"]) * D(risk_multiplier)
        order_notional = max(order_notional, D(equity) * D(self.config["min_order_size_pct_equity"]) * D(risk_multiplier))
        order_notional = min(order_notional, D(equity) * D(self.config["max_order_size_pct_equity"]) * D(risk_multiplier))
        if self.config.get("maker_quote_mode") == "top_of_book":
            long_entry = snapshot["best_bid"]
            short_entry = snapshot["best_ask"]
        else:
            long_entry = mid * (D("1") - entry_offset)
            short_entry = mid * (D("1") + entry_offset)
        long_tp = long_entry * (D("1") + tp)
        short_tp = short_entry * (D("1") - tp)
        return {
            "order_notional": order_notional,
            "long_entry_price": long_entry,
            "short_entry_price": short_entry,
            "long_take_profit_price": long_tp,
            "short_take_profit_price": short_tp,
            "take_profit_pct": tp,
        }
