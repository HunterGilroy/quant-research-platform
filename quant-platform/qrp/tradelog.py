"""
qrp.tradelog — Research CSV logs for the head-to-head study.

Same columns as the AI bot's logs, so the two spreadsheets merge directly:

  trades.csv    — one row per order: what, how much, at what reference price,
                  and the rule-based rationale for the trade.
  decisions.csv — one row per cycle, including cycles with NO trades and the
                  rule that produced the no-trade outcome.
"""
import csv
import os
from datetime import datetime, timezone

OUT_DIR = "output"
TRADES_CSV = os.path.join(OUT_DIR, "trades.csv")
DECISIONS_CSV = os.path.join(OUT_DIR, "decisions.csv")

BOT_NAME = "Python"  # this side of the experiment

TRADE_COLS = [
    "timestamp_utc", "bot", "symbol", "side", "notional_usd", "est_price",
    "status", "order_id", "reject_reason", "equity_before", "cash_before",
    "thesis", "market_view",
]
DECISION_COLS = [
    "timestamp_utc", "bot", "woken_by", "equity", "cash", "open_positions",
    "trades_proposed", "trades_executed", "market_view", "no_trade_reason",
]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(path, cols, row):
    os.makedirs(OUT_DIR, exist_ok=True)
    is_new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if is_new:
            writer.writeheader()
        writer.writerow({c: row.get(c, "") for c in cols})


def log_trade(symbol, side, notional_usd, est_price, status, order_id,
              reject_reason, equity_before, cash_before, thesis, market_view=""):
    _append(TRADES_CSV, TRADE_COLS, {
        "timestamp_utc": _now(), "bot": BOT_NAME, "symbol": symbol,
        "side": side, "notional_usd": round(float(notional_usd), 2),
        "est_price": est_price, "status": status, "order_id": order_id,
        "reject_reason": reject_reason, "equity_before": equity_before,
        "cash_before": cash_before, "thesis": thesis, "market_view": market_view,
    })


def log_decision(woken_by, equity, cash, open_positions, trades_proposed,
                 trades_executed, market_view, no_trade_reason):
    _append(DECISIONS_CSV, DECISION_COLS, {
        "timestamp_utc": _now(), "bot": BOT_NAME, "woken_by": woken_by,
        "equity": equity, "cash": cash, "open_positions": open_positions,
        "trades_proposed": trades_proposed, "trades_executed": trades_executed,
        "market_view": market_view, "no_trade_reason": no_trade_reason,
    })
