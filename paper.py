import time
import uuid

from utils import D, dstr


class PaperBroker:
    def __init__(self, state, starting_equity):
        self.state = state
        self.starting_equity = D(starting_equity)

    def equity(self):
        return self.starting_equity + D(self.state.get("daily_realized_pnl_usdc", "0"))

    def open_orders(self):
        return list(self.state.get("paper_orders", {}).values())

    def positions(self):
        return self.state.setdefault("paper_positions", {})

    def place_order(self, payload):
        order_id = "paper_" + uuid.uuid4().hex[:16]
        order = {
            "orderId": order_id,
            "clientOrderId": payload.get("clientOrderId"),
            "market": payload["market"],
            "side": payload["side"],
            "price": payload.get("price"),
            "size": payload.get("size"),
            "type": payload.get("type", "limit"),
            "reduceOnly": bool(payload.get("reduceOnly", False)),
            "createdAt": time.time(),
            "status": "open",
        }
        self.state.setdefault("paper_orders", {})[order_id] = order
        return {"success": True, "result": order}

    def cancel_all(self, market=None):
        orders = self.state.setdefault("paper_orders", {})
        for order in orders.values():
            if market is None or order.get("market") == market:
                order["status"] = "canceled"
        self.state["paper_orders"] = {k: v for k, v in orders.items() if v["status"] == "open"}
        return {"success": True}

    def simulate_fills(self, market, best_bid, best_ask):
        orders = list(self.state.setdefault("paper_orders", {}).items())
        positions = self.state.setdefault("paper_positions", {})
        filled = []
        for order_id, order in orders:
            if order["market"] != market:
                continue
            price = D(order["price"])
            should_fill = (order["side"] == "buy" and price >= best_ask) or (order["side"] == "sell" and price <= best_bid)
            if not should_fill:
                continue
            qty = D(order["size"])
            signed = qty if order["side"] == "buy" else -qty
            pos = D(positions.get(market, {}).get("quantity", "0"))
            new_pos = pos + signed
            positions[market] = {"quantity": dstr(new_pos), "mark": dstr(price)}
            notional = abs(qty * price)
            self.state["daily_volume_usdc"] = dstr(D(self.state.get("daily_volume_usdc", "0")) + notional)
            order["status"] = "fullyfilled"
            filled.append(order)
            self.state.setdefault("paper_fills", []).append({**order, "fillPrice": dstr(price), "fillTime": time.time()})
        self.state["paper_orders"] = {k: v for k, v in self.state["paper_orders"].items() if v["status"] == "open"}
        return filled

