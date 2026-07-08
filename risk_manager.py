import time

from utils import D, dstr


class RiskDecision:
    def __init__(self, allow_new=True, reduce_only=False, size_multiplier="1", reason="ok"):
        self.allow_new = allow_new
        self.reduce_only = reduce_only
        self.size_multiplier = D(size_multiplier)
        self.reason = reason


class RiskManager:
    def __init__(self, config, state_store, logger):
        self.config = config
        self.state_store = state_store
        self.logger = logger

    def leverage_allowed(self):
        return D(self.config["default_leverage"]) == D("10") and D(self.config["max_leverage"]) == D("10")

    def spread_decision(self, spread_pct):
        if spread_pct <= D(self.config["spread_normal_pct"]):
            return RiskDecision()
        if spread_pct <= D(self.config["spread_reduce_pct"]):
            return RiskDecision(size_multiplier="0.5", reason="spread_reduced_size")
        return RiskDecision(allow_new=False, reason="spread_too_wide")

    def daily_pnl_decision(self, equity, daily_pnl):
        ratio = D(daily_pnl) / D(equity) if D(equity) else D("0")
        if ratio <= D(self.config["daily_loss_stop_pct"]):
            self.state_store.state["stopped_for_day"] = True
            return RiskDecision(allow_new=False, reduce_only=True, reason="daily_loss_stop")
        if ratio <= D(self.config["daily_loss_reduce_pct"]):
            return RiskDecision(allow_new=False, reduce_only=True, reason="daily_loss_reduce")
        if ratio <= D(self.config["daily_loss_pause_pct"]):
            return RiskDecision(allow_new=False, reason="daily_loss_pause")
        return RiskDecision()

    def consecutive_loss_decision(self):
        losses = int(self.state_store.state.get("consecutive_losses", 0))
        if losses >= int(self.config["consecutive_loss_stop_count"]):
            self.state_store.state["stopped_for_day"] = True
            return RiskDecision(allow_new=False, reduce_only=True, reason="consecutive_loss_stop")
        if losses >= int(self.config["consecutive_loss_pause_count"]):
            until = self.state_store.state.get("paused_until")
            now = time.time()
            if not until or now > float(until):
                self.state_store.pause_minutes(int(self.config["loss_pause_minutes"]), "consecutive_loss_pause")
            return RiskDecision(allow_new=False, reason="consecutive_loss_pause")
        return RiskDecision()

    def volatility_decision(self, ratio):
        if not self.config.get("enable_volatility_pause", True):
            return RiskDecision()
        if D(ratio) > D(self.config["volatility_spike_multiplier"]):
            self.state_store.pause_minutes(int(self.config["volatility_pause_minutes"]), "volatility_spike")
            return RiskDecision(allow_new=False, reduce_only=True, reason="volatility_spike")
        return RiskDecision()

    def target_volume_decision(self):
        if not self.config.get("enable_daily_target_stop", True):
            return RiskDecision()
        if D(self.state_store.state.get("daily_volume_usdc", "0")) >= D(self.config["daily_target_volume_usdc"]):
            return RiskDecision(allow_new=False, reduce_only=True, reason="daily_target_volume_reached")
        return RiskDecision()

    def pause_decision(self):
        if self.state_store.state.get("stopped_for_day"):
            return RiskDecision(allow_new=False, reduce_only=True, reason="stopped_for_day")
        until = self.state_store.state.get("paused_until")
        if until and time.time() < float(until):
            return RiskDecision(allow_new=False, reason="paused")
        return RiskDecision()

    def exposure_decision(self, equity, long_notional, short_notional):
        total = D(long_notional) + D(short_notional)
        if total > D(equity) * D(self.config["max_total_exposure_pct_equity"]):
            return RiskDecision(allow_new=False, reduce_only=True, reason="total_exposure_limit")
        return RiskDecision()

    def combine(self, decisions):
        allow = all(d.allow_new for d in decisions)
        reduce_only = any(d.reduce_only for d in decisions)
        multiplier = min((d.size_multiplier for d in decisions), default=D("1"))
        reason = ",".join(d.reason for d in decisions if d.reason != "ok") or "ok"
        return RiskDecision(allow, reduce_only, multiplier, reason)
