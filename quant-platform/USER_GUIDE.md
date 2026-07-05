# QRP User Guide & Glossary

This guide assumes zero prior quant-finance knowledge. Part 1 tells you exactly how to run everything. Part 2 explains what each component does and why it exists. Part 3 is a plain-English glossary of every term the platform uses.

---

## Part 1 — How to run everything

### Setup (once)

```bash
pip install -r requirements.txt
```

On Google Colab: upload the folder (or clone your GitHub repo), then run the same commands in a cell prefixed with `!`.

### The research run

```bash
python run_research.py
```

What happens, in order:
1. **Data loads.** If the internet and `yfinance` are available, it downloads ~10 years of daily prices for 40 large US stocks. If not, it generates a synthetic stock universe with realistic statistical structure and tells you so.
2. **Signals are measured.** Each of the four signals is tested walk-forward: "if I had computed this signal every month in the past, how well did it predict the next month's returns?" The answer is the IC printed to the screen.
3. **The backtest runs.** Month by month through history, the platform re-computes signals, re-fits the risk model, re-optimizes the portfolio, pays trading costs, and records what happened.
4. **Three files appear in `output/`:**
   - `research_report.html` — open it in any browser. This is your deliverable.
   - `targets.csv` — the portfolio the strategy wants to hold *today*.
   - `prices_latest.csv` — reference prices for the live loop.

### The live paper-trading run

```bash
python run_live.py
```

What happens: it reads `targets.csv`, connects to a broker, compares what the account *holds* to what it *should hold*, and submits exactly the orders that close the gap (sells first, then buys; trades under $25 are skipped as dust). Run it again immediately and it submits zero orders — the account is already at target.

**Which broker?**
- Out of the box: a built-in **simulator** — a fake brokerage account stored in `output/sim_broker_state.json` that fills your orders with realistic slippage. Zero risk, zero signup.
- Real paper trading: create a free account at alpaca.markets, generate *paper* API keys, then:
  ```bash
  export ALPACA_API_KEY="your_key"
  export ALPACA_SECRET_KEY="your_secret"
  python run_live.py
  ```
  The identical code now trades a real Alpaca paper account (fake money, real market). Nothing else changes — that's the point of the broker interface.

**Automating it:** on any machine that's on at the right time, `crontab -e` and add
`45 15 * * 1-5 cd /path/to/quant-platform && python run_live.py`
to run the cycle every weekday at 15:45. Re-run `run_research.py` monthly to refresh targets.

### Changing the strategy

Open `run_research.py` and edit `SIGNAL_WEIGHTS` — the blend of signals. Open `qrp/optimizer.py` defaults to change risk aversion, the turnover penalty, or the 8% position cap. To add a brand-new signal, copy any function in `qrp/signals.py`, decorate it with `@register("your_name")`, and add it to the blend. That registry pattern is exactly how signal libraries work at real funds.

---

## Part 2 — What each component is, and why it exists

**Data layer (`qrp/data.py`).** Everything downstream is only as good as the prices going in. The synthetic fallback isn't a toy: it embeds a real momentum effect and a real factor structure, so the rest of the platform has genuine statistical signal to find — which is how you can verify the machinery works.

