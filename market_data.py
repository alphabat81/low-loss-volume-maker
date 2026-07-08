import time
from collections import deque

from utils import D


class MarketData:
    def __init__(self, exchange, market, depth_levels=10):
        self.exchange = exchange
        self.market = market
        self.depth_levels = depth_levels
        self.mid_history = deque(maxlen=360)
        self.market_meta = {"baseIncrement": "0.01", "quoteIncrement": "0.01"}

    def sync_market_meta(self):
        data = self.exchange.markets()
        pairs = data.get("result", {}).get("perps", {}).get("tradingPairs", [])
        for pair in pairs:
            if pair.get("market") == self.market:
                self.market_meta = pair
                return pair
        return self.market_meta

    def snapshot(self):
        book = self.exchange.depth(self.market, self.depth_levels).get("result", {})
        bids = [(D(p), D(q)) for p, q in book.get("bids", [])]
        asks = [(D(p), D(q)) for p, q in book.get("asks", [])]
        if not bids or not asks:
            raise RuntimeError("empty order book")
        best_bid = bids[0][0]
        best_ask = asks[0][0]
        mid = (best_bid + best_ask) / D("2")
        spread_pct = (best_ask - best_bid) / mid
        self.mid_history.append((time.time(), mid))
        return {"bids": bids, "asks": asks, "best_bid": best_bid, "best_ask": best_ask, "mid": mid, "spread_pct": spread_pct}

    def one_min_volatility_ratio(self):
        now = time.time()
        points = [(ts, mid) for ts, mid in self.mid_history if now - ts <= 30 * 60]
        if len(points) < 4:
            return D("1")
        one_min = [p for p in points if now - p[0] <= 60]
        if len(one_min) < 2:
            return D("1")
        latest_vol = abs(one_min[-1][1] - one_min[0][1]) / one_min[0][1]
        minute_returns = []
        for idx in range(1, len(points)):
            dt = points[idx][0] - points[idx - 1][0]
            if dt > 0:
                minute_returns.append(abs(points[idx][1] - points[idx - 1][1]) / points[idx - 1][1])
        avg = sum(minute_returns) / D(len(minute_returns)) if minute_returns else D("0")
        if avg == 0:
            return D("1")
        return latest_vol / avg

