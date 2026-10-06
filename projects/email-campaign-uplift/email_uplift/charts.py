"""Static charts for the README and slides (matplotlib, PNG).

Colors follow one rule: an email keeps its color in every chart (men's = blue, women's =
orange); baselines (no email, random targeting) are gray. Text is never drawn in series color.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

COLORS = {"mens": "#2a78d6", "womens": "#eb6834", "mixed": "#1baf7a", "baseline": "#8f8e89"}
LABELS = {"mens": "Men's email", "womens": "Women's email"}
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"
METRIC_TITLES = {
    "visit": ("Visit rate", "percentage points"),
    "conversion": ("Purchase rate", "percentage points"),
    "spend": ("Spend per customer", "dollars"),
}


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _figure(w, h, **kw):
    fig, axes = plt.subplots(figsize=(w, h), facecolor=SURFACE, **kw)
    return fig, axes


def _save(fig, path: Path):
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def _scale(metric):
    return 100.0 if metric in ("visit", "conversion") else 1.0


def _fmt(metric, v):
    return f"+{v:.2f} pp" if metric != "spend" else f"+${v:.2f}"


def lift_overview(lift: pd.DataFrame, path: Path):
    """Lift vs no email with 95% CI, one panel per outcome."""
    fig, axes = _figure(10, 2.6, ncols=3)
    for ax, metric in zip(axes, ["visit", "conversion", "spend"]):
        _style(ax)
        k = _scale(metric)
        rows = lift[(lift["metric"] == metric) & (lift["baseline"] == "control")]
        for i, arm in enumerate(["mens", "womens"]):
            r = rows[rows["treatment"] == arm].iloc[0]
            y = 1 - i
            ax.plot([r.abs_ci_low * k, r.abs_ci_high * k], [y, y], color=COLORS[arm], lw=2,
                    solid_capstyle="round")
            ax.plot(r.abs_lift * k, y, "o", ms=9, color=COLORS[arm], mec=SURFACE, mew=2)
            ax.annotate(_fmt(metric, r.abs_lift * k), (r.abs_ci_high * k, y),
                        xytext=(8, 0), textcoords="offset points", va="center",
                        fontsize=9, color=INK)
        ax.axvline(0, color=INK_2, lw=1)
        ax.set_yticks([1, 0], [LABELS["mens"], LABELS["womens"]] if metric == "visit" else ["", ""])
        ax.set_ylim(-0.6, 1.6)
        lo, hi = ax.get_xlim()
        ax.set_xlim(min(lo, 0), hi + (hi - min(lo, 0)) * 0.45)
        title, unit = METRIC_TITLES[metric]
        ax.set_title(f"{title}\nlift vs no email ({unit})", loc="left", fontsize=10, color=INK)
    fig.suptitle("Both emails raised visits, purchases and spend; the men's email by more "
                 "(dots = estimate, bars = 95% CI)", x=0.01, ha="left", fontsize=11, color=INK, y=1.1)
    _save(fig, path)


def segment_forest(seg: pd.DataFrame, metric: str, path: Path):
    """Lift by segment level for both emails, grouped by dimension."""
    rows = seg[seg["metric"] == metric]
    order = ["Past purchase", "Customer type", "Past-year spend", "Recency", "Channel", "Location"]
    level_order = {
        "Recency": ["1-3 months", "4-6 months", "7-9 months", "10-12 months"],
        "Past-year spend": ["$0-100", "$100-200", "$200-350", "$350-500", "$500+"],
    }
    labels, positions, pos, group_tops, y = [], [], {}, [], 0.0
    for dim in order:
        levels = level_order.get(dim, sorted(rows.loc[rows["dimension"] == dim, "level"].unique()))
        group_tops.append((dim, y))
        for level in levels:
            labels.append(level)
            positions.append(y)
            pos[(dim, level)] = y
            y -= 1
        y -= 0.9
    fig, ax = _figure(8, 0.32 * len(labels) + 2.5)
    _style(ax)
    k = _scale(metric)
    for arm, offset in [("mens", 0.17), ("womens", -0.17)]:
        r = rows[rows["treatment"] == arm]
        ys = np.array([pos[(d, l)] + offset for d, l in zip(r["dimension"], r["level"])])
        ax.hlines(ys, r["abs_ci_low"] * k, r["abs_ci_high"] * k, color=COLORS[arm], lw=2)
        ax.plot(r["abs_lift"] * k, ys, "o", ms=6, color=COLORS[arm], mec=SURFACE, mew=1.5,
                label=LABELS[arm])
    ax.axvline(0, color=INK_2, lw=1)
    ax.set_yticks(positions, labels, fontsize=9)
    for dim, top in group_tops:
        ax.text(ax.get_xlim()[0], top + 0.75, dim, fontsize=9.5, fontweight="bold", color=INK,
                ha="left")
    ax.set_ylim(y + 0.5, 1.6)
    title, unit = METRIC_TITLES[metric]
    ax.set_xlabel(f"{title} lift vs no email ({unit}), 95% CI", color=INK_2, fontsize=9)
    ax.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK)
    ax.set_title(f"{title} lift by customer segment", loc="left", fontsize=11, color=INK, pad=18)
    _save(fig, path)


def uplift_curves(curves: pd.DataFrame, path: Path, fraction: float = 0.5):
    """Incremental revenue vs share of list emailed: model ranking vs random."""
    fig, axes = _figure(10, 3.6, ncols=2, sharey=True)
    for ax, arm in zip(axes, ["mens", "womens"]):
        _style(ax)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        c = curves[curves["treatment"] == arm]
        x = np.concatenate([[0], c["fraction"] * 100])
        model = np.concatenate([[0], c["incremental"] / 1000])
        rand = np.concatenate([[0], c["incremental_random"] / 1000])
        ax.plot(x, rand, color=COLORS["baseline"], lw=2, ls=(0, (4, 3)), label="Random selection")
        ax.plot(x, model, color=COLORS[arm], lw=2, label="Ranked by uplift model")
        at = c[np.isclose(c["fraction"], fraction)].iloc[0]
        ax.plot(fraction * 100, at["incremental"] / 1000, "o", ms=8, color=COLORS[arm],
                mec=SURFACE, mew=2)
        ax.annotate(f"top {fraction:.0%}: ${at['incremental'] / 1000:.1f}k\nrandom: "
                    f"${at['incremental_random'] / 1000:.1f}k",
                    (0.03, 0.95), xycoords="axes fraction", va="top", ha="left",
                    fontsize=9, color=INK)
        ax.set_title(LABELS[arm], loc="left", fontsize=10.5, color=INK)
        ax.set_xlabel("% of customers emailed", color=INK_2, fontsize=9)
        ax.set_xlim(0, 100)
        ax.legend(loc="lower right", frameon=False, fontsize=8.5, labelcolor=INK)
    axes[0].set_ylabel("Incremental spend, $ thousands\n(64,000 customers, 2 weeks)",
                       color=INK_2, fontsize=9)
    fig.suptitle("Ranking by the uplift model pays off for the women's email; the men's email "
                 "works about equally for everyone", x=0.01, ha="left", fontsize=11, color=INK, y=1.02)
    _save(fig, path)


def policy_bars(policies: pd.DataFrame, path: Path, population: int):
    """Expected two-week spend for each way of using a half-list budget."""
    p = policies.iloc[::-1]
    fig, ax = _figure(8.5, 0.5 * len(p) + 1.2)
    _style(ax)
    ys = np.arange(len(p))
    colors = [COLORS.get(e, COLORS["baseline"]) for e in p["color_key"]]
    total = p["per_customer"] * population / 1000
    lo = p["ci_low"] * population / 1000
    hi = p["ci_high"] * population / 1000
    ax.barh(ys, total, height=0.6, color=colors, edgecolor=SURFACE, linewidth=2)
    ax.hlines(ys, lo, hi, color=INK_2, lw=1.2)
    for yv, t, h in zip(ys, total, hi):
        ax.text(h + 1, yv, f"${t:.1f}k", va="center", fontsize=9, color=INK)
    ax.set_yticks(ys, p["policy"], fontsize=9)
    ax.set_xlabel("Expected spend over two weeks, $ thousands (64,000 customers), 95% CI",
                  color=INK_2, fontsize=9)
    ax.set_xlim(0, hi.max() * 1.15)
    ax.set_title("What a half-list budget buys", loc="left", fontsize=11, color=INK)
    _save(fig, path)
