"""Render Figures 3 and 5 of the Serendipity individual report.

Data comes from the committed reports in evals/serendipity/reports/:
component-reliability-2026-09-24-prompt-3cf0760f.json, -2026-10-08-production-before-promotion.json,
-2026-10-08-promoted.json, -2026-10-09-current.json, and the five-agent Scenario evidence trace.

Run: uv run --no-project --with matplotlib python make_charts.py
"""

from pathlib import Path

import matplotlib.pyplot as plt

OUT = Path(__file__).parent
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#d9d8d4"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # validated categorical slots; 1-3 pass all-pairs

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 9,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

CONFIGS = ["gpt-6-luna medium", "gpt-6-luna low", "gpt-5.6-luna medium"]
PATTERNS = ["Restraint", "Selection", "Routing", "Recall"]
# Paired runs on 13 Oct 2026, current skill and cases, five runs per case:
# low and medium from experiment-reasoning-suite-2026-10-13.json, gpt-5.6-luna
# from experiment-model-medium-2026-10-13.json (paired with gpt-6-luna medium).
PASSES = {  # (passes, runs) per pattern
    "Restraint": [(27, 30), (29, 30), (22, 30)],
    "Selection": [(71, 75), (55, 75), (70, 75)],
    "Routing": [(95, 105), (74, 105), (103, 105)],
    "Recall": [(18, 20), (19, 20), (18, 20)],
}
TOTAL = [211, 177, 213]
USD_PER_1000_PASSES = [1.74, 1.55, 3.43]


def figure_3() -> None:
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.0, 3.0), gridspec_kw={"width_ratios": [1.9, 1]})
    width = 0.26
    for i, config in enumerate(CONFIGS):
        xs = [p + (i - 1) * width for p in range(len(PATTERNS))]
        rates = [100 * PASSES[p][i][0] / PASSES[p][i][1] for p in PATTERNS]
        a.bar(xs, rates, width=width * 0.9, color=SERIES[i], label=config, zorder=2)
        for x, r in zip(xs, rates):
            a.text(x, r + 1.5, f"{r:.0f}", ha="center", va="bottom", fontsize=6.5, color=MUTED)
    a.set_xticks(range(len(PATTERNS)), PATTERNS)
    a.set_ylim(0, 112)
    a.set_yticks([0, 25, 50, 75, 100])
    a.set_ylabel("Runs passed (%)")
    a.yaxis.grid(True, color=GRID, linewidth=0.6, zorder=0)
    a.set_title("(a) Pass rate by behaviour pattern", loc="left", fontsize=9, color=INK)
    a.legend(frameon=False, fontsize=7, loc="lower left", ncol=3, bbox_to_anchor=(0, -0.3))

    for i, config in enumerate(CONFIGS):
        b.scatter(USD_PER_1000_PASSES[i], 100 * TOTAL[i] / 230, s=40, color=SERIES[i], zorder=3,
                  edgecolor="white", linewidth=1)
    labels = ["6 medium", "6 low", "5.6 medium"]
    offsets = [(6, 4), (6, -3), (-6, -12)]
    for i, label in enumerate(labels):
        b.annotate(label, (USD_PER_1000_PASSES[i], 100 * TOTAL[i] / 230), textcoords="offset points",
                   xytext=offsets[i], ha="right" if offsets[i][0] < 0 else "left", fontsize=7, color=INK)
    b.set_xlim(1, 4)
    b.set_ylim(70, 100)
    b.set_xlabel("USD per 1,000 passing runs")
    b.set_ylabel("All runs passed (%)")
    b.grid(True, color=GRID, linewidth=0.6, zorder=0)
    b.set_title("(b) Accuracy against cost", loc="left", fontsize=9, color=INK)

    fig.tight_layout()
    fig.savefig(OUT / "figure-3.png", dpi=300, bbox_inches="tight", facecolor="white")


def figure_5() -> None:
    stages = [
        "Retrieved",
        "Kept by Librarian's assessment",
        "Kept after Serendipity's selection",
        "Cited in the released reply",
    ]
    share = [0.97, 0.85, 0.85, 0.53]
    fig, ax = plt.subplots(figsize=(6.0, 1.9))
    colors = ["#a8a7a2", "#a8a7a2", SERIES[0], "#a8a7a2"]
    ys = list(range(len(stages)))[::-1]
    ax.barh(ys, share, color=colors, height=0.6, zorder=2)
    for y, s in zip(ys, share):
        ax.text(s + 0.01, y, f"{s:.2f}", va="center", fontsize=8, color=INK)
    ax.set_yticks(ys, stages)
    ax.set_xlim(0, 1.08)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xlabel("Share of required book evidence")
    ax.xaxis.grid(True, color=GRID, linewidth=0.6, zorder=0)
    ax.tick_params(axis="y", length=0)
    fig.tight_layout()
    fig.savefig(OUT / "figure-5.png", dpi=300, bbox_inches="tight", facecolor="white")


if __name__ == "__main__":
    figure_3()
    figure_5()
