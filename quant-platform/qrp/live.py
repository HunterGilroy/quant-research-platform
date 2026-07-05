"""
qrp.live — The live paper-trading cycle.

One cycle = what a production system does at each rebalance:

  1. Load the latest TARGET portfolio (written by run_research.py).
  2. Ask the broker for current account equity and positions.
  3. Convert target weights into target share quantities at current prices.
  4. Diff targets vs. holdings -> a trade list (skipping dust trades).
  5. Submit orders (sells first, freeing cash for buys).
  6. Log everything and persist state.

Run it manually (python run_live.py) or schedule it — e.g. weekdays at
15:45 ET via cron / GitHub Actions. The loop is idempotent: run it twice
and the second run finds nothing to trade.
"""
import json
import os
from datetime import datetime, timezone

import pandas as pd

MIN_TRADE_NOTIONAL = 25.0     # skip trades smaller than $25 (dust)


def run_cycle(broker, targets: pd.Series, prices: pd.Series,
              log_path: str = "output/live_log.jsonl") -> dict:
    targets = targets[targets > 1e-6]
    acct = broker.get_account()
    equity = acct["equity"]
    positions = broker.get_positions()
    broker.mark_prices(prices.to_dict())

    # target shares
    tgt_qty = {s: (w * equity) / prices[s] for s, w in targets.items() if s in prices.index}
    cur_qty = {s: p.qty for s, p in positions.items()}

    trades = []
    for s in sorted(set(tgt_qty) | set(cur_qty)):
        diff = tgt_qty.get(s, 0.0) - cur_qty.get(s, 0.0)
        notional = abs(diff) * float(prices.get(s, 0.0))
        if notional >= MIN_TRADE_NOTIONAL and s in prices.index:
            trades.append({"symbol": s, "qty": abs(diff),
                           "side": "buy" if diff > 0 else "sell",
                           "price": float(prices[s])})
    trades.sort(key=lambda t: t["side"] != "sell")            # sells first

    fills = [broker.submit_order(t["symbol"], t["qty"], t["side"], t["price"])
             for t in trades]
    broker.save()

    record = {"ts": datetime.now(timezone.utc).isoformat(),
              "equity_before": equity, "n_targets": len(targets),
              "n_trades": len(fills), "fills": fills,
              "equity_after": broker.get_account()["equity"]}
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record
