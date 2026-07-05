"""
run_live.py — One paper-trading cycle, one command.

Reads the latest targets from the research run, connects to the broker
(Alpaca paper account if ALPACA_API_KEY / ALPACA_SECRET_KEY are set,
otherwise the built-in simulator), and trades the account to target.

Usage:   python run_live.py
Repeat:  run it any time — it is idempotent. Schedule with cron for autopilot.
"""
import pandas as pd
from qrp.broker import get_broker
from qrp.live import run_cycle

def main():
    targets = pd.read_csv("output/targets.csv", index_col=0)["weight"]
    prices = pd.read_csv("output/prices_latest.csv", index_col=0)["price"]
    broker = get_broker()
    rec = run_cycle(broker, targets, prices)
    print(f"[live] equity ${rec['equity_before']:,.2f} -> ${rec['equity_after']:,.2f}")
    print(f"[live] {rec['n_trades']} orders submitted toward {rec['n_targets']} targets")
    for f in rec["fills"][:8]:
        print("   ", f)
    if rec["n_trades"] > 8:
        print(f"    ... and {rec['n_trades'] - 8} more (see output/live_log.jsonl)")

if __name__ == "__main__":
    main()
