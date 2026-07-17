"""
run_risk_check.py — Intraday DEFENSIVE risk check. Not a trading strategy.

Institutional systems use intraday frequency for defense, not offense: this
script runs midday, looks at today's move in every held position, and acts
only if something is genuinely broken.

Rules (in order):
  1. Any single position down more than POSITION_STOP today  -> liquidate it.
  2. Portfolio down more than PORTFOLIO_ALERT today           -> log an alert
     (visible in the committed risk log); no forced action.
  3. Otherwise: do nothing, print "all clear", exit.

It never buys, never adds risk, never rebalances. Offense stays with the
daily pipeline; this is the smoke detector.
"""
import json
import os
from datetime import datetime, timezone

import pandas as pd

from qrp.broker import get_broker
from qrp.tradelog import log_decision, log_trade

POSITION_STOP   = -0.15     # single-name intraday stop-out threshold
PORTFOLIO_ALERT = -0.05     # portfolio-level alert threshold
LOG_PATH        = "output/risk_log.jsonl"


def todays_moves(symbols: list) -> pd.Series:
    """Percent move from yesterday's close to the latest price, per symbol.
    Live via yfinance; offline falls back to zeros (no false alarms)."""
    if not symbols:
        return pd.Series(dtype=float)
    try:
        import yfinance as yf
        px = yf.download(symbols, period="5d", auto_adjust=True,
                         progress=False)["Close"]
        if isinstance(px, pd.Series):
            px = px.to_frame(symbols[0])
        px = px.ffill().dropna(how="all")
        return (px.iloc[-1] / px.iloc[-2] - 1.0).reindex(symbols).fillna(0.0)
    except Exception as e:
        print(f"[risk] price fetch unavailable ({type(e).__name__}); no action taken")
        return pd.Series(0.0, index=symbols)


def run_check(broker, moves: pd.Series) -> dict:
    positions = broker.get_positions()
    record = {"ts": datetime.now(timezone.utc).isoformat(),
              "checked": len(positions), "stops": [], "alerts": []}
    if not positions:
        record["status"] = "no positions"
        return record

    # latest prices for sizing sell orders
    last_prices = {}
    try:
        last_prices = pd.read_csv("output/prices_latest.csv", index_col=0)["price"].to_dict()
    except Exception:
        pass

    # Rule 1: single-name stop-out
    for sym, pos in positions.items():
        mv = float(moves.get(sym, 0.0))
        if mv <= POSITION_STOP:
            ref = float(last_prices.get(sym, pos.avg_price)) * (1 + mv)
            fill = broker.submit_order(sym, pos.qty, "sell", ref)
            record["stops"].append({"symbol": sym, "move": round(mv, 4), "fill": fill})
            acct = broker.get_account()
            log_trade(sym, "sell", pos.qty * ref, ref, "submitted",
                      fill.get("order_id", "sim"), "",
                      acct.get("equity", ""), acct.get("cash", ""),
                      f"rule: single-name stop-out — {mv:+.1%} today breached "
                      f"the {POSITION_STOP:.0%} intraday stop", "midday risk check")
            print(f"[risk] STOP-OUT {sym}: {mv:+.1%} today -> position liquidated")

    # Rule 2: portfolio-level alert (equal-weight proxy of held names)
    port_move = float(moves.reindex(list(positions)).fillna(0).mean())
    if port_move <= PORTFOLIO_ALERT:
        record["alerts"].append({"portfolio_move": round(port_move, 4)})
        print(f"[risk] ALERT: portfolio proxy {port_move:+.1%} today "
              f"(threshold {PORTFOLIO_ALERT:.0%}) — review the account")

    broker.save()
    record["status"] = ("action taken" if record["stops"]
                        else "alert" if record["alerts"] else "all clear")
    return record


def main():
    broker = get_broker()
    positions = broker.get_positions()
    moves = todays_moves(list(positions))
    record = run_check(broker, moves)
    acct = broker.get_account()
    log_decision("risk_check", acct.get("equity", ""), acct.get("cash", ""),
                 "|".join(f"{s}:{p.qty:.2f}" for s, p in positions.items()) or "none",
                 len(record["stops"]), len(record["stops"]),
                 f"midday defensive check: {record['status']}",
                 "" if record["stops"] else
                 "no position breached the intraday stop; defense-only check adds no risk")
    os.makedirs("output", exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")
    print(f"[risk] {record['status']} | {record['checked']} positions checked "
          f"| {len(record['stops'])} stop-outs | {len(record['alerts'])} alerts")


if __name__ == "__main__":
    main()
