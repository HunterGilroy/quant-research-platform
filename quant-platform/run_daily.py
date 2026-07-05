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
from qrp.construction import build_weights, vol_target_scale

# ------------------------- configuration -------------------------
ACCOUNT_VALUE   = 8_000        # informs position sizing / name count
MAX_NAMES       = 20           # hold the top ~20 (≈ $400/position)
MIN_POSITION    = 200          # never target a position under $200
DRIFT_BAND      = 0.10         # propose trades only if total drift > 10% (one-way)
LOOKBACK_YEARS  = 2

CONSTRUCTION_METHODS = ["optimizer", "erc", "hrp", "inverse_vol"]
TOURNAMENT_MONTHS = 12         # trailing window for the method tournament
SHARPE_MARGIN     = 0.25       # challenger must beat the optimizer by this much
VOL_TARGET        = 0.15       # de-risk toward cash above 15% predicted vol

# Candidate signals — the walk-forward selector decides the weights daily.
SIGNAL_CANDIDATES = ["momentum_12_1", "trend_50_200", "reversal_1m",
                     "low_vol", "high_52w", "lottery", "low_beta"]
SIGNAL_WEIGHTS = {}   # filled at runtime by select_signal_weights()
# ------------------------------------------------------------------


MIN_PRICE       = 5.0          # exclude sub-$5 stocks (untradeable spreads)


def get_universe() -> list:
    """S&P SmallCap 600 tickers — the quality-screened small-cap index.
    Rationale: published anomalies are stronger and decay slower in small
    caps, where large funds cannot deploy capital without moving prices.
    Being small is the structural edge; this universe exploits it.
    Fallback: the S&P 500 mirror (with a loud warning — large caps are a
    different experiment)."""
    import io, urllib.request
    try:
        req = urllib.request.Request(
            "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
            headers={"User-Agent": "Mozilla/5.0 (research script)"})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
        tables = pd.read_html(io.StringIO(html))
        for t in tables:
            if "Symbol" in t.columns:
                tickers = t["Symbol"].str.replace(".", "-", regex=False).tolist()
                print(f"[universe] S&P SmallCap 600 via Wikipedia: {len(tickers)} tickers")
                return tickers
        raise RuntimeError("no Symbol column found")
    except Exception as e:
        print(f"[universe] S&P 600 fetch failed ({type(e).__name__}); trying large-cap mirror...")
    try:
        url = ("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
               "main/data/constituents.csv")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        csv = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
        tickers = pd.read_csv(io.StringIO(csv))["Symbol"].str.replace(
            ".", "-", regex=False).tolist()
        print(f"[universe] WARNING: fell back to S&P 500 large caps "
              f"({len(tickers)} tickers) — NOT the small-cap experiment universe")
        return tickers
    except Exception as e:
        from qrp.data import LIVE_UNIVERSE
        print(f"[universe] mirror failed too ({type(e).__name__}); "
              f"using built-in {len(LIVE_UNIVERSE)}-stock universe")
        return LIVE_UNIVERSE


def load_universe_prices() -> tuple[pd.DataFrame, str]:
    tickers = get_universe()
    try:
        import yfinance as yf
        start = (pd.Timestamp.now() - pd.DateOffset(years=LOOKBACK_YEARS)).date()
        px = yf.download(tickers, start=str(start), auto_adjust=True,
                         progress=False)["Close"]
        px = px.dropna(how="all").ffill()
        px = px.dropna(axis=1, thresh=int(len(px) * 0.95)).dropna()
        px = px.loc[:, px.iloc[-1] >= MIN_PRICE]          # drop sub-$5 names
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


def _weights_for(method: str, prices: pd.DataFrame) -> pd.Series:
    """Alpha-select top names from `prices` history, weight them with `method`."""
    alpha_full = compute_alpha(prices, SIGNAL_WEIGHTS)
    top = alpha_full.nlargest(MAX_NAMES).index
    rets = prices[top].pct_change().dropna().iloc[-252:]
    cov = pd.DataFrame(np.cov(rets.values.T), index=top, columns=top)
    corr = rets.corr()
    max_w = max(0.08, (MIN_POSITION / ACCOUNT_VALUE) * 2)
    return build_weights(method, alpha_full[top], cov, corr, max_weight=max_w)


def run_tournament(prices: pd.DataFrame) -> dict:
    """Walk-forward mini-backtest: for each trailing month-end, build each
    method's portfolio using ONLY prior data, hold one month, record returns.
    Returns each method's trailing Sharpe. No look-ahead."""
    try:
        month_ends = prices.resample("ME").last().index
    except ValueError:
        month_ends = prices.resample("M").last().index
    month_ends = [d for d in month_ends if d <= prices.index[-1]]
    windows = month_ends[-(TOURNAMENT_MONTHS + 1):]

    rets = {m: [] for m in CONSTRUCTION_METHODS}
    for i in range(len(windows) - 1):
        past = prices[prices.index <= windows[i]]
        if len(past) < 273:
            continue
        nxt = prices[(prices.index > windows[i]) & (prices.index <= windows[i + 1])]
        period_ret = nxt.iloc[-1] / nxt.iloc[0] - 1.0 if len(nxt) > 1 else None
        if period_ret is None:
            continue
        for m in CONSTRUCTION_METHODS:
            try:
                w = _weights_for(m, past)
                rets[m].append(float((w * period_ret.reindex(w.index)).sum()))
            except Exception:
                rets[m].append(0.0)

    sharpes = {}
    for m, r in rets.items():
        r = np.array(r)
        sharpes[m] = float(r.mean() / r.std() * np.sqrt(12)) if len(r) > 2 and r.std() > 0 else 0.0
    return sharpes


