# quant-research-platform
An end-to-end systematic equity research platform with automated daily paper trading. Every weekday, GitHub Actions scans the S&P 500 on four signals, runs a walk-forward tournament between four portfolio-construction methods (mean-variance, risk parity, HRP, inverse-vol), applies a volatility-targeting overlay, and trades an Alpaca paper account to target — then commits its own research report to this repo.
How It Works
Every weekday at 10:45 AM ET, GitHub Actions runs the full research-to-execution pipeline with no human involvement:
1. Universe & data. The platform pulls the current S&P 500 constituent list (Wikipedia, with a GitHub dataset mirror as fallback) and downloads two years of daily prices for all ~500 stocks via yfinance.
2. Signal scoring. Every stock is scored on a blend of three classic cross-sectional signals — 12-1 momentum (Jegadeesh & Titman, 1993), 50/200-day trend, and 1-month reversal. Scores are winsorized and z-scored so signals are comparable, then combined with fixed weights. The top ~20 names by combined score become the candidate portfolio.
3. Construction tournament. Rather than committing to one way of weighting those names, the platform runs a walk-forward tournament between four portfolio-construction philosophies: an alpha-aware mean-variance optimizer with a turnover penalty, Equal Risk Contribution (classic risk parity, Qian 2005), Hierarchical Risk Parity (López de Prado 2016), and inverse-volatility weighting. Each method is backtested over the trailing 12 months using only data available at each point in time. The optimizer is the incumbent; a challenger must beat it by a Sharpe margin of +0.25 to take over — hysteresis that prevents the system from flip-flopping between methods on noise.
4. Volatility targeting. A PCA factor risk model (Σ = BFB′ + D) estimates the chosen portfolio's ex-ante volatility. If predicted risk exceeds 15% annualized, positions are scaled down proportionally and the remainder is held in cash — automatic de-risking in turbulent markets.
5. Disciplined execution. New targets are only written when the portfolio has drifted more than 10% (one-way) from the current one — daily research, infrequent trading. When a rebalance triggers, the live loop reads the targets, queries the Alpaca paper account's actual equity and positions, computes the difference, and submits exactly the orders that close the gap (sells first, dust trades under $25 skipped). The loop is idempotent: run twice, the second run trades nothing.
6. Reporting & state. Every run generates a self-contained HTML research brief — ranked watchlist, tournament results, predicted risk, target portfolio — and commits it back to this repo along with the target state, so each day's run remembers the last. The commit history is the audit trail.
Key architecture principles: no look-ahead anywhere (every decision uses only data prior to the decision date); alpha, risk, and cost handled by separate modules; strategy code talks to a broker interface (Alpaca and a built-in simulator are interchangeable), never a vendor SDK directly.
Run It Yourself
No API keys required — without them, market data falls back to a calibrated synthetic universe and the broker falls back to a built-in simulator with the same interface as Alpaca.
In Google Colab (or any Python 3.11+ environment):
python!git clone https://github.com/HunterGilroy/quant-research-platform.git
%cd quant-research-platform/quant-platform
!pip install -r requirements.txt
python!python run_daily.py     # scan the S&P 500, run the tournament, write targets + brief
!python run_live.py      # trade the (simulated) paper account to target
Open output/daily_brief.html for the ranked watchlist and tournament results. Run run_live.py a second time to see the idempotency check: zero orders.
To trade a real Alpaca paper account (free, fake money, real markets): create paper API keys at alpaca.markets, then set ALPACA_API_KEY and ALPACA_SECRET_KEY as environment variables before running. The identical code connects automatically.
To automate it: fork this repo, add your Alpaca keys as repository secrets (Settings → Secrets and variables → Actions), and the included workflow (.github/workflows/daily.yml) runs the full pipeline every weekday.
Limitations
Stated plainly, because honest caveats are the difference between research and marketing:

Paper trading only. Nothing here is investment advice, and this system has not demonstrated it can beat a benchmark — in backtesting on real 2015–2024 data, an earlier configuration underperformed an equal-weight benchmark (negative information ratio), driven by a low-volatility signal that failed for identifiable, regime-specific reasons. That finding motivated the current design; it does not guarantee it.
Signal weights are fixed and partly informed by past results — adjusting the blend after observing which signal worked is in-sample reasoning. A more robust version would select signal weights walk-forward, as the construction method already is.
The method tournament has its own regime risk. Selecting the construction method by trailing Sharpe assumes recent relative performance persists; the hysteresis margin limits churn but cannot make the assumption true.
Survivorship bias in the universe. Using today's S&P 500 list means historical evaluation is run on stocks that survived; fine for a forward-looking daily scan, misleading for backtest conclusions.
Simplified frictions. Costs are modeled as linear (10 bps) with no market impact; execution uses market orders with no limit-order logic or partial-fill handling. Long-only; no shorting, leverage, or borrow costs.
Single estimation horizon and monthly-scale rebalancing introduce horizon risk and timing luck; statistical (PCA) factors are unnamed and can shift meaning across regimes.
Live evaluation is in progress: a 90-day paper-trading run against a SPY benchmark, results to be published in this repo either way.
