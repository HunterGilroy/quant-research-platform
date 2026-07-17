"""
qrp.construction — Portfolio construction methods (from Project 16).

Given a set of selected names (chosen by alpha), these decide HOW to weight
them. Four philosophies:

  optimizer    : alpha-aware mean-variance with turnover penalty (qrp.optimizer)
  erc          : Equal Risk Contribution — classic risk parity (Qian 2005)
  hrp          : Hierarchical Risk Parity (Lopez de Prado 2016), no inversion
  inverse_vol  : naive risk weighting, weights proportional to 1/sigma

All return long-only weights summing to 1 over the given names.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform

TRADING_DAYS = 252


# ---------------------------------------------------------------- ERC
def erc_weights(cov: pd.DataFrame) -> np.ndarray:
    """Equal Risk Contribution: every asset contributes the same share of
    portfolio volatility. Uses no expected returns at all."""
    S = cov.values
    n = S.shape[0]

    def risk_contrib(w):
        sigma = np.sqrt(w @ S @ w)
        return w * (S @ w) / max(sigma, 1e-12)

    def objective(w):
        rc = risk_contrib(w)
        return np.sum((rc - rc.mean()) ** 2) * 1e4

    cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    res = minimize(objective, np.ones(n) / n, method="SLSQP",
                   bounds=[(1e-6, 1.0)] * n, constraints=cons,
                   options={"maxiter": 800, "ftol": 1e-13})
    w = np.clip(res.x, 0, None)
    return w / w.sum()


# ---------------------------------------------------------------- HRP
def _quasi_diag(link: np.ndarray) -> list:
    link = link.astype(int)
    n = link.shape[0] + 1
    def rec(node):
        if node < n:
            return [node]
        return rec(link[node - n, 0]) + rec(link[node - n, 1])
    return rec(2 * n - 2)


def _cluster_var(S: np.ndarray, idx: list) -> float:
    sub = S[np.ix_(idx, idx)]
    ivp = 1.0 / np.diag(sub)
    ivp /= ivp.sum()
    return float(ivp @ sub @ ivp)


def hrp_weights(cov: pd.DataFrame, corr: pd.DataFrame) -> np.ndarray:
    """Hierarchical Risk Parity: cluster by correlation distance, then split
    the risk budget recursively down the tree. Never inverts the matrix, so
    it stays stable when covariances are noisy."""
    dist = np.sqrt(0.5 * (1.0 - corr.values).clip(min=0.0))
    link = linkage(squareform(dist, checks=False), method="single")
    order = _quasi_diag(link)
    S = cov.values
    w = pd.Series(1.0, index=order)
    clusters = [order]
    while clusters:
        clusters = [c[j:k] for c in clusters
                    for j, k in ((0, len(c) // 2), (len(c) // 2, len(c)))
                    if len(c) > 1]
        for i in range(0, len(clusters), 2):
            left, right = clusters[i], clusters[i + 1]
            vl, vr = _cluster_var(S, left), _cluster_var(S, right)
            alpha = 1.0 - vl / (vl + vr)
            w[left] *= alpha
            w[right] *= (1.0 - alpha)
    out = np.zeros(len(order))
    for pos, asset_idx in enumerate(w.index):
        out[asset_idx] = w.iloc[pos]
    return out / out.sum()


# ------------------------------------------------------- inverse vol
def inverse_vol_weights(cov: pd.DataFrame) -> np.ndarray:
    iv = 1.0 / np.sqrt(np.diag(cov.values))
    return iv / iv.sum()


# ------------------------------------------------- unified interface
def build_weights(method: str, alpha: pd.Series, cov: pd.DataFrame,
                  corr: pd.DataFrame, max_weight: float = 1.0) -> pd.Series:
    """One entry point for every construction method. `alpha` and `cov`
    must already be restricted to the selected names."""
    if method == "optimizer":
        from .optimizer import solve_portfolio
        w = solve_portfolio(alpha, cov, w_prev=None, max_weight=max_weight)
    elif method == "erc":
        w = erc_weights(cov)
    elif method == "hrp":
        w = hrp_weights(cov, corr)
    elif method == "inverse_vol":
        w = inverse_vol_weights(cov)
    else:
        raise ValueError(f"unknown construction method: {method}")
    w = np.minimum(w, max_weight)          # enforce cap for all methods
    return pd.Series(w / w.sum(), index=alpha.index)


# ------------------------------------------------- vol targeting
def vol_target_scale(weights: pd.Series, risk_model, target_vol: float) -> tuple:
    """Scale the whole portfolio down toward cash when predicted (ex-ante)
    volatility exceeds the target. Long-only, so we can de-risk but not
    lever up: scale factor is capped at 1.0.
    Returns (scaled_weights, ex_ante_vol, scale)."""
    w = weights.values
    ex_ante = risk_model.portfolio_risk(w)["ex_ante_vol"]
    scale = min(1.0, target_vol / max(ex_ante, 1e-9))
    return weights * scale, ex_ante, scale
