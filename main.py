import argparse
import math
import random
import time
from datetime import date, datetime
from pathlib import Path

from exchange import ExchangeError, OndoExchange
from logger import log_event, setup_logger
from market_data import MarketData
from order_manager import OrderManager
from paper import PaperBroker
from risk_manager import RiskManager
from state import StateStore
from strategy import LowLossVolumeMaker
from utils import D, dstr, load_env, load_json


def position_notional_from_paper(paper, market, mid):
    pos = paper.positions().get(market, {})
    qty = D(pos.get("quantity", "0"))
    long_notional = max(qty, D("0")) * mid
    short_notional = abs(min(qty, D("0"))) * mid
    return long_notional, short_notional


def live_position_notional(exchange, market):
    long_notional = D("0")
    short_notional = D("0")
    try:
        for pos in exchange.positions().get("result", []):
            if pos.get("market") != market:
                continue
            notional = D(pos.get("notionalValue", "0"))
            if pos.get("direction") == "long":
                long_notional += notional
            elif pos.get("direction") == "short":
                short_notional += notional
    except ExchangeError:
        pass
    return long_notional, short_notional


def live_positions(exchange, market):
    try:
        return [p for p in exchange.positions().get("result", []) if p.get("market") == market and p.get("direction") in {"long", "short"}]
    except ExchangeError:
        return []


def fill_notional(order):
    filled_cost = order.get("filledCost")
    if filled_cost not in (None, ""):
        return abs(D(filled_cost))
    filled_size = D(order.get("filledSize") or order.get("executedSize") or "0")
    price = D(order.get("averageFillPrice") or order.get("avgFillPrice") or order.get("price") or "0")
    return abs(filled_size * price)


def is_today_fill(order):
    ts = order.get("filledAt") or order.get("createdAt")
    if not ts:
        return False
    try:
        filled_day = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().date()
    except ValueError:
        return False
    return filled_day == date.today()


def sync_live_daily_volume(exchange, state_store, market, logger):
    state = state_store.state
    counted = state.setdefault("counted_live_fills", {})
    try:
        live_orders = exchange.orders(market).get("result", [])
    except ExchangeError as exc:
        log_event(logger, "volume_sync_error", error=str(exc))
        return

    added = D("0")
    realized_total = D("0")
    for order in live_orders:
        if order.get("market") != market or not is_today_fill(order):
            continue
        realized_total += D(order.get("realizedPnl") or "0")
        order_id = order.get("orderId") or order.get("clientOrderId")
        if not order_id:
            continue
        notional = fill_notional(order)
        previous = D(counted.get(order_id, "0"))
        if notional > previous:
            added += notional - previous
            counted[order_id] = dstr(notional)

    if added > 0:
        state["daily_volume_usdc"] = dstr(D(state.get("daily_volume_usdc", "0")) + added)
        log_event(logger, "live_volume_sync", added_volume=dstr(added), daily_volume=state["daily_volume_usdc"])
    state["daily_realized_pnl_usdc"] = dstr(realized_total)


def place_reduce_orders(config, orders, market, mid, paper, exchange):
    tp = D(config["take_profit_min_pct"])
    sl = D(config["stop_loss_min_pct"])
    if exchange.mode == "paper":
        pos = paper.positions().get(market)
        if not pos:
            return
        qty = D(pos.get("quantity", "0"))
        if qty > 0:
            orders.place_limit(market, "sell", mid * (D("1") + tp), abs(qty), True, "long_tp")
            orders.place_limit(market, "sell", mid * (D("1") - sl), abs(qty), True, "long_sl")
        elif qty < 0:
            orders.place_limit(market, "buy", mid * (D("1") - tp), abs(qty), True, "short_tp")
            orders.place_limit(market, "buy", mid * (D("1") + sl), abs(qty), True, "short_sl")
        return

    for pos in live_positions(exchange, market):
        qty = D(pos.get("netQuantity", "0"))
        if qty <= 0:
            continue
        entry = D(pos.get("averageEntryPrice") or pos.get("markPrice") or mid)
        if pos.get("direction") == "long":
            orders.place_limit(market, "sell", entry * (D("1") + tp), qty, True, "long_tp")
            orders.place_limit(market, "sell", entry * (D("1") - sl), qty, True, "long_sl")
        elif pos.get("direction") == "short":
            orders.place_limit(market, "buy", entry * (D("1") - tp), qty, True, "short_tp")
            orders.place_limit(market, "buy", entry * (D("1") + sl), qty, True, "short_sl")


def equity_value(config, exchange, paper):
    if exchange.mode == "paper":
        return paper.equity()
    try:
        summary = exchange.portfolio().get("result", {})
        return D(summary.get("marginBalance") or summary.get("totalAccountValue") or config["paper_starting_equity_usdc"])
    except ExchangeError:
        return D(config["paper_starting_equity_usdc"])


def exchange_leverage_value(config):
    return "10"


