"""
run_daily.py — Daily research scan over a large universe (S&P 500).

Designed for a small account: scans ~500 stocks, ranks all of them on the
signal blend, and maintains a CONCENTRATED target portfolio (top N names,
each position large enough to matter). Trades are only proposed when the
account has drifted from target beyond a band — daily research, disciplined
trading.

Usage:
    python run_daily.py            # research brief + (maybe) rebalance targets
    python run_live.py             # execute proposed trades on the paper account

Outputs:
    output/daily_brief.html        # today's ranked watchlist + portfolio status
    output/targets.csv             # ONLY refreshed when a rebalance is proposed
    output/prices_latest.csv
"""
import os
import numpy as np
import pandas as pd

from qrp.signals import compute_alpha, REGISTRY
from qrp.risk_model import RiskModel
from qrp.optimizer import solve_portfolio

# ------------------------- configuration -------------------------
ACCOUNT_VALUE   = 8_000        # informs position sizing / name count
MAX_NAMES       = 20           # hold the top ~20 (≈ $400/position)
MIN_POSITION    = 200          # never target a position under $200
DRIFT_BAND      = 0.10         # propose trades only if total drift > 10% (one-way)
LOOKBACK_YEARS  = 2

SIGNAL_WEIGHTS = {
    "momentum_12_1": 0.45,
    "trend_50_200":  0.30,
    "reversal_1m":   0.25,
}
# ------------------------------------------------------------------


def get_sp500_universe() -> list:
    """S&P 500 tickers: Wikipedia (browser-identified request), then a GitHub
    dataset mirror, then the built-in 40 as the last resort."""
    import io, urllib.request
    # source 1: Wikipedia, sending a browser User-Agent (it rejects anonymous bots)
    try:
        req = urllib.request.Request(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers={"User-Agent": "Mozilla/5.0 (research script)"})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
        tables = pd.read_html(io.StringIO(html))
        tickers = tables[0]["Symbol"].str.replace(".", "-", regex=False).tolist()
        print(f"[universe] S&P 500 via Wikipedia: {len(tickers)} tickers")
        return tickers
    except Exception as e:
        print(f"[universe] Wikipedia failed ({type(e).__name__}); trying mirror...")
    # source 2: maintained dataset mirror on GitHub
    try:
        url = ("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
               "main/data/constituents.csv")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        csv = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
        tickers = pd.read_csv(io.StringIO(csv))["Symbol"].str.replace(
            ".", "-", regex=False).tolist()
        print(f"[universe] S&P 500 via GitHub mirror: {len(tickers)} tickers")
        return tickers
    except Exception as e:
        from qrp.data import LIVE_UNIVERSE
        print(f"[universe] mirror failed too ({type(e).__name__}); "
              f"using built-in {len(LIVE_UNIVERSE)}-stock universe")
        return LIVE_UNIVERSE


def load_universe_prices() -> tuple[pd.DataFrame, str]:
    tickers = get_sp500_universe()
    try:
        import yfinance as yf
        start = (pd.Timestamp.now() - pd.DateOffset(years=LOOKBACK_YEARS)).date()
        px = yf.download(tickers, start=str(start), auto_adjust=True,
                         progress=False)["Close"]
        px = px.dropna(how="all").ffill()
        px = px.dropna(axis=1, thresh=int(len(px) * 0.95)).dropna()
        if px.shape[1] < 20:
            raise RuntimeError("too few tickers survived cleaning")
        print(f"[data] live: {px.shape[0]} days x {px.shape[1]} stocks")
        return px, "live"
    except Exception as e:
        from qrp.data import synthetic_universe
        print(f"[data] live unavailable ({type(e).__name__}); synthetic 500-stock universe")
        start = (pd.Timestamp.now() - pd.DateOffset(years=LOOKBACK_YEARS)).date()
        return synthetic_universe(n_stocks=500, start=str(start),
                                  end=str(pd.Timestamp.now().date())), "synthetic"


