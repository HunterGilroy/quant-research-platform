"""
qrp.risk_model — Statistical multi-factor risk model.

Decomposes the stock covariance matrix into a small number of statistical
factors (via PCA) plus stock-specific (idiosyncratic) variance:

    Sigma = B F B' + D

where B = factor loadings (n_stocks x k), F = factor covariance (k x k,
diagonal here), D = diagonal idiosyncratic variances. This is the same
structure as commercial models (Barra/Axioma); they use named fundamental
factors, we let the data speak via principal components.

Why bother? Two reasons every institutional desk cares about:
1. Conditioning: Sigma built this way is well-conditioned and invertible
   even when n_stocks > n_days.
2. Attribution: portfolio risk splits into "factor risk" (systematic, cheap
   to hold) and "idio risk" (where stock-picking alpha should live).
"""
import numpy as np
import pandas as pd

TRADING_DAYS = 252


class RiskModel:
    def __init__(self, n_factors: int = 5):
        self.k = n_factors

    def fit(self, returns: pd.DataFrame):
        """Fit on a window of daily returns (days x stocks)."""
        self.assets = returns.columns
        X = returns.values - returns.values.mean(axis=0)
        # PCA via SVD (rows = days)
        U, S, Vt = np.linalg.svd(X, full_matrices=False)
        k = min(self.k, len(S))
        self.B = Vt[:k].T * S[:k] / np.sqrt(len(X))          # loadings scaled to daily vol units
        fac_rets = U[:, :k] * np.sqrt(len(X))                # unit-variance daily factor returns
        self.F = np.diag(np.var(fac_rets, axis=0, ddof=1))   # ~ identity by construction
        resid = X - fac_rets @ self.B.T
        self.D = np.maximum(np.var(resid, axis=0, ddof=1), 1e-8)
        self.explained = float(np.sum(S[:k] ** 2) / np.sum(S ** 2))
        return self

    def covariance(self) -> pd.DataFrame:
        """Full daily covariance Sigma = B F B' + D."""
        S = self.B @ self.F @ self.B.T + np.diag(self.D)
        return pd.DataFrame(S, index=self.assets, columns=self.assets)

    def portfolio_risk(self, w: np.ndarray) -> dict:
        """Ex-ante annualized vol, split into factor and idio components."""
        var_fac = float(w @ self.B @ self.F @ self.B.T @ w)
        var_idio = float(w @ np.diag(self.D) @ w)
        tot = np.sqrt((var_fac + var_idio) * TRADING_DAYS)
        return {
            "ex_ante_vol": tot,
            "factor_vol": np.sqrt(var_fac * TRADING_DAYS),
            "idio_vol": np.sqrt(var_idio * TRADING_DAYS),
            "pct_factor": var_fac / (var_fac + var_idio + 1e-18),
        }

    def factor_exposures(self, w: np.ndarray) -> np.ndarray:
        """Portfolio loading on each statistical factor (B' w)."""
        return self.B.T @ w
