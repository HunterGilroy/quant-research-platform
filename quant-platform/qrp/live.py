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

from qrp.tradelog import log_decision, log_trade

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
        # Sells must work even if the symbol dropped out of today's universe
        # (delisted/renamed) — fall back to the position's average price as
        # the order reference so holdings can never be orphaned.
        ref = float(prices[s]) if s in prices.index else (
            positions[s].avg_price if diff < 0 and s in positions else 0.0)
        notional = abs(diff) * ref
        if notional >= MIN_TRADE_NOTIONAL and ref > 0:
            trades.append({"symbol": s, "qty": abs(diff),
                           "side": "buy" if diff > 0 else "sell",
                           "price": ref})
    trades.sort(key=lambda t: t["side"] != "sell")            # sells first

    fills, skipped = [], []
    for t in trades:
        tgt_w = float(targets.get(t["symbol"], 0.0))
        thesis = (f"rebalance to target weight {tgt_w:.1%}" if tgt_w > 0
                  else "exit: no longer in target portfolio")
        try:
            fill = broker.submit_order(t["symbol"], t["qty"], t["side"], t["price"])
            fills.append(fill)
            log_trade(t["symbol"], t["side"], t["qty"] * t["price"], t["price"],
                      "submitted", fill.get("order_id", "sim"), "",
                      equity, acct.get("cash", ""), thesis,
                      "rule-based rebalance toward optimizer targets")
        except Exception as e:
            # One untradeable symbol must never sink the whole rebalance.
            # Typical cause: a stale index constituent (delisted/renamed).
            skipped.append({"symbol": t["symbol"], "side": t["side"],
                            "reason": str(e)[:160]})
            log_trade(t["symbol"], t["side"], t["qty"] * t["price"], t["price"],
                      "rejected_by_broker", "", str(e)[:160],
                      equity, acct.get("cash", ""), thesis, "")
            print(f"[live] SKIPPED {t['symbol']} ({t['side']}): "
                  f"{type(e).__name__} — order rejected, continuing")
    broker.save()

    # Research CSV: one decision row per cycle — including no-trade cycles.
    log_decision(
        "scheduled_rebalance", equity, acct.get("cash", ""),
        "|".join(f"{sym}:{p.qty:.2f}" for sym, p in positions.items()) or "none",
        len(trades), len(fills),
        f"rebalance to {len(targets)} targets",
        "" if trades else ("portfolio already at target — every diff below "
                           f"the ${MIN_TRADE_NOTIONAL:.0f} dust threshold"))

    record = {"ts": datetime.now(timezone.utc).isoformat(),
              "equity_before": equity, "n_targets": len(targets),
              "n_trades": len(fills), "n_skipped": len(skipped),
              "fills": fills, "skipped": skipped,
              "equity_after": broker.get_account()["equity"]}
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record
