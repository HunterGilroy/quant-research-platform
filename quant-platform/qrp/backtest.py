"""
qrp.backtest — Event-driven walk-forward backtester.

The research loop, exactly as run inside a systematic fund:

  for each rebalance date (monthly):
      1. take ONLY data available strictly before that date   (no look-ahead)
      2. compute the combined alpha signal                    (qrp.signals)
      3. fit the risk model on the trailing window            (qrp.risk_model)
      4. solve the constrained portfolio                      (qrp.optimizer)
      5. pay transaction costs on the trades
  between rebalances, weights drift with returns.

Outputs everything the report needs: daily returns, weight history, turnover,
ex-ante risk decomposition at each rebalance, and cumulative cost drag.
"""
import numpy as np
import pandas as pd

from .signals import compute_alpha
from .risk_model import RiskModel
from .optimizer import solve_portfolio

TRADING_DAYS = 252


def run_backtest(prices: pd.DataFrame, signal_weights: dict,
                 lookback: int = 252, tc_bps: float = 10.0,
                 risk_aversion: float = 8.0, turnover_penalty: float = 1.5,
                 max_weight: float = 0.08, n_factors: int = 5) -> dict:
    rets = prices.pct_change().dropna()
    try:
        rebal = rets.resample("ME").last().index
    except ValueError:
        rebal = rets.resample("M").last().index

    n = rets.shape[1]
    w = np.zeros(n)
    port = pd.Series(0.0, index=rets.index)
    weights_hist, turnover_hist, risk_hist = {}, {}, {}
    cost_total, ptr = 0.0, 0
    dates = rets.index

    for t, date in enumerate(dates):
        if ptr < len(rebal) and date > rebal[ptr]:
            ptr += 1
            if t >= max(lookback, 273):                      # need history for 12-1 momentum
                px_win = prices.iloc[:t]                     # strictly past prices
                ret_win = rets.iloc[t - lookback:t]
                alpha = compute_alpha(px_win, signal_weights)
                rm = RiskModel(n_factors).fit(ret_win)
                w_new = solve_portfolio(alpha, rm.covariance(),
                                        w_prev=w if w.sum() > 0 else None,
                                        risk_aversion=risk_aversion,
                                        turnover_penalty=turnover_penalty,
                                        max_weight=max_weight)
                trade = np.abs(w_new - w).sum() / 2.0
                cost = 2 * trade * tc_bps / 1e4
                cost_total += cost
                w = w_new
                weights_hist[date] = w.copy()
                turnover_hist[date] = trade
                risk_hist[date] = rm.portfolio_risk(w)
                port.iloc[t] = w @ rets.iloc[t].values - cost
                w = w * (1 + rets.iloc[t].values); w = w / w.sum()
                continue
        port.iloc[t] = w @ rets.iloc[t].values
        if w.sum() > 0:
            w = w * (1 + rets.iloc[t].values); w = w / w.sum()

    bench = rets.mean(axis=1)                                # equal-weight universe benchmark
    return {
        "returns": port, "benchmark": bench,
        "weights": pd.DataFrame(weights_hist, index=prices.columns).T,
        "turnover": pd.Series(turnover_hist),
        "risk": pd.DataFrame(risk_hist).T,
        "cost_total": cost_total,
        "final_weights": pd.Series(w, index=prices.columns),
    }


def perf_stats(r: pd.Series, bench: pd.Series = None) -> dict:
    r = r[r.index >= r.ne(0).idxmax()]
    ann = (1 + r).prod() ** (TRADING_DAYS / len(r)) - 1
    vol = r.std() * np.sqrt(TRADING_DAYS)
    curve = (1 + r).cumprod()
    dd = (curve / curve.cummax() - 1).min()
    out = {"Ann. Return": ann, "Ann. Vol": vol,
           "Sharpe": ann / vol if vol > 0 else np.nan, "Max Drawdown": dd}
    if bench is not None:
        b = bench.reindex(r.index)
        active = r - b
        te = active.std() * np.sqrt(TRADING_DAYS)
        ir = (active.mean() * TRADING_DAYS) / te if te > 0 else np.nan
        out.update({"Active Return": active.mean() * TRADING_DAYS,
                    "Tracking Error": te, "Information Ratio": ir})
    return out