def build_target(prices: pd.DataFrame) -> pd.Series:
    """Rank the full universe, keep the top MAX_NAMES by alpha, then run the
    risk-aware optimizer on just those names."""
    alpha_full = compute_alpha(prices, SIGNAL_WEIGHTS)
    top = alpha_full.nlargest(MAX_NAMES).index

    rets = prices[top].pct_change().dropna().iloc[-252:]
    rm = RiskModel(n_factors=5).fit(rets)
    max_w = max(0.08, (MIN_POSITION / ACCOUNT_VALUE) * 2)   # sane cap for small accts
    w = solve_portfolio(alpha_full[top], rm.covariance(),
                        w_prev=None, max_weight=max_w)
    tgt = pd.Series(w, index=top)
    tgt = tgt[tgt * ACCOUNT_VALUE >= MIN_POSITION]          # drop sub-$200 dust
    return (tgt / tgt.sum()).sort_values(ascending=False), alpha_full


def current_drift(targets: pd.Series) -> float:
    """One-way distance between saved targets and the new ideal targets."""
    if not os.path.exists("output/targets.csv"):
        return 1.0                                          # nothing held yet: full trade
    old = pd.read_csv("output/targets.csv", index_col=0)["weight"]
    allnames = old.index.union(targets.index)
    return float(np.abs(old.reindex(allnames, fill_value=0)
                        - targets.reindex(allnames, fill_value=0)).sum() / 2)


def write_brief(alpha: pd.Series, targets: pd.Series, drift: float,
                rebalance: bool, source: str, prices: pd.DataFrame):
    top25 = alpha.nlargest(25)
    rows = "".join(
        f"<tr><td>{i+1}</td><td><b>{t}</b></td>"
        f"<td style='text-align:right'>{alpha[t]:+.2f}</td>"
        f"<td style='text-align:right'>{prices[t].iloc[-1]:,.2f}</td>"
        f"<td style='text-align:right'>{(targets.get(t, 0)*100):.1f}%</td>"
        f"<td style='text-align:right'>${targets.get(t, 0)*ACCOUNT_VALUE:,.0f}</td></tr>"
        for i, t in enumerate(top25.index))
    status = ("REBALANCE PROPOSED — run <code>python run_live.py</code>"
              if rebalance else
              f"No action: drift {drift:.1%} is inside the {DRIFT_BAND:.0%} band")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Daily Brief</title>
<style>body{{font-family:Georgia,serif;max-width:820px;margin:30px auto;color:#1a2033;padding:0 16px}}
h1{{color:#1E2761;border-bottom:3px solid #1E2761;padding-bottom:8px}}
table{{border-collapse:collapse;font-family:Arial;font-size:.9em;width:100%}}
td,th{{border:1px solid #d8dee9;padding:5px 10px}} th{{background:#1E2761;color:#fff}}
.status{{background:{'#eaf3ec' if not rebalance else '#fdf3e7'};padding:10px 14px;border-radius:6px;margin:14px 0}}
.meta{{color:#666;font-size:.9em}}</style></head><body>
<h1>Daily Research Brief</h1>
<p class="meta">{pd.Timestamp.now():%Y-%m-%d %H:%M} · universe: {prices.shape[1]} stocks ({source})
· account basis: ${ACCOUNT_VALUE:,} · holding top {len(targets)} names</p>
<div class="status"><b>Status:</b> {status}</div>
<h2>Top 25 by combined signal score</h2>
<table><tr><th>#</th><th>Ticker</th><th>Score</th><th>Last Px</th><th>Target Wt</th><th>Target $</th></tr>
{rows}</table>
<p class="meta">Signal blend: {SIGNAL_WEIGHTS}. Scores are cross-sectional z-scores — a
hypothesis about relative tendency, not a prediction. Research/paper-trading tool;
not investment advice.</p></body></html>"""
    os.makedirs("output", exist_ok=True)
    with open("output/daily_brief.html", "w") as f:
        f.write(html)


def main():
    prices, source = load_universe_prices()
    targets, alpha = build_target(prices)
    drift = current_drift(targets)
    rebalance = drift > DRIFT_BAND

    print(f"[daily] scanned {prices.shape[1]} stocks; "
          f"top name: {alpha.idxmax()} ({alpha.max():+.2f})")
    print(f"[daily] drift vs current targets: {drift:.1%} "
          f"({'REBALANCE' if rebalance else 'hold — inside band'})")

    if rebalance:
        targets.to_csv("output/targets.csv", header=["weight"])
        print(f"[daily] new targets written ({len(targets)} names) -> run_live.py will trade")
    prices.iloc[-1].to_csv("output/prices_latest.csv", header=["price"])
    write_brief(alpha, targets, drift, rebalance, source, prices)
    print("[daily] brief -> output/daily_brief.html")


if __name__ == "__main__":
    main()