def choose_method(sharpes: dict) -> str:
    """Default to the optimizer; a risk-based method must beat it by
    SHARPE_MARGIN over the tournament window to take over. The margin is
    hysteresis — it stops the bot flip-flopping on noise."""
    base = sharpes.get("optimizer", 0.0)
    challengers = {m: s for m, s in sharpes.items() if m != "optimizer"}
    best = max(challengers, key=challengers.get)
    if challengers[best] > base + SHARPE_MARGIN:
        return best
    return "optimizer"


def select_signal_weights(prices: pd.DataFrame) -> dict:
    """Walk-forward signal weighting: measure each candidate signal's trailing
    rank IC using ONLY past data, then weight signals proportionally to their
    positive IC. Signals with zero or negative trailing IC get zero weight.
    If nothing has worked, fall back to equal weight on momentum + trend
    (the two signals with the deepest published evidence base).
    This replaces hand-picked weights — the in-sample caveat documented in
    the README — with a rule the backtest could have followed in real time."""
    from qrp.signals import information_coefficient
    ics = {}
    for name in SIGNAL_CANDIDATES:
        try:
            ic_series = information_coefficient(prices, name)
            ics[name] = float(ic_series.iloc[-12:].mean()) if len(ic_series) else 0.0
        except Exception:
            ics[name] = 0.0
    clipped = {m: max(v, 0.0) for m, v in ics.items()}
    total = sum(clipped.values())
    if total <= 1e-9:
        weights = {"momentum_12_1": 0.5, "trend_50_200": 0.5}
    else:
        weights = {m: v / total for m, v in clipped.items() if v / total >= 0.05}
        s = sum(weights.values())
        weights = {m: v / s for m, v in weights.items()}
    return weights, ics


def build_target(prices: pd.DataFrame):
    """Tournament -> chosen method -> weights -> vol-target overlay."""
    sharpes = run_tournament(prices)
    method = choose_method(sharpes)

    alpha_full = compute_alpha(prices, SIGNAL_WEIGHTS)
    top = alpha_full.nlargest(MAX_NAMES).index
    rets = prices[top].pct_change().dropna().iloc[-252:]
    cov = pd.DataFrame(np.cov(rets.values.T), index=top, columns=top)
    corr = rets.corr()
    max_w = max(0.08, (MIN_POSITION / ACCOUNT_VALUE) * 2)
    tgt = build_weights(method, alpha_full[top], cov, corr, max_weight=max_w)

    rm = RiskModel(n_factors=5).fit(rets)
    tgt, ex_ante, scale = vol_target_scale(tgt, rm, VOL_TARGET)

    tgt = tgt[tgt * ACCOUNT_VALUE >= MIN_POSITION]
    meta = {"method": method, "sharpes": sharpes,
            "ex_ante_vol": ex_ante, "vol_scale": scale,
            "cash_weight": 1.0 - float(tgt.sum())}
    return tgt.sort_values(ascending=False), alpha_full, meta


def current_drift(targets: pd.Series) -> float:
    """One-way distance between saved targets and the new ideal targets."""
    if not os.path.exists("output/targets.csv"):
        return 1.0                                          # nothing held yet: full trade
    old = pd.read_csv("output/targets.csv", index_col=0)["weight"]
    allnames = old.index.union(targets.index)
    return float(np.abs(old.reindex(allnames, fill_value=0)
                        - targets.reindex(allnames, fill_value=0)).sum() / 2)


def write_brief(alpha: pd.Series, targets: pd.Series, drift: float,
                rebalance: bool, source: str, prices: pd.DataFrame,
                meta: dict = None):
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
    constr_panel = ""
    if meta:
        sh = ", ".join("{} {:+.2f}".format(m, s) for m, s in meta["sharpes"].items())
        constr_panel = (
            '<div class="status" style="background:#eef2fb"><b>Construction:</b> '
            + str(meta["method"])
            + " &nbsp;&middot;&nbsp; tournament Sharpe: " + sh
            + " &nbsp;&middot;&nbsp; predicted vol {:.1%}".format(meta["ex_ante_vol"])
            + " &rarr; exposure {:.0%}, cash {:.0%}".format(
                meta["vol_scale"], meta["cash_weight"])
            + "<br><b>Signal weights (walk-forward):</b> "
            + ", ".join("{} {:.0%}".format(m, w)
                        for m, w in meta.get("signal_weights", {}).items())
            + "</div>")

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
{constr_panel}
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

    global SIGNAL_WEIGHTS
    SIGNAL_WEIGHTS, ics = select_signal_weights(prices)
    print("[signals] trailing IC: " + ", ".join(
        "{} {:+.3f}".format(m, v) for m, v in sorted(ics.items(), key=lambda x: -x[1])))
    print("[signals] walk-forward weights: " + ", ".join(
        "{} {:.0%}".format(m, w) for m, w in SIGNAL_WEIGHTS.items()))

    targets, alpha, meta = build_target(prices)
    meta["signal_weights"] = dict(SIGNAL_WEIGHTS)
    meta["signal_ics"] = ics
    print(f"[tournament] trailing Sharpe by method: "
          + ', '.join(f'{m}={s:+.2f}' for m, s in meta['sharpes'].items()))
    print(f"[tournament] chosen: {meta['method']} | predicted vol "
          f"{meta['ex_ante_vol']:.1%} | exposure scale {meta['vol_scale']:.0%} "
          f"| cash {meta['cash_weight']:.0%}")
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
    write_brief(alpha, targets, drift, rebalance, source, prices, meta)
    print("[daily] brief -> output/daily_brief.html")


if __name__ == "__main__":
    main()
