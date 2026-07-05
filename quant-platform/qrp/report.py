"""
qrp.report — Auto-generated HTML research report.

Turns a backtest result into a single self-contained research_report.html
(charts embedded as base64 — email it, host it, open it anywhere).
Sections: performance summary, equity curve vs benchmark, drawdown,
signal ICs, ex-ante risk decomposition, turnover, current target portfolio.
"""
import base64
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams.update({"figure.dpi": 110, "font.size": 9, "axes.grid": True,
                     "grid.alpha": 0.3, "axes.spines.top": False, "axes.spines.right": False})

NAVY, ACCENT = "#1E2761", "#C55A11"


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _img(b64):  return f'<img src="data:image/png;base64,{b64}" style="width:100%;max-width:900px"/>'


def _stats_table(stats: dict) -> str:
    fmt = {"Ann. Return": "{:.1%}", "Ann. Vol": "{:.1%}", "Sharpe": "{:.2f}",
           "Max Drawdown": "{:.1%}", "Active Return": "{:.1%}",
           "Tracking Error": "{:.1%}", "Information Ratio": "{:.2f}"}
    rows = "".join(f"<tr><td>{k}</td><td style='text-align:right'>{fmt.get(k, '{:.3f}').format(v)}</td></tr>"
                   for k, v in stats.items())
    return f"<table class='t'>{rows}</table>"


def generate_report(bt: dict, stats: dict, ic_table: pd.DataFrame,
                    source: str, out_path: str = "output/research_report.html"):
    r = bt["returns"]; r = r[r.index >= r.ne(0).idxmax()]
    b = bt["benchmark"].reindex(r.index)
    curve, bcurve = (1 + r).cumprod(), (1 + b).cumprod()

    # equity + drawdown
    fig, ax = plt.subplots(2, 1, figsize=(10, 5.5), sharex=True,
                           gridspec_kw={"height_ratios": [2, 1]})
    ax[0].plot(curve, color=NAVY, lw=1.5, label="Strategy")
    ax[0].plot(bcurve, color="#999", lw=1.2, label="Equal-weight benchmark")
    ax[0].set_title("Growth of $1, net of costs"); ax[0].legend()
    ax[1].plot(curve / curve.cummax() - 1, color=NAVY, lw=1)
    ax[1].set_title("Drawdown")
    img_equity = _fig_to_b64(fig)

    # IC bars
    fig, ax = plt.subplots(figsize=(8, 3))
    ic_mean = ic_table.mean()
    ic_mean.plot(kind="bar", ax=ax, color=[NAVY if v > 0 else ACCENT for v in ic_mean])
    ax.axhline(0, color="k", lw=0.8)
    ax.set_title("Mean rank IC by signal (21-day horizon)"); ax.set_ylabel("IC")
    img_ic = _fig_to_b64(fig)

    # risk decomposition + turnover
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.2))
    bt["risk"][["factor_vol", "idio_vol"]].plot(ax=ax[0], lw=1.3, color=[NAVY, ACCENT])
    ax[0].set_title("Ex-ante risk decomposition (annualized)")
    bt["turnover"].plot(ax=ax[1], color=NAVY, lw=1.2)
    ax[1].set_title("One-way turnover per rebalance")
    img_risk = _fig_to_b64(fig)

    # current portfolio
    top = bt["final_weights"].sort_values(ascending=False)
    top = top[top > 1e-4]
    fig, ax = plt.subplots(figsize=(10, 3))
    top.plot(kind="bar", ax=ax, color=NAVY)
    ax.set_title(f"Current target portfolio ({len(top)} names)"); ax.set_ylabel("weight")
    img_port = _fig_to_b64(fig)

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Systematic Research Report</title>
<style>
 body {{ font-family: Georgia, serif; max-width: 960px; margin: 30px auto; color: #1a2033; padding: 0 16px; }}
 h1 {{ color: {NAVY}; border-bottom: 3px solid {NAVY}; padding-bottom: 8px; }}
 h2 {{ color: {NAVY}; margin-top: 34px; }}
 .meta {{ color: #666; font-size: 0.9em; }}
 .t {{ border-collapse: collapse; font-family: Arial, sans-serif; font-size: 0.92em; }}
 .t td {{ border: 1px solid #d8dee9; padding: 6px 14px; }}
 .warn {{ background: #fdf3e7; border-left: none; padding: 10px 14px; font-size: 0.9em; border-radius: 6px;}}
</style></head><body>
<h1>Systematic Equity Research Report</h1>
<p class="meta">Generated {pd.Timestamp.now():%Y-%m-%d %H:%M} · data source: <b>{source}</b> ·
monthly rebalance · 10 bps costs · max position 8% · PCA risk model (5 factors)</p>

<h2>1. Performance Summary</h2>
{_stats_table(stats)}

<h2>2. Equity Curve &amp; Drawdown</h2>
{_img(img_equity)}

<h2>3. Signal Research — Information Coefficients</h2>
<p>Rank IC = Spearman correlation between each signal and next-month returns,
measured walk-forward. Sustained |IC| of 0.02–0.05 is institutionally meaningful.</p>
{_img(img_ic)}

<h2>4. Ex-Ante Risk &amp; Turnover</h2>
<p>Risk the model <i>predicted</i> at each rebalance, split into factor
(systematic) and idiosyncratic components, alongside realized trading.</p>
{_img(img_risk)}

<h2>5. Current Target Portfolio</h2>
{_img(img_port)}
<p>This target is what <code>run_live.py</code> trades toward on the paper account.</p>

<div class="warn"><b>Limitations.</b> {"Synthetic factor-structured data — relative conclusions transfer, absolute performance does not; re-run with live data on Colab." if source == "synthetic" else "Live data run."}
Long-only, linear costs, monthly rebalancing, statistical (unnamed) factors, no borrow/financing modeling. Research artifact — not investment advice.</div>
</body></html>"""
    import os
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(html)
    return out_path
