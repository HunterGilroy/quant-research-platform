"""
qrp.signals — Signal registry.

Each signal is a function: prices (DataFrame, days x stocks) -> cross-sectional
score Series for the LAST date in the frame. Scores are winsorized and z-scored
cross-sectionally, so every signal speaks the same language and they can be
combined with simple weights. New signals register with @register("name").
"""
import numpy as np
import pandas as pd

REGISTRY = {}

def register(name):
    def deco(fn):
        REGISTRY[name] = fn
        return fn
    return deco

def zscore_xs(s: pd.Series, winsor: float = 3.0) -> pd.Series:
    """Cross-sectional z-score with winsorization at +/- `winsor` sigma."""
    z = (s - s.mean()) / (s.std(ddof=0) + 1e-12)
    return z.clip(-winsor, winsor)

# ----------------------------------------------------------------------
@register("momentum_12_1")
def momentum_12_1(prices: pd.DataFrame) -> pd.Series:
    """Classic 12-1 momentum: trailing 12-month return, skipping the most
    recent month (which reverses). Jegadeesh & Titman (1993)."""
    if len(prices) < 273:
        return pd.Series(0.0, index=prices.columns)
    p = prices.iloc[-1 - 21] / prices.iloc[-252] - 1.0
    return zscore_xs(p)

@register("reversal_1m")
def reversal_1m(prices: pd.DataFrame) -> pd.Series:
    """Short-term reversal: last month's losers tend to bounce. Sign is
    flipped so a HIGH score = attractive (recent loser)."""
    if len(prices) < 22:
        return pd.Series(0.0, index=prices.columns)
    r = prices.iloc[-1] / prices.iloc[-21] - 1.0
    return zscore_xs(-r)

@register("low_vol")
def low_vol(prices: pd.DataFrame) -> pd.Series:
    """Low-volatility anomaly: boring stocks earn more per unit of risk than
    they should. High score = low trailing 60-day volatility."""
    rets = prices.pct_change().iloc[-60:]
    vol = rets.std()
    return zscore_xs(-vol)

@register("trend_50_200")
def trend_50_200(prices: pd.DataFrame) -> pd.Series:
    """Price trend: 50-day vs 200-day moving average spread, vol-scaled."""
    if len(prices) < 200:
        return pd.Series(0.0, index=prices.columns)
    ma_f = prices.iloc[-50:].mean()
    ma_s = prices.iloc[-200:].mean()
    vol = prices.pct_change().iloc[-60:].std() + 1e-12
    return zscore_xs((ma_f / ma_s - 1.0) / vol)

# ----------------------------------------------------------------------
def compute_alpha(prices: pd.DataFrame, weights: dict) -> pd.Series:
    """Combine registered signals into one alpha score per stock.
    `weights` example: {"momentum_12_1": 0.4, "low_vol": 0.3, ...}"""
    combo = pd.Series(0.0, index=prices.columns)
    for name, w in weights.items():
        combo = combo + w * REGISTRY[name](prices)
    return zscore_xs(combo)

def information_coefficient(prices: pd.DataFrame, signal_name: str,
                            horizon: int = 21, step: int = 21) -> pd.Series:
    """Rolling rank IC: Spearman correlation between the signal today and
    forward `horizon`-day returns. The single most important number in
    signal research: |IC| of 0.02-0.05 is a real, tradeable signal."""
    fn = REGISTRY[signal_name]
    out = {}
    idx = prices.index
    for t in range(273, len(prices) - horizon, step):
        window = prices.iloc[:t]
        sig = fn(window)
        fwd = prices.iloc[t + horizon - 1] / prices.iloc[t - 1] - 1.0
        out[idx[t - 1]] = sig.rank().corr(fwd.rank())
    return pd.Series(out)
