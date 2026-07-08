import random
import time
import uuid
from datetime import datetime, timezone

from logger import log_event
from utils import D, dstr, q_down


class OrderManager:
    def __init__(self, config, exchange, paper, market_meta, logger):
        self.config = config
        self.exchange = exchange
        self.paper = paper
        self.market_meta = market_meta
        self.logger = logger

    def _client_id(self, tag):
        return f"llv_{tag}_{uuid.uuid4().hex[:12]}"

    def _requote_seconds(self):
        min_seconds = float(self.config.get("random_requote_min_seconds", self.config["limit_requote_seconds"]))
        max_seconds = float(self.config.get("random_requote_max_seconds", self.config["limit_requote_seconds"]))
        if max_seconds < min_seconds:
            max_seconds = min_seconds
        return random.uniform(min_seconds, max_seconds)

    def _order_submit_delay(self):
        min_seconds = float(self.config.get("order_submit_delay_min_seconds", 0))
        max_seconds = float(self.config.get("order_submit_delay_max_seconds", min_seconds))
        if max_seconds < min_seconds:
            max_seconds = min_seconds
        delay = random.uniform(min_seconds, max_seconds)
        if delay > 0:
            log_event(self.logger, "order_submit_delay", seconds=round(delay, 2))
            time.sleep(delay)

    def cancel_stale_or_all(self, market, cancel_all=False):
        if cancel_all:
            self.cancel_all(market, "cancel_all_requested")
            return "canceled"
        if self.exchange.mode == "paper":
            now = time.time()
            active = False
            for order in self.paper.open_orders():
                if order.get("market") == market:
                    active = True
                if now - float(order.get("createdAt", now)) > self._requote_seconds():
                    self.paper.cancel_all(market)
                    log_event(self.logger, "paper_cancel_stale", market=market)
                    return "canceled"
            return "active" if active else "none"
        orders = self.exchange.open_orders(market).get("result", [])
        if not orders:
            return "none"
        now = datetime.now(timezone.utc)
        stale = False
        for order in orders:
            created = order.get("createdAt")
            if not created:
                continue
            created_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if (now - created_at).total_seconds() > self._requote_seconds():
                stale = True
                break
        if stale:
            self.cancel_all(market, "requote_refresh")
            return "canceled"
        return "active"

    def cancel_all(self, market, reason):
        if self.exchange.mode == "paper":
            result = self.paper.cancel_all(market)
        else:
            result = self.exchange.cancel_all(market)
        log_event(self.logger, "cancel_all", market=market, reason=reason, result=result)
        return result

    def place_limit(self, market, side, price, size, reduce_only=False, tag="entry"):
        payload = {
            "clientOrderId": self._client_id(tag),
            "market": market,
            "side": side,
            "price": dstr(q_down(price, self.market_meta.get("quoteIncrement", "0.01"))),
            "size": dstr(q_down(size, self.market_meta.get("baseIncrement", "0.01"))),
            "type": "limit",
            "timeInForce": "IOC" if reduce_only else "GTC",
            "postOnly": False if reduce_only else True,
            "reduceOnly": bool(reduce_only),
        }
        if D(payload["size"]) <= 0:
            log_event(self.logger, "skip_zero_size", payload=payload)
            return None
        if self.exchange.mode == "paper":
            result = self.paper.place_order(payload)
        else:
            try:
                self._order_submit_delay()
                result = self.exchange.create_order(payload)
            except Exception as exc:
                result = {"success": False, "error": str(exc)}
        log_event(self.logger, "place_limit", payload=payload, result=result)
        return result