def loop_sleep_seconds(config):
    min_seconds = float(config.get("random_loop_interval_min_seconds", config["loop_interval_seconds"]))
    max_seconds = float(config.get("random_loop_interval_max_seconds", config["loop_interval_seconds"]))
    if max_seconds < min_seconds:
        max_seconds = min_seconds
    return random.uniform(min_seconds, max_seconds)


def sleep_between_loops(config, logger):
    delay = loop_sleep_seconds(config)
    log_event(logger, "loop_sleep", seconds=round(delay, 2))
    time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description="Low Loss Volume Maker")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    load_env()
    config = load_json(args.config)
    logger = setup_logger(config["log_path"])
    state_store = StateStore(config["state_path"])
    state = state_store.load()
    mode = config.get("mode", "paper")
    exchange = OndoExchange(config["api_base"], mode)
    paper = PaperBroker(state, config["paper_starting_equity_usdc"])
    market_data = MarketData(exchange, config["market"])
    meta = market_data.sync_market_meta()
    orders = OrderManager(config, exchange, paper, meta, logger)
    risk = RiskManager(config, state_store, logger)
    strategy = LowLossVolumeMaker(config)

    log_event(logger, "startup", mode=mode, market=config["market"])
    if not risk.leverage_allowed():
        log_event(logger, "blocked", reason="leverage_over_limit", leverage=config["default_leverage"])
        return
    if mode == "live":
        lev = exchange_leverage_value(config)
        result = exchange.set_leverage(config["market"], lev)
        log_event(logger, "set_exchange_leverage", target=config["default_leverage"], exchange_leverage=lev, result=result)
    orders.cancel_stale_or_all(config["market"], cancel_all=False)

    while True:
        try:
            snap = market_data.snapshot()
            if mode == "paper":
                fills = paper.simulate_fills(config["market"], snap["best_bid"], snap["best_ask"])
                for fill in fills:
                    log_event(logger, "paper_fill", fill=fill)
            else:
                sync_live_daily_volume(exchange, state_store, config["market"], logger)
            equity = equity_value(config, exchange, paper)
            long_notional, short_notional = (
                position_notional_from_paper(paper, config["market"], snap["mid"])
                if mode == "paper"
                else live_position_notional(exchange, config["market"])
            )
            decisions = [
                risk.pause_decision(),
                risk.spread_decision(snap["spread_pct"]),
                risk.consecutive_loss_decision(),
                risk.volatility_decision(market_data.one_min_volatility_ratio()),
                risk.target_volume_decision(),
                risk.exposure_decision(equity, long_notional, short_notional),
            ]
            decision = risk.combine(decisions)
            log_event(
                logger,
                "risk_check",
                spread_pct=snap["spread_pct"],
                decision=decision.reason,
                allow_new=decision.allow_new,
                reduce_only=decision.reduce_only,
                daily_volume=state.get("daily_volume_usdc"),
            )

            if decision.reduce_only:
                orders.cancel_all(config["market"], decision.reason)
                place_reduce_orders(config, orders, config["market"], snap["mid"], paper, exchange)
            elif decision.allow_new:
                order_state = orders.cancel_stale_or_all(config["market"])
                if order_state == "active":
                    log_event(logger, "skip_new_quotes", reason="open_orders_still_fresh")
                    state_store.save()
                    if args.once:
                        break
                    sleep_between_loops(config, logger)
                    continue
                place_reduce_orders(config, orders, config["market"], snap["mid"], paper, exchange)
                plan = strategy.quote_plan(snap, equity, decision.size_multiplier)
                size = plan["order_notional"] / snap["mid"]
                min_size = D(meta.get("baseIncrement", "0"))
                min_notional = min_size * snap["mid"]
                direction_limit = equity * D(config["max_direction_exposure_pct_equity"])
                if config.get("allow_exchange_min_size") and min_size > 0 and D("0") < size < min_size:
                    if min_notional <= direction_limit:
                        log_event(
                            logger,
                            "upsize_to_exchange_minimum",
                            original_size=size,
                            min_size=min_size,
                            min_notional=min_notional,
                            direction_limit=direction_limit,
                        )
                        size = min_size
                    else:
                        log_event(
                            logger,
                            "skip_below_exchange_minimum",
                            original_size=size,
                            min_size=min_size,
                            min_notional=min_notional,
                            direction_limit=direction_limit,
                        )
                        size = D("0")
                if long_notional <= equity * D(config["max_direction_exposure_pct_equity"]):
                    orders.place_limit(config["market"], "buy", plan["long_entry_price"], size, False, "long_entry")
                if short_notional <= equity * D(config["max_direction_exposure_pct_equity"]):
                    orders.place_limit(config["market"], "sell", plan["short_entry_price"], size, False, "short_entry")
            else:
                orders.cancel_all(config["market"], decision.reason)

            state_store.save()
        except Exception as exc:
            state["last_error"] = str(exc)
            state_store.save()
            log_event(logger, "error", error=str(exc))
        if args.once:
            break
        sleep_between_loops(config, logger)


if __name__ == "__main__":
    main()
