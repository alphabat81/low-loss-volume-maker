import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request


class ExchangeError(Exception):
    pass


class OndoExchange:
    def __init__(self, base_url, mode="paper"):
        self.base_url = base_url.rstrip("/")
        self.mode = mode
        self.key_id = os.getenv("ONDO_KEY_ID")
        self.api_secret = os.getenv("ONDO_API_SECRET")
        self._clock_offset_ms = 0
        # Ondo API traffic must go directly to the exchange. A stale system
        # proxy can otherwise leave the bot running while every request fails.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @property
    def live_ready(self):
        return self.mode == "live" and os.getenv("ONDO_LIVE_ENABLED") == "1" and self.key_id and self.api_secret

    def _headers(self, method, path, body):
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "low-loss-volume-maker/0.1",
        }
        if self.key_id and self.api_secret:
            ts = str(int(time.time() * 1000) + self._clock_offset_ms)
            msg = ts + method.upper() + path + body
            sig = hmac.new(self.api_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
            headers.update({"ONDO-KEY-ID": self.key_id, "ONDO-TIMESTAMP": ts, "ONDO-SIGN": sig})
        return headers

    def request(self, method, path, payload=None, auth=False):
        if auth and self.mode == "live" and not self.live_ready:
            raise ExchangeError("live trading is not enabled or API credentials are missing")
        body = "" if payload is None else json.dumps(payload, separators=(",", ":"))
        for attempt in range(2):
            req = urllib.request.Request(
                self.base_url + path,
                data=body.encode() if body else None,
                headers=self._headers(method, path, body),
                method=method.upper(),
            )
            try:
                with self._opener.open(req, timeout=20) as res:
                    return json.loads(res.read().decode())
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode(errors="replace")
                if attempt == 0 and self._sync_clock_from_error(raw):
                    continue
                raise ExchangeError(f"HTTP {exc.code}: {raw}") from exc
            except urllib.error.URLError as exc:
                raise ExchangeError(f"network error: {exc}") from exc

        raise ExchangeError("request failed after clock synchronization")

    def _sync_clock_from_error(self, raw):
        if "timestamp_too_far" not in raw:
            return False
        match = re.search(r"current time unixMilli (\d+)", raw)
        if not match:
            return False
        server_ms = int(match.group(1))
        self._clock_offset_ms = server_ms - int(time.time() * 1000) - 100
        return True

    def markets(self):
        return self.request("GET", "/v1/markets")

    def depth(self, market, depth=10):
        q = urllib.parse.urlencode({"market": market, "depth": depth})
        return self.request("GET", f"/v1/perps/depth?{q}")

    def candles(self, market, resolution, start, end):
        q = urllib.parse.urlencode({"market": market, "resolution": resolution, "from": int(start), "to": int(end)})
        return self.request("GET", f"/v1/perps/candles?{q}", auth=True)

    def account(self):
        return self.request("GET", "/v1/account", auth=True)

    def portfolio(self):
        return self.request("GET", "/v1/portfolio/summary", auth=True)

    def positions(self):
        return self.request("GET", "/v1/perps/positions", auth=True)

    def open_orders(self, market):
        return self.orders(market, status="open")

    def orders(self, market, status=None, limit=1000):
        params = {"market": market, "limit": limit}
        if status:
            params["status"] = status
        q = urllib.parse.urlencode(params)
        return self.request("GET", f"/v1/perps/orders?{q}", auth=True)

    def create_order(self, payload):
        return self.request("POST", "/v1/perps/orders", payload, auth=True)

    def cancel_all(self, market=None):
        path = "/v1/perps/orders"
        if market:
            path += "?" + urllib.parse.urlencode({"market": market})
        return self.request("DELETE", path, auth=True)

    def set_leverage(self, market, leverage):
        return self.request("POST", "/v1/perps/leverage", {"market": market, "leverage": str(leverage)}, auth=True)
