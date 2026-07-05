# Making This LinkedIn-Ready

## Step 1 — Put it on GitHub (the link you'll share)

1. Create a repo named `quant-research-platform` at github.com/new (public).
2. Upload everything in this folder **except** `output/sim_broker_state.json` and `output/live_log.jsonl` (they're your local account state — add an `output/.gitkeep` instead, or commit the `research_report.html` so recruiters can click straight into results).
3. The README renders automatically as your project page. That page *is* the pitch.
4. Optional but strong: repo Settings → Pages → serve `output/research_report.html` so the live report has its own URL.

## Step 2 — The LinkedIn post (draft — edit to your voice)

---

I built an end-to-end systematic trading research platform in Python — the full lifecycle a quantitative fund runs, in miniature.

What it does:
📊 Scores 40 stocks daily on four classic signals (momentum, trend, low-vol, reversal)
🧮 Fits a PCA factor risk model and solves a constrained portfolio optimization
⏮ Backtests walk-forward with zero look-ahead and real transaction costs
📄 Auto-generates a self-contained HTML research report every run
🔁 Trades a live paper account to target — Alpaca API or a built-in simulator, behind one broker interface

The result that taught me the most: adding a turnover penalty to the optimizer cut trading costs 4× with no loss of performance (information ratio 0.56 either way). The gap between a good backtest and an implementable strategy is exactly that kind of engineering.

Design principles I held myself to:
• No look-ahead, anywhere — every decision uses only data available at decision time
• Alpha, risk, and cost separated into independent modules, like real desks do
• Strategy code never touches a vendor SDK — the live loop is broker-agnostic and idempotent
• Every run ends in a report, because on a real desk the report is the product

Repo (code, docs, sample report, and a full plain-English glossary): [YOUR GITHUB LINK]

Built as the capstone of a 20-project quantitative finance curriculum. Feedback from practitioners very welcome — especially on what I should break next.

#QuantitativeFinance #Python #SystematicTrading #DataScience #AlgorithmicTrading #FinTech

---

## Step 3 — Posting tips

- **Attach 1–2 images**: a screenshot of the report's equity-curve section, and/or the architecture diagram from the README. Posts with a visual get far more reach than link-only posts.
- **Never claim live profits.** The post above describes engineering and honest metrics from a disclosed research environment. That reads as competence; "my bot returns 15%" reads as a red flag to every professional who sees it.
- **Add it to your profile**: Profile → Add section → Projects → link the repo. Also pin the post to Featured.
- **When someone comments** asking how X works, answer with substance — those comment threads are where recruiters actually form opinions.
- **One honest line beats ten hype lines.** The turnover-penalty finding is your best material precisely because it's specific, measured, and true.