**Signal registry (`qrp/signals.py`).** A *signal* is a recipe that scores every stock on the same scale. This platform ships four classics: 12-1 momentum (past winners keep winning), 50/200-day trend, low volatility (boring stocks are underpriced), and 1-month reversal (last month's losers bounce). Scores are standardized so they can be blended with simple weights.

**Risk model (`qrp/risk_model.py`).** Answers "if I hold this portfolio, how much could it swing, and *why*?" It compresses 40 stocks' co-movements into 5 statistical factors plus stock-specific noise. The "why" matters: risk from common factors is cheap market exposure; risk that's stock-specific is where skill-based returns should live.

**Optimizer (`qrp/optimizer.py`).** The arbiter. Signals say "buy these," the risk model says "that's concentrated," trading costs say "you traded yesterday, are you sure?" The optimizer maximizes signal score minus a risk penalty minus a trading penalty, subject to: fully invested, no shorting, no stock above 8%. The turnover penalty is the single most professional line in the codebase — this run showed it cutting trading costs 4× at zero cost to performance.

**Backtester (`qrp/backtest.py`).** A time machine with rules. The cardinal rule is *no look-ahead*: at each simulated month, the platform may only use data that existed before that month. Violating this rule is the #1 way beginners produce backtests that look brilliant and lose money live.

**Broker + live loop (`qrp/broker.py`, `qrp/live.py`).** The bridge from research to reality. The design principle: strategy code talks to a *broker interface*, never to Alpaca directly, so switching between the simulator and a real paper account requires zero code changes. The loop is *idempotent* — safe to run repeatedly.

**Report generator (`qrp/report.py`).** On a real desk, the unit of communication is the research report, not the code. Every run produces a self-contained HTML file anyone can open — performance, signal quality, risk decomposition, current portfolio, and stated limitations.

---

## Part 3 — Glossary (plain English)

**Alpha** — return above what mere market exposure explains; the part attributable to skill. Also used loosely for the signal score that tries to predict it.

**Active return** — your return minus the benchmark's. The "did the cleverness add anything" number. Here: +3.1%/yr.

**Backtest** — simulating a strategy on historical data under strict rules, to estimate how it would have behaved.

**Benchmark** — the dumb alternative you must beat to justify complexity. Here: an equal-weight portfolio of the same stocks.

**Cost drag** — cumulative performance lost to trading costs. Small per trade, deadly in aggregate.

**Cross-sectional** — comparing stocks *against each other* on the same day (who's best today?), versus time-series (is this stock better than it used to be?).

**Drawdown** — the fall from a portfolio's previous peak. Max drawdown is the worst such fall — the "how much pain, at the worst moment" number.

**Event-driven backtest** — a backtest that steps through time chronologically, making each decision only with information available at that moment.

**Factor** — a common force moving many stocks at once (the market itself, value vs growth, size…). Factor *exposure* is how strongly your portfolio leans on each force.

**Idempotent** — safe to run twice; the second run changes nothing. A must-have for anything automated.

**Idiosyncratic risk** — stock-specific risk not explained by common factors. Where genuine stock-picking skill shows up.

**Information Coefficient (IC)** — the correlation between a signal's scores today and stocks' actual returns next month. Sounds tiny at 0.03; sustained, that's a real edge. The single most-watched number in signal research.

**Information Ratio (IR)** — active return divided by tracking error: how much beat-the-benchmark per unit of dare-to-be-different. 0.5+ is respectable.

**Long-only** — only buying stocks, never betting against them (no short selling).

**Look-ahead bias** — accidentally letting tomorrow's data leak into today's decision. Produces spectacular fake backtests.

**Momentum (12-1)** — the tendency of the past year's winners (excluding the most recent month) to keep winning. One of the most robust effects ever documented.

**Paper trading** — trading with fake money through a real (or simulated) brokerage, to test a system's plumbing without risk.

**PCA (principal component analysis)** — a statistical method that finds the few independent "directions" explaining most of how stocks co-move; our risk model's engine.

**Position cap** — a maximum weight per stock (here 8%), so no single mistake can sink the ship.

**Rebalance** — periodically trading the portfolio back to its target weights (here monthly).

**Reversal (short-term)** — last month's extreme losers tend to bounce, and winners to fade, over the next month.

**Risk aversion (λ)** — the optimizer knob trading expected signal against risk. Higher = more diversified, tamer portfolio.

**Sharpe ratio** — return earned per unit of volatility taken. The standard risk-adjusted scorecard; ~1 is very good for a simple long-only strategy.

**Signal** — any systematic, repeatable recipe that ranks stocks by expected attractiveness.

**Slippage** — the gap between the price you expected and the price you actually got. The simulator charges 5 bps of it on every fill to keep you honest.

**Tracking error** — the volatility of your active return; how far you *dare* to deviate from the benchmark.

**Turnover** — how much of the portfolio is traded at a rebalance (one-way). High turnover = high costs = the silent killer of paper alpha.

**Walk-forward** — evaluating a model by repeatedly training on the past and testing on the immediately following period, marching through history. The honest way.

**Winsorize** — clipping extreme outliers (here at ±3 standard deviations) so one crazy data point can't hijack a signal.

**Z-score** — restating a number as "how many standard deviations from average," so different signals become comparable and blendable.
