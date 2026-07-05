"""
qrp.optimizer — Constrained portfolio construction.

Solves the canonical institutional mean-variance-cost problem:

    maximize   alpha' w  -  lambda * w' Sigma w  -  gamma * ||w - w_prev||_1
    subject to sum(w) = 1,  0 <= w_i <= max_weight

- alpha       : combined signal scores (from qrp.signals)
- lambda      : risk aversion (bigger = more diversified / lower risk)
- gamma       : turnover penalty (bigger = trade less; models t-costs)
- max_weight  : single-name concentration cap

The turnover penalty is the piece amateurs skip and professionals never do:
it makes the optimizer *reluctant* to trade unless the alpha justifies the cost.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize


def solve_portfolio(alpha: pd.Series, cov: pd.DataFrame,
                    w_prev: np.ndarray | None = None,
                    risk_aversion: float = 8.0,
                    turnover_penalty: float = 1.5,
                    max_weight: float = 0.08) -> np.ndarray:
    n = len(alpha)
    a = alpha.values
    S = cov.values * 252                      # annualize for sane lambda scaling
    if w_prev is None:
        w_prev = np.ones(n) / n
        gamma = 0.0                           # no penalty on the first build
    else:
        gamma = turnover_penalty

    # smooth |x| approximation keeps SLSQP happy
    eps = 1e-6
    def objective(w):
        util = a @ w - risk_aversion * (w @ S @ w) - gamma * np.sum(np.sqrt((w - w_prev) ** 2 + eps))
        return -util

    cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = [(0.0, max_weight)] * n
    res = minimize(objective, np.clip(w_prev, 0, max_weight), method="SLSQP",
                   bounds=bounds, constraints=cons,
                   options={"maxiter": 500, "ftol": 1e-10})
    w = np.clip(res.x, 0.0, max_weight)
    return w / w.sum()
