"""Lead figure for the research note. Reads results/exploration.json only.

One row per platform, three markers: the shortlist, third-party domains retrieved,
third-party domains cited, each with its 90% interval. Color follows the platform;
marker shape names the measure, so identity is never color alone.

Usage: uv run python experiments/012-source-churn-vs-shortlist/exploration/figure.py
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from aeo_research.plotting import GRID, INK, INK_MUTED, PLATFORM_COLORS, save_figure, theme

HERE = Path(__file__).resolve().parents[1]
P = json.loads((HERE / "results/exploration.json").read_text())["panels"]
ROWS = [("ChatGPT", "openai"), ("Claude API", "claude"), ("claude.ai", "claude"), ("Gemini", "gemini")]
MEAS = [("R", "o", "On the shortlist"), ("ret3", "D", "Third-party sites retrieved"), ("third", "s", "Third-party sites cited")]

theme()
fig, ax = plt.subplots(figsize=(12, 6.2))
OFF = {"R": -0.2, "ret3": 0.0, "third": 0.2}
for i, (label, ck) in enumerate(ROWS):
    c = PLATFORM_COLORS[ck]
    for key, marker, _ in MEAS:
        if key == "ret3" and not P[label]["has_ret"]:
            continue
        m = P[label][key]
        y = i + OFF[key]
        ax.plot(m["ci"], [y, y], color=c, lw=2, solid_capstyle="round", zorder=2)
        ax.plot(m["est"], y, marker=marker, ms=9, color=c, mec="white", mew=1.2, ls="none", zorder=3)
        ax.annotate(f"{m['est']*100:.0f}%", (m["ci"][1], y), xytext=(7, 0), textcoords="offset points",
                    va="center", fontsize=9, color=INK)
ax.set_yticks(range(len(ROWS)), [r[0] for r in ROWS], color=INK)
ax.invert_yaxis()
ax.set_xlim(0, 1)
ax.set_xticks([0, .25, .5, .75, 1], ["0%", "25%", "50%", "75%", "100%"], color=INK_MUTED)
ax.set_xlabel("Share repeated in another run of the same prompt", color=INK_MUTED)
ax.grid(axis="x", color=GRID, lw=.8)
ax.grid(axis="y", visible=False)
ax.set_axisbelow(True)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.tick_params(length=0)
ax.legend(handles=[Line2D([], [], marker=mk, color=INK_MUTED, mec="white", ls="none", ms=9, label=lb) for _, mk, lb in MEAS],
          loc="upper center", bbox_to_anchor=(.45, 1.14), ncol=3, frameon=False, fontsize=9.5)
fig.suptitle("AI changes its sources far more than its shortlist", x=.02, ha="left", fontsize=13, color=INK, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, .95))
save_figure(fig, HERE / "results/figures", "source_vs_shortlist")
