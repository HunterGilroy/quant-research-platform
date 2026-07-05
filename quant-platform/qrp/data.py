"""
qrp.data — Data layer.

Loads daily prices for the equity universe. Tries live data (yfinance) first;
falls back to a calibrated synthetic generator with genuine factor structure
(market/value/size factors + slow-moving stock-specific drift), so signals,
the risk model, and the optimizer all have real statistical structure to find.
"""
import numpy as np
import pandas as pd

# 40 liquid US large caps across sectors (used when live data is available)
LIVE_UNIVERSE = [
    "AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA","AVGO","ORCL","CRM",
    "JPM","BAC","WFC","GS","MS","V","MA","BRK-B","BLK","SCHW",
    "JNJ","UNH","PFE","MRK","ABBV","LLY","TMO","ABT",
    "XOM","CVX","COP","PG","KO","PEP","WMT","HD","MCD","CAT","BA","GE",
]

TRADING_DAYS = 252


def synthetic_universe(n_stocks: int = 40, start: str = "2015-01-01",
                       end: str = "2024-12-31", seed: int = 21) -> pd.DataFrame:
    """Simulate an equity universe with a true 3-factor structure plus
    slowly mean-reverting stock-specific drift (creates real momentum),
    so every downstream component has signal to detect."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, end)
    T, n = len(dates), n_stocks

    # --- factor returns: market, value, size ---
    f_mu = np.array([0.07, 0.02, 0.01]) / TRADING_DAYS
    f_vol = np.array([0.16, 0.06, 0.05]) / np.sqrt(TRADING_DAYS)
    F = rng.standard_normal((T, 3)) * f_vol + f_mu

    # --- loadings ---
    B = np.column_stack([
        rng.normal(1.0, 0.25, n),      # market beta
        rng.normal(0.0, 0.6, n),       # value loading
        rng.normal(0.0, 0.6, n),       # size loading
    ])

    # --- slow stock-specific drift (OU) -> genuine momentum in the cross-section ---
    drift = np.zeros((T, n))
    theta, drift_vol = 0.005, 0.0009
    for t in range(1, T):
        drift[t] = drift[t-1] * (1 - theta) + rng.standard_normal(n) * drift_vol * np.sqrt(theta)

    idio_vol = rng.uniform(0.18, 0.35, n) / np.sqrt(TRADING_DAYS)
    idio = rng.standard_normal((T, n)) * idio_vol

    rets = F @ B.T + drift + idio
    tickers = [f"STK{i:02d}" for i in range(n)]
    prices = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=dates, columns=tickers)
    return prices


def load_prices(start: str = "2015-01-01", end: str = None):
    """Returns (prices, source). Live via yfinance when reachable, else synthetic."""
    try:
        import yfinance as yf
        px = yf.download(LIVE_UNIVERSE, start=start, end=end,
                         auto_adjust=True, progress=False)["Close"]
        px = px.dropna(how="all").ffill().dropna(axis=1, thresh=int(len(px) * 0.95)).dropna()
        if len(px) < 500 or px.shape[1] < 20:
            raise RuntimeError("insufficient live data")
        print(f"[data] live: {px.shape[0]} days x {px.shape[1]} stocks")
        return px, "live"
    except Exception as e:
        print(f"[data] live unavailable ({type(e).__name__}); using factor-structured synthetic universe")
        return synthetic_universe(start=start), "synthetic"
