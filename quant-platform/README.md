# QRP — Quantitative Research Platform

**An end-to-end systematic equity research platform with live paper trading.**
Data → signals → risk model → constrained optimization → event-driven backtest → auto-generated research report → live paper-trading loop. The full lifecycle of a systematic strategy, in ~700 lines of documented Python.

```
        ┌──────────┐   ┌──────────┐   ┌────────────┐   ┌───────────┐
        │  Data    │──▶│ Signals  │──▶│ Risk Model │──▶│ Optimizer │
        │  layer   │   │ registry │   │ (PCA k=5)  │   │ (SLSQP)   │
        └──────────┘   └──────────┘   └────────────┘   └─────┬─────┘
                                                             ▼
        ┌──────────┐   ┌──────────┐   ┌─────────────────────────────┐
        │  Live    │◀──│ Targets  │◀──│  Event-driven backtester    │
        │  loop    │   │  .csv    │   │  (walk-forward, costs)      │
        └────┬─────┘   └──────────┘   └──────────────┬──────────────┘
             ▼                                       ▼
        Alpaca paper account                 research_report.html
        (or built-in simulator)              (self-contained, emailable)
```

## Quick start

```bash
pip install -r requirements.txt
python run_research.py     # backtest + report + target portfolio
python run_live.py         # trade the paper account to target
```

No API keys? Everything still runs: live market data falls back to a factor-structured synthetic universe, and the broker falls back to a built-in simulator with the same interface as Alpaca. Set `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` and the identical code trades a real Alpaca paper account.

## What it demonstrates (latest run, synthetic universe)

| Metric | Value |
|---|---|
| Annualized return, net of 10 bps costs | 15.1% |
| Sharpe ratio | 0.92 |
| Active return vs equal-weight benchmark | +3.1%/yr |
| Information ratio | 0.56 |
| Avg one-way turnover per rebalance | 3.8% |
| Total cost drag over 9 years | 0.82% |

The headline engineering result: adding a **turnover penalty** to the optimizer preserved the full information ratio while cutting trading costs by 4× — the difference between a backtest and an implementable strategy.

## Architecture principles

- **No look-ahead, anywhere.** Every rebalance decision uses data strictly prior to the decision date.
- **Alpha, risk, and cost are separated.** Signals propose, the risk model constrains, the optimizer arbitrates — the same separation used at institutional funds.
- **Strategy code never imports a vendor SDK.** The live loop talks to a broker *interface*; Alpaca and the simulator are interchangeable implementations.
- **Idempotent live cycle.** Run `run_live.py` twice; the second run trades nothing.
- **Reports are artifacts.** Every research run emits a self-contained HTML report with embedded charts — the unit of communication on a real desk.

## Repository layout

```
qrp/data.py        universe + live/synthetic price loading
qrp/signals.py     signal registry: momentum 12-1, trend, low-vol, reversal + IC tooling
qrp/risk_model.py  PCA statistical factor model (Σ = BFB' + D)
qrp/optimizer.py   max alpha − λ·risk − γ·turnover, long-only, position caps
qrp/backtest.py    event-driven walk-forward backtest with costs
qrp/broker.py      Alpaca paper broker + drop-in simulator
qrp/live.py        the rebalance-to-target trading cycle
qrp/report.py      auto-generated HTML research report
run_research.py    research pipeline entry point
run_live.py        live trading entry point
USER_GUIDE.md      full manual + plain-English glossary
```

## Honest limitations

Long-only; linear transaction costs (no market impact); monthly rebalancing (timing luck unmeasured); statistical rather than named factors; synthetic fallback data is calibrated but stylized — absolute performance numbers do not transfer to live markets, relative behavior does. This is a research and learning artifact, not investment advice.

## Extensions on the roadmap

Volatility targeting overlay · Expected-Shortfall risk contributions · square-root impact cost model · fundamental signals via SEC EDGAR · purged cross-validation for signal weights · GitHub Actions scheduling of the live loop.
