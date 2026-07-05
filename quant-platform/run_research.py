"""
run_research.py — The research pipeline, one command.

  data -> signal ICs -> event-driven backtest (signals + risk model +
  optimizer) -> HTML research report -> target portfolio for the live loop.

Usage:  python run_research.py
Outputs: output/research_report.html, output/targets.csv, output/prices_latest.csv
"""
import pandas as pd
from qrp.data import load_prices
from qrp.signals import information_coefficient, REGISTRY
from qrp.backtest import run_backtest, perf_stats
from qrp.report import generate_report

SIGNAL_WEIGHTS = {          # the alpha blend — edit freely
    "momentum_12_1": 0.40,
    "trend_50_200":  0.25,
    "low_vol":       0.20,
    "reversal_1m":   0.15,
}

def main():
    prices, source = load_prices(start="2015-01-01")

    print("[research] measuring signal ICs (walk-forward)...")
    ic = pd.DataFrame({name: information_coefficient(prices, name)
                       for name in SIGNAL_WEIGHTS})
    print(ic.mean().round(4).to_string())

    print("[research] running event-driven backtest...")
    bt = run_backtest(prices, SIGNAL_WEIGHTS)
    stats = perf_stats(bt["returns"], bt["benchmark"])
    for k, v in stats.items():
        print(f"  {k:<20s} {v: .3f}")
    print(f"  {'Cost drag':<20s} {bt['cost_total']: .3%}")

    path = generate_report(bt, stats, ic, source)
    print(f"[research] report -> {path}")

    bt["final_weights"].to_csv("output/targets.csv", header=["weight"])
    prices.iloc[-1].to_csv("output/prices_latest.csv", header=["price"])
    print("[research] targets -> output/targets.csv  (consumed by run_live.py)")

if __name__ == "__main__":
    main()
